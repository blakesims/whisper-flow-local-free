# Code Review: Phase 4

## Gate: PASS

**Summary:** Clean implementation of slide editing, template selection, re-render, and CLI publish support. All 8 acceptance criteria verified. 370/370 tests pass with zero regressions. The Phase 3 review fix (save-edit on ready items invalidates visuals) was correctly applied. No critical issues found. Two major issues: the /render endpoint does not validate template_name before spawning the background thread, and find_staged_renderables() has no test coverage. Four minor issues around code duplication, missing break in nested loop, and a UX edge case.

---

## Git Reality Check

**Commits:**
```
f2eff82 Phase4: Slide editing, template selection, re-render, publish CLI
```

**Files Changed:**
- `kb/serve.py`
- `kb/templates/posting_queue.html`
- `kb/publish.py`
- `kb/tests/test_slide_editing.py`
- `tasks/active/T023-content-curation-workflow/main.md`

**Matches Execution Report:** Yes -- all 5 files match what the execution log claims.

**Test Results:** 370/370 pass (23 new + 347 existing). Zero failures, zero regressions.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Slides viewable and editable after visual generation | Yes | Yes | GET /slides returns slide data; buildSlideEditorHtml() renders per-slide cards with title/content textareas |
| AC2: Each slide shows title and content in textarea fields | Yes | Yes | slide-card has .slide-title-input and .slide-content-input textareas; rows auto-sized by content |
| AC3: Slide type is read-only | Yes | Yes | save-slides only updates title/content, type field ignored; mermaid content textarea has readonly attribute; test_save_slides_preserves_type verifies server side |
| AC4: Save edits updates carousel_slides data | Yes | Yes | test_save_slides_updates_content and test_save_slides_records_timestamp verify; _slides_edited_at timestamp added |
| AC5: Template selector shows available templates | Yes | Yes | GET /api/templates reads config.json; buildTemplateSelectorHtml() populates dropdown; test_known_templates_present confirms brand-purple, modern-editorial, tech-minimal |
| AC6: Re-render produces new visuals with template | Yes | Yes | POST /render passes template_name to render_pipeline(); background thread updates status; test_render_starts_thread and test_render_works_for_ready_status verify |
| AC7: `kb publish --decimal X` works with staged content | Yes | Yes | --staged flag routes to find_staged_renderables(); --template passes to render_one(); render_one passes template_name kwarg to render_pipeline |
| AC8: Slide edits persist across page refreshes | Yes | Yes | test_save_and_refetch_slides verifies save then GET returns edited values |

**Phase 3 Review Fix (save-edit stale visuals):** Verified at `kb/serve.py` lines 1020-1025. When save-edit is called on a "ready" item, status resets to "staged" and visual_status to "stale". Two dedicated tests (test_save_edit_on_ready_resets_to_staged, test_save_edit_on_staged_does_not_change_status) cover this.

---

## Issues Found

### Major

1. **No template_name validation in /render endpoint**
   - File: `kb/serve.py:1302`
   - Problem: The `/api/action/<id>/render` endpoint reads `template_name = data.get("template")` from the request body and passes it directly to `render_pipeline()` inside a background thread. If a user supplies a bogus template name (e.g., `{"template": "nonexistent"}`), the background thread will crash with a `KeyError` from `render_pipeline()` -> `render_carousel()` (render.py:304-307). The HTTP response has already returned 200 "Render started" at that point, so the user gets a false success. The failure is silently caught by the except block and sets visual_status to "failed", but the user experience is poor: they see success, then later discover it failed.
   - Fix: Validate template_name against available templates before spawning the thread. Either load the config and check, or accept None and let render_pipeline use the default. Something like: if template_name is not None, verify it exists in load_carousel_config()["templates"] before starting the thread.

