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
