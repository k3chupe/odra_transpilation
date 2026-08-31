# qtrans — quantum transpiler project

Custom **Routing** and **Optimization** stages for the ODRA5 (IQM Adonis) 5-qubit star topology, compared against Qiskit 1.2.

## Setup

Requirements: Python 3.11+, qiskit 1.2.4 (pinned, see `tests/test_env.py`).

```bash
git clone git@github.com:k3chupe/odra_transpilation.git
cd odra_transpilation
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

On Windows (PowerShell), run commands one at a time instead of chaining with `&&`.

Conda alternative: `conda env create -f environment.yml && conda activate qtrans`, then `pip install -e ".[dev]"`.

Optional extras:

```bash
pip install -e ".[hardware]"   # IQM fake Adonis backend
pip install -e ".[ilp]"        # Gurobi for ILP baselines
pip install -e ".[analysis]"   # pandas/plotly for plots
```

`pytest -q` runs all tests; registered solvers are checked automatically by [tests/test_contract.py](tests/test_contract.py).

## Add a solver

Full workflow: [docs/contract.md](docs/contract.md). Reference implementation: [src/qtrans/routing/baseline.py](src/qtrans/routing/baseline.py).

Where to put code (by directory): [docs/split.md](docs/split.md).

Qiskit integration (`transpile_with_solver`): [src/qtrans/qiskit_glue.py](src/qtrans/qiskit_glue.py).

Reference notebook: [notebooks/00_baseline.ipynb](notebooks/00_baseline.ipynb).

## Run benchmarks

```bash
qtrans-bench          # synthetic suite          -> results/benchmark.csv
qtrans-bench-queko    # known-optimal QUEKO suite -> results/queko.csv
qtrans-bench-sweat    # time-budget sweep        -> results/sweat.csv + sweat-summary.md
qtrans-bench-fidelity # fidelity objective (phase 3) -> results/benchmark-fidelity.csv + fidelity-summary.md
```

Benchmark cases: [benchmarks/suite.json](benchmarks/suite.json).
Datasets (external QASM + QUEKO): [docs/benchmarks.md](docs/benchmarks.md).

## Documentation

| Topic | Location |
|-------|----------|
| Status, results and roadmap (PL) | [STATUS.md](STATUS.md) |
| Solver contract | [docs/contract.md](docs/contract.md) |
| Directory layout | [docs/split.md](docs/split.md) |
| Benchmarks & datasets | [docs/benchmarks.md](docs/benchmarks.md) |
| Repo context (agents) | [AGENTS.md](AGENTS.md) |

## Local-only files

`_local/` is gitignored and holds machine-local notes; it is never committed.
Syncthing is configured via `.stignore` to keep repo sources out of the sync
folder — only local notes are synced.

## Branch workflow

- `main` — green CI only
- Feature branches — one solver or logical unit per PR
