# Task: Speaker Diarization Integration

## Task ID
T010

## Overview
Add speaker diarization (identifying "who spoke when") to the transcription pipeline. After research, we'll use **pyannote-audio directly** with the existing whisper.cpp backend, rather than WhisperX, to avoid dependency conflicts and keep the fast transcription.

**Approach**: whisper.cpp transcription → pyannote diarization → merge timestamps

## Objectives
- Add speaker diarization as post-processing step after whisper.cpp transcription
- Use pyannote-audio 4.0 with the "community-1" model (free, fast)
- Add `--diarize` flag to `transcribe_file.py`
- Output format: `[SPEAKER_00] text` with timestamps
- Cache diarized transcripts separately from non-diarized

## Dependencies
- None (uses existing whisper.cpp setup)

## Rules Required
- task-documentation

## Resources & References
- [pyannote-audio GitHub](https://github.com/pyannote/pyannote-audio)
- [pyannote community-1 model](https://huggingface.co/pyannote/speaker-diarization-community-1) (CC-BY-4.0, free)
- [pyannote 4.0 release notes](https://www.pyannote.ai/blog/community-1)
- [pyannote-whisper reference](https://github.com/extrange/pyannote-whisper)
- Existing: `app/core/transcription_service_cpp.py`, `transcribe_file.py`

## Prerequisites (User Action Required)
1. Create free HuggingFace account
2. Accept user agreement for [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Generate HuggingFace access token (read permission)
4. Store token: `export HF_TOKEN="hf_xxxxx"` or in config

## Technical Approach

### Architecture
```
Audio File
    ↓
whisper.cpp (existing) → segments with timestamps
    ↓
pyannote-audio → speaker segments (who spoke when)
    ↓
Merge/Align → segments with speaker labels
    ↓
Output: "[SPEAKER_00] Hello..." with timestamps
```

### Output Format
```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 2.48,
      "text": "Hello, how are you?",
      "speaker": "SPEAKER_00"
    },
    {
      "start": 2.80,
      "end": 4.92,
      "text": "I'm doing great!",
      "speaker": "SPEAKER_01"
    }
  ]
}
```

## Phases Breakdown

### Phase 1: pyannote Integration
**Status**: Not Started

**Objectives**:
- Install pyannote-audio (check compatibility with existing deps)
- Test basic diarization on sample audio
- Verify HuggingFace token flow
- Measure performance overhead

**Estimated Time**: 1 day

**Code to test**:
```python
from pyannote.audio import Pipeline

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token="YOUR_HF_TOKEN"
)
diarization = pipeline("audio.wav")

for turn, _, speaker in diarization.itertracks(yield_label=True):
    print(f"{turn.start:.1f}s - {turn.end:.1f}s: {speaker}")
```

**Dependencies**: None

### Phase 2: Timestamp Alignment
**Status**: Not Started

**Objectives**:
- Create alignment function to merge whisper.cpp segments with pyannote speakers
- Handle edge cases (overlapping speech, silence gaps)
- Test with various audio types

**Estimated Time**: 1 day

**Algorithm**:
```python
def assign_speakers(whisper_segments, diarization):
    for segment in whisper_segments:
        # Find speaker with most overlap in this time range
        seg_start, seg_end = segment["start"], segment["end"]
        best_speaker = None
        best_overlap = 0

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            overlap = min(turn.end, seg_end) - max(turn.start, seg_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker

        segment["speaker"] = best_speaker or "UNKNOWN"
    return whisper_segments
```

**Dependencies**: Phase 1

### Phase 3: CLI Integration
**Status**: Not Started

**Objectives**:
- Add `--diarize` flag to `transcribe_file.py`
- Separate cache keys for diarized vs non-diarized
- Format output with speaker labels
- Handle missing HF token gracefully

**Estimated Time**: 1 day

**Usage**:
```bash
python transcribe_file.py audio.mp3                    # No diarization
python transcribe_file.py --diarize audio.mp3          # With diarization
python transcribe_file.py --diarize --force audio.mp3  # Bypass cache
```

**Dependencies**: Phase 2

### Phase 4: Testing & Polish
**Status**: Not Started

**Objectives**:
- Test with 1, 2, 3, 6+ speakers
- Test with overlapping speech
- Test with single-speaker (should still work)
- Update README and CLAUDE.md
- Add to Raycast script

**Estimated Time**: 1 day

**Dependencies**: Phase 3

## Notes & Updates
- 2025-01-16: Task created
- 2025-01-16: Research completed - switched from WhisperX to pyannote-audio direct integration
  - WhisperX has torch 2.8.0 dependency that conflicts with existing setup
  - pyannote-audio works as post-processing, keeps fast whisper.cpp
  - pyannote 4.0 "community-1" model is free (CC-BY-4.0) and 40% faster

## Why pyannote-audio instead of WhisperX?
| Factor | WhisperX | pyannote-audio |
|--------|----------|----------------|
| Dependency conflicts | Yes (torch 2.8.0) | Minimal |
| Separate venv needed | Yes | No |
| Transcription backend | Replaces whisper.cpp | Keeps whisper.cpp |
| Complexity | High (3-step pipeline) | Low (post-processing) |
| Speed | Fast transcription, slower overall | Adds ~30% overhead |
