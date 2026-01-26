# Task: T013 - Cap Recording Auto-Clean

## 0. Task Summary
- **Task Name:** Cap Recording Auto-Clean
- **Priority:** 1
- **Number of Stories:** 5
- **Current Status:** PLANNING
- **Dependencies:** kb.sources.cap, whisper.cpp models, Gemini API
- **Rules Required:** task-documentation
- **Acceptance Criteria:**
  - [ ] `kb clean` command transcribes all segments in a .cap recording
  - [ ] Explicit trigger phrases ("delete delete", "cut cut") auto-delete segments
  - [ ] LLM suggests deletions for dead air, stumbles, duplicate takes
  - [ ] Interactive review allows quick audio preview and approve/reject
  - [ ] Soft-deleted segments renamed to `_deleted_segment-N/` (recoverable)
  - [ ] Cap opens the cleaned recording with no awareness of deleted segments
  - [ ] `kb clean --restore` can undo soft-deletes

## 1. Goal / Objective

Create a `kb clean` command that pre-processes Cap recordings before editing. Using voice commands during recording ("delete delete") and LLM analysis, automatically remove junk segments so when opened in Cap the timeline is already clean.

This is an 80/20 optimization: voice commands during recording + quick CLI review replaces manual scrubbing in the editor.

## 2. Overall Status

PLANNING - Design complete, ready for implementation.

## 3. Stories Breakdown

| Story ID | Story Name / Objective | Status | Deliverable |
| :--- | :--- | :--- | :--- |
| S00 | Core transcription refactor | Planned | Extract `transcribe_audio()` from core.py |
| S01 | Per-segment transcription | Planned | Parallel transcription with progress |
| S02 | Trigger phrase detection | Planned | Auto-mark segments with triggers |
| S03 | LLM analysis & suggestions | Planned | Gemini identifies problematic segments |
| S04 | Interactive review + soft-delete | Planned | CLI review, audio preview, soft-delete |

## 4. Story Details

### S00 - Core Transcription Refactor (DRY)

**Rationale:** `transcribe_to_kb()` in `kb/core.py` combines transcription + KB saving. We need a lower-level function for segment-only transcription.

**Acceptance Criteria:**
- [ ] Extract `transcribe_audio(file_path, model_name) -> dict` from core.py
- [ ] Returns `{text, segments, duration}` without KB side effects
- [ ] `transcribe_to_kb()` refactored to use `transcribe_audio()` internally
- [ ] No breaking changes to existing sources

**Implementation:**
```python
# kb/core.py - NEW FUNCTION

def transcribe_audio(
    file_path: str,
    model_name: str = "medium",
    progress_callback: callable = None,
) -> dict:
    """
    Transcribe audio file without saving to KB.

    Returns:
        {
            "text": str,           # Full transcript text
            "segments": list,      # [{t0, t1, text}, ...]
            "duration": int,       # Duration in seconds
            "formatted": str,      # "[MM:SS] text" formatted
        }
    """
    # Extract transcription logic from transcribe_to_kb (lines 299-343)
    ...

def transcribe_to_kb(...):
    # Refactor to use transcribe_audio() internally
    result = transcribe_audio(file_path, model_name, progress_callback)
    transcript_text = result["formatted"]
    duration = result["duration"]
    # ... rest of KB saving logic unchanged
```

**Files Changed:**
- `kb/core.py` - Add `transcribe_audio()`, refactor `transcribe_to_kb()`

---

### S01 - Per-Segment Transcription

**Acceptance Criteria:**
- [x] Iterate `content/segments/segment-*/audio-input.ogg`
- [x] Sequential transcription with single shared model (thread-safety requirement)
- [x] Store transcripts with segment index, duration, status
- [x] Handle missing audio files gracefully (warn + skip)
- [x] Progress display with Rich

**Note:** Originally planned parallel transcription with ThreadPoolExecutor, but
whisper.cpp model is NOT thread-safe. Sequential with single shared model instance
is more efficient than loading 3 separate models (~4.5GB RAM vs ~1.5GB).

