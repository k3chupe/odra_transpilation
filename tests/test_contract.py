"""Every registered solver must pass validate() on random circuits."""

from __future__ import annotations

import qtrans  # noqa: F401
from qtrans.contract import SOLVERS, apply, make_problem, metrics, validate
from qtrans.generator import random_circuit
from qtrans.arch import trivial_circuit


def test_trivial_circuit_all_solvers():
    problem = make_problem(trivial_circuit())
    for name, solver in SOLVERS.items():
        if name == "sabre_baseline":
            continue  # Sabre output format differs; covered separately
        sol = solver.solve(problem, seed=0, budget_s=10.0)
        validate(problem, sol)
        routed = apply(problem, sol)
        assert routed.num_qubits == problem.num_qubits


def test_random_circuits_parametrized(solver_name):
    if solver_name == "sabre_baseline":
        return
    solver = SOLVERS[solver_name]
    for seed in range(10):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        if not problem.interactions:
            continue
        sol = solver.solve(problem, seed=seed, budget_s=15.0)
        validate(problem, sol)
        m = metrics(problem, sol)
        assert m["swap_count"] >= 0


def test_apply_builds_valid_routed_circuit():
    problem = make_problem(random_circuit(seed=7, num_gates=6))
    solver = SOLVERS["greedy_shortest_path"]
    sol = solver.solve(problem, seed=0, budget_s=5.0)
    routed = apply(problem, sol)
    validate(problem, sol)
    assert routed.num_qubits == problem.num_qubits
    assert len(routed.data) >= len(problem.circuit.data)
