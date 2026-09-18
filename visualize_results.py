#!/usr/bin/env python3
"""
Visualization of the fidelity benchmark results (phase 3).

Reference (exact_dp) is the optimal solution: a full search of the routing
space, computed once per case, deterministically. Solvers being compared are
plotted as a distance from this optimum, not as equal competitors.

Tabu variants are very similar to each other, so before plotting they are
collapsed into family representatives (see FAMILIES and collapse_families).
The script prints to stdout how much the collapsed variants actually differ,
so nothing disappears silently under the representative's label.

The script only reads results/benchmark-fidelity.csv (results are not
computed here). When the CSV has `*_cancelled` columns (true minimum: input
reduced, output scored after cancellation), plots and the summary use
`fidelity_cost_cancelled` instead of the raw `fidelity_cost`.

Output: plots/*.png (4 plots plus an optional crossover plot) and
results_summary.md.
"""

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive: runs headless, never blocks

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

warnings.filterwarnings("ignore")

RESULTS_DIR = Path("results")
PLOTS_DIR = Path("plots")
FIDELITY_CSV = RESULTS_DIR / "benchmark-fidelity.csv"
CROSSOVER_CSV = RESULTS_DIR / "crossover.csv"
SUMMARY_PATH = Path("results_summary.md")

# Cost equality tolerance (costs within this band count as identical).
TOL = 1e-9

plt.rcParams["font.size"] = 10
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["axes.labelsize"] = 10
plt.rcParams["figure.dpi"] = 100

# Optimal solution = exact_dp: full search (layouts, SWAPs on edges, any
# topological order, exact fidelity cost). Cannot be beaten in our routing
# model; a solver can only match it.
REFERENCES = ("exact_dp",)

# Algorithm families (for coloring/grouping on the plots — otherwise tabu
# and genetic variants blend together under a single gap-sorted list).
GROUPS: dict[str, str] = {
    "tabu_fidelity": "tabu",
    "tabu_search": "tabu",
    "genetic_fidelity": "genetic",
    "genetic_search": "genetic",
    "qiskit_sabre": "qiskit",
    "qiskit_preset": "qiskit",
    "greedy_shortest_path": "baseline",
    "brute_force_layout": "baseline",
    "brute_fidelity_layout": "baseline",
}
GROUP_ORDER = ["tabu", "genetic", "qiskit", "baseline"]
GROUP_COLORS = {
    "tabu": "#7D7A1E",       # olive
    "genetic": "#B5306D",    # dark pink
    "qiskit": "#F2A6C6",     # light pink
    "baseline": "#0B3D2E",   # dark bottle green
    "other": "#937860",
}
GROUP_LABELS = {
    "tabu": "tabu (family)",
    "genetic": "genetic (family)",
    "qiskit": "Qiskit",
    "baseline": "baseline (greedy/brute)",
    "other": "other",
}


def _group(solver: str) -> str:
    return GROUPS.get(solver, "other")


def _group_rank(solver: str) -> int:
    g = _group(solver)
    return GROUP_ORDER.index(g) if g in GROUP_ORDER else len(GROUP_ORDER)


def _group_color(solver: str) -> str:
    return GROUP_COLORS[_group(solver)]

# Solver families: representative -> variants it stands for.
# Order inside the tuple matters: the first element is the representative.
FAMILIES = (
    ("tabu_fidelity", ("tabu_fidelity", "tabu_fidelity_greedy", "tabu_fidelity_sabre")),
    ("tabu_search", ("tabu_search", "tabu_sabre_start")),
    ("genetic_search", ("genetic_search",)),
    (
        "genetic_fidelity",
        ("genetic_fidelity", "genetic_fidelity_greedy", "genetic_fidelity_sabre"),
    ),
    ("qiskit_sabre", ("qiskit_sabre",)),
    ("qiskit_preset", ("qiskit_preset",)),
    ("greedy_shortest_path", ("greedy_shortest_path",)),
    ("brute_force_layout", ("brute_force_layout",)),
    ("brute_fidelity_layout", ("brute_fidelity_layout",)),
)

