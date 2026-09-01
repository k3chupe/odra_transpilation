"""Pytest fixtures."""

from __future__ import annotations

import pytest

import odra_router  # noqa: F401 — register solvers
from odra_router.arch import trivial_circuit
from odra_router.contract import SOLVERS, make_problem
from odra_router.generator import random_circuit


@pytest.fixture
def trivial_problem():
    return make_problem(trivial_circuit())


@pytest.fixture(params=sorted(SOLVERS.keys()))
def solver_name(request):
    return request.param


@pytest.fixture
def random_problems():
    return [make_problem(random_circuit(seed=i, num_gates=6)) for i in range(5)]
