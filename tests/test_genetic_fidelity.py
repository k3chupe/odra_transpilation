"""Tests for the full-encoding genetic algorithm solver."""

from __future__ import annotations

import odra_router  # noqa: F401 — register all solvers
from odra_router.arch import trivial_circuit
from odra_router.contract import SOLVERS, apply, build_plan, make_problem, validate
from odra_router.fidelity import (
    calc_goal_function,
    fidelity_cost,
    odra5_default_fidelity,
    solution_from_encoding,
)
from odra_router.generator import hard_circuit, random_circuit
from odra_router.routing.tabu_fidelity import _greedy_encoding

MODEL = odra5_default_fidelity()
_NAMES = ("genetic_fidelity", "genetic_fidelity_greedy", "genetic_fidelity_sabre")


def test_registered():
    for name in _NAMES:
        assert name in SOLVERS, f"{name!r} not found in SOLVERS"


def test_deterministic():
    """Two calls with the same seed must return identical solutions."""
    problem = make_problem(random_circuit(seed=3, num_gates=10))
    for name in _NAMES:
        a = SOLVERS[name].solve(problem, seed=5, budget_s=10.0)
        b = SOLVERS[name].solve(problem, seed=5, budget_s=10.0)
        assert a == b, f"{name}: non-deterministic output"


def test_feasible_on_trivial():
    problem = make_problem(trivial_circuit())
    for name in _NAMES:
        sol = SOLVERS[name].solve(problem, seed=0, budget_s=10.0)
        validate(problem, sol)
        routed = apply(problem, sol)
        assert routed.num_qubits == problem.num_qubits


def test_feasible_on_random():
    for seed in range(5):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        for name in _NAMES:
            sol = SOLVERS[name].solve(problem, seed=seed, budget_s=10.0)
            validate(problem, sol)


def test_feasible_on_hard():
    problem = make_problem(hard_circuit(4))
    for name in _NAMES:
        sol = SOLVERS[name].solve(problem, seed=0, budget_s=15.0)
        validate(problem, sol)


def test_never_worse_than_warm_start_fidelity():
    """GA with greedy warm start must not produce a higher cost than its
    own greedy warm-start (elitism guarantees the seed_chrom survives)."""
    solver = SOLVERS["genetic_fidelity_greedy"]
    for seed in range(5):
        problem = make_problem(random_circuit(seed=seed, num_gates=8))
        if not problem.interactions:
            continue
        plan = build_plan(problem)
        layout_id = list(range(problem.num_qubits))
        layout_t, swaps_t, flags_t = _greedy_encoding(problem, layout_id, plan)
        warm_cost = calc_goal_function(
            problem, (tuple(layout_t), tuple(swaps_t), flags_t), MODEL, plan
        )
        sol = solver.solve(problem, seed=seed, budget_s=10.0)
        routed = apply(problem, sol)
        ga_cost = fidelity_cost(routed, MODEL)
        assert ga_cost <= warm_cost + 1e-9, (
            f"seed={seed}: GA cost {ga_cost:.6f} > warm-start cost {warm_cost:.6f}"
        )


def test_evals_counter():
    problem = make_problem(hard_circuit(2))
    for name in _NAMES:
        SOLVERS[name].solve(problem, seed=0, budget_s=5.0)
        assert SOLVERS[name].last_evals > 0, f"{name}: last_evals not updated"


def test_no_interactions_returns_identity():
    """Circuit with only 1Q gates has no interactions; solver must not crash."""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(5)
    qc.h(0)
    qc.h(2)
    problem = make_problem(qc)
    for name in _NAMES:
        sol = SOLVERS[name].solve(problem, seed=0, budget_s=5.0)
        validate(problem, sol)
