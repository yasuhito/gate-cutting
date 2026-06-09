import unittest


class FakeQuantumCircuit:
    def __init__(self, num_qubits):
        self.num_qubits = num_qubits
        self.operations = []

    def h(self, q): self.operations.append(("h", q))
    def s(self, q): self.operations.append(("s", q))
    def sdg(self, q): self.operations.append(("sdg", q))
    def x(self, q): self.operations.append(("x", q))
    def y(self, q): self.operations.append(("y", q))
    def z(self, q): self.operations.append(("z", q))
    def cx(self, c, t): self.operations.append(("cx", c, t))


def generated_circuit(seed=1, num_qubits=4, depth=2):
    from gate_cutting.circuits import random_clifford_circuit

    return random_clifford_circuit(
        num_qubits,
        depth,
        seed=seed,
        circuit_factory=FakeQuantumCircuit,
        single_qubit_probability=1.0,
        cx_probability=1.0,
    )


class RandomCliffordCircuitTest(unittest.TestCase):
    def test_random_clifford_circuit_is_deterministic_with_seed(self):
        a = generated_circuit(seed=123, num_qubits=6, depth=3)
        b = generated_circuit(seed=123, num_qubits=6, depth=3)

        self.assertEqual(a.operations, b.operations)

    def test_random_clifford_circuit_emits_at_least_one_operation(self):
        circuit = generated_circuit(seed=1)

        self.assertTrue(circuit.operations)

    def test_random_clifford_circuit_uses_expected_gate_set(self):
        circuit = generated_circuit(seed=1)
        allowed = {"h", "s", "sdg", "x", "y", "z", "cx"}

        self.assertTrue(all(op[0] in allowed for op in circuit.operations))

    def test_random_clifford_circuit_targets_existing_qubits(self):
        circuit = generated_circuit(seed=1)

        self.assertTrue(all(q < circuit.num_qubits for op in circuit.operations for q in op[1:]))

    def test_random_clifford_circuit_preserves_requested_qubit_count(self):
        circuit = generated_circuit(seed=7, num_qubits=4, depth=2)

        self.assertEqual(circuit.num_qubits, 4)

    def test_circuits_module_does_not_expose_compatibility_class(self):
        import gate_cutting.circuits as circuits

        self.assertFalse(hasattr(circuits, "CircuitGenerator"))


if __name__ == "__main__":
    unittest.main()
