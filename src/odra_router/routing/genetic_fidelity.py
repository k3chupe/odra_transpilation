"""Genetic algorithm routing solver — full encoding space, fidelity objective.

This is the Genetic Algorithm described in the paper (Section "Routing
algorithms"); defaults follow the paper's parameters. The hybrid variant with
an exact decoder lives in ``genetic_hybrid.py`` and is not part of the
benchmark.

Chromosome c = (pi, s, o):
  - layout (pi) : permutation of 0..n-1 (virtual -> physical),
  - swaps (s)   : int 0..4 per interaction — SWAP choice before it (0 = none,
                  1..4 = star edges per EDGE_SWAPS),
  - flags (o)   : bool per ambiguous DAG layer (exactly two independent
                  interactions) — which of the two executes first.

Objective:
  minimise sum(-ln f) over the routed circuit (``calc_goal_function``);
  infeasible encodings score None and are discarded.

Operators
---------
Crossover         : with probability ``crossover_rate`` (p_c = 0.80) OX1 on
                    the layout and uniform on the flags; otherwise the child
                    copies the first parent.
SWAPs             : never crossed over or mutated directly (a SWAP code is
                    only meaningful for the physical state built up by every
                    earlier SWAP); re-derived for the child's own layout +
                    flags by the lookahead heuristic (``_lookahead_encoding``),
                    so every offspring is feasible by construction.
Mutation          : layout transposition (p_m = 0.15) and order-flag flip
                    (p_f = 0.10), independently.
Selection         : tournament (k = 3), elitism keeps the top 2.

Lookahead SWAP synchronization
------------------------------
When both endpoints of a non-adjacent interaction sit on leaves, the endpoint
with the higher upcoming demand stays at / is moved to the hub: each later
interaction at topological distance d >= 0 (horizon 15) adds w_d = 1/(d+1) to
the score of the logical qubit it uses; ties fall back to the count of all
remaining interactions.

Initialisation
--------------
``random`` (the paper's primary setting): the random warm-start individual
plus ``population_size - 1`` individuals with independent random layouts and
random flags. ``greedy`` / ``sabre``: identity / single-Sabre-run layout,
the rest of the population are copies mutated ``init_mutations`` times.

Diversity
---------
After ``stagnation_limit`` generations without improvement, ``diversity_frac``
of the non-elite population is replaced by mutated variants of the best.

Polish
------
When ``polish`` is set (default), the best individual goes through a bounded
(deadline) best-improvement descent: layout transpositions and flag flips
(re-deriving SWAPs) and single SWAP-code changes. Only strict improvements
are taken, so it never makes the result worse.

Registered solvers
------------------
- ``genetic_fidelity``        : random start (paper).
- ``genetic_fidelity_greedy`` : identity-layout warm start.
- ``genetic_fidelity_sabre``  : Sabre-layout warm start.
"""

from __future__ import annotations

import random
import time
from typing import NamedTuple

from odra_router.contract import RoutingProblem, RoutingSolution, register_solver, _swap_positions
from odra_router.routing.baseline import _route_with_layout
from odra_router.routing.tabu import _sabre_initial_layout
from odra_router.routing.tabu_fidelity import _edge_list
from odra_router.fidelity import FidelityModel

#: Lookahead horizon (number of later interactions scored) and decay w_d.
LOOKAHEAD_HORIZON = 15


# ---------------------------------------------------------------------------
# Internal chromosome type
# ---------------------------------------------------------------------------

class _Chrom(NamedTuple):
    layout: tuple[int, ...]
    swaps: tuple[int, ...]   # per-interaction SWAP codes 0..4
    flags: tuple[bool, ...]  # per-two-gate-layer order flag


# ---------------------------------------------------------------------------
# Lookahead SWAP synchronization
# ---------------------------------------------------------------------------

