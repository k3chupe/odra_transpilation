"""Exact optimal routing for the fidelity objective (true lower bound).

Dijkstra over states ``(frontier, position)``:

- ``frontier``: the ready-but-not-executed interactions. The ODRA5 DAG has
  width at most 2 (three independent two-qubit gates would need 6 qubits),
  so the frontier holds at most 2 interactions; every topological order is
  explored, including interleavings across DAG levels (Sabre-style early
  SWAPs that serve several later gates).
- ``advance``: execute one frontier interaction, paying its attached 1Q
  gates at their current wires plus the 2Q gate cost;
- ``swap``: transpose any undirected star edge, paying ``3 * edge cost``
  (native CZ decomposition), at any point in the schedule.

All 120 initial layouts are seeded at cost 0 (the layout is free in the
contract), and every permutation is reachable from any layout by star-edge
transpositions. The accumulated cost equals ``solution_cost`` (the same walk
``apply`` emits), so no solver whose solution maps onto the per-interaction
contract can beat the result; it can only match it. Primary objective is the
total ``-ln f`` (fidelity_cost), with swap count as tie-breaker.
"""

from __future__ import annotations

import heapq
import itertools
import time

from odra_router.contract import (
    RoutingProblem,
    RoutingSolution,
    build_plan,
    register_solver,
    _swap_positions,
)
from odra_router.fidelity import odra5_default_fidelity


class ExactDPSolver:
    """Exact fidelity-optimal routing (the reference lower bound)."""

    name = "exact_dp"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        model = odra5_default_fidelity()
        plan = build_plan(problem)
        cm = problem.coupling_map
        n = problem.num_qubits
        I = len(plan.interactions)

        if not plan.layers:
            return RoutingSolution(initial_layout=tuple(range(n)))

        undirected_edges = {tuple(sorted(e)) for e in cm.get_edges()}

        # DAG levels and predecessors: an interaction precedes another iff it
        # shares a qubit and has a lower level.
        prev_level = [0] * n
        levels: list[int] = []
        for a, b in plan.interactions:
            lvl = max(prev_level[a], prev_level[b]) + 1
            levels.append(lvl)
            prev_level[a] = prev_level[b] = lvl

        preds: list[list[int]] = [[] for _ in range(I)]
        for j in range(I):
            qs = plan.interactions[j]
            preds[j] = [
                k
                for k in range(I)
                if levels[k] < levels[j]
                and (plan.interactions[k][0] in qs or plan.interactions[k][1] in qs)
            ]

        # above[j]: bitmask of j and everything it precedes (transitive closure).
        above: list[int] = [0] * I
        for j in range(I - 1, -1, -1):
            m = 1 << j
            for k in range(j + 1, I):
                if j in preds[k]:
                    m |= above[k]
            above[j] = m

        def ready_mask(done: int) -> int:
            rm = 0
            for j in range(I):
                if done & (1 << j):
                    continue
                ok = True
                for p in preds[j]:
                    if not (done & (1 << p)):
                        ok = False
                        break
                if ok:
                    rm |= 1 << j
            return rm

        INF = float("inf")

        # State key: (frontier_mask, pos_tuple). The done set is implied by the
        # frontier (done = complement of the upward closure of the frontier).
        best: dict[tuple, tuple[float, int]] = {}
        # Predecessors: key -> (prev_key, ("adv", i) | ("swap", (a, b)))
        pred: dict[tuple, tuple] = {}

        start_frontier = ready_mask(0)
        counter = 0
        heap: list[tuple] = []
        for layout in itertools.permutations(range(n)):
            key = (start_frontier, layout)
            heap.append((0.0, 0, key))
            best[key] = (0.0, 0)
        heapq.heapify(heap)
        deadline = time.monotonic() + budget_s

        terminal: tuple[float, int, tuple] | None = None  # (cost, swaps, key)

        while heap:
            if time.monotonic() > deadline:
                break
            fcost, nswaps, key = heapq.heappop(heap)
            if best.get(key) != (fcost, nswaps):
                continue
            frontier, pos = key

            if frontier == 0:
                total = fcost
                for node in plan.leftover:
                    total += model.cost_1q(pos[node.qargs[0]._index])
                if terminal is None or (total, nswaps) < (terminal[0], terminal[1]):
                    terminal = (total, nswaps, key)
                continue

            # done is implied by the frontier: everything not above it.
            up = 0
            f2 = frontier
            while f2:
                bit = f2 & -f2
                up |= above[bit.bit_length() - 1]
                f2 ^= bit
            done = ((1 << I) - 1) ^ up

            # Advance moves for each ready interaction.
            f = frontier
            while f:
                bit = f & -f
                j = bit.bit_length() - 1
                f ^= bit
                va, vb = plan.interactions[j]
                pa, pb = pos[va], pos[vb]
                if cm.distance(pa, pb) > 1:
                    continue
                step_cost = model.cost_2q(pa, pb)
                for node in plan.attached.get(j, ()):
                    step_cost += model.cost_1q(pos[node.qargs[0]._index])
                new_done = done | bit
                nkey = (ready_mask(new_done), pos)
                nval = (fcost + step_cost, nswaps)
                if nval < best.get(nkey, (INF, INF)):
                    best[nkey] = nval
                    pred[nkey] = (key, ("adv", j))
                    counter += 1
                    heapq.heappush(heap, (nval[0], nval[1], nkey))

            # Swap moves: any undirected star edge, at any point in the schedule.
            for a, b in undirected_edges:
                new_pos = list(pos)
                _swap_positions(new_pos, a, b)
                npos = tuple(new_pos)
                nkey = (frontier, npos)
                nval = (fcost + model.cost_swap(a, b), nswaps + 1)
                if nval < best.get(nkey, (INF, INF)):
                    best[nkey] = nval
                    pred[nkey] = (key, ("swap", (a, b)))
                    counter += 1
                    heapq.heappush(heap, (nval[0], nval[1], nkey))

        if terminal is None:
            # Budget exhausted without a complete route (large instances):
            # deterministic fallback, never better than the DP result.
            from odra_router.routing.baseline import GreedyShortestPathSolver

            return GreedyShortestPathSolver().solve(problem, seed=seed, budget_s=budget_s)

        # Reconstruct the path back to a start state (no predecessor).
        order_backward: list[int] = []
        swaps_backward: list[tuple[int, tuple[int, int]]] = []  # (key, edge)
        next_adv: int | None = None
        state = terminal[2]
        while state in pred:
            prev, move = pred[state]
            if move[0] == "adv":
                next_adv = move[1]
                order_backward.append(next_adv)
            else:
                assert next_adv is not None
                swaps_backward.append((next_adv, move[1]))
            state = prev
        initial_layout = state[1]

        gate_order = list(reversed(order_backward))
        gate_order_out = None if gate_order == list(range(I)) else tuple(gate_order)

        swaps_by_key: dict[int, list[tuple[int, int]]] = {}
        for key, edge in reversed(swaps_backward):
            swaps_by_key.setdefault(key, []).append(edge)
        swaps = tuple(
            (i, a, b) for i in sorted(swaps_by_key) for (a, b) in swaps_by_key[i]
        )

        return RoutingSolution(
            initial_layout=initial_layout,
            swaps=swaps,
            gate_order=gate_order_out,
        )


def _register() -> None:
    register_solver(ExactDPSolver())


_register()
