"""Gate cancellation: drop adjacent self-inverse two-qubit gate pairs (phase 2).

On the ODRA5 gate level the two-qubit gates we route are self-inverse: two
adjacent CX on the same physical pair (same control and target), two adjacent
CZ on the same pair, or two adjacent SWAPs on the same pair equal the
identity. Cancelling such pairs is the optimization stage the Qiskit preset
runs (its gate-cancellation passes) and this project so far lacks, which is
why ``qiskit_preset`` reports lower ``cz_cost`` than our solvers on routed
outputs.

``cancel_adjacent`` is a pure circuit transform: it never mutates its input.
It serves two purposes:

- post-routing pass: run on ``contract.apply()`` output to clean adjacent
  pairs the router emitted;
- input reduction: run on the source circuit before routing. Cancelling
  adjacent CX pairs in the source lowers the routing minimum (measured:
  rand20 6->5 SWAPs, rand40 12->11, two CX fewer), so the routing "ideal"
  must optimize the reduced circuit to search the true minimum.

Only *literally adjacent* pairs cancel: any gate on either of the two wires
between them (a 1Q gate, another 2Q gate, measure, barrier) breaks the pair.
Gates on other wires do not interfere. Because removing a pair can make two
previously separated gates adjacent (e.g. an X-X pair between two CX pairs),
the pass iterates to a fixpoint.
"""

from __future__ import annotations

from qiskit import QuantumCircuit

# Two-qubit gates we emit or route that are their own inverse. CX is only
# self-inverse when control and target are in the same order, so pairs are
# matched by exact qargs order, not by the unordered qubit pair.
SELF_INVERSE_2Q: frozenset[str] = frozenset({"cx", "cz", "swap"})


def cancel_adjacent(circuit: QuantumCircuit) -> QuantumCircuit:
    """Return a copy of ``circuit`` with adjacent self-inverse 2Q pairs removed.

    Each fixpoint round scans the operation list in circuit order and removes
    every non-overlapping adjacent pair found; the scan repeats until no pair
    is removed, so pairs that become adjacent only after other removals are
    still cancelled.
    """
    data = list(circuit.data)
    n = circuit.num_qubits

    while True:
        removed: set[int] = set()
        # For every kept operation index i, the last kept index that touched
        # each of its qubits.
        last_touch: list[int | None] = [None] * n
        changed = False

        for i, instruction in enumerate(data):
            if i in removed:
                continue
            gate = instruction.operation
            qargs = instruction.qubits
            if len(qargs) == 2 and gate.name in SELF_INVERSE_2Q:
                a, b = qargs[0]._index, qargs[1]._index
                m = last_touch[a]
                if (
                    m is not None
                    and m == last_touch[b]
                    and m not in removed
                    and data[m].operation.name == gate.name
                    and tuple(q._index for q in data[m].qubits) == (a, b)
                ):
                    # Nothing on wires a or b since m, and m is the same
                    # self-inverse 2Q gate on the same pair: m * gate = I.
                    removed.add(m)
                    removed.add(i)
                    changed = True
                    continue  # a removed gate must not update last_touch
            for q in qargs:
                last_touch[q._index] = i

        if not changed:
            break
        data = [d for j, d in enumerate(data) if j not in removed]

    out = QuantumCircuit(n, *circuit.cregs)
    for instruction in data:
        out.append(instruction.operation, instruction.qubits, instruction.clbits)
    return out


def reduce_input(circuit: QuantumCircuit) -> QuantumCircuit:
    """Cancel adjacent pairs in a source circuit before routing.

    Same rules as :func:`cancel_adjacent`; the separate name documents the
    use: the routing minimum (and every routing solver's input) should be
    defined on the reduced circuit, otherwise solvers pay for gates that
    would never be executed.
    """
    return cancel_adjacent(circuit)
