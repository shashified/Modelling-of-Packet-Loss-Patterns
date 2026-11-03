"""Figure for the conference paper: P(L|N) and P(L|L) for the simulated networks and the real hotspot captures."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src import plots as P

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(ROOT, "results", "results.json")))
J = json.load(open(os.path.join(ROOT, "realworld", "results", "results.json")))
C = {c["label"]: c for c in J["captures"]}
rows = [(R["scenarios"][k]["bayes"]["markov"], R["scenarios"][k]["label"] + " (sim.)", P._col(k))
        for k in ["S1_Wired", "S2_WiFi", "S3_Mobile"]]
rows += [(C["hotspot#1"]["markov"], "Hotspot, gateway (real)", "#5c4d7d"),
         (C["hotspot_internet#2"]["markov"], "Hotspot, 1.1.1.1 (real)", "#2d6a4f")]

fig, ax = plt.subplots(figsize=(7, 4.4))
for i, (m, name, col) in enumerate(rows):
    for q, marker, lab in [(m["a_q"], "o", "P(loss | previous delivered)"), (m["b_q"], "s", "P(loss | previous lost)")]:
        ax.errorbar(q[1] * 100, i, xerr=[[(q[1] - q[0]) * 100], [(q[2] - q[1]) * 100]], fmt=marker, color=col, ms=8,
                    capsize=4, label=lab if i == 0 else None, mfc=col if marker == "s" else "white")
    ax.annotate(f"x{m['amp_q'][1]:.0f}", ((m["a_q"][1] * m["b_q"][1]) ** 0.5 * 100, i + 0.2), ha="center", fontsize=10, color=col)
ax.axhline(2.5, color="#999999", lw=0.8, ls="--")
ax.set_yticks(range(len(rows)))
ax.set_yticklabels([r[1] for r in rows])
ax.set_xscale("log")
ax.set_xlabel("probability (%), posterior median with 95% credible interval")
ax.set_ylim(-0.6, len(rows) - 0.4)
ax.legend(fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, frameon=False)
P._save(fig, os.path.join(HERE, "figures", "fig_markov_sim_real.png"))
