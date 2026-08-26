#!/usr/bin/env python3
"""Tests for worker-side hook agreement and deterministic staging."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BUNDLE_DIR / "scripts" / "worker_input.py"


def write_jpeg(path: Path, width: int = 640, height: int = 480, suffix: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\xff\xd8\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + suffix
        + b"\xff\xd9"
    )


class TestWorkerInput(unittest.TestCase):
    def run_worker(
        self,
        images: Path,
        intermediate: Path,
        *,
        expected_count: int,
        expected_bytes: int,
        expected_megapixels: float,
        expected_submodels: int = 1,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input-images",
                str(images),
                "--intermediate-dir",
                str(intermediate),
                "--expected-count",
                str(expected_count),
                "--expected-submodels",
                str(expected_submodels),
                "--expected-bytes",
                str(expected_bytes),
                "--expected-megapixels",
                str(expected_megapixels),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_stages_flat_images_and_sorted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            intermediate = root / "intermediate"
            first = images / "z" / "z.jpg"
            second = images / "a.jpg"
            write_jpeg(first, suffix=b"z")
            write_jpeg(second, suffix=b"a")
            source_bytes = first.stat().st_size + second.stat().st_size
            result = self.run_worker(
                images,
                intermediate,
                expected_count=2,
                expected_bytes=source_bytes,
                expected_megapixels=0.6144,
                expected_submodels=2,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            staged = sorted(
                path.name for path in (intermediate / "survey" / "images").iterdir()
            )
            self.assertEqual(staged, ["a.jpg", "z.jpg"])
            manifest_path = (
                intermediate / "survey" / "deadline" / "manifests" / "input.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [record["relative_path"] for record in manifest["images"]],
                ["a.jpg", "z/z.jpg"],
            )
            self.assertEqual(manifest["expected_submodels"], 2)

    def test_unexpanded_sentinel_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            result = self.run_worker(
                images,
                root / "intermediate",
                expected_count=0,
                expected_bytes=0,
                expected_megapixels=0,
                expected_submodels=0,
            )
            self.assertEqual(result.returncode, 64)
            self.assertIn("did not expand", result.stderr)

    def test_hook_worker_count_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            image = images / "one.jpg"
            write_jpeg(image)
            result = self.run_worker(
                images,
                root / "intermediate",
                expected_count=2,
                expected_bytes=image.stat().st_size,
                expected_megapixels=0.3072,
            )
            self.assertEqual(result.returncode, 65)
            self.assertIn("image count does not match", result.stderr)


if __name__ == "__main__":
    unittest.main()