**Implementation:**
```python
# kb/sources/cap_clean.py

from kb.core import get_audio_duration, format_timestamp, LocalFileCopy
from kb.sources.cap import get_cap_recordings, CAP_RECORDINGS_DIR

def transcribe_segments(cap_path: Path, model_name: str = "medium") -> list[dict]:
    """
    Transcribe all segments in a Cap recording.

    Returns:
        [{
            "index": 0,
            "path": "content/segments/segment-0/audio-input.ogg",
            "duration": 12.3,
            "text": "I ran an experiment...",
            "segments": [...],  # whisper segments with timestamps
        }, ...]
    """
    meta = load_recording_meta(cap_path)
    segments = []
    audio_files = []

    for i, seg in enumerate(meta["segments"]):
        audio_path = cap_path / seg["mic"]["path"]
        if audio_path.exists():
            audio_files.append((i, str(audio_path)))
        else:
            console.print(f"[yellow]⚠ Segment {i}: audio missing, skipping[/yellow]")

    # Parallel transcription (3 concurrent)
    results = {}
    with Progress(...) as progress:
        task = progress.add_task("Transcribing...", total=len(audio_files))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(transcribe_audio, path, model_name): idx
                for idx, path in audio_files
            }
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()
                progress.advance(task)

    # Build ordered result
    for i, path in audio_files:
        r = results[i]
        segments.append({
            "index": i,
            "path": path,
            "duration": r["duration"],
            "text": r["text"],
            "formatted": r["formatted"],
        })

    return segments
```

**Reuses:**
- `get_cap_recordings()` from `kb/sources/cap.py`
- `transcribe_audio()` from `kb/core.py` (S00)
- `get_audio_duration()` from `kb/core.py`

**Files Changed:**
- `kb/sources/cap_clean.py` (new)

---

### S02 - Trigger Phrase Detection

**Acceptance Criteria:**
- [ ] Default triggers: `["delete delete", "cut cut", "delete this"]`
- [ ] Case-insensitive matching
- [ ] Segments with triggers marked `auto_delete: True`
- [ ] Report which segments will be auto-deleted

**Implementation:**
```python
# kb/sources/cap_clean.py

DEFAULT_TRIGGERS = ["delete delete", "cut cut", "delete this"]

def detect_triggers(segments: list[dict], triggers: list[str] = None) -> list[dict]:
    """
    Scan transcripts for trigger phrases.

    Returns segments with added fields:
        auto_delete: bool
        trigger_match: str | None
    """
    triggers = triggers or DEFAULT_TRIGGERS
    triggers_lower = [t.lower() for t in triggers]

    for seg in segments:
        text_lower = seg["text"].lower()
        seg["auto_delete"] = False
        seg["trigger_match"] = None

        for trigger in triggers_lower:
            if trigger in text_lower:
                seg["auto_delete"] = True
                seg["trigger_match"] = trigger
                break

    return segments
```

**Files Changed:**
- `kb/sources/cap_clean.py`

---

### S03 - LLM Analysis & Suggestions

**Acceptance Criteria:**
- [ ] Send segment list to Gemini with transcript text
- [ ] LLM returns deletion suggestions with confidence scores
- [ ] Identifies: dead air, filler/stumbles, duplicate takes
- [ ] For duplicates, recommends which take to keep
- [ ] Create `config/analysis_types/cap_clean.json` for prompt

**Implementation:**
```python
# kb/sources/cap_clean.py

from kb.analyze import analyze_transcript

def analyze_segments_for_cleanup(segments: list[dict], script: str = None) -> dict:
    """
    Use Gemini to analyze segments for cleanup suggestions.

    Returns:
        {
            "suggestions": [
                {
                    "segment_index": 3,
                    "action": "delete",
                    "confidence": 0.92,
                    "reason": "dead_air",
                    "explanation": "Segment contains only silence/filler"
                },
                {
                    "segment_indices": [5, 6],
                    "action": "duplicate",
                    "confidence": 0.88,
                    "keep_index": 6,
                    "explanation": "Segment 6 has cleaner delivery"
                }
            ]
        }
    """
    # Build context for LLM
    transcript_context = "\n".join([
        f"Segment {s['index']} ({s['duration']:.1f}s): {s['text']}"
        for s in segments
    ])

    # Use existing analyze_transcript pattern
    result = analyze_transcript(
        transcript_text=transcript_context,
        analysis_type="cap_clean",
        title="Cap Recording Cleanup Analysis",
    )

    return result
```

**New File:** `config/analysis_types/cap_clean.json`
```json
{
  "name": "cap_clean",
  "description": "Analyze Cap recording segments for cleanup",
  "prompt": "You are analyzing segments from a screen recording for cleanup...",
  "output_schema": {
    "type": "object",
    "properties": {
      "suggestions": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "segment_index": {"type": "integer"},
            "segment_indices": {"type": "array", "items": {"type": "integer"}},
            "action": {"enum": ["delete", "duplicate"]},
            "confidence": {"type": "number"},
            "keep_index": {"type": "integer"},
            "reason": {"enum": ["dead_air", "filler", "stumble", "duplicate", "off_script"]},
            "explanation": {"type": "string"}
          }
        }
      }
    }
  }
}
```

