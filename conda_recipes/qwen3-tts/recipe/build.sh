#!/bin/env bash
set -xeuo pipefail

cd "$SRC_DIR/qwen3_tts"

echo "openjd_status: Installing qwen-tts package"

pip install .

echo "openjd_status: Finished qwen3-tts package build"
