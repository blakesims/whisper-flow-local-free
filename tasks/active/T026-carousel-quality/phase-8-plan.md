# Phase 8 Plan: KB Serve -- Iteration View + Processing UX

## Objective

Surface all judge feedback data in the iteration view (improvements, strengths, rewritten hooks, score history), add decimal-level filtering to the action queue, and enable triggering analysis from the UI.

## Scope

- **In:**
  - 8A: Render judge feedback (improvements, strengths, rewritten hook, score chart) in iteration detail view
  - 8B: Decimal filter dropdown on the entity list
  - 8C: New `/api/transcript/<decimal>/analyze` endpoint + UI trigger button in browse mode
- **Out:**
  - Batch processing orchestration (multi-transcript analysis queue)
  - New analysis type creation from UI
  - Real-time streaming of analysis output

### UX Principles (from Blake, 2026-02-10)
- **No buttons — keyboard only.** All actions triggered via keybinds.
- **Queue = inbox triage.** Items start here. Quick decisions: approve (a), done (d), skip (s), copy (c).
- **Review = refinement.** Only items explicitly approved from Queue appear here. This is where iterate, edit slides, generate visuals happen.
- **"Publish" = manual for now** (copy and post). Future: auto-publish via API.
- **Visuals are optional.** linkedin_v2 defaults to generating visuals, but user can choose text-only.
- **linkedin_post v1 is retired.** Only linkedin_v2 going forward. Existing v1 analyses can be regenerated as v2.

---

## Sub-Phase 8A: Render Judge Feedback in Iteration View

### Objective
Show the full judge evaluation for each iteration round: improvements (with criterion, current issue, suggestion), strengths, rewritten hook, and a score progression mini-chart.

### Bug Fix (API)
The `/api/action/<id>/iterations` endpoint does NOT include `strengths` in its response. The judge output schema (`linkedin_judge.json`) defines `strengths` as an array of strings (line 39-43), and judge results include this field, but `serve.py` lines 1170-1175 omit it.

### Tasks

- [ ] **Task 8A.1: Fix API to include `strengths` in iteration response**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py`
  - Location: Lines 1170-1175 (inside `get_iterations()`)
  - Change: Add `"strengths": judge_data.get("strengths", [])` to the scores dict
  - Also fix the duplicate block at lines 1191-1197 (pre-T023 backward compat path)

- [ ] **Task 8A.2: Add CSS styles for feedback sections**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html`
  - Location: Inside `<style>` block (before `</style>` at line 926)
  - Add styles for: `.feedback-section`, `.improvement-card`, `.improvement-criterion`, `.improvement-issue`, `.improvement-suggestion`, `.strengths-list`, `.strength-item`, `.rewritten-hook`, `.score-chart`

- [ ] **Task 8A.3: Render improvements section in `renderIterationView()`**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html`
  - Location: Inside `renderIterationView()` function (lines 1200-1336)
  - After `${scoresHtml}` (line 1305), add a new `feedbackHtml` variable that renders:
    1. **Improvements list**: For each item in `current.scores.improvements`, show criterion name, current_issue, and suggestion as a styled card
    2. **Strengths list**: For each item in `current.scores.strengths`, show as a green-tinted list item
    3. **Rewritten hook**: If `current.scores.rewritten_hook` is non-null, show in a highlighted box with the suggested replacement hook
  - Insert `${feedbackHtml}` into the pane innerHTML between `${scoresHtml}` and the `.post-section` div

- [ ] **Task 8A.4: Add text-only score progression**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html`
  - Use the top-level `iterationsData.score_history` array (already returned by the API)
  - Render as plain text showing overall score per round, e.g. "Round 1: 3.2 → Round 2: 3.8 → Round 3: 4.1"
  - Place above or beside the round navigator (`.round-nav`)
  - Use existing color scheme for each score value (red < 3, yellow 3-3.9, green >= 4) via inline `<span>` color