**Reuses:**
- `analyze_transcript()` from `kb/analyze.py`

**Files Changed:**
- `kb/sources/cap_clean.py`
- `config/analysis_types/cap_clean.json` (new)

---

### S04 - Interactive Review + Soft-Delete

**Acceptance Criteria:**
- [ ] Check if Cap is running with recording open → warn user
- [ ] Show each LLM suggestion with transcript preview
- [ ] Audio preview with `p` (afplay, blocking)
- [ ] Keyboard-driven: `p`=play, `d`=delete, `k`=keep
- [ ] For duplicates: `1`/`2` to play, `a`=accept LLM, `s`=swap
- [ ] Soft-delete: rename `segment-N` → `_deleted_segment-N`
- [ ] Renumber remaining segments sequentially
- [ ] Update `recording-meta.json` with new paths
- [ ] Delete `project-config.json` (Cap regenerates)
- [ ] Save audit log to `_clean_audit.json`
- [ ] `--restore` command to undo soft-deletes

**Implementation - Core Functions:**
```python
# kb/sources/cap_clean.py

import subprocess

def is_cap_running(cap_path: Path) -> bool:
    """Check if Cap app has this recording open."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Cap"],
            capture_output=True, text=True
        )
        # Could also check lsof for file locks
        return result.returncode == 0
    except Exception:
        return False

def play_audio(audio_path: str, timeout: int = None):
    """Play audio file using afplay (blocking)."""
    cmd = ["afplay", audio_path]
    if timeout:
        cmd = ["timeout", str(timeout)] + cmd
    subprocess.run(cmd)

def soft_delete_segments(cap_path: Path, indices_to_delete: list[int]):
    """
    Soft-delete segments by renaming folders.

    1. Rename segment-N → _deleted_segment-N for each deleted index
    2. Renumber remaining segments sequentially
    3. Update recording-meta.json
    4. Delete project-config.json
    """
    segments_dir = cap_path / "content" / "segments"
    meta_path = cap_path / "recording-meta.json"
    config_path = cap_path / "project-config.json"

    # Load meta
    with open(meta_path) as f:
        meta = json.load(f)

    # Step 1: Soft-delete (rename to _deleted_)
    for idx in indices_to_delete:
        src = segments_dir / f"segment-{idx}"
        dst = segments_dir / f"_deleted_segment-{idx}"
        if src.exists():
            src.rename(dst)

    # Step 2: Identify remaining segments and renumber
    remaining = []
    for i, seg in enumerate(meta["segments"]):
        if i not in indices_to_delete:
            remaining.append((i, seg))

    # Renumber folders
    for new_idx, (old_idx, seg) in enumerate(remaining):
        if new_idx != old_idx:
            src = segments_dir / f"segment-{old_idx}"
            dst = segments_dir / f"segment-{new_idx}"
            if src.exists():
                src.rename(dst)

    # Step 3: Update meta.json
    new_segments = []
    for new_idx, (old_idx, seg) in enumerate(remaining):
        # Update paths in segment
        new_seg = update_segment_paths(seg, new_idx)
        new_segments.append(new_seg)

    meta["segments"] = new_segments

    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    # Step 4: Delete project-config.json (Cap regenerates)
    if config_path.exists():
        config_path.unlink()

def update_segment_paths(seg: dict, new_index: int) -> dict:
    """Update all paths in a segment to reflect new index."""
    new_seg = {}
    for key, value in seg.items():
        if isinstance(value, dict) and "path" in value:
            old_path = value["path"]
            new_path = old_path.replace(
                f"segment-{old_path.split('segment-')[1].split('/')[0]}",
                f"segment-{new_index}"
            )
            new_seg[key] = {**value, "path": new_path}
        elif key == "cursor":
            # cursor is just a string path
            new_seg[key] = value.replace(
                f"segment-{value.split('segment-')[1].split('/')[0]}",
                f"segment-{new_index}"
            )
        else:
            new_seg[key] = value
    return new_seg

def restore_deleted_segments(cap_path: Path):
    """Restore soft-deleted segments (undo cleanup)."""
    segments_dir = cap_path / "content" / "segments"

    # Find all _deleted_ folders
    deleted = sorted(segments_dir.glob("_deleted_segment-*"))
    if not deleted:
        console.print("[yellow]No deleted segments to restore.[/yellow]")
        return

    # This is complex: need to re-integrate and renumber
    # For MVP: just rename back and warn user to re-run Cap
    for folder in deleted:
        original_name = folder.name.replace("_deleted_", "")
        # Can't just rename - indices may conflict
        # Need full rebuild of meta.json

    console.print("[yellow]Restore requires rebuilding meta.json - not yet implemented[/yellow]")

def save_audit_log(cap_path: Path, audit_data: dict):
    """Save cleanup audit log."""
    audit_path = cap_path / "_clean_audit.json"
    audit_data["cleaned_at"] = datetime.now().isoformat()

    with open(audit_path, 'w') as f:
        json.dump(audit_data, f, indent=2)
```

