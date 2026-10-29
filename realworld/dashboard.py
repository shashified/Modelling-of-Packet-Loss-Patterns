"""Real Network Lab: record real packet captures and see every statistic of the case study as charts.

Opened through `streamlit run lab.py` (it is the first page of the Packet-Loss Lab).
"""
import glob
import io
import json
import os
import re
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

CAPS = os.environ.get("PL_CAPTURES_DIR", os.path.join(ROOT, "realworld", "captures"))
DEMO = os.path.join(ROOT, "realworld", "demo_captures")
PROBE = os.path.join(ROOT, "realworld", "probe.py")
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
def list_captures(folder):
    out = []
    for f in sorted(glob.glob(os.path.join(folder, "*.csv"))):
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
st.sidebar.markdown("**1. Record a capture**")
with st.sidebar.form("record"):
    net = st.selectbox("Network you are on", ["Wi-Fi", "Phone hotspot", "Wired (Ethernet)", "Other"])
    other = st.text_input("Name (for Other)", placeholder="e.g. library_wifi")
    tgt = st.selectbox("Send packets to", ["My router (recommended)", "The internet (1.1.1.1)", "Custom address"])
    custom = st.text_input("Custom address", placeholder="e.g. 192.168.1.1")
    dur_s = st.select_slider("Length", options=[30, 120, 300, 600, 1200], value=600, format_func=lambda s: {
        30: "30 s (quick test)", 120: "2 min", 300: "5 min", 600: "10 min (recommended)", 1200: "20 min"}[s])
    note = st.text_input("Note (optional)", placeholder="e.g. hostel room, evening")
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
    target = {"My router (recommended)": "gateway", "The internet (1.1.1.1)": "1.1.1.1"}.get(tgt, custom.strip())
    if not target:
        st.error("Type a custom address, or pick 'My router'.")
        st.stop()
    os.makedirs(CAPS, exist_ok=True)
    cmd = [sys.executable, PROBE, "--label", label, "--target", target, "--duration", str(dur_s), "--live", "--out", CAPS]
    if note.strip():
        cmd += ["--note", note.strip()]
    st.subheader(f"Recording **{label}** for {nice_dur(dur_s)}")
    st.caption("Keep this tab open and the laptop still and plugged in. The analysis starts by itself when the recording ends.")
    bar = st.progress(0.0)
    m1, m2, m3 = st.columns(3)
    sent_m, lost_m, rate_m = m1.empty(), m2.empty(), m3.empty()
    chart_ph = st.empty()
    log, per_sec, last = [], [], 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=ROOT)
    saved_path = None
    for line in proc.stdout:
        log.append(line.rstrip())
        if line.startswith("PROGRESS "):
            d = json.loads(line[9:])
            bar.progress(min(1.0, d["sent"] / d["total"]), text=f"{d['t']:.0f} s of {dur_s} s")
            sent_m.metric("Packets sent", f"{d['sent']:,}")
            lost_m.metric("Lost so far", f"{d['lost']:,}")
            rate_m.metric("Loss rate so far", pct(d["lost"] / max(1, d["decided"]), 2))
            per_sec.append(dict(second=round(d["t"]), lost=d["lost"] - last))
            last = d["lost"]
            if len(per_sec) % 2 == 0 or len(per_sec) < 5:
                chart_ph.altair_chart(alt.Chart(pd.DataFrame(per_sec)).mark_bar(color=BAD).encode(
                    x=alt.X("second:Q", title="time (s)"), y=alt.Y("lost:Q", title="packets lost", axis=alt.Axis(format="d", tickMinStep=1))).properties(height=200),
                    width="stretch")
        elif line.startswith("SAVED "):
            saved_path = line[6:].strip()
    proc.wait()
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

# ------------------------------------------------------------------ choose captures
caps = list_captures(CAPS)
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
    return f"{c['label']}  ·  {c['when']:%d %b %H:%M}" + (f"  ·  {nice_dur(dur)}" if dur else "")

latest = {}
for c in caps:
    latest[c["label"]] = c["path"]
default = list(latest.values())
if st.session_state.get("just_recorded") and st.session_state["just_recorded"] not in default:
    default.append(st.session_state["just_recorded"])
by_path = {c["path"]: c for c in caps}
chosen = st.sidebar.multiselect("Newest capture of each network is picked", list(by_path), default=default,
                                format_func=lambda p: cap_name(by_path[p]))
if not chosen:
    st.info("Pick at least one capture in the sidebar.")
    st.stop()

with st.spinner("Running all the statistics (about 10 s per capture the first time)..."):
    A = {}
    for pth in chosen:
        c = by_path[pth]
        key = c["label"]
        if key in A:
            key = f"{key} ({c['when']:%d %b %H:%M})"
        A[key] = analyse_file(pth, c["mtime"])
names = list(A)
COL = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(names)}
color_scale = alt.Scale(domain=names, range=[COL[k] for k in names])
full = [k for k in names if A[k]["res"]["enough_losses"]]

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

tabs = st.tabs(["👀 Packets", "📊 O1 Loss counts", "⏱️ O2 Gaps", "🔗 O3 Independence", "⚖️ O4 Compare",
                "🎯 O5 Bayesian", "📏 O6 Reliability", "🧪 Phase 1 vs 2", "📄 Report & glossary"])

# ------------------------------------------------------------------ tab: packets
with tabs[0]:
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
with tabs[1]:
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
with tabs[2]:
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
with tabs[3]:
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
with tabs[4]:
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
        c1.metric("Kruskal-Wallis H", f"{cmp['kruskal_H']:.1f}", f"p = {fmt_p(cmp['kruskal_p'])}", delta_color="off")
        c2.metric("χ² homogeneity", f"{cmp['chi2_homog']:.1f}", f"p = {fmt_p(cmp['chi2_p'])}", delta_color="off")
        c3.metric("P(" + " < ".join(order) + ")", f"{p_order:.3f}", "from 50,000 posterior draws", delta_color="off")
        st.dataframe(pd.DataFrame([{"Pair": f"{q['a']} vs {q['b']}", "Mann-Whitney U": f"{q['U']:,.0f}",
                                    "p (Bonferroni)": fmt_p(q["p_bonf"]),
                                    "Different at 5%?": "yes" if q["p_bonf"] < ALPHA else "no"}
                                   for q in cmp["pairwise"]]), hide_index=True, width="stretch")
        explain("Kruskal-Wallis compares losses per second across all networks at once using ranks, because the counts are mostly zeros "
                "and far from normal. Mann-Whitney compares pairs; Bonferroni multiplies each p-value by the number of pairs so that "
                "testing several pairs does not inflate false alarms. The χ² homogeneity test asks whether the loss proportion is the same everywhere.")

# ------------------------------------------------------------------ tab: O5
with tabs[5]:
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
with tabs[6]:
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
with tabs[7]:
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
with tabs[8]:
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
