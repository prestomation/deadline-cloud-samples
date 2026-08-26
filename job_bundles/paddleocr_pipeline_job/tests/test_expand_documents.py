#!/usr/bin/env python3
"""Tests for PaddleOCR pipeline inventory and hook expansion."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

BUNDLE = Path(__file__).resolve().parents[1]


class TestExpandDocuments(unittest.TestCase):
    def run_hook(self, directory: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUNDLE / "scripts" / "expand_documents.py")],
            input=json.dumps({"jobBundleDir": str(BUNDLE), "parameters": {"InputDocuments": str(directory), "OutputDir": str(directory / "output")}}),
            text=True, capture_output=True, check=False,
        )

    def test_expands_identical_stable_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.pdf").write_bytes(b"x")
            (root / "nested").mkdir()
            (root / "nested" / "b.png").write_bytes(b"x")
            result = self.run_hook(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            template = yaml.safe_load(payload["template"])
            ranges = [step["parameterSpace"]["taskParameterDefinitions"][0]["range"] for step in template["steps"] if step["name"] != "AssembleResults"]
            self.assertEqual(ranges, [[0, 1], [0, 1]])
            self.assertEqual(payload["parameters"]["DocumentCount"], 2)

    def test_rejects_empty_and_unsupported_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertNotEqual(self.run_hook(root).returncode, 0)
            (root / "bad.txt").write_text("x", encoding="utf-8")
            self.assertIn("unsupported", self.run_hook(root).stderr)


if __name__ == "__main__":
    unittest.main()
