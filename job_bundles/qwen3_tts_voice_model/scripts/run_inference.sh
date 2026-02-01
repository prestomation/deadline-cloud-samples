#!/bin/env bash
# Run TTS inference with fine-tuned Qwen3-TTS model
# Usage: run_inference.sh <model_dir> <speaker_name> <text> <output_file>

set -xeuo pipefail

MODEL_DIR="$1"
SPEAKER_NAME="$2"
TEXT="$3"
OUTPUT_FILE="$4"

echo "=== Qwen3-TTS Inference ==="
echo "Model: $MODEL_DIR"
echo "Speaker: $SPEAKER_NAME"
echo "Text: $TEXT"
echo "Output: $OUTPUT_FILE"

# Find the latest checkpoint
CHECKPOINT=$(ls -d "$MODEL_DIR"/checkpoint-epoch-* 2>/dev/null | sort -V | tail -1)
if [ -z "$CHECKPOINT" ]; then
    CHECKPOINT="$MODEL_DIR"
fi
echo "Using checkpoint: $CHECKPOINT"

python3 -c "
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    '$CHECKPOINT',
    device_map='cuda:0',
    dtype=torch.bfloat16,
    attn_implementation='flash_attention_2',
)

wavs, sr = model.generate_custom_voice(
    text='$TEXT',
    speaker='$SPEAKER_NAME',
)

sf.write('$OUTPUT_FILE', wavs[0], sr)
print(f'Audio saved to: $OUTPUT_FILE')
"

echo "Inference complete: $OUTPUT_FILE"
