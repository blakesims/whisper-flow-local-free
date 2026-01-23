# Task: KB Transcription Architecture + Zoom Support

## Task ID
T012

## Overview
Refactor the KB CLI architecture to unify all transcription sources under `kb transcribe`, then add Zoom meeting support and clipboard paste import.

**Current State**: Separate top-level commands (`kb transcribe`, `kb capture`, `kb sync`)
**Target State**: Unified `kb transcribe` with source submenu (`file`, `cap`, `volume`, `zoom`, `paste`)

## Objectives
- Create `kb/core.py` for shared utilities (prevents import breakage)
- Refactor CLI: `kb transcribe` becomes interactive submenu with sources
- Unify transcript format: `[MM:SS]` or `[HH:MM:SS] Speaker: Text` (no markdown bold)
- Add `type` field to JSON schema for source identification
- Add Zoom source: multi-file meeting transcription from `~/Documents/Zoom/`
- Add Paste source: import transcript text from clipboard (Google Meet, etc.)
- Define `--analyze` flag flow through source dispatcher
- Maintain non-interactive mode for Raycast scripts
- Update `pyproject.toml` entry points
- Keep `kb analyze` as separate top-level command

## Dependencies
- None (self-contained in `kb/` module)

## Rules Required
- task-documentation

## Resources & References
- Legacy implementation: `_legacy/ui/meeting_worker.py`
- Data structures: `_legacy/app/core/meeting_transcript.py`
- Current KB transcribe: `kb/transcribe.py`
- Current whisper.cpp service: `app/core/transcription_service_cpp.py`

## Technical Design

### Zoom Folder Structure
```
~/Documents/Zoom/
└── 2024-03-11 21.54.11 Blake Sims's Personal Meeting Room/
    ├── Audio Record/
    │   ├── audioBlakeSims21759316641.m4a
    │   └── audioHonedInTutoring11759316641.m4a
    ├── chat.txt
    └── recording.conf
```

### Speaker Name Extraction
Pattern: `audio{CamelCaseName}{ID}.m4a` → Insert spaces before capitals
- `audioBlakeSims21759316641.m4a` → "Blake Sims"
- `audioHonedInTutoring11759316641.m4a` → "Honed In Tutoring"

### Output JSON Schema
```json
{
  "id": "50.03.01-240311-alpha-session-blake-tutoring",
  "decimal": "50.03.01",
  "title": "Alpha Session - Blake, Tutoring",
  "type": "meeting",
  "source_files": ["/full/path/audioBlakeSims...m4a", "/full/path/audioHoned...m4a"],
  "source_folder": "/Users/blake/Documents/Zoom/2024-03-11...",
  "recorded_at": "2024-03-11",
  "duration_seconds": 3600,
  "speakers": ["Blake Sims", "Honed In Tutoring"],
  "tags": ["meeting", "zoom", "alpha"],
  "transcript": "[00:05] Blake Sims: Hello, can you hear me?\n[00:08] Honed In Tutoring: Yes, loud and clear...",
  "analysis": {},
  "created_at": "2025-01-23T10:00:00"
}
```

**`type` values**: `video`, `audio`, `meeting`, `paste`, `cap`

### Registry Tracking
Add to `registry.json`:
```json
{
  "transcribed_zoom_meetings": [
    "/Users/blake/Documents/Zoom/2024-03-11 21.54.11 Blake Sims's Personal Meeting Room"
  ]
}
```

### Decimal Categories
```
50.03.01 - Alpha cohort sessions (DEFAULT)
50.03.02 - Beta cohort sessions
50.03.xx - Other cohort sessions
50.04    - Generic zoom meetings
```

### CLI Interface
```bash
# List unprocessed Zoom meetings
kb zoom --list

# Transcribe specific meeting (interactive prompts for decimal/title)
kb zoom "2024-03-11 21.54.11 Blake Sims's Personal Meeting Room"

# Non-interactive with explicit options
kb zoom --decimal 50.03.01 --title "Alpha Session 5" "2024-03-11..."

# With analysis
kb zoom --analyze summary "2024-03-11..."
```

