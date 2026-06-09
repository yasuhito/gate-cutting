"""Gate Cutting helpers built on top of the reusable Stim backend."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable, Iterator, Sequence

from . import stim_backend
from .stim_backend import ErrorParams, active_qubits, append_operation_with_noise, run_standard, sample_expectation


CX_DECOMPOSITION: tuple[tuple[float, str, str], ...] = (
    (0.5, "I", "I"),
    (0.5, "Z", "I"),
    (0.5, "I", "X"),
    (-0.5, "Z", "X"),
)


@dataclass(frozen=True)
class CutTarget:
    """A concrete CX instruction selected for cutting."""

    instruction_index: int
    qubits: tuple[int, int]


def _instruction_targets(instruction: Any) -> list[int]:
    targets: list[int] = []
    for target in instruction.targets_copy():
        if getattr(target, "is_qubit_target", True):
            targets.append(int(target.value if hasattr(target, "value") else target))
    return targets


def find_cx_cut_targets(
    circuit: Any,
    *,
    cut_pairs: Iterable[tuple[int, int]] | None = None,
    instruction_indices: Iterable[int] | None = None,
) -> list[CutTarget]:
    """Find concrete CX instructions to cut.

    ``cut_pairs`` preserves the legacy API where MIP returns ``(control,
    target)`` pairs.  ``instruction_indices`` is the preferred precise API; it
    can distinguish repeated CX gates on the same qubit pair.
    """

    pair_set = set(cut_pairs or [])
    index_set = set(instruction_indices or [])
    use_pairs = cut_pairs is not None
    use_indices = instruction_indices is not None

    if not use_pairs and not use_indices:
        return []

    cuts: list[CutTarget] = []
    for index, instruction in enumerate(circuit):
        if instruction.name != "CX":
            continue
        targets = _instruction_targets(instruction)
        if len(targets) != 2:
            continue
        qubits = (targets[0], targets[1])

        selected = True
        if use_indices:
            selected = selected and index in index_set
        if use_pairs:
            selected = selected and qubits in pair_set
        if selected:
            cuts.append(CutTarget(instruction_index=index, qubits=qubits))

    return cuts


def iter_gate_cut_terms(
    original_circuit: Any,
    cuts: Sequence[CutTarget],
    error_params: ErrorParams,
    *,
    decomposition: Sequence[tuple[float, str, str]] = CX_DECOMPOSITION,
) -> Iterator[tuple[float, Any]]:
    """Yield weighted noisy sub-circuits for a Gate Cutting expansion."""

    stim_module = stim_backend._require_stim()
    instructions = list(original_circuit)
    cut_indices = {cut.instruction_index for cut in cuts}

    if not cut_indices:
        sub_circuit = stim_module.Circuit()
        for instruction in instructions:
            append_operation_with_noise(sub_circuit, instruction.name, _instruction_targets(instruction), error_params)
        yield 1.0, sub_circuit
        return

    for combination in product(decomposition, repeat=len(cuts)):
        coefficient = 1.0
        term_by_index: dict[int, tuple[str, str]] = {}
        for cut, term in zip(cuts, combination):
            term_coeff, control_op, target_op = term
            coefficient *= term_coeff
            term_by_index[cut.instruction_index] = (control_op, target_op)

        sub_circuit = stim_module.Circuit()
        for index, instruction in enumerate(instructions):
            targets = _instruction_targets(instruction)
            if index in cut_indices:
                if instruction.name != "CX" or len(targets) != 2:
                    raise ValueError(f"Cut target at instruction {index} is not a two-qubit CX instruction")
                control, target = targets
                control_op, target_op = term_by_index[index]
                if control_op != "I":
                    append_operation_with_noise(sub_circuit, control_op, [control], error_params)
                if target_op != "I":
                    append_operation_with_noise(sub_circuit, target_op, [target], error_params)
            else:
                append_operation_with_noise(sub_circuit, instruction.name, targets, error_params)

        yield coefficient, sub_circuit


def _ensure_measurements_on_qubits(circuit: Any, qubits: Sequence[int], error_params: ErrorParams) -> None:
    if getattr(circuit, "num_measurements", 0) == 0:
        append_operation_with_noise(circuit, "M", list(qubits), error_params)


def run_gate_cut(
    original_circuit: Any,
    cuts: Sequence[CutTarget],
    error_params: ErrorParams,
    *,
    shots: int = 10000,
    decomposition: Sequence[tuple[float, str, str]] = CX_DECOMPOSITION,
) -> float:
    """Run a Gate Cutting expansion and combine weighted expectations."""

    if not cuts:
        return run_standard(original_circuit, shots=shots, error_params=error_params)

    measurement_qubits = active_qubits(original_circuit)
    total_expectation = 0.0
    for coefficient, sub_circuit in iter_gate_cut_terms(
        original_circuit,
        cuts,
        error_params,
        decomposition=decomposition,
    ):
        _ensure_measurements_on_qubits(sub_circuit, measurement_qubits, error_params)
        total_expectation += coefficient * sample_expectation(sub_circuit, shots)

    return float(total_expectation)
