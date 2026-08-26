# PaddleOCR job bundle test plan

> **Status: partially executed on Deadline Cloud on 2026-08-06.** The
> simple and pipeline canaries passed. Retry, corrupt-input,
> unavailable-egress, JPEG, and TIFF coverage remain outstanding.

This plan covers [PaddleOCR simple job](../paddleocr_simple_job/) and this
pipeline job. Complete the gates in order. Do not submit a full document batch
until copied-attachment handoff passes.

## Test environment

Use a test farm and queue with both CPU and GPU fleet associations:

| Resource | Requirements |
|---|---|
| CPU fleet | Linux, 32-64 GiB, maximum five workers, and `attr.GPU=No` |
| GPU fleet | Linux, A10G/L4/T4-class GPU, 32 GiB memory, and one to five GPUs |

Before a GPU test, an authorized operator must allow at least one GPU worker.
Restore the fleet's original maximum after testing. This plan does not modify
fleet capacity.

All workers need public egress to PyPI, PaddlePaddle's package endpoint, and
PaddleOCR model downloads. Session logs are the evidence for egress, GPU
driver/runtime, import, and model-cache checks.

## Fixtures and evidence

Create a small mixed fixture outside the repository:

```text
paddleocr-fixture/
├── invoice.pdf        # two pages: text and a table
├── receipt.jpg        # EXIF-rotated text image
└── nested/note.png    # text image
```

Record fixture checksums and expected page counts. Store evidence outside the
repository in `paddleocr-test-results/<UTC timestamp>/`, including commands,
Git revision, farm/queue/fleet/job/step/task/session/worker IDs, session logs,
manifests, and outputs. Do not store credentials or attachment URLs.

## Gate A: local correctness

| ID | Test | Pass criteria |
|---|---|---|
| A01 | Repository validation | `python3 scripts/validate_repository.py` passes. |
| A02 | OpenJD validation | `openjd check` and `openjd summary` pass for both templates. |
| A03 | Inventory failures | Empty input, unsupported files, normalized duplicate paths, and 1,025 documents fail locally. |
| A04 | Hook task ranges | One, several, and 1,024 documents produce identical `DocumentIndex` ranges in both pipeline fan-out steps. |
| A05 | Render/assembly script | Mixed PDF/image fixtures with mocked OCR yield ordered page manifests, Markdown, and JSON. |
| A06 | Parameter audit | Only input/output paths, OCR language, render DPI, and quality are visible to submitters. |

## Gate B: cloud canary and routing

Enable bundle hooks and submit a one-document fixture to the selected queue:

```console
deadline config set settings.allow_bundle_hooks true
deadline bundle submit job_bundles/paddleocr_simple_job \
  --profile <profile-name> \
  --farm-id <farm-id> \
  --queue-id <queue-id> \
  -p InputDocuments=/absolute/path/paddleocr-fixture \
  -p OutputDir=/absolute/path/paddleocr-output-simple \
  --job-attachments-file-system COPIED
```

| ID | Test | Pass criteria |
|---|---|---|
| B01 | GPU provisioning | The simple job runs on the GPU fleet with one GPU and 32 GiB memory. |
| B02 | GPU runtime | Session logs show the pinned GPU package, `paddle.device.is_compiled_with_cuda()` succeeds, and PP-StructureV3 assets populate the session cache. |
| B03 | CPU routing | Pipeline `RenderDocuments` and `AssembleResults` run on the CPU fleet, not the GPU fleet. |
| B04 | GPU routing | Pipeline `ParseDocuments` runs on the GPU fleet, not the CPU fleet. |
| B05 | Cross-fleet handoff | GPU parsing sees the CPU task's rendered pages and assembly sees all parse results when tasks use different workers. |
| B06 | Cache observation | Repeat the simple job on a retained worker when possible; cache reuse may improve timing but is not required for correctness. |

B05 is a hard gate. If it fails, stop and capture output-attachment metadata
and task logs. The intermediate transfer contract must be corrected before
running functional OCR tests.

## Executed evidence

The executed fixture contained `invoice.pdf` (five pages) and
`nested/note.png` (one page). Input checksums were recorded with the retained
test evidence outside the repository.

| Check | Result |
|---|---|
| Repository validation and focused tests | Passed: repository validation (35 tests), simple bundle tests (3), and pipeline bundle tests (2). |
| OpenJD | Passed: `openjd check` and parameterized `openjd summary` for both templates. |
| Simple GPU canary | Passed: produced two documents, six pages, Markdown, JSON, and a failure-free manifest. |
| Pipeline hook and routing | Passed: expanded two stable document indices. Render and assembly sessions used CPU workers; parsing used GPU workers. |
| Cross-fleet handoff | Passed: two CPU renders produced intermediates consumed by two GPU parses, followed by CPU assembly. Fifteen intermediate/customer-facing files downloaded successfully. |
| Output equivalence | Passed: simple and pipeline manifests match excluding simple-job elapsed time; Markdown hashes match. Structured JSON differs only in session-specific `input_path` values. |
| Cancellation | Passed: cancelled after rendering. Its outputs contain only eight intermediate render files and no final manifest. |
| Fleet cleanup | Passed: CPU minimum restored to zero; Linux GPU fleet restored to Spot, zero workers, 16-32 GiB memory, and one to five GPUs; Windows GPU fleet maximum restored to one. |

The first two failed simple canaries identified and corrected PaddleOCR 3.1
runtime compatibility issues: PaddleX is pinned to 3.1.0 with LangChain
0.2.17, and language mappings use PaddleX 3.1-compatible PP-OCRv4 recognition
models. An initial pipeline canary also showed that CPU steps could match the
GPU fleet; CPU stages now require `attr.GPU=No`.

## Gate C: functional output comparison

Run both bundles with the three-document fixture.

| ID | Test | Pass criteria |
|---|---|---|
| C01 | Simple contract | One top-level manifest and one Markdown/JSON directory per document, with source mapping, page counts, provenance, timing, and no unexpected failures. |
| C02 | Pipeline contract | The same customer-facing layout and document/page ordering as C01. |
| C03 | Equivalence | Document IDs, source paths, page counts, and page order match; compare Markdown after normalizing documented nondeterministic metadata only. |
| C04 | Input coverage | PDF page order, JPEG EXIF orientation, PNG, and TIFF normalization succeed. |
| C05 | Parameter coverage | Validate default `en`, 200 DPI, standard quality and one supported non-default language/quality/DPI combination. |
| C06 | Corrupt source | A corrupt PDF gives an actionable simple-job failure entry and no misleading successful document result. |

## Gate D: retries, failure, and cleanup

| ID | Test | Pass criteria |
|---|---|---|
| D01 | Render retry | Retrying one document replaces only its intermediate directory; sibling checksums remain unchanged. |
| D02 | Parse retry | Retrying one GPU task changes only that document's page results. |
| D03 | Assembly retry | Final manifest is atomically replaced and valid document outputs remain intact. |
| D04 | Cancellation | Cancellation during rendering or parsing publishes no partial customer-facing final manifest. |
| D05 | Egress failure | A controlled unavailable dependency/model source fails before work with the failing download command in session logs. |
| D06 | Cleanup | Workers return to zero, output/intermediate attachments are removed as appropriate, and GPU maximum returns to zero. |

The bundles are ready for normal use when A-C and D01-D04 pass, B05 proves
cross-fleet handoff, and the evidence identifies the expected CPU and GPU
fleets.
