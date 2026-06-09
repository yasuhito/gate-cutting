"""Circuit generation helpers used by the gate-cutting experiments."""

from __future__ import annotations

import random
from typing import Any, Callable


SINGLE_QUBIT_CLIFFORD_GATES: tuple[str, ...] = ("h", "s", "sdg", "x", "y", "z")


def _default_quantum_circuit_factory(num_qubits: int) -> Any:
    try:
        from qiskit import QuantumCircuit
    except ModuleNotFoundError as exc:  # pragma: no cover - env dependent.
        raise ModuleNotFoundError(
            "qiskit is required when circuit_factory is not provided. "
            "Install qiskit or pass a QuantumCircuit-compatible factory."
        ) from exc
    return QuantumCircuit(num_qubits)


def random_clifford_circuit(
    num_qubits: int,
    depth: int,
    *,
    seed: int | None = None,
    circuit_factory: Callable[[int], Any] | None = None,
    single_qubit_probability: float = 0.6,
    cx_probability: float = 1.0,
) -> Any:
    """Generate a random Clifford circuit using H/S/Sdg/X/Y/Z and CX gates.

    ``circuit_factory`` is injectable so the generator can be tested without
    importing Qiskit.  The returned object only needs methods named like the
    emitted gates (``h``, ``s``, ``sdg``, ``x``, ``y``, ``z``, ``cx``).
    """

    rng = random.Random(seed)
    factory = circuit_factory or _default_quantum_circuit_factory
    circuit = factory(num_qubits)
    qubits = list(range(num_qubits))

    for _ in range(depth):
        for qubit in qubits:
            if rng.random() < single_qubit_probability:
                gate_name = rng.choice(SINGLE_QUBIT_CLIFFORD_GATES)
                getattr(circuit, gate_name)(qubit)

        shuffled = qubits[:]
        rng.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            if rng.random() < cx_probability:
                circuit.cx(shuffled[i], shuffled[i + 1])

    return circuit


class CircuitGenerator:
    """Backward-compatible wrapper for experiment scripts."""

    @staticmethod
    def random_clifford(
        num_qubits: int,
        depth: int,
        seed: int | None = None,
        *,
        circuit_factory: Callable[[int], Any] | None = None,
        single_qubit_probability: float = 0.6,
        cx_probability: float = 1.0,
    ) -> Any:
        return random_clifford_circuit(
            num_qubits,
            depth,
            seed=seed,
            circuit_factory=circuit_factory,
            single_qubit_probability=single_qubit_probability,
            cx_probability=cx_probability,
        )
