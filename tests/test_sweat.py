"""Smoke test for the budget-sweep benchmark."""

from __future__ import annotations

import csv
from pathlib import Path

import qtrans  # noqa: F401
from qtrans.bench import run_sweat_benchmark
from qtrans.generator import hard_circuit
from qtrans.queko import odra5_queko


def test_run_sweat_smoke(tmp_path: Path):
    circuit, _ = odra5_queko(8, seed=0)
    cases = [("smoke", circuit), ("hard", hard_circuit(2))]
    path = run_sweat_benchmark(
        tmp_path,
        budgets=(0.05, 0.2),
        reps=2,
        cases=cases,
    )
    assert path.exists()
    assert (tmp_path / "sweat-summary.md").exists()

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expected = 2 * len(cases) * 2 * 6  # budgets x cases x reps x solvers
    assert len(rows) == expected
    assert "budget_s" in rows[0]
    assert "optimal" in rows[0]
    assert all(r["error"] == "" for r in rows)
