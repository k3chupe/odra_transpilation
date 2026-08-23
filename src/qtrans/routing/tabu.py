"""Tabu search routing solver — stub."""

from __future__ import annotations

from qtrans.contract import RoutingProblem, RoutingSolution


class TabuSearchSolver:
    """Register with ``register_solver`` when implemented. See docs/contract.md."""

    name = "tabu_search"

    def solve(
        self,
        problem: RoutingProblem,
        *,
        seed: int = 0,
        budget_s: float = 30.0,
    ) -> RoutingSolution:
        raise NotImplementedError(
            "Implement tabu search over (initial_layout, swap sequences). "
            "See docs/contract.md and routing/baseline.py for the Solver contract."
        )
