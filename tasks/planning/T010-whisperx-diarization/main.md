# Task: WhisperX Speaker Diarization Module

## Task ID
T010

## Overview
Add speaker diarization using **WhisperX** as a standalone module with its own virtual environment. This provides an all-in-one solution for transcription with speaker labels, isolated from the main project's dependencies.

**Approach**: Separate venv with WhisperX, called via subprocess from main project.

## Objectives
- Set up WhisperX in isolated `~/whisperx-diarize/` directory
- Create simple Python wrapper script for diarized transcription
- Add `--diarize` flag to `transcribe_file.py` that calls WhisperX
- Output format: `[SPEAKER_00] text` with timestamps
- Cache diarized transcripts in same cache with `_diarized` suffix
- macOS notification on completion (success or failure)
- Update existing Raycast script to support `--diarize` flag

## Dependencies
- None (isolated venv)

## Rules Required
- task-documentation

## Resources & References
- [WhisperX GitHub](https://github.com/m-bain/whisperX) (v3.7.4, 19k+ stars)
- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)

## Prerequisites (User Action Required)
1. Create free [HuggingFace account](https://huggingface.co/join)
2. Accept model licenses (click "Agree" while logged in):
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-3.1
3. Create access token: https://huggingface.co/settings/tokens (Read access)
4. Add to shell: `export HF_TOKEN="hf_xxxxx"`

## Technical Details

### Architecture
```
Main Project (whisper-transcribe-ui)
    │
    ├── transcribe_file.py --diarize audio.mp3
    │       │
    │       ▼ (subprocess call)
    │
    └── ~/whisperx-diarize/.venv/bin/python
            │
            ▼
        WhisperX Pipeline:
        [1] faster-whisper → transcription
        [2] wav2vec2 → word alignment
        [3] pyannote → speaker diarization
        [4] merge → "[SPEAKER_00] Hello..."
```

### Disk Space Requirements
| Component | Size |
|-----------|------|
| WhisperX + PyTorch CPU | ~1 GB |
| Whisper large-v2 model | ~3 GB |
| pyannote models | ~500 MB |
| wav2vec2 alignment | ~1-2 GB |
| **Total** | **~5-7 GB** |

### macOS/Apple Silicon Requirements
```bash
whisperx audio.mp3 \
    --device cpu \           # Required for macOS
    --compute_type float32   # Required for Apple Silicon
```

## Phases Breakdown

### Phase 1: WhisperX Setup
**Status**: Not Started

**Objectives**:
- Create `~/whisperx-diarize/` with isolated venv
- Install WhisperX and verify installation
- Test CLI with sample audio
- Verify HuggingFace token works

**Deliverables**:
- `~/whisperx-diarize/.venv/` - isolated environment
- `~/whisperx-diarize/setup.sh` - reproducible setup script

**Setup Script**:
```bash
#!/bin/bash
# ~/whisperx-diarize/setup.sh
set -e
cd "$(dirname "$0")"

python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install whisperx

echo "Test with: whisperx audio.mp3 --device cpu --compute_type float32 --diarize --hf_token \$HF_TOKEN"
```

**Test Command**:
```bash
source ~/whisperx-diarize/.venv/bin/activate
whisperx test.mp3 --model base --device cpu --compute_type float32 --diarize --hf_token $HF_TOKEN --output_format txt
```

**Estimated Time**: 1 day

### Phase 2: Python Wrapper Script
**Status**: Not Started

**Objectives**:
- Create `~/whisperx-diarize/transcribe.py` wrapper
- Handle errors gracefully
- Format output nicely
- Support JSON and text output

**Deliverable**: `~/whisperx-diarize/transcribe.py`

```python
#!/usr/bin/env python3
"""WhisperX transcription with speaker diarization."""

import argparse
import json
import os
import sys
import gc
import whisperx


def transcribe(audio_file: str, hf_token: str, model: str = "large-v2") -> dict:
    """Transcribe with diarization, return segments."""
    device = "cpu"
    compute_type = "float32"

    # Load and transcribe
    audio = whisperx.load_audio(audio_file)
    model_obj = whisperx.load_model(model, device, compute_type=compute_type)
    result = model_obj.transcribe(audio, batch_size=4)
    language = result["language"]

    del model_obj
    gc.collect()

    # Align
    model_a, metadata = whisperx.load_align_model(language_code=language, device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device)

    del model_a
    gc.collect()

    # Diarize
    diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
    diarize_segments = diarize_model(audio)
    result = whisperx.assign_word_speakers(diarize_segments, result)

    return result


def format_text(segments: list) -> str:
    """Format segments as readable transcript."""
    lines = []
    current_speaker = None
    current_text = []

    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "").strip()

        if speaker != current_speaker:
            if current_text:
                lines.append(f"[{current_speaker}] {' '.join(current_text)}")
            current_speaker = speaker
            current_text = [text] if text else []
        elif text:
            current_text.append(text)

    if current_text:
        lines.append(f"[{current_speaker}] {' '.join(current_text)}")

    return "\n\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_file")
    parser.add_argument("--hf_token", default=os.environ.get("HF_TOKEN"))
    parser.add_argument("--model", default="large-v2")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output", "-o")
    args = parser.parse_args()

    if not args.hf_token:
        print("Error: Set HF_TOKEN env var or use --hf_token", file=sys.stderr)
        sys.exit(1)

    result = transcribe(args.audio_file, args.hf_token, args.model)

    if args.format == "json":
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = format_text(result["segments"])

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
```

**Estimated Time**: 1 day

### Phase 3: Main Project Integration
**Status**: Not Started

**Objectives**:
- Add `--diarize` flag to `transcribe_file.py`
- Call WhisperX via subprocess (background process)
- Same cache directory, use `{hash}_diarized.json` suffix
- macOS notification on completion (success/failure)
- Update existing Raycast script with `--diarize` option

**Cache Strategy**:
- Regular: `~/.cache/whisper-transcripts/{hash}.json`
- Diarized: `~/.cache/whisper-transcripts/{hash}_diarized.json`
- Same 24h expiry for both

**macOS Notification** (using osascript):
```python
def send_notification(title: str, message: str):
    """Send macOS notification."""
    subprocess.run([
        'osascript', '-e',
        f'display notification "{message}" with title "{title}"'
    ])
```

**Integration Code** (add to `transcribe_file.py`):
```python
import subprocess

WHISPERX_VENV = os.path.expanduser("~/whisperx-diarize/.venv/bin/python")
WHISPERX_SCRIPT = os.path.expanduser("~/whisperx-diarize/transcribe.py")

def get_cache_path(cache_key: str, diarized: bool = False) -> Path:
    """Get the cache file path for a given key."""
    suffix = "_diarized" if diarized else ""
    return CACHE_DIR / f"{cache_key}{suffix}.json"

def send_notification(title: str, message: str):
    """Send macOS notification."""
    subprocess.run([
        'osascript', '-e',
        f'display notification "{message}" with title "{title}"'
    ], capture_output=True)

def transcribe_with_diarization(file_path: str) -> str:
    """Call WhisperX in separate venv."""
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise ValueError("HF_TOKEN environment variable required for diarization")

    result = subprocess.run(
        [WHISPERX_VENV, WHISPERX_SCRIPT, file_path, "--hf_token", hf_token, "--format", "text"],
        capture_output=True,
        text=True,
        timeout=7200  # 2 hours for long files
    )

    if result.returncode != 0:
        raise RuntimeError(f"WhisperX failed: {result.stderr}")

    return result.stdout
```

**Raycast Script Update** (`~/raycast-scripts/whisper-file-transcribe.sh`):
```bash
# Add argument handling for --diarize
# @raycast.argument1 { "type": "text", "placeholder": "file path" }
# @raycast.argument2 { "type": "text", "placeholder": "--diarize (optional)", "optional": true }

DIARIZE_FLAG=""
if [[ "$2" == "--diarize" ]] || [[ "$2" == "-d" ]]; then
    DIARIZE_FLAG="--diarize"
fi

python "$PROJECT_DIR/transcribe_file.py" $DIARIZE_FLAG "$FILE_PATH"
```

**Usage**:
```bash
python transcribe_file.py audio.mp3                   # Regular (whisper.cpp)
python transcribe_file.py --diarize audio.mp3         # With speakers (WhisperX)
```

**Estimated Time**: 1 day

### Phase 4: Testing & Documentation
**Status**: Not Started

**Objectives**:
- Test with 1, 2, 3, 6+ speakers
- Test with long files (1+ hours)
- Update README.md
- Update CLAUDE.md

**Estimated Time**: 1 day

## Output Format Example

```
[SPEAKER_00] Hello, thanks for joining us today. I wanted to discuss the quarterly results.

[SPEAKER_01] Sure, I've reviewed the numbers. Revenue is up 15% compared to last quarter.

[SPEAKER_00] That's great news. What about the customer acquisition cost?

[SPEAKER_01] We managed to reduce it by about 8% through the new marketing channels.

[SPEAKER_02] If I may add, the engineering team also reduced infrastructure costs by 12%.
```

## Notes & Updates
- 2025-01-16: Task created
- 2025-01-16: Revised to use pyannote-audio directly
- 2025-01-16: Revised again to use WhisperX (user preference for simplicity)
  - Separate venv avoids dependency conflicts
  - All-in-one solution (transcription + alignment + diarization)
  - Word-level speaker labels
  - ~5-7GB disk space for models
- 2025-01-19: Clarified implementation details
  - Cache: Same directory with `_diarized` suffix (not separate cache)
  - Raycast: Add `--diarize` flag to existing script (not new script)
  - Notification: macOS notification on completion via osascript

## Why WhisperX?
| Factor | Decision |
|--------|----------|
| Simplicity | All-in-one vs glue code |
| Quality | Word-level speaker labels |
| Isolation | Separate venv = no conflicts |
| Maintenance | Well-maintained (19k+ stars) |
| Speed | Not critical for one-off archival use |
