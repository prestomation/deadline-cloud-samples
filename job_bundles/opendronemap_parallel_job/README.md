# OpenDroneMap parallel job

> **Status: experimental implementation under validation.**
>
> The five-stage bundle has completed local and two-worker Deadline Cloud
> Brighton Beach validation plus a four-worker, 524-image Deadline Cloud
> scale run plus controlled retry and cancellation tests. The remaining
> failure matrix, secondary-survey, and native-reference quality gates in
> [TESTING.md](TESTING.md) must pass before this sample is production-ready.
> Use `COPIED` job attachments; `VIRTUAL` is not supported for this workflow.

## Customer outcome

A Deadline Cloud user selects a directory of their own geotagged aerial
images, chooses an output directory, and submits one job. The sample plans the
survey, distributes independent ODM submodels across a Docker-enabled Linux
fleet, aligns them, and returns merged geospatial outputs.

The user does not need to edit the template, calculate a task range, deploy
ClusterODM or NodeODM, create an extra S3 bucket, or build a custom container.
Input images, stage intermediates, and final results move through Deadline
Cloud job attachments.

The OpenDroneMap data zoo is the reproducible benchmark used to implement and
validate the sample. It is not hard-coded as the only runtime input.

## Prerequisites and fleet setup

The design can be reviewed without AWS resources. Running the sample requires:

- Deadline Cloud CLI 0.58.0 or newer, with bundle hooks explicitly enabled.
- A farm and queue configured for job attachments.
- A workstation configured to submit this bundle with `COPIED` attachments.
- A Linux `x86_64` service-managed fleet using the repository's
  [Docker Engine host configuration](../../host_configuration_scripts/docker_engine/)
  and custom capabilities `attr.OpenDroneMap=docker_3_6_1` and
  `amount.OpenDroneMapScratchGiB` set to the worker root-volume size in GiB.

Starting without a fleet, create the farm and queue in the Deadline Cloud
console, then create a service-managed fleet with a zero minimum and a bounded
maximum of at least two workers for fan-out testing. Add both capabilities,
paste the complete contents of
[`linux.sh`](../../host_configuration_scripts/docker_engine/linux.sh) into
**Host configuration**, and associate the fleet with the queue. Temporarily
launch one worker and confirm its host configuration log ends with
`Docker Engine setup complete`, then restore the minimum to zero.

Configure the local Deadline client with the profile, region, farm, and queue.
The final command opts in to the bundle's local pre-submission hook:

```console
pip install --upgrade deadline
deadline config set defaults.aws_profile_name my-profile
deadline config set defaults.farm_region us-west-2
deadline config set defaults.farm_id farm-0123456789abcdef0123456789abcdef
deadline config set defaults.queue_id queue-0123456789abcdef0123456789abcdef
deadline config set defaults.job_attachments_file_system COPIED
deadline config set settings.allow_bundle_hooks true
```

The complete console checklist and an `aws deadline update-fleet` example for
applying the repository script are in the
[Docker Engine host configuration README](../../host_configuration_scripts/docker_engine/).
Every step requires `attr.OpenDroneMap=docker_3_6_1` and a sufficient
`amount.OpenDroneMapScratchGiB`, so it cannot be routed to a generic Linux
fleet that does not advertise the Docker configuration and scratch capacity.

The host configuration is shared by both ODM samples; there is no
CloudFormation stack or sample-specific infrastructure to deploy. Deadline
runs `linux.sh` on each newly launched worker, so replace existing workers
after changing the script.

The template includes experimental small, medium, and large resource profiles.
The large profile covered the data-zoo run with the intended memory and disk
headroom. Its supported envelope remains provisional until the secondary
survey and additional fleet-width measurements in [TESTING.md](TESTING.md)
are complete.

## Submission experience

A user submits a survey with:

```console
deadline bundle gui-submit job_bundles/opendronemap_parallel_job
```

Or from the command line:

```console
deadline bundle submit job_bundles/opendronemap_parallel_job \
    -p InputImages=/path/to/survey/images \
    -p OutputDir=/path/to/odm-output \
    --job-attachments-file-system COPIED
```

