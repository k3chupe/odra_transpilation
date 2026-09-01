import odra_router  # noqa: F401
from odra_router.contract import SOLVERS, make_problem, validate
from odra_router.generator import hard_circuit, random_circuit
from odra_router.routing.baseline import BruteForceLayoutSolver, GreedyShortestPathSolver


def test_exact_dp_no_worse_than_greedy_on_small():
    dp = SOLVERS["exact_dp"]
    greedy = GreedyShortestPathSolver()
    problem = make_problem(random_circuit(seed=3, num_gates=8))
    if not problem.interactions:
        return
    dp_sol = dp.solve(problem, seed=0, budget_s=30.0)
    greedy_sol = greedy.solve(problem, seed=0, budget_s=30.0)
    validate(problem, dp_sol)
    validate(problem, greedy_sol)
    assert len(dp_sol.swaps) <= len(greedy_sol.swaps)


def test_exact_dp_beats_greedy_on_hard():
    # Regression: the ODRA5 CouplingMap is directed, so _neighbors() via
    # cm.neighbors() (successors only) dead-ended the DP and it silently fell
    # back to greedy. hard circuits require routing, so DP must be strictly
    # better than greedy on the identity layout.
    dp = SOLVERS["exact_dp"]
    greedy = GreedyShortestPathSolver()
    for rounds in (2, 4):
        problem = make_problem(hard_circuit(rounds))
        dp_sol = dp.solve(problem, seed=0, budget_s=30.0)
        greedy_sol = greedy.solve(problem, seed=0, budget_s=30.0)
        validate(problem, dp_sol)
        assert len(dp_sol.swaps) < len(greedy_sol.swaps)


def test_exact_dp_no_worse_than_brute_force():
    # exact DP (schedule-aware) must never be worse than brute force over
    # layouts with a greedy per-layout schedule.
    dp = SOLVERS["exact_dp"]
    brute = BruteForceLayoutSolver()
    for rounds in (1, 2, 4, 8):
        problem = make_problem(hard_circuit(rounds))
        dp_sol = dp.solve(problem, seed=0, budget_s=30.0)
        brute_sol = brute.solve(problem, seed=0, budget_s=30.0)
        validate(problem, dp_sol)
        assert len(dp_sol.swaps) <= len(brute_sol.swaps)
