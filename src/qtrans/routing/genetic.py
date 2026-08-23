"""Genetic algorithm routing solver — stub for teammate B."""

from __future__ import annotations

from qtrans.contract import RoutingProblem, RoutingSolution


class GeneticAlgorithmSolver:
    """Assign to teammate B. Register with ``register_solver`` when implemented."""

    name = "genetic_algorithm"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        raise NotImplementedError(
            "Implement GA with chromosomes encoding layout + swap schedule. "
            "See docs/contract.md and routing/baseline.py for the Solver contract."
        )
