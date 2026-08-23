# Work split

Split by **directory** to reduce merge conflicts.

## Phase 1 — Routing

| Area | Files |
|------|-------|
| Core / infra | `contract.py`, `arch.py`, `generator.py`, `bench.py`, `qiskit_glue.py`, `routing/baseline.py`, CI |
| Solvers | `routing/tabu.py`, `routing/genetic.py`, `routing/exact_dp.py` |

Each solver lives in its own file. Read [contract.md](contract.md) before editing.

## Phase 2 — Optimization

| Area | Files |
|------|-------|
| Optimize | `optimize/baseline.py`, `optimize/cancel.py` |

## Shared rules

- Read [contract.md](contract.md) before coding.
- Freeze `contract.py` after week 1 — changes need team PR.
- Benchmarks: edit `benchmarks/suite.json`, not committed CSVs.
- Results go to `results/` (gitignored).
- Do not register stub solvers that raise `NotImplementedError` — breaks CI.

## Sync

- **Code**: git only.
- **Notes / chat context**: `_local/` via Syncthing (not in git).
