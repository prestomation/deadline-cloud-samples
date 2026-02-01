# Qwen3-TTS Conda Recipe

Conda recipe for building the qwen3-tts package for voice model training and inference.

## Building

```bash
cd ~/deadline-cloud-samples/conda_recipes
./submit-package-job qwen3-tts
```

Or with explicit parameters:

```bash
deadline bundle submit conda_build_linux_package \
    --parameter RecipeDir=/path/to/qwen3-tts/recipe \
    --parameter BuildTool=rattler-build \
    --parameter S3CondaChannel=s3://YOUR_BUCKET/Conda/qwen3-tts \
    --parameter CondaChannels="conda-forge"
```

## Requirements

- rattler-build (specified via `BuildTool=rattler-build`)
- conda-forge channel for Python and dependencies

## Package Contents

The built package provides a minimal Python environment. The actual `qwen-tts` pip package should be installed at runtime for full functionality.

## Notes

- Uses rattler-build format (`recipe.yaml`)
- Requires `setuptools` and `wheel` in build dependencies
- Queue role needs S3 write permissions to the Conda channel prefix
