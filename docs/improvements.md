# Whisper Transcribe UI - Improvements Roadmap

## Status Tracking

| # | Feature | Priority | Status | Effort | Impact | Notes |
|---|---------|----------|--------|--------|--------|-------|
| 1 | [whisper.cpp Migration](#1-whispercpp-migration) | High | ✅ Done | Medium | 5-6x faster | Metal GPU enabled |
| 2 | [LLM Post-Processing](#2-llm-post-processing) | High | ⏳ Planned | Medium | Cleaner output | MLX + Phi-3.2 |
| 3 | [Speech Clarity Metrics](#3-speech-clarity-metrics) | Medium | ⏳ Planned | Low | User feedback | Filler word tracking |
| 4 | [Clarity Tracking Over Time](#4-clarity-tracking-over-time) | Medium | ⏳ Planned | Medium | Gamification | Historical trends |
| 5 | [Model Selection in UI](#5-model-selection-in-ui) | Low | ⏳ Planned | Low | Flexibility | Settings dialog |
| 6 | [Native App (Rust/Swift)](#6-native-app-rustswift) | Low | 💭 Future | High | Best performance | Long-term goal |

**Legend:** ✅ Done | 🔄 In Progress | ⏳ Planned | 💭 Future | ❌ Blocked

---

## 1. whisper.cpp Migration

**Goal:** Replace faster-whisper with whisper.cpp for 5-6x speed improvement on Apple Silicon.

### Benchmarks (Apple Silicon)

| Engine | Speed | Relative |
|--------|-------|----------|
| faster-whisper (current) | 6.96s | 1x (baseline) |
| whisper.cpp | 1.23s | **5.7x faster** |
| MLX Whisper | 1.02s | 6.8x faster |

### Implementation

- **Library:** `pywhispercpp` (Python bindings for whisper.cpp)
- **Installation:** `pip install pywhispercpp`
- **Metal GPU:** Automatic on macOS
- **Tracking:** See [whisper-cpp-migration.md](./whisper-cpp-migration.md)

---

## 2. LLM Post-Processing

**Goal:** Optional local LLM cleanup of transcriptions (remove filler words, format lists).

### Recommended Stack

- **Framework:** MLX (Apple Silicon optimized)
- **Model:** Phi-3.2 mini (2.7B params, ~2GB)
- **Latency:** ~400-600ms for 100 words

### Features

- [ ] Remove filler words (um, uh, like, you know, kind of, sort of)
- [ ] Format numbered items as bullet lists
- [ ] Light grammar cleanup
- [ ] Toggle in right-click menu

### Example Prompt

```
Clean up the following transcribed text:
- Remove filler words (um, uh, like, you know, sort of, kind of)
- Format numbered lists as bullet points
- Fix obvious grammar issues
- Keep original meaning

Text: {transcription}
```

---

## 3. Speech Clarity Metrics

**Goal:** Real-time feedback on speech quality to help users improve.

### Metrics to Track

| Metric | Description | Target |
|--------|-------------|--------|
| Filler word count | um, uh, like, you know | < 2 per minute |
| Speaking pace | Words per minute | 120-150 WPM |
| Repetitions | Repeated phrases | 0 |
| Restructuring needed | Sentences LLM had to reorder | < 10% |

### UI Concept

```
┌─────────────────────────────────────────────────────────┐
│  Speech Clarity Score: 78%  ████████░░                  │
├─────────────────────────────────────────────────────────┤
│  Filler words: 3 (um, like, you know)                   │
│  Words/minute: 142 (optimal: 120-150)                   │
│  Repetitions: 1                                          │
├─────────────────────────────────────────────────────────┤
│  Tip: You said "like" 2 times. Try pausing instead.     │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Clarity Tracking Over Time

**Goal:** Track improvement in speech clarity over time.

### Features

- [ ] Store clarity scores per transcription
- [ ] Weekly/monthly trend graphs
- [ ] Common filler words breakdown
- [ ] Speaking pace trends
- [ ] Streak tracking (consecutive clean transcriptions)

---

## 5. Model Selection in UI

**Goal:** Expose Whisper model selection in settings dialog.

### Models Available

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| tiny | 75MB | Fastest | Basic |
| base | 140MB | Fast | Good |
| small | 500MB | Medium | Better |
| medium | 1.5GB | Slow | High |
| large-v2 | 3GB | Slowest | Best |

### Implementation

- Add dropdown to Settings dialog
- Show download size and speed/quality tradeoff
- Model downloads on first use

---

## 6. Native App (Rust/Swift)

**Goal:** Long-term rewrite for maximum performance.

### Options

| Approach | Pros | Cons |
|----------|------|------|
| **Tauri + Rust** | Cross-platform, fast, small binary | Learning curve |
| **Swift + SwiftUI** | Native macOS, best integration | Mac-only |
| **Rust + egui** | Cross-platform, very fast | Less native feel |

### Components to Rewrite

1. Audio recording (currently Python sounddevice)
2. Whisper integration (use whisper.cpp directly)
3. UI (replace PySide6)
4. Hotkey listener (use native APIs)

---

## Research Notes

### Performance Comparison Sources

- [Apple Silicon Whisper Performance Benchmarks](https://www.voicci.com/blog/apple-silicon-whisper-performance.html)
- [mac-whisper-speedtest M4 benchmarks](https://github.com/anvanvan/mac-whisper-speedtest)
- [Production-Grade Local LLM on Apple Silicon](https://arxiv.org/abs/2511.05502)

### Current Optimizations (Already Implemented)

- ✅ int8 quantization
- ✅ VAD filter enabled
- ✅ beam_size=1 (fast mode)
- ✅ Apple Silicon threading (n-1 cores)
- ✅ Hallucination detection
- ✅ temperature=0.0 (deterministic)