def _lookahead_encoding(
    problem: RoutingProblem,
    layout,
    plan,
    flags: tuple[bool, ...] | None = None,
) -> tuple[list[int], list[int], tuple[bool, ...]]:
    """SWAP codes for ``layout`` under ``flags`` (feasible by construction).

    One SWAP per non-adjacent interaction (on the star that is always enough):
    the leaf endpoint with the higher decayed upcoming demand
    (w_d = 1/(d+1), d = 0.. over the next ``LOOKAHEAD_HORIZON`` interactions)
    goes to the hub; ties fall back to all remaining interactions.

    ponytail: same rule as main's ``tabu_fidelity._greedy_choices``; kept
    here so this branch's tabu_fidelity stays as benchmarked.
    """
    pos = list(layout)
    cm = problem.coupling_map
    degrees = [0] * problem.num_qubits
    for a, b in cm.get_edges():
        degrees[a] += 1
        degrees[b] += 1
    center = max(range(problem.num_qubits), key=lambda q: degrees[q])
    edges = _edge_list(problem)
    flags = flags if flags is not None else (False,) * plan.flag_count
    order = list(plan.execution_order(flags))
    swaps = [0] * len(plan.interactions)

    for idx, j in enumerate(order):
        va, vb = plan.interactions[j]
        pa, pb = pos[va], pos[vb]
        if cm.distance(pa, pb) <= 1:
            continue
        if pa != center and pb != center:
            score_a = score_b = 0.0
            for d, k in enumerate(order[idx + 1:idx + 1 + LOOKAHEAD_HORIZON]):
                w = 1.0 / (d + 1)
                if va in plan.interactions[k]:
                    score_a += w
                if vb in plan.interactions[k]:
                    score_b += w
            if abs(score_a - score_b) < 1e-5:
                score_a = sum(1 for k in order[idx + 1:] if va in plan.interactions[k])
                score_b = sum(1 for k in order[idx + 1:] if vb in plan.interactions[k])
            edge = (pb, center) if score_b > score_a else (pa, center)
        else:
            edge = (pa, center) if pa != center else (pb, center)
        for s, e in enumerate(edges, start=1):
            if e == edge or e == (edge[1], edge[0]):
                swaps[j] = s
                break
        else:
            raise AssertionError(f"lookahead SWAP {edge} is not a coupling-map edge")
        _swap_positions(pos, edge[0], edge[1])
    return list(layout), swaps, flags


def _synced(problem, plan, layout, flags) -> _Chrom:
    """Chromosome with SWAPs re-derived for ``layout`` + ``flags``."""
    _, swaps, _ = _lookahead_encoding(problem, list(layout), plan, tuple(flags))
    return _Chrom(tuple(layout), tuple(swaps), tuple(flags))


# ---------------------------------------------------------------------------
# Genetic operators
# ---------------------------------------------------------------------------

