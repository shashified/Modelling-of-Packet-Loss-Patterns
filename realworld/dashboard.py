"""Real Network Lab: record real packet captures and see every statistic of the case study as charts.

Opened through `streamlit run lab.py` (it is the first page of the Packet-Loss Lab).
"""
import glob
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "realworld")):
    if p not in sys.path:
        sys.path.insert(0, p)
from src import config as C                      # noqa: E402
from src import distributions as D               # noqa: E402
from src import hypothesis_tests as HT           # noqa: E402
from src import loss_model as LM                 # noqa: E402
from src import plots as P                       # noqa: E402
import analyze_captures as AC                    # noqa: E402
import lab_stats as LS                           # noqa: E402
import lab_readme                                # noqa: E402
import run_library as RL                         # noqa: E402
import study_ref as SR                           # noqa: E402

CAPS = os.environ.get("PL_CAPTURES_DIR", os.path.join(ROOT, "realworld", "captures"))
DEMO = os.path.join(ROOT, "realworld", "demo_captures")
PROBE = os.path.join(ROOT, "realworld", "probe.py")
ECHO = os.path.join(ROOT, "realworld", "echo_server.py")
# Test network on this laptop: an echo server that drops replies on purpose (never a real measurement).
# Bursty patterns replay the case study's Good/Bad parameters; the random one drops independently at Wi-Fi's long-run rate.
_W, _M = C.SCENARIOS["S2_WiFi"], C.SCENARIOS["S3_Mobile"]
_W_RATE = LM.theoretical_loss_rate(**{k: v for k, v in _W.items() if k != "label"})
TEST_PATTERNS = {
    "Bad moods like campus Wi-Fi (bursty)": ("testnet_wifi_bursty", (_W["p_gb"], _W["p_bg"], _W["h_g"], _W["h_b"])),
    "Bad moods like a mobile hotspot (very bursty)": ("testnet_mobile_bursty", (_M["p_gb"], _M["p_bg"], _M["h_g"], _M["h_b"])),
    "Random drops at the same rate (no bad moods)": ("testnet_random", (0.0, 1.0, _W_RATE, _W_RATE)),
}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]
ALPHA = C.ALPHA
PALETTE = ["#2E6DB4", "#E07A1F", "#B23A48", "#2D6A4F", "#5C4D7D", "#8A6D1D", "#1D3557", "#6B7280"]
BAD, DELIV, GOOD, GREY, NAVY = "#C0392B", "#BFE3CC", "#2D6A4F", "#9AA5B1", "#1F3A5F"

