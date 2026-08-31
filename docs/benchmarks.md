# Benchmarks

Three benchmark sources are available. All evaluate the **routing** stage on
two-qubit gates (the swap count after placing two-qubit gates onto adjacent
physical qubits).

| Source | Ground truth | Command / API |
|--------|--------------|---------------|
| Synthetic suite | none (comparative) | `qtrans-bench` |
| QUEKO generator | **0 SWAPs** (known-optimal placement) | `qtrans-bench-queko` |
| External QASM | dataset-dependent | `qtrans.datasets` |

Brute-force layout and exact DP act as **references** (how far each solver is
from the ideal), not as competitors to beat. The comparison targets are the
Qiskit preset baseline and the metaheuristics (`tabu_search`,
`tabu_sabre_start`, `genetic_trivial`).

## Cost metric: `cz_cost`

The ODRA5 target has no native SWAP gate (only `r` and `cz`), so Qiskit's
preset transpiler expands every SWAP into CZ gates and its raw `swap_count` is
always 0. To compare all solvers on one cost, every CSV row carries `cz_cost`:
the number of two-qubit gates after translating the routed circuit to the
native `cz` basis (`swap` counts as 3 CZ, `cx`/`cz` as 1, single-qubit
rotations are ignored). See `native_cz_cost()` in `src/qtrans/contract.py`.
`swap_count` remains in the CSVs as the logical swap count of our solvers.

## Tabu warm start (`tabu_sabre_start`)

`tabu_search` starts from a random layout; `tabu_sabre_start` instead starts
from the initial layout a single Sabre run chooses (`SabreLayout`), so the
search begins in a good region. Both variants are registered and appear side by
side in the CSVs, which doubles as the random-vs-warm-start ablation.

## Why quality saturates on the star

On ODRA5 the layout alone determines the optimal swap count (for fixed gate
order, the greedy per-layout schedule is optimal, and brute force over the 120
layouts equals the exact DP optimum; verified across hard and random
instances). So any solver that searches layouts eventually reaches the same
optimum: brute force, exact DP, tabu and GA agree in quality, only greedy
(identity layout) lags. Benchmarks therefore compare the **time-quality
frontier** (best result within a time budget), not just final quality.

There is a structural reason even this frontier is flat: for any circuit on
the star, exactly **24 of the 120 layouts reach the optimum** (the 4! leaf
permutations are equivalent under the star symmetry), so random layout
sampling hits an optimal layout with probability 1/5 on the first few draws.
Making layout-searching algorithms genuinely struggle requires more qubits
(the layout space grows as n!) or a swap-sequence search (exponential in the
interaction count); both are out of the current ODRA5 scope.

## Budget sweep (`qtrans-bench-sweat`)

Sweeps a time budget across hard, dense-random and deep-QUEKO instances, with
R repetitions per seed, so the measurable differences (greedy gap, time and
layout-evaluation overhead of each solver, warm-start effect) are visible:

```bash
qtrans-bench-sweat
# -> results/sweat.csv + results/sweat-summary.md
```

- Instances: `hard_Nr` (deterministic cycles over the six non-edge pairs,
  [`generator.hard_circuit`](../src/qtrans/generator.py)), dense random
  (`num_gates` 40/60, `p_two_qubit` 0.7), deep QUEKO (depth 8/16/24).
- Budgets: 0.05, 0.1, 0.2, 0.5, 1.0 s; repetitions: R=5 (solver seed = rep).
- Reference ("ideal"): brute force over layouts with a generous budget.
  `%opt` = fraction of reps reaching the reference swap count, `gap` = median
  swaps above reference, `med_s` = median seconds, `med evals` = median layout
  evaluations per solve (the solvers report `last_evals`).
- Solvers: greedy, brute force, exact DP, `tabu_search`, `tabu_sabre_start`,
  `genetic_trivial`. Qiskit preset and `sabre_baseline` are not budget-limited
  solvers, so they stay out of the sweep (see `qtrans-bench`/`qtrans-bench-queko`).

## Fidelity benchmark (`qtrans-bench-fidelity`)

Phase 3 introduced the fidelity-aware objective suggested by the project
expert: per-wire and per-edge fidelities, minimize `sum(-ln f)` over the
routed circuit (see `src/qtrans/fidelity.py` and `docs/contract.md`). The
benchmark scores every solver and the Qiskit preset on this objective:

```bash
qtrans-bench-fidelity
# -> results/benchmark-fidelity.csv + results/fidelity-summary.md
```

- Instances: the synthetic suite + `hard_Nr` (2/4/8 rounds).
- Columns: `fidelity_cost` (lower is better), `swap_count`, `cz_cost`,
  `depth`, `evals`, `seconds`.
- Solvers: all registered ones + `qiskit_preset`; `tabu_fidelity` /
  `tabu_fidelity_greedy` are the move-based phase-3 solvers and
  `brute_fidelity_layout` is the layout-level reference (all 120 layouts,
  greedy SWAPs).
