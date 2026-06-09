import types
import unittest


class FakeInstruction:
    def __init__(self, name, qubits):
        self.operation = types.SimpleNamespace(name=name)
        self.qubits = qubits


class FakeQiskitCircuit:
    def __init__(self, instructions, num_qubits=3):
        self.data = instructions
        self.num_qubits = num_qubits

    def find_bit(self, qubit):
        return types.SimpleNamespace(index=qubit)


class MIPHelperTest(unittest.TestCase):
    def test_build_cut_graph_collects_nodes_and_cx_edges_with_stim_indices(self):
        from gate_cutting.cut_selection import CircuitEdge
        from gate_cutting.mip import build_cut_graph

        circuit = FakeQiskitCircuit([
            FakeInstruction("h", [0]),
            FakeInstruction("cx", [0, 1]),
            FakeInstruction("barrier", [0, 1]),
            FakeInstruction("cx", [1, 2]),
        ])

        graph = build_cut_graph(
            circuit,
            cx_fidelities={(0, 1): 0.5, (1, 2): 0.8},
            one_q_fidelities={0: 0.99, 1: 0.98},
            qubit_coords={0: (0.0, 0.0), 1: (1.0, 0.0)},
        )

        self.assertEqual(graph.num_qubits, 3)
        self.assertEqual(graph.nodes[0]["fidelity"], 0.99)
        self.assertEqual(graph.nodes[2]["fidelity"], 1.0)
        self.assertEqual(graph.nodes[2]["pos"], (2.0, 0.0))
        self.assertEqual(
            graph.edges,
            [
                CircuitEdge(edge_index=0, instruction_index=1, qubits=(0, 1), fidelity=0.5, source_instruction_index=1),
                CircuitEdge(edge_index=1, instruction_index=4, qubits=(1, 2), fidelity=0.8, source_instruction_index=3),
            ],
        )

    def test_select_low_fidelity_cut_targets_respects_max_cuts_and_instruction_indices(self):
        from gate_cutting.cut_selection import CircuitEdge
        from gate_cutting.gate_cutting import CutTarget
        from gate_cutting.mip import select_low_fidelity_cut_targets

        edges = [
            CircuitEdge(edge_index=0, instruction_index=1, qubits=(0, 1), fidelity=0.7),
            CircuitEdge(edge_index=1, instruction_index=3, qubits=(0, 1), fidelity=0.4),
            CircuitEdge(edge_index=2, instruction_index=5, qubits=(1, 2), fidelity=0.99),
        ]

        cuts = select_low_fidelity_cut_targets(edges, max_cuts=1, cut_fidelity_threshold=0.96)

        self.assertEqual(cuts, [CutTarget(instruction_index=3, qubits=(0, 1))])

    def test_mip_cut_finder_can_solve_cut_graph_without_optional_solver_dependencies(self):
        from gate_cutting.gate_cutting import CutTarget
        from gate_cutting.mip import MIPCutFinder

        circuit = FakeQiskitCircuit([
            FakeInstruction("cx", [0, 1]),
            FakeInstruction("cx", [0, 1]),
        ], num_qubits=2)
        finder = MIPCutFinder(
            cx_fidelities={(0, 1): 0.5},
            one_q_fidelities={0: 0.99, 1: 0.98},
            qubit_coords={0: (0.0, 0.0), 1: (1.0, 0.0)},
        )

        graph = finder.build_cut_graph(circuit)
        cuts = finder.solve_cut_graph(graph, max_cuts=2, cut_fidelity_threshold=0.96)

        self.assertEqual(
            cuts,
            [
                CutTarget(instruction_index=0, qubits=(0, 1)),
                CutTarget(instruction_index=2, qubits=(0, 1)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
