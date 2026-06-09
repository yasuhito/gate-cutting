import ast
from pathlib import Path
import unittest


class TestStyleTest(unittest.TestCase):
    def test_each_test_case_has_exactly_one_unittest_assertion(self):
        violations = []
        for path in sorted(Path("tests").glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
                for test_node in [node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test")]:
                    assertion_count = sum(
                        1
                        for node in ast.walk(test_node)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr.startswith("assert")
                    )
                    if assertion_count != 1:
                        violations.append(f"{path}:{class_node.name}.{test_node.name} has {assertion_count} assertions")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
