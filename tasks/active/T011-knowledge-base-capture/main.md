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
- None (builds on existing transcribe_file.py)

## Rules Required
- None

## Resources & References
- Existing script: `transcribe_file.py` (already handles ffmpeg audio extraction)
- Destination: `~/Obsidian/zen-ai/knowledge-base/transcripts/`
- Cap recordings: `/Users/blake/Library/Application Support/so.cap.desktop.dev/recordings/`
- Volume videos: `/Volumes/BackupArchive/skool-videos/`

## Phases Breakdown

### Phase 1: Config Structure & Registry
**Status**: Complete

**Objectives**:
- Create transcript directory structure at `~/Obsidian/zen-ai/knowledge-base/transcripts/`
- Create `config/registry.json` with decimal definitions and tag list
- Create `config/analysis_types/` directory with initial analysis type definitions
- Define JSON schema for transcript files

**Estimated Time**: 1-2 hours

**Resources Needed**:
- JSON schema definition from planning discussion

**Dependencies**:
- None

---

### Phase 2: kb_transcribe.py Standalone Script
**Status**: Complete

**Objectives**:
- Modify `transcribe_file.py` to output JSON instead of plain text
- Include metadata: id, decimal, title, source_files, recorded_at, duration_seconds, speakers, tags
- Compute duration automatically from audio
- Support both single and multi-speaker transcript formats

**Estimated Time**: 2-3 hours

**Resources Needed**:
- JSON schema from Phase 1

**Dependencies**:
- T011#P1

---

### Phase 3: Rich CLI for Metadata Input
**Status**: Complete

**Objectives**:
- Build rich text CLI using `rich` library for interactive metadata input
- Multi-select tag picker with "add new tag" option
- Decimal category selector (loads from registry.json)
- Optional recording date input
- Analysis type toggles (defaults pre-selected based on decimal category)
- Progress feedback during LLM analysis

**Estimated Time**: 3-4 hours

**Resources Needed**:
- `rich` Python library
- registry.json from Phase 1

**Dependencies**:
- T011#P1
- T011#P2

---

### Phase 4: Cap Recordings Capture Script
**Status**: Complete

**Objectives**:
- Script to list Cap recordings sorted by date (newest first)
- Multi-select which recordings to transcribe
- Extract and merge audio from `.cap` package segments
- Integrate with rich CLI for metadata input
- Output JSON transcripts to knowledge base

**Estimated Time**: 2-3 hours

**Resources Needed**:
- Cap package structure: `content/segments/segment-N/audio-input.ogg`

**Dependencies**:
- T011#P2
- T011#P3

---

### Phase 5: Volume Auto-Transcriber with Ledger
**Status**: Complete

**Objectives**:
- Script to scan `/Volumes/BackupArchive/skool-videos/` for videos
- Maintain ledger of already-transcribed files (in registry.json or separate file)
- Auto-transcribe new files without manual input
- Use filename for title, derive decimal from config defaults
- Support batch processing

**Estimated Time**: 2-3 hours

**Resources Needed**:
- Ledger storage decision

**Dependencies**:
- T011#P2

---

### Phase 6: LLM Analysis Integration
**Status**: Not Started

**Objectives**:
- Load analysis type definitions from `config/analysis_types/`
- Call LLM (Google Gemini or Claude Code) with configured prompts
- Enforce structured output matching analysis type schema
- Support analysis types: summary, key_points, guide, resources, improvements, lead_magnet
- Show progress feedback during analysis
- Make analysis toggleable at transcription time

**Estimated Time**: 4-6 hours

**Resources Needed**:
- Google Gemini API (google-genai Python module) OR Claude Code integration
- Analysis type prompt definitions

**Dependencies**:
- T011#P1
- T011#P2
- T011#P3

---

## Notes & Updates
- 2026-01-22: Task created from planning discussion. ffmpeg audio extraction already implemented in transcribe_file.py. Decimal system and JSON schema agreed upon.
