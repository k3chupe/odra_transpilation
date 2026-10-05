"""Numbers for the paper's "Primary benchmark suite" section (Table tab:results).

Runs the 13 fidelity cases under the default (IQMFakeAdonis) fidelity model:

- ``exact_dp``                 once per case (reference),
- ``tabu_fidelity``, ``genetic_fidelity``: seeds 0..N-1, ``--budget`` s each,
- Qiskit SABRE                 seeds 0..N-1 (SabreLayout + SabreSwap,
                               20 layout / 20 SWAP trials as in the paper),
- Qiskit preset                once (``optimization_level=3``, seed_transpiler=0),
- ``greedy_shortest_path``     once.

Scored like ``odra-router-bench-fidelity``: our solvers on the reduced input
(``reduce_input``), every output after ``cancel_adjacent``
(``fidelity_cost_cancelled``); CZ count = ``native_cz_cost`` after
cancellation (SWAP = 3 CZ). Qiskit rows get the original circuit, as in the
benchmark.

Writes
  results/paper-runs.csv    one row per (case, solver, seed),
  results/paper-table.tex   the LaTeX table (paper format),
  results/paper-numbers.md  every number the section's text quotes.

Usage: python scripts/paper_table.py [--seeds 20] [--budget 30]
       (~20-30 min for 20 seeds; ``--seeds 2 --cases tiny_0,hard_2r`` to smoke-test)
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import odra_router  # noqa: E402,F401 — registers all solvers
from odra_router.bench import fidelity_cases  # noqa: E402
from odra_router.contract import SOLVERS, make_problem, native_cz_cost, validate, apply  # noqa: E402
from odra_router.fidelity import fidelity_cost, odra5_default_fidelity  # noqa: E402
from odra_router.optimize.cancel import cancel_adjacent, reduce_input  # noqa: E402
from odra_router.qiskit_glue import qiskit_baseline  # noqa: E402

TOL = 1e-9
PRESET_LEVEL = 3
SABRE_TRIALS = 20
#: Column order and labels of the paper's table.
COLUMNS = (
    ("exact_dp", "Exact DP"),
    ("tabu_fidelity", "Tabu Search"),
    ("genetic_fidelity", "GA"),
    ("qiskit_sabre", "Qiskit SABRE"),
    ("qiskit_preset", "Qiskit preset"),
    ("greedy_shortest_path", "Greedy"),
)
STOCHASTIC = ("tabu_fidelity", "genetic_fidelity", "qiskit_sabre")
METAHEURISTICS = ("tabu_fidelity", "genetic_fidelity")
#: Paper's case order: random circuits, then the adversarial ones.
CASE_ORDER = (
    "tiny_0", "tiny_1", "small_0", "small_1", "medium_0", "medium_1",
    "heavy_0", "heavy_1", "dense_0", "dense_1", "hard_2r", "hard_4r", "hard_8r",
)
ADVERSARIAL = ("hard_2r", "hard_4r", "hard_8r")


def _score(qc, model) -> tuple[float, float]:
    """(cancelled fidelity cost, cancelled native CZ count) of a circuit."""
    cancelled = cancel_adjacent(qc)
    return fidelity_cost(cancelled, model), float(native_cz_cost(cancelled))


def _sabre(circuit, problem, seed: int):
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import SabreLayout, SabreSwap

    cm = problem.coupling_map
    pm = PassManager([
        SabreLayout(cm, seed=seed, swap_trials=SABRE_TRIALS, layout_trials=SABRE_TRIALS),
        SabreSwap(cm, seed=seed, trials=SABRE_TRIALS),
    ])
    return pm.run(circuit)


def run(seeds: int, budget_s: float, only: set[str] | None) -> list[dict]:
    model = odra5_default_fidelity()
    rows: list[dict] = []
    cases = [(n, c) for n, c in fidelity_cases() if only is None or n in only]

    def add(case, solver, seed, cost, cz, seconds):
        rows.append({"case": case, "solver": solver, "seed": seed,
                     "cost": round(cost, 6), "cz": cz, "seconds": round(seconds, 4)})

    for case, circuit in cases:
        problem = make_problem(reduce_input(circuit))
        print(f"{case}:", end="", flush=True)

        def ours(name: str, seed: int) -> None:
            t0 = time.perf_counter()
            sol = SOLVERS[name].solve(problem, seed=seed, budget_s=budget_s)
            dt = time.perf_counter() - t0
            validate(problem, sol)
            add(case, name, seed, *_score(apply(problem, sol), model), dt)

        ours("exact_dp", 0)
        ours("greedy_shortest_path", 0)
        t0 = time.perf_counter()
        qc = qiskit_baseline(circuit, PRESET_LEVEL, seed=0)
        add(case, "qiskit_preset", 0, *_score(qc, model), time.perf_counter() - t0)

        for seed in range(seeds):
            ours("tabu_fidelity", seed)
            ours("genetic_fidelity", seed)
            t0 = time.perf_counter()
            qc = _sabre(circuit, problem, seed)
            add(case, "qiskit_sabre", seed, *_score(qc, model), time.perf_counter() - t0)
            print(".", end="", flush=True)
        print()
    return rows


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:+.1f}\\%"


def aggregate(rows: list[dict]) -> dict:
    cases = [c for c in CASE_ORDER if any(r["case"] == c for r in rows)]
    by: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by.setdefault((r["case"], r["solver"]), []).append(r)
    ref = {c: by[(c, "exact_dp")][0]["cost"] for c in cases}

    def costs(c, s):
        return [r["cost"] for r in by[(c, s)]]

    mean = {(c, s): statistics.fmean(costs(c, s)) for c in cases for s, _ in COLUMNS}
    std = {(c, s): statistics.stdev(costs(c, s)) if len(costs(c, s)) > 1 else 0.0
           for c in cases for s, _ in COLUMNS}
    return {"cases": cases, "by": by, "ref": ref, "mean": mean, "std": std, "costs": costs}


def _mean_over(cases, f):
    return statistics.fmean(f(c) for c in cases)


def write_table(agg: dict, path: Path) -> None:
    cases, mean, std, ref, costs = agg["cases"], agg["mean"], agg["std"], agg["ref"], agg["costs"]
    lines = [
        r"\begin{tabular}{l c c c c c c}",
        r"\toprule",
        r"\textbf{Instance} & " + " & ".join(rf"\textbf{{{lab}}}" for _, lab in COLUMNS) + r" \\",
        r"\midrule",
    ]
    for c in cases:
        if c == ADVERSARIAL[0]:
            lines.append(r"\midrule")
        cells = [rf"\texttt{{{c.replace('_', chr(92) + '_')}}}"]
        for s, _ in COLUMNS:
            if s in STOCHASTIC:
                cell = rf"{mean[(c, s)]:.4f}\,$\pm$\,{std[(c, s)]:.4f}"
                if all(abs(x - ref[c]) <= TOL for x in costs(c, s)):
                    cell = rf"\best{{{cell}}}"
            else:
                cell = f"{mean[(c, s)]:.4f}"
            cells.append(cell)
        lines.append(" & ".join(cells) + r" \\")

    ref_mean = _mean_over(cases, lambda c: ref[c])
    mc = {s: _mean_over(cases, lambda c, s=s: mean[(c, s)]) for s, _ in COLUMNS}
    at_ref = {s: sum(abs(x - ref[c]) <= TOL for c in cases for x in costs(c, s)) for s in STOCHASTIC}
    runs = {s: sum(len(costs(c, s)) for c in cases) for s in STOCHASTIC}
    t0 = {s: statistics.median(next(r["seconds"] for r in agg["by"][(c, s)] if r["seed"] == 0)
                               for c in cases) for s, _ in COLUMNS}
    lines += [
        r"\midrule[\heavyrulewidth]",
        "Mean cost & " + " & ".join(f"{mc[s]:.4f}" for s, _ in COLUMNS) + r" \\",
        "Mean gap (\\%) & --- & " + " & ".join(_pct(100 * (mc[s] / ref_mean - 1)) for s, _ in COLUMNS[1:]) + r" \\",
        "Runs at reference & --- & " + " & ".join(
            f"{at_ref[s]}/{runs[s]}" if s in STOCHASTIC else "---" for s, _ in COLUMNS[1:]) + r" \\",
        "Median time (s) & " + " & ".join(f"{t0[s]:.3f}" for s, _ in COLUMNS) + r" \\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_numbers(agg: dict, path: Path, seeds: int, budget_s: float) -> None:
    cases, mean, std, ref, costs, by = (agg[k] for k in ("cases", "mean", "std", "ref", "costs", "by"))
    names = dict(COLUMNS)
    random_cases = [c for c in cases if c not in ADVERSARIAL]
    adv_cases = [c for c in cases if c in ADVERSARIAL]
    L = [
        "# Numbers for the \"Primary benchmark suite\" section",
        "",
        f"Setup: fidelity model IQMFakeAdonis error profile; {len(cases)} cases; "
        f"seeds 0..{seeds - 1} for Tabu/GA/SABRE; budget {budget_s:g} s per heuristic run; "
        f"Qiskit preset optimization_level={PRESET_LEVEL}, seed_transpiler=0 (one run); "
        f"SABRE = SabreLayout + SabreSwap, {SABRE_TRIALS} layout / {SABRE_TRIALS} SWAP trials. "
        "Cost = cancelled -ln f. Gap of a solver over a set of cases = "
        "(mean cost - mean DP cost) / mean DP cost (ratio of means, as in the table); "
        "per-instance gap = (C - C_DP) / C_DP.",
        "",
    ]

    def block(title, cs):
        dp = _mean_over(cs, lambda c: ref[c])
        L.append(f"## {title} (DP mean {dp:.4f})")
        L.append("")
        L.append("| solver | mean cost | gap (ratio of means) | mean per-instance gap | median per-instance gap |")
        L.append("|---|---|---|---|---|")
        for s, _ in COLUMNS[1:]:
            m = _mean_over(cs, lambda c: mean[(c, s)])
            g = [100 * (mean[(c, s)] / ref[c] - 1) for c in cs]
            L.append(f"| {names[s]} | {m:.4f} | {100 * (m / dp - 1):+.1f}% | "
                     f"{statistics.fmean(g):+.1f}% | {statistics.median(g):+.1f}% |")
        L.append("")

    block("All instances", cases)
    block("Random circuits", random_cases)
    block("Adversarial circuits", adv_cases)

    L.append("## Reaching the DP reference")
    L.append("")
    for s in STOCHASTIC:
        hits = sum(abs(x - ref[c]) <= TOL for c in cases for x in costs(c, s))
        total = sum(len(costs(c, s)) for c in cases)
        all20 = [c for c in cases if all(abs(x - ref[c]) <= TOL for x in costs(c, s))]
        some = [c for c in cases if any(abs(x - ref[c]) <= TOL for x in costs(c, s))]
        never = [c for c in cases if c not in some]
        L.append(f"- {names[s]}: {hits}/{total} runs; all runs on {len(all20)} instances; "
                 f"at least one run on {len(some)}; never on: {', '.join(never) or 'none'}")
        for c in never:
            L.append(f"  - {c}: best run {min(costs(c, s)):.4f} vs DP {ref[c]:.4f}")
    L.append("")

    L.append("## Below the DP reference (outside the routing decision space)")
    L.append("")
    for s, _ in COLUMNS[1:]:
        below = [(c, x) for c in cases for x in costs(c, s) if x < ref[c] - TOL]
        if below:
            per = {}
            for c, x in below:
                per.setdefault(c, []).append(x)
            L.append(f"- {names[s]}: " + "; ".join(
                f"{c} ({len(v)} run(s), min {min(v):.4f} vs DP {ref[c]:.4f})" for c, v in per.items()))
    L.append("")

    L.append("## Pairwise, by per-instance mean cost")
    L.append("")
    for a, b in (("tabu_fidelity", "qiskit_sabre"), ("genetic_fidelity", "qiskit_sabre"),
                 ("tabu_fidelity", "genetic_fidelity"), ("tabu_fidelity", "qiskit_preset"),
                 ("genetic_fidelity", "qiskit_preset")):
        lo = [c for c in cases if mean[(c, a)] < mean[(c, b)] - TOL]
        hi = [c for c in cases if mean[(c, a)] > mean[(c, b)] + TOL]
        eq = len(cases) - len(lo) - len(hi)
        L.append(f"- {names[a]} vs {names[b]}: lower on {len(lo)}, higher on {len(hi)} "
                 f"({', '.join(hi) or '-'}), equal on {eq}")
        for c in hi:
            L.append(f"  - {c}: {mean[(c, a)]:.4f} vs {mean[(c, b)]:.4f} "
                     f"(std {std[(c, a)]:.4f} / {std[(c, b)]:.4f})")
    L.append("")

    dp = _mean_over(cases, lambda c: ref[c])
    best_sabre = _mean_over(cases, lambda c: min(costs(c, "qiskit_sabre")))
    L.append("## SABRE best of the seeds per instance")
    L.append("")
    L.append(f"- mean of per-instance best: {best_sabre:.4f} ({100 * (best_sabre / dp - 1):+.1f}%)")
    L.append("")

    L.append("## Spread over seeds")
    L.append("")
    for s in STOCHASTIC:
        tight = [c for c in cases if std[(c, s)] < 5e-5]
        worst = max(cases, key=lambda c: std[(c, s)])
        L.append(f"- {names[s]}: std < 5e-5 on {len(tight)}/{len(cases)}; "
                 f"largest std {std[(worst, s)]:.4f} on {worst} "
                 f"(mean gap there {100 * (mean[(worst, s)] / ref[worst] - 1):+.1f}%)")
    L.append("")

    L.append("## Panel (d): mean physical CZ count (SWAP = 3 CZ, after cancellation)")
    L.append("")
    for s, _ in COLUMNS:
        cz = _mean_over(cases, lambda c, s=s: statistics.fmean(r["cz"] for r in by[(c, s)]))
        L.append(f"- {names[s]}: {cz:.1f}")
    L.append("")

    L.append("## Median solve time (s), seed 0, median over instances")
    L.append("")
    for s, _ in COLUMNS:
        t = statistics.median(next(r["seconds"] for r in by[(c, s)] if r["seed"] == 0) for c in cases)
        L.append(f"- {names[s]}: {t:.3f}")
    L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--budget", type=float, default=30.0)
    ap.add_argument("--cases", default="", help="comma-separated subset (smoke test)")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    args = ap.parse_args()

    only = set(args.cases.split(",")) if args.cases else None
    rows = run(args.seeds, args.budget, only)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "paper-runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    agg = aggregate(rows)
    write_table(agg, args.out / "paper-table.tex")
    write_numbers(agg, args.out / "paper-numbers.md", args.seeds, args.budget)
    for name in ("paper-runs.csv", "paper-table.tex", "paper-numbers.md"):
        print(f"Wrote {args.out / name}")


if __name__ == "__main__":
    main()
