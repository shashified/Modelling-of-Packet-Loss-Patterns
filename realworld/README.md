# Phase 2: measuring real packet loss

Phase 1 showed, on simulated networks, that losses come in bursts and that naive 95% intervals for the loss rate are too narrow. Phase 2 checks this on real networks. `probe.py` sends a steady stream of small packets (50 per second, one every 20 ms, like a voice call) and records which ones come back. `analyze_captures.py` then runs the same statistics as Phase 1 on what was recorded.

Nothing needs installing beyond what the project already uses. `probe.py` itself is plain Python with no extra packages and no admin rights.

## What gets measured

Each packet carries a sequence number and its send time. If no reply with that number arrives within 2 seconds, the packet counts as lost. This is round-trip loss: the request or the reply went missing.

There are two ways to probe:

| Mode | What it sends to | When to use |
|---|---|---|
| `icmp` (default) | pings to a host, usually your router (`--target gateway`) or `1.1.1.1` | Normal use. Works alone on one laptop. |
| `udp` | `echo_server.py` running on a second computer | If pings are blocked, or to measure between two laptops. |

Probing the router (`gateway`) measures the wireless hop, which is where most bursts come from. Probing `1.1.1.1` measures the whole path to the internet. Some public servers limit how many pings they answer, which can look like loss. So use the router for the main runs and `1.1.1.1` as a second view.

## Running it on a MacBook

**1. Get the code and the Python packages (once)**

```bash
git clone https://github.com/AashmanBiyani08/Prob_Stats_Project.git
cd Prob_Stats_Project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

If you already have the repo: `cd Prob_Stats_Project && git pull && source .venv/bin/activate`.

**2. Before every capture**

- Plug in the charger and close heavy apps (games, big downloads, video calls).
- Turn off any VPN.
- Keep the laptop in one place for the whole run.
- Prefix the command with `caffeinate -i` so the Mac does not sleep.

**3. One 10-minute capture per network**

Ten minutes (600 s) comes from the Phase 1 power study: shorter runs can miss bursts on a good link.

Campus or home Wi-Fi:

```bash
caffeinate -i python3 realworld/probe.py --label wifi --target gateway --duration 600 --note "hostel room, evening"
```

Phone hotspot. Turn on the hotspot, join it from the Mac, then:

```bash
caffeinate -i python3 realworld/probe.py --label hotspot --target gateway --duration 600 --note "4G, phone on desk"
```

Wired (needs an Ethernet port or a USB-C Ethernet adapter, with Wi-Fi turned off):

```bash
caffeinate -i python3 realworld/probe.py --label wired --target gateway --duration 600
```

Optional second view of each network, through to the internet:

```bash
caffeinate -i python3 realworld/probe.py --label wifi_internet --target 1.1.1.1 --duration 600
```

While it runs, it prints the loss so far every 10 seconds. Each run saves a `.csv` (one row per packet) and a `.json` (settings and totals) in `realworld/captures/`.

**4. Analyse**

```bash
python3 realworld/analyze_captures.py --latest
```

This takes about a minute. Open `realworld/results/summary.md` and the four `real_fig*.png` figures.

## Reading the results

| Column in summary.md | What it means |
|---|---|
| Loss rate (95% CrI) | Bayesian estimate of the loss rate with its credible interval |
| Var / mean | 1 for random loss; above 1 means losses clump into the same seconds |
| Runs z (p) | strongly negative z with small p means losses sit next to each other |
| P(L given N), P(L given L) | chance of a loss after a delivered packet, and after a lost one |
| b/a | how many times likelier a loss is right after a loss (1 = random) |
| Design effect | how much the bursts inflate the variance; 1 = no inflation |
| Adjusted 95% interval | the corrected interval from Phase 1; wider when the design effect is above 1 |
| Verdict | "bursty" when the runs or Markov test finds clustering at α = 0.05 |

If a network loses fewer than 10 packets in the whole run, the tests have nothing to work with. The summary then shows only the loss-rate estimate. That is a real result too: the link is very clean. Try a busier time, a weaker spot in the room, or a longer run.

## Ideas for good captures

- Use a different label for each condition, for example `wifi_peak` (evening) and `wifi_offpeak` (early morning), or `hotspot_indoor` and `hotspot_window`. The analysis compares all captures with the Kruskal-Wallis and Mann-Whitney tests.
- Run the same network twice on different days to see whether the results repeat.
- Note where and when you ran each capture with `--note`. It is saved in the `.json`.

## Second-computer mode (UDP)

On computer B (same network):

```bash
python3 realworld/echo_server.py --port 9999
```

On computer A, using B's IP address (System Settings > Wi-Fi > Details on a Mac):

```bash
caffeinate -i python3 realworld/probe.py --mode udp --target 192.168.1.23 --port 9999 --label lan_udp --duration 600
```

If nothing comes back, allow incoming connections for Python on computer B's firewall.

## Troubleshooting

| Message | Fix |
|---|---|
| `No replies from ...` | The target ignores pings. Try `--target 1.1.1.1`, or use UDP mode. |
| `does not allow ICMP ... for normal users` | Put `sudo` in front of the command. |
| `Could not find your router's address` | Pass it yourself, e.g. `--target 192.168.1.1` (System Settings > Wi-Fi > Details > TCP/IP > Router). |
| `packets went out more than one interval late` | The laptop was too busy. Close apps, plug in and run again. |

## Being a good network citizen

50 small packets per second is about 4 KB/s, far less than a video call. Keep the default rate, and follow your campus network's rules.

`echo_server.py --test-drop` exists only to test the analysis code: the server drops replies on purpose in bursts. Never use it for a real measurement.
