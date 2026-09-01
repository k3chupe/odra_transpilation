"""Tests for odra_router.datasets — all offline (no network)."""

from __future__ import annotations

from qiskit import QuantumCircuit

from odra_router.datasets import QUEKO_CORPUS, load_qasm, qasm_circuits

FIVE_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[5];
x q[0];
x q[1];
cx q[0], q[1];
"""

SIX_QUBIT_QASM = """\
OPENQASM 2.0;
include "qelib1.inc";
qreg q[6];
x q[0];
cx q[0], q[1];
"""


def test_load_qasm_parses_file(tmp_path):
    qasm_file = tmp_path / "tiny.qasm"
    qasm_file.write_text(FIVE_QUBIT_QASM)

    circuit = load_qasm(qasm_file)

    assert isinstance(circuit, QuantumCircuit)
    assert circuit.num_qubits == 5


def test_qasm_circuits_filters_sorts_and_names(tmp_path):
    (tmp_path / "five.qasm").write_text(FIVE_QUBIT_QASM)
    (tmp_path / "six.qasm").write_text(SIX_QUBIT_QASM)
    (tmp_path / "notes.txt").write_text("not qasm")

    circuits = qasm_circuits(tmp_path, max_qubits=5)

    assert [name for name, _ in circuits] == ["five"]
    assert circuits[0][1].num_qubits == 5


def test_qasm_circuits_empty_directory(tmp_path):
    assert qasm_circuits(tmp_path) == []


def test_queko_corpus_structure():
    assert QUEKO_CORPUS
    for filename, url in QUEKO_CORPUS:
        assert isinstance(filename, str)
        assert isinstance(url, str)
        assert filename.endswith(".qasm")
