#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""PaddleOCR document inventory, rendering, parsing, and result assembly."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_DOCUMENTS = 1024
RECOGNITION_MODELS = {
    "ch": "PP-OCRv4_server_rec",
    "en": "en_PP-OCRv4_mobile_rec",
    "japan": "japan_PP-OCRv4_mobile_rec",
    "korean": "korean_PP-OCRv4_mobile_rec",
}


class DocumentError(ValueError):
    """Raised when a document directory does not meet this sample's contract."""


def document_id(relative_path: str) -> str:
    """Return a stable path-safe identifier without exposing the source path."""
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20]


def ensure_unique_relative_paths(relative_paths: list[str]) -> None:
    """Reject source paths that collide after the portable path normalization."""
    seen: dict[str, str] = {}
    for relative in relative_paths:
        key = relative.casefold()
        if key in seen:
            raise DocumentError(
                f"duplicate relative paths after case normalization: {seen[key]} and {relative}"
            )
        seen[key] = relative


def inventory_documents(root: Path) -> list[dict[str, str]]:
    """Return supported files in deterministic relative-path order."""
    if not root.is_dir() or root.is_symlink():
        raise DocumentError(f"InputDocuments must be a non-symlink directory: {root}")
    records: list[dict[str, str]] = []
    relative_paths: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        if any((current_path / name).is_symlink() for name in directories):
            raise DocumentError("directory symlinks are not supported")
        for name in files:
            source = current_path / name
            relative = source.relative_to(root).as_posix()
            if source.is_symlink():
                raise DocumentError(f"file symlinks are not supported: {relative}")
            if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise DocumentError(
                    f"unsupported document type {source.suffix!r}: {relative}; "
                    "supported types are pdf, jpg, jpeg, png, tif, and tiff"
                )
            relative_paths.append(relative)
            records.append(
                {
                    "relative_path": relative,
                    "document_id": document_id(relative),
                    "source_type": source.suffix.lower().lstrip("."),
                }
            )
    ensure_unique_relative_paths(relative_paths)
    records.sort(key=lambda item: (item["relative_path"].casefold(), item["relative_path"]))
    if not records:
        raise DocumentError("InputDocuments contains no supported documents")
    if len(records) > MAX_DOCUMENTS:
        raise DocumentError(
            f"InputDocuments contains {len(records)} documents; the limit is {MAX_DOCUMENTS}"
        )
    return records


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_inventory(root: Path) -> list[dict[str, str]]:
    return inventory_documents(root)


def prepare_document(source_root: Path, record: dict[str, str], destination: Path, dpi: int) -> list[Path]:
    """Render one PDF or normalize one image into ordered PNG page files."""
    source = source_root / record["relative_path"]
    page_dir = destination / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise DocumentError("PyMuPDF is unavailable; job environment setup did not complete") from exc
        document = fitz.open(source)
        try:
            if document.page_count == 0:
                raise DocumentError(f"PDF has no pages: {record['relative_path']}")
            scale = dpi / 72
            pages = []
            for index, page in enumerate(document):
                target = page_dir / f"page-{index + 1:04d}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pixmap.save(target)
                pages.append(target)
            return pages
        finally:
            document.close()
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise DocumentError("Pillow is unavailable; job environment setup did not complete") from exc
    with Image.open(source) as image:
        frames = []
        frame_count = getattr(image, "n_frames", 1)
        for index in range(frame_count):
            image.seek(index)
            normalized = ImageOps.exif_transpose(image.convert("RGB"))
            target = page_dir / f"page-{index + 1:04d}.png"
            normalized.save(target, "PNG")
            frames.append(target)
    return frames


def _jsonable(value: Any) -> Any:
    if hasattr(value, "json"):
        candidate = value.json
        return candidate() if callable(candidate) else candidate
    if hasattr(value, "to_json"):
        return value.to_json()
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


def parse_pages(page_paths: list[Path], language: str, quality: str, mock: bool) -> list[dict[str, Any]]:
    """Run PP-StructureV3 and retain one structured result for every page."""
    if mock:
        return [
            {
                "page": index + 1,
                "engine": "mock",
                "markdown": f"# Mock OCR\n\n{page_path.name}\n",
                "result": {"page_image": page_path.name, "text": "mock OCR"},
            }
            for index, page_path in enumerate(page_paths)
        ]
    try:
        from paddleocr import PPStructureV3
    except ImportError as exc:
        raise DocumentError("PaddleOCR is unavailable; inspect job environment download logs") from exc
    # PP-StructureV3 resolves model assets through PADDLE_PDX_MODEL_SOURCE_DIR,
    # populated by the job environment once for each GPU worker session.
    pipeline = PPStructureV3(
        text_recognition_model_name=RECOGNITION_MODELS[language],
        use_doc_orientation_classify=quality == "high",
    )
    parsed: list[dict[str, Any]] = []
    for index, page_path in enumerate(page_paths):
        predictions = list(pipeline.predict(str(page_path)))
        structured = [_jsonable(prediction) for prediction in predictions]
        markdown = "\n\n".join(
            str(item.get("markdown", ""))
            for item in structured
            if isinstance(item, dict) and item.get("markdown")
        )
        parsed.append(
            {
                "page": index + 1,
                "engine": "PP-StructureV3",
                "markdown": markdown or f"<!-- PP-StructureV3 result for {page_path.name} -->\n",
                "result": structured,
            }
        )
    return parsed


