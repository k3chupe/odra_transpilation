"""Fidelity-aware move-based tabu search (phase 3, strengthened).

Searches the space suggested by the expert: an initial layout, per
two-qubit interaction a SWAP choice (0..4 over the star edges), and a full
topological order of the interactions (not just per-layer flags: independent
gates may interleave across DAG levels, which is exactly the freedom Sabre's
lookahead exploits). The objective is total -ln(fidelity) over the routed
circuit; infeasible encodings score None and are skipped.

Neighbourhood (one random move per iteration):

1. transpose two positions of the initial layout (re-greedy SWAPs),
2. change the SWAP choice of a random interaction,
3. swap two adjacent independent interactions in the execution order
   (re-greedy SWAPs under the new order),
4. diversification: re-route with a fresh random topological order.

A deterministic best-improvement descent polishes the best solution to a
local optimum over all single moves *and* evaluation-capped pair SWAP choice
changes before returning (single moves cannot leave a minimum that needs two
choices changed at once, e.g. the medium_1 gap to exact_dp).

Registered variants:

- ``tabu_fidelity``: warm start from greedy routing of a *random* layout;
- ``tabu_fidelity_greedy``: warm start from greedy routing of the identity
  layout (never worse than its own warm start; the search only accepts
  improvements);
- ``tabu_fidelity_sabre``: warm start from the layout a single Qiskit Sabre
  run picks;
- ``brute_fidelity_layout``: reference, best fidelity over all 120 layouts
  with greedy SWAP routing (layout-level baseline, not the full move space).
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
    odra5_default_fidelity,
    solution_cost,
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


def _greedy_choices(
    problem: RoutingProblem,
    layout: list[int],
    plan,
    order: tuple[int, ...],
) -> list[int]:
    """Greedy per-interaction SWAP choices for ``layout`` under ``order``.

    When both endpoints of an interaction sit on leaves, the endpoint with
    more *remaining* interactions (from this point of the order onward) is
    brought to the center: a Sabre-style lookahead that keeps the busiest
    qubit central instead of always routing the first endpoint.
    """
    pos = list(layout)
    cm = problem.coupling_map
    degrees = [0] * problem.num_qubits
    for a, b in cm.get_edges():
        degrees[a] += 1
        degrees[b] += 1
    center = max(range(problem.num_qubits), key=lambda q: degrees[q])
    order_list = list(order)
    choices = [0] * len(plan.interactions)

    for idx, j in enumerate(order_list):
        va, vb = plan.interactions[j]
        pa, pb = pos[va], pos[vb]
        if cm.distance(pa, pb) <= 1:
            continue
        if pa != center and pb != center:
            rem_a = sum(1 for k in order_list[idx + 1:] if va in plan.interactions[k])
            rem_b = sum(1 for k in order_list[idx + 1:] if vb in plan.interactions[k])
            edge = (pb, center) if rem_b > rem_a else (pa, center)
        else:
            edge = (pa, center) if pa != center else (pb, center)
        for s, e in enumerate(EDGE_SWAPS, start=1):
            if e == edge or e == (edge[1], edge[0]):
                choices[j] = s
                break
        else:
            raise AssertionError(f"greedy SWAP {edge} not a star edge")
        _swap_positions(pos, edge[0], edge[1])
    return choices


def _random_topological_order(plan, rng: random.Random) -> tuple[int, ...]:
    """Kahn's algorithm with random tie-breaking: a random DAG-valid order."""
    I = len(plan.interactions)
    qubits = [set(plan.interactions[i]) for i in range(I)]
    preds: list[list[int]] = [[] for _ in range(I)]
    indeg = [0] * I
    for j in range(I):
        for k in range(I):
            if k != j and qubits[k] & qubits[j] and k < j:
                preds[j].append(k)
                indeg[j] += 1
    ready = [j for j in range(I) if indeg[j] == 0]
    order: list[int] = []
    while ready:
        idx = rng.randrange(len(ready))
        j = ready.pop(idx)
        order.append(j)
        for k in range(I):
            if j in preds[k]:
                indeg[k] -= 1
                if indeg[k] == 0:
                    ready.append(k)
    return tuple(order)


def _independent(plan, a: int, b: int) -> bool:
    qa = set(plan.interactions[a])
    qb = set(plan.interactions[b])
    return not (qa & qb)


def _solution_from(problem, plan, layout, choices, order) -> RoutingSolution:
    I = len(plan.interactions)
    swaps = tuple(
        (i, *EDGE_SWAPS[s - 1]) for i, s in enumerate(choices) if s
    )
    order_out = None if order == tuple(range(I)) else tuple(order)
    return RoutingSolution(
        initial_layout=tuple(layout),
        swaps=swaps,
        gate_order=order_out,
    )