**Interactive Flow** (default):
```
$ kb zoom "2024-03-11..."

Found 2 participants: Blake Sims, Honed In Tutoring

Category:
  [1] Alpha cohort (50.03.01)  <- default
  [2] Beta cohort (50.03.02)
  [3] Generic zoom (50.04)
  [4] Other (enter decimal)

Title [Alpha Session - 2024-03-11]: _

Transcribing...
```

## Phases Breakdown

### Phase 0: CLI Architecture Refactor
**Status**: Completed (2025-01-23)

**Objectives**:
- Create `kb/core.py` for shared utilities (critical - prevents import breakage)
- Restructure `kb/__main__.py` to make `transcribe` a submenu
- Create `kb/sources/` directory with modular source handlers
- Move existing logic into source modules
- Add `paste` source for clipboard import
- Standardize transcript format (no markdown bold)
- Update `pyproject.toml` entry points
- Ensure non-interactive mode still works
- Add `type` field to JSON schema for source identification

#### Current Structure
```
kb/__main__.py          # Main menu: transcribe, analyze, capture, sync
kb/transcribe.py        # Single file transcription + transcribe_to_kb()
kb/capture.py           # Cap recordings batch (imports from transcribe.py)
kb/volume_sync.py       # Mounted volume auto-transcribe (imports from transcribe.py)
kb/cli.py               # Interactive prompt helpers (duplicates some registry funcs)
kb/analyze.py           # LLM analysis (unchanged)
```

#### Target Structure
```
kb/__main__.py          # Main menu: transcribe, analyze, config
kb/transcribe.py        # Transcribe submenu dispatcher + --analyze flow
kb/core.py              # Shared utilities (NEW - critical)
kb/sources/
├── __init__.py         # Source registry
├── file.py             # Single file (from old transcribe.py)
├── cap.py              # Cap recordings (from old capture.py)
├── volume.py           # Mounted volumes (from old volume_sync.py)
├── zoom.py             # Zoom meetings (new - Phase 1)
└── paste.py            # Clipboard import (new)
kb/cli.py               # Shared interactive helpers (consolidated)
kb/analyze.py           # LLM analysis (unchanged)
```

#### Key Changes

**0. `kb/core.py` - Shared Utilities (CRITICAL)**

Extract these from `transcribe.py` and `cli.py` to prevent import breakage:
```python
# kb/core.py - Shared utilities for all sources
"""Core utilities shared across KB sources."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from kb.__main__ import load_config, get_paths, KB_ROOT, CONFIG_DIR

REGISTRY_PATH = CONFIG_DIR / "registry.json"

# --- Registry Functions (consolidated from transcribe.py + cli.py) ---
def load_registry() -> dict:
    """Load the registry.json file."""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {"decimals": {}, "tags": [], "transcribed_files": [], "transcribed_zoom_meetings": []}

def save_registry(registry: dict):
    """Save the registry.json file."""
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)

# --- Transcription Utilities ---
def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def get_audio_duration(file_path: str) -> int:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return int(float(result.stdout.strip()))
    except Exception:
        pass
    return 0

def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

# --- LocalFileCopy for network volumes ---
class LocalFileCopy:
    """Context manager to extract audio from network files."""
    # ... (move from transcribe.py)

# --- Core Transcription Function ---
def transcribe_to_kb(
    file_path: str,
    decimal: str,
    title: str,
    tags: list[str],
    recorded_at: str | None = None,
    speakers: list[str] | None = None,
    source_type: str = "video",  # NEW: video, audio, meeting, paste, cap
    model_name: str = "medium",
    transcript_text: str | None = None,  # NEW: for paste source (already has transcript)
) -> dict:
    """
    Transcribe a file (or save existing transcript) to the knowledge base.
    Returns the saved transcript data.
    """
    # ... (move from transcribe.py, add source_type field)

# --- Progress Reporting (unified) ---
def print_status(msg: str):
    """Print status message with consistent format."""
    print(f"[KB] {msg}", flush=True)
```