# Full names (legend, axes) and short names (matrix columns, panels).
DISPLAY = {
    "exact_dp": "optimal (exact DP)",
    "tabu_fidelity": "tabu fidelity",
    "tabu_fidelity_greedy": "tabu fidelity (greedy)",
    "tabu_fidelity_sabre": "tabu fidelity (sabre)",
    "tabu_search": "tabu search",
    "tabu_sabre_start": "tabu + sabre (ours)",
    "genetic_search": "genetic (GA over layouts)",
    "genetic_fidelity": "genetic fidelity",
    "qiskit_sabre": "sabre (Qiskit)",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "greedy (identity)",
    "brute_force_layout": "brute layout (greedy swaps)",
    "brute_fidelity_layout": "brute fidelity (greedy swaps)",
}

SHORT = {
    "exact_dp": "optimal (exact DP)",
    "tabu_fidelity": "tabu fidelity",
    "tabu_search": "tabu search",
    "genetic_search": "genetic",
    "genetic_fidelity": "gen. fidelity",
    "qiskit_sabre": "sabre (Qiskit)",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "greedy",
    "brute_force_layout": "brute layout",
    "brute_fidelity_layout": "brute fidelity",
}

# Labels wrapped over two lines: fit without rotation, nothing overlaps.
STACKED = {
    "exact_dp": "optimal\n(exact DP)",
    "tabu_fidelity": "tabu\nfidelity",
    "tabu_search": "tabu\nsearch",
    "genetic_search": "genetic",
    "genetic_fidelity": "genetic\nfidelity",
    "qiskit_sabre": "sabre\n(Qiskit)",
    "qiskit_preset": "Qiskit\npreset",
    "greedy_shortest_path": "greedy",
    "brute_force_layout": "brute\nlayout",
    "brute_fidelity_layout": "brute\nfidelity",
}


def _name(solver: str) -> str:
    return DISPLAY.get(solver, solver)


def _short(solver: str) -> str:
    return SHORT.get(solver, _name(solver))


def _stacked(solver: str) -> str:
    return STACKED.get(solver, _short(solver))


def load_data(results_dir: Path = RESULTS_DIR) -> pd.DataFrame:
    """Loads the CSV and switches to the true-minimum metric if available."""
    results_path = Path(results_dir)
    df = pd.read_csv(results_path / "benchmark-fidelity.csv")
    df = df[df["error"].isna() | (df["error"] == "")].copy()
    # True minimum (phase 2): score after cancellation. When the CSV has a
    # `fidelity_cost_cancelled` column, use it instead of the raw cost, so
    # the comparison runs on the same metric as the benchmark summary.
    if "fidelity_cost_cancelled" in df.columns:
        df = df.drop(columns=["fidelity_cost"]).rename(
            columns={"fidelity_cost_cancelled": "fidelity_cost"}
        )
    df = df[df["fidelity_cost"] >= 0]
    return df


def ideal_per_case(df: pd.DataFrame) -> pd.Series:
    """Optimal cost per case = min fidelity_cost over the references."""
    refs = df[df["solver"].isin(REFERENCES)]
    return refs.groupby("case")["fidelity_cost"].min()


def case_order(ideal: pd.Series) -> list[str]:
    """Case order: increasing optimal cost (instance size)."""
    return sorted(ideal.index, key=lambda c: (float(ideal[c]), str(c)))


def _cost_vector(df: pd.DataFrame, solver: str) -> pd.Series:
    return df[df["solver"] == solver].set_index("case")["fidelity_cost"].sort_index()


def _same_vector(a: pd.Series, b: pd.Series) -> bool:
    """Whether two cost vectors are identical (same cases, tolerance TOL)."""
    if not a.index.equals(b.index):
        return False
    return bool((a - b).abs().max() <= TOL)