- Execution convention: the phase-3 solvers execute in layer (level) order per
  the expert's model (their `gate_order`), older solvers in DAG order; 1Q
  gates ride their qubit through SWAPs (C2 placement), so the fidelity of a
  1Q gate depends on which wire it ends up on.

Known results (synthetic model): on the adversarial `hard` instances the
move-based tabu beats the cz-optimal references in fidelity (it trades routes
onto better-fidelity edges and sometimes even finds fewer SWAPs than any
layout-only route, e.g. hard_4r: 12 vs 13 SWAPs). On dense random circuits the
cz-minimizing routes win: with many gates, total gate count dominates the
cost, so the minimum-SWAP route is also the best-fidelity route.

## Synthetic suite

Seeded random circuits defined in [`benchmarks/suite.json`](../benchmarks/suite.json),
generated by [`src/qtrans/generator.py`](../src/qtrans/generator.py). Useful for
smoke comparisons; the optimal swap count is not known in advance.

```bash
qtrans-bench
# -> results/benchmark.csv
```

## QUEKO (known optimal)

QUEKO ("quantum mapping examples with known optimal", Tan & Cong 2020) generates,
for a given coupling graph, circuits together with a placement that routes every
two-qubit gate without any SWAP. For those circuits the **optimal swap count is
0** by construction, which makes them a correctness/or optimality oracle: a
solver reaches the optimum if and only if it returns a layout with 0 SWAPs.

The generator is implemented locally in
[`src/qtrans/queko.py`](../src/qtrans/queko.py) (adapted from
`glassnotes/queko-generator`, MIT). It has **no external dependencies** beyond
`numpy` and builds circuits directly as Qiskit objects.

```bash
qtrans-bench-queko
# -> results/queko.csv  (columns include `optimal` = swap_count == 0)
```

Programmatic use:

```python
from qtrans.queko import odra5_queko
from qtrans.contract import make_problem
from qtrans.routing.baseline import _route_with_layout

circuit, optimal_layout = odra5_queko(depth=8, density_vec=(0.2, 0.3), seed=0)
problem = make_problem(circuit)                     # ODRA5 star coupling map
assert len(_route_with_layout(problem, optimal_layout).swaps) == 0
```

- `queko_circuit(edges, depth, density_vec, seed=0) -> (circuit, optimal_layout)`
  generates on an arbitrary edge list; `optimal_layout` is the virtual→physical
  mapping achieving 0 SWAPs.
- `odra5_queko(depth, density_vec=(0.2, 0.3), seed=0)` is the ODRA5-star
  convenience wrapper.
- A matching of the star admits at most one edge, so the generator places at
  most one two-qubit gate per timestep and the two-qubit density is bounded
  (`d2 * n / 2 <= 1` for `n=5`); the module raises `ValueError` for
  inadmissible densities, mirroring the reference checks. Note that DAG
  *layers* of arbitrary circuits can still hold two two-qubit gates (e.g.
  `cx(0,1); cx(3,4)`), which is exactly what the phase-3 layer-order flags
  decide.

## External QASM

[`src/qtrans/datasets.py`](../src/qtrans/datasets.py) loads OpenQASM 2.0 files
so external benchmarks can be dropped in without adding dependencies:

```python
from qtrans.datasets import load_qasm, qasm_circuits

qc = load_qasm("benchmarks/qasm/queko_linear_5.qasm")
cases = qasm_circuits("benchmarks/qasm", max_qubits=5)   # [(name, circuit), ...]
```

A small public corpus can be fetched with the standard library only:

```python
from qtrans.datasets import fetch_corpus
fetch_corpus()   # -> benchmarks/qasm/ (gitignored), 5-qubit QUEKO QASM files
```

### Caveat on fetched QASM

The fetched 5-qubit QUEKO files are known-optimal on **their native topology**
(linear / mesh / torus), **not** on the ODRA5 star. Use them as diverse input
circuits for comparative runs; for ground truth on ODRA5 use the local QUEKO
generator above.

## Sources considered

- [QUEKO-benchmark](https://github.com/qu-tan-um/QUEKO-benchmark) — original
  dataset (QASM + solution files), but sized for 16–54-qubit devices; too large
  for ODRA5. The algorithm is reused via the local generator instead.
- [MQT Bench](https://pypi.org/project/mqt.bench/) — realistic algorithm
  circuits, but current `mqt.bench` (2.x) requires `qiskit>=2.0`, incompatible
  with the pinned `qiskit==1.2.4` here, so it is not a dependency. Load its
  exported QASM files through `qtrans.datasets` if needed.
- [QASMBench](https://github.com/pnnl/QASMBench) — large, multi-qubit circuits;
  not sized for a 5-qubit star.
- [qqq-wisc/quantum-compiler-benchmark-circuits](https://github.com/qqq-wisc/quantum-compiler-benchmark-circuits)
  — curated QASM files including 5-qubit QUEKO circuits; used by
  `fetch_corpus()`.
