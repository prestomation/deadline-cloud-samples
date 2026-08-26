#!/usr/bin/env python3
"""Focused, dependency-free tests for the PaddleOCR orchestration script."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paddleocr_job", BUNDLE / "scripts" / "paddleocr_job.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class TestInventory(unittest.TestCase):
    def test_case_normalized_duplicate_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.DocumentError, "duplicate"):
            MODULE.ensure_unique_relative_paths(["one/a.pdf", "ONE/A.PDF"])

    def test_supported_files_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "b.PDF").write_bytes(b"%PDF-")
            (root / "nested" / "a.png").write_bytes(b"image")
            records = MODULE.inventory_documents(root)
            self.assertEqual([record["relative_path"] for record in records], ["b.PDF", "nested/a.png"])
            self.assertNotEqual(records[0]["document_id"], records[1]["document_id"])

    def test_empty_unsupported_duplicate_and_limit_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(MODULE.DocumentError, "no supported"):
                MODULE.inventory_documents(root)
            (root / "bad.txt").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(MODULE.DocumentError, "unsupported"):
                MODULE.inventory_documents(root)
            (root / "bad.txt").unlink()
            for index in range(MODULE.MAX_DOCUMENTS + 1):
                (root / f"document-{index:04d}.pdf").write_bytes(b"x")
            with self.assertRaisesRegex(MODULE.DocumentError, "limit"):
                MODULE.inventory_documents(root)


if __name__ == "__main__":
    unittest.main()