def collapse_families(df: pd.DataFrame) -> tuple[list[str], list[dict]]:
    """Returns the list of representatives and a report of differences within collapsed families."""
    reps: list[str] = []
    report: list[dict] = []
    for rep, members in FAMILIES:
        if df[df["solver"] == rep].empty:
            continue
        reps.append(rep)
        rep_vec = _cost_vector(df, rep)
        for variant in members:
            if variant == rep or df[df["solver"] == variant].empty:
                continue
            var_vec = _cost_vector(df, variant)
            idx = rep_vec.index.intersection(var_vec.index)
            diff = (rep_vec.loc[idx] - var_vec.loc[idx]).abs()
            report.append(
                {
                    "rep": rep,
                    "variant": variant,
                    "n_cases": len(idx),
                    "n_diff": int((diff > TOL).sum()),
                    "max_diff": float(diff.max()) if len(diff) else 0.0,
                    "mean_diff": float(diff.mean()) if len(diff) else 0.0,
                }
            )
    return reps, report


def merge_identical_reps(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str]
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Merges representatives with identical cost vectors (tolerance TOL)."""
    vectors = {r: _cost_vector(df, r) for r in reps}
    groups: list[list[str]] = []
    for rep in reps:
        for group in groups:
            if _same_vector(vectors[rep], vectors[group[0]]):
                group.append(rep)
                break
        else:
            groups.append([rep])
    merges = [(group[0], group[1:]) for group in groups if len(group) > 1]
    return [group[0] for group in groups], merges


def representative_stats(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str]
) -> pd.DataFrame:
    """Per-representative stats: cost, gap, time, evaluations, optimum hits."""
    rows = []
    for rep in reps:
        sdf = df[df["solver"] == rep]
        gaps = sdf.set_index("case")["fidelity_cost"] - ideal
        ev = sdf[sdf["evals"] >= 0]["evals"]
        rows.append(
            {
                "solver": rep,
                "name": _name(rep),
                "short": _short(rep),
                "mean_cost": float(sdf["fidelity_cost"].mean()),
                "mean_gap": float(gaps.mean()),
                "std_gap": float(gaps.std()),
                "median_seconds": float(sdf["seconds"].median()),
                "mean_seconds": float(sdf["seconds"].mean()),
                "mean_evals": float(ev.mean()) if len(ev) else float("nan"),
                # at optimum = matches the optimal cost (equal within TOL);
                # going below the optimum counts separately as a negative gap.
                "n_opt": int((gaps.abs() <= TOL).sum()),
                "n_cases": int(len(gaps)),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_gap").reset_index(drop=True)


def best_solver(stats: pd.DataFrame) -> str:
    """Solver id with the lowest mean gap to optimum (the overall winner)."""
    return str(stats.sort_values("mean_gap").iloc[0]["solver"])


def gap_matrix(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str]
) -> tuple[list[str], pd.DataFrame]:
    """Gap matrix: rows = cases (increasing optimal cost), columns =
    representatives grouped by family (tabu/genetic/qiskit/baseline)."""
    cases = case_order(ideal)
    reps_grouped = sorted(reps, key=lambda r: (_group_rank(r), r))
    data = {}
    for rep in reps_grouped:
        sdf = df[df["solver"] == rep].set_index("case")["fidelity_cost"]
        data[rep] = [float(sdf.get(c, np.nan)) - float(ideal[c]) for c in cases]
    return cases, pd.DataFrame(data, index=cases)


def _place_labels(fig, ax, xs, ys, labels) -> None:
    """Labels next to points, with simple overlap avoidance."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer)
    placed = []
    candidates = [
        (8, 8), (8, -14), (-8, 8), (-8, -14), (12, 0), (0, 16), (0, -18),
        (-72, 0), (14, 22), (-72, 22), (14, -24), (-72, -24), (0, 30), (0, -32),
    ]
    for x, y, label in zip(xs, ys, labels):
        chosen = None
        for dx, dy in candidates:
            txt = ax.annotate(
                label,
                (x, y),
                xytext=(dx, dy),
                textcoords="offset points",
                fontsize=9,
                ha="left" if dx >= 0 else "right",
                va="bottom" if dy >= 0 else "top",
            )
            fig.canvas.draw()
            box = txt.get_window_extent(renderer)
            inside = axes_box.contains(box.x0, box.y0) and axes_box.contains(box.x1, box.y1)
            if inside and not any(box.overlaps(p) for p in placed):
                chosen = txt
                placed.append(box)
                break
            txt.remove()
        if chosen is None:
            txt = ax.annotate(
                label, (x, y), xytext=candidates[0], textcoords="offset points", fontsize=9
            )
            fig.canvas.draw()
            placed.append(txt.get_window_extent(renderer))


