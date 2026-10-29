# HANDOFF: Packet-Loss Case Study (BAMAT207)

Read this file top to bottom before doing anything on a new device. It records what exists, where it lives, how to run it, the rules the work follows, and what is still pending.

Last updated: 22 Oct 2026 (paper and final deck added). Repo state at handoff: `main` (latest code commit `fd6c12a`, this file added in `9661279`), 37 tests passing.

---

## 0. Quick start (new device, about 5 minutes)

```bash
git clone https://github.com/AashmanBiyani08/Prob_Stats_Project.git
cd Prob_Stats_Project
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
python3 -m pytest tests -q         # expect: 37 passed
python3 run_case_study.py          # ~15 s, ends with "DONE. Results in ./results/"
streamlit run app.py               # opens http://localhost:8501
```

To rebuild the PowerPoint (needs Node.js 18+):

```bash
cd slides && npm install && cd ..
python3 slides/export_deck_data.py
node slides/build_deck.js Packet_Loss_Case_Study_Review1.pptx
```

Note: on the original laptop the virtual environment lived one folder up (`../.venv`). On a new device keep it inside the repo as `.venv` (already in `.gitignore`).

---

## 1. Project in one paragraph

**Title:** Statistical Modelling of Packet-Loss Patterns in Computer Networks: Distribution Fitting, Burstiness Testing and Bayesian Estimation.
**Course:** BAMAT207 Probability and Statistics. **Tracks:** Track 3 (core, distribution modelling), Track 1 (Bayesian) and Track 5 (hypothesis testing).
**Idea:** textbooks assume each packet is lost independently (Poisson counts, exponential gaps). We simulate three networks with a two-state Gilbert-Elliott model (Good/Bad), show losses come in bursts, quantify the burstiness, and show that naive 95% intervals for the loss rate are badly over-confident. A design-effect correction fixes them.
**Framing rule:** results are **Phase 1, a simulation study with known parameters**. Phase 2 (future) uses real captures with the same code. Never present the data as real network measurements.

### Team (shown on slide 1, stored in `slides/build_deck.js` → `TEAM`)

| Name | Registration number |
|---|---|
| Kyra Panwar | 25BBS0095 |
| Shashank Tiwari | 25BDS0053 |
| Aashman Biyani | 25BBS0100 |

---

## 2. Where everything lives

### 2.1 In GitHub (https://github.com/AashmanBiyani08/Prob_Stats_Project)

| Path | What it is |
|---|---|
| `run_case_study.py` | Main pipeline: simulate → describe → fit → test → Bayesian → Monte Carlo → figures → `results/`. Checks config first (`check_config`). |
| `src/config.py` | **Every setting.** Seed, packet rate, duration, scenarios, Monte Carlo sizes, thresholds, app settings. Change things here, nowhere else. |
| `src/loss_model.py` | Gilbert-Elliott simulator (geometric sojourn method), window counts, gaps, burst lengths. Validates probabilities. |
| `src/distributions.py` | MLE fits: Poisson, Negative Binomial (profile MLE), Exponential; EM for 2-phase hyperexponential; AIC. |
| `src/hypothesis_tests.py` | χ² GOF (tail pooling), dispersion test, bootstrap KS (exp and mixture), runs test, Markov LRT, Kruskal-Wallis / Mann-Whitney / χ² homogeneity, power study. |
| `src/bayesian.py` | Beta-Binomial posteriors, sequential updating, ordering probability, Markov posteriors, predictive check, design effect, adjusted posterior, coverage study. |
| `src/plots.py` | The 7 figures. Colours per scenario; unknown scenarios get spare colours. |
| `results/` | Generated outputs: `fig1`…`fig7`, `results.json`, `summary.md`. Committed so the numbers are visible on GitHub. |
| `app.py` | **Packet-Loss Lab**, the Streamlit web app (see §5). |
| `.streamlit/config.toml` | App theme. Only applies when `streamlit run` is started from the repo folder. |
| `slides/export_deck_data.py` | Collects every number the deck shows into `slides/deck_data.json` (re-simulates with the same seed and asserts it matches `results.json`). |
| `slides/build_deck.js` | Builds the 16-slide PowerPoint with pptxgenjs from `deck_data.json`. **All slide text and team names live here.** |
| `slides/package.json` | Node dependency: `pptxgenjs@3.12.0`. `node_modules/` is git-ignored. |
| `tests/test_model.py` | 33 tests: edge cases, statistical correctness, full pipeline under 7 configs, determinism. |
| `tests/test_app.py` | 4 Streamlit `AppTest` smoke tests (default view reproduces 2,326 Wi-Fi losses; coin mode; other networks). |
| `README.md` | Public description, run instructions, tests, slides, known limitations. |
| `requirements.txt` | numpy, scipy, matplotlib, streamlit, pandas, altair. (pytest is extra, for tests only.) |

