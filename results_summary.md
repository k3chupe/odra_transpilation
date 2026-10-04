# Benchmark results summary (fidelity)

Optimal solution = exact_dp: full search of the space (layouts, any
SWAPs on edges, any topological order, exact fidelity cost), computed
once per case. No solver can beat it, only match it. `gap` =
solver's fidelity_cost minus the case's optimal cost: 0 = reaches
optimum, positive = distance from optimum, negative = the solver went
below our routing optimum (Qiskit's full optimization, see
`results/gap-analysis.md`).

- Test cases: 13
- Representatives: 9 (out of 14 compared variants)
- Metric: `fidelity_cost_cancelled` (true minimum), when present in the CSV

## Optimum (exact DP, lower bound)

| Reference | Mean fidelity_cost | Median time (s) | Mean time (s) |
|---|---|---|---|
| optimal (exact DP) | 0.7475 | 0.0779 | 0.2262 |

## Representatives (distance from optimum)

| Family | Representative | Mean fidelity_cost | Mean gap vs optimum | std gap | Median time (s) | Mean time (s) | Mean evals | At optimum |
|---|---|---|---|---|---|---|---|---|
| tabu (family) | tabu fidelity | 0.8077 | +0.0602 | 0.1153 | 1.0339 | 2.727 | 11256 | 8/13 |
| Qiskit | Qiskit preset | 0.8169 | +0.0694 | 0.1061 | 0.0742 | 1.350 | - | 0/13 |
| genetic (family) | genetic fidelity | 0.8249 | +0.0775 | 0.1308 | 1.7103 | 3.163 | 4960 | 4/13 |
| Qiskit | sabre (Qiskit) | 0.8697 | +0.1222 | 0.1334 | 0.0140 | 0.018 | - | 0/13 |
| baseline (greedy/brute) | brute fidelity (greedy swaps) | 0.8723 | +0.1248 | 0.1676 | 0.0552 | 0.113 | 120 | 3/13 |
| tabu (family) | tabu search | 1.0438 | +0.2963 | 0.3419 | 9.6310 | 13.560 | 18380 | 0/13 |
| baseline (greedy/brute) | brute layout (greedy swaps) | 1.0590 | +0.3116 | 0.3545 | 0.0794 | 0.155 | 120 | 0/13 |
| baseline (greedy/brute) | greedy (identity) | 1.1214 | +0.3739 | 0.3483 | 0.0199 | 0.056 | 1 | 0/13 |
| genetic (family) | genetic (GA over layouts) | 1.1363 | +0.3889 | 0.4506 | 1.3881 | 2.358 | 2501 | 0/13 |

`At optimum` = cases where |gap| <= 1e-9, i.e. the solver matched the optimum. Going below the optimum does not count as a hit, since that is a different game (see gap-analysis).

## Representatives: what was merged

Variants within a family share the same algorithm and differ only in
the start, so the plots show the representative. The table shows how
much the collapsed variant actually differed from the representative (over the gaps, tolerance 1e-09), so nothing disappears silently under the label.

| Representative | Collapsed variant | Cases with a difference | Max |delta| | Mean |delta| |
|---|---|---|---|---|
| tabu fidelity | tabu fidelity (greedy) | 3/13 | 0.0545 | 0.0074 |
| tabu fidelity | tabu fidelity (sabre) | 2/13 | 0.0724 | 0.0064 |
| tabu search | tabu + sabre (ours) | 9/13 | 0.1934 | 0.0312 |
| genetic fidelity | genetic_fidelity_greedy | 0/13 | 0.0000 | 0.0000 |
| genetic fidelity | genetic_fidelity_sabre | 0/13 | 0.0000 | 0.0000 |

- Additional representative merges: none (no pair has identical fidelity_cost vectors).

