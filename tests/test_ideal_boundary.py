"""Ideal boundary (step 2 of the "why tabu" analysis): what the ideal bounds.

`exact_dp` is exact for one game only: free initial layout, SWAPs on star
edges, any topological order, and cancellation of *literally adjacent*
self-inverse pairs. The Qiskit preset plays a wider game (non-adjacent
commutation, 1Q and 2Q resynthesis, CX to CZ), so it can land below the
ideal, and that must never be sold as a bug of the ideal.

These tests pin the variant A decision written down in `docs/contract.md`:

1. the boundary and the decision are documented;
2. Qiskit really does go below the ideal on a concrete case, and our own
   cancellation pass removes none of that advantage;
3. the step 1 artefact has no unexplained case: every advantage carries a
   cause from the taxonomy, `other` never appears (skipped when the
   gitignored artefact is absent, with the command that regenerates it);
4. on the fidelity suite the ideal answers inside its budget, so it is a
   lower bound there and not a silent greedy fallback.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from odra_router.bench import fidelity_cases
from odra_router.contract import SOLVERS, make_problem
from odra_router.fidelity import cancelled_fidelity_cost, fidelity_cost, odra5_default_fidelity
from odra_router.optimize.cancel import cancel_adjacent, reduce_input
from odra_router.qiskit_glue import qiskit_baseline

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "contract.md"
GAP_ANALYSIS = ROOT / "results" / "gap-analysis.csv"

MODEL = odra5_default_fidelity()

#: Cases where results/gap-analysis.csv shows the preset below the ideal.
DOCUMENTED_ADVANTAGE_CASES = ("small_0", "medium_1", "heavy_1")

#: Causes the gap analysis is allowed to report for a Qiskit advantage.
KNOWN_CAUSES = {
    "cx-cz-decomposition",
    "synthesis-1q",
    "non-adjacent-commutation",
    "synthesis-2q",
}


def _case(name: str):
    for case_name, circuit in fidelity_cases():
        if case_name == name:
            return circuit
    raise AssertionError(f"case {name} is missing from fidelity_cases()")


def test_contract_documents_the_ideal_boundary():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "## Ideal boundary (decision: variant A)" in text
    for phrase in (
        "non-adjacent commutation",
        "cancellation of literally adjacent self-inverse pairs",
        "not implemented",
    ):
        assert phrase in text, f"contract no longer states: {phrase}"
    for case in DOCUMENTED_ADVANTAGE_CASES:
        assert case in text, f"contract lost the evidence case {case}"


def test_qiskit_preset_goes_below_the_ideal_outside_our_game():
    circuit = _case("small_0")
    problem = make_problem(reduce_input(circuit))
    ideal = cancelled_fidelity_cost(
        problem, SOLVERS["exact_dp"].solve(problem, seed=0, budget_s=30.0), MODEL
    )

    preset_costs = []
    covered = []
    for seed in (0, 1, 2):
        out = qiskit_baseline(circuit, 2, seed=seed)
        cleaned = cancel_adjacent(out)
        preset_costs.append(fidelity_cost(cleaned, MODEL))
        # What our own pass removes from this Qiskit output.
        covered.append(fidelity_cost(out, MODEL) - preset_costs[-1])

    best_preset = min(preset_costs)
    assert best_preset < ideal - 1e-9, (
        f"small_0: preset {best_preset} is not below the ideal {ideal}; "
        "if Qiskit changed, re-run scripts/gap_analysis.py and update the contract"
    )
    assert max(covered) <= 1e-9, (
        "adjacent cancellation now removes part of the Qiskit advantage; "
        "the boundary in docs/contract.md needs an update"
    )


def test_gap_analysis_artefact_has_no_unexplained_case():
    if not GAP_ANALYSIS.exists():
        pytest.skip(
            "results/gap-analysis.csv is gitignored; "
            "regenerate it with `python scripts/gap_analysis.py`"
        )
    with GAP_ANALYSIS.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "gap-analysis.csv is empty"

    assert not [r for r in rows if r["cause"] == "other"], "cause 'other' is not allowed"

    flagged = {r["case"] for r in rows if r["qiskit_below_ideal"] == "True"}
    assert flagged, "no case where Qiskit is below the ideal; the analysis lost its point"
    for case in sorted(flagged):
        case_rows = [r for r in rows if r["case"] == case]
        advantage_rows = [r for r in case_rows if float(r["delta_vs_ideal"]) < -1e-9]
        assert advantage_rows, f"{case}: flagged as below the ideal but no negative delta"
        for row in advantage_rows:
            assert row["cause"] in KNOWN_CAUSES, f"{case}: cause {row['cause']!r} is not in the taxonomy"
            assert row["stage"].startswith("preset_"), f"{case}: unexpected stage {row['stage']}"
        # The advantage is outside our pass: nothing adjacent to cancel.
        for row in case_rows:
            if row["stage"] not in {f"preset_L{level}" for level in range(4)}:
                continue
            match = re.search(r"cancel-covered ([0-9.eE+-]+)", row["note"])
            assert match, f"{case}/{row['stage']}: note lost the cancel-covered figure"
            assert float(match.group(1)) <= 1e-9, (
                f"{case}/{row['stage']}: our cancellation covers part of the win"
            )


def test_ideal_answers_inside_budget_on_the_fidelity_suite():
    solver = SOLVERS["exact_dp"]
    for name in ("medium_1", "hard_2r"):
        problem = make_problem(reduce_input(_case(name)))
        if not problem.interactions:
            continue
        solver.solve(problem, seed=0, budget_s=30.0)
        assert not solver.last_hit_budget, f"{name}: exact_dp fell back to greedy"
