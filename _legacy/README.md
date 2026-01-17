# Legacy Full UI Mode (Deprecated)

This directory contains the deprecated Full UI mode of the Whisper Transcription application.

## Status

**Deprecated** - These files are kept for reference but are not actively developed.

## What's Here

- `ui/` - PySide6/Qt-based GUI components (main window, dialogs, workers)
- `run_whisper_ui.sh` - Shell script to launch the Full UI application
- `main.py` - Entry point for the Full UI application

## Technical Details

The Full UI mode uses:
- **faster-whisper** for transcription (Python bindings to whisper.cpp with ctranslate2)
- **PySide6** for the graphical user interface
- Thread-based audio recording with real-time waveform visualization

## Active Development

The daemon mode in `app/daemon/` is now the primary and actively maintained interface:
- Uses **whisper.cpp** directly via subprocess
- Provides a lightweight socket-based API
- Designed for integration with Raycast and other tools
- Better resource management and faster startup

## Migration

If you were using the Full UI mode, consider switching to the daemon mode:
1. Install the daemon: `./install-daemon.sh`
2. Use Raycast scripts or the toggle script to control recording
3. See `docs/` for daemon documentation
