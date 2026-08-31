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
    """Virtual->physical initial layout plus SWAP schedule."""

    initial_layout: tuple[int, ...]
    # (before_interaction_index, physical_a, physical_b)
    swaps: tuple[tuple[int, int, int], ...] = ()


def _layout_from_tuple(initial_layout: tuple[int, ...]) -> list[int]:
    return list(initial_layout)


def _swap_positions(pos: list[int], phys_a: int, phys_b: int) -> None:
    va = pos.index(phys_a)
    vb = pos.index(phys_b)
    pos[va], pos[vb] = pos[vb], pos[va]


def positions_at_interaction(
    initial_layout: tuple[int, ...],
    swaps: tuple[tuple[int, int, int], ...],
    interaction_index: int,
) -> list[int]:
    """Virtual qubit i is on physical ``pos[i]`` before interaction ``interaction_index``."""
    pos = _layout_from_tuple(initial_layout)
    for idx, pa, pb in swaps:
        if idx > interaction_index:
            break
        _swap_positions(pos, pa, pb)
    return pos


def apply(problem: RoutingProblem, solution: RoutingSolution) -> QuantumCircuit:
    """Build routed circuit: initial layout + scheduled SWAPs + original gates."""
    n = problem.num_qubits
    if len(solution.initial_layout) != n:
        raise ValueError(f"layout length {len(solution.initial_layout)} != {n} qubits")

    pos = _layout_from_tuple(solution.initial_layout)
    out = QuantumCircuit(n, *problem.circuit.cregs)
    swap_iter = iter(solution.swaps)
    next_swap = next(swap_iter, None)
    interaction_idx = 0

    for node in problem.dag.topological_op_nodes():
        if len(node.qargs) == 2:
            while next_swap is not None and next_swap[0] == interaction_idx:
                _, pa, pb = next_swap
                out.swap(pa, pb)
                _swap_positions(pos, pa, pb)
                next_swap = next(swap_iter, None)
            va = _virtual_index(node.qargs[0])
            vb = _virtual_index(node.qargs[1])
            out.append(node.op, [pos[va], pos[vb]], node.cargs)
            interaction_idx += 1
        elif len(node.qargs) == 1:
            va = _virtual_index(node.qargs[0])
            out.append(node.op, [pos[va]], node.cargs)
        else:
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

    for i, (va, vb) in enumerate(problem.interactions):
        pos = positions_at_interaction(layout, solution.swaps, i)
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