**1. `kb/__main__.py` - Simplified Top-Level Menu**
```python
COMMANDS = {
    "transcribe": {
        "label": "Transcribe",
        "description": "Transcribe audio/video to Knowledge Base",
        "module": "kb.transcribe",  # Now shows source submenu
    },
    "analyze": {
        "label": "Analyze",
        "description": "Run LLM analysis on existing transcript",
        "module": "kb.analyze",
    },
}
# Remove: capture, sync (now under transcribe)
```

**2. `kb/transcribe.py` - Source Submenu**
```python
SOURCES = {
    "file": {
        "label": "File",
        "description": "Transcribe a single audio/video file",
        "handler": "kb.sources.file",
    },
    "cap": {
        "label": "Cap",
        "description": "Batch process Cap recordings",
        "handler": "kb.sources.cap",
    },
    "volume": {
        "label": "Volume",
        "description": "Auto-transcribe from mounted volume",
        "handler": "kb.sources.volume",
    },
    "zoom": {
        "label": "Zoom",
        "description": "Transcribe Zoom meeting recordings",
        "handler": "kb.sources.zoom",
    },
    "paste": {
        "label": "Paste",
        "description": "Import transcript from clipboard",
        "handler": "kb.sources.paste",
    },
}

def show_source_menu() -> str | None:
    """Show source selection menu."""
    # Interactive: questionary select
    # Returns source key

def main():
    args = sys.argv[1:]

    # Non-interactive: kb transcribe file /path/to/file.mp4
    if args and args[0] in SOURCES:
        run_source(args[0], args[1:])
        return

    # Interactive: show source menu
    selected = show_source_menu()
    if selected:
        run_source(selected, [], interactive=True)
```

**3. `kb/sources/paste.py` - Clipboard Import**
```python
"""Import transcript from clipboard."""

import re
import subprocess
from datetime import datetime

# Expected format from Google Meet script (supports both MM:SS and HH:MM:SS):
# [00:25] Blake Sims: It.
# [03:57] Nemanja Pavlovic: Hey there.
# [01:23:45] Speaker: For longer meetings...

# Regex handles both [MM:SS] and [HH:MM:SS] formats
TRANSCRIPT_PATTERN = re.compile(
    r'^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s+([^:]+):\s+(.+)$',
    re.MULTILINE
)

def get_clipboard() -> str:
    """Get clipboard contents (macOS)."""
    result = subprocess.run(['pbpaste'], capture_output=True, text=True)
    return result.stdout

def normalize_timestamp(ts: str) -> str:
    """Normalize timestamp to HH:MM:SS format."""
    parts = ts.split(':')
    if len(parts) == 2:
        # MM:SS -> 00:MM:SS
        return f"00:{parts[0].zfill(2)}:{parts[1]}"
    elif len(parts) == 3:
        # HH:MM:SS (already correct)
        return f"{parts[0].zfill(2)}:{parts[1]}:{parts[2]}"
    return ts

def validate_transcript(text: str) -> tuple[bool, list[dict]]:
    """
    Validate clipboard text is a transcript.
    Returns (is_valid, parsed_segments).
    """
    matches = TRANSCRIPT_PATTERN.findall(text)
    if not matches:
        return False, []

    segments = [
        {
            "timestamp": normalize_timestamp(m[0]),
            "speaker": m[1].strip(),
            "text": m[2].strip()
        }
        for m in matches
    ]
    return True, segments

def extract_speakers(segments: list[dict]) -> list[str]:
    """Extract unique speakers in order of appearance."""
    seen = set()
    speakers = []
    for seg in segments:
        if seg["speaker"] not in seen:
            seen.add(seg["speaker"])
            speakers.append(seg["speaker"])
    return speakers

def run_interactive():
    """Interactive paste import flow."""
    console.print(Panel("[bold]Import Transcript from Clipboard[/bold]", border_style="cyan"))

    # Get clipboard
    text = get_clipboard()
    if not text.strip():
        console.print("[red]Clipboard is empty[/red]")
        return

    # Validate format
    is_valid, segments = validate_transcript(text)
    if not is_valid:
        console.print("[red]Clipboard does not contain valid transcript format[/red]")
        console.print("[dim]Expected: [MM:SS] Speaker: Text  or  [HH:MM:SS] Speaker: Text[/dim]")
        return

    # Show preview
    speakers = extract_speakers(segments)
    console.print(f"\n[green]Found {len(segments)} segments from {len(speakers)} speakers:[/green]")
    for speaker in speakers:
        console.print(f"  • {speaker}")

    console.print(f"\n[dim]Preview (first 3 lines):[/dim]")
    for seg in segments[:3]:
        console.print(f"  [{seg['timestamp']}] {seg['speaker']}: {seg['text'][:50]}...")

    # Prompt for metadata (reuse from cli.py)
    # ... decimal, title, tags, etc.

    # Save to KB JSON using core.transcribe_to_kb() with source_type="paste"
    # Pass transcript_text directly (no audio transcription needed)
```

