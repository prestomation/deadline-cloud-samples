# PaddleOCR simple document extraction

Runs one GPU task that inventories a copied directory attachment of PDFs and images, renders or
normalizes pages, and extracts structured layout results with PP-StructureV3. It writes a
per-document `document.md`, `document.json`, and top-level `manifest.json` to `OutputDir`.

## Prerequisites

- Deadline Cloud job attachments configured as `COPIED`; select `InputDocuments` and `OutputDir`
  as directory attachments.
- A Linux GPU fleet with at least one GPU and 32 GiB system memory. Workers need a compatible
  NVIDIA driver and public egress to PyPI, PaddlePaddle's package index, and PaddleOCR model
  downloads.
- Python 3 with `venv` on workers. This sample does not use containers, Conda, custom AMIs, or a
  queue environment.

## Submit

```console
deadline bundle submit job_bundles/paddleocr_simple_job \
  -p InputDocuments=/path/to/documents -p OutputDir=/path/to/output \
  --job-attachments-file-system COPIED
```

Accepted files are `pdf`, `jpg`, `jpeg`, `png`, `tif`, and `tiff`, recursively. Empty directories,
unsupported files, duplicate case-normalized relative paths, and more than 1,024 documents fail
before OCR begins.

## Runtime and outputs

The job environment creates a virtual environment and model cache beneath
`Session.WorkingDirectory`. Setup is once per worker session, not once globally across every
worker in the job. It installs pinned dependencies, selects the GPU PaddlePaddle runtime after
checking `nvidia-smi`, verifies imports, and preloads model assets as the PP-StructureV3 pipeline
starts. Failed package or model downloads remain visible in the session log.

The single task is intentional for small batches and preserves a complete top-level manifest with
source paths, page counts, model provenance, timing, and failures. GPU-worker time and attachment
storage are billable; remove output attachments when no longer needed.

## Test plan

The pipeline bundle's shared [test plan](../paddleocr_pipeline_job/TESTING.md)
covers this simple job's GPU canary and output-equivalence tests.
