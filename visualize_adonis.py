"""Adonis plot set (incl. publication_overview.png) -> plots/adonis/.

Copy of ``visualize_results.py`` from ``main`` (which writes this set into
plots/), writing to plots/adonis/ instead so it does not clean up this
branch's plots/*.png. Changes vs main: panel (d) uses ``cz_cost_cancelled``
(SWAP = 3 CZ, comparable with the CZ-decomposed Qiskit output) and the
bottom panels draw leader lines from labels to markers.
ponytail: duplicate of main's script until the branches are merged.

Usage: python visualize_adonis.py
"""

#!/usr/bin/env python3
"""
Wizualizacja wyników benchmarku fidelity (faza 3).

Referencja (exact_dp) to "ideał": pełne przeszukanie przestrzeni routingu,
liczone raz na przypadek, deterministycznie. Solvery porównywane rysujemy
jako odległość od tego ideału, a nie jako równorzędnych konkurentów.

Warianty tabu są do siebie bardzo podobne, więc przed rysowaniem scalamy je
do reprezentantów rodziny (patrz FAMILIES i funkcja collapse_families).
Skrypt wypisuje na stdout, jak bardzo scalone warianty faktycznie się różnią,
żeby nic nie zniknęło pod etykietą reprezentanta.

Skrypt tylko czyta results/benchmark-fidelity.csv (wyniki nie są tu liczone).
Gdy CSV ma kolumny `*_cancelled` (true minimum: wejście zredukowane, wynik
punktowany po anulowaniu), wykresy i podsumowanie używają
`fidelity_cost_cancelled`, a nie surowego `fidelity_cost`.

Wyjście: plots/*.png (benchmark comparisons plus a theoretical scaling plot)
and results_summary.md.
"""

import math
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive: skrypt działa bez ekranu i bez blokowania

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

warnings.filterwarnings("ignore")

RESULTS_DIR = Path("results")
PLOTS_DIR = Path("plots/adonis")
FIDELITY_CSV = RESULTS_DIR / "benchmark-fidelity.csv"
CROSSOVER_CSV = RESULTS_DIR / "crossover.csv"
SUMMARY_PATH = PLOTS_DIR / "results_summary.md"

# Tolerancja równości kosztów (te same przypadki uznajemy za identyczne).
TOL = 1e-9

LONG_CSV = RESULTS_DIR / "long.csv"
LONG_BASELINE_CSV = RESULTS_DIR / "long-baselines.csv"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Liberation Sans", "DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 9.5,
        "axes.titlesize": 11.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 10.0,
        "axes.labelweight": "medium",
        "xtick.labelsize": 9.0,
        "ytick.labelsize": 9.0,
        "legend.fontsize": 8.5,
        "figure.dpi": 150,
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#CBD5E1",
        "axes.linewidth": 0.8,
        "grid.color": "#F1F5F9",
        "grid.linewidth": 0.8,
    }
)

# Ideał = exact_dp: pełne przeszukanie (layouty, SWAP-y na krawędziach,
# dowolny porządek topologiczny, dokładny koszt fidelity). Nie do pobicia
# w naszym modelu routingu; solver może się z nim zrównać.
REFERENCES = ("exact_dp",)

GROUPS = {
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
    "tabu": "#D97706",      # Warm Amber / Terracotta
    "genetic": "#8B5CF6",   # Elegant Royal Purple
    "qiskit": "#2563EB",    # High-contrast Royal Blue
    "baseline": "#0D9488",  # Crisp Emerald / Teal
    "exact_dp": "#1E293B",  # Deep Slate / Charcoal
    "other": "#64748B",     # Muted Slate
}

PLOT_NAMES = {
    "tabu_fidelity": "Tabu fidelity",
    "genetic_fidelity": "Fidelity-aware GA",
    "qiskit_sabre": "Qiskit SABRE",
    "qiskit_preset": "Qiskit preset",
    "brute_fidelity_layout": "Brute-force fidelity",
    "brute_force_layout": "Brute-force layout",
    "greedy_shortest_path": "Greedy identity",
    "tabu_search": "Tabu search",
    "genetic_search": "Layout-only GA",
}


def _group(solver: str) -> str:
    return GROUPS.get(solver, "other")


def _group_rank(solver: str) -> int:
    group = _group(solver)
    return GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)


def _group_color(solver: str) -> str:
    return GROUP_COLORS[_group(solver)]

# Rodziny solverów: reprezentant -> warianty, które reprezentuje.
# Kolejność w krotce ma znaczenie: pierwszy element to reprezentant.
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

# Pełne nazwy (legenda, osie) i krótkie nazwy (kolumny macierzy, panele).
DISPLAY = {
    "exact_dp": "Exact DP reference",
    "tabu_fidelity": "Fidelity-aware Tabu",
    "tabu_fidelity_greedy": "Fidelity-aware Tabu (greedy start)",
    "tabu_fidelity_sabre": "Fidelity-aware Tabu (SABRE start)",
    "tabu_search": "Tabu search",
    "tabu_sabre_start": "Tabu + SABRE warm start",
    "genetic_search": "Genetic algorithm (layout)",
    "genetic_fidelity": "Fidelity-aware GA",
    "genetic_fidelity_sabre": "Fidelity-aware GA (SABRE start)",
    "qiskit_sabre": "Qiskit SABRE",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "Greedy (identity)",
    "brute_force_layout": "Brute-force layout (greedy SWAPs)",
    "brute_fidelity_layout": "Brute-force fidelity (greedy SWAPs)",
}

SHORT = {
    "exact_dp": "Exact DP reference",
    "tabu_fidelity": "Fidelity-aware Tabu",
    "tabu_fidelity_sabre": "FA-Tabu (SABRE)",
    "tabu_search": "Tabu search",
    "genetic_search": "Genetic algorithm",
    "genetic_fidelity": "Fidelity-aware GA",
    "genetic_fidelity_sabre": "FA-GA (SABRE)",
    "qiskit_sabre": "Qiskit SABRE",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "greedy",
    "brute_force_layout": "brute layout",
    "brute_fidelity_layout": "brute fidelity",
}

