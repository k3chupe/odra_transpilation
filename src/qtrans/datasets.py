"""Load external QASM benchmark circuits and fetch a curated QASM corpus.

Contributors can drop OpenQASM 2.0 files into a directory and run the repo's
solvers on them via :func:`qasm_circuits`.  :func:`fetch_corpus` downloads a
small public 5-qubit corpus (QUEKO) into ``benchmarks/qasm`` relative to the
current working directory.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve

from qiskit import QuantumCircuit
from qiskit.qasm2 import load

from qtrans.arch import ODRA5_NUM_QUBITS

#: (filename, url) pairs of 5-qubit QUEKO benchmark circuits, from the public
#: repo qqq-wisc/quantum-compiler-benchmark-circuits (branch ``main``, dir ``queko``).
QUEKO_CORPUS: list[tuple[str, str]] = [
    (
        "queko_linear_5.qasm",
        "https://raw.githubusercontent.com/qqq-wisc/quantum-compiler-benchmark-circuits/main/queko/queko_linear_5.qasm",
    ),
    (
        "queko_mesh_5.qasm",
        "https://raw.githubusercontent.com/qqq-wisc/quantum-compiler-benchmark-circuits/main/queko/queko_mesh_5.qasm",
    ),
    (
        "queko_tor_5.qasm",
        "https://raw.githubusercontent.com/qqq-wisc/quantum-compiler-benchmark-circuits/main/queko/queko_tor_5.qasm",
    ),
]


def load_qasm(path) -> QuantumCircuit:
    """Parse an OpenQASM 2.0 file into a qiskit QuantumCircuit."""
    return load(str(path))


def qasm_circuits(directory, max_qubits=ODRA5_NUM_QUBITS) -> list[tuple[str, QuantumCircuit]]:
    """Recursively find ``*.qasm`` under ``directory`` and parse each.

    Only circuits with ``num_qubits <= max_qubits`` are kept, sorted by the
    name relative to ``directory`` (POSIX-style, without the ``.qasm``
    extension).  Non-QASM files are ignored.  Empty directory -> ``[]``.
    """
    directory = Path(directory)
    circuits = []
    for path in sorted(
        directory.rglob("*.qasm"),
        key=lambda p: p.relative_to(directory).as_posix(),
    ):
        circuit = load_qasm(path)
        if circuit.num_qubits <= max_qubits:
            name = path.relative_to(directory).as_posix()[: -len(".qasm")]
            circuits.append((name, circuit))
    return circuits


def fetch_corpus(target_dir: Path = Path("benchmarks/qasm")) -> list[Path]:
    """Download QUEKO_CORPUS into ``target_dir`` (created if missing).

    Uses only the Python standard library (``urllib.request``).  Files that
    already exist are skipped (idempotent).  Prints one short line per
    downloaded/skipped file and returns the list of target Paths (downloaded
    OR already present).  The default ``target_dir`` resolves relative to the
    current working directory.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, url in QUEKO_CORPUS:
        dest = target_dir / filename
        if dest.exists():
            print(f"skip {filename} (already present)")
            paths.append(dest)
            continue
        try:
            urlretrieve(url, dest)
        except (URLError, OSError) as exc:
            raise RuntimeError(
                f"failed to download {filename} from {url}: {exc}"
            ) from exc
        print(f"downloaded {filename}")
        paths.append(dest)
    return paths
