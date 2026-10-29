"""Phase 2 packet-loss probe: send a steady packet stream over a real network and record which packets come back.

Standard library only, no root needed. Works on macOS and Linux.

Two modes:
  icmp  (default) echo requests ("pings") to a host, for example your Wi-Fi router or 1.1.1.1
  udp   packets to realworld/echo_server.py running on another computer

Examples (run from the repo folder):
  python3 realworld/probe.py --label wifi --target gateway --duration 600
  python3 realworld/probe.py --label wifi_internet --target 1.1.1.1 --duration 600
  python3 realworld/probe.py --label hotspot --target gateway --duration 600
  python3 realworld/probe.py --mode udp --target 192.168.1.23 --label lan_udp --duration 600

Every packet carries its own sequence number and send time, so a packet counts as lost when
no reply carrying its number arrives within --timeout seconds. This is round-trip loss: either
the request or the reply went missing.

Output: realworld/captures/<label>_<YYYYmmdd-HHMMSS>.csv (one row per packet) and a matching .json
with the run settings and totals.
"""
import argparse
import csv
import json
import os
import platform
import random
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

MAGIC = b"PLv1"
HEADER = struct.Struct("!4sIIQ")        # magic, run id, sequence number, send time (ns)
HERE = os.path.dirname(os.path.abspath(__file__))