**Implementation - Interactive Review UI:**
```python
# kb/sources/cap_clean.py

def run_interactive_review(segments: list[dict], suggestions: list[dict]) -> list[int]:
    """
    Interactive CLI review of LLM suggestions.

    Returns: list of segment indices to delete
    """
    to_delete = set()

    # First: auto-deletes from triggers
    for seg in segments:
        if seg.get("auto_delete"):
            to_delete.add(seg["index"])
            console.print(f"[dim]Auto-delete segment {seg['index']}: trigger '{seg['trigger_match']}'[/dim]")

    # Then: LLM suggestions
    for suggestion in suggestions:
        if suggestion["action"] == "delete":
            idx = suggestion["segment_index"]
            seg = segments[idx]

            console.print(f"\n{'━' * 60}")
            console.print(f"[bold]Segment {idx}[/bold] ({seg['duration']:.1f}s) — DELETE? ({suggestion['confidence']*100:.0f}%)")
            console.print(Panel(seg["text"][:200], border_style="dim"))
            console.print(f"[dim]Reason: {suggestion['explanation']}[/dim]")

            choice = questionary.select(
                "",
                choices=[
                    questionary.Choice("play", "p"),
                    questionary.Choice("delete", "d"),
                    questionary.Choice("keep", "k"),
                ],
                style=custom_style
            ).ask()

            if choice == "p":
                play_audio(seg["path"])
                # Ask again after playing
                choice = questionary.select(
                    "",
                    choices=[
                        questionary.Choice("delete", "d"),
                        questionary.Choice("keep", "k"),
                    ],
                    style=custom_style
                ).ask()

            if choice == "d":
                to_delete.add(idx)
                console.print("[green]✓ Marked for deletion[/green]")

        elif suggestion["action"] == "duplicate":
            indices = suggestion["segment_indices"]
            keep_idx = suggestion["keep_index"]
            delete_idx = [i for i in indices if i != keep_idx][0]

            console.print(f"\n{'━' * 60}")
            console.print(f"[bold]DUPLICATE TAKES[/bold]: Segments {indices[0]} & {indices[1]}")

            for idx in indices:
                seg = segments[idx]
                marker = " [LLM recommends KEEP]" if idx == keep_idx else ""
                console.print(f"\nSegment {idx} ({seg['duration']:.1f}s){marker}:")
                console.print(Panel(seg["text"][:150], border_style="dim"))

            console.print(f"[dim]{suggestion['explanation']}[/dim]")

            choice = questionary.select(
                "",
                choices=[
                    questionary.Choice(f"play {indices[0]}", "1"),
                    questionary.Choice(f"play {indices[1]}", "2"),
                    questionary.Choice("accept LLM", "a"),
                    questionary.Choice("swap (keep other)", "s"),
                    questionary.Choice("keep both", "b"),
                ],
                style=custom_style
            ).ask()

            if choice == "1":
                play_audio(segments[indices[0]]["path"])
            elif choice == "2":
                play_audio(segments[indices[1]]["path"])

            if choice in ("1", "2"):
                choice = questionary.select(
                    "",
                    choices=[
                        questionary.Choice("accept LLM", "a"),
                        questionary.Choice("swap", "s"),
                        questionary.Choice("keep both", "b"),
                    ],
                    style=custom_style
                ).ask()

            if choice == "a":
                to_delete.add(delete_idx)
                console.print(f"[green]✓ Deleting segment {delete_idx}, keeping {keep_idx}[/green]")
            elif choice == "s":
                to_delete.add(keep_idx)
                console.print(f"[green]✓ Deleting segment {keep_idx}, keeping {delete_idx}[/green]")
            # "b" keeps both - do nothing

    return sorted(to_delete)
```

