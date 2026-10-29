> Continuing on a new device? Read [`HANDOFF.md`](HANDOFF.md) first.

# Statistical Modelling of Packet-Loss Patterns in Computer Networks

*Distribution Fitting, Burstiness Testing and Bayesian Estimation* — Probability & Statistics (BAMAT207) case study.

**Tracks:** Track 3 (Probability Distribution Modelling) as the core; Track 1 (Bayesian Intelligence) and Track 5 (Hypothesis Testing & Comparative Analysis) as supporting components.

Textbook models assume packets are lost independently (a Poisson process). This project tests that assumption, shows how it fails (losses come in bursts), quantifies the burstiness, and shows that ignoring it makes standard 95% intervals over-confident. It then corrects them with a design-effect adjustment.

**Phase 1 (this repo):** a simulation study built on the Gilbert-Elliott two-state Markov loss model. The true parameters are known, so every estimator and test can be checked against the truth. **Phase 2:** real packet captures, analysed with the same pipeline.

## Networks studied (1 hour at 50 packets/s = 180,000 packets each)

| Code | Network | Loss level |
|---|---|---|
| S1 | Wired broadband | ~0.3% |
| S2 | Campus Wi-Fi | ~1.3% |
| S3 | Mobile hotspot | ~4% |

## Run

```bash
pip install -r requirements.txt
python3 run_case_study.py
```

Requires Python 3.9+. The seed is fixed at 2026, so results are reproducible. Outputs go to `results/`: figures `fig1`–`fig7`, `results.json` and `summary.md`.

## Interactive app

```bash
streamlit run app.py
```

This opens the **Packet-Loss Lab** in your browser. Pick a network, choose how long to watch, and see:

1. **Watch the packets:** every packet as a green (delivered) or red (lost) square, plus losses per second.
2. **Is it random?** Four checks (spread, heavy seconds, runs, after-a-loss), each marked "looks random" or "not random".
3. **How sure are we?** The normal and corrected 95% ranges against the true loss rate, a button that re-runs hundreds of pretend recordings to test them, and Bayesian learning over time.
4. **Full study results:** the saved one-hour study and the power curves.

Turn on **coin-flip mode** to make losses independent with the same average rate: every check turns green. With the default settings (Wi-Fi, 1 hour, seed 2026) the app reproduces the numbers in `results/summary.md`.

## Code layout

| File | Contents | Owner |
|---|---|---|
| `src/config.py` | Seed, scenario parameters, Monte Carlo sizes | shared |
| `src/loss_model.py` | Gilbert-Elliott simulation, windows, gaps, bursts | Member A |
| `src/distributions.py` | MLE: Poisson, Negative Binomial, Exponential; EM for the 2-phase hyperexponential | Member A |
| `src/hypothesis_tests.py` | χ² GOF, dispersion, bootstrap KS, runs test, Markov LRT, Kruskal-Wallis / Mann-Whitney, power study | Member B |
| `src/bayesian.py` | Beta-Binomial posteriors, sequential updating, Markov posteriors, predictive check, design effect, coverage study | Member C |
| `src/plots.py` | Figures | shared |
| `app.py` | Interactive Streamlit app built on the same modules | shared |
| `run_case_study.py` | Full pipeline and auto-generated `summary.md`; checks the config before running | shared |
| `slides/export_deck_data.py` | Collects every number shown in the Review-1 deck from the pipeline output | shared |
| `slides/build_deck.js` | Builds the Review-1 PowerPoint from `slides/deck_data.json` | shared |
| `tests/test_model.py` | Edge cases, statistical checks and full-pipeline runs under different settings | shared |

## Tests

```bash
pip install pytest
python3 -m pytest tests -q
```

There are 37 tests. `tests/test_app.py` (4 tests) starts the app and checks it reproduces the study. The 33 model tests cover three areas:

- Edge cases: empty traces, no losses, all losses and very short runs.
- Statistical checks: the simulator against theory, recovery of known Negative Binomial, two-phase and Markov parameters, the Markov G² against SciPy's G-test, Type I error, and interval coverage.
- Full pipeline runs: shorter traces, 2-s windows, 20 packets/s, another seed, two networks and four networks, plus a check that two runs give identical results.

Invalid settings (one network, an unknown `SEQ_SCENARIO`, a network with fewer than 3 losses) stop with a clear error message.

## Rebuilding the slides

```bash
python3 run_case_study.py
python3 slides/export_deck_data.py
cd slides && npm install && node build_deck.js
```

Final-review deck (21 slides: adds progress, discussion, limitations, the web app and an abbreviations appendix):

```bash
node slides/build_deck.js Packet_Loss_Case_Study_Final.pptx --final
```

## IEEE paper

Six-page IEEE conference paper (IEEEtran). Every number is filled in from `results/results.json` and `slides/deck_data.json`.

```bash
python3 paper/build_paper.py   # writes paper/Packet_Loss_IEEE_Paper.tex and .pdf (needs pdflatex)
python3 paper/make_docx.py     # writes paper/Packet_Loss_IEEE_Paper.docx (needs pandoc, python-docx)
```

For Overleaf, upload `paper/Packet_Loss_IEEE_Paper.tex`, `paper/IEEEtran.cls` and the `paper/figures/` folder.

## Phase 2: real network measurements

`realworld/probe.py` sends 50 packets per second over a real network (Wi-Fi, phone hotspot, wired) and records which are lost; `realworld/analyze_captures.py` runs the Phase 1 statistics on the captures. Step-by-step guide: [realworld/README.md](realworld/README.md).

```bash
caffeinate -i python3 realworld/probe.py --label wifi --target gateway --duration 600
python3 realworld/analyze_captures.py --latest
```

## Known limitations

- The index-of-dispersion test compares counts with a Poisson law. Counts of 50 independent packets are Binomial, whose variance is slightly below the mean, so the test is conservative: under independence it rejects about 1% of the time instead of 5%. It never over-states burstiness.
- The runs test and the Markov likelihood-ratio test use large-sample approximations. In very short captures with few losses, their false-rejection rate ranges from about 1% to 9% instead of exactly 5%. For the full one-hour traces it is close to 5%.

## Headline findings

- Poisson is rejected in all three networks (variance/mean = 1.59 / 5.31 / 10.17). The Negative Binomial fits far better.
- Inter-loss gaps are not exponential (KS-bootstrap p < 0.0005). A 2-phase hyperexponential separates in-burst gaps from between-burst gaps.
- A loss makes the next loss 31–43× more likely (runs test and Markov LRT, p < 1e-10).
- Naive 95% intervals cover the true loss rate only 85.7% / 60.9% / 40.3% of the time. The design-effect correction restores coverage to 93–94%.
- Detecting burstiness with 80% power takes about 30 s of traffic on Wi-Fi, 15 s on mobile and about 5 min on wired broadband.

See [`results/summary.md`](results/summary.md) for the full tables.
