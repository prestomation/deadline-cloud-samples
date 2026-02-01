#!/bin/env bash
# Fine-tune Qwen3-TTS voice model
# Usage: train_voice_model.sh <base_model> <train_jsonl> <output_dir> <speaker_name> <epochs> <batch_size> <lr>

set -xeuo pipefail

BASE_MODEL="$1"
TRAIN_JSONL="$2"
OUTPUT_DIR="$3"
SPEAKER_NAME="$4"
NUM_EPOCHS="$5"
BATCH_SIZE="$6"
LR="$7"

echo "=== Qwen3-TTS Fine-tuning ==="
echo "Base model: $BASE_MODEL"
echo "Training data: $TRAIN_JSONL"
echo "Output: $OUTPUT_DIR"
echo "Speaker: $SPEAKER_NAME"
echo "Epochs: $NUM_EPOCHS, Batch: $BATCH_SIZE, LR: $LR"

mkdir -p "$OUTPUT_DIR"

# Clone Qwen3-TTS repo for finetuning scripts
if [ ! -d "/tmp/Qwen3-TTS" ]; then
    git clone --depth 1 https://github.com/QwenLM/Qwen3-TTS.git /tmp/Qwen3-TTS
fi

cd /tmp/Qwen3-TTS/finetuning

# Run fine-tuning
python sft_12hz.py \
    --init_model_path "$BASE_MODEL" \
    --output_model_path "$OUTPUT_DIR" \
    --train_jsonl "$TRAIN_JSONL" \
    --batch_size "$BATCH_SIZE" \
    --lr "$LR" \
    --num_epochs "$NUM_EPOCHS" \
    --speaker_name "$SPEAKER_NAME"

echo "Fine-tuning complete. Model saved to $OUTPUT_DIR"