**4. `kb/sources/file.py` - Single File (Interactive Enhancement)**
```python
"""Transcribe a single audio/video file."""

from pathlib import Path
import questionary
from rich.console import Console
from kb.core import transcribe_to_kb, load_registry

console = Console()

# Configurable recent directories (could move to config.yaml)
RECENT_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
]

SUPPORTED_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm',
                        '.mp4', '.m4v', '.mov', '.aac', '.wma', '.mkv', '.avi'}

def find_recent_media(directory: Path, limit: int = 10) -> list[Path]:
    """Find recent audio/video files in a directory."""
    files = []
    if directory.exists():
        for f in directory.iterdir():
            if f.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(f)
    # Sort by modification time, most recent first
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]

def run_interactive():
    """Interactive file selection flow."""
    console.print(Panel("[bold]Transcribe File[/bold]", border_style="cyan"))

    # Build choices: recent files from configured dirs + free-form entry
    choices = []

    for directory in RECENT_DIRS:
        recent = find_recent_media(directory)
        if recent:
            for f in recent[:3]:  # Top 3 from each directory
                rel_path = f"~/{f.relative_to(Path.home())}"
                age = format_age(f.stat().st_mtime)
                choices.append(questionary.Choice(
                    title=f"{rel_path}  [dim]({age})[/dim]",
                    value=str(f)
                ))

    choices.append(questionary.Choice(
        title="[Enter path manually...]",
        value="__manual__"
    ))

    selected = questionary.select(
        "Select file:",
        choices=choices,
        style=custom_style,
    ).ask()

    if selected == "__manual__":
        file_path = questionary.text("File path:").ask()
        if not file_path:
            return
        file_path = Path(file_path.strip().strip("'\"")).expanduser()
    else:
        file_path = Path(selected)

    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    # Continue with decimal/title/tags prompts...
    # Then call core.transcribe_to_kb()
```

**5. Transcript Format Standardization**

All sources output plain format (no markdown):
```
[00:05] Blake Sims: Hello, can you hear me?
[00:08] Honed In Tutoring: Yes, loud and clear.
[01:23:45] Speaker: For longer content...
```

Format rules:
- Use `[MM:SS]` for content under 1 hour
- Use `[HH:MM:SS]` for content 1 hour or longer
- No markdown bold (`**`) around speaker names
- Single space after timestamp, colon after speaker name

Update these files to use plain format:
- `kb/sources/file.py` - use plain format
- `kb/sources/zoom.py` - use plain format
- `kb/sources/paste.py` - normalize input timestamps

#### Non-Interactive Mode Support

Each source must support direct CLI invocation:
```bash
# File
kb transcribe file /path/to/audio.mp4 --decimal 50.01 --title "My Video"

# Cap (process specific or all unprocessed)
kb transcribe cap                           # Interactive: select from list
kb transcribe cap --all                     # Process all unprocessed
kb transcribe cap "recording-id"            # Specific recording

# Volume
kb transcribe volume                        # Interactive: select from mounted
kb transcribe volume --all                  # Process all unprocessed

# Zoom
kb transcribe zoom                          # Interactive: select meeting
kb transcribe zoom "2024-03-11 21.54..."    # Specific meeting folder

# Paste
kb transcribe paste                         # Read from clipboard
kb transcribe paste --file transcript.txt   # Read from file instead
```

