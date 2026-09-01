"""Genetic algorithm routing solver — full encoding space, fidelity objective.

Chromosome = (layout, swaps, flags):
  - layout   : permutation of 0..n-1 (virtual -> physical),
  - swaps[i] : int 0..4 — SWAP choice before interaction i (0 = none,
               1..4 = star edges per EDGE_SWAPS),
  - flags[k] : bool — execution order of the two gates in the k-th
               two-gate DAG layer.

Objective:
  minimise sum(-ln f) over the routed circuit (calc_goal_function / fidelity.py);
  infeasible encodings score None and are discarded.

Operators
---------
Layout crossover  : OX1 (Order Crossover 1) — permutation-safe.
                    After crossover the SWAP choices are re-derived via
                    greedy routing (_greedy_encoding), guaranteeing
                    feasibility.  Flags are inherited via uniform crossover.
SWAP crossover    : uniform (each gene taken from parent 1 or 2 at random).
                    Applied as a secondary refinement *after* greedy re-
                    derivation: a gene from the other parent may select a
                    different star edge with better fidelity.
Flags crossover   : uniform.
Mutation          : one random move from the same three types as
                    TabuFidelitySolver (layout transposition, flag flip,
                    SWAP code change), applied independently per component
                    according to ``mutation_rate``.

Initialisation
--------------
1. Obtain a warm-start layout based on ``warm_start`` parameter.
2. All ``population_size`` individuals start from this point and are then
   independently mutated ``init_mutations`` times each, producing a diverse
   but locally good initial population.

Diversity
---------
After ``stagnation_limit`` generations without improvement, ``diversity_frac``
of the population (excluding elite) is replaced by freshly mutated copies of
the current best individual, while the rest is kept.

Registered solvers
------------------
- ``genetic_fidelity``        : fidelity objective, random warm start.
- ``genetic_fidelity_greedy`` : fidelity objective, greedy warm start.
- ``genetic_fidelity_sabre``  : fidelity objective, SABRE warm start.
"""

from __future__ import annotations

import random
import time
from typing import NamedTuple

from odra_router.contract import RoutingProblem, RoutingSolution, register_solver
from odra_router.routing.baseline import _route_with_layout
from odra_router.routing.tabu import _sabre_initial_layout
from odra_router.routing.tabu_fidelity import _greedy_encoding
from odra_router.fidelity import FidelityModel


# ---------------------------------------------------------------------------
# Internal chromosome type
# ---------------------------------------------------------------------------

class _Chrom(NamedTuple):
    layout: tuple[int, ...]
    swaps: tuple[int, ...]   # per-interaction SWAP codes 0..4
    flags: tuple[bool, ...]  # per-two-gate-layer order flag


# ---------------------------------------------------------------------------
# Objective helpers
# ---------------------------------------------------------------------------

def _cost_fidelity(problem, chrom: _Chrom, model, plan) -> float | None:
    """Return sum(-ln f) for the chromosome, or None if infeasible."""
    from odra_router.fidelity import calc_goal_function
    return calc_goal_function(
        problem, (chrom.layout, chrom.swaps, chrom.flags), model, plan
    )


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


def _crossover(
    p1: _Chrom,
    p2: _Chrom,
    problem,
    plan,
    rng: random.Random,
) -> _Chrom:
    """Produce one offspring.

    Layout: OX1 -> re-derive greedy SWAPs (guaranteed feasible).
    SWAPs: uniform crossover on top of greedy baseline (edge refinement).
    Flags: uniform crossover.
    """
    child_layout = _ox1(p1.layout, p2.layout, rng)
    child_flags = _uniform(p1.flags, p2.flags, rng)

    # Re-derive greedy SWAPs for the new layout + inherited flags.
    _, greedy_swaps, _ = _greedy_encoding(
        problem, list(child_layout), plan, child_flags
    )

    # Uniform crossover on SWAP codes: use the greedy baseline but let
    # genes from the other parent's SWAP choice compete.  Infeasible
    # choices from raw crossover are implicitly corrected by evaluating
    # via calc_goal_function (which returns None for infeasible ones);
    # here we just blend — the solver's fitness call will filter.
    raw_swaps = _uniform(tuple(greedy_swaps), _uniform(p1.swaps, p2.swaps, rng), rng)
    child_swaps = tuple(int(s) % 5 for s in raw_swaps)

    return _Chrom(child_layout, child_swaps, child_flags)


