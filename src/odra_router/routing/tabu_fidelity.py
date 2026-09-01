"""Fidelity-aware move-based tabu search (phase 3).

Searches the space suggested by the expert: an initial layout plus, per
two-qubit interaction, a SWAP choice (0..4 over the star edges) and, per
two-gate DAG layer, an order flag (which of the two gates executes first).
The objective is total -ln(fidelity) over the routed circuit (see
``fidelity.calc_goal_function``); infeasible encodings score None and are
skipped.

Neighbourhood (one random move per iteration):

1. transpose two positions of the initial layout,
2. flip the order flag of a random two-gate layer,
3. change the SWAP choice of a random interaction to a different value.

Registered variants:

- ``tabu_fidelity``: warm start from greedy routing of a *random* layout;
- ``tabu_fidelity_greedy``: warm start from greedy routing of the identity
  layout (never worse than its own warm start; the search only accepts
  improvements);
- ``brute_fidelity_layout``: reference, best fidelity over all 120 layouts
  with greedy SWAP routing (layout-level lower bound, not the full move space).
"""

from __future__ import annotations

import itertools
import random
import time

from odra_router.contract import (
    RoutingProblem,
    RoutingSolution,
    build_plan,
    register_solver,
    _swap_positions,
)
from odra_router.fidelity import (
    EDGE_SWAPS,
    FidelityModel,
    calc_goal_function,
    odra5_default_fidelity,
    solution_from_encoding,
)


def _greedy_encoding(
    problem: RoutingProblem,
    layout: list[int],
    plan,
    flags: tuple[bool, ...] | None = None,
) -> tuple[list[int], list[int], tuple[bool, ...]]:
    """Encode greedy routing of ``layout`` in *execution* order.

    Walks the layers left to right (order flags ``flags``, all False by
    default, i.e. DAG order within each two-gate layer) and picks, for every
    interaction whose endpoints are not yet adjacent, the shortest-path SWAP:
    bring the first endpoint to the center via its star edge. On the star this
    is exactly one SWAP per non-adjacent interaction, so the result maps to
    per-interaction choices in 1..4 (0 = none) and is feasible by construction
    in the same order.
    """
    pos = list(layout)
    cm = problem.coupling_map
    degrees = [0] * problem.num_qubits
    for a, b in cm.get_edges():
        degrees[a] += 1
        degrees[b] += 1
    center = max(range(problem.num_qubits), key=lambda q: degrees[q])  # star center
    flags = flags if flags is not None else (False,) * plan.flag_count
    swaps = [0] * len(plan.interactions)

    for j in plan.execution_order(flags):
        va, vb = plan.interactions[j]
        pa, pb = pos[va], pos[vb]
        if cm.distance(pa, pb) <= 1:
            continue
        edge = (pa, center) if pa != center else (pb, center)
        for s, e in enumerate(EDGE_SWAPS, start=1):
            if e == edge or e == (edge[1], edge[0]):
                swaps[j] = s
                break
        else:
            raise AssertionError(f"greedy SWAP {edge} not a star edge")
        _swap_positions(pos, edge[0], edge[1])
    return list(layout), swaps, flags


