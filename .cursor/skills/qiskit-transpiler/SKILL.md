---
name: qiskit-transpiler
description: Qiskit 1.2.4 transpiler facts for odra-router — StagedPassManager stages, replacing routing, ODRA5 topology, GateDirection pitfalls. Use when integrating solvers with Qiskit or debugging transpile errors.
---

# Qiskit transpiler (1.2.4) — odra-router notes

## ODRA5 / Adonis

- 5 qubits, **star** topology, center qubit index **2**
- Edges: (0,2), (1,2), (2,3), (2,4)
- Native gates: `r` (phased RX), `cz`
- Defined in `src/odra_router/arch.py` without IQM

## StagedPassManager stages

`init` → `layout` → `routing` → `translation` → `optimization` → `scheduling`

Replace routing:

```python
from qiskit.transpiler import generate_preset_pass_manager, PassManager
pm = generate_preset_pass_manager(2, target=odra5_target())
pm.routing = PassManager([SolverRoutingPass(solver)])
out = pm.run(circuit)
```

## GateDirection error

`TranspilerError: connection between physical qubits (X, Y) for cz`

Cause: routing pass left a 2-qubit gate on non-adjacent physical qubits, or `layout`/`final_layout` in `property_set` disagree with the DAG.

Fix: use `apply()` + set both `layout` and `final_layout` in `SolverRoutingPass` (see `qiskit_glue.py`).

## IQM optional

```bash
pip install -e ".[hardware]"
from iqm.qiskit_iqm.fake_backends import fake_adonis
backend = fake_adonis.IQMFakeAdonis()
```

Requires `iqm-client[qiskit]` extra, not plain `iqm-client`.

## Comparison baseline

```python
from odra_router.qiskit_glue import qiskit_baseline
transpiled = qiskit_baseline(circuit, optimization_level=2)
```

## References

- [IBM transpiler stages](https://quantum.cloud.ibm.com/docs/en/guides/transpiler-stages)
- Project glue: `src/odra_router/qiskit_glue.py`
