"""Fidelity model and fidelity-aware cost functions for ODRA5 (phase 3).

Every physical wire and every star edge carries a fidelity, and routing
quality is measured as the total gate cost ``sum(-ln f)`` over the routed
circuit. This de-symmetrizes the layout/SWAP space that saturated under pure
CZ counting (24 of 120 layouts are optimal for every circuit): with distinct
per-edge fidelities the initial layout and which edge a SWAP uses change the
objective even at equal swap counts.

Conventions (per the expert's suggestions):

- one SWAP choice per two-qubit interaction, ``0`` = none, ``1..4`` = the
  four star edges (``EDGE_SWAPS``; the expert's 1-based numbering with central
  qubit 3 maps 1:(1,3) 2:(2,3) 3:(3,4) 4:(3,5) onto our 1:(0,2) 2:(1,2)
  3:(2,3) 4:(2,4), same order);
- a SWAP counts as 3 two-qubit gates on that edge (native CZ decomposition),
  consistent with ``native_cz_cost``;
- single-qubit gates are attached to the *next* two-qubit gate on the same
  logical qubit (they execute right before it, after its SWAPs); leftovers
  (after the last two-qubit gate on a qubit, or on qubits with none) execute
  at the very end on the final layout (see ``contract.build_plan``);
- the objective is one scalar ``sum(-ln f)`` over all executed gates at their
  physical location (no per-wire error attribution: qubits are entangled);
  ``calc_goal_function`` returns ``None`` for infeasible solutions (a
  two-qubit gate whose endpoints are not adjacent).

The default model is deterministic synthetic placeholder data; swap it for
real IQM calibration values when available.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag

from qtrans.arch import ODRA5_EDGES, ODRA5_NUM_QUBITS
from qtrans.contract import (
    RoutingProblem,
    RoutingSolution,
    build_plan,
    execution_steps,
)

# SWAP choice per two-qubit interaction: 0 = none, 1..4 = the four star edges.
EDGE_SWAPS: tuple[tuple[int, int], ...] = ODRA5_EDGES

# 1Q ops that are not part of the routed unitary (not charged fidelity).
_SKIP_1Q = frozenset({"measure", "reset", "barrier"})


def _neg_log(f: float) -> float:
    return -math.log(f)


@dataclass(frozen=True)
class FidelityModel:
    """Per-wire and per-edge fidelities for the ODRA5 star.

    ``one_qubit[q]`` is the fidelity of a single-qubit gate on physical qubit
    ``q``; ``two_qubit[(a, b)]`` the fidelity of a two-qubit gate on the
    undirected edge ``(a, b)`` (keys stored with ``a < b``). Fidelities are
    probabilities in (0, 1).
    """

    one_qubit: tuple[float, ...]
    two_qubit: dict[tuple[int, int], float]

    def __post_init__(self) -> None:
        if len(self.one_qubit) != ODRA5_NUM_QUBITS:
            raise ValueError(
                f"one_qubit must have {ODRA5_NUM_QUBITS} entries, got {len(self.one_qubit)}"
            )
        for q, f in enumerate(self.one_qubit):
            if not 0.0 < f < 1.0:
                raise ValueError(f"fidelity of qubit {q} out of (0,1): {f}")
        expected = {tuple(sorted(e)) for e in ODRA5_EDGES}
        got: set[tuple[int, int]] = set()
        for key, f in self.two_qubit.items():
            if len(key) != 2:
                raise ValueError(f"two_qubit key must be a pair, got {key}")
            if not 0.0 < f < 1.0:
                raise ValueError(f"fidelity of edge {key} out of (0,1): {f}")
            got.add(tuple(sorted(key)))
        if got != expected:
            raise ValueError(
                f"two_qubit must cover exactly the ODRA5 edges {sorted(expected)}, got {sorted(got)}"
            )

    def cost_1q(self, q: int) -> float:
        return _neg_log(self.one_qubit[q])

    def cost_2q(self, a: int, b: int) -> float:
        key = (a, b) if a < b else (b, a)
        return _neg_log(self.two_qubit[key])

    def cost_swap(self, a: int, b: int) -> float:
        """A SWAP decomposes to 3 CZ on the star (native_cz_cost convention)."""
        return 3.0 * self.cost_2q(a, b)


def odra5_default_fidelity(*, seed: int = 0) -> FidelityModel:
    """Deterministic synthetic fidelity model (placeholder for real IQM data).

    Values are spread enough that routing choices matter: single-qubit
    fidelities around 0.99, two-qubit around 0.95, distinct per wire/edge.
    """
    rng = random.Random(seed)
    one_qubit = tuple(0.995 - 0.004 * rng.random() for _ in range(ODRA5_NUM_QUBITS))
    two_qubit = {tuple(sorted(e)): 0.97 - 0.025 * rng.random() for e in ODRA5_EDGES}
    return FidelityModel(one_qubit=one_qubit, two_qubit=two_qubit)


def fidelity_cost(circuit: QuantumCircuit, model: FidelityModel) -> float:
    """Total -ln(fidelity) of a routed circuit (any source).

    1Q gates cost on their physical wire, 2Q gates on their edge, SWAP nodes
    cost 3 two-qubit gates (the Qiskit preset expands SWAP into CZ, which
    costs the same 3 * edge cost). Measure/reset/barrier are ignored.
    """
    dag = circuit_to_dag(circuit)
    total = 0.0
    for node in dag.op_nodes():
        if len(node.qargs) == 1:
            if node.op.name in _SKIP_1Q:
                continue
            total += model.cost_1q(node.qargs[0]._index)
        elif len(node.qargs) == 2:
            a = node.qargs[0]._index
            b = node.qargs[1]._index
            if node.op.name == "swap":
                total += model.cost_swap(a, b)
            else:
                total += model.cost_2q(a, b)
    return total


def solution_cost(
    problem: RoutingProblem,
    solution: RoutingSolution,
    model: FidelityModel,
    plan=None,
) -> float | None:
    """Objective of a RoutingSolution, or None if infeasible.

    Walks the same execution steps that ``apply`` emits (contract.py), so for
    feasible solutions this always equals
    ``fidelity_cost(apply(problem, solution), model)``.
    """
    plan = plan if plan is not None else build_plan(problem)
    cm = problem.coupling_map
    total = 0.0
    for step in execution_steps(problem, solution, plan):
        kind = step[0]
        if kind == "swap":
            _, pa, pb = step
            total += model.cost_swap(pa, pb)
        elif kind == "1q":
            _, _, wire = step
            total += model.cost_1q(wire)
        elif kind == "2q":
            _, _, pa, pb = step
            if cm.distance(pa, pb) > 1:
                return None
            total += model.cost_2q(pa, pb)
    return total


def solution_from_encoding(
    problem: RoutingProblem,
    encoding: tuple[tuple[int, ...], tuple[int, ...], tuple[bool, ...]],
    plan=None,
) -> RoutingSolution:
    """Build the RoutingSolution an encoding evaluates to.

    Shared by the solvers and ``calc_goal_function`` so that the emitted
    solution is always exactly what was evaluated.
    """
    layout, swaps_choices, flags = encoding
    plan = plan if plan is not None else build_plan(problem)
    I = len(plan.interactions)
    if len(swaps_choices) != I:
        raise ValueError(
            f"swaps_choices must have {I} entries, got {len(swaps_choices)}"
        )
    order = plan.execution_order(flags)
    swaps_out = tuple(
        (i, *EDGE_SWAPS[s - 1]) for i, s in enumerate(swaps_choices) if s
    )
    return RoutingSolution(
        initial_layout=tuple(layout),
        swaps=swaps_out,
        gate_order=None if order == tuple(range(I)) else order,
    )


def calc_goal_function(
    problem: RoutingProblem,
    encoding: tuple[tuple[int, ...], tuple[int, ...], tuple[bool, ...]],
    model: FidelityModel,
    plan=None,
) -> float | None:
    """Objective of an encoding, or None if infeasible (expert's calcGoalFunction).

    ``encoding = (initial_layout, swaps_choices, flags)`` where
    ``swaps_choices[i]`` in 0..4 selects ``EDGE_SWAPS`` (0 = no SWAP) before
    interaction ``i`` and ``flags[k]`` toggles the execution order of the two
    two-qubit gates in the k-th two-gate layer (see ``RoutingPlan``).
    """
    plan = plan if plan is not None else build_plan(problem)
    solution = solution_from_encoding(problem, encoding, plan)
    return solution_cost(problem, solution, model, plan)
