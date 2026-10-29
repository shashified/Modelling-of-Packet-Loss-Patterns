"""Phase 2: run the study's statistics on real captures from probe.py.

  python3 realworld/analyze_captures.py                      # every capture in realworld/captures
  python3 realworld/analyze_captures.py --captures some/dir --out some/results
  python3 realworld/analyze_captures.py --latest             # only the newest capture per label

Uses the same functions as the Phase 1 simulation study (src/): Poisson and Negative Binomial
fits, exponential and two-phase fits, chi-square, dispersion, bootstrap KS, runs and Markov tests,
Beta-Binomial posteriors, the design-effect correction and the predictive check.

Writes <out>/summary.md, <out>/results.json and figures.
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src import config as C                      # noqa: E402
from src import loss_model as LM                 # noqa: E402
from src import distributions as D               # noqa: E402
from src import hypothesis_tests as HT           # noqa: E402
from src import bayesian as BY                   # noqa: E402
from src import plots as P                       # noqa: E402

MIN_LOSSES = 10            # fewer losses than this: only the loss-rate estimate is reported
RECOMMENDED_S = 600        # Phase 1 power study: at least ten minutes per network


def load(csv_path):
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    meta_path = csv_path[:-4] + ".json"
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    loss = np.array([r["received"] == "0" for r in rows], dtype=bool)
    t = np.array([float(r["t_send_s"]) for r in rows])
    rtt = np.array([float(r["rtt_ms"]) for r in rows if r["rtt_ms"]])
    rate = float(meta.get("rate") or (len(t) - 1) / max(t[-1] - t[0], 1e-9))
    label = meta.get("label") or os.path.basename(csv_path).rsplit("_", 2)[0]
    return dict(label=label, loss=loss, t=t, rtt=rtt, rate=rate, meta=meta, file=os.path.basename(csv_path))


def fmt_p(p, B=None):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "n/a"
    if B is not None and p <= 1 / (B + 1) + 1e-12:
        return f"< {1 / B:.2g}"
    return "< 1e-10" if p < 1e-10 else f"{p:.3g}"


def analyse(cap, rng):
    loss, rate = cap["loss"], cap["rate"]
    n, k = len(loss), int(loss.sum())
    ppw = max(1, int(round(rate * C.WINDOW_S)))
    block = max(1, int(round(rate * C.BLOCK_S)))
    out = dict(label=cap["label"], file=cap["file"], packets=n, losses=k, loss_rate=k / n if n else float("nan"),
               duration_s=float(cap["t"][-1] - cap["t"][0]) if n > 1 else 0.0, rate=rate,
               rtt_median_ms=float(np.median(cap["rtt"])) if len(cap["rtt"]) else None,
               rtt_p95_ms=float(np.quantile(cap["rtt"], 0.95)) if len(cap["rtt"]) else None,
               meta=cap["meta"])
    out["posterior"] = BY.beta_posterior(k, n)
    out["enough_losses"] = k >= MIN_LOSSES
    if not out["enough_losses"]:
        return out, None

    counts = LM.window_counts(loss, ppw)
    gaps = np.diff(cap["t"][loss])
    gaps = gaps[gaps > 0]
    bl = LM.burst_lengths(loss)
    pois, nb = D.fit_poisson(counts), D.fit_negbin(counts)
    ex, hy = D.fit_exponential(gaps), D.fit_hyperexp(gaps)
    out["descriptive"] = dict(window_mean=float(counts.mean()), window_var=float(counts.var(ddof=1)),
                              max_losses_in_window=int(counts.max()), mean_burst_len=float(bl.mean()),
                              max_burst_len=int(bl.max()), share_losses_in_bursts=float(bl[bl > 1].sum() / bl.sum()))
    out["fits"] = dict(poisson_lambda=pois["lam"], negbin_r=nb["r"], aic_poisson=D.aic(pois), aic_negbin=D.aic(nb),
                       exp_rate=ex["rate"], hyper_w_fast=hy["w"], hyper_rate_fast=hy["rate_fast"],
                       hyper_rate_slow=hy["rate_slow"], aic_exp=D.aic(ex), aic_hyper=D.aic(hy))
    out["tests"] = dict(
        chisq_poisson=HT.chisq_gof_counts(counts, lambda x: stats.poisson.pmf(x, pois["lam"]), 1),
        dispersion=HT.dispersion_test(counts),
        runs=HT.runs_test(loss),
        markov_lrt=HT.markov_lrt(loss),
        ks_exponential=HT.ks_exponential_bootstrap(gaps, C.N_BOOT_KS, rng) if len(gaps) >= 5 else None,
    )
    mk = BY.markov_posterior(loss, C.MARKOV_DRAWS, rng)
    out["markov"] = {kk: vv for kk, vv in mk.items() if not kk.startswith("samples")}
    out["adjusted_posterior"] = BY.adjusted_posterior(loss, block)
    out["predictive_tail"] = BY.posterior_predictive_tail(out["posterior"], ppw, C.HEAVY_LOSS_K, counts)
    return out, dict(counts=counts, gaps=gaps, fits={"poisson": pois, "negbin": nb},
                     gap_fits={"exp": ex, "hyper": hy}, markov=mk)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def pct(x, d=3):
    return f"{100 * x:.{d}f}%"


def write_summary(res, comparison, path):
    L = ["# Phase 2 results: real packet captures", "",
         "Loss here is round-trip loss: a probe counts as lost when no reply came back within the timeout.", ""]
    L += ["## Captures", "", "| Label | File | Mode | Target | Packets | Duration | Lost | Loss rate (95% CrI) | RTT median / p95 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        m, p = r["meta"], r["posterior"]
        rt = f"{r['rtt_median_ms']:.1f} / {r['rtt_p95_ms']:.1f} ms" if r["rtt_median_ms"] is not None else "n/a"
        L.append(f"| {r['label']} | {r['file']} | {m.get('mode', '?')} | {m.get('target', '?')} | {r['packets']:,} | "
                 f"{r['duration_s']:.0f} s | {r['losses']:,} | {pct(p['mean'])} [{pct(p['ci_low'])}, {pct(p['ci_high'])}] | {rt} |")
    short = [r for r in res if r["duration_s"] < RECOMMENDED_S - 1]
    if short:
        L += ["", f"Note: {', '.join(r['label'] for r in short)} ran for less than {RECOMMENDED_S} s. "
                  f"The Phase 1 power study needs about ten minutes to detect bursts reliably on a low-loss link."]
    few = [r for r in res if not r["enough_losses"]]
    if few:
        L += ["", f"Too few losses for the distribution and independence tests (fewer than {MIN_LOSSES}): "
                  f"{', '.join(r['label'] for r in few)}. Only the loss-rate estimate is shown for these."]
    full = [r for r in res if r["enough_losses"]]
    if full:
        L += ["", "## Is loss random (independent)?", "",
              "| Label | Var / mean | Dispersion p | Runs z (p) | P(L given N) | P(L given L) | b/a (95% CrI) | Mean burst | Verdict |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in full:
            t, mk, d = r["tests"], r["markov"], r["descriptive"]
            bursty = (t["runs"]["p"] < C.ALPHA and t["runs"]["z"] < 0) or (t["markov_lrt"]["p"] < C.ALPHA and mk["P_b_gt_a"] > 0.975)
            L.append(f"| {r['label']} | {d['window_var'] / d['window_mean']:.2f} | {fmt_p(t['dispersion']['p'])} | "
                     f"{t['runs']['z']:.1f} ({fmt_p(t['runs']['p'])}) | {pct(t['markov_lrt']['p_L_given_N'], 2)} | "
                     f"{pct(t['markov_lrt']['p_L_given_L'], 1)} | {mk['amp_q'][1]:.1f} [{mk['amp_q'][0]:.1f}, {mk['amp_q'][2]:.1f}] | "
                     f"{d['mean_burst_len']:.2f} | {'bursty' if bursty else 'no evidence of bursts'} |")
        L += ["", "## Distribution fits", "",
              "| Label | AIC Poisson | AIC Neg. Bin. | Chi-square Poisson p | KS exponential p | AIC exp. | AIC two-phase | Fast share | Fast / slow mean gap |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in full:
            f, t = r["fits"], r["tests"]
            ks = t["ks_exponential"]
            L.append(f"| {r['label']} | {f['aic_poisson']:.0f} | {f['aic_negbin']:.0f} | {fmt_p(t['chisq_poisson']['p'])} | "
                     f"{fmt_p(ks['p'], ks['B']) if ks else 'n/a'} | {f['aic_exp']:.0f} | {f['aic_hyper']:.0f} | "
                     f"{100 * f['hyper_w_fast']:.0f}% | {1000 / f['hyper_rate_fast']:.0f} ms / {1 / f['hyper_rate_slow']:.1f} s |")
        L += ["", "## Interval estimates", "",
              "| Label | Naive 95% interval | Design effect | Adjusted 95% interval | Heavy windows: predicted vs observed |",
              "|---|---|---|---|---|"]
        for r in full:
            p, a, pt = r["posterior"], r["adjusted_posterior"], r["predictive_tail"]
            L.append(f"| {r['label']} | [{pct(p['ci_low'])}, {pct(p['ci_high'])}] | {a['deff']:.2f} | "
                     f"[{pct(a['ci_low'])}, {pct(a['ci_high'])}] | {pt['predicted']:.2e} vs {pt['observed']:.2e} |")
    if comparison:
        L += ["", "## Comparing captures", "",
              f"Kruskal-Wallis H = {comparison['kruskal_H']:.1f}, p = {fmt_p(comparison['kruskal_p'])}; "
              f"chi-square homogeneity = {comparison['chi2_homog']:.1f} on {comparison['chi2_df']} df, p = {fmt_p(comparison['chi2_p'])}."]
        for q in comparison["pairwise"]:
            L.append(f"- {q['a']} vs {q['b']}: Bonferroni p = {fmt_p(q['p_bonf'])}")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Analyse real captures from probe.py")
    ap.add_argument("--captures", default=os.path.join(ROOT, "realworld", "captures"))
    ap.add_argument("--out", default=os.path.join(ROOT, "realworld", "results"))
    ap.add_argument("--latest", action="store_true", help="use only the newest capture for each label")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.captures, "*.csv")))
    if not files:
        sys.exit(f"No captures in {args.captures}. Run realworld/probe.py first.")
    caps = [load(f) for f in files]
    caps = [c for c in caps if len(c["loss"]) > 1]
    if args.latest:
        newest = {}
        for c in caps:
            newest[c["label"]] = c          # files are sorted by name, so the last one per label is newest
        caps = list(newest.values())
    # make labels unique if a label was captured more than once
    seen = {}
    for c in caps:
        seen[c["label"]] = seen.get(c["label"], 0) + 1
    count = {}
    for c in caps:
        if seen[c["label"]] > 1:
            count[c["label"]] = count.get(c["label"], 0) + 1
            c["label"] = f"{c['label']}#{count[c['label']]}"

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(C.SEED)
    results, extras = [], {}
    for c in caps:
        print(f"Analysing {c['file']} ({len(c['loss']):,} packets, {int(c['loss'].sum()):,} lost)", flush=True)
        r, x = analyse(c, rng)
        results.append(r)
        if x:
            extras[c["label"]] = x

    comparison = None
    if len(extras) >= 2:
        comparison = HT.compare_scenarios({k: v["counts"] for k, v in extras.items()},
                                          {c["label"]: c["loss"] for c in caps if c["label"] in extras})
    if extras:
        labels = {k: k for k in extras}
        win = C.WINDOW_S
        P.timeline({k: v["counts"] for k, v in extras.items()}, labels, os.path.join(args.out, "real_fig1_timeline.png"),
                   seconds=C.TIMELINE_S, window_s=win)
        P.count_fits({k: v["counts"] for k, v in extras.items()}, {k: v["fits"] for k, v in extras.items()}, labels,
                     os.path.join(args.out, "real_fig2_count_fits.png"), window_s=win)
        P.gap_survival({k: v["gaps"] for k, v in extras.items()}, {k: v["gap_fits"] for k, v in extras.items()}, labels,
                       os.path.join(args.out, "real_fig3_gap_survival.png"))
        P.markov_posteriors({k: v["markov"] for k, v in extras.items()}, labels,
                            os.path.join(args.out, "real_fig4_markov.png"),
                            title="Loss probability after a delivered packet vs after a lost packet")
    with open(os.path.join(args.out, "results.json"), "w") as f:
        json.dump(clean(dict(captures=results, comparison=comparison)), f, indent=2)
    write_summary(results, comparison, os.path.join(args.out, "summary.md"))
    print(f"Done. Results in {args.out}/summary.md")


if __name__ == "__main__":
    main()