The selected `InputImages` directory is uploaded as a `dataFlow: IN` job
attachment. The normal path requires no network access to a dataset host from
workers. Workers still need access to the pinned ODM image on Docker Hub
unless the image is already cached.

The Deadline Monitor should show:

```text
Submission preflight [local workstation hook]
    |
    v
PrepareSurvey
    |
    v
ReconstructSubmodels [one task per planned submodel]
    |
    v
AlignSubmodels
    |
    v
ProcessSubmodels [one task per aligned submodel]
    |
    v
MergeSurvey
```

The two fan-out steps use stable submodel numbers and task-specific output
directories. Retrying one task must not invalidate successful sibling tasks.

## Dynamic task planning

OpenJD task ranges are fixed when the job is created, so a worker task cannot
discover an image count and add tasks later. The bundle uses a local
`preSubmission` hook to inspect the selected input and expand the job template
before submission.

After the GUI or CLI has resolved the user's parameters, the hook:

1. Scan `InputImages` for supported image files.
2. Reject an empty directory, duplicate staged names, and unsupported scale.
3. Read image dimensions without decoding full images, then report image
   count, source bytes, and source megapixels.
4. Calculate the base submodel count as
   `ceil(image_count / TargetImagesPerSubmodel)`.
5. Reject more than OpenJD's 1024 tasks and recommend a larger target size.
6. Replace placeholder task ranges in both fan-out steps with
   `0..submodel_count-1`.
7. Select concrete host requirements from the chosen resource policy.
8. Put the planned image count, submodel count, and resource estimate into
   hidden parameters for worker-side verification.

The hook does not modify files on disk and does not upload data itself. The
Deadline client applies its expanded template immediately before job
creation. Bundle hooks require Deadline Cloud CLI 0.58.0 or newer and one
workstation setting:

```console
deadline config set settings.allow_bundle_hooks true
```

`PrepareSurvey` remains authoritative. It verifies that every staged image is
readable and GPS geotagged, checks that the hook and worker found the same
image count, and fails before fan-out if the plan is invalid.

## Parameters

### Input and output

| Parameter | Default | Purpose |
|---|---:|---|
| `InputImages` | none | Directory of the user's geotagged survey JPEGs, uploaded with job attachments. |
| `OutputDir` | `./output` | Directory receiving final job-attachment outputs. |
| `RetainIntermediates` | `False` | Copy a curated intermediate tree into the final output for debugging. |

Version 1 targets a single RGB survey with unique JPEG filenames and GPS
metadata on every image. Multispectral grouping, videos, GCP-only surveys, and
multiple surveys per job are follow-up extensions.

### Partitioning

| Parameter | Default | Purpose |
|---|---:|---|
| `TargetImagesPerSubmodel` | `100` | Desired average number of base images per submodel; controls task count. |
| `SplitOverlapMeters` | `0` | Overlap radius in meters; `0` asks preprocessing to choose it automatically. |
| `MinimumSharedImages` | `10` | Provisional minimum shared-image target between neighboring submodels in automatic mode. |

`TargetImagesPerSubmodel` is the user-facing equivalent of ODM's `--split`.
It must be a positive integer. `SplitOverlapMeters` accepts a positive manual
override for users who know their flight geometry.

Automatic overlap is computed on the worker after ODM extracts authoritative
GPS coordinates:

1. Create the same base clusters used by pinned OpenSfM.
2. Measure image spacing and survey extent in local metric coordinates.
3. Evaluate increasing overlap radii with OpenSfM's own
   `add_cluster_neighbors` implementation.
4. Build a graph whose nodes are submodels and whose edges have at least
   `MinimumSharedImages` in common.
5. Choose the smallest radius that connects the graph without causing an
   unacceptable submodel-size expansion.
6. Fail with the measured diagnostics if no safe radius exists. Disconnected
   flights should be submitted as separate surveys rather than joined with an
   extreme overlap.

The default produced a connected six-submodel graph on the data zoo with a
maximum 1.34x expansion ratio. It remains provisional until at least one
second public survey passes without retuning.

### Processing

