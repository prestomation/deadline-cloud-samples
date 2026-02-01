# Qwen3 TTS Conda Recipe

This conda recipe builds the `qwen3-tts` package for voice model training and inference.

## Building the Package

Use the Deadline Cloud conda build job to build this package:

```bash
cd ~/deadline-cloud-samples/conda_recipes
./submit-package-job ~/qwen3_tts_voice_model/conda_recipe
```

Or manually with rattler-build:

```bash
rattler-build build --recipe ~/qwen3_tts_voice_model/conda_recipe/recipe/recipe.yaml
```

## Requirements

- CUDA-capable GPU
- Linux x86_64

## Package Contents

- `qwen3_tts.train` - Voice model training module
- `qwen3_tts.inference` - TTS inference module

## Usage in Job Bundle

Add to your queue environment's conda packages:

```
qwen3-tts ffmpeg
```
