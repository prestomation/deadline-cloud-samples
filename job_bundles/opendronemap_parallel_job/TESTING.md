# OpenDroneMap parallel job testing plan

> **Status: implementation validation in progress.**
>
> The bundle has completed local and Deadline Cloud Brighton Beach runs plus
> a four-worker, 524-image Deadline Cloud scale run. This plan defines the
> remaining evidence required before removing the experimental status. It
> complements the customer-facing [README.md](README.md).

## Objectives

Testing must prove that:

1. A user-selected geotagged JPEG directory produces the correct static
   Deadline task graph without template editing.
2. ODM 3.6.1 can resume correctly across the proposed prepare, reconstruct,
   align, process, and merge boundaries.
3. Job attachments carry all cross-worker inputs and intermediates without a
   user-managed bucket or filesystem.
4. Automatic partition and resource choices are defensible for supported
   inputs and fail clearly outside their validated range.
5. Retry, worker loss, and cancellation do not corrupt sibling submodels or
   leave Docker containers running.
6. Final GeoTIFF, LAZ, and elevation outputs are structurally valid, spatially
   coherent, and comparable to native ODM split/merge.
7. The workflow generalizes beyond the primary ODM data-zoo benchmark.
8. A dedicated service-managed fleet returns to zero workers after testing.

## Test environments

### Submission workstation

- macOS, Linux, and Windows are supported submission targets.
- Python 3 with PyYAML.
- Deadline Cloud CLI 0.58.0 or newer, because template-modifying bundle hooks
  are required.
- Bundle hooks enabled:

  ```console
  deadline config set settings.allow_bundle_hooks true
  ```

- OpenJD CLI for template validation.
- Enough local disk to hold the selected survey while Deadline hashes and
  uploads it.

The first implementation cycle may use macOS only, but Linux and Windows hook
fixtures must pass before publication.

### Local Docker host

- Linux x86_64 with Docker Engine.
- At least 8 vCPUs, 32 GiB memory, and 200 GiB free disk for full benchmark
  work. Increase these values if measurement shows they are insufficient.
- Pinned ODM image:

  ```text
  opendronemap/odm:3.6.1@sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d
  ```

- GDAL and PDAL command-line tools for output validation.
- Optional QGIS, CloudCompare, and an OBJ-independent raster thumbnail tool
  for visual inspection.

An ARM64 Docker host provides image-compatibility smoke coverage. Full
Deadline validation targets service-managed architectures currently supported
by Deadline Cloud.

### Deadline Cloud

- A dedicated test farm/queue or an existing test queue with job attachments.
- A dedicated Linux service-managed fleet using
  `host_configuration_scripts/docker_engine/linux.sh`.
- Fleet attribute `attr.OpenDroneMap=docker_3_6_1`.
- Minimum workers `0`.
- Maximum workers initially `2`, then increased only for the full fan-out
  tests.
- Spot capacity unless it prevents a controlled retry test.
- Root disk sized from local measurements.
- Outbound access to Docker Hub.

Every job step must require both Linux and
`attr.OpenDroneMap=docker_3_6_1`. A routing-negative test must prove the job
cannot run on a Linux fleet without that attribute.

## Test datasets

### F0: Generated fixtures

Small generated directories test inventory and rejection behavior without
photogrammetry:

- Empty directory.
- Valid minimal JPEG headers with dimensions.
- Corrupt and truncated JPEGs.
- Duplicate basenames in nested directories.
- Duplicate content under different names.
- Mixed extensions and ignored files.
- Missing, malformed, and outlier GPS metadata.
- Paths containing spaces and non-ASCII characters.

Generated fixtures never stand in for end-to-end ODM quality tests.

### F1: Brighton Beach smoke survey

Use the pinned 18-image Brighton Beach dataset from the simple job:

- Commit: `9506a9bf09c9678b7d0b80b014af5b606c8a7255`.
- Archive SHA-256:
  `4ec7c469ae9242bd7a08eec46bb5b2442bcae904e43c3b7c9d48d5de2fb538a7`.

Set a small target such as six images per submodel to exercise all five stages
and multiple tasks cheaply. This is a workflow smoke test, not evidence that
the default target or overlap is good.

### F2: Primary scale benchmark

Use the OpenDroneMap data zoo:

- Commit: `60a74095e297d76062ba14312fa581a74021916a`.
- 524 JPEGs under `images/`.
- Current source-image bytes: `3,690,489,119`.
- License: CC0-1.0.
- Archive SHA-256:
  `a7a86646e8bd7a170a736d8f0973424e552a7454cbc04c1ffec58b104a99a220`.

This dataset establishes partition, resource, transfer, and scaling behavior.

### F3: Secondary public survey

Select and pin a second public geotagged RGB survey before quality thresholds
or resource profiles are called general. It must differ from F2 in:

- Image count and source resolution.
- Camera model.
- Flight geometry and image spacing.
- Terrain/elevation variation.
- Surface texture or vegetation.

Record URL, immutable version, license, archive checksum, image inventory, and
GPS audit. Thresholds calibrated on F2 must pass F3 without retuning.

## Evidence storage

Do not commit large test data or generated outputs. Store evidence outside the
repository under a run-specific directory such as:

```text
open-drone-map-parallel-test-results/
`-- 2026-08-04T120000Z/
    |-- environment.json
    |-- commands.log
    |-- test-results.json
    |-- submissions/
    |   `-- <job-id>/
    |       |-- job.json
    |       |-- steps.json
    |       |-- tasks.json
    |       |-- workers.json
    |       |-- logs/
    |       |-- manifests/
    |       |-- metrics/
    |       `-- outputs/
    |-- local/
    |-- comparisons/
    `-- screenshots/
```

For every test record:

- Test ID and exact command.
- Git commit/worktree diff identifier.
- UTC start/end timestamps.
- Dataset manifest checksum.
- Expanded template checksum.
- Farm, queue, fleet, job, step, task, session, and worker IDs when relevant.
- Terminal state and pass/fail reason.
- Docker/ODM/OpenSfM identity.
- Host architecture and allocated resources.
- Logs, output manifests, and measured metrics.

Secrets, credentials, local usernames, and account-specific URLs must not be
added to the repository.

## Test order and gates

Tests run in the order below. A failed gate blocks later expensive stages
unless the failure is explicitly classified as test-infrastructure-only.

### Gate A: Static and hook correctness

| ID | Test | Pass criteria |
|---|---|---|
| A01 | Repository validation | Repository tests and Markdown links pass. |
| A02 | Shell and Python static checks | Bash syntax, ShellCheck, Python compilation, formatter, and configured linters pass. |
| A03 | Base template validation | Placeholder template passes `openjd check`; summary shows the five expected steps. |
| A04 | Hook expansion validation | Every expanded fixture passes `openjd check` and `openjd summary`. |
| A05 | Parameter surface audit | No arbitrary URL, shell command, raw ODM argument, mutable image identity, or unreviewed flag is exposed. |
| A06 | Host-requirement audit | Every expanded step requires Linux, Docker capability, measured vCPU, memory, and scratch. |
| A07 | Documentation contract | README parameters, template definitions, hook behavior, and output contract agree. |

Expected commands after implementation:

```console
bash -n scripts/*.sh tests/*.sh
shellcheck scripts/*.sh tests/*.sh
python3 -m compileall scripts tests
openjd check template.yaml
openjd summary template.yaml
python3 ../../scripts/validate_repository.py
```

### Gate B: Submission preflight

| ID | Test | Pass criteria |
|---|---|---|
| B01 | Empty/missing input | Hook aborts before upload with an actionable path error. |
| B02 | File inventory | Supported JPEGs are counted identically across fixtures; unrelated files are handled as documented. |
| B03 | Header validation | Corrupt/truncated JPEG and zero dimensions are rejected locally. |
| B04 | Path handling | Spaces, Unicode, long paths, nested paths, and symlinks follow the documented policy on each submission OS. |
| B05 | Name collision | Duplicate staged names are rejected before upload. |
| B06 | Task count | Counts for 1, 2, several, and 1024 submodels expand both fan-out ranges identically. |
| B07 | Task limit | A 1025-submodel plan is rejected with the minimum acceptable larger target size. |
| B08 | Parameter precedence | GUI, CLI `-p`, parameter file, and defaults produce the same resolved plan. |
| B09 | Resource selection | Auto, named, and manual resource modes rewrite requirements as documented. |
| B10 | Hook safety | Hook reads only selected inputs/bundle files, writes no local data, and emits only protocol JSON on stdout. |
| B11 | Disabled hook | Submission cannot accidentally run the placeholder range; worker sentinel also rejects an unexpanded template. |
| B12 | Debug snapshot | `--save-debug-snapshot` contains the expected attachments, parameters, and expanded task ranges. |

