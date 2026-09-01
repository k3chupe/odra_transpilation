"""Optimization stage solvers (phase 2) — stubs."""

from __future__ import annotations

from qiskit import QuantumCircuit


class OptimizationPass:
    """Reduce depth / two-qubit count after routing."""

    name = "baseline_optimize"

    def run(self, circuit: QuantumCircuit) -> QuantumCircuit:
        # ponytail: identity until optimize/cancel.py lands
        return circuit
