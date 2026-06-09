import ast
from pathlib import Path
import unittest


class ExperimentRefactorTest(unittest.TestCase):
    def test_exp1_b1_uses_shared_stim_helpers_instead_of_local_copies(self):
        source_path = Path("experiments/exp1/b1.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        local_defs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertNotIn("ErrorParams", local_defs)
        self.assertNotIn("qiskit_to_stim", local_defs)
        self.assertNotIn("append_operation_with_noise", local_defs)

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.gate_cutting", imported_modules)
        self.assertIn("gate_cutting.stim_backend", imported_modules)

    def test_exp2_b1_uses_shared_helpers_instead_of_local_stim_device_and_mip_copies(self):
        source_path = Path("experiments/exp2/b1.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        local_defs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertNotIn("ErrorParams", local_defs)
        self.assertNotIn("MIPCutFinder", local_defs)

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.device", imported_modules)
        self.assertIn("gate_cutting.gate_cutting", imported_modules)
        self.assertIn("gate_cutting.mip", imported_modules)
        self.assertIn("gate_cutting.stim_backend", imported_modules)

    def test_exp2_b2_uses_shared_mip_finder(self):
        source_path = Path("experiments/exp2/b2.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        local_defs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertNotIn("MIPCutFinder", local_defs)

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.mip", imported_modules)

    def test_exp2_check_uses_shared_helpers_instead_of_local_stim_device_and_mip_copies(self):
        source_path = Path("experiments/exp2/check.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        local_defs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertNotIn("ErrorParams", local_defs)
        self.assertNotIn("MIPCutFinder", local_defs)

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.device", imported_modules)
        self.assertIn("gate_cutting.gate_cutting", imported_modules)
        self.assertIn("gate_cutting.mip", imported_modules)
        self.assertIn("gate_cutting.stim_backend", imported_modules)

        source = source_path.read_text(encoding="utf-8")
        self.assertIn("CutTarget", source)
        self.assertIn("cut.qubits", source)

    def test_exp2_benchmarks_import_b2_via_project_package_path(self):
        for source_path in [
            Path("experiments/exp2/benchmark_phase1.py"),
            Path("experiments/exp2/benchmark_phase2.py"),
        ]:
            with self.subTest(path=str(source_path)):
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                imported_modules = {
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                }
                self.assertIn("experiments.exp2.b2", imported_modules)
                self.assertNotIn("b2", imported_modules)

                source = source_path.read_text(encoding="utf-8")
                self.assertIn("PROJECT_ROOT", source)


if __name__ == "__main__":
    unittest.main()