class TabuFidelitySolver:
    """Move-based tabu over (layout, SWAP choices, layer-order flags)."""

    name = "tabu_fidelity"

    def __init__(
        self,
        *,
        warm_start: str = "random",
        name: str | None = None,
        fidelity: FidelityModel | None = None,
        tenure: int = 8,
        max_iterations: int = 5000,
        stagnation_limit: int = 400,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
        self.fidelity = fidelity
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
        model = self.fidelity or odra5_default_fidelity()
        plan = build_plan(problem)
        I = len(problem.interactions)
        F = plan.flag_count
        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        evals = 0

        def cost(layout, swaps, flags) -> float | None:
            nonlocal evals
            evals += 1
            return calc_goal_function(problem, (tuple(layout), tuple(swaps), flags), model, plan)

        # Warm start: greedy routing (always feasible) of the identity or of a
        # random layout, all layer flags False (DAG order).
        if self.warm_start == "greedy":
            start_layout = list(range(n))
        else:
            start_layout = rng.sample(range(n), n)
        current_layout, current_swaps, current_flags = _greedy_encoding(problem, start_layout, plan)
        current_cost = cost(current_layout, current_swaps, current_flags)
        assert current_cost is not None  # greedy routing is always feasible

        best_layout, best_swaps, best_flags = (
            list(current_layout),
            list(current_swaps),
            list(current_flags),
        )
        best_cost = current_cost

        # tabu[(move_type, *attrs)] = iteration until which the move is forbidden.
        tabu: dict[tuple, int] = {}
        last_improvement = 0

        for iteration in range(1, self.max_iterations + 1):
            if time.monotonic() > deadline:
                break

            # Diversification: jump back to the best known solution after a plateau.
            if iteration - last_improvement > self.stagnation_limit:
                current_layout, current_swaps, current_flags = (
                    list(best_layout),
                    list(best_swaps),
                    list(best_flags),
                )
                tabu.clear()
                last_improvement = iteration
                continue

            # One random move: 0 = layout transposition, 1 = order flag flip,
            # 2 = SWAP choice change; sample only among applicable types.
            types = [0]
            if F > 0:
                types.append(1)
            if I > 0:
                types.append(2)
            move_type = rng.choice(types)

            if move_type == 0:
                i, j = rng.sample(range(n), 2)
                cand_layout = list(current_layout)
                cand_layout[i], cand_layout[j] = cand_layout[j], cand_layout[i]
                # Re-derive the greedy SWAP choices for the new layout (with the
                # current order flags): a raw layout transposition would almost
                # always keep stale, infeasible SWAP choices.
                cand_layout, cand_swaps, _ = _greedy_encoding(
                    problem, cand_layout, plan, tuple(current_flags)
                )
                cand_flags = current_flags
                move_key = (0, i, j)
            elif move_type == 1:
                k = rng.randrange(F)
                cand_flags = list(current_flags)
                cand_flags[k] = not cand_flags[k]
                cand_layout, cand_swaps = current_layout, current_swaps
                move_key = (1, k)
            else:
                i = rng.randrange(I)
                cand_swaps = list(current_swaps)
                cand_swaps[i] = (cand_swaps[i] + rng.randrange(1, 5)) % 5
                cand_layout, cand_flags = current_layout, current_flags
                move_key = (2, i)

            c = cost(cand_layout, cand_swaps, cand_flags)
            if c is None:
                continue  # infeasible encoding, skip
            is_tabu = tabu.get(move_key, -1) >= iteration
            # Aspiration: a tabu move is accepted only if it improves the best.
            if is_tabu and c >= best_cost:
                continue
            current_layout, current_swaps, current_flags = (
                cand_layout,
                cand_swaps,
                cand_flags,
            )
            tabu[move_key] = iteration + self.tenure
            if c < best_cost:
                best_cost = c
                best_layout, best_swaps, best_flags = (
                    list(cand_layout),
                    list(cand_swaps),
                    list(cand_flags),
                )
                last_improvement = iteration

        self.last_evals = evals
        return solution_from_encoding(problem, (tuple(best_layout), tuple(best_swaps), tuple(best_flags)), plan)


class BruteFidelityLayoutSolver:
    """Reference: best fidelity over all 120 layouts with greedy SWAP routing."""

    name = "brute_fidelity_layout"

    def __init__(self, *, fidelity: FidelityModel | None = None) -> None:
        self.fidelity = fidelity

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        model = self.fidelity or odra5_default_fidelity()
        plan = build_plan(problem)
        n = problem.num_qubits
        deadline = time.monotonic() + budget_s
        evals = 0
        best: RoutingSolution | None = None
        best_cost = float("inf")

        for perm in itertools.permutations(range(n)):
            if time.monotonic() > deadline:
                break
            layout, swaps, flags = _greedy_encoding(problem, list(perm), plan)
            evals += 1
            c = calc_goal_function(problem, (tuple(layout), tuple(swaps), flags), model, plan)
            if c is not None and c < best_cost:
                best_cost = c
                best = solution_from_encoding(
                    problem, (tuple(layout), tuple(swaps), flags), plan
                )

        self.last_evals = evals
        return best or _route_with_layout(problem, tuple(range(n)))


def _register() -> None:
    register_solver(TabuFidelitySolver(warm_start="random"))
    register_solver(TabuFidelitySolver(warm_start="greedy", name="tabu_fidelity_greedy"))
    register_solver(BruteFidelityLayoutSolver())


_register()