- [ ] **Task 8A.5: Add tests for 8A changes**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/tests/test_serve_integration.py` (or new test file)
  - Test that `GET /api/action/<id>/iterations` response includes `strengths` array
  - Test that rounds with no judge data don't crash the frontend rendering logic
  - Test the score_history data structure is present and correctly ordered

### Acceptance Criteria

- [ ] AC-8A.1: Viewing an entity with judge data shows improvements (criterion + issue + suggestion) below the scores grid
- [ ] AC-8A.2: Strengths are displayed as a list for each round that has judge data
- [ ] AC-8A.3: Rewritten hook appears when the judge provided one (check `if (rewritten_hook)`, not score threshold)
- [ ] AC-8A.4: Score progression is visible showing how overall score changed across rounds
- [ ] AC-8A.5: Rounds with no judge data (not yet judged) show "Not judged" without crashing

### Files

- `kb/serve.py` -- add `strengths` to iterations API response (lines 1170-1175, 1191-1197)
- `kb/templates/posting_queue.html` -- CSS + JS changes in `renderIterationView()`

### Dependencies
None -- this builds on existing API and frontend infrastructure.

---

## Sub-Phase 8B: Decimal Filter on Entity List

### Objective
Add a dropdown filter to the posting queue entity list so Blake can filter by decimal (e.g., only show 50.03.01 linkedin_v2 items, hiding 50.01.01 summaries/guides).

### Tasks

- [ ] **Task 8B.1: Add filter dropdown HTML/CSS**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html`
  - Location: Above the entity list section header (line 1093 area, inside `renderEntityList()`)
  - Add a `<select>` dropdown with options: "All decimals" + one per unique `source_decimal` from `queueData.items`
  - Style with existing `.template-select` CSS class or similar

- [ ] **Task 8B.2: Add filter state variable and filtering logic**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html`
  - Location: JS state section (line 998 area)
  - Add `let selectedDecimalFilter = null;` state variable
  - In `renderEntityList()`, filter `queueData.items` by `selectedDecimalFilter` before rendering
  - Dropdown `onchange` sets `selectedDecimalFilter` and re-renders the entity list
  - Preserve the section count to show filtered/total (e.g., "3/12")

- [ ] **Task 8B.3: Persist filter across queue refreshes**
  - When `fetchQueue()` refreshes data, re-apply the current decimal filter
  - Ensure `selectedEntityIndex` is clamped to the filtered list length
  - If the currently-selected entity disappears after filtering, select the first item in the filtered list

### Acceptance Criteria

- [ ] AC-8B.1: Dropdown appears above the entity list with all unique decimals
- [ ] AC-8B.2: Selecting a decimal filters the list to only that decimal's items
- [ ] AC-8B.3: "All" option shows all items (default)
- [ ] AC-8B.4: Filter persists across 5-second polling refreshes
- [ ] AC-8B.5: Section count shows filtered/total (e.g., "Iterations 3/12")
- [ ] AC-8B.6: Keyboard nav (j/k) works correctly on the filtered list

### Files

- `kb/templates/posting_queue.html` -- JS state, `renderEntityList()`, CSS

### Dependencies
None.

---

## Sub-Phase 8C: Trigger Analysis from UI

### Objective
Allow Blake to trigger `kb analyze -t <type>` on a transcript from the browse UI, so he can create new post types (e.g., run linkedin_v2 on a transcript that only has a summary).

### Tasks

- [ ] **Task 8C.1: New backend endpoint `POST /api/transcript/<transcript_id>/analyze`**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py`
  - Location: After the existing `/api/transcript/<transcript_id>` route (around line 1527)
  - Request body: `{ "analysis_types": ["linkedin_v2", "summary"], "force": false }`
  - Validation:
    - transcript_id must match `^[\w\.\-]+$` (existing validation pattern)
    - analysis_types must be a non-empty list of strings
    - Each analysis type must exist in `list_analysis_types()` names
  - Implementation:
    - Find transcript file (reuse the search loop from `get_transcript()` or extract helper)
    - Run in background thread (like iterate and visual pipelines)
    - For types in `AUTO_JUDGE_TYPES`: call `run_with_judge_loop()`
    - For regular types: call `analyze_transcript_file()`
    - Track processing state in action-state.json (new `"analyzing"` flag per transcript)
  - Response: `{ "success": true, "message": "Analysis started", "types": [...] }`

- [ ] **Task 8C.2: New backend endpoint `GET /api/analysis-types`**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py`
  - Returns the list of available analysis types from `list_analysis_types()`
  - Response: `{ "types": [{"name": "linkedin_v2", "description": "..."}, ...] }`
  - Used by the frontend to populate the analysis type selector

- [ ] **Task 8C.3: Extract transcript file finder helper**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py`
  - The pattern of searching across all decimal dirs for a transcript by ID appears in:
    - `get_transcript()` (line 1463-1475)
    - `_find_transcript_file()` in `serve_visual.py` (lines 26-55)
  - Extract a shared `find_transcript_by_id(transcript_id)` helper in `serve_visual.py` (or a new utils module) that returns `(transcript_data, file_path)` or `None`
  - Refactor existing callsites to use it