### Gate C: Worker input validation and partitioning

| ID | Test | Pass criteria |
|---|---|---|
| C01 | Hook/worker agreement | Worker image count and dimensions match hidden preflight values. |
| C02 | Missing GPS | Prepare fails before fan-out and lists every affected image. |
| C03 | Invalid GPS/outlier | Invalid ranges and reviewed outlier policy produce deterministic diagnostics. |
| C04 | Duplicate content | Duplicate policy is enforced and manifest ordering remains deterministic. |
| C05 | Base task count | Pinned OpenSfM creates exactly `ceil(N / target)` base clusters. |
| C06 | Automatic overlap | Selected radius produces a connected intersection graph within expansion limits. |
| C07 | Disconnected flights | Auto mode fails instead of selecting an extreme overlap. |
| C08 | Manual overlap valid | Requested radius is used exactly and diagnostics show a valid graph. |
| C09 | Manual overlap invalid | Prepare fails before reconstruction with connectivity evidence. |
| C10 | Plan persistence | Every downstream retry consumes the original authoritative manifest and never reclusters. |

### Gate D: ODM boundary contracts

Run every wrapper in a fresh container with networking disabled.

| ID | Test | Pass criteria |
|---|---|---|
| D01 | Image identity | Digest, ODM version, and OpenSfM commit match pins; mismatch fails. |
| D02 | Prepare boundary | Minimal declared artifacts resume reconstruction in a fresh container. |
| D03 | Reconstruction boundary | Minimal outputs resume alignment; missing required files fail. |
| D04 | Alignment boundary | Aligned outputs resume processing; unaligned/corrupt reconstruction fails. |
| D05 | Process boundary | Minimal submodel products resume merge. |
| D06 | Merge boundary | Merge creates only the supported orthophoto, LAZ, DSM, and optional DTM contract. |
| D07 | File-access trace | Observed file reads are a subset of the documented stage contract. |
| D08 | Delete-one tests | Removing every required artifact causes the expected deterministic failure. |
| D09 | Exit propagation | Each wrapper returns Docker/ODM's exact nonzero exit code. |
| D10 | Cancellation | SIGTERM stops and removes the named container within the notify period. |

### Gate E: Job-attachment canary

Use tiny generated files before ODM data:

| ID | Test | Pass criteria |
|---|---|---|
| E01 | Prepare to fan-out | Parallel tasks on different workers receive coordinator outputs. |
| E02 | Fan-out isolation | Each task writes only its stable unique directory. |
| E03 | Fan-out to coordinator | Alignment-like task sees every successful submodel. |
| E04 | Revised handoff | Second fan-out receives coordinator-rewritten artifacts. |
| E05 | Final root | Merge-like task reads all intermediates and publishes a separate final root. |
| E06 | Retry | Retrying one task leaves sibling checksums and manifests unchanged. |
| E07 | Manifest chronology | Earlier outputs remain available; later same-path files supersede them as documented. |
| E08 | Deletion semantics | Deleting local intermediates does not falsely claim removal from earlier output manifests. |
| E09 | COPIED mode | Cross-worker handoff succeeds and transferred bytes are recorded. |
| E10 | VIRTUAL mode | Compatibility result and required fallback or submission mode are documented. |
| E11 | Final-only download | Downloading MergeSurvey step output excludes the hidden root. |
| E12 | Retained download | Opt-in output includes the curated intermediate tree and stage logs. |

No full ODM cloud job proceeds until this gate passes.

### Gate F: Local end-to-end surveys

| ID | Dataset | Mode | Pass criteria |
|---|---|---|---|
| F01 | F1 | Deadline-shaped sequential graph | All five stages and multiple submodels succeed. |
| F02 | F1 | Native ODM split/merge | Produces the supported reference outputs. |
| F03 | F2 | Deadline-shaped sequential graph, auto overlap | Completes with valid stage manifests and outputs. |
| F04 | F2 | Native ODM split/merge | Completes with identical input and processing settings. |
| F05 | F2 | Manual 150 m overlap | Completes and records comparison with automatic overlap. |
| F06 | F2 | DTM enabled | Valid merged DTM is produced. |
| F07 | F2 | Retain intermediates | Curated retained tree matches its manifest. |
| F08 | F3 | Deadline-shaped sequential graph | General input succeeds without dataset-specific code. |
| F09 | F3 | Native ODM split/merge | Produces a second reference output set. |

