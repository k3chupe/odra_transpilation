"""Seeded random circuit generator for benchmarks and tests."""

from __future__ import annotations

import json
import random
from pathlib import Path

from qiskit import QuantumCircuit
from qiskit.circuit import Parameter

from qtrans.arch import ODRA5_NUM_QUBITS


def random_circuit(
    num_qubits: int = ODRA5_NUM_QUBITS,
    num_gates: int = 10,
    *,
    seed: int = 0,
    p_two_qubit: float = 0.4,
) -> QuantumCircuit:
    """Random circuit over ``cx``, ``h``, ``rz`` (no measurements)."""
    rng = random.Random(seed)
    qc = QuantumCircuit(num_qubits)
    for _ in range(num_gates):
        if rng.random() < p_two_qubit and num_qubits >= 2:
            a, b = rng.sample(range(num_qubits), 2)
            qc.cx(a, b)
        else:
            qc.h(rng.randrange(num_qubits))
            qc.rz(rng.uniform(0, 6.28), rng.randrange(num_qubits))
    return qc


def load_suite(path: Path | None = None) -> list[dict]:
    path = path or Path(__file__).resolve().parents[2] / "benchmarks" / "suite.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def circuits_from_suite(path: Path | None = None) -> list[tuple[str, QuantumCircuit]]:
    out: list[tuple[str, QuantumCircuit]] = []
    for case in load_suite(path):
        qc = random_circuit(
            num_qubits=case.get("num_qubits", ODRA5_NUM_QUBITS),
            num_gates=case["num_gates"],
            seed=case["seed"],
            p_two_qubit=case.get("p_two_qubit", 0.4),
        )
        out.append((case["name"], qc))
    return out
