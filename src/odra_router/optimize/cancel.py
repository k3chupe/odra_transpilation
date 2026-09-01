"""Gate cancellation and commutation rules — stub for phase 2."""

from __future__ import annotations

from qiskit import QuantumCircuit


def cancel_adjacent_swaps(circuit: QuantumCircuit) -> QuantumCircuit:
    """Remove consecutive SWAP pairs on the same qubits."""
    raise NotImplementedError("Phase 2: implement in optimize/cancel.py")
