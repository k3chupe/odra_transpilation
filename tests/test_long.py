"""Longer instances and diverse-random pipeline tests (phase 4).

Covers the "more diverse tests / longer circuits" goal: solvers on circuits
beyond the 80-gate suite cap, the reduction+cancellation pipeline on a grid
of random circuits, and a smoke test of the long benchmark command.
"""

from __future__ import annotations

import odra_router  # noqa: F401
from odra_router.bench import long_cases, run_long_benchmark
from odra_router.contract import (
    SOLVERS,
    apply,
    cancelled_metrics,
    make_problem,
    metrics,
    validate,
)
from odra_router.fidelity import cancelled_fidelity_cost, fidelity_cost, odra5_default_fidelity
from odra_router.generator import hard_circuit, random_circuit
from odra_router.optimize.cancel import reduce_input

MODEL = odra5_default_fidelity()


def test_exact_dp_beats_greedy_on_long_instances():
    for name, circuit in (("hard_16r", hard_circuit(16)), ("rand160", random_circuit(seed=0, num_gates=160, p_two_qubit=0.7))):
        problem = make_problem(reduce_input(circuit))
        dp_sol = SOLVERS["exact_dp"].solve(problem, seed=0, budget_s=30.0)
        greedy_sol = SOLVERS["greedy_shortest_path"].solve(problem, seed=0, budget_s=30.0)
        validate(problem, dp_sol)
        validate(problem, greedy_sol)
        dp_cost = fidelity_cost(apply(problem, dp_sol), MODEL)
        greedy_cost = fidelity_cost(apply(problem, greedy_sol), MODEL)
        assert dp_cost <= greedy_cost + 1e-9, name
        assert len(dp_sol.swaps) > 0  # these instances genuinely need routing


def test_long_cases_structure():
    cases = long_cases()
    names = {n for n, _ in cases}
    assert {
        "hard_12r",
        "hard_16r",
        "hard_32r",
        "hard_64r",
        "rand120_s0",
        "rand160_s0",
        "rand160_s1",
        "rand320_s0",
        "rand512_s0",
        "layered128",
        "layered256",
        "queko_d32",
    } <= names
    for name, circuit in cases:
        assert circuit.num_qubits == 5
        problem = make_problem(reduce_input(circuit))
        # hard/random long cases carry real routing work
        if name.startswith(("hard_", "rand")):
            assert len(problem.interactions) >= 60, name


def test_long_cases_separate_the_two_size_axes():
    """Tor A: the suite needs heavy-gate, light-interaction cases.

    ``scripts/scale_probe.py`` claims that the interaction count, not the gate
    count, prices ``exact_dp``. That claim only works if the suite actually
    contains cases with many gates and few interactions (the control group) and
    cases with many interactions and fewer gates, so both axes vary
    independently.
    """
    by_name = dict(long_cases())
    control: dict[str, int] = {}
    for name in ("layered128", "layered256"):
        circuit = by_name[name]
        problem = make_problem(reduce_input(circuit))
        assert circuit.size() >= 300, f"{name}: {circuit.size()} gates is not heavy"
        assert len(problem.interactions) <= 230, (
            f"{name}: {len(problem.interactions)} interactions, the control group needs few"
        )
        control[name] = len(problem.interactions)
    # The control group must not simply be the smallest instances: the top of
    # the hard ladder carries more interactions at fewer gates.
    for name in ("hard_32r", "hard_64r"):
        problem = make_problem(reduce_input(by_name[name]))
        assert len(problem.interactions) >= 150, name
        assert by_name[name].size() < 500, f"{name}: expected fewer gates than the layered pair"
    heaviest = make_problem(reduce_input(by_name["hard_64r"]))
    assert len(heaviest.interactions) > max(control.values()), (
        "the heaviest-interaction case must be a hard instance, not a layered one"
    )


def test_diverse_random_pipeline_never_worse_after_cancellation():
    # Grid of generator parameters through the phase-2 pipeline: the reduced
    # input never routes worse than the original, and post-routing
    # cancellation never increases any metric.
    greedy = SOLVERS["greedy_shortest_path"]
    for num_gates, p2q in ((10, 0.3), (20, 0.7), (40, 0.5), (60, 0.65)):
        for seed in range(4):
            circuit = random_circuit(seed=seed, num_gates=num_gates, p_two_qubit=p2q)
            red = reduce_input(circuit)
            problem_orig = make_problem(circuit)
            problem_red = make_problem(red)
            if not problem_orig.interactions or not problem_red.interactions:
                continue
            sol_orig = greedy.solve(problem_orig, seed=0, budget_s=5.0)
            sol_red = greedy.solve(problem_red, seed=0, budget_s=5.0)
            validate(problem_red, sol_red)
            assert fidelity_cost(apply(problem_red, sol_red), MODEL) <= fidelity_cost(
                apply(problem_orig, sol_orig), MODEL
            ) + 1e-9
            # post-cancellation metrics are never worse than raw ones
            raw = metrics(problem_red, sol_red)
            cancelled = cancelled_metrics(problem_red, sol_red)
            assert cancelled["cz_cost"] <= raw["cz_cost"] + 1e-9
            assert cancelled_fidelity_cost(problem_red, sol_red, MODEL) <= fidelity_cost(
                apply(problem_red, sol_red), MODEL
            ) + 1e-9


def test_long_benchmark_smoke(tmp_path):
    from odra_router.generator import hard_circuit

    path = run_long_benchmark(
        tmp_path,
        solvers=["greedy_shortest_path", "exact_dp"],
        cases=[("hard_2r", hard_circuit(2))],
    )
    assert path.exists()
    assert (tmp_path / "long-summary.md").exists()
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2  # two solvers
    assert all(r["error"] == "" for r in rows)
