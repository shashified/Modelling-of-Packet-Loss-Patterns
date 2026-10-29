"""Extra statistics for real captures, used by the Real Network Lab dashboard.

On a real network the true loss rate is unknown, so Objective O6 (are the tests and intervals
reliable?) is answered with a model fitted to the capture itself: a two-state Markov chain whose
two numbers are a = P(loss | previous delivered) and b = P(loss | previous lost). This is the
simple Gilbert model (loss in the Bad state is certain, never in the Good state). Simulating it
many times shows how often naive and adjusted 95% intervals would contain this network's true
long-run loss rate, and how long a capture must be for the runs test to notice the bursts.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from src import bayesian as BY            # noqa: E402
from src import hypothesis_tests as HT    # noqa: E402


def stationary_loss(a, b):
    """Long-run loss rate of the fitted chain: pi_L = a / (a + 1 - b)."""
    return a / (a + 1 - b) if (a + 1 - b) > 0 else float("nan")


def simulate_markov(n, a, b, rng):
    """0/1 loss sequence of length n from the two-state chain, drawn run by run (fast)."""
    if a <= 0:
        return np.zeros(n, dtype=bool)
    lost = rng.random() < stationary_loss(a, b)
    q_leave_loss = max(1 - b, 1e-12)
    chunks, total = [], 0
    while total < n:
        k = max(16, int(2 * (n - total) * a) + 16)
        runs_n = rng.geometric(a, size=k)               # delivered runs end when a loss starts
        runs_l = rng.geometric(q_leave_loss, size=k)    # loss runs end when a delivery comes
        if lost:
            lengths = np.column_stack([runs_l, runs_n]).ravel(); vals = np.tile([True, False], k)
        else:
            lengths = np.column_stack([runs_n, runs_l]).ravel(); vals = np.tile([False, True], k)
        chunks.append(np.repeat(vals, lengths))
        total += int(lengths.sum())
    return np.concatenate(chunks)[:n]


def sequential_curve(loss, rate, points=40):
    """Posterior mean and 95% credible interval of the loss rate as the capture goes on."""
    n = len(loss)
    cuts = np.unique(np.linspace(max(1, int(rate * 5)), n, points).astype(int))
    cum = np.cumsum(loss)
    rows = []
    for m in cuts:
        p = BY.beta_posterior(int(cum[m - 1]), int(m))
        rows.append(dict(t=m / rate, mean=p["mean"], lo=p["ci_low"], hi=p["ci_high"]))
    return rows


def power_curve(a, b, rate, durations_s, reps, alpha, rng):
    """Share of simulated captures (from the fitted chain) in which the runs test rejects independence."""
    out = []
    for T in durations_s:
        n = int(T * rate)
        hits = 0
        for _ in range(reps):
            x = simulate_markov(n, a, b, rng)
            if x.sum() >= 2 and (len(x) - x.sum()) >= 2:
                r = HT.runs_test(x)
                hits += r["p"] < alpha and r["z"] < 0
        out.append(dict(duration_s=T, power=hits / reps))
    return out


def coverage_check(a, b, rate, duration_s, reps, block_packets, rng):
    """How often naive and design-effect adjusted 95% intervals contain the chain's true loss rate."""
    true_p = stationary_loss(a, b)
    n = int(duration_s * rate)
    hit_n = hit_a = 0
    for _ in range(reps):
        x = simulate_markov(n, a, b, rng)
        k = int(x.sum())
        pn = BY.beta_posterior(k, n)
        pa = BY.adjusted_posterior(x, block_packets)
        hit_n += pn["ci_low"] <= true_p <= pn["ci_high"]
        hit_a += pa["ci_low"] <= true_p <= pa["ci_high"]
    return dict(true_p=true_p, naive=hit_n / reps, adjusted=hit_a / reps, reps=reps, duration_s=duration_s)
