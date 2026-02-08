# Task: Knowledge Base Transcript Capture System

## Task ID
T011

## Overview
Build a systematic, machine-readable knowledge base for capturing all spoken/video content (Skool classroom recordings, cohort sessions, YouTube content, raw ideas) as structured JSON. This enables LLM analysis for content strategy, summaries, and insight extraction.

## Objectives
- Create JSON-based transcript storage with decimal naming system
- Build rich CLI for metadata input (tags, categories, dates)
- Implement two capture workflows: Cap recordings (quick ideas) and Volume videos (published content)
- Add configurable LLM analysis pipeline (summaries, key points, etc.)

## Dependencies
- None (standalone scripts, use existing whisper.cpp transcription service)

## Rules Required
- None

## Resources & References
- **Architecture doc**: [architecture.md](./architecture.md) - System design, data flow, tracking mechanisms
- Destination: `~/Obsidian/zen-ai/knowledge-base/transcripts/`
- Cap recordings: `/Users/blake/Library/Application Support/so.cap.desktop.dev/recordings/`
- Volume videos: `/Volumes/BackupArchive/skool-videos/`
- Zoom recordings: `~/Documents/Zoom/` (future integration)
- Config: `~/Obsidian/zen-ai/knowledge-base/transcripts/config/`

## Scripts Created

All scripts located in `kb/` directory (reorganized from root):

| Script | Purpose |
|--------|---------|
| `kb/transcribe.py` | Core transcription to JSON with CLI args or interactive mode |
| `kb/cli.py` | Rich interactive CLI components (questionary checkboxes) |
| `kb/capture.py` | Multi-select Cap recordings for batch transcription |
| `kb/volume_sync.py` | Auto-transcribe new videos from mounted volume |
| `kb/analyze.py` | LLM analysis with interactive transcript selector |

## Phases Breakdown

### Phase 1: Config Structure & Registry
**Status**: Complete

**Objectives**:
- Create transcript directory structure at `~/Obsidian/zen-ai/knowledge-base/transcripts/`
- Create `config/registry.json` with decimal definitions and tag list
- Create `config/analysis_types/` directory with analysis type definitions (summary, key_points, guide, resources, improvements, lead_magnet)
- Define JSON schema for transcript files

**Deliverables**:
- Decimal folders: 50.00.01, 50.01.01, 50.01.02, 50.02.01, 50.03.01, 50.03.02
- registry.json with decimals, tags, and transcribed_files ledger
- 6 analysis type JSON definitions with prompts and output schemas

---

### Phase 2: kb_transcribe.py Standalone Script
**Status**: Complete

**Objectives**:
- Create standalone `kb_transcribe.py` (separate from transcribe_file.py)
- Output structured JSON to knowledge base
- Include metadata: id, decimal, title, source_files, recorded_at, duration_seconds, speakers, tags
- Compute duration automatically via ffprobe
- Network volume support: extract audio via ffmpeg (transfers ~1% of video size)
- Default to medium model for quality (configurable via --model flag)

**Usage**:
```bash
python kb/transcribe.py -d 50.01.01 -t "Title" /path/to/video.mp4
python kb/transcribe.py -i /path/to/video.mp4  # Interactive mode
python kb/transcribe.py --list-decimals
```

---

### Phase 3: Rich CLI for Metadata Input
**Status**: Complete

**Objectives**:
- Build interactive CLI using `rich` and `questionary` libraries
- Arrow key / vim navigation (↑↓ or j/k)
- Spacebar to toggle selections
- Decimal category selector (single select)
- Multi-select tag picker with "add new tag" option
- Analysis type toggles with defaults pre-selected based on decimal
- Optional recording date input

**Libraries**: rich, questionary

---

### Phase 4: Cap Recordings Capture Script
**Status**: Complete

**Objectives**:
- Script to list Cap recordings sorted by date (newest first)
- Multi-select which recordings to transcribe
- Extract and merge audio from `.cap` package segments
- Integrate with rich CLI for metadata input

**Usage**:
```bash
python kb/capture.py --list   # List recordings
python kb/capture.py          # Interactive selection and transcription
```

---

### Phase 5: Volume Auto-Transcriber with Ledger
**Status**: Complete

**Objectives**:
- Script to scan mounted volume for videos
- Maintain ledger in registry.json (transcribed_files array)
- Auto-transcribe new files without manual input
- Use filename for title (cleaned up), configurable decimal
- Support batch processing with dry-run option

