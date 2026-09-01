"""Baseline routing solvers: brute-force layout search and greedy shortest-path."""

from __future__ import annotations

import itertools
import time

from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import SabreSwap, TrivialLayout

from odra_router.contract import (
    RoutingProblem,
    RoutingSolution,
    register_solver,
    positions_at_interaction,
    _swap_positions,
)


def _shortest_swap_sequence(
    coupling_map,
    pos: list[int],
    va: int,
    vb: int,
) -> list[tuple[int, int]]:
    """SWAPs on physical wires to make virtual ``va`` and ``vb`` neighbors."""
    pa, pb = pos[va], pos[vb]
    if coupling_map.distance(pa, pb) <= 1:
        return []

    path = coupling_map.shortest_undirected_path(pa, pb)
    swaps: list[tuple[int, int]] = []
    for i in range(len(path) - 2):
        w1, w2 = path[i], path[i + 1]
        swaps.append((w1, w2))
        _swap_positions(pos, w1, w2)
    return swaps


def _route_with_layout(problem: RoutingProblem, initial_layout: tuple[int, ...]) -> RoutingSolution:
    pos = list(initial_layout)
    cm = problem.coupling_map
    swaps: list[tuple[int, int, int]] = []

    for idx, (va, vb) in enumerate(problem.interactions):
        for pa, pb in _shortest_swap_sequence(cm, pos, va, vb):
            swaps.append((idx, pa, pb))
    return RoutingSolution(initial_layout=tuple(initial_layout), swaps=tuple(swaps))


class GreedyShortestPathSolver:
    name = "greedy_shortest_path"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        n = problem.num_qubits
        layout = tuple(range(n))
        self.last_evals = 1
        return _route_with_layout(problem, layout)


class BruteForceLayoutSolver:
    name = "brute_force_layout"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        deadline = time.monotonic() + budget_s
        n = problem.num_qubits
        best: RoutingSolution | None = None
        best_swaps = 10**9
        evals = 0

        for perm in itertools.permutations(range(n)):
            if time.monotonic() > deadline:
                break
            evals += 1
            sol = _route_with_layout(problem, perm)
            if len(sol.swaps) < best_swaps:
                best_swaps = len(sol.swaps)
                best = sol

        self.last_evals = evals
        return best or _route_with_layout(problem, tuple(range(n)))


class SabreBaselineSolver:
    name = "sabre_baseline"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        cm = problem.coupling_map
        pm = PassManager([TrivialLayout(cm), SabreSwap(cm, seed=seed)])
        routed = pm.run(problem.circuit)
        layout = pm.property_set.get("layout")
        if layout is None:
            initial = tuple(range(problem.num_qubits))
        else:
            vbits = layout.get_virtual_bits()
            initial = tuple(vbits[q] for q in problem.circuit.qubits)

        from qiskit.converters import circuit_to_dag

        swaps: list[tuple[int, int, int]] = []
        interaction_idx = 0
        pos = list(initial)

        for node in circuit_to_dag(routed).topological_op_nodes():
            if node.op.name == "swap":
                pa = node.qargs[0]._index
                pb = node.qargs[1]._index
                swaps.append((interaction_idx, pa, pb))
                _swap_positions(pos, pa, pb)
            elif len(node.qargs) == 2:
                interaction_idx += 1

        return RoutingSolution(initial_layout=initial, swaps=tuple(swaps))


def _register() -> None:
    register_solver(GreedyShortestPathSolver())
    register_solver(BruteForceLayoutSolver())
    register_solver(SabreBaselineSolver())


_register()
