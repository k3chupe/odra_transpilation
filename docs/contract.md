# Integration contract

All routing solvers implement the same interface in [`src/qtrans/contract.py`](../src/qtrans/contract.py).

## Problem

```python
RoutingProblem(circuit, coupling_map)
  .interactions  # ((v0, v1), ...) two-qubit gates in DAG order
```

## Solution

```python
RoutingSolution(
    initial_layout=(0, 1, 2, 3, 4),  # virtual q -> physical
    swaps=((0, 2, 4), ...),          # (before_interaction_i, phys_a, phys_b)
)
```

## Lifecycle

1. `solver.solve(problem, seed=..., budget_s=...) -> RoutingSolution`
2. `validate(problem, solution)` — must pass for integration
3. `apply(problem, solution) -> QuantumCircuit` — shared builder (physical wire indices)
4. `metrics(problem, solution)` — swap count, depth, etc.

Unitary equivalence vs the original circuit requires layout-aware comparison (physical vs virtual wire labels); use `validate()` for integration tests.

## Adding a solver

1. Create `src/qtrans/routing/your_solver.py`
2. Implement `class YourSolver` with `name` and `solve()`
3. Call `register_solver(YourSolver())` at module bottom
4. Import module from `src/qtrans/__init__.py` or `routing/__init__.py`
5. Run `pytest -q` — `test_contract.py` picks it up automatically

## DP caveat

`exact_dp` is optimal for **fixed gate order** and searches layout + swaps. It does not commute gates; report it as a lower bound reference, not global optimum over all equivalent circuits.