**Reuses:**
- `custom_style` from `kb/cli.py`
- Rich Panel, Table, Progress patterns

**Files Changed:**
- `kb/sources/cap_clean.py`
- `kb/__main__.py` (add `clean` command to CLI)

---

## 5. CLI Interface

### Main Command
```bash
# Interactive (select from list)
kb clean

# Direct path
kb clean "recording.cap"
kb clean ~/Library/.../recording.cap

# Options
kb clean --triggers "delete delete,cut cut"    # Custom triggers
kb clean --triggers-only                        # Skip LLM analysis
kb clean --dry-run                              # Preview only, no changes
kb clean --script notes.md                      # Compare to script (future)
kb clean --auto-approve 0.95                    # Auto-approve high confidence (future)

# Recovery
kb clean --restore "recording.cap"              # Undo soft-deletes
kb clean --purge "recording.cap"                # Permanently delete _deleted_* (future)
```

### CLI Entry Point
```python
# kb/__main__.py - add to existing CLI

@app.command()
def clean(
    recording: str = typer.Argument(None, help="Path to .cap recording"),
    triggers: str = typer.Option(None, help="Comma-separated trigger phrases"),
    triggers_only: bool = typer.Option(False, "--triggers-only", help="Skip LLM analysis"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    restore: bool = typer.Option(False, "--restore", help="Restore deleted segments"),
):
    """Clean up Cap recording by removing junk segments."""
    from kb.sources.cap_clean import run_clean

    trigger_list = triggers.split(",") if triggers else None
    run_clean(
        recording_path=recording,
        triggers=trigger_list,
        triggers_only=triggers_only,
        dry_run=dry_run,
        restore=restore,
    )
```

---

## 6. User Flow (Concrete)

### Phase 1: Selection & Safety
```
$ kb clean

╭─────────────────────────────────────────────────────╮
│  Cap Recording Cleanup                              │
╰─────────────────────────────────────────────────────╯

Cap Recordings (newest first)
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ #  ┃ Name                            ┃ Duration  ┃ Segments ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1  │ Cap 2026-01-26 at 17.15         │ 3m 42s    │ 6        │
│ 2  │ Cap 2026-01-25 at 15.10         │ 8m 15s    │ 12       │
│ 3  │ Cap 2026-01-24 at 16.48         │ 5m 22s    │ 9        │
└────┴─────────────────────────────────┴───────────┴──────────┘

Select recording: 3

⚠️  Cap appears to be running. Close it before cleaning.

Close Cap and press Enter to continue, or Ctrl+C to abort.
[Press Enter]

✓ Proceeding with cleanup...
```

### Phase 2: Transcription
```
🔍 Transcribing 9 segments (3 parallel)...

  [████████████████████████████████████████] 9/9 complete

Segment Transcripts:
┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Segment  ┃ Duration┃ Preview                                             ┃
┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 0        │ 12.3s   │ "I ran an experiment. I gave ChatGPT..."            │
│ 1        │ 8.1s    │ "...document with 400 variables scattered..."       │
│ 2 ⚡     │ 4.2s    │ "Um, let me just... delete delete..."               │
│ 3        │ 2.1s    │ "[silence]"                                         │
│ 4        │ 15.7s   │ "The context window is the key limitation..."       │
│ 5        │ 11.2s   │ "So the takeaway here is that you need to..."       │
│ 6        │ 10.8s   │ "So the takeaway is you absolutely need to..."      │
│ 7 ⚡     │ 3.5s    │ "Uh... wait, where was I... delete delete"          │
│ 8        │ 18.4s   │ "Anyway, the main point is that context..."         │
└──────────┴─────────┴─────────────────────────────────────────────────────┘
⚡ = trigger phrase detected

Auto-deletions (2 segments):
  • Segment 2: "delete delete"
  • Segment 7: "delete delete"

Continue to LLM analysis? [Y/n]: y
```

### Phase 3: LLM Analysis
```
🤖 Analyzing with Gemini...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Suggestion 1/2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Segment 3 (2.1s) — DELETE? (92%)
╭─────────────────────────────────────────────────────────────────────────╮
│ "[silence]"                                                             │
╰─────────────────────────────────────────────────────────────────────────╯
Reason: Dead air, no speech content

  [p] play   [d] delete   [k] keep
> d

✓ Marked for deletion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Suggestion 2/2 — DUPLICATE TAKES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Segments 5 & 6 appear to be retakes

Segment 5 (11.2s):
╭─────────────────────────────────────────────────────────────────────────╮
│ "So the takeaway here is that you need to... uh... structure your..."   │
╰─────────────────────────────────────────────────────────────────────────╯

Segment 6 (10.8s) [LLM: KEEP]:
╭─────────────────────────────────────────────────────────────────────────╮
│ "So the takeaway is you absolutely need to structure your prompts..."   │
╰─────────────────────────────────────────────────────────────────────────╯

LLM: Keep 6 (cleaner delivery, no hesitation)

  [1] play 5   [2] play 6   [a] accept LLM   [s] swap   [b] both
> a

✓ Deleting segment 5, keeping segment 6
```

