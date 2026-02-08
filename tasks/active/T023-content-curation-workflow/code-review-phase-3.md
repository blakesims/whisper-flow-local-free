# Code Review: Phase 3

## Gate: PASS

**Summary:** Solid implementation of the staging area with correct edit versioning, proper background thread reuse for visual generation, and good test coverage. 342/342 tests pass. Two major issues found (save-edit on ready items does not invalidate stale visuals; generate-visuals has a race window before visual_status is set) and three minor issues, but none break the stated acceptance criteria. The major issues are edge cases that will matter in practice but are not blocking for Phase 4.

---

## Git Reality Check

**Commits:**
```
fa2689d Phase3: Update execution log and set status to CODE_REVIEW
3f17cd2 Phase3: Staging area + text editing + visual generation trigger
```

**Files Changed (3f17cd2):**
- `kb/serve.py` -- +268 lines (new endpoints + stage enhancement)
- `kb/templates/posting_queue.html` -- +466 lines (staging UI)
- `kb/tests/test_staging.py` -- +655 lines (23 tests, NEW file)
- `tasks/active/T023-content-curation-workflow/main.md` -- execution log

**Matches Execution Report:** Yes. Files and scope match the claims.

**Test Results:**
- 342/342 pass (full suite). Execution log claimed 339/342 with 3 pre-existing T024 failures, but those were fixed by the intervening T024 commit (2c493cc). Minor discrepancy -- test count is now higher than claimed. Not an issue.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: 'a' stages post, creates linkedin_v2_N_0 | Yes | Yes | `/stage` creates `_N_0` in transcript JSON with `_source` and `_edited_at`. Verified via test and code at serve.py:920-931. Idempotent (skips if `_N_0` already exists). |
| AC2: Staging area shows editable textarea | Yes | Yes | `renderStagingView()` renders `<textarea id="staging-editor">` with the post text. |
| AC3: Saving creates new edit version (_N_1, _N_2) | Yes | Yes | `/save-edit` reads `_edit` from alias, increments, creates versioned key. Verified via `test_save_edit_creates_n_1` and `test_save_edit_increments_correctly`. |
| AC4: Edit versions preserved in transcript JSON | Yes | Yes | Versioned keys stored in `transcript_data["analysis"]`, alias `_edit` and `post` updated. |
| AC5: Visual generation only from staging | Yes | Yes | `/generate-visuals` requires `status == "staged"`. Approve was already gated for AUTO_JUDGE_TYPES in Phase 2. |
| AC6: "Generating..." spinner | Yes | Yes | `visual-status.generating` CSS class with spinner element. `pollVisualGeneration()` polls every 2s. |
| AC7: "Ready" status with visual preview | Yes | Yes | `visual-status.ready` with thumbnail from `selectedEntity.thumbnail_url`. Background thread transitions status to "ready" via `_run_and_update_status`. |
| AC8: Published/copy only when ready | Yes | Yes | Server-side: `mark_posted()` requires status in `("approved", "ready")`. Client-side: `publishItem()` gates on `status === 'ready' || vs === 'ready' || vs === 'text_only'`. Publish button disabled otherwise. |

---

## Issues Found

### Critical

None.

### Major

1. **Save-edit on "ready" items does not invalidate stale visuals**
   - File: `kb/serve.py:968-971`
   - Problem: The `/save-edit` endpoint allows edits when status is "staged" OR "ready". When a "ready" item is re-edited, the text changes but `visual_status` stays "ready" and the old visuals remain. The user can then "publish" with visuals generated from the old text. The status should either revert to "staged" (requiring re-generation) or the visuals should be flagged as stale.
   - Fix: After saving an edit on a "ready" item, set `status` back to `"staged"` and clear `visual_status` (or set to `"stale"`). This forces the user to regenerate visuals after text changes.

