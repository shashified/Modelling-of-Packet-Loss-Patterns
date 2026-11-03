# Phase 2 results: real packet captures

Loss here is round-trip loss: a probe counts as lost when no reply came back within the timeout.

## Captures

| Label | File | Mode | Target | Packets | Duration | Lost | Loss rate (95% CrI) | RTT median / p95 |
|---|---|---|---|---|---|---|---|---|
| hotspot#1 | hotspot_20261029-142109.csv | icmp | 10.23.154.194 | 6,000 | 120 s | 22 | 0.383% [0.243%, 0.555%] | 6.8 / 15.6 ms |
| hotspot#2 | hotspot_20261030-110608.csv | icmp | 172.20.10.1 | 6,000 | 120 s | 0 | 0.017% [0.000%, 0.061%] | 3.7 / 4.4 ms |
| hotspot_internet#1 | hotspot_internet_20261030-113339.csv | icmp | 1.1.1.1 | 1,500 | 30 s | 1 | 0.133% [0.016%, 0.371%] | 50.1 / 234.2 ms |
| hotspot_internet#2 | hotspot_internet_20261030-115651.csv | icmp | 1.1.1.1 | 1,500 | 30 s | 11 | 0.799% [0.414%, 1.307%] | 131.2 / 912.6 ms |

Note: hotspot#1, hotspot#2, hotspot_internet#1, hotspot_internet#2 ran for less than 600 s. The Phase 1 power study needs about ten minutes to detect bursts reliably on a low-loss link.

Too few losses for the distribution and independence tests (fewer than 10): hotspot#2, hotspot_internet#1. Only the loss-rate estimate is shown for these.

## Is loss random (independent)?

| Label | Var / mean | Dispersion p | Runs z (p) | P(L given N) | P(L given L) | b/a (95% CrI) | Mean burst | Verdict |
|---|---|---|---|---|---|---|---|---|
| hotspot#1 | 1.28 | 0.0206 | -6.9 (< 1e-10) | 0.33% | 9.1% | 33.1 [7.7, 92.3] | 1.10 | bursty |
| hotspot_internet#2 | 1.97 | 0.00137 | -10.6 (< 1e-10) | 0.54% | 27.3% | 50.6 [14.9, 138.9] | 1.38 | bursty |

## Distribution fits

| Label | AIC Poisson | AIC Neg. Bin. | Chi-square Poisson p | KS exponential p | AIC exp. | AIC two-phase | Fast share | Fast / slow mean gap |
|---|---|---|---|---|---|---|---|---|
| hotspot#1 | 128 | 126 | n/a | 0.0805 | 112 | 110 | 49% | 1287 ms / 8.6 s |
| hotspot_internet#2 | 55 | 48 | n/a | 0.001 | 40 | 22 | 49% | 34 ms / 4.8 s |

## Interval estimates

| Label | Naive 95% interval | Design effect | Adjusted 95% interval | Heavy windows: predicted vs observed |
|---|---|---|---|---|
| hotspot#1 | [0.243%, 0.555%] | 2.07 | [0.205%, 0.662%] | 2.21e-06 vs 0.00e+00 |
| hotspot_internet#2 | [0.414%, 1.307%] | 1.00 | [0.414%, 1.307%] | 9.51e-05 vs 0.00e+00 |

## Comparing captures

Kruskal-Wallis H = 0.4, p = 0.554; chi-square homogeneity = 2.9 on 1 df, p = 0.0889.
- hotspot#1 vs hotspot_internet#2: Bonferroni p = 0.556
