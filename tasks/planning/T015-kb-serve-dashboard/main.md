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
- Mockups: `/tmp/kb-serve-mockups/style4-action-queue.html` (primary)
- Mockups: `/tmp/kb-serve-mockups/style4-browse-mode.html` (secondary)
- Existing dashboard: `kb/dashboard.py` (config visualization, can reuse patterns)
- KB Core: `kb/core.py` (transcribe_to_kb, registry functions)
- Analysis: `kb/analyze.py` (existing analysis runner)

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
    "50.03.01-260128-alpha::skool_post": {
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
- [ ] `kb serve` starts server on port 8765 (configurable via --port)
- [ ] Ctrl+C cleanly shuts down
- [ ] Scans KB for transcripts with actionable analyses on startup
- [ ] `j`/`k` navigate, `c` copy, `d` done, `s` skip
- [ ] Selected item shows preview in right pane
- [ ] Toast on copy (disappears after 2s)
- [ ] Completed items dimmed with strikethrough
- [ ] Empty state when no pending actions
- [ ] 5s polling updates queue

**Estimated Time**: 1-2 days

**Resources Needed**:
- Flask
- pyperclip for clipboard fallback
- Mockup: `/tmp/kb-serve-mockups/style4-action-queue.html`

**Dependencies**: None

### Phase 2: Compound Analysis Types
**Status**: Not Started

**Objectives**:
- Extend analysis type JSON schema with `requires` field
- Modify `kb/analyze.py` to resolve dependencies
- Run prerequisite analyses before compound analysis
- Pass prerequisite outputs as context to compound prompt

**Estimated Time**: 0.5 days

**Resources Needed**:
- Existing `kb/analyze.py`

**Dependencies**: None (can be done in parallel with P1)

### Phase 3: Actionable Output System
**Status**: Not Started

**Objectives**:
- Define action mapping in config (analysis → destination label)
- Track action state (pending, copied, done) in registry or separate state file
- Filter analyses into "actionable" for queue display
- Implement "mark done" functionality

**Estimated Time**: 0.5 days

**Resources Needed**:
- Config schema update
- State persistence (JSON file or SQLite)

**Dependencies**: P1, P2

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
