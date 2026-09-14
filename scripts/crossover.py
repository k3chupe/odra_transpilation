#!/usr/bin/env python3
"""Crossover benchmark: when does the exact reference stop paying for itself?

On the ODRA5 star the *quality* comparison saturates (24 of 120 layouts are
optimal for every circuit), so the interesting axis is cost. ``exact_dp`` is
the true lower bound, but its state space is ``(frontier, layout)`` with a
frontier width of at most 2, i.e. it grows like ``I^2 * 120`` in the number of
two-qubit interactions ``I``: adding gates *does* eventually make it slow, just
polynomially. A budgeted metaheuristic can therefore win on time at some
instance size even though it cannot beat the bound.

This script measures that crossover instead of asserting it. For a ladder of
increasingly long hard circuits it records:

- ``exact_dp``: wall time and cost with a generous cap (``--dp-budget``). When
  the cap is hit the solver falls back to greedy and ``exact_dp_hit_budget``
  is 1, so the row is not a verified bound;
- ``tabu_fidelity`` (random warm start): one run per (budget, seed), scored
  after the cancellation pass, with the *actual* seconds next to the requested
  budget (the solver honours ``budget_s``, including its polish phase, since
  the budget-honesty fix; overshoot is reported, not hidden).

Derived in the markdown:

- the smallest tabu wall time that reaches the exact cost ("time to match");
- for each budget, the longest instance ``exact_dp`` still finishes inside it,
  and what tabu reaches on that same instance within the same budget.

Outputs ``results/crossover.csv`` and ``results/crossover.md``.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qiskit import QuantumCircuit  # noqa: E402

from odra_router.contract import build_plan, make_problem  # noqa: E402
from odra_router.fidelity import (  # noqa: E402
    cancelled_fidelity_cost,
    odra5_default_fidelity,
)
from odra_router.generator import hard_circuit, layered_random_circuit  # noqa: E402
from odra_router.optimize.cancel import reduce_input  # noqa: E402
from odra_router.routing.exact_dp import ExactDPSolver  # noqa: E402
from odra_router.routing.tabu_fidelity import TabuFidelitySolver  # noqa: E402

BUDGETS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1.0)
DEFAULT_ROUNDS: tuple[int, ...] = (4, 8, 16, 24, 32, 48, 64, 96)
DEFAULT_SEEDS: tuple[int, ...] = (0, 1, 2)

#: A tabu run counts as "at the bound" when it is within this of exact_dp.
OPT_TOL = 1e-9


def ladder(rounds: tuple[int, ...], *, family: str) -> list[tuple[str, QuantumCircuit]]:
    """Benchmark instances ordered by growing interaction count."""
    cases: list[tuple[str, QuantumCircuit]] = []
    for r in rounds:
        cases.append((f"hard_{r}r", hard_circuit(r)))
    if family == "mixed":
        for layers in (8, 16, 32):
            cases.append((f"layered_{layers}", layered_random_circuit(layers)))
    return cases


def run_case(
    case: str,
    circuit: QuantumCircuit,
    *,
    budgets: tuple[float, ...],
    seeds: tuple[int, ...],
    dp_budget: float,
    model,
) -> tuple[list[dict], dict]:
    """Run exact_dp once and tabu per (budget, seed); return rows and a summary."""
    problem = make_problem(reduce_input(circuit))
    interactions = len(build_plan(problem).interactions)

    dp = ExactDPSolver()
    t0 = time.perf_counter()
    dp_solution = dp.solve(problem, seed=0, budget_s=dp_budget)
    dp_seconds = time.perf_counter() - t0
    dp_cost = cancelled_fidelity_cost(problem, dp_solution, model)
    dp_hit = bool(getattr(dp, "last_hit_budget", False))

    rows: list[dict] = []
    for budget in budgets:
        for seed in seeds:
            solver = TabuFidelitySolver(warm_start="random")
            t0 = time.perf_counter()
            solution = solver.solve(problem, seed=seed, budget_s=budget)
            seconds = time.perf_counter() - t0
            cost = cancelled_fidelity_cost(problem, solution, model)
            gap = cost - dp_cost
            rows.append(
                {
                    "case": case,
                    "family": "hard" if case.startswith("hard") else "layered",
                    "interactions": interactions,
                    "exact_dp_seconds": round(dp_seconds, 6),
                    "exact_dp_cost": round(dp_cost, 6),
                    "exact_dp_hit_budget": int(dp_hit),
                    "budget_s": budget,
                    "seed": seed,
                    "tabu_seconds": round(seconds, 6),
                    "tabu_cost": round(cost, 6),
                    "tabu_gap": round(gap, 6),
                    "tabu_optimal": int(gap <= OPT_TOL),
                    "tabu_evals": getattr(solver, "last_evals", -1),
                    "tabu_hit_budget": int(bool(getattr(solver, "last_deadline_hit", False))),
                }
            )

    matching = [r for r in rows if r["tabu_gap"] <= OPT_TOL]
    summary = {
        "case": case,
        "interactions": interactions,
        "dp_seconds": dp_seconds,
        "dp_cost": dp_cost,
        "dp_hit": dp_hit,
        "tabu_seconds_to_match": min((r["tabu_seconds"] for r in matching), default=None),
        "tabu_best_gap": min(r["tabu_gap"] for r in rows),
        "tabu_best_budget": min(
            (r["budget_s"] for r in rows if r["tabu_gap"] <= OPT_TOL), default=None
        ),
        "by_budget": {
            b: [r for r in rows if r["budget_s"] == b] for b in budgets
        },
    }
    return rows, summary


def _summarise_budget(rows: list[dict]) -> tuple[float, float, float]:
    """(median gap, optimal rate, median actual seconds) for one case+budget."""
    gaps = [r["tabu_gap"] for r in rows]
    return (
        statistics.median(gaps),
        sum(r["tabu_optimal"] for r in rows) / len(rows),
        statistics.median([r["tabu_seconds"] for r in rows]),
    )


def write_md(path: Path, summaries: list[dict], budgets: tuple[float, ...], seeds: tuple[int, ...]) -> None:
    lines: list[str] = [
        "# Crossover: exact reference vs budgeted metaheuristic vs instance size",
        "",
        "Ladder of `hard_circuit(r)` instances (adversarial: cycles over the six",
        "non-edge pairs of the star, so every interaction needs a SWAP).",
        "`exact_dp` is the true lower bound of the routing + adjacent-cancel game;",
        "its state space is `(frontier, layout)` with frontier width at most 2, so",
        "its cost grows roughly quadratically in the interaction count `I`.",
        "Tabu is the budgeted metaheuristic (`tabu_fidelity`, random warm start,",
        f"{len(seeds)} seeds per budget). `gap` is measured against `exact_dp` on",
        "the reduced input, after the cancellation pass (true minimum).",
        "",
        "`dp s` = wall time of the reference, `hit` = it ran out of its time cap",
        "and fell back to greedy (then the row is not a verified bound).",
        "`tabu match s` = smallest *actual* tabu wall time over all budgets and",
        "seeds that still reached the exact cost, `best gap` = best gap seen at",
        "any budget. Requested budget and actual seconds are both recorded in the",
        "CSV: the polish phase used to ignore `budget_s` entirely (up to 60x",
        "overshoot); since the budget-honesty fix the deadline is enforced there",
        "too, and any remaining overshoot is visible in the table.",
        "",
        "## Scaling and match time",
        "",
        "| case | I | dp s | dp cost | hit | tabu match s | best gap | cheapest matching budget |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        match = "-" if s["tabu_seconds_to_match"] is None else f"{s['tabu_seconds_to_match']:.2f}"
        budget = "-" if s["tabu_best_budget"] is None else f"{s['tabu_best_budget']}"
        lines.append(
            f"| {s['case']} | {s['interactions']} | {s['dp_seconds']:.3f} | "
            f"{s['dp_cost']:.4f} | {int(s['dp_hit'])} | {match} | "
            f"{s['tabu_best_gap']:+.4f} | {budget} |"
        )
    lines.append("")

    lines += [
        "## Tabu quality per budget",
        "",
        "Median gap vs `exact_dp` over the seeds, share of runs that reached the",
        "bound, and median actual wall time. The bound is unavailable (row above",
        "has `hit = 1`) only when the reference ran out of its cap.",
        "",
        "| case | I | " + " | ".join(f"{b}s gap / opt / s" for b in budgets) + " |",
        "|---|---|" + "---|" * len(budgets),
    ]
    for s in summaries:
        cells = []
        for b in budgets:
            gap, rate, secs = _summarise_budget(s["by_budget"][b])
            cells.append(f"{gap:+.4f} / {100 * rate:.0f}% / {secs:.3f}")
        lines.append(f"| {s['case']} | {s['interactions']} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += [
        "## Crossover points",
        "",
        "For each budget: the longest instance the exact reference still finishes",
        "inside it, and the first instance where it does not, with what tabu",
        "reaches on that same instance within the same budget.",
        "",
        "| budget | last instance exact fits | I | first instance exact misses | I | tabu gap there | tabu opt rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in budgets:
        fits = [s for s in summaries if s["dp_seconds"] <= b]
        misses = [s for s in summaries if s["dp_seconds"] > b]
        last_fit = max(fits, key=lambda s: s["interactions"]) if fits else None
        first_miss = min(misses, key=lambda s: s["interactions"]) if misses else None
        if first_miss is None:
            gap_txt, rate_txt, miss_txt, miss_i = "-", "-", "-", "-"
        else:
            gap, rate, _ = _summarise_budget(first_miss["by_budget"][b])
            gap_txt, rate_txt = f"{gap:+.4f}", f"{100 * rate:.0f}%"
            miss_txt, miss_i = first_miss["case"], str(first_miss["interactions"])
        lines.append(
            f"| {b}s | {last_fit['case'] if last_fit else '-'} | "
            f"{last_fit['interactions'] if last_fit else '-'} | {miss_txt} | {miss_i} | "
            f"{gap_txt} | {rate_txt} |"
        )
    lines.append("")

    matchable = [s for s in summaries if s["tabu_seconds_to_match"] is not None]
    if matchable:
        faster = [s for s in matchable if s["tabu_seconds_to_match"] < s["dp_seconds"]]
        lines += [
            "## Reading",
            "",
            f"- tabu reaches the exact cost on {len(matchable)} of {len(summaries)} instances;",
            f"- on {len(faster)} of those it does so faster than the reference "
            "(by construction it can never do better in quality, only in time);",
            "- the reference stays exact and predictable, so the crossover is a",
            "  budget decision, not a quality one: below the crossover the reference",
            "  is the answer, above it the budget decides how close tabu gets.",
            "",
        ]
    else:
        lines += [
            "## Reading",
            "",
            "- tabu did not reach the exact cost on any instance in this ladder;",
            "  the gaps above are purely structural (local minima), not budget-driven.",
            "",
        ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run(
    out_dir: Path,
    *,
    rounds: tuple[int, ...] = DEFAULT_ROUNDS,
    family: str = "hard",
    budgets: tuple[float, ...] = BUDGETS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    dp_budget: float = 120.0,
) -> tuple[Path, Path]:
    model = odra5_default_fidelity()
    all_rows: list[dict] = []
    summaries: list[dict] = []
    for case, circuit in ladder(rounds, family=family):
        rows, summary = run_case(
            case, circuit, budgets=budgets, seeds=seeds, dp_budget=dp_budget, model=model
        )
        all_rows.extend(rows)
        summaries.append(summary)
        match = summary["tabu_seconds_to_match"]
        print(
            f"{case:>10} I={summary['interactions']:>4} dp={summary['dp_seconds']:.3f}s "
            f"hit={int(summary['dp_hit'])} "
            f"tabu_match={'never' if match is None else f'{match:.2f}s'}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "crossover.csv"
    md_path = out_dir / "crossover.md"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    write_md(md_path, summaries, budgets, seeds)
    return csv_path, md_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="results")
    parser.add_argument("--rounds", default=",".join(str(r) for r in DEFAULT_ROUNDS))
    parser.add_argument("--budgets", default=",".join(str(b) for b in BUDGETS))
    parser.add_argument("--seeds", default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--dp-budget", type=float, default=120.0,
                        help="time cap for the exact reference (s)")
    parser.add_argument("--family", default="hard", choices=("hard", "mixed"))
    args = parser.parse_args(argv)

    csv_path, md_path = run(
        Path(args.out_dir),
        rounds=tuple(int(r) for r in args.rounds.split(",")),
        family=args.family,
        budgets=tuple(float(b) for b in args.budgets.split(",")),
        seeds=tuple(int(s) for s in args.seeds.split(",")),
        dp_budget=args.dp_budget,
    )
    print(f"Wrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
