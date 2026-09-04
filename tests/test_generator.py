from odra_router.generator import (
    HARD_PAIRS,
    hard_circuit,
    load_suite,
    random_circuit,
    circuits_from_suite,
)


def test_load_suite_has_cases():
    cases = load_suite()
    assert len(cases) >= 5
    assert "seed" in cases[0]


def test_random_circuit_reproducible():
    a = random_circuit(seed=42, num_gates=10)
    b = random_circuit(seed=42, num_gates=10)
    assert a == b


def test_hard_circuit_shape_and_determinism():
    qc = hard_circuit(rounds=3, seed=0)
    assert qc.num_qubits == 5
    two_q = [g for g in qc.data if len(g.qubits) == 2]
    assert len(two_q) == 6 * 3
    assert hard_circuit(rounds=3, seed=0) == qc


def test_hard_circuit_only_non_edge_pairs():
    edges = {(0, 2), (1, 2), (2, 3), (2, 4)}
    for rounds in (1, 2, 4):
        qc = hard_circuit(rounds)
        for gate in qc.data:
            if len(gate.qubits) == 2:
                a, b = (q._index for q in gate.qubits)
                assert (a, b) in HARD_PAIRS and (a, b) not in edges


def test_circuits_from_suite():
    pairs = circuits_from_suite()
    assert len(pairs) == len(load_suite())
    for name, qc in pairs:
        assert qc.num_qubits == 5
        assert name


def test_layered_random_circuit_deterministic_and_structured():
    from qiskit.converters import circuit_to_dag

    from odra_router.generator import layered_random_circuit

    a = layered_random_circuit(12, seed=7)
    b = layered_random_circuit(12, seed=7)
    c = layered_random_circuit(12, seed=8)
    assert a == b
    assert a != c
    assert a.num_qubits == 5
    assert len(circuit_to_dag(a).two_qubit_ops()) > 0  # layers carry 2Q gates
    # seeds with no two-qubit gates must still exist deterministically
    small = layered_random_circuit(3, p_two_qubit=0.0, seed=0)
    assert len(circuit_to_dag(small).two_qubit_ops()) == 0


def test_batch_circuits_reproducible():
    from odra_router.generator import _batch_circuits

    batch = _batch_circuits((20,), (0.5,), num_seeds=2, hard_rounds_list=(4,))
    names = [n for n, _, _ in batch]
    assert len(batch) == 2 + 2  # 1x1x2 random + 1x2 hard
    assert all(n.startswith(("random_", "hard_")) for n in names)
    again = _batch_circuits((20,), (0.5,), num_seeds=2, hard_rounds_list=(4,))
    assert [qc for _, qc, _ in batch] == [qc for _, qc, _ in again]


def test_main_gen_writes_qasm_and_manifest(tmp_path):
    from odra_router.datasets import qasm_circuits
    from odra_router.generator import main_gen

    main_gen(
        [
            "--num-gates", "10,15",
            "--p2q", "0.6",
            "--seeds", "2",
            "--hard-rounds", "2",
            "--out", str(tmp_path),
        ]
    )
    manifest = (tmp_path / "manifest.json")
    assert manifest.exists()
    import json

    data = json.loads(manifest.read_text())
    assert len(data["cases"]) == 6  # 2 gate counts x 2 seeds + 2 hard
    files = qasm_circuits(tmp_path)
    assert len(files) == 6
    names = {n for n, _ in files}
    assert names == {c["name"] for c in data["cases"]}
    # every QASM reloads and parses
    for _, qc in files:
        assert qc.num_qubits == 5
    # idempotent regeneration produces identical bytes
    main_gen(
        [
            "--num-gates", "10,15",
            "--p2q", "0.6",
            "--seeds", "2",
            "--hard-rounds", "2",
            "--out", str(tmp_path),
        ]
    )
    assert (tmp_path / "random_g10_p0_6_s0.qasm").exists()
