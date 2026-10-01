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
| Exact DP reference | 1.5953 | 0.0152 | 0.0459 |

## Solver representatives

| Solver | Mean fidelity cost | Mean gap vs reference | Gap std. | Median runtime (s) | Mean runtime (s) | Mean evaluations | At reference |
|---|---|---|---|---|---|---|---|
| Fidelity-aware Tabu | 1.6891 | +0.0938 | 0.1871 | 0.1893 | 0.496 | 11756 | 9/13 |
| Fidelity-aware GA | 1.7273 | +0.1320 | 0.2669 | 0.3540 | 0.595 | 4977 | 4/13 |
| Qiskit SABRE | 1.7839 | +0.1886 | 0.2204 | 0.0042 | 0.005 | - | 0/13 |
| Brute-force fidelity (greedy SWAPs) | 1.8114 | +0.2161 | 0.3273 | 0.0119 | 0.020 | 120 | 3/13 |
| Brute-force layout (greedy SWAPs) | 2.0743 | +0.4790 | 0.6130 | 0.0234 | 0.030 | 120 | 0/13 |
| Tabu search | 2.1046 | +0.5092 | 0.6223 | 2.6081 | 3.154 | 19921 | 1/13 |
| Qiskit preset | 2.1136 | +0.5183 | 0.6718 | 0.0244 | 0.027 | - | 0/13 |
| Genetic algorithm (layout) | 2.1663 | +0.5710 | 0.6939 | 0.3429 | 0.415 | 2501 | 1/13 |
| Greedy (identity) | 2.2495 | +0.6542 | 0.6599 | 0.0066 | 0.011 | 1 | 0/13 |

`At reference` counts cases with |gap| <= 1e-9.

## Collapsed variants

Variants in the same family share the algorithm and differ only in their
initialization, so plots use one representative. The table reports how
much each collapsed variant differs from its representative (tolerance 1e-09).

| Representative | Collapsed variant | Cases differing | Max |delta| | Mean |delta| |
|---|---|---|---|---|
| Fidelity-aware Tabu | Fidelity-aware Tabu (greedy start) | 2/13 | 0.3354 | 0.0263 |
| Fidelity-aware Tabu | Fidelity-aware Tabu (SABRE start) | 3/13 | 0.0061 | 0.0010 |
| Tabu search | Tabu + SABRE warm start | 9/13 | 0.1794 | 0.0403 |
| Fidelity-aware GA | genetic_fidelity_greedy | 0/13 | 0.0000 | 0.0000 |
| Fidelity-aware GA | Fidelity-aware GA (SABRE start) | 0/13 | 0.0000 | 0.0000 |

- Additional merges: none (no pair has identical fidelity-cost vectors).

