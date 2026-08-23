# Agent context — qtrans

## Goal

Build custom **Routing** and **Optimization** transpiler stages for ODRA5 (5-qubit star, native `r` + `cz`), compare against Qiskit 1.2 preset transpiler.

## Architecture

- **Representation**: Qiskit `DAGCircuit` internally; solvers return `RoutingSolution` (layout + SWAP schedule), never mutate input circuits.
- **Contract**: `src/qtrans/contract.py` — read before editing any solver.
- **Topology**: `src/qtrans/arch.py` — ODRA5 without IQM deps.
- **Integration**: `src/qtrans/qiskit_glue.py` — `Solver` → `TransformationPass`.

## Solvers

| Module | Status |
|--------|--------|
| `routing/baseline.py` | greedy + brute-force + sabre |
| `routing/exact_dp.py` | exact DP (fixed gate order) |
| `routing/tabu.py` | stub |
| `routing/genetic.py` | stub |
| `optimize/*` | phase 2 stubs |

Register new solvers with `register_solver()` in `contract.py`.

## Rules

1. Do not change `contract.py` without team PR.
2. Every solver must pass `tests/test_contract.py` automatically.
3. Use `ponytail:` comments for deliberate shortcuts.
4. Private notes go in `_local/` (Syncthing), never commit them.
5. Pin qiskit 1.2.4 — see `tests/test_env.py`.

## Commands

```bash
pytest -q
qtrans-bench
```

## References

- [IBM transpiler stages](https://quantum.cloud.ibm.com/docs/en/guides/transpiler-stages)
- Reference baseline: `notebooks/00_baseline.ipynb`
