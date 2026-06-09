import importlib
import types
import unittest

import numpy as np


class FakeStimTarget:
    def __init__(self, value):
        self.value = value
        self.is_qubit_target = True


class FakeStimInstruction:
    def __init__(self, name, targets):
        self.name = name
        self._targets = list(targets)

    def targets_copy(self):
        return [FakeStimTarget(t) for t in self._targets]


class FakeSampler:
    def sample(self, shots):
        return np.zeros((shots, 2), dtype=np.uint8)


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

    def compile_sampler(self):
        return FakeSampler()


class FakeStimModule:
    Circuit = FakeStimCircuit


class GateCuttingTest(unittest.TestCase):
    def setUp(self):
        self.backend = importlib.import_module("gate_cutting.stim_backend")
        self.backend._stim = FakeStimModule()
        self.gc = importlib.import_module("gate_cutting.gate_cutting")

    def repeated_pair_circuit(self):
        circuit = FakeStimCircuit()
        circuit.append("CX", [0, 1])
        circuit.append("TICK")
        circuit.append("CX", [0, 1])
        return circuit

    def one_cut_terms(self):
        error_params = self.backend.ErrorParams(one_qubit={0: 0.01, 1: 0.02}, two_qubit={(0, 1): 0.2}, readout={})
        return list(self.gc.iter_gate_cut_terms(
            self.repeated_pair_circuit(),
            [self.gc.CutTarget(instruction_index=0, qubits=(0, 1))],
            error_params,
        ))

    def test_find_cx_cut_targets_can_select_by_instruction_index(self):
        cuts = self.gc.find_cx_cut_targets(self.repeated_pair_circuit(), instruction_indices=[2])

        self.assertEqual(cuts, [self.gc.CutTarget(instruction_index=2, qubits=(0, 1))])

    def test_find_cx_cut_targets_supports_legacy_cut_pairs(self):
        circuit = FakeStimCircuit()
        circuit.append("CX", [0, 1])
        circuit.append("TICK")
        circuit.append("CX", [1, 0])

        cuts = self.gc.find_cx_cut_targets(circuit, cut_pairs=[(1, 0)])

        self.assertEqual(cuts, [self.gc.CutTarget(instruction_index=2, qubits=(1, 0))])

    def test_iter_gate_cut_terms_uses_expected_coefficients(self):
        self.assertEqual([coeff for coeff, _ in self.one_cut_terms()], [0.5, 0.5, 0.5, -0.5])

    def test_iter_gate_cut_terms_preserves_uncut_cx_in_first_term(self):
        self.assertEqual(
            self.one_cut_terms()[0][1].operations,
            [("TICK", [], None), ("CX", [0, 1], None), ("DEPOLARIZE2", [0, 1], 0.2)],
        )

    def test_iter_gate_cut_terms_replaces_selected_cx_in_last_term(self):
        self.assertEqual(
            self.one_cut_terms()[-1][1].operations,
            [
                ("Z", [0], None),
                ("DEPOLARIZE1", [0], 0.01),
                ("X", [1], None),
                ("DEPOLARIZE1", [1], 0.02),
                ("TICK", [], None),
                ("CX", [0, 1], None),
                ("DEPOLARIZE2", [0, 1], 0.2),
            ],
        )

    def test_run_gate_cut_combines_weighted_term_expectations(self):
        circuit = FakeStimCircuit()
        circuit.append("CX", [0, 1])
        error_params = self.backend.ErrorParams(one_qubit={}, two_qubit={}, readout={})

        value = self.gc.run_gate_cut(
            circuit,
            [self.gc.CutTarget(instruction_index=0, qubits=(0, 1))],
            error_params,
            shots=4,
        )

        self.assertEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main()