#### `--analyze` Flag Flow

Analysis can be triggered from any source via the dispatcher:
```
kb transcribe <source> [args] --analyze summary key_points
         │
         ▼
  Source handler produces transcript JSON
         │
         ▼
  Dispatcher checks for --analyze flag
         │
         ▼
  If set: calls kb.analyze.analyze_transcript_file(path, types)
```

Each source passes `--analyze` through to the dispatcher. The dispatcher handles it uniformly after the transcript is saved.

#### `type` Field in JSON Schema

Add `type` field to identify transcript source (useful for filtering/analysis):

| Source | Type Value |
|--------|------------|
| file (video) | `"video"` |
| file (audio) | `"audio"` |
| zoom | `"meeting"` |
| paste | `"paste"` |
| cap | `"cap"` |
| volume | `"video"` |

Detected from file extension or source type.

#### Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `kb/core.py` | **Create** | **CRITICAL**: Shared utilities extracted here |
| `kb/__main__.py` | Modify | Remove capture/sync from COMMANDS |
| `kb/transcribe.py` | Rewrite | Becomes source submenu dispatcher + --analyze flow |
| `kb/cli.py` | Modify | Consolidate registry functions, add source-specific helpers |
| `kb/sources/__init__.py` | Create | Source registry |
| `kb/sources/file.py` | Create | Extract from old transcribe.py |
| `kb/sources/cap.py` | Create | Extract from old capture.py |
| `kb/sources/volume.py` | Create | Extract from old volume_sync.py |
| `kb/sources/paste.py` | Create | New clipboard import |
| `kb/capture.py` | Delete | Moved to sources/cap.py |
| `kb/volume_sync.py` | Delete | Moved to sources/volume.py |
| `pyproject.toml` | **Modify** | Remove `kb-capture`, `kb-sync` entry points |

#### pyproject.toml Changes

```toml
# REMOVE these entry points:
# kb-capture = "kb.capture:main"
# kb-sync = "kb.volume_sync:main"

# UPDATE packages list to include sources:
[tool.setuptools.packages]
find = {}
# Will auto-discover kb.sources
```

#### Migration Notes

- Old `kb capture` → now `kb transcribe cap`
- Old `kb sync` → now `kb transcribe volume`
- Old `kb transcribe <file>` → now `kb transcribe file <file>`
- Backward compatibility aliases NOT needed (breaking change accepted)
- No Raycast scripts use old commands (confirmed)

#### Error Handling Strategy (Unified)

All sources follow the same pattern:
```python
try:
    result = process_item(item)
    console.print(f"[green]✓[/green] {item.name}")
except Exception as e:
    console.print(f"[yellow]⚠[/yellow] {item.name}: {e}")
    # Log error but continue with next item (don't abort batch)
```

#### Progress Reporting (Unified)

Use `kb.core.print_status()` for consistent output:
```
[KB] Loading model: medium...
[KB] Transcribing: audio.m4a (45s)
[KB] Saved: ~/Obsidian/.../50.03.01/240311-alpha-session.json
```

**Dependencies**: None

---

### Phase 1: Zoom Source
**Status**: Not Started

**Objectives**:
- Create `kb/sources/zoom.py` with meeting transcription logic
- Port `extract_speaker_name()` from legacy code
- Process pywhispercpp segments directly (use `t0`/`t1` centiseconds for timestamps)
- Implement segment merging and sorting by timestamp
- Zoom folder discovery from `~/Documents/Zoom/`
- Registry tracking of processed meeting folders (`transcribed_zoom_meetings` array)
- Interactive: single meeting selection (multi-select deferred to v2)
- Reuse `select_decimal()` from cli.py for decimal selection
- Skip failed participant files, continue with remaining (require at least 1 success)

#### Critical: Transcription Flow

**Zoom source does NOT use `transcribe_to_kb()` for transcription.** Instead:

