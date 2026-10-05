"""Hybrid GA (matheuristic): GA over gate orders + exact layout/SWAP decoder.

NOT the paper's Genetic Algorithm (that is ``genetic_fidelity``) and
deliberately *not registered*: it does not appear in the benchmark CSV or on
the plots. Kept as an experiment; run it explicitly::

    from odra_router.routing.genetic_hybrid import GeneticHybridSolver
    sol = GeneticHybridSolver().solve(problem, seed=0)

Chromosome = (layout, swaps, keys):
  - keys[i]  : priority of interaction i; the execution order is Kahn's
               topological sort with the ready set popped by smallest key
               (random-key encoding), so every key vector is a valid order.
               This is the only gene the GA evolves.
  - layout   : permutation of 0..n-1 (virtual -> physical),
  - swaps[i] : int 0..4 — SWAP choice before interaction i (0 = none,
               1..4 = star edges per EDGE_SWAPS).
  layout and swaps are *decoded* from the order by an exact DP
  (``_OrderDP``), not evolved.

Why an exact decoder
--------------------
The paper's GA re-derives SWAPs with a lookahead heuristic. Measured: handing
that heuristic exact_dp's *optimal* layout and order still lost 0.4-0.7 on
dense_1 / hard_8r (22 / 27 SWAPs vs 17 / 19), so a heuristic decoder caps the
GA however well it searches layout and order. On the star there are only
n! = 120 qubit placements, so for a fixed order the optimal (layout,
one-SWAP-per-slot) routing is a DP over 120 states per interaction. Result on
the 13 fidelity cases (seed 0): mean 0.7491 vs exact_dp 0.7475, 12/13 at the
optimum, ~1 s per case.

Caveat: the decoder is n! in the qubit count (720 at n = 6, ~3.6M at n = 10),
so it scales exactly as badly as exact_dp; it is an ODRA5-only tool.

Objective:
  minimise sum(-ln f) over the routed circuit (``solution_cost``).

Operators
---------
Keys crossover    : uniform.
Mutation          : swap the keys of two interactions adjacent in the decoded
                    order (moves one interaction past its neighbour wherever
                    the DAG allows), ``mutation_rate`` per child.

Initialisation
--------------
Warm-start order (``warm_start``) plus ``population_size - 1`` copies each
mutated ``init_mutations`` times. ``random`` (default) starts from random keys,
anything else from DAG order (the decoder picks the layout itself, so there is
no warm-start layout to seed).

Diversity
---------
After ``stagnation_limit`` generations without improvement, ``diversity_frac``
of the population (excluding elite) is replaced by freshly mutated copies of
the current best individual.

Polish
------
When ``polish`` is set (default), the best order goes through a
best-improvement descent over adjacent order swaps, each decoded exactly.
Layout and SWAP-choice moves are pointless after the exact decoder (it is
already optimal for the order). Only strict improvements are taken.
"""

from __future__ import annotations

import heapq
import itertools
import random
import time
from typing import NamedTuple

import numpy as np

from odra_router.contract import (
    RoutingProblem,
    RoutingSolution,
    _swap_positions,
    _virtual_index,
)
from odra_router.routing.baseline import _route_with_layout
from odra_router.routing.tabu_fidelity import _edge_list, _solution_from
from odra_router.fidelity import FidelityModel


# ---------------------------------------------------------------------------
# Internal chromosome type
# ---------------------------------------------------------------------------

class _Chrom(NamedTuple):
    layout: tuple[int, ...]
    swaps: tuple[int, ...]   # per-interaction SWAP codes 0..4
    keys: tuple[int, ...]    # per-interaction priority (random-key order gene)


def _predecessors(plan) -> list[list[int]]:
    """``preds[j]``: earlier interactions sharing a qubit with ``j``."""
    qubits = [set(q) for q in plan.interactions]
    return [
        [k for k in range(j) if qubits[k] & qubits[j]]
        for j in range(len(plan.interactions))
    ]


def _decode_order(keys: tuple[int, ...], preds: list[list[int]]) -> tuple[int, ...]:
    """Topological order of the interactions: Kahn's algorithm, ready set
    popped by smallest ``(key, index)``. Any key vector decodes to a valid
    order, so crossover/mutation on keys can never break the DAG."""
    I = len(keys)
    succs: list[list[int]] = [[] for _ in range(I)]
    indeg = [len(p) for p in preds]
    for j, ps in enumerate(preds):
        for k in ps:
            succs[k].append(j)
    heap = [(keys[j], j) for j in range(I) if indeg[j] == 0]
    heapq.heapify(heap)
    order: list[int] = []
    while heap:
        _, j = heapq.heappop(heap)
        order.append(j)
        for k in succs[j]:
            indeg[k] -= 1
            if indeg[k] == 0:
                heapq.heappush(heap, (keys[k], k))
    return tuple(order)


# ---------------------------------------------------------------------------
# Exact decoder: optimal layout + SWAP choices for a fixed order
# ---------------------------------------------------------------------------

