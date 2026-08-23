import qiskit


def test_qiskit_version_pinned():
    major, minor, *_ = qiskit.__version__.split(".")
    assert (int(major), int(minor)) == (1, 2), (
        f"Expected qiskit 1.2.x, got {qiskit.__version__}. "
        "Run: conda env create -f environment.yml"
    )
