"""Tabu search routing solver.

Searches over initial layouts (virtual -> physical permutations) with a
deterministic greedy SWAP schedule per layout, using a tabu list over layout
transpositions to escape local optima. See docs/contract.md.

Two registered variants:
- ``tabu_search``: starts from a random layout.
- ``tabu_sabre_start``: warm-starts from the initial layout a single Sabre
  run chooses (``SabreLayout``), so the search begins in a good region instead
  of wandering the whole space.
"""

from __future__ import annotations

import random
import time

from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import SabreLayout

from qtrans.contract import RoutingProblem, RoutingSolution, register_solver
from qtrans.routing.baseline import _route_with_layout  # ponytail: reuse shared greedy router


def _sabre_initial_layout(problem: RoutingProblem, seed: int) -> list[int] | None:
    """Virtual->physical layout chosen by a single Sabre run, or None on failure."""
    try:
        pm = PassManager([SabreLayout(problem.coupling_map, seed=seed)])
        pm.run(problem.circuit)
        layout = pm.property_set.get("layout")
        if layout is None:
            return None
        perm = [layout.get_virtual_bits()[q] for q in problem.circuit.qubits]
        if sorted(perm) != list(range(problem.num_qubits)):
            return None
        return perm
    except Exception:
        return None


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
        warm_start: str = "random",
        name: str | None = None,
        tenure: int = 4,
        max_iterations: int = 2000,
        stagnation_limit: int = 200,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
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
        evals = 0

        # Deterministic fallback: greedy on identity layout (always valid).
        best = _route_with_layout(problem, tuple(range(n)))
        evals += 1
        best_cost = len(best.swaps)

        if self.warm_start == "sabre":
            warm = _sabre_initial_layout(problem, seed)
            current = warm if warm is not None else rng.sample(range(n), n)
        else:
            current = rng.sample(range(n), n)
        current_sol = _route_with_layout(problem, tuple(current))
        evals += 1
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
                evals += 1
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
                    evals += 1
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

        self.last_evals = evals
        return best


def _register() -> None:
    register_solver(TabuSearchSolver())
    register_solver(TabuSearchSolver(warm_start="sabre", name="tabu_sabre_start"))


_register()
