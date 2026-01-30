# Task: KB Serve - Action Queue Dashboard & Automation

## Task ID
T015

## Overview
Build a web-based dashboard (`kb serve`) and automation system for the Knowledge Base workflow. The dashboard serves as an **action queue** (not a browsing tool) - surfacing outputs ready for the user to copy/share (Skool posts, LinkedIn posts, student guides, etc.). Includes automated transcription/analysis via file inbox and compound analysis types.

## Core Concept: Two-Inbox Model

```
┌─────────────────────────────────────────────────────────────────────┐
│  INBOX 1 (Files)              INBOX 2 (Actions)                     │
│  ~/.kb/inbox/<decimal>/       Dashboard "Ready for Action"          │
│                                                                      │
│  [Drop file] ───► [Auto-process] ───► [Action appears] ───► [Copy] │
│                   (cron/watcher)       (Skool post ready)           │
└─────────────────────────────────────────────────────────────────────┘
```

## Objectives
- Create `kb serve` command that runs a local web server (Flask/FastAPI)
- Build action queue as the primary dashboard view (not transcript browsing)
- Implement file inbox with automatic processing based on decimal/category
- Support compound analysis types (analysis that depends on other analyses)
- Enable one-click copy of outputs to clipboard
- Keyboard-driven UI (vim motions: j/k navigate, c copy, d done)
- Secondary browse mode for finding specific transcripts/analyses

## Dependencies
- T011 (Knowledge Base Capture System) - uses existing KB infrastructure
- T012 (KB Zoom Meetings) - zoom source and registry system

## Rules Required
- task-documentation

## Resources & References
- **Mockups** (in /tmp, will be lost on reboot - CSS/JS patterns now in `kb/templates/action_queue.html`):
  - `/tmp/kb-serve-mockups/style4-action-queue.html` (primary - implemented)
  - `/tmp/kb-serve-mockups/style4-browse-mode.html` (secondary - Phase 5)
- Existing dashboard: `kb/dashboard.py` (config visualization, can reuse patterns)
- KB Core: `kb/core.py` (transcribe_to_kb, registry functions)
- Analysis: `kb/analyze.py` (existing analysis runner)
- **Implemented**: `kb/serve.py`, `kb/templates/action_queue.html`

## Design Decisions (Locked In)

### D1: Compound Analysis Dependencies ✓
Add `requires` field to analysis type JSON:
```json
{
  "name": "skool_post",
  "requires": ["summary", "key_moments"],
  "prompt": "Given this summary and key moments..."
}
```

### D2: Action Queue Item Definition ✓
Actionable outputs defined by **(input_type + analysis_type) → destination**:
```yaml
actions:
  # Format: "input_type.analysis_type" → "destination label"
  video.skool_post: "→ Skool"
  meeting.skool_post: "→ Skool"
  meeting.student_guide: "→ Student"
  video.linkedin_post: "→ LinkedIn"
```
This allows the same analysis type to be actionable for some input types but not others.

### D3: User Actions ✓
Three actions on queue items:
- `c` = Copy to clipboard (can copy multiple times)
- `d` = Mark done (moves to completed)
- `s` = Skip (dismiss without copying)

### D4: File Inbox Structure ✓
Decimal in path (explicit):
```
~/.kb/inbox/50.01.02/skool-call.mp4
~/.kb/inbox/50.03.01/alpha-session.mp4
```

### D5: Server Deployment ✓
**Configurable** - support both local and server daemon modes. Details to be determined during implementation. Key: clean separation so either works.

### D6: Processing Trigger ✓
**Configurable** - cron as default, but architecture should support:
- Cron job (default)
- Filesystem watcher (optional)
- Manual `kb process-inbox` command (always available)

## Phases Breakdown

### Phase 1: Core Server & Action Queue UI
**Status**: Complete

**Technical Decisions (from plan review)**:
- **Flask** (not FastAPI) - simpler, matches existing patterns, Flask-SocketIO available
- **Polling** (not WebSocket) for Phase 1 - 5s interval, upgrade to WebSocket in Phase 4/6
- **Action state** persisted in `~/.kb/action-state.json` (separate from transcript files)
- **Clipboard**: Client-side `navigator.clipboard` with pyperclip API fallback