def _ox1(p1: tuple[int, ...], p2: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
    """Order Crossover 1: keep a segment of p1, fill the rest in p2 order."""
    n = len(p1)
    a, b = sorted(rng.sample(range(n), 2))
    child: list[int | None] = [None] * n
    child[a:b + 1] = list(p1[a:b + 1])
    segment_set = set(child[a:b + 1])
    filler = (x for x in p2 if x not in segment_set)
    for i in range(n):
        if child[i] is None:
            child[i] = next(filler)
    return tuple(child)  # type: ignore[return-value]


def _uniform(seq1: tuple, seq2: tuple, rng: random.Random) -> tuple:
    """Uniform crossover: each gene independently from parent 1 or 2."""
    return tuple(a if rng.random() < 0.5 else b for a, b in zip(seq1, seq2))


def _mutate(
    layout: tuple, flags: tuple, rng: random.Random, p_layout: float, p_flag: float
) -> tuple[tuple, tuple]:
    """Layout transposition (prob. ``p_layout``) and flag flip (``p_flag``).
    SWAPs are re-derived by the caller."""
    layout = list(layout)
    flags = list(flags)
    if rng.random() < p_layout and len(layout) >= 2:
        i, j = rng.sample(range(len(layout)), 2)
        layout[i], layout[j] = layout[j], layout[i]
    if rng.random() < p_flag and flags:
        k = rng.randrange(len(flags))
        flags[k] = not flags[k]
    return tuple(layout), tuple(flags)


def _polish(problem, plan, chrom: _Chrom, fitness, deadline: float | None = None) -> tuple[_Chrom, bool]:
    """Bounded best-improvement descent; returns ``(chrom, deadline_hit)``.

    Moves: layout transpositions (re-derive SWAPs), single SWAP-code changes,
    order-flag flips (re-derive SWAPs). Strict improvements only.
    """
    layout, swaps, flags = list(chrom.layout), list(chrom.swaps), list(chrom.flags)
    n, I, F = len(layout), len(swaps), len(flags)
    deadline_hit = False

    def out_of_time() -> bool:
        nonlocal deadline_hit
        if deadline is not None and time.monotonic() > deadline:
            deadline_hit = True
        return deadline_hit

    while not out_of_time():
        best_cost = fitness(_Chrom(tuple(layout), tuple(swaps), tuple(flags)))
        best = None

        for i in range(n):
            if out_of_time():
                break
            for j in range(i + 1, n):
                cand = list(layout)
                cand[i], cand[j] = cand[j], cand[i]
                c_chrom = _synced(problem, plan, cand, flags)
                c = fitness(c_chrom)
                if c is not None and (best_cost is None or c < best_cost):
                    best_cost, best = c, c_chrom

        for i in range(I):
            if out_of_time():
                break
            for s in range(len(_edge_list(problem)) + 1):
                if s == swaps[i]:
                    continue
                cand_swaps = list(swaps)
                cand_swaps[i] = s
                c_chrom = _Chrom(tuple(layout), tuple(cand_swaps), tuple(flags))
                c = fitness(c_chrom)
                if c is not None and (best_cost is None or c < best_cost):
                    best_cost, best = c, c_chrom

        for k in range(F):
            if out_of_time():
                break
            cand_flags = list(flags)
            cand_flags[k] = not cand_flags[k]
            c_chrom = _synced(problem, plan, layout, cand_flags)
            c = fitness(c_chrom)
            if c is not None and (best_cost is None or c < best_cost):
                best_cost, best = c, c_chrom

        if best is None:
            break
        layout, swaps, flags = list(best.layout), list(best.swaps), list(best.flags)

    return _Chrom(tuple(layout), tuple(swaps), tuple(flags)), deadline_hit


# ---------------------------------------------------------------------------
# Main solver class
# ---------------------------------------------------------------------------

class GeneticFidelitySolver:
    """Full-encoding genetic algorithm: layout + SWAP choices + order flags."""

    name = "genetic_fidelity"

    def __init__(
        self,
        *,
        warm_start: str = "random",
        name: str | None = None,
        fidelity: FidelityModel | None = None,
        population_size: int = 60,
        generations: int = 80,
        tournament_size: int = 3,
        crossover_rate: float = 0.80,
        layout_mutation_rate: float = 0.15,
        flag_mutation_rate: float = 0.10,
        elitism: int = 2,
        stagnation_limit: int = 20,
        diversity_frac: float = 0.3,
        init_mutations: int = 5,
        polish: bool = True,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
        self.fidelity = fidelity
        self.population_size = population_size
        self.generations = generations
        self.tournament_size = tournament_size
        self.crossover_rate = crossover_rate
        self.layout_mutation_rate = layout_mutation_rate
        self.flag_mutation_rate = flag_mutation_rate
        self.elitism = elitism
        self.stagnation_limit = stagnation_limit
        self.diversity_frac = diversity_frac
        self.init_mutations = init_mutations
        self.polish = polish
        self.last_evals: int = 0
        self.last_deadline_hit: bool = False

    # ------------------------------------------------------------------
    # Public interface (Solver protocol)
    # ------------------------------------------------------------------

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        from odra_router.contract import build_plan
        from odra_router.fidelity import (
            calc_goal_function,
            odra5_default_fidelity,
            solution_from_encoding,
        )

        n = problem.num_qubits
        if not problem.interactions:
            return RoutingSolution(initial_layout=tuple(range(n)))

        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        plan = build_plan(problem)
        F = plan.flag_count
        model = self.fidelity or odra5_default_fidelity()
        evals = 0

        def fitness(chrom: _Chrom) -> float | None:
            nonlocal evals
            evals += 1
            return calc_goal_function(problem, (chrom.layout, chrom.swaps, chrom.flags), model, plan)

        def scrambled(chrom: _Chrom) -> _Chrom:
            layout, flags = chrom.layout, chrom.flags
            for _ in range(self.init_mutations):
                layout, flags = _mutate(layout, flags, rng, 1.0, 1.0)
            return _synced(problem, plan, layout, flags)

        # ----------------------------------------------------------------
        # Initial population.
        # ----------------------------------------------------------------
        if self.warm_start == "greedy":
            warm_layout = list(range(n))
        elif self.warm_start == "sabre":
            warm_layout = _sabre_initial_layout(problem, seed)
            if warm_layout is None:
                warm_layout = rng.sample(range(n), n)
        else:
            warm_layout = rng.sample(range(n), n)
        seed_chrom = _synced(problem, plan, warm_layout, (False,) * F)

        population: list[_Chrom] = [seed_chrom]
        for _ in range(self.population_size - 1):
            if self.warm_start == "random":
                layout = rng.sample(range(n), n)
                flags = tuple(rng.random() < 0.5 for _ in range(F))
                population.append(_synced(problem, plan, layout, flags))
            else:
                population.append(scrambled(seed_chrom))
        fits: list[float | None] = [fitness(ind) for ind in population]

        best_chrom: _Chrom | None = None
        best_cost: float | None = None
        for ind, c in zip(population, fits):
            if c is not None and (best_cost is None or c < best_cost):
                best_chrom, best_cost = ind, c

        # ----------------------------------------------------------------
        # Evolution loop.
        # ----------------------------------------------------------------
        def _tournament() -> _Chrom:
            contestants = [rng.randrange(len(population)) for _ in range(self.tournament_size)]
            valid = [i for i in contestants if fits[i] is not None]
            if valid:
                return population[min(valid, key=lambda i: fits[i])]
            return population[rng.choice(contestants)]

        stagnation = 0
        self.last_deadline_hit = False

        for _gen in range(self.generations):
            if time.monotonic() > deadline:
                self.last_deadline_hit = True
                break

            valid_sorted = sorted(
                (i for i in range(len(population)) if fits[i] is not None),
                key=lambda i: fits[i],
            )
            new_population = [population[i] for i in valid_sorted[: self.elitism]]
            new_fits = [fits[i] for i in valid_sorted[: self.elitism]]

            # Diversity injection after stagnation.
            if stagnation >= self.stagnation_limit and best_chrom is not None:
                n_diverse = max(1, int((self.population_size - self.elitism) * self.diversity_frac))
                for _ in range(n_diverse):
                    new_population.append(scrambled(best_chrom))
                    new_fits.append(fitness(new_population[-1]))
                stagnation = 0

            while len(new_population) < self.population_size:
                if time.monotonic() > deadline:
                    self.last_deadline_hit = True
                    break
                p1, p2 = _tournament(), _tournament()
                if rng.random() < self.crossover_rate:
                    layout = _ox1(p1.layout, p2.layout, rng)
                    flags = _uniform(p1.flags, p2.flags, rng)
                else:
                    layout, flags = p1.layout, p1.flags
                layout, flags = _mutate(
                    layout, flags, rng, self.layout_mutation_rate, self.flag_mutation_rate
                )
                new_population.append(_synced(problem, plan, layout, flags))
                new_fits.append(fitness(new_population[-1]))

            population, fits = new_population, new_fits

            improved = False
            for ind, c in zip(population, fits):
                if c is not None and (best_cost is None or c < best_cost):
                    best_chrom, best_cost = ind, c
                    improved = True
            stagnation = 0 if improved else stagnation + 1

        if best_chrom is None:
            # ponytail: lookahead encodings are feasible by construction, so
            # this is unreachable; greedy identity routing is always valid.
            self.last_evals = evals
            return _route_with_layout(problem, tuple(range(n)))

        if self.polish:
            polished, hit = _polish(problem, plan, best_chrom, fitness, deadline=deadline)
            self.last_deadline_hit = self.last_deadline_hit or hit
            pc = fitness(polished)
            if pc is not None and pc < best_cost:
                best_chrom, best_cost = polished, pc

        self.last_evals = evals
        return solution_from_encoding(
            problem, (best_chrom.layout, best_chrom.swaps, best_chrom.flags), plan
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _register() -> None:
    register_solver(GeneticFidelitySolver(warm_start="random"))
    register_solver(GeneticFidelitySolver(warm_start="greedy", name="genetic_fidelity_greedy"))
    register_solver(GeneticFidelitySolver(warm_start="sabre", name="genetic_fidelity_sabre"))


_register()