def _mutate(chrom: _Chrom, rng: random.Random, mutation_rate: float) -> _Chrom:
    """Apply up to three independent mutations (one per chromosome part)."""
    layout = list(chrom.layout)
    swaps = list(chrom.swaps)
    flags = list(chrom.flags)

    # Layout transposition.
    if rng.random() < mutation_rate and len(layout) >= 2:
        i, j = rng.sample(range(len(layout)), 2)
        layout[i], layout[j] = layout[j], layout[i]

    # SWAP code change.
    if rng.random() < mutation_rate and swaps:
        idx = rng.randrange(len(swaps))
        swaps[idx] = (swaps[idx] + rng.randrange(1, 5)) % 5

    # Order flag flip.
    if rng.random() < mutation_rate and flags:
        k = rng.randrange(len(flags))
        flags[k] = not flags[k]

    return _Chrom(tuple(layout), tuple(swaps), tuple(flags))


# ---------------------------------------------------------------------------
# Main solver class
# ---------------------------------------------------------------------------

class GeneticFidelitySolver:
    """Full-encoding genetic algorithm: layout + SWAP choices + order flags.

    ponytail: crossover always re-derives greedy SWAPs for the child layout
    so the offspring is feasible by construction; a uniform SWAP crossover
    is then applied on top as an edge-selection refinement step.
    """

    name = "genetic_fidelity"

    def __init__(
        self,
        *,
        warm_start: str = "random",
        name: str | None = None,
        fidelity: FidelityModel | None = None,
        population_size: int = 40,
        generations: int = 80,
        tournament_size: int = 3,
        mutation_rate: float = 0.25,
        elitism: int = 2,
        stagnation_limit: int = 20,
        diversity_frac: float = 0.3,
        init_mutations: int = 5,
    ) -> None:
        self.warm_start = warm_start
        if name is not None:
            self.name = name
        self.fidelity = fidelity
        self.population_size = population_size
        self.generations = generations
        self.tournament_size = tournament_size
        self.mutation_rate = mutation_rate
        self.elitism = elitism
        self.stagnation_limit = stagnation_limit
        self.diversity_frac = diversity_frac
        self.init_mutations = init_mutations
        self.last_evals: int = 0

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
            odra5_default_fidelity,
            solution_from_encoding,
        )

        n = problem.num_qubits
        if not problem.interactions:
            return RoutingSolution(initial_layout=tuple(range(n)))

        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        plan = build_plan(problem)
        model = self.fidelity or odra5_default_fidelity()
        evals = 0

        def fitness(chrom: _Chrom) -> float | None:
            nonlocal evals
            evals += 1
            return _cost_fidelity(problem, chrom, model, plan)

        # ----------------------------------------------------------------
        # Warm start logic
        # ----------------------------------------------------------------
        if self.warm_start == "greedy":
            warm_layout = list(range(n))
        elif self.warm_start == "sabre":
            warm_layout = _sabre_initial_layout(problem, seed)
            if warm_layout is None:
                warm_layout = rng.sample(range(n), n)
        else:
            warm_layout = rng.sample(range(n), n)

        warm_layout_t, warm_swaps, warm_flags = _greedy_encoding(
            problem, warm_layout, plan
        )
        seed_chrom = _Chrom(
            tuple(warm_layout_t), tuple(warm_swaps), tuple(warm_flags)
        )

        # ----------------------------------------------------------------
        # Initial population: independent mutations of the warm-start point.
        # ----------------------------------------------------------------
        population: list[_Chrom] = [seed_chrom]
        for _ in range(self.population_size - 1):
            ind = seed_chrom
            for _ in range(self.init_mutations):
                ind = _mutate(ind, rng, mutation_rate=1.0)  # always mutate
            # Re-derive greedy SWAPs after layout may have changed.
            _, derived_swaps, _ = _greedy_encoding(
                problem, list(ind.layout), plan, ind.flags
            )
            population.append(
                _Chrom(ind.layout, tuple(derived_swaps), ind.flags)
            )

        # Evaluate initial population.
        fits: list[float | None] = [fitness(ind) for ind in population]

        # Track global best (use a fallback greedy solution as floor).
        fallback_sol = _route_with_layout(problem, tuple(range(n)))
        best_chrom = seed_chrom
        best_cost: float | None = fitness(seed_chrom)

        def _valid_cost(c: float | None) -> bool:
            return c is not None

        for ind, c in zip(population, fits):
            if _valid_cost(c) and (best_cost is None or c < best_cost):
                best_chrom = ind
                best_cost = c

        # ----------------------------------------------------------------
        # Evolution loop.
        # ----------------------------------------------------------------
        def _tournament() -> _Chrom:
            contestants = [rng.randrange(len(population)) for _ in range(self.tournament_size)]
            # Prefer valid individuals; among valid prefer smallest cost.
            valid = [(i, fits[i]) for i in contestants if _valid_cost(fits[i])]
            if valid:
                return population[min(valid, key=lambda x: x[1])[0]]
            # All invalid: return random contestant.
            return population[rng.choice(contestants)]

        stagnation = 0

        for _gen in range(self.generations):
            if time.monotonic() > deadline:
                break

            # Elitism: carry over the best individuals unchanged.
            valid_sorted = [
                i for i in range(len(population)) if _valid_cost(fits[i])
            ]
            valid_sorted.sort(key=lambda i: fits[i])  # type: ignore[arg-type]
            elite_indices = valid_sorted[: self.elitism]
            new_population: list[_Chrom] = [population[i] for i in elite_indices]

            # Diversification after stagnation.
            if stagnation >= self.stagnation_limit:
                n_diverse = max(1, int((self.population_size - self.elitism) * self.diversity_frac))
                for _ in range(n_diverse):
                    ind = best_chrom
                    for _ in range(self.init_mutations):
                        ind = _mutate(ind, rng, mutation_rate=1.0)
                    _, derived_swaps, _ = _greedy_encoding(
                        problem, list(ind.layout), plan, ind.flags
                    )
                    new_population.append(
                        _Chrom(ind.layout, tuple(derived_swaps), ind.flags)
                    )
                stagnation = 0

            # Fill the rest of the new population via crossover + mutation.
            while len(new_population) < self.population_size:
                if time.monotonic() > deadline:
                    break
                parent1 = _tournament()
                parent2 = _tournament()
                child = _crossover(parent1, parent2, problem, plan, rng)
                child = _mutate(child, rng, self.mutation_rate)
                # After layout mutation, re-sync greedy SWAPs.
                _, synced_swaps, _ = _greedy_encoding(
                    problem, list(child.layout), plan, child.flags
                )
                # Blend synced greedy with mutated swaps (fidelity refinement).
                blended = tuple(
                    cs if rng.random() < 0.5 else ms
                    for cs, ms in zip(synced_swaps, child.swaps)
                )
                child = _Chrom(child.layout, blended, child.flags)
                new_population.append(child)

            population = new_population
            fits = [fitness(ind) for ind in population]

            # Update global best.
            improved = False
            for ind, c in zip(population, fits):
                if _valid_cost(c) and (best_cost is None or c < best_cost):
                    best_chrom = ind
                    best_cost = c
                    improved = True

            if improved:
                stagnation = 0
            else:
                stagnation += 1

        self.last_evals = evals

        # Convert best chromosome to RoutingSolution.
        if best_cost is not None:
            return solution_from_encoding(
                problem, (best_chrom.layout, best_chrom.swaps, best_chrom.flags), plan
            )

        # Ultimate fallback: greedy identity routing (always valid).
        return fallback_sol


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _register() -> None:
    register_solver(GeneticFidelitySolver(warm_start="random"))
    register_solver(
        GeneticFidelitySolver(
            warm_start="greedy",
            name="genetic_fidelity_greedy",
        )
    )
    register_solver(
        GeneticFidelitySolver(
            warm_start="sabre",
            name="genetic_fidelity_sabre",
        )
    )


_register()
