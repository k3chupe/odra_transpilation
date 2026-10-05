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
| Exact DP reference | 0.7475 | 0.0675 | 0.1888 |

## Solver representatives

| Solver | Mean fidelity cost | Mean gap vs reference | Gap std. | Median runtime (s) | Mean runtime (s) | Mean evaluations | At reference |
|---|---|---|---|---|---|---|---|
| Fidelity-aware GA | 0.7740 | +0.0266 | 0.0430 | 1.3497 | 1.920 | 4789 | 5/13 |
| Fidelity-aware Tabu | 0.7752 | +0.0278 | 0.0497 | 2.1045 | 3.054 | 12540 | 5/13 |
| Qiskit preset | 0.8169 | +0.0694 | 0.1061 | 0.0786 | 0.087 | - | 0/13 |
| Brute-force fidelity (greedy SWAPs) | 0.8283 | +0.0809 | 0.0994 | 0.0530 | 0.085 | 120 | 3/13 |
| Qiskit SABRE | 0.8697 | +0.1222 | 0.1334 | 0.0138 | 0.015 | - | 0/13 |
| Tabu search | 1.0438 | +0.2963 | 0.3419 | 13.0039 | 16.055 | 19433 | 0/13 |
| Brute-force layout (greedy SWAPs) | 1.0590 | +0.3116 | 0.3545 | 0.0776 | 0.134 | 120 | 0/13 |
| Greedy (identity) | 1.1214 | +0.3739 | 0.3483 | 0.0299 | 0.056 | 1 | 0/13 |
| Genetic algorithm (layout) | 1.1363 | +0.3889 | 0.4506 | 1.3687 | 2.091 | 2501 | 0/13 |

`At reference` counts cases with |gap| <= 1e-9.

## Collapsed variants

Variants in the same family share the algorithm and differ only in their
initialization, so plots use one representative. The table reports how
much each collapsed variant differs from its representative (tolerance 1e-09).

| Representative | Collapsed variant | Cases differing | Max |delta| | Mean |delta| |
|---|---|---|---|---|
| Fidelity-aware Tabu | Fidelity-aware Tabu (greedy start) | 4/13 | 0.0219 | 0.0027 |
| Fidelity-aware Tabu | Fidelity-aware Tabu (SABRE start) | 4/13 | 0.0363 | 0.0040 |
| Tabu search | Tabu + SABRE warm start | 9/13 | 0.1934 | 0.0312 |
| Fidelity-aware GA | genetic_fidelity_greedy | 0/13 | 0.0000 | 0.0000 |
| Fidelity-aware GA | Fidelity-aware GA (SABRE start) | 1/13 | 0.0014 | 0.0001 |

- Additional merges: none (no pair has identical fidelity-cost vectors).

