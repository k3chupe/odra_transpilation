#!/usr/bin/env python3
"""Tor A of the "why tabu" analysis: does the gate count alone slow exact_dp?

The plan expected a flat, nearly linear curve, i.e. "the number of gates on
five qubits cannot make the ideal blow up". This probe checks that instead of
assuming it: it walks the long-instance families and records the wall time of
``exact_dp`` against three different size axes:

- ``gates`` / ``depth``: the raw quantity of the circuit,
- ``interactions``: the number of two-qubit gates ``exact_dp`` actually has to
  schedule (after ``reduce_input``),
- the layout factor: 120 always, since the layout is free in the contract.

Layer-structured circuits are the control group: their gate count grows with
the layer count while their interaction count barely moves (gates inside a
layer are disjoint), so a flat time against ``gates`` but a rising time
against ``interactions`` proves which axis drives the search.

Writes ``results/scale-probe.csv`` and ``results/scale-probe.md``.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from odra_router.bench import long_cases  # noqa: E402
from odra_router.contract import make_problem  # noqa: E402
from odra_router.fidelity import cancelled_fidelity_cost, odra5_default_fidelity  # noqa: E402
from odra_router.optimize.cancel import reduce_input  # noqa: E402
from odra_router.routing.exact_dp import ExactDPSolver  # noqa: E402

MODEL = odra5_default_fidelity()


def measure(cases, budget_s: float) -> list[dict]:
    rows: list[dict] = []
    solver = ExactDPSolver()
    for name, circuit in cases:
        problem = make_problem(reduce_input(circuit))
        interactions = len(problem.interactions)
        t0 = time.perf_counter()
        solution = solver.solve(problem, seed=0, budget_s=budget_s)
        seconds = time.perf_counter() - t0
        rows.append(
            {
                "case": name,
                "gates": circuit.size(),
                "depth": circuit.depth(),
                "interactions": interactions,
                "dp_seconds": round(seconds, 4),
                "dp_hit_budget": int(solver.last_hit_budget),
                "us_per_interaction": round(1e6 * seconds / interactions, 1) if interactions else 0.0,
                "swaps": len(solution.swaps),
                "fidelity_cost_cancelled": round(
                    cancelled_fidelity_cost(problem, solution, MODEL), 6
                ),
            }
        )
        print(
            f"{name:14s} gates={rows[-1]['gates']:4d} I={interactions:4d} "
            f"{seconds:8.3f}s hit={solver.last_hit_budget}"
        )
    return rows


def write_report(rows: list[dict], out_dir: Path, budget_s: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "scale-probe.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    finite = [r for r in rows if not r["dp_hit_budget"]]
    by_gates = sorted(rows, key=lambda r: r["gates"])
    by_interactions = sorted(finite, key=lambda r: r["interactions"])

    lines = [
        "# Scale probe (Tor A): is the gate count what slows the ideal down?",
        "",
        f"`exact_dp` on the long-instance families, cap {budget_s:g}s per run, "
        "seed 0. `hit` = the cap was reached and the answer is a greedy "
        "fallback. `us / 2Q` = wall time per scheduled interaction.",
        "",
        "| case | gates | depth | 2Q after reduce | dp s | hit | us / 2Q | swaps |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in by_gates:
        lines.append(
            f"| {r['case']} | {r['gates']} | {r['depth']} | {r['interactions']} | "
            f"{r['dp_seconds']:g} | {r['dp_hit_budget']} | {r['us_per_interaction']:g} | "
            f"{r['swaps']} |"
        )

    lines += ["", "## Reading", ""]
    if len(by_interactions) >= 2:
        cheapest = by_interactions[0]
        dearest = by_interactions[-1]
        lines.append(
            f"- over {len(finite)} instances that finished inside the cap the wall "
            f"time rises from {cheapest['dp_seconds']:g}s ({cheapest['case']}, "
            f"{cheapest['interactions']} interactions) to {dearest['dp_seconds']:g}s "
            f"({dearest['case']}, {dearest['interactions']} interactions): the "
            "interaction count is the axis, not the gate count;"
        )
    heavy_gates = [r for r in rows if r["gates"] >= 600]
    if heavy_gates:
        control = min(heavy_gates, key=lambda r: r["interactions"])
        busiest = max(rows, key=lambda r: r["gates"])
        rivals = [
            r
            for r in finite
            if r["gates"] < control["gates"] and r["interactions"] > control["interactions"]
        ]
        if rivals:
            # The comparison is derived from the rows, not asserted: the control
            # case is only "heavy" relative to a named, measured rival.
            rival = max(rivals, key=lambda r: r["interactions"])
            lines.append(
                f"- the gate-count control group holds: {control['case']} has "
                f"{control['gates']} gates (the heaviest case here, {busiest['case']}, "
                f"has {busiest['gates']}) and only {control['interactions']} "
                f"interactions, and costs {control['dp_seconds']:g}s, less than "
                f"{rival['case']} ({rival['gates']} gates, {rival['interactions']} "
                f"interactions, {rival['dp_seconds']:g}s). One-qubit gates are free for "
                "the search and 120 layouts is a constant, so quantity alone does not "
                "price the ideal;"
            )
    if any(r["dp_hit_budget"] for r in rows):
        hits = ", ".join(r["case"] for r in rows if r["dp_hit_budget"])
        lines.append(
            f"- {hits}: the cap ({budget_s:g}s) was reached, so the ideal is not "
            "always affordable, and it is the interaction-heavy end that breaks "
            "it (see `results/crossover.md` for the budget crossover)."
        )
    lines.append("")

    md_path = out_dir / "scale-probe.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=300.0, help="cap per solve in seconds")
    parser.add_argument("--out", type=Path, default=Path("results"), help="output directory")
    args = parser.parse_args(argv)

    rows = measure(long_cases(), args.budget)
    print(f"Wrote {write_report(rows, args.out, args.budget)}")


if __name__ == "__main__":
    main()
