#!/usr/bin/env python3
"""One-factor sweep over ``genetic_fidelity`` parameters.

Same method as ``tabu_sweep.py``: move one knob at a time from the baseline
and measure what actually changes -- gap to ``exact_dp`` on the fidelity
suite, share of runs that reach the bound, wall time and evaluation count.
Manual one-off edits (bump population_size, then mutation_rate, then...)
on a single seed cannot tell a real improvement from noise; this sweep runs
every config on the same seeds so the comparison is apples to apples.

Everything is scored on the true-minimum metric (reduced input, output
cancelled) with the same 13 benchmark cases as ``odra-router-bench-fidelity``.

Outputs ``results/genetic-sweep.csv`` and ``results/genetic-sweep.md``.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from odra_router.bench import fidelity_cases  # noqa: E402
from odra_router.contract import make_problem  # noqa: E402
from odra_router.fidelity import (  # noqa: E402
    cancelled_fidelity_cost,
    odra5_default_fidelity,
)
from odra_router.optimize.cancel import reduce_input  # noqa: E402
from odra_router.routing.exact_dp import ExactDPSolver  # noqa: E402
from odra_router.routing.genetic_fidelity import GeneticFidelitySolver  # noqa: E402

#: Baseline = population_size/generations/mutation_rate/elitism as currently
#: registered on ``GeneticFidelitySolver`` (random warm start).
BASELINE: dict = {
    "warm_start": "random",
    "population_size": 60,
    "generations": 120,
    "tournament_size": 3,
    "mutation_rate": 0.1,
    "elitism": 6,
    "stagnation_limit": 20,
    "diversity_frac": 0.3,
    "init_mutations": 5,
}

#: One-factor-at-a-time alternatives to the baseline value.
KNOBS: tuple[tuple[str, tuple], ...] = (
    ("population_size", (40, 100)),
    ("generations", (80, 200, 300)),
    ("mutation_rate", (0.05, 0.25, 0.4)),
    ("elitism", (2, 4, 10)),
    ("stagnation_limit", (10, 50)),
)

OPT_TOL = 1e-9


def configs() -> list[tuple[str, str, object, dict]]:
    """(name, knob, value, params) for the baseline and every one-factor variant."""
    out: list[tuple[str, str, object, dict]] = [("baseline", "-", "-", dict(BASELINE))]
    for knob, values in KNOBS:
        for value in values:
            params = dict(BASELINE)
            params[knob] = value
            out.append((f"{knob}={value}", knob, value, params))
    return out


def ideals(cases, model, budget_s: float) -> dict[str, float]:
    """exact_dp cost per case (the reference the sweep measures against)."""
    out: dict[str, float] = {}
    for name, circuit in cases:
        problem = make_problem(reduce_input(circuit))
        t0 = time.perf_counter()
        solution = ExactDPSolver().solve(problem, seed=0, budget_s=budget_s)
        out[name] = cancelled_fidelity_cost(problem, solution, model)
        print(f"  ideal {name}: {out[name]:.6f} ({time.perf_counter() - t0:.2f}s)")
    return out


def run_sweep(
    out_dir: Path,
    *,
    seeds: tuple[int, ...] = (0, 1),
    budget_s: float = 30.0,
    dp_budget: float = 60.0,
) -> tuple[Path, Path]:
    model = odra5_default_fidelity()
    cases = fidelity_cases()
    print("Exact references:")
    ideal = ideals(cases, model, dp_budget)

    rows: list[dict] = []
    for name, knob, value, params in configs():
        for case, circuit in cases:
            problem = make_problem(reduce_input(circuit))
            for seed in seeds:
                solver = GeneticFidelitySolver(**params)
                t0 = time.perf_counter()
                solution = solver.solve(problem, seed=seed, budget_s=budget_s)
                seconds = time.perf_counter() - t0
                cost = cancelled_fidelity_cost(problem, solution, model)
                gap = cost - ideal[case]
                rows.append(
                    {
                        "config": name,
                        "knob": knob,
                        "value": value,
                        "case": case,
                        "seed": seed,
                        "fidelity_cost_cancelled": round(cost, 6),
                        "gap": round(gap, 6),
                        "optimal": int(gap <= OPT_TOL),
                        "seconds": round(seconds, 6),
                        "evals": getattr(solver, "last_evals", -1),
                    }
                )
        print(f"  {name}: done")

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "genetic-sweep.csv"
    md_path = out_dir / "genetic-sweep.md"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    write_md(md_path, rows, seeds, budget_s)
    return csv_path, md_path


def _stats(rows: list[dict]) -> dict:
    gaps = [r["gap"] for r in rows]
    return {
        "mean_gap": statistics.mean(gaps),
        "median_gap": statistics.median(gaps),
        "worst_gap": max(gaps),
        "opt_rate": sum(r["optimal"] for r in rows) / len(rows),
        "median_s": statistics.median([r["seconds"] for r in rows]),
        "median_evals": statistics.median([r["evals"] for r in rows]),
        "runs": len(rows),
    }


def write_md(path: Path, rows: list[dict], seeds: tuple[int, ...], budget_s: float) -> None:
    by_config: dict[str, list[dict]] = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)
    order = [name for name, _, _, _ in configs()]
    cases = sorted({r["case"] for r in rows})

    lines: list[str] = [
        "# Genetic (fidelity) parameter sweep (one factor at a time)",
        "",
        "`genetic_fidelity` on the 13 fidelity cases, scored on the true-minimum",
        "metric (gap to `exact_dp` on the reduced input, output cancelled),",
        f"{len(seeds)} seeds per case, {budget_s}s budget per solve. Baseline is",
        "the currently registered configuration (`population_size=60`,",
        "`generations=120`, `mutation_rate=0.1`, `elitism=6`, `stagnation_limit=20`,",
        "random warm start).",
        "`opt` = share of runs that reach the exact cost, `med s` / `med evals`",
        "are medians over all case+seed runs of the configuration.",
        "",
        "## Configurations",
        "",
        "| config | mean gap | median gap | worst gap | opt | med s | med evals |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in order:
        if name not in by_config:
            continue
        s = _stats(by_config[name])
        lines.append(
            f"| {name} | {s['mean_gap']:+.4f} | {s['median_gap']:+.4f} | {s['worst_gap']:+.4f} | "
            f"{100 * s['opt_rate']:.0f}% | {s['median_s']:.3f} | {s['median_evals']:.0f} |"
        )
    lines.append("")

    base = _stats(by_config["baseline"])
    lines += [
        "## Per knob (against the baseline)",
        "",
        "| knob | value | mean gap | delta mean gap | opt | delta med s |",
        "|---|---|---|---|---|---|",
        f"| - | baseline | {base['mean_gap']:+.4f} | - | {100 * base['opt_rate']:.0f}% | - |",
    ]
    for knob, values in KNOBS:
        for value in values:
            name = f"{knob}={value}"
            if name not in by_config:
                continue
            s = _stats(by_config[name])
            lines.append(
                f"| {knob} | {value} | {s['mean_gap']:+.4f} | "
                f"{s['mean_gap'] - base['mean_gap']:+.4f} | {100 * s['opt_rate']:.0f}% | "
                f"{s['median_s'] - base['median_s']:+.3f} |"
            )
    lines.append("")

    # Per-case detail for the configs that differ from the baseline.
    lines += [
        "## Per case, gap vs exact_dp",
        "",
        "| case | " + " | ".join(order) + " |",
        "|---|" + "---|" * len(order),
    ]
    per_case: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        per_case.setdefault((r["case"], r["config"]), []).append(r)
    for case in cases:
        cells = []
        for name in order:
            rs = per_case.get((case, name))
            cells.append("-" if not rs else f"{statistics.median([r['gap'] for r in rs]):+.4f}")
        lines.append(f"| {case} | " + " | ".join(cells) + " |")
    lines.append("")

    worst_knob = max(
        (name for name in order if name != "baseline"),
        key=lambda n: abs(_stats(by_config[n])["mean_gap"] - base["mean_gap"]),
    )

    # Representative rule (same as tabu_sweep.py): Pareto on the pair
    # (mean gap, median seconds), with a quality band that stands for the
    # sweep's own noise, ties broken on time.
    noise = 0.02
    stats = {name: _stats(by_config[name]) for name in order}
    best_gap = min(s["mean_gap"] for s in stats.values())
    within_band = sorted(
        (name for name, s in stats.items() if s["mean_gap"] <= best_gap + noise),
        key=lambda n: (stats[n]["median_s"], stats[n]["mean_gap"]),
    )
    winner = within_band[0]

    lines += [
        "## Representative: which genetic_fidelity is the default",
        "",
        f"Rule: Pareto on (mean gap, median seconds), quality band {noise:g} mean"
        " gap, ties broken on the smaller time -- same rule as `tabu_sweep.py`."
        " A configuration is promoted to default only if it beats the registered"
        " baseline by more than the band; otherwise tuning it would be fitting"
        " noise.",
        "",
        f"- configurations inside the quality band: {', '.join(f'`{n}`' for n in within_band)};",
        f"- fastest inside the band: `{winner}` "
        f"(mean gap {stats[winner]['mean_gap']:+.4f}, median {stats[winner]['median_s']:.3f}s);",
        "- registered baseline: "
        f"`baseline` (mean gap {stats['baseline']['mean_gap']:+.4f}, "
        f"median {stats['baseline']['median_s']:.3f}s).",
        "",
    ]
    improvement = stats["baseline"]["mean_gap"] - stats[winner]["mean_gap"]
    if winner == "baseline" or improvement <= noise:
        delta = stats[winner]["mean_gap"] - stats["baseline"]["mean_gap"]
        lines.append(
            f"- default genetic_fidelity: `baseline` stays. The fastest configuration"
            f" inside the band is `{winner}`, whose mean gap is {delta:+.4f} against the"
            f" baseline, inside the {noise:g} band (and its time delta is"
            f" {stats['baseline']['median_s'] - stats[winner]['median_s']:+.3f}s"
            " median). Promoting a knob on a difference that small would be"
            " fitting noise, so the registered configuration keeps the simpler"
            " story."
        )
    else:
        lines.append(
            f"- default genetic_fidelity: `{winner}`, promoted over the baseline by"
            f" {improvement:+.4f} mean gap (outside the {noise:g} band) and"
            f" {stats['baseline']['median_s'] - stats[winner]['median_s']:+.3f}s median time."
        )
    lines += [
        "",
        "## Reading",
        "",
        f"- the most sensitive knob is `{worst_knob}` "
        f"({stats[worst_knob]['mean_gap'] - base['mean_gap']:+.4f} mean gap against the baseline);",
        "- compare the best config's mean gap here against `tabu_fidelity`'s"
        " (results_summary.md) to see how much of the gap is closeable by",
        "  tuning alone, versus structural (population-based search vs move-based",
        "  local search on this state space);",
        "- the knobs buy or cost wall time -- check `delta med s` before adopting",
        "  a config that only wins inside the noise band.",
        "",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="results")
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--budget-s", type=float, default=30.0)
    parser.add_argument("--dp-budget", type=float, default=60.0)
    args = parser.parse_args(argv)

    csv_path, md_path = run_sweep(
        Path(args.out_dir),
        seeds=tuple(int(s) for s in args.seeds.split(",")),
        budget_s=args.budget_s,
        dp_budget=args.dp_budget,
    )
    print(f"Wrote {csv_path} and {md_path}")


if __name__ == "__main__":
    main()