### Gate G: Deadline functional submissions

| ID | Dataset | Fleet width | Pass criteria |
|---|---|---:|---|
| G01 | F1 | 1 | Small real survey succeeds through attachments. |
| G02 | F1 | 2 | At least two submodel tasks overlap on different workers. |
| G03 | F2 | 1 | Cloud sequential baseline succeeds. |
| G04 | F2 | 2 | Cross-worker graph succeeds with identical final contract. |
| G05 | F2 | Intended maximum | Useful fan-out occurs without coordinator starvation. |
| G06 | F3 | 2 or more | Second survey succeeds without template/code changes. |
| G07 | F2 | Intended maximum, DTM | Optional DTM path succeeds. |
| G08 | F2 | Intended maximum, retained | Retention parameter produces documented output. |
| G09 | F2 | Cold fleet | Cold image pull, attachment materialization, and total runtime are measured. |
| G10 | F2 | Warm fleet | Cache benefit is measured without being required for correctness. |

For each job, verify step dependencies, task counts, worker IDs, status/progress
messages, manifests, and output downloads.

### Gate H: Routing, retry, failure, and cancellation

Failure injection must use test-only scripts or infrastructure controls. Do
not expose public failure flags.

| ID | Test | Pass criteria |
|---|---|---|
| H01 | Fleet routing positive | Every task runs on a worker with the required capability. |
| H02 | Fleet routing negative | Job remains unscheduled when only an incompatible fleet is available. |
| H03 | Docker pull failure | Prepare fails with pull diagnostics and no processing container. |
| H04 | Input mismatch | Worker rejects a hook/attachment inventory mismatch before fan-out. |
| H05 | Reconstruction nonzero | Exact exit propagates; sibling tasks remain valid. |
| H06 | Missing reconstruction artifact | Task fails validation even if ODM exits zero. |
| H07 | Alignment failure | Process tasks do not start. |
| H08 | Missing process artifact | Merge does not start or fails before partial publication. |
| H09 | Merge nonzero/missing final | Job fails and no success manifest is written. |
| H10 | Automatic task retry | One-shot failure succeeds on retry without changing sibling checksums. |
| H11 | Worker interruption | Retried task resumes from attachment inputs on another worker. |
| H12 | Cancel Prepare | Container exits within notify period; downstream steps never start. |
| H13 | Cancel reconstruction fan-out | All active containers stop; completed siblings remain diagnosable. |
| H14 | Cancel Align | Process and merge never start. |
| H15 | Cancel processing fan-out | All active containers stop; no merge success is published. |
| H16 | Cancel Merge | No success manifest; partial logs remain downloadable. |

### Gate I: Output structure and visual quality

#### Structural checks

| ID | Artifact | Checks |
|---|---|---|
| I01 | Orthophoto | `gdalinfo`, CRS, pixel size, bands, nodata, bounds, nonempty valid mask. |
| I02 | DSM/DTM | `gdalinfo`, CRS/bounds agreement, resolution, nodata, finite elevation distribution. |
| I03 | LAZ | `pdal info`, CRS, bounds, point count, density, classifications, finite coordinates. |
| I04 | Manifest | Input, stage, parameter, version, runtime, and artifact checksums are complete. |
| I05 | Logs | Every stage/submodel has complete raw and structured status logs. |

#### White-blob and coverage checks

The earlier simple-job review showed that a naive TIFF viewer can make valid
geospatial rasters look white. Tests must distinguish display scaling from
bad data:

1. Compute per-band min/max, percentiles, histogram, nodata ratio, and valid
   mask.
2. Generate contrast-stretched PNG previews from valid pixels.
3. Measure connected interior nodata holes and valid-data area.
4. Open GeoTIFFs in QGIS with percentile stretch.
5. Compare georeferenced bounds and coverage against source-image GPS extent.

A white default preview is not a failure when numeric ranges and a stretched
preview are valid. A near-empty valid mask, saturated source values, or large
unexplained interior holes is a failure.

