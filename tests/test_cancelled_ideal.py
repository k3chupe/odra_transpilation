"""True-minimum ideal (phase 2): exact_dp on the reduced input is the lower bound.

The routing task is defined on ``reduce_input(circuit)`` (adjacent CX pairs
cancelled before routing) and every routed output is scored after the
post-routing cancellation pass. ``exact_dp`` solves the reduced problem
exactly; these tests pin down that it is still the unbeatable reference:

1. no per-interaction solver's *post-cancelled* fidelity beats it,
2. its own optimal output is already cancellation-free (post-cancellation
   never changes its score), so it really searches the minimum of the
   true-minimum metric,
3. routing the reduced input never costs more than routing the original.
"""

from __future__ import annotations

from odra_router.contract import SOLVERS, apply, make_problem
from odra_router.fidelity import (
    cancelled_fidelity_cost,
    fidelity_cost,
    odra5_default_fidelity,
)
from odra_router.generator import circuits_from_suite, hard_circuit, random_circuit
from odra_router.optimize.cancel import reduce_input

MODEL = odra5_default_fidelity()


def _case_circuits() -> list[tuple[str, object]]:
    """Bounded subset of the fidelity suite plus one hard case."""
    out: list[tuple[str, object]] = []
    for name, circuit in circuits_from_suite():
        if name in ("tiny_0", "medium_1", "dense_0"):
            out.append((name, circuit))
    out.append(("hard_2r", hard_circuit(2)))
    return out


def test_no_solver_beats_ideal_after_cancellation():
    for case_name, circuit in _case_circuits():
        problem = make_problem(reduce_input(circuit))
        dp_sol = SOLVERS["exact_dp"].solve(problem, seed=0, budget_s=30.0)
        ideal = cancelled_fidelity_cost(problem, dp_sol, MODEL)
        for name in ("greedy_shortest_path", "brute_fidelity_layout", "tabu_fidelity", "tabu_fidelity_greedy"):
            sol = SOLVERS[name].solve(problem, seed=0, budget_s=10.0)
            c = cancelled_fidelity_cost(problem, sol, MODEL)
            assert c >= ideal - 1e-9, f"{case_name}: {name} {c} < ideal {ideal}"


def test_exact_dp_output_is_already_cancellation_free():
    # exact_dp never emits dominated SWAP-SWAP pairs and the input is reduced,
    # so post-cancelling its optimal route changes nothing: it already
    # searches the true-minimum metric.
    for seed in range(5):
        problem = make_problem(reduce_input(random_circuit(seed=seed, num_gates=12)))
        if not problem.interactions:
            continue
        sol = SOLVERS["exact_dp"].solve(problem, seed=0, budget_s=30.0)
        raw = fidelity_cost(apply(problem, sol), MODEL)
        cancelled = cancelled_fidelity_cost(problem, sol, MODEL)
        assert raw == cancelled


def test_ideal_on_reduced_never_worse_than_on_original():
    # Removing input gates only removes work, so the exact optimum of the
    # reduced problem cannot exceed the optimum of the original problem.
    for seed in range(5):
        circuit = random_circuit(seed=seed, num_gates=12)
        problem_orig = make_problem(circuit)
        problem_red = make_problem(reduce_input(circuit))
        if not problem_orig.interactions or not problem_red.interactions:
            continue
        sol_orig = SOLVERS["exact_dp"].solve(problem_orig, seed=0, budget_s=30.0)
        sol_red = SOLVERS["exact_dp"].solve(problem_red, seed=0, budget_s=30.0)
        c_orig = fidelity_cost(apply(problem_orig, sol_orig), MODEL)
        c_red = fidelity_cost(apply(problem_red, sol_red), MODEL)
        assert c_red <= c_orig + 1e-9
