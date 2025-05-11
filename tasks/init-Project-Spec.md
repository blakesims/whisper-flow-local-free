# Whisper Transcription App Specification (Final)

## Overview

A lightweight macOS desktop application that provides a simple interface for audio recording, transcription using faster-whisper, and post-processing with fabric. The app will be triggered via Raycast and provide visual feedback during recording.

## Core Features

### Recording Interface

- **Small, floating window** that stays on top of other applications
- **Live waveform visualization** showing audio input levels
- **Keyboard shortcuts** to control recording and processing
- **Status indicators** showing current state (recording, transcribing, processing)
- **Pause/Resume** functionality for recording
- **Delete and restart** option during recording

### Transcription Engine

- Uses the existing faster-whisper implementation
- Supports different model sizes (base, small, medium, large-v2, large-v3)
- Language detection and optional translation
- **Progress indicator** during transcription (based on segments processed)

### Post-Processing with Fabric

- Fuzzy search interface to select from available fabric patterns (retrieved via `fabric -l`)
- Direct integration with fabric CLI
- Two primary workflows:
  1. Stop recording → transcribe → paste to active application
  2. Stop recording → transcribe → select fabric pattern → process → paste result

### Error Handling

- Basic error handling with clear error messages
- If transcription fails, offer option to save the audio file for later retry
- Temporary storage of recordings in memory/app folder until successful transcription

## Technical Specifications

### Application Framework

- **PySide6** for the UI (Qt for Python)
- Packaged as a standalone macOS app using **py2app**

### Audio Recording

- **sounddevice** for audio capture
- Real-time amplitude calculation for waveform visualization
- Temporary storage of recordings with cleanup after successful processing

### UI Components

1. **Main Window**

   - Small, frameless window with minimal controls
   - Always-on-top behavior
   - Draggable to reposition
   - Tokyo Night or pastel color palette

2. **Waveform Display**

   - Simple, responsive visualization of audio input
   - Color changes to indicate recording status (recording/paused)

3. **Control Buttons**

   - Minimal buttons for stop/pause/cancel
   - Keyboard shortcut hints

4. **Pattern Selector**

   - Fuzzy search interface for fabric patterns
   - Appears only when needed (after choosing to process with fabric)

5. **Settings Dialog**
   - Accessible via Cmd+, (standard macOS shortcut)
   - Configure model size, language preferences, keyboard shortcuts

### Configuration

- Store settings in a JSON file in the application's data directory
- Default settings for model size, language, etc.
- Configurable keyboard shortcuts

### Integration Points

- **Raycast Integration**: Launch app via keyboard shortcut
- **Clipboard Integration**: Paste transcribed text
- **Fabric CLI Integration**: Execute fabric commands with selected patterns

## Implementation Details

### Progress Reporting

- Implement a progress callback for faster-whisper transcription
- Since faster-whisper doesn't have a built-in progress API, we'll track progress by:
  - Monitoring the segments as they're generated
  - Estimating progress based on audio duration and processed segments
  - Displaying a progress bar in the UI

### Error Handling

- Try/except blocks around critical operations
- Clear error messages displayed in the UI
- Option to save audio if transcription fails
- Logging of errors to a log file for debugging

### Performance Optimization

- Ensure the UI remains responsive during transcription by:
  - Running transcription in a separate thread
  - Using Qt signals to update the UI from the worker thread
  - Optimizing memory usage for longer recordings (up to 30+ minutes)

### Data Flow

1. **Recording**:

   - Audio data stored in memory buffer
   - Waveform visualization updated in real-time
   - On completion, audio saved to temporary file

2. **Transcription**:

   - Load faster-whisper model (cached if possible)
   - Process audio with progress updates
   - Display transcribed text

3. **Post-Processing**:
   - If direct paste: Copy to clipboard and simulate paste
   - If fabric processing: Show pattern selector, process with fabric, then paste

## Development Plan

1. **Setup Project Structure**:

   - Create a PySide6 application skeleton
   - Integrate existing faster-whisper code

2. **Build Basic UI**:

   - Implement the waveform visualization
   - Add recording controls and status indicators

3. **Integrate Transcription**:

   - Connect UI to the faster-whisper transcription engine
   - Implement progress tracking and display

4. **Add Fabric Integration**:

   - Implement pattern selection interface
   - Connect to fabric CLI

5. **Implement Settings and Configuration**:

   - Create settings dialog
   - Add configuration persistence

6. **Package as macOS App**:

   - Create standalone application
   - Test Raycast integration

7. **Testing and Refinement**:
   - Test with various audio lengths and conditions
   - Optimize performance and memory usage

## Technical Stack

- **UI Framework**: PySide6 (Qt for Python)
- **Audio Processing**: sounddevice + numpy
- **Transcription**: faster-whisper
- **Packaging**: py2app
- **Pattern Selection**: Python-based fuzzy finder (like fuzzywuzzy or rapidfuzz)

## Additional Notes

- The app is designed for personal use only, focusing on simplicity and efficiency
- No need for user management or multi-user features
- Emphasis on keyboard shortcuts for efficient workflow
- Minimal, clean UI with focus on functionality
- Temporary storage of recordings with proper cleanup to maintain privacy

This specification provides a comprehensive guide for developing a dedicated transcription tool that integrates with your existing workflow while providing the visual feedback and control you're looking for.