### 2.2 NOT in GitHub: copy these to the new device yourself

These sit in the parent folder `~/Desktop/Prob Stats Proj/` on the original laptop. Send them by Google Drive, WhatsApp, a pen drive or email.

| File | Can it be regenerated? |
|---|---|
| `Packet_Loss_Case_Study_Review1.pptx`, the final 16-slide deck | **Yes**, exactly, with the commands in §0. Checked on 22 Oct: the folder copy has no manual edits (built 1 s before the last commit). |
| `Team_Prep_Guide.pdf` (4 pages: roles, formulas, 18 viva Q&As) | **No.** Its HTML source was in a temporary folder. Copy the PDF. Note: it still lists "Member A/B/C" slide assignments. |
| `Project_Study_Handbook.pdf` (16 pages: full study guide) | **No.** Copy the PDF. The user said they don't want more handbook-style docs. |
| `PNS_Case_Study_CLAUDE 2.md`, the original brief (65 KB) | **No.** Copy it. It is the source spec: PART 7 holds the original code, PART 4 the expected numbers, PARTS 5 and 6 roles and viva questions. Kept private on purpose (not pushed). |
| `fig*.png` in the parent folder | Old copies; the real ones are in `results/`. Not needed. |

### 2.3 Claude artifacts (claude.ai, private to the account)

- Web slide deck (old 12-slide version, has presenter tags and em dashes): https://claude.ai/artifact/NQXcMMcsmprd9Am6jWUCee
- Team prep guide doc (older wording): https://claude.ai/code/artifact/78ad0565-a0df-4ba6-8a5c-082d7961802a

Both are **outdated** relative to the `.pptx`. The `.pptx` is the source of truth for slides.

---

## 3. Key results (seed 2026, 1 hour, 50 packets/s, 180,000 packets per network)

| Quantity | Wired | Wi-Fi | Mobile |
|---|---|---|---|
| Model parameters p / r / hG / hB | 0.0005 / 0.30 / 0.002 / 0.50 | 0.002 / 0.15 / 0.004 / 0.60 | 0.004 / 0.08 / 0.006 / 0.70 |
| True loss rate (theory) | 0.283% | 1.184% | 3.905% |
| Observed loss rate (1-hour run) | 0.275% (495 losses) | 1.292% (2,326) | 3.937% (7,087) |
| Variance ÷ mean per second | 1.59 | 5.31 | 10.17 |
| Share of losses in bursts | 17.4% | 52.8% | 76.1% |
| Longest burst / most losses in 1 s | 6 / 7 | 9 / 25 | 16 / 40 |
| Seconds with ≥5 losses: observed / Poisson / NB | 7 / 0.001 / 0.9 | 131 / 2.0 / 124 | 487 / 180 / 492 |
| AIC Poisson → NB | 3,143 → 2,992 | 10,607 → 7,186 | 25,042 → 11,700 |
| KS exponential p | < 0.0005 | < 0.0005 | < 0.0005 |
| Hyperexp fast share, mean fast gap, mean slow gap | 16%, 32 ms, 8.6 s | 55%, 33 ms, 3.4 s | 77%, 29 ms, 2.1 s |
| Runs observed vs expected (z) | 887 vs 988 (−43.5) | 3,005 vs 4,593 (−146.7) | 6,293 vs 13,617 (−228.2) |
| P(L\|N) → P(L\|L) | 0.247% → 10.5% | 0.845% → 35.4% | 1.819% → 55.6% |
| Markov G² | 288.4 | 4,498.6 | 18,560.2 |
| Burst amplification b/a (posterior median) | 43× | 42× | 31× |
| Posterior mean [95% CrI] | 0.276% [0.252, 0.300] | 1.293% [1.241, 1.345] | 3.938% [3.848, 4.028] |
| Design effect (10-s blocks) | 1.52 | 6.43 | 12.14 |
| Adjusted 95% interval | [0.247, 0.307] | [1.167, 1.431] | [3.636, 4.263] |
| Coverage naive → adjusted (2,000 × 10-min captures) | 85.7% → 93.3% | 60.9% → 94.0% | 40.3% → 94.0% |
| Capture for 80% power (runs test) | 300 s | 30 s | 15 s |

