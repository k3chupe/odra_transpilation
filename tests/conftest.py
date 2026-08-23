"""Pytest fixtures."""

from __future__ import annotations

import pytest

import qtrans  # noqa: F401 — register solvers
from qtrans.arch import trivial_circuit
from qtrans.contract import SOLVERS, make_problem
from qtrans.generator import random_circuit


@pytest.fixture
def trivial_problem():
    return make_problem(trivial_circuit())


@pytest.fixture(params=sorted(SOLVERS.keys()))
def solver_name(request):
    return request.param


@pytest.fixture
def random_problems():
    return [make_problem(random_circuit(seed=i, num_gates=6)) for i in range(5)]
