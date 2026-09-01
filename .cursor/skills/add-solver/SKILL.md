---
name: add-solver
description: Scaffold a new routing solver for odra-router that conforms to contract.py, registers in SOLVERS, and passes test_contract.py. Use when adding tabu search, genetic algorithm, or any new routing/optimization solver.
---

# Add a odra-router solver

## Steps

1. Read `src/odra_router/contract.py` and `docs/contract.md`.
2. Copy structure from `src/odra_router/routing/baseline.py` (`GreedyShortestPathSolver`).
3. Implement:
   - class with `name: str`
   - `solve(problem, *, seed, budget_s) -> RoutingSolution`
4. At module bottom: `register_solver(YourSolver())`.
5. Import module in `src/odra_router/__init__.py` if not loaded via `routing/__init__.py`.
6. Run `pytest tests/test_contract.py -q`.

## Do not

- Mutate `problem.circuit` in place.
- Return raw `QuantumCircuit` from `solve()` — return `RoutingSolution`.
- Register stub solvers that raise `NotImplementedError` (breaks CI).

## Checklist

- [ ] `validate(problem, solution)` passes on `trivial_circuit()`
- [ ] Passes on 10 random seeds in `test_contract.py`
- [ ] Respects `budget_s` (check `time.monotonic()`)
- [ ] `ponytail:` comment if algorithm has known ceiling
