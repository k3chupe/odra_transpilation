# qtrans — quantum transpiler project

Custom **Routing** and **Optimization** stages for the ODRA5 (IQM Adonis) 5-qubit star topology, compared against Qiskit 1.2.

## Setup (5 commands)

```bash
git clone <repo-url> && cd transpilacja
conda env create -f environment.yml
conda activate qtrans
pip install -e ".[dev]"
pytest -q
```

Optional extras:

```bash
pip install -e ".[hardware]"   # IQM fake Adonis backend
pip install -e ".[ilp]"        # Gurobi for ILP baselines
pip install -e ".[analysis]"   # pandas/plotly for plots
```

## Who owns what

See [docs/split.md](docs/split.md). Integration contract: [docs/contract.md](docs/contract.md).

## Run benchmarks

```bash
qtrans-bench
# -> results/benchmark.csv
```

## Private notes (Syncthing)

Sync **`_local/`** only — not the repo root. See `_local/README.md`.

## Branch workflow

- `main` — green CI only
- `feat/tabu`, `feat/ga`, `feat/dp` — one solver per branch
