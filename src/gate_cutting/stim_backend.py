"""Reusable Stim backend helpers for the gate-cutting experiments.

The original experiment scripts duplicated three responsibilities in several
places: converting Qiskit circuits to Stim, inserting device-derived noise, and
sampling parity expectations.  This module centralizes that behavior so the
experiments can share one tested implementation.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

try:  # Stim is optional in the lightweight test environment.
    import stim as _stim  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised when Stim is absent.
    _stim = None


@dataclass(frozen=True)
class ErrorParams:
    """Error probabilities used when inserting Stim noise operations."""

    one_qubit: Mapping[int, float]
    two_qubit: Mapping[tuple[int, int], float]
    readout: Mapping[int, float]


MEASURE_OPS = {"M", "MR", "MX", "MY", "MZ"}
ANNOTATION_OPS = {"TICK", "SHIFT_COORDS", "QUBIT_COORDS", "DETECTOR", "OBSERVABLE_INCLUDE"}
NO_NOISE_OPS = ANNOTATION_OPS | {"I", "BARRIER"}

_QISKIT_TO_STIM_1Q = {
    "id": "I",
    "x": "X",
    "y": "Y",
    "z": "Z",
    "h": "H",
    "s": "S",
    "sdg": "S_DAG",
}


def _require_stim() -> Any:
    if _stim is None:
        raise ModuleNotFoundError(
            "Stim is required for this operation. Install the 'stim' package "
            "or inject a compatible test double into gate_cutting.stim_backend._stim."
        )
    return _stim


def _as_target_list(targets: Iterable[int] | int | None) -> list[int]:
    if targets is None:
        return []
    if isinstance(targets, int):
        return [targets]
    return list(targets)


def _append(circuit: Any, name: str, targets: Iterable[int] | int | None = None, arg: float | None = None) -> None:
    """Append to a Stim circuit while keeping zero-target operations portable."""

    target_list = _as_target_list(targets)
    if arg is None:
        circuit.append(name, target_list)
    else:
        circuit.append(name, target_list, arg)


def _instruction_qubits(qiskit_circuit: Any, instruction: Any) -> list[int]:
    return [qiskit_circuit.find_bit(q).index for q in instruction.qubits]


def qiskit_to_stim(qc: Any, *, insert_ticks: bool = True, strict: bool = True) -> Any:
    """Convert a Qiskit-like circuit into a Stim circuit.

    Only the gate set used by the experiments is supported.  CX operations are
    followed by ``TICK`` instead of the legacy ``I`` separator, making the
    operation boundary explicit without adding a fake identity gate.
    """

    stim_module = _require_stim()
    stim_circuit = stim_module.Circuit()

    for instruction in qc.data:
        op = instruction.operation.name.lower()
        qubits = _instruction_qubits(qc, instruction)

        if op in _QISKIT_TO_STIM_1Q:
            _append(stim_circuit, _QISKIT_TO_STIM_1Q[op], qubits)
        elif op in {"cx", "cnot"}:
            _append(stim_circuit, "CX", qubits)
            if insert_ticks:
                _append(stim_circuit, "TICK")
        elif op == "measure":
            _append(stim_circuit, "M", qubits)
        elif op == "barrier":
            if insert_ticks:
                _append(stim_circuit, "TICK")
        elif strict:
            raise NotImplementedError(f"Unsupported Qiskit gate for Stim conversion: {op}")
        else:
            warnings.warn(
                f"Skipping unsupported Qiskit gate during Stim conversion: {op}",
                RuntimeWarning,
                stacklevel=2,
            )

    return stim_circuit


def lookup_two_qubit_error(
    error_params: ErrorParams,
    u: int,
    v: int,
    *,
    allow_reverse: bool = True,
) -> float:
    """Look up a two-qubit error probability, optionally falling back to reverse direction."""

    if (u, v) in error_params.two_qubit:
        return float(error_params.two_qubit[(u, v)])
    if allow_reverse and (v, u) in error_params.two_qubit:
        return float(error_params.two_qubit[(v, u)])
    return 0.0


def append_operation_with_noise(
    circuit: Any,
    op_name: str,
    targets: Sequence[int],
    error_params: ErrorParams,
    *,
    allow_reverse_two_qubit: bool = True,
) -> None:
    """Append an operation and the corresponding device-derived noise.

    Measurement operations receive readout ``X_ERROR`` before the measurement.
    One-qubit Clifford operations receive ``DEPOLARIZE1`` after the operation.
    CX operations receive ``DEPOLARIZE2`` after the operation.
    Annotation/separator operations such as ``TICK`` are copied without noise.
    """

    stim_name = op_name.upper()
    target_list = list(targets)

    if stim_name in MEASURE_OPS:
        for q in target_list:
            p = float(error_params.readout.get(q, 0.0))
            if p > 0:
                _append(circuit, "X_ERROR", [q], p)
        _append(circuit, stim_name, target_list)
        return

    if stim_name == "BARRIER":
        _append(circuit, "TICK")
        return

    if stim_name in NO_NOISE_OPS:
        _append(circuit, stim_name, target_list)
        return

    _append(circuit, stim_name, target_list)

    if len(target_list) == 2 and stim_name in {"CX", "CNOT"}:
        u, v = target_list
        p = lookup_two_qubit_error(error_params, u, v, allow_reverse=allow_reverse_two_qubit)
        if p > 0:
            _append(circuit, "DEPOLARIZE2", [u, v], p)
    elif len(target_list) == 1:
        q = target_list[0]
        p = float(error_params.one_qubit.get(q, 0.0))
        if p > 0:
            _append(circuit, "DEPOLARIZE1", [q], p)


def _stim_instruction_targets(instruction: Any) -> list[int]:
    targets = []
    for target in instruction.targets_copy():
        if getattr(target, "is_qubit_target", True):
            targets.append(int(target.value if hasattr(target, "value") else target))
    return targets


def active_qubits(circuit: Any) -> list[int]:
    """Return sorted qubit ids referenced by a Stim circuit."""

    qubits: set[int] = set()
    for instruction in circuit:
        qubits.update(_stim_instruction_targets(instruction))
    return sorted(qubits)


def add_noise(circuit: Any, error_params: ErrorParams) -> Any:
    """Return a new Stim circuit with noise inserted after supported operations."""

    stim_module = _require_stim()
    noisy = stim_module.Circuit()
    for instruction in circuit:
        append_operation_with_noise(noisy, instruction.name, _stim_instruction_targets(instruction), error_params)
    return noisy


def ensure_measurements(circuit: Any, error_params: ErrorParams | None = None) -> Any:
    """Ensure a circuit measures all active qubits, adding readout noise if requested.

    The input circuit is mutated and returned for convenience.
    """

    if getattr(circuit, "num_measurements", 0) == 0:
        qubits = active_qubits(circuit)
        if error_params is None:
            _append(circuit, "M", qubits)
        else:
            append_operation_with_noise(circuit, "M", qubits, error_params)
    return circuit


def parity_expectation(samples: np.ndarray) -> float:
    """Compute a Z-parity expectation from binary measurement samples."""

    sample_array = np.asarray(samples)
    parities = np.sum(sample_array, axis=1) % 2
    eigenvalues = 1 - 2 * parities
    return float(np.mean(eigenvalues))


def sample_expectation(circuit: Any, shots: int) -> float:
    sampler = circuit.compile_sampler()
    samples = sampler.sample(shots=shots)
    return parity_expectation(samples)


def _copy_stim_circuit(circuit: Any) -> Any:
    if hasattr(circuit, "copy"):
        return circuit.copy()
    stim_module = _require_stim()
    copied = stim_module.Circuit()
    for instruction in circuit:
        copied.append(instruction)
    return copied


def run_standard(circuit: Any, *, shots: int = 10000, error_params: ErrorParams | None = None) -> float:
    """Run an ideal or noisy Stim circuit and return the parity expectation."""

    if error_params is None:
        runnable = _copy_stim_circuit(circuit)
        ensure_measurements(runnable)
    else:
        runnable = add_noise(circuit, error_params)
        ensure_measurements(runnable, error_params)
    return sample_expectation(runnable, shots)
