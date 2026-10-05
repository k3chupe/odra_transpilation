"""Fidelity-aware move-based tabu search (phase 3, strengthened).

Searches the space suggested by the expert: an initial layout, per
two-qubit interaction a SWAP choice (0..4 over the star edges), and
per-layer order flags (which of two independent gates in an ambiguous DAG
layer executes first). The objective is total -ln(fidelity) over the routed
circuit; infeasible encodings score None and are skipped.

Neighbourhood (one random move per iteration, as in the paper):

1. layout transposition, p_layout = 0.40 (re-derive SWAPs),
2. order-flag flip of one ambiguous (two-gate) DAG layer, p_order = 0.20
   (re-derive SWAPs),
3. SWAP choice change of a random interaction, p_swap = 0.40.

SWAPs are re-derived by the lookahead heuristic shared with genetic_fidelity
(``_greedy_choices``: w_d = 1/(d+1), horizon 15). Recency tabu list with
tenure 7 and aspiration (a tabu move is accepted if it beats the best).
Diversification: after ``stagnation_limit`` iterations without improvement,
restart from the best layout with random order flags.

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
from odra_router.arch import ODRA5_NUM_QUBITS
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
        for s, e in enumerate(_edge_list(problem), start=1):
            if e == edge or e == (edge[1], edge[0]):
                swaps[j] = s
                break
        else:
            raise AssertionError(f"greedy SWAP {edge} is not a coupling-map edge")
        _swap_positions(pos, edge[0], edge[1])
    return list(layout), swaps, flags


#: Lookahead horizon of the SWAP heuristic (later interactions scored, w_d decay).
LOOKAHEAD_HORIZON = 15


def _greedy_choices(
    problem: RoutingProblem,
    layout: list[int],
    plan,
    order: tuple[int, ...],
) -> list[int]:
    """Lookahead per-interaction SWAP choices for ``layout`` under ``order``.

    Shared by tabu_fidelity and genetic_fidelity (the paper's "same lookahead
    heuristic"). When both endpoints of a non-adjacent interaction sit on
    leaves, the endpoint with the higher decayed upcoming demand goes to the
    center: each later interaction at distance d >= 0 within
    ``LOOKAHEAD_HORIZON`` adds w_d = 1/(d+1) to the score of the logical qubit
    it uses; ties fall back to the count of all remaining interactions.
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
            score_a = score_b = 0.0
            for d, k in enumerate(order_list[idx + 1:idx + 1 + LOOKAHEAD_HORIZON]):
                w = 1.0 / (d + 1)
                if va in plan.interactions[k]:
                    score_a += w
                if vb in plan.interactions[k]:
                    score_b += w
            if abs(score_a - score_b) < 1e-5:
                score_a = sum(1 for k in order_list[idx + 1:] if va in plan.interactions[k])
                score_b = sum(1 for k in order_list[idx + 1:] if vb in plan.interactions[k])
            edge = (pb, center) if score_b > score_a else (pa, center)
        else:
            edge = (pa, center) if pa != center else (pb, center)
        for s, e in enumerate(_edge_list(problem), start=1):
            if e == edge or e == (edge[1], edge[0]):
                choices[j] = s
                break
        else:
            raise AssertionError(f"greedy SWAP {edge} is not a coupling-map edge")
        _swap_positions(pos, edge[0], edge[1])
    return choices


def _edge_list(problem: RoutingProblem) -> tuple[tuple[int, int], ...]:
    """SWAP choices this solver may use on ``problem``'s coupling map.

    On ODRA5 the historical ``EDGE_SWAPS`` order is kept (choice 1..4 maps onto
    (0,2) (1,2) (2,3) (2,4)), so every result on the target topology is
    unchanged. Other coupling maps (the N-qubit crossover experiment) fall
    back to their undirected edges in a stable sorted order.
    """
    edges = {tuple(sorted(edge)) for edge in problem.coupling_map.get_edges()}
    if problem.num_qubits == ODRA5_NUM_QUBITS and edges == {
        tuple(sorted(edge)) for edge in EDGE_SWAPS
    }:
        return EDGE_SWAPS
    return tuple(sorted(edges))


def _choice_count(problem: RoutingProblem) -> int:
    """SWAP choices per interaction: 0 = none, 1..len(edges) (5 on ODRA5)."""
    return len(_edge_list(problem)) + 1


def _solution_from(problem, plan, layout, choices, order) -> RoutingSolution:
    I = len(plan.interactions)
    edges = _edge_list(problem)
    swaps = tuple(
        (i, *edges[s - 1]) for i, s in enumerate(choices) if s
    )
    order_out = None if order == tuple(range(I)) else tuple(order)
    return RoutingSolution(
        initial_layout=tuple(layout),
        swaps=swaps,
        gate_order=order_out,
    )


class TabuFidelitySolver:
    """Tabu search over (layout, SWAP choices, order flags), as in the paper."""

    name = "tabu_fidelity"

    def __init__(
        self,
        *,
        warm_start: str = "random",
        name: str | None = None,
        fidelity: FidelityModel | None = None,
        tenure: int = 7,
        p_layout: float = 0.40,
        p_order: float = 0.20,
        p_swap: float = 0.40,
        max_iterations: int = 6000,
        stagnation_limit: int = 500,
        polish: bool = True,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
        self.fidelity = fidelity
        self.tenure = tenure
        self.p_layout = p_layout
        self.p_order = p_order
        self.p_swap = p_swap
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
        F = plan.flag_count
        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        evals = 0

        # Budget honesty: polish used to run to its fixpoint regardless of
        # ``budget_s`` (measured: 15.6 s of polishing for a 0.25 s budget on a
        # 270-interaction circuit), which made the budget sweeps meaningless.
        # The deadline is now honoured by the polish scans too.
        self.last_deadline_hit = False
        self._polish_deadline_hit = False

        def cost(layout, choices, flags) -> float | None:
            nonlocal evals
            evals += 1
            order = plan.execution_order(tuple(flags))
            return solution_cost(
                problem, _solution_from(problem, plan, layout, choices, order), model, plan
            )

        def rederive(layout, flags) -> list[int]:
            return _greedy_choices(problem, layout, plan, plan.execution_order(tuple(flags)))

        # Warm start: lookahead routing (always feasible) of a random layout,
        # the identity, or the layout a single Sabre run picks; DAG order.
        if self.warm_start == "greedy":
            start_layout = list(range(n))
        elif self.warm_start == "sabre":
            from odra_router.routing.tabu import _sabre_initial_layout

            warm = _sabre_initial_layout(problem, seed)
            start_layout = warm if warm is not None else rng.sample(range(n), n)
        else:
            start_layout = rng.sample(range(n), n)
        current_flags = (False,) * F
        current_layout = list(start_layout)
        current_choices = rederive(current_layout, current_flags)
        current_cost = cost(current_layout, current_choices, current_flags)
        assert current_cost is not None  # lookahead routing is always feasible

        best_layout, best_choices, best_flags = (
            list(current_layout),
            list(current_choices),
            current_flags,
        )
        best_cost = current_cost

        # Operator probabilities; the order move needs an ambiguous layer.
        p_order = self.p_order if F else 0.0
        p_total = self.p_layout + p_order + self.p_swap

        # tabu[(move_type, *attrs)] = iteration until which the move is forbidden.
        tabu: dict[tuple, int] = {}
        last_improvement = 0

        for iteration in range(1, self.max_iterations + 1):
            if time.monotonic() > deadline:
                self.last_deadline_hit = True
                break

            # Diversification: restart from the best layout with random order
            # flags after ``stagnation_limit`` iterations without improvement.
            if iteration - last_improvement > self.stagnation_limit:
                current_layout = list(best_layout)
                current_flags = tuple(rng.random() < 0.5 for _ in range(F))
                current_choices = rederive(current_layout, current_flags)
                current_cost = cost(current_layout, current_choices, current_flags)
                tabu.clear()
                last_improvement = iteration
                continue

            # One random move: layout (p_layout), order flag (p_order) or
            # SWAP choice (p_swap).
            r = rng.random() * p_total
            if r < self.p_layout:
                i, j = rng.sample(range(n), 2)
                cand_layout = list(current_layout)
                cand_layout[i], cand_layout[j] = cand_layout[j], cand_layout[i]
                cand_flags = current_flags
                cand_choices = rederive(cand_layout, cand_flags)
                move_key = (0, i, j)
            elif r < self.p_layout + p_order:
                k = rng.randrange(F)
                cand_flags = tuple(not f if t == k else f for t, f in enumerate(current_flags))
                cand_layout = current_layout
                cand_choices = rederive(cand_layout, cand_flags)
                move_key = (1, k)
            else:
                i = rng.randrange(I)
                cand_choices = list(current_choices)
                k_choices = _choice_count(problem)
                cand_choices[i] = (cand_choices[i] + rng.randrange(1, k_choices)) % k_choices
                cand_layout, cand_flags = current_layout, current_flags
                move_key = (2, i)

            c = cost(cand_layout, cand_choices, cand_flags)
            if c is None:
                continue  # infeasible encoding, skip
            is_tabu = tabu.get(move_key, -1) >= iteration
            # Aspiration: a tabu move is accepted only if it improves the best.
            if is_tabu and c >= best_cost:
                continue
            current_layout, current_choices, current_flags = (
                cand_layout,
                cand_choices,
                cand_flags,
            )
            tabu[move_key] = iteration + self.tenure
            if c < best_cost:
                best_cost = c
                best_layout, best_choices, best_flags = (
                    list(cand_layout),
                    list(cand_choices),
                    cand_flags,
                )
                last_improvement = iteration

        if self.polish:
            best_layout, best_choices, best_flags, evals = self._polish(
                problem, plan, model, best_layout, best_choices, best_flags, evals,
                deadline=deadline,
            )
            self.last_deadline_hit = self.last_deadline_hit or self._polish_deadline_hit

        self.last_evals = evals
        return _solution_from(
            problem, plan, best_layout, best_choices, plan.execution_order(tuple(best_flags))
        )

    def _polish(self, problem, plan, model, layout, choices, flags, evals, deadline=None):
        """Best-improvement descent to a local optimum (deterministic).

        Alternates two fixpoints, each only taking strict improvements:

        1. single moves: layout transpositions (re-derive SWAPs), single SWAP
           choice changes, order-flag flips (re-derive SWAPs);
        2. pair SWAP choice changes: minima that need two choices moved at
           once are escaped by scanning interaction pairs with an evaluation
           cap so large instances stay affordable.

        Moves are scanned in a fixed order and only strict improvements are
        taken, so the emitted solution is never worse than the input. When
        ``deadline`` is given, the scans stop at it and the best solution found
        so far is returned; ``self._polish_deadline_hit`` records that.
        """
        n = problem.num_qubits
        I = len(plan.interactions)
        F = plan.flag_count

        def out_of_time() -> bool:
            if deadline is not None and time.monotonic() > deadline:
                self._polish_deadline_hit = True
                return True
            return False

        def cost(l, c, f) -> float | None:
            nonlocal evals
            evals += 1
            order = plan.execution_order(tuple(f))
            return solution_cost(
                problem, _solution_from(problem, plan, l, c, order), model, plan
            )

        def rederive(l, f) -> list[int]:
            return _greedy_choices(problem, l, plan, plan.execution_order(tuple(f)))

        def single_fixpoint(layout, choices, flags):
            """Best-improvement descent over all single moves (returns state)."""
            improved = True
            while improved:
                improved = False
                best_cost = cost(layout, choices, flags)
                best_move = None
                timed_out = False

                # 1a. Layout transpositions, re-deriving SWAPs.
                for i in range(n):
                    if out_of_time():
                        timed_out = True
                        break
                    for j in range(i + 1, n):
                        cand = list(layout)
                        cand[i], cand[j] = cand[j], cand[i]
                        c = cost(cand, rederive(cand, flags), flags)
                        if c is not None and c < best_cost:
                            best_cost = c
                            best_move = ("layout", i, j)
                if timed_out:
                    break

                # 1b. SWAP choice changes for single interactions.
                for i in range(I):
                    if out_of_time():
                        timed_out = True
                        break
                    for s in range(_choice_count(problem)):
                        if choices[i] == s:
                            continue
                        cand_choices = list(choices)
                        cand_choices[i] = s
                        c = cost(layout, cand_choices, flags)
                        if c is not None and c < best_cost:
                            best_cost = c
                            best_move = ("choice", i, s)
                if timed_out:
                    break

                # 1c. Order-flag flips, re-deriving SWAPs.
                for k in range(F):
                    if out_of_time():
                        timed_out = True
                        break
                    cand_flags = tuple(not f if t == k else f for t, f in enumerate(flags))
                    c = cost(layout, rederive(layout, cand_flags), cand_flags)
                    if c is not None and c < best_cost:
                        best_cost = c
                        best_move = ("flag", cand_flags)
                if timed_out:
                    break

                if best_move is None:
                    break
                improved = True
                if best_move[0] == "layout":
                    i, j = best_move[1], best_move[2]
                    cand = list(layout)
                    cand[i], cand[j] = cand[j], cand[i]
                    layout = cand
                    choices = rederive(layout, flags)
                elif best_move[0] == "choice":
                    choices = list(choices)
                    choices[best_move[1]] = best_move[2]
                else:
                    flags = best_move[1]
                    choices = rederive(layout, flags)
            return layout, choices, flags

        layout, choices, flags = single_fixpoint(layout, choices, tuple(flags))

        if I >= 2:
            # Pair-choice fixpoint, evaluation-capped for large instances.
            # Cap: a full scan over pairs is O(I^2 * 24); on dense_1 (I=51)
            # that is ~30k evals per scan, so several scans still fit a
            # benchmark budget.
            max_pair_evals = 25_000
            pair_evals = 0
            while True:
                if out_of_time():
                    break
                best_cost = cost(layout, choices, flags)
                best_pair = None
                spent = 0
                for i in range(I):
                    if out_of_time():
                        break
                    for j in range(i + 1, I):
                        for si in range(_choice_count(problem)):
                            for sj in range(_choice_count(problem)):
                                if si == choices[i] and sj == choices[j]:
                                    continue
                                spent += 1
                                if pair_evals + spent > max_pair_evals:
                                    break
                                cand_choices = list(choices)
                                cand_choices[i] = si
                                cand_choices[j] = sj
                                c = cost(layout, cand_choices, flags)
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
                layout, choices, flags = single_fixpoint(layout, choices, flags)

        return layout, choices, flags, evals


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
