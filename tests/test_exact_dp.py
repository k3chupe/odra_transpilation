import qtrans  # noqa: F401
from qtrans.contract import SOLVERS, make_problem, validate
from qtrans.generator import random_circuit
from qtrans.routing.baseline import GreedyShortestPathSolver


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
