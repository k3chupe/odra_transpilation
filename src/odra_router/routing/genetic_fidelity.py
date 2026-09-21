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
Flags crossover   : uniform.
SWAPs             : never crossed over or mutated directly. swaps[i]'s
                    feasibility depends on the cumulative physical position
                    built up by every earlier swap, so they are not
                    independent genes; always re-derived by greedy routing
                    of the child's own layout + flags after crossover and
                    after mutation, which is the only way to keep every
                    child feasible by construction. An earlier version blended
                    in swap codes from parents/pre-mutation as a "refinement"
                    step; measured effect: ~100% feasible children on tiny
                    instances collapsing to ~0% above ~15 interactions (one
                    foreign gene early in the sequence invalidates everything
                    after it), which silently starved the population on
                    exactly the cases with the worst gaps (heavy/hard/dense).
                    Removed; SWAP-choice exploration beyond greedy now only
                    happens in ``_polish``, which evaluates before accepting.
Mutation          : one random move per component (layout transposition,
                    order flag flip), independently according to
                    ``mutation_rate``.

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

Polish
------
When ``polish`` is set (default), the best individual after the last
generation is handed to a deterministic best-improvement descent (same
neighbourhood as ``TabuFidelitySolver._polish``): layout transpositions,
single SWAP-code changes, and order-flag flips, scanned to a fixpoint.
Only strict improvements are taken, so this never makes the result worse.

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
from odra_router.routing.tabu_fidelity import _greedy_choices
from odra_router.fidelity import FidelityModel


# ---------------------------------------------------------------------------
# Internal chromosome type
# ---------------------------------------------------------------------------

class _Chrom(NamedTuple):
    layout: tuple[int, ...]
    swaps: tuple[int, ...]   # per-interaction SWAP codes 0..4
    flags: tuple[bool, ...]  # per-two-gate-layer order flag

