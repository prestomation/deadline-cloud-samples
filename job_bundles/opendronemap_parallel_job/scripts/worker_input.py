#!/usr/bin/env python3
"""Validate and stage the attached input survey for the prepare task."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jpeg_inventory import InventoryError, inventory_images, inventory_metrics

PROJECT_NAME = "survey"


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-images", type=Path, required=True)
    parser.add_argument("--intermediate-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--expected-submodels", type=int, required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--expected-megapixels", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.expected_count <= 0 or args.expected_submodels <= 0:
        print(
            "openjd_fail: submission hook did not expand image and submodel counts",
            file=sys.stderr,
        )
        return 64

    try:
        records = inventory_images(args.input_images, calculate_hashes=True)
    except InventoryError as exc:
        print(f"openjd_fail: {exc}", file=sys.stderr)
        return 65
    metrics = inventory_metrics(records)
    if metrics["image_count"] != args.expected_count:
        print(
            "openjd_fail: worker image count does not match submission preflight "
            f"({metrics['image_count']} != {args.expected_count})",
            file=sys.stderr,
        )
        return 65
    if metrics["source_bytes"] != args.expected_bytes:
        print(
            "openjd_fail: worker source bytes do not match submission preflight "
            f"({metrics['source_bytes']} != {args.expected_bytes})",
            file=sys.stderr,
        )
        return 65
    if abs(float(metrics["source_megapixels"]) - args.expected_megapixels) > 0.001:
        print(
            "openjd_fail: worker megapixels do not match submission preflight "
            f"({metrics['source_megapixels']:.6f} != {args.expected_megapixels:.6f})",
            file=sys.stderr,
        )
        return 65

    project_dir = args.intermediate_dir / PROJECT_NAME
    if project_dir.exists():
        shutil.rmtree(project_dir)
    (project_dir / "images").mkdir(parents=True)
    (project_dir / "deadline" / "manifests").mkdir(parents=True)
    (args.intermediate_dir / "logs").mkdir(parents=True, exist_ok=True)
    (args.intermediate_dir / "metrics").mkdir(parents=True, exist_ok=True)

    for record in records:
        source = args.input_images / record["relative_path"]
        destination = project_dir / "images" / record["staged_name"]
        shutil.copyfile(source, destination)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(args.input_images),
        "expected_submodels": args.expected_submodels,
        "metrics": metrics,
        "images": records,
    }
    atomic_json(project_dir / "deadline" / "manifests" / "input.json", manifest)
    print(
        f"Staged {metrics['image_count']} images and "
        f"{metrics['source_bytes']} bytes into the attachment workspace"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
