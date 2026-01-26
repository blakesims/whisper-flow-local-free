# Task: T013 - Cap Recording Auto-Clean

## 0. Task Summary
- **Task Name:** Cap Recording Auto-Clean
- **Priority:** 1
- **Number of Stories:** 4
- **Current Status:** PLANNING
- **Dependencies:** kb.sources.cap, whisper.cpp models, Gemini API
- **Rules Required:** task-documentation
- **Acceptance Criteria:**
  - [ ] `kb clean` command transcribes all segments in a .cap recording
  - [ ] Explicit trigger phrases ("delete delete", "cut cut") auto-delete segments
  - [ ] LLM suggests deletions for dead air, stumbles, duplicate takes
  - [ ] Interactive review allows quick audio preview and approve/reject
  - [ ] Deleted segments leave no trace in Cap's metadata files
  - [ ] Cap opens the cleaned recording with no awareness of deleted segments

## 1. Goal / Objective

Create a `kb clean` command that pre-processes Cap recordings before editing. Using voice commands during recording ("delete delete") and LLM analysis, automatically remove junk segments so when opened in Cap the timeline is already clean.

This is an 80/20 optimization: voice commands during recording + quick CLI review replaces manual scrubbing in the editor.

## 2. Overall Status

PLANNING - Design complete, ready for implementation.

## 3. Stories Breakdown

| Story ID | Story Name / Objective | Status | Deliverable | Link to Details |
| :--- | :--- | :--- | :--- | :--- |
| S01 | Per-segment transcription | Planned | Transcribe each segment's audio | Inline |
| S02 | Trigger phrase detection | Planned | Auto-delete on "delete delete" etc. | Inline |
| S03 | LLM analysis & suggestions | Planned | Gemini identifies dead/duplicate segments | Inline |
| S04 | Interactive review + cleanup | Planned | CLI review with audio preview, metadata cleanup | Inline |

## 4. Story Details

### S01 - Per-Segment Transcription
- **Acceptance Criteria:**
  - [ ] Iterate `content/segments/segment-*/audio-input.ogg`
  - [ ] Transcribe each with whisper.cpp (reuse existing kb transcription)
  - [ ] Store transcripts with segment index and timestamps
  - [ ] Handle missing audio files gracefully
- **Tasks/Subtasks:**
  - [ ] Create `kb/sources/cap_clean.py` module
  - [ ] Parse .cap directory structure
  - [ ] Call whisper transcription per segment
  - [ ] Return structured transcript data with segment mapping

### S02 - Trigger Phrase Detection
- **Acceptance Criteria:**
  - [ ] Configurable trigger phrases (default: "delete delete", "cut cut", "gemini delete")
  - [ ] Case-insensitive matching
  - [ ] Segments with triggers marked for auto-deletion
  - [ ] Report which segments will be auto-deleted
- **Tasks/Subtasks:**
  - [ ] Add `triggers` config option (list of phrases)
  - [ ] Scan transcript for triggers
  - [ ] Mark segments: `auto_delete: true` with `reason: "trigger: delete delete"`

### S03 - LLM Analysis & Suggestions
- **Acceptance Criteria:**
  - [ ] Send full transcript to Gemini with optional script context
  - [ ] LLM returns deletion suggestions with confidence scores
  - [ ] Identifies: dead air, filler/stumbles, duplicate takes
  - [ ] For duplicates, recommends which take to keep
  - [ ] Suggestions include brief reasoning
- **Tasks/Subtasks:**
  - [ ] Create prompt template for segment analysis
  - [ ] Support optional `--script` argument for comparison
  - [ ] Parse LLM response into structured suggestions
  - [ ] Threshold: confidence >= 0.9 could be auto-approved (configurable)

### S04 - Interactive Review + Cleanup
- **Acceptance Criteria:**
  - [ ] Show each LLM suggestion with transcript preview
  - [ ] Audio preview with single keypress
  - [ ] Keyboard-driven: p=play, d=delete, k=keep, a=accept-LLM, Enter=accept
  - [ ] For duplicates: play both, accept LLM pick or swap
  - [ ] After review: delete segment folders, renumber remaining, update metadata
  - [ ] Cap opens with clean timeline, no trace of deleted segments
- **Tasks/Subtasks:**
  - [ ] Build rich CLI review interface
  - [ ] Implement audio playback (afplay for macOS)
  - [ ] Implement segment deletion + renumbering
  - [ ] Update `recording-meta.json` with new paths
  - [ ] Delete `project-config.json` (Cap regenerates on open)
  - [ ] Summary output: "Deleted N segments, M remain"

## 5. Technical Considerations

### Cap Recording Structure (CRITICAL - must leave no trace)

```
recording.cap/
├── recording-meta.json      # MUST UPDATE: remove deleted segments, renumber paths
├── project-config.json      # DELETE: Cap regenerates fresh timeline on open
└── content/
    └── segments/
        ├── segment-0/       # Each segment folder contains:
        │   ├── display.mp4  #   - Screen recording
        │   ├── camera.mp4   #   - Camera feed (optional)
        │   ├── audio-input.ogg  # - Microphone audio (THIS IS TRANSCRIBED)
        │   └── cursor.json  #   - Cursor movement data
        ├── segment-1/
        └── ...
```

### recording-meta.json Structure

```json
{
  "segments": [
    {
      "display": { "path": "content/segments/segment-0/display.mp4", "fps": 53 },
      "camera": { "path": "content/segments/segment-0/camera.mp4", "fps": 60 },
      "mic": { "path": "content/segments/segment-0/audio-input.ogg" },
      "cursor": "content/segments/segment-0/cursor.json"
    },
    // ... more segments
  ]
}
```

