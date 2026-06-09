import unittest

import stim
from qiskit import QuantumCircuit

from gate_cutting import stim_backend
from gate_cutting.gate_cutting import CutTarget, run_gate_cut
from gate_cutting.stim_backend import ErrorParams, qiskit_to_stim, run_standard


EMPTY_ERRORS = ErrorParams(one_qubit={}, two_qubit={}, readout={})


def deterministic_qiskit_circuit():
    circuit = QuantumCircuit(2)
    circuit.x(1)
    circuit.cx(0, 1)
    return circuit


def trivial_cx_stim_circuit():
    circuit = stim.Circuit()
    circuit.append("CX", [0, 1])
    circuit.append("TICK")
    return circuit


class StimIntegrationTest(unittest.TestCase):
    def setUp(self):
        stim_backend._stim = stim

    def test_tick_separator_does_not_change_noiseless_standard_expectation(self):
        circuit_with_tick = qiskit_to_stim(deterministic_qiskit_circuit(), insert_ticks=True)
        circuit_without_tick = qiskit_to_stim(deterministic_qiskit_circuit(), insert_ticks=False)

        self.assertEqual(
            run_standard(circuit_with_tick, shots=256),
            run_standard(circuit_without_tick, shots=256),
        )

    def test_noiseless_gate_cut_matches_standard_for_trivial_cx(self):
        circuit = trivial_cx_stim_circuit()

        self.assertAlmostEqual(
            run_gate_cut(circuit, [CutTarget(instruction_index=0, qubits=(0, 1))], EMPTY_ERRORS, shots=256),
            run_standard(circuit, shots=256, error_params=EMPTY_ERRORS),
        )


if __name__ == "__main__":
    unittest.main()