#### Native-reference comparison

For F2 and F3, run at least three native and three parallel executions:

- CRS and pixel size are hard invariants.
- Compare orthophoto/DEM bounds, valid area, nodata, coverage IoU, and seams.
- Compare LAZ bounds, point count, density, and classifications.
- Compare DSM/DTM elevation difference percentiles on common valid pixels.
- Visually inspect raster and point-cloud alignment.

Set thresholds from native-to-native and parallel-to-parallel variation plus
a reviewed safety margin. Calibrate on F2, then apply to F3 without retuning.

### Gate J: Resource and scaling validation

| ID | Test | Pass criteria |
|---|---|---|
| J01 | Instrumentation accuracy | Container RSS, host memory, scratch, bytes, CPU, and runtime samples reconcile with logs. |
| J02 | Auto estimate on F1 | Requirements cover measured peaks with required headroom. |
| J03 | Auto estimate on F2 | Every stage has at least 30 percent memory and scratch headroom. |
| J04 | Auto estimate on F3 | Held-out survey stays within the approved estimator error. |
| J05 | Manual override | Expanded requirements exactly match valid overrides. |
| J06 | Undersized override | Expected OOM/disk failure is clear and does not corrupt output. |
| J07 | Unsupported envelope | Hook rejects input outside measured bounds with a concrete profile recommendation. |
| J08 | Fleet width sweep | Record widths 1, 2, 4, and available maximum. |
| J09 | Scaling efficiency | Record wall time, worker-minutes, utilization, and attachment overhead per width. |
| J10 | Coordinator bottleneck | Prepare/align/merge wait and runtime are quantified. |
| J11 | Cold/warm comparison | Image and attachment caching effects are reported separately. |

There is no requirement that parallel execution cost less. The result must
state where wall-time gains stop justifying additional worker-minutes.

### Gate K: Security and cleanup

| ID | Test | Pass criteria |
|---|---|---|
| K01 | Container network | Processing containers have networking disabled. |
| K02 | Mount scope | Containers receive only required attachment/session paths. |
| K03 | Archive/path handling | Traversal, symlink escape, and unsafe filenames are rejected. |
| K04 | Command construction | Filenames never become shell code; subprocess argument arrays are used. |
| K05 | Hook scope | Hook performs no network calls and writes no input files. |
| K06 | Docker cleanup | No named test container remains after success, failure, retry, or cancellation. |
| K07 | Job cleanup | No nonterminal test job remains after the run. |
| K08 | Scale to zero | Fleet target and running worker counts return to zero after idle timeout. |

## Autonomous cloud execution procedure

Once implementation passes Gates A-F, the test operator may execute Gates
G-K autonomously against the configured test profile:

1. Resolve and record the explicit farm, queue, and dedicated fleet IDs.
2. Reconfirm the fleet has minimum workers zero and the required attribute.
3. Set maximum workers to the current test's bounded width.
4. Submit only jobs carrying an `odm-parallel-validation` name/tag convention.
5. Wait for terminal state and collect evidence before the next large run.
6. Use test-only expanded templates for failure injection; never alter the
   public parameter surface.
7. Cancel only jobs created by this test run.
8. Never delete or modify unrelated farms, queues, fleets, jobs, or outputs.
9. After every cloud test batch, cancel nonterminal test jobs, restore fleet
   minimum workers to zero, and verify scale-to-zero.

Run at most one F2/F3 full-survey job at a time until resource estimates have
been validated. Cost is not a primary constraint, but bounded fleet width
prevents accidental runaway capacity.

## Stop conditions

Stop new submissions and preserve evidence when:

- The expanded template has unexpected steps, parameters, task counts, or
  host requirements.
- A task runs on a fleet without the required capability.
- Hook and worker image inventories differ.
- More workers launch than the configured test maximum.
- A worker repeatedly runs out of disk or memory outside an intentional
  undersizing test.
- Cancellation leaves an active container after the notification period.
- Attachment outputs from one submodel overwrite another.
- Merge publishes a success manifest with missing or invalid artifacts.
- A quality hard invariant fails.
- Testing would require modifying unrelated customer resources.

Resume only after the cause is understood and the relevant earlier gate is
rerun.

## Publication acceptance

The sample is ready to publish when:

