"""ODRA5 / IQM Adonis 5-qubit star topology — no IQM dependency."""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.circuit import Instruction, Parameter
from qiskit.transpiler import CouplingMap, Target
from qiskit.circuit.library import CZGate

# Star topology: center QB3 (index 2) connected to outer qubits 0,1,3,4
#     0
#     |
# 1 - 2 - 3
#     |
#     4
ODRA5_EDGES = [(0, 2), (1, 2), (2, 3), (2, 4)]
ODRA5_NUM_QUBITS = 5


def odra5_coupling_map() -> CouplingMap:
    return CouplingMap(ODRA5_EDGES)


def odra5_target() -> Target:
    """Native gate set: phased-R (as ``r``) and ``cz``."""
    target = Target(num_qubits=ODRA5_NUM_QUBITS)
    theta = Parameter("theta")
    phi = Parameter("phi")
    r_gate = Instruction("r", 1, 0, [theta, phi])
    for q in range(ODRA5_NUM_QUBITS):
        target.add_instruction(r_gate, {(q,): None})
    for a, b in ODRA5_EDGES:
        target.add_instruction(CZGate(), {(a, b): None})
        target.add_instruction(CZGate(), {(b, a): None})
    return target


def odra5_backend_props() -> dict:
    """Minimal metadata for benchmarks and docs."""
    return {
        "name": "ODRA5",
        "num_qubits": ODRA5_NUM_QUBITS,
        "topology": "star",
        "center_qubit": 2,
        "native_gates": ("r", "cz"),
        "edges": ODRA5_EDGES,
    }


def trivial_circuit() -> QuantumCircuit:
    """Small smoke-test circuit (5 qubits, 2 CX)."""
    qc = QuantumCircuit(5)
    qc.h(3)
    qc.cx(4, 3)
    qc.cx(0, 1)
    return qc