# Etykiety łamane na dwie linie: mieszczą się bez obracania, nic się nie zlewa.
STACKED = {
    "exact_dp": "Exact DP\nreference",
    "tabu_fidelity": "Fidelity-aware\nTabu",
    "tabu_fidelity_sabre": "FA-Tabu\n(SABRE)",
    "tabu_search": "Tabu\nsearch",
    "genetic_search": "Genetic\nalgorithm",
    "genetic_fidelity": "Fidelity-aware\nGA",
    "genetic_fidelity_sabre": "FA-GA\n(SABRE)",
    "qiskit_sabre": "Qiskit\nSABRE",
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
    """Wczytuje CSV i przechodzi na metrykę true minimum, jeśli jest dostępna."""
    results_path = Path(results_dir)
    df = pd.read_csv(results_path / "benchmark-fidelity.csv")
    df = df[df["error"].isna() | (df["error"] == "")].copy()
    # True minimum (faza 2): wynik po anulowaniu. Gdy CSV ma kolumnę
    # `fidelity_cost_cancelled`, używamy jej zamiast surowego kosztu, żeby
    # porównanie szło po tej samej metryce co podsumowanie benchmarku.
    if "fidelity_cost_cancelled" in df.columns:
        df = df.drop(columns=["fidelity_cost"]).rename(
            columns={"fidelity_cost_cancelled": "fidelity_cost"}
        )
    df = df[df["fidelity_cost"] >= 0]
    return df


def ideal_per_case(df: pd.DataFrame) -> pd.Series:
    """Ideał per przypadek = min fidelity_cost po referencjach."""
    refs = df[df["solver"].isin(REFERENCES)]
    return refs.groupby("case")["fidelity_cost"].min()


def case_order(ideal: pd.Series) -> list[str]:
    """Kolejność przypadków: rosnący koszt ideału (rozmiar instancji)."""
    return sorted(ideal.index, key=lambda c: (float(ideal[c]), str(c)))


def _cost_vector(df: pd.DataFrame, solver: str) -> pd.Series:
    return df[df["solver"] == solver].set_index("case")["fidelity_cost"].sort_index()


def _same_vector(a: pd.Series, b: pd.Series) -> bool:
    """Czy dwa wektory kosztów są identyczne (te same przypadki, tolerancja TOL)."""
    if not a.index.equals(b.index):
        return False
    return bool((a - b).abs().max() <= TOL)


def collapse_families(df: pd.DataFrame) -> tuple[list[str], list[dict]]:
    """Zwraca listę reprezentantów i raport różnic w scalonych rodzinach."""
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
    """Scala reprezentantów o identycznych wektorach kosztów (tolerancja TOL)."""
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
    """Statystyki per reprezentant: koszt, gap, czas, ewaluacje, trafienia w optimum."""
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
                # na optimum = trafienie w ideał (równość w granicach TOL);
                # zejście poniżej ideału liczymy osobno jako ujemny gap.
                "n_opt": int((gaps.abs() <= TOL).sum()),
                "n_cases": int(len(gaps)),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_gap").reset_index(drop=True)


def best_solver(stats: pd.DataFrame) -> str:
    """Return the representative with the lowest mean gap."""
    return str(stats.sort_values("mean_gap").iloc[0]["solver"])


def gap_matrix(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str]
) -> tuple[list[str], pd.DataFrame]:
    """Macierz gapów: wiersze = przypadki (rosnący ideał), kolumny = reprezentanci."""
    cases = case_order(ideal)
    reps = sorted(reps, key=lambda solver: (_group_rank(solver), solver))
    data = {}
    for rep in reps:
        sdf = df[df["solver"] == rep].set_index("case")["fidelity_cost"]
        data[rep] = [float(sdf.get(c, np.nan)) - float(ideal[c]) for c in cases]
    return cases, pd.DataFrame(data, index=cases)