**Objectives**:
- Create `kb/serve.py` with Flask server
- Build action queue HTML template (from mockup CSS/JS)
- Implement keyboard navigation (j/k/c/d/s)
- Add polling for queue updates (5s interval)
- Copy-to-clipboard with toast notification

**API Endpoints**:
```
GET  /                           # Main dashboard HTML
GET  /api/queue                  # List pending/completed actions
GET  /api/action/<id>/content    # Get full content
POST /api/action/<id>/copy       # Server-side clipboard (pyperclip)
POST /api/action/<id>/done       # Mark done
POST /api/action/<id>/skip       # Mark skipped
```

**Data Model**:
```python
# Action state file: ~/.kb/action-state.json
{
  "actions": {
    "50.03.01-260128-alpha--skool_post": {  # Note: -- separator (URL safe)
      "status": "pending",  # pending, copied, done, skipped
      "copied_count": 0,
      "created_at": "2026-01-29T14:00:00"
    }
  }
}
```

**File Structure**:
```
kb/
  serve.py              # Flask app, routes
  templates/
    action_queue.html   # Main dashboard (inline CSS from mockup)
```

**Acceptance Criteria**:
- [x] `kb serve` starts server on port 8765 (configurable via --port)
- [x] Ctrl+C cleanly shuts down
- [x] Scans KB for transcripts with actionable analyses on startup
- [x] `j`/`k` navigate, `c` copy, `d` done, `s` skip
- [x] Selected item shows preview in right pane
- [x] Toast on copy (disappears after 2s)
- [x] Completed items dimmed with strikethrough
- [x] Empty state when no pending actions
- [x] 5s polling updates queue

**Estimated Time**: 1-2 days

**Resources Needed**:
- Flask
- pyperclip for clipboard fallback
- Mockup: `/tmp/kb-serve-mockups/style4-action-queue.html`

**Dependencies**: None

### Phase 2: Compound Analysis Types
**Status**: COMPLETE

**Objectives**:
- Extend analysis type JSON schema with `requires` field
- Modify `kb/analyze.py` to resolve dependencies
- Run prerequisite analyses before compound analysis
- Pass prerequisite outputs as context to compound prompt
- Create `skool_post` analysis type as first compound example

**Example Compound Analysis Type**:
```json
// ~/.config/kb/analysis_types/skool_post.json
{
  "name": "skool_post",
  "description": "Community post formatted for Skool",
  "requires": ["summary", "key_moments"],
  "prompt": "You are creating a Skool community post based on a recorded session.\n\nHere is the summary:\n{{summary}}\n\nHere are the key moments:\n{{key_moments}}\n\nCreate an engaging Skool post that:\n- Starts with an attention-grabbing opener (can use 1-2 emojis)\n- Highlights 3-5 key takeaways as bullet points\n- Includes a memorable quote or insight\n- Ends with a discussion question\n- Keeps total length under 300 words\n\nWrite in a conversational but professional tone.",
  "output_schema": {
    "type": "object",
    "properties": {
      "post": { "type": "string" }
    }
  }
}
```

**Dependency Resolution Logic**:
```python
def run_analysis_with_deps(transcript_path, analysis_type):
    analysis_def = load_analysis_type(analysis_type)

    # Check for required analyses
    for req in analysis_def.get("requires", []):
        if req not in transcript["analysis"]:
            # Run prerequisite first
            run_analysis(transcript_path, req)

    # Now run the compound analysis with context
    context = {req: transcript["analysis"][req] for req in analysis_def.get("requires", [])}
    run_analysis(transcript_path, analysis_type, context=context)
```

**Estimated Time**: 0.5 days

**Resources Needed**:
- Existing `kb/analyze.py`

**Dependencies**: None (can be done in parallel with P1)

### Phase 3: Actionable Output System (Config-Driven)
**Status**: Not Started

**Objectives**:
- Move action mapping from hardcoded `DEFAULT_ACTION_MAPPING` to `~/.config/kb/config.yaml`
- Support `input_type.analysis_type` pattern for granular control
- Add wildcard support (`*.skool_post` matches all input types)

**Config Schema**:
```yaml
# ~/.config/kb/config.yaml
serve:
  action_mapping:
    # Format: "analysis_type" or "input_type.analysis_type"
    skool_post: "Skool"           # Any input type
    linkedin_post: "LinkedIn"
    meeting.student_guide: "Student"  # Only for meetings
    "*.summary": "Review"         # Wildcard - all summaries
```

