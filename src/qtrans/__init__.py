"""Custom routing and optimization for ODRA5 / Adonis topology."""

from qtrans.arch import odra5_coupling_map, odra5_target, trivial_circuit
from qtrans.contract import (
    RoutingProblem,
    RoutingSolution,
    SOLVERS,
    apply,
    equivalent,
    make_problem,
    metrics,
    register_solver,
    validate,
)

# Register built-in solvers on import
from qtrans.routing import baseline as _baseline  # noqa: F401
from qtrans.routing import exact_dp as _exact_dp  # noqa: F401

__all__ = [
    "RoutingProblem",
    "RoutingSolution",
    "SOLVERS",
    "apply",
    "equivalent",
    "make_problem",
    "metrics",
    "odra5_coupling_map",
    "odra5_target",
    "register_solver",
    "trivial_circuit",
    "validate",
]
