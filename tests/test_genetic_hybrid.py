"""Tests for the (unregistered) hybrid GA: GA over orders + exact decoder."""

from __future__ import annotations

import odra_router  # noqa: F401 — register all solvers
from odra_router.contract import SOLVERS, build_plan, make_problem, validate
from odra_router.fidelity import odra5_default_fidelity, solution_cost
from odra_router.generator import hard_circuit, random_circuit
from odra_router.routing.genetic_hybrid import GeneticHybridSolver, _OrderDP
from odra_router.routing.tabu_fidelity import _solution_from

MODEL = odra5_default_fidelity()


def test_not_registered():
    """Kept out of the benchmark and the plots on purpose."""
    assert "genetic_hybrid" not in SOLVERS


def test_decoder_cost_matches_solution_cost():
    problem = make_problem(hard_circuit(4))
    plan = build_plan(problem)
    order = tuple(range(len(plan.interactions)))
    cost, layout, choices = _OrderDP(problem, plan, MODEL).decode(order)
    sol = _solution_from(problem, plan, layout, choices, order)
    validate(problem, sol)
    assert abs(cost - solution_cost(problem, sol, MODEL, plan)) < 1e-9


def test_feasible_deterministic_and_not_below_exact():
    solver = GeneticHybridSolver()
    for seed in range(3):
        problem = make_problem(random_circuit(seed=seed, num_gates=10))
        a = solver.solve(problem, seed=seed, budget_s=10.0)
        assert a == solver.solve(problem, seed=seed, budget_s=10.0)
        validate(problem, a)
        if problem.interactions:
            exact = SOLVERS["exact_dp"].solve(problem)
            assert solution_cost(problem, a, MODEL) >= solution_cost(problem, exact, MODEL) - 1e-9
