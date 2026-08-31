"""Integration contract: solvers return layouts + swaps, never mutate circuits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag, dag_to_circuit
from qiskit.dagcircuit import DAGCircuit
from qiskit.quantum_info import Operator
from qiskit.transpiler import CouplingMap, Layout

from qtrans.arch import odra5_coupling_map


def _virtual_index(qubit) -> int:
    # ponytail: Qiskit 1.2 Qubit exposes register index via _index
    return qubit._index


def _adjacent(cm: CouplingMap, a: int, b: int) -> bool:
    return cm.distance(a, b) <= 1


@dataclass(frozen=True)
class RoutingProblem:
    circuit: QuantumCircuit
    coupling_map: CouplingMap

    @property
    def num_qubits(self) -> int:
        return self.circuit.num_qubits

    @property
    def dag(self) -> DAGCircuit:
        return circuit_to_dag(self.circuit)

    @property
    def interactions(self) -> tuple[tuple[int, int], ...]:
        """Two-qubit gate pairs in DAG topological order (virtual indices)."""
        pairs: list[tuple[int, int]] = []
        for node in self.dag.topological_op_nodes():
            if len(node.qargs) != 2:
                continue
            a, b = _virtual_index(node.qargs[0]), _virtual_index(node.qargs[1])
            pairs.append((a, b))
        return tuple(pairs)


@dataclass(frozen=True)
class RoutingSolution:
    """Virtual->physical initial layout plus SWAP schedule.

    ``gate_order`` optionally permutes the interaction execution order (e.g.
    two independent two-qubit gates of one DAG layer executed in the other
    order); ``None`` means DAG topological order. Swaps are always keyed by
    interaction index; with a custom order they are applied in execution
    order.
    """

    initial_layout: tuple[int, ...]
    # (before_interaction_index, physical_a, physical_b)
    swaps: tuple[tuple[int, int, int], ...] = ()
    gate_order: tuple[int, ...] | None = None


def _layout_from_tuple(initial_layout: tuple[int, ...]) -> list[int]:
    return list(initial_layout)


def _swap_positions(pos: list[int], phys_a: int, phys_b: int) -> None:
    va = pos.index(phys_a)
    vb = pos.index(phys_b)
    pos[va], pos[vb] = pos[vb], pos[va]


# One-qubit ops that are not part of the routed unitary: they neither attach to
# a two-qubit gate nor are charged fidelity (measure/reset/barrier).
_SKIP_1Q = frozenset({"measure", "reset", "barrier"})


@dataclass
class RoutingPlan:
    """Precomputed scheduling structure of a RoutingProblem.

    ``layers`` groups two-qubit interaction indices by DAG level (a level holds
    0, 1 or 2 interactions on the 5-qubit star, since 3 would need 6 disjoint
    qubits); ``flag_count`` counts the levels with exactly 2 interactions, the
    only places where gate order is a free decision. ``attached[i]`` lists the
    single-qubit nodes that execute right before interaction ``i`` (all 1Q
    gates on its qubits since the previous 2Q gate on each), ``leftover`` the
    1Q nodes after the last 2Q gate on their qubit (executed at the very end),
    ``other`` the remaining nodes (measure/reset/barrier, multi-qubit ops) and
    ``two_qubit_nodes[i]`` the DAG node of interaction ``i`` and
    ``interactions`` the cached interaction pairs (``problem.interactions``
    rebuilds the DAG on every access, which is too slow for per-evaluation
    loops).
    """

    layers: tuple[tuple[int, ...], ...]
    attached: dict[int, tuple]
    leftover: tuple
    other: tuple
    two_qubit_nodes: dict[int, object]
    interactions: tuple[tuple[int, int], ...]

    @property
    def flag_count(self) -> int:
        return sum(1 for layer in self.layers if len(layer) == 2)

    def execution_order(self, flags: tuple[bool, ...]) -> tuple[int, ...]:
        """Interaction indices in execution order given per-2-gate-layer flags."""
        if len(flags) != self.flag_count:
            raise ValueError(f"expected {self.flag_count} flags, got {len(flags)}")
        order: list[int] = []
        f = 0
        for layer in self.layers:
            if len(layer) == 2:
                order.extend(reversed(layer) if flags[f] else layer)
                f += 1
            else:
                order.extend(layer)
        return tuple(order)


def build_plan(problem: RoutingProblem) -> RoutingPlan:
    """Levels of 2Q interactions + 1Q attachment (C2 scheduling convention).

    Single-qubit gates are attached to the *next* two-qubit gate on the same
    logical qubit (they execute right before it, after its SWAPs); gates after
    the last two-qubit gate on their qubit (or on qubits with none) become
    ``leftover`` and execute at the very end on the final layout.
    """
    dag = problem.dag
    n = problem.num_qubits
    pending: dict[int, list] = {q: [] for q in range(n)}
    attached: dict[int, tuple] = {}
    leftover: list = []
    other: list = []
    prev_level = [0] * n
    level_of_interaction: dict[int, int] = {}
    two_qubit_nodes: dict[int, object] = {}
    interaction_index = 0

    for node in dag.topological_op_nodes():
        qs = [_virtual_index(q) for q in node.qargs]
        if not qs:
            continue
        lvl = max(prev_level[q] for q in qs) + 1
        for q in qs:
            prev_level[q] = lvl
        if len(qs) == 2:
            attached[interaction_index] = tuple(pending[qs[0]] + pending[qs[1]])
            pending[qs[0]].clear()
            pending[qs[1]].clear()
            level_of_interaction[interaction_index] = lvl
            two_qubit_nodes[interaction_index] = node
            interaction_index += 1
        elif len(qs) == 1 and node.op.name not in _SKIP_1Q:
            pending[qs[0]].append(node)
        else:
            other.append(node)

    for q in range(n):
        leftover.extend(pending[q])

    by_level: dict[int, list[int]] = {}
    for i, lvl in level_of_interaction.items():
        by_level.setdefault(lvl, []).append(i)
    layers = tuple(tuple(by_level[l]) for l in sorted(by_level))

    return RoutingPlan(
        layers=layers,
        attached=attached,
        leftover=tuple(leftover),
        other=tuple(other),
        two_qubit_nodes=two_qubit_nodes,
        interactions=tuple(problem.interactions),
    )


def execution_steps(problem: RoutingProblem, solution: RoutingSolution, plan: RoutingPlan | None = None):
    """Yield the routed circuit's operations in execution order.

    Yields ``("swap", pa, pb)``, ``("1q", node, physical_wire)``,
    ``("2q", node, pa, pb)``, ``("measure", node, physical_wire)`` (mapped 1Q
    ops that are not part of the unitary) and ``("other", node)``. ``apply``
    and the fidelity objective both consume this iterator, so they always
    agree on placement.
    """
    plan = plan if plan is not None else build_plan(problem)
    I = len(plan.interactions)
    order = solution.gate_order if solution.gate_order is not None else tuple(range(I))
    if sorted(order) != list(range(I)):
        raise ValueError(f"gate_order must be a permutation of 0..{I-1}, got {order}")
    pos = _layout_from_tuple(solution.initial_layout)

    # Group SWAPs by interaction index so the walk is O(interactions + swaps),
    # not O(interactions * swaps).
    swaps_by_idx: dict[int, list[tuple[int, int]]] = {}
    for idx, pa, pb in solution.swaps:
        swaps_by_idx.setdefault(idx, []).append((pa, pb))

    for j in order:
        for pa, pb in swaps_by_idx.get(j, ()):
            yield ("swap", pa, pb)
            _swap_positions(pos, pa, pb)
        for node in plan.attached.get(j, ()):
            q = _virtual_index(node.qargs[0])
            yield ("1q", node, pos[q])
        va, vb = plan.interactions[j]
        node = plan.two_qubit_nodes[j]
        yield ("2q", node, pos[va], pos[vb])

    for node in plan.leftover:
        q = _virtual_index(node.qargs[0])
        yield ("1q", node, pos[q])
    for node in plan.other:
        if len(node.qargs) == 1:
            q = _virtual_index(node.qargs[0])
            yield ("measure", node, pos[q])
        else:
            yield ("other", node)


def positions_at_interaction(
    initial_layout: tuple[int, ...],
    swaps: tuple[tuple[int, int, int], ...],
    interaction_index: int,
    gate_order: tuple[int, ...] | None = None,
) -> list[int]:
    """Virtual qubit i is on physical ``pos[i]`` before interaction ``interaction_index``.

    With ``gate_order`` the swaps are applied in execution order (interactions
    may execute out of DAG order); without it, in swap-list (DAG) order. In
    both cases the SWAPs of the interaction itself are applied, matching the
    gate executing after its own SWAPs.
    """
    pos = _layout_from_tuple(initial_layout)
    if gate_order is None:
        for idx, pa, pb in swaps:
            if idx > interaction_index:
                break
            _swap_positions(pos, pa, pb)
    else:
        for j in gate_order:
            for idx, pa, pb in swaps:
                if idx == j:
                    _swap_positions(pos, pa, pb)
            if j == interaction_index:
                break
    return pos


def apply(problem: RoutingProblem, solution: RoutingSolution) -> QuantumCircuit:
    """Build routed circuit from the execution plan (layout + SWAPs + gate order).

    Single-qubit gates follow their logical qubit through SWAPs: gates before
    the next two-qubit gate on the same qubit execute right before it (after
    its SWAPs), leftovers at the very end. Logical equivalence to the input
    circuit is preserved (a 1Q gate commutes with a SWAP on the same wires up
    to wire labels).
    """
    n = problem.num_qubits
    if len(solution.initial_layout) != n:
        raise ValueError(f"layout length {len(solution.initial_layout)} != {n} qubits")

    out = QuantumCircuit(n, *problem.circuit.cregs)
    plan = build_plan(problem)
    for step in execution_steps(problem, solution, plan):
        kind = step[0]
        if kind == "swap":
            _, pa, pb = step
            out.swap(pa, pb)
        elif kind == "1q":
            _, node, wire = step
            out.append(node.op, [wire], node.cargs)
        elif kind == "2q":
            _, node, pa, pb = step
            out.append(node.op, [pa, pb], node.cargs)
        elif kind == "measure":
            _, node, wire = step
            out.append(node.op, [wire], node.cargs)
        else:  # "other": multi-qubit / barrier / unmapped ops
            _, node = step
            out.append(node.op, node.qargs, node.cargs)

    return out


def validate(problem: RoutingProblem, solution: RoutingSolution) -> None:
    """Raise ValueError if layout/swaps do not route all two-qubit gates."""
    n = problem.num_qubits
    layout = solution.initial_layout
    if len(layout) != n:
        raise ValueError("initial_layout wrong length")
    if sorted(layout) != list(range(n)):
        raise ValueError(f"initial_layout must be a permutation of 0..{n-1}, got {layout}")

    cm = problem.coupling_map
    for idx, pa, pb in solution.swaps:
        if idx < 0 or idx > len(problem.interactions):
            raise ValueError(f"swap index {idx} out of range")
        if not _adjacent(cm, pa, pb):
            raise ValueError(f"swap ({pa},{pb}) not on coupling map")

    if solution.gate_order is not None and sorted(solution.gate_order) != list(range(len(problem.interactions))):
        raise ValueError("gate_order must be a permutation of interaction indices")

    for i, (va, vb) in enumerate(problem.interactions):
        pos = positions_at_interaction(layout, solution.swaps, i, solution.gate_order)
        pa, pb = pos[va], pos[vb]
        if not _adjacent(cm, pa, pb):
            raise ValueError(
                f"interaction {i} virtual ({va},{vb}) -> physical ({pa},{pb}) not connected"
            )


def native_cz_cost(circuit: QuantumCircuit) -> float:
    """Two-qubit gate count in the ODRA5 native ``cz`` basis.

    SWAP decomposes to 3 CZ on the star, CX to 1 CZ; single-qubit rotations are
    ignored. One cost for every solver: the Qiskit preset baseline never emits
    ``swap`` gates (the target has no native SWAP, Qiskit expands it to CZ), so
    its raw swap count would always be 0 and comparisons would be meaningless.
    """
    dag = circuit_to_dag(circuit)
    cost = 0.0
    for node in dag.two_qubit_ops():
        cost += 3.0 if node.op.name == "swap" else 1.0
    return cost


def metrics(problem: RoutingProblem, solution: RoutingSolution) -> dict[str, float]:
    validate(problem, solution)
    routed = apply(problem, solution)
    dag = circuit_to_dag(routed)
    return {
        "swap_count": float(len(solution.swaps)),
        "cz_cost": native_cz_cost(routed),
        "two_qubit_count": float(len(dag.two_qubit_ops())),
        "depth": float(dag.depth()),
        "size": float(dag.size()),
    }


def equivalent(a: QuantumCircuit, b: QuantumCircuit, atol: float = 1e-8) -> bool:
    """Compare unitaries (ignores measurements)."""
    def strip_meas(qc: QuantumCircuit) -> QuantumCircuit:
        dag = circuit_to_dag(qc)
        for node in list(dag.op_nodes()):
            if node.op.name == "measure":
                dag.remove_op_node(node)
        return dag_to_circuit(dag)

    try:
        ua = Operator(strip_meas(a))
        ub = Operator(strip_meas(b))
    except Exception:
        return False
    return ua.equiv(ub, atol=atol)


class Solver(Protocol):
    name: str

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution: ...


SOLVERS: dict[str, Solver] = {}


def register_solver(solver: Solver) -> None:
    SOLVERS[solver.name] = solver


def make_problem(circuit: QuantumCircuit, coupling_map: CouplingMap | None = None) -> RoutingProblem:
    return RoutingProblem(circuit, coupling_map or odra5_coupling_map())


def layout_to_qiskit(initial_layout: tuple[int, ...], circuit: QuantumCircuit) -> Layout:
    """Build Qiskit Layout from virtual->physical tuple."""
    layout = Layout()
    for v, p in enumerate(initial_layout):
        layout[circuit.qubits[v]] = p
    return layout
