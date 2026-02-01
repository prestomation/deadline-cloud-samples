# Qwen3 TTS Voice Model Training

Job bundles and conda recipe for training custom voice models using [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS).

## Contents

- `template.yaml` - Full training pipeline (preprocess → train → test inference)
- `inference_test/` - Simple inference test with built-in voices
- `conda_recipe/` - Conda package recipe (also in `conda_recipes/qwen3-tts/`)
- `scripts/` - Helper scripts for data preparation, training, and inference

## Overview

Qwen3-TTS supports:
- Voice cloning from 3-second audio samples
- Voice design via natural language descriptions  
- High-quality multilingual TTS (10 languages)
- Streaming generation with low latency

## Requirements

- GPU worker with `amount.worker.gpu >= 1`
- Linux worker
- Conda environment with PyTorch and transformers

## Quick Start - Inference Test

Test TTS with built-in voices (no training required):

```bash
deadline bundle submit job_bundles/qwen3_tts_voice_model/inference_test \
    --parameter Text="Hello, this is a test." \
    --parameter Speaker="Ryan" \
    --parameter Language="English" \
    --parameter OutputDir=/path/to/output
```

Built-in speakers: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee

## Training Pipeline

For custom voice training:

```bash
deadline bundle submit job_bundles/qwen3_tts_voice_model \
    --parameter AudioInputDir=/path/to/audio \
    --parameter TranscriptFile=/path/to/train.jsonl \
    --parameter RefAudio=/path/to/reference.wav \
    --parameter OutputModelDir=/path/to/output
```

### Transcript JSONL Format

```json
{"audio": "./data/utt0001.wav", "text": "The transcript text.", "ref_audio": "./data/ref.wav"}
```

## Building the Conda Package

```bash
cd conda_recipes
./submit-package-job qwen3-tts
```

## Testing Summary

### Test Results (2026-02-01)

| Job | Status | Notes |
|-----|--------|-------|
| CondaBuild: qwen3-tts (v1) | FAILED | YAML syntax error in test scripts |
| CondaBuild: qwen3-tts (v2) | FAILED | S3 permissions - queue role missing `s3:PutObject` on `Conda/*` |
| CondaBuild: qwen3-tts (v3) | FAILED | Missing conda channel (conda-forge) |
| CondaBuild: qwen3-tts (v4) | FAILED | Missing setuptools in build deps |
| CondaBuild: qwen3-tts (v5) | **SUCCESS** | Package built and uploaded to S3 |
| Inference Test (v1) | FAILED | Conda package missing torch (only had python) |
| Inference Test (v2) | PENDING | Using pip install qwen-tts at runtime |

### Key Learnings

1. **Queue IAM Role**: Needed to add `s3:PutObject` permission for `Conda/*` prefix
2. **Conda Recipe**: Must include `setuptools` and `wheel` in build requirements
3. **Package Dependencies**: For ML packages, either include all deps in conda recipe OR pip install at runtime
4. **Fleet Requirements**: Training requires GPU fleet - current fleet only has CPU workers

### Infrastructure Notes

- Queue: `RenderingAgentSpacesWorkshop`
- Fleet: Service-managed EC2, Linux x86_64, 1-4 vCPU, 4-32GB RAM, **no GPU**
- S3 Channel: `s3://rendering-agent-spaces-workshop/Conda/qwen3-tts`

## References

- [Qwen3-TTS GitHub](https://github.com/QwenLM/Qwen3-TTS)
- [Qwen3-TTS Paper](https://arxiv.org/abs/2601.15621)
- [Hugging Face Models](https://huggingface.co/collections/Qwen/qwen3-tts)
