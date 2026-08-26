# PaddleOCR document extraction pipeline

Uses one CPU render task and one GPU PP-StructureV3 task per input document, then one CPU assembly
task. Select this sample when PDF rendering can scale separately from GPU OCR.

## Prerequisites and submission

Use `COPIED` job attachments, a Linux CPU fleet with at least 8 GiB system memory that advertises
the custom worker attribute `attr.GPU=No`, and a Linux GPU fleet with at least one GPU and 32 GiB
system memory. GPU drivers must support the tested
PaddlePaddle CUDA runtime. Every worker needs public egress to PyPI, PaddlePaddle's package index,
and PaddleOCR model downloads.

Bundle hooks must be enabled on the submitting workstation:

```console
deadline config set settings.allow_bundle_hooks true
deadline bundle submit job_bundles/paddleocr_pipeline_job \
  -p InputDocuments=/path/to/documents -p OutputDir=/path/to/output \
  --job-attachments-file-system COPIED
```

The local hook inventories the selected directory and replaces placeholder ranges with stable
`DocumentIndex` values. It rejects empty input, unsupported files, duplicate case-normalized paths,
and more than 1,024 documents. It needs PyYAML in the workstation `python3` environment.

## Data flow and retries

`RenderDocuments` creates immutable per-document page manifests in the hidden intermediate output
attachment. `ParseDocuments` reads the matching document ID, writes page-level results, and
`AssembleResults` atomically publishes only `documents/<document-id>/document.md`,
`document.json`, and `manifest.json` to `OutputDir`. A retry only replaces its document ID's
intermediate directory; siblings are unaffected. Cancellation before assembly leaves no final
manifest.

Intermediate attachments are retained for cross-fleet data handoff and can materially increase
attachment storage and transfer cost. Delete them after investigation.

## Session lifecycle

The job environment creates its virtual environment and model cache under `Session.WorkingDirectory`.
This occurs once per worker session, not once globally for the job. CPU sessions install the pinned
CPU runtime; GPU sessions install and validate the GPU runtime and preload the selected
PP-StructureV3 assets into their session-local model cache. Package and model download failures are
reported in the session log with the failing command.

## Test plan

See the shared [test plan](TESTING.md) for CPU/GPU fleet requirements, the
routing canary, attachment-handoff gate, output comparison, retry, and cleanup
procedures.
