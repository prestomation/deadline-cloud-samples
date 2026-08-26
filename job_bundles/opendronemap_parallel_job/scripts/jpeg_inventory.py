#!/usr/bin/env python3
"""Deterministic, dependency-free JPEG inventory shared by hook and worker."""

from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
from typing import Any

JPEG_EXTENSIONS = {".jpg", ".jpeg"}
MAX_RELATIVE_PATH_BYTES = 240
SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


class InventoryError(ValueError):
    """Raised when an input directory violates the supported survey contract."""


def read_jpeg_dimensions(path: Path) -> tuple[int, int]:
    """Read JPEG dimensions from marker segments without decoding image pixels."""
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"\xff\xd8":
                raise InventoryError(f"not a JPEG file: {path}")

            while True:
                prefix = stream.read(1)
                if not prefix:
                    break
                if prefix != b"\xff":
                    continue
                marker_bytes = stream.read(1)
                while marker_bytes == b"\xff":
                    marker_bytes = stream.read(1)
                if not marker_bytes:
                    break
                marker = marker_bytes[0]
                if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                    continue
                if marker == 0xDA:
                    break

                length_bytes = stream.read(2)
                if len(length_bytes) != 2:
                    raise InventoryError(f"truncated JPEG segment: {path}")
                segment_length = struct.unpack(">H", length_bytes)[0]
                if segment_length < 2:
                    raise InventoryError(f"invalid JPEG segment length: {path}")

                if marker in SOF_MARKERS:
                    payload = stream.read(segment_length - 2)
                    if len(payload) < 5:
                        raise InventoryError(f"truncated JPEG size segment: {path}")
                    height, width = struct.unpack(">HH", payload[1:5])
                    if width <= 0 or height <= 0:
                        raise InventoryError(f"JPEG has zero dimensions: {path}")
                    return width, height

                stream.seek(segment_length - 2, os.SEEK_CUR)
    except OSError as exc:
        raise InventoryError(f"cannot read JPEG {path}: {exc}") from exc

    raise InventoryError(f"JPEG has no supported size marker: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_images(root: Path, *, calculate_hashes: bool) -> list[dict[str, Any]]:
    """Inventory supported JPEGs and enforce portable flattening rules."""
    if not root.exists():
        raise InventoryError(f"input image directory does not exist: {root}")
    if not root.is_dir():
        raise InventoryError(f"input image path is not a directory: {root}")
    if root.is_symlink():
        raise InventoryError(f"input image directory must not be a symlink: {root}")

    records: list[dict[str, Any]] = []
    staged_names: dict[str, str] = {}
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            candidate = current / name
            if candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                raise InventoryError(f"directory symlinks are not supported: {relative}")

        for name in file_names:
            candidate = current / name
            if candidate.is_symlink():
                relative = candidate.relative_to(root).as_posix()
                raise InventoryError(f"file symlinks are not supported: {relative}")
            if candidate.suffix.lower() not in JPEG_EXTENSIONS:
                continue

            relative = candidate.relative_to(root).as_posix()
            if len(relative.encode("utf-8")) > MAX_RELATIVE_PATH_BYTES:
                raise InventoryError(
                    f"relative image path exceeds {MAX_RELATIVE_PATH_BYTES} UTF-8 bytes: "
                    f"{relative}"
                )
            staged_key = candidate.name.casefold()
            if staged_key in staged_names:
                raise InventoryError(
                    "duplicate staged image name after flattening: "
                    f"{staged_names[staged_key]} and {relative}"
                )
            staged_names[staged_key] = relative

            width, height = read_jpeg_dimensions(candidate)
            record: dict[str, Any] = {
                "relative_path": relative,
                "staged_name": candidate.name,
                "bytes": candidate.stat().st_size,
                "width": width,
                "height": height,
                "megapixels": width * height / 1_000_000,
            }
            if calculate_hashes:
                record["sha256"] = sha256_file(candidate)
            records.append(record)

    records.sort(key=lambda item: (item["relative_path"].casefold(), item["relative_path"]))
    if not records:
        raise InventoryError(
            "input directory contains no supported JPEG files (.jpg or .jpeg, case-insensitive)"
        )

    if calculate_hashes:
        by_hash: dict[str, str] = {}
        for record in records:
            digest = record["sha256"]
            if digest in by_hash:
                raise InventoryError(
                    "duplicate image content is not supported: "
                    f"{by_hash[digest]} and {record['relative_path']}"
                )
            by_hash[digest] = record["relative_path"]
    return records


def inventory_metrics(records: list[dict[str, Any]]) -> dict[str, int | float]:
    return {
        "image_count": len(records),
        "source_bytes": sum(int(record["bytes"]) for record in records),
        "source_megapixels": sum(float(record["megapixels"]) for record in records),
        "maximum_megapixels": max(float(record["megapixels"]) for record in records),
    }
