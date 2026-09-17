#!/usr/bin/env python3
"""Tor D of the "why tabu" analysis: where the exact reference stops fitting.

The plan for this analysis asked for a size argument beyond ODRA5: on a star
(and on a line) of ``n`` qubits the layout space is ``n!`` and the ready
frontier can hold ``floor(n/2)`` interactions instead of 2, so the exact DP
should stop being free at some ``n`` while a budgeted metaheuristic keeps a
constant cost.

This probe measures that on synthetic topologies, with a synthetic fidelity
model per topology (``FidelityModel`` values in the same range as the ODRA5
placeholder) and random circuits:

- ``exact_dp`` gets a fixed cap; ``hit`` marks the runs where it fell back to
  greedy, so a "gap" is never quoted against an unfinished reference;
- ``tabu_fidelity`` gets a fixed budget (default 1s) as the constant-cost
  alternative;
- ``greedy_shortest_path`` is the free baseline.

Nothing here is a statement about ODRA5: it is out of scope for the project's
target topology and exists only to answer "po co metaheurystyki" with numbers.

Writes ``results/n-qubit-crossover.md`` (and the CSV next to it).
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qiskit.transpiler import CouplingMap  # noqa: E402

from odra_router.contract import SOLVERS, make_problem  # noqa: E402
from odra_router.fidelity import FidelityModel, cancelled_fidelity_cost  # noqa: E402
from odra_router.generator import random_circuit  # noqa: E402
from odra_router.optimize.cancel import reduce_input  # noqa: E402
from odra_router.routing.exact_dp import ExactDPSolver  # noqa: E402
from odra_router.routing.tabu_fidelity import TabuFidelitySolver  # noqa: E402


def topology(kind: str, n: int) -> tuple[tuple[int, int], ...]:
    if kind == "star":
        return tuple((0, i) for i in range(1, n))
    if kind == "line":
        return tuple((i, i + 1) for i in range(n - 1))
    raise ValueError(f"unknown topology {kind!r}")


def synthetic_model(n: int, edges, seed: int) -> FidelityModel:
    """Model in the same value range as the ODRA5 placeholder, for n wires."""
    rng = random.Random(seed)
    return FidelityModel(
        one_qubit=tuple(0.995 - 0.004 * rng.random() for _ in range(n)),
        two_qubit={tuple(sorted(e)): 0.97 - 0.025 * rng.random() for e in edges},
    )


def run_case(kind: str, n: int, num_gates: int, dp_budget: float, tabu_budget: float) -> dict:
    edges = topology(kind, n)
    model = synthetic_model(n, edges, seed=1000 * n + len(edges))
    circuit = reduce_input(
        random_circuit(num_qubits=n, num_gates=num_gates, seed=0, p_two_qubit=0.7)
    )
    problem = make_problem(circuit, CouplingMap(list(edges)))

    row: dict = {
        "topology": kind,
        "n": n,
        "gates": circuit.size(),
        "interactions": len(problem.interactions),
        "layouts": math.factorial(n),
    }

    def solve(solver, budget: float) -> tuple[float, float | None, int, str]:
        t0 = time.perf_counter()
        try:
            solution = solver.solve(problem, seed=0, budget_s=budget)
            seconds = time.perf_counter() - t0
            cost = cancelled_fidelity_cost(problem, solution, model)
        except MemoryError:
            return time.perf_counter() - t0, None, 1, "memory"
        except Exception as exc:  # ponytail: the probe records any solver failure
            return time.perf_counter() - t0, None, 0, type(exc).__name__
        hit = int(
            bool(
                getattr(solver, "last_hit_budget", False)
                or getattr(solver, "last_deadline_hit", False)
            )
        )
        return seconds, cost, hit, ""

    seconds, cost, hit, err = solve(ExactDPSolver(fidelity=model), dp_budget)
    row |= {
        "dp_seconds": round(seconds, 3),
        "dp_cost": round(cost, 6) if cost is not None else "",
        "dp_hit": hit,
        "dp_error": err,
    }

    for name, solver, budget in (
        ("tabu", TabuFidelitySolver(fidelity=model) if kind == "star" else None, tabu_budget),
        ("greedy", SOLVERS["greedy_shortest_path"], dp_budget),
    ):
        if solver is None:
            # tabu_fidelity encodes one SWAP per interaction, which only works
            # on a hub topology; on a line it is not applicable.
            row |= {f"{name}_seconds": "", f"{name}_cost": "", f"{name}_error": "n/a on a line", f"{name}_gap_pct": ""}
            continue
        seconds, cost, hit, err = solve(solver, budget)
        row |= {
            f"{name}_seconds": round(seconds, 3),
            f"{name}_cost": round(cost, 6) if cost is not None else "",
            f"{name}_error": err,
        }
        if cost is not None and row["dp_cost"] != "" and not row["dp_hit"]:
            row[f"{name}_gap_pct"] = round(100 * (cost - row["dp_cost"]) / row["dp_cost"], 2)
        else:
            row[f"{name}_gap_pct"] = ""
    tabu_seconds = f"{row['tabu_seconds']:6.3f}s" if row["tabu_seconds"] != "" else "   n/a"
    print(
        f"{kind:5s} n={n} I={row['interactions']:3d} dp={row['dp_seconds']:7.3f}s"
        f" hit={row['dp_hit']} tabu={tabu_seconds} gap={row['tabu_gap_pct'] or 'n/a'}"
    )
    return row


def write_report(rows: list[dict], out_dir: Path, dp_budget: float, tabu_budget: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "n-qubit-crossover.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# N-qubit crossover (Tor D): the reference stops fitting, the heuristic does not",
        "",
        "Synthetic star and line topologies, random circuits, one synthetic",
        "fidelity model per topology. `exact_dp` cap "
        f"{dp_budget:g}s, `tabu_fidelity` budget {tabu_budget:g}s, `greedy` free.",
        "Out of scope for ODRA5: this is the size argument for keeping",
        "metaheuristics around, not a result about the target device.",
        "",
        "| topology | n | layouts | 2Q | dp s | hit | dp cost | tabu s | tabu gap | greedy gap |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        gap = f"{r['tabu_gap_pct']}%" if r["tabu_gap_pct"] != "" else "n/a"
        ggap = f"{r['greedy_gap_pct']}%" if r["greedy_gap_pct"] != "" else "n/a"
        tabu_s = f"{r['tabu_seconds']:g}" if r["tabu_seconds"] != "" else "n/a"
        dp_cost = f"{r['dp_cost']:g}" if r["dp_cost"] != "" else "n/a"
        lines.append(
            f"| {r['topology']} | {r['n']} | {r['layouts']} | {r['interactions']} | "
            f"{r['dp_seconds']:g} | {r['dp_hit']} | {dp_cost} | {tabu_s} | "
            f"{gap} | {ggap} |"
        )

    lines += ["", "## Reading", ""]
    for kind in ("star", "line"):
        kind_rows = [r for r in rows if r["topology"] == kind]
        first_hit = next((r for r in kind_rows if r["dp_hit"]), None)
        free = [r for r in kind_rows if not r["dp_hit"]]
        if free:
            lines.append(
                f"- {kind}: the reference is still free at n={free[-1]['n']} "
                f"({free[-1]['dp_seconds']:g}s for {free[-1]['interactions']} interactions)."
            )
        if first_hit:
            if first_hit["tabu_seconds"] != "":
                gap_text = (
                    f"{first_hit['tabu_gap_pct']}%"
                    if first_hit["tabu_gap_pct"] != ""
                    else "n/a (no verified bound at that size)"
                )
                tail = (
                    f" while tabu answers in {first_hit['tabu_seconds']:g}s with gap"
                    f" {gap_text} against that fallback"
                )
            else:
                tail = " while tabu is not applicable on this topology"
            lines.append(
                f"- {kind}: at n={first_hit['n']} (`{first_hit['layouts']}` layouts) the"
                f" reference hits the {dp_budget:g}s cap and degrades to greedy,"
                f"{tail}; that is the crossover the plan asked for."
            )
        else:
            lines.append(
                f"- {kind}: no crossover inside the tested range; the reference fits even"
                " at the largest n here, so a claim that it cannot would be wrong."
            )
    lines += [
        "",
        "Note: `tabu_fidelity` encodes one SWAP per interaction (`_edge_list` in",
        "`tabu_fidelity`), which is only complete on a hub topology, so it runs on",
        "the star and is reported as n/a on the line; on ODRA5 the historical edge",
        "numbering and the 5-choice neighbourhood are untouched.",
        "",
    ]

    md_path = out_dir / "n-qubit-crossover.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", type=int, nargs="+", default=[5, 6, 7, 8])
    parser.add_argument("--topologies", nargs="+", default=["star", "line"])
    parser.add_argument("--gates", type=int, default=40)
    parser.add_argument("--dp-budget", type=float, default=60.0)
    parser.add_argument("--tabu-budget", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)

    rows = [
        run_case(kind, n, args.gates, args.dp_budget, args.tabu_budget)
        for kind in args.topologies
        for n in args.ns
    ]
    print(f"Wrote {write_report(rows, args.out, args.dp_budget, args.tabu_budget)}")


if __name__ == "__main__":
    main()
