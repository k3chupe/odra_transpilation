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
| optimal (exact DP) | 1.5953 | 0.0657 | 0.1600 |

## Representatives (distance from optimum)

| Family | Representative | Mean fidelity_cost | Mean gap vs optimum | std gap | Median time (s) | Mean time (s) | Mean evals | At optimum |
|---|---|---|---|---|---|---|---|---|
| tabu (family) | tabu fidelity | 1.6891 | +0.0938 | 0.1871 | 0.9723 | 2.211 | 11756 | 9/13 |
| genetic (family) | genetic fidelity | 1.7273 | +0.1320 | 0.2669 | 1.7299 | 3.074 | 4977 | 4/13 |
| Qiskit | sabre (Qiskit) | 1.8075 | +0.2122 | 0.2403 | 0.0140 | 0.016 | - | 0/13 |
| baseline (greedy/brute) | brute fidelity (greedy swaps) | 1.8114 | +0.2161 | 0.3273 | 0.0682 | 0.103 | 120 | 3/13 |
| baseline (greedy/brute) | brute layout (greedy swaps) | 2.0743 | +0.4790 | 0.6130 | 0.0854 | 0.132 | 120 | 0/13 |
| Qiskit | Qiskit preset | 2.0967 | +0.5013 | 0.6439 | 0.0765 | 1.864 | - | 0/13 |
| tabu (family) | tabu search | 2.1046 | +0.5092 | 0.6223 | 11.5820 | 13.902 | 19809 | 1/13 |
| genetic (family) | genetic (GA over layouts) | 2.1663 | +0.5710 | 0.6939 | 1.5611 | 1.896 | 2501 | 1/13 |
| baseline (greedy/brute) | greedy (identity) | 2.2495 | +0.6542 | 0.6599 | 0.0272 | 0.047 | 1 | 0/13 |

`At optimum` = cases where |gap| <= 1e-9, i.e. the solver matched the optimum. Going below the optimum does not count as a hit, since that is a different game (see gap-analysis).

## Representatives: what was merged

Variants within a family share the same algorithm and differ only in
the start, so the plots show the representative. The table shows how
much the collapsed variant actually differed from the representative (over the gaps, tolerance 1e-09), so nothing disappears silently under the label.

| Representative | Collapsed variant | Cases with a difference | Max |delta| | Mean |delta| |
|---|---|---|---|---|
| tabu fidelity | tabu fidelity (greedy) | 2/13 | 0.3354 | 0.0263 |
| tabu fidelity | tabu fidelity (sabre) | 2/13 | 0.0061 | 0.0005 |
| tabu search | tabu + sabre (ours) | 9/13 | 0.1436 | 0.0372 |
| genetic fidelity | genetic_fidelity_greedy | 0/13 | 0.0000 | 0.0000 |
| genetic fidelity | genetic_fidelity_sabre | 1/13 | 0.0008 | 0.0001 |

- Additional representative merges: none (no pair has identical fidelity_cost vectors).

