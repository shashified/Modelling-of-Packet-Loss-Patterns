"""Tests for the Phase 2 real-network tools in realworld/."""
import csv
import glob
import json
import os
import socket
import struct
import subprocess
import sys
import time

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "realworld"))
import probe  # noqa: E402
from src import loss_model as LM  # noqa: E402


def test_icmp_checksum_verifies():
    payload = probe.HEADER.pack(probe.MAGIC, 7, 42, 123) + b"\0" * 8
    pkt = probe.icmp_packet(42, payload)
    assert probe.checksum(pkt) == 0          # a correct checksum makes the whole packet sum to zero


def test_parse_reply_icmp_with_and_without_ip_header():
    payload = probe.HEADER.pack(probe.MAGIC, 99, 5, 0)
    reply = struct.pack("!BBHHH", 0, 0, 0, 1, 5) + payload               # type 0 = echo reply
    ip = bytes([0x45]) + b"\0" * 19                                       # minimal IPv4 header (macOS style)
    assert probe.parse_reply(reply, "icmp") == (99, 5)
    assert probe.parse_reply(ip + reply, "icmp") == (99, 5)
    request = struct.pack("!BBHHH", 8, 0, 0, 1, 5) + payload              # our own request echoed by the OS
    assert probe.parse_reply(request, "icmp") is None
    assert probe.parse_reply(b"junk", "udp") is None
    assert probe.parse_reply(payload, "udp") == (99, 5)


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_probe_udp_end_to_end(tmp_path):
    port = _free_port()
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "realworld", "echo_server.py"), "--port", str(port),
                            "--bind", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "realworld", "probe.py"), "--mode", "udp",
                            "--target", "127.0.0.1", "--port", str(port), "--label", "t", "--duration", "2",
                            "--timeout", "0.5", "--out", str(tmp_path)], capture_output=True, text=True, timeout=60)
    finally:
        srv.terminate()
    assert r.returncode == 0, r.stderr
    meta = json.load(open(glob.glob(str(tmp_path / "t_*.json"))[0]))
    assert meta["packets_sent"] == 100 and meta["packets_lost"] == 0
    rows = list(csv.DictReader(open(glob.glob(str(tmp_path / "t_*.csv"))[0])))
    assert len(rows) == 100 and all(row["received"] == "1" for row in rows)


def _write_capture(folder, label, loss, rate=50.0):
    t = np.arange(len(loss)) / rate
    with open(os.path.join(folder, f"{label}_20260101-000000.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "t_send_s", "received", "rtt_ms"])
        for i, (ti, lost) in enumerate(zip(t, loss)):
            w.writerow([i, f"{ti:.6f}", 0 if lost else 1, "" if lost else "5.000"])
    with open(os.path.join(folder, f"{label}_20260101-000000.json"), "w") as f:
        json.dump(dict(label=label, mode="udp", target="test", rate=rate), f)


def test_analysis_separates_bursty_from_random(tmp_path):
    rng = np.random.default_rng(1)
    n = 50 * 600
    bursty = LM.simulate_losses(n, p_gb=0.002, p_bg=0.15, h_g=0.004, h_b=0.6, rng=rng)
    random_ = rng.random(n) < bursty.mean()
    clean = np.zeros(3000, dtype=bool)
    caps, out = tmp_path / "caps", tmp_path / "out"
    caps.mkdir()
    _write_capture(caps, "bursty", bursty)
    _write_capture(caps, "random", random_)
    _write_capture(caps, "clean", clean)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "realworld", "analyze_captures.py"),
                        "--captures", str(caps), "--out", str(out)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    res = {c["label"]: c for c in json.load(open(out / "results.json"))["captures"]}
    assert res["bursty"]["tests"]["runs"]["p"] < 0.05 and res["bursty"]["tests"]["runs"]["z"] < 0
    assert res["bursty"]["adjusted_posterior"]["deff"] > 2
    assert res["random"]["tests"]["runs"]["p"] > 0.01
    assert not res["clean"]["enough_losses"] and res["clean"]["losses"] == 0
    summary = (out / "summary.md").read_text()
    assert "| bursty |" in summary and "bursty |" in summary and "no evidence of bursts" in summary
    for fig in ["real_fig1_timeline.png", "real_fig2_count_fits.png", "real_fig3_gap_survival.png", "real_fig4_markov.png"]:
        assert (out / fig).exists()
