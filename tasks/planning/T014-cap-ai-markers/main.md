# Task: Cap AI Markers for Intra-Segment Editing

## Task ID
T014

## Overview
Extend the `kb clean` AI analysis to output markers for suggested edit points within segments. These markers would be stored as JSON metadata alongside Cap recordings, allowing the (forked) Cap editor to display and navigate to AI-suggested cut points using vim-style keybindings.

## Context
- User has forked Cap and added custom features: in/out markers (I/O keys), generic markers (M key), segment navigation (W/B keys)
- Current `kb clean` identifies segments to delete but doesn't suggest intra-segment cuts
- Whisper provides centisecond-precision timestamps that can pinpoint edit points within segments
- Goal: AI suggests "cut first 5 seconds" or "trim at 0:23" and these become navigable markers in Cap

## Objectives
- AI analyzes transcripts to identify intra-segment cut points (false starts, restarts, filler)
- Output markers as JSON metadata (backwards-compatible with Cap)
- Cap integration to read markers and enable navigation (vim-style, e.g. `]a` / `[a` for next/prev AI marker)

## Dependencies
- T013 (Cap Recording Auto-Clean) - builds on the LLM analysis infrastructure
- Forked Cap codebase (separate repo)

## Rules Required
- None

## Resources & References
- `kb/sources/cap_clean.py` - existing cleanup analysis
- `kb/analyze.py` - Gemini LLM integration
- Whisper timestamp format: `seg.t0` in centiseconds (100ths of second)
- Cap recording structure: `recording-meta.json`, `content/segments/segment-N/`

## Phases Breakdown

### Phase 1: Marker Schema Design
**Status**: Not Started

**Objectives**:
- Define JSON schema for AI markers (timestamp, type, confidence, reason)
- Determine storage location (new file `ai-markers.json` or extend `recording-meta.json`)
- Ensure backwards compatibility (Cap should ignore unknown fields)

**Example schema**:
```json
{
  "ai_markers": [
    {
      "segment": 2,
      "timestamp_ms": 5200,
      "type": "trim_start",
      "confidence": 0.85,
      "reason": "False start - speaker restarts sentence"
    }
  ]
}
```

### Phase 2: LLM Prompt Enhancement
**Status**: Not Started

**Objectives**:
- Extend `cap_clean` analysis prompt to identify intra-segment cut points
- Return marker suggestions with timestamps derived from whisper segments
- Types to detect: `trim_start`, `trim_end`, `cut_section`, `possible_edit`

**Dependencies**:
- Phase 1 (schema)

### Phase 3: Marker Output in kb clean
**Status**: Not Started

**Objectives**:
- Write markers to JSON file after cleanup analysis
- Display marker suggestions in CLI review (optional: play specific timestamp)
- Preserve markers even if user skips actual deletion

### Phase 4: Cap Integration (Separate Repo)
**Status**: Not Started

**Objectives**:
- Load AI markers from JSON in Cap editor
- Display markers on timeline (distinct color/icon from manual markers)
- Implement navigation keybindings (`]a`/`[a` or similar vim-style)
- Optional: jump to marker and auto-play 2-3 seconds of context

## Open Questions
- Should markers survive after user edits, or regenerate on re-analysis?
- What vim keybindings feel natural? (`]a`/`[a`, `ga`/`gA`, or custom?)
- Should AI markers be editable/deletable in Cap, or read-only?

## Notes & Updates
- 2025-01-29: Task created from discussion about extending kb clean with intra-segment cut suggestions