st.markdown("""
<style>
  .block-container { padding-top: 1.4rem; }
  .tiles { display: flex; flex-wrap: wrap; gap: 10px; margin: 4px 0 12px 0; }
  .tile { flex: 1 1 160px; background: #F2F5F9; border-radius: 10px; padding: 10px 14px; }
  .tile .lab { color: #4A5563; font-size: 0.85rem; }
  .tile .val { font-size: 1.45rem; font-weight: 700; color: #1B2430; white-space: nowrap; }
  .tile .sub { color: #4A5563; font-size: 0.8rem; }
  .net { border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; border: 1px solid #DDE3EA; }
  .net.bursty { border-left: 7px solid #C0392B; background: #FCF2F1; }
  .net.random { border-left: 7px solid #2D6A4F; background: #F1F8F4; }
  .net.thin { border-left: 7px solid #9AA5B1; background: #F7F8FA; }
  .net h4 { margin: 0 0 6px 0; font-size: 1.05rem; }
  .net .row { display: flex; flex-wrap: wrap; gap: 18px; font-size: 0.92rem; color: #1B2430; }
  .net .row b { font-size: 1.05rem; }
  .explain { background: #F2F5F9; border-radius: 10px; padding: 10px 14px; font-size: 0.93rem; margin: 6px 0 10px 0; }
  .obj { display: inline-block; background: #1F3A5F; color: white; border-radius: 6px; padding: 1px 8px; font-size: 0.8rem; margin-right: 6px; }
  .packets { display: flex; flex-wrap: wrap; gap: 2px; margin: 6px 0 4px 0; }
  .packets span { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .legend span { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin: 0 4px -1px 10px; }
  .demo { background: #FFF6E0; border: 1px solid #F0D58A; border-radius: 10px; padding: 8px 14px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)


def explain(text):
    st.markdown(f'<div class="explain">{text}</div>', unsafe_allow_html=True)


def obj(tag, title):
    st.markdown(f'<span class="obj">{tag}</span> <b>{title}</b>', unsafe_allow_html=True)


def pct(x, d=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.{d}f}%"


def fmt_p(p, B=None):
    return AC.fmt_p(p, B)


def nice_dur(s):
    s = int(round(s))
    return f"{s // 60} min {s % 60} s" if s % 60 and s >= 60 else (f"{s // 60} min" if s >= 60 else f"{s} s")


# ------------------------------------------------------------------ data loading and analysis
def list_captures(folder, pattern="*.csv"):
    out = []
    for f in sorted(glob.glob(os.path.join(folder, pattern))):
        meta_p = f[:-4] + ".json"
        meta = {}
        if os.path.exists(meta_p):
            try:
                meta = json.load(open(meta_p))
            except (OSError, ValueError):
                meta = {}
        label = meta.get("label") or os.path.basename(f).rsplit("_", 2)[0]
        m = re.search(r"_(\d{8})-(\d{6})\.csv$", f)
        when = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else datetime.fromtimestamp(os.path.getmtime(f))
        out.append(dict(path=f, label=label, when=when, meta=meta, mtime=os.path.getmtime(f)))
    return out


@st.cache_data(show_spinner=False, max_entries=64)
def analyse_file(path, mtime):
    cap = AC.load(path)
    rng = np.random.default_rng(C.SEED)
    res, ex = AC.analyse(cap, rng)
    out = dict(res=AC.clean(res), loss=cap["loss"], t=cap["t"], rtt_all=None, rate=cap["rate"])
    # per-packet RTT aligned with the packets (NaN where lost), for the RTT chart
    rows = pd.read_csv(path)
    out["rtt_all"] = pd.to_numeric(rows["rtt_ms"], errors="coerce").to_numpy()
    out["seq_curve"] = LS.sequential_curve(cap["loss"], cap["rate"])
    out["bursts"] = LM.burst_lengths(cap["loss"]) if cap["loss"].any() else np.array([], dtype=int)
    if ex:
        out["counts"], out["gaps"] = ex["counts"], ex["gaps"]
        out["fits"], out["gap_fits"] = ex["fits"], ex["gap_fits"]
        out["markov_samples"] = (ex["markov"]["samples_a"][:20000], ex["markov"]["samples_b"][:20000])
        a, b = res["tests"]["markov_lrt"]["p_L_given_N"], res["tests"]["markov_lrt"]["p_L_given_L"]
        rng2 = np.random.default_rng(C.SEED + 1)
        dur = max(60, res["duration_s"])
        out["coverage"] = LS.coverage_check(a, b, cap["rate"], dur, 1000, max(1, int(round(cap["rate"] * C.BLOCK_S))), rng2)
        lengths = sorted({30, 60, 120, 300, 600, 1200, int(round(dur))})
        out["power"] = LS.power_curve(a, b, cap["rate"], lengths, 300, ALPHA, rng2)
    else:
        out["counts"] = LM.window_counts(cap["loss"], max(1, int(round(cap["rate"] * C.WINDOW_S))))
    return out


@st.cache_data(show_spinner=False)
def study_results():
    return SR.load_results()


@st.cache_data(show_spinner=False)
def study_traces():
    return SR.traces()


def verdict(r):
    if not r["enough_losses"]:
        return "thin"
    t, mk = r["tests"], r["markov"]
    bursty = (t["runs"]["p"] < ALPHA and t["runs"]["z"] < 0) or (t["markov_lrt"]["p"] < ALPHA and mk["P_b_gt_a"] > 0.975)
    return "bursty" if bursty else "random"


def make_demo():
    """Two clearly labelled demo captures (simulated, not measured) so the dashboard can be explored first."""
    os.makedirs(DEMO, exist_ok=True)
    rng = np.random.default_rng(7)
    n = 50 * 600
    bursty = LM.simulate_losses(n, p_gb=0.002, p_bg=0.15, h_g=0.004, h_b=0.6, rng=rng)
    indep = rng.random(n) < bursty.mean()
    for label, loss in [("DEMO_bursty", bursty), ("DEMO_random", indep)]:
        base = os.path.join(DEMO, f"{label}_20260101-120000")
        with open(base + ".csv", "w") as f:
            f.write("seq,t_send_s,received,rtt_ms\n")
            for i, lost in enumerate(loss):
                f.write(f"{i},{i / 50:.6f},{0 if lost else 1},{'' if lost else f'{rng.gamma(9, 1.2):.3f}'}\n")
        json.dump(dict(label=label, mode="demo", target="simulated (not a real measurement)", rate=50.0,
                       note="Demo data generated by the simulator, for exploring the dashboard."), open(base + ".json", "w"))


# ------------------------------------------------------------------ sidebar: record / upload / choose
st.sidebar.title("📶 Real Network Lab")
lab_readme.render()
st.sidebar.markdown("**1. Record a capture**")
with st.sidebar.form("record"):
    net = st.selectbox("Network you are on", ["Wi-Fi", "Phone hotspot", "Wired (Ethernet)", "Other"])
    other = st.text_input("Name (for Other)", placeholder="e.g. library_wifi")
    tgt = st.selectbox("Send packets to", ["My router (recommended)", "The internet (1.1.1.1)", "Custom address",
                                           "Test network on this laptop (drops on purpose)"],
                       help="The test network is an echo server on your own laptop that loses packets on purpose, "
                            "so you can see bursts even when your real network is clean. It is a controlled test, not a measurement.")
    custom = st.text_input("Custom address", placeholder="e.g. 192.168.1.1")
    pattern = st.selectbox("Test network: how it drops packets", list(TEST_PATTERNS),
                           help="Only used with 'Test network on this laptop'.")
    dur_s = st.select_slider("Length", options=[30, 120, 300, 600, 1200], value=600, format_func=lambda s: {
        30: "30 s (quick test)", 120: "2 min", 300: "5 min", 600: "10 min (recommended)", 1200: "20 min"}[s])
    note = st.text_input("Note (optional)", placeholder="e.g. hostel room, evening")
    ref_choice = st.selectbox("Compare live against", ["Matching case-study network"] +
                              [f"Case study: {SR.label(k)}" for k in SR.KEYS],
                              help="The simulated network from the case study that the live numbers are set against.")
    go = st.form_submit_button("▶ Start recording", type="primary", width="stretch")

st.sidebar.markdown("**2. Or add capture files**")
ups = st.sidebar.file_uploader("CSV and JSON files made by probe.py", type=["csv", "json"], accept_multiple_files=True)
if ups:
    os.makedirs(CAPS, exist_ok=True)
    saved = 0
    for u in ups:
        name = os.path.basename(u.name)
        data = u.getvalue()
        if name.endswith(".csv") and not data.startswith(b"seq,t_send_s,received,rtt_ms"):
            st.sidebar.error(f"{name} is not a probe.py capture.")
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.#-]+", name):
            st.sidebar.error(f"{name}: please rename it to letters, digits, _ and - only.")
            continue
        with open(os.path.join(CAPS, name), "wb") as f:
            f.write(data)
        saved += 1
    if saved:
        st.sidebar.success(f"Added {saved} file(s).")

use_demo = st.sidebar.toggle("Show demo data (simulated)", value=False,
                             help="Two simulated captures, clearly marked DEMO, so you can explore the dashboard before recording.")

# ------------------------------------------------------------------ live recording
st.title("📶 Real Network Lab")
st.caption("Phase 2 of the case study: real packets on real networks, analysed with every method from Phase 1.")

if go:
    label = {"Wi-Fi": "wifi", "Phone hotspot": "hotspot", "Wired (Ethernet)": "wired"}.get(net) or \
        (re.sub(r"[^A-Za-z0-9_-]", "_", other.strip()) or "other")
    if tgt.startswith("The internet"):
        label += "_internet"
    testnet = tgt.startswith("Test network")
    echo_proc = None
    if testnet:
        label, drop = TEST_PATTERNS[pattern]
        port = free_port()
        echo_proc = subprocess.Popen([sys.executable, ECHO, "--port", str(port), "--bind", "127.0.0.1",
                                      "--test-drop", *[str(v) for v in drop]],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)
        import time as _time
        _time.sleep(0.6)
        target = "127.0.0.1"
    else:
        target = {"My router (recommended)": "gateway", "The internet (1.1.1.1)": "1.1.1.1"}.get(tgt, custom.strip())
    if not target:
        st.error("Type a custom address, or pick 'My router'.")
        st.stop()
    os.makedirs(CAPS, exist_ok=True)
    cmd = [sys.executable, PROBE, "--label", label, "--target", target, "--duration", str(dur_s), "--live", "--out", CAPS]
    if testnet:
        cmd += ["--mode", "udp", "--port", str(port),
                "--note", f"CONTROLLED TEST on this laptop: {pattern}. Not a real network measurement."]
    elif note.strip():
        cmd += ["--note", note.strip()]
    if testnet:
        st.warning(f"🧪 Test network: packets go to an echo server on this laptop that drops them on purpose "
                   f"({pattern.lower()}). This shows the method working; it is not a measurement of a real network.")
    st.subheader(f"Recording **{label}** for {nice_dur(dur_s)}")
    st.caption("Keep this tab open and the laptop still and plugged in. The analysis starts by itself when the recording ends.")
    ref_key = SR.match(label) if ref_choice.startswith("Matching") else \
        next(k for k in SR.KEYS if ref_choice.endswith(SR.label(k)))
    R1 = study_results()
    REF = SR.summary(R1, ref_key) if R1 else None
    if REF:
        st.caption(f"Live comparison with the case study's **{SR.label(ref_key)}**: loss rate "
                   f"{pct(REF['loss_rate'], 2)}, a loss makes the next one {REF['ba']:.0f}× likelier.")
    bar = st.progress(0.0)
    m1, m2, m3, m4 = st.columns(4)
    sent_m, lost_m, rate_m, ba_m = m1.empty(), m2.empty(), m3.empty(), m4.empty()
    lc1, lc2 = st.columns(2)
    chart_ph, cum_ph = lc1.empty(), lc2.empty()
    log, per_sec, cum, last = [], [], [], 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=ROOT)
    saved_path = None
    for line in proc.stdout:
        log.append(line.rstrip())
        if line.startswith("PROGRESS "):
            d = json.loads(line[9:])
            bar.progress(min(1.0, d["sent"] / d["total"]), text=f"{d['t']:.0f} s of {dur_s} s")
            sent_m.metric("Packets sent", f"{d['sent']:,}")
            lost_m.metric("Lost so far", f"{d['lost']:,}")
            live_rate = d["lost"] / max(1, d["decided"])
            rate_m.metric("Loss rate so far", pct(live_rate, 2),
                          f"study {pct(REF['loss_rate'], 2)}" if REF else None, delta_color="off")
            if d.get("after_l", 0) >= 3 and d.get("nl", 0) > 0 and d.get("after_n", 0) > 0:
                live_ba = (d["ll"] / d["after_l"]) / (d["nl"] / d["after_n"])
                ba_m.metric("After a loss, next loss is", f"{live_ba:.1f}× likelier",
                            f"study {REF['ba']:.0f}×" if REF else None, delta_color="off")
            else:
                ba_m.metric("After a loss, next loss is", "waiting for losses")
            per_sec.append(dict(second=round(d["t"]), lost=d["lost"] - last))
            cum.append(dict(second=d["t"], rate=100 * live_rate, source="this run (live)"))
            last = d["lost"]
            if len(per_sec) % 2 == 0 or len(per_sec) < 5:
                chart_ph.altair_chart(alt.Chart(pd.DataFrame(per_sec)).mark_bar(color=BAD).encode(
                    x=alt.X("second:Q", title="time (s)"), y=alt.Y("lost:Q", title="packets lost", axis=alt.Axis(format="d", tickMinStep=1))
                ).properties(height=200, title="Packets lost each second"), width="stretch")
                live = alt.Chart(pd.DataFrame(cum)).mark_line(color=NAVY, strokeWidth=2).encode(
                    x=alt.X("second:Q", title="time (s)"), y=alt.Y("rate:Q", title="loss rate so far (%)"))
                if REF:
                    live = live + alt.Chart(pd.DataFrame({"y": [100 * REF["loss_rate"]], "lab": [f"study: {SR.label(ref_key)}"]})).mark_rule(
                        color=GREY, strokeDash=[6, 4], strokeWidth=2).encode(y="y:Q", tooltip=["lab", "y"])
                cum_ph.altair_chart(live.properties(height=200, title="Loss rate so far vs the case study (dashed)"), width="stretch")
        elif line.startswith("SAVED "):
            saved_path = line[6:].strip()
    proc.wait()
    if echo_proc is not None:
        echo_proc.terminate()
    if proc.returncode != 0 or not saved_path:
        st.error("The recording did not finish. Message from the probe:")
        st.code("\n".join(log[-8:]) or "(no output)")
        st.info("If it mentions ICMP permission, open Terminal in the project folder and run the same capture with sudo: "
                f"`sudo python3 realworld/probe.py --label {label} --target {target} --duration {dur_s}`. "
                "The file appears here automatically. If it says 'No replies', pick 'The internet (1.1.1.1)'.")
        st.stop()
    bar.progress(1.0, text="Done")
    st.success(f"Saved {os.path.basename(saved_path)}. Running the statistics now.")
    st.session_state["just_recorded"] = saved_path
    st.session_state["vs_run_path"] = saved_path
    st.session_state["vs_ref_key"] = ref_key
    st.info("Open the **🆚 Live vs study** tab below for the full side-by-side comparison, "
            "and use **💾 Save this run** to keep it in your saved runs.")

# ------------------------------------------------------------------ choose captures
caps = list_captures(CAPS)
lib_caps = list_captures(RL.folder(), "*/*.csv")
caps += lib_caps
if use_demo:
    if not glob.glob(os.path.join(DEMO, "*.csv")):
        make_demo()
    caps += list_captures(DEMO)

st.sidebar.markdown("**3. Captures to analyse**")
if not caps:
    st.info("No captures yet. Use **Record a capture** in the sidebar (10 minutes on each network), "
            "or switch on **Show demo data** to explore the dashboard first.")
    with st.expander("How this works", expanded=True):
        st.markdown(
            "1. Connect the laptop to a network (Wi-Fi, your phone's hotspot, or a cable).\n"
            "2. Press **Start recording**. The laptop sends 50 small numbered packets per second, like a voice call, "
            "and notes which ones never come back.\n"
            "3. When it finishes, every test from the case study runs automatically and the results appear here as charts.\n"
            "4. Repeat on the other networks, then compare them in the **O4 Compare** tab.")
    st.stop()

def cap_name(c):
    dur = c["meta"].get("planned_duration_s")
    tag = "💾 " if c["meta"].get("saved_name") else ""
    return f"{tag}{c['label']}  ·  {c['when']:%d %b %H:%M}" + (f"  ·  {nice_dur(dur)}" if dur else "")

latest = {}
for c in caps:
    if not c["meta"].get("saved_name"):
        latest[c["label"]] = c["path"]
default = list(latest.values())
if st.session_state.get("just_recorded") and st.session_state["just_recorded"] not in default:
    default.append(st.session_state["just_recorded"])
by_path = {c["path"]: c for c in caps}
# keep the selection across reruns; add captures that appeared since the last run (new recordings, demo)
known = st.session_state.setdefault("known_paths", set())
if "chosen" not in st.session_state:
    st.session_state["chosen"] = default
else:
    st.session_state["chosen"] = [p for p in st.session_state["chosen"] if p in by_path] + \
        [p for p in default if p not in known and p not in st.session_state["chosen"]]
if not st.session_state["chosen"]:
    st.session_state["chosen"] = default
known.update(by_path)
chosen = st.sidebar.multiselect("Newest capture of each network is picked (💾 = saved run)", list(by_path), key="chosen",
                                format_func=lambda p: cap_name(by_path[p]))
if not chosen:
    st.info("Pick at least one capture in the sidebar.")
    st.stop()

with st.spinner("Running all the statistics (about 10 s per capture the first time)..."):
    A, KEY2PATH = {}, {}
    for pth in chosen:
        c = by_path[pth]
        key = c["label"]
        if key in A:
            key = f"{key} ({c['when']:%d %b %H:%M})"
        A[key] = analyse_file(pth, c["mtime"])
        KEY2PATH[key] = pth
names = list(A)
COL = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(names)}
color_scale = alt.Scale(domain=names, range=[COL[k] for k in names])
full = [k for k in names if A[k]["res"]["enough_losses"]]

if any(by_path[p]["label"].startswith("testnet_") or by_path[p]["meta"].get("original_label", "").startswith("testnet_") for p in chosen):
    st.markdown('<div class="demo">🧪 Runs named <b>testnet_…</b> went through the test network on this laptop, which drops packets '
                'on purpose. They show the method working; they are not measurements of a real network.</div>', unsafe_allow_html=True)
thin_real = [k for k in names if verdict(A[k]["res"]) == "thin" and not k.startswith("testnet_")]
if thin_real:
    with st.expander(f"💡 {', '.join(thin_real)}: too few losses. How to get some", expanded=False):
        st.markdown(
            "Your link was very clean, which is a real result in itself. To see losses on a **real** network:\n"
            "- Record on the **phone hotspot**, or Wi-Fi with the laptop **far from the router** (another room, behind walls).\n"
            "- Pick **The internet (1.1.1.1)** instead of the router, so the packets cross more links.\n"
            "- Record at a **busy time** (evening in the hostel), or start a large download or video stream at the same time.\n"
            "- Record longer (20 min).\n\n"
            "To show bursts on demand (for the demo), pick **Send packets to: Test network on this laptop**. "
            "It drops packets on purpose with the case study's Good/Bad model, and is labelled as a test.")
if any(by_path[p]["meta"].get("mode") == "demo" for p in chosen):
    st.markdown('<div class="demo">⚠️ Captures named <b>DEMO_…</b> are simulated examples for exploring the dashboard. '
                'They are not real measurements. Switch off "Show demo data" before presenting.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ headline cards
n_bursty = sum(verdict(A[k]["res"]) == "bursty" for k in names)
n_rand = sum(verdict(A[k]["res"]) == "random" for k in names)
total_pk = sum(A[k]["res"]["packets"] for k in names)
total_lost = sum(A[k]["res"]["losses"] for k in names)
st.markdown('<div class="tiles">' + "".join(
    f'<div class="tile"><div class="lab">{lab}</div><div class="val">{val}</div><div class="sub">{sub}</div></div>'
    for lab, val, sub in [
        ("Networks analysed", f"{len(names)}", ", ".join(names)),
        ("Packets sent", f"{total_pk:,}", f"{total_lost:,} lost in total"),
        ("Bursty networks", f"{n_bursty} of {len(names)}", "losses cluster together"),
        ("Random-looking networks", f"{n_rand} of {len(names)}", "no evidence of bursts"),
    ]) + "</div>", unsafe_allow_html=True)

for k in names:
    r = A[k]["res"]
    v = verdict(r)
    p = r["posterior"]
    head = {"bursty": "🔴 Losses come in bursts", "random": "🟢 No evidence of bursts",
            "thin": "⚪ Too few losses to test (a very clean link)"}[v]
    extra = ""
    if v != "thin":
        mk, adj = r["markov"], r["adjusted_posterior"]
        extra = (f"<span>After a loss, next loss is <b>{mk['amp_q'][1]:.1f}×</b> likelier</span>"
                 f"<span>Average burst <b>{r['descriptive']['mean_burst_len']:.2f}</b> packets</span>"
                 f"<span>Design effect <b>{adj['deff']:.2f}</b></span>")
    rtt = f"<span>Round-trip time <b>{r['rtt_median_ms']:.1f} ms</b></span>" if r.get("rtt_median_ms") else ""
    st.markdown(f'<div class="net {v}"><h4>{k}: {head}</h4><div class="row">'
                f'<span>Loss rate <b>{pct(p["mean"], 3)}</b> [{pct(p["ci_low"], 3)}, {pct(p["ci_high"], 3)}]</span>'
                f'<span><b>{r["losses"]:,}</b> of {r["packets"]:,} lost</span>{extra}{rtt}'
                f'<span>{nice_dur(r["duration_s"])}</span></div></div>', unsafe_allow_html=True)
short = [k for k in names if A[k]["res"]["duration_s"] < 590]
if short:
    st.caption(f"Shorter than 10 minutes: {', '.join(short)}. The power study (O6 tab) shows whether that was long enough.")



# ------------------------------------------------------------------ run summaries (for saving and comparing)
def real_summary(k):
    """Headline numbers of one real run, in the same shape as SR.summary() for a study network."""
    x, r = A[k], A[k]["res"]
    p, c = r["posterior"], by_path[KEY2PATH[k]]
    out = dict(name=k, network=c["meta"].get("original_label") or c["meta"].get("label") or k,
               target=c["meta"].get("target"), mode=c["meta"].get("mode"), captured=c["when"].isoformat(timespec="minutes"),
               loss_rate=r["loss_rate"], ci=(p["ci_low"], p["ci_high"]), packets=r["packets"], losses=r["losses"],
               duration_s=r["duration_s"], rtt_median_ms=r.get("rtt_median_ms"), verdict=verdict(r))
    if r["enough_losses"]:
        t, f, mk, adj, d = r["tests"], r["fits"], r["markov"], r["adjusted_posterior"], r["descriptive"]
        ks, cov = t.get("ks_exponential") or {}, x.get("coverage") or {}
        out.update(D=d["window_var"] / d["window_mean"], disp_p=t["dispersion"]["p"], chisq_p=t["chisq_poisson"]["p"],
                   nb_better=bool(f["aic_negbin"] < f["aic_poisson"]), runs_z=t["runs"]["z"], runs_p=t["runs"]["p"],
                   a=t["markov_lrt"]["p_L_given_N"], b=t["markov_lrt"]["p_L_given_L"], markov_p=t["markov_lrt"]["p"],
                   ba=mk["amp_q"][1], mean_burst=d["mean_burst_len"], ks_p=ks.get("p"), ks_B=ks.get("B"),
                   deff=adj["deff"], adj_ci=(adj["ci_low"], adj["ci_high"]),
                   cov_naive=cov.get("naive"), cov_adjusted=cov.get("adjusted"))
    return out


def peq(p, B=None):
    t = fmt_p(p, B)
    return "p " + t if t.startswith("<") else "p = " + t


def _p(x):
    return 1.0 if x is None or (isinstance(x, float) and np.isnan(x)) else x


def reading(s):
    """What each test says about one run (or study network), in words."""
    if "D" not in s:
        return {}
    return {
        "poisson": "not Poisson (clumped)" if min(_p(s["disp_p"]), _p(s["chisq_p"])) < ALPHA else "Poisson fits",
        "runs": "losses cluster" if s["runs_p"] < ALPHA and s["runs_z"] < 0 else "no clustering",
        "markov": "a loss pulls in the next" if s["markov_p"] < ALPHA and s["b"] > s["a"] else "no pull",
        "gaps": "not exponential" if _p(s["ks_p"]) < ALPHA else "exponential fits",
        "interval": ("usual 95% interval too narrow" if s.get("cov_naive") is not None and s["cov_naive"] < 0.9
                     else "usual 95% interval fine"),
    }


VERDICT_TXT = {"bursty": "🔴 bursty", "random": "🟢 no evidence of bursts", "thin": "⚪ too few losses"}
RS = {k: real_summary(k) for k in names}

# ------------------------------------------------------------------ offer to save a fresh recording
jr = st.session_state.get("just_recorded")
jr_key = next((k for k in names if KEY2PATH[k] == jr), None)
if jr_key and not st.session_state.get(f"saved::{jr}"):
    with st.form("save_new", border=True):
        st.markdown(f"**💾 Save this run** ({jr_key}, {nice_dur(RS[jr_key]['duration_s'])}) to keep it with its results "
                    "in the **💾 Saved runs** tab.")
        f1, f2 = st.columns([1, 2])
        nm = f1.text_input("Name", value=f"{jr_key} {by_path[jr]['when']:%d %b %H:%M}")
        nt = f2.text_input("Note", value=by_path[jr]["meta"].get("note", ""), placeholder="where, when, anything unusual")
        if st.form_submit_button("💾 Save run", type="primary"):
            RL.save_run(jr, nm, nt, RS[jr_key])
            st.session_state[f"saved::{jr}"] = True
            st.success(f"Saved as “{nm}”. It is listed in the 💾 Saved runs tab.")

TAB_NAMES = {"packets": "👀 Packets", "vs": "🆚 Live vs study", "o1": "📊 O1 Loss counts", "o2": "⏱️ O2 Gaps",
             "o3": "🔗 O3 Independence", "o4": "⚖️ O4 Compare", "o5": "🎯 O5 Bayesian", "o6": "📏 O6 Reliability",
             "assume": "🧠 Assumptions vs findings", "phase": "🧪 Phase 1 vs 2", "saved": "💾 Saved runs",
             "report": "📄 Report & glossary"}
T = dict(zip(TAB_NAMES, st.tabs(list(TAB_NAMES.values()))))

# ------------------------------------------------------------------ tab: packets
with T["packets"]:
    st.subheader("Every square is one packet")
    for k in names:
        loss = A[k]["loss"]
        first = int(np.flatnonzero(loss)[0]) if loss.any() else 0
        start = max(0, first - 40)
        show = loss[start:start + 600]
        cells = "".join(f'<span style="background:{BAD if x else DELIV}"></span>' for x in show)
        st.markdown(f'<div class="legend"><b>{k}</b>: packets {start + 1:,} to {start + len(show):,} '
                    f'({len(show) / A[k]["rate"]:g} s) <span style="background:{DELIV}"></span>delivered '
                    f'<span style="background:{BAD}"></span>lost</div><div class="packets">{cells}</div>', unsafe_allow_html=True)
    explain("Red squares sitting next to each other are bursts. If losses were random they would be scattered one by one.")
    st.subheader("Lost packets in each second")
    rows = []
    for k in names:
        c = A[k]["counts"]
        rows += [dict(network=k, second=i + 1, lost=int(v)) for i, v in enumerate(c[:C.TIMELINE_S])]
    if rows:
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar().encode(
            x=alt.X("second:Q", title="time (s)", scale=alt.Scale(domain=[0, max(r["second"] for r in rows)], nice=False)),
            y=alt.Y("lost:Q", title="lost", axis=alt.Axis(format="d", tickMinStep=1)),
            color=alt.Color("network:N", scale=color_scale, legend=None), tooltip=["network", "second", "lost"]
        ).properties(height=120).facet(row=alt.Row("network:N", title=None)).resolve_scale(y="independent"), width="stretch")
    explain("Tall bars with long empty stretches between them mean losses arrive in clumps. Random loss gives small, evenly spread bars.")
    st.subheader("Round-trip time")
    rows = []
    for k in names:
        t, rt = A[k]["t"], A[k]["rtt_all"]
        step = max(1, len(t) // 1500)
        rows += [dict(network=k, t=float(t[i]), rtt=float(rt[i])) for i in range(0, len(t), step) if not np.isnan(rt[i])]
    if rows:
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_circle(size=8, opacity=0.5).encode(
            x=alt.X("t:Q", title="time (s)"), y=alt.Y("rtt:Q", title="round-trip time (ms)", scale=alt.Scale(type="log")),
            color=alt.Color("network:N", scale=color_scale), tooltip=["network", "t", "rtt"]).properties(height=240), width="stretch")
    explain("How long each reply took to come back. Spikes often appear just before or during bursts of loss, when the link is struggling.")

# ------------------------------------------------------------------ tab: O1
with T["o1"]:
    obj("O1", "Do losses per second follow a Poisson distribution?")
    if not full:
        st.info("No capture has enough losses (at least 10) for this test.")
    for k in full:
        r, x = A[k]["res"], A[k]
        c = x["counts"]
        kmax = int(max(np.quantile(c, 0.999), 3)) + 2
        ks = np.arange(kmax + 1)
        obs = np.bincount(c, minlength=kmax + 1)[:kmax + 1] / len(c)
        nb = x["fits"]["negbin"]
        df = pd.concat([
            pd.DataFrame(dict(k=ks, prob=obs, model="observed")),
            pd.DataFrame(dict(k=ks, prob=stats.poisson.pmf(ks, x["fits"]["poisson"]["lam"]), model="Poisson (random loss)")),
            pd.DataFrame(dict(k=ks, prob=stats.nbinom.pmf(ks, nb["r"], nb["p"]), model="Negative Binomial (bursty)"))])
        df = df[df.prob > 1e-6]
        base = alt.Chart(df).encode(x=alt.X("k:O", title="losses in a 1-s window"))
        bars = base.transform_filter(alt.datum.model == "observed").mark_bar(color=COL[k], opacity=0.6).encode(
            y=alt.Y("prob:Q", scale=alt.Scale(type="log", domain=[1e-5, 1]), title="probability (log scale)"), tooltip=["k", "prob"])
        lines = base.transform_filter(alt.datum.model != "observed").mark_line(point=True).encode(
            y="prob:Q", color=alt.Color("model:N", scale=alt.Scale(range=["#2D6A4F", "#222222"]), title=None),
            strokeDash=alt.StrokeDash("model:N", legend=None), tooltip=["model", "k", "prob"])
        t, f, d = r["tests"], r["fits"], r["descriptive"]
        cA, cB = st.columns([3, 2])
        with cA:
            st.markdown(f"**{k}**")
            st.altair_chart((bars + lines).properties(height=260), width="stretch")
        with cB:
            ratio = d["window_var"] / d["window_mean"]
            st.metric("Variance ÷ mean (D)", f"{ratio:.2f}", help="1 for random (Poisson) loss. Above 1 = clumping.")
            st.metric("Dispersion test p", fmt_p(t["dispersion"]["p"]))
            st.metric("χ² Poisson fit p", fmt_p(t["chisq_poisson"]["p"]))
            better = "Negative Binomial" if f["aic_negbin"] < f["aic_poisson"] else "Poisson"
            st.metric("Better model (AIC)", better, f"{f['aic_poisson'] - f['aic_negbin']:+.0f} AIC", delta_color="off")
    explain("For random loss, the count of losses in each second follows a Poisson distribution, whose variance equals its mean (D ≈ 1). "
            "If the bars stay high far to the right of where the black Poisson line falls away, there are too many heavy seconds: losses clump. "
            "A small p-value (below 0.05) rejects Poisson. AIC (Akaike Information Criterion) picks the better model; lower is better.")

# ------------------------------------------------------------------ tab: O2
with T["o2"]:
    obj("O2", "Is the waiting time between losses exponential?")
    if not full:
        st.info("No capture has enough losses for this test.")
    rows = []
    for k in full:
        g = np.sort(A[k]["gaps"])
        if len(g) < 5:
            continue
        surv = 1 - np.arange(1, len(g) + 1) / len(g)
        idx = np.unique(np.linspace(0, len(g) - 2, min(400, len(g) - 1)).astype(int))
        rows += [dict(network=k, t=float(g[i]), surv=float(surv[i]), curve="observed") for i in idx if surv[i] > 0]
        tt = np.linspace(0, float(np.quantile(g, 0.995)), 200)
        ex, hy = A[k]["gap_fits"]["exp"], A[k]["gap_fits"]["hyper"]
        rows += [dict(network=k, t=float(v), surv=float(np.exp(-ex["rate"] * v)), curve="exponential (random)") for v in tt]
        rows += [dict(network=k, t=float(v), surv=float(1 - D.hyperexp_cdf(v, hy["w"], hy["rate_fast"], hy["rate_slow"])),
                      curve="two-phase (bursts)") for v in tt]
    if rows:
        df = pd.DataFrame(rows)
        df = df[df.surv > 1e-3]
        st.altair_chart(alt.Chart(df).mark_line().encode(
            x=alt.X("t:Q", title="time between losses (s)"),
            y=alt.Y("surv:Q", title="P(gap longer than t), log scale", scale=alt.Scale(type="log")),
            color=alt.Color("curve:N", scale=alt.Scale(domain=["observed", "exponential (random)", "two-phase (bursts)"],
                                                       range=[BAD, "#222222", GOOD]), title=None),
            strokeDash=alt.StrokeDash("curve:N", legend=None, scale=alt.Scale(domain=["observed", "exponential (random)", "two-phase (bursts)"],
                                                                         range=[[1, 0], [6, 4], [2, 2]])),
            strokeWidth=alt.value(2), tooltip=["curve", "t", "surv"]
        ).properties(height=230, width=300).facet(column=alt.Column("network:N", title=None)).resolve_scale(x="independent"))
        cols = st.columns(max(1, len(full)))
        for col, k in zip(cols, full):
            r = A[k]["res"]
            ksr, f = r["tests"]["ks_exponential"], r["fits"]
            with col:
                st.markdown(f"**{k}**")
                st.metric("KS test p (exponential)", fmt_p(ksr["p"], ksr["B"]) if ksr else "n/a")
                st.metric("Short gaps (inside bursts)", f"{100 * f['hyper_w_fast']:.0f}%", f"mean {1000 / f['hyper_rate_fast']:.0f} ms", delta_color="off")
                st.metric("Long gaps (between bursts)", f"mean {1 / f['hyper_rate_slow']:.1f} s")
    explain("For random loss the waiting time between losses is exponential, which is a straight line on this log scale (black dashed). "
            "Bursty loss bends: a steep drop from many tiny gaps inside bursts, then a flat tail of long quiet gaps. "
            "The green two-phase mixture, fitted with the EM (Expectation-Maximisation) algorithm, captures that bend. "
            "KS (Kolmogorov-Smirnov) p below 0.05 rejects the exponential; it uses a bootstrap because the rate is estimated from the same data.")

# ------------------------------------------------------------------ tab: O3
with T["o3"]:
    obj("O3", "Does one loss make the next one more likely?")
    if not full:
        st.info("No capture has enough losses for this test.")
    else:
        rows = []
        for k in full:
            mk = A[k]["res"]["markov"]
            rows.append(dict(network=k, which="after a delivered packet, P(L|N)", med=100 * mk["a_q"][1], lo=100 * mk["a_q"][0], hi=100 * mk["a_q"][2]))
            rows.append(dict(network=k, which="after a lost packet, P(L|L)", med=100 * mk["b_q"][1], lo=100 * mk["b_q"][0], hi=100 * mk["b_q"][2]))
        df = pd.DataFrame(rows)
        base = alt.Chart(df).encode(y=alt.Y("network:N", title=None), color=alt.Color("which:N", title=None,
                                    scale=alt.Scale(range=[GREY, BAD])))
        st.altair_chart((base.mark_rule(strokeWidth=3).encode(x=alt.X("lo:Q", title="chance the next packet is lost (%), log scale",
                         scale=alt.Scale(type="log")), x2="hi:Q") +
                         base.mark_point(size=120, filled=True).encode(x="med:Q", tooltip=["network", "which", "med", "lo", "hi"])
                         ).properties(height=70 * len(full) + 40), width="stretch")
        explain("Grey dot: chance of a loss right after a packet that arrived. Red dot: chance right after a packet that was lost. "
                "Lines are 95% credible intervals. If losses were independent the two dots would sit together. "
                "The further apart they are, the more one loss drags the next one with it.")
        c1, c2 = st.columns(2)
        with c1:
            df = pd.DataFrame([dict(network=k, kind=kind, runs=val) for k in full for kind, val in
                               [("expected", A[k]["res"]["tests"]["runs"]["expected"]), ("observed", A[k]["res"]["tests"]["runs"]["runs"])]])
            st.markdown("**Runs: expected vs observed**")
            st.altair_chart(alt.Chart(df).mark_bar().encode(x=alt.X("kind:N", title=None, axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("runs:Q", title="number of runs"), color=alt.Color("kind:N", scale=alt.Scale(range=[GREY, NAVY]), legend=None),
                            column=alt.Column("network:N", title=None), tooltip=["network", "kind", "runs"]).properties(width=110, height=200))
        with c2:
            st.markdown("**Burst lengths (losses in a row)**")
            rows = []
            for k in full:
                bl = A[k]["bursts"]
                vals, cnt = np.unique(np.minimum(bl, 10), return_counts=True)
                rows += [dict(network=k, length=("10+" if v == 10 else str(int(v))), share=c / len(bl), order=int(v)) for v, c in zip(vals, cnt)]
            len_order = [str(i) for i in range(1, 10)] + ["10+"]
            st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar().encode(
                x=alt.X("length:N", sort=[v for v in len_order if v in {r["length"] for r in rows}], title="burst length (packets)", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("share:Q", title="share of bursts", axis=alt.Axis(format="%")), color=alt.Color("network:N", scale=alt.Scale(domain=list(full), range=[COL[k] for k in full])),
                xOffset="network:N", tooltip=["network", "length", alt.Tooltip("share:Q", format=".1%")]).properties(height=220), width="stretch")
        st.dataframe(pd.DataFrame([dict(
            Network=k, **{"Runs z": round(A[k]["res"]["tests"]["runs"]["z"], 1), "Runs p": fmt_p(A[k]["res"]["tests"]["runs"]["p"]),
                          "Markov G²": round(A[k]["res"]["tests"]["markov_lrt"]["G2"], 1), "Markov p": fmt_p(A[k]["res"]["tests"]["markov_lrt"]["p"]),
                          "b/a (median)": round(A[k]["res"]["markov"]["amp_q"][1], 1),
                          "Mean burst (packets)": round(A[k]["res"]["markov"]["burst_len_q"][1], 2),
                          "Verdict": {"bursty": "bursty", "random": "no evidence of bursts"}[verdict(A[k]["res"])]}) for k in full]),
            hide_index=True, width="stretch")
        explain("A run is a stretch of identical outcomes. Bursts glue losses together, so there are fewer runs than chance predicts "
                "(negative z, small p). The Markov likelihood-ratio test (G², compared with χ² on 1 degree of freedom by Wilks' theorem) "
                "asks directly whether P(L|L) differs from P(L|N). b/a is how many times likelier a loss is right after a loss; 1 means random.")

# ------------------------------------------------------------------ tab: O4
with T["o4"]:
    obj("O4", "Do the networks differ?")
    if len(names) < 2:
        st.info("Record or pick at least two networks to compare them.")
    else:
        rows = []
        for k in names:
            p = A[k]["res"]["posterior"]
            a_, b_ = p["alpha"], p["beta"]
            lo, hi = stats.beta.ppf([1e-4, 1 - 1e-4], a_, b_)
            for xv in np.linspace(lo, hi, 200):
                rows.append(dict(network=k, rate=100 * xv, density=stats.beta.pdf(xv, a_, b_) / 100))
        st.markdown("**Loss rate of each network (posterior distribution)**")
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_area(opacity=0.45, line=True).encode(
            x=alt.X("rate:Q", title="loss rate (%)"), y=alt.Y("density:Q", title="posterior density", axis=None, stack=None),
            color=alt.Color("network:N", scale=color_scale), tooltip=["network", "rate"]).properties(height=230), width="stretch")
        rng = np.random.default_rng(C.SEED)
        draws = {k: rng.beta(A[k]["res"]["posterior"]["alpha"], A[k]["res"]["posterior"]["beta"], 50000) for k in names}
        order = sorted(names, key=lambda k: A[k]["res"]["posterior"]["mean"])
        p_order = float(np.mean(np.all([draws[order[i]] < draws[order[i + 1]] for i in range(len(order) - 1)], axis=0)))
        cmp = HT.compare_scenarios({k: A[k]["counts"] for k in names}, {k: A[k]["loss"] for k in names})
        c1, c2, c3 = st.columns(3)
        c1.metric("Kruskal-Wallis H", f"{cmp['kruskal_H']:.1f}", f"{peq(cmp['kruskal_p'])}", delta_color="off")
        c2.metric("χ² homogeneity", f"{cmp['chi2_homog']:.1f}", f"{peq(cmp['chi2_p'])}", delta_color="off")
        c3.metric("P(" + " < ".join(order) + ")", f"{p_order:.3f}", "from 50,000 posterior draws", delta_color="off")
        st.dataframe(pd.DataFrame([{"Pair": f"{q['a']} vs {q['b']}", "Mann-Whitney U": f"{q['U']:,.0f}",
                                    "p (Bonferroni)": fmt_p(q["p_bonf"]),
                                    "Different at 5%?": "yes" if q["p_bonf"] < ALPHA else "no"}
                                   for q in cmp["pairwise"]]), hide_index=True, width="stretch")
        explain("Kruskal-Wallis compares losses per second across all networks at once using ranks, because the counts are mostly zeros "
                "and far from normal. Mann-Whitney compares pairs; Bonferroni multiplies each p-value by the number of pairs so that "
                "testing several pairs does not inflate false alarms. The χ² homogeneity test asks whether the loss proportion is the same everywhere.")

# ------------------------------------------------------------------ tab: O5
with T["o5"]:
    obj("O5", "Bayesian estimate of each loss rate")
    rows = []
    for k in names:
        rows += [dict(network=k, t=q["t"], mean=100 * q["mean"], lo=100 * q["lo"], hi=100 * q["hi"]) for q in A[k]["seq_curve"]]
    df = pd.DataFrame(rows)
    st.markdown("**What we believed about the loss rate as packets came in**")
    band = alt.Chart(df).mark_area(opacity=0.2).encode(x=alt.X("t:Q", title="time into the capture (s)"),
                                                       y=alt.Y("lo:Q", title="loss rate (%)"), y2="hi:Q",
                                                       color=alt.Color("network:N", scale=color_scale))
    line = alt.Chart(df).mark_line().encode(x="t:Q", y="mean:Q", color=alt.Color("network:N", scale=color_scale),
                                            tooltip=["network", "t", "mean", "lo", "hi"])
    st.altair_chart((band + line).properties(height=260), width="stretch")
    explain("We start from a flat Beta(1, 1) prior: before any packet, every loss rate is equally plausible. After k losses in n packets "
            "the posterior is Beta(1 + k, 1 + n − k). The shaded band is the 95% credible interval; it narrows as evidence builds up.")
    st.dataframe(pd.DataFrame([dict(Network=k, **{
        "Posterior mean": pct(A[k]["res"]["posterior"]["mean"], 3),
        "95% credible interval": f"[{pct(A[k]['res']['posterior']['ci_low'], 3)}, {pct(A[k]['res']['posterior']['ci_high'], 3)}]",
        "Heavy seconds predicted (if random)": (f"{100 * A[k]['res']['predictive_tail']['predicted']:.3f}% of seconds" if A[k]["res"]["enough_losses"] else "n/a"),
        "Heavy seconds observed": (f"{100 * A[k]['res']['predictive_tail']['observed']:.3f}% of seconds" if A[k]["res"]["enough_losses"] else "n/a")})
        for k in names]), hide_index=True, width="stretch")
    explain(f"Posterior predictive check: if losses were random, how often would a second contain {C.HEAVY_LOSS_K} or more losses? "
            "If the observed share is far above the predicted one, the random model cannot explain the data.")

# ------------------------------------------------------------------ tab: O6
with T["o6"]:
    obj("O6", "Can we trust the usual 95% interval, and was the capture long enough?")
    if not full:
        st.info("No capture has enough losses for this check.")
    else:
        rows = []
        for k in full:
            r = A[k]["res"]
            for kind, p in [("naive", r["posterior"]), ("adjusted", r["adjusted_posterior"])]:
                rows.append(dict(network=k, kind=kind, mid=100 * p["mean"], lo=100 * p["ci_low"], hi=100 * p["ci_high"]))
        df = pd.DataFrame(rows)
        base = alt.Chart(df).encode(y=alt.Y("kind:N", title=None), color=alt.Color("kind:N", scale=alt.Scale(range=[GOOD, GREY]), legend=None))
        st.markdown("**95% interval for the loss rate: naive vs adjusted**")
        st.altair_chart((base.mark_rule(strokeWidth=6).encode(x=alt.X("lo:Q", title="loss rate (%)"), x2="hi:Q") +
                         base.mark_tick(color="black", thickness=2, size=18).encode(x="mid:Q", tooltip=["kind", "lo", "mid", "hi"])
                         ).properties(height=70).facet(row=alt.Row("network:N", title=None)).resolve_scale(x="independent"), width="stretch")
        explain("The naive interval treats every packet as independent evidence. Inside a burst, packets share their fate, so there is less "
                "real information. The design effect (deff) = variance of 10-second block counts ÷ the variance random loss would give. "
                "Dividing n by deff gives the effective sample size and a wider, honest interval.")
        cov = pd.DataFrame([dict(network=k, kind=kind, coverage=100 * A[k]["coverage"][key]) for k in full
                            for kind, key in [("naive", "naive"), ("adjusted", "adjusted")]])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**How often would each interval be right on this network?**")
            cov["target"] = 95
            base_c = alt.Chart(cov)
            bars = base_c.mark_bar().encode(x=alt.X("kind:N", title=None, axis=alt.Axis(labelAngle=0)),
                                            y=alt.Y("coverage:Q", title="coverage (%)", scale=alt.Scale(domain=[0, 100])),
                                            color=alt.Color("kind:N", scale=alt.Scale(range=[GOOD, GREY]), legend=None),
                                            tooltip=["network", "kind", alt.Tooltip("coverage:Q", format=".1f")])
            rule = base_c.mark_rule(color=BAD, strokeDash=[4, 4]).encode(y="target:Q")
            st.altair_chart(alt.layer(bars, rule).properties(width=120, height=220).facet(column=alt.Column("network:N", title=None)))
        with c2:
            st.markdown("**Was the capture long enough? (power of the runs test)**")
            rows = []
            for k in full:
                rows += [dict(network=k, minutes=q["duration_s"] / 60, power=q["power"]) for q in A[k]["power"]]
            pw = alt.Chart(pd.DataFrame(rows)).mark_line(point=True).encode(
                x=alt.X("minutes:Q", title="capture length (minutes), log scale", scale=alt.Scale(type="log")),
                y=alt.Y("power:Q", title="power", scale=alt.Scale(domain=[0, 1])), color=alt.Color("network:N", scale=color_scale),
                tooltip=["network", "minutes", "power"])
            st.altair_chart((pw + alt.Chart(pd.DataFrame({"y": [C.POWER_TARGET]})).mark_rule(color=GREY, strokeDash=[4, 4]).encode(y="y:Q")
                             ).properties(height=250), width="stretch")
        explain("A real network's true loss rate is unknown, so we fit a two-state Markov chain to each capture (using its P(L|N) and P(L|L)) "
                "and replay it 1,000 times. Left: how often each kind of 95% interval would contain that network's true long-run rate. "
                f"Right: the chance the runs test spots the bursts for different capture lengths; the dotted line is the {C.POWER_TARGET:g} target. "
                "Monte Carlo standard error is about 1 percentage point.")

# ------------------------------------------------------------------ tab: Phase 1 vs 2
with T["phase"]:
    st.subheader("Simulated networks (Phase 1) next to real ones (Phase 2)")
    ph1 = os.path.join(ROOT, "results", "results.json")
    rows = []
    if os.path.exists(ph1):
        R1 = json.load(open(ph1))
        for key, s in R1["scenarios"].items():
            d = s["descriptive"]
            rows.append(dict(Phase="1 simulated", Network=s["label"], loss=100 * d["loss_rate"], D=d["window_var"] / d["window_mean"],
                             ba=s["bayes"]["markov"]["amp_q"][1], burst=s["bayes"]["markov"]["burst_len_q"][1],
                             deff=s["bayes"]["adjusted_posterior"]["deff"]))
    for k in full:
        r = A[k]["res"]
        rows.append(dict(Phase="2 real", Network=k, loss=100 * r["loss_rate"], D=r["descriptive"]["window_var"] / r["descriptive"]["window_mean"],
                         ba=r["markov"]["amp_q"][1], burst=r["markov"]["burst_len_q"][1], deff=r["adjusted_posterior"]["deff"]))
    if rows:
        df = pd.DataFrame(rows)
        st.altair_chart(alt.Chart(df).mark_point(size=160, filled=True).encode(
            x=alt.X("loss:Q", title="loss rate (%), log scale", scale=alt.Scale(type="log")),
            y=alt.Y("ba:Q", title="b/a, log scale", scale=alt.Scale(type="log")),
            shape=alt.Shape("Phase:N"), color=alt.Color("Phase:N", scale=alt.Scale(range=[GREY, BAD])),
            tooltip=["Phase", "Network", "loss", "ba", "deff"]).properties(height=300) +
            alt.Chart(df).mark_text(dx=10, align="left", fontSize=11).encode(x="loss:Q", y="ba:Q", text="Network:N"), width="stretch")
        st.dataframe(df.rename(columns={"loss": "Loss rate (%)", "D": "Var ÷ mean", "ba": "b/a", "burst": "Mean burst", "deff": "Design effect"})
                     .round(3), hide_index=True, width="stretch")
        explain("b/a = 1 is the line of pure randomness. Points far above it are bursty. If the real networks sit near the simulated ones, "
                "the Gilbert-Elliott model from Phase 1 was a realistic choice; if they sit elsewhere, the real data tell us how to retune it.")

# ------------------------------------------------------------------ tab: report and glossary
with T["report"]:
    st.subheader("Download everything")

    @st.cache_data(show_spinner=False)
    def build_zip(paths_mtimes):
        buf = io.BytesIO()
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "captures")
            os.makedirs(sub)
            for pth, _ in paths_mtimes:
                for ext in (".csv", ".json"):
                    if os.path.exists(pth[:-4] + ext):
                        with open(pth[:-4] + ext, "rb") as src, open(os.path.join(sub, os.path.basename(pth[:-4] + ext)), "wb") as dst:
                            dst.write(src.read())
            subprocess.run([sys.executable, os.path.join(ROOT, "realworld", "analyze_captures.py"), "--captures", sub,
                            "--out", os.path.join(tmp, "results")], check=True, capture_output=True, cwd=ROOT)
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for folder in ("results", "captures"):
                    for f in sorted(os.listdir(os.path.join(tmp, folder))):
                        z.write(os.path.join(tmp, folder, f), f"{folder}/{f}")
        return buf.getvalue()

    if st.button("Prepare report (summary, figures, data)", type="primary"):
        with st.spinner("Building the report..."):
            data = build_zip(tuple((p, by_path[p]["mtime"]) for p in chosen))
        st.download_button("⬇️ Download Phase2_report.zip", data, file_name="Phase2_report.zip", mime="application/zip")
    st.caption("Contains summary.md (all tables), results.json (every number), four report-ready figures and the raw captures.")

    st.subheader("Glossary")
    st.dataframe(pd.DataFrame([
        ("p-value", "Probability of a result at least this extreme if the null hypothesis were true. Below 0.05 = reject."),
        ("α (alpha)", "Significance level, 0.05: the false-alarm rate we accept."),
        ("D, variance ÷ mean", "Index of dispersion of losses per second. 1 for random (Poisson) loss."),
        ("Poisson", "Count distribution for independent rare events; variance equals mean."),
        ("Negative Binomial (NB)", "Poisson whose rate varies; allows variance > mean, i.e. clumping."),
        ("χ² (chi-square) test", "Compares observed and expected counts (goodness of fit, homogeneity)."),
        ("AIC", "Akaike Information Criterion = 2k − 2 ln L. Lower means the better model."),
        ("KS test", "Kolmogorov-Smirnov: largest gap between data and model curves; bootstrapped here."),
        ("EM algorithm", "Expectation-Maximisation: fits the two-phase mixture of short and long gaps."),
        ("Runs test", "Wald-Wolfowitz: too few runs of identical outcomes means losses cluster."),
        ("P(L|N), P(L|L)", "Chance of a loss after a delivered packet (a), after a lost packet (b)."),
        ("b/a", "How many times likelier a loss is right after a loss. 1 = independent."),
        ("Markov LRT, G²", "Likelihood-ratio test of 'a = b'; G² ~ χ²(1) by Wilks' theorem."),
        ("Kruskal-Wallis, Mann-Whitney", "Rank tests comparing networks (all at once / in pairs)."),
        ("Bonferroni", "Multiply p-values by the number of comparisons to keep false alarms at 5%."),
        ("Beta(1, 1) prior", "Flat starting belief: every loss rate equally plausible."),
        ("Posterior, credible interval", "Updated belief after data; 95% interval contains the rate with 95% probability."),
        ("Posterior predictive check", "Ask the fitted random model to predict heavy seconds and compare with reality."),
        ("Design effect (deff)", "Real variance ÷ variance under independence. n ÷ deff = effective sample size."),
        ("Coverage", "How often a '95%' interval actually contains the true value."),
        ("Power", "Chance a test detects bursts that are really there."),
        ("Monte Carlo", "Answering a question by simulating it many times."),
        ("RTT", "Round-trip time: how long a reply takes to come back (ms)."),
    ], columns=["Term", "Plain meaning"]), hide_index=True, width="stretch")

# ------------------------------------------------------------------ tab: live run vs the case study
RUN_C, REF_C = "#2E6DB4", "#E07A1F"


def fmt_ci(ci, d=3):
    return f"[{pct(ci[0], d)}, {pct(ci[1], d)}]"


def series_for(source):
    """Packets, counts per second and gaps of a real run (key in A) or a study network (key in SR.KEYS)."""
    if source in SR.KEYS:
        tr = study_traces()[source]
        return tr["loss"], tr["counts"], tr["gaps"], tr["rate"]
    x = A[source]
    return x["loss"], x["counts"], x.get("gaps"), x["rate"]


with T["vs"]:
    st.subheader("Your real run next to the case study")
    R1 = study_results()
    pre_run = next((k for k in names if KEY2PATH[k] == st.session_state.get("vs_run_path")), None)
    v1, v2 = st.columns(2)
    run_k = v1.selectbox("Your run", names, index=names.index(pre_run) if pre_run else len(names) - 1, key="vs_run")
    ref_opts = ([f"Case study: {SR.label(k)}" for k in SR.KEYS] if R1 else []) + [f"Another run: {k}" for k in names if k != run_k]
    if not ref_opts:
        st.info("The case-study results (results/results.json) are missing. Run `python3 run_case_study.py` once.")
    else:
        want = st.session_state.get("vs_ref_key") if pre_run == run_k else None
        want = want or SR.match(RS[run_k]["network"])
        idx = next((i for i, o in enumerate(ref_opts) if R1 and o == f"Case study: {SR.label(want)}"), 0)
        ref_pick = v2.selectbox("Compare with", ref_opts, index=idx, key="vs_ref",
                                help="The case-study network your run is meant to resemble, or another of your runs.")
        if ref_pick.startswith("Case study"):
            ref_src = next(k for k in SR.KEYS if ref_pick.endswith(SR.label(k)))
            REF = SR.summary(R1, ref_src)
            ref_name = SR.label(ref_src) + " (study)"
        else:
            ref_src = ref_pick.split(": ", 1)[1]
            REF = RS[ref_src]
            ref_name = ref_src
        RUN = RS[run_k]
        rr, rf = reading(RUN), reading(REF)

        # headline: two cards side by side
        def card(s, title, colour):
            bits = [f"<span>Loss rate <b>{pct(s['loss_rate'], 3)}</b> {fmt_ci(s['ci'])}</span>",
                    f"<span><b>{s['losses']:,}</b> of {s['packets']:,} lost</span>",
                    f"<span>{nice_dur(s['duration_s'])}</span>"]
            if "ba" in s:
                bits += [f"<span>Next loss <b>{s['ba']:.1f}×</b> likelier after a loss</span>",
                         f"<span>Mean burst <b>{s['mean_burst']:.2f}</b></span>", f"<span>Design effect <b>{s['deff']:.2f}</b></span>"]
            return (f'<div class="net" style="border-left:7px solid {colour}"><h4>{title}: {VERDICT_TXT[s["verdict"]]}</h4>'
                    f'<div class="row">{"".join(bits)}</div></div>')
        h1, h2 = st.columns(2)
        h1.markdown(card(RUN, f"Your run: {run_k}", RUN_C), unsafe_allow_html=True)
        h2.markdown(card(REF, ref_name, REF_C), unsafe_allow_html=True)

        # side-by-side table
        lo, hi = RUN["ci"]
        same_level = lo <= REF["loss_rate"] <= hi
        rows = [dict(Measure="Loss rate", Reference=f"{pct(REF['loss_rate'], 3)}", **{"Your run": f"{pct(RUN['loss_rate'], 3)} {fmt_ci(RUN['ci'])}"},
                     **{"Same story?": "✅ same level" if same_level else
                        f"❌ {'higher' if RUN['loss_rate'] > REF['loss_rate'] else 'lower'} ({RUN['loss_rate'] / max(REF['loss_rate'], 1e-12):.2f}×)"})]
        if rr and rf:
            def row(m, key, fr, fu):
                rows.append({"Measure": m, "Reference": f"{fr} → {rf[key]}", "Your run": f"{fu} → {rr[key]}",
                             "Same story?": "✅ yes" if rr[key] == rf[key] else "❌ no"})
            row("O1 Var ÷ mean (D), Poisson tests", "poisson", f"D = {REF['D']:.2f}", f"D = {RUN['D']:.2f}")
            row("O2 Gaps, KS test", "gaps", f"{peq(REF['ks_p'], REF.get('ks_B'))}", f"{peq(RUN['ks_p'], RUN.get('ks_B'))}")
            row("O3 Runs test", "runs", f"z = {REF['runs_z']:.1f}", f"z = {RUN['runs_z']:.1f}")
            row("O3 P(L|L) vs P(L|N), Markov test", "markov", f"b/a = {REF['ba']:.1f}", f"b/a = {RUN['ba']:.1f}")
            row("O6 Naive 95% interval coverage", "interval",
                f"{pct(REF.get('cov_naive'), 0)}" if REF.get("cov_naive") is not None else "n/a",
                f"{pct(RUN.get('cov_naive'), 0)}" if RUN.get("cov_naive") is not None else "n/a")
            rows.append({"Measure": "Overall verdict", "Reference": VERDICT_TXT[REF["verdict"]], "Your run": VERDICT_TXT[RUN["verdict"]],
                         "Same story?": "✅ yes" if REF["verdict"] == RUN["verdict"] else "❌ no"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        agree = sum(r_["Same story?"].startswith("✅") for r_ in rows[1:])
        if rr and rf:
            explain(f"<b>{agree} of {len(rows) - 1}</b> checks tell the same story as {ref_name}. "
                    f"Your loss rate is {RUN['loss_rate'] / max(REF['loss_rate'], 1e-12):.2f}× the reference "
                    f"({'inside' if same_level else 'outside'} your run's 95% credible interval). "
                    "The burst checks matter more than the level: a network can lose fewer packets than the study's and still lose them in bursts.")
        else:
            explain("Your run has fewer than 10 losses, so only the loss rate can be compared. The burst tests need more losses: "
                    "record longer, at a busier time, or further from the router.")

        # charts: the same four views, both sources overlaid
        Lr, Cr, Gr, rate_r = series_for(run_k)
        Lf, Cf, Gf, rate_f = series_for(ref_src)
        src_scale = alt.Scale(domain=[f"your run: {run_k}", ref_name], range=[RUN_C, REF_C])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Loss rate as the run went on**")
            n_r = len(Lr)
            seq_r = pd.DataFrame(LS.sequential_curve(Lr, rate_r)).assign(source=f"your run: {run_k}")
            seq_f = pd.DataFrame(LS.sequential_curve(Lf[:max(n_r, 10)], rate_f)).assign(source=ref_name)
            dfq = pd.concat([seq_r, seq_f])
            for col in ("mean", "lo", "hi"):
                dfq[col] *= 100
            band = alt.Chart(dfq).mark_area(opacity=0.18).encode(x=alt.X("t:Q", title="time into the run (s)"),
                                                                 y=alt.Y("lo:Q", title="loss rate (%)"), y2="hi:Q",
                                                                 color=alt.Color("source:N", scale=src_scale, title=None))
            line = alt.Chart(dfq).mark_line(strokeWidth=2).encode(x="t:Q", y="mean:Q", color=alt.Color("source:N", scale=src_scale, title=None),
                                                                 tooltip=["source", "t", alt.Tooltip("mean:Q", format=".3f")])
            st.altair_chart((band + line).properties(height=240).configure_legend(orient="bottom"), width="stretch")
        with c2:
            st.markdown("**Losses in each second (log scale)**")
            kmax = 10
            rows = []
            for nm_, cnt in [(f"your run: {run_k}", Cr), (ref_name, Cf)]:
                b_ = np.bincount(np.minimum(cnt, kmax), minlength=kmax + 1) / len(cnt)
                rows += [dict(source=nm_, k=("10+" if i == kmax else str(i)), order=i, share=float(v)) for i, v in enumerate(b_) if v > 0]
            st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(point=True, strokeWidth=2).encode(
                x=alt.X("k:N", sort=[str(i) for i in range(kmax)] + ["10+"], title="losses in a 1-s window", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("share:Q", scale=alt.Scale(type="log"), title="share of seconds"),
                color=alt.Color("source:N", scale=src_scale, title=None), tooltip=["source", "k", alt.Tooltip("share:Q", format=".4f")]
            ).properties(height=240).configure_legend(orient="bottom"), width="stretch")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Chance of a loss: after a delivered vs after a lost packet**")
            rows = []
            for nm_, s_ in [(f"your run: {run_k}", RUN), (ref_name, REF)]:
                if "a" in s_:
                    rows += [dict(source=nm_, after="after delivered, P(L|N)", p=100 * s_["a"]),
                             dict(source=nm_, after="after lost, P(L|L)", p=100 * s_["b"])]
            if rows:
                st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_bar().encode(
                    x=alt.X("after:N", title=None, axis=alt.Axis(labelAngle=0, labelLimit=200)), xOffset="source:N",
                    y=alt.Y("p:Q", title="chance of a loss (%)"),
                    color=alt.Color("source:N", scale=src_scale, title=None), tooltip=["source", "after", alt.Tooltip("p:Q", format=".3f")]
                ).properties(height=240).configure_legend(orient="bottom"), width="stretch")
            else:
                st.caption("Needs at least 10 losses in both.")
        with c4:
            st.markdown("**Time between losses (log scale)**")
            rows = []
            for nm_, g in [(f"your run: {run_k}", Gr), (ref_name, Gf)]:
                if g is None or len(g) < 5:
                    continue
                g = np.sort(g)
                surv = 1 - np.arange(1, len(g) + 1) / len(g)
                idx = np.unique(np.linspace(0, len(g) - 2, min(300, len(g) - 1)).astype(int))
                rows += [dict(source=nm_, t=float(g[i]), surv=float(surv[i])) for i in idx if surv[i] > 0]
            if rows:
                st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2).encode(
                    x=alt.X("t:Q", title="gap between losses (s)"),
                    y=alt.Y("surv:Q", scale=alt.Scale(type="log"), title="P(gap > t)"),
                    color=alt.Color("source:N", scale=src_scale, title=None), tooltip=["source", "t", "surv"]
                ).properties(height=240).configure_legend(orient="bottom"), width="stretch")
            else:
                st.caption("Needs at least 10 losses in both.")
        explain("Blue is your run, orange the reference. For the case study, the reference curve on the left uses the study's "
                "simulated packets for the same length of time as your run, so both had the same chance to settle. "
                "Bursty networks show a long right tail of heavy seconds, a much taller 'after lost' bar, and a gap curve that "
                "drops fast and then flattens.")

# ------------------------------------------------------------------ tab: assumptions vs findings
with T["assume"]:
    st.subheader("What we assumed, what the case study showed, what your runs show, and why")
    R1 = study_results()
    ST = {k: SR.summary(R1, k) for k in SR.KEYS} if R1 else {}
    FR = [RS[k] for k in names if "D" in RS[k]]

    def rng_txt(vals, f):
        vals = [v for v in vals if v is not None]
        return f(min(vals)) if len(vals) == 1 or f(min(vals)) == f(max(vals)) else f"{f(min(vals))} to {f(max(vals))}"

    def per_run(fn):
        if not FR:
            return "No run has 10 or more losses yet, so this cannot be tested on real data."
        return "; ".join(f"{s['name']}: {fn(s)}" for s in FR)

    def count_txt(key, bad_value):
        if not FR:
            return ""
        n_bad = sum(reading(s)[key] == bad_value for s in FR)
        return f"**{n_bad} of {len(FR)}** runs reject it. "

    st_ba = rng_txt([ST[k]["ba"] for k in ST], lambda v: f"{v:.0f}×") if ST else "n/a"
    st_D = rng_txt([ST[k]["D"] for k in ST], lambda v: f"{v:.1f}") if ST else "n/a"
    st_cn = rng_txt([ST[k]["cov_naive"] for k in ST], lambda v: f"{100 * v:.0f}%") if ST else "n/a"
    st_ca = rng_txt([ST[k]["cov_adjusted"] for k in ST], lambda v: f"{100 * v:.0f}%") if ST else "n/a"
    pw_txt = ""
    if R1:
        bits = []
        for k in SR.KEYS:
            curve = R1["power"][k]["runs"]
            first = next((d_ for d_, pw in zip(R1["power"]["durations_s"], curve) if pw >= C.POWER_TARGET), None)
            bits.append(f"{SR.label(k)} {nice_dur(first) if first else 'over 10 min'}")
        pw_txt = ", ".join(bits)
    kw_txt = "Record at least two networks."
    if len(names) >= 2:
        cmp_ = HT.compare_scenarios({k: A[k]["counts"] for k in names}, {k: A[k]["loss"] for k in names})
        kw_txt = (f"Kruskal-Wallis H = {cmp_['kruskal_H']:.1f}, {peq(cmp_['kruskal_p'])}; "
                  f"χ² homogeneity {peq(cmp_['chi2_p'])}: the loss rates "
                  f"{'differ' if cmp_['chi2_p'] < ALPHA else 'do not differ detectably'}.")

    def power_at(k):
        """Power of the runs test (fitted chain) for this run's own length."""
        pts = A[k].get("power") or []
        target = max(60, A[k]["res"]["duration_s"])
        return min(pts, key=lambda q: abs(q["duration_s"] - target))["power"] if pts else float("nan")

    ITEMS = [
        ("Losses are independent: every packet is its own coin flip",
         f"Rejected for all three networks. Runs test p < 1e-10 and a loss makes the next one {st_ba} likelier.",
         count_txt("runs", "losses cluster") + per_run(lambda s: f"b/a = {s['ba']:.1f}, runs {peq(s['runs_p'])}"),
         "Interference, fading and a full router queue last much longer than the 20 ms between packets, so one cause knocks out "
         "several packets in a row. The channel has memory: it sits in a Good or a Bad state for a while (the Gilbert-Elliott model)."),
        ("Losses per second follow a Poisson distribution (variance = mean)",
         f"Rejected. Variance ÷ mean D = {st_D}, dispersion and χ² p < 0.05; the Negative Binomial wins on AIC.",
         count_txt("poisson", "not Poisson (clumped)") + per_run(lambda s: f"D = {s['D']:.2f}, dispersion {peq(s['disp_p'])}"),
         "Bursts pile many losses into a few seconds and leave the rest empty, so the counts spread out more than Poisson allows. "
         "A Negative Binomial is a Poisson whose rate itself changes (Good vs Bad state), which is exactly that."),
        ("The time between losses is exponential",
         "Rejected for all three (bootstrap KS p < 0.0005). A two-phase mixture fits: short gaps inside bursts, long gaps between.",
         count_txt("gaps", "not exponential") + per_run(lambda s: f"KS {peq(s['ks_p'], s.get('ks_B'))}"),
         "An exponential has one time scale. Bursty loss has two: milliseconds inside a burst and seconds between bursts, "
         "so the curve drops fast and then flattens."),
        ("The usual 95% interval for the loss rate can be trusted",
         f"No. It held the true rate only {st_cn} of the time. The design-effect interval restored {st_ca}.",
         count_txt("interval", "usual 95% interval too narrow") + per_run(
             lambda s: f"deff = {s['deff']:.2f}, naive {pct(s.get('cov_naive'), 0)} vs adjusted {pct(s.get('cov_adjusted'), 0)}"),
         "The usual formula counts every packet as separate evidence. Packets in the same burst share one fate, so the real "
         "amount of information is n ÷ deff. Too much confidence makes the interval too narrow."),
        ("All networks lose packets at the same rate",
         "Rejected: Kruskal-Wallis H = 937, every pair different after Bonferroni.",
         kw_txt,
         "Each link has different causes of loss: a cable rarely drops packets, a crowded Wi-Fi channel and a cellular link do."),
        ("A short capture is enough to see the bursts",
         f"Not on a good link. The runs test needs about: {pw_txt} to reach power {C.POWER_TARGET:g}.",
         per_run(lambda s: f"{nice_dur(s['duration_s'])} recorded, runs-test power at that length {power_at(s['name']):.2f}"),
         "Bursts are rare events. On a clean link a short run may hold no burst at all, so there is nothing to detect. "
         "Power grows with length, which is why 10 minutes is recommended."),
        ("The flat Beta(1, 1) prior does not bias the estimate",
         "Held. The prior is worth one loss and one delivery against 180,000 packets.",
         "; ".join(f"{k}: prior worth 2 packets vs {RS[k]['packets']:,} measured" for k in names),
         "With thousands of packets the data swamp the prior, so Bayesian and plain estimates agree; the prior only matters in the first seconds."),
    ]
    for i, (assumed, study, yours, why) in enumerate(ITEMS, 1):
        with st.container(border=True):
            st.markdown(f"**{i}. {assumed}**")
            a1, a2, a3 = st.columns(3)
            a1.markdown("*We assumed*  \n" + assumed)
            a2.markdown("*Case study (Phase 1) found*  \n" + study)
            a3.markdown("*Your runs (Phase 2) show*  \n" + yours)
            explain("<b>Why:</b> " + why)

# ------------------------------------------------------------------ tab: saved runs
def _show_in_tabs(path):
    if path not in st.session_state.get("chosen", []):
        st.session_state["chosen"] = st.session_state.get("chosen", []) + [path]


def _delete(run_id, path):
    RL.delete_run(run_id)
    st.session_state["chosen"] = [p for p in st.session_state.get("chosen", []) if p != path]


with T["saved"]:
    st.subheader("Save a run")
    with st.form("save_any", border=True):
        s1, s2, s3 = st.columns([1, 1, 2])
        pick = s1.selectbox("Run", names)
        nm = s2.text_input("Name", placeholder="e.g. Hostel Wi-Fi, evening")
        nt = s3.text_input("Note", placeholder="where, when, anything unusual")
        if st.form_submit_button("💾 Save", type="primary"):
            RL.save_run(KEY2PATH[pick], nm or pick, nt, RS[pick])
            st.success(f"Saved “{nm or pick}”.")
    st.caption(f"Saved runs are kept in `{os.path.relpath(RL.folder(), ROOT)}` with their packets and results, "
               "and can be picked in the sidebar (marked 💾) like any capture.")

    runs = RL.list_runs()
    st.subheader(f"Saved runs ({len(runs)})")
    if not runs:
        st.info("Nothing saved yet. Record a run and press **💾 Save run**, or save any run above.")
    else:
        tbl = pd.DataFrame([{
            "Name": r_["name"], "Network": r_.get("network"), "Recorded": r_.get("captured", "")[:16].replace("T", " "),
            "Length": nice_dur(r_["duration_s"]), "Packets": r_["packets"], "Lost": r_["losses"],
            "Loss rate": pct(r_["loss_rate"], 3), "95% interval": fmt_ci(r_["ci"]),
            "b/a": round(r_["ba"], 1) if "ba" in r_ else None, "Mean burst": round(r_["mean_burst"], 2) if "mean_burst" in r_ else None,
            "Design effect": round(r_["deff"], 2) if "deff" in r_ else None, "Verdict": VERDICT_TXT[r_["verdict"]],
            "Note": r_.get("note", ""), "Saved": r_.get("saved_at", "")[:16].replace("T", " ")} for r_ in runs])
        st.dataframe(tbl, hide_index=True, width="stretch")
        st.download_button("⬇️ Download this table (CSV)", tbl.to_csv(index=False).encode(), "saved_runs.csv", "text/csv")

        vcol = alt.Scale(domain=list(VERDICT_TXT.values()), range=[BAD, GOOD, GREY])
        dfr = pd.DataFrame([dict(name=r_["name"], rate=100 * r_["loss_rate"], lo=100 * r_["ci"][0], hi=100 * r_["ci"][1],
                                 verdict=VERDICT_TXT[r_["verdict"]], ba=r_.get("ba")) for r_ in runs])
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Loss rate of each saved run (95% interval)**")
            base = alt.Chart(dfr).encode(y=alt.Y("name:N", title=None), color=alt.Color("verdict:N", scale=vcol, legend=None))
            st.altair_chart((base.mark_rule(strokeWidth=4).encode(x=alt.X("lo:Q", title="loss rate (%)"), x2="hi:Q") +
                             base.mark_point(filled=True, size=110).encode(x="rate:Q", tooltip=["name", "rate", "lo", "hi", "verdict"]))
                            .properties(height=50 * len(dfr) + 40), width="stretch")
        with g2:
            st.markdown("**How much a loss pulls in the next (b/a, log scale)**")
            dba = dfr.dropna(subset=["ba"])
            if len(dba):
                dba = dba.assign(one=1.0)
                bb = alt.Chart(dba).encode(y=alt.Y("name:N", title=None), color=alt.Color("verdict:N", scale=vcol, legend=None))
                st.altair_chart((bb.mark_rule(strokeWidth=4).encode(x=alt.X("one:Q", title="b/a (1 = independent), log scale",
                                                                            scale=alt.Scale(type="log")), x2="ba:Q") +
                    bb.mark_point(filled=True, size=110).encode(x="ba:Q", tooltip=["name", alt.Tooltip("ba:Q", format=".1f")]) +
                    alt.Chart(pd.DataFrame({"x": [1]})).mark_rule(color="black", strokeDash=[4, 4]).encode(x="x:Q"))
                    .properties(height=50 * len(dba) + 40), width="stretch")
            else:
                st.caption("No saved run has enough losses for b/a yet.")

        st.markdown("**Open or delete a saved run**")
        by_id = {r_["id"]: r_ for r_ in runs}
        sel = st.selectbox("Saved run", list(by_id), format_func=lambda i: f"{by_id[i]['name']}  ·  {by_id[i].get('captured', '')[:16].replace('T', ' ')}")
        r_ = by_id[sel]
        parts = [f"<span>Loss rate <b>{pct(r_['loss_rate'], 3)}</b> {fmt_ci(r_['ci'])}</span>",
                 f"<span><b>{r_['losses']:,}</b> of {r_['packets']:,} lost</span>", f"<span>{nice_dur(r_['duration_s'])}</span>"]
        if "ba" in r_:
            parts += [f"<span>Next loss <b>{r_['ba']:.1f}×</b> likelier after a loss</span>",
                      f"<span>Design effect <b>{r_['deff']:.2f}</b></span>",
                      f"<span>Runs {peq(r_['runs_p'])}</span>", f"<span>Var ÷ mean {r_['D']:.2f}</span>"]
        if r_.get("note"):
            parts.append(f"<span>📝 {r_['note']}</span>")
        st.markdown(f'<div class="net {r_["verdict"]}"><h4>{r_["name"]}: {VERDICT_TXT[r_["verdict"]]}</h4>'
                    f'<div class="row">{"".join(parts)}</div></div>', unsafe_allow_html=True)
        b1, b2, b3 = st.columns([1, 1, 2])
        b1.button("📈 Show in all tabs", key=f"open_{sel}", on_click=_show_in_tabs, args=(r_["csv"],),
                  help="Adds this run to the sidebar selection so every tab analyses it.")
        sure = b3.checkbox("Yes, delete it for good", key=f"sure_{sel}")
        b2.button("🗑️ Delete", key=f"del_{sel}", disabled=not sure, on_click=_delete, args=(sel, r_["csv"]))
