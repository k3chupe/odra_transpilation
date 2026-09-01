#!/usr/bin/env python3
"""
Wizualizacja wyników benchmarku fidelity.

Referencje (brute force, exact DP) to "ideał": liczone raz na przypadek,
deterministycznie, i pokazywane jako linia optimum. Porównywane solvery
(tabu, genetyka, sabre z Qiskita, greedy) są rysowane jako odległość od
tego ideału, a nie jako równorzędni konkurenci.

Skrypt tylko czyta results/benchmark-fidelity.csv (wyniki nie są tu liczone).
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

plt.rcParams["figure.figsize"] = (12, 7)
plt.rcParams["font.size"] = 10

# Ideał = exact_dp: pełne przeszukanie (layouty + swapy + dowolny porządek
# topologiczny, dokładny koszt fidelity). Żaden solver nie może go pobić.
REFERENCES = ("exact_dp",)

# Solvery porównywane: nasze + sabre/genetyka + słabsze referencje greedy.
COMPARED = (
    "tabu_fidelity",
    "tabu_fidelity_greedy",
    "tabu_fidelity_sabre",
    "tabu_search",
    "tabu_sabre_start",
    "genetic_trivial",
    "qiskit_sabre",
    "qiskit_preset",
    "greedy_shortest_path",
    "brute_force_layout",
    "brute_fidelity_layout",
)

DISPLAY = {
    "exact_dp": "optymalny routing (exact DP)",
    "tabu_fidelity": "tabu fidelity",
    "tabu_fidelity_greedy": "tabu fidelity (greedy)",
    "tabu_fidelity_sabre": "tabu fidelity (sabre)",
    "tabu_search": "tabu search",
    "tabu_sabre_start": "tabu + sabre (nasz)",
    "genetic_trivial": "genetyka",
    "qiskit_sabre": "sabre (Qiskit)",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "greedy (identity)",
    "brute_force_layout": "brute layout (greedy swapy)",
    "brute_fidelity_layout": "brute fidelity (greedy swapy)",
}


def _name(solver: str) -> str:
    return DISPLAY.get(solver, solver)


def load_data(results_dir: str = "results"):
    results_path = Path(results_dir)
    df = pd.read_csv(results_path / "benchmark-fidelity.csv")
    df = df[df["error"].isna() | (df["error"] == "")].copy()
    df = df[df["fidelity_cost"] >= 0]
    return df


def _ideal_per_case(df: pd.DataFrame) -> pd.Series:
    """Ideał per przypadek = min fidelity_cost po referencjach."""
    refs = df[df["solver"].isin(REFERENCES)]
    return refs.groupby("case")["fidelity_cost"].min()


def plot_case_by_case(df: pd.DataFrame, ideal: pd.Series, output_path: Path):
    """Każdy przypadek: słupki solverów + linia ideału (czerwona, przerywana)."""
    cases = sorted(df["case"].unique())
    n = len(cases)
    fig, axes = plt.subplots(n, 1, figsize=(14, 3.2 * n), sharex=False)
    if n == 1:
        axes = [axes]

    for ax, case in zip(axes, cases):
        case_data = df[df["case"] == case]
        case_data = case_data[case_data["solver"].isin(COMPARED)].sort_values("fidelity_cost")
        solvers = [_name(s) for s in case_data["solver"]]
        costs = case_data["fidelity_cost"].values
        colors = ["#4C72B0" if c <= ideal[case] + 1e-9 else "#C44E52" for c in costs]
        ax.bar(range(len(solvers)), costs, color=colors, alpha=0.85)
        ax.axhline(ideal[case], color="red", linestyle="--", linewidth=1.6, label="ideał (min referencji)")
        ax.set_xticks(range(len(solvers)))
        ax.set_xticklabels(solvers, rotation=40, ha="right")
        ax.set_ylabel("fidelity_cost (niżej lepiej)")
        ax.set_title(f"{case}: ideał {ideal[case]:.4f}", fontsize=10)
        ax.grid(True, axis="y", alpha=0.3)
        for i, c in enumerate(costs):
            ax.text(i, c, f"{c:.3f}", ha="center", va="bottom", fontsize=7)
        ax.legend(loc="upper right", fontsize=8)

    plt.suptitle("Solver vs optimum per przypadek (niebieski = osiąga optimum)", fontsize=12, y=1.002)
    plt.tight_layout()
    plt.savefig(output_path / "ideal_vs_solvers.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_gap_to_ideal(df: pd.DataFrame, ideal: pd.Series, output_path: Path):
    """Średnia odległość od ideału per solver; 0 = ideał, ujemne = lepszy od referencji."""
    rows = []
    for solver in COMPARED:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        gaps = sdf.apply(lambda r: r["fidelity_cost"] - ideal.get(r["case"], np.nan), axis=1)
        rows.append({"solver": _name(solver), "gap": gaps.mean(), "std": gaps.std()})
    gdf = pd.DataFrame(rows).sort_values("gap")

    plt.figure(figsize=(13, 6))
    colors = ["#2ca02c" if g <= 0 else "#C44E52" for g in gdf["gap"]]
    bars = plt.bar(range(len(gdf)), gdf["gap"], color=colors, alpha=0.85)
    plt.axhline(0, color="black", linewidth=1.2)
    plt.xticks(range(len(gdf)), gdf["solver"], rotation=40, ha="right")
    plt.ylabel("Średnia odległość od ideału (fidelity_cost)")
    plt.title("Jak daleko od ideału jest każdy solver (0 = ideał, ujemne = lepszy od referencji)")
    for i, (bar, g) in enumerate(zip(bars, gdf["gap"])):
        plt.text(bar.get_x() + bar.get_width() / 2, g, f"{g:+.3f}", ha="center", va="bottom" if g >= 0 else "top", fontsize=9)
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path / "gap_to_ideal.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_wins(df: pd.DataFrame, output_path: Path):
    """Wygrane per solver tylko wśród porównywanych (remisy liczą się każdemu)."""
    wins: dict[str, int] = {}
    for case, case_data in df.groupby("case"):
        comp = case_data[case_data["solver"].isin(COMPARED)]
        if comp.empty:
            continue
        best = comp["fidelity_cost"].min()
        for solver in comp[comp["fidelity_cost"] <= best + 1e-9]["solver"]:
            wins[solver] = wins.get(solver, 0) + 1
    items = sorted(wins.items(), key=lambda kv: -kv[1])
    names = [_name(s) for s, _ in items]
    counts = [c for _, c in items]

    plt.figure(figsize=(12, 6))
    bars = plt.bar(range(len(names)), counts, color="skyblue")
    plt.xticks(range(len(names)), names, rotation=40, ha="right")
    plt.ylabel("Przypadki z najlepszym wynikiem")
    plt.title("Liczba przypadków, w których solver osiągnął najlepszy fidelity_cost (porównywane solvery)")
    for bar, c in zip(bars, counts):
        plt.text(bar.get_x() + bar.get_width() / 2, c, str(int(c)), ha="center", va="bottom")
    plt.tight_layout()
    plt.savefig(output_path / "wins_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_time(df: pd.DataFrame, output_path: Path):
    """Średni czas per porównywany solver."""
    rows = []
    for solver in COMPARED:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        rows.append({"solver": _name(solver), "seconds": sdf["seconds"].mean()})
    tdf = pd.DataFrame(rows).sort_values("seconds")

    plt.figure(figsize=(12, 6))
    bars = plt.bar(range(len(tdf)), tdf["seconds"], color="lightcoral")
    plt.xticks(range(len(tdf)), tdf["solver"], rotation=40, ha="right")
    plt.ylabel("Średni czas (s)")
    plt.title("Średni czas wykonania (porównywane solvery)")
    for i, (bar, v) in enumerate(zip(bars, tdf["seconds"])):
        plt.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.2f}s", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path / "time_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_tradeoff(df: pd.DataFrame, ideal: pd.Series, output_path: Path):
    """Jakość vs czas: porównywane solvery + punkty referencji (krzyżyki)."""
    fig, ax = plt.subplots(figsize=(12, 8))
    for solver in COMPARED:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        ax.scatter(sdf["seconds"].mean(), sdf["fidelity_cost"].mean(), s=110, label=_name(solver))
        ax.annotate(_name(solver), (sdf["seconds"].mean(), sdf["fidelity_cost"].mean()),
                    xytext=(6, 6), textcoords="offset points", fontsize=8)
    for solver in REFERENCES:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        ax.scatter(sdf["seconds"].mean(), sdf["fidelity_cost"].mean(), marker="x", s=140,
                   color="red", label=f"{_name(solver)} (referencja)")
    ax.axhline(ideal.mean(), color="red", linestyle="--", linewidth=1, alpha=0.6,
               label=f"średni ideał {ideal.mean():.3f}")
    ax.set_xlabel("Średni czas (s)")
    ax.set_ylabel("Średni fidelity_cost (niżej lepiej)")
    ax.set_title("Trade-off: jakość vs czas (czerwona linia = średni ideał)")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path / "quality_vs_time_tradeoff.png", dpi=300, bbox_inches="tight")
    plt.close()


def plot_evals(df: pd.DataFrame, output_path: Path):
    """Średnia liczba ewaluacji layoutów per porównywany solver."""
    rows = []
    for solver in COMPARED:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        ev = sdf[sdf["evals"] >= 0]["evals"]
        rows.append({"solver": _name(solver), "evals": ev.mean() if len(ev) else 0})
    edf = pd.DataFrame(rows).sort_values("evals")

    plt.figure(figsize=(12, 6))
    bars = plt.bar(range(len(edf)), edf["evals"], color="lightgreen")
    plt.xticks(range(len(edf)), edf["solver"], rotation=40, ha="right")
    plt.ylabel("Średnia liczba ewaluacji")
    plt.title("Średnia liczba ewaluacji layoutów (porównywane solvery)")
    for i, (bar, v) in enumerate(zip(bars, edf["evals"])):
        plt.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path / "evaluations_comparison.png", dpi=300, bbox_inches="tight")
    plt.close()


def generate_summary_stats(df: pd.DataFrame, ideal: pd.Series, output_file: str = "results_summary.md"):
    """Podsumowanie: referencje osobno, solvery jako odległość od ideału."""
    lines = [
        "# Podsumowanie wyników benchmarków (fidelity)",
        "",
        "Ideał = exact_dp: pełne przeszukanie przestrzeni (layouty, dowolne",
        "SWAP-y na krawędziach, dowolny porządek topologiczny, dokładny koszt",
        "fidelity), liczone raz na przypadek. Żaden solver nie może go pobić,",
        "może się tylko z nim zrównać. `gap` = fidelity_cost solwera minus",
        "ideał przypadku: 0 = osiąga optimum, dodatnia = odległość od optimum.",
        "",
    ]

    total_cases = df["case"].nunique()
    lines += [f"- Przypadki testowe: {total_cases}", ""]

    # Referencje
    lines.append("## Ideał (exact DP, dolne ograniczenie)")
    lines.append("")
    lines.append("| Referencja | Średni fidelity_cost | Średni czas (s) |")
    lines.append("|---|---|---|")
    for solver in REFERENCES:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        lines.append(f"| {_name(solver)} | {sdf['fidelity_cost'].mean():.4f} | {sdf['seconds'].mean():.4f} |")
    lines.append("")

    # Porównywane solvery
    lines.append("## Porównywane solvery (odległość od ideału)")
    lines.append("")
    lines.append("| Solver | Śr. fidelity_cost | Śr. gap vs ideał | std gap | Śr. czas (s) | Śr. evals |")
    lines.append("|---|---|---|---|---|---|")
    for solver in COMPARED:
        sdf = df[df["solver"] == solver]
        if sdf.empty:
            continue
        gaps = sdf.apply(lambda r: r["fidelity_cost"] - ideal.get(r["case"], np.nan), axis=1)
        ev = sdf[sdf["evals"] >= 0]["evals"]
        lines.append(
            f"| {_name(solver)} | {sdf['fidelity_cost'].mean():.4f} | {gaps.mean():+.4f} | "
            f"{gaps.std():.4f} | {sdf['seconds'].mean():.3f} | {ev.mean() if len(ev) else -1:.0f} |"
        )
    lines.append("")

    # Wygrane wśród porównywanych
    lines.append("## Przypadki z najlepszym wynikiem (tylko porównywane solvery)")
    lines.append("")
    wins: dict[str, int] = {}
    for case, case_data in df.groupby("case"):
        comp = case_data[case_data["solver"].isin(COMPARED)]
        if comp.empty:
            continue
        best = comp["fidelity_cost"].min()
        for solver in comp[comp["fidelity_cost"] <= best + 1e-9]["solver"]:
            wins[solver] = wins.get(solver, 0) + 1
    for solver, count in sorted(wins.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {_name(solver)}: {count}/{total_cases}")
    lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Podsumowanie zapisane: {output_file}")


def main():
    print("Ładowanie danych...")
    df = load_data()
    ideal = _ideal_per_case(df)

    print("Generowanie wykresów...")
    out = Path("plots")
    out.mkdir(exist_ok=True)
    plot_case_by_case(df, ideal, out)
    plot_gap_to_ideal(df, ideal, out)
    plot_wins(df, out)
    plot_time(df, out)
    plot_tradeoff(df, ideal, out)
    plot_evals(df, out)

    print("Generowanie podsumowania...")
    generate_summary_stats(df, ideal)

    print("Gotowe.")


if __name__ == "__main__":
    main()