#greedy_encoding
def _greedy_encoding(
    problem, layout: list[int], plan, flags: tuple[bool, ...] | None = None
) -> tuple[list[int], list[int], tuple[bool, ...]]:
    """Greedy SWAP choices for ``layout`` under ``flags``, same signature as
    ``tabu_fidelity._greedy_encoding`` but backed by ``_greedy_choices``
    (Sabre-style lookahead: the endpoint with more *remaining* interactions
    goes to center) instead of the naive "always route the first endpoint"
    heuristic.

    Measured: the naive heuristic left up to +1.24 fidelity_cost on the
    table versus lookahead on the same layout (dense_0), which alone
    explained genetic_fidelity's worst gaps -- it was capped by a weaker
    router than tabu_fidelity/brute_fidelity_layout use for the identical
    task, regardless of how good the search over layouts was.
    """
    flags = flags if flags is not None else (False,) * plan.flag_count
    order = plan.execution_order(flags)
    # Lookahead (busier qubit -> center) instead of the naive "always route
    # the first endpoint": measured +1.24 fidelity_cost left on the table
    # per this one decision on dense circuits
    swaps = _greedy_choices(problem, layout, plan, order) 
    return list(layout), swaps, flags


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

    Layout: OX1. Flags: uniform crossover. SWAPs: always re-derived by
    greedy routing of the child's own layout + flags (guaranteed feasible).

    SWAP codes are *not* independent genes: swaps[i]'s validity depends on
    the cumulative physical position built up by every swap before it, so
    mixing swap codes from two parents with different layouts/histories
    produces an internally inconsistent sequence almost certain to be
    infeasible once the instance has more than a handful of interactions
    (measured: ~0% feasible children above ~15 interactions). Greedy
    re-derivation is the only part of the old "SWAP crossover" that was
    ever actually feasible; the blend on top of it never paid for itself.
    """
    child_layout = _ox1(p1.layout, p2.layout, rng)
    child_flags = _uniform(p1.flags, p2.flags, rng)
    _, child_swaps, _ = _greedy_encoding(
        problem, list(child_layout), plan, child_flags
    )
    return _Chrom(child_layout, tuple(child_swaps), child_flags)


def _polish(
    problem,
    plan,
    chrom: _Chrom,
    fitness,
    deadline: float | None = None,
) -> tuple[_Chrom, bool]:
    """Deterministic best-improvement descent to a local optimum.

    Same neighbourhood as ``TabuFidelitySolver._polish``, adapted to this
    chromosome: layout transpositions (re-derive greedy SWAPs), single
    SWAP-code changes, and order-flag flips (re-derive greedy SWAPs),
    scanned to a fixpoint. Only strict improvements are taken, so the
    result is never worse than the input. GA's crossover/mutation explore
    broadly but never finish a local descent the way tabu's polish does;
    this closes exactly that gap on the GA's own best individual.
    Returns ``(chrom, deadline_hit)``.
    """
    n = len(chrom.layout)
    I = len(chrom.swaps)
    F = len(chrom.flags)
    layout, swaps, flags = list(chrom.layout), list(chrom.swaps), list(chrom.flags)
    deadline_hit = False

    def out_of_time() -> bool:
        nonlocal deadline_hit
        if deadline is not None and time.monotonic() > deadline:
            deadline_hit = True
            return True
        return False

    improved = True
    while improved:
        improved = False
        best_cost = fitness(_Chrom(tuple(layout), tuple(swaps), tuple(flags)))
        best_move = None

        # 1. Layout transpositions, re-deriving greedy SWAPs.
        for i in range(n):
            if out_of_time():
                break
            for j in range(i + 1, n):
                cand_layout = list(layout)
                cand_layout[i], cand_layout[j] = cand_layout[j], cand_layout[i]
                _, cand_swaps, _ = _greedy_encoding(problem, cand_layout, plan, tuple(flags))
                c = fitness(_Chrom(tuple(cand_layout), tuple(cand_swaps), tuple(flags)))
                if c is not None and (best_cost is None or c < best_cost):
                    best_cost = c
                    best_move = ("layout", i, j)
        if out_of_time():
            break

        # 2. Single SWAP-code changes.
        for i in range(I):
            if out_of_time():
                break
            for s in range(5):
                if swaps[i] == s:
                    continue
                cand_swaps = list(swaps)
                cand_swaps[i] = s
                c = fitness(_Chrom(tuple(layout), tuple(cand_swaps), tuple(flags)))
                if c is not None and (best_cost is None or c < best_cost):
                    best_cost = c
                    best_move = ("swap", i, s)
        if out_of_time():
            break

        # 3. Order-flag flips, re-deriving greedy SWAPs.
        for k in range(F):
            if out_of_time():
                break
            cand_flags = list(flags)
            cand_flags[k] = not cand_flags[k]
            _, cand_swaps, _ = _greedy_encoding(problem, layout, plan, tuple(cand_flags))
            c = fitness(_Chrom(tuple(layout), tuple(cand_swaps), tuple(cand_flags)))
            if c is not None and (best_cost is None or c < best_cost):
                best_cost = c
                best_move = ("flag", k)
        if out_of_time():
            break

        if best_move is None:
            break
        improved = True
        if best_move[0] == "layout":
            i, j = best_move[1], best_move[2]
            layout[i], layout[j] = layout[j], layout[i]
            _, swaps, _ = _greedy_encoding(problem, layout, plan, tuple(flags))
            swaps = list(swaps)
        elif best_move[0] == "swap":
            swaps[best_move[1]] = best_move[2]
        else:
            flags[best_move[1]] = not flags[best_move[1]]
            _, swaps, _ = _greedy_encoding(problem, layout, plan, tuple(flags))
            swaps = list(swaps)

    return _Chrom(tuple(layout), tuple(swaps), tuple(flags)), deadline_hit


def _mutate(chrom: _Chrom, rng: random.Random, mutation_rate: float) -> _Chrom:
    """Apply up to two independent mutations (layout transposition, order
    flag flip). SWAP codes are not mutated directly here: every call site
    re-derives them by greedy routing of the (possibly mutated) layout +
    flags right after, since SWAP codes are sequentially dependent on each
    other (see ``_crossover``) and a direct random change would just be
    discarded or corrupt feasibility the same way the old crossover blend
    did. SWAP-choice exploration beyond greedy happens in ``_polish``,
    which evaluates each candidate before accepting it.
    """
    layout = list(chrom.layout)
    flags = list(chrom.flags)

    # Layout transposition.
    if rng.random() < mutation_rate and len(layout) >= 2:
        i, j = rng.sample(range(len(layout)), 2)
        layout[i], layout[j] = layout[j], layout[i]

    # Order flag flip.
    if rng.random() < mutation_rate and flags:
        k = rng.randrange(len(flags))
        flags[k] = not flags[k]

    return _Chrom(tuple(layout), chrom.swaps, tuple(flags))


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
        population_size: int = 60,
        generations: int = 80, #genetic_sweep.py: 120 vs 80 is inside the noise
                                #band (+0.0021 mean gap) but 80 is ~1.4x faster
        tournament_size: int = 3,
        mutation_rate: float = 0.1,
        elitism: int = 6,
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
        self.mutation_rate = mutation_rate
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
                # Re-sync SWAPs by greedy routing of the (possibly mutated)
                # layout + flags -- always feasible, see _crossover's docstring.
                _, synced_swaps, _ = _greedy_encoding(
                    problem, list(child.layout), plan, child.flags
                )
                child = _Chrom(child.layout, tuple(synced_swaps), child.flags)
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

        # GA's crossover/mutation explore broadly but never finish a local
        # descent; polish the best individual to a local optimum the same
        # way tabu_fidelity does, on the same neighbourhood.
        if self.polish and best_cost is not None:
            polished, deadline_hit = _polish(problem, plan, best_chrom, fitness, deadline=deadline)
            self.last_deadline_hit = deadline_hit
            polished_cost = fitness(polished)
            if polished_cost is not None and polished_cost < best_cost:
                best_chrom, best_cost = polished, polished_cost

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
