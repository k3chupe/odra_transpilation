"""odra5_target and the Qiskit preset integration must actually run."""

from odra_router.arch import ODRA5_EDGES, odra5_target, trivial_circuit
from odra_router.contract import SOLVERS
from odra_router.qiskit_glue import qiskit_baseline, transpile_with_solver


def test_odra5_target_builds():
    target = odra5_target()
    assert target.num_qubits == 5
    assert set(target.operation_names) == {"r", "cz"}
    directed = [(a, b) for a, b in ODRA5_EDGES] + [(b, a) for a, b in ODRA5_EDGES]
    for a, b in directed:
        assert target.instruction_supported("cz", (a, b))


def test_qiskit_baseline_runs_and_stays_native():
    out = qiskit_baseline(trivial_circuit())
    assert set(out.count_ops()) <= {"r", "cz"}


def test_transpile_with_solver_runs_and_stays_native():
    out = transpile_with_solver(trivial_circuit(), SOLVERS["greedy_shortest_path"])
    assert set(out.count_ops()) <= {"r", "cz"}