class TabuFidelitySolver:
    """Move-based tabu over (layout, SWAP choices, topological order)."""

    name = "tabu_fidelity"

    def __init__(
        self,
        *,
        warm_start: str = "random",
        name: str | None = None,
        fidelity: FidelityModel | None = None,
        tenure: int = 8,
        max_iterations: int = 6000,
        stagnation_limit: int = 500,
        polish: bool = True,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
        self.fidelity = fidelity
        self.tenure = tenure
        self.max_iterations = max_iterations
        self.stagnation_limit = stagnation_limit
        self.polish = polish

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
        I = len(plan.interactions)
        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        evals = 0

        def cost(layout, choices, order) -> float | None:
            nonlocal evals
            evals += 1
            return solution_cost(
                problem, _solution_from(problem, plan, layout, choices, order), model, plan
            )

        # Warm start: greedy routing (always feasible) of the identity, of a
        # random layout, or of the layout a single Sabre run picks; DAG order.
        if self.warm_start == "greedy":
            start_layout = list(range(n))
        elif self.warm_start == "sabre":
            from odra_router.routing.tabu import _sabre_initial_layout

            warm = _sabre_initial_layout(problem, seed)
            start_layout = warm if warm is not None else rng.sample(range(n), n)
        else:
            start_layout = rng.sample(range(n), n)
        current_order = tuple(range(I))
        current_layout = list(start_layout)
        current_choices = _greedy_choices(problem, current_layout, plan, current_order)
        current_cost = cost(current_layout, current_choices, current_order)
        assert current_cost is not None  # greedy routing is always feasible

        best_layout, best_choices, best_order = (
            list(current_layout),
            list(current_choices),
            current_order,
        )
        best_cost = current_cost

        # tabu[(move_type, *attrs)] = iteration until which the move is forbidden.
        tabu: dict[tuple, int] = {}
        last_improvement = 0

        for iteration in range(1, self.max_iterations + 1):
            if time.monotonic() > deadline:
                break

            # Diversification: restart from the best solution with a fresh
            # random topological order (Sabre-style lookahead exploration).
            if iteration - last_improvement > self.stagnation_limit:
                current_layout = list(best_layout)
                current_order = _random_topological_order(plan, rng)
                current_choices = _greedy_choices(problem, current_layout, plan, current_order)
                current_cost = cost(current_layout, current_choices, current_order)
                tabu.clear()
                last_improvement = iteration
                continue

            # One random move among the applicable types.
            types = [0, 2]
            if I > 1:
                types.append(3)
            move_type = rng.choice(types)

            if move_type == 0:
                i, j = rng.sample(range(n), 2)
                cand_layout = list(current_layout)
                cand_layout[i], cand_layout[j] = cand_layout[j], cand_layout[i]
                cand_choices = _greedy_choices(problem, cand_layout, plan, current_order)
                cand_order = current_order
                move_key = (0, i, j)
            elif move_type == 2:
                i = rng.randrange(I)
                cand_choices = list(current_choices)
                cand_choices[i] = (cand_choices[i] + rng.randrange(1, 5)) % 5
                cand_layout, cand_order = current_layout, current_order
                move_key = (2, i)
            else:
                k = rng.randrange(I - 1)
                a, b = current_order[k], current_order[k + 1]
                if not _independent(plan, a, b):
                    continue
                cand_order = list(current_order)
                cand_order[k], cand_order[k + 1] = cand_order[k + 1], cand_order[k]
                cand_order = tuple(cand_order)
                cand_choices = _greedy_choices(problem, current_layout, plan, cand_order)
                cand_layout = current_layout
                move_key = (3, k)

            c = cost(cand_layout, cand_choices, cand_order)
            if c is None:
                continue  # infeasible encoding, skip
            is_tabu = tabu.get(move_key, -1) >= iteration
            # Aspiration: a tabu move is accepted only if it improves the best.
            if is_tabu and c >= best_cost:
                continue
            current_layout, current_choices, current_order = (
                cand_layout,
                cand_choices,
                cand_order,
            )
            tabu[move_key] = iteration + self.tenure
            if c < best_cost:
                best_cost = c
                best_layout, best_choices, best_order = (
                    list(cand_layout),
                    list(cand_choices),
                    cand_order,
                )
                last_improvement = iteration

        if self.polish:
            best_layout, best_choices, best_order, evals = self._polish(
                problem, plan, model, best_layout, best_choices, best_order, evals
            )

        self.last_evals = evals
        return _solution_from(problem, plan, best_layout, best_choices, best_order)

    def _polish(self, problem, plan, model, layout, choices, order, evals):
        """Best-improvement descent to a local optimum (deterministic).

        Alternates two fixpoints, each only taking strict improvements:

        1. single moves: layout transpositions (re-greedy SWAPs), single SWAP
           choice changes, adjacent independent order swaps;
        2. pair SWAP choice changes: minima that need two choices moved at
           once (measured: the medium_1 gap to exact_dp is a pair-change
           minimum, unreachable by any single move) are escaped by scanning
           interaction pairs with an evaluation cap so large instances stay
           affordable.

        Moves are scanned in a fixed order and only strict improvements are
        taken, so the emitted solution is never worse than the input.
        """
        n = problem.num_qubits
        I = len(plan.interactions)

        def cost(l, c, o) -> float | None:
            nonlocal evals
            evals += 1
            return solution_cost(
                problem, _solution_from(problem, plan, l, c, o), model, plan
            )

        def single_fixpoint(layout, choices, order):
            """Best-improvement descent over all single moves (returns state)."""
            improved = True
            while improved:
                improved = False
                best_cost = cost(layout, choices, order)
                best_move = None

                # 1a. Layout transpositions, re-deriving greedy SWAPs.
                for i in range(n):
                    for j in range(i + 1, n):
                        cand = list(layout)
                        cand[i], cand[j] = cand[j], cand[i]
                        cand_choices = _greedy_choices(problem, cand, plan, order)
                        c = cost(cand, cand_choices, order)
                        if c is not None and c < best_cost:
                            best_cost = c
                            best_move = ("layout", i, j)

                # 1b. SWAP choice changes for single interactions.
                for i in range(I):
                    for s in range(5):
                        if choices[i] == s:
                            continue
                        cand_choices = list(choices)
                        cand_choices[i] = s
                        c = cost(layout, cand_choices, order)
                        if c is not None and c < best_cost:
                            best_cost = c
                            best_move = ("choice", i, s)

                # 1c. Adjacent independent pairs in the order (re-greedy).
                for k in range(I - 1):
                    a, b = order[k], order[k + 1]
                    if not _independent(plan, a, b):
                        continue
                    cand_order = list(order)
                    cand_order[k], cand_order[k + 1] = cand_order[k + 1], cand_order[k]
                    cand_order = tuple(cand_order)
                    cand_choices = _greedy_choices(problem, layout, plan, cand_order)
                    c = cost(layout, cand_choices, cand_order)
                    if c is not None and c < best_cost:
                        best_cost = c
                        best_move = ("order", k, cand_order)

                if best_move is None:
                    break
                improved = True
                if best_move[0] == "layout":
                    i, j = best_move[1], best_move[2]
                    cand = list(layout)
                    cand[i], cand[j] = cand[j], cand[i]
                    layout = cand
                    choices = _greedy_choices(problem, layout, plan, order)
                elif best_move[0] == "choice":
                    choices = list(choices)
                    choices[best_move[1]] = best_move[2]
                else:
                    order = best_move[2]
                    choices = _greedy_choices(problem, layout, plan, order)
            return layout, choices, order

        layout, choices, order = single_fixpoint(layout, choices, order)

        if I >= 2:
            # Pair-choice fixpoint, evaluation-capped for large instances.
            # Cap: a full scan over pairs is O(I^2 * 24); on dense_1 (I=51)
            # that is ~30k evals per scan, so several scans still fit a
            # benchmark budget.
            max_pair_evals = 25_000
            pair_evals = 0
            while True:
                best_cost = cost(layout, choices, order)
                best_pair = None
                spent = 0
                for i in range(I):
                    for j in range(i + 1, I):
                        for si in range(5):
                            for sj in range(5):
                                if si == choices[i] and sj == choices[j]:
                                    continue
                                spent += 1
                                if pair_evals + spent > max_pair_evals:
                                    break
                                cand_choices = list(choices)
                                cand_choices[i] = si
                                cand_choices[j] = sj
                                c = cost(layout, cand_choices, order)
                                if c is not None and c < best_cost:
                                    best_cost = c
                                    best_pair = (i, j, si, sj)
                            if pair_evals + spent > max_pair_evals:
                                break
                        if pair_evals + spent > max_pair_evals:
                            break
                    if pair_evals + spent > max_pair_evals:
                        break
                pair_evals += spent
                if best_pair is None:
                    break
                i, j, si, sj = best_pair
                choices = list(choices)
                choices[i] = si
                choices[j] = sj
                # A pair change can unlock single moves again.
                layout, choices, order = single_fixpoint(layout, choices, order)

        return layout, choices, order, evals


class BruteFidelityLayoutSolver:
    """Baseline: best fidelity over all 120 layouts with greedy SWAP routing."""

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
            layout = list(perm)
            choices = _greedy_choices(problem, layout, plan, tuple(range(len(plan.interactions))))
            evals += 1
            sol = _solution_from(problem, plan, layout, choices, tuple(range(len(plan.interactions))))
            c = solution_cost(problem, sol, model, plan)
            if c is not None and c < best_cost:
                best_cost = c
                best = sol

        self.last_evals = evals
        return best or _solution_from(
            problem, plan, list(range(n)),
            _greedy_choices(problem, list(range(n)), plan, tuple(range(len(plan.interactions)))),
            tuple(range(len(plan.interactions))),
        )


def _register() -> None:
    register_solver(TabuFidelitySolver(warm_start="random"))
    register_solver(TabuFidelitySolver(warm_start="greedy", name="tabu_fidelity_greedy"))
    register_solver(TabuFidelitySolver(warm_start="sabre", name="tabu_fidelity_sabre"))
    register_solver(BruteFidelityLayoutSolver())


_register()
