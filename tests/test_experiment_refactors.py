import ast
import unittest
from pathlib import Path


def top_level_defs(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }


def imported_modules(path: str) -> set[str | None]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }


def all_imported_modules(path: str) -> set[str | None]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


class ExperimentRefactorTest(unittest.TestCase):
    def test_exp1_b1_does_not_define_error_params(self):
        self.assertNotIn("ErrorParams", top_level_defs("experiments/exp1/b1.py"))

    def test_exp1_b1_does_not_define_qiskit_to_stim(self):
        self.assertNotIn("qiskit_to_stim", top_level_defs("experiments/exp1/b1.py"))

    def test_exp1_b1_does_not_define_noise_insertion(self):
        self.assertNotIn("append_operation_with_noise", top_level_defs("experiments/exp1/b1.py"))

    def test_exp1_b1_does_not_define_random_clifford_circuit(self):
        self.assertNotIn("random_clifford_circuit", top_level_defs("experiments/exp1/b1.py"))

    def test_exp1_b1_imports_shared_circuits(self):
        self.assertIn("gate_cutting.circuits", imported_modules("experiments/exp1/b1.py"))

    def test_exp1_b1_imports_shared_gate_cutting(self):
        self.assertIn("gate_cutting.gate_cutting", imported_modules("experiments/exp1/b1.py"))

    def test_exp1_b1_imports_shared_stim_backend(self):
        self.assertIn("gate_cutting.stim_backend", imported_modules("experiments/exp1/b1.py"))

    def test_exp1_b1_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp1/b1.py").read_text(encoding="utf-8"))

    def test_exp2_b1_does_not_define_circuit_generator(self):
        self.assertNotIn("CircuitGenerator", top_level_defs("experiments/exp2/b1.py"))

    def test_exp2_b1_does_not_define_error_params(self):
        self.assertNotIn("ErrorParams", top_level_defs("experiments/exp2/b1.py"))

    def test_exp2_b1_does_not_define_mip_cut_finder(self):
        self.assertNotIn("MIPCutFinder", top_level_defs("experiments/exp2/b1.py"))

    def test_exp2_b1_imports_shared_circuits(self):
        self.assertIn("gate_cutting.circuits", imported_modules("experiments/exp2/b1.py"))

    def test_exp2_b1_imports_shared_device(self):
        self.assertIn("gate_cutting.device", imported_modules("experiments/exp2/b1.py"))

    def test_exp2_b1_imports_shared_gate_cutting(self):
        self.assertIn("gate_cutting.gate_cutting", imported_modules("experiments/exp2/b1.py"))

    def test_exp2_b1_imports_shared_mip(self):
        self.assertIn("gate_cutting.mip", imported_modules("experiments/exp2/b1.py"))

    def test_exp2_b1_imports_shared_stim_backend(self):
        self.assertIn("gate_cutting.stim_backend", imported_modules("experiments/exp2/b1.py"))

    def test_exp2_b1_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp2/b1.py").read_text(encoding="utf-8"))

    def test_exp2_b2_does_not_define_circuit_generator(self):
        self.assertNotIn("CircuitGenerator", top_level_defs("experiments/exp2/b2.py"))

    def test_exp2_b2_does_not_define_mip_cut_finder(self):
        self.assertNotIn("MIPCutFinder", top_level_defs("experiments/exp2/b2.py"))

    def test_exp2_b2_imports_shared_circuits(self):
        self.assertIn("gate_cutting.circuits", imported_modules("experiments/exp2/b2.py"))

    def test_exp2_b2_imports_shared_mip(self):
        self.assertIn("gate_cutting.mip", imported_modules("experiments/exp2/b2.py"))

    def test_exp2_b2_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp2/b2.py").read_text(encoding="utf-8"))

    def test_exp2_check_does_not_define_circuit_generator(self):
        self.assertNotIn("CircuitGenerator", top_level_defs("experiments/exp2/check.py"))

    def test_exp2_check_does_not_define_error_params(self):
        self.assertNotIn("ErrorParams", top_level_defs("experiments/exp2/check.py"))

    def test_exp2_check_does_not_define_mip_cut_finder(self):
        self.assertNotIn("MIPCutFinder", top_level_defs("experiments/exp2/check.py"))

    def test_exp2_check_imports_shared_circuits(self):
        self.assertIn("gate_cutting.circuits", imported_modules("experiments/exp2/check.py"))

    def test_exp2_check_imports_shared_device(self):
        self.assertIn("gate_cutting.device", imported_modules("experiments/exp2/check.py"))

    def test_exp2_check_imports_shared_gate_cutting(self):
        self.assertIn("gate_cutting.gate_cutting", imported_modules("experiments/exp2/check.py"))

    def test_exp2_check_imports_shared_mip(self):
        self.assertIn("gate_cutting.mip", imported_modules("experiments/exp2/check.py"))

    def test_exp2_check_imports_shared_stim_backend(self):
        self.assertIn("gate_cutting.stim_backend", imported_modules("experiments/exp2/check.py"))

    def test_exp2_check_handles_cut_target_objects_in_visualization(self):
        self.assertIn("cut.qubits", Path("experiments/exp2/check.py").read_text(encoding="utf-8"))

    def test_exp2_check_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp2/check.py").read_text(encoding="utf-8"))

    def test_exp2_benchmark_phase1_imports_b2_via_package_path(self):
        self.assertIn("experiments.exp2.b2", all_imported_modules("experiments/exp2/benchmark_phase1.py"))

    def test_exp2_benchmark_phase2_imports_b2_via_package_path(self):
        self.assertIn("experiments.exp2.b2", all_imported_modules("experiments/exp2/benchmark_phase2.py"))

    def test_exp2_benchmark_phase1_does_not_import_b2_as_local_module(self):
        self.assertNotIn("b2", all_imported_modules("experiments/exp2/benchmark_phase1.py"))

    def test_exp2_benchmark_phase2_does_not_import_b2_as_local_module(self):
        self.assertNotIn("b2", all_imported_modules("experiments/exp2/benchmark_phase2.py"))

    def test_exp2_benchmark_phase1_sets_project_root(self):
        self.assertIn("PROJECT_ROOT", Path("experiments/exp2/benchmark_phase1.py").read_text(encoding="utf-8"))

    def test_exp2_benchmark_phase2_sets_project_root(self):
        self.assertIn("PROJECT_ROOT", Path("experiments/exp2/benchmark_phase2.py").read_text(encoding="utf-8"))

    def test_exp2_benchmark_phase1_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp2/benchmark_phase1.py").read_text(encoding="utf-8"))

    def test_exp2_benchmark_phase2_adds_src_root_for_source_layout_imports(self):
        self.assertIn("SRC_ROOT", Path("experiments/exp2/benchmark_phase2.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
