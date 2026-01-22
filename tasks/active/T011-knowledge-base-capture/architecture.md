# KB System Architecture

## Overview

The Knowledge Base (KB) system captures video/audio content as structured JSON transcripts with LLM-generated analysis. It's designed for archiving educational content, coaching sessions, and idea captures.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           INPUT SOURCES                                  │
├──────────────────┬──────────────────┬──────────────────┬────────────────┤
│  Mounted Volume  │  Cap Recordings  │  Zoom Meetings   │  Direct File   │
│  /Volumes/...    │  ~/Library/...   │  ~/Documents/... │  Any path      │
└────────┬─────────┴────────┬─────────┴────────┬─────────┴───────┬────────┘
         │                  │                  │                 │
         ▼                  ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         KB SCRIPTS (kb/)                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │volume_sync  │  │  capture    │  │ (future)    │  │ transcribe  │    │
│  │   .py       │  │    .py      │  │  zoom.py    │  │    .py      │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         └─────────────────┴─────────────────┴───────────────┘           │
│                                    │                                     │
│                    ┌───────────────▼───────────────┐                    │
│                    │  app/core/transcription_      │                    │
│                    │       service_cpp.py          │                    │
│                    │    (whisper.cpp backend)      │                    │
│                    └───────────────┬───────────────┘                    │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE BASE OUTPUT                                 │
│              ~/Obsidian/zen-ai/knowledge-base/transcripts/              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ config/                                                          │   │
│  │   ├── registry.json      (decimals, tags, transcribed_files)    │   │
│  │   └── analysis_types/    (LLM prompt definitions)               │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │ 50.00.01/  Raw captures                                         │   │
│  │ 50.01.01/  Skool classroom    ← 260122-skool-cc-skills.json    │   │
│  │ 50.01.02/  Skool Q&A                                            │   │
│  │ 50.02.01/  YouTube                                              │   │
│  │ 50.03.01/  Alpha cohort                                         │   │
│  │ 50.03.02/  Beta cohort                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         LLM ANALYSIS (kb/analyze.py)                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Google Gemini API (gemini-2.0-flash)                            │  │
│  │  Reads: config/analysis_types/*.json                             │  │
│  │  Outputs: transcript.analysis.{summary, key_points, guide, ...}  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tracking & State

### registry.json

Central ledger at `config/registry.json`:

```json
{
  "decimals": {
    "50.01.01": {
      "name": "Skool classroom content",
      "description": "Published tutorials...",
      "default_analyses": ["summary", "guide", "resources"]
    }
  },
  "tags": ["claude-code", "workflow", "alpha-cohort", ...],
  "transcribed_files": [
    "/Volumes/BackupArchive/skool-videos/skool-cc-skills.mp4",
    ...
  ]
}
```

**What it tracks:**
- `transcribed_files`: Absolute paths of source files already processed (prevents re-transcription)
- `tags`: Global tag vocabulary (new tags auto-added)
- `decimals`: Category definitions with default analysis types

### Transcript JSON

Each transcript is stored as `{YYMMDD}-{slug}.json`:

```json
{
  "id": "50.01.01-260122-skool-cc-skills",
  "decimal": "50.01.01",
  "title": "skool-cc-skills",
  "source_files": ["/Volumes/BackupArchive/skool-videos/skool-cc-skills.mp4"],
  "recorded_at": "2026-01-22",
  "duration_seconds": 1548,
  "speakers": ["Blake Sims"],
  "tags": ["claude-code", "skills"],
  "transcript": "Full transcript text...",
  "analysis": {
    "summary": { "summary": "..." },
    "key_points": { "key_points": [...] }
  }
}
```

**Analysis status tracked by presence of keys in `analysis` object.**

---

## Input Sources

### 1. Mounted Volume (`kb/volume_sync.py`)

**Path:** `/Volumes/BackupArchive/skool-videos/`

**File naming convention:**
```
skool-cc-skills.mp4
skool-planning-deep-dive.mp4
```
- Prefix `skool-` stripped for title
- Hyphens converted to spaces, title-cased

**Tracking:** `registry.json.transcribed_files` prevents re-processing

### 2. Cap Recordings (`kb/capture.py`)

**Path:** `~/Library/Application Support/so.cap.desktop.dev/recordings/`

**Structure:**
```
recordings/
└── {uuid}.cap/
    ├── recording-meta.json
    └── content/segments/segment-0/
        └── audio-input.ogg
```

**Tracking:** By source file path in `transcribed_files`

### 3. Zoom Meetings (NOT YET IMPLEMENTED)

**Path:** `~/Documents/Zoom/`

**Structure:**
```
Zoom/
└── 2024-03-11 21.54.11 Blake Sims's Personal Meeting Room/
    ├── audio_only.m4a
    └── video_gallery.mp4
```

**Potential decimal:** `50.03.01` / `50.03.02` (cohort sessions)

**Integration approach:**
- Add `kb/zoom_sync.py` similar to `volume_sync.py`
- Parse folder name for date
- Track by folder path in `transcribed_files`

### 4. Direct File (`kb/transcribe.py`)

Any audio/video file via CLI:
```bash
python kb/transcribe.py -i /path/to/file.mp4
```

---

## Analysis Types

Defined in `config/analysis_types/*.json`:

| Type | Output Schema | Use Case |
|------|---------------|----------|
| `summary` | `{summary: string}` | Quick overview |
| `key_points` | `{key_points: [{quote, insight}]}` | Learning moments |
| `guide` | `{guide: {title, steps[], tips[]}}` | How-to extraction |
| `resources` | `{resources: [{name, url, description}]}` | Links mentioned |
| `improvements` | `{improvements: [...]}` | Instructor notes (private) |
| `lead_magnet` | `{ideas: [...]}` | Content marketing |

**Each decimal has `default_analyses`** pre-selected in CLI.

---

## Key Behaviors

| Behavior | Implementation |
|----------|----------------|
| Skip already-transcribed files | Check `registry.json.transcribed_files` |
| Skip already-analyzed types | Check `transcript.analysis` keys |
| Network volume optimization | Extract audio via ffmpeg (~1% of file size) |
| Interactive selection | questionary checkboxes with vim navigation |
| Batch processing | `--all-pending` flag in analyze.py |

---

## Dependencies

| Component | Depends On |
|-----------|------------|
| `kb/transcribe.py` | `app/core/transcription_service_cpp.py` (whisper.cpp) |
| `kb/analyze.py` | Google Gemini API (`google-genai` package) |
| `kb/capture.py` | ffmpeg (audio merging) |
| `kb/volume_sync.py` | ffmpeg (audio extraction) |
| All scripts | `config/registry.json` for decimals/tags |

---

## Future: Zoom Integration

To add Zoom meeting support:

1. Create `kb/zoom_sync.py`:
   ```python
   ZOOM_DIR = Path.home() / "Documents" / "Zoom"

   def get_zoom_recordings():
       for folder in ZOOM_DIR.iterdir():
           # Parse: "2024-03-11 21.54.11 Blake Sims's..."
           date_str = folder.name[:10]  # "2024-03-11"
           audio = folder / "audio_only.m4a"
           if audio.exists():
               yield {"path": str(audio), "date": date_str, ...}
   ```

2. Add decimal `50.04.01` for Zoom recordings (or map to cohort decimals)

3. Track by folder path in `transcribed_files`

This would consolidate the legacy Zoom transcription workflow into the KB system.
