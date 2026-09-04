"""Phase 2 gate cancellation: rules, idempotence, equivalence, routing effect."""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from odra_router.contract import make_problem
from odra_router.generator import random_circuit
from odra_router.optimize.cancel import cancel_adjacent, reduce_input
from odra_router.routing.baseline import GreedyShortestPathSolver


def _equiv(a: QuantumCircuit, b: QuantumCircuit) -> bool:
    return Operator(a).equiv(Operator(b))


def test_cx_cx_cancels():
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(0, 2)
    out = cancel_adjacent(qc)
    assert len(out.data) == 0
    assert _equiv(qc, out)


def test_cx_flipped_orientation_does_not_cancel():
    # CX is only self-inverse with identical control and target order.
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(2, 0)
    out = cancel_adjacent(qc)
    assert len(out.data) == 2


def test_cx_with_1q_between_does_not_cancel():
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.h(0)
    qc.cx(0, 2)
    out = cancel_adjacent(qc)
    assert len(out.data) == 3


def test_1q_on_other_wire_does_not_break_pair():
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.h(1)
    qc.cx(0, 2)
    out = cancel_adjacent(qc)
    assert len(out.data) == 1  # only the h(1) survives
    assert _equiv(qc, out)


def test_odd_run_reduces_to_one():
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(0, 2)
    qc.cx(0, 2)
    out = cancel_adjacent(qc)
    assert len(out.data) == 1
    assert _equiv(qc, out)


def test_swap_swap_cancels():
    qc = QuantumCircuit(5)
    qc.swap(0, 2)
    qc.swap(0, 2)
    assert len(cancel_adjacent(qc).data) == 0


def test_cz_cz_cancels():
    qc = QuantumCircuit(5)
    qc.cz(0, 2)
    qc.cz(0, 2)
    assert len(cancel_adjacent(qc).data) == 0


def test_fixpoint_nested_pairs():
    # Removing the inner cx(0,3) pair makes the outer cx(0,2) pair adjacent.
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(0, 3)
    qc.cx(0, 3)
    qc.cx(0, 2)
    out = cancel_adjacent(qc)
    assert len(out.data) == 0
    assert _equiv(qc, out)


def test_idempotent():
    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(0, 3)
    qc.cx(0, 3)
    qc.cx(0, 2)
    once = cancel_adjacent(qc)
    twice = cancel_adjacent(once)
    assert len(twice.data) == len(once.data)
    assert _equiv(once, twice)


def test_equivalence_preserved_on_random_circuits():
    for seed in range(10):
        qc = random_circuit(seed=seed, num_gates=20, p_two_qubit=0.7)
        out = cancel_adjacent(qc)
        assert _equiv(qc, out)


def test_input_reduction_drops_gates_and_swaps():
    # Duplicated non-edge CX pair cancels before routing: 2 SWAPs -> 1.
    qc = QuantumCircuit(5)
    qc.cx(0, 1)
    qc.cx(0, 1)
    qc.cx(3, 4)
    red = reduce_input(qc)
    assert len(red.data) == 1

    greedy = GreedyShortestPathSolver()
    before = greedy.solve(make_problem(qc), seed=0)
    after = greedy.solve(make_problem(red), seed=0)
    assert len(after.swaps) < len(before.swaps)


def test_route_reduced_never_worse_than_original():
    greedy = GreedyShortestPathSolver()
    for seed in range(10):
        qc = random_circuit(seed=seed, num_gates=30, p_two_qubit=0.7)
        red = reduce_input(qc)
        n0 = len(greedy.solve(make_problem(qc), seed=0).swaps)
        n1 = len(greedy.solve(make_problem(red), seed=0).swaps)
        assert n1 <= n0


def test_optimization_pass_applies_cancellation():
    from odra_router.optimize.baseline import OptimizationPass

    qc = QuantumCircuit(5)
    qc.cx(0, 2)
    qc.cx(0, 2)
    qc.cx(1, 4)
    out = OptimizationPass().run(qc)
    assert len(out.data) == 1
    assert _equiv(qc, out)
    # cancellation=False leaves the circuit untouched
    same = OptimizationPass(cancellation=False).run(qc)
    assert len(same.data) == 3
