"""Seeded random circuit generator for benchmarks and tests."""

from __future__ import annotations

import json
import random
from pathlib import Path

from qiskit import QuantumCircuit
from qiskit.circuit import Parameter

from qtrans.arch import ODRA5_NUM_QUBITS

# All six non-edge pairs of the ODRA5 star. A cycle over them forces the
# routing to keep swapping through the center, unlike random circuits where
# many interactions are already adjacent or cheap.
HARD_PAIRS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 3),
    (3, 4),
    (4, 0),
    (0, 3),
    (1, 4),
)


def hard_circuit(rounds: int, *, seed: int = 0) -> QuantumCircuit:
    """Deterministic adversarial circuit: ``rounds`` cycles over non-edge pairs.

    Each round emits one ``cx`` per non-edge pair (6 gates), so routing has to
    move qubits through the center continuously. Deterministic for a given
    ``seed`` (seed only permutes the pair order per round).
    """
    rng = random.Random(seed)
    qc = QuantumCircuit(ODRA5_NUM_QUBITS)
    for _ in range(rounds):
        order = rng.sample(HARD_PAIRS, len(HARD_PAIRS))
        for a, b in order:
            qc.cx(a, b)
    return qc


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
