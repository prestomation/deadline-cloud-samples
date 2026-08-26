#!/usr/bin/env python3
"""Expand ODM fan-out ranges and resource requirements before submission."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from jpeg_inventory import InventoryError, inventory_images, inventory_metrics

FAN_OUT_STEPS = {"ReconstructSubmodels", "ProcessSubmodels"}
COORDINATOR_STEPS = {"PrepareSurvey", "AlignSubmodels", "MergeSurvey"}
ALL_STEPS = FAN_OUT_STEPS | COORDINATOR_STEPS
MAX_TASKS = 1024

PROFILES = {
    "small": {
        "max_images": 100,
        "max_megapixels": 2500,
        "coordinator_vcpus": 2,
        "coordinator_memory_mib": 8192,
        "coordinator_scratch_gib": 20,
        "submodel_vcpus": 2,
        "submodel_memory_mib": 8192,
        "submodel_scratch_gib": 20,
    },
    "medium": {
        "max_images": 600,
        "max_megapixels": 20000,
        "coordinator_vcpus": 8,
        "coordinator_memory_mib": 32768,
        "coordinator_scratch_gib": 200,
        "submodel_vcpus": 4,
        "submodel_memory_mib": 16384,
        "submodel_scratch_gib": 100,
    },
    "large": {
        "max_images": 1200,
        "max_megapixels": 40000,
        "coordinator_vcpus": 16,
        "coordinator_memory_mib": 65536,
        "coordinator_scratch_gib": 500,
        "submodel_vcpus": 8,
        "submodel_memory_mib": 32768,
        "submodel_scratch_gib": 250,
    },
}


def fail(message: str) -> "NoReturn":
    print(f"expand_parallel_job: {message}", file=sys.stderr)
    raise SystemExit(1)


def parameter_default(template: dict[str, Any], name: str) -> Any:
    for definition in template.get("parameterDefinitions", []):
        if definition.get("name") == name:
            return definition.get("default")
    fail(f"template has no parameter named {name}")


def parameter(metadata: dict[str, Any], template: dict[str, Any], name: str) -> Any:
    value = metadata.get("parameters", {}).get(name)
    return parameter_default(template, name) if value is None else value


def integer_parameter(
    metadata: dict[str, Any], template: dict[str, Any], name: str, minimum: int
) -> int:
    try:
        value = int(parameter(metadata, template, name))
    except (TypeError, ValueError):
        fail(f"{name} must be an integer")
    if value < minimum:
        fail(f"{name} must be at least {minimum}")
    return value


def select_resources(
    requested_profile: str,
    metrics: dict[str, int | float],
    feature_quality: str,
    point_cloud_quality: str,
    coordinator_override: int,
    submodel_override: int,
    scratch_override: int,
) -> tuple[str, dict[str, int | float]]:
    if requested_profile == "auto":
        selected = None
        for profile_name in ("small", "medium", "large"):
            profile = PROFILES[profile_name]
            if (
                metrics["image_count"] <= profile["max_images"]
                and metrics["source_megapixels"] <= profile["max_megapixels"]
            ):
                selected = profile_name
                break
        if selected is None:
            fail(
                "input is outside the measured automatic resource envelope "
                f"({metrics['image_count']} images, "
                f"{metrics['source_megapixels']:.1f} megapixels); select a reviewed "
                "fixed profile after benchmarking this survey"
            )
    elif requested_profile in PROFILES:
        selected = requested_profile
    else:
        fail(f"unsupported ResourceProfile: {requested_profile}")

    resources = dict(PROFILES[selected])
    quality_rank = {"lowest": 0, "low": 1, "medium": 2, "high": 3, "ultra": 4}
    if max(quality_rank[feature_quality], quality_rank[point_cloud_quality]) >= 3:
        resources["coordinator_memory_mib"] = max(
            int(resources["coordinator_memory_mib"]), 32768
        )
        resources["submodel_memory_mib"] = max(int(resources["submodel_memory_mib"]), 16384)

    if coordinator_override:
        if coordinator_override < 4096:
            fail("CoordinatorMemoryMiB override must be zero or at least 4096")
        resources["coordinator_memory_mib"] = coordinator_override
    if submodel_override:
        if submodel_override < 4096:
            fail("SubmodelMemoryMiB override must be zero or at least 4096")
        resources["submodel_memory_mib"] = submodel_override
    if scratch_override:
        if scratch_override < 20:
            fail("ScratchGiB override must be zero or at least 20")
        resources["coordinator_scratch_gib"] = scratch_override
        resources["submodel_scratch_gib"] = scratch_override
    return selected, resources


def update_requirement(step: dict[str, Any], resources: dict[str, int | float]) -> None:
    role = "submodel" if step["name"] in FAN_OUT_STEPS else "coordinator"
    values = {
        "amount.worker.vcpu": int(resources[f"{role}_vcpus"]),
        "amount.worker.memory": int(resources[f"{role}_memory_mib"]),
        "amount.OpenDroneMapScratchGiB": int(resources[f"{role}_scratch_gib"]),
    }
    amounts = {
        requirement["name"]: requirement
        for requirement in step["hostRequirements"].get("amounts", [])
    }
    if set(amounts) != set(values):
        fail(f"step {step['name']} does not have the expected resource requirements")
    for name, value in values.items():
        amounts[name]["min"] = value


def update_hidden_default(template: dict[str, Any], name: str, value: Any) -> None:
    for definition in template["parameterDefinitions"]:
        if definition["name"] == name:
            definition["default"] = value
            return
    fail(f"template has no hidden parameter named {name}")


def main() -> None:
    try:
        metadata = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail(f"could not parse hook metadata: {exc}")

    bundle_dir = Path(metadata["jobBundleDir"]).resolve()
    with (bundle_dir / "template.yaml").open(encoding="utf-8") as stream:
        template = yaml.safe_load(stream)

    input_value = parameter(metadata, template, "InputImages")
    if not input_value:
        fail("InputImages is required")
    input_dir = Path(str(input_value))
    if not input_dir.is_absolute():
        input_dir = bundle_dir / input_dir
    input_dir = input_dir.resolve(strict=False)

    try:
        records = inventory_images(input_dir, calculate_hashes=False)
    except InventoryError as exc:
        fail(str(exc))
    metrics = inventory_metrics(records)

    target = integer_parameter(metadata, template, "TargetImagesPerSubmodel", 2)
    submodel_count = math.ceil(int(metrics["image_count"]) / target)
    if submodel_count > MAX_TASKS:
        minimum_target = math.ceil(int(metrics["image_count"]) / MAX_TASKS)
        fail(
            f"plan needs {submodel_count} submodels, above OpenJD's {MAX_TASKS}-task "
            f"limit; set TargetImagesPerSubmodel to at least {minimum_target}"
        )

    feature_quality = str(parameter(metadata, template, "FeatureQuality"))
    point_cloud_quality = str(parameter(metadata, template, "PointCloudQuality"))
    quality_values = {"ultra", "high", "medium", "low", "lowest"}
    if feature_quality not in quality_values or point_cloud_quality not in quality_values:
        fail("feature and point-cloud quality values must be ODM quality names")

    requested_profile = str(parameter(metadata, template, "ResourceProfile"))
    coordinator_override = integer_parameter(
        metadata, template, "CoordinatorMemoryMiB", 0
    )
    submodel_override = integer_parameter(metadata, template, "SubmodelMemoryMiB", 0)
    scratch_override = integer_parameter(metadata, template, "ScratchGiB", 0)
    selected_profile, resources = select_resources(
        requested_profile,
        metrics,
        feature_quality,
        point_cloud_quality,
        coordinator_override,
        submodel_override,
        scratch_override,
    )

    steps = {step["name"]: step for step in template.get("steps", [])}
    if set(steps) != ALL_STEPS:
        fail("template step set does not match the five-stage ODM graph")
    task_range = list(range(submodel_count))
    for step_name in FAN_OUT_STEPS:
        definitions = steps[step_name]["parameterSpace"]["taskParameterDefinitions"]
        if len(definitions) != 1 or definitions[0]["name"] != "SubmodelIndex":
            fail(f"step {step_name} has an unexpected task parameter definition")
        definitions[0]["range"] = task_range
    for step in steps.values():
        update_requirement(step, resources)

    output_value = str(parameter(metadata, template, "OutputDir"))
    intermediate_override = os.environ.get("ODM_PARALLEL_INTERMEDIATE_DIR")
    if intermediate_override:
        intermediate_dir = Path(intermediate_override).resolve()
    else:
        identity = hashlib.sha256(
            (
                str(input_dir)
                + "\0"
                + output_value
                + "\0"
                + str(os.getpid())
            ).encode("utf-8")
        ).hexdigest()[:16]
        intermediate_dir = (
            Path(tempfile.gettempdir()) / "deadline-odm-parallel" / identity
        ).resolve()

    overrides = {
        "IntermediateDir": str(intermediate_dir),
        "ExpectedImageCount": int(metrics["image_count"]),
        "ExpectedSubmodelCount": submodel_count,
        "ExpectedSourceBytes": int(metrics["source_bytes"]),
        "ExpectedSourceMegapixels": round(float(metrics["source_megapixels"]), 6),
        "PlannedCoordinatorVcpus": int(resources["coordinator_vcpus"]),
        "PlannedSubmodelVcpus": int(resources["submodel_vcpus"]),
        "PlannedCoordinatorMemoryMiB": int(resources["coordinator_memory_mib"]),
        "PlannedSubmodelMemoryMiB": int(resources["submodel_memory_mib"]),
        "PlannedCoordinatorScratchGiB": int(resources["coordinator_scratch_gib"]),
        "PlannedSubmodelScratchGiB": int(resources["submodel_scratch_gib"]),
    }
    for name, value in overrides.items():
        update_hidden_default(template, name, value)

    print(
        "ODM preflight: "
        f"{metrics['image_count']} images, {metrics['source_bytes']} bytes, "
        f"{metrics['source_megapixels']:.1f} MP, {submodel_count} submodels, "
        f"profile {selected_profile}; coordinator "
        f"{resources['coordinator_vcpus']} vCPU/"
        f"{resources['coordinator_memory_mib']} MiB, submodel "
        f"{resources['submodel_vcpus']} vCPU/"
        f"{resources['submodel_memory_mib']} MiB",
        file=sys.stderr,
    )
    print(
        json.dumps(
            {
                "template": yaml.safe_dump(template, sort_keys=False),
                "parameters": overrides,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