def _place_labels(fig, ax, xs, ys, labels) -> None:
    """Etykiety obok punktów, z prostym unikaniem nachodzenia na siebie."""
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
    """Compare mean gaps with family colors and a marker for the best solver."""
    s = stats.copy()
    s["_rank"] = s["solver"].map(_group_rank)
    s = s.sort_values(["_rank", "mean_gap"]).reset_index(drop=True)
    total = int(s["n_cases"].max())
    fig, ax = plt.subplots(figsize=(10.5, 0.52 * len(s) + 1.8), constrained_layout=True)
    y = np.arange(len(s))
    gaps = s["mean_gap"].to_numpy()
    colors = [_group_color(solver) for solver in s["solver"]]
    ax.barh(y, gaps, color=colors, alpha=0.92, height=0.62, edgecolor="white", linewidth=0.8)
    ax.axvline(0, color="#1E293B", linewidth=1.2)
    best_gap = float(s.loc[s["solver"] == best, "mean_gap"].iloc[0])
    ax.axvline(best_gap, color="#EF4444", linestyle="--", linewidth=1.5,
               label=f"Best mean gap: {_name(best)} (+{best_gap:.4f})")

    lo, hi = min(float(gaps.min()), 0.0), max(float(gaps.max()), 0.0)
    span = max(hi - lo, 1e-6)
    for yi, g, n_opt in zip(y, gaps, s["n_opt"]):
        off = 0.015 * span
        ax.text(
            g + off if g >= 0 else g - off,
            yi,
            f"{g:+.4f}   ({int(n_opt)}/{total} at reference)",
            va="center",
            ha="left" if g >= 0 else "right",
            fontsize=8.5,
            fontweight="bold" if g == best_gap else "normal",
        )
    ax.set_yticks(y)
    ax.set_yticklabels(s["name"], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(lo - 0.04 * span, hi + 0.45 * span)
    ax.set_xlabel("Mean Fidelity-Cost Gap to Exact Reference (0 = Optimum; Lower is Better)", fontweight="bold")
    ax.set_title("Mean Gap to the Exact-DP Reference", pad=10, fontweight="bold")
    ax.grid(True, axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=GROUP_COLORS[group])
               for group in GROUP_ORDER]
    ax.legend(handles, [group.title() for group in GROUP_ORDER], loc="lower right", frameon=True, facecolor="white", edgecolor="#CBD5E1", fontsize=8.5)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_quality_vs_time(stats: pd.DataFrame, ideal_stats: dict, out_path: Path) -> None:
    """Rozrzut: średni gap (y) vs mediana czasu (x, skala log), plus punkt ideału."""
    fig, ax = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    s = stats.sort_values("median_seconds").reset_index(drop=True)

    ax.scatter(
        s["median_seconds"],
        s["mean_gap"],
        s=100,
        color=[_group_color(solver) for solver in s["solver"]],
        edgecolor="white",
        linewidth=1.2,
        zorder=4,
        label="Solver representatives",
    )
    ax.axhline(0, color="#CBD5E1", linewidth=1.0, linestyle=":", zorder=1)
    ax.scatter(
        [ideal_stats["median_seconds"]],
        [0.0],
        s=140,
        marker="X",
        color="#EF4444",
        edgecolor="white",
        linewidth=1.2,
        zorder=5,
        label="Exact DP reference",
    )

    # Pareto boundary: SABRE -> Tabu -> Exact DP
    pareto_solvers = ["qiskit_sabre", "tabu_fidelity"]
    p_pts = [(ideal_stats["median_seconds"], 0.0)]
    for ps in pareto_solvers:
        row = s[s["solver"] == ps]
        if not row.empty:
            p_pts.append((float(row["median_seconds"].iloc[0]), float(row["mean_gap"].iloc[0])))
    p_pts = sorted(p_pts, key=lambda x: x[1])
    ax.plot([pt[0] for pt in p_pts], [pt[1] for pt in p_pts], linestyle=":", color="#94A3B8", linewidth=1.5, zorder=2)

    ax.set_xscale("log")
    ax.set_xlabel("Median Solve Time (s, logarithmic scale)", fontweight="bold")
    ax.set_ylabel("Mean Fidelity-Cost Gap to Exact Reference", fontweight="bold")
    ax.set_title("Routing Quality versus Runtime Frontier", pad=10, fontweight="bold")
    y_lo = min(0.0, float(s["mean_gap"].min()))
    y_hi = max(0.0, float(s["mean_gap"].max()))
    margin = max(y_hi - y_lo, 1e-6)
    ax.set_ylim(y_lo - 0.25 * margin, y_hi + 0.35 * margin)
    _place_labels(
        fig,
        ax,
        s["median_seconds"].tolist(),
        s["mean_gap"].tolist(),
        s["name"].tolist(),
    )
    ax.annotate(
        "Exact DP reference (0.015s)",
        (ideal_stats["median_seconds"], 0.0),
        xytext=(10, -16),
        textcoords="offset points",
        fontsize=8.5,
        fontweight="bold",
        color="#EF4444",
    )
    ax.grid(True, which="both", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#CBD5E1", fontsize=8.5)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_gap_heatmap(matrix: pd.DataFrame, out_path: Path) -> None:
    """Kompaktowa macierz gapów: wiersze = przypadki, kolumny = reprezentanci."""
    n_rows, n_cols = matrix.shape
    values = matrix.to_numpy(dtype=float)
    vmin_data, vmax_data = float(np.nanmin(values)), float(np.nanmax(values))

    norm = TwoSlopeNorm(vmin=-0.05, vcenter=0.0, vmax=max(vmax_data, 0.5))

    fig, ax = plt.subplots(figsize=(max(9.0, 1.15 * n_cols + 2.5), 0.50 * n_rows + 2.2), constrained_layout=True)
    im = ax.imshow(values, cmap="YlOrRd", norm=norm, aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Gap to Exact-DP Reference (Fidelity Cost)", fontsize=8.5)

    ax.set_xticks(np.arange(n_cols))
    ax.set_xticklabels([_stacked(c) for c in matrix.columns], fontsize=8.5)
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels(matrix.index, fontsize=8.5)
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.0)
    ax.tick_params(which="minor", length=0)

    for i in range(n_rows):
        for j in range(n_cols):
            value = values[i, j]
            if np.isnan(value):
                text = "N/A"
            elif abs(value) <= TOL:
                text = "0"
            else:
                text = f"{value:.3f}"
            color = "white" if value > 0.8 else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=7.5, color=color, fontweight="bold" if value > 0.5 else "normal")

    ax.set_title("Gap to Exact-DP Reference by Case and Solver (0 = Optimum)", pad=10, fontweight="bold")
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    plt.close(fig)


