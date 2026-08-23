"""Exact optimal SWAP schedule for fixed gate order (dynamic programming)."""

from __future__ import annotations

import heapq
import itertools
import time

from qtrans.contract import RoutingProblem, RoutingSolution, register_solver, _swap_positions


def _neighbors(cm, phys: int) -> list[int]:
    return list(cm.neighbors(phys))


def _solve_from_layout(
    problem: RoutingProblem,
    initial_layout: tuple[int, ...],
    deadline: float,
) -> RoutingSolution | None:
    cm = problem.coupling_map
    interactions = problem.interactions
    if not interactions:
        return RoutingSolution(initial_layout=initial_layout)

    start = initial_layout
    counter = 0
    heap: list[tuple[int, int, int, tuple[int, ...], tuple[tuple[int, int, int], ...]]] = [
        (0, counter, 0, start, ())
    ]
    best: dict[tuple[int, tuple[int, ...]], int] = {(0, start): 0}
    best_cost = 10**9
    best_swaps: tuple[tuple[int, int, int], ...] = ()

    while heap:
        if time.monotonic() > deadline:
            return None
        cost, _, idx, pos_t, swaps = heapq.heappop(heap)
        if cost >= best_cost or best.get((idx, pos_t), 10**9) < cost:
            continue

        if idx == len(interactions):
            if cost < best_cost:
                best_cost = cost
                best_swaps = swaps
            continue

        va, vb = interactions[idx]
        pa, pb = pos_t[va], pos_t[vb]
        if cm.distance(pa, pb) <= 1:
            counter += 1
            key = (idx + 1, pos_t)
            if best.get(key, 10**9) > cost:
                best[key] = cost
                heapq.heappush(heap, (cost, counter, idx + 1, pos_t, swaps))
            continue

        pos = list(pos_t)
        for p in _neighbors(cm, pa):
            if p == pb:
                continue
            pos2 = pos.copy()
            _swap_positions(pos2, pa, p)
            pos2_t = tuple(pos2)
            new_swaps = swaps + ((idx, pa, p),)
            new_cost = cost + 1
            key = (idx, pos2_t)
            if best.get(key, 10**9) <= new_cost:
                continue
            best[key] = new_cost
            counter += 1
            heapq.heappush(heap, (new_cost, counter, idx, pos2_t, new_swaps))

    if best_cost >= 10**9:
        return None
    return RoutingSolution(initial_layout=initial_layout, swaps=best_swaps)


class ExactDPSolver:
    """Shortest SWAP path per interaction layer; optimal for fixed gate order.

    ponytail: tries all initial layouts (n!); fine for n=5, not for n>8.
    """

    name = "exact_dp"

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

        for perm in itertools.permutations(range(n)):
            if time.monotonic() > deadline:
                break
            sol = _solve_from_layout(problem, perm, deadline)
            if sol is not None and len(sol.swaps) < best_swaps:
                best_swaps = len(sol.swaps)
                best = sol

        if best is not None:
            return best

        from qtrans.routing.baseline import GreedyShortestPathSolver

        return GreedyShortestPathSolver().solve(problem, seed=seed, budget_s=budget_s)


def _register() -> None:
    register_solver(ExactDPSolver())


_register()
