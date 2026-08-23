from qtrans.generator import load_suite, random_circuit, circuits_from_suite


def test_load_suite_has_cases():
    cases = load_suite()
    assert len(cases) >= 5
    assert "seed" in cases[0]


def test_random_circuit_reproducible():
    a = random_circuit(seed=42, num_gates=10)
    b = random_circuit(seed=42, num_gates=10)
    assert a == b


def test_circuits_from_suite():
    pairs = circuits_from_suite()
    assert len(pairs) == len(load_suite())
    for name, qc in pairs:
        assert qc.num_qubits == 5
        assert name