def plot_case_detail(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str], stats: pd.DataFrame, out_path: Path
) -> bool:
    """Szczegół tylko dla przypadków, w których ktoś nie trafił w optimum (max 6)."""
    order = case_order(ideal)
    gaps = {}
    for rep in reps:
        sdf = df[df["solver"] == rep].set_index("case")["fidelity_cost"]
        gaps[rep] = {c: float(sdf.get(c, np.nan)) - float(ideal[c]) for c in order}

    problematic = [
        c for c in order if any(abs(gaps[rep][c]) > TOL for rep in reps)
    ]
    if not problematic:
        print("Every representative reaches the reference on every case; skipping case_detail.")
        return False

    severity = {c: max(abs(gaps[rep][c]) for rep in reps) for c in problematic}
    selected = sorted(
        sorted(problematic, key=lambda c: -severity[c])[:6], key=lambda c: order.index(c)
    )
    ncols = 2 if len(selected) > 1 else 1
    nrows = int(np.ceil(len(selected) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 3.7 * nrows), squeeze=False)

    rep_order = stats["solver"].tolist()  # ta sama kolejność co w pozostałych wykresach
    cost_lookup = {
        (r["solver"], r["case"]): float(r["fidelity_cost"])
        for _, r in df[df["solver"].isin(rep_order)].iterrows()
    }
    for ax, case in zip(axes.ravel(), selected):
        costs = [cost_lookup.get((r, case), np.nan) for r in rep_order]
        x = np.arange(len(rep_order))
        colors = [
            "#2ca02c" if abs(gaps[r][case]) <= TOL
            else "#4C72B0" if gaps[r][case] < 0 else "#C44E52"
            for r in rep_order
        ]
        ax.bar(x, costs, color=colors, alpha=0.9, width=0.65)
        ax.axhline(float(ideal[case]), color="#C44E52", linestyle="--", linewidth=1.5,
                    label="Exact DP reference")
        ax.set_xticks(x)
        ax.set_xticklabels([_stacked(r) for r in rep_order], fontsize=8)
        worst = max((gaps[r][case] for r in rep_order), key=abs)
        ax.set_title(
            f"{case}: reference {float(ideal[case]):.4f}, largest gap {worst:+.4f}",
            fontsize=10,
        )
        ax.set_ylabel("fidelity_cost", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        ax.margins(y=0.18)

    for ax in axes.ravel()[len(selected):]:
        ax.axis("off")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    handles += [
        plt.Rectangle((0, 0), 1, 1, color="#2ca02c"),
        plt.Rectangle((0, 0), 1, 1, color="#4C72B0"),
        plt.Rectangle((0, 0), 1, 1, color="#C44E52"),
    ]
    labels += ["At reference", "Below reference", "Above reference"]
    axes.ravel()[0].legend(handles, labels, loc="upper left", fontsize=8)
    fig.suptitle(
        f"Cases not reaching the reference: showing {len(selected)} of {len(problematic)} "
        "largest gaps; red bars indicate higher cost",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return True


def plot_fidelity_vs_swaps(df: pd.DataFrame, reps: list[str], out_path: Path) -> None:
    """Show whether fewer SWAPs also means lower fidelity cost."""
    fig, ax = plt.subplots(figsize=(7.5, 4.8), constrained_layout=True)
    plotted_groups: set[str] = set()
    for solver in reps:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        group = _group(solver)
        label = group.title() if group not in plotted_groups else "_nolegend_"
        ax.scatter(
            sdf["swap_count"],
            sdf["fidelity_cost"],
            s=48,
            alpha=0.85,
            color=_group_color(solver),
            edgecolor="white",
            linewidth=0.8,
            label=label,
        )
        plotted_groups.add(group)
    ax.set_xlabel("Inserted SWAP Count", fontweight="bold")
    ax.set_ylabel("Cancelled Fidelity Cost", fontweight="bold")
    ax.set_title("Fidelity Quality versus Movement Overhead", pad=10, fontweight="bold")
    ax.grid(True, alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(title="Solver Family", frameon=True, facecolor="white", edgecolor="#CBD5E1", ncol=2, loc="upper left", fontsize=8.5)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_solver_wins(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str], out_path: Path
) -> None:
    """Count the benchmark cases won by each solver representative."""
    scores = df[df["solver"].isin(reps)].pivot(
        index="case", columns="solver", values="fidelity_cost"
    )
    scores = scores.reindex(ideal.index)
    winners = scores.eq(scores.min(axis=1), axis=0)
    wins = winners.sum().sort_values(ascending=True)
    wins = wins[wins > 0]

    fig, ax = plt.subplots(figsize=(7.5, 4.0), constrained_layout=True)
    colors = [_group_color(solver) for solver in wins.index]
    labels = [PLOT_NAMES.get(solver, _name(solver)) for solver in wins.index]
    ax.barh(labels, wins.values, color=colors, height=0.58, alpha=0.92, edgecolor="white", linewidth=0.8)
    for index, value in enumerate(wins.values):
        ax.text(value + 0.15, index, f"{int(value)} / {len(ideal)} cases ({100*value/len(ideal):.0f}%)", va="center", fontsize=8.5, fontweight="bold")
    ax.set_xlim(0, max(float(wins.max()) + 2.5, 4))
    ax.set_xlabel("Cases Achieving Lowest Fidelity Cost", fontweight="bold")
    ax.set_title("Benchmark Wins Across 13 Instances", pad=10, fontweight="bold")
    ax.grid(True, axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_cost_distribution(df: pd.DataFrame, reps: list[str], out_path: Path) -> None:
    """Compare the spread of fidelity costs across solver families."""
    groups = []
    labels = []
    colors = []
    for group in GROUP_ORDER:
        values = df[df["solver"].isin([s for s in reps if _group(s) == group])][
            "fidelity_cost"
        ].dropna()
        if values.empty:
            continue
        groups.append(values.to_numpy())
        labels.append(group.title())
        colors.append(GROUP_COLORS[group])

    fig, ax = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
    box = ax.boxplot(
        groups,
        patch_artist=True,
        tick_labels=labels,
        showmeans=True,
        showfliers=False,
        widths=0.56,
        meanprops={"marker": "D", "markerfacecolor": "white", "markeredgecolor": "#333333", "markersize": 4},
        medianprops={"color": "#222222", "linewidth": 1.2},
    )
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.62)
    rng = np.random.default_rng(7)
    for index, (values, color) in enumerate(zip(groups, colors), start=1):
        jitter = rng.uniform(-0.13, 0.13, len(values))
        ax.scatter(
            index + jitter,
            values,
            s=13,
            color=color,
            alpha=0.42,
            edgecolor="white",
            linewidth=0.35,
            zorder=2,
        )
    ax.set_ylabel("Cancelled fidelity cost")
    ax.set_title("Spread of routing quality", pad=10)
    ax.grid(True, axis="y", alpha=0.22, linewidth=0.7)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_theoretical_scaling(out_path: Path) -> None:
    """Architectural layout scaling diagram: combinatorial state explosion vs heuristic neighborhood."""
    qubits = np.array([5, 8, 10, 15, 20, 30, 50])
    layouts = np.array([math.factorial(int(n)) for n in qubits], dtype=float)
    neighbors = qubits * (qubits - 1) / 2
    eval_budget = np.full_like(qubits, 4800, dtype=float)  # GA population (60) * generations (80)

    fig, ax = plt.subplots(figsize=(8.2, 5.0), constrained_layout=True)

    # Shaded feasibility zones
    ax.axvspan(4.2, 7.5, color="#ECFDF5", alpha=0.9, zorder=1, label="Exact search computationally practical")
    ax.axvspan(7.5, 52, color="#F8FAFC", alpha=0.9, zorder=1, label="Heuristic / metaheuristic domain")

    # Curves
    ax.semilogy(
        qubits,
        layouts,
        marker="o",
        markersize=6,
        linewidth=2.4,
        color="#8B5CF6",
        zorder=3,
        label="Exact layout permutations ($n!$)",
    )
    ax.semilogy(
        qubits,
        neighbors,
        marker="s",
        markersize=6,
        linewidth=2.4,
        color="#0D9488",
        zorder=3,
        label="1-step transposition neighborhood $\\binom{n}{2}$",
    )
    ax.semilogy(
        qubits,
        eval_budget,
        linestyle="--",
        linewidth=2.0,
        color="#D97706",
        zorder=3,
        label="GA evaluation budget ($P \\times G = 4,800$)",
    )

    # Architectural annotations
    arch_annotations = [
        (5, math.factorial(5), "ODRA5 / IQM Spark (5Q)\n120 layouts (exact DP: 0.015 s)", (20, 25)),
        (10, math.factorial(10), "10Q threshold\n$3.6\\times 10^6$ layouts", (25, 18)),
        (20, math.factorial(20), "IQM Garnet (20Q)\n$2.4\\times 10^{18}$ layouts", (-75, 20)),
        (50, math.factorial(50), "Utility Scale (50Q)\n$3.0\\times 10^{64}$ layouts", (-110, -28)),
    ]
    for q, val, text, offset in arch_annotations:
        ax.scatter([q], [val], color="#EF4444", s=50, zorder=4, edgecolor="white", linewidth=1.2)
        ax.annotate(
            text,
            (q, val),
            xytext=offset,
            textcoords="offset points",
            fontsize=8.5,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", fc="#FFFFFF", ec="#CBD5E1", alpha=0.92),
            arrowprops=dict(arrowstyle="->", color="#64748B", lw=0.9),
            zorder=5,
        )

    ax.set_xlabel("Number of Physical Qubits ($n$)", fontweight="bold")
    ax.set_ylabel("Candidate State Count (log scale)", fontweight="bold")
    ax.set_title("Combinatorial Scaling: Exact Layout Search vs. Metaheuristic Neighborhoods", pad=12)
    ax.set_xlim(4, 52)
    ax.set_ylim(1, 1e70)
    ax.grid(True, which="both", alpha=0.25, linestyle="-")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=True, facecolor="white", edgecolor="#CBD5E1", loc="upper left", fontsize=8.5)

    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_deep_benchmark(csv_path: Path, out_path: Path) -> bool:
    """Plot deep-circuit stress test with clean grouping, percentage labels, and regime insights."""
    if not csv_path.exists():
        return False
    data = pd.read_csv(csv_path)
    data = data[data["error"].fillna("") == ""].copy()
    if data.empty or "exact_dp" not in set(data["solver"]):
        return False
    exact = data[data["solver"] == "exact_dp"].set_index("case")["fidelity_cost_cancelled"]
    exact_swaps = data[data["solver"] == "exact_dp"].set_index("case")["swap_count"]

    data["gap_percent"] = data.apply(
        lambda row: 100 * (row["fidelity_cost_cancelled"] - exact[row["case"]])
        / exact[row["case"]]
        if exact[row["case"]] > 0 else 0.0,
        axis=1,
    )

    baseline_data = pd.read_csv(LONG_BASELINE_CSV) if LONG_BASELINE_CSV.exists() else pd.DataFrame()
    if not baseline_data.empty:
        baseline_data["gap_percent"] = baseline_data.apply(
            lambda row: 100 * (row["fidelity_cost_cancelled"] - exact[row["case"]])
            / exact[row["case"]] if exact[row["case"]] > 0 else 0.0,
            axis=1,
        )
        data = pd.concat([data, baseline_data], ignore_index=True)

    tabu_solver = "tabu_fidelity_sabre" if "tabu_fidelity_sabre" in set(data["solver"]) else "tabu_fidelity"
    ga_solver = "genetic_fidelity_sabre" if "genetic_fidelity_sabre" in set(data["solver"]) else "genetic_fidelity"

    # Logical order: Structured -> Random -> Adversarial Hard
    preferred_order = ["queko_d32", "rand120_s0", "rand160_s0", "rand160_s1", "hard_12r", "hard_16r"]
    order = [c for c in preferred_order if c in set(data["case"])]
    if not order:
        order = list(exact.index)

    display_cases = {
        "queko_d32": "QUEKO (d=32)\n[0 SWAP ref]",
        "rand120_s0": "Rand 120\n[20 SWAP ref]",
        "rand160_s0": "Rand 160 (s0)\n[25 SWAP ref]",
        "rand160_s1": "Rand 160 (s1)\n[33 SWAP ref]",
        "hard_12r": "Hard 12r\n[28 SWAP ref]",
        "hard_16r": "Hard 16r\n[36 SWAP ref]",
    }

    solvers = ["greedy_shortest_path", tabu_solver, "genetic_fidelity", "qiskit_sabre"]
    labels = ["Greedy (Baseline)", "Fidelity-aware Tabu (SABRE start)", "Fidelity-aware GA", "Qiskit SABRE"]
    colors = ["#94A3B8", "#D97706", "#8B5CF6", "#2563EB"]

    fig, (ax_gap, ax_swaps) = plt.subplots(1, 2, figsize=(11.0, 5.0), constrained_layout=True)
    x = np.arange(len(order))
    width = 0.19
    offsets = np.linspace(-1.5 * width, 1.5 * width, len(solvers))

    for offset, solver, label, color in zip(offsets, solvers, labels, colors):
        sdf = data[data["solver"] == solver].set_index("case").reindex(order)
        bars_gap = ax_gap.bar(x + offset, sdf["gap_percent"], width, label=label, color=color, alpha=0.92, edgecolor="white", linewidth=0.6)
        bars_sw = ax_swaps.bar(x + offset, sdf["swap_count"], width, label=label, color=color, alpha=0.92, edgecolor="white", linewidth=0.6)

        # Labels on top of bars
        for b, val in zip(bars_gap, sdf["gap_percent"]):
            if not np.isnan(val) and val > 0.05:
                ax_gap.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.9, f"{val:.1f}%", ha="center", va="bottom", fontsize=7, rotation=90)
            elif not np.isnan(val) and abs(val) <= 0.05:
                ax_gap.text(b.get_x() + b.get_width() / 2, 0.6, "0%", ha="center", va="bottom", fontsize=7.5, fontweight="bold")

        for b, val in zip(bars_sw, sdf["swap_count"]):
            if not np.isnan(val):
                ax_swaps.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6, f"{int(val)}", ha="center", va="bottom", fontsize=7, rotation=90)

    # Reference exact swaps as horizontal red dashed lines
    for i, c in enumerate(order):
        if c in exact_swaps:
            val = exact_swaps[c]
            ax_swaps.hlines(val, i - 2 * width, i + 2 * width, colors="#EF4444", linestyles="--", linewidth=1.5, zorder=4)

    # Category dividers and background tint
    for ax in (ax_gap, ax_swaps):
        ax.set_xticks(x)
        ax.set_xticklabels([display_cases.get(c, c) for c in order], fontsize=8.5)
        ax.grid(True, axis="y", alpha=0.25, linestyle="-")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.axvline(0.5, color="#CBD5E1", linestyle=":", linewidth=1.2)
        ax.axvline(3.5, color="#CBD5E1", linestyle=":", linewidth=1.2)

    # Annotations explaining regimes (placed safely above bars at y=70)
    ax_gap.text(0, 71, "Structured\n(Zero-SWAP)", ha="center", fontsize=8, fontweight="bold", color="#475569")
    ax_gap.text(2.0, 71, "Random Deep Circuits\n(Fidelity selection wins)", ha="center", fontsize=8, fontweight="bold", color="#475569")
    ax_gap.text(4.5, 71, "Adversarial Dense\n(Gate count dominates)", ha="center", fontsize=8, fontweight="bold", color="#475569")

    ax_gap.set_ylabel("Fidelity Gap to Exact DP (%)", fontweight="bold")
    ax_gap.set_title("(a) Solution Quality Gap (Lower is Better)", loc="left", fontweight="bold")
    ax_gap.set_ylim(0, 80)
    ax_gap.legend(frameon=True, facecolor="white", edgecolor="#CBD5E1", fontsize=8, loc="upper right", ncol=2)

    ax_swaps.set_ylabel("Inserted SWAP Count", fontweight="bold")
    ax_swaps.set_title("(b) Movement Overhead (Red dashed = Exact DP)", loc="left", fontweight="bold")
    ax_swaps.set_ylim(0, 75)

    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return True