| Parameter | Default | Purpose |
|---|---:|---|
| `OrthophotoResolution` | `10` | Orthophoto resolution in centimeters per pixel. |
| `FeatureQuality` | `low` | ODM feature extraction quality. |
| `PointCloudQuality` | `lowest` | ODM dense point cloud quality. |
| `GenerateDsm` | `True` | Generate and merge a digital surface model. |
| `GenerateDtm` | `False` | Generate and merge a digital terrain model. |
| `MaxConcurrency` | `2` | Positive integer limiting processes inside each task. |

### Resource sizing

| Parameter | Default | Purpose |
|---|---:|---|
| `ResourceProfile` | `auto` | Select measured automatic sizing, a documented fixed profile, or custom overrides. |
| `CoordinatorMemoryMiB` | `0` | Advanced override for prepare, align, and merge tasks; `0` uses the profile. |
| `SubmodelMemoryMiB` | `0` | Advanced override for reconstruction and processing tasks; `0` uses the profile. |
| `ScratchGiB` | `0` | Advanced minimum worker root-volume override for scratch data; `0` uses the profile. |

The automatic estimator will use image count, source bytes, total source
megapixels, quality settings, target submodel size, and output selections. Its
coefficients and profile boundaries must come from measured benchmark runs,
not undocumented guesses. The hook will print the selected vCPU, memory, and
scratch requirements before submission. Inputs outside the measured envelope
will require an explicit profile or override.

Set the fleet's custom `amount.OpenDroneMapScratchGiB` minimum and maximum to
its root-volume size in GiB. Deadline uses that amount for scheduling, and the
sample still checks actual free space when each stage starts.

Dataset URLs, Docker image identity, raw shell arguments, and arbitrary ODM
flags are not parameters.

## Execution graph

### 1. PrepareSurvey

One coordinator task will:

1. Check Docker, disk, memory, and the pinned ODM image identity.
2. Inventory and checksum the attached input images.
3. Validate image readability, dimensions, camera metadata, and GPS coverage.
4. Verify the submission hook's image and submodel counts.
5. Run pinned ODM/OpenSfM setup, feature matching, and base clustering.
6. Select or validate the overlap radius and create overlapping submodels.
7. Write the authoritative submodel manifest and publish the minimum required
   preparation artifacts through job attachments.

The manifest records each submodel's exact image membership. Downstream tasks
consume this one plan; they never recalculate clustering independently.

### 2. ReconstructSubmodels

One task per submodel will consume its declared images and preparation
metadata, then run OpenSfM track creation and reconstruction. Each task writes
only to `reconstruction/submodel_NNNN/`, records checksums, streams its log,
and fails if required reconstruction artifacts are absent.

### 3. AlignSubmodels

One coordinator task will collect every valid reconstruction, run ODM's
cross-submodel alignment, and publish the aligned reconstructions needed by
the next fan-out. Alignment remains mandatory. GPS-only placement is not an
acceptable default without separate quality evidence.

### 4. ProcessSubmodels

One task per aligned submodel will run the remaining ODM toolchain needed for
dense point clouds, cutline orthophotos, and elevation models. It writes only
to `processed/submodel_NNNN/` and validates every artifact required by the
merge.

### 5. MergeSurvey

One coordinator task will use ODM's pinned merge implementations to produce
the final point cloud, orthophoto, DSM, and optional DTM. It validates the
result set, writes checksums and provenance, and publishes customer-facing
deliverables under `OutputDir`.

## Job-attachment data flow

The sample will use three attachment roots:

- `InputImages`: user-selected `dataFlow: IN`.
- A hidden intermediate root: generated stage data synchronized between
  dependent steps.
- `OutputDir`: final `dataFlow: OUT` results.

Every fan-out task gets a unique relative directory. Files are published
atomically only after validation, so a failed retry cannot expose a partial
submodel as successful input.

Deadline materializes output manifests from a step's direct dependencies, not
the full transitive dependency graph. Align, process, and merge therefore
declare every earlier producer whose files they consume. Later outputs at the
same relative path supersede earlier versions, which allows alignment to
replace reconstruction files while preserving the unchanged reconstruction
tree.

Intermediate files necessarily remain in the queue's job-attachment storage
for the job's retention period because later steps depend on them. Deleting a
file in the final task does not remove it from earlier output manifests.
Therefore `RetainIntermediates=False` means:

