import importlib
import types
import unittest


class FakeStimInstruction:
    def __init__(self, name, targets):
        self.name = name
        self._targets = targets

    def targets_copy(self):
        return [types.SimpleNamespace(is_qubit_target=True, value=t) for t in self._targets]


class FakeStimCircuit:
    def __init__(self):
        self.operations = []

    def append(self, name, targets=(), arg=None):
        if targets is None:
            targets = []
        elif isinstance(targets, int):
            targets = [targets]
        else:
            targets = list(targets)
        self.operations.append((name, targets, arg))

    def __iter__(self):
        for name, targets, _ in self.operations:
            yield FakeStimInstruction(name, targets)

    @property
    def num_measurements(self):
        return sum(1 for name, _, _ in self.operations if name in {"M", "MR", "MX", "MY", "MZ"})


class FakeStimModule:
    Circuit = FakeStimCircuit


class FakeInstruction:
    def __init__(self, name, qubits):
        self.operation = types.SimpleNamespace(name=name)
        self.qubits = qubits


class FakeQiskitCircuit:
    def __init__(self, instructions):
        self.data = instructions

    def find_bit(self, qubit):
        return types.SimpleNamespace(index=qubit)


class StimBackendTest(unittest.TestCase):
    def setUp(self):
        self.backend = importlib.import_module("gate_cutting.stim_backend")
        self.backend._stim = FakeStimModule()

    def test_qiskit_to_stim_inserts_tick_after_cx_not_identity(self):
        qc = FakeQiskitCircuit([
            FakeInstruction("h", [0]),
            FakeInstruction("cx", [0, 1]),
            FakeInstruction("measure", [0]),
        ])

        stim_circuit = self.backend.qiskit_to_stim(qc)

        self.assertEqual(
            stim_circuit.operations,
            [
                ("H", [0], None),
                ("CX", [0, 1], None),
                ("TICK", [], None),
                ("M", [0], None),
            ],
        )
        self.assertNotIn("I", [name for name, _, _ in stim_circuit.operations])

    def test_qiskit_barrier_converts_to_tick(self):
        qc = FakeQiskitCircuit([FakeInstruction("barrier", [0, 1])])

        stim_circuit = self.backend.qiskit_to_stim(qc)

        self.assertEqual(stim_circuit.operations, [("TICK", [], None)])

    def test_unknown_qiskit_gate_raises_by_default(self):
        qc = FakeQiskitCircuit([FakeInstruction("rz", [0])])

        with self.assertRaises(NotImplementedError):
            self.backend.qiskit_to_stim(qc)

    def test_append_operation_with_noise_adds_depolarize1_after_one_qubit_gate(self):
        err = self.backend.ErrorParams(one_qubit={0: 0.01}, two_qubit={}, readout={})
        circuit = FakeStimCircuit()

        self.backend.append_operation_with_noise(circuit, "H", [0], err)

        self.assertEqual(circuit.operations, [("H", [0], None), ("DEPOLARIZE1", [0], 0.01)])

    def test_append_operation_with_noise_adds_depolarize2_after_cx_with_reverse_lookup(self):
        err = self.backend.ErrorParams(one_qubit={}, two_qubit={(1, 0): 0.2}, readout={})
        circuit = FakeStimCircuit()

        self.backend.append_operation_with_noise(circuit, "CX", [0, 1], err)

        self.assertEqual(circuit.operations, [("CX", [0, 1], None), ("DEPOLARIZE2", [0, 1], 0.2)])

    def test_append_operation_with_noise_adds_readout_error_before_measurement(self):
        err = self.backend.ErrorParams(one_qubit={}, two_qubit={}, readout={0: 0.03})
        circuit = FakeStimCircuit()

        self.backend.append_operation_with_noise(circuit, "M", [0], err)

        self.assertEqual(circuit.operations, [("X_ERROR", [0], 0.03), ("M", [0], None)])

    def test_ensure_measurements_adds_readout_error_for_auto_measurement(self):
        err = self.backend.ErrorParams(one_qubit={}, two_qubit={}, readout={0: 0.04})
        circuit = FakeStimCircuit()
        circuit.append("H", [0])

        self.backend.ensure_measurements(circuit, err)

        self.assertEqual(circuit.operations, [("H", [0], None), ("X_ERROR", [0], 0.04), ("M", [0], None)])


if __name__ == "__main__":
    unittest.main()
