# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a macOS desktop application for audio recording and transcription using Whisper AI locally. The app has **two distinct modes**:

### Daemon Mode (Primary - Recommended)
A lightweight background service with a minimal floating indicator. Uses **whisper.cpp** for faster transcription.
- **Entry point**: `./scripts/whisper-daemon.sh start`
- **UI**: Small floating pill/dot that expands during recording
- **Hotkeys**: `Ctrl+F` (toggle recording), `Escape` (cancel)
- **Features**: Always-on, instant recording, right-click menu for settings
- **Location**: `app/daemon/` (whisper_daemon.py, recording_indicator.py, hotkey_listener.py)

### Full UI Mode (Legacy)
A larger floating window with more controls. Uses **faster-whisper** library.
- **Entry point**: `./run_whisper_ui.sh`
- **UI**: Full window with buttons, waveform, text display
- **Hotkeys**: Single-letter shortcuts (R, S, P, T, F, U, Q)
- **Features**: Meeting transcription, Fabric patterns, file upload dialog
- **Location**: `app/ui/` (main_window.py, waveform_widget.py)

**Note**: The daemon mode is the actively used and developed mode. The full UI mode is maintained but secondary.

### Knowledge Base Workflow (`kb/`)
Standalone scripts for archiving video content to a structured JSON knowledge base with LLM analysis.
- **Location**: `kb/` directory
- **Output**: `~/Obsidian/zen-ai/knowledge-base/transcripts/`
- **Entry points**:
  - `python kb/transcribe.py` - Core transcription to JSON
  - `python kb/analyze.py` - LLM analysis (Gemini API)
  - `python kb/capture.py` - Cap recordings batch capture
  - `python kb/volume_sync.py` - Auto-transcribe from mounted volumes

## Key Rules

- **Gemini API**: Use `google-genai` package (NOT `google-generativeai`, deprecated Nov 2025)
- **Network volumes**: Extract audio via ffmpeg, never copy whole video files
- **Transcription quality**: Default to "medium" Whisper model for quality
- **Venv**: `source .venv/bin/activate && pip install -r requirements.txt`

## Common Development Commands

### Running the Application
```bash
# DAEMON MODE (recommended) - lightweight floating indicator
./scripts/whisper-daemon.sh start    # Start daemon in background
./scripts/whisper-daemon.sh stop     # Stop daemon
./scripts/whisper-daemon.sh status   # Check status
./scripts/whisper-daemon.sh logs     # View logs

# FULL UI MODE - larger window with all features
./run_whisper_ui.sh

# Alternative: manual venv activation
source .venv/bin/activate
python -m app.daemon.whisper_daemon start  # Daemon mode
python -m app.main                          # Full UI mode
```

### Raycast File Transcription
```bash
python transcribe_file.py /path/to/audio.mp3          # With 24h cache
python transcribe_file.py --force /path/to/audio.mp3  # Bypass cache
```

### Build macOS App
```bash
./scripts/build_app.sh  # Output: dist/Whisper Transcription UI.app
```

## Architecture Overview

### Daemon Components (`app/daemon/`) - Primary
- **whisper_daemon.py**: Background service orchestrating recording, transcription, and clipboard
- **recording_indicator.py**: Minimal floating UI (pill/dot) with right-click menu
- **hotkey_listener.py**: Global hotkey detection via pynput (Ctrl+F, Escape)

### Core Services (`app/core/`)
- **audio_recorder.py**: Thread-based audio recording with real-time chunk streaming for waveform visualization
- **transcription_service_cpp.py**: Whisper.cpp integration via pywhispercpp (used by daemon, faster)
- **transcription_service.py**: faster-whisper integration (used by full UI)
- **post_processor.py**: LLM-based transcription cleanup (optional)
- **fabric_service.py**: Integration with Fabric CLI for AI pattern processing

### Full UI Components (`app/ui/`) - Secondary
- **main_window.py**: Frameless, always-on-top floating window with Tokyo Night theme
- **waveform_widget.py**: Real-time audio visualization widget
- **pattern_selection_dialog.py**: Fuzzy search dialog for Fabric pattern selection
- **workers.py**: QThread workers for async operations (transcription, model loading, fabric processing)

### Key Design Patterns
- **Async Operations**: All heavy operations (transcription, model loading) run in separate QThreads to maintain UI responsiveness
- **Signal/Slot Communication**: PySide6 signals used for thread-safe UI updates
- **Temporary File Management**: Audio recordings stored as temp files, cleaned up after processing
- **Keyboard-Driven UX**: Primary actions mapped to single-key shortcuts (R, S, P, T, F, U, Q)
- **File Upload Support**: Users can upload audio files directly for transcription without recording

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
- Supported audio formats for upload: WAV, MP3, M4A, FLAC, OGG, OPUS, WEBM
- Package optimizations include: disabling argv emulation, bytecode optimization, compression, and excluding unused packages

## Performance Optimization

The app now automatically optimizes CPU usage for transcription:
- Auto-detects CPU core count and uses optimal number of threads
- **Apple Silicon (M1/M2/M3) specific optimizations**:
  - Uses all cores minus 1 (Apple Silicon handles multi-threading efficiently)
  - Voice Activity Detection (VAD) enabled for faster processing
  - Beam size reduced to 1 (minimal quality impact, significant speed boost)
  - Temperature set to 0 for deterministic, faster results
  - Note: MPS (GPU) not supported by faster-whisper, CPU-only but still 4x faster than OpenAI Whisper
- Intel/AMD: Uses physical core count (logical cores / 2) minus 2 for system
- Can be manually configured via `transcription_cpu_threads` in config
- Default behavior significantly improves transcription speed and CPU utilization