```
1. Load WhisperCppService once (shared across all participant files)
2. For each participant audio file:
   - Call service.transcribe(audio_file)
   - Extract segments from result["segments"]
   - Tag each segment with speaker name and timestamps (t0/t1)
3. Merge all segments, sort by start timestamp
4. Format as transcript text: [MM:SS] Speaker: Text
5. Call transcribe_to_kb(transcript_text=..., source_type="meeting")
6. Manually update registry["transcribed_zoom_meetings"]
```

This follows the paste source pattern - `transcribe_to_kb()` is only used for saving, not transcribing.

**Key Code** (`kb/sources/zoom.py`):
```python
import re
from pathlib import Path
from datetime import datetime
from rich.console import Console
import questionary

from app.core.transcription_service_cpp import get_transcription_service
from app.utils.config_manager import ConfigManager
from kb.core import (
    transcribe_to_kb, load_registry, save_registry,
    format_timestamp, print_status, KB_ROOT
)
from kb.cli import select_decimal, get_title, select_tags, custom_style

console = Console()

ZOOM_DIR = Path.home() / "Documents" / "Zoom"
AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav'}

def parse_date_from_folder(folder_name: str) -> str:
    """Extract date from Zoom folder name (YYYY-MM-DD HH.MM.SS ...)."""
    match = re.match(r'^(\d{4}-\d{2}-\d{2})', folder_name)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y-%m-%d")

def extract_speaker_name(filename: str) -> str:
    """Extract speaker name from Zoom audio filename."""
    # Pattern: audioBlakeSims21759316641.m4a -> Blake Sims
    match = re.match(r'audio([A-Za-z]+)\d+\.\w+', filename)
    if match:
        name = match.group(1)
        # Insert spaces before capitals: BlakeSims -> Blake Sims
        return re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    # Fallback: use filename without extension
    return Path(filename).stem

def discover_meetings(zoom_dir: Path = ZOOM_DIR) -> list[dict]:
    """Find all Zoom meeting folders with Audio Record subdirs."""
    if not zoom_dir.exists():
        return []

    meetings = []
    for folder in zoom_dir.iterdir():
        if not folder.is_dir():
            continue
        audio_dir = folder / "Audio Record"
        if not audio_dir.exists():
            continue

        # Find audio files (support multiple extensions)
        audio_files = [f for f in audio_dir.iterdir()
                       if f.suffix.lower() in AUDIO_EXTENSIONS
                       and f.name.lower().startswith('audio')]

        if audio_files:
            meetings.append({
                "path": folder,
                "name": folder.name,
                "date": parse_date_from_folder(folder.name),
                "participants": [extract_speaker_name(f.name) for f in audio_files],
                "audio_files": audio_files,
            })

    return sorted(meetings, key=lambda m: m["date"], reverse=True)

def get_unprocessed_meetings(zoom_dir: Path = ZOOM_DIR) -> list[dict]:
    """Get meetings not yet in registry."""
    registry = load_registry()
    processed = set(registry.get("transcribed_zoom_meetings", []))

    all_meetings = discover_meetings(zoom_dir)
    return [m for m in all_meetings if str(m["path"]) not in processed]

def transcribe_meeting(meeting: dict, model_name: str = "medium") -> tuple[str, list[str], int]:
    """
    Transcribe all audio files and merge by timestamp.

    Returns: (transcript_text, speakers, duration_seconds)
    """
    config = ConfigManager()
    service = get_transcription_service(config)
    service.set_target_model_config(model_name, "cpu", "int8")

    print_status(f"Loading model: {model_name}...")
    service.load_model()

    all_segments = []
    speakers = []
    max_duration = 0

    for audio_file in meeting["audio_files"]:
        speaker = extract_speaker_name(audio_file.name)
        if speaker not in speakers:
            speakers.append(speaker)

        print_status(f"Transcribing {speaker}...")
        try:
            result = service.transcribe(str(audio_file))

            # Extract segments with timestamps
            for seg in result.get("segments", []):
                start = seg.t0 / 100.0  # centiseconds to seconds
                end = seg.t1 / 100.0
                all_segments.append({
                    "speaker": speaker,
                    "start": start,
                    "end": end,
                    "text": seg.text.strip(),
                })
                max_duration = max(max_duration, end)

        except Exception as e:
            console.print(f"[yellow]Warning: Failed {speaker}: {e}[/yellow]")
            continue

    if not all_segments:
        raise RuntimeError("No segments transcribed from any participant")

    # Sort by start timestamp
    all_segments.sort(key=lambda s: s["start"])

    # Format transcript
    lines = []
    for seg in all_segments:
        ts = format_timestamp(seg["start"])
        lines.append(f"[{ts}] {seg['speaker']}: {seg['text']}")

    transcript_text = "\n".join(lines)
    return transcript_text, speakers, int(max_duration)
```