class _OrderDP:
    """Exact routing for a fixed execution order, over all n! placements.

    State = placement (virtual -> physical). Before each interaction either no
    SWAP or one SWAP on any star edge (choice codes as ``_edge_list``), then
    the interaction must be adjacent. Costs follow ``solution_cost``: SWAP,
    attached 1Q gates at their current wire, the 2Q gate, and leftover 1Q
    gates on the final placement. Every placement starts at cost 0 (the layout
    is free), so the result is optimal over layout and SWAPs for this order.

    ponytail: n! states, so this is for ODRA5-sized maps only (n = 5 -> 120).
    """

    def __init__(self, problem: RoutingProblem, plan, model: FidelityModel) -> None:
        n = problem.num_qubits
        cm = problem.coupling_map
        self.edges = _edge_list(problem)
        self.perms = list(itertools.permutations(range(n)))
        index = {p: i for i, p in enumerate(self.perms)}
        S = len(self.perms)

        # trans[s, e]: placement after SWAP on edge e (an involution per edge).
        self.trans = np.empty((S, len(self.edges)), dtype=np.int64)
        for s, p in enumerate(self.perms):
            for e, (a, b) in enumerate(self.edges):
                q = list(p)
                _swap_positions(q, a, b)
                self.trans[s, e] = index[tuple(q)]
        self.swap_cost = np.array([model.cost_swap(a, b) for a, b in self.edges])

        perm_arr = np.array(self.perms)  # [s, virtual] -> physical
        one_q = np.array([model.cost_1q(w) for w in range(n)])
        two_q = np.full((n, n), np.inf)
        for a in range(n):
            for b in range(n):
                if a != b and cm.distance(a, b) <= 1:
                    two_q[a, b] = model.cost_2q(a, b)

        # exec_cost[j, s]: cost of running interaction j (+ its attached 1Q
        # gates) in placement s; inf when its endpoints are not adjacent.
        I = len(plan.interactions)
        self.exec_cost = np.empty((I, S))
        for j, (va, vb) in enumerate(plan.interactions):
            c = two_q[perm_arr[:, va], perm_arr[:, vb]].copy()
            for node in plan.attached.get(j, ()):
                c += one_q[perm_arr[:, _virtual_index(node.qargs[0])]]
            self.exec_cost[j] = c
        self.final_cost = np.zeros(S)
        for node in plan.leftover:
            self.final_cost += one_q[perm_arr[:, _virtual_index(node.qargs[0])]]

    def decode(self, order: tuple[int, ...]) -> tuple[float, tuple[int, ...], tuple[int, ...]]:
        """``(cost, layout, choices)`` optimal for ``order``."""
        S = len(self.perms)
        cur = np.zeros(S)
        back = np.empty((len(order), S), dtype=np.int8)
        for t, j in enumerate(order):
            # opts[:, 0] = no SWAP; opts[:, e+1] = arrive in s via SWAP e from
            # trans[s, e] (involution). argmin's first-minimum rule prefers
            # "no SWAP" on ties.
            opts = np.empty((S, len(self.edges) + 1))
            opts[:, 0] = cur
            opts[:, 1:] = cur[self.trans] + self.swap_cost
            back[t] = np.argmin(opts, axis=1)
            cur = opts[np.arange(S), back[t]] + self.exec_cost[j]
        total = cur + self.final_cost
        s = int(np.argmin(total))
        cost = float(total[s])

        choices = [0] * len(order)
        for t in range(len(order) - 1, -1, -1):
            c = int(back[t, s])
            choices[order[t]] = c
            if c:
                s = int(self.trans[s, c - 1])
        return cost, self.perms[s], tuple(choices)


# ---------------------------------------------------------------------------
# Genetic operators
# ---------------------------------------------------------------------------

def _uniform(seq1: tuple, seq2: tuple, rng: random.Random) -> tuple:
    """Uniform crossover: each gene independently from parent 1 or 2."""
    return tuple(a if rng.random() < 0.5 else b for a, b in zip(seq1, seq2))


def _mutate_keys(keys: tuple, order: tuple, rng: random.Random) -> tuple:
    """Swap the keys of two interactions adjacent in ``order``: the later one
    moves up if the DAG allows, otherwise the order is unchanged."""
    if len(order) < 2:
        return keys
    keys = list(keys)
    t = rng.randrange(len(order) - 1)
    a, b = order[t], order[t + 1]
    keys[a], keys[b] = keys[b], keys[a]
    return tuple(keys)


# ---------------------------------------------------------------------------
# Main solver class
# ---------------------------------------------------------------------------