**Estimated Time**: 0.5 days

**Resources Needed**:
- Update `kb/serve.py` to load from config
- Update `kb/__main__.py` config schema

**Dependencies**: P1

### Phase 4: File Inbox & Auto-Processing
**Status**: Not Started

**Objectives**:
- Create inbox directory structure (`~/.kb/inbox/<decimal>/`)
- Implement `kb process-inbox` command
- Auto-detect file type and apply decimal-default analyses
- Move processed files to archive or delete
- Set up cron job template/instructions

**Estimated Time**: 1 day

**Resources Needed**:
- Cron configuration
- File watching (optional, for immediate processing)

**Dependencies**: P2 (needs compound analysis support)

### Phase 5: Browse Mode & Secondary Views
**Status**: Not Started

**Objectives**:
- Add browse view (categories → transcripts → detail)
- Search functionality
- View/copy any analysis output
- Toggle between Queue and Browse modes

**Estimated Time**: 1 day

**Resources Needed**:
- Second HTML template

**Dependencies**: P1

### Phase 6: Server Deployment & Access
**Status**: Not Started

**Objectives**:
- Systemd service or launchd plist for always-on server
- Tailscale access configuration
- Raycast script/shortcut for quick access
- Documentation for setup

**Estimated Time**: 0.5 days

**Resources Needed**:
- Server access (zen)
- Tailscale network

**Dependencies**: P1-P5

## Future Considerations (v2)
- Configuration UI for adding decimals/analysis types/mappings
- Analytics (words per meeting, topics over time)
- Mobile-friendly responsive design
- Integration with actual posting (Skool API, LinkedIn API)

## Execution Log

### Phase 2: Compound Analysis Types
- **Status:** COMPLETE
- **Started:** 2026-01-30
- **Completed:** 2026-01-30
- **Commits:** `b8bd2e8`
- **Files Modified:**
  - `kb/analyze.py` - Added dependency resolution logic, template substitution
  - `kb/tests/__init__.py` - New test package
  - `kb/tests/test_compound_analysis.py` - Unit tests for compound analysis
  - `~/.../analysis_types/skool_post.json` - New compound analysis type (in KB)

### Tasks Completed
- [x] Added `format_prerequisite_output()` - formats analysis results for prompt injection
- [x] Added `substitute_template_vars()` - replaces {{variable}} placeholders in prompts
- [x] Added `run_analysis_with_deps()` - recursive dependency resolution
- [x] Updated `analyze_transcript()` - accepts prerequisite_context parameter
- [x] Updated `analyze_transcript_file()` - uses run_analysis_with_deps for all analyses
- [x] Created `skool_post.json` analysis type with requires: ["summary", "key_points"]
- [x] Added 10 unit tests covering template substitution, formatting, and dependency resolution

### Acceptance Criteria
- [x] `requires` field is parsed from analysis type definitions - verified via tests
- [x] Prerequisites are automatically run if missing - verified via test_runs_prerequisites_when_missing
- [x] Prerequisite outputs injected via template substitution - verified via template tests
- [x] `skool_post` analysis type created and working - file created in KB analysis_types dir

### Notes
- Plan referenced `key_moments` but existing analysis type is `key_points` - used correct name
- skool_post.json created in synced Obsidian KB at `/home/blake/lem/mac-sync/Obsidian/zen-ai/knowledge-base/transcripts/config/analysis_types/`
- KB path on server differs from Mac - tests use mocked paths for portability

---

## Notes & Updates
- 2026-01-29: Task created from design session. Mockups at `/tmp/kb-serve-mockups/`.
- Design decision: Action queue is primary view, not transcript browser.
- Design decision: Tmux-pane style UI with Catppuccin Mocha theme.
- Design decision: Keyboard-first (vim motions).
- 2026-01-29: Phase 1 complete. Code review identified and fixed:
  - Changed action ID separator from `::` to `--` for URL safety
  - Added input validation for action_id parameters (regex pattern)
  - Added corrupted state file handling with backup creation
- Learnings for future phases:
  - Consider caching for scan_actionable_items() if performance becomes an issue
  - Load action_mapping from config in Phase 3 instead of hardcoded
  - Large content truncation may be needed in frontend
- 2026-01-30: Phase 2 complete. Compound analysis support added.
