# qtrans — quantum transpiler project

Custom **Routing** and **Optimization** stages for the ODRA5 (IQM Adonis) 5-qubit star topology, compared against Qiskit 1.2.

## Setup

Requirements: Python 3.11+, [Conda](https://docs.conda.io/) (recommended).

```bash
git clone <repo-url> && cd transpilacja
conda env create -f environment.yml
conda activate qtrans
pip install -e ".[dev]"
pytest -q
```

On Windows (PowerShell), run commands one at a time instead of chaining with `&&`.

Without Conda: see dependencies in [pyproject.toml](pyproject.toml), then `pip install -e ".[dev]"`.

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
qtrans-bench
# -> results/benchmark.csv
```

Benchmark cases: [benchmarks/suite.json](benchmarks/suite.json).

## Documentation

| Topic | Location |
|-------|----------|
| Solver contract | [docs/contract.md](docs/contract.md) |
| Directory layout | [docs/split.md](docs/split.md) |
| Repo context (agents) | [AGENTS.md](AGENTS.md) |

## Private notes (Syncthing)

Sync **`_local/`** only — not the repo root. See [_local/README.md](_local/README.md).

## Branch workflow

- `main` — green CI only
- Feature branches — one solver or logical unit per PR