Comparison: Kruskal-Wallis H = 937.3; χ² homogeneity 7,143 (df 2); every pairwise Mann-Whitney significant after Bonferroni. Sequential (Wi-Fi): 10 s 3.78% [2.30, 5.62] → 3,600 s 1.29% [1.24, 1.35]. Live example: Wi-Fi naive interval misses the true 1.184%; the adjusted one contains it. Phase 2 recommendation: ≥ 10 minutes per network (every test power ≥ 0.97).

**One-sentence finding:** packet losses are not independent; they come in bursts, so Poisson and exponential models fail and naive 95% intervals can be wrong more than half the time. We quantify the burstiness and correct the inference.

---

## 4. How the pieces connect (regeneration chain)

```
src/config.py ──► run_case_study.py ──► results/ (figs, results.json, summary.md)
                                              │
                                              ▼
                         slides/export_deck_data.py ──► slides/deck_data.json
                                                                  │
                                                                  ▼
                                   slides/build_deck.js ──► Packet_Loss_Case_Study_Review1.pptx
app.py ──► imports src/* directly, and reads results/results.json for its "Full study" tab
```

**Rule:** nothing on the slides or in the app is typed in by hand. If you change `config.py`, rerun the chain and everything updates. Presentation-only constants (colours, layout sizes, team names, slide wording) are the only literals.

---

## 5. The web app (Packet-Loss Lab)

Start: `streamlit run app.py` from the repo folder → **http://localhost:8501** (if 8501 is busy it uses 8502; check the terminal output). Stop with Ctrl-C.

- **Sidebar:** pick network; "Turn bursts OFF (coin-flip mode)" (same loss rate, independent losses); how long to watch (1 min to 1 hour); optional fine-tune sliders for p, r, hG, hB; "New run" (seed + 1) and "Seed 2026" (reset).
- **Top:** 5 stat tiles (wrap on narrow screens) + red/green verdict.
- **Tab 1 Watch the packets:** 700 packets as green/red squares, losses per second chart.
- **Tab 2 Is it random?:** 4 check cards (spread, heavy seconds via Poisson tail test, runs, after-a-loss) + Poisson vs NB chart + bonus gap check.
- **Tab 3 How sure are we?:** naive vs corrected interval against the true rate; button runs a coverage study (100 to 1,000 pretend recordings); Bayesian learning curve.
- **Tab 4 Full study results:** table from `results/results.json` + power curves.
- Default settings reproduce the study exactly (2,326 Wi-Fi losses, 42×), because the app consumes random draws in the same order as the pipeline.

**1-minute demo script:** (1) Wi-Fi default: point at clumped red squares and "42× likelier". (2) Toggle coin-flip mode: all 4 checks go green. (3) Toggle back, tab 3: naive misses, corrected catches; press the button: about 60% vs 93%.

---

## 6. The PowerPoint (16 slides)

Style: white background, navy panel headers `#1F3A5F`, blue footer band `#2E6DB4` with page number, Cambria titles, Calibri body, pill cards, native editable charts (not images), speaker notes on every slide. Modelled on the user's SIH deck style.

