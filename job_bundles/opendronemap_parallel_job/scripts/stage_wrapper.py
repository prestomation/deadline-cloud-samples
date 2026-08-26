#!/usr/bin/env python3
"""Narrow, version-guarded ODM 3.6.1 stage wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ODM_VERSION = "3.6.1"
ODM_IMAGE = (
    "opendronemap/odm:3.6.1@"
    "sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
)
ODM_IMAGE_DIGEST = "sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
OPENSFM_COMMIT = "c5328439465e6ace011f39077d1077d7b1cdd65d"
PINNED_FILE_HASHES = {
    "/code/SuperBuild/install/bin/opensfm/opensfm/large/metadataset.py": (
        "6691cf7d5be2d7fd227d8cecf27cf4bd554a824f2f782c8f48ada4e112fa0f4a"
    ),
    "/code/stages/splitmerge.py": (
        "539287a9ec608c2f98d38dcdaf99e58dcd8ac1773ce3f324bae636a556dbd541"
    ),
    "/code/opendm/osfm.py": (
        "32779d4788e7136ffabd77aa8407d75f74ea6747e95e0cecf568bdfea09fce8f"
    ),
}
PROJECT_NAME = "survey"
MAX_EXPANSION_RATIO = 3.0
OUTLIER_MINIMUM_METERS = 5000.0
PROCESSING_REQUIRED = [
    "odm_georeferencing/odm_georeferenced_model.laz",
    "odm_georeferencing/odm_georeferenced_model.bounds.gpkg",
    "odm_orthophoto/odm_orthophoto_feathered.tif",
    "odm_orthophoto/odm_orthophoto_cut.tif",
    "odm_report/shots.geojson",
    "cameras.json",
]

ACTIVE_CHILD: subprocess.Popen[Any] | None = None


class StageError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def status(message: str) -> None:
    print(f"openjd_status: {message}", flush=True)


def progress(value: int | float) -> None:
    print(f"openjd_progress: {value}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def require_file(path: Path, description: str | None = None) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise StageError(f"missing required {description or 'artifact'}: {path}", 66)


def read_json(path: Path) -> dict[str, Any]:
    require_file(path, "manifest")
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError(f"cannot read JSON manifest {path}: {exc}", 65) from exc
    if not isinstance(value, dict):
        raise StageError(f"JSON manifest is not an object: {path}", 65)
    return value


def software_identity() -> dict[str, Any]:
    version = Path("/code/VERSION").read_text(encoding="utf-8").strip()
    if version != ODM_VERSION:
        raise StageError(f"expected ODM {ODM_VERSION}, found {version}", 69)
    opensfm_head = Path(
        "/code/SuperBuild/install/bin/opensfm/.git/HEAD"
    ).read_text(encoding="utf-8").strip()
    if opensfm_head != OPENSFM_COMMIT:
        raise StageError(
            f"expected OpenSfM {OPENSFM_COMMIT}, found {opensfm_head}", 69
        )
    hashes: dict[str, str] = {}
    for filename, expected in PINNED_FILE_HASHES.items():
        actual = sha256_file(Path(filename))
        if actual != expected:
            raise StageError(
                f"pinned source hash mismatch for {filename}: {actual}", 69
            )
        hashes[filename] = actual
    return {
        "odm_version": version,
        "odm_image": ODM_IMAGE,
        "odm_image_digest": ODM_IMAGE_DIGEST,
        "opensfm_commit": opensfm_head,
        "source_hashes": hashes,
    }


def project_paths(project_root: Path) -> tuple[Path, Path, Path]:
    deadline_dir = project_root / "deadline"
    return (
        deadline_dir / "manifests",
        project_root / "opensfm",
        project_root / "submodels",
    )


def parse_bool(value: str, name: str) -> bool:
    if value not in {"True", "False"}:
        raise StageError(f"{name} must be True or False", 64)
    return value == "True"


def odm_args(args: argparse.Namespace) -> Any:
    from opendm import config

    values = [
        "--project-path",
        str(args.project_root.parent),
        args.project_root.name,
        "--feature-quality",
        args.feature_quality,
        "--pc-quality",
        args.point_cloud_quality,
        "--orthophoto-resolution",
        str(args.orthophoto_resolution),
        "--max-concurrency",
        str(args.max_concurrency),
        "--split",
        str(args.target_images),
    ]
    overlap = getattr(args, "split_overlap", 0.0)
    values.extend(["--split-overlap", str(overlap)])
    if args.generate_dsm:
        values.append("--dsm")
    if args.generate_dtm:
        values.append("--dtm")
    parsed = config.config(values)
    parsed.project_path = str(args.project_root)
    return parsed


def topocentric_positions(positions: Any) -> Any:
    import numpy as np
    from opensfm import geo

    reference_lla = np.mean(positions, 0)
    converter = geo.TopocentricConverter(reference_lla[0], reference_lla[1], 0)
    result = []
    for latitude, longitude in positions:
        x, y, _ = converter.to_topocentric(latitude, longitude, 0)
        result.append([x, y])
    return np.asarray(result, dtype=float)


def graph_diagnostics(
    clusters: list[list[int]], minimum_shared: int
) -> dict[str, Any]:
    node_count = len(clusters)
    adjacency = {index: set() for index in range(node_count)}
    shared_matrix: list[list[int]] = [[0] * node_count for _ in range(node_count)]
    for left in range(node_count):
        left_set = set(clusters[left])
        shared_matrix[left][left] = len(left_set)
        for right in range(left + 1, node_count):
            shared = len(left_set.intersection(clusters[right]))
            shared_matrix[left][right] = shared
            shared_matrix[right][left] = shared
            if shared >= minimum_shared:
                adjacency[left].add(right)
                adjacency[right].add(left)

    components: list[list[int]] = []
    unseen = set(range(node_count))
    while unseen:
        pending = [min(unseen)]
        component: list[int] = []
        unseen.remove(pending[0])
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    pending.append(neighbor)
        components.append(sorted(component))
    return {
        "connected": len(components) == 1,
        "components": components,
        "shared_image_matrix": shared_matrix,
    }


def candidate_overlap_radii(positions: Any) -> tuple[list[float], dict[str, float]]:
    import numpy as np

    topocentric = topocentric_positions(positions)
    deltas = topocentric[:, None, :] - topocentric[None, :, :]
    distances = np.sqrt(np.sum(deltas * deltas, axis=2))
    np.fill_diagonal(distances, np.inf)
    nearest = np.min(distances, axis=1)
    spacing = float(np.median(nearest))
    extent = np.ptp(topocentric, axis=0)
    diagonal = float(np.sqrt(np.sum(extent * extent)))
    upper_bound = max(spacing, min(diagonal * 0.4, max(150.0, spacing * 32.0)))
    multipliers = (1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32)
    values = {max(0.1, spacing * multiplier) for multiplier in multipliers}
    values.add(150.0)
    values.add(upper_bound)
    candidates = sorted(value for value in values if value <= upper_bound + 1e-6)
    return candidates, {
        "median_nearest_neighbor_meters": spacing,
        "survey_diagonal_meters": diagonal,
        "maximum_candidate_meters": upper_bound,
    }


def validate_photo_contract(photos: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    missing: list[str] = []
    invalid: list[str] = []
    records: list[dict[str, Any]] = []
    camera_models: set[str] = set()
    for photo in photos:
        if photo.latitude is None or photo.longitude is None or photo.altitude is None:
            missing.append(photo.filename)
            continue
        latitude = float(photo.latitude)
        longitude = float(photo.longitude)
        altitude = float(photo.altitude)
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not math.isfinite(altitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            invalid.append(photo.filename)
            continue
        camera = f"{photo.camera_make} {photo.camera_model}".strip() or "unknown"
        camera_models.add(camera)
        records.append(
            {
                "staged_name": photo.filename,
                "width": int(photo.width),
                "height": int(photo.height),
                "camera": camera,
                "band_name": photo.band_name,
                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude,
            }
        )
    if missing:
        raise StageError(
            "every version 1 image must have GPS latitude, longitude, and altitude; "
            f"missing: {', '.join(sorted(missing))}",
            65,
        )
    if invalid:
        raise StageError(
            f"images have invalid GPS values: {', '.join(sorted(invalid))}", 65
        )
    if any(record["band_name"].upper() not in {"RGB", "REDGREENBLUE"} for record in records):
        raise StageError(
            "version 1 accepts one RGB survey; multispectral bands are not supported",
            65,
        )

    if len(records) >= 8:
        import numpy as np

        positions = np.asarray(
            [[record["latitude"], record["longitude"]] for record in records],
            dtype=float,
        )
        topocentric = topocentric_positions(positions)
        center = np.median(topocentric, axis=0)
        distances = np.sqrt(np.sum((topocentric - center) ** 2, axis=1))
        median = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median)))
        threshold = max(OUTLIER_MINIMUM_METERS, median + 50.0 * max(mad, 1.0))
        outliers = [
            records[index]["staged_name"]
            for index, distance in enumerate(distances)
            if distance > threshold
        ]
        if outliers:
            raise StageError(
                "GPS positions contain extreme geographic outliers beyond "
                f"{threshold:.1f} meters: {', '.join(sorted(outliers))}",
                65,
            )

    return records, {"camera_models": sorted(camera_models)}


def prepare(args: argparse.Namespace, identity: dict[str, Any]) -> None:
    import cv2
    import numpy as np
    from opendm import log
    from opendm.osfm import OSFMContext
    from opensfm.actions import create_submodels
    from opensfm.dataset import DataSet
    from opensfm.large import tools
    from opensfm.large.metadataset import MetaDataSet
    from stages.odm_app import ODMApp

    manifests_dir, opensfm_dir, submodels_dir = project_paths(args.project_root)
    input_manifest_path = manifests_dir / "input.json"
    input_manifest = read_json(input_manifest_path)
    if args.expected_images <= 0 or args.expected_submodels <= 0:
        raise StageError("submission hook sent an unexpanded sentinel", 64)
    if input_manifest["metrics"]["image_count"] != args.expected_images:
        raise StageError("staged image count differs from the hook plan", 65)

    status("Prepare: reading EXIF and validating GPS")
    progress(2)
    parsed_args = odm_args(args)
    application = ODMApp(parsed_args)
    outputs: dict[str, Any] = {}
    try:
        parsed_args.end_with = "dataset"
        application.first_stage.run(outputs)
        tree = outputs["tree"]
        reconstruction = outputs["reconstruction"]
        if len(reconstruction.photos) != args.expected_images:
            raise StageError(
                "ODM usable image count differs from submission preflight "
                f"({len(reconstruction.photos)} != {args.expected_images})",
                65,
            )
        if reconstruction.multi_camera:
            raise StageError(
                "version 1 does not accept multispectral or multi-camera band groups",
                65,
            )
        photo_records, survey_metadata = validate_photo_contract(reconstruction.photos)

        staged_by_name = {
            record["staged_name"]: record for record in input_manifest["images"]
        }
        for photo in photo_records:
            if photo["staged_name"] not in staged_by_name:
                raise StageError(
                    f"ODM returned an unplanned image: {photo['staged_name']}", 65
                )
            staged_by_name[photo["staged_name"]].update(photo)
        atomic_json(input_manifest_path, input_manifest)

        status("Prepare: extracting features and matching images")
        progress(10)
        octx = OSFMContext(tree.opensfm)
        appended_config = [
            "submodels_relpath: ../submodels/opensfm",
            "submodel_relpath_template: ../submodels/submodel_%04d/opensfm",
            "submodel_images_relpath_template: ../submodels/submodel_%04d/images",
            f"submodel_size: {args.target_images}",
            f"submodel_overlap: {args.split_overlap}",
        ]
        octx.setup(
            parsed_args,
            tree.dataset_raw,
            reconstruction=reconstruction,
            append_config=appended_config,
            rerun=False,
        )
        octx.photos_to_metadata(
            reconstruction.photos,
            parsed_args.rolling_shutter,
            parsed_args.rolling_shutter_readout,
            False,
        )
        octx.feature_matching(False)
        progress(55)

        status("Prepare: calculating base clusters and overlap")
        metadata = MetaDataSet(tree.opensfm)
        metadata.remove_submodels()
        data = DataSet(tree.opensfm)
        data.init_reference()
        create_submodels._create_image_list(data, metadata)
        cv2.setRNGSeed(0)
        create_submodels._cluster_images(metadata, args.target_images)
        images, positions, labels, centers = metadata.load_clusters()
        base_clusters = [
            list(np.where(labels == label)[0])
            for label in range(int(centers.shape[0]))
        ]
        if len(base_clusters) != args.expected_submodels:
            raise StageError(
                "OpenSfM base cluster count differs from the hook task range "
                f"({len(base_clusters)} != {args.expected_submodels})",
                65,
            )
        base_sizes = [len(cluster) for cluster in base_clusters]
        if not base_sizes or min(base_sizes) <= 0:
            raise StageError("OpenSfM produced an empty base cluster", 65)
        if max(base_sizes) / min(base_sizes) > 4.0:
            raise StageError(
                f"base clusters are pathologically imbalanced: {base_sizes}", 65
            )

        if args.split_overlap > 0:
            candidate_radii = [float(args.split_overlap)]
            spacing_metrics: dict[str, float] = {}
            mode = "manual"
        elif len(base_clusters) == 1:
            candidate_radii = [0.0]
            spacing_metrics = {}
            mode = "automatic"
        else:
            candidate_radii, spacing_metrics = candidate_overlap_radii(positions)
            mode = "automatic"

        selected_radius: float | None = None
        selected_clusters: list[list[int]] | None = None
        selected_graph: dict[str, Any] | None = None
        evaluations = []
        for radius in candidate_radii:
            if radius == 0 and len(base_clusters) == 1:
                clusters = [list(base_clusters[0])]
            else:
                clusters = [
                    [int(index) for index in cluster]
                    for cluster in tools.add_cluster_neighbors(
                        positions, labels, centers, radius
                    )
                ]
            graph = graph_diagnostics(clusters, args.minimum_shared_images)
            expansion = [
                len(cluster) / base_sizes[index]
                for index, cluster in enumerate(clusters)
            ]
            acceptable_expansion = max(expansion) <= MAX_EXPANSION_RATIO
            evaluations.append(
                {
                    "radius_meters": radius,
                    "connected": graph["connected"],
                    "components": graph["components"],
                    "expanded_sizes": [len(cluster) for cluster in clusters],
                    "maximum_expansion_ratio": max(expansion),
                    "acceptable_expansion": acceptable_expansion,
                }
            )
            if graph["connected"] and acceptable_expansion:
                selected_radius = radius
                selected_clusters = clusters
                selected_graph = graph
                break

        if selected_clusters is None or selected_graph is None or selected_radius is None:
            raise StageError(
                "no overlap radius produced a connected submodel graph within "
                f"the {MAX_EXPANSION_RATIO:.1f}x expansion cap; "
                f"evaluations={json.dumps(evaluations, sort_keys=True)}",
                65,
            )
        if mode == "manual" and selected_radius != args.split_overlap:
            raise StageError("manual overlap radius was not used exactly", 65)

        image_clusters = [
            [str(value) for value in np.take(images, np.asarray(cluster))]
            for cluster in selected_clusters
        ]
        metadata.save_clusters_with_neighbors(image_clusters)
        create_submodels._save_clusters_geojson(metadata)
        create_submodels._save_cluster_neighbors_geojson(metadata)
        metadata.create_submodels(metadata.load_clusters_with_neighbors())
        submodel_paths = metadata.get_submodel_paths()
        if len(submodel_paths) != args.expected_submodels:
            raise StageError(
                f"expected {args.expected_submodels} submodels, created "
                f"{len(submodel_paths)}",
                65,
            )

        partition_manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "software": identity,
            "image_count": args.expected_images,
            "submodel_count": args.expected_submodels,
            "target_images_per_submodel": args.target_images,
            "overlap_mode": mode,
            "requested_overlap_meters": args.split_overlap,
            "selected_overlap_meters": selected_radius,
            "minimum_shared_images": args.minimum_shared_images,
            "maximum_expansion_ratio": MAX_EXPANSION_RATIO,
            "spacing": spacing_metrics,
            "base_sizes": base_sizes,
            "expanded_sizes": [len(cluster) for cluster in selected_clusters],
            "base_membership": [
                [str(value) for value in np.take(images, np.asarray(cluster))]
                for cluster in base_clusters
            ],
            "expanded_membership": image_clusters,
            "intersection_graph": selected_graph,
            "candidate_evaluations": evaluations,
            "survey": survey_metadata,
            "random_seed": 0,
        }
        atomic_json(manifests_dir / "partition.json", partition_manifest)
        atomic_json(
            manifests_dir / "prepare.json",
            {
                "schema_version": 1,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "required_outputs": [
                    str(path.relative_to(args.project_root))
                    for path in (
                        opensfm_dir / "config.yaml",
                        submodels_dir,
                        manifests_dir / "partition.json",
                    )
                ],
            },
        )
        progress(100)
        status(
            f"Prepare complete: {args.expected_submodels} submodels, "
            f"{selected_radius:.2f} m overlap"
        )
    finally:
        log.logger.close()


def load_partition(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    manifests_dir, _, _ = project_paths(args.project_root)
    partition = read_json(manifests_dir / "partition.json")
    expected = int(partition.get("submodel_count", 0))
    if expected != args.expected_submodels:
        raise StageError(
            f"partition submodel count mismatch ({expected} != "
            f"{args.expected_submodels})",
            65,
        )
    return manifests_dir, partition


def submodel_path(args: argparse.Namespace) -> Path:
    if args.submodel_index < 0 or args.submodel_index >= args.expected_submodels:
        raise StageError(
            f"submodel index {args.submodel_index} is outside the planned range",
            64,
        )
    return (
        args.project_root
        / "submodels"
        / f"submodel_{args.submodel_index:04d}"
    )


def reconstruct(args: argparse.Namespace, identity: dict[str, Any]) -> None:
    from opendm.osfm import OSFMContext

    manifests_dir, _ = load_partition(args)
    selected = submodel_path(args)
    opensfm_path = selected / "opensfm"
    require_file(opensfm_path / "image_list.txt", "submodel image list")
    status(f"Reconstructing submodel {args.submodel_index + 1}/{args.expected_submodels}")
    progress(5)
    context = OSFMContext(str(opensfm_path))
    context.create_tracks(False)
    progress(35)
    context.reconstruct(False, True, False)
    require_file(opensfm_path / "reconstruction.json", "OpenSfM reconstruction")
    require_file(opensfm_path / "tracks.csv", "OpenSfM tracks")
    atomic_json(
        manifests_dir / "reconstruction" / f"submodel_{args.submodel_index:04d}.json",
        {
            "schema_version": 1,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "submodel_index": args.submodel_index,
            "software": identity,
            "artifacts": {
                "opensfm/reconstruction.json": sha256_file(
                    opensfm_path / "reconstruction.json"
                ),
                "opensfm/tracks.csv": sha256_file(opensfm_path / "tracks.csv"),
            },
        },
    )
    progress(100)
    status(f"Reconstruction complete for submodel {args.submodel_index}")


def align(args: argparse.Namespace, identity: dict[str, Any]) -> None:
    from opendm.osfm import OSFMContext
    from opensfm.large.metadataset import MetaDataSet

    manifests_dir, _ = load_partition(args)
    master = args.project_root / "opensfm"
    metadata = MetaDataSet(str(master))
    paths = [Path(path) for path in metadata.get_submodel_paths()]
    if len(paths) != args.expected_submodels:
        raise StageError(
            f"alignment found {len(paths)} submodels, expected "
            f"{args.expected_submodels}",
            65,
        )
    for index, path in enumerate(paths):
        require_file(
            manifests_dir / "reconstruction" / f"submodel_{index:04d}.json",
            "reconstruction stage manifest",
        )
        require_file(path / "reconstruction.json", "reconstruction input")

    status(f"Aligning {args.expected_submodels} reconstructed submodels")
    progress(5)
    OSFMContext(str(master)).align_reconstructions(False)
    progress(80)
    artifacts = {}
    for index, path in enumerate(paths):
        aligned = path / "reconstruction.aligned.json"
        current = path / "reconstruction.json"
        unaligned = path / "reconstruction.unaligned.json"
        require_file(aligned, "aligned reconstruction")
        if unaligned.exists():
            unaligned.unlink()
        os.replace(current, unaligned)
        os.replace(aligned, current)
        artifacts[f"submodel_{index:04d}"] = {
            "aligned_reconstruction_sha256": sha256_file(current),
            "unaligned_reconstruction_sha256": sha256_file(unaligned),
        }
    atomic_json(
        manifests_dir / "alignment.json",
        {
            "schema_version": 1,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "software": identity,
            "submodel_count": args.expected_submodels,
            "artifacts": artifacts,
        },
    )
    progress(100)
    status("Submodel alignment complete")


def forward_signal(signum: int, _frame: Any) -> None:
    if ACTIVE_CHILD is not None and ACTIVE_CHILD.poll() is None:
        ACTIVE_CHILD.send_signal(signum)


def run_child(command: list[str]) -> int:
    global ACTIVE_CHILD
    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)
    ACTIVE_CHILD = subprocess.Popen(command)
    while True:
        try:
            return ACTIVE_CHILD.wait()
        except InterruptedError:
            continue


def process(args: argparse.Namespace, identity: dict[str, Any]) -> None:
    manifests_dir, _ = load_partition(args)
    require_file(manifests_dir / "alignment.json", "alignment manifest")
    selected = submodel_path(args)
    name = selected.name
    command = [
        "python3",
        "/code/run.py",
        "--project-path",
        str(selected.parent),
        name,
        "--orthophoto-cutline",
        "--dem-euclidean-map",
        "--skip-3dmodel",
        "--skip-report",
        "--orthophoto-resolution",
        str(args.orthophoto_resolution),
        "--feature-quality",
        args.feature_quality,
        "--pc-quality",
        args.point_cloud_quality,
        "--max-concurrency",
        str(args.max_concurrency),
    ]
    if args.generate_dsm:
        command.append("--dsm")
    if args.generate_dtm:
        command.append("--dtm")
    status(f"Processing submodel {args.submodel_index + 1}/{args.expected_submodels}")
    progress(2)
    exit_code = run_child(command)
    if exit_code != 0:
        raise StageError(
            f"ODM submodel toolchain exited with status {exit_code}", exit_code
        )
    required = list(PROCESSING_REQUIRED)
    if args.generate_dsm:
        required.append("odm_dem/dsm.tif")
    if args.generate_dtm:
        required.append("odm_dem/dtm.tif")
    artifacts = {}
    for relative in required:
        path = selected / relative
        require_file(path, "processed submodel artifact")
        artifacts[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    atomic_json(
        manifests_dir / "processing" / f"submodel_{args.submodel_index:04d}.json",
        {
            "schema_version": 1,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "submodel_index": args.submodel_index,
            "software": identity,
            "artifacts": artifacts,
        },
    )
    progress(100)
    status(f"Processing complete for submodel {args.submodel_index}")


def collect_final_artifacts(result_dir: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(result_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append(
                {
                    "path": path.relative_to(result_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return artifacts


def merge(args: argparse.Namespace, identity: dict[str, Any]) -> None:
    from opendm import log
    from stages.odm_app import ODMApp

    manifests_dir, partition = load_partition(args)
    for index in range(args.expected_submodels):
        require_file(
            manifests_dir / "processing" / f"submodel_{index:04d}.json",
            "processing stage manifest",
        )
    status(f"Merging {args.expected_submodels} processed submodels")
    progress(2)
    parsed_args = odm_args(args)
    application = ODMApp(parsed_args)
    outputs: dict[str, Any] = {}
    try:
        parsed_args.end_with = "dataset"
        application.first_stage.run(outputs)
        outputs["large"] = True
        merge_stage = application.first_stage.next_stage.next_stage
        parsed_args.end_with = "merge"
        merge_stage.run(outputs)
    finally:
        log.logger.close()
    progress(85)

    required = [
        args.project_root / "odm_orthophoto" / "odm_orthophoto.tif",
        args.project_root
        / "odm_georeferencing"
        / "odm_georeferenced_model.laz",
    ]
    if args.generate_dsm:
        required.append(args.project_root / "odm_dem" / "dsm.tif")
    if args.generate_dtm:
        required.append(args.project_root / "odm_dem" / "dtm.tif")
    for path in required:
        require_file(path, "merged output")

    result_dir = args.output_dir / "open_drone_map_parallel"
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir(parents=True)
    copy_groups = {
        "odm_orthophoto": args.project_root / "odm_orthophoto",
        "odm_georeferencing": args.project_root / "odm_georeferencing",
        "odm_dem": args.project_root / "odm_dem",
        "logs": args.project_root.parent / "logs",
        "metrics": args.project_root.parent / "metrics",
        "stage_manifests": manifests_dir,
    }
    for destination_name, source in copy_groups.items():
        if source.exists():
            shutil.copytree(source, result_dir / destination_name)
    if args.retain_intermediates:
        retained = result_dir / "intermediates"
        retained.mkdir()
        for relative in (
            "opensfm/submodels/clusters.geojson",
            "opensfm/submodels/clusters_with_neighbors.geojson",
        ):
            source = args.project_root / relative
            if source.exists():
                destination = retained / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    summary = {
        "image_count": args.expected_images,
        "submodel_count": args.expected_submodels,
        "selected_overlap_meters": partition["selected_overlap_meters"],
        "base_sizes": partition["base_sizes"],
        "expanded_sizes": partition["expanded_sizes"],
        "retained_intermediates": args.retain_intermediates,
    }
    atomic_json(result_dir / "processing_summary.json", summary)
    manifest = {
        "schema_version": 1,
        "status": "success",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "software": identity,
        "parameters": {
            "target_images_per_submodel": args.target_images,
            "split_overlap_meters": args.split_overlap,
            "orthophoto_resolution": args.orthophoto_resolution,
            "feature_quality": args.feature_quality,
            "point_cloud_quality": args.point_cloud_quality,
            "generate_dsm": args.generate_dsm,
            "generate_dtm": args.generate_dtm,
            "max_concurrency": args.max_concurrency,
            "retain_intermediates": args.retain_intermediates,
        },
        "partition": partition,
        "artifacts": collect_final_artifacts(result_dir),
    }
    atomic_json(result_dir / "manifest.json", manifest)
    progress(100)
    status("OpenDroneMap parallel merge complete")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--expected-submodels", type=int, required=True)
    parser.add_argument("--max-concurrency", type=int, default=2)


def add_processing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-images", type=int, default=100)
    parser.add_argument("--split-overlap", type=float, default=0)
    parser.add_argument("--orthophoto-resolution", type=int, default=10)
    parser.add_argument(
        "--feature-quality",
        choices=["ultra", "high", "medium", "low", "lowest"],
        default="low",
    )
    parser.add_argument(
        "--point-cloud-quality",
        choices=["ultra", "high", "medium", "low", "lowest"],
        default="lowest",
    )
    parser.add_argument("--generate-dsm", type=lambda value: parse_bool(value, "GenerateDsm"))
    parser.add_argument("--generate-dtm", type=lambda value: parse_bool(value, "GenerateDtm"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="stage", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    add_common_arguments(prepare_parser)
    add_processing_arguments(prepare_parser)
    prepare_parser.add_argument("--expected-images", type=int, required=True)
    prepare_parser.add_argument("--minimum-shared-images", type=int, required=True)

    reconstruct_parser = subparsers.add_parser("reconstruct")
    add_common_arguments(reconstruct_parser)
    reconstruct_parser.add_argument("--submodel-index", type=int, required=True)

    align_parser = subparsers.add_parser("align")
    add_common_arguments(align_parser)

    process_parser = subparsers.add_parser("process")
    add_common_arguments(process_parser)
    add_processing_arguments(process_parser)
    process_parser.add_argument("--submodel-index", type=int, required=True)

    merge_parser = subparsers.add_parser("merge")
    add_common_arguments(merge_parser)
    add_processing_arguments(merge_parser)
    merge_parser.add_argument("--expected-images", type=int, required=True)
    merge_parser.add_argument("--output-dir", type=Path, required=True)
    merge_parser.add_argument(
        "--retain-intermediates",
        type=lambda value: parse_bool(value, "RetainIntermediates"),
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    started = time.monotonic()
    try:
        args = parse_args()
        if args.expected_submodels <= 0:
            raise StageError("submission hook left the submodel sentinel unexpanded", 64)
        if args.max_concurrency <= 0:
            raise StageError("MaxConcurrency must be positive", 64)
        identity = software_identity()
        if args.stage == "prepare":
            prepare(args, identity)
        elif args.stage == "reconstruct":
            reconstruct(args, identity)
        elif args.stage == "align":
            align(args, identity)
        elif args.stage == "process":
            process(args, identity)
        elif args.stage == "merge":
            merge(args, identity)
        else:
            raise StageError(f"unsupported stage: {args.stage}", 64)
        print(f"Stage runtime seconds: {time.monotonic() - started:.3f}")
        return 0
    except StageError as exc:
        print(f"openjd_fail: {exc}", file=sys.stderr, flush=True)
        return exc.exit_code
    except KeyboardInterrupt:
        print("openjd_fail: stage canceled", file=sys.stderr, flush=True)
        return 130
    except BaseException as exc:
        print(f"openjd_fail: unexpected stage failure: {exc}", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
