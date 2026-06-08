from __future__ import annotations

import sys
import unittest
from pathlib import Path


TRAIN_ROOT = Path(__file__).resolve().parents[1]
if str(TRAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(TRAIN_ROOT))

from rollout import _extract_python_code


VALID_SCRIPT = """from __future__ import annotations

LABELS = ["用量异常"]


def predict_labels(features: dict) -> list[str]:
    return LABELS


def format_prediction(labels: list[str]) -> str:
    return "、".join(labels)
"""


class ExtractPythonCodeTest(unittest.TestCase):
    def test_extracts_unfenced_code_after_nga_explanation(self) -> None:
        response = "I'll generate the python script based on the rules.\n\n" + VALID_SCRIPT

        code = _extract_python_code(response)

        self.assertNotIn("I'll generate", code)
        self.assertIn("LABELS =", code)
        compile(code, "<generated>", "exec")

    def test_extracts_code_with_trailing_explanation(self) -> None:
        response = VALID_SCRIPT + "\nThis script follows the requested interface."

        code = _extract_python_code(response)

        self.assertNotIn("This script follows", code)
        compile(code, "<generated>", "exec")

    def test_extracts_non_python_fenced_code(self) -> None:
        response = f"Here is the script:\n```\n{VALID_SCRIPT}```\n"

        code = _extract_python_code(response)

        self.assertNotIn("Here is the script", code)
        compile(code, "<generated>", "exec")

    def test_rejects_response_without_required_functions(self) -> None:
        with self.assertRaisesRegex(ValueError, "predict_labels"):
            _extract_python_code("I'll generate it later.")


if __name__ == "__main__":
    unittest.main()