class GeneticHybridSolver:
    """Genetic algorithm over gate orders with an exact layout+SWAP decoder."""

    name = "genetic_hybrid"

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
        mutation_rate: float = 1.0, # one adjacent order swap per child; 5 seeds on
                                    # dense_1/hard_8r: 0.1 -> 2.306/2.219, 1.0 -> 2.270/2.212
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
        from odra_router.fidelity import odra5_default_fidelity

        n = problem.num_qubits
        if not problem.interactions:
            return RoutingSolution(initial_layout=tuple(range(n)))

        rng = random.Random(seed)
        deadline = time.monotonic() + budget_s
        plan = build_plan(problem)
        preds = _predecessors(plan)
        I = len(plan.interactions)
        model = self.fidelity or odra5_default_fidelity()
        dp = _OrderDP(problem, plan, model)
        evals = 0
        # Many children decode to an order already seen (uniform crossover of
        # similar parents); the DP result depends only on the order.
        cache: dict[tuple[int, ...], tuple[float, tuple, tuple]] = {}

        def decode(order: tuple[int, ...]) -> tuple[float, tuple, tuple]:
            nonlocal evals
            hit = cache.get(order)
            if hit is None:
                evals += 1
                hit = cache[order] = dp.decode(order)
            return hit

        def make(keys: tuple[int, ...]) -> tuple[_Chrom, float]:
            cost, layout, swaps = decode(_decode_order(keys, preds))
            return _Chrom(layout, swaps, keys), cost

        def scrambled(keys: tuple[int, ...]) -> tuple[_Chrom, float]:
            for _ in range(self.init_mutations):
                keys = _mutate_keys(keys, _decode_order(keys, preds), rng)
            return make(keys)

        # ----------------------------------------------------------------
        # Warm start: the order to seed from (the decoder picks the layout).
        # ----------------------------------------------------------------
        if self.warm_start == "random":
            seed_keys = tuple(rng.sample(range(I), I))
        else:
            # keys = index decodes to DAG order (same start as tabu_fidelity).
            seed_keys = tuple(range(I))

        seed_chrom, seed_cost = make(seed_keys)

        # ----------------------------------------------------------------
        # Initial population: independent mutations of the warm-start point.
        # ----------------------------------------------------------------
        population: list[_Chrom] = [seed_chrom]
        fits: list[float] = [seed_cost]
        for _ in range(self.population_size - 1):
            chrom, cost = scrambled(seed_keys)
            population.append(chrom)
            fits.append(cost)

        best_idx = min(range(len(population)), key=lambda i: fits[i])
        best_chrom, best_cost = population[best_idx], fits[best_idx]

        # ----------------------------------------------------------------
        # Evolution loop.
        # ----------------------------------------------------------------
        def _tournament() -> _Chrom:
            contestants = [rng.randrange(len(population)) for _ in range(self.tournament_size)]
            return population[min(contestants, key=lambda i: fits[i])]

        stagnation = 0
        self.last_deadline_hit = False

        for _gen in range(self.generations):
            if time.monotonic() > deadline:
                self.last_deadline_hit = True
                break

            elite_indices = sorted(range(len(population)), key=lambda i: fits[i])[: self.elitism]
            new_population: list[_Chrom] = [population[i] for i in elite_indices]
            new_fits: list[float] = [fits[i] for i in elite_indices]

            # Diversification after stagnation.
            if stagnation >= self.stagnation_limit:
                n_diverse = max(1, int((self.population_size - self.elitism) * self.diversity_frac))
                for _ in range(n_diverse):
                    chrom, cost = scrambled(best_chrom.keys)
                    new_population.append(chrom)
                    new_fits.append(cost)
                stagnation = 0

            # Fill the rest of the new population via crossover + mutation.
            while len(new_population) < self.population_size:
                if time.monotonic() > deadline:
                    break
                keys = _uniform(_tournament().keys, _tournament().keys, rng)
                if rng.random() < self.mutation_rate:
                    keys = _mutate_keys(keys, _decode_order(keys, preds), rng)
                chrom, cost = make(keys)
                new_population.append(chrom)
                new_fits.append(cost)

            population, fits = new_population, new_fits

            improved = False
            for ind, c in zip(population, fits):
                if c < best_cost:
                    best_chrom, best_cost = ind, c
                    improved = True
            stagnation = 0 if improved else stagnation + 1

        order = _decode_order(best_chrom.keys, preds)
        layout, choices = best_chrom.layout, best_chrom.swaps

        # GA's crossover/mutation explore broadly but never finish a local
        # descent: best-improvement over adjacent order swaps, each decoded
        # exactly (layout/SWAP moves cannot improve on the exact decoder).
        if self.polish:
            improved = True
            while improved and not self.last_deadline_hit:
                improved = False
                best_move = None
                for t in range(I - 1):
                    if time.monotonic() > deadline:
                        self.last_deadline_hit = True
                        break
                    a, b = order[t], order[t + 1]
                    if a in preds[b]:
                        continue  # dependent: the swap would break the DAG
                    cand = order[:t] + (b, a) + order[t + 2:]
                    c = decode(cand)
                    if c[0] < best_cost - 1e-12:
                        best_cost, best_move = c[0], (cand, c)
                if best_move is not None:
                    order, (_, layout, choices) = best_move
                    improved = True

        self.last_evals = evals

        if np.isfinite(best_cost):
            return _solution_from(problem, plan, layout, choices, order)

        # ponytail: unreachable on connected maps (every order is routable);
        # greedy identity routing as an always-valid fallback.
        return _route_with_layout(problem, tuple(range(n)))
