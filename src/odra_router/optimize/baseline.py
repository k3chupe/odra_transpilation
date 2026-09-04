"""Optimization stage passes (phase 2): post-routing gate cancellation."""

from __future__ import annotations

from qiskit import QuantumCircuit

from odra_router.optimize.cancel import cancel_adjacent


class OptimizationPass:
    """Reduce two-qubit count / depth of a routed circuit."""

    name = "baseline_optimize"

    def __init__(self, cancellation: bool = True) -> None:
        self.cancellation = cancellation

    def run(self, circuit: QuantumCircuit) -> QuantumCircuit:
        out = circuit
        if self.cancellation:
            out = cancel_adjacent(out)
        return out
