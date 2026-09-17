# Integration contract

All routing solvers implement the same interface in [`src/odra_router/contract.py`](../src/odra_router/contract.py).

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
    gate_order=None,                 # optional permutation of interaction
)                                    # indices in execution order; None = DAG order
```

## Scheduling convention (gate_order and 1Q placement)

`apply` and the fidelity objective both consume the same `execution_steps`
iterator (`build_plan` in `contract.py`), so they always agree on placement:

- interactions execute in `gate_order` (or DAG order when `None`); SWAPs are
  keyed by interaction index and applied in execution order;
- single-qubit gates are attached to the *next* two-qubit gate on the same
  logical qubit: they execute right before it, after its SWAPs, on the wire
  the qubit sits on at that moment (a 1Q gate "rides" its qubit through
  SWAPs, which is unitarily equivalent to the DAG placement);
- 1Q gates after the last two-qubit gate on their qubit (or on qubits with no
  two-qubit gates at all) are leftovers: they execute at the very end on the
  final layout;
- measure/reset/barrier are placed at the end on the final wire of their
  qubit.

This is what makes fidelity evaluation meaningful: a 1Q gate's physical wire
(and hence its fidelity) depends on the SWAPs that moved its qubit.

## Lifecycle

1. `solver.solve(problem, seed=..., budget_s=...) -> RoutingSolution`
2. `validate(problem, solution)` — must pass for integration
3. `apply(problem, solution) -> QuantumCircuit` — shared builder (physical wire indices)
4. `metrics(problem, solution)` — swap count, depth, etc.

Unitary equivalence vs the original circuit requires layout-aware comparison (physical vs virtual wire labels); use `validate()` for integration tests.

## Adding a solver

1. Create `src/odra_router/routing/your_solver.py`
2. Implement `class YourSolver` with `name` and `solve()`
3. Call `register_solver(YourSolver())` at module bottom
4. Import module from `src/odra_router/__init__.py` or `routing/__init__.py`
5. Run `pytest -q` — `test_contract.py` picks it up automatically

## Ideal boundary (decision: variant A)

`exact_dp` is optimal for **fixed gate order** and searches layout + swaps. It
does not commute gates; report it as a lower bound reference, not global
optimum over all equivalent circuits.

The game the ideal plays exactly (nothing outside this list is bounded by it):

1. initial layout free (any of the 120 permutations of the star leaves);
2. SWAPs on star edges only, priced as 3 native CZ;
3. any topological order of the interactions, including interleavings across
   DAG levels;
4. cancellation of literally adjacent self-inverse pairs, both on the input
   (`reduce_input`) and on the routed output (`cancel_adjacent`).

Outside that game, and therefore not covered by the bound: non-adjacent
commutation (CX/CZ pairs separated by commuting gates), 1Q resynthesis,
whole 2Q-block resynthesis (`Collect2qBlocks` + `ConsolidateBlocks` +
`UnitarySynthesis`), and the CX to CZ translation of the source circuit. The
Qiskit preset runs all of them, so it can land below the ideal.

**Decision (variant A, 2026-09-14):** keep `exact_dp` as "routing plus
adjacent cancellation" and document the boundary, instead of widening the
reference. Evidence, from `scripts/gap_analysis.py` into
`results/gap-analysis.md`:

- the Qiskit preset ends below the ideal on 3 of 13 cases (`small_0`,
  `medium_1`, `heavy_1`), always through non-adjacent commutation at
  optimization level 2 or higher;
- `cancel_adjacent` removes 0.00e+00 of that advantage: the preset never
  leaves a literally adjacent cancellable pair, so the win is outside our
  pass, not something our pass forgot to do;
- our cancellation does pay off elsewhere, on our own ideal before routing
  (`reduce_input` lowers `raw` to `reduced` on 6 cases);
- every case where Qiskit wins has a named cause from the taxonomy, `other`
  never appears.

Variant B (a second reference "routing plus full Qiskit optimisation") is
deliberately not implemented: it would be a heuristic, not a lower bound, and
would need its own label everywhere a bound is quoted.

Pinned by `tests/test_ideal_boundary.py`.

## Fidelity objective (phase 3)

`src/odra_router/fidelity.py` adds the fidelity-aware objective suggested by the
project expert: minimize `sum(-ln f)` over the routed circuit with per-wire
and per-edge fidelities (`FidelityModel`). Key entry points:

- `calc_goal_function(problem, encoding, model) -> float | None` — the expert's
  `calcGoalFunction`: an encoding is `(initial_layout, swaps_choices, flags)`
  with `swaps_choices[i]` in 0..4 selecting `EDGE_SWAPS` (0 = no SWAP) and
  `flags[k]` toggling the order of a two-gate layer; returns `None` when some
  two-qubit gate's endpoints are not adjacent;
- `fidelity_cost(circuit, model)` — metric on any routed circuit (also the
  Qiskit preset output);
- `solution_cost(problem, solution, model)` / `solution_from_encoding(...)` —
  solution-level helpers shared with the solvers.

The default model `odra5_default_fidelity()` is synthetic placeholder data
(documented in `fidelity.py`), replaceable with real IQM calibration.
