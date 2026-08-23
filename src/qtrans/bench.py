"""Compare solvers on benchmark suite; write CSV to results/."""

from __future__ import annotations

import csv
import time
from pathlib import Path

from qtrans.contract import SOLVERS, make_problem, metrics, validate
from qtrans.generator import circuits_from_suite
from qtrans.qiskit_glue import qiskit_baseline


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