def render_command(args: argparse.Namespace) -> None:
    records = read_inventory(Path(args.input_dir))
    record = records[args.document_index]
    stage = Path(args.intermediate_dir) / record["document_id"]
    if stage.exists():
        shutil.rmtree(stage)
    pages = prepare_document(Path(args.input_dir), record, stage, args.dpi)
    write_json(
        stage / "render-manifest.json",
        {**record, "page_count": len(pages), "pages": [page.name for page in pages], "render_dpi": args.dpi},
    )
    print(record["document_id"])


def parse_command(args: argparse.Namespace) -> None:
    stage = Path(args.intermediate_dir) / args.document_id
    manifest = json.loads((stage / "render-manifest.json").read_text(encoding="utf-8"))
    pages = [stage / "pages" / page for page in manifest["pages"]]
    parsed = parse_pages(pages, args.language, args.quality, args.mock_ocr)
    write_json(stage / "parse-results.json", {"document_id": args.document_id, "pages": parsed})


def assemble_document(stage: Path, output_root: Path) -> dict[str, Any]:
    render = json.loads((stage / "render-manifest.json").read_text(encoding="utf-8"))
    parsed = json.loads((stage / "parse-results.json").read_text(encoding="utf-8"))
    destination = output_root / "documents" / render["document_id"]
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    markdown = "\n\n".join(page["markdown"] for page in parsed["pages"])
    (temporary / "document.md").write_text(markdown, encoding="utf-8")
    write_json(temporary / "document.json", {**render, **parsed})
    if destination.exists():
        shutil.rmtree(destination)
    temporary.rename(destination)
    return {
        "document_id": render["document_id"],
        "source": render["relative_path"],
        "page_count": render["page_count"],
        "output": f"documents/{render['document_id']}",
    }


def simple_command(args: argparse.Namespace) -> None:
    started = time.time()
    input_root, output_root = Path(args.input_dir), Path(args.output_dir)
    records = read_inventory(input_root)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="paddleocr-simple-", dir=output_root.parent))
    failures, completed = [], []
    try:
        for record in records:
            try:
                stage = temporary / "work" / record["document_id"]
                pages = prepare_document(input_root, record, stage, args.dpi)
                parsed = parse_pages(pages, args.language, args.quality, args.mock_ocr)
                write_json(stage / "render-manifest.json", {**record, "page_count": len(pages), "pages": [p.name for p in pages], "render_dpi": args.dpi})
                write_json(stage / "parse-results.json", {"document_id": record["document_id"], "pages": parsed})
                completed.append(assemble_document(stage, temporary))
            except Exception as exc:  # Continue to report all document failures.
                failures.append({"source": record["relative_path"], "error": str(exc)})
        manifest = {
            "schema_version": 1,
            "documents": completed,
            "failures": failures,
            "parameters": {"language": args.language, "render_dpi": args.dpi, "model_quality": args.quality},
            "provenance": {"engine": "PP-StructureV3", "paddleocr_version": "3.1.0"},
            "elapsed_seconds": round(time.time() - started, 3),
        }
        write_json(temporary / "manifest.json", manifest)
        if output_root.exists():
            shutil.rmtree(output_root)
        temporary.rename(output_root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    if failures:
        raise SystemExit(f"{len(failures)} document(s) failed; see {output_root / 'manifest.json'}")


def assemble_command(args: argparse.Namespace) -> None:
    records = read_inventory(Path(args.input_dir))
    output_root = Path(args.output_dir)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="paddleocr-assemble-", dir=output_root.parent))
    try:
        documents = [
            assemble_document(Path(args.intermediate_dir) / record["document_id"], temporary)
            for record in records
        ]
        write_json(temporary / "manifest.json", {"schema_version": 1, "documents": documents, "failures": [], "parameters": {"language": args.language, "render_dpi": args.dpi, "model_quality": args.quality}, "provenance": {"engine": "PP-StructureV3", "paddleocr_version": "3.1.0"}})
        if output_root.exists():
            shutil.rmtree(output_root)
        temporary.rename(output_root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("simple", "render", "assemble"):
        command = subcommands.add_parser(name)
        command.add_argument("--input-dir", required=True)
        command.add_argument("--output-dir")
        command.add_argument("--intermediate-dir")
        command.add_argument("--language", default="en")
        command.add_argument("--dpi", type=int, default=200)
        command.add_argument("--quality", default="standard", choices=("standard", "high"))
        command.add_argument("--mock-ocr", action="store_true")
        if name == "render":
            command.add_argument("--document-index", type=int, required=True)
        command.set_defaults(handler={"simple": simple_command, "render": render_command, "assemble": assemble_command}[name])
    parse = subcommands.add_parser("parse")
    parse.add_argument("--intermediate-dir", required=True)
    parse.add_argument("--document-id", required=True)
    parse.add_argument("--language", default="en")
    parse.add_argument("--quality", default="standard", choices=("standard", "high"))
    parse.add_argument("--mock-ocr", action="store_true")
    parse.set_defaults(handler=parse_command)
    args = parser.parse_args()
    if args.command in {"render", "assemble"} and not args.intermediate_dir:
        parser.error(f"{args.command} requires --intermediate-dir")
    if args.command in {"simple", "assemble"} and not args.output_dir:
        parser.error(f"{args.command} requires --output-dir")
    args.handler(args)


if __name__ == "__main__":
    main()
