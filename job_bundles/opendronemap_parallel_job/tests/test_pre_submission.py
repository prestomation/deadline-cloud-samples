#!/usr/bin/env python3
"""Tests for ODM parallel submission planning and input inventory."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

BUNDLE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BUNDLE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from jpeg_inventory import InventoryError, inventory_images  # noqa: E402
from stage_wrapper import graph_diagnostics  # noqa: E402


def write_jpeg(path: Path, width: int = 640, height: int = 480) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        b"\xff\xd8"
        + b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03"
        + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + b"\xff\xd9"
    )
    path.write_bytes(payload)


def snapshot_tree(path: Path) -> list[tuple[str, int, int]]:
    return [
        (
            candidate.relative_to(path).as_posix(),
            candidate.stat().st_size,
            candidate.stat().st_mtime_ns,
        )
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file()
    ]


class HookHarness:
    def __init__(self, test_case: unittest.TestCase):
        self.test_case = test_case
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.images = self.root / "input images"
        self.images.mkdir()
        self.output = self.root / "output"
        self.intermediate = self.root / "hidden intermediates"

    def close(self) -> None:
        self.temporary.cleanup()

    def metadata(self, **parameters: object) -> dict[str, object]:
        values: dict[str, object] = {
            "InputImages": str(self.images),
            "OutputDir": str(self.output),
            "TargetImagesPerSubmodel": 100,
            "ResourceProfile": "small",
            "FeatureQuality": "low",
            "PointCloudQuality": "lowest",
            "CoordinatorMemoryMiB": 0,
            "SubmodelMemoryMiB": 0,
            "ScratchGiB": 0,
        }
        values.update(parameters)
        return {
            "jobBundleDir": str(BUNDLE_DIR),
            "parameters": values,
            "submissionPayload": {},
        }

    def run(self, *, success: bool = True, **parameters: object):
        environment = os.environ.copy()
        environment["ODM_PARALLEL_INTERMEDIATE_DIR"] = str(self.intermediate)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "expand_parallel_job.py")],
            input=json.dumps(self.metadata(**parameters)),
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        if success:
            self.test_case.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            return result, payload, yaml.safe_load(payload["template"])
        self.test_case.assertNotEqual(result.returncode, 0, result.stdout)
        return result


class TestJpegInventory(unittest.TestCase):
    def test_recursive_inventory_and_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_jpeg(root / "A.JPG", 100, 200)
            write_jpeg(root / "nested" / "b.jpeg", 300, 400)
            (root / "notes.txt").write_text("ignored", encoding="utf-8")
            records = inventory_images(root, calculate_hashes=False)
            self.assertEqual(
                [record["relative_path"] for record in records],
                ["A.JPG", "nested/b.jpeg"],
            )
            self.assertEqual(records[0]["width"], 100)
            self.assertEqual(records[1]["height"], 400)

    def test_corrupt_jpeg_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jpg"
            path.write_bytes(b"not-a-jpeg")
            with self.assertRaisesRegex(InventoryError, "not a JPEG"):
                inventory_images(Path(temporary), calculate_hashes=False)

    def test_duplicate_flattened_name_rejected_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_jpeg(root / "one" / "image.JPG")
            write_jpeg(root / "two" / "IMAGE.jpg")
            with self.assertRaisesRegex(InventoryError, "duplicate staged image name"):
                inventory_images(root, calculate_hashes=False)

    @unittest.skipIf(os.name == "nt", "symlink creation requires Windows privileges")
    def test_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.jpg"
            write_jpeg(target)
            (root / "link.jpg").symlink_to(target)
            with self.assertRaisesRegex(InventoryError, "symlinks are not supported"):
                inventory_images(root, calculate_hashes=False)

    def test_duplicate_content_rejected_by_worker_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_jpeg(root / "one.jpg")
            shutil.copyfile(root / "one.jpg", root / "two.jpg")
            with self.assertRaisesRegex(InventoryError, "duplicate image content"):
                inventory_images(root, calculate_hashes=True)


class TestSubmissionHook(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = HookHarness(self)

    def tearDown(self) -> None:
        self.harness.close()

    def add_images(self, count: int) -> None:
        for index in range(count):
            write_jpeg(self.harness.images / f"image_{index:04d}.jpg")

    @staticmethod
    def step(template: dict[str, object], name: str) -> dict[str, object]:
        return next(step for step in template["steps"] if step["name"] == name)

    def task_range(self, template: dict[str, object], name: str) -> list[int]:
        step = self.step(template, name)
        return step["parameterSpace"]["taskParameterDefinitions"][0]["range"]

    def test_one_task_and_hidden_overrides(self) -> None:
        self.add_images(2)
        result, payload, template = self.harness.run(TargetImagesPerSubmodel=100)
        self.assertEqual(self.task_range(template, "ReconstructSubmodels"), [0])
        self.assertEqual(self.task_range(template, "ProcessSubmodels"), [0])
        self.assertEqual(payload["parameters"]["ExpectedImageCount"], 2)
        self.assertEqual(payload["parameters"]["ExpectedSubmodelCount"], 1)
        self.assertEqual(
            Path(payload["parameters"]["IntermediateDir"]),
            self.harness.intermediate.resolve(),
        )
        self.assertIn("ODM preflight:", result.stderr)

    def test_several_tasks_expand_both_ranges_identically(self) -> None:
        self.add_images(5)
        _, _, template = self.harness.run(TargetImagesPerSubmodel=2)
        expected = [0, 1, 2]
        self.assertEqual(self.task_range(template, "ReconstructSubmodels"), expected)
        self.assertEqual(self.task_range(template, "ProcessSubmodels"), expected)

    def test_1024_tasks(self) -> None:
        self.add_images(2048)
        _, _, template = self.harness.run(
            TargetImagesPerSubmodel=2, ResourceProfile="large"
        )
        task_range = self.task_range(template, "ReconstructSubmodels")
        self.assertEqual(len(task_range), 1024)
        self.assertEqual(task_range[0], 0)
        self.assertEqual(task_range[-1], 1023)

    def test_1025_tasks_rejected_with_minimum_target(self) -> None:
        self.add_images(2050)
        result = self.harness.run(
            success=False, TargetImagesPerSubmodel=2, ResourceProfile="large"
        )
        self.assertIn("1025 submodels", result.stderr)
        self.assertIn("at least 3", result.stderr)

    def test_missing_and_empty_input_rejected(self) -> None:
        result = self.harness.run(success=False)
        self.assertIn("no supported JPEG", result.stderr)
        result = self.harness.run(
            success=False, InputImages=str(self.harness.root / "missing")
        )
        self.assertIn("does not exist", result.stderr)

    def test_spaces_unicode_and_nested_paths(self) -> None:
        write_jpeg(self.harness.images / "nested folder" / "caf\u00e9 image.JPG")
        _, payload, _ = self.harness.run()
        self.assertEqual(payload["parameters"]["ExpectedImageCount"], 1)

    def test_manual_resource_overrides_rewrite_requirements(self) -> None:
        self.add_images(10)
        _, payload, template = self.harness.run(
            CoordinatorMemoryMiB=24576,
            SubmodelMemoryMiB=12288,
            ScratchGiB=75,
        )
        self.assertEqual(payload["parameters"]["PlannedCoordinatorMemoryMiB"], 24576)
        self.assertEqual(payload["parameters"]["PlannedSubmodelMemoryMiB"], 12288)
        for step in template["steps"]:
            amounts = {
                value["name"]: value["min"]
                for value in step["hostRequirements"]["amounts"]
            }
            expected_memory = (
                12288 if step["name"] in {"ReconstructSubmodels", "ProcessSubmodels"}
                else 24576
            )
            self.assertEqual(amounts["amount.worker.memory"], expected_memory)
            self.assertEqual(amounts["amount.OpenDroneMapScratchGiB"], 75)

    def test_every_step_has_dedicated_fleet_requirements(self) -> None:
        self.add_images(4)
        _, _, template = self.harness.run()
        for step in template["steps"]:
            attributes = {
                value["name"]: value["anyOf"]
                for value in step["hostRequirements"]["attributes"]
            }
            amounts = {
                value["name"]: value["min"]
                for value in step["hostRequirements"]["amounts"]
            }
            self.assertEqual(attributes["attr.worker.os.family"], ["linux"])
            self.assertEqual(attributes["attr.worker.cpu.arch"], ["x86_64"])
            self.assertEqual(
                attributes["attr.OpenDroneMap"], ["docker_3_6_1"]
            )
            self.assertGreaterEqual(amounts["amount.worker.vcpu"], 1)
            self.assertGreaterEqual(amounts["amount.worker.memory"], 4096)
            self.assertGreaterEqual(amounts["amount.OpenDroneMapScratchGiB"], 20)

    def test_every_stage_receives_local_session_working_directory(self) -> None:
        self.add_images(4)
        _, _, template = self.harness.run()
        for step in template["steps"]:
            args = step["script"]["actions"]["onRun"]["args"]
            self.assertEqual(args[6], "{{Session.WorkingDirectory}}")

    def test_steps_directly_depend_on_every_required_attachment_producer(self) -> None:
        self.add_images(4)
        _, _, template = self.harness.run()
        expected = {
            "PrepareSurvey": set(),
            "ReconstructSubmodels": {"PrepareSurvey"},
            "AlignSubmodels": {"PrepareSurvey", "ReconstructSubmodels"},
            "ProcessSubmodels": {
                "PrepareSurvey",
                "ReconstructSubmodels",
                "AlignSubmodels",
            },
            "MergeSurvey": {
                "PrepareSurvey",
                "ReconstructSubmodels",
                "AlignSubmodels",
                "ProcessSubmodels",
            },
        }
        for step in template["steps"]:
            dependencies = {
                dependency["dependsOn"] for dependency in step.get("dependencies", [])
            }
            self.assertEqual(dependencies, expected[step["name"]])

    def test_hook_does_not_modify_input_or_bundle(self) -> None:
        self.add_images(3)
        before_input = snapshot_tree(self.harness.images)
        before_bundle = snapshot_tree(BUNDLE_DIR)
        self.harness.run()
        self.assertEqual(snapshot_tree(self.harness.images), before_input)
        self.assertEqual(snapshot_tree(BUNDLE_DIR), before_bundle)
        self.assertFalse(self.harness.intermediate.exists())

    def test_no_arbitrary_execution_or_mutable_identity_parameters(self) -> None:
        with (BUNDLE_DIR / "template.yaml").open(encoding="utf-8") as stream:
            template = yaml.safe_load(stream)
        names = {definition["name"].lower() for definition in template["parameterDefinitions"]}
        forbidden = {"url", "command", "arguments", "args", "image", "digest"}
        self.assertTrue(names.isdisjoint(forbidden))


class TestPartitionDiagnostics(unittest.TestCase):
    def test_connected_graph_uses_shared_image_threshold(self) -> None:
        diagnostics = graph_diagnostics([[0, 1, 2], [1, 2, 3], [2, 3, 4]], 2)
        self.assertTrue(diagnostics["connected"])
        self.assertEqual(diagnostics["components"], [[0, 1, 2]])

    def test_disconnected_graph(self) -> None:
        diagnostics = graph_diagnostics([[0, 1], [1, 2], [10, 11]], 1)
        self.assertFalse(diagnostics["connected"])
        self.assertEqual(diagnostics["components"], [[0, 1], [2]])


if __name__ == "__main__":
    unittest.main()