- Do not copy intermediates into the final `OutputDir`.
- Document downloading only the `MergeSurvey` step output for the clean final
  result.

When `RetainIntermediates=True`, `MergeSurvey` publishes a curated intermediate
tree and all stage manifests/logs under `OutputDir/intermediates`. Content
addressing should avoid duplicating identical blob storage, although the
additional paths will appear in the final manifest.

No user-created bucket, shared filesystem, database, ClusterODM service, or
NodeODM service is required.

Use `COPIED` attachment mode. OpenSfM creates relative links inside the
intermediate submodel tree. In validation, VIRTUAL mode mounted successfully
and completed Prepare, but Deadline's task-output publication did not finish
within 16 minutes for the 18-image Brighton survey and the job was canceled.
The same COPIED survey completed all five stages in 5 minutes 59 seconds.

## Intended outputs

Successful defaults return:

- A merged GeoTIFF orthophoto.
- A merged LAZ georeferenced point cloud.
- A merged DSM and, when enabled, a DTM.
- Complete per-stage and per-submodel logs.
- A JSON manifest with input checksums, camera/GPS inventory, ODM version,
  parameters, selected partition settings, submodel membership, resource
  estimates, task runtimes, and artifact checksums.
- A concise processing summary assembled from stage records.

ODM 3.6.1 split/merge deliberately adds `--skip-3dmodel` to submodel
processing and has no textured-model merge. A merged textured OBJ is not in
version 1. Its split/merge path also skips normal submodel PDF reports, so the
processing summary replaces the single-project `report.pdf`.

## How resource defaults are being chosen

Validation benchmarks several image counts, source resolutions,
partition sizes, and quality levels. Each stage records peak RSS, peak disk,
input/output bytes, and runtime. The automatic profile will select the
smallest measured worker class that covers the estimate with at least 30
percent memory and disk headroom.

Coordinator and submodel tasks are sized separately:

- Prepare is driven by global metadata, features, and matching.
- Reconstruction and processing are driven by the largest overlapping
  submodel and quality settings.
- Alignment is driven by reconstruction count and size.
- Merge is driven by the combined LAZ and raster intermediates.

If a formula does not predict a benchmark within the safety margin, use a
conservative lookup table instead. The sample should fail early with a sizing
recommendation rather than silently schedule a worker likely to run out of
memory or disk.

## How quality tolerances will be chosen

The parallel result will be compared with native ODM 3.6.1 split/merge using
the same input and parameters. Tolerances will be calibrated from repeated
native and parallel runs because OpenCV clustering and photogrammetry can
produce small nondeterministic differences.

Hard invariants:

- Matching CRS and pixel size.
- Readable GeoTIFF and LAZ structures.
- No missing required submodel.
- No unexplained disconnected coverage or large interior nodata holes.

Calibrated metrics:

- Orthophoto and DEM bounds, valid-data area, nodata area, and seam coverage.
- LAZ bounds, point count, density, and classification distribution.
- DSM/DTM elevation differences over common valid pixels.

For each metric, the threshold will be the larger of observed repeat-run
variation plus a documented safety margin or a domain-specific minimum. The
exact numbers must pass the data zoo and a second public survey, then be
reviewed before publication. Pixel-perfect or byte-identical output is not a
goal.

## Acceptance criteria

The sample becomes runnable only when:

- A user-selected image directory drives the task count without template
  editing.
- Hook and worker inventories agree, and invalid GPS/image inputs fail before
  fan-out.
- Automatic and manual partition modes are both tested.
- Every step has Linux, Docker capability, vCPU, memory, and scratch host
  requirements.
- At least two submodel tasks run concurrently on different Deadline workers.
- Cross-worker handoffs use only job attachments.
- A failed or retried submodel affects only its own output directory.
- Cancellation stops and removes every active ODM container within the OpenJD
  notification period.
- Merge fails when a required submodel or final artifact is missing.
- Native-reference metrics pass the reviewed tolerances.
- `RetainIntermediates` produces the documented final output behavior.
- Monitor status and progress identify the current stage and submodel.
- Wall-clock runtime, worker-minutes, peak memory, disk, attachment transfer,
  image-pull time, and scale-to-zero behavior are recorded.