**Usage**:
```bash
python kb/volume_sync.py --list       # Show status
python kb/volume_sync.py --dry-run    # Preview what would be transcribed
python kb/volume_sync.py              # Transcribe all new files
python kb/volume_sync.py -d 50.02.01  # Override decimal
```

---

### Phase 6: LLM Analysis Integration
**Status**: Complete

**Objectives**:
- Load analysis type definitions from `config/analysis_types/`
- Call Google Gemini API with configured prompts
- Enforce structured JSON output using Pydantic models
- Support analysis types: summary, key_points, guide, resources, improvements, lead_magnet
- Show progress feedback during analysis
- Make analysis toggleable at transcription time

**Technical Decisions**:
- **LLM Provider**: Google Gemini (`google-genai` SDK, NOT deprecated `google-generativeai`)
- **Model**: `gemini-2.0-flash` (stable, fast)
- **Structured Output**: Schema included in prompt with `response_mime_type='application/json'`
- **Auth**: Environment variable `GEMINI_API_KEY`

**Implementation Plan**:

1. **Create `kb_analyze.py`** - Standalone analysis module
   - Load analysis type definitions from config
   - Convert JSON schemas to Pydantic models dynamically
   - Call Gemini with transcript + prompt
   - Validate and return structured response

2. **Analysis Type Pydantic Models**:
   ```python
   class SummaryAnalysis(BaseModel):
       summary: str
       word_count: int

   class KeyPointsAnalysis(BaseModel):
       key_points: list[str]
       themes: list[str]
   ```

3. **Integration Points**:
   - `kb_transcribe.py`: Add `--analyze` flag to run analysis after transcription
   - `kb_cli.py`: Analysis type selection already exists, wire up to actual calls
   - Store results in transcript JSON's `analysis` field

4. **Error Handling**:
   - Retry with exponential backoff on rate limits (429)
   - Graceful fallback if analysis fails (don't lose transcript)

**Resources**:
- Research doc: `tasks/active/T011-knowledge-base-capture/google-genai-research.md`
- Analysis type definitions: `~/Obsidian/zen-ai/knowledge-base/transcripts/config/analysis_types/`
- Dependency: `pip install google-genai pydantic`

---

## Future Enhancements

### CLI Package for Global Access
**Status**: Complete

Created `pyproject.toml` with entry points. Install with `pip install -e .`:
```bash
kb-transcribe -i /path/to/file.mp4   # Core transcription
kb-analyze -p                         # LLM analysis
kb-capture                            # Cap recordings
kb-sync                               # Volume sync
```

### Email/Clipboard for Student-Facing Content
After LLM analysis (Phase 6), add options to:

1. **Copy to clipboard**: Prompt user to copy summary, key_points, or both
2. **Email to student**: Send analysis output via SMTP through Google Workspace (zenaitutoring.com domain)

**Student-facing analysis types**:
- summary ✓
- key_points ✓
- guide ✓
- resources ✓
- improvements ✗ (instructor-only)

**Email implementation**:
- Use SMTP with App Password (simpler than OAuth)
- Add optional `student_email` field to cohort transcript metadata
- Sender: noreply@zenaitutoring.com or blake@zenaitutoring.com

---

## Notes & Updates
- 2026-01-22: Task created from planning discussion. Decimal system and JSON schema agreed upon.
- 2026-01-22: Phases 1-3 complete. Tested full pipeline with 7.6GB video → 56MB audio extraction → JSON output.
- 2026-01-22: Updated to use questionary for checkbox-style selection (vim/arrow navigation, spacebar toggle).
- 2026-01-22: Phases 4-5 complete. Cap capture and Volume sync scripts working.
- 2026-01-22: Default model changed to "medium" for quality transcriptions.
- 2026-01-22: Phase 6 research complete. Chose Google Gemini (`google-genai` SDK) over Claude Code for simpler integration. Research doc created at `google-genai-research.md`.
- 2026-01-22: Phase 6 complete. `kb_analyze.py` with interactive transcript selector, skip-existing logic, batch mode, and structured JSON output via Gemini.
- 2026-01-22: Project reorganization. All KB scripts moved to `kb/` directory as a proper Python package. Shell scripts moved to `scripts/`. CLAUDE.md updated with KB workflow section and key rules.
- 2026-01-22: Created pyproject.toml with CLI entry points. `pip install -e .` enables `kb-transcribe`, `kb-analyze`, `kb-capture`, `kb-sync` commands globally.
