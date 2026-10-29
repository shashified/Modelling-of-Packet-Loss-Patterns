"""UDP echo server for probe.py --mode udp. Run it on a second computer on the network you want to test.

  python3 realworld/echo_server.py              # listens on UDP port 9999
  python3 realworld/echo_server.py --port 9000

Every packet received is sent straight back to its sender. Standard library only.

--test-drop is for testing the analysis only: it makes the server itself drop replies in bursts
using a Gilbert-Elliott Good/Bad process. Never use it for a real measurement.
"""
import argparse
import random
import socket


def main():
    ap = argparse.ArgumentParser(description="UDP echo server for probe.py")
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--test-drop", nargs=4, type=float, metavar=("P_GB", "P_BG", "H_G", "H_B"),
                    help="TESTING ONLY: drop replies with a Gilbert-Elliott process")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    bad = False
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    print(f"Echoing UDP on port {args.port}" + ("  [TEST MODE: dropping replies in bursts]" if args.test_drop else ""),
          flush=True)
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            if args.test_drop:
                p_gb, p_bg, h_g, h_b = args.test_drop
                if bad:
                    bad = rng.random() >= p_bg
                else:
                    bad = rng.random() < p_gb
                if rng.random() < (h_b if bad else h_g):
                    continue
            sock.sendto(data, addr)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
