"""Packet-Loss Lab: an interactive front end for the case study.

Run from the project folder:
    streamlit run app.py

It reuses the project's own modules in src/, so the app and run_case_study.py always agree.
"""
import json
import os

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from src import bayesian as BY
from src import config as C
from src import distributions as D
from src import hypothesis_tests as HT
from src import loss_model as LM

st.set_page_config(page_title="Packet-Loss Lab", page_icon="📡", layout="wide")

GOOD, BAD, NAVY, GREY, DELIV = "#2D6A4F", "#C0392B", "#1F3A5F", "#9AA5B1", "#BFE3CC"
RATE = C.PACKET_RATE
BLOCK_S = C.BLOCK_S
PRESET_NAMES = {k: v["label"] for k, v in C.SCENARIOS.items()}

st.markdown("""
<style>
  .block-container { padding-top: 1.6rem; }
  .card { border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; border: 1px solid #DDE3EA; background: #FFFFFF; }
  .card h4 { margin: 0 0 4px 0; font-size: 1.02rem; }
  .card .q { color: #4A5563; font-size: 0.92rem; margin-bottom: 8px; }
  .card .big { font-size: 1.35rem; font-weight: 700; }
  .card .small { color: #4A5563; font-size: 0.85rem; margin-top: 4px; }
  .pass { border-left: 6px solid #2D6A4F; background: #F1F8F4; }
  .fail { border-left: 6px solid #C0392B; background: #FCF2F1; }
  .verdict { border-radius: 12px; padding: 14px 18px; font-size: 1.1rem; font-weight: 600; margin: 4px 0 14px 0; }
  .packets { display: flex; flex-wrap: wrap; gap: 2px; margin: 6px 0 4px 0; }
  .packets span { width: 11px; height: 11px; border-radius: 2px; display: inline-block; }
  .legend span { display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin: 0 4px -1px 10px; }
  .explain { background: #F2F5F9; border-radius: 10px; padding: 10px 14px; font-size: 0.95rem; }
  .tiles { display: flex; flex-wrap: wrap; gap: 10px; margin: 4px 0 12px 0; }
  .tile { flex: 1 1 150px; background: #F2F5F9; border-radius: 10px; padding: 10px 14px; }
  .tile .lab { color: #4A5563; font-size: 0.85rem; }
  .tile .val { font-size: 1.55rem; font-weight: 700; color: #1B2430; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar
st.sidebar.title("📡 Controls")
preset_key = st.sidebar.radio("1. Pick a network", list(PRESET_NAMES), format_func=lambda k: PRESET_NAMES[k], index=1)
preset = C.SCENARIOS[preset_key]

coin_mode = st.sidebar.toggle("2. Turn bursts OFF (coin-flip mode)", value=False,
                              help="Keeps the same average loss rate, but every packet is lost independently, "
                                   "like a separate coin flip. Use it to compare.")

def nice_time(s):
    """60 -> '1 min', 3600 -> '1 hour', 45 -> '45 s'."""
    if s % 3600 == 0:
        return f"{s // 3600} hour" + ("s" if s > 3600 else "")
    return f"{s // 60} min" if s % 60 == 0 else f"{s} s"


durations = sorted(set(C.APP_DURATIONS_S) | {C.DURATION_S})
duration = st.sidebar.select_slider("3. How long to watch", options=durations, value=C.DURATION_S, format_func=nice_time)
duration_label = nice_time(duration)

with st.sidebar.expander("⚙️ Fine-tune the network (optional)"):
    st.caption("The network switches between a Good mood and a Bad mood.")
    p_gb = st.slider("Chance per packet of falling into the Bad mood", 0.0001, 0.02, float(preset["p_gb"]), 0.0001, format="%.4f", key=f"pgb_{preset_key}")
    p_bg = st.slider("Chance per packet of recovering from the Bad mood", 0.01, 1.0, float(preset["p_bg"]), 0.01, key=f"pbg_{preset_key}")
    h_g = st.slider("Loss chance in the Good mood", 0.0, 0.05, float(preset["h_g"]), 0.001, format="%.3f", key=f"hg_{preset_key}")
    h_b = st.slider("Loss chance in the Bad mood", 0.0, 1.0, float(preset["h_b"]), 0.05, key=f"hb_{preset_key}")

if "seed" not in st.session_state:
    st.session_state.seed = C.SEED
c1, c2 = st.sidebar.columns(2)
if c1.button("🎲 New run", width="stretch"):
    st.session_state.seed += 1
if c2.button(f"↩️ Seed {C.SEED}", width="stretch"):
    st.session_state.seed = C.SEED
st.sidebar.caption(f"Random seed: {st.session_state.seed}. The same seed always gives the same result.")


# ------------------------------------------------------------------ the experiment
@st.cache_data(show_spinner=False)
def experiment(key, p_gb, p_bg, h_g, h_b, duration, seed, coin):
    rng = np.random.default_rng(seed)
    n = duration * RATE
    true_p = LM.theoretical_loss_rate(p_gb, p_bg, h_g, h_b)
    if coin:
        loss = rng.random(n) < true_p
        gaps = LM.inter_loss_gaps(loss, RATE, rng)
    else:
        # Same order of random draws as run_case_study.py, so the default settings
        # reproduce the numbers in results/summary.md and the slides exactly.
        for k, v in C.SCENARIOS.items():
            if k == key:
                loss = LM.simulate_losses(n, rng=rng, p_gb=p_gb, p_bg=p_bg, h_g=h_g, h_b=h_b)
                gaps = LM.inter_loss_gaps(loss, RATE, rng)
                break
            prm = {kk: vv for kk, vv in v.items() if kk != "label"}
            LM.inter_loss_gaps(LM.simulate_losses(n, rng=rng, **prm), RATE, rng)
    counts = LM.window_counts(loss, RATE)
    k = int(loss.sum())
    out = dict(loss=loss, counts=counts, n=n, k=k, true_p=true_p, rate=loss.mean())
    if k < 3:
        return out
    bursts = LM.burst_lengths(loss)
    lam = counts.mean()
    nb = D.fit_negbin(counts)
    hk = C.HEAVY_LOSS_K
    out.update(
        bursts=bursts,
        disp=HT.dispersion_test(counts),
        runs=HT.runs_test(loss),
        markov=HT.markov_lrt(loss),
        lam=lam, nb=nb,
        heavy_obs=int(np.sum(counts >= hk)),
        heavy_pois=float(len(counts) * stats.poisson.sf(hk - 1, lam)),
        heavy_nb=float(len(counts) * stats.nbinom.sf(hk - 1, nb["r"], nb["p"])),
        gaps=gaps,
        ks=HT.ks_exponential_bootstrap(gaps, C.APP_N_BOOT_KS, np.random.default_rng(seed + 1)) if len(gaps) >= 10 else None,
        naive=BY.beta_posterior(k, n),
        adjusted=BY.adjusted_posterior(loss, BLOCK_S * RATE),
        seq=BY.sequential_posteriors(loss, RATE, [t for t in C.APP_SEQ_CHECKPOINTS_S if t <= duration]),
    )
    return out


with st.spinner("Sending packets and running the statistics..."):
    E = experiment(preset_key, p_gb, p_bg, h_g, h_b, duration, st.session_state.seed, coin_mode)

ALPHA = C.ALPHA
mode_txt = "coin-flip mode (independent losses)" if coin_mode else "bursty mode (Good/Bad model)"

# ------------------------------------------------------------------ header
st.title("📡 Packet-Loss Lab")
st.markdown(f"**{PRESET_NAMES[preset_key]}**, {mode_txt}, watched for **{duration_label}** "
            f"({E['n']:,} packets at {RATE} packets per second).")

if E["k"] < 3:
    st.warning("Fewer than 3 packets were lost, so there is nothing to analyse. Watch for longer or raise the loss chances.")
    st.stop()

pLN, pLL = E["markov"]["p_L_given_N"], E["markov"]["p_L_given_L"]
mult = pLL / pLN if pLN > 0 else float("nan")
bursty = E["markov"]["p"] < ALPHA or E["runs"]["p"] < ALPHA

# Stat tiles wrap onto a new row on narrow screens instead of being cut off.
tiles = [
    ("Packets lost", f"{E['k']:,}", ""),
    ("Loss rate seen", f"{E['rate'] * 100:.2f}%", "What we measured in this run."),
    ("True loss rate", f"{E['true_p'] * 100:.2f}%", "The real long-run rate, known because we built the model."),
    ("After a loss, next loss is", f"{mult:.0f}× likelier" if mult == mult else "n/a",
     "P(loss | previous lost) divided by P(loss | previous delivered). About 1× means independent."),
    ("Longest burst", f"{int(E['bursts'].max())} in a row", ""),
]
st.markdown('<div class="tiles">' + "".join(
    f'<div class="tile" title="{tip}"><div class="lab">{lab}</div><div class="val">{val}</div></div>'
    for lab, val, tip in tiles) + "</div>", unsafe_allow_html=True)

if bursty:
    st.markdown(f'<div class="verdict" style="background:#FCF2F1;border:1px solid #E8B4AE;">🔴 Verdict: losses come in <b>bursts</b>. '
                f'They are not independent coin flips.</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="verdict" style="background:#F1F8F4;border:1px solid #A9D3B9;">🟢 Verdict: losses look <b>independent</b>, '
                f'like coin flips. No evidence of bursts.</div>', unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["👀 1. Watch the packets", "🎲 2. Is it random?", "📏 3. How sure are we?", "📊 4. Full study results"])

# ------------------------------------------------------------------ tab 1
with tab1:
    loss = E["loss"]
    first = int(np.flatnonzero(loss)[0])
    start = max(0, first - 40)
    show = loss[start:start + C.APP_STRIP_PACKETS]
    cells = "".join(f'<span style="background:{BAD if x else DELIV}"></span>' for x in show)
    st.subheader("Every square is one packet")
    st.markdown(f'<div class="legend">Packets {start + 1:,} to {start + len(show):,} ({len(show) / RATE:g} seconds) '
                f'<span style="background:{DELIV}"></span>delivered <span style="background:{BAD}"></span>lost</div>'
                f'<div class="packets">{cells}</div>', unsafe_allow_html=True)
    st.caption("Look for red squares sitting next to each other. Those are bursts. In coin-flip mode they are scattered.")

    st.subheader("Lost packets in each second")
    secs = min(C.TIMELINE_S, len(E["counts"]))
    df = pd.DataFrame({"second": np.arange(1, secs + 1), "lost": E["counts"][:secs]})
    chart = alt.Chart(df).mark_bar(color=BAD).encode(
        x=alt.X("second:Q", title="time (seconds)", scale=alt.Scale(domain=[0, secs], nice=False)), y=alt.Y("lost:Q", title="packets lost"),
        tooltip=["second", "lost"]).properties(height=260)
    st.altair_chart(chart, width="stretch")
    st.markdown('<div class="explain">If losses were random, the bars would be small and evenly spread. '
                'Tall bars with long empty stretches between them mean losses arrive in clumps.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ tab 2
def card(ok_random, title, question, big, small):
    cls = "pass" if ok_random else "fail"
    badge = "🟢 Looks random" if ok_random else "🔴 Not random"
    st.markdown(f'<div class="card {cls}"><h4>{badge} · {title}</h4><div class="q">{question}</div>'
                f'<div class="big">{big}</div><div class="small">{small}</div></div>', unsafe_allow_html=True)


def p_txt(p):
    return "p < 0.0000000001" if p < 1e-10 else f"p = {p:.3g}"


with tab2:
    st.subheader("Four checks. If losses were coin flips, all four should look random.")
    d, r, mk = E["disp"], E["runs"], E["markov"]
    a, b = st.columns(2)
    with a:
        card(not (d["p"] < ALPHA), "Spread check",
             "For coin-flip losses, the spread of losses per second (variance) equals the average.",
             f"Spread ÷ average = {d['D']:.2f} (coin flips: about 1)",
             f"Index-of-dispersion test, {p_txt(d['p'])}")
        card(not (r["p"] < ALPHA), "Runs check",
             "A run is a block of identical packets in a row. Clumped losses make fewer runs.",
             f"{r['runs']:,} runs seen vs {r['expected']:,.0f} expected",
             f"Wald-Wolfowitz runs test, z = {r['z']:.1f}, {p_txt(r['p'])}")
    with b:
        # Poisson tail test: under the coin-flip model the count of heavy seconds is itself ~ Poisson(expected)
        heavy_p = stats.poisson.sf(E["heavy_obs"] - 1, E["heavy_pois"]) if E["heavy_obs"] > 0 else 1.0
        heavy_ok = heavy_p >= ALPHA
        card(heavy_ok, f"Heavy-seconds check",
             f"How many seconds had {C.HEAVY_LOSS_K} or more losses? The Poisson (coin-flip) model predicts a number.",
             f"{E['heavy_obs']} seen vs {E['heavy_pois']:.1f} predicted",
             f"Negative Binomial (bursty) model predicts {E['heavy_nb']:.0f}; {p_txt(heavy_p)}")
        card(not (mk["p"] < ALPHA), "After-a-loss check",
             "Is the next packet more likely to be lost right after a loss?",
             f"{pLN * 100:.2f}% after a delivery vs {pLL * 100:.1f}% after a loss",
             f"Markov likelihood-ratio test, G² = {mk['G2']:.1f}, {p_txt(mk['p'])}")

    st.subheader("The coin-flip model vs what really happened")
    c = E["counts"]
    kmax = int(max(6, np.quantile(c, 0.995))) + 1
    ks = np.arange(kmax + 1)
    obs = np.bincount(c, minlength=kmax + 1)[: kmax + 1] / len(c)
    pois = stats.poisson.pmf(ks, E["lam"])
    nbp = stats.nbinom.pmf(ks, E["nb"]["r"], E["nb"]["p"])
    floor = 1e-6
    dd = pd.DataFrame({"losses in a second": np.tile(ks, 3),
                       # empty observed counts are left out (not drawn at zero); model curves stop at the floor
                       "probability": np.concatenate([np.where(obs > 0, obs, np.nan), np.maximum(pois, floor), np.maximum(nbp, floor)]),
                       "series": ["What happened"] * len(ks) + ["Poisson (coin flips)"] * len(ks) + ["Negative Binomial (bursty)"] * len(ks)})
    colors = alt.Scale(domain=["What happened", "Poisson (coin flips)", "Negative Binomial (bursty)"], range=[BAD, GREY, GOOD])
    line = alt.Chart(dd).mark_line(point=True, strokeWidth=2.5).encode(
        x=alt.X("losses in a second:O"), y=alt.Y("probability:Q", scale=alt.Scale(type="log", domain=[floor, 1]), title="probability (log scale)", axis=alt.Axis(tickCount=4, format=".0e")),
        color=alt.Color("series:N", scale=colors, legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["series", "losses in a second", alt.Tooltip("probability:Q", format=".2g")]).properties(height=340)
    st.altair_chart(line, width="stretch")
    st.markdown('<div class="explain">The grey line is what coin-flip losses would look like. If the red line (reality) runs far above it '
                'on the right, then busy seconds happen much more often than coin flips allow.</div>', unsafe_allow_html=True)

    with st.expander("Bonus check: the gaps between losses"):
        g = E["gaps"]
        st.write(f"Average gap: **{g.mean():.2f} s**. For coin-flip losses the middle (median) gap would be about "
                 f"**{np.log(2) * g.mean():.2f} s**. The real median gap is **{np.median(g):.3f} s**.")
        if E["ks"] is not None:
            st.write(f"Kolmogorov-Smirnov test against the exponential (coin-flip) model: D = {E['ks']['D']:.3f}, "
                     f"bootstrap p = {E['ks']['p']:.3f}.")
        st.caption("A tiny median gap means many losses arrive almost on top of the previous one, inside a burst.")

# ------------------------------------------------------------------ tab 3
with tab3:
    nv, ad, tp = E["naive"], E["adjusted"], E["true_p"]
    st.subheader("Our estimate of the loss rate, with a 95% safety range")
    rows = pd.DataFrame([
        {"range": "Normal", "name": "Normal range (assumes coin flips)", "low": nv["ci_low"] * 100, "high": nv["ci_high"] * 100,
         "hit": nv["ci_low"] <= tp <= nv["ci_high"]},
        {"range": "Corrected", "name": "Corrected range (allows for bursts)", "low": ad["ci_low"] * 100, "high": ad["ci_high"] * 100,
         "hit": ad["ci_low"] <= tp <= ad["ci_high"]},
    ])
    rows["result"] = np.where(rows["hit"], "contains the truth ✅", "misses the truth ❌")
    bars = alt.Chart(rows).mark_bar(height=26, cornerRadius=4).encode(
        x=alt.X("low:Q", title="loss rate (%)", scale=alt.Scale(zero=False)), x2="high:Q",
        y=alt.Y("range:N", title=None, sort=None, axis=alt.Axis(labelFontSize=13)),
        color=alt.Color("hit:N", scale=alt.Scale(domain=[True, False], range=[GOOD, GREY]), legend=None),
        tooltip=["range", alt.Tooltip("low:Q", format=".3f"), alt.Tooltip("high:Q", format=".3f"), "result"])
    rule = alt.Chart(pd.DataFrame({"true": [tp * 100]})).mark_rule(color=BAD, strokeDash=[6, 4], strokeWidth=2.5).encode(x="true:Q")
    st.altair_chart((bars + rule).properties(height=150), width="stretch")
    for _, row in rows.iterrows():
        st.write(f"**{row['name']}:** {row['low']:.3f}% to {row['high']:.3f}%, {row['result']}")
    st.caption(f"Red dashed line: the true loss rate, {tp * 100:.3f}%.")

    neff = E["n"] / ad["deff"]
    st.markdown(f'<div class="explain">Lost packets inside a burst are linked, so they carry less information than separate coin flips. '
                f'Here the <b>design effect</b> is <b>{ad["deff"]:.2f}</b>: the {E["n"]:,} packets are worth only about '
                f'<b>{neff:,.0f}</b> independent ones. The corrected range uses that smaller number, so it is wider and honest.</div>',
                unsafe_allow_html=True)

    st.subheader("Test the safety ranges many times")
    cov_dur = min(duration, C.COVERAGE_DURATION_S)
    reps = st.select_slider("Number of pretend recordings", options=C.APP_COVERAGE_REPS, value=C.APP_COVERAGE_REPS[1])
    if st.button(f"▶ Run {reps} pretend recordings of {nice_time(cov_dur)} each", type="primary"):
        rng = np.random.default_rng(st.session_state.seed + 7)
        if coin_mode:
            sim, prm = (lambda n, rng, **_: rng.random(n) < tp), {}
        else:
            sim, prm = LM.simulate_losses, dict(p_gb=p_gb, p_bg=p_bg, h_g=h_g, h_b=h_b)
        with st.spinner("Running..."):
            cov = BY.coverage_study(prm, tp, cov_dur, reps, RATE, BLOCK_S, rng, sim)
        cdf = pd.DataFrame({"range": ["Normal range", "Corrected range"], "coverage": [cov["naive"] * 100, cov["adjusted"] * 100]})
        cb = alt.Chart(cdf).mark_bar(cornerRadius=4).encode(
            x=alt.X("range:N", title=None, sort=None, axis=alt.Axis(labelAngle=0, labelFontSize=13)), y=alt.Y("coverage:Q", title="% caught the truth", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("range:N", scale=alt.Scale(domain=["Normal range", "Corrected range"], range=[GREY, GOOD]), legend=None))
        text = cb.mark_text(dy=-8, fontWeight="bold").encode(text=alt.Text("coverage:Q", format=".1f"))
        target = alt.Chart(pd.DataFrame({"y": [95]})).mark_rule(color=BAD, strokeDash=[6, 4]).encode(y="y:Q")
        st.altair_chart((cb + text + target).properties(height=320), width="stretch")
        st.write(f"A 95% range should catch the truth in about 95% of recordings (red line). "
                 f"Normal range: **{cov['naive'] * 100:.1f}%**. Corrected range: **{cov['adjusted'] * 100:.1f}%**.")
    else:
        st.caption("Press the button to check how often each range is really right.")

    st.subheader("Learning as we watch (Bayesian updating)")
    sq = pd.DataFrame([{"seconds watched": s["t"], "estimate": s["mean"] * 100, "low": s["ci_low"] * 100, "high": s["ci_high"] * 100} for s in E["seq"]])
    band = alt.Chart(sq).mark_area(opacity=0.25, color=NAVY).encode(x=alt.X("seconds watched:Q", scale=alt.Scale(type="log")), y=alt.Y("low:Q", title="loss rate (%)"), y2="high:Q")
    ln = alt.Chart(sq).mark_line(point=True, color=NAVY).encode(x="seconds watched:Q", y="estimate:Q", tooltip=["seconds watched", alt.Tooltip("estimate:Q", format=".2f")])
    st.altair_chart((band + ln).properties(height=240), width="stretch")
    st.caption("We start knowing nothing (a uniform Beta(1,1) prior). The shaded band narrows as more packets arrive.")

# ------------------------------------------------------------------ tab 4
with tab4:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), C.RESULTS_DIR, "results.json")
    if not os.path.exists(path):
        st.info("Run `python3 run_case_study.py` first to create the full study results.")
    else:
        R = json.load(open(path))
        cfg = R["config"]
        st.subheader(f"The full study: {len(R['scenarios'])} networks, {nice_time(cfg['duration_s'])} each, seed {cfg['seed']}")
        rows = []
        for k, s in R["scenarios"].items():
            dsc, t, b = s["descriptive"], s["tests"], s["bayes"]
            rows.append({"Network": s["label"],
                         "True loss rate": f"{s['true_long_run_loss_rate'] * 100:.3f}%",
                         "Spread ÷ average": round(dsc["window_var"] / dsc["window_mean"], 2),
                         "Next loss likelier by": f"{b['markov']['amp_q'][1]:.0f}×",
                         "Design effect": round(b["adjusted_posterior"]["deff"], 2),
                         "Normal range right": f"{R['coverage'][k]['naive'] * 100:.1f}%",
                         "Corrected range right": f"{R['coverage'][k]['adjusted'] * 100:.1f}%"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        st.subheader("How long must a real recording be?")
        labels_in_order = [R["scenarios"][k]["label"] for k in R["scenarios"]]
        pw = pd.DataFrame([{"seconds": d_, "network": R["scenarios"][k]["label"], "power": R["power"][k]["runs"][i]}
                           for k in R["scenarios"] for i, d_ in enumerate(R["power"]["durations_s"])])
        pc = alt.Chart(pw).mark_line(point=True, strokeWidth=2.5).encode(
            x=alt.X("seconds:Q", scale=alt.Scale(type="log", domain=[min(R["power"]["durations_s"]), max(R["power"]["durations_s"])], nice=False), title="recording length (seconds, log scale)",
                    axis=alt.Axis(values=R["power"]["durations_s"])),
            y=alt.Y("power:Q", title="power", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color("network:N", sort=list(labels_in_order),
                            scale=alt.Scale(domain=list(labels_in_order), range=["#2A6F97", "#E07A1F", "#B23A48"][:len(labels_in_order)]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["network", "seconds", "power"])
        st.altair_chart((pc + alt.Chart(pd.DataFrame({"y": [C.POWER_TARGET]})).mark_rule(strokeDash=[6, 4], color=GREY).encode(y="y:Q")).properties(height=300),
                        width="stretch")
        st.caption(f"Runs test, {C.POWER_REPS:,} simulated recordings per point. The dashed line is the {C.POWER_TARGET:.0%} target.")

with st.expander("ℹ️ How does the pretend network work?"):
    st.markdown("""
The network is always in one of two moods:

- 😊 **Good mood:** packets are almost never lost.
- 🤧 **Bad mood:** packets are lost often.

Before each packet it may switch mood. Bad moods are short, so losses come in **bursts**.
This is the **Gilbert-Elliott model**, a two-state **Markov chain**.

Because we set these chances ourselves, we know the **true** loss rate, so we can check whether the statistics find it.
Turn on **coin-flip mode** in the sidebar to see what independent losses look like with the same average rate.
""")
