#!/bin/env bash
# Prepare training data for Qwen3-TTS fine-tuning
# Usage: prepare_training_data.sh <audio_dir> <transcript_jsonl> <ref_audio> <output_jsonl>

set -xeuo pipefail

AUDIO_DIR="$1"
TRANSCRIPT_JSONL="$2"
REF_AUDIO="$3"
OUTPUT_JSONL="$4"

WORK_DIR=$(dirname "$OUTPUT_JSONL")
RAW_JSONL="$WORK_DIR/train_raw.jsonl"

# If no transcript provided, generate from audio files
if [ -z "$TRANSCRIPT_JSONL" ] || [ ! -f "$TRANSCRIPT_JSONL" ]; then
    echo "No transcript file provided, generating from audio files..."
    
    # Find first audio file to use as ref if not provided
    if [ -z "$REF_AUDIO" ] || [ ! -f "$REF_AUDIO" ]; then
        REF_AUDIO=$(find "$AUDIO_DIR" -name "*.wav" | head -1)
        echo "Using first audio as reference: $REF_AUDIO"
    fi
    
    # Generate JSONL entries for each audio file
    > "$RAW_JSONL"
    for AUDIO_FILE in "$AUDIO_DIR"/*.wav; do
        [ -f "$AUDIO_FILE" ] || continue
        BASENAME=$(basename "$AUDIO_FILE" .wav)
        # Placeholder text - in production you'd use ASR
        echo "{\"audio\":\"$AUDIO_FILE\",\"text\":\"$BASENAME\",\"ref_audio\":\"$REF_AUDIO\"}" >> "$RAW_JSONL"
    done
else
    # Use provided transcript, ensure ref_audio is set
    if [ -z "$REF_AUDIO" ] || [ ! -f "$REF_AUDIO" ]; then
        cp "$TRANSCRIPT_JSONL" "$RAW_JSONL"
    else
        # Add ref_audio to each line if not present
        python3 -c "
import json
import sys

with open('$TRANSCRIPT_JSONL', 'r') as f_in, open('$RAW_JSONL', 'w') as f_out:
    for line in f_in:
        data = json.loads(line.strip())
        if 'ref_audio' not in data or not data['ref_audio']:
            data['ref_audio'] = '$REF_AUDIO'
        f_out.write(json.dumps(data) + '\n')
"
    fi
fi

echo "Raw training data:"
head -5 "$RAW_JSONL"

# Extract audio codes using qwen-tts
echo "Extracting audio codes..."
python3 -c "
from qwen_tts import Qwen3TTSTokenizer
import json
import torch

tokenizer = Qwen3TTSTokenizer.from_pretrained(
    'Qwen/Qwen3-TTS-Tokenizer-12Hz',
    device_map='cuda:0',
)

with open('$RAW_JSONL', 'r') as f_in, open('$OUTPUT_JSONL', 'w') as f_out:
    for line in f_in:
        data = json.loads(line.strip())
        # Encode audio to codes
        codes = tokenizer.encode(data['audio'])
        data['audio_codes'] = codes['audio_codes'].tolist() if hasattr(codes['audio_codes'], 'tolist') else codes['audio_codes']
        f_out.write(json.dumps(data) + '\n')
        print(f\"Processed: {data['audio']}\")

print('Audio code extraction complete')
"

echo "Training data prepared: $OUTPUT_JSONL"
