#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Expand PaddleOCR pipeline task ranges from the selected input directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from paddleocr_job import DocumentError, MAX_DOCUMENTS, inventory_documents


def fail(message: str) -> "None":
    print(f"expand_documents: {message}", file=sys.stderr)
    raise SystemExit(1)


def parameter(template: dict[str, Any], metadata: dict[str, Any], name: str) -> Any:
    supplied = metadata.get("parameters", {}).get(name)
    if supplied is not None:
        return supplied
    for definition in template["parameterDefinitions"]:
        if definition["name"] == name:
            return definition.get("default")
    fail(f"template is missing parameter {name}")


def main() -> None:
    try:
        metadata = json.load(sys.stdin)
        bundle = Path(metadata["jobBundleDir"]).resolve()
        template = yaml.safe_load((bundle / "template.yaml").read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        fail(f"could not load submission metadata or template: {exc}")
    input_value = parameter(template, metadata, "InputDocuments")
    if not input_value:
        fail("InputDocuments is required")
    source = Path(str(input_value))
    if not source.is_absolute():
        source = bundle / source
    try:
        documents = inventory_documents(source.resolve(strict=False))
    except DocumentError as exc:
        fail(str(exc))
    if len(documents) > MAX_DOCUMENTS:
        fail(f"more than {MAX_DOCUMENTS} tasks are not supported")
    steps = {step["name"]: step for step in template.get("steps", [])}
    for name in ("RenderDocuments", "ParseDocuments"):
        definition = steps.get(name, {}).get("parameterSpace", {}).get("taskParameterDefinitions", [])
        if len(definition) != 1 or definition[0].get("name") != "DocumentIndex":
            fail(f"{name} does not have the expected DocumentIndex range")
        definition[0]["range"] = list(range(len(documents)))
    overrides = {
        "DocumentCount": len(documents),
        "IntermediateDir": str(
            Path(str(parameter(template, metadata, "OutputDir"))).parent
            / ".paddleocr-intermediates"
        ),
    }
    print(json.dumps({"template": yaml.safe_dump(template, sort_keys=False), "parameters": overrides}))
    print(f"PaddleOCR preflight: {len(documents)} documents", file=sys.stderr)


if __name__ == "__main__":
    main()
