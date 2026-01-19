# Task: WhisperX Speaker Diarization Integration

## Task ID
T010

## Overview
Add speaker diarization (identifying "who spoke when") to the transcription pipeline using WhisperX. This will enable multi-speaker transcripts with speaker labels, particularly useful for meetings, interviews, and podcasts.

WhisperX combines Whisper transcription with pyannote-audio for speaker diarization, running fully locally after initial model download.

## Objectives
- Integrate WhisperX as an alternative transcription backend with diarization
- Add speaker labels to transcripts (Speaker 1, Speaker 2, etc.)
- Support diarization in the Raycast file transcription script
- Cache diarized transcripts (24h cache already exists)
- Optionally add diarization toggle to daemon menu

## Dependencies
- None (fresh start after project refocus)

## Rules Required
- task-documentation

## Resources & References
- [WhisperX GitHub](https://github.com/m-bain/whisperX)
- [pyannote-audio](https://github.com/pyannote/pyannote-audio)
- HuggingFace models required:
  - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
  - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- Existing transcription: `app/core/transcription_service_cpp.py`
- File transcription script: `transcribe_file.py`

## Prerequisites (User Action Required)
1. Create free HuggingFace account
2. Accept user agreement for pyannote models (links above)
3. Generate HuggingFace access token (read permission)
4. Store token in config or environment variable

## Phases Breakdown

### Phase 1: Research & Setup
**Status**: Not Started

**Objectives**:
- Install WhisperX and dependencies
- Test basic WhisperX transcription with diarization
- Verify HuggingFace token flow
- Benchmark performance vs current whisper.cpp

**Estimated Time**: 1 day

**Resources Needed**:
- WhisperX installation docs
- Test audio files with multiple speakers
- HuggingFace token

**Dependencies**:
- None

### Phase 2: Create WhisperX Service
**Status**: Not Started

**Objectives**:
- Create `app/core/transcription_service_whisperx.py`
- Implement compatible API with existing services
- Add speaker label formatting to output
- Handle HF token configuration

**Estimated Time**: 2 days

**Resources Needed**:
- WhisperX API documentation
- Existing service patterns from `transcription_service_cpp.py`

**Dependencies**:
- Phase 1 completion

### Phase 3: Integrate with File Transcription
**Status**: Not Started

**Objectives**:
- Add `--diarize` flag to `transcribe_file.py`
- Update cache to store diarized vs non-diarized separately
- Format output with speaker labels
- Update Raycast script if needed

**Estimated Time**: 1 day

**Resources Needed**:
- Existing `transcribe_file.py`
- Test multi-speaker audio files

**Dependencies**:
- Phase 2 completion

### Phase 4: Optional Daemon Integration
**Status**: Not Started

**Objectives**:
- Add diarization toggle to daemon right-click menu
- Implement diarization mode for recordings
- Consider UX for speaker-labeled output

**Estimated Time**: 1 day

**Resources Needed**:
- `recording_indicator.py` menu system
- `whisper_daemon.py` integration points

**Dependencies**:
- Phase 3 completion

### Phase 5: Testing & Documentation
**Status**: Not Started

**Objectives**:
- Test with various multi-speaker recordings
- Test with single-speaker (should still work)
- Update CLAUDE.md with diarization docs
- Document HF token setup process

**Estimated Time**: 1 day

**Resources Needed**:
- Diverse test audio (2-6 speakers)
- Performance benchmarks

**Dependencies**:
- Phase 4 completion

## Notes & Updates
- 2025-01-16: Task created for WhisperX diarization integration
- WhisperX chosen over alternatives because:
  - Fully local after model download
  - Free and open source
  - Well-maintained, popular project
  - Simpler than NeMo-based alternatives
  - Only requires free HuggingFace account for pyannote models
