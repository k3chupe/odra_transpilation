# Fidelity benchmark results

The exact-DP solver is the reference: it exhaustively searches layouts,
legal SWAPs, and topological execution orders for each case. `gap` is
the solver's fidelity cost minus the reference cost: 0 reaches the
reference, while a positive value indicates a larger cost.

- Benchmark cases: 13
- Solver representatives: 9 (from 14 variants)
- Metric: `fidelity_cost_cancelled` (true minimum), when available

## Exact-DP reference

| Reference | Mean fidelity cost | Median runtime (s) | Mean runtime (s) |
|---|---|---|---|
| Exact DP reference | 0.7475 | 0.0779 | 0.2262 |

## Solver representatives

| Solver | Mean fidelity cost | Mean gap vs reference | Gap std. | Median runtime (s) | Mean runtime (s) | Mean evaluations | At reference |
|---|---|---|---|---|---|---|---|
| Fidelity-aware Tabu | 0.8077 | +0.0602 | 0.1153 | 1.0339 | 2.727 | 11256 | 8/13 |
| Qiskit preset | 0.8169 | +0.0694 | 0.1061 | 0.0742 | 1.350 | - | 0/13 |
| Fidelity-aware GA | 0.8249 | +0.0775 | 0.1308 | 1.7103 | 3.163 | 4960 | 4/13 |
| Qiskit SABRE | 0.8697 | +0.1222 | 0.1334 | 0.0140 | 0.018 | - | 0/13 |
| Brute-force fidelity (greedy SWAPs) | 0.8723 | +0.1248 | 0.1676 | 0.0552 | 0.113 | 120 | 3/13 |
| Tabu search | 1.0438 | +0.2963 | 0.3419 | 9.6310 | 13.560 | 18380 | 0/13 |
| Brute-force layout (greedy SWAPs) | 1.0590 | +0.3116 | 0.3545 | 0.0794 | 0.155 | 120 | 0/13 |
| Greedy (identity) | 1.1214 | +0.3739 | 0.3483 | 0.0199 | 0.056 | 1 | 0/13 |
| Genetic algorithm (layout) | 1.1363 | +0.3889 | 0.4506 | 1.3881 | 2.358 | 2501 | 0/13 |

`At reference` counts cases with |gap| <= 1e-9.

## Collapsed variants

Variants in the same family share the algorithm and differ only in their
initialization, so plots use one representative. The table reports how
much each collapsed variant differs from its representative (tolerance 1e-09).

| Representative | Collapsed variant | Cases differing | Max |delta| | Mean |delta| |
|---|---|---|---|---|
| Fidelity-aware Tabu | Fidelity-aware Tabu (greedy start) | 3/13 | 0.0545 | 0.0074 |
| Fidelity-aware Tabu | Fidelity-aware Tabu (SABRE start) | 2/13 | 0.0724 | 0.0064 |
| Tabu search | Tabu + SABRE warm start | 9/13 | 0.1934 | 0.0312 |
| Fidelity-aware GA | genetic_fidelity_greedy | 0/13 | 0.0000 | 0.0000 |
| Fidelity-aware GA | Fidelity-aware GA (SABRE start) | 0/13 | 0.0000 | 0.0000 |

- Additional merges: none (no pair has identical fidelity-cost vectors).

