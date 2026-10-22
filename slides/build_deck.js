// Builds the Review-1 deck from slides/deck_data.json.
// Every number on the slides is read from that file; run export_deck_data.py first.
//   python3 slides/export_deck_data.py
//   node slides/build_deck.js
const path = require("path");
const pptxgen = require("pptxgenjs");
const DATA = require(path.join(__dirname, "deck_data.json"));

const CFG = DATA.config, R = DATA.results, SR = DATA.series;
// "--final" builds the final-review deck: same slides plus discussion, limitations, the app and an appendix.
const ARGS = process.argv.slice(2);
const FINAL = ARGS.includes("--final");
const STAGE = FINAL ? "Final Review" : "Review 1";

// Team shown on the title slide: [name, registration number]
const TEAM = [
  ["Kyra Panwar", "25BBS0095"],
  ["Shashank Tiwari", "25BDS0053"],
  ["Aashman Biyani", "25BBS0100"],
];
const KEYS = DATA.keys;
const SCN = (k) => DATA.scenarios[k];
const RS = (k) => R.scenarios[k];

// short display names derived from the scenario labels in config.py
const SHORT = Object.fromEntries(KEYS.map((k) => [k, SCN(k).label.replace(/^Campus\s+/, "").split(" ")[0]]));
const NAMES = KEYS.map((k) => SHORT[k]);

// ---------- formatting ----------
const pc = (v, d = 2) => (v * 100).toFixed(d) + "%";
const num = (v, d = 0) => Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pval = (p) => (p < 1e-10 ? "< 10⁻¹⁰" : p < 0.001 ? p.toExponential(1) : p.toFixed(3));
const ksp = (t) => (t.p <= 1 / (t.B + 1) + 1e-12 ? "< " + (1 / t.B).toPrecision(1) : t.p.toFixed(2));
const range = (arr, f) => { const a = arr.map(f); return [Math.min(...a), Math.max(...a)]; };
const all = (f) => KEYS.every(f);
const listJoin = (a) => a.slice(0, -1).join(", ") + " and " + a[a.length - 1];
const minutes = (s) => (s % 3600 === 0 ? s / 3600 + (s === 3600 ? " hour" : " hours") : s % 60 === 0 ? s / 60 + (s === 60 ? " minute" : " minutes") : s + " s");
const minuteAdj = (s) => (s % 3600 === 0 ? s / 3600 + "-hour" : s % 60 === 0 ? s / 60 + "-minute" : s + "-second");

const N_NET = KEYS.length;
const PPW = CFG.packet_rate * CFG.window_s;
const N_WIN = CFG.duration_s / CFG.window_s;
const SEQ = R.sequential.scenario, SEQN = SHORT[SEQ];
const ALPHA = CFG.alpha;

// derived results used in several places
const allPoissonRejected = all((k) => RS(k).tests.dispersion.p < ALPHA && RS(k).tests.chisq_poisson.p < ALPHA);
const nbBetterAll = all((k) => RS(k).fits.aic_negbin < RS(k).fits.aic_poisson);
const indepRejectedAll = all((k) => RS(k).tests.runs.p < ALPHA && RS(k).tests.markov_lrt.p < ALPHA);
const [ampMin, ampMax] = range(KEYS, (k) => RS(k).bayes.markov.amp_q[1]);
const [covNMin, covNMax] = range(KEYS, (k) => R.coverage[k].naive);
const [covAMin, covAMax] = range(KEYS, (k) => R.coverage[k].adjusted);
const [fastMsMin, fastMsMax] = range(KEYS, (k) => 1000 / RS(k).fits.hyper_rate_fast);
const kwP = R.comparison.kruskal_p;
const maxPairP = Math.max(...R.comparison.pairwise.map((q) => q.p_bonf));
const highestRatioKey = KEYS.reduce((a, k) => (RS(k).descriptive.window_var / RS(k).descriptive.window_mean > RS(a).descriptive.window_var / RS(a).descriptive.window_mean ? k : a));
const longestBurstKey = KEYS.reduce((a, k) => (RS(k).descriptive.max_burst_len > RS(a).descriptive.max_burst_len ? k : a));
const maxWinKey = KEYS.reduce((a, k) => (SCN(k).max_losses_in_window > SCN(a).max_losses_in_window ? k : a));
const durs = R.power.durations_s;
const TESTS = ["dispersion", "runs", "markov_lrt"];
const firstAt = (arr, thr) => { const i = arr.findIndex((v) => v >= thr); return i < 0 ? null : durs[i]; };
const recIdx = durs.findIndex((_, i) => KEYS.every((k) => TESTS.every((t) => R.power[k][t][i] >= CFG.power_recommend)));
const recDur = recIdx < 0 ? durs[durs.length - 1] : durs[recIdx];
const recMinPower = Math.min(...KEYS.flatMap((k) => TESTS.map((t) => R.power[k][t][recIdx < 0 ? durs.length - 1 : recIdx])));
const mcSE = Math.sqrt(0.25 / CFG.power_reps);
const PT = CFG.power_target;   // power target from config.py

// ---------- deck ----------
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: "Cambria", bodyFontFace: "Calibri" };
pres.title = "Statistical Modelling of Packet-Loss Patterns";

const NAVY = "1F3A5F", BLUE = "2E6DB4", INK = "1B2430", MUTED = "4A5563", LINE = "C9D3DF";
const NETCOL = ["2A6F97", "E07A1F", "B23A48"];
const COL = Object.fromEntries(KEYS.map((k, i) => [k, NETCOL[i % NETCOL.length]]));
const GOOD = "2D6A4F", GREY = "8A96A3";
const T = { blue: "EAF1F8", green: "E6F2EA", peach: "FBEEDF", rose: "F8E6E9", sand: "F5EFD6" };
const TINT = [T.blue, T.peach, T.rose];
const S = pres.shapes;
let page = 0;

function base(title, presenter, notes) {
  const s = pres.addSlide();
  page++;
  s.background = { color: "FFFFFF" };
  if (presenter) {
    s.addShape(S.ROUNDED_RECTANGLE, { x: 0.4, y: 0.3, w: 1.9, h: 0.5, rectRadius: 0.25, fill: { color: "FFFFFF" }, line: { color: NAVY, width: 1.25 } });
    s.addText(presenter, { x: 0.4, y: 0.3, w: 1.9, h: 0.5, align: "center", valign: "middle", fontSize: 13, color: NAVY, isTextBox: true, margin: 0 });
  }
  s.addText(title, { x: 2.5, y: 0.2, w: 8.33, h: 0.75, align: "center", valign: "middle", fontFace: "Cambria", bold: true, fontSize: 28, color: INK, isTextBox: true, margin: 0 });
  s.addText([{ text: "BAMAT207", options: { breakLine: true } }, { text: STAGE }], { x: 11.2, y: 0.28, w: 1.73, h: 0.6, align: "right", valign: "middle", fontSize: 12, bold: true, color: NAVY, isTextBox: true, margin: 0 });
  s.addShape(S.RECTANGLE, { x: 0, y: 7.12, w: 13.333, h: 0.38, fill: { color: BLUE }, line: { color: BLUE } });
  s.addText("Statistical Modelling of Packet-Loss Patterns", { x: 0.4, y: 7.12, w: 8, h: 0.38, fontSize: 11, color: "FFFFFF", valign: "middle", isTextBox: true, margin: 0 });
  s.addText(String(page), { x: 12.3, y: 7.12, w: 0.63, h: 0.38, fontSize: 12, bold: true, color: "FFFFFF", align: "right", valign: "middle", isTextBox: true, margin: 0 });
  if (notes) s.addNotes(notes);
  return s;
}

function panel(s, x, y, w, h, title) {
  s.addShape(S.RECTANGLE, { x, y, w, h, fill: { color: "FFFFFF" }, line: { color: NAVY, width: 1 } });
  s.addShape(S.RECTANGLE, { x, y, w, h: 0.36, fill: { color: NAVY }, line: { color: NAVY } });
  s.addText(title.toUpperCase(), { x: x + 0.15, y, w: w - 0.3, h: 0.36, align: "center", valign: "middle", fontSize: 13, bold: true, color: "FFFFFF", isTextBox: true, margin: 0 });
}

function pill(s, x, y, w, h, label, desc, fill) {
  s.addShape(S.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: Math.min(0.2, h / 2), fill: { color: fill || "FFFFFF" }, line: { color: "3B4552", width: 0.75 } });
  const runs = [{ text: label, options: { bold: true, fontSize: 12, color: INK, breakLine: !!desc } }];
  if (desc) runs.push({ text: desc, options: { fontSize: 12, color: "333D49" } });
  s.addText(runs, { x: x + 0.12, y, w: w - 0.24, h, valign: "middle", isTextBox: true, margin: 2, paraSpaceAfter: 1 });
}

function stat(s, x, y, w, h, value, label, fill, color) {
  s.addShape(S.RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: "3B4552", width: 0.75 } });
  s.addText([{ text: value, options: { fontSize: 24, bold: true, color: color || INK, breakLine: true } }, { text: label, options: { fontSize: 11, color: MUTED } }],
    { x: x + 0.05, y, w: w - 0.1, h, align: "center", valign: "middle", isTextBox: true, margin: 2 });
}

function text(s, x, y, w, h, runs, o = {}) {
  s.addText(runs, Object.assign({ x, y, w, h, fontSize: 13, color: INK, valign: "top", isTextBox: true, margin: 0 }, o));
}

function bullets(s, x, y, w, h, items, o = {}) {
  const runs = [];
  items.forEach((it, i) => {
    const last = i === items.length - 1;
    if (Array.isArray(it)) {
      runs.push({ text: it[0], options: { bold: true, bullet: true } });
      runs.push({ text: " " + it[1], options: { breakLine: !last } });
    } else runs.push({ text: it, options: { bullet: true, breakLine: !last } });
  });
  s.addText(runs, Object.assign({ x, y, w, h, fontSize: 13, color: INK, valign: "top", isTextBox: true, margin: 2, paraSpaceAfter: 6 }, o));
}

function chartOpts(extra) {
  return Object.assign({
    catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "Calibri", valAxisLabelFontFace: "Calibri",
    valGridLine: { color: "E3E8EE", size: 0.75 }, catGridLine: { style: "none" },
    dataLabelFontSize: 10, dataLabelFontFace: "Calibri", dataLabelColor: INK,
    legendFontSize: 10, legendFontFace: "Calibri", legendColor: MUTED,
    showTitle: false, titleFontSize: 12, titleFontFace: "Calibri", titleColor: INK,
    catAxisTitleFontSize: 10, valAxisTitleFontSize: 10, catAxisTitleColor: MUTED, valAxisTitleColor: MUTED,
    catAxisTitleFontFace: "Calibri", valAxisTitleFontFace: "Calibri",
  }, extra);
}

