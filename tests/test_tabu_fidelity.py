"""Fidelity-aware move-based tabu: registration, determinism, feasibility, quality."""

from __future__ import annotations

import pytest
from qiskit import QuantumCircuit

from odra_router.contract import SOLVERS, apply, build_plan, make_problem, validate
from odra_router.fidelity import calc_goal_function, fidelity_cost, odra5_default_fidelity
from odra_router.generator import hard_circuit, random_circuit
from odra_router.routing.tabu_fidelity import _greedy_encoding

MODEL = odra5_default_fidelity()


def test_new_solvers_registered():
    for name in ("tabu_fidelity", "tabu_fidelity_greedy", "brute_fidelity_layout"):
        assert name in SOLVERS


def test_deterministic():
    problem = make_problem(random_circuit(seed=1, num_gates=10))
    a = SOLVERS["tabu_fidelity"].solve(problem, seed=7, budget_s=5.0)
    b = SOLVERS["tabu_fidelity"].solve(problem, seed=7, budget_s=5.0)
    assert a == b


def test_feasible_on_random_and_hard():
    for seed in range(5):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        for name in ("tabu_fidelity", "tabu_fidelity_greedy", "brute_fidelity_layout"):
            sol = SOLVERS[name].solve(problem, seed=seed, budget_s=5.0)
            validate(problem, sol)
    problem = make_problem(hard_circuit(4))
    for name in ("tabu_fidelity", "tabu_fidelity_greedy", "brute_fidelity_layout"):
        sol = SOLVERS[name].solve(problem, seed=0, budget_s=10.0)
        validate(problem, sol)


def test_greedy_warm_start_never_worse_than_warm_start():
    # The greedy warm start is feasible by construction; the search only
    # accepts improvements, so the emitted solution cannot cost more.
    solver = SOLVERS["tabu_fidelity_greedy"]
    for seed in range(5):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        plan = build_plan(problem)
        layout, swaps, flags = _greedy_encoding(problem, list(range(problem.num_qubits)), plan)
        warm_cost = calc_goal_function(problem, (tuple(layout), tuple(swaps), flags), MODEL, plan)
        sol = solver.solve(problem, seed=seed, budget_s=5.0)
        routed = apply(problem, sol)
        assert fidelity_cost(routed, MODEL) <= warm_cost + 1e-9


def test_finds_cheaper_order_in_two_gate_layer():
    # Two independent gates in one layer: reversed order costs 1 SWAP instead
    # of 2 (see test_fidelity.test_order_flag_changes_cost); the search must
    # find it via the order-flag move.
    qc = QuantumCircuit(5)
    qc.cx(0, 1)
    qc.cx(2, 3)
    problem = make_problem(qc)
    plan = build_plan(problem)
    layout = (0, 1, 2, 3, 4)
    c_dag = calc_goal_function(problem, (layout, (1, 1), (False,)), MODEL, plan)
    c_rev = calc_goal_function(problem, (layout, (1, 0), (True,)), MODEL, plan)
    assert c_rev < c_dag
    sol = SOLVERS["tabu_fidelity_greedy"].solve(problem, seed=0, budget_s=10.0)
    routed = apply(problem, sol)
    assert fidelity_cost(routed, MODEL) <= min(c_dag, c_rev) + 1e-9


def test_finds_better_edge_choice_than_greedy():
    # Greedy always routes the second gate of cx(0,1);cx(3,4) via SWAP (3,2)
    # onto edge (2,4); depending on the model the other edge may be cheaper.
    qc = QuantumCircuit(5)
    qc.cx(0, 1)
    qc.cx(3, 4)
    problem = make_problem(qc)
    plan = build_plan(problem)
    layout = (0, 1, 2, 3, 4)
    c3 = calc_goal_function(problem, (layout, (1, 3), (False,)), MODEL, plan)
    c4 = calc_goal_function(problem, (layout, (1, 4), (False,)), MODEL, plan)
    sol = SOLVERS["tabu_fidelity_greedy"].solve(problem, seed=0, budget_s=10.0)
    routed = apply(problem, sol)
    assert fidelity_cost(routed, MODEL) <= min(c3, c4) + 1e-9


def test_brute_fidelity_layout_is_feasible_reference():
    problem = make_problem(random_circuit(seed=2, num_gates=8))
    sol = SOLVERS["brute_fidelity_layout"].solve(problem, seed=0, budget_s=10.0)
    validate(problem, sol)
    assert SOLVERS["brute_fidelity_layout"].last_evals == 120  # all layouts on the star


def test_evals_counter():
    problem = make_problem(hard_circuit(2))
    SOLVERS["tabu_fidelity"].solve(problem, seed=0, budget_s=1.0)
    assert SOLVERS["tabu_fidelity"].last_evals > 0


def test_pair_polish_closes_medium_1_gap():
    # Regression: the medium_1 gap to exact_dp is a *pair* SWAP-choice local
    # minimum (same layout, same order, both use 3 SWAPs but on different
    # interactions); no single move reaches it. The polish pair scan must
    # close it on the reduced problem (true-minimum input).
    from odra_router.generator import circuits_from_suite
    from odra_router.optimize.cancel import reduce_input

    circuit = next(c for n, c in circuits_from_suite() if n == "medium_1")
    problem = make_problem(reduce_input(circuit))
    plan = build_plan(problem)
    if len(plan.interactions) == 0:
        return
    dp_sol = SOLVERS["exact_dp"].solve(problem, seed=0, budget_s=30.0)
    ideal = fidelity_cost(apply(problem, dp_sol), MODEL)
    for name in ("tabu_fidelity", "tabu_fidelity_greedy", "tabu_fidelity_sabre"):
        sol = SOLVERS[name].solve(problem, seed=0, budget_s=10.0)
        c = fidelity_cost(apply(problem, sol), MODEL)
        assert c <= ideal + 1e-9, f"{name}: {c} > ideal {ideal}"
