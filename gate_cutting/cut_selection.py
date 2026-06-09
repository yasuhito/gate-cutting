"""Helpers for mapping circuit CX instructions to concrete cut targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .gate_cutting import CutTarget


@dataclass(frozen=True)
class CircuitEdge:
    """A CX instruction represented as an edge candidate for cutting.

    ``instruction_index`` is the index of the corresponding CX instruction in
    the Stim circuit produced by ``qiskit_to_stim(insert_ticks=True)``.
    ``source_instruction_index`` is the original Qiskit circuit instruction
    index, kept for traceability.
    """

    edge_index: int
    instruction_index: int
    qubits: tuple[int, int]
    fidelity: float
    source_instruction_index: int | None = None


def _qiskit_instruction_qubits(circuit: Any, instruction: Any) -> tuple[int, int]:
    qubits = [circuit.find_bit(q).index for q in instruction.qubits]
    if len(qubits) != 2:
        raise ValueError("CX instruction must have exactly two qubits")
    return int(qubits[0]), int(qubits[1])


def collect_cx_edges(
    circuit: Any,
    cx_fidelities: Mapping[tuple[int, int], float],
    *,
    default_fidelity: float = 1.0,
    insert_ticks: bool = True,
) -> list[CircuitEdge]:
    """Collect CX instructions with graph edge order and Stim instruction index.

    ``edge_index`` is the order among CX edges and matches the order used by
    ``networkx.MultiDiGraph.edges(keys=True, data=True)`` after adding edges in
    this sequence.  ``instruction_index`` is the index of the CX in the Stim
    circuit produced by the shared ``qiskit_to_stim`` converter.  This allows
    MIP-selected graph edges to become concrete ``CutTarget`` values for
    ``run_gate_cut`` even when the same qubit pair appears multiple times.
    """

    edges: list[CircuitEdge] = []
    stim_instruction_index = 0
    for source_instruction_index, instruction in enumerate(circuit.data):
        op_name = instruction.operation.name.lower()
        if op_name in {"cx", "cnot"}:
            qubits = _qiskit_instruction_qubits(circuit, instruction)
            fidelity = float(cx_fidelities.get(qubits, default_fidelity))
            edges.append(
                CircuitEdge(
                    edge_index=len(edges),
                    instruction_index=stim_instruction_index,
                    qubits=qubits,
                    fidelity=fidelity,
                    source_instruction_index=source_instruction_index,
                )
            )
            stim_instruction_index += 1
            if insert_ticks:
                stim_instruction_index += 1
        elif op_name == "barrier":
            if insert_ticks:
                stim_instruction_index += 1
        else:
            # The shared converter emits one Stim instruction for each supported
            # non-CX operation used in these experiments.
            stim_instruction_index += 1
    return edges


def cut_targets_from_edges(
    edges: Sequence[CircuitEdge],
    *,
    selected_edge_indices: Iterable[int],
) -> list[CutTarget]:
    """Convert selected edge indices into concrete ``CutTarget`` objects."""

    selected = set(selected_edge_indices)
    return [
        CutTarget(instruction_index=edge.instruction_index, qubits=edge.qubits)
        for edge in edges
        if edge.edge_index in selected
    ]
