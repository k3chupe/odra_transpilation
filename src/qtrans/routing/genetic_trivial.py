"""Trivial genetic algorithm routing solver.

Deliberately minimal placeholder so the benchmark has a GA point of comparison.
The production GA belongs to the team member working on ``routing/genetic.py``
(still a stub); this module is not that algorithm. See docs/contract.md.
"""

from __future__ import annotations

import random
import time

from qtrans.contract import RoutingProblem, RoutingSolution, register_solver
from qtrans.routing.baseline import _route_with_layout  # ponytail: reuse shared greedy router


class TrivialGeneticSolver:
    """Layout-permutation GA: tournament selection, order crossover, swap mutation.

    ponytail: intentionally trivial placeholder for benchmark comparison only;
    the real GA lives in routing/genetic.py (team member). Chromosomes encode
    layouts (like tabu), fitness is the greedy SWAP count for that layout.
    """

    name = "genetic_trivial"

    def __init__(
        self,
        *,
        population_size: int = 40,
        generations: int = 60,
        tournament_size: int = 3,
        mutation_rate: float = 0.2,
        elitism: int = 2,
    ) -> None:
        self.population_size = population_size
        self.generations = generations
        self.tournament_size = tournament_size
        self.mutation_rate = mutation_rate
        self.elitism = elitism

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

        def fitness(layout: list[int]) -> int:
            nonlocal evals
            evals += 1
            return len(_route_with_layout(problem, tuple(layout)).swaps)

        # Population: random permutations plus one identity (guaranteed valid).
        population = [rng.sample(range(n), n) for _ in range(self.population_size - 1)]
        population.append(list(range(n)))
        fits = [fitness(ind) for ind in population]
        evals += 1
        best = _route_with_layout(problem, tuple(population[min(range(len(population)), key=fits.__getitem__)]))

        def tournament() -> int:
            contestants = [rng.randrange(len(population)) for _ in range(self.tournament_size)]
            return min(contestants, key=fits.__getitem__)

        def order_crossover(p1: list[int], p2: list[int]) -> list[int]:
            # OX1: keep a random segment of p1, fill the rest in p2 order.
            a, b = sorted(rng.sample(range(n), 2))
            child: list[int | None] = [None] * n
            child[a : b + 1] = p1[a : b + 1]
            filler = iter(x for x in p2 if x not in child)
            for i in range(n):
                if child[i] is None:
                    child[i] = next(filler)
            return child  # type: ignore[return-value]

        def mutate(ind: list[int]) -> list[int]:
            out = list(ind)
            if rng.random() < self.mutation_rate:
                i, j = rng.sample(range(n), 2)
                out[i], out[j] = out[j], out[i]
            return out

        for _ in range(self.generations):
            if time.monotonic() > deadline:
                break
            order = sorted(range(len(population)), key=fits.__getitem__)
            new_population = [list(population[i]) for i in order[: self.elitism]]
            while len(new_population) < self.population_size:
                parent1 = population[tournament()]
                parent2 = population[tournament()]
                new_population.append(mutate(order_crossover(parent1, parent2)))
            population = new_population
            fits = [fitness(ind) for ind in population]
            idx = min(range(len(population)), key=fits.__getitem__)
            evals += 1
            sol = _route_with_layout(problem, tuple(population[idx]))
            if len(sol.swaps) < len(best.swaps):
                best = sol

        self.last_evals = evals
        return best


def _register() -> None:
    register_solver(TrivialGeneticSolver())


_register()
