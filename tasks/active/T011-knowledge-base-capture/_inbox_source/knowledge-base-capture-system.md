# Knowledge Base Transcript Capture System

## Problem
Need a systematic, machine-readable way to capture all spoken/video content (Skool classroom recordings, cohort sessions, YouTube content, raw ideas) into a structured JSON knowledge base for later LLM analysis and content strategy generation.

## Requirements

### Storage Structure
- JSON format for all transcripts (not markdown)
- Decimal naming system: `50.01.01-YYMMDD-<title>.json`
- Registry for tags and decimal definitions
- Analysis type definitions with prompts for LLM processing

### Decimal Categories (50.xx.xx)
- 50.00.01 - Raw captures / drafts (Cap recordings)
- 50.01.01 - Skool classroom content
- 50.01.02 - Skool weekly Q&A (future, needs diarization)
- 50.02.01 - YouTube published
- 50.03.01 - Alpha cohort sessions
- 50.03.02 - Beta cohort sessions

### Capture Sources
1. **Cap recordings** - Quick idea capture from local `.cap` packages
   - Location: `/Users/blake/Library/Application Support/so.cap.desktop.dev/recordings/`
   - Audio: `content/segments/segment-N/audio-input.ogg`

2. **Volume videos** - Published content on mounted drive
   - Location: `/Volumes/BackupArchive/skool-videos/`
   - Extract audio via ffmpeg (already implemented)

### JSON Schema
```json
{
  "id": "50.01.01-260116-creating-tasks-executing",
  "decimal": "50.01.01",
  "title": "Creating Tasks and Executing",
  "source_files": ["..."],
  "recorded_at": "2026-01-16",
  "duration_seconds": 1847,
  "speakers": ["Blake Sims"],
  "tags": ["claude-code", "task-management"],
  "transcript": "...",
  "analysis": {
    "summary": "...",
    "key_points": ["..."]
  }
}
```

### Rich CLI Features
- Multi-select tag input with ability to add new tags
- Decimal category selection
- Optional recording date input
- Toggle LLM analysis types (with defaults pre-selected based on decimal)
- Progress feedback for LLM analysis

### LLM Analysis (Phase 6)
- Configurable analysis types per decimal category
- Types: summary, key_points, guide, resources, improvements, lead_magnet
- Each type has its own prompt and output schema
- Option to use Google Gemini or Claude Code

## Destination
`~/Obsidian/zen-ai/knowledge-base/transcripts/`
