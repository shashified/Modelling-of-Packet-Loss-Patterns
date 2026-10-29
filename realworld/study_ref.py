"""The case-study (Phase 1) reference that real runs are compared against.

Phase 1 simulated three networks with the Gilbert-Elliott model and saved every number in
results/results.json. This module reads those numbers and, for charts, rebuilds the exact
simulated packet traces (same seed and order as run_case_study.py), so a real capture can be
laid over the study network it is meant to resemble.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from src import config as C        # noqa: E402
from src import loss_model as LM   # noqa: E402

RESULTS = os.path.join(ROOT, "results", "results.json")
KEYS = list(C.SCENARIOS)            # S1_Wired, S2_WiFi, S3_Mobile


def label(key):
    return C.SCENARIOS[key]["label"]


def match(run_label):
    """Which study network a real run should be compared with, from its label."""
    s = run_label.lower()
    if "hotspot" in s or "mobile" in s or "4g" in s or "5g" in s:
        return "S3_Mobile"
    if "wired" in s or "ethernet" in s or "lan" in s:
        return "S1_Wired"
    return "S2_WiFi"


def load_results():
    if not os.path.exists(RESULTS):
        return None
    with open(RESULTS) as f:
        return json.load(f)


def summary(R, key):
    """The headline numbers of one study network, in the same shape as a real-run summary."""
    s = R["scenarios"][key]
    d, t, f, b = s["descriptive"], s["tests"], s["fits"], s["bayes"]
    cov = R.get("coverage", {}).get(key, {})
    return dict(
        name=f"Case study: {s['label']}", loss_rate=d["loss_rate"],
        ci=(b["posterior"]["ci_low"], b["posterior"]["ci_high"]),
        adj_ci=(b["adjusted_posterior"]["ci_low"], b["adjusted_posterior"]["ci_high"]),
        D=d["window_var"] / d["window_mean"], disp_p=t["dispersion"]["p"],
        chisq_p=t["chisq_poisson"]["p"], nb_better=f["aic_negbin"] < f["aic_poisson"],
        runs_z=t["runs"]["z"], runs_p=t["runs"]["p"],
        a=t["markov_lrt"]["p_L_given_N"], b=t["markov_lrt"]["p_L_given_L"], markov_p=t["markov_lrt"]["p"],
        ba=b["markov"]["amp_q"][1], mean_burst=d["mean_burst_len"], ks_p=t["ks_exponential"]["p"],
        ks_B=t["ks_exponential"].get("B"), deff=b["adjusted_posterior"]["deff"],
        cov_naive=cov.get("naive"), cov_adjusted=cov.get("adjusted"),
        packets=d["packets"], losses=d["losses"], duration_s=R["config"]["duration_s"],
        heavy_pred=b["predictive_tail"]["predicted"], heavy_obs=b["predictive_tail"]["observed"],
        verdict="bursty")


def traces():
    """Rebuild the three simulated traces exactly as run_case_study.py made them."""
    rng = np.random.default_rng(C.SEED)
    n = C.PACKET_RATE * C.DURATION_S
    out = {}
    for k, prm in C.SCENARIOS.items():
        prm = {x: v for x, v in prm.items() if x != "label"}
        loss = LM.simulate_losses(n, rng=rng, **prm)
        gaps = LM.inter_loss_gaps(loss, C.PACKET_RATE, rng)
        out[k] = dict(loss=loss, gaps=gaps, rate=float(C.PACKET_RATE),
                      counts=LM.window_counts(loss, C.PACKET_RATE * C.WINDOW_S))
    return out