## Benchmark survey

Implementation and cloud validation will use the
[OpenDroneMap ODM data zoo](https://github.com/OpenDroneMap/odm_data_zoo/tree/60a74095e297d76062ba14312fa581a74021916a)
at commit `60a74095e297d76062ba14312fa581a74021916a`:

- License: CC0-1.0.
- Source images: 524 JPEG files under `images/`.
- Current source-image size: 3,690,489,119 bytes, about 3.44 GiB.
- Archive SHA-256:
  `a7a86646e8bd7a170a736d8f0973424e552a7454cbc04c1ffec58b104a99a220`.

The test process downloads this pinned survey to the submission machine and
passes its `images/` directory through `InputImages`, exactly as a user would
submit private data. Runtime code does not special-case the Zoo.

## Security, dependencies, and cost

The official
`opendronemap/odm:3.6.1@sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d`
multi-architecture manifest remains pinned. Processing containers run without
network access. Paths and image filenames are treated as data and subprocesses
use argument arrays.

Bundle hooks execute local scripts before submission. They are disabled by
default, require explicit workstation enablement, read only the selected
input directory and bundle files, and modify no local data.

The Docker host configuration adds `job-user` to the `docker` group, which is
root-equivalent access. Only trusted jobs should use this dedicated fleet.

The only required infrastructure is a Deadline queue with job attachments and
the Docker-enabled fleet. Job attachments use the queue's existing S3 storage;
the user does not provision another bucket.

Cost is measured, not an optimization gate. Multiple cold workers each pull
about 1.55 GiB of ODM layers and materialize overlapping images and
intermediates. The benchmark below reports transfer and worker time for
attachment `COPIED` mode. `VIRTUAL` mode is unsupported based on the Brighton
compatibility test described above.

### Brighton Deadline Cloud validation

Validated on 2026-08-05 in `us-west-2` with `COPIED` job attachments and two
fresh Linux Spot workers. Each worker had 8 vCPUs, 32 GiB RAM, a 500-GiB root
volume, the Docker host configuration, and no cached ODM image. The submission
used 18 images, `TargetImagesPerSubmodel=6`, and
`MinimumSharedImages=3`, producing three submodels.

| Measurement | Result |
|---|---:|
| Submitted inputs | 23 files; 64.97 MB |
| Job wall time | 5 minutes 59 seconds |
| Fan-out | Two tasks overlapped on distinct workers in both fan-out steps |
| Selected automatic overlap | 26.854 m |
| Largest expanded submodel | 12 images |
| Peak sampled container memory | 941 MiB |
| Peak sampled project scratch | 0.721 GiB |
| Downloaded final outputs | 41 files; 21.82 MB |

The final manifest recorded 40 artifacts; every file size and SHA-256 matched.
GDAL reported an EPSG:32615 1300x1073 four-band orthophoto with meaningful RGB
statistics and a 2599x2147 DSM spanning 154.423 to 174.150 meters. PDAL read
724,585 colored LAZ points over matching bounds. A contrast-stretched preview
showed coherent coverage with only the expected transparent survey perimeter.

This smoke survey validates the five-stage graph, direct-dependency attachment
handoffs, automatic overlap, output download, and two-worker fan-out. It does
not calibrate the default split/overlap choices or the medium and large
resource profiles.

### Retry and cancellation validation

A one-worker COPIED Brighton run injected one test-only failure into
reconstruction submodel 1. Deadline retried only that task; submodels 0 and 2
each retained a zero retry count. All nine tasks then succeeded in 10 minutes
56 seconds. The downloaded result contained 41 files, and all 40 manifest
artifacts matched their declared sizes and SHA-256 checksums.

A separate run was canceled while submodel processing was executing
`DensifyPointCloud`. Six tasks had succeeded; the active task and its two
remaining tasks became canceled with no failed tasks and no merge success.
The wrapper logged `Cancellation requested; stopping process container`. A
follow-up Docker probe ran on the same worker and found no
`deadline-odm-parallel-*` containers. The fleet then returned to zero target
and zero running workers.

These tests used disposable validation-only bundle changes. Failure injection
and account-specific fleet attributes are not present in this sample.

### Data-zoo Deadline Cloud validation

Validated on 2026-08-05 in `us-west-2` with `COPIED` job attachments and four
fresh Linux Spot workers. Each worker had 8 vCPUs, 32 GiB RAM, a 500-GiB root
volume, the Docker host configuration, and no cached ODM image. The run used
all 524 images with the default processing and partition settings.

| Measurement | Result |
|---|---:|
| Submitted inputs | 524 JPEGs; 3,690,489,119 bytes |
| Job result | 15 of 15 tasks succeeded; no failures or retries |
| Job wall time | 2 hours 0 minutes 58 seconds |
| Prepare / reconstruct / align | 18:03 / 4:39 / 3:01 |
| Process / merge | 1:16:04 / 19:07 |
| Fan-out | Six reconstruction and six processing tasks across four workers |
| Recorded task-session time | 4.94 worker-hours |
| Base submodel sizes | 61, 87, 88, 112, 98, 78 images |
| Expanded submodel sizes | 71, 113, 115, 150, 131, 95 images |
| Selected automatic overlap | 76.429 m; connected at 10 shared images |
| Peak sampled container memory | 12.22 GiB |
| Peak sampled project scratch | 38.31 GiB during merge |
| Downloaded final outputs | 59 files; 2.25 GB in 66.8 seconds |

The initial upload sent 3.69 GB in 109.9 seconds. The prepare output manifest
described 15,931 files and 9.24 GB of logical data, but content addressing
uploaded only 116 MB of new blobs. One processing task published 3.43 GB in
78.5 seconds. Those measurements confirm correct cross-worker handoff, but
also show that `COPIED` mode spends substantial time materializing the
intermediate tree on each worker.

The final manifest declared 58 artifacts totaling 2,246,928,467 bytes; every
size and SHA-256 matched the downloaded file. GDAL reported an EPSG:32617
19794x11916 four-band orthophoto at 10 cm per pixel with 46.50 percent valid
coverage and meaningful RGB statistics. The DSM is EPSG:32617,
39587x23834 at 5 cm per pixel, with 46.78 percent valid coverage and finite
elevations from 121.314 to 215.747 meters. PDAL read 29,789,128 colored,
compressed LAZ points over matching bounds. A downsampled preview showed a
coherent survey with the expected transparent perimeter and no missing
submodel.

Spot prices observed during the run were $0.0870 to $0.1375 per hour for the
eligible `t3a.2xlarge` and `t3.2xlarge` types. Recorded task sessions imply
about $0.43 to $0.68 of raw EC2 Spot compute; four workers active for the full
wall time would be a conservative $0.70 to $1.11 upper bound. These estimates
exclude EBS, job-attachment S3, data transfer, and any Deadline Cloud service
charges. The fleet returned to zero target and zero running workers after the
job.

## Non-goals for version 1

- Non-geotagged or GCP-only surveys.
- Multispectral image groups and video input.
- Dynamic task creation after job creation.
- ClusterODM or NodeODM deployment.
- GPU processing.
- A merged textured OBJ or ODM PDF report.
- Multiple surveys in one job.
- Arbitrary shell arguments, image URLs, or unreviewed ODM flags.
- A promise that parallel execution costs less than the simple job.

## Resolved design choices

1. **General input:** use `InputImages` job attachments; Zoo is a benchmark.
2. **Split planning:** expose target images and overlap controls; use a
   pre-submission hook for task count and worker preprocessing for GPS overlap.
3. **Intermediates:** use job attachments only, with no extra user bucket.
4. **Resource sizing:** measured auto profile with explicit advanced
   overrides.
5. **Stage contracts:** derive them with pinned internals, file-access tracing,
   and fresh-container resume tests.
6. **Retention:** expose `RetainIntermediates`, default `False`, with the
   attachment-retention limitation documented.
7. **ODM integration:** use narrow, version-guarded wrappers.
8. **Quality gates:** calibrate metrics from repeat native/parallel runs on
   two public surveys before freezing thresholds.

See [TESTING.md](TESTING.md) for the local, Docker, Deadline, resilience,
quality, and scaling test matrix.
