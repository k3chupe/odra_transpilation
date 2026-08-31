"""Fidelity model, objective and consistency tests."""

from __future__ import annotations

import random

import pytest
from qiskit import QuantumCircuit

from qtrans.arch import ODRA5_EDGES
from qtrans.contract import build_plan, make_problem, validate
from qtrans.fidelity import (
    FidelityModel,
    calc_goal_function,
    fidelity_cost,
    odra5_default_fidelity,
    solution_cost,
    solution_from_encoding,
)
from qtrans.generator import random_circuit


def test_model_validation():
    good = odra5_default_fidelity()
    # wrong number of 1Q fidelities
    with pytest.raises(ValueError):
        FidelityModel(one_qubit=(0.99,) * 4, two_qubit={})
    # fidelity out of (0, 1)
    with pytest.raises(ValueError):
        FidelityModel(one_qubit=(1.5,) * 5, two_qubit={tuple(sorted(e)): 0.9 for e in ODRA5_EDGES})
    # 2Q map must cover exactly the star edges
    with pytest.raises(ValueError):
        FidelityModel(one_qubit=good.one_qubit, two_qubit={(0, 1): 0.9})
    # undirected cost + SWAP = 3 two-qubit gates
    assert good.cost_2q(2, 0) == pytest.approx(good.cost_2q(0, 2))
    assert good.cost_swap(0, 2) == pytest.approx(3 * good.cost_2q(0, 2))


def test_default_model_has_spread():
    model = odra5_default_fidelity()
    assert len(set(round(f, 6) for f in model.one_qubit)) > 1
    assert len(set(round(f, 6) for f in model.two_qubit.values())) > 1
    assert all(0.0 < f < 1.0 for f in model.one_qubit)
    assert all(0.0 < f < 1.0 for f in model.two_qubit.values())


def test_calc_goal_infeasible_returns_none():
    qc = QuantumCircuit(5)
    qc.cx(0, 1)  # non-edge pair under the identity layout
    problem = make_problem(qc)
    plan = build_plan(problem)
    model = odra5_default_fidelity()
    # no SWAP: gate (0,1) cannot touch the center -> infeasible
    assert calc_goal_function(problem, ((0, 1, 2, 3, 4), (0,), ()), model, plan) is None
    # one SWAP on edge (0,2): brings virtual 0 to the center -> feasible
    c = calc_goal_function(problem, ((0, 1, 2, 3, 4), (1,), ()), model, plan)
    assert c is not None and c > 0
    # wrong flags length raises
    with pytest.raises(ValueError):
        calc_goal_function(problem, ((0, 1, 2, 3, 4), (1,), (False,)), model, plan)


def test_one_qubit_only_circuit():
    qc = QuantumCircuit(5)
    qc.h(0)
    qc.rz(0.5, 1)
    qc.h(3)
    problem = make_problem(qc)
    plan = build_plan(problem)
    model = odra5_default_fidelity()
    assert len(plan.interactions) == 0
    c = calc_goal_function(problem, ((0, 1, 2, 3, 4), (), ()), model, plan)
    assert c == pytest.approx(model.cost_1q(0) + model.cost_1q(1) + model.cost_1q(3))
    # initial layout changes which physical wire each 1Q gate lands on
    c2 = calc_goal_function(problem, ((0, 1, 2, 4, 3), (), ()), model, plan)
    assert c2 != pytest.approx(c)


def test_order_flag_changes_cost():
    # Two independent gates in one DAG layer: (0,1) then (2,3) needs 2 SWAPs,
    # reversed order needs 1 (gate (2,3) already touches the center).
    qc = QuantumCircuit(5)
    qc.cx(0, 1)
    qc.cx(2, 3)
    problem = make_problem(qc)
    plan = build_plan(problem)
    model = odra5_default_fidelity()
    assert plan.layers == ((0, 1),) and plan.flag_count == 1
    layout = (0, 1, 2, 3, 4)
    c_dag = calc_goal_function(problem, (layout, (1, 1), (False,)), model, plan)
    c_rev = calc_goal_function(problem, (layout, (1, 0), (True,)), model, plan)
    assert c_dag is not None and c_rev is not None
    assert c_rev < c_dag  # 1 SWAP vs 2 SWAPs


def test_swap_edge_choice_changes_fidelity():
    # Same SWAP count, different edge: greedy picks SWAP (3,2) so the second
    # gate lands on edge (2,4); SWAP (2,4) puts it on edge (2,3).
    qc = QuantumCircuit(5)
    qc.cx(0, 1)
    qc.cx(3, 4)
    problem = make_problem(qc)
    plan = build_plan(problem)
    model = odra5_default_fidelity()
    layout = (0, 1, 2, 3, 4)
    c_greedy_edge = calc_goal_function(problem, (layout, (1, 3), (False,)), model, plan)
    c_alt_edge = calc_goal_function(problem, (layout, (1, 4), (False,)), model, plan)
    assert c_greedy_edge is not None and c_alt_edge is not None
    assert c_greedy_edge != pytest.approx(c_alt_edge)


def test_objective_equals_metric_on_emitted_circuit():
    model = odra5_default_fidelity()
    rng = random.Random(0)
    for seed in range(5):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        plan = build_plan(problem)
        I = len(plan.interactions)
        F = plan.flag_count
        for _ in range(20):
            layout = tuple(rng.sample(range(problem.num_qubits), problem.num_qubits))
            swaps = tuple(rng.randrange(5) for _ in range(I))
            flags = tuple(rng.random() < 0.5 for _ in range(F))
            c = calc_goal_function(problem, (layout, swaps, flags), model, plan)
            if c is None:
                continue
            sol = solution_from_encoding(problem, (layout, swaps, flags), plan)
            validate(problem, sol)
            from qtrans.contract import apply

            assert c == pytest.approx(fidelity_cost(apply(problem, sol), model))
            assert solution_cost(problem, sol, model, plan) == pytest.approx(c)