### Phase 4: Confirmation & Execution
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To DELETE (soft-delete, recoverable):
  • Segment 2 — trigger: "delete delete"
  • Segment 3 — dead air (LLM 92%)
  • Segment 5 — duplicate of 6 (LLM 88%)
  • Segment 7 — trigger: "delete delete"

To KEEP: 0, 1, 4, 6, 8

Result: 9 → 5 segments

Proceed? [Y/n]: y

🗑️  Soft-deleting segments...
   segment-2 → _deleted_segment-2
   segment-3 → _deleted_segment-3
   segment-5 → _deleted_segment-5
   segment-7 → _deleted_segment-7

📁 Renumbering remaining segments...
   segment-4 → segment-2
   segment-6 → segment-3
   segment-8 → segment-4

📝 Updating recording-meta.json...
🧹 Removing project-config.json...
💾 Saving audit log to _clean_audit.json...

✓ Done! 5 segments remain.
  Open in Cap to see clean timeline.

  To undo: kb clean --restore "Cap 2026-01-24..."
```

---

## 7. File Structure After Cleanup

```
recording.cap/
├── recording-meta.json          # Updated: only 5 segments
├── _clean_audit.json            # NEW: audit log
├── content/
│   └── segments/
│       ├── segment-0/           # Original segment-0 (unchanged)
│       ├── segment-1/           # Original segment-1 (unchanged)
│       ├── segment-2/           # Was segment-4
│       ├── segment-3/           # Was segment-6
│       ├── segment-4/           # Was segment-8
│       ├── _deleted_segment-2/  # Soft-deleted
│       ├── _deleted_segment-3/  # Soft-deleted
│       ├── _deleted_segment-5/  # Soft-deleted
│       └── _deleted_segment-7/  # Soft-deleted
└── output/
```

---

## 8. Audit Log Structure

```json
{
  "cleaned_at": "2026-01-26T18:30:00Z",
  "original_segment_count": 9,
  "remaining_segment_count": 5,
  "triggers_used": ["delete delete"],
  "llm_model": "gemini-2.0-flash",
  "deleted_segments": [
    {
      "original_index": 2,
      "reason": "trigger",
      "trigger": "delete delete",
      "duration": 4.2,
      "transcript": "Um, let me just... delete delete... okay so..."
    },
    {
      "original_index": 3,
      "reason": "llm_suggestion",
      "llm_confidence": 0.92,
      "llm_category": "dead_air",
      "duration": 2.1,
      "transcript": "[silence]"
    },
    {
      "original_index": 5,
      "reason": "llm_suggestion",
      "llm_confidence": 0.88,
      "llm_category": "duplicate",
      "kept_instead": 6,
      "duration": 11.2,
      "transcript": "So the takeaway here is that you need to..."
    },
    {
      "original_index": 7,
      "reason": "trigger",
      "trigger": "delete delete",
      "duration": 3.5,
      "transcript": "Uh... wait, where was I... delete delete"
    }
  ],
  "kept_segments": [
    {"original_index": 0, "new_index": 0},
    {"original_index": 1, "new_index": 1},
    {"original_index": 4, "new_index": 2},
    {"original_index": 6, "new_index": 3},
    {"original_index": 8, "new_index": 4}
  ]
}
```

---

## 9. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `kb/core.py` | Modify | Extract `transcribe_audio()` function |
| `kb/sources/cap_clean.py` | Create | Main cleanup module |
| `kb/__main__.py` | Modify | Add `kb clean` command |
| `config/analysis_types/cap_clean.json` | Create | LLM prompt for segment analysis |

---

## 10. Implementation Order

1. **S00** - Refactor core.py (extract transcribe_audio)
2. **S01** - Per-segment transcription with parallel execution
3. **S02** - Trigger detection (quick win, no LLM needed)
4. **S03** - LLM analysis integration
5. **S04** - Interactive review + soft-delete execution

Each story is independently testable. S01+S02 can work without LLM (--triggers-only mode).
