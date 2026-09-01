# Agent context — odra-router

## Goal

Build custom **Routing** and **Optimization** transpiler stages for ODRA5 (5-qubit star, native `r` + `cz`), compare against Qiskit 1.2 preset transpiler.

## Architecture

- **Representation**: Qiskit `DAGCircuit` internally; solvers return `RoutingSolution` (layout + SWAP schedule), never mutate input circuits.
- **Contract**: `src/odra_router/contract.py` — read before editing any solver.
- **Topology**: `src/odra_router/arch.py` — ODRA5 without IQM deps.
- **Integration**: `src/odra_router/qiskit_glue.py` — `Solver` → `TransformationPass`.

## Solvers

| Module | Status |
|--------|--------|
| `routing/baseline.py` | greedy shortest-path + brute-force layout + sabre |
| `routing/exact_dp.py` | exact DP (fixed gate order), reference (undirected neighbors) |
| `routing/tabu.py` | tabu over layouts: `tabu_search` (random start) + `tabu_sabre_start` (warm start from a single Sabre run) |
| `routing/genetic_trivial.py` | trivial GA placeholder for benchmark comparison (implemented, registered) |
| `routing/genetic.py` | the real GA, owned by a team member, still a stub (`NotImplementedError`, unregistered) |
| `optimize/*` | phase 2 stubs |

Register new solvers with `register_solver()` in `contract.py`. Do **not**
register a solver that raises `NotImplementedError` — `tests/test_contract.py`
runs every registered solver automatically.

Brute-force layout and exact DP are **references** (how far from the ideal),
not competitors to beat. The comparison targets are the Qiskit preset baseline
and the metaheuristics (`tabu_*`, `genetic_trivial`).

## Benchmarks

- `src/odra_router/queko.py` — QUEKO generator: circuits with a known-optimal
  placement (0 SWAPs) on a given coupling graph.
- `src/odra_router/datasets.py` — load external OpenQASM 2.0 files, and fetch a
  small public QASM corpus.
- `odra-router-bench-sweat` — budget sweep (time-quality frontier) on hard,
  dense and deep-QUEKO instances; quality saturates on the star, so this is
  where convergence differences show.
- Details and sources: `docs/benchmarks.md`.

## Rules

1. Do not change `contract.py` without team PR. Phase 3 added a backward-
   compatible extension (approved): `RoutingSolution.gate_order`, the
   `execution_steps`/`build_plan` scheduling helpers and the C2 1Q placement
   in `apply` (1Q gates ride their qubit through SWAPs). Old solvers emit
   `gate_order=None` and behave as before.
2. Every solver must pass `tests/test_contract.py` automatically.
3. Use `ponytail:` comments for deliberate shortcuts.
4. Private notes go in `_local/` (Syncthing), never commit them.
5. Pin qiskit 1.2.4 — see `tests/test_env.py`.

## Commands

```bash
pytest -q
odra-router-bench
odra-router-bench-queko
odra-router-bench-sweat
odra-router-bench-fidelity        # fidelity objective (phase 3)
python visualize_results.py       # plots/ + results_summary.md from results/benchmark-fidelity.csv
```

## References

- [IBM transpiler stages](https://quantum.cloud.ibm.com/docs/en/guides/transpiler-stages)
- Reference baseline: `notebooks/00_baseline.ipynb`
