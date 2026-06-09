import importlib
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


def sample_cut_graph():
    from gate_cutting.mip import build_cut_graph

    circuit = FakeQiskitCircuit([
        FakeInstruction("h", [0]),
        FakeInstruction("cx", [0, 1]),
        FakeInstruction("barrier", [0, 1]),
        FakeInstruction("cx", [1, 2]),
    ])

    return build_cut_graph(
        circuit,
        cx_fidelities={(0, 1): 0.5, (1, 2): 0.8},
        one_q_fidelities={0: 0.99, 1: 0.98},
        qubit_coords={0: (0.0, 0.0), 1: (1.0, 0.0)},
    )


def two_bad_edge_cut_graph():
    from gate_cutting.mip import build_cut_graph

    circuit = FakeQiskitCircuit([
        FakeInstruction("cx", [0, 1]),
        FakeInstruction("cx", [0, 1]),
    ], num_qubits=2)
    return build_cut_graph(
        circuit,
        cx_fidelities={(0, 1): 0.5},
        one_q_fidelities={0: 0.99, 1: 0.98},
        qubit_coords={0: (0.0, 0.0), 1: (1.0, 0.0)},
    )


class MIPHelperTest(unittest.TestCase):
    def test_build_cut_graph_reads_num_qubits(self):
        self.assertEqual(sample_cut_graph().num_qubits, 3)

    def test_build_cut_graph_uses_provided_node_fidelity(self):
        self.assertEqual(sample_cut_graph().nodes[0]["fidelity"], 0.99)

    def test_build_cut_graph_defaults_missing_node_fidelity(self):
        self.assertEqual(sample_cut_graph().nodes[2]["fidelity"], 1.0)

    def test_build_cut_graph_defaults_missing_node_position(self):
        self.assertEqual(sample_cut_graph().nodes[2]["pos"], (2.0, 0.0))

    def test_build_cut_graph_collects_cx_edges_with_stim_indices(self):
        from gate_cutting.cut_selection import CircuitEdge

        self.assertEqual(
            sample_cut_graph().edges,
            [
                CircuitEdge(edge_index=0, instruction_index=1, qubits=(0, 1), fidelity=0.5, source_instruction_index=1),
                CircuitEdge(edge_index=1, instruction_index=4, qubits=(1, 2), fidelity=0.8, source_instruction_index=3),
            ],
        )

    def test_mip_module_does_not_expose_greedy_fallback(self):
        self.assertFalse(hasattr(importlib.import_module("gate_cutting.mip"), "select_low_fidelity_cut_targets"))

    def test_solve_cut_graph_calls_scipy_milp(self):
        import scipy.optimize

        from gate_cutting.mip import MIPCutFinder

        calls = []
        real_milp = scipy.optimize.milp

        def spy_milp(*args, **kwargs):
            calls.append(True)
            return real_milp(*args, **kwargs)

        try:
            scipy.optimize.milp = spy_milp
            MIPCutFinder().solve_cut_graph(two_bad_edge_cut_graph(), max_cuts=1, cut_fidelity_threshold=0.96)
        finally:
            scipy.optimize.milp = real_milp

        self.assertTrue(calls)

    def test_solve_cut_graph_raises_when_mip_solver_fails(self):
        import scipy.optimize

        from gate_cutting.mip import MIPCutFinder

        real_milp = scipy.optimize.milp

        def failed_milp(*args, **kwargs):
            return types.SimpleNamespace(success=False, message="forced failure", x=[])

        try:
            scipy.optimize.milp = failed_milp
            with self.assertRaises(RuntimeError):
                MIPCutFinder().solve_cut_graph(two_bad_edge_cut_graph(), max_cuts=1, cut_fidelity_threshold=0.96)
        finally:
            scipy.optimize.milp = real_milp

    def test_mip_cut_finder_solves_cut_graph_with_scipy_mip(self):
        from gate_cutting.gate_cutting import CutTarget
        from gate_cutting.mip import MIPCutFinder

        cuts = MIPCutFinder().solve_cut_graph(two_bad_edge_cut_graph(), max_cuts=2, cut_fidelity_threshold=0.96)

        self.assertEqual(
            cuts,
            [
                CutTarget(instruction_index=0, qubits=(0, 1), fidelity=0.5),
                CutTarget(instruction_index=2, qubits=(0, 1), fidelity=0.5),
            ],
        )


if __name__ == "__main__":
    unittest.main()
