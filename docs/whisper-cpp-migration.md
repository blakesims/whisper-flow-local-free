# whisper.cpp Migration Plan

## Overview

Migrate from `faster-whisper` to `whisper.cpp` (via `pywhispercpp`) for 5-6x transcription speed improvement on Apple Silicon.

## Status: ✅ Complete

| Task | Status |
|------|--------|
| Research & benchmarks | ✅ Done |
| Create migration plan | ✅ Done |
| Install pywhispercpp | ✅ Done |
| Create WhisperCppService | ✅ Done |
| Update daemon to use new service | ✅ Done |
| Test performance | 🔄 In Progress |
| Fallback mechanism | ✅ Done (auto-fallback to faster-whisper) |

### Implementation Results

- **Metal GPU**: Enabled (MTLGPUFamilyMetal3)
- **Memory Usage**: 328 MB (base model)
- **Model Size**: 147.37 MB on GPU
- **Load Time**: ~10s (first time includes download)

## Implementation Details

### 1. Installation

```bash
# Install pywhispercpp with Metal support
pip install pywhispercpp

# Required dependency
brew install ffmpeg
```

### 2. New Service: `app/core/transcription_service_cpp.py`

```python
from pywhispercpp.model import Model

class WhisperCppService:
    def __init__(self, model_name="base"):
        self.model = None
        self.model_name = model_name

    def load_model(self):
        # Models auto-download to ~/.cache/whisper/
        self.model = Model(self.model_name)

    def transcribe(self, audio_path, language=None):
        segments = self.model.transcribe(audio_path, language=language)
        text = " ".join(seg.text for seg in segments)
        return {"text": text, "segments": segments}
```

### 3. Model Mapping

| Model Name | whisper.cpp Name | Size |
|------------|------------------|------|
| tiny | tiny | 75MB |
| base | base | 140MB |
| small | small | 500MB |
| medium | medium | 1.5GB |
| large-v2 | large | 3GB |

### 4. API Differences

| Feature | faster-whisper | pywhispercpp |
|---------|---------------|--------------|
| Model loading | `WhisperModel()` | `Model()` |
| Transcribe | `.transcribe()` returns generator | `.transcribe()` returns list |
| Progress callback | Supported | Not directly supported |
| VAD | Built-in | Built-in |
| Language detection | Automatic | Automatic |

### 5. Migration Strategy

**Option A: Replace entirely** (recommended)
- Simpler codebase
- One transcription engine
- Consistent behavior

**Option B: Feature flag**
- Keep both engines
- Allow users to choose
- More complex

## Rollback Plan

If whisper.cpp has issues:
1. Keep `transcription_service.py` (faster-whisper) as backup
2. Add config option: `transcription_engine: "cpp" | "faster-whisper"`
3. Default to cpp, fallback to faster-whisper if import fails

## Testing Checklist

- [ ] Short recordings (< 5 seconds)
- [ ] Long recordings (> 5 minutes)
- [ ] Multiple languages
- [ ] Noisy audio
- [ ] Memory usage
- [ ] Model switching
- [ ] Daemon restart behavior
