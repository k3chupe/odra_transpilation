"""QUEKO benchmark circuit generator (Tan & Cong, 2020).

Ported from the MIT-licensed reference implementation
https://github.com/glassnotes/queko-generator (``queko.py``), adapted to:

  * plain integer node labels ``0..n-1`` (no networkx, no ``lattice_dim``),
  * a deterministic seeded RNG (``np.random.default_rng(seed)``),
  * direct Qiskit circuit construction instead of QASM emission.

QUEKO ("quantum mapping examples with known optimal") builds a circuit on a
given coupling graph together with a virtual->physical initial layout that
routes it with ZERO SWAPs, providing ground-truth benchmarks for routing
solvers. Construction (Algorithm 1 of Tan & Cong):

  1. "backbone"  — one gate per timestep ``0..depth-1`` forming a dependency
     chain (each gate shares a qubit with its predecessor),
  2. "sprinkling" — fill the remaining gate budget (up to ``max_1q + max_2q``
     total gates) into random non-overlapping slots,
  3. "scrambling" — relabel qubits by a random permutation ``perm`` (qubit
     ``i`` becomes ``perm[i]``), then sort gates by timestep and emit.

Deviation from the reference: the reference sprinkles via unbounded rejection
sampling, which can loop forever when the greedy two-qubit placement runs out
of free slots (star graphs make this easy); here candidates are scanned in
random order with a single-qubit fallback, so generation always terminates.
"""

from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit

from qtrans.arch import ODRA5_EDGES


def _max_matching_size(edges, n):
    """Maximum cardinality matching size of an undirected graph.

    Backtracking over edges (take/skip) with endpoint bookkeeping. ``n`` is
    tiny (<= 5 in this repo) so simplicity beats speed; replaces the reference
    implementation's ``nx.maximal_matching`` without the networkx dependency.
    """
    edge_list = list(edges)
    used = [False] * n
    best = 0

    def dfs(i, count):
        nonlocal best
        if count + (len(edge_list) - i) <= best:
            return  # cannot improve on the current best
        if i == len(edge_list):
            best = count
            return
        a, b = edge_list[i]
        dfs(i + 1, count)  # skip this edge
        if not used[a] and not used[b]:
            used[a] = used[b] = True
            dfs(i + 1, count + 1)  # take this edge
            used[a] = used[b] = False

    dfs(0, 0)
    return best


def _backbone_construction(rng, node_list, edge_list, depth, max_2q_gates):
    """Step 1 of QUEKO construction: build the "backbone" of depth ``depth``
    by creating a dependency chain of gates.

    Returns ``(gate_list, count_1q_gates, count_2q_gates)`` where
    ``gate_list`` holds ``(timestep, qubits)`` entries with ``qubits`` a tuple
    of one (single-qubit gate) or two (two-qubit gate) node labels.
    """
    count_1q_gates = 0
    count_2q_gates = 0

    edge_choices = list(range(len(edge_list)))

    timesteps = []  # Timesteps
    gates = []  # Applied gates

    for timestep in range(depth):
        # Determine whether to add a 1- or 2-qubit gate
        gate_type = rng.choice([1, 2])

        # Choose a random edge for a 2-qubit gate, only if we haven't reached the max.
        if gate_type == 2 and count_2q_gates < max_2q_gates:
            which_qubits = edge_list[rng.choice(edge_choices)]
        else:
            # Otherwise, choose a random qubit for a single-qubit gate
            which_qubits = (rng.choice(node_list),)

        # To create a dependency chain, we need overlap between the current
        # gate and the previous one. If there is no overlap, pick again.
        if timestep > 0:
            while not any(q in gates[timestep - 1] for q in which_qubits):
                if gate_type == 2 and count_2q_gates < max_2q_gates:
                    which_qubits = edge_list[rng.choice(edge_choices)]
                else:
                    which_qubits = (rng.choice(node_list),)

        # Update the gate counts and the list
        if gate_type == 2 and count_2q_gates < max_2q_gates:
            count_2q_gates += 1
        else:
            count_1q_gates += 1

        timesteps.append(timestep)
        gates.append(which_qubits)

    return list(zip(timesteps, gates)), count_1q_gates, count_2q_gates


def _sprinkling_phase(
    rng,
    gate_list,
    node_list,
    edge_list,
    depth,
    max_1q_gates,
    max_2q_gates,
    count_1q_gates,
    count_2q_gates,
):
    """Step 2 of QUEKO construction: sprinkle gates into the empty spaces
    created by the backbone, up to the gate budget from the density vector.

    Unlike the reference (which uses unbounded rejection sampling and can spin
    forever when the two-qubit budget has no free slot left), candidates are
    tried in random order, so placement always terminates; if no two-qubit
    slot exists anywhere, a single-qubit gate is placed instead.
    """
    available_timesteps = list(range(depth))

    for _ in range(depth, max_1q_gates + max_2q_gates):
        gate_type = rng.choice([1, 2])
        two_qubit = gate_type == 2 and count_2q_gates < max_2q_gates

        if two_qubit:
            options = [(t, e) for t in available_timesteps for e in edge_list]
        else:
            options = [(t, (q,)) for t in available_timesteps for q in node_list]

        # Try candidates in random order; pick the first non-overlapping slot.
        timestep, which_qubits = None, None
        for idx in rng.permutation(len(options)):
            t, cand = options[idx]
            gates_at_t = [gate for gate in gate_list if gate[0] == t]
            if not any(any(q in gate[1] for q in cand) for gate in gates_at_t):
                timestep, which_qubits = t, cand
                break

        # No two-qubit slot anywhere (greedy scheduling corner case): fall
        # back to a single-qubit gate, which always has a free slot because
        # the capacity bound max_1q + 2*max_2q <= n_qubits*depth holds.
        if timestep is None:
            oneq_options = [(t, (q,)) for t in available_timesteps for q in node_list]
            for idx in rng.permutation(len(oneq_options)):
                t, cand = oneq_options[idx]
                gates_at_t = [gate for gate in gate_list if gate[0] == t]
                if not any(any(q in gate[1] for q in cand) for gate in gates_at_t):
                    timestep, which_qubits = t, cand
                    break
            assert timestep is not None, "no free single-qubit slot (capacity check broken)"

        # Update the gate counts and the list (counted by what was placed)
        if len(which_qubits) == 2:
            count_2q_gates += 1
        else:
            count_1q_gates += 1

        gate_list.append((timestep, which_qubits))

    return gate_list