### Deletion Algorithm

1. Identify segments to delete (triggers + approved LLM suggestions)
2. Delete segment folders: `rm -rf segment-N/`
3. Renumber remaining folders: if deleting segment-2, rename segment-3→segment-2, etc.
4. Update `recording-meta.json`:
   - Remove deleted entries from `segments` array
   - Update paths in remaining entries to match renamed folders
5. Delete `project-config.json` entirely (Cap creates fresh on open)
6. Verify: opening in Cap shows clean timeline with no gaps

### Audio Playback

macOS built-in:
```bash
afplay segment-0/audio-input.ogg  # Blocks until complete
```

For background/async playback options, see Open Questions.

## 6. Open Questions

### Q1: Background Audio Playback for Quick Preview
**Context:** When reviewing LLM suggestions with <90% confidence, user may want to quickly hear the segment without blocking the CLI.

**Options:**
1. **afplay with timeout** - `timeout 5 afplay file.ogg` - plays first 5 seconds
2. **afplay in background** - `afplay file.ogg &` then kill on next keypress
3. **mpv** - `mpv --no-video --really-quiet file.ogg` - more control, requires install
4. **ffplay** - `ffplay -nodisp -autoexit file.ogg` - from ffmpeg, cross-platform

**Recommendation:** Start with blocking `afplay` (simple), add `--quick` flag that plays first 3 seconds via timeout.

### Q2: Confidence Threshold for Auto-Approval
**Context:** Should high-confidence LLM suggestions be auto-approved without review?

**Options:**
1. Always require confirmation (safest)
2. Auto-approve if confidence >= 0.95 (trust the AI)
3. Configurable via `--auto-approve-threshold 0.9`

**Recommendation:** Option 3 - configurable, default to requiring confirmation.

### Q3: Handling Segments Without Audio
**Context:** Some segments may have missing or corrupt audio files.

**Options:**
1. Skip silently
2. Warn and skip
3. Treat as "keep" by default
4. Treat as "delete" (if no audio, likely a mistake)

**Recommendation:** Warn and treat as "keep" - let user decide manually.

### Q4: Duplicate Take Detection
**Context:** LLM needs to identify when segments are retakes of the same content.

**Approach:** Include timestamps and ask LLM to identify segments with similar content. For detected duplicates, ask which has better delivery (fewer filler words, clearer speech, etc.)

**Open:** Should we compare audio features (length, energy) or rely purely on transcript similarity?

### Q5: Script Comparison Mode
**Context:** When user provides a script, LLM can identify off-script segments.

**Questions:**
- How strictly to match? (Exact words vs. semantic similarity)
- Should off-script segments default to delete or keep?
- How to handle intentional ad-libs?

**Recommendation:** Default to "keep" for off-script but flag for review. User can adjust via `--strict-script` flag.

## 7. CLI Interface Design

```bash
# Basic usage
kb clean "recording.cap"

# With script for comparison
kb clean "recording.cap" --script script.md

# Custom triggers
kb clean "recording.cap" --triggers "delete delete,cut this,remove"

# Auto-approve high confidence
kb clean "recording.cap" --auto-approve 0.95

# Dry run (show what would be deleted)
kb clean "recording.cap" --dry-run

# Skip LLM analysis (only trigger phrases)
kb clean "recording.cap" --triggers-only
```

## 8. Example Session

```
$ kb clean "~/Library/.../recording.cap"

🔍 Transcribing 12 segments...
✓ Segment 0 (12.3s): "I ran an experiment. I gave ChatGPT..."
✓ Segment 1 (8.1s): "...document with 400 variables scattered..."
✓ Segment 2 (4.2s): "Um, let me just... delete delete... okay so..."
  → Auto-deleting (trigger: "delete delete")
✓ Segment 3 (15.7s): "The context window is the key limitation..."
...

🤖 Analyzing with Gemini...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Segment 5 (4.2s) — SUGGESTED: DELETE (88%)
"Uh... wait, let me check... okay so..."
Reason: Filler/hesitation, breaks flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[p]lay / [D]elete / [k]eep / [q]uit? p
♫ Playing... (4.2s)
[D]elete / [k]eep? d
✓ Marked for deletion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Segments 7 & 8 — DUPLICATE TAKES
  7 (11.2s): "So the takeaway here is that you need to..."
  8 (10.8s): "So the takeaway is you absolutely need to..."
LLM recommends: Keep 8 (cleaner delivery, no false start)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1] play 7 / [2] play 8 / [a]ccept LLM / [s]wap / [b]oth? a
✓ Deleting segment 7

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Auto-deleted (triggers): 1
User-approved deletions: 2
Total to delete: 3 of 12 segments

Proceed? [Y/n] y

🗑️  Deleting segment folders...
📁 Renumbering: segment-3 → segment-2, segment-4 → segment-3...
📝 Updating recording-meta.json...
🧹 Removing project-config.json...

✓ Done. 9 segments remain.
  Open in Cap: the timeline is clean.
```

## 9. Relevant Files

| Purpose | Location |
|---------|----------|
| New clean module | `kb/sources/cap_clean.py` (to create) |
| Existing cap source | `kb/sources/cap.py` (reference for .cap handling) |
| Whisper transcription | `kb/core.py` (reuse `transcribe_audio()`) |
| Gemini integration | `kb/analyze.py` (reuse LLM patterns) |
| CLI patterns | `kb/__main__.py`, `kb/cli.py` (rich + questionary) |