- Gates A-K pass.
- F2 and F3 both pass native-reference quality thresholds.
- Automatic partitioning and resource sizing have documented supported
  envelopes.
- At least one full job demonstrates concurrent tasks on distinct workers.
- Retry, worker interruption, and cancellation evidence is complete.
- Final-only and retained-intermediate download behavior is documented.
- Measured cold/warm runtime, worker-minutes, memory, disk, transfer, and cost
  are in the README.
- The dedicated fleet has scaled to zero.
- No unresolved severity-high correctness, security, or data-loss issue
  remains.

## Execution record

The 2026-08-05 F2 cloud run used four fresh 8-vCPU, 32-GiB Spot workers
with 500-GiB root volumes and `COPIED` attachments. All 15 tasks succeeded
without retry in 2:00:58. Six submodels used automatic 76.429 m overlap;
peak sampled container memory was 12.22 GiB and peak sampled project scratch
was 38.31 GiB. The final-only download contained 59 files and 2.25 GB.
Manifest hashes, GDAL checks, PDAL checks, a visual preview, and fleet
scale-to-zero all passed. See the customer-facing
[benchmark record](README.md#data-zoo-deadline-cloud-validation) for measured
transfer, output, and cost details.

Two 2026-08-05 Brighton diagnostics used VIRTUAL attachments. In the first,
VFS mounted, Docker processed the survey, and Prepare completed, but
task-output publication remained active for more than 16 minutes with no S3
traffic before cancellation. A second diagnostic confirmed that materializing
OpenSfM's internal links through the VFS also failed to complete within 10
minutes. That workaround was not retained. The sample now requires COPIED
attachment mode.

A controlled COPIED retry run injected one reconstruction failure for
submodel 1. Deadline retried that task once; submodels 0 and 2 each succeeded
with zero retries. All nine tasks succeeded in 656.3 seconds, and all 40 final
manifest artifacts passed size and SHA-256 verification.

A cancellation run was stopped while `DensifyPointCloud` was active in a
processing container. It ended with six succeeded, three canceled, and zero
failed tasks. The wrapper logged its container-stop status. A subsequent
probe on the same worker found no named ODM containers. The dedicated fleet
returned to zero target and zero running workers.

Populate this table during implementation and link each row to retained
evidence outside the repository:

| Gate | Status | Evidence | Notes |
|---|---|---|---|
| A: Static and hook correctness | Passed | Local validation record | ShellCheck, 23 bundle tests, repository validation, base and expanded OpenJD checks passed. |
| B: Submission preflight | Partial | Brighton debug snapshot | Real CLI hook expanded 18 images to three submodels; remaining OS and parameter-precedence cases are open. |
| C: Input and partitioning | Partial | Local and cloud Brighton runs | Automatic overlap produced a connected three-submodel graph; rejection matrix remains open. |
| D: ODM boundaries | Partial | Local Brighton run | All five fresh-container stages passed; file tracing and delete-one matrix remain open. |
| E: Attachment canary | Partial | COPIED production runs and VIRTUAL diagnostics | Direct dependency closure, same-path supersession, final-only download, and mode compatibility are documented; retry and retention remain open. |
| F: Local end-to-end | Partial | Brighton three-submodel run | Five-stage automatic-overlap run passed; local data-zoo, native reference, and secondary survey remain open. |
| G: Deadline functional | Partial | Brighton and data-zoo cloud runs | Data zoo completed 15 tasks across four workers with no retry; width-one baseline, DTM, retention, warm-cache, and secondary survey remain open. |
| H: Failure/cancellation | Partial | Routing, retry, and active-process cancellation runs | Dedicated routing, H10 automatic retry, and H15 processing cancellation passed; the remaining injected-failure and interruption cases are open. |
| I: Output quality | Partial | Downloaded Brighton and data-zoo outputs | Manifest hashes, GDAL, PDAL, bounds, numeric statistics, and visual previews passed; native tolerances remain open. |
| J: Resource/scaling | Partial | Brighton and data-zoo metrics | F2 auto profile covered 12.22-GiB memory and 38.31-GiB scratch peaks; width sweep and held-out estimator validation remain open. |
| K: Security/cleanup | Partial | Docker and fleet records | Network-disabled containers, same-worker cancellation cleanup, no nonterminal jobs, and fleet scale-to-zero passed; the remaining path and failure cleanup cases are open. |
