# Whisper Transcription UI

A lightweight macOS background service for instant audio transcription using whisper.cpp. Features a minimal floating indicator, global hotkeys, and automatic clipboard integration.

## Features

- 🎙️ **Instant Recording**: Press `Ctrl+F` anywhere to start/stop recording
- 🤖 **Local AI Transcription**: Uses whisper.cpp for fast, private transcription (no internet required)
- 📋 **Auto Clipboard**: Transcriptions automatically copied and pasted to active app
- 🎯 **Minimal UI**: Unobtrusive floating indicator that stays out of your way
- 📁 **File Transcription**: Transcribe existing audio/video files via Raycast or CLI
- 🚀 **Apple Silicon Optimized**: Metal GPU acceleration on M1/M2/M3

## Requirements

- macOS 11.0 or later
- Python 3.9 or later
- Microphone permissions
- Accessibility permissions (for global hotkeys)
- ~500MB-3GB disk space for Whisper models

## Installation

### 1. Clone and setup
```bash
git clone https://github.com/yourusername/whisper-transcribe-ui.git
cd whisper-transcribe-ui
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Grant permissions
The app needs two macOS permissions:
- **Microphone**: Granted on first recording attempt
- **Accessibility**: System Settings → Privacy & Security → Accessibility → Add Terminal/Python

### 3. Start the daemon
```bash
./scripts/whisper-daemon.sh start
```

## Usage

### Global Hotkeys
| Hotkey | Action |
|--------|--------|
| `Ctrl+F` | Toggle recording |
| `Escape` | Cancel recording (saves audio file) |
| `Ctrl+Option+F` | Transcribe file path from clipboard |

### Recording Workflow
1. Press `Ctrl+F` to start recording (indicator turns into waveform)
2. Press `Ctrl+F` again to stop and transcribe
3. Transcription is automatically copied and pasted

### Floating Indicator
- **Idle**: Small cyan dot at bottom of screen
- **Recording**: Expanded with live waveform
- **Transcribing**: Spinner with percentage progress
- **Click**: Toggle recording
- **Right-click**: Settings menu (model selection, input device, quit)
- **Drag**: Reposition anywhere on screen

### File Transcription (Raycast)
```bash
# Via CLI (results cached for 24 hours)
python transcribe_file.py /path/to/audio.mp3
python transcribe_file.py --force /path/to/audio.mp3  # Bypass cache

# Or copy file path to clipboard and press Ctrl+Option+F
```

Supported formats: WAV, MP3, M4A, FLAC, OGG, OPUS, WEBM, MP4, M4V, MOV

### Daemon Management
```bash
./scripts/whisper-daemon.sh start    # Start in background
./scripts/whisper-daemon.sh stop     # Stop daemon
./scripts/whisper-daemon.sh restart  # Restart daemon
./scripts/whisper-daemon.sh status   # Check status and memory usage
./scripts/whisper-daemon.sh logs     # View recent logs
```

## Models

Available Whisper models (select via right-click menu):
| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| tiny | ~75 MB | Fastest | Basic |
| base | ~140 MB | Fast | Good (default) |
| small | ~500 MB | Medium | Better |
| medium | ~1.5 GB | Slower | High |
| large-v2 | ~3 GB | Slowest | Best |

Models are automatically downloaded to `~/.cache/whisper/` on first use.

## Configuration

Settings are stored in `~/Library/Application Support/WhisperTranscribeUI/settings.json`:
- Model selection
- Input device
- Post-processing (LLM cleanup) toggle
- Indicator position

Most settings can be changed via the right-click menu.

## Knowledge Base Workflow (`kb/`)

A separate system for archiving video content to a structured JSON knowledge base with LLM analysis.

```bash
# Transcribe a video to KB
python kb/transcribe.py -i /path/to/video.mp4

# Analyze transcripts with Gemini
python kb/analyze.py -p        # Interactive, pending only
python kb/analyze.py --list    # Show all transcripts and status

# Batch capture from sources
python kb/capture.py           # Cap recordings
python kb/volume_sync.py       # Mounted volume
```

**Output:** `~/Obsidian/zen-ai/knowledge-base/transcripts/`

**Features:**
- Decimal category system (50.01.01 = Skool classroom, etc.)
- Tracks already-transcribed files (no re-processing)
- LLM analysis: summary, key_points, guide, resources
- Skips already-analyzed types

See [architecture doc](tasks/active/T011-knowledge-base-capture/architecture.md) for full system design.

## Project Structure
```
whisper-transcribe-ui/
├── app/
│   ├── core/           # Shared services (audio, transcription)
│   ├── daemon/         # Daemon mode (primary)
│   └── utils/          # Utilities
├── kb/                 # Knowledge Base workflow
│   ├── transcribe.py   # Core KB transcription
│   ├── analyze.py      # LLM analysis (Gemini)
│   ├── capture.py      # Cap recordings
│   └── volume_sync.py  # Volume auto-sync
├── _legacy/            # Deprecated Full UI mode
├── scripts/            # Shell scripts (whisper-daemon.sh, etc.)
├── transcribe_file.py  # CLI file transcription
└── tasks/              # Development task tracking
```

## Troubleshooting

### Hotkeys not working
Ensure Accessibility permission is granted for Terminal or your Python installation.

### Model download issues
Models are cached in `~/.cache/whisper/`. Delete this folder to re-download.

### Audio recording issues
Check microphone permissions in System Settings → Privacy & Security → Microphone.

### View logs
```bash
./scripts/whisper-daemon.sh logs
# Or: cat /tmp/whisper-daemon.log
```

## Legacy Full UI Mode

A more feature-rich UI with Fabric integration and meeting transcription exists in `_legacy/`. It uses faster-whisper instead of whisper.cpp. To run it:
```bash
./_legacy/run_whisper_ui.sh
```
This mode is not actively maintained.

## License

MIT

## Acknowledgments

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) - Fast C++ Whisper implementation
- [pywhispercpp](https://github.com/aarnphm/pywhispercpp) - Python bindings for whisper.cpp
- [OpenAI Whisper](https://github.com/openai/whisper) - Original Whisper model
- [PySide6](https://www.qt.io/qt-for-python) - Qt for Python
- [pynput](https://github.com/moses-palmer/pynput) - Global hotkey support
