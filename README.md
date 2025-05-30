# Whisper Transcription UI

A macOS desktop application for audio recording and transcription using OpenAI's Whisper AI model locally. Features a modern floating UI with real-time audio visualization, keyboard shortcuts, and optional AI-powered text processing through Fabric patterns.

## Features

- 🎙️ **Audio Recording**: High-quality audio recording with real-time waveform visualization
- 🤖 **Local AI Transcription**: Uses Whisper AI models locally (no internet required for transcription)
- 📁 **File Upload**: Upload existing audio files for transcription
- ⌨️ **Keyboard-Driven**: Efficient keyboard shortcuts (R, S, P, T, F, U, Q)
- 🎨 **Modern UI**: Floating window with Tokyo Night theme
- 🧵 **Fabric Integration**: Optional AI-powered text processing (requires Fabric CLI)
- 🚀 **Optimized for Apple Silicon**: Specially tuned for M1/M2/M3 processors

## Requirements

- macOS 11.0 or later
- Python 3.9 or later
- Microphone permissions
- ~2-6GB disk space for Whisper models

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/whisper-transcribe-ui.git
cd whisper-transcribe-ui
```

### 2. Create virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the application
```bash
./run_whisper_ui.sh
```

## Usage

### Keyboard Shortcuts
- **R** - Start/Resume recording
- **S** - Stop recording
- **P** - Pause recording
- **C** - Cancel recording
- **T** - Transcribe (with auto-paste)
- **F** - Process with Fabric
- **U** - Upload audio file
- **Q** - Quit application
- **M** - Minimize window

### Recording Workflow
1. Press **R** to start recording
2. Press **S** to stop or **T** to stop and transcribe immediately
3. Transcription is automatically copied to clipboard and pasted

### File Upload Workflow
1. Press **U** to open file dialog
2. Select an audio file (WAV, MP3, M4A, FLAC, OGG, OPUS, WEBM)
3. Transcription starts automatically

### Fabric Workflow (Optional)
1. Record audio or upload file
2. Press **F** to open Fabric pattern selection
3. Search and select a pattern
4. Processed text is copied and pasted automatically

## Models

Available Whisper models (automatically downloaded on first use):
- **tiny** (~39 MB) - Fastest, lowest accuracy
- **base** (~74 MB) - Good balance (default)
- **small** (~244 MB) - Better accuracy
- **medium** (~769 MB) - High accuracy
- **large** (~1550 MB) - Best accuracy

## Performance

### Apple Silicon Optimization
The app is specially optimized for M1/M2/M3 processors:
- Uses all available cores efficiently
- Voice Activity Detection for faster processing
- Optimized beam search parameters
- Typically 4x faster than standard Whisper

### CPU Usage
- **faster-whisper**: 50-70% CPU (efficient)
- **openai-whisper**: 90-100% CPU (less efficient)
- Lower CPU usage = more efficient processing

## Building

To create a macOS app bundle:
```bash
./build_app.sh
```

The app will be in `dist/Whisper Transcription UI.app`

## Configuration

Settings can be configured via `config.json` (when implemented):
- Model selection
- CPU thread count
- Fabric settings
- Audio quality

## Troubleshooting

### High CPU Usage
This is normal during transcription. The app uses optimized settings for your hardware.

### Model Download Issues
Models are cached in `~/.cache/whisper/`. Delete this folder to re-download.

### Audio Recording Issues
Ensure microphone permissions are granted in System Preferences > Security & Privacy.

## Development

### Project Structure
```
whisper-transcribe-ui/
├── app/
│   ├── core/           # Core services
│   ├── ui/             # UI components
│   └── utils/          # Utilities
├── resources/          # Icons and assets
├── tasks/              # Development tasks
└── requirements.txt    # Dependencies
```

### Running Tests
```bash
python test_cpu_optimization.py
python compare_whisper_implementations.py audio_file.wav
```

## License

[Your license here]

## Acknowledgments

- OpenAI Whisper
- faster-whisper by guillaumekln
- Fabric by danielmiessler
- PySide6 (Qt for Python)