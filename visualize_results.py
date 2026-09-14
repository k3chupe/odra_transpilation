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

Wyjście: plots/*.png (4 wykresy plus opcjonalny crossover) i results_summary.md.
"""

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
PLOTS_DIR = Path("plots")
FIDELITY_CSV = RESULTS_DIR / "benchmark-fidelity.csv"
CROSSOVER_CSV = RESULTS_DIR / "crossover.csv"
SUMMARY_PATH = Path("results_summary.md")

# Tolerancja równości kosztów (te same przypadki uznajemy za identyczne).
TOL = 1e-9

plt.rcParams["font.size"] = 10
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["axes.labelsize"] = 10
plt.rcParams["figure.dpi"] = 100

# Ideał = exact_dp: pełne przeszukanie (layouty, SWAP-y na krawędziach,
# dowolny porządek topologiczny, dokładny koszt fidelity). Nie do pobicia
# w naszym modelu routingu; solver może się z nim zrównać.
REFERENCES = ("exact_dp",)

# Rodziny solverów: reprezentant -> warianty, które reprezentuje.
# Kolejność w krotce ma znaczenie: pierwszy element to reprezentant.
FAMILIES = (
    ("tabu_fidelity", ("tabu_fidelity", "tabu_fidelity_greedy", "tabu_fidelity_sabre")),
    ("tabu_search", ("tabu_search", "tabu_sabre_start")),
    ("genetic_trivial", ("genetic_trivial",)),
    ("qiskit_sabre", ("qiskit_sabre",)),
    ("qiskit_preset", ("qiskit_preset",)),
    ("greedy_shortest_path", ("greedy_shortest_path",)),
    ("brute_force_layout", ("brute_force_layout",)),
    ("brute_fidelity_layout", ("brute_fidelity_layout",)),
)

# Pełne nazwy (legenda, osie) i krótkie nazwy (kolumny macierzy, panele).
DISPLAY = {
    "exact_dp": "ideał (exact DP)",
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

SHORT = {
    "exact_dp": "ideał (exact DP)",
    "tabu_fidelity": "tabu fidelity",
    "tabu_search": "tabu search",
    "genetic_trivial": "genetyka",
    "qiskit_sabre": "sabre (Qiskit)",
    "qiskit_preset": "Qiskit preset",
    "greedy_shortest_path": "greedy",
    "brute_force_layout": "brute layout",
    "brute_fidelity_layout": "brute fidelity",
}

# Etykiety łamane na dwie linie: mieszczą się bez obracania, nic się nie zlewa.
STACKED = {
    "exact_dp": "ideał\n(exact DP)",
    "tabu_fidelity": "tabu\nfidelity",
    "tabu_search": "tabu\nsearch",
    "genetic_trivial": "genetyka",
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


def gap_matrix(
    df: pd.DataFrame, ideal: pd.Series, reps: list[str]
) -> tuple[list[str], pd.DataFrame]:
    """Macierz gapów: wiersze = przypadki (rosnący ideał), kolumny = reprezentanci."""
    cases = case_order(ideal)
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


def plot_gap_to_ideal(stats: pd.DataFrame, out_path: Path) -> None:
    """Poziome słupki: średni gap do ideału, posortowane, z liczbą trafień w optimum."""
    s = stats.sort_values("mean_gap").reset_index(drop=True)
    total = int(s["n_cases"].max())
    fig, ax = plt.subplots(figsize=(11.5, 0.55 * len(s) + 2.4))
    y = np.arange(len(s))
    gaps = s["mean_gap"].to_numpy()
    colors = ["#2ca02c" if g <= TOL else "#C44E52" for g in gaps]
    ax.barh(y, gaps, color=colors, alpha=0.9, height=0.62)
    ax.axvline(0, color="black", linewidth=1.2)

    lo, hi = min(float(gaps.min()), 0.0), max(float(gaps.max()), 0.0)
    span = max(hi - lo, 1e-6)
    for yi, g, n_opt in zip(y, gaps, s["n_opt"]):
        off = 0.02 * span
        ax.text(
            g + off if g >= 0 else g - off,
            yi,
            f"{g:+.4f}   ({int(n_opt)}/{total} na optimum)",
            va="center",
            ha="left" if g >= 0 else "right",
            fontsize=9,
        )
    ax.set_yticks(y)
    ax.set_yticklabels(s["name"])
    ax.invert_yaxis()
    ax.set_xlim(lo - 0.06 * span, hi + 0.62 * span)
    ax.set_xlabel("średnia różnica fidelity_cost względem ideału (0 = optimum, niżej lepiej)")
    ax.set_title("Jak daleko od ideału (exact DP) jest reprezentant")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_quality_vs_time(stats: pd.DataFrame, ideal_stats: dict, out_path: Path) -> None:
    """Rozrzut: średni gap (y) vs mediana czasu (x, skala log), plus punkt ideału."""
    fig, ax = plt.subplots(figsize=(12, 7.5))
    s = stats.sort_values("median_seconds").reset_index(drop=True)

    ax.scatter(
        s["median_seconds"],
        s["mean_gap"],
        s=150,
        color="#4C72B0",
        edgecolor="black",
        linewidth=0.6,
        zorder=3,
        label="reprezentanci solverów",
    )
    ax.axhline(0, color="black", linewidth=1.0, linestyle=":", zorder=1)
    ax.scatter(
        [ideal_stats["median_seconds"]],
        [0.0],
        s=200,
        marker="X",
        color="#C44E52",
        edgecolor="black",
        linewidth=0.6,
        zorder=4,
        label="ideał (exact DP)",
    )
    ax.set_xscale("log")
    ax.set_xlabel("mediana czasu solve (s, skala log)")
    ax.set_ylabel("średni gap do ideału (fidelity_cost, niżej lepiej)")
    ax.set_title("Jakość vs czas: reprezentanci na tle ideału")
    # Zapas miejsca nad punktami na etykiety i pod zerem, żeby oś nie ucinała opisu.
    y_lo = min(0.0, float(s["mean_gap"].min()))
    y_hi = max(0.0, float(s["mean_gap"].max()))
    margin = max(y_hi - y_lo, 1e-6)
    ax.set_ylim(y_lo - 0.35 * margin, y_hi + 0.45 * margin)
    _place_labels(
        fig,
        ax,
        s["median_seconds"].tolist(),
        s["mean_gap"].tolist(),
        s["name"].tolist(),
    )
    ax.annotate(
        "ideał (exact DP)",
        (ideal_stats["median_seconds"], 0.0),
        xytext=(10, -16),
        textcoords="offset points",
        fontsize=9,
        color="#C44E52",
    )
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_gap_heatmap(matrix: pd.DataFrame, out_path: Path) -> None:
    """Kompaktowa macierz gapów: wiersze = przypadki, kolumny = reprezentanci."""
    n_rows, n_cols = matrix.shape
    values = matrix.to_numpy(dtype=float)
    vmin_data, vmax_data = float(np.nanmin(values)), float(np.nanmax(values))

    # Skala rozbieżna z zerem w środku; obsługa danych bez wartości ujemnych.
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
    cbar.set_label("gap vs ideał (fidelity_cost)")

    ax.set_xticks(np.arange(n_cols))
    ax.set_xticklabels([_stacked(c) for c in matrix.columns], fontsize=9)
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels(matrix.index, fontsize=9)
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)

    for i in range(n_rows):
        for j in range(n_cols):
            value = values[i, j]
            if np.isnan(value):
                text = "brak"
            elif abs(value) <= TOL:
                text = "0"
            else:
                text = f"{value:.4f}"
            frac = float(norm(value)) if not np.isnan(value) else 0.5
            color = "white" if (frac < 0.16 or frac > 0.84) else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=8, color=color)

    ax.set_title("Gap vs ideał per przypadek i reprezentant (0 = optimum, czerwone = gorzej)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
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
        print("Każdy reprezentant trafia w optimum na każdym przypadku, pomijam case_detail.")
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
        colors = ["#2ca02c" if abs(gaps[r][case]) <= TOL else "#C44E52" for r in rep_order]
        ax.bar(x, costs, color=colors, alpha=0.9, width=0.65)
        ax.axhline(float(ideal[case]), color="#C44E52", linestyle="--", linewidth=1.5,
                   label="ideał (exact DP)")
        ax.set_xticks(x)
        ax.set_xticklabels([_stacked(r) for r in rep_order], fontsize=8)
        worst = max((gaps[r][case] for r in rep_order), key=abs)
        ax.set_title(
            f"{case}: ideał {float(ideal[case]):.4f}, największy gap {worst:+.4f}",
            fontsize=10,
        )
        ax.set_ylabel("fidelity_cost", fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        ax.margins(y=0.18)

    for ax in axes.ravel()[len(selected):]:
        ax.axis("off")
    axes.ravel()[0].legend(loc="upper left", fontsize=8)
    fig.suptitle(
        f"Przypadki bez trafienia w optimum: pokazano {len(selected)} z {len(problematic)} "
        "(największe gapy); czerwone słupki = powyżej ideału",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return True


def plot_crossover(csv_path: Path, out_path: Path) -> bool:
    """Opcjonalny wykres skalowania: czas i gap vs liczba interakcji."""
    if not csv_path.exists():
        print("Brak results/crossover.csv, pomijam wykres crossover.")
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
                    color="#C44E52", label="exact_dp (ideał)", zorder=3)
    ax_time.scatter(df["interactions"], df["tabu_seconds"], s=45,
                    color="#4C72B0", label="tabu fidelity", zorder=3)
    if not hit.empty:
        ax_time.scatter(hit["interactions"], hit["exact_dp_seconds"], s=90, marker="o",
                        facecolors="none", edgecolors="#C44E52", linewidth=1.2,
                        label="exact_dp przy budżecie (fallback)", zorder=4)
    ax_time.set_xscale("log")
    ax_time.set_yscale("log")
    ax_time.set_xlabel("liczba interakcji 2Q")
    ax_time.set_ylabel("czas solve (s, skala log)")
    ax_time.set_title("Czas vs rozmiar instancji")
    ax_time.grid(True, which="both", alpha=0.25)
    ax_time.legend(fontsize=8)

    if ok.empty:
        ax_gap.text(0.5, 0.5, "brak wierszy bez fallbacku exact_dp",
                    ha="center", va="center", transform=ax_gap.transAxes, fontsize=10)
    else:
        ax_gap.scatter(ok["interactions"], ok["tabu_gap"], s=45, color="#4C72B0", zorder=3)
        ax_gap.axhline(0, color="black", linewidth=1.0, linestyle=":")
    ax_gap.set_xscale("log")
    ax_gap.set_xlabel("liczba interakcji 2Q")
    ax_gap.set_ylabel("gap tabu vs exact_dp (fidelity_cost)")
    ax_gap.set_title("Gap vs rozmiar (tylko wiersze bez fallbacku)")
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
    """Podsumowanie: ideał osobno, reprezentanci jako odległość od ideału."""
    total_cases = int(df["case"].nunique())
    n_variants = sum(len(members) for _, members in FAMILIES if not df[df["solver"] == members[0]].empty)
    ref = df[df["solver"].isin(REFERENCES)]
    lines = [
        "# Podsumowanie wyników benchmarków (fidelity)",
        "",
        "Ideał = exact_dp: pełne przeszukanie przestrzeni (layouty, dowolne",
        "SWAP-y na krawędziach, dowolny porządek topologiczny, dokładny koszt",
        "fidelity), liczone raz na przypadek. Żaden solver nie może go pobić,",
        "może się tylko z nim zrównać. `gap` = fidelity_cost solwera minus",
        "ideał przypadku: 0 = osiąga optimum, dodatnia = odległość od optimum,",
        "ujemna = solver zszedł poniżej naszego ideału routingu (pełna",
        "optymalizacja Qiskita, patrz `results/gap-analysis.md`).",
        "",
        f"- Przypadki testowe: {total_cases}",
        f"- Reprezentanci: {len(stats)} (z {n_variants} porównywanych wariantów)",
        "- Metryka: `fidelity_cost_cancelled` (true minimum), gdy jest w CSV",
        "",
        "## Ideał (exact DP, dolne ograniczenie)",
        "",
        "| Referencja | Średni fidelity_cost | Mediana czasu (s) | Średni czas (s) |",
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
        "## Reprezentanci (odległość od ideału)",
        "",
        "| Reprezentant | Śr. fidelity_cost | Śr. gap vs ideał | std gap | "
        "Mediana czasu (s) | Śr. czas (s) | Śr. evals | Na optimum |",
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
        "`Na optimum` = przypadki, w których |gap| <= 1e-9, czyli solver "
        "zrównał się z ideałem. Zejście poniżej ideału nie liczy się jako "
        "trafienie, bo to inna gra (patrz gap-analysis)."
    )
    lines.append("")

    lines += [
        "## Reprezentanci: co zostało scalone",
        "",
        "Warianty w rodzinie mają ten sam algorytm i różnią się tylko startem,",
        "więc na wykresach występuje reprezentant. Tabela pokazuje, jak bardzo",
        "scalony wariant faktycznie różnił się od reprezentanta (po gapach, "
        f"tolerancja {TOL:g}), żeby nic nie zniknęło pod etykietą.",
        "",
        "| Reprezentant | Scalony wariant | Przypadki z różnicą | Max |delta| | Śr. |delta| |",
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
                f"- Dodatkowe scalenie: {_name(kept)} i {names} mają identyczne "
                f"wektory fidelity_cost na wszystkich przypadkach."
            )
    else:
        lines.append(
            "- Dodatkowe scalenia reprezentantów: brak (żadna para nie ma "
            "identycznych wektorów fidelity_cost)."
        )
    lines.append("")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Podsumowanie zapisane: {out_file}")


def cleanup_plots(out_dir: Path, keep: set[str]) -> list[str]:
    """Usuwa z plots/ pliki PNG spoza bieżącego zestawu wykresów."""
    removed = []
    for png in sorted(out_dir.glob("*.png")):
        if png.name not in keep:
            png.unlink()
            removed.append(png.name)
    return removed


def main() -> None:
    print("Ładowanie danych...")
    df = load_data()
    ideal = ideal_per_case(df)
    if ideal.empty:
        raise SystemExit("Brak wierszy referencji (exact_dp) w CSV, nie ma od czego liczyć gapu.")

    reps, collapse_report = collapse_families(df)
    reps, identical_merges = merge_identical_reps(df, ideal, reps)
    stats = representative_stats(df, ideal, reps)

    # Jawny wydruk mapowania reprezentantów, żeby scalenie było widoczne od razu.
    print("\nReprezentanci rodzin (dedup):")
    for rep, members in FAMILIES:
        if rep not in reps:
            continue
        scaled = [m for m in members if m != rep]
        suffix = f" <- {', '.join(scaled)}" if scaled else ""
        print(f"  {rep}{suffix}")
    print("\nRóżnice w scalonych rodzinach (gap, tolerancja 1e-9):")
    for item in collapse_report:
        print(
            f"  {item['rep']} vs {item['variant']}: różni się na "
            f"{item['n_diff']}/{item['n_cases']} przypadków, "
            f"max |delta| {item['max_diff']:.4f}, śr. |delta| {item['mean_diff']:.4f}"
        )
    if identical_merges:
        for kept, merged in identical_merges:
            print(f"  dodatkowe scalenie (identyczne wektory): {kept} <- {', '.join(merged)}")
    else:
        print("  dodatkowe scalenia identycznych reprezentantów: brak")
    print("")

    out = PLOTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    print("Generowanie wykresów...")
    written: list[str] = []
    plot_gap_to_ideal(stats, out / "gap_to_ideal.png")
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
    if plot_crossover(CROSSOVER_CSV, out / "crossover.png"):
        written.append("crossover.png")

    removed = cleanup_plots(out, set(written))
    if removed:
        print(f"Usunięto stare wykresy: {', '.join(removed)}")

    print("Generowanie podsumowania...")
    generate_summary(df, ideal, stats, collapse_report, identical_merges)

    print("\nZapisane pliki:")
    for name in written:
        print(f"  plots/{name}")
    print(f"  {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
