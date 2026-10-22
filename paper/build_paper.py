"""Build the IEEE conference paper from the study results.

Every number in the paper is read from results/results.json and slides/deck_data.json.
Nothing numeric is typed into the template by hand.

Run from the repo root:
    python3 paper/build_paper.py          # writes paper/Packet_Loss_IEEE_Paper.tex and compiles the PDF
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER = os.path.join(ROOT, "paper")
OUT_NAME = "Packet_Loss_IEEE_Paper"

AUTHORS = [  # name, registration number, email
    ("Kyra Panwar", "25BBS0095", "kyra.panwar2025@vitstudent.ac.in"),
    ("Shashank Tiwari", "25BDS0053", "shashank.tiwari2025@vitstudent.ac.in"),
    ("Aashman Biyani", "25BBS0100", "aashman.biyani2025@vitstudent.ac.in"),
]
AFFILIATION = "Vellore Institute of Technology, Vellore, India"
SHORT = {"S1_Wired": "Wired", "S2_WiFi": "Wi-Fi", "S3_Mobile": "Mobile"}


def load():
    with open(os.path.join(ROOT, "results", "results.json")) as f:
        R = json.load(f)
    with open(os.path.join(ROOT, "slides", "deck_data.json")) as f:
        D = json.load(f)
    return R, D


# ---------- formatting helpers ----------
def pct(x, d=2):
    return f"{x * 100:.{d}f}\\%"


def num(x, d=0):
    s = f"{x:,.{d}f}"
    return s.replace(",", "{,}")


def pval(p, B=None):
    if B is not None and p <= 1 / (B + 1) + 1e-12:
        return f"$<{1 / B:g}$"
    if p < 1e-10:
        return "$<10^{-10}$"
    return f"{p:.3g}"


def build_values(R, D):
    C = D["config"]
    keys = D["keys"]
    S = R["scenarios"]
    v = {
        "seed": str(C["seed"]),
        "rate": str(C["packet_rate"]),
        "spacing_ms": f"{1000 / C['packet_rate']:g}",
        "duration_s": num(C["duration_s"]),
        "duration_h": f"{C['duration_s'] / 3600:g}",
        "packets": num(C["packets"]),
        "packets_total": num(C["packets"] * len(keys)),
        "windows": num(C["duration_s"] / C["window_s"]),
        "window_s": f"{C['window_s']:g}",
        "block_s": f"{C['block_s']:g}",
        "block_packets": num(C["block_s"] * C["packet_rate"]),
        "alpha": f"{C['alpha']:g}",
        "n_boot": num(C["n_boot_ks"]),
        "n_boot_mix": num(S[keys[0]]["tests"]["ks_hyperexp"]["B"]),
        "power_reps": num(C["power_reps"]),
        "cov_reps": num(C["coverage_reps"]),
        "cov_min": f"{C['coverage_duration_s'] / 60:g}",
        "ord_draws": num(C["ordering_draws"]),
        "heavy_k": str(C["heavy_k"]),
        "mc_se": f"{(0.25 / C['power_reps']) ** 0.5:.3f}",
        "power_target": f"{C['power_target']:g}",
        "n_scen": {2: "two", 3: "three", 4: "four"}.get(len(keys), str(len(keys))),
        "kw_H": f"{R['comparison']['kruskal_H']:.1f}",
        "chi_hom": num(R["comparison"]["chi2_homog"], 1),
        "chi_hom_df": str(R["comparison"]["chi2_df"]),
        "ordering": f"{R['ordering']['all_ordered']:.3f}",
    }
    seq = R["sequential"]
    v["seq_label"] = S[seq["scenario"]]["label"]
    v["seq_first_t"] = str(seq["steps"][0]["t"])
    v["seq_first"] = f"{pct(seq['steps'][0]['mean'])} [{pct(seq['steps'][0]['ci_low'])}, {pct(seq['steps'][0]['ci_high'])}]"
    v["seq_last_t"] = num(seq["steps"][-1]["t"])
    v["seq_last"] = f"{pct(seq['steps'][-1]['mean'])} [{pct(seq['steps'][-1]['ci_low'])}, {pct(seq['steps'][-1]['ci_high'])}]"
    v["bonf_max"] = pval(max(p["p_bonf"] for p in R["comparison"]["pairwise"]))

    durs = R["power"]["durations_s"]
    rows = {k: [] for k in ["params", "counts", "gaps", "dep", "bayes", "power"]}
    per = {}
    for k in keys:
        s, d, f, t, b = S[k], S[k]["descriptive"], S[k]["fits"], S[k]["tests"], S[k]["bayes"]
        sc = D["scenarios"][k]
        cov = R["coverage"][k]
        pw = R["power"][k]

        def first_len(series):
            for T, x in zip(durs, series):
                if x >= C["power_target"]:
                    return f"{T}"
            return f"$>{durs[-1]}$"

        m = dict(
            label=SHORT.get(k, s["label"]), name=s["label"],
            p=f"{sc['p_gb']:g}", r=f"{sc['p_bg']:g}", hg=f"{sc['h_g']:g}", hb=f"{sc['h_b']:g}",
            pib=pct(sc["pi_b"]), spell=f"{sc['mean_bad_spell']:.1f}",
            true=pct(s["true_long_run_loss_rate"], 3), obs=pct(d["loss_rate"], 3), losses=num(d["losses"]),
            mean=f"{d['window_mean']:.3f}", var=f"{d['window_var']:.3f}", D=f"{t['dispersion']['D']:.2f}",
            share=pct(d["share_losses_in_bursts"], 1), mburst=f"{d['mean_burst_len']:.2f}",
            maxburst=str(d["max_burst_len"]), maxwin=str(d["max_losses_in_window"]),
            chiP=num(t["chisq_poisson"]["stat"], 1), chiNB=num(t["chisq_negbin"]["stat"], 1),
            aicP=num(f["aic_poisson"]), aicNB=num(f["aic_negbin"]), nbr=f"{f['negbin_r']:.3f}",
            hobs=num(sc["heavy_seconds"]["observed"]), hpois=f"{sc['heavy_seconds']['poisson']:.3g}",
            hnb=f"{sc['heavy_seconds']['negbin']:.1f}",
            wfast=pct(f["hyper_w_fast"], 0), fastms=f"{1000 / f['hyper_rate_fast']:.0f}",
            slows=f"{1 / f['hyper_rate_slow']:.1f}", ksexpD=f"{t['ks_exponential']['D']:.3f}",
            ksexp=pval(t["ks_exponential"]["p"], t["ks_exponential"]["B"]),
            ksmix=pval(t["ks_hyperexp"]["p"], t["ks_hyperexp"]["B"]),
            aicE=num(f["aic_exp"]), aicH=num(f["aic_hyper"]),
            runs=num(t["runs"]["runs"]), runsE=num(t["runs"]["expected"]), z=f"{t['runs']['z']:.1f}",
            G2=num(t["markov_lrt"]["G2"], 1), a=pct(t["markov_lrt"]["p_L_given_N"], 2),
            b=pct(t["markov_lrt"]["p_L_given_L"], 1), amp=f"{b['markov']['amp_q'][1]:.0f}",
            ampci=f"[{b['markov']['amp_q'][0]:.0f}, {b['markov']['amp_q'][2]:.0f}]",
            blen=f"{b['markov']['burst_len_q'][1]:.2f}",
            pmean=pct(b["posterior"]["mean"], 3),
            pci=f"[{pct(b['posterior']['ci_low'], 3)}, {pct(b['posterior']['ci_high'], 3)}]",
            deff=f"{b['adjusted_posterior']['deff']:.2f}",
            neff=num(round(d["packets"] / b["adjusted_posterior"]["deff"], -3)),
            aci=f"[{pct(b['adjusted_posterior']['ci_low'], 3)}, {pct(b['adjusted_posterior']['ci_high'], 3)}]",
            covN=pct(cov["naive"], 1), covA=pct(cov["adjusted"], 1),
            wN=f"{cov['width_naive'] * 100:.3f}", wA=f"{cov['width_adjusted'] * 100:.3f}",
            pred=f"{b['predictive_tail']['predicted']:.2g}", seen=f"{b['predictive_tail']['observed']:.2g}",
            ratio=num(b["predictive_tail"]["observed"] / b["predictive_tail"]["predicted"]),
            pwD=first_len(pw["dispersion"]), pwR=first_len(pw["runs"]), pwM=first_len(pw["markov_lrt"]),
            pw600=f"{min(pw['dispersion'][-1], pw['runs'][-1], pw['markov_lrt'][-1]):.2f}",
            true_raw=s["true_long_run_loss_rate"],
            naive_hit=b["posterior"]["ci_low"] <= s["true_long_run_loss_rate"] <= b["posterior"]["ci_high"],
            adj_hit=b["adjusted_posterior"]["ci_low"] <= s["true_long_run_loss_rate"] <= b["adjusted_posterior"]["ci_high"],
        )
        per[k] = m
        rows["params"].append(f"{m['label']} & {m['p']} & {m['r']} & {m['hg']} & {m['hb']} & {m['pib']} & {m['spell']} & {m['true']} \\\\")
        rows["counts"].append(f"{m['label']} & {m['obs']} & {m['mean']} & {m['var']} & {m['D']} & {m['chiP']} & {m['aicP']} & {m['aicNB']} & {m['hobs']} / {m['hpois']} / {m['hnb']} \\\\")
        rows["gaps"].append(f"{m['label']} & {m['wfast']} & {m['fastms']} & {m['slows']} & {m['ksexp']} & {m['ksmix']} & {m['aicE']} & {m['aicH']} \\\\")
        rows["dep"].append(f"{m['label']} & {m['runs']} & {m['runsE']} & {m['z']} & {m['G2']} & {m['a']} & {m['b']} & {m['amp']} & {m['blen']} \\\\")
        rows["bayes"].append(f"{m['label']} & {m['pmean']} & {m['pci']} & {m['deff']} & {m['aci']} & {m['covN']} & {m['covA']} \\\\")
        rows["power"].append(f"{m['label']} & {m['pwD']} & {m['pwR']} & {m['pwM']} & {m['pw600']} \\\\")

    for name, lines in rows.items():
        v[f"rows_{name}"] = "\n".join(lines)
    for k, m in per.items():
        tag = {"S1_Wired": "W", "S2_WiFi": "F", "S3_Mobile": "M"}.get(k)
        if tag:
            for kk, vv in m.items():
                v[f"{tag}_{kk}"] = vv if isinstance(vv, str) else vv
    lab = lambda f: ", ".join(per[k][f] for k in keys)
    v["list_D"] = lab("D")
    v["list_amp"] = lab("amp")
    v["list_covN"] = lab("covN")
    v["list_covA"] = lab("covA")
    v["list_pmean"] = lab("pmean")
    v["list_blen"] = lab("blen")
    v["amp_lo"] = min(per[k]["amp"] for k in keys)
    v["amp_lo"] = str(min(int(per[k]["amp"]) for k in keys))
    v["amp_hi"] = str(max(int(per[k]["amp"]) for k in keys))
    v["covN_lo"] = pct(min(R["coverage"][k]["naive"] for k in keys), 1)
    v["covN_hi"] = pct(max(R["coverage"][k]["naive"] for k in keys), 1)
    v["covA_lo"] = pct(min(R["coverage"][k]["adjusted"] for k in keys), 1)
    v["covA_hi"] = pct(max(R["coverage"][k]["adjusted"] for k in keys), 1)
    v["fast_lo"] = str(min(int(per[k]["fastms"]) for k in keys))
    v["fast_hi"] = str(max(int(per[k]["fastms"]) for k in keys))
    v["ratio_MW"] = f"{S[keys[-1]]['descriptive']['loss_rate'] / S[keys[0]]['descriptive']['loss_rate']:.0f}"
    v["pbga"] = f"{min(S[k]['bayes']['markov']['P_b_gt_a'] for k in keys):.3f}"
    v["dur_lo"], v["dur_hi"] = str(durs[0]), str(durs[-1])
    v["min_pw_hi"] = f"{min(min(R['power'][k][t][-1] for t in ('dispersion','runs','markov_lrt')) for k in keys):.2f}"
    v["authors_tex"] = "\n\\and\n".join(
        f"\\IEEEauthorblockN{{{n}}}\n\\IEEEauthorblockA{{Reg. No. {rno}\\\\\n{AFFILIATION}\\\\\n\\texttt{{{e}}}}}"
        for n, rno, e in AUTHORS)
    return v


def fill(template, v):
    missing = set()

    def rep(mo):
        key = mo.group(1)
        if key not in v:
            missing.add(key)
            return mo.group(0)
        return str(v[key])

    out = re.sub(r"<<([A-Za-z0-9_]+)>>", rep, template)
    if missing:
        sys.exit(f"Template keys with no value: {sorted(missing)}")
    return out


def main():
    R, D = load()
    v = build_values(R, D)
    with open(os.path.join(PAPER, "template.tex")) as f:
        tex = fill(f.read(), v)
    # house rules: no en or em dashes in the text
    body = tex.split("\\begin{document}", 1)[1]
    if re.search(r"(?<![-!])--(?!-)|---|\u2013|\u2014", body):
        sys.exit("Dash rule broken: the paper contains an en or em dash")
    figdir = os.path.join(PAPER, "figures")
    os.makedirs(figdir, exist_ok=True)
    for fn in os.listdir(os.path.join(ROOT, "results")):
        if fn.endswith(".png"):
            shutil.copy(os.path.join(ROOT, "results", fn), figdir)
    tex_path = os.path.join(PAPER, OUT_NAME + ".tex")
    with open(tex_path, "w") as f:
        f.write(tex)
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", OUT_NAME + ".tex"],
                           cwd=PAPER, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-3000:])
            sys.exit("pdflatex failed")
    for ext in (".aux", ".log", ".out"):
        p = os.path.join(PAPER, OUT_NAME + ext)
        if os.path.exists(p):
            os.remove(p)
    print("Wrote", os.path.join(PAPER, OUT_NAME + ".pdf"))


if __name__ == "__main__":
    main()
