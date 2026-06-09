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

    def test_exp2_b1_uses_shared_helpers_instead_of_local_stim_and_device_copies(self):
        source_path = Path("experiments/exp2/b1.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        local_defs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertNotIn("ErrorParams", local_defs)

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.cut_selection", imported_modules)
        self.assertIn("gate_cutting.device", imported_modules)
        self.assertIn("gate_cutting.gate_cutting", imported_modules)
        self.assertIn("gate_cutting.stim_backend", imported_modules)

    def test_exp2_b2_mip_uses_cut_selection_helpers(self):
        source_path = Path("experiments/exp2/b2.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        imported_modules = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("gate_cutting.cut_selection", imported_modules)

        source = source_path.read_text(encoding="utf-8")
        self.assertIn("collect_cx_edges", source)
        self.assertIn("cut_targets_from_edges", source)


if __name__ == "__main__":
    unittest.main()
