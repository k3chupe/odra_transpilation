"""Non-ODRA5 topologies: solvers take a coupling map and that map's model.

Tor D of the why-tabu analysis runs synthetic stars and lines of 5 to 8 qubits
(the size argument for keeping metaheuristics). That needs three things the
library did not have: a fidelity model that is not forced to be the ODRA5 star,
an exact reference that accepts such a model, and a tabu solver that reads its
SWAP choices from the coupling map instead of the hardcoded four star edges.

Pinned here on a six-qubit star. Only a hub topology works for `tabu_fidelity`,
because its encoding holds one SWAP per interaction.
"""

from __future__ import annotations

import pytest
from qiskit import QuantumCircuit
from qiskit.transpiler import CouplingMap

from odra_router.contract import SOLVERS, make_problem, validate
from odra_router.fidelity import FidelityModel, cancelled_fidelity_cost
from odra_router.generator import random_circuit
from odra_router.optimize.cancel import reduce_input
from odra_router.routing.exact_dp import ExactDPSolver
from odra_router.routing.tabu_fidelity import TabuFidelitySolver

N = 6
EDGES = tuple((0, i) for i in range(1, N))
EDGE_SET = {tuple(sorted(e)) for e in EDGES}


def _model() -> FidelityModel:
    return FidelityModel(
        one_qubit=tuple(0.995 - 0.001 * i for i in range(N)),
        two_qubit={tuple(sorted(e)): 0.97 - 0.002 * i for i, e in enumerate(EDGES)},
    )


def _problem():
    circuit = reduce_input(random_circuit(num_qubits=N, num_gates=20, seed=0, p_two_qubit=0.7))
    return make_problem(circuit, CouplingMap(list(EDGES)))


def test_model_accepts_another_topology():
    model = _model()
    assert len(model.one_qubit) == N
    assert {tuple(sorted(k)) for k in model.two_qubit} == EDGE_SET


def test_exact_dp_uses_the_injected_model():
    problem = _problem()
    solver = ExactDPSolver(fidelity=_model())
    solution = solver.solve(problem, seed=0, budget_s=60.0)
    validate(problem, solution)
    assert cancelled_fidelity_cost(problem, solution, _model()) > 0.0


def test_tabu_routes_on_this_topology_edges_only():
    problem = _problem()
    model = _model()
    solution = TabuFidelitySolver(fidelity=model).solve(problem, seed=0, budget_s=5.0)
    validate(problem, solution)
    for _, a, b in solution.swaps:
        assert tuple(sorted((a, b))) in EDGE_SET, f"SWAP {(a, b)} is not an edge of this star"

    greedy = SOLVERS["greedy_shortest_path"].solve(problem, seed=0, budget_s=5.0)
    assert cancelled_fidelity_cost(problem, solution, model) <= cancelled_fidelity_cost(
        problem, greedy, model
    ) + 1e-9


def test_tabu_without_a_model_falls_back_to_odra5():
    # The default must stay the ODRA5 placeholder, so nothing on the target
    # topology changes for callers that never pass a model in: routing a
    # six-qubit circuit with the five-wire default fails loudly.
    circuit = QuantumCircuit(6)
    circuit.cx(0, 5)
    solver = TabuFidelitySolver()
    assert solver.fidelity is None
    with pytest.raises((KeyError, IndexError)):
        solver.solve(make_problem(circuit, CouplingMap(list(EDGES))), budget_s=1.0)
