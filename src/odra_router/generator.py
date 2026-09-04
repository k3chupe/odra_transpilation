"""Seeded random circuit generator for benchmarks and tests."""

from __future__ import annotations

import json
import random
from pathlib import Path

from qiskit import QuantumCircuit
from qiskit.circuit import Parameter

from odra_router.arch import ODRA5_NUM_QUBITS

# All six non-edge pairs of the ODRA5 star. A cycle over them forces the
# routing to keep swapping through the center, unlike random circuits where
# many interactions are already adjacent or cheap.
HARD_PAIRS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 3),
    (3, 4),
    (4, 0),
    (0, 3),
    (1, 4),
)


def hard_circuit(rounds: int, *, seed: int = 0) -> QuantumCircuit:
    """Deterministic adversarial circuit: ``rounds`` cycles over non-edge pairs.

    Each round emits one ``cx`` per non-edge pair (6 gates), so routing has to
    move qubits through the center continuously. Deterministic for a given
    ``seed`` (seed only permutes the pair order per round).
    """
    rng = random.Random(seed)
    qc = QuantumCircuit(ODRA5_NUM_QUBITS)
    for _ in range(rounds):
        order = rng.sample(HARD_PAIRS, len(HARD_PAIRS))
        for a, b in order:
            qc.cx(a, b)
    return qc


def random_circuit(
    num_qubits: int = ODRA5_NUM_QUBITS,
    num_gates: int = 10,
    *,
    seed: int = 0,
    p_two_qubit: float = 0.4,
) -> QuantumCircuit:
    """Random circuit over ``cx``, ``h``, ``rz`` (no measurements)."""
    rng = random.Random(seed)
    qc = QuantumCircuit(num_qubits)
    for _ in range(num_gates):
        if rng.random() < p_two_qubit and num_qubits >= 2:
            a, b = rng.sample(range(num_qubits), 2)
            qc.cx(a, b)
        else:
            qc.h(rng.randrange(num_qubits))
            qc.rz(rng.uniform(0, 6.28), rng.randrange(num_qubits))
    return qc


def layered_random_circuit(
    num_layers: int = 10,
    *,
    p_two_qubit: float = 0.6,
    p_one_qubit: float = 0.5,
    seed: int = 0,
) -> QuantumCircuit:
    """Layer-structured random circuit, closer to real compiled circuits.

    Each layer holds a set of *disjoint* two-qubit ``cx`` gates (never two
    gates sharing a qubit inside one layer, like a hardware-mapped layer)
    plus independent single-qubit gates on the remaining qubits. Every layer
    gets at least one gate; deterministic per ``seed``.
    """
    rng = random.Random(seed)
    qc = QuantumCircuit(ODRA5_NUM_QUBITS)
    qubits = list(range(ODRA5_NUM_QUBITS))
    for _ in range(num_layers):
        used: set[int] = set()
        # Disjoint two-qubit gates within the layer.
        while True:
            if rng.random() >= p_two_qubit:
                break
            free = [q for q in qubits if q not in used]
            if len(free) < 2:
                break
            a, b = rng.sample(free, 2)
            qc.cx(a, b)
            used.update((a, b))
        # Independent single-qubit gates on the remaining qubits.
        for q in qubits:
            if q not in used and rng.random() < p_one_qubit:
                if rng.random() < 0.5:
                    qc.h(q)
                else:
                    qc.rz(rng.uniform(0, 6.28), q)
    return qc


def load_suite(path: Path | None = None) -> list[dict]:
    path = path or Path(__file__).resolve().parents[2] / "benchmarks" / "suite.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def circuits_from_suite(path: Path | None = None) -> list[tuple[str, QuantumCircuit]]:
    out: list[tuple[str, QuantumCircuit]] = []
    for case in load_suite(path):
        qc = random_circuit(
            num_qubits=case.get("num_qubits", ODRA5_NUM_QUBITS),
            num_gates=case["num_gates"],
            seed=case["seed"],
            p_two_qubit=case.get("p_two_qubit", 0.4),
        )
        out.append((case["name"], qc))
    return out


#: Generator batch kinds supported by ``odra-router-gen``.
def _batch_circuits(
    num_gates_list: tuple[int, ...],
    p_two_qubit_list: tuple[float, ...],
    num_seeds: int,
    hard_rounds_list: tuple[int, ...],
    seed_base: int = 0,
) -> list[tuple[str, QuantumCircuit, dict]]:
    """Deterministic batch of random and hard circuits (name, circuit, meta).

    One random circuit per (num_gates, p_two_qubit, seed) combination plus
    one hard circuit per (rounds, seed); ``seed_base`` offsets the RNG seeds.
    """
    out: list[tuple[str, QuantumCircuit, dict]] = []
    for gates in num_gates_list:
        for p in p_two_qubit_list:
            for s in range(seed_base, seed_base + num_seeds):
                name = f"random_g{gates}_p{str(p).replace('.', '_')}_s{s}"
                qc = random_circuit(seed=s, num_gates=gates, p_two_qubit=p)
                out.append(
                    (
                        name,
                        qc,
                        {"kind": "random", "seed": s, "num_gates": gates, "p_two_qubit": p},
                    )
                )
    for rounds in hard_rounds_list:
        for s in range(seed_base, seed_base + num_seeds):
            name = f"hard_{rounds}r_s{s}"
            qc = hard_circuit(rounds, seed=s)
            out.append((name, qc, {"kind": "hard", "seed": s, "rounds": rounds}))
    return out


def main_gen(argv: list[str] | None = None) -> None:
    """Generate a reproducible batch of random/hard circuits as QASM + manifest.

    ``odra-router-gen --num-gates 40,80,120 --p2q 0.35,0.7 --seeds 3
    --hard-rounds 8,16 --out benchmarks/generated`` writes one QASM 2.0 file
    per circuit plus a ``manifest.json`` with the generator parameters, so the
    corpus can be regenerated bit-for-bit.
    """
    import argparse

    from qiskit import qasm2

    parser = argparse.ArgumentParser(description=main_gen.__doc__)
    parser.add_argument("--num-gates", default="40,80,120", help="comma list of gate counts")
    parser.add_argument("--p2q", default="0.35,0.7", help="comma list of two-qubit probabilities")
    parser.add_argument("--seeds", type=int, default=3, help="number of seeds per combination")
    parser.add_argument("--hard-rounds", default="8,16", help="comma list of hard circuit rounds")
    parser.add_argument("--seed-base", type=int, default=0, help="first RNG seed")
    parser.add_argument("--out", default="benchmarks/generated", help="output directory")
    args = parser.parse_args(argv)

    num_gates = tuple(int(x) for x in args.num_gates.split(","))
    p2q = tuple(float(x) for x in args.p2q.split(","))
    rounds = tuple(int(x) for x in args.hard_rounds.split(","))
    batch = _batch_circuits(num_gates, p2q, args.seeds, rounds, args.seed_base)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for name, qc, meta in batch:
        path = out_dir / f"{name}.qasm"
        qasm2.dump(qc, path)
        manifest.append({"name": name, "file": path.name, **meta})
    (out_dir / "manifest.json").write_text(
        json.dumps({"num_gates": num_gates, "p_two_qubit": p2q,
                    "hard_rounds": rounds, "seeds": args.seeds,
                    "seed_base": args.seed_base, "cases": manifest}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(manifest)} circuits to {out_dir}")