#: Thin connector from an annotation box to its marker (publication overview).
LEADER_LINE = dict(arrowstyle="-", color="#64748B", lw=0.9, shrinkA=0, shrinkB=5)


def _pad_y(ax, values) -> None:
    """Room below/above the extreme markers so their labels stay inside."""
    lo, hi = float(values.min()), float(values.max())
    ax.set_ylim(lo - 0.15 * (hi - lo), hi + 0.06 * (hi - lo))


def plot_publication_overview(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str], out_path: Path
) -> None:
    """Create one cohesive, publication-grade four-panel overview for the article."""
    preferred = [
        "exact_dp", "tabu_fidelity", "genetic_fidelity", "qiskit_sabre",
        "qiskit_preset", "greedy_shortest_path",
    ]
    solvers = [solver for solver in preferred if solver in set(df["solver"])]
    names = ["Exact DP", "Tabu Fidelity", "Fidelity-aware GA", "Qiskit SABRE", "Qiskit Preset", "Greedy Baseline"]
    display = dict(zip(preferred, names))

    palette = {
        "exact_dp": "#1E293B",
        "tabu_fidelity": "#D97706",
        "genetic_fidelity": "#8B5CF6",
        "qiskit_sabre": "#2563EB",
        "qiskit_preset": "#64748B",
        "greedy_shortest_path": "#0D9488",
    }

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5), constrained_layout=True)
    ax_mean, ax_heat, ax_runtime, ax_cz = axes.ravel()

    # --- Panel A: Mean Cancelled Fidelity Cost ---
    means = df[df["solver"].isin(solvers)].groupby("solver")["fidelity_cost"].mean()
    order = means.sort_values(ascending=False).index.tolist()  # best at top in barh
    exact_cost = float(means.get("exact_dp", 1.5953))

    y_pos = np.arange(len(order))
    bar_colors = [palette[s] for s in order]
    ax_mean.barh(y_pos, [means[s] for s in order], color=bar_colors, alpha=0.92, height=0.62, edgecolor="white", linewidth=0.8)
    ax_mean.set_yticks(y_pos)
    ax_mean.set_yticklabels([display[s] for s in order], fontsize=9.5, fontweight="medium")

    # Annotate bar values and gap %
    for idx, s in enumerate(order):
        val = means[s]
        if s == "exact_dp":
            label = f"{val:.4f}  (Optimum)"
        else:
            gap_pct = 100 * (val - exact_cost) / exact_cost
            label = f"{val:.4f}  (+{gap_pct:.1f}%)"
        ax_mean.text(val + 0.03, idx, label, va="center", fontsize=8.5, fontweight="bold" if s in ("tabu_fidelity", "genetic_fidelity") else "normal")

    ax_mean.axvline(exact_cost, color="#EF4444", linestyle="--", linewidth=1.5, alpha=0.85, label=f"Exact DP reference ({exact_cost:.4f})")
    ax_mean.set_title("(a) Mean Cancelled Fidelity Cost (13 Cases)", loc="left", fontweight="bold")
    ax_mean.set_xlabel("Fidelity Cost (Lower is Better)", fontweight="bold")
    ax_mean.set_xlim(0, 2.85)
    ax_mean.grid(True, axis="x", alpha=0.25)
    # Put reference text in top subtitle/legend
    ax_mean.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#CBD5E1", fontsize=8.0)

    # --- Panel B: Case-level Gap Heatmap ---
    heat_solvers = [s for s in ["tabu_fidelity", "genetic_fidelity", "qiskit_sabre", "qiskit_preset"] if s in solvers]
    cases = case_order(ideal)
    matrix = []
    for solver in heat_solvers:
        values = df[df["solver"] == solver].set_index("case")["fidelity_cost"]
        matrix.append([float(values[c] - ideal[c]) for c in cases])
    matrix = np.array(matrix)

    norm = TwoSlopeNorm(vmin=-0.05, vcenter=0.0, vmax=max(float(matrix.max()), 0.5))
    im = ax_heat.imshow(matrix, aspect="auto", cmap="YlOrRd", norm=norm)
    ax_heat.set_title("(b) Case-Level Gap to Exact DP Reference", loc="left", fontweight="bold")
    ax_heat.set_yticks(np.arange(len(heat_solvers)))
    ax_heat.set_yticklabels([display[s] for s in heat_solvers], fontsize=9)
    ax_heat.set_xticks(np.arange(len(cases)))
    clean_cases = [c.replace("_", " ") for c in cases]
    ax_heat.set_xticklabels(clean_cases, fontsize=8, rotation=45, ha="right")

    for i in range(len(heat_solvers)):
        for j in range(len(cases)):
            val = matrix[i, j]
            txt = "0" if abs(val) <= TOL else f"{val:.2f}"
            text_color = "white" if val > 0.8 else "black"
            ax_heat.text(j, i, txt, ha="center", va="center", fontsize=7.5, color=text_color, fontweight="bold" if val > 0.5 else "normal")

    cbar = fig.colorbar(im, ax=ax_heat, fraction=0.035, pad=0.02)
    cbar.set_label("Fidelity Cost Gap", fontsize=8.5)

    # --- Panel C: Quality vs Runtime Trade-off ---
    stats = df[df["solver"].isin(solvers)].groupby("solver").agg(
        cost=("fidelity_cost", "mean"), runtime=("seconds", "median")
    ).reset_index()

    for _, row in stats.iterrows():
        solver = row["solver"]
        color = palette[solver]
        marker = "X" if solver == "exact_dp" else "o"
        size = 85 if solver == "exact_dp" else 70
        ax_runtime.scatter(row["runtime"], row["cost"], s=size, color=color, marker=marker,
                           edgecolor="white", linewidth=1.0, zorder=4)

    ann_offsets = {
        "qiskit_sabre": (28, 22),
        "exact_dp": (0, -30),
        "qiskit_preset": (30, 32),
        "tabu_fidelity": (0, 40),
        "genetic_fidelity": (-30, -26),
        "greedy_shortest_path": (30, -16),
    }
    for _, row in stats.iterrows():
        solver = row["solver"]
        dx, dy = ann_offsets.get(solver, (8, 4))
        ax_runtime.annotate(
            display[solver],
            (row["runtime"], row["cost"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8.5,
            fontweight="bold" if solver in ("tabu_fidelity", "genetic_fidelity", "qiskit_sabre") else "normal",
            ha="center" if dx == 0 else ("right" if dx < 0 else "left"),
            va="center",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#CBD5E1", alpha=0.9),
            arrowprops=LEADER_LINE,
            zorder=5,
        )

    ax_runtime.set_xscale("log")
    _pad_y(ax_runtime, stats["cost"])
    ax_runtime.set_title("(c) Solution Quality vs. Solve Time", loc="left", fontweight="bold")
    ax_runtime.set_xlabel("Median Solve Time (s, logarithmic scale)", fontweight="bold")
    ax_runtime.set_ylabel("Mean Cancelled Fidelity Cost", fontweight="bold")
    ax_runtime.grid(True, which="both", alpha=0.25)

    # --- Panel D: Physical 2Q (CZ) Gate Count vs Fidelity Cost ---
    cz_data = df[df["solver"].isin(solvers)].groupby("solver").agg(
        # cz_cost_cancelled counts a SWAP as 3 CZ, so routed solutions and the
        # (already CZ-decomposed) Qiskit outputs are on the same scale;
        # two_qubit_count_cancelled counted a SWAP as one gate.
        cz=("cz_cost_cancelled", "mean"), cost=("fidelity_cost", "mean")
    ).reset_index()

    for _, row in cz_data.iterrows():
        solver = row["solver"]
        color = palette[solver]
        marker = "X" if solver == "exact_dp" else "o"
        size = 85 if solver == "exact_dp" else 70
        ax_cz.scatter(row["cz"], row["cost"], s=size, color=color, marker=marker,
                      edgecolor="white", linewidth=1.0, zorder=4)

    cz_offsets = {
        "exact_dp": (-26, -18),
        "tabu_fidelity": (34, -6),
        "genetic_fidelity": (40, -14),
        "qiskit_sabre": (34, 18),
        "qiskit_preset": (0, 36),
        "greedy_shortest_path": (-34, -22),
    }
    for _, row in cz_data.iterrows():
        solver = row["solver"]
        dx, dy = cz_offsets.get(solver, (8, 4))
        ax_cz.annotate(
            display[solver],
            (row["cz"], row["cost"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8.5,
            ha="center" if dx == 0 else ("right" if dx < 0 else "left"),
            va="center",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#CBD5E1", alpha=0.9),
            arrowprops=LEADER_LINE,
            zorder=5,
        )

    ax_cz.set_title("(d) Physical 2Q (CZ) Gates vs. Fidelity Cost", loc="left", fontweight="bold")
    ax_cz.set_xlabel("Mean Physical CZ Count (SWAP = 3 CZ)", fontweight="bold")
    ax_cz.set_ylabel("Mean Cancelled Fidelity Cost", fontweight="bold")
    lo, hi = float(cz_data["cz"].min()), float(cz_data["cz"].max())
    ax_cz.set_xlim(lo - 0.3 * (hi - lo), hi + 0.08 * (hi - lo))
    _pad_y(ax_cz, cz_data["cost"])
    ax_cz.grid(True, alpha=0.25)

    for ax in axes.ravel():
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_crossover(csv_path: Path, out_path: Path) -> bool:
    """Opcjonalny wykres skalowania: czas i gap vs liczba interakcji."""
    if not csv_path.exists():
        print("results/crossover.csv not found; skipping crossover plot.")
        return False
    df = pd.read_csv(csv_path)
    needed = {
        "interactions", "exact_dp_seconds", "tabu_seconds", "tabu_gap",
        "exact_dp_hit_budget",
    }
    if df.empty or not needed.issubset(df.columns):
        print("results/crossover.csv bez wymaganych kolumn, pomijam wykres crossover.")
        return False
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(needed))
    if df.empty:
        print("results/crossover.csv pusty po odfiltrowaniu, pomijam wykres crossover.")
        return False

    fig, (ax_time, ax_gap) = plt.subplots(1, 2, figsize=(13, 5.2))

    hit = df[df["exact_dp_hit_budget"] > 0]
    ok = df[df["exact_dp_hit_budget"] == 0]
    ax_time.scatter(df["interactions"], df["exact_dp_seconds"], s=45,
                    color="#C44E52", label="Exact DP reference", zorder=3)
    ax_time.scatter(df["interactions"], df["tabu_seconds"], s=45,
                    color="#4C72B0", label="tabu fidelity", zorder=3)
    if not hit.empty:
        ax_time.scatter(hit["interactions"], hit["exact_dp_seconds"], s=90, marker="o",
                        facecolors="none", edgecolors="#C44E52", linewidth=1.2,
                        label="exact_dp przy budżecie (fallback)", zorder=4)
    ax_time.set_xscale("log")
    ax_time.set_yscale("log")
    ax_time.set_xlabel("liczba interakcji 2Q")
    ax_time.set_ylabel("Solve time (s, logarithmic scale)")
    ax_time.set_title("Runtime versus instance size")
    ax_time.grid(True, which="both", alpha=0.25)
    ax_time.legend(fontsize=8)

    if ok.empty:
        ax_gap.text(0.5, 0.5, "No rows without exact-DP fallback",
                    ha="center", va="center", transform=ax_gap.transAxes, fontsize=10)
    else:
        ax_gap.scatter(ok["interactions"], ok["tabu_gap"], s=45, color="#4C72B0", zorder=3)
        ax_gap.axhline(0, color="black", linewidth=1.0, linestyle=":")
    ax_gap.set_xscale("log")
    ax_gap.set_xlabel("Number of two-qubit interactions")
    ax_gap.set_ylabel("Tabu gap versus exact DP (fidelity cost)")
    ax_gap.set_title("Quality gap versus instance size")
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
    """Write the exact-DP reference and solver gaps in Markdown."""
    total_cases = int(df["case"].nunique())
    n_variants = sum(len(members) for _, members in FAMILIES if not df[df["solver"] == members[0]].empty)
    ref = df[df["solver"].isin(REFERENCES)]
    lines = [
        "# Fidelity benchmark results",
        "",
        "The exact-DP solver is the reference: it exhaustively searches layouts,",
        "legal SWAPs, and topological execution orders for each case. `gap` is",
        "the solver's fidelity cost minus the reference cost: 0 reaches the",
        "reference, while a positive value indicates a larger cost.",
        "",
        f"- Benchmark cases: {total_cases}",
        f"- Solver representatives: {len(stats)} (from {n_variants} variants)",
        "- Metric: `fidelity_cost_cancelled` (true minimum), when available",
        "",
        "## Exact-DP reference",
        "",
        "| Reference | Mean fidelity cost | Median runtime (s) | Mean runtime (s) |",
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
        "## Solver representatives",
        "",
        "| Solver | Mean fidelity cost | Mean gap vs reference | Gap std. | "
        "Median runtime (s) | Mean runtime (s) | Mean evaluations | At reference |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, row in stats.iterrows():
        evals = "-" if np.isnan(row["mean_evals"]) else f"{row['mean_evals']:.0f}"
        lines.append(
            f"| {row['name']} | {row['mean_cost']:.4f} | {row['mean_gap']:+.4f} | "
            f"{row['std_gap']:.4f} | {row['median_seconds']:.4f} | "
            f"{row['mean_seconds']:.3f} | {evals} | "
            f"{int(row['n_opt'])}/{int(row['n_cases'])} |"
        )
    lines.append("")
    lines.append(
        "`At reference` counts cases with |gap| <= 1e-9."
    )
    lines.append("")

    lines += [
        "## Collapsed variants",
        "",
        "Variants in the same family share the algorithm and differ only in their",
        "initialization, so plots use one representative. The table reports how",
        f"much each collapsed variant differs from its representative (tolerance {TOL:g}).",
        "",
        "| Representative | Collapsed variant | Cases differing | Max |delta| | Mean |delta| |",
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
                f"fidelity-cost vectors on all cases."
            )
    else:
        lines.append(
            "- Additional merges: none (no pair has identical fidelity-cost vectors)."
        )
    lines.append("")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Summary written: {out_file}")


def cleanup_plots(out_dir: Path, keep: set[str]) -> list[str]:
    """Usuwa z plots/ pliki PNG spoza bieżącego zestawu wykresów."""
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
        raise SystemExit("No exact-DP reference rows found in the CSV.")

    reps, collapse_report = collapse_families(df)
    reps, identical_merges = merge_identical_reps(df, ideal, reps)
    stats = representative_stats(df, ideal, reps)

    print("\nSolver-family representatives:")
    for rep, members in FAMILIES:
        if rep not in reps:
            continue
        scaled = [m for m in members if m != rep]
        suffix = f" <- {', '.join(scaled)}" if scaled else ""
        print(f"  {rep}{suffix}")
    print("\nDifferences between collapsed variants (gap, tolerance 1e-9):")
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
        print("  additional merges: none")
    print("")

    out = PLOTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    print("Generating plots...")
    written: list[str] = []
    plot_gap_to_ideal(stats, out / "gap_to_ideal.png", best_solver(stats))
    written.append("gap_to_ideal.png")
    ideal_stats = {
        "median_seconds": float(df[df["solver"] == REFERENCES[0]]["seconds"].median())
    }
    plot_quality_vs_time(stats, ideal_stats, out / "quality_vs_time_tradeoff.png")
    written.append("quality_vs_time_tradeoff.png")
    _, matrix = gap_matrix(df, ideal, stats["solver"].tolist())
    plot_gap_heatmap(matrix, out / "gap_heatmap.png")
    written.append("gap_heatmap.png")
    if plot_case_detail(df, ideal, reps, stats, out / "case_detail.png"):
        written.append("case_detail.png")
    plot_fidelity_vs_swaps(df, reps, out / "fidelity_vs_swaps.png")
    written.append("fidelity_vs_swaps.png")
    plot_solver_wins(df, ideal, reps, out / "solver_wins.png")
    written.append("solver_wins.png")
    plot_cost_distribution(df, reps, out / "cost_distribution.png")
    written.append("cost_distribution.png")
    plot_theoretical_scaling(out / "theoretical_scaling.png")
    written.append("theoretical_scaling.png")
    if plot_deep_benchmark(LONG_CSV, out / "deep_benchmark.png"):
        written.append("deep_benchmark.png")
    plot_publication_overview(df, ideal, reps, out / "publication_overview.png")
    written.append("publication_overview.png")
    if plot_crossover(CROSSOVER_CSV, out / "crossover.png"):
        written.append("crossover.png")

    removed = cleanup_plots(out, set(written))
    if removed:
        print(f"Removed stale plots: {', '.join(removed)}")

    print("Generating summary...")
    generate_summary(df, ideal, stats, collapse_report, identical_merges)

    print("\nWritten files:")
    for name in written:
        print(f"  {PLOTS_DIR / name}")
    print(f"  {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
