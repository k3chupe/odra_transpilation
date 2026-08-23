"""Bridge Solver implementations to Qiskit StagedPassManager."""

from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag, dag_to_circuit
from qiskit.dagcircuit import DAGCircuit
from qiskit.transpiler import PassManager, StagedPassManager, generate_preset_pass_manager
from qiskit.transpiler.basepasses import TransformationPass

from qtrans.arch import odra5_target
from qtrans.contract import Solver, RoutingProblem, apply, layout_to_qiskit, make_problem


class SolverRoutingPass(TransformationPass):
    """Replace Qiskit routing stage with a ``Solver`` from our contract."""

    def __init__(self, solver: Solver, *, seed: int = 0, budget_s: float = 30.0):
        super().__init__()
        self.solver = solver
        self.seed = seed
        self.budget_s = budget_s

    def run(self, dag: DAGCircuit) -> DAGCircuit:
        circuit = dag_to_circuit(dag)
        problem = make_problem(circuit)
        solution = self.solver.solve(problem, seed=self.seed, budget_s=self.budget_s)
        routed = apply(problem, solution)
        layout = layout_to_qiskit(solution.initial_layout, circuit)
        self.property_set["layout"] = layout
        pos = list(solution.initial_layout)
        for _, pa, pb in solution.swaps:
            from qtrans.contract import _swap_positions

            _swap_positions(pos, pa, pb)
        self.property_set["final_layout"] = layout_to_qiskit(tuple(pos), circuit)
        return circuit_to_dag(routed)


def transpile_with_solver(
    circuit: QuantumCircuit,
    solver: Solver,
    *,
    seed: int = 0,
    budget_s: float = 30.0,
    optimization_level: int = 2,
) -> QuantumCircuit:
    """Run preset transpiler but swap routing stage for ``solver``."""
    target = odra5_target()
    pm = generate_preset_pass_manager(optimization_level, target=target)
    custom_routing = PassManager(
        [SolverRoutingPass(solver, seed=seed, budget_s=budget_s)]
    )
    pm.routing = custom_routing
    return pm.run(circuit)


def qiskit_baseline(circuit: QuantumCircuit, optimization_level: int = 2) -> QuantumCircuit:
    """Full Qiskit preset transpile on ODRA5 target."""
    target = odra5_target()
    pm = generate_preset_pass_manager(optimization_level, target=target)
    return pm.run(circuit)