function table(s, rows, o) {
  const left = o.leftCols || [];
  const head = rows[0].map((c) => ({ text: c, options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center", valign: "middle" } }));
  const body = rows.slice(1).map((r, i) => r.map((c, j) => ({ text: String(c), options: { fill: { color: i % 2 ? "F4F7FA" : "FFFFFF" }, align: j === 0 || left.includes(j) ? "left" : "center", valign: "middle", bold: j === 0 } })));
  const opts = Object.assign({ fontSize: 12, fontFace: "Calibri", color: INK, border: { type: "solid", pt: 0.75, color: LINE }, margin: 3 }, o);
  delete opts.leftCols;
  s.addTable([head, ...body], opts);
}

const arrowDown = (s, x, y, h) => s.addShape(S.LINE, { x, y, w: 0, h, line: { color: NAVY, width: 1.5, endArrowType: "triangle" } });

// =====================================================================
// 1. Title
{
  const tk = SR.title.scenario;
  const s = base("PROBABILITY AND STATISTICS CASE STUDY", null,
    `Introduce the team and the course. This is ${FINAL ? "the final review" : "Review 1"}. The results come from Phase 1, a simulation study with known parameters. Phase 2 will apply the same analysis to measured network traces.`);
  text(s, 0.6, 1.35, 6.6, 0.5, "TITLE PAGE", { fontFace: "Cambria", bold: true, fontSize: 24, align: "center" });
  bullets(s, 0.6, 1.95, 6.6, 2.45, [
    ["Course:", "BAMAT207 Probability and Statistics"],
    ["Project title:", "Statistical Modelling of Packet-Loss Patterns in Computer Networks"],
    ["Focus:", "Distribution fitting, tests of independence and Bayesian estimation"],
    ["Tracks:", "Track 3 (core), Track 1 and Track 5 (supporting)"],
    ["Stage:", FINAL ? "Final review (Phase 1 complete: simulation study)" : "Review 1 (Phase 1: simulation study)"],
  ], { fontSize: 15, paraSpaceAfter: 7 });
  text(s, 0.6, 4.45, 6.6, 0.3, "TEAM", { fontSize: 13, bold: true, color: NAVY });
  TEAM.forEach(([name, reg], i) => {
    const x = 0.6 + i * 2.27;
    s.addShape(S.ROUNDED_RECTANGLE, { x, y: 4.8, w: 2.05, h: 0.85, rectRadius: 0.12, fill: { color: "FFFFFF" }, line: { color: NAVY, width: 1 } });
    s.addText([{ text: name, options: { bold: true, fontSize: 14, color: INK, breakLine: true } }, { text: reg, options: { fontSize: 12, color: MUTED } }],
      { x, y: 4.8, w: 2.05, h: 0.85, align: "center", valign: "middle", isTextBox: true, margin: 2 });
  });
  stat(s, 0.6, 5.85, 2.05, 0.95, String(N_NET), "network conditions", T.blue, NETCOL[0]);
  stat(s, 2.87, 5.85, 2.05, 0.95, num(CFG.packets * N_NET), "packets analysed", T.peach, NETCOL[1]);
  stat(s, 5.14, 5.85, 2.05, 0.95, "6", "objectives", T.rose, NETCOL[2]);
  panel(s, 7.6, 1.35, 5.33, 5.4, "Sample trace");
  s.addChart(pres.charts.BAR, [{ name: "Losses per second", labels: SR.title.counts.map((_, i) => String(i + 1)), values: SR.title.counts }],
    chartOpts({ x: 7.7, y: 1.8, w: 5.13, h: 3.9, barDir: "col", barGapWidthPct: 20, chartColors: [COL[tk]], showLegend: false, showTitle: true,
      title: `${SCN(tk).label}: losses per second, first ${SR.title.seconds} s`, catAxisLabelFrequency: 20, catAxisTitle: "Time (s)", showCatAxisTitle: true,
      valAxisTitle: "Lost packets", showValAxisTitle: true }));
  text(s, 7.8, 5.8, 4.93, 0.85, "Each bar is one second of traffic. Several losses often fall in the same second.", { fontSize: 13, color: MUTED });
}

// =====================================================================
// Final only: progress since Review 1
if (FINAL) {
  const s = base("PROGRESS SINCE REVIEW 1", null,
    `At Review 1 we showed the analysis and first results. Since then we tested every module, built an interactive web app and wrote the IEEE paper. All numbers in this deck still come from the same pipeline with seed ${CFG.seed}.`);
  const col = (x, title, fill, items) => {
    panel(s, x, 1.1, 4.0, 4.0, title);
    bullets(s, x + 0.15, 1.6, 3.7, 3.4, items, { fontSize: 15, paraSpaceAfter: 10 });
  };
  col(0.4, "Shown at Review 1", "FFFFFF", [
    ["Problem:", "objectives and hypotheses."],
    ["Model:", "Good/Bad loss model and simulation design."],
    ["Results:", "distribution fits and independence tests."],
    ["Inference:", "Bayesian estimates and interval coverage."],
    ["Planning:", "power study for Phase 2."],
  ]);
  col(4.67, "Added since", "FFFFFF", [
    ["Testing:", "automated tests for edge cases, correctness and reproducibility."],
    ["Fixes:", "empty traces and zero-loss cases now handled safely."],
    ["Web app:", "Packet-Loss Lab, to explore the results live."],
    ["IEEE paper:", "six-page conference paper with all results."],
  ]);
  col(8.93, "Final deliverables", "FFFFFF", [
    ["Code:", "one Python pipeline, public on GitHub."],
    ["Results:", "7 figures, results.json and summary.md."],
    ["Paper:", "IEEE format, PDF and Word."],
    ["Slides:", "this deck, built from the same data."],
  ]);
  stat(s, 0.4, 5.35, 3.0, 1.5, num(CFG.packets * N_NET), "packets analysed", T.blue, NAVY);
  stat(s, 3.57, 5.35, 3.0, 1.5, num(CFG.power_reps), "simulated captures per Monte Carlo point", T.peach, NETCOL[1]);
  stat(s, 6.75, 5.35, 3.0, 1.5, String(CFG.seed), "seed: every number reproducible", T.green, GOOD);
  stat(s, 9.93, 5.35, 3.0, 1.5, "6 pages", "IEEE conference paper", T.rose, NETCOL[2]);
}

// =====================================================================
// 2. Introduction
{
  const c = SR.compare;
  const zeros = (a) => a.filter((v) => v === 0).length;
  const s = base("INTRODUCTION", null,
    `Basic loss models assume each packet is lost independently. Under that assumption the number of losses per second is Poisson and the time between losses is exponential. The two charts on the right have the same loss rate of ${pc(c.rate)}. The second one comes from our ${SEQN} scenario and shows grouped losses.`);
  text(s, 0.4, 1.1, 7.6, 0.8, "Basic loss models assume that each packet is lost independently. Under this assumption, loss counts are Poisson and gaps are exponential. Measured traffic often shows losses grouped close together.", { fontSize: 14 });
  text(s, 0.4, 2.0, 7.6, 0.3, "CONTEXT", { fontSize: 13, bold: true, color: NAVY });
  pill(s, 0.4, 2.33, 3.7, 0.95, "REAL-TIME MEDIA", "Several losses in a row are harder to conceal than isolated ones.", T.sand);
  pill(s, 4.3, 2.33, 3.7, 0.95, "PROTOCOL SETTINGS", "Retransmission and error-correction settings use loss statistics.", "FFFFFF");
  pill(s, 0.4, 3.43, 3.7, 0.95, "SERVICE LEVELS", "A reported loss rate is only useful if the model behind it holds.", T.rose);
  pill(s, 4.3, 3.43, 3.7, 0.95, "STATISTICAL INFERENCE", "Ignoring dependence makes standard errors too small.", T.green);
  panel(s, 0.4, 4.6, 7.6, 2.3, "Research questions");
  s.addText([
    { text: "1.  Do loss counts and gaps follow the Poisson model?", options: { breakLine: true } },
    { text: "2.  Which distributions describe them better?", options: { breakLine: true } },
    { text: "3.  How much does dependence affect interval estimates?" }],
    { x: 0.6, y: 5.1, w: 7.2, h: 1.7, fontSize: 15, color: INK, valign: "top", isTextBox: true, margin: 2, paraSpaceAfter: 12 });
  panel(s, 8.3, 1.1, 4.63, 5.8, "Independent and dependent losses");
  const lab = c.iid.map((_, i) => String(i + 1));
  const ymax = Math.max(...c.iid, ...c.bursty);
  const co = (title, col) => chartOpts({ barDir: "col", barGapWidthPct: 25, chartColors: [col], showLegend: false, showTitle: true, title, catAxisLabelFrequency: 10, valAxisMaxVal: Math.ceil(ymax / 2) * 2, valAxisMinVal: 0, valAxisMajorUnit: 2 });
  s.addChart(pres.charts.BAR, [{ name: "Independent", labels: lab, values: c.iid }], Object.assign(co(`Independent losses, first ${c.seconds} s`, GREY), { x: 8.4, y: 1.55, w: 4.43, h: 2.2 }));
  s.addChart(pres.charts.BAR, [{ name: SEQN, labels: lab, values: c.bursty }], Object.assign(co(`${SEQN} scenario, first ${c.seconds} s`, COL[c.scenario]), { x: 8.4, y: 3.8, w: 4.43, h: 2.2 }));
  const moreZeros = zeros(c.bursty) > zeros(c.iid), higherPeak = Math.max(...c.bursty) > Math.max(...c.iid);
  const cap = `Both series have a loss rate of ${pc(c.rate)}.` + (moreZeros && higherPeak ? ` The ${SEQN} series has more seconds with no loss and a few seconds with many.` : "");
  text(s, 8.5, 6.05, 4.23, 0.8, cap, { fontSize: 12, color: MUTED });
}

// =====================================================================
// 3. Objectives
{
  const s = base("OBJECTIVES AND HYPOTHESES", null,
    `Objectives one and two cover distribution modelling. Objectives three and four are hypothesis tests. Objective five is the Bayesian part. Objective six checks the tests and intervals by simulation. Each objective has a matching null and alternative hypothesis, tested at alpha equal to ${ALPHA}.`);
  panel(s, 0.4, 1.1, 6.6, 4.65, "Objectives");
  const obj = [
    ["O1  LOSS COUNTS", "Compare Poisson and Negative Binomial models for losses per second.", T.blue],
    ["O2  INTER-LOSS GAPS", "Fit exponential and two-phase hyperexponential models.", T.blue],
    ["O3  INDEPENDENCE", "Runs test and Markov chain likelihood ratio test.", T.peach],
    ["O4  NETWORK COMPARISON", `Compare the ${N_NET} networks with rank-based tests.`, T.peach],
    ["O5  BAYESIAN ESTIMATION", "Loss rates and burst parameters with credible intervals.", T.green],
    ["O6  RELIABILITY", "Power of the tests and coverage of the intervals.", T.green],
  ];
  obj.forEach((o, i) => pill(s, 0.6 + (i % 2) * 3.2, 1.65 + Math.floor(i / 2) * 1.35, 3.0, 1.15, o[0], o[1], o[2]));
  panel(s, 7.3, 1.1, 5.63, 4.65, "Hypotheses");
  table(s, [["", "Null hypothesis H0", "Alternative H1"],
    ["H1", "Losses per second are Poisson (random)", "Too spread out: losses cluster"],
    ["H2", "Gaps between losses are exponential", "Gaps are not exponential"],
    ["H3", "Each packet is lost independently", "A loss changes the next packet's chance: P(L|L) ≠ P(L|N)"],
    ["H4", "All networks behave the same", "At least one network differs"]],
    { x: 7.45, y: 1.65, w: 5.33, colW: [0.5, 2.45, 2.38], rowH: 0.7, fontSize: 12 });
  text(s, 7.45, 5.25, 5.33, 0.4, `All tests use a significance level of α = ${ALPHA}.`, { fontSize: 12, color: MUTED });
  text(s, 0.4, 5.95, 6, 0.3, "TRACK MAPPING", { fontSize: 13, bold: true, color: NAVY });
  pill(s, 0.4, 6.28, 4.0, 0.62, "Track 3 (core):", "O1 and O2, distribution modelling", T.blue);
  pill(s, 4.6, 6.28, 4.0, 0.62, "Track 5:", "O3, O4 and O6a, hypothesis testing", T.peach);
  pill(s, 8.8, 6.28, 4.13, 0.62, "Track 1:", "O5 and O6b, Bayesian inference", T.green);
}

// =====================================================================
// 4. Loss model and data
{
  const s = base("LOSS MODEL AND DATA", null,
    `The channel has two hidden states, Good and Bad. Before each packet it may change state with probability p or r. Losses are rare in Good and frequent in Bad. Since we set these parameters ourselves, the true loss rate of each network is known. Each network is simulated for ${CFG.duration_s} seconds at ${CFG.packet_rate} packets per second.`);
  panel(s, 0.4, 1.1, 5.6, 5.8, "Gilbert-Elliott two-state model");
  s.addShape(S.OVAL, { x: 0.85, y: 1.95, w: 1.8, h: 1.2, fill: { color: T.blue }, line: { color: NETCOL[0], width: 2 } });
  s.addShape(S.OVAL, { x: 3.75, y: 1.95, w: 1.8, h: 1.2, fill: { color: T.peach }, line: { color: NETCOL[1], width: 2 } });
  text(s, 0.85, 1.95, 1.8, 1.2, [{ text: "GOOD", options: { bold: true, fontSize: 16, breakLine: true } }, { text: "loss prob. hG", options: { fontSize: 12 } }], { align: "center", valign: "middle" });
  text(s, 3.75, 1.95, 1.8, 1.2, [{ text: "BAD", options: { bold: true, fontSize: 16, breakLine: true } }, { text: "loss prob. hB", options: { fontSize: 12 } }], { align: "center", valign: "middle" });
  s.addShape(S.LINE, { x: 2.7, y: 2.3, w: 1.0, h: 0, line: { color: INK, width: 1.75, endArrowType: "triangle" } });
  s.addShape(S.LINE, { x: 2.7, y: 2.8, w: 1.0, h: 0, line: { color: INK, width: 1.75, beginArrowType: "triangle" } });
  text(s, 2.6, 1.95, 1.2, 0.3, "p", { align: "center", fontSize: 14, bold: true });
  text(s, 2.6, 2.85, 1.2, 0.3, "r", { align: "center", fontSize: 14, bold: true });
  text(s, 0.6, 3.25, 2.3, 0.3, "stays with prob. 1 - p", { align: "center", fontSize: 11, color: MUTED });
  text(s, 3.5, 3.25, 2.3, 0.3, "stays with prob. 1 - r", { align: "center", fontSize: 11, color: MUTED });
  pill(s, 0.6, 3.75, 5.2, 0.7, "πB = p / (p + r)", "Share of time the network spends in the Bad state.", T.sand);
  pill(s, 0.6, 4.55, 5.2, 0.7, "P(loss) = (1 − πB) × hG + πB × hB", "Total loss = Good loss × Good time + Bad loss × Bad time.", T.sand);
  pill(s, 0.6, 5.35, 5.2, 0.7, "Average stay = 1/p in Good, 1/r in Bad", "If you leave with chance r per packet, you stay about 1/r packets.", T.sand);
  text(s, 0.6, 6.15, 5.2, 0.65, "The simulation draws complete sojourn times from the geometric distribution instead of updating the state for every packet.", { fontSize: 12, color: MUTED });

  panel(s, 6.3, 1.1, 6.63, 3.3, "Scenario parameters");
  const rows = [["Network", "p", "r", "hG", "hB", "πB", "True loss", "Mean Bad spell"]];
  KEYS.forEach((k) => { const q = SCN(k); rows.push([SHORT[k], q.p_gb, q.p_bg, q.h_g, q.h_b, pc(q.pi_b), pc(RS(k).true_long_run_loss_rate, 3), num(q.mean_bad_spell, 1) + " pkts"]); });
  table(s, rows, { x: 6.45, y: 1.6, w: 6.33, colW: [0.95, 0.7, 0.55, 0.65, 0.55, 0.75, 0.98, 1.2], rowH: 0.5, fontSize: 12 });
  text(s, 6.45, 3.75, 6.33, 0.55, "p and r are per-packet transition probabilities. hG and hB are the loss probabilities in each state.", { fontSize: 12, color: MUTED });

  text(s, 6.3, 4.6, 6.6, 0.3, "SAMPLING SETUP", { fontSize: 13, bold: true, color: NAVY });
  stat(s, 6.3, 4.95, 1.55, 1.0, CFG.packet_rate + "/s", `packets (${1000 / CFG.packet_rate} ms apart)`, T.blue, NAVY);
  stat(s, 7.99, 4.95, 1.55, 1.0, minutes(CFG.duration_s), "per network", T.blue, NAVY);
  stat(s, 9.68, 4.95, 1.55, 1.0, num(CFG.packets), "packets each", T.blue, NAVY);
  stat(s, 11.38, 4.95, 1.55, 1.0, String(CFG.seed), "random seed", T.blue, NAVY);
  pill(s, 6.3, 6.1, 3.2, 0.8, "PHASE 1 (COMPLETED)", "Simulation with known parameters.", T.green);
  pill(s, 9.73, 6.1, 3.2, 0.8, "PHASE 2 (PLANNED)", "Measured traces, same code.", T.rose);
}

// =====================================================================
// 5. Methodology
{
  const s = base("METHODOLOGY", null,
    `The analysis runs as one pipeline. The simulated traces are summarised first. Distribution fitting, hypothesis testing and Bayesian analysis then run on the same data. The Monte Carlo studies use ${CFG.power_reps} replicates each. The output is a set of figures and two results files.`);
  panel(s, 0.4, 1.1, 8.1, 5.8, "Analysis pipeline");
  const box = (x, y, w, h, t1, t2, fill) => {
    s.addShape(S.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: NAVY, width: 1 } });
    text(s, x, y, w, h, [{ text: t1, options: { bold: true, fontSize: 13, breakLine: true } }, { text: t2, options: { fontSize: 11, color: MUTED } }], { align: "center", valign: "middle" });
  };
  box(2.45, 1.65, 4.0, 0.7, "SIMULATION", `Gilbert-Elliott model, ${N_NET} networks, ${minutes(CFG.duration_s)} each`, T.blue);
  arrowDown(s, 4.45, 2.35, 0.3);
  box(2.45, 2.65, 4.0, 0.7, "PRE-PROCESSING", "Counts per second, gaps, burst lengths", T.blue);
  s.addShape(S.LINE, { x: 1.75, y: 3.55, w: 5.4, h: 0, line: { color: NAVY, width: 1.5 } });
  arrowDown(s, 4.45, 3.35, 0.2);
  [1.75, 4.45, 7.15].forEach((x) => arrowDown(s, x, 3.55, 0.3));
  box(0.6, 3.85, 2.3, 0.95, "DISTRIBUTION FITTING", "MLE, EM, AIC", T.green);
  box(3.3, 3.85, 2.3, 0.95, "HYPOTHESIS TESTING", "Fit, independence, comparison", T.peach);
  box(6.0, 3.85, 2.3, 0.95, "BAYESIAN ANALYSIS", "Beta posteriors, Markov", T.rose);
  [1.75, 4.45, 7.15].forEach((x) => s.addShape(S.LINE, { x, y: 4.8, w: 0, h: 0.2, line: { color: NAVY, width: 1.5 } }));
  s.addShape(S.LINE, { x: 1.75, y: 5.0, w: 5.4, h: 0, line: { color: NAVY, width: 1.5 } });
  arrowDown(s, 4.45, 5.0, 0.2);
  box(2.45, 5.2, 4.0, 0.7, "MONTE CARLO STUDIES", `Power and coverage, ${num(CFG.power_reps)} replicates`, T.sand);
  arrowDown(s, 4.45, 5.9, 0.25);
  box(2.45, 6.15, 4.0, 0.62, "OUTPUT", "Figures, results.json, summary.md", "FFFFFF");

  panel(s, 8.8, 1.1, 4.13, 3.0, "Reason for a simulation phase");
  bullets(s, 8.95, 1.6, 3.85, 2.45, [
    "The true parameters are known in advance.",
    "Estimates can be compared with the true values.",
    "The power study gives the capture length for Phase 2.",
    "Phase 2 uses the same code on measured data.",
  ], { fontSize: 13 });
  panel(s, 8.8, 4.3, 4.13, 2.6, "Software");
  ["Python 3", "NumPy", "SciPy", "Matplotlib"].forEach((t, i) => {
    const x = 8.98 + (i % 2) * 1.95, y = 4.8 + Math.floor(i / 2) * 0.55;
    s.addShape(S.ROUNDED_RECTANGLE, { x, y, w: 1.8, h: 0.42, rectRadius: 0.21, fill: { color: T.blue }, line: { color: NAVY, width: 0.75 } });
    text(s, x, y, 1.8, 0.42, t, { align: "center", valign: "middle", fontSize: 12, bold: true, color: NAVY });
  });
  text(s, 8.98, 5.95, 3.8, 0.85, "Each statistical component is a separate module with one owner.", { fontSize: 12, color: MUTED });
}

// =====================================================================
// 6. Statistical methods
{
  const s = base("STATISTICAL METHODS", null,
    `The table lists the method used for each objective. The Kolmogorov-Smirnov test uses a parametric bootstrap, because the rate is calculated from the sample being tested. The Markov test is a likelihood ratio test. By Wilks' theorem, G squared then follows a chi-square distribution with one degree of freedom.`);
  panel(s, 0.4, 1.1, 12.53, 5.0, "Methods by objective");
  table(s, [
    ["Obj.", "Method", "Formula", "What it does"],
    ["O1", "Chi-square goodness of fit", "χ² = Σ (O − E)² / E", "Checks if the model's prediction matches what really happened."],
    ["O1", "Index of dispersion", "D = s² / x̄", "Checks if losses are more spread out than random (clumping)."],
    ["O2", "Kolmogorov-Smirnov (bootstrap)", "D = max |Fn(t) − F(t)|", "Checks if the waiting times between losses are random."],
    ["O2", "EM algorithm", "guess → update → repeat", "Splits the waiting times into short (in a burst) and long ones."],
    ["O3", "Runs test", "z = (R − E[R]) / sd(R)", "Checks if lost packets stick together in clumps."],
    ["O3", "Markov likelihood ratio", "G² = 2 (ln L1 − ln L0)", "Checks if one loss makes the next loss more likely."],
    ["O4", "Kruskal-Wallis, Mann-Whitney", "p × number of pairs", "Checks if the networks are really different, not just by luck."],
    ["O5", "Bayesian update", "Beta(1 + k, 1 + n − k)", "Estimates the loss rate and how sure we are."],
    ["O6", "Monte Carlo", "SE = √(p(1 − p) / N)", `Repeats the experiment ${num(CFG.power_reps)} times to check our methods work.`],
  ], { x: 0.55, y: 1.6, w: 12.23, colW: [0.7, 3.2, 2.9, 5.43], rowH: 0.43, fontSize: 12, leftCols: [1, 2, 3] });
  pill(s, 0.4, 6.28, 4.0, 0.65, "AIC = 2k − 2 ln L", "Picks the better model: the lower score wins.", T.sand);
  pill(s, 4.6, 6.28, 4.0, 0.65, "Count window:", `${CFG.window_s} s = ${PPW} packets, ${num(N_WIN)} windows`, T.blue);
  pill(s, 8.8, 6.28, 4.13, 0.65, "Design-effect blocks:", `${CFG.block_s} s = ${CFG.block_s * CFG.packet_rate} packets`, T.green);
}

// =====================================================================
// 7. Descriptive statistics
{
  const ratio = (k) => RS(k).descriptive.window_var / RS(k).descriptive.window_mean;
  const above = all((k) => ratio(k) > 1);
  const s = base("DESCRIPTIVE STATISTICS", null,
    `These summaries are computed before any model is fitted. For a Poisson process the variance of the counts equals the mean. The variance-to-mean ratio is ${listJoin(KEYS.map((k) => ratio(k).toFixed(2)))} for ${listJoin(NAMES)}. The right-hand chart shows the share of losses that belong to a burst of two or more packets.`);
  panel(s, 0.4, 1.1, 7.5, 3.0, `${minutes(CFG.duration_s)} per network, ${num(CFG.packets)} packets each`);
  const rows = [["Network", "Loss rate", "Mean / s", "Variance", "Var ÷ mean", "Mean burst", "Max burst"]];
  KEYS.forEach((k) => { const d = RS(k).descriptive; rows.push([SHORT[k], pc(d.loss_rate), d.window_mean.toFixed(3), d.window_var.toFixed(3), ratio(k).toFixed(2), d.mean_burst_len.toFixed(2), d.max_burst_len]); });
  table(s, rows, { x: 0.55, y: 1.6, w: 7.2, colW: [1.1, 1.0, 1.0, 1.0, 1.1, 1.0, 1.0], rowH: 0.5, fontSize: 12 });
  text(s, 0.55, 3.65, 7.2, 0.4, "A burst is a run of consecutive lost packets.", { fontSize: 12, color: MUTED });
  text(s, 0.4, 4.3, 7.5, 0.3, "KEY FIGURES", { fontSize: 13, bold: true, color: NAVY });
  stat(s, 0.4, 4.65, 2.35, 1.3, ratio(highestRatioKey).toFixed(2), `highest var ÷ mean (${SHORT[highestRatioKey]})`, T.rose, COL[highestRatioKey]);
  stat(s, 2.98, 4.65, 2.35, 1.3, String(RS(longestBurstKey).descriptive.max_burst_len), `longest burst, packets (${SHORT[longestBurstKey]})`, T.peach, COL[longestBurstKey]);
  stat(s, 5.55, 4.65, 2.35, 1.3, String(SCN(maxWinKey).max_losses_in_window), `most losses in one second (${SHORT[maxWinKey]})`, T.blue, COL[maxWinKey]);
  text(s, 0.4, 6.15, 7.5, 0.75, "For a Poisson process the variance-to-mean ratio would be close to 1." + (above ? ` All ${N_NET} networks are above this value.` : ""), { fontSize: 14 });

  panel(s, 8.2, 1.1, 4.73, 2.85, "Variance-to-mean ratio");
  const rmax = Math.ceil(Math.max(...KEYS.map(ratio)) * 1.2);
  s.addChart([{ type: pres.charts.BAR, data: [{ name: "Observed", labels: NAMES, values: KEYS.map((k) => +ratio(k).toFixed(2)) }], options: { barDir: "col", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", barGapWidthPct: 60 } },
    { type: pres.charts.LINE, data: [{ name: "Poisson value (1.0)", labels: NAMES, values: KEYS.map(() => 1) }], options: { chartColors: [NETCOL[1]], lineDataSymbol: "none", lineSize: 2 } }],
    chartOpts({ x: 8.3, y: 1.5, w: 4.53, h: 2.4, showLegend: true, legendPos: "b", valAxisMaxVal: rmax, valAxisMinVal: 0 }));
  panel(s, 8.2, 4.1, 4.73, 2.8, "Share of losses inside bursts");
  s.addChart(pres.charts.BAR, [{ name: "In bursts", labels: NAMES, values: KEYS.map((k) => +(RS(k).descriptive.share_losses_in_bursts * 100).toFixed(1)) }],
    chartOpts({ x: 8.3, y: 4.5, w: 4.53, h: 2.35, barDir: "bar", chartColors: KEYS.map((k) => COL[k]), showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"', showLegend: false, valAxisMaxVal: 100, valAxisMinVal: 0, barGapWidthPct: 50 }));
}

// =====================================================================
// 8. Loss counts
{
  const P = SR.pmf, hk = CFG.heavy_k;
  const hs = (k) => SCN(k).heavy_seconds;
  const maxDispP = Math.max(...KEYS.map((k) => RS(k).tests.dispersion.p));
  const s = base("DISTRIBUTION OF LOSS COUNTS", null,
    `The left chart uses a logarithmic scale. The Poisson curve drops quickly after a few losses, while the observed frequencies decline slowly. The Negative Binomial curve stays close to the data. For ${SEQN}, the Poisson model expects ${num(hs(SEQ).poisson, 0)} seconds with ${hk} or more losses. The trace contains ${hs(SEQ).observed}.`);
  panel(s, 0.4, 1.1, 6.4, 4.75, `${SEQN}: probability of k losses in one second`);
  const floor = (a) => a.map((v) => Math.max(v, 1e-6));
  s.addChart(pres.charts.LINE, [
    { name: "Observed", labels: P.k.map(String), values: floor(P.observed) },
    { name: "Poisson fit", labels: P.k.map(String), values: floor(P.poisson) },
    { name: "Negative Binomial fit", labels: P.k.map(String), values: floor(P.negbin) }],
    chartOpts({ x: 0.5, y: 1.5, w: 6.2, h: 3.95, chartColors: [COL[SEQ], GREY, GOOD], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6,
      valAxisLogScaleBase: 10, valAxisMinVal: 0.000001, valAxisMaxVal: 1, valAxisLabelFormatCode: "0.E+00", showLegend: true, legendPos: "b",
      catAxisTitle: "Losses in a 1-second window (k)", showCatAxisTitle: true, valAxisTitle: "Probability (log scale)", showValAxisTitle: true }));
  text(s, 0.55, 5.45, 6.1, 0.35, "Values below 10⁻⁶ are plotted at the axis minimum.", { fontSize: 11, color: MUTED });
  panel(s, 7.1, 1.1, 5.83, 2.75, `Seconds with ${hk} or more losses (of ${num(N_WIN)})`);
  const hmax = Math.ceil(Math.max(...KEYS.map((k) => Math.max(hs(k).observed, hs(k).negbin))) / 100 + 1) * 100;
  s.addChart(pres.charts.BAR, [
    { name: "Observed", labels: NAMES, values: KEYS.map((k) => hs(k).observed) },
    { name: "Poisson expected", labels: NAMES, values: KEYS.map((k) => +hs(k).poisson.toFixed(1)) },
    { name: "Neg. Binomial expected", labels: NAMES, values: KEYS.map((k) => +hs(k).negbin.toFixed(1)) }],
    chartOpts({ x: 7.2, y: 1.5, w: 5.63, h: 2.3, barDir: "col", chartColors: [NETCOL[1], GREY, GOOD], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0", dataLabelFontSize: 9, showLegend: true, legendPos: "b", valAxisMaxVal: hmax, barGapWidthPct: 40 }));
  panel(s, 7.1, 4.0, 5.83, 1.85, "Goodness of fit");
  const rows = [["Network", "Dispersion D", "χ² Poisson", "AIC Poisson", "AIC Neg. Bin."]];
  KEYS.forEach((k) => { const t = RS(k).tests, f = RS(k).fits; rows.push([SHORT[k], t.dispersion.D.toFixed(2), t.chisq_poisson.stat.toFixed(1), num(f.aic_poisson), num(f.aic_negbin)]); });
  table(s, rows, { x: 7.2, y: 4.42, w: 5.63, colW: [1.03, 1.15, 1.1, 1.15, 1.2], rowH: 0.34, fontSize: 11 });
  const head = allPoissonRejected ? `RESULT: POISSON MODEL REJECTED FOR ALL ${N_NET} NETWORKS (DISPERSION TEST p ${pval(maxDispP)})` : "RESULT: POISSON MODEL NOT REJECTED FOR EVERY NETWORK";
  pill(s, 0.4, 6.0, 12.53, 0.92, head,
    "The Negative Binomial is a Poisson distribution whose rate follows a Gamma distribution. This lets the variance exceed the mean." + (nbBetterAll ? " Its AIC is lower for every network." : ""), T.green);
}

// =====================================================================
// 9. Inter-loss gaps
{
  const Sv = SR.survival;
  const slow = KEYS.map((k) => `${(1 / RS(k).fits.hyper_rate_slow).toFixed(1)} s (${SHORT[k]})`);
  const s = base("DISTRIBUTION OF INTER-LOSS GAPS", null,
    `Gaps between losses are exponential only when losses form a Poisson process. On a log scale the exponential survival curve is a straight line, and the observed curve departs from it. The two-phase mixture fitted with the EM algorithm matches it closely. The fast phase corresponds to gaps inside a burst and the slow phase to gaps between bursts.`);
  panel(s, 0.4, 1.1, 6.4, 4.75, `${SEQN}: probability that a gap exceeds t`);
  s.addChart(pres.charts.LINE, [
    { name: "Observed", labels: Sv.t.map(String), values: Sv.observed.map((v) => Math.max(v, 0.001)) },
    { name: "Exponential fit", labels: Sv.t.map(String), values: Sv.exponential.map((v) => Math.max(v, 0.001)) },
    { name: "Two-phase fit", labels: Sv.t.map(String), values: Sv.hyperexp.map((v) => Math.max(v, 0.001)) }],
    chartOpts({ x: 0.5, y: 1.55, w: 6.2, h: 4.2, chartColors: [COL[SEQ], GREY, GOOD], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 6,
      valAxisLogScaleBase: 10, valAxisMinVal: 0.001, valAxisMaxVal: 1, showLegend: true, legendPos: "b",
      catAxisTitle: "t (seconds)", showCatAxisTitle: true, valAxisTitle: "P(gap > t), log scale", showValAxisTitle: true }));
  panel(s, 7.1, 1.1, 5.83, 2.55, "Two-phase hyperexponential fit (EM)");
  const rows = [["Network", "Fast share", "Fast mean", "Slow mean", "KS exp. p", "KS mix. p"]];
  KEYS.forEach((k) => { const f = RS(k).fits, t = RS(k).tests; rows.push([SHORT[k], (f.hyper_w_fast * 100).toFixed(0) + "%", (1000 / f.hyper_rate_fast).toFixed(0) + " ms", (1 / f.hyper_rate_slow).toFixed(1) + " s", ksp(t.ks_exponential), ksp(t.ks_hyperexp)]); });
  table(s, rows, { x: 7.2, y: 1.55, w: 5.63, colW: [0.98, 0.95, 0.9, 0.9, 0.95, 0.95], rowH: 0.45, fontSize: 11 });
  panel(s, 7.1, 3.8, 5.83, 2.05, "Reduction in AIC with the two-phase model");
  const drops = KEYS.map((k) => Math.round(RS(k).fits.aic_exp - RS(k).fits.aic_hyper));
  s.addChart(pres.charts.BAR, [{ name: "AIC reduction", labels: NAMES, values: drops }],
    chartOpts({ x: 7.2, y: 4.18, w: 5.63, h: 1.62, barDir: "bar", chartColors: KEYS.map((k) => COL[k]), showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", showLegend: false, valAxisMaxVal: Math.ceil(Math.max(...drops) / 5000 + 1) * 5000, barGapWidthPct: 45 }));
  pill(s, 0.4, 6.0, 6.15, 0.92, "FAST PHASE: GAPS INSIDE A BURST", `Mean gap between ${fastMsMin.toFixed(0)} and ${fastMsMax.toFixed(0)} ms, about one or two packet intervals.`, T.peach);
  pill(s, 6.78, 6.0, 6.15, 0.92, "SLOW PHASE: GAPS BETWEEN BURSTS", "Mean gap " + slow.join(", ") + ".", T.blue);
}

// =====================================================================
// 10. Independence
{
  const s = base("TESTS OF INDEPENDENCE", null,
    `If losses were independent, the chance of a loss would not depend on the previous packet. For ${SEQN}, it is ${pc(RS(SEQ).tests.markov_lrt.p_L_given_N)} after a delivered packet and ${pc(RS(SEQ).tests.markov_lrt.p_L_given_L, 1)} after a lost one. The runs test agrees: there are fewer runs than independence predicts, which means losses are grouped.`);
  panel(s, 0.4, 1.1, 6.2, 3.65, "Loss probability given the previous packet");
  const lmax = Math.ceil(Math.max(...KEYS.map((k) => RS(k).tests.markov_lrt.p_L_given_L * 100)) / 10 + 1) * 10;
  s.addChart(pres.charts.BAR, [
    { name: "Previous delivered: P(L|N)", labels: NAMES, values: KEYS.map((k) => +(RS(k).tests.markov_lrt.p_L_given_N * 100).toFixed(2)) },
    { name: "Previous lost: P(L|L)", labels: NAMES, values: KEYS.map((k) => +(RS(k).tests.markov_lrt.p_L_given_L * 100).toFixed(1)) }],
    chartOpts({ x: 0.5, y: 1.5, w: 6.0, h: 3.2, barDir: "col", chartColors: [GREY, NETCOL[2]], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0#"%"', showLegend: true, legendPos: "b", valAxisMaxVal: lmax, valAxisLabelFormatCode: '0"%"', barGapWidthPct: 50 }));
  panel(s, 6.9, 1.1, 6.03, 3.65, "Number of runs: expected and observed");
  const rmax = Math.ceil(Math.max(...KEYS.map((k) => RS(k).tests.runs.expected)) / 2000 + 1) * 2000;
  s.addChart(pres.charts.BAR, [
    { name: "Expected under independence", labels: NAMES, values: KEYS.map((k) => Math.round(RS(k).tests.runs.expected)) },
    { name: "Observed", labels: NAMES, values: KEYS.map((k) => RS(k).tests.runs.runs) }],
    chartOpts({ x: 7.0, y: 1.5, w: 5.83, h: 3.2, barDir: "col", chartColors: [GREY, NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", showLegend: true, legendPos: "b", valAxisMaxVal: rmax, barGapWidthPct: 50 }));
  panel(s, 0.4, 4.9, 7.9, 2.0, "Test results");
  const rows = [["Network", "Runs z", "Markov G²", "p-value", "Ratio b/a", "Mean burst"]];
  KEYS.forEach((k) => { const t = RS(k).tests, m = RS(k).bayes.markov; rows.push([SHORT[k], t.runs.z.toFixed(1), t.markov_lrt.G2.toFixed(1), pval(Math.max(t.runs.p, t.markov_lrt.p)), m.amp_q[1].toFixed(0) + "×", m.burst_len_q[1].toFixed(2) + " pkts"]); });
  table(s, rows, { x: 0.55, y: 5.3, w: 7.6, colW: [1.2, 1.1, 1.3, 1.2, 1.5, 1.3], rowH: 0.38, fontSize: 12 });
  stat(s, 8.6, 4.9, 4.33, 2.0, `${ampMin.toFixed(0)}× to ${ampMax.toFixed(0)}×`,
    "Increase in loss probability after a loss (posterior median of b/a)." + (indepRejectedAll ? " H3 is rejected for every network." : ""), T.rose, NETCOL[2]);
}

// =====================================================================
// 11. Bayesian estimation
{
  const seq = R.sequential.steps, first = seq[0], last = seq[seq.length - 1];
  const ord = R.ordering;
  const s = base("BAYESIAN ESTIMATION", null,
    `We use a uniform Beta(1, 1) prior. With a binomial likelihood the posterior is also a Beta distribution. The chart shows the ${SEQN} posterior as more traffic is observed. After ${first.t} seconds the interval is wide; after ${last.t} seconds it is narrow. The posterior probability that the networks are ordered ${listJoin(NAMES)} by loss rate is ${ord.all_ordered.toFixed(3)}.`);
  panel(s, 0.4, 1.1, 6.4, 4.4, `${SEQN}: posterior after more traffic`);
  const lab = seq.map((q) => q.t + " s");
  const ymax = Math.ceil(Math.max(...seq.map((q) => q.ci_high * 100)));
  s.addChart(pres.charts.LINE, [
    { name: "Upper 95%", labels: lab, values: seq.map((q) => +(q.ci_high * 100).toFixed(2)) },
    { name: "Posterior mean", labels: lab, values: seq.map((q) => +(q.mean * 100).toFixed(2)) },
    { name: "Lower 95%", labels: lab, values: seq.map((q) => +(q.ci_low * 100).toFixed(2)) }],
    chartOpts({ x: 0.5, y: 1.5, w: 6.2, h: 3.45, chartColors: [GREY, COL[SEQ], GREY], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 7,
      showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: ymax, valAxisLabelFormatCode: '0"%"', catAxisTitle: "Traffic observed", showCatAxisTitle: true }));
  text(s, 0.55, 4.98, 6.1, 0.45, `After ${first.t} s: ${pc(first.mean)} [${pc(first.ci_low)}, ${pc(first.ci_high)}]. After ${last.t} s: ${pc(last.mean)} [${pc(last.ci_low)}, ${pc(last.ci_high)}].`, { fontSize: 12, bold: true, color: NAVY });
  panel(s, 7.1, 1.1, 5.83, 2.45, "Posterior loss rate, full trace");
  const rows = [["Network", "Posterior mean", "95% credible interval"]];
  KEYS.forEach((k) => { const p = RS(k).bayes.posterior; rows.push([SHORT[k], pc(p.mean, 3), `[${pc(p.ci_low, 3)}, ${pc(p.ci_high, 3)}]`]); });
  table(s, rows, { x: 7.25, y: 1.55, w: 5.53, colW: [1.3, 1.7, 2.53], rowH: 0.45, fontSize: 12 });
  panel(s, 7.1, 3.7, 5.83, 1.8, "Comparing the networks (H4)");
  bullets(s, 7.25, 4.15, 5.55, 1.3, [
    ["Kruskal-Wallis:", `H = ${R.comparison.kruskal_H.toFixed(1)}, p ${pval(kwP)}`],
    ["Chi-square homogeneity:", `${R.comparison.chi2_homog.toFixed(1)} on ${R.comparison.chi2_df} df`],
    ["Mann-Whitney pairs:", `largest Bonferroni p ${pval(maxPairP)}`],
  ], { fontSize: 14, paraSpaceAfter: 4 });
  pill(s, 0.4, 5.7, 4.05, 1.2, "Beta(1, 1) → Beta(1 + k, 1 + n − k)", "Start knowing nothing. Add the k losses and n − k deliveries you saw.", T.sand);
  pill(s, 4.62, 5.7, 4.05, 1.2, "ORDERING", `P(${NAMES.join(" < ")}) = ${ord.all_ordered.toFixed(3)} from ${num(CFG.ordering_draws)} posterior draws.`, T.green);
  pill(s, 8.85, 5.7, 4.08, 1.2, "MEAN BURST LENGTH", "Posterior medians of " + listJoin(KEYS.map((k) => RS(k).bayes.markov.burst_len_q[1].toFixed(2))) + " packets.", T.blue);
}

// =====================================================================
// 12. Predictive check and design effect
{
  const hk = CFG.heavy_k;
  const tail = (k) => RS(k).bayes.predictive_tail;
  const ratio = (k) => tail(k).observed / tail(k).predicted;
  const fmtRatio = (v) => (v >= 100 ? num(Math.round(v / 100) * 100) : v >= 10 ? num(v) : v.toFixed(1)) + "×";
  const deff = (k) => RS(k).bayes.adjusted_posterior.deff;
  const s = base("PREDICTIVE CHECK AND DESIGN EFFECT", null,
    `The posterior predictive check asks how often the independent model expects ${hk} or more losses in one second. For ${SEQN} it predicts a probability of ${tail(SEQ).predicted.toExponential(1)}. The observed frequency is ${pc(tail(SEQ).observed, 1)}. The reason is positive correlation between nearby packets, which adds covariance terms to the variance of the total.`);
  panel(s, 0.4, 1.1, 6.4, 3.9, `P(${hk} or more losses in one second)`);
  s.addChart(pres.charts.BAR, [
    { name: "Predicted by independent model", labels: NAMES, values: KEYS.map((k) => tail(k).predicted) },
    { name: "Observed", labels: NAMES, values: KEYS.map((k) => tail(k).observed) }],
    chartOpts({ x: 0.5, y: 1.5, w: 6.2, h: 3.45, barDir: "col", chartColors: [GREY, NETCOL[1]], showLegend: true, legendPos: "b",
      valAxisLogScaleBase: 10, valAxisMinVal: 0.0000001, valAxisMaxVal: 1, valAxisLabelFormatCode: "0.E+00", valAxisTitle: "Probability (log scale)", showValAxisTitle: true, barGapWidthPct: 50 }));
  KEYS.forEach((k, i) => stat(s, 0.4 + i * 2.2, 5.15, 2.0, 1.1, fmtRatio(ratio(k)), SHORT[k], TINT[i % 3], COL[k]));
  text(s, 0.4, 6.35, 6.4, 0.6, "Observed frequency divided by the frequency predicted under independence.", { fontSize: 12, color: MUTED });

  panel(s, 7.1, 1.1, 5.83, 3.0, `Design effect (${CFG.block_s}-second blocks)`);
  s.addChart(pres.charts.BAR, [{ name: "Design effect", labels: NAMES, values: KEYS.map((k) => +deff(k).toFixed(2)) }],
    chartOpts({ x: 7.2, y: 1.5, w: 5.63, h: 2.55, barDir: "col", chartColors: KEYS.map((k) => COL[k]), showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", showLegend: false, valAxisMinVal: 0, valAxisMaxVal: Math.ceil(Math.max(...KEYS.map(deff)) / 2 + 1) * 2, barGapWidthPct: 60 }));
  panel(s, 7.1, 4.25, 5.83, 2.65, "Effect of positive correlation");
  text(s, 7.3, 4.62, 5.45, 0.4, "Var(ΣXᵢ) = ΣVar(Xᵢ) + 2ΣCov(Xᵢ, Xⱼ)", { fontSize: 15, bold: true, align: "center", color: NAVY });
  text(s, 7.3, 5.0, 5.45, 0.3, "Total spread = each packet's own spread + extra spread from packets moving together", { fontSize: 11, italic: true, align: "center", color: MUTED });
  const neff = Math.round(CFG.packets / deff(SEQ) / 1000) * 1000;
  bullets(s, 7.3, 5.38, 5.45, 1.5, [
    "Inside a burst, neighbouring packets are positively correlated.",
    "Design effect = real spread ÷ spread if losses were random.",
    `Effective sample size n ÷ deff: for ${SEQN}, ${num(CFG.packets)} packets count as about ${num(neff)}.`,
  ], { fontSize: 12, paraSpaceAfter: 4 });
}

// =====================================================================
// 13. Coverage
{
  const tr = RS(SEQ).true_long_run_loss_rate, pn = RS(SEQ).bayes.posterior, pa = RS(SEQ).bayes.adjusted_posterior;
  const inN = pn.ci_low <= tr && tr <= pn.ci_high, inA = pa.ci_low <= tr && tr <= pa.ci_high;
  const s = base("COVERAGE OF 95% INTERVALS", null,
    `We simulated ${num(CFG.coverage_reps)} captures of ${minutes(CFG.coverage_duration_s)} per network and recorded how often each interval contained the true loss rate. A 95% interval should do so about 95% of the time. Naive coverage ranged from ${pc(covNMin, 1)} to ${pc(covNMax, 1)}. After dividing by the design effect it ranged from ${pc(covAMin, 1)} to ${pc(covAMax, 1)}.`);
  panel(s, 0.4, 1.1, 7.2, 5.8, `Coverage in ${num(CFG.coverage_reps)} simulated ${minuteAdj(CFG.coverage_duration_s)} captures`);
  s.addChart([
    { type: pres.charts.BAR, data: [
      { name: "Naive interval", labels: NAMES, values: KEYS.map((k) => +(R.coverage[k].naive * 100).toFixed(1)) },
      { name: "Design-effect adjusted", labels: NAMES, values: KEYS.map((k) => +(R.coverage[k].adjusted * 100).toFixed(1)) }],
      options: { barDir: "col", chartColors: [GREY, GOOD], showValue: true, dataLabelPosition: "inEnd", dataLabelColor: "FFFFFF", dataLabelFontSize: 12, dataLabelFormatCode: '0.0"%"', barGapWidthPct: 50 } },
    { type: pres.charts.LINE, data: [{ name: "Nominal 95%", labels: NAMES, values: KEYS.map(() => 95) }], options: { chartColors: [NETCOL[2]], lineDataSymbol: "none", lineSize: 2 } }],
    chartOpts({ x: 0.5, y: 1.55, w: 7.0, h: 5.25, showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: 100, valAxisLabelFormatCode: '0"%"' }));

  panel(s, 7.9, 1.1, 5.03, 3.1, `Example: ${SEQN}, full trace`);
  const vals = [tr, pn.ci_low, pn.ci_high, pa.ci_low, pa.ci_high].map((v) => v * 100);
  const lo = Math.floor(Math.min(...vals) * 20) / 20, hi = Math.ceil(Math.max(...vals) * 20) / 20;
  const x0 = 8.2, x1 = 12.6, px = (v) => x0 + ((v * 100 - lo) / (hi - lo)) * (x1 - x0);
  s.addShape(S.LINE, { x: x0, y: 3.35, w: x1 - x0, h: 0, line: { color: GREY, width: 1 } });
  const ticks = 4;
  for (let i = 0; i < ticks; i++) { const v = lo + (i * (hi - lo)) / (ticks - 1); text(s, x0 + (i * (x1 - x0)) / (ticks - 1) - 0.4, 3.42, 0.8, 0.25, v.toFixed(2) + "%", { fontSize: 10, color: MUTED, align: "center" }); }
  s.addShape(S.RECTANGLE, { x: px(pn.ci_low), y: 2.0, w: px(pn.ci_high) - px(pn.ci_low), h: 0.3, fill: { color: GREY }, line: { color: GREY } });
  text(s, x0, 1.62, 4.4, 0.3, `Naive: [${pc(pn.ci_low, 3)}, ${pc(pn.ci_high, 3)}], ${inN ? "contains" : "misses"} the true rate`, { fontSize: 12, bold: true, color: MUTED });
  s.addShape(S.RECTANGLE, { x: px(pa.ci_low), y: 2.78, w: px(pa.ci_high) - px(pa.ci_low), h: 0.3, fill: { color: GOOD }, line: { color: GOOD } });
  text(s, x0, 2.4, 4.4, 0.3, `Adjusted: [${pc(pa.ci_low, 3)}, ${pc(pa.ci_high, 3)}], ${inA ? "contains" : "misses"} the true rate`, { fontSize: 12, bold: true, color: GOOD });
  s.addShape(S.LINE, { x: px(tr), y: 1.95, w: 0, h: 1.4, line: { color: NETCOL[2], width: 2.25, dashType: "dash" } });
  text(s, x0, 3.72, 4.4, 0.3, `Dashed line: true long-run rate ${pc(tr, 3)}`, { fontSize: 12, color: NETCOL[2], bold: true });

  panel(s, 7.9, 4.35, 5.03, 2.55, "Average interval width");
  table(s, [["Network", "Naive", "Adjusted"], ...KEYS.map((k) => [SHORT[k], (R.coverage[k].width_naive * 100).toFixed(3) + " pp", (R.coverage[k].width_adjusted * 100).toFixed(3) + " pp"])],
    { x: 8.05, y: 4.82, w: 4.73, colW: [1.6, 1.55, 1.58], rowH: 0.38, fontSize: 12 });
  text(s, 8.05, 6.4, 4.73, 0.45, "pp = percentage points.", { fontSize: 12, color: MUTED });
}

// =====================================================================
// 14. Power
{
  const runsBest = KEYS.filter((k) => firstAt(R.power[k].runs, PT) <= Math.min(...TESTS.map((t) => firstAt(R.power[k][t], PT) ?? Infinity))).length;
  const s = base("POWER ANALYSIS", null,
    `Power is the probability of rejecting independence when the losses really are dependent. For each capture length we simulated ${num(CFG.power_reps)} captures and counted how often each test rejected. The table shows the shortest tested length with power of at least ${PT.toFixed(2)}. Based on this, Phase 2 should record at least ${minutes(recDur)} per network.`);
  panel(s, 0.4, 1.1, 7.2, 5.8, "Power of the runs test by capture length");
  const D = durs.map((d) => d + " s");
  s.addChart(pres.charts.LINE, [
    ...KEYS.map((k) => ({ name: SHORT[k], labels: D, values: R.power[k].runs })),
    { name: `${PT.toFixed(2)} level`, labels: D, values: D.map(() => PT) }],
    chartOpts({ x: 0.5, y: 1.55, w: 7.0, h: 5.25, chartColors: [...KEYS.map((k) => COL[k]), GREY], lineSize: 2.25, lineDataSymbol: "circle", lineDataSymbolSize: 7,
      showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: 1, valAxisLabelFormatCode: "0%", catAxisTitle: "Capture length", showCatAxisTitle: true, valAxisTitle: "Power", showValAxisTitle: true }));
  panel(s, 7.9, 1.1, 5.03, 3.05, `Shortest capture with power ≥ ${PT.toFixed(2)}`);
  const cell = (arr) => { const d = firstAt(arr, PT); return d === null ? "> " + durs[durs.length - 1] + " s" : d + " s"; };
  table(s, [["Network", "Dispersion", "Runs", "Markov"], ...KEYS.map((k) => [SHORT[k], cell(R.power[k].dispersion), cell(R.power[k].runs), cell(R.power[k].markov_lrt)])],
    { x: 8.05, y: 1.6, w: 4.73, colW: [1.3, 1.2, 1.0, 1.23], rowH: 0.45, fontSize: 12 });
  text(s, 8.05, 3.55, 4.73, 0.5, (runsBest === N_NET ? "The runs test needs the shortest capture for every network." : `The runs test needs the shortest capture for ${runsBest} of ${N_NET} networks.`), { fontSize: 12, color: MUTED });
  stat(s, 7.9, 4.35, 2.4, 1.2, num(CFG.power_reps), "replicates per point", T.blue, NAVY);
  stat(s, 10.53, 4.35, 2.4, 1.2, "≤ " + mcSE.toFixed(3), "Monte Carlo standard error", T.blue, NAVY);
  pill(s, 7.9, 5.75, 5.03, 1.15, "RECOMMENDATION FOR PHASE 2", `Record at least ${minutes(recDur)} per network. At this length every test has power of at least ${recMinPower.toFixed(2)}.`, T.green);
}

// =====================================================================
// Final only: discussion
if (FINAL) {
  const lr = (k) => RS(k).descriptive.loss_rate;
  const lowK = KEYS.reduce((a, k) => (lr(k) < lr(a) ? k : a)), highK = KEYS.reduce((a, k) => (lr(k) > lr(a) ? k : a));
  const worstK = KEYS.reduce((a, k) => (R.coverage[k].naive < R.coverage[a].naive ? k : a));
  const deff = (k) => RS(k).bayes.adjusted_posterior.deff;
  const s = base("DISCUSSION", null,
    `The loss rate alone hides how losses are arranged. ${SHORT[highK]} loses about ${Math.round(lr(highK) / lr(lowK))} times more packets than ${SHORT[lowK]}, yet both show strong bursts. Naive intervals get worse as bursts get stronger. The design-effect correction fixes this with one simple step.`);
  panel(s, 0.4, 1.1, 6.6, 3.55, "What the results mean");
  bullets(s, 0.55, 1.58, 6.3, 3.0, [
    ["Burstiness is its own property.", `${SHORT[highK]} loses ${Math.round(lr(highK) / lr(lowK))} times more than ${SHORT[lowK]}. On both, a loss makes the next ${ampMin.toFixed(0)} to ${ampMax.toFixed(0)} times likelier.`],
    ["Stronger bursts, worse intervals.", `Naive coverage is lowest on ${SHORT[worstK]}: ${pc(R.coverage[worstK].naive, 1)} instead of 95%.`],
    ["One step fixes it.", `Dividing n by the design effect gives ${pc(covAMin, 1)} to ${pc(covAMax, 1)} coverage.`],
  ], { fontSize: 16, paraSpaceAfter: 14 });
  panel(s, 7.3, 1.1, 5.63, 3.55, "Naive coverage falls as design effect grows");
  s.addChart([
    { type: pres.charts.BAR, data: [{ name: "Naive coverage (%)", labels: NAMES, values: KEYS.map((k) => +(R.coverage[k].naive * 100).toFixed(1)) }],
      options: { barDir: "col", chartColors: [GREY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '0.0"%"', barGapWidthPct: 60 } },
    { type: pres.charts.LINE, data: [{ name: "Design effect", labels: NAMES, values: KEYS.map((k) => +deff(k).toFixed(2)) }],
      options: { chartColors: [NETCOL[2]], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 8, secondaryValAxis: true, secondaryCatAxis: true, showValue: true, dataLabelPosition: "t", dataLabelFormatCode: "0.00" } }],
    chartOpts({ x: 7.4, y: 1.5, w: 5.43, h: 3.1, showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: 100,
      valAxes: [{ showValAxisTitle: true, valAxisTitle: "Naive coverage (%)", valAxisMinVal: 0, valAxisMaxVal: 100 }, { showValAxisTitle: true, valAxisTitle: "Design effect", valAxisMinVal: 0, valAxisMaxVal: Math.ceil(Math.max(...KEYS.map(deff)) / 2 + 1) * 2, valGridLine: { style: "none" } }],
      catAxes: [{ catAxisTitle: "Network" }, { catAxisHidden: true }] }));
  text(s, 0.4, 4.85, 12.5, 0.3, "WHY IT MATTERS IN PRACTICE", { fontSize: 13, bold: true, color: NAVY });
  pill(s, 0.4, 5.2, 3.0, 1.7, "VIDEO AND VOICE", `Error correction should cover a burst, not one packet. Mean burst: ${listJoin(KEYS.map((k) => RS(k).bayes.markov.burst_len_q[1].toFixed(2)))} packets.`, T.sand);
  pill(s, 3.57, 5.2, 3.0, 1.7, "SERVICE REPORTS", "A loss rate should come with a burst measure, such as P(L|L).", T.blue);
  pill(s, 6.75, 5.2, 3.0, 1.7, "PROTOCOL TUNING", "Retransmission timers tuned on random loss react badly to bursts.", T.peach);
  pill(s, 9.93, 5.2, 3.0, 1.7, "STATISTICS", "Check independence before trusting any standard error or interval.", T.green);
}

// =====================================================================
// Final only: limitations
if (FINAL) {
  const s = base("LIMITATIONS", null,
    `Every study has limits. The main one is that Phase 1 data are simulated. The other points are about test approximations and model choices. For each one we list how we handle it now, or how Phase 2 will.`);
  panel(s, 0.4, 1.1, 12.53, 5.8, "Limits of this study and how we handle them");
  table(s, [
    ["Limitation", "Why it matters", "How we handle it"],
    ["Data are simulated", "Real links may add effects, such as busy hours.", "Phase 2 runs the same code on real captures."],
    ["Dispersion test uses a Poisson baseline", `Counts of ${PPW} packets are Binomial, a little less spread out.`, "The test can only under-state burstiness, never over-state it."],
    ["Runs and Markov tests are approximate", "In very short captures the false-alarm rate can drift from 5%.", `Our traces last ${minutes(CFG.duration_s)}, where the rate is close to 5%.`],
    ["Tail models are not perfect", "Negative Binomial and two-phase fits are still rejected for some networks.", "Future work: hidden Markov and three-phase models."],
    ["Design effect depends on block size", "Other block sizes give slightly different interval widths.", `${CFG.block_s}-second blocks are far longer than any Bad spell.`],
    ["One trace per network", "A single run could be unusual.", `The Monte Carlo studies repeat the experiment ${num(CFG.coverage_reps)} times.`],
  ], { x: 0.55, y: 1.6, w: 12.23, colW: [3.3, 4.6, 4.33], rowH: 0.72, fontSize: 13, leftCols: [1, 2] });
}

// =====================================================================
// Final only: the web app
if (FINAL) {
  const wifi = KEYS.find((k) => k === SEQ) || KEYS[0];
  const s = base("PACKET-LOSS LAB: WEB APP", null,
    `The app runs the same code as the study. Its default view reproduces our ${SHORT[wifi]} results exactly. In the demo we show the red loss squares, then switch to coin-flip mode, then compare the two intervals.`);
  panel(s, 0.4, 1.1, 4.4, 5.8, "What you can do");
  bullets(s, 0.55, 1.58, 4.1, 3.4, [
    ["Pick a network:", NAMES.join(", ") + "."],
    ["Coin-flip mode:", "same loss rate, but every packet independent."],
    ["Watch the packets:", "lost packets shown as red squares."],
    ["Is it random?", "the four tests, passed or failed."],
    ["How sure are we?", "naive and corrected intervals against the truth."],
  ], { fontSize: 14, paraSpaceAfter: 12 });
  pill(s, 0.55, 5.1, 4.1, 1.65, "ONE-MINUTE DEMO", `1. ${SHORT[wifi]}: losses clump together. 2. Coin-flip mode: all checks pass. 3. Intervals: naive misses, corrected covers.`, T.green);
  s.addImage({ path: path.join(__dirname, "assets", "app_watch.jpg"), x: 5.05, y: 1.1, w: 3.85, h: 2.97 });
  s.addImage({ path: path.join(__dirname, "assets", "app_sure.jpg"), x: 9.08, y: 1.1, w: 3.85, h: 2.97 });
  s.addShape(S.RECTANGLE, { x: 5.05, y: 1.1, w: 3.85, h: 2.97, fill: { type: "none" }, line: { color: NAVY, width: 1 } });
  s.addShape(S.RECTANGLE, { x: 9.08, y: 1.1, w: 3.85, h: 2.97, fill: { type: "none" }, line: { color: NAVY, width: 1 } });
  text(s, 5.05, 4.12, 3.85, 0.3, "Watch the packets: red squares are losses", { fontSize: 11, color: MUTED, align: "center" });
  text(s, 9.08, 4.12, 3.85, 0.3, "How sure are we: naive vs corrected", { fontSize: 11, color: MUTED, align: "center" });
  const d = RS(wifi).descriptive;
  stat(s, 5.05, 4.65, 2.5, 1.1, num(d.losses), `${SHORT[wifi]} losses, same as the study`, T.blue, NAVY);
  stat(s, 7.74, 4.65, 2.5, 1.1, RS(wifi).bayes.markov.amp_q[1].toFixed(0) + "×", "likelier after a loss", T.rose, NETCOL[2]);
  stat(s, 10.43, 4.65, 2.5, 1.1, String(CFG.seed), "default seed", T.green, GOOD);
  pill(s, 5.05, 5.95, 7.88, 0.95, "RUN IT", "streamlit run app.py, from the project folder. It opens in the browser.", T.sand);
}

// =====================================================================
// 15. Conclusions
{
  const means = KEYS.map((k) => pc(RS(k).bayes.posterior.mean));
  const s = base("CONCLUSIONS AND FUTURE WORK", null,
    `The main result is that losses in all three scenarios are dependent and arrive in bursts. Models that assume independence fit poorly and give intervals that are too narrow. Phase 2 will repeat the analysis on measured traces. The timeline at the bottom is a proposal in weeks after this review.`);
  panel(s, 0.4, 1.1, 6.15, 3.55, "Conclusions");
  bullets(s, 0.55, 1.58, 5.85, 3.0, [
    ["Loss counts:", (allPoissonRejected ? "the Poisson model is rejected" : "Poisson fits some networks") + (nbBetterAll ? "; the Negative Binomial has lower AIC." : ".")],
    ["Gaps:", `a fast phase (mean ${fastMsMin.toFixed(0)} to ${fastMsMax.toFixed(0)} ms) and a slow phase of seconds.`],
    ["Dependence:", `P(L|L) is ${ampMin.toFixed(0)} to ${ampMax.toFixed(0)} times P(L|N).`],
    ["Networks:", `mean loss rates of ${listJoin(means)} differ significantly.`],
    ["Intervals:", `naive coverage ${pc(covNMin, 0)} to ${pc(covNMax, 0)}; corrected ${pc(covAMin, 0)} to ${pc(covAMax, 0)}.`],
  ], { fontSize: 15, paraSpaceAfter: 10 });
  panel(s, 6.78, 1.1, 6.15, 3.55, "Future work");
  bullets(s, 6.93, 1.58, 5.85, 3.0, [
    ["Measured data:", `${CFG.packet_rate} packets/s streams on wired, Wi-Fi and mobile links.`],
    ["Calibration:", "estimate the two-state model with the Baum-Welch algorithm."],
    ["Tail models:", "three-phase mixtures or a hidden Markov model."],
    ["Hierarchical Bayes:", "pool across networks, with Phase 1 results as priors."],
    ["Time of day:", "compare peak and off-peak loss rates."],
  ], { fontSize: 15, paraSpaceAfter: 10 });
  panel(s, 0.4, 4.85, 12.53, 2.05, `Proposed Phase 2 timeline (weeks after ${FINAL ? "the final review" : "Review 1"})`);
  const gx = 1.0, gw = 11.4, weeks = 8;
  for (let w = 0; w <= weeks; w += 2) {
    const x = gx + (w / weeks) * gw;
    text(s, x - 0.5, 5.25, 1.0, 0.25, w === 0 ? "Now" : "Week " + w, { fontSize: 11, bold: true, color: NAVY, align: "center" });
    s.addShape(S.LINE, { x, y: 5.5, w: 0, h: 1.3, line: { color: LINE, width: 0.75, dashType: "dash" } });
  }
  const bar = (a, b, y, label, fill, col) => {
    const x = gx + (a / weeks) * gw, w = ((b - a) / weeks) * gw;
    s.addShape(S.ROUNDED_RECTANGLE, { x: x + 0.04, y, w: w - 0.08, h: 0.36, rectRadius: 0.08, fill: { color: fill }, line: { color: col, width: 1 } });
    text(s, x + 0.15, y, w - 0.3, 0.36, label, { fontSize: 12, bold: true, color: col === NAVY ? "FFFFFF" : col, valign: "middle" });
  };
  bar(0, 2, 5.55, `Record traces, ${minutes(recDur)} each`, NAVY, NAVY);
  bar(2, 5, 5.98, "Baum-Welch fit and repeat the analysis", T.sand, "7A5A00");
  bar(5, 8, 6.41, "Hierarchical model, time of day, report", T.green, GOOD);
}

// =====================================================================
// 16. References
{
  const s = base("REFERENCES", null,
    `These are the original sources for the loss model and for each statistical method. The code is available on GitHub. Running it with seed ${CFG.seed} reproduces every number in this presentation.`);
  panel(s, 0.4, 1.1, 8.4, 5.8, "Sources");
  const refs = [
    'E. N. Gilbert, "Capacity of a burst-noise channel," Bell System Technical Journal, vol. 39, no. 5, pp. 1253-1265, 1960.',
    'E. O. Elliott, "Estimates of error rates for codes on burst-noise channels," Bell System Technical Journal, vol. 42, no. 5, pp. 1977-1997, 1963.',
    'M. Yajnik, S. Moon, J. Kurose and D. Towsley, "Measurement and modelling of the temporal dependence in packet loss," Proc. IEEE INFOCOM, 1999, pp. 345-352.',
    'A. P. Dempster, N. M. Laird and D. B. Rubin, "Maximum likelihood from incomplete data via the EM algorithm," J. Royal Statistical Society B, vol. 39, no. 1, pp. 1-38, 1977.',
    'A. Wald and J. Wolfowitz, "On a test whether two samples are from the same population," Annals of Mathematical Statistics, vol. 11, no. 2, pp. 147-162, 1940.',
    'H. W. Lilliefors, "On the Kolmogorov-Smirnov test for the exponential distribution with mean unknown," J. American Statistical Association, vol. 64, pp. 387-389, 1969.',
    'S. S. Wilks, "The large-sample distribution of the likelihood ratio for testing composite hypotheses," Annals of Mathematical Statistics, vol. 9, no. 1, pp. 60-62, 1938.',
    'W. H. Kruskal and W. A. Wallis, "Use of ranks in one-criterion variance analysis," J. American Statistical Association, vol. 47, pp. 583-621, 1952.',
    'H. B. Mann and D. R. Whitney, "On a test of whether one of two random variables is stochastically larger than the other," Annals of Mathematical Statistics, vol. 18, no. 1, pp. 50-60, 1947.',
    'H. Akaike, "A new look at the statistical model identification," IEEE Trans. Automatic Control, vol. 19, no. 6, pp. 716-723, 1974.',
    "L. Kish, Survey Sampling. New York: Wiley, 1965.",
    "A. Gelman, J. B. Carlin, H. S. Stern, D. B. Dunson, A. Vehtari and D. B. Rubin, Bayesian Data Analysis, 3rd ed. CRC Press, 2013.",
    'C. R. Harris et al., "Array programming with NumPy," Nature, vol. 585, pp. 357-362, 2020.',
    'P. Virtanen et al., "SciPy 1.0: fundamental algorithms for scientific computing in Python," Nature Methods, vol. 17, pp. 261-272, 2020.',
    'J. D. Hunter, "Matplotlib: a 2D graphics environment," Computing in Science and Engineering, vol. 9, no. 3, pp. 90-95, 2007.',
  ];
  const runs = [];
  refs.forEach((r, i) => {
    runs.push({ text: "[" + (i + 1) + "] ", options: { bold: true, color: BLUE } });
    runs.push({ text: r, options: { breakLine: i < refs.length - 1 } });
  });
  text(s, 0.6, 1.55, 8.0, 5.3, runs, { fontSize: 11, paraSpaceAfter: 3, color: INK });
  pill(s, 9.1, 1.1, 3.83, 1.6, "USE OF SOURCES", "Loss model [1, 2, 3]. EM algorithm [4]. Tests [5 to 9]. AIC [10]. Design effect [11]. Bayesian methods [12]. Software [13 to 15].", T.sand);
  pill(s, 9.1, 2.9, 3.83, 1.25, FINAL ? "PAPER AND CODE" : "REPRODUCIBILITY", FINAL ? `IEEE paper in the paper folder. Seed ${CFG.seed} regenerates every number.` : `Seed ${CFG.seed}. Running run_case_study.py regenerates all results.`, T.green);
  pill(s, 9.1, 4.35, 3.83, 1.25, "SOURCE CODE", "github.com/AashmanBiyani08/Prob_Stats_Project", T.blue);
  pill(s, 9.1, 5.8, 3.83, 1.1, "DATA", "Phase 1 traces are simulated. No measured data is used yet.", T.rose);
}

// =====================================================================
// Final only: appendix of abbreviations
if (FINAL) {
  const s = base("APPENDIX: ABBREVIATIONS", null,
    `This slide lists every short form used in the deck, with its full name and a one-line meaning. Use it to answer panel questions on terms.`);
  const L = [
    ["GE", "Gilbert-Elliott model", "Two-state Good/Bad channel that makes bursts"],
    ["πB", "Stationary Bad probability", "Share of time spent in the Bad state"],
    ["hG, hB", "Loss probability in Good, Bad", "Chance a packet is lost in each state"],
    ["MLE", "Maximum likelihood estimation", "Picks values that make the data most likely"],
    ["EM", "Expectation-Maximisation", "Guess, update, repeat: fits the two-phase mixture"],
    ["AIC", "Akaike Information Criterion", "Model score; lower is better"],
    ["NB", "Negative Binomial", "Count model that allows clumping"],
    ["χ²", "Chi-square test", "Compares observed and expected counts"],
    ["KS", "Kolmogorov-Smirnov test", "Largest gap between data and model curves"],
  ];
  const Rr = [
    ["LRT, G²", "Likelihood-ratio test, its statistic", "Does the previous packet matter?"],
    ["P(L|N), P(L|L)", "Loss after delivered, after lost", "a and b; b/a is the burst amplification"],
    ["H0, H1", "Null, alternative hypothesis", "No effect vs the effect we test for"],
    ["α", "Significance level", `Reject H0 when p < ${ALPHA}`],
    ["CrI", "Credible interval", "95% Bayesian range for the loss rate"],
    ["deff", "Design effect", "Real spread ÷ spread under independence"],
    ["n_eff", "Effective sample size", "n ÷ deff: worth of correlated packets"],
    ["MC, SE", "Monte Carlo, standard error", "Repeat by simulation; its accuracy"],
    ["pp", "Percentage points", "Difference between two percentages"],
  ];
  panel(s, 0.4, 1.1, 6.15, 5.8, "Models and fitting");
  table(s, [["Short", "Full form", "Plain meaning"], ...L], { x: 0.5, y: 1.55, w: 5.95, colW: [0.85, 2.3, 2.8], rowH: 0.52, fontSize: 11, leftCols: [1, 2] });
  panel(s, 6.78, 1.1, 6.15, 5.8, "Tests and inference");
  table(s, [["Short", "Full form", "Plain meaning"], ...Rr], { x: 6.88, y: 1.55, w: 5.95, colW: [1.15, 2.2, 2.6], rowH: 0.52, fontSize: 11, leftCols: [1, 2] });
}

const out = ARGS.filter((a) => !a.startsWith("--"))[0] || path.join(__dirname, "..", "..", "Packet_Loss_Case_Study_Review1.pptx");
pres.writeFile({ fileName: out }).then((f) => console.log("wrote", f));
