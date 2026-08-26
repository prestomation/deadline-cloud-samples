#!/usr/bin/env python3
"""Write a machine-readable manifest for an OpenDroneMap sample run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path

ODM_VERSION = "3.6.1"
ODM_IMAGE = (
    "opendronemap/odm:3.6.1@"
    "sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
)
DATASET_REPOSITORY = "https://github.com/pierotofy/drone_dataset_brighton_beach"
DATASET_COMMIT = "9506a9bf09c9678b7d0b80b014af5b606c8a7255"
DATASET_ARCHIVE_SHA256 = (
    "4ec7c469ae9242bd7a08eec46bb5b2442bcae904e43c3b7c9d48d5de2fb538a7"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--status", required=True, choices=("success", "failed", "canceled"))
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--container-exit-code", default="")
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", required=True)
    parser.add_argument("--duration-seconds", required=True, type=int)
    parser.add_argument("--orthophoto-resolution", required=True, type=int)
    parser.add_argument("--feature-quality", required=True)
    parser.add_argument("--point-cloud-quality", required=True)
    parser.add_argument("--generate-dsm", required=True, choices=("True", "False"))
    parser.add_argument("--generate-dtm", required=True, choices=("True", "False"))
    parser.add_argument("--max-concurrency", required=True, type=int)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_role(relative_path: str) -> str:
    if relative_path == "odm_orthophoto/odm_orthophoto.tif":
        return "orthophoto"
    if relative_path == "odm_georeferencing/odm_georeferenced_model.laz":
        return "point_cloud"
    if relative_path == "odm_dem/dsm.tif":
        return "dsm"
    if relative_path == "odm_dem/dtm.tif":
        return "dtm"
    if relative_path.startswith("odm_texturing/"):
        return "textured_model"
    if relative_path == "odm_report/report.pdf":
        return "processing_report"
    if relative_path == "odm.log":
        return "processing_log"
    return "supporting_file"


def collect_artifacts(result_dir: Path) -> list[dict[str, object]]:
    artifacts = []
    for path in sorted(result_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative_path = path.relative_to(result_dir).as_posix()
        artifacts.append(
            {
                "path": relative_path,
                "role": artifact_role(relative_path),
                "sha256": sha256(path),
                "sizeBytes": path.stat().st_size,
            }
        )
    return artifacts


def main() -> int:
    args = parse_args()
    args.result_dir.mkdir(parents=True, exist_ok=True)
    container_exit_code = (
        int(args.container_exit_code) if args.container_exit_code else None
    )
    document = {
        "schemaVersion": 1,
        "application": {
            "name": "OpenDroneMap",
            "version": ODM_VERSION,
            "containerImage": ODM_IMAGE,
        },
        "dataset": {
            "name": "Brighton Beach aerial survey",
            "repository": DATASET_REPOSITORY,
            "commit": DATASET_COMMIT,
            "archiveSha256": DATASET_ARCHIVE_SHA256,
            "license": "BSD-2-Clause",
            "sourceImageCount": 18,
        },
        "parameters": {
            "orthophotoResolutionCmPerPixel": args.orthophoto_resolution,
            "featureQuality": args.feature_quality,
            "pointCloudQuality": args.point_cloud_quality,
            "generateDsm": args.generate_dsm == "True",
            "generateDtm": args.generate_dtm == "True",
            "maxConcurrency": args.max_concurrency,
        },
        "runtime": {
            "status": args.status,
            "exitCode": args.exit_code,
            "containerExitCode": container_exit_code,
            "startedAt": args.started_at,
            "finishedAt": args.finished_at,
            "durationSeconds": args.duration_seconds,
            "host": {
                "architecture": platform.machine(),
                "operatingSystem": platform.system(),
                "workerUser": os.environ.get("USER", ""),
            },
        },
        "artifacts": collect_artifacts(args.result_dir),
    }
    output_path = args.result_dir / "manifest.json"
    temporary_path = args.result_dir / ".manifest.json.tmp"
    temporary_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_path.replace(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
