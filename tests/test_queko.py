"""Tests for the QUEKO benchmark circuit generator (src/qtrans/queko.py)."""

from __future__ import annotations

import pytest

import qtrans  # noqa: F401 — import must succeed without registering genetic
from qtrans import odra5_coupling_map
from qtrans.arch import ODRA5_EDGES
from qtrans.contract import make_problem
from qtrans.queko import odra5_queko, queko_circuit
from qiskit import qasm2
from qiskit.transpiler import CouplingMap

from qtrans.routing.baseline import _route_with_layout


def test_import_qtrans_does_not_register_genetic():
    """`import qtrans` works and the unregistered genetic stub stays absent."""
    assert "genetic_algorithm" not in qtrans.SOLVERS


def test_determinism_same_seed():
    c1, l1 = queko_circuit(ODRA5_EDGES, depth=6, density_vec=(0.2, 0.3), seed=42)
    c2, l2 = queko_circuit(ODRA5_EDGES, depth=6, density_vec=(0.2, 0.3), seed=42)
    assert c1 == c2
    assert qasm2.dumps(c1) == qasm2.dumps(c2)
    assert l1 == l2


def test_determinism_odra5_wrapper():
    a, la = odra5_queko(depth=8, seed=7)
    b, lb = odra5_queko(depth=8, seed=7)
    assert a == b
    assert la == lb


def test_different_seed_gives_different_circuit():
    c1, _ = queko_circuit(ODRA5_EDGES, depth=12, density_vec=(0.2, 0.3), seed=0)
    c2, _ = queko_circuit(ODRA5_EDGES, depth=12, density_vec=(0.2, 0.3), seed=1)
    assert c1 != c2


@pytest.mark.parametrize("depth,seed", [(3, 0), (5, 1), (7, 2), (10, 3), (12, 7), (15, 11)])
def test_known_optimal_zero_swaps(depth, seed):
    """The returned optimal_layout must route the circuit with zero SWAPs."""
    circuit, optimal_layout = odra5_queko(depth=depth, seed=seed)
    problem = make_problem(circuit, odra5_coupling_map())
    sol = _route_with_layout(problem, optimal_layout)
    assert len(sol.swaps) == 0, f"expected 0 swaps for depth={depth} seed={seed}"


def test_circuit_shape_and_two_qubit_gates():
    circuit, _ = odra5_queko(depth=8, seed=0)
    assert circuit.num_qubits == 5
    two_q = [instr for instr in circuit.data if len(instr.qubits) == 2]
    assert len(two_q) >= 1
    # two-qubit gates are a budget: at most ceil(d2 * n * depth / 2) of them
    expected = int(__import__("math").ceil(0.3 * 5 * 8 / 2))
    assert len(two_q) <= expected


def test_optimal_layout_is_permutation():
    circuit, optimal_layout = odra5_queko(depth=5, seed=3)
    assert len(optimal_layout) == circuit.num_qubits == 5
    assert sorted(optimal_layout) == [0, 1, 2, 3, 4]


def test_inadmissible_density_raises():
    """(0.0, 1.0) on the star at depth 5 needs 13 two-qubit gates: impossible."""
    with pytest.raises(ValueError):
        queko_circuit(ODRA5_EDGES, depth=5, density_vec=(0.0, 1.0))


def test_insufficient_density_raises():
    """Too few gates to reach the requested depth is inadmissible."""
    with pytest.raises(ValueError):
        queko_circuit(ODRA5_EDGES, depth=50, density_vec=(0.01, 0.01))


def test_layout_routes_with_zero_swaps_on_nonstar_edges():
    """QUEKO holds on arbitrary coupling graphs, not just the star."""
    edges = [(0, 1), (1, 2), (2, 3), (3, 4)]  # 5-qubit line
    circuit, optimal_layout = queko_circuit(edges, depth=6, density_vec=(0.2, 0.3), seed=5)
    problem = make_problem(circuit, CouplingMap(edges))
    sol = _route_with_layout(problem, optimal_layout)
    assert len(sol.swaps) == 0
