"""Genetic algorithm routing solver — stub."""

from __future__ import annotations

from qtrans.contract import RoutingProblem, RoutingSolution


class GeneticAlgorithmSolver:
    """Register with ``register_solver`` when implemented. See docs/contract.md."""

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