**Non-Interactive Mode**:
```bash
kb transcribe zoom --list                              # Show unprocessed
kb transcribe zoom "2024-03-11 21.54..." --decimal 50.03.01 --title "Alpha S5"
```

**CLI Arguments**:
```python
parser.add_argument("folder_name", nargs="?", help="Zoom meeting folder name")
parser.add_argument("--decimal", "-d", help="Decimal category (required for non-interactive)")
parser.add_argument("--title", "-t", help="Title for the transcript")
parser.add_argument("--tags", nargs="+", help="Tags")
parser.add_argument("--analyze", "-a", nargs="*", help="Run analysis after transcription")
parser.add_argument("--list", action="store_true", help="List unprocessed meetings")
parser.add_argument("--zoom-dir", help="Custom Zoom recordings directory")
parser.add_argument("--model", "-m", default="medium", help="Whisper model")
```

**Registry Update**:
```python
# After successful transcription
registry = load_registry()
if "transcribed_zoom_meetings" not in registry:
    registry["transcribed_zoom_meetings"] = []
registry["transcribed_zoom_meetings"].append(str(meeting["path"]))
save_registry(registry)
```

**Dependencies**: Phase 0

#### Implementation Order

1. Create `kb/sources/zoom.py` skeleton with imports and constants
2. Implement `parse_date_from_folder()` and `extract_speaker_name()`
3. Implement `discover_meetings()` and `get_unprocessed_meetings()`
4. Implement `transcribe_meeting()` - test with one real meeting
5. Implement `run_interactive()` - meeting selection, decimal/title prompts
6. Implement `main()` for non-interactive mode
7. Update SOURCES registry to remove placeholder flag
8. Test both modes

---

### Phase 2: Testing & Documentation
**Status**: Not Started

**Objectives**:
- Test Phase 0 refactor (all existing sources still work)
- Test Zoom with real recordings (2-person, 3+ person)
- Test Paste with Google Meet clipboard format
- Test non-interactive modes for Raycast scripts
- Update CLAUDE.md with new CLI structure
- Document non-interactive usage for scripting

**Test Matrix**:
| Source | Interactive | Non-Interactive | Notes |
|--------|-------------|-----------------|-------|
| file | ✓ | ✓ | Existing, verify unchanged |
| cap | ✓ | ✓ | Verify after refactor |
| volume | ✓ | ✓ | Verify after refactor |
| zoom | ✓ | ✓ | New |
| paste | ✓ | ✓ | New |

**Dependencies**: Phase 0, Phase 1

## Implementation Notes

### whisper.cpp Segment Timestamps
The `pywhispercpp` model returns segments with `t0` and `t1` (start/end in centiseconds). Convert:
```python
start_seconds = segment.t0 / 100.0
end_seconds = segment.t1 / 100.0
```

**Important**: The current `WhisperCppService.transcribe()` already returns segments with these attributes. No need to add a new method - just process the segments directly in `kb/zoom.py`.

### Handling Concurrent Speech
When speakers talk simultaneously, segments will overlap. Use simple interleaving by start time (option 1). Accept that timestamps may not perfectly align due to audio sync drift between Zoom participant recordings.

### Error Handling
Skip failed participant files and continue with remaining participants. Log warning but don't abort the meeting transcription.

