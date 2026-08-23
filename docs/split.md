# Work split (4 people)

Split by **directory** to avoid merge conflicts.

## Phase 1 — Routing

| Person | Files | Branch |
|--------|-------|--------|
| Infra (you) | `contract.py`, `arch.py`, `generator.py`, `bench.py`, `qiskit_glue.py`, `routing/baseline.py`, CI | `main` / infra PRs |
| A | `routing/tabu.py` | `feat/tabu` |
| B | `routing/genetic.py` | `feat/ga` |
| C | `routing/exact_dp.py` (extend / tune) | `feat/dp` |

## Phase 2 — Optimization

| Person | Files |
|--------|-------|
| All | `optimize/baseline.py`, `optimize/cancel.py` |

## Shared rules

- Read `docs/contract.md` before coding.
- Freeze `contract.py` after week 1 — changes need team PR.
- Benchmarks: edit `benchmarks/suite.json`, not committed CSVs.
- Results go to `results/` (gitignored).

## Sync

- **Code**: git only.
- **Notes / chat context**: `_local/` via Syncthing (not in git).
