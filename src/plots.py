"""Figures (light theme, report-ready)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
from scipy import stats

from .distributions import hyperexp_cdf

COLORS = {"S1_Wired": "#2a6f97", "S2_WiFi": "#e07a1f", "S3_Mobile": "#b23a48"}
_EXTRA = ["#5c4d7d", "#2d6a4f", "#8a6d1d", "#6b7280", "#1d3557"]


def _col(k):
    """Colour for a scenario; scenarios not listed in COLORS get the next spare colour."""
    if k not in COLORS:
        COLORS[k] = _EXTRA[(len(COLORS) - 3) % len(_EXTRA)]
    return COLORS[k]
plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 160, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def timeline(counts, labels, path, seconds=300, window_s=1):
    fig, axes = plt.subplots(len(counts), 1, figsize=(10, 6), sharex=True, squeeze=False)
    axes = axes.ravel()
    shown = 0
    for ax, (k, c) in zip(axes, counts.items()):
        m = min(int(seconds // window_s), len(c))   # never ask for more windows than exist
        shown = m * window_s
        ax.bar(np.arange(m) * window_s, c[:m], width=window_s, align="edge", color=_col(k))
        ax.set_ylabel(f"losses / {window_s} s")
        ax.set_title(labels[k], loc="left", fontsize=10)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle(f"Packet losses per {window_s}-s window (first {shown:g} s)", fontsize=12)
    _save(fig, path)


def count_fits(counts, fits, labels, path, window_s=1):
    fig, axes = plt.subplots(1, len(counts), figsize=(13, 4), squeeze=False)
    axes = axes.ravel()
    for ax, (k, c) in zip(axes, counts.items()):
        kmax = int(np.quantile(c, 0.995)) + 2
        xs = np.arange(kmax + 1)
        obs = np.bincount(c, minlength=kmax + 1)[: kmax + 1] / len(c)
        ax.bar(xs, obs, color=_col(k), alpha=0.55, label="observed")
        ax.plot(xs, stats.poisson.pmf(xs, fits[k]["poisson"]["lam"]), "ko--", ms=4, label="Poisson fit")
        nb = fits[k]["negbin"]
        ax.plot(xs, stats.nbinom.pmf(xs, nb["r"], nb["p"]), "s-", color="#2d6a4f", ms=4, label="Neg. binomial fit")
        ax.set_yscale("log"); ax.set_ylim(bottom=1e-4)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.set_title(labels[k]); ax.set_xlabel(f"losses in a {window_s}-s window")
    axes[0].set_ylabel("probability (log scale)")
    axes[0].legend(fontsize=8)
    _save(fig, path)


def gap_survival(gaps, gap_fits, labels, path):
    fig, axes = plt.subplots(1, len(gaps), figsize=(13, 4), squeeze=False)
    axes = axes.ravel()
    for ax, (k, g) in zip(axes, gaps.items()):
        gs = np.sort(g)
        surv = 1 - np.arange(1, len(gs) + 1) / len(gs)
        ax.step(gs, surv, where="post", color=_col(k), lw=1.6, label="empirical")
        t = np.linspace(0, np.quantile(g, 0.999), 400)
        ax.plot(t, np.exp(-gap_fits[k]["exp"]["rate"] * t), "k--", label="exponential fit")
        h = gap_fits[k]["hyper"]
        ax.plot(t, 1 - hyperexp_cdf(t, h["w"], h["rate_fast"], h["rate_slow"]), color="#2d6a4f",
                label="2-phase hyperexp. fit")
        ax.set_yscale("log"); ax.set_ylim(1e-3, 1.05)
        ax.set_title(labels[k]); ax.set_xlabel("time between losses (s)")
    axes[0].set_ylabel("P(gap > t)  (log scale)")
    axes[0].legend(fontsize=8)
    _save(fig, path)


def posteriors(posts, seq, labels, path, seq_label=""):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    ax = axes[0]
    for k, p in posts.items():
        lo = stats.beta.ppf(1e-4, p["alpha"], p["beta"]); hi = stats.beta.ppf(1 - 1e-4, p["alpha"], p["beta"])
        x = np.linspace(lo, hi, 400)
        ax.plot(x * 100, stats.beta.pdf(x, p["alpha"], p["beta"]) / 100, color=_col(k), label=labels[k])
        ax.fill_between(x * 100, stats.beta.pdf(x, p["alpha"], p["beta"]) / 100, color=_col(k), alpha=0.15)
    ax.set_xlabel("packet loss probability (%)"); ax.set_ylabel("posterior density")
    ax.set_title("Posterior of loss rate, Beta(1,1) prior"); ax.legend(fontsize=8)
    ax = axes[1]
    xmax = max(s["ci_high"] for s in seq) * 1.07   # a little past the widest credible interval
    for s in seq:
        x = np.linspace(0, xmax, 600)
        ax.plot(x * 100, stats.beta.pdf(x, s["alpha"], s["beta"]) / 100, label=f"after {s['t']} s")
    ax.set_xlabel("packet loss probability (%)"); ax.set_title(f"Sequential updating: {seq_label}")
    ax.legend(fontsize=8)
    _save(fig, path)


def markov_posteriors(mpost, labels, path):
    """Forest plot: posterior median and 95% interval of P(L|N) and P(L|L) per network."""
    fig, ax = plt.subplots(figsize=(9, 3.6))
    keys = list(mpost)
    for i, k in enumerate(keys):
        m = mpost[k]
        for q, marker, name in [(m["a_q"], "o", "P(loss | previous delivered)"),
                                (m["b_q"], "s", "P(loss | previous lost)")]:
            ax.errorbar(q[1] * 100, i, xerr=[[(q[1] - q[0]) * 100], [(q[2] - q[1]) * 100]],
                        fmt=marker, color=_col(k), ms=8, capsize=4,
                        label=name if i == 0 else None, mfc=_col(k) if marker == "s" else "white")
        ax.annotate(f"x{m['amp_q'][1]:.0f}", ((m["a_q"][1] * m["b_q"][1]) ** 0.5 * 100, i + 0.18),
                    ha="center", fontsize=9, color=_col(k))
    ax.set_yticks(range(len(keys))); ax.set_yticklabels([labels[k] for k in keys])
    ax.set_xscale("log"); ax.set_xlabel("probability (%), posterior median with 95% credible interval")
    ax.set_ylim(-0.6, len(keys) - 0.3)
    ax.set_title("A loss makes the next loss tens of times more likely")
    ax.legend(fontsize=8, loc="lower right")
    _save(fig, path)


def power_curves(power, durations, labels, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    names = {"dispersion": "Index-of-dispersion test", "runs": "Runs test", "markov_lrt": "Markov LRT"}
    for ax, test in zip(axes, names):
        for k, pw in power.items():
            ax.plot(durations, pw[test], "o-", color=_col(k), label=labels[k])
        ax.axhline(0.8, color="grey", ls=":", lw=1)
        ax.set_xscale("log"); ax.set_xticks(durations); ax.set_xticklabels(durations)
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(names[test]); ax.set_xlabel("capture length (s)")
    axes[0].set_ylabel("power (P reject independence)"); axes[0].legend(fontsize=8)
    _save(fig, path)


def coverage_bar(cov, labels, path):
    fig, ax = plt.subplots(figsize=(8, 4))
    keys = list(cov); x = np.arange(len(keys))
    ax.bar(x - 0.18, [cov[k]["naive"] for k in keys], 0.36, color="#adb5bd", label="naive Beta posterior")
    ax.bar(x + 0.18, [cov[k]["adjusted"] for k in keys], 0.36, color="#2d6a4f", label="design-effect adjusted")
    ax.axhline(0.95, color="k", ls="--", lw=1, label="nominal 95%")
    ax.set_xticks(x); ax.set_xticklabels([labels[k] for k in keys])
    ax.set_ylim(0, 1.02); ax.set_ylabel("coverage of true loss rate")
    ax.set_title("Do 95% intervals really cover 95% of the time?"); ax.legend(fontsize=8, loc="lower left")
    _save(fig, path)
