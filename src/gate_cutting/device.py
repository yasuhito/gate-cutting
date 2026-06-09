"""Device JSON parsing helpers for the gate-cutting experiments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .stim_backend import ErrorParams


@dataclass(frozen=True)
class DeviceData:
    """Parsed device metadata and error parameters.

    The project device JSON stores fidelities.  Stim noise insertion uses error
    probabilities, so this structure keeps both the original fidelity maps and
    derived ``ErrorParams`` together.
    """

    raw: Mapping[str, Any]
    name: str | None
    device_id: str | None
    calibrated_at: str | None
    cx_fidelities: dict[tuple[int, int], float]
    one_q_fidelities: dict[int, float]
    qubit_coords: dict[int, tuple[float, float]]
    error_params: ErrorParams

    @property
    def qubit_count(self) -> int:
        return len(self.raw.get("qubits", []))

    @property
    def coupling_count(self) -> int:
        return len(self.raw.get("couplings", []))


def _error_from_fidelity(fidelity: float) -> float:
    return max(0.0, 1.0 - float(fidelity))


def _parse_position(qubit: Mapping[str, Any], qid: int) -> tuple[float, float]:
    position = qubit.get("position", {})
    if isinstance(position, Mapping) and "x" in position and "y" in position:
        return (float(position["x"]), float(position["y"]))
    if "x" in qubit and "y" in qubit:
        return (float(qubit["x"]), float(qubit["y"]))
    return (float(qid), 0.0)


def parse_device(data: Mapping[str, Any]) -> DeviceData:
    """Parse an OQTOPUS-like device JSON dictionary.

    Missing fidelities default to 1.0 and missing readout errors default to 0.0,
    matching the legacy experiment scripts' behavior.
    """

    cx_fidelities: dict[tuple[int, int], float] = {}
    one_q_fidelities: dict[int, float] = {}
    qubit_coords: dict[int, tuple[float, float]] = {}
    one_qubit_errors: dict[int, float] = {}
    two_qubit_errors: dict[tuple[int, int], float] = {}
    readout_errors: dict[int, float] = {}

    for qubit in data.get("qubits", []):
        qid = int(qubit["id"])
        fidelity = float(qubit.get("fidelity", 1.0))
        one_q_fidelities[qid] = fidelity
        qubit_coords[qid] = _parse_position(qubit, qid)
        one_qubit_errors[qid] = _error_from_fidelity(fidelity)

        meas = qubit.get("meas_error", {})
        if not isinstance(meas, Mapping):
            meas = {}
        readout_errors[qid] = max(0.0, float(meas.get("readout_assignment_error", 0.0)))

    for coupling in data.get("couplings", []):
        control = int(coupling["control"])
        target = int(coupling["target"])
        fidelity = float(coupling.get("fidelity", 1.0))
        cx_fidelities[(control, target)] = fidelity
        two_qubit_errors[(control, target)] = _error_from_fidelity(fidelity)

        if "reverse_fidelity" in coupling:
            reverse_fidelity = float(coupling["reverse_fidelity"])
            cx_fidelities[(target, control)] = reverse_fidelity
            two_qubit_errors[(target, control)] = _error_from_fidelity(reverse_fidelity)

    return DeviceData(
        raw=data,
        name=data.get("name"),
        device_id=data.get("device_id"),
        calibrated_at=data.get("calibrated_at"),
        cx_fidelities=cx_fidelities,
        one_q_fidelities=one_q_fidelities,
        qubit_coords=qubit_coords,
        error_params=ErrorParams(
            one_qubit=one_qubit_errors,
            two_qubit=two_qubit_errors,
            readout=readout_errors,
        ),
    )


def load_device(path: str | Path) -> DeviceData:
    """Load and parse a device JSON file."""

    device_path = Path(path)
    data = json.loads(device_path.read_text(encoding="utf-8"))
    return parse_device(data)