- [ ] **Task 8C.4: Add keyboard-triggered analysis in browse transcript detail view**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/browse.html`
  - Keybind: `a` opens analysis type picker when viewing a transcript detail
  - Show a keyboard-navigable list of available analysis types (from `/api/analysis-types`)
  - Grey out types already present in the transcript's analysis (unless `f` toggles force mode)
  - Enter confirms selection → POST to `/api/transcript/<id>/analyze`
  - Show inline status indicator while analysis runs
  - Poll for completion (check if new analysis types appear on the transcript)
  - Only expose user-facing types: linkedin_v2, skool_post, skool_weekly_catchup (hide internal: visual_format, carousel_slides, linkedin_judge, linkedin_post)

- [ ] **Task 8C.5: Processing state tracking**
  - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve_state.py` (or inline in `serve.py`)
  - Track which transcripts have analyses in progress: `state["processing"][transcript_id] = {"types": [...], "started_at": "..."}`
  - Clear when the background thread completes
  - Expose via a `GET /api/processing` endpoint (or include in the transcript detail response)
  - This replaces the TODO at `serve.py:155`: `"processing": [] # Phase 2`

### Acceptance Criteria

- [ ] AC-8C.1: `POST /api/transcript/<id>/analyze` starts analysis in background thread and returns immediately
- [ ] AC-8C.2: Available analysis types are listed via API endpoint
- [ ] AC-8C.3: Browse transcript detail: pressing `a` opens keyboard-navigable analysis type picker
- [ ] AC-8C.4: Already-analyzed types are shown as disabled (unless `f` toggles force mode)
- [ ] AC-8C.5: Analysis completion refreshes the transcript detail to show new analysis
- [ ] AC-8C.6: Error handling: invalid transcript ID returns 404, invalid analysis type returns 400
- [ ] AC-8C.7: Concurrent analysis requests for the same transcript are rejected (409 Conflict)
- [ ] AC-8C.8: linkedin_post (v1) items filtered out of staging/review views and analysis type picker

**Tests for 8C:**
- [ ] Test `POST /api/transcript/<id>/analyze` returns 200 with valid types, 400 with invalid type, 404 with bad transcript_id
- [ ] Test `GET /api/analysis-types` returns only user-facing types (excludes visual_format, carousel_slides, linkedin_judge, linkedin_post)
- [ ] Test concurrent analysis rejection (409)

### Files

- `kb/serve.py` -- new endpoints + helper extraction
- `kb/serve_visual.py` -- potentially refactor `_find_transcript_file` to shared util
- `kb/serve_state.py` -- processing state tracking (optional, could be inline)
- `kb/templates/browse.html` -- UI changes for analyze trigger

### Dependencies
- Depends on existing browse mode (`/browse` route, `/api/transcript/<id>` endpoint)
- Uses `analyze_transcript_file()` and `run_with_judge_loop()` from `kb/analyze.py` and `kb/judge.py`

---

## Execution Order

1. **8A first** -- Highest value, most contained change (API fix + frontend rendering)
2. **8B second** -- Small scope, improves usability for 8A testing
3. **8C third** -- Largest scope, new endpoints + UI, builds on understanding from 8A/8B

## Decision Matrix

### Open Questions (Need Human Input)

| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Score progression chart style | A) CSS bar chart B) Inline dots C) Text-only | Affects visual complexity | **RESOLVED: C) Text-only** — scores per round already shown, keep simple |
| 2 | Where should the "Analyze" button live? | A) Browse detail only B) Also posting queue C) Both + standalone | Affects scope of 8C | **RESOLVED: Browse detail only, keyboard-triggered** (`a` key). No buttons — all keyboard. |
| 3 | Which analysis types to expose? | A) All B) Non-internal only C) All with "advanced" label | Exposing internals could confuse | **RESOLVED: B) Non-internal only** — hide visual_format, carousel_slides, linkedin_judge. Expose: linkedin_v2, skool_post, skool_weekly_catchup. linkedin_post (v1) config stays but is filtered out of staging/review and analysis picker. Existing v1 items remain in queue for triage. Config default update (decimals → linkedin_v2) is a separate manual step. |

### Decisions Made (Autonomous)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Add `strengths` to API response | Fix the omission | Judge schema defines it, data exists in JSON, frontend needs it |
| Use background thread for analysis | Same pattern as iterate/visuals | Consistent with existing architecture in `serve.py` |
| Decimal filter is client-side | Filter `queueData.items` in JS | All items already loaded; avoids new API parameter |
| Extract transcript finder helper | Refactor from existing code | Pattern duplicated in 3+ places, DRY principle |
| Processing state in action-state.json | Extend existing state file | Follows existing pattern, no new file needed |
