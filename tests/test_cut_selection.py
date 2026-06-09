import types
import unittest


class FakeInstruction:
    def __init__(self, name, qubits):
        self.operation = types.SimpleNamespace(name=name)
        self.qubits = qubits


class FakeQiskitCircuit:
    def __init__(self, instructions, num_qubits=2):
        self.data = instructions
        self.num_qubits = num_qubits

    def find_bit(self, qubit):
        return types.SimpleNamespace(index=qubit)


def one_missing_fidelity_edge():
    from gate_cutting.cut_selection import collect_cx_edges

    circuit = FakeQiskitCircuit([FakeInstruction("cx", [1, 0])])
    return collect_cx_edges(circuit, {})[0]


class CutSelectionTest(unittest.TestCase):
    def test_collect_cx_edges_preserves_instruction_indices_for_repeated_pairs(self):
        from gate_cutting.cut_selection import CircuitEdge, collect_cx_edges

        circuit = FakeQiskitCircuit([
            FakeInstruction("h", [0]),
            FakeInstruction("cx", [0, 1]),
            FakeInstruction("cx", [0, 1]),
        ])

        edges = collect_cx_edges(circuit, {(0, 1): 0.75})

        self.assertEqual(
            edges,
            [
                CircuitEdge(edge_index=0, instruction_index=1, qubits=(0, 1), fidelity=0.75, source_instruction_index=1),
                CircuitEdge(edge_index=1, instruction_index=3, qubits=(0, 1), fidelity=0.75, source_instruction_index=2),
            ],
        )

    def test_cut_targets_from_edges_selects_specific_repeated_gate_by_edge_index(self):
        from gate_cutting.cut_selection import CircuitEdge, cut_targets_from_edges
        from gate_cutting.gate_cutting import CutTarget

        edges = [
            CircuitEdge(edge_index=0, instruction_index=1, qubits=(0, 1), fidelity=0.75, source_instruction_index=1),
            CircuitEdge(edge_index=1, instruction_index=3, qubits=(0, 1), fidelity=0.75, source_instruction_index=2),
        ]

        cuts = cut_targets_from_edges(edges, selected_edge_indices=[1])

        self.assertEqual(cuts, [CutTarget(instruction_index=3, qubits=(0, 1))])

    def test_collect_cx_edges_defaults_missing_fidelity_to_one(self):
        self.assertEqual(one_missing_fidelity_edge().fidelity, 1.0)

    def test_collect_cx_edges_preserves_qubits_when_fidelity_is_missing(self):
        self.assertEqual(one_missing_fidelity_edge().qubits, (1, 0))


if __name__ == "__main__":
    unittest.main()