def _scrambling_phase(gate_list, perm):
    """Step 3 of QUEKO construction: relabel qubits by the permutation ``perm``
    (qubit ``i`` becomes ``perm[i]``)."""
    permuted_gate_list = []

    for timestep, gate in gate_list:
        if len(gate) == 2:
            permuted_gate = (perm[gate[0]], perm[gate[1]])
        else:
            permuted_gate = (perm[gate[0]],)

        permuted_gate_list.append((timestep, permuted_gate))

    return permuted_gate_list


def _build_circuit(gate_list, n_qubits):
    """Append gates (sorted by timestep) to a Qiskit circuit on ``n_qubits``."""
    qc = QuantumCircuit(n_qubits)
    for _, gate in gate_list:
        if len(gate) == 2:
            qc.cx(int(gate[0]), int(gate[1]))
        else:
            qc.x(int(gate[0]))
    return qc


def queko_circuit(edges, depth, density_vec, seed=0):
    """Return (circuit, optimal_layout).

    edges: list of (int, int) coupling-graph edges (e.g. the ODRA5 star).
    depth: target number of layers (cycles).
    density_vec: (d1, d2) single- and two-qubit gate densities.

    circuit: qiskit QuantumCircuit on n qubits (n = max node index + 1).
    optimal_layout: tuple[int, ...] of length n — the virtual->physical
        initial layout that routes `circuit` with ZERO SWAPs on `edges`.

    Raises:
        ValueError: If the depth/density combination cannot produce an
            admissible circuit.
    """
    rng = np.random.default_rng(seed)

    n_qubits = max(max(a, b) for a, b in edges) + 1
    node_list = list(range(n_qubits))

    # Determine the number of single- and two-qubit gates required
    max_1q_gates = int(np.ceil(density_vec[0] * n_qubits * depth))
    max_2q_gates = int(np.ceil(density_vec[1] * n_qubits * depth / 2))

    # Admissibility checks: max_1q_gates + max_2q_gates cannot be less than the
    # depth, otherwise there are not enough gates to produce something with
    # depth `depth`.
    if max_1q_gates + max_2q_gates < depth:
        raise ValueError(
            "Input data inadmissible. Insufficient gate densities "
            f"to produce a circuit with depth {depth}.\n"
            f"max_1q_gates = {max_1q_gates}, max_2q_gates = {max_2q_gates}"
        )

    # max_1q_gates + 2 * max_2q_gates cannot be greater than n_qubits * depth;
    # that would be too many gates to fit in that depth on the device.
    if max_1q_gates + 2 * max_2q_gates > n_qubits * depth:
        raise ValueError(
            "Input data inadmissible. Desired gate densities are too large "
            f"to produce a circuit with depth {depth}.\n"
            f"max_1q_gates = {max_1q_gates}, max_2q_gates = {max_2q_gates}"
        )

    # The number of two-qubit gates cannot be larger than depth * the size of
    # the maximum matching: each timestep holds at most that many disjoint
    # two-qubit gates.
    max_match_size = _max_matching_size(edges, n_qubits)
    if max_2q_gates > max_match_size * depth:
        raise ValueError(
            "Input data inadmissible. Number of 2-qubit gates determined "
            f"from density vector is too large to fit within depth {depth}.\n"
            f"max_2q_gates = {max_2q_gates}, max. matching size {max_match_size}"
        )

    # Generate a permutation of the graph vertices; this is the solution to
    # the allocation problem (qubit i becomes perm[i] in the emitted circuit).
    perm = rng.permutation(n_qubits)

    # Three stages of QUEKO construction
    gate_list, count_1q_gates, count_2q_gates = _backbone_construction(
        rng, node_list, edges, depth, max_2q_gates
    )
    gate_list = _sprinkling_phase(
        rng,
        gate_list,
        node_list,
        edges,
        depth,
        max_1q_gates,
        max_2q_gates,
        count_1q_gates,
        count_2q_gates,
    )
    gate_list = _scrambling_phase(gate_list, perm)

    # Sort the resulting circuit according to the timesteps
    gate_list.sort(key=lambda x: x[0])

    circuit = _build_circuit(gate_list, n_qubits)

    # The emitted circuit holds virtual qubit `perm[p]` where the reference
    # circuit used physical qubit `p`, so placing virtual `perm[p]` on
    # physical `p` routes every gate with zero SWAPs:
    #   optimal_layout = inverse(perm).
    optimal_layout = [0] * n_qubits
    for p in range(n_qubits):
        optimal_layout[int(perm[p])] = p

    return circuit, tuple(optimal_layout)


def odra5_queko(depth, density_vec=(0.2, 0.3), seed=0):
    """QUEKO circuit on the ODRA5 star graph. Returns (circuit, optimal_layout)."""
    return queko_circuit(ODRA5_EDGES, depth, density_vec, seed=seed)