### Memory Efficiency
For long meetings, transcribe one file at a time with a single shared model instance:
```python
service = get_transcription_service(config)
service.load_model()  # Load once

for audio_file in audio_files:
    result = service.transcribe(audio_file)
    # Process segments...

# Model stays loaded for speed - unloaded when service goes out of scope
```

Note: `gc.collect()` is not effective here since the model remains referenced by the service instance. This is intentional for performance.

## Deferred to v2
- `--all` batch processing mode
- `speaker_stats` in JSON output (talk time percentages)
- Configurable zoom directory in config.yaml (hardcode `~/Documents/Zoom` for v1)

## Review Findings (2025-01-23)

### Initial Architecture Review

| Issue | Resolution |
|-------|------------|
| `transcribe_with_timestamps()` doesn't exist | Process pywhispercpp segments directly in kb/zoom.py |
| Phases over-separated | Merged into 2 phases (MVP + Polish) |
| Index-based selection (`kb zoom 1`) | Removed - use folder name |
| `--all` batch mode | Deferred to v2 |
| Config for zoom paths | Hardcode default, allow `--zoom-dir` CLI override |
| Error handling unclear | Skip failed files, continue with remaining |
| Decimal selection | Interactive with Alpha (default), Beta, Generic options |

### Phase 0 Deep Review

| Critical Issue | Resolution |
|----------------|------------|
| Entry points in pyproject.toml will break | Added pyproject.toml to files to modify |
| Shared `transcribe_to_kb()` would be lost | Create `kb/core.py` for shared utilities |
| `--analyze` flag flow undefined | Added --analyze flow section to plan |

| Gap | Resolution |
|-----|------------|
| Registry functions duplicated | Consolidate in `kb/core.py` |
| Paste regex assumes HH:MM:SS | Fixed regex to handle both MM:SS and HH:MM:SS |
| File source lacks discovery | Added directory selection + free-form entry |
| No `type` field in JSON | Added `type` field with values per source |
| Error handling inconsistent | Unified error handling pattern documented |
| Progress reporting inconsistent | Unified `print_status()` in core.py |

## Notes & Updates
- 2025-01-23: Task created based on legacy `meeting_worker.py` analysis
- 2025-01-23: Architecture review completed - identified missing `transcribe_with_timestamps()`, simplified approach
- 2025-01-23: Scope expanded to include CLI architecture refactor (Phase 0)
  - `kb transcribe` becomes submenu with sources: file, cap, volume, zoom, paste
  - Added paste source for Google Meet clipboard import
  - Standardized transcript format: `[MM:SS]` or `[HH:MM:SS]` (no markdown bold)
  - Breaking change to CLI structure accepted
- 2025-01-23: Phase 1 review - clarified transcription flow:
  - Zoom source manages its own WhisperCppService (doesn't use transcribe_to_kb for transcription)
  - Uses transcribe_to_kb() only for saving with transcript_text parameter (like paste source)
  - Simplified to single meeting selection (multi-select deferred)
  - Reuse select_decimal() from cli.py instead of custom options
  - Expanded audio file pattern to support .m4a, .mp3, .wav
  - Added parse_date_from_folder() function
  - Removed gc.collect() (not effective with model loaded)
- 2025-01-23: Phase 0 deep review - identified 3 critical issues, 8 gaps:
  - **Critical**: Must create `kb/core.py` for shared utilities (`transcribe_to_kb()`, registry functions)
  - **Critical**: Must update `pyproject.toml` to remove old entry points
  - **Critical**: Must define `--analyze` flag flow through dispatcher
  - Fixed paste regex to handle both `[MM:SS]` and `[HH:MM:SS]` formats (Google Meet uses MM:SS)
  - Added `type` field to JSON schema for source identification
  - Enhanced file source with directory selection + free-form entry
  - Unified error handling and progress reporting patterns
- Approach: Use whisper.cpp (not WhisperX) for consistency with rest of kb module
- This is complementary to T010 (WhisperX diarization) - T010 handles single-file speaker detection, T012 handles multi-file Zoom recordings