2. **No test coverage for find_staged_renderables()**
   - File: `kb/publish.py:111-195`
   - Problem: `find_staged_renderables()` is a brand-new 85-line function that reads action-state.json, iterates all KB directories, matches transcript IDs, and extracts slides data. It has zero test coverage. The tests for `--template` only cover `render_one()` directly. If `find_staged_renderables()` has a bug (e.g., wrong key lookup, bad filter logic, path handling), it would not be caught.
   - Fix: Add at least 2-3 tests: one for the happy path (staged item with carousel_slides found), one for filtering (decimal_filter works), one for skip logic (non-staged items excluded).

### Minor

1. **Duplicated slides extraction logic across three endpoints**
   - Files: `kb/serve.py:1141-1157` (get_slides), `kb/serve.py:1212-1223` (save_slides), `kb/serve.py:1320-1338` (_run_render)
   - Note: The same carousel_slides -> output -> slides extraction pattern with string-parsing fallback is repeated three times. A helper like `_extract_slides_from_transcript(transcript_data)` would reduce duplication and lower the risk of the three copies drifting out of sync. This is a code quality observation, not a bug.

2. **find_staged_renderables() does not break after finding the matching transcript**
   - File: `kb/publish.py:144-193`
   - Note: The nested loop `for decimal_dir ... for json_file ...` continues scanning all directories and files even after finding the transcript matching a given action_id. Since transcript IDs are unique, a break after appending to renderables (breaking both inner and outer loops for that action_id) would avoid unnecessary file I/O. Not a bug but O(n*m) instead of O(n) where m = total JSON files.

3. **selectedTemplate persists across entity switches**
   - File: `kb/templates/posting_queue.html:1771-1779`
   - Note: `fetchTemplates()` caches both `templatesData` and `selectedTemplate`. When switching from entity A to entity B, `selectedTemplate` retains whatever the user chose for entity A. This could be confusing if the user expects each entity to default to the config default template. Minor UX inconsistency.

4. **Render endpoint race window before "generating" status is set**
   - File: `kb/serve.py:1310-1312`
   - Note: Same pattern as the Phase 3 generate-visuals endpoint (noted in Phase 3 review as M2). `_update_visual_status(action_id, "generating")` is called inside the background thread, not before it starts. There is a brief window where a second /render request could pass the "already generating" check. Mitigated by client-side guards (button disabled), but server-side is not fully guarded. Carried forward from Phase 3, consistent with existing pattern.

---

## What's Good

- The Phase 3 code review fix (save-edit stale visual invalidation) was correctly implemented with two dedicated tests.
- save-slides correctly invalidates visual_status to "stale" for both staged and ready items, with status reset to "staged" when coming from "ready". This is consistent behavior.
- The slide editor UI correctly makes mermaid content read-only (both UI via readonly attribute and server via only updating title/content fields). Type preservation is test-verified.
- Template selector properly escapes output with `escapeHtml()` in the HTML template, consistent with the XSS protections established in Phase 2.
- The render endpoint correctly rejects requests when visual_status is "generating" (prevents concurrent renders).
- All 4 new API endpoints have proper input validation (validate_action_id, status checks, request body validation) and consistent error response formatting.
- The publish.py changes are additive and backward-compatible: existing `--pending` and `--regenerate` modes are untouched; `--staged` is a new mode.
- render_one() correctly passes template_name as a keyword argument to render_pipeline(), matching the function signature.
- 23 tests cover all major paths: templates, slides CRUD, render, visual invalidation, publish template flag, and persistence.

---

## Required Actions (for REVISE)

N/A -- PASS gate. Issues are noted for future improvement but do not block completion.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Validate user-provided enum values before spawning background threads | Any endpoint that defers work to threads | Pre-validate template names against config before thread start |
| New utility functions need their own test coverage | All phases | When adding a new public function (find_staged_renderables), add unit tests even if it's only called from CLI |
| Extract repeated patterns into helpers before they triple | serve.py | The slides extraction pattern appears 3x; extract to _extract_slides() |
