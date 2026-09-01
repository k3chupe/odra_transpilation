"""Warm-started tabu and the trivial GA: registration, warm-start layout, QUEKO."""

from __future__ import annotations

import odra_router  # noqa: F401 — register solvers
from odra_router.contract import SOLVERS, make_problem, validate
from odra_router.generator import random_circuit
from odra_router.queko import odra5_queko


def test_new_solvers_registered():
    assert "tabu_sabre_start" in SOLVERS
    assert "genetic_search" in SOLVERS


def test_sabre_warm_start_layout_is_a_permutation():
    from odra_router.routing.tabu import _sabre_initial_layout

    problem = make_problem(random_circuit(seed=3, num_gates=8))
    perm = _sabre_initial_layout(problem, seed=0)
    assert perm is not None
    assert sorted(perm) == list(range(problem.num_qubits))


def test_tabu_variants_reach_queko_optimum():
    # QUEKO circuits have a known-optimal 0-SWAP layout; both tabu variants
    # (random start and Sabre warm start) must find it.
    for name in ("tabu_search", "tabu_sabre_start"):
        solver = SOLVERS[name]
        for depth in (4, 8):
            circuit, _ = odra5_queko(depth, seed=0)
            problem = make_problem(circuit)
            sol = solver.solve(problem, seed=0, budget_s=10.0)
            validate(problem, sol)
            assert len(sol.swaps) == 0, f"{name} missed the 0-SWAP optimum on d{depth}"


def test_genetic_search_produces_valid_solution():
    solver = SOLVERS["genetic_search"]
    for depth in (4, 8):
        circuit, _ = odra5_queko(depth, seed=1)
        problem = make_problem(circuit)
        sol = solver.solve(problem, seed=0, budget_s=10.0)
        validate(problem, sol)
