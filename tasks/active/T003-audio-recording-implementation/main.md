# Task: Audio Recording Implementation

## Task ID
T003

## Overview
Implement the audio recording functionality for the Whisper Transcription App, including audio capture, temporary storage, and the ability to pause, resume, and cancel recordings. This task focuses on the core audio recording feature that will feed into the transcription process.
**This service will be located at `app/core/audio_recorder.py` as per `project-architecture.mdc`.**

## Objectives
- Implement audio capture using the sounddevice library
- Create a robust recording system with pause/resume functionality
- Develop temporary storage for audio data with proper cleanup
- Ensure accurate audio amplitude calculation for waveform visualization
- Build an audio recording service that integrates with the UI

## Dependencies
- T001
- T002

## Rules Required
- task-documentation
- code-conventions
- integration-points
- project-architecture

## Resources & References
- Project specification: `tasks/init-Project-Spec.md`
- sounddevice documentation: https://python-sounddevice.readthedocs.io/
- NumPy documentation: https://numpy.org/doc/
- Audio processing best practices

## Phases Breakdown

### Phase 1: Audio Capture Implementation & Core Service Setup
**Status**: ACTIVE

**Objectives**:
- **Setup `AudioRecorder` Service:**
    - Create `app/core/audio_recorder.py`.
    - Implement the `AudioRecorder` class.
- **Threading:**
    - The `AudioRecorder` service **must** operate in a separate worker thread (`QThread`) to prevent UI freezes, as per `code-conventions.mdc`.
- **Audio Input (sounddevice):**
    - Set up `sounddevice` for audio input capture (e.g., default microphone).
    - Implement robust audio stream management (opening, closing, error checking).
- **Data Format & Interface:**
    - Capture audio as raw PCM data.
    - Provide raw audio data chunks compatible with `WaveformWidget.update_waveform_data(raw_audio_chunk: np.ndarray)`. The `raw_audio_chunk` should be a 1D NumPy array of floating-point PCM samples (e.g., values between -1.0 and 1.0).
- **Communication (Signals & Slots):**
    - Implement Qt signals for communication from `AudioRecorder` to `MainWindow` (or other UI components), as per `code-conventions.mdc`. This includes:
        - Emitting new audio data chunks.
        - Signaling changes in operational status (e.g., `recording_started_signal`, `recording_stopped_signal`, `recording_failed_to_start_signal`, `error_occurred_signal`).
- **State Management Integration (Foundation):**
    - The `AudioRecorder` will be the *actual driver* of recording-related states.
    - Implement methods like `start_recording()`, `stop_recording()` etc., which will then emit signals to `MainWindow` to confirm the *actual* outcome.
    - `MainWindow` will have slots connected to these signals to update its internal `_app_state` and UI.
- **Error Handling (Initial):**
    - Implement basic detection of potential errors (e.g., no microphone available, microphone access denied).
    - Emit specific error signals (e.g., `error_signal(error_message: str)`) that `MainWindow` can connect to.
- **Configuration (Consideration):**
    - Identify parameters for `AudioRecorder` (e.g., preferred input device, sample rate (default 16000Hz), audio chunk size) that might need to be managed via `ConfigManager` (as per `integration-points.mdc`). Implement with defaults for now, with an eye towards future configurability.
- **Basic Testing:**
    - Test basic recording functionality and signal emission.

**Estimated Time**: 3 days (adjusted for increased detail)

**Resources Needed**:
- sounddevice documentation
- Audio testing equipment (microphone)

**Dependencies**:
- T001#P4 completion
- T002#P1 completion

### Phase 2: Recording Controls Development
**Status**: Not Started

**Objectives**:
- Implement start/stop recording functionality
- Develop pause/resume capabilities
- Create recording cancellation with cleanup
- Build audio buffer management system
- Ensure thread safety for all recording operations

**Estimated Time**: 2 days

**Resources Needed**:
- Thread synchronization reference
- Audio buffer management examples

**Dependencies**:
- Phase 1 completion

### Phase 3: Temporary Storage Implementation
**Status**: Not Started

**Objectives**:
- Develop system for temporary audio storage
- Implement proper file format management (WAV, temp files)
- Create cleanup routines for successful/failed recordings
- Ensure proper memory management for longer recordings
- Build audio metadata tracking (duration, sample rate, etc.)

**Estimated Time**: 2 days

**Resources Needed**:
- File I/O documentation
- Temporary file management best practices

**Dependencies**:
- Phase 2 completion

### Phase 4: Integration and Testing
**Status**: Not Started

**Objectives**:
- Integrate audio recording with UI components
- Connect amplitude data to waveform visualization
- Implement state management for recording status
- Test with various recording durations and conditions
- Verify pause/resume/cancel functionality

**Estimated Time**: 1 day

**Resources Needed**:
- Test audio samples
- Integration test plan

**Dependencies**:
- Phase 3 completion
- T002#P3 completion

## Notes & Updates 