def checksum(data: bytes) -> int:
    """Internet checksum (RFC 1071) for the ICMP header."""
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack(f"!{len(data) // 2}H", data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def icmp_packet(seq: int, payload: bytes) -> bytes:
    head = struct.pack("!BBHHH", 8, 0, 0, os.getpid() & 0xFFFF, seq & 0xFFFF)
    return struct.pack("!BBHHH", 8, 0, checksum(head + payload), os.getpid() & 0xFFFF, seq & 0xFFFF) + payload


def default_gateway() -> str:
    """IPv4 address of the default router (the Wi-Fi router or the phone, on a hotspot)."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"gateway:\s*([\d.]+)", out)
        else:
            out = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"default via ([\d.]+)", out)
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    sys.exit("Could not find your router's address. Pass it with --target, for example --target 192.168.1.1")


def open_socket(mode: str) -> socket.socket:
    if mode == "icmp":
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
        except PermissionError:
            sys.exit("This system does not allow ICMP (ping) sockets for normal users.\n"
                     "  macOS: run the same command with sudo in front.\n"
                     "  Linux: sudo sysctl -w net.ipv4.ping_group_range='0 2147483647'\n"
                     "Or use --mode udp with realworld/echo_server.py on another computer.")
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)
    return sock


def parse_reply(data: bytes, mode: str):
    """Return (run_id, seq) from a reply, or None if it is not one of ours."""
    if mode == "icmp":
        if len(data) >= 20 and data[0] >> 4 == 4:      # macOS hands back the IP header too
            data = data[(data[0] & 0x0F) * 4:]
        if len(data) < 8 + HEADER.size or data[0] != 0:  # type 0 = echo reply
            return None
        data = data[8:]
    if len(data) < HEADER.size:
        return None
    magic, run_id, seq, _ = HEADER.unpack_from(data)
    return (run_id, seq) if magic == MAGIC else None


def main():
    ap = argparse.ArgumentParser(description="Send a steady packet stream and record which packets are lost.")
    ap.add_argument("--label", required=True, help="name for this capture, e.g. wifi, hotspot, wired")
    ap.add_argument("--target", default="gateway", help="host to probe; 'gateway' means your router (default)")
    ap.add_argument("--mode", choices=["icmp", "udp"], default="icmp")
    ap.add_argument("--port", type=int, default=9999, help="UDP port of echo_server.py (udp mode)")
    ap.add_argument("--rate", type=float, default=50.0, help="packets per second (default 50, one every 20 ms)")
    ap.add_argument("--duration", type=float, default=600.0, help="seconds to send for (default 600 = 10 minutes)")
    ap.add_argument("--timeout", type=float, default=2.0, help="seconds to wait for a reply before calling it lost")
    ap.add_argument("--size", type=int, default=64, help="payload bytes per packet (default 64)")
    ap.add_argument("--note", default="", help="free text saved with the run, e.g. 'hostel room, evening'")
    ap.add_argument("--out", default=os.path.join(HERE, "captures"))
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        sys.exit("--label may contain only letters, digits, - and _")

    target = default_gateway() if args.target == "gateway" else args.target
    try:
        addr = socket.gethostbyname(target)
    except socket.gaierror:
        sys.exit(f"Cannot resolve {target!r}")
    sock = open_socket(args.mode)
    dest = (addr, 0 if args.mode == "icmp" else args.port)
    run_id = random.getrandbits(32)
    pad = b"\0" * max(0, args.size - HEADER.size)
    n_total = int(round(args.rate * args.duration))
    interval_ns = int(1e9 / args.rate)
    recv_ns = [0] * n_total
    stats = {"late": 0, "duplicates": 0, "foreign": 0}
    stop = threading.Event()

    def build(seq, t_ns):
        payload = HEADER.pack(MAGIC, run_id, seq, t_ns) + pad
        return icmp_packet(seq, payload) if args.mode == "icmp" else payload

    # ---- preflight: make sure the target answers at all ----
    ok = False
    for i in range(5):
        sock.sendto(build(0xFFFFFFFF - i, time.perf_counter_ns()), dest)
        end = time.time() + 1.0
        while time.time() < end:
            try:
                r = parse_reply(sock.recv(4096), args.mode)
            except socket.timeout:
                continue
            if r and r[0] == run_id:
                ok = True
                break
        if ok:
            break
    if not ok:
        sys.exit(f"No replies from {addr} ({args.mode}). Check the address, that you are connected, and that "
                 f"the target answers {'pings' if args.mode == 'icmp' else 'on UDP port ' + str(args.port)}. "
                 f"Some routers and hotspots ignore pings; try --target 1.1.1.1.")

    send_ns = [0] * n_total

    def receiver():
        while not stop.is_set():
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            now = time.perf_counter_ns()
            r = parse_reply(data, args.mode)
            if not r or r[0] != run_id or r[1] >= n_total:
                stats["foreign"] += 1
                continue
            seq = r[1]
            if recv_ns[seq]:
                stats["duplicates"] += 1
            elif now - send_ns[seq] > args.timeout * 1e9:
                stats["late"] += 1
            else:
                recv_ns[seq] = now

    th = threading.Thread(target=receiver, daemon=True)
    th.start()
    start_wall = datetime.now(timezone.utc)
    print(f"Probing {addr} ({args.mode}) at {args.rate:g} packets/s for {args.duration:g} s "
          f"= {n_total:,} packets. Label: {args.label}. Press Ctrl-C to stop early.", flush=True)

    t0 = time.perf_counter_ns()
    sent = 0
    behind = 0
    next_report = t0 + 10 * 10**9
    try:
        for seq in range(n_total):
            due = t0 + seq * interval_ns
            while True:
                now = time.perf_counter_ns()
                wait = due - now
                if wait <= 0:
                    break
                time.sleep(wait / 1e9 if wait > 2_000_000 else 0)   # sleep, then spin the last 2 ms
            if now - due > interval_ns:
                behind += 1
            now = time.perf_counter_ns()
            send_ns[seq] = now
            try:
                sock.sendto(build(seq, now), dest)
            except OSError:
                pass                       # e.g. network briefly down: the packet simply counts as lost
            sent = seq + 1
            if now >= next_report:
                got = sum(1 for i in range(sent) if recv_ns[i])
                waiting = sum(1 for i in range(sent) if not recv_ns[i] and now - send_ns[i] < args.timeout * 1e9)
                lost = sent - got - waiting
                print(f"  {(now - t0) / 1e9:6.0f} s  sent {sent:,}  lost so far {lost:,} "
                      f"({100 * lost / max(1, sent - waiting):.2f}%)", flush=True)
                next_report += 10 * 10**9
    except KeyboardInterrupt:
        print("\nStopped early; saving what was sent.", flush=True)
    time.sleep(args.timeout)
    stop.set()
    th.join(timeout=1)
    sock.close()

    os.makedirs(args.out, exist_ok=True)
    stamp = start_wall.astimezone().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(args.out, f"{args.label}_{stamp}")
    received = 0
    rtts = []
    with open(base + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "t_send_s", "received", "rtt_ms"])
        for seq in range(sent):
            ok = 1 if recv_ns[seq] else 0
            rtt = (recv_ns[seq] - send_ns[seq]) / 1e6 if ok else ""
            received += ok
            if ok:
                rtts.append(rtt)
            w.writerow([seq, f"{(send_ns[seq] - t0) / 1e9:.6f}", ok, f"{rtt:.3f}" if ok else ""])
    rtts.sort()
    meta = dict(
        label=args.label, mode=args.mode, target=target, address=addr, port=args.port if args.mode == "udp" else None,
        rate=args.rate, planned_duration_s=args.duration, packets_sent=sent, packets_received=received,
        packets_lost=sent - received, loss_rate=(sent - received) / max(1, sent),
        late_replies=stats["late"], duplicate_replies=stats["duplicates"], sends_behind_schedule=behind,
        rtt_median_ms=rtts[len(rtts) // 2] if rtts else None,
        rtt_p95_ms=rtts[int(0.95 * (len(rtts) - 1))] if rtts else None,
        timeout_s=args.timeout, payload_bytes=max(args.size, HEADER.size), start_local=start_wall.astimezone().isoformat(),
        platform=f"{platform.system()} {platform.release()}", python=platform.python_version(), note=args.note,
        loss_definition="round trip: no reply within timeout_s of sending",
    )
    with open(base + ".json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nDone. Sent {sent:,}, lost {sent - received:,} ({100 * meta['loss_rate']:.3f}%).")
    if behind > 0.01 * max(1, sent):
        print(f"Warning: {behind:,} packets went out more than one interval late (busy laptop?). "
              f"Close heavy apps and keep the laptop plugged in.")
    print(f"Saved {base}.csv and .json")


if __name__ == "__main__":
    main()
