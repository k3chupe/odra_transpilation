"""Compare solvers on benchmark suite; write CSV to results/."""

from __future__ import annotations

import csv
import time
from pathlib import Path

from qtrans.contract import SOLVERS, make_problem, metrics, validate
from qtrans.generator import circuits_from_suite
from qtrans.qiskit_glue import qiskit_baseline
from qtrans.queko import odra5_queko


def run_benchmark(
    out_dir: Path | None = None,
    *,
    budget_s: float = 30.0,
    solvers: list[str] | None = None,
) -> Path:
    out_dir = out_dir or Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "benchmark.csv"
    names = solvers or [n for n in SOLVERS if n not in ("sabre_baseline",)]

    rows: list[dict] = []
    for case_name, circuit in circuits_from_suite():
        problem = make_problem(circuit)
        for solver_name in names:
            solver = SOLVERS[solver_name]
            t0 = time.perf_counter()
            try:
                sol = solver.solve(problem, seed=0, budget_s=budget_s)
                validate(problem, sol)
                m = metrics(problem, sol)
                err = ""
            except Exception as exc:  # ponytail: bench captures all solver failures
                m = {"swap_count": -1, "two_qubit_count": -1, "depth": -1, "size": -1}
                err = str(exc)
            elapsed = time.perf_counter() - t0
            rows.append(
                {
                    "case": case_name,
                    "solver": solver_name,
                    "swap_count": m["swap_count"],
                    "two_qubit_count": m["two_qubit_count"],
                    "depth": m["depth"],
                    "size": m["size"],
                    "seconds": round(elapsed, 4),
                    "error": err,
                }
            )

        t0 = time.perf_counter()
        try:
            qc = qiskit_baseline(circuit)
            from qiskit.converters import circuit_to_dag

            dag = circuit_to_dag(qc)
            rows.append(
                {
                    "case": case_name,
                    "solver": "qiskit_preset",
                    "swap_count": len([n for n in dag.op_nodes() if n.op.name == "swap"]),
                    "two_qubit_count": len(dag.two_qubit_ops()),
                    "depth": dag.depth(),
                    "size": dag.size(),
                    "seconds": round(time.perf_counter() - t0, 4),
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "case": case_name,
                    "solver": "qiskit_preset",
                    "swap_count": -1,
                    "two_qubit_count": -1,
                    "depth": -1,
                    "size": -1,
                    "seconds": round(time.perf_counter() - t0, 4),
                    "error": str(exc),
                }
            )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main() -> None:
    path = run_benchmark()
    print(f"Wrote {path}")


def run_queko_benchmark(
    out_dir: Path | None = None,
    *,
    depths: tuple[int, ...] = (4, 8, 12),
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    density_vec: tuple[float, float] = (0.2, 0.3),
    budget_s: float = 30.0,
    solvers: list[str] | None = None,
) -> Path:
    """Run solvers on QUEKO circuits with a known optimum of 0 SWAPs."""
    out_dir = out_dir or Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "queko.csv"
    names = solvers or [n for n in SOLVERS if n not in ("sabre_baseline",)]

    rows: list[dict] = []
    for depth in depths:
        for seed in seeds:
            case_name = f"queko_d{depth}_s{seed}"
            circuit, _optimal_layout = odra5_queko(depth, density_vec=density_vec, seed=seed)
            problem = make_problem(circuit)

            for solver_name in names:
                solver = SOLVERS[solver_name]
                t0 = time.perf_counter()
                try:
                    sol = solver.solve(problem, seed=seed, budget_s=budget_s)
                    validate(problem, sol)
                    m = metrics(problem, sol)
                    err = ""
                except Exception as exc:  # ponytail: bench captures all solver failures
                    m = {"swap_count": -1, "two_qubit_count": -1, "depth": -1, "size": -1}
                    err = str(exc)
                elapsed = time.perf_counter() - t0
                rows.append(
                    {
                        "case": case_name,
                        "solver": solver_name,
                        "swap_count": m["swap_count"],
                        "depth": m["depth"],
                        "optimal": m["swap_count"] == 0,
                        "seconds": round(elapsed, 4),
                        "error": err,
                    }
                )

            t0 = time.perf_counter()
            try:
                qc = qiskit_baseline(circuit)
                from qiskit.converters import circuit_to_dag

                dag = circuit_to_dag(qc)
                swap_count = len([n for n in dag.op_nodes() if n.op.name == "swap"])
                rows.append(
                    {
                        "case": case_name,
                        "solver": "qiskit_preset",
                        "swap_count": swap_count,
                        "depth": dag.depth(),
                        "optimal": swap_count == 0,
                        "seconds": round(time.perf_counter() - t0, 4),
                        "error": "",
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "case": case_name,
                        "solver": "qiskit_preset",
                        "swap_count": -1,
                        "depth": -1,
                        "optimal": False,
                        "seconds": round(time.perf_counter() - t0, 4),
                        "error": str(exc),
                    }
                )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main_queko() -> None:
    path = run_queko_benchmark()
    print(f"Wrote {path}")

    from collections import defaultdict

    totals: dict[str, int] = defaultdict(int)
    optimal: dict[str, int] = defaultdict(int)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["error"]:
                continue
            totals[row["solver"]] += 1
            if row["optimal"] == "True":
                optimal[row["solver"]] += 1

    print("\noptimal (0 SWAP) success rate:")
    for name in sorted(totals):
        print(f"  {name}: {optimal[name]}/{totals[name]}")