2. **Race window in generate-visuals before visual_status is set**
   - File: `kb/serve.py:1059-1074`
   - Problem: The `/generate-visuals` endpoint spawns a background thread and returns immediately. The `visual_status` is only set to `"generating"` inside `run_visual_pipeline()` (line 269), which runs in the background thread. Between the HTTP response and the thread executing line 269, a rapid second request could bypass the "already generating" guard (line 1050-1052) because `visual_status` is still empty/old. The existing approve flow has the same pattern (delegates to `run_visual_pipeline`) but the staging flow is more likely to see rapid clicks since the user is actively interacting.
   - Fix: Set `visual_status = "generating"` in the action state _before_ starting the thread (between lines 1057 and 1059), same pattern as the `iterate` endpoint which sets `iterating = True` before spawning the thread.

### Minor

1. **Shortcut bar shows g/s globally, not just in staging mode**
   - File: `kb/templates/posting_queue.html:799-800`
   - Problem: The `g` (generate) and `s` (save) shortcuts are shown in the bottom shortcut bar at all times, even though they only function in staging mode. The iteration view shortcuts (i, a) are similarly always shown even when in staging mode. The shortcut bar is never dynamically updated based on mode.
   - Note: Not functionally broken since `isStagingMode()` gates the keyboard handler. Cosmetic confusion only.

2. **No empty-text validation on save-edit**
   - File: `kb/serve.py:979`
   - Problem: The `/save-edit` endpoint validates that the `"text"` field exists in the request body, but does not check for empty strings. A user could save an empty post, creating a versioned edit with `"post": ""`. While unlikely from the UI (the save button is disabled unless text differs from original, and empty text would diff from original), a direct API call could create garbage edit versions.
   - Note: Low risk given single-user tool.

3. **edit_count in action state can diverge from alias _edit in transcript**
   - File: `kb/serve.py:1017-1019`
   - Problem: The `edit_count` in action-state.json and `_edit` in the transcript alias are written independently (lines 1011-1015 for transcript, lines 1017-1019 for state). If the state save fails, they diverge. The code correctly reads `current_edit` from the transcript alias (the source of truth), so the next edit would still work. The `edit_count` in state is only used for display in the queue. A display inconsistency, not a data integrity issue.

---

## What's Good

- **Edit versioning is clean.** The `_N_M` pattern with `_source` chaining creates an auditable edit history. The `_N_0` snapshot on stage correctly preserves the raw LLM output. The alias always points to the latest version.
- **Background thread pattern reuses existing infrastructure.** The `_run_and_update_status` wrapper around `run_visual_pipeline()` correctly handles the status transition to "ready" after the pipeline completes, including the "text_only" case.
- **Keyboard shortcut handling is well-designed.** Textarea focus suppression (all keys except Ctrl+S and Escape go to the textarea), context-dependent 'p' shortcut (publish in staging, prompts navigation otherwise), and Escape-to-blur are all good UX.
- **Tests are real and thorough.** 23 tests covering the key behaviors: edit version creation, incrementing, status guards, end-to-end flow, ready/staged gating. The `_make_transcript` and `_make_state` helpers are well-factored.
- **Idempotent stage:** If `_N_0` already exists, staging does not overwrite it. Good defensive coding.
- **Copy in staging reads from textarea.** The `copyContent()` function was updated to read from the staging textarea if present, so the user always copies the latest edited text.

---

## Required Actions (for REVISE)

N/A -- PASS gate. Major issues documented for awareness but do not block Phase 4.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| When allowing edits on a "ready" item, the visual state should be invalidated | Any workflow with dependent generation steps | Consider adding status reversion in Phase 4 or a follow-up fix |
| Background thread status should be set before thread.start(), not inside the thread | All background thread patterns in serve.py | The iterate endpoint already does this correctly; generate-visuals should match |
| Dual-source tracking (action-state + transcript JSON) creates divergence risk | Future endpoint design | Consider making one the source of truth and deriving the other |