| # | Title | Main content |
|---|---|---|
| 1 | Probability and Statistics Case Study | Title page, team name cards (name + reg no.), 3 stat boxes, sample mobile trace chart |
| 2 | Introduction | Problem text, 4 "Context" pills (real-time media, protocol settings, service levels, statistical inference), 3 research questions, independent vs Wi-Fi charts at the same rate |
| 3 | Objectives and Hypotheses | O1 to O6 cards, H1 to H4 table in plain words, α, track mapping |
| 4 | Loss Model and Data | Good/Bad diagram, 3 formula pills **with plain meanings**, scenario table, sampling boxes, Phase 1/2 |
| 5 | Methodology | Pipeline flowchart, why simulate first, software |
| 6 | Statistical Methods | Table: Obj · Method · Formula · **What it does** (plain one-liners), AIC / window / block pills |
| 7 | Descriptive Statistics | Table, key figures, var/mean chart, share-in-bursts chart |
| 8 | Distribution of Loss Counts | Log pmf chart, heavy-seconds bar chart, GOF table, verdict pill |
| 9 | Distribution of Inter-Loss Gaps | Survival chart, hyperexp table, AIC drop chart, fast/slow pills |
| 10 | Tests of Independence | P(L\|N) vs P(L\|L), runs chart, results table, "31× to 43×" box |
| 11 | Bayesian Estimation | Sequential chart, posterior table, H4 comparison, conjugate/ordering/burst pills |
| 12 | Predictive Check and Design Effect | Predicted vs observed chart, ratio boxes, deff chart, Var formula **+ plain meaning** |
| 13 | Coverage of 95% Intervals | Coverage combo chart, number-line example, width table |
| 14 | Power Analysis | Power curves, shortest-capture table, MC boxes, Phase 2 recommendation |
| 15 | Conclusions and Future Work | Findings, future work, proposed timeline (weeks after Review 1) |
| 16 | References | 15 IEEE-style references (Gilbert 1960, Elliott 1963, Yajnik 1999, Dempster 1977, Wald-Wolfowitz 1940, Lilliefors 1969, Wilks 1938, Kruskal-Wallis 1952, Mann-Whitney 1947, Akaike 1974, Kish 1965, Gelman 2013, NumPy 2020, SciPy 2020, Matplotlib 2007) |

### Deck rules the user asked for (must keep)

1. **No em dashes or en dashes** anywhere (slides and notes). Use commas, colons or "to".
2. **Short sentences**, none over 20 words.
3. **Original, plain, non-AI wording.** No "not X, but Y" constructions, no catchy taglines, no words like delve/crucial/leverage/seamless/robust.
4. **No presenter labels** ("Member A/B/C") on any slide.
5. **Every formula has a one-line plain-English meaning** next to it.
6. **All numbers come from the data** (`deck_data.json`), never typed in.
7. Run a 6-word overlap check against the original brief md to avoid copying its text (only the title and standard formulas may match).

QA used: `markitdown` text dump + regex checks for dashes and long sentences; render via LibreOffice → PDF → `pdftoppm` images and inspect every slide; `validate.py` from the pptx skill.

---

## 7. Testing and known limitations

- `python3 -m pytest tests -q` → **37 passed** (~14 s).
- 13 edge-case bugs were found and fixed on 15 Oct (empty traces, ZeroDivision in Markov/runs/dispersion, NaN fits, short runs, unknown scenario colours, WINDOW_S ignored in power study, missing SEQ_SCENARIO, etc.). Default results did not change.
- Invalid configs stop with a clear `ValueError`: fewer than 2 scenarios, unknown `SEQ_SCENARIO`, a network with fewer than 3 losses.
- **Limitation 1:** the dispersion test compares with Poisson; counts of 50 Bernoulli packets are Binomial (variance slightly below the mean), so it is conservative (about 1% false rejections instead of 5%). It never over-claims burstiness.
- **Limitation 2:** runs and Markov tests use large-sample approximations; in very short captures their false-rejection rate is between about 1% and 9%. For 1-hour traces it is close to 5%.
- The Markov G² is verified equal to SciPy's G-test (log-likelihood χ²) on the 2×2 transition table.

---

## 8. What is pending

### 8.1 IEEE conference paper (DONE, 22 Oct)
Built from the data by `paper/build_paper.py` (LaTeX, IEEEtran, 8 pages) and `paper/make_docx.py` (Word, same content, IEEE-style two columns). Structure: Abstract, Index Terms, I Introduction, II Related Work, III Loss Model and Data, IV Methodology, V Results (6 tables, 5 figures), VI Discussion and Limitations, VII Conclusion and Future Work, Reproducibility. II is now "Background".
- 22 Oct (evening) revision, at the user's request: no names, emails or author block (header is just "BAMAT207 Probability and Statistics: Case Study Report"), no reference list or numbered citations (earlier work is mentioned by name and year in Background), language rewritten in a plainer, more natural student voice, 8 pages (limit is 10). Floats are pinned to their Results subsection with `placeins`. `AUTHORS` in `build_paper.py` is no longer used by the template.
- The only em dashes are IEEE's own "Abstract" and "Index Terms" labels (part of the template). The build stops if any other en or em dash appears.
- Template text lives in `paper/template.tex`; numbers are `<<keys>>` filled by `build_paper.py`. Never type a number into the template.

