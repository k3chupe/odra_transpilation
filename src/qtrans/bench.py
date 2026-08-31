"""Compare solvers on benchmark suite; write CSV to results/."""

from __future__ import annotations

import csv
import statistics
import time
from pathlib import Path

from qiskit import QuantumCircuit

from qtrans.contract import SOLVERS, apply, make_problem, metrics, native_cz_cost, validate
from qtrans.generator import circuits_from_suite, hard_circuit, random_circuit
from qtrans.qiskit_glue import qiskit_baseline
from qtrans.queko import odra5_queko
from qtrans.routing.baseline import BruteForceLayoutSolver


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
                m = {"swap_count": -1, "cz_cost": -1, "two_qubit_count": -1, "depth": -1, "size": -1}
                err = str(exc)
            elapsed = time.perf_counter() - t0
            rows.append(
                {
                    "case": case_name,
                    "solver": solver_name,
                    "swap_count": m["swap_count"],
                    "cz_cost": m["cz_cost"],
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
                    "cz_cost": native_cz_cost(qc),
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
                    "cz_cost": -1,
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
                    m = {"swap_count": -1, "cz_cost": -1, "two_qubit_count": -1, "depth": -1, "size": -1}
                    err = str(exc)
                elapsed = time.perf_counter() - t0
                rows.append(
                    {
                        "case": case_name,
                        "solver": solver_name,
                        "swap_count": m["swap_count"],
                        "cz_cost": m["cz_cost"],
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
                        "cz_cost": native_cz_cost(qc),
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
                        "cz_cost": -1,
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


# Solver quality saturates on the ODRA5 star (layout alone determines the
# optimum), so the sweat benchmark compares the time-quality frontier:
# best result found within a time budget, repeated over seeds.
SWEAT_BUDGETS: tuple[float, ...] = (0.05, 0.1, 0.2, 0.5, 1.0)
SWEAT_SOLVERS: tuple[str, ...] = (
    "greedy_shortest_path",
    "brute_force_layout",
    "exact_dp",
    "tabu_search",
    "tabu_sabre_start",
    "genetic_trivial",
)


def sweat_cases() -> list[tuple[str, QuantumCircuit]]:
    """Hard, dense-random and deep-QUEKO instances for the budget sweep."""
    cases: list[tuple[str, QuantumCircuit]] = []
    for rounds in (4, 8, 12):
        cases.append((f"hard_{rounds}r", hard_circuit(rounds)))
    for gates, seed in ((40, 0), (40, 1), (60, 0), (60, 1)):
        cases.append(
            (f"rand{gates}_s{seed}", random_circuit(seed=seed, num_gates=gates, p_two_qubit=0.7))
        )
    for depth in (8, 16, 24):
        circuit, _ = odra5_queko(depth, density_vec=(0.25, 0.3), seed=0)
        cases.append((f"queko_d{depth}", circuit))
    return cases


def run_sweat_benchmark(
    out_dir: Path | None = None,
    *,
    budgets: tuple[float, ...] = SWEAT_BUDGETS,
    reps: int = 5,
    solvers: list[str] | None = None,
    cases: list[tuple[str, QuantumCircuit]] | None = None,
    reference_budget_s: float = 30.0,
) -> Path:
    """Budget sweep: best solution per solver within each time budget, R reps.

    Reference ("ideal") is brute force over layouts with a generous budget;
    on the star that equals the fixed-gate-order optimum (see exact_dp).
    Writes results/sweat.csv and a markdown summary with medians.
    """
    out_dir = out_dir or Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sweat.csv"
    names = solvers or list(SWEAT_SOLVERS)
    cases = cases if cases is not None else sweat_cases()

    rows: list[dict] = []
    for case_name, circuit in cases:
        problem = make_problem(circuit)
        reference = len(BruteForceLayoutSolver().solve(problem, seed=0, budget_s=reference_budget_s).swaps)
        for budget in budgets:
            for rep in range(reps):
                for solver_name in names:
                    solver = SOLVERS[solver_name]
                    t0 = time.perf_counter()
                    try:
                        sol = solver.solve(problem, seed=rep, budget_s=budget)
                        validate(problem, sol)
                        m = metrics(problem, sol)
                        err = ""
                    except Exception as exc:  # ponytail: bench captures all solver failures
                        m = {"swap_count": -1, "cz_cost": -1}
                        err = str(exc)
                    elapsed = time.perf_counter() - t0
                    swaps = m["swap_count"]
                    rows.append(
                        {
                            "case": case_name,
                            "solver": solver_name,
                            "budget_s": budget,
                            "rep": rep,
                            "seed": rep,
                            "swap_count": swaps,
                            "cz_cost": m["cz_cost"],
                            "evals": getattr(solver, "last_evals", -1),
                            "seconds": round(elapsed, 6),
                            "optimal": swaps >= 0 and swaps == reference,
                            "gap": (swaps - reference) if swaps >= 0 else -1,
                            "error": err,
                        }
                    )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    _write_sweat_summary(out_dir / "sweat-summary.md", rows, names, budgets)
    return out_path


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else -1.0


def _write_sweat_summary(path: Path, rows: list[dict], names: list[str], budgets: tuple[float, ...]) -> None:
    """Compact markdown: median swaps/gap/%optimal/time per case+budget+solver."""
    by_key: dict[tuple[str, str, float], list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["case"], r["solver"], r["budget_s"]), []).append(r)

    lines: list[str] = [
        "# Sweat benchmark (budget sweep)",
        "",
        "Budget sweep: best solution found within each time budget, R repetitions per seed.",
        "Reference = brute force over layouts with a generous budget (on the star this equals",
        "the fixed-gate-order optimum, see exact_dp). `%opt` = fraction of reps reaching the",
        "reference swap count; `gap` = median swaps above reference; `med_s` = median seconds;",
        "`med evals` = median layout evaluations per solve.",
        "",
        "Structural note: on the ODRA5 star exactly 24 of the 120 layouts reach the optimum",
        "for every circuit (the 4! leaf permutations), so random layout sampling converges",
        "almost immediately. The sweep therefore shows time/eval overhead rather than a",
        "quality gradient between the layout-searching solvers.",
        "",
    ]
    for budget in budgets:
        for case in sorted({r["case"] for r in rows}):
            lines.append(f"## {case} @ {budget}s")
            lines.append("")
            lines.append("| solver | med swaps | gap | %opt | med evals | med_s |")
            lines.append("|---|---|---|---|---|---|")
            for name in names:
                reps_rows = by_key.get((case, name, budget), [])
                if not reps_rows:
                    continue
                swaps = [r["swap_count"] for r in reps_rows if r["swap_count"] >= 0]
                gaps = [r["gap"] for r in reps_rows if r["gap"] >= 0]
                opt = sum(1 for r in reps_rows if r["optimal"]) / len(reps_rows)
                evals = [r["evals"] for r in reps_rows if r["evals"] >= 0]
                secs = [r["seconds"] for r in reps_rows]
                lines.append(
                    f"| {name} | {_median(swaps):g} | {_median(gaps):g} | {100*opt:.0f}% | "
                    f"{_median(evals):g} | {_median(secs):.3f} |"
                )
            lines.append("")

    # Warm-start ablation at equal budget.
    lines.append("## Warm start: tabu_search vs tabu_sabre_start")
    lines.append("")
    lines.append("| case | budget_s | random %opt | sabre %opt | random med_s | sabre med_s |")
    lines.append("|---|---|---|---|---|---|")
    for budget in budgets:
        for case in sorted({r["case"] for r in rows}):
            def opt_rate(name: str) -> float:
                rs = by_key.get((case, name, budget), [])
                return (sum(1 for r in rs if r["optimal"]) / len(rs)) if rs else -1.0

            def med_time(name: str) -> float:
                rs = by_key.get((case, name, budget), [])
                return _median([r["seconds"] for r in rs])
            lines.append(
                f"| {case} | {budget} | {100*opt_rate('tabu_search'):.0f}% | "
                f"{100*opt_rate('tabu_sabre_start'):.0f}% | {med_time('tabu_search'):.3f} | "
                f"{med_time('tabu_sabre_start'):.3f} |"
            )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main_sweat() -> None:
    path = run_sweat_benchmark()
    print(f"Wrote {path}")


FIDELITY_CASES_EXTRA_ROUNDS: tuple[int, ...] = (2, 4, 8)


def fidelity_cases() -> list[tuple[str, QuantumCircuit]]:
    """Benchmark suite + hard adversarial circuits for the fidelity benchmark."""
    cases = circuits_from_suite()
    for rounds in FIDELITY_CASES_EXTRA_ROUNDS:
        cases.append((f"hard_{rounds}r", hard_circuit(rounds)))
    return cases


def run_fidelity_benchmark(
    out_dir: Path | None = None,
    *,
    budget_s: float = 30.0,
    solvers: list[str] | None = None,
) -> Path:
    """Compare solvers on total -ln(fidelity) of the routed circuit.

    Every solver is run on the suite + hard cases and scored by
    ``fidelity_cost`` (lower is better) with the default ODRA5 fidelity model,
    alongside the classic CZ metrics. Writes results/benchmark-fidelity.csv
    and a markdown summary with per-case winners and greedy gaps.
    """
    from qtrans.fidelity import fidelity_cost, odra5_default_fidelity

    model = odra5_default_fidelity()
    out_dir = out_dir or Path("results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "benchmark-fidelity.csv"
    names = solvers or [n for n in SOLVERS if n not in ("sabre_baseline",)]

    rows: list[dict] = []
    for case_name, circuit in fidelity_cases():
        problem = make_problem(circuit)
        for solver_name in names:
            solver = SOLVERS[solver_name]
            t0 = time.perf_counter()
            try:
                sol = solver.solve(problem, seed=0, budget_s=budget_s)
                validate(problem, sol)
                m = metrics(problem, sol)
                fcost = fidelity_cost(apply(problem, sol), model)
                err = ""
            except Exception as exc:  # ponytail: bench captures all solver failures
                m = {"swap_count": -1, "cz_cost": -1, "two_qubit_count": -1, "depth": -1, "size": -1}
                fcost = -1.0
                err = str(exc)
            elapsed = time.perf_counter() - t0
            rows.append(
                {
                    "case": case_name,
                    "solver": solver_name,
                    "swap_count": m["swap_count"],
                    "cz_cost": m["cz_cost"],
                    "fidelity_cost": round(fcost, 6) if fcost >= 0 else -1,
                    "depth": m["depth"],
                    "evals": getattr(solver, "last_evals", -1),
                    "seconds": round(elapsed, 4),
                    "error": err,
                }
            )

        t0 = time.perf_counter()
        try:
            qc = qiskit_baseline(circuit)
            dag = circuit_to_dag(qc)
            rows.append(
                {
                    "case": case_name,
                    "solver": "qiskit_preset",
                    "swap_count": len([nd for nd in dag.op_nodes() if nd.op.name == "swap"]),
                    "cz_cost": native_cz_cost(qc),
                    "fidelity_cost": round(fidelity_cost(qc, model), 6),
                    "depth": dag.depth(),
                    "evals": -1,
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
                    "cz_cost": -1,
                    "fidelity_cost": -1,
                    "depth": -1,
                    "evals": -1,
                    "seconds": round(time.perf_counter() - t0, 4),
                    "error": str(exc),
                }
            )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    _write_fidelity_summary(out_dir / "fidelity-summary.md", rows, names)
    return out_path


def _write_fidelity_summary(path: Path, rows: list[dict], names: list[str]) -> None:
    """Markdown: per-case best fidelity, greedy gap, tabu improvement, cz-vs-fidelity note."""
    by_case: dict[str, list[dict]] = {}
    for r in rows:
        if r["error"]:
            continue
        by_case.setdefault(r["case"], []).append(r)

    cases = sorted(by_case)
    lines: list[str] = [
        "# Fidelity benchmark (total -ln f over routed circuits)",
        "",
        "Default ODRA5 fidelity model (`odra5_default_fidelity`), lower is better.",
        "`tabu_fidelity` = move-based tabu (random layout warm start),",
        "`tabu_fidelity_greedy` = same with identity-layout greedy warm start,",
        "`brute_fidelity_layout` = reference, best of all 120 layouts with greedy",
        "SWAP routing. `greedy` is the identity-layout baseline.",
        "",
    ]

    for case in cases:
        rs = by_case[case]
        lines.append(f"## {case}")
        lines.append("")
        lines.append("| solver | fidelity_cost | swap_count | cz_cost | seconds |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(rs, key=lambda r: (r["fidelity_cost"], r["solver"])):
            lines.append(
                f"| {r['solver']} | {r['fidelity_cost']:g} | {r['swap_count']:g} | "
                f"{r['cz_cost']:g} | {r['seconds']:g} |"
            )
        lines.append("")

    # Aggregate: how often each solver wins, and the greedy gap.
    wins: dict[str, int] = {}
    for case in cases:
        best = min(by_case[case], key=lambda r: r["fidelity_cost"])
        wins[best["solver"]] = wins.get(best["solver"], 0) + 1
    lines.append("## Wins per case")
    lines.append("")
    for name, count in sorted(wins.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {name}: {count}/{len(cases)}")
    lines.append("")

    greedy_rows = [r for r in rows if r["solver"] == "greedy_shortest_path" and not r["error"]]
    if greedy_rows:
        gaps: list[float] = []
        for r in rows:
            if r["solver"] == "greedy_shortest_path" or r["error"]:
                continue
            gr = next((g for g in greedy_rows if g["case"] == r["case"]), None)
            if gr is not None and gr["fidelity_cost"] > 0:
                gaps.append(100 * (r["fidelity_cost"] - gr["fidelity_cost"]) / gr["fidelity_cost"])
        if gaps:
            lines.append(f"Median fidelity_cost gap vs greedy over all solver-case pairs: {_median(gaps):.1f}%")
            lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main_fidelity() -> None:
    path = run_fidelity_benchmark()
    print(f"Wrote {path}")