def plot_gap_to_ideal(stats: pd.DataFrame, out_path: Path, best: str) -> None:
    """Horizontal bars: mean gap to optimum, grouped by family (tabu/genetic/...),
    sorted within each family, with the count of optimum hits. A dashed red
    line marks the overall winner's gap (lowest mean gap)."""
    s = stats.copy()
    s["_rank"] = s["solver"].map(_group_rank)
    s = s.sort_values(["_rank", "mean_gap"]).reset_index(drop=True)
    total = int(s["n_cases"].max())
    fig, ax = plt.subplots(figsize=(11.5, 0.55 * len(s) + 2.4))
    y = np.arange(len(s))
    gaps = s["mean_gap"].to_numpy()
    colors = ["#2ca02c" if g <= TOL else "#C44E52" for g in gaps]
    ax.barh(y, gaps, color=colors, alpha=0.9, height=0.62)
    ax.axvline(0, color="black", linewidth=1.2)
    best_gap = float(s.loc[s["solver"] == best, "mean_gap"].iloc[0])
    ax.axvline(best_gap, color="red", linestyle="--", linewidth=1.4, zorder=2)

    lo, hi = min(float(gaps.min()), 0.0), max(float(gaps.max()), 0.0)
    span = max(hi - lo, 1e-6)
    for yi, g, n_opt in zip(y, gaps, s["n_opt"]):
        off = 0.02 * span
        ax.text(
            g + off if g >= 0 else g - off,
            yi,
            f"{g:+.4f} ({int(n_opt)}/{total})",
            va="center",
            ha="left" if g >= 0 else "right",
            fontsize=9,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(s["name"])
    for tick, solver in zip(ax.get_yticklabels(), s["solver"]):
        tick.set_color(_group_color(solver))
        tick.set_fontweight("bold")
    # Separator between families, so tabu and genetic don't blend together.
    for i in range(1, len(s)):
        if s.loc[i, "_rank"] != s.loc[i - 1, "_rank"]:
            ax.axhline(i - 0.5, color="black", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.invert_yaxis()
    ax.set_xlim(lo - 0.06 * span, hi + 0.62 * span)
    ax.set_xlabel("mean gap (fidelity_cost)")
    ax.set_title("Gap to optimum, by family")
    ax.grid(True, axis="x", alpha=0.3)
    handles = [
        plt.Line2D([0], [0], marker="s", linestyle="", color=GROUP_COLORS[g], markersize=9)
        for g in GROUP_ORDER
        if g in s["solver"].map(_group).values
    ]
    labels = [GROUP_LABELS[g] for g in GROUP_ORDER if g in s["solver"].map(_group).values]
    handles.append(plt.Line2D([0], [0], color="red", linestyle="--", linewidth=1.4))
    labels.append("best (lowest mean gap)")
    if handles:
        ax.legend(
            handles, labels, loc="upper left", bbox_to_anchor=(1.01, 1.0),
            fontsize=8, title="family", borderaxespad=0.0,
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_quality_vs_time(stats: pd.DataFrame, ideal_stats: dict, out_path: Path, best: str) -> None:
    """Scatter: mean gap (y) vs median time (x, log scale), color = family, plus the optimum
    point. A dashed red line marks the overall winner's gap (lowest mean gap)."""
    fig, ax = plt.subplots(figsize=(12, 7.5))
    s = stats.sort_values("median_seconds").reset_index(drop=True)

    seen_groups: list[str] = []
    for _, row in s.iterrows():
        g = _group(row["solver"])
        ax.scatter(
            [row["median_seconds"]],
            [row["mean_gap"]],
            s=150,
            color=GROUP_COLORS[g],
            edgecolor="black",
            linewidth=0.6,
            zorder=3,
            label=GROUP_LABELS[g] if g not in seen_groups else None,
        )
        seen_groups.append(g)
    best_gap = float(s.loc[s["solver"] == best, "mean_gap"].iloc[0])
    ax.axhline(best_gap, color="red", linestyle="--", linewidth=1.2, zorder=2,
               label="best (lowest mean gap)")
    ax.axhline(0, color="black", linewidth=1.0, linestyle=":", zorder=1)
    ax.scatter(
        [ideal_stats["median_seconds"]],
        [0.0],
        s=200,
        marker="X",
        color="#5DADE2",
        edgecolor="black",
        linewidth=0.6,
        zorder=4,
        label="optimal (exact DP)",
    )
    ax.set_xscale("log")
    ax.set_xlabel("time (s, log)")
    ax.set_ylabel("gap to optimum")
    ax.set_title("Quality vs time")
    # Extra room above the points for labels and below zero, so the axis
    # doesn't clip the annotation.
    y_lo = min(0.0, float(s["mean_gap"].min()))
    y_hi = max(0.0, float(s["mean_gap"].max()))
    margin = max(y_hi - y_lo, 1e-6)
    ax.set_ylim(y_lo - 0.35 * margin, y_hi + 0.45 * margin)
    _place_labels(
        fig,
        ax,
        s["median_seconds"].tolist(),
        s["mean_gap"].tolist(),
        s["short"].tolist(),
    )
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_gap_heatmap(matrix: pd.DataFrame, out_path: Path, best: str) -> None:
    """Compact gap matrix: rows = cases, columns = representatives. A dashed
    red box outlines the overall winner's column (lowest mean gap)."""
    n_rows, n_cols = matrix.shape
    values = matrix.to_numpy(dtype=float)
    vmin_data, vmax_data = float(np.nanmin(values)), float(np.nanmax(values))

    # Diverging scale centered on zero; handles data with no negative values.
    vmin = min(0.0, vmin_data)
    vmax = max(0.0, vmax_data)
    if vmin >= 0.0:
        vmin = -max(1e-6, 0.05 * vmax)
    if vmax <= 0.0:
        vmax = max(1e-6, 0.05 * abs(vmin))
    norm = TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(max(9.0, 1.15 * n_cols + 3.0), 0.52 * n_rows + 2.6))
    im = ax.imshow(values, cmap="RdYlGn_r", norm=norm, aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("gap")

    ax.set_xticks(np.arange(n_cols))
    ax.set_xticklabels([_stacked(c) for c in matrix.columns], fontsize=9)
    for tick, solver in zip(ax.get_xticklabels(), matrix.columns):
        tick.set_color(_group_color(solver))
        tick.set_fontweight("bold")
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels(matrix.index, fontsize=9)
    ax.set_xlabel("representative")
    ax.set_ylabel("case")
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)
    # Separator (black line) between solver families in the columns.
    for j in range(1, n_cols):
        if _group_rank(matrix.columns[j]) != _group_rank(matrix.columns[j - 1]):
            ax.axvline(j - 0.5, color="black", linewidth=1.6)
    # Dashed red box around the overall winner's column (lowest mean gap).
    if best in list(matrix.columns):
        j_best = list(matrix.columns).index(best)
        ax.add_patch(plt.Rectangle(
            (j_best - 0.5, -0.5), 1, n_rows,
            fill=False, edgecolor="red", linestyle="--", linewidth=2.0, zorder=5,
        ))

    for i in range(n_rows):
        for j in range(n_cols):
            value = values[i, j]
            if np.isnan(value):
                text = "n/a"
            elif abs(value) <= TOL:
                text = "0"
            else:
                text = f"{value:.4f}"
            frac = float(norm(value)) if not np.isnan(value) else 0.5
            color = "white" if (frac < 0.16 or frac > 0.84) else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=8, color=color)

    ax.set_title("Gap vs optimum")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_case_detail(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str], stats: pd.DataFrame, out_path: Path,
    best: str,
) -> bool:
    """Detail only for cases where at least one representative missed the optimum
    (max 6). A dashed red line marks the overall winner's cost in each case."""
    order = case_order(ideal)
    gaps = {}
    for rep in reps:
        sdf = df[df["solver"] == rep].set_index("case")["fidelity_cost"]
        gaps[rep] = {c: float(sdf.get(c, np.nan)) - float(ideal[c]) for c in order}

    problematic = [
        c for c in order if any(abs(gaps[rep][c]) > TOL for rep in reps)
    ]
    if not problematic:
        print("Every representative hits the optimum on every case, skipping case_detail.")
        return False

    severity = {c: max(abs(gaps[rep][c]) for rep in reps) for c in problematic}
    selected = sorted(
        sorted(problematic, key=lambda c: -severity[c])[:6], key=lambda c: order.index(c)
    )
    ncols = 2 if len(selected) > 1 else 1
    nrows = int(np.ceil(len(selected) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 3.7 * nrows), squeeze=False)

    rep_order = sorted(stats["solver"].tolist(), key=lambda r: (_group_rank(r), r))
    cost_lookup = {
        (r["solver"], r["case"]): float(r["fidelity_cost"])
        for _, r in df[df["solver"].isin(rep_order)].iterrows()
    }
    for ax, case in zip(axes.ravel(), selected):
        costs = [cost_lookup.get((r, case), np.nan) for r in rep_order]
        x = np.arange(len(rep_order))
        colors = ["#2ca02c" if abs(gaps[r][case]) <= TOL else "#C44E52" for r in rep_order]
        ax.bar(x, costs, color=colors, alpha=0.9, width=0.65)
        ax.axhline(float(ideal[case]), color="black", linestyle="--", linewidth=1.5,
                   label="optimal")
        best_cost = cost_lookup.get((best, case), np.nan)
        if not np.isnan(best_cost):
            ax.axhline(best_cost, color="red", linestyle="--", linewidth=1.2, label="best")
        ax.set_xticks(x)
        ax.set_xticklabels([_stacked(r) for r in rep_order], fontsize=8)
        for tick, solver in zip(ax.get_xticklabels(), rep_order):
            tick.set_color(_group_color(solver))
            tick.set_fontweight("bold")
        worst = max((gaps[r][case] for r in rep_order), key=abs)
        ax.set_title(f"{case} ({worst:+.4f})", fontsize=10)
        ax.set_ylabel("fidelity_cost", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        ax.margins(y=0.18)

    for ax in axes.ravel()[len(selected):]:
        ax.axis("off")
    axes.ravel()[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(f"Largest gaps ({len(selected)} of {len(problematic)} cases)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return True


def plot_crossover(csv_path: Path, out_path: Path) -> bool:
    """Optional scaling plot: time and gap vs number of interactions."""
    if not csv_path.exists():
        print("No results/crossover.csv, skipping the crossover plot.")
        return False
    df = pd.read_csv(csv_path)
    needed = {
        "interactions", "exact_dp_seconds", "tabu_seconds", "tabu_gap",
        "exact_dp_hit_budget",
    }
    if df.empty or not needed.issubset(df.columns):
        print("results/crossover.csv is missing required columns, skipping the crossover plot.")
        return False
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(needed))
    if df.empty:
        print("results/crossover.csv is empty after filtering, skipping the crossover plot.")
        return False

    fig, (ax_time, ax_gap) = plt.subplots(1, 2, figsize=(13, 5.2))

    hit = df[df["exact_dp_hit_budget"] > 0]
    ok = df[df["exact_dp_hit_budget"] == 0]
    ax_time.scatter(df["interactions"], df["exact_dp_seconds"], s=45,
                    color="#C44E52", label="exact_dp (optimal)", zorder=3)
    ax_time.scatter(df["interactions"], df["tabu_seconds"], s=45,
                    color="#4C72B0", label="tabu fidelity", zorder=3)
    if not hit.empty:
        ax_time.scatter(hit["interactions"], hit["exact_dp_seconds"], s=90, marker="o",
                        facecolors="none", edgecolors="#C44E52", linewidth=1.2,
                        label="exact_dp at budget (fallback)", zorder=4)
    ax_time.set_xscale("log")
    ax_time.set_yscale("log")
    ax_time.set_xlabel("number of 2Q interactions")
    ax_time.set_ylabel("solve time (s, log scale)")
    ax_time.set_title("Time vs instance size")
    ax_time.grid(True, which="both", alpha=0.25)
    ax_time.legend(fontsize=8)

    if ok.empty:
        ax_gap.text(0.5, 0.5, "no rows without an exact_dp fallback",
                    ha="center", va="center", transform=ax_gap.transAxes, fontsize=10)
    else:
        ax_gap.scatter(ok["interactions"], ok["tabu_gap"], s=45, color="#4C72B0", zorder=3)
        ax_gap.axhline(0, color="black", linewidth=1.0, linestyle=":")
    ax_gap.set_xscale("log")
    ax_gap.set_xlabel("number of 2Q interactions")
    ax_gap.set_ylabel("tabu vs exact_dp gap (fidelity_cost)")
    ax_gap.set_title("Gap vs size (rows without a fallback only)")
    ax_gap.grid(True, which="both", alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return True


def generate_summary(
    df: pd.DataFrame,
    ideal: pd.Series,
    stats: pd.DataFrame,
    collapse_report: list[dict],
    identical_merges: list[tuple[str, list[str]]],
    out_file: Path = SUMMARY_PATH,
) -> None:
    """Summary: optimum on its own, representatives as a distance from it."""
    total_cases = int(df["case"].nunique())
    n_variants = sum(len(members) for _, members in FAMILIES if not df[df["solver"] == members[0]].empty)
    ref = df[df["solver"].isin(REFERENCES)]
    lines = [
        "# Benchmark results summary (fidelity)",
        "",
        "Optimal solution = exact_dp: full search of the space (layouts, any",
        "SWAPs on edges, any topological order, exact fidelity cost), computed",
        "once per case. No solver can beat it, only match it. `gap` =",
        "solver's fidelity_cost minus the case's optimal cost: 0 = reaches",
        "optimum, positive = distance from optimum, negative = the solver went",
        "below our routing optimum (Qiskit's full optimization, see",
        "`results/gap-analysis.md`).",
        "",
        f"- Test cases: {total_cases}",
        f"- Representatives: {len(stats)} (out of {n_variants} compared variants)",
        "- Metric: `fidelity_cost_cancelled` (true minimum), when present in the CSV",
        "",
        "## Optimum (exact DP, lower bound)",
        "",
        "| Reference | Mean fidelity_cost | Median time (s) | Mean time (s) |",
        "|---|---|---|---|",
    ]
    for solver in REFERENCES:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        lines.append(
            f"| {_name(solver)} | {sdf['fidelity_cost'].mean():.4f} | "
            f"{sdf['seconds'].median():.4f} | {sdf['seconds'].mean():.4f} |"
        )
    lines += [
        "",
        "## Representatives (distance from optimum)",
        "",
        "| Family | Representative | Mean fidelity_cost | Mean gap vs optimum | std gap | "
        "Median time (s) | Mean time (s) | Mean evals | At optimum |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, row in stats.iterrows():
        evals = "-" if np.isnan(row["mean_evals"]) else f"{row['mean_evals']:.0f}"
        lines.append(
            f"| {GROUP_LABELS[_group(row['solver'])]} | {row['name']} | {row['mean_cost']:.4f} | "
            f"{row['mean_gap']:+.4f} | "
            f"{row['std_gap']:.4f} | {row['median_seconds']:.4f} | "
            f"{row['mean_seconds']:.3f} | {evals} | "
            f"{int(row['n_opt'])}/{int(row['n_cases'])} |"
        )
    lines.append("")
    lines.append(
        "`At optimum` = cases where |gap| <= 1e-9, i.e. the solver matched "
        "the optimum. Going below the optimum does not count as a hit, "
        "since that is a different game (see gap-analysis)."
    )
    lines.append("")

    lines += [
        "## Representatives: what was merged",
        "",
        "Variants within a family share the same algorithm and differ only in",
        "the start, so the plots show the representative. The table shows how",
        "much the collapsed variant actually differed from the representative "
        f"(over the gaps, tolerance {TOL:g}), so nothing disappears silently under the label.",
        "",
        "| Representative | Collapsed variant | Cases with a difference | Max |delta| | Mean |delta| |",
        "|---|---|---|---|---|",
    ]
    for item in collapse_report:
        lines.append(
            f"| {_name(item['rep'])} | {_name(item['variant'])} | "
            f"{item['n_diff']}/{item['n_cases']} | {item['max_diff']:.4f} | "
            f"{item['mean_diff']:.4f} |"
        )
    lines.append("")
    if identical_merges:
        for kept, merged in identical_merges:
            names = ", ".join(_name(m) for m in merged)
            lines.append(
                f"- Additional merge: {_name(kept)} and {names} have identical "
                f"fidelity_cost vectors on every case."
            )
    else:
        lines.append(
            "- Additional representative merges: none (no pair has "
            "identical fidelity_cost vectors)."
        )
    lines.append("")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Summary written: {out_file}")


def cleanup_plots(out_dir: Path, keep: set[str]) -> list[str]:
    """Removes PNG files from plots/ that are outside the current plot set."""
    removed = []
    for png in sorted(out_dir.glob("*.png")):
        if png.name not in keep:
            png.unlink()
            removed.append(png.name)
    return removed


def main() -> None:
    print("Loading data...")
    df = load_data()
    ideal = ideal_per_case(df)
    if ideal.empty:
        raise SystemExit("No reference (exact_dp) rows in the CSV, nothing to compute the gap against.")

    reps, collapse_report = collapse_families(df)
    reps, identical_merges = merge_identical_reps(df, ideal, reps)
    stats = representative_stats(df, ideal, reps)
    best = best_solver(stats)
    print(f"Best representative (lowest mean gap): {best}\n")

    # Explicit printout of the representative mapping, so the merge is visible right away.
    print("\nFamily representatives (dedup):")
    for rep, members in FAMILIES:
        if rep not in reps:
            continue
        scaled = [m for m in members if m != rep]
        suffix = f" <- {', '.join(scaled)}" if scaled else ""
        print(f"  {rep}{suffix}")
    print("\nDifferences within collapsed families (gap, tolerance 1e-9):")
    for item in collapse_report:
        print(
            f"  {item['rep']} vs {item['variant']}: differs on "
            f"{item['n_diff']}/{item['n_cases']} cases, "
            f"max |delta| {item['max_diff']:.4f}, mean |delta| {item['mean_diff']:.4f}"
        )
    if identical_merges:
        for kept, merged in identical_merges:
            print(f"  additional merge (identical vectors): {kept} <- {', '.join(merged)}")
    else:
        print("  additional merges of identical representatives: none")
    print("")

    out = PLOTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    print("Generating plots...")
    written: list[str] = []
    plot_gap_to_ideal(stats, out / "gap_to_ideal.png", best)
    written.append("gap_to_ideal.png")
    ideal_stats = {
        "median_seconds": float(df[df["solver"] == REFERENCES[0]]["seconds"].median())
    }
    plot_quality_vs_time(stats, ideal_stats, out / "quality_vs_time_tradeoff.png", best)
    written.append("quality_vs_time_tradeoff.png")
    _, matrix = gap_matrix(df, ideal, stats["solver"].tolist())
    plot_gap_heatmap(matrix, out / "gap_heatmap.png", best)
    written.append("gap_heatmap.png")
    if plot_case_detail(df, ideal, reps, stats, out / "case_detail.png", best):
        written.append("case_detail.png")
    if plot_crossover(CROSSOVER_CSV, out / "crossover.png"):
        written.append("crossover.png")

    removed = cleanup_plots(out, set(written))
    if removed:
        print(f"Removed stale plots: {', '.join(removed)}")

    print("Generating summary...")
    generate_summary(df, ideal, stats, collapse_report, identical_merges)

    print("\nFiles written:")
    for name in written:
        print(f"  plots/{name}")
    print(f"  {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