### 8.1b Final review deck (DONE, 22 Oct)
`node slides/build_deck.js Packet_Loss_Case_Study_Final.pptx --final` builds 21 slides: the 16 Review 1 slides (header now "Final Review") plus Progress since Review 1 (slide 2), Discussion, Limitations, Packet-Loss Lab web app (screenshots in `slides/assets/`), and an Appendix of abbreviations. Without `--final` the Review 1 deck is rebuilt unchanged (text checked identical to the presented copy).

### 8.2 Phase 2 (tools ready, 29 Oct; captures not yet taken)
`realworld/probe.py` (stdlib only, no root on macOS/Linux) sends 50 packets/s by ICMP to the router or a host, or by UDP to `realworld/echo_server.py`, and saves one CSV row per packet plus a JSON of settings. `realworld/analyze_captures.py` runs the Phase 1 fits, tests, Bayesian estimates and design effect on the captures and writes `realworld/results/summary.md` and four figures. Guide: `realworld/README.md`. Tested end to end with real packets over loopback (a bursty-drop echo server and an independent-drop one at the same ~1.2% rate were told apart correctly); `tests/test_realworld.py` adds 4 tests (41 total). Next: 10-minute captures on Wi-Fi, hotspot and wired from a team laptop. Loss is round-trip. Original Phase 2 plan, still open beyond the captures:
Real captures at 50 packets/s, ≥ 10 min per network; Baum-Welch estimation of Gilbert-Elliott parameters; 3-phase / HMM tail models; hierarchical Bayes across networks with Phase 1 posteriors as priors; peak vs off-peak loss rates.

### 8.3 Small optional items
- `Team_Prep_Guide.pdf` still shows Member A/B/C slide assignments (the user removed these from the deck).
- Streamlit prints "install Watchdog" on start; harmless (`pip install watchdog` silences it).

---

## 9. How the user likes to work (important for whoever continues)

- **Explain extremely simply.** The user is learning this topic from scratch. Use everyday analogies (ball game, "sneezing friend" for Good/Bad states, coin flips), short sections, plain words; define any term at first use. Long formula-heavy explanations and quizzes did not work. Slide-by-slide "what you see / what it means / what to say" worked well.
- They want things **done and pushed to GitHub**, with every change verified (tests run, slides rendered and checked).
- **Nothing hardcoded**: all numbers and labels derived from config or results.
- They prefer the final deliverable files sent directly (`.pptx`, `.pdf`).
- They do not want more handbook-style documents.

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: src` | Run commands from the repo root (where `run_case_study.py` is). |
| `streamlit: command not found` | Activate the venv first (`source .venv/bin/activate`). |
| App opens on 8502 | Another app holds 8501. Use the URL the terminal prints, or stop the other one. |
| `Cannot find module 'pptxgenjs'` | `cd slides && npm install`. |
| Python too old | Use Python 3.10+ (tested on 3.14.6). Streamlit needs a recent Python. |
| Deck numbers differ from this file | Rerun the chain in §4; with seed 2026 and default config they match exactly. |

### Versions on the original laptop (tested)
Python 3.14.6 · numpy 2.5.4 · scipy 1.18.1 · matplotlib 3.11.2 · streamlit 1.66.0 · pandas 3.0.6 · altair 6.3.0 · pytest 9.1.1 · Node 26.11.1 · pptxgenjs 3.12.0.

---

## 11. Prompt to paste into a new Claude session

> I'm continuing my BAMAT207 Probability and Statistics case study on a new device. Repo: https://github.com/AashmanBiyani08/Prob_Stats_Project. Read `HANDOFF.md` in the repo first; it has the full context, results, rules and pending work. Explain things to me very simply. Next task: [write the IEEE conference paper / other].
