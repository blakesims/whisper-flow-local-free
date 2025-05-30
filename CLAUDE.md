# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a macOS desktop application for audio recording and transcription using OpenAI's Whisper AI model locally. The app provides a floating UI window triggered via Raycast, featuring real-time audio visualization, keyboard shortcuts, and optional AI-powered text processing through Fabric patterns.

## Common Development Commands

### Running the Application
```bash
# Main way to run the app (activates venv automatically)
./run_whisper_ui.sh

# Alternative: manual venv activation and run
source .venv/bin/activate
python -m app.main
```

### Package Management
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Building macOS App Bundle
```bash
# Build the .app bundle using py2app
python setup.py py2app
```

## Architecture Overview

### Core Services (`app/core/`)
- **audio_recorder.py**: Thread-based audio recording with real-time chunk streaming for waveform visualization
- **transcription_service.py**: Whisper AI integration using faster-whisper library, handles model loading and transcription
- **fabric_service.py**: Integration with Fabric CLI for AI pattern processing (currently experiencing external API issues)

### UI Components (`app/ui/`)
- **main_window.py**: Frameless, always-on-top floating window with Tokyo Night theme
- **waveform_widget.py**: Real-time audio visualization widget
- **pattern_selection_dialog.py**: Fuzzy search dialog for Fabric pattern selection
- **workers.py**: QThread workers for async operations (transcription, model loading, fabric processing)

### Key Design Patterns
- **Async Operations**: All heavy operations (transcription, model loading) run in separate QThreads to maintain UI responsiveness
- **Signal/Slot Communication**: PySide6 signals used for thread-safe UI updates
- **Temporary File Management**: Audio recordings stored as temp files, cleaned up after processing
- **Keyboard-Driven UX**: Primary actions mapped to single-key shortcuts (R, S, P, T, F, Q)

### Model Loading Strategy
The app uses lazy loading for Whisper models. Models are downloaded and cached on first use in `~/.cache/whisper/`. Available models: tiny, base, small, medium, large-v2.

### Clipboard Integration
After transcription or Fabric processing, text is automatically copied to clipboard and can be auto-pasted to the previously active application using simulated CMD+V.

## Important Notes

- The app requires microphone permissions on macOS
- Fabric integration depends on having the Fabric CLI installed and configured
- The UI uses a frameless window design that stays on top of other windows
- Audio recording runs in a separate thread to prevent UI blocking
- Transcription progress is reported via Qt signals for smooth UI updates