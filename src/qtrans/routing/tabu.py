"""Tabu search routing solver.

Searches over initial layouts (virtual -> physical permutations) with a
deterministic greedy SWAP schedule per layout, using a tabu list over layout
transpositions to escape local optima. See docs/contract.md.
"""

from __future__ import annotations

import random
import time

from qtrans.contract import RoutingProblem, RoutingSolution, register_solver
from qtrans.routing.baseline import _route_with_layout  # ponytail: reuse shared greedy router


class TabuSearchSolver:
    """Tabu search over layouts; the SWAP schedule is greedy per layout.

    ponytail: the neighbourhood is transpositions of the layout only. On the
    ODRA5 star one SWAP per non-adjacent interaction is optimal for a fixed
    layout, so the layout alone determines the swap count; searching
    swap-sequence moves too is a future extension.
    """

    name = "tabu_search"

    def __init__(
        self,
        *,
        tenure: int = 4,
        max_iterations: int = 2000,
        stagnation_limit: int = 200,
    ) -> None:
        self.tenure = tenure
        self.max_iterations = max_iterations
        self.stagnation_limit = stagnation_limit

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        n = problem.num_qubits
        if not problem.interactions:
            return RoutingSolution(initial_layout=tuple(range(n)))

        deadline = time.monotonic() + budget_s
        rng = random.Random(seed)

        # Deterministic fallback: greedy on identity layout (always valid).
        best = _route_with_layout(problem, tuple(range(n)))
        best_cost = len(best.swaps)

        current = rng.sample(range(n), n)
        current_sol = _route_with_layout(problem, tuple(current))
        if len(current_sol.swaps) < best_cost:
            best = current_sol
            best_cost = len(current_sol.swaps)

        # tabu[(i, j)] = iteration until which transposing layout positions i,j is forbidden.
        tabu: dict[tuple[int, int], int] = {}
        last_improvement = 0

        for iteration in range(1, self.max_iterations + 1):
            if time.monotonic() > deadline:
                break

            # Diversification: random restart after a long plateau.
            if iteration - last_improvement > self.stagnation_limit:
                current = rng.sample(range(n), n)
                current_sol = _route_with_layout(problem, tuple(current))
                if len(current_sol.swaps) < best_cost:
                    best = current_sol
                    best_cost = len(current_sol.swaps)
                last_improvement = iteration
                tabu.clear()
                continue

            best_neighbor: list[int] | None = None
            best_neighbor_sol: RoutingSolution | None = None
            best_neighbor_cost = float("inf")
            best_move: tuple[int, int] | None = None

            for i in range(n):
                for j in range(i + 1, n):
                    move = (i, j)
                    cand = current.copy()
                    cand[i], cand[j] = cand[j], cand[i]
                    sol = _route_with_layout(problem, tuple(cand))
                    cost = len(sol.swaps)
                    is_tabu = tabu.get(move, -1) >= iteration
                    # Aspiration: a tabu move is accepted only if it improves
                    # the global best.
                    if is_tabu and cost >= best_cost:
                        continue
                    if cost < best_neighbor_cost:
                        best_neighbor_cost = cost
                        best_neighbor = cand
                        best_neighbor_sol = sol
                        best_move = move

            if best_neighbor is None:
                current = rng.sample(range(n), n)
                continue

            current = best_neighbor
            tabu[best_move] = iteration + self.tenure

            if best_neighbor_cost < best_cost:
                best = best_neighbor_sol
                best_cost = best_neighbor_cost
                last_improvement = iteration

        return best


def _register() -> None:
    register_solver(TabuSearchSolver())


_register()
