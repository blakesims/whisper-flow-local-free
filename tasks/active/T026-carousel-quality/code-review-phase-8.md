# Code Review: Phase 8

## Gate: PASS

**Summary:** Solid implementation across all three sub-phases. The `strengths` API bug is genuinely fixed, score progression is text-only as decided, decimal filter works correctly with filtered list propagation, and the analysis picker is keyboard-driven with proper validation. 19 new tests all passing, zero regressions (39 pre-existing failures unchanged). No critical or major issues. 4 minor findings, all non-blocking.

---

## Git Reality Check

**Commits:**
```
53b6ca4 Phase8A: Render judge feedback in iteration view
9f176d1 Phase8B: Decimal filter on entity list
b138a8e Phase8C: Trigger analysis from browse UI with keyboard picker
7d5d8cb docs(T026): update main.md with Phase 8 execution log, set CODE_REVIEW
```

**Files Changed (code commits only, 53b6ca4..b138a8e):**
- `kb/serve.py` -- +160 lines (strengths fix, analysis endpoints)
- `kb/templates/browse.html` -- +367 lines (analysis picker CSS/HTML/JS)
- `kb/templates/posting_queue.html` -- +292/-17 lines (feedback rendering, decimal filter)
- `kb/tests/test_phase8_iteration_feedback.py` -- +315 lines (7 tests)
- `kb/tests/test_phase8_analyze.py` -- +276 lines (12 tests)

**Matches Execution Report:** Yes -- file list, commit count, and test counts all match.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| 8A-AC1: Improvements render per round | Yes | Yes | `improvements` array mapped to `.improvement-card` divs with criterion, issue, suggestion. `escapeHtml` applied to all. |
| 8A-AC2: Strengths render per round | Yes | Yes | Both versioned (line 1174) and backward-compat (line 1197) paths now include `"strengths": judge_data.get("strengths", [])`. Frontend renders as `.strength-item` list. |
| 8A-AC3: Rewritten hook shows when provided | Yes | Yes | `if (rewrittenHook)` guard correctly shows/hides. Tested: round 0 has hook, round 1 has `null`. |
| 8A-AC4: Score progression text-only, color-coded | Yes | Yes | Text-only per Blake's decision. Color thresholds: red < 3, yellow 3-3.9, green >= 4. Uses `var(--green/yellow/red)` CSS vars. Only shows when `scoreHistory.length > 1`. |
| 8A-AC5: Unjudged rounds scores=None | Yes | Yes | Test `test_unjudged_round_has_scores_none` verifies. Frontend `if (current.scores)` guard prevents crash. |
| 8A-AC6: Pre-T023 backward compat | Yes | Yes | Test `test_unversioned_judge_includes_strengths` verifies backward compat path with unversioned `linkedin_judge` key. |
| 8B-AC1: Decimal filter dropdown | Yes | Yes | `<select>` element with class `template-select` rendered in entity list header. Populated from `getUniqueDecimals()`. |
| 8B-AC2: Filter persists across polling | Yes | Yes | `fetchQueue()` re-applies `getFilteredItems()` after poll. `selectedDecimalFilter` variable preserved. Index clamping + entity re-selection logic correct. |
| 8B-AC3: "All" option shows everything | Yes | Yes | `<option value="">All decimals</option>` maps to `selectedDecimalFilter = null`, and `getFilteredItems()` returns all items when filter is null. |
| 8B-AC4: Status bar shows filtered/total | Yes | Yes | `updateStatusBar()` shows `"N/M entities"` when filtered, `"M entities"` when unfiltered. Section header also shows `countLabel`. |
| 8C-AC1: analysis-types excludes internal | Yes | Yes | `_INTERNAL_ANALYSIS_TYPES = {"visual_format", "carousel_slides", "linkedin_judge", "linkedin_post"}`. Test verifies all 4 excluded and user types included. |
| 8C-AC2: analyze endpoint validates and runs background | Yes | Yes | Regex validation, type validation against `list_analysis_types()`, non-empty check, string type check. Thread started with daemon=True. |
| 8C-AC3: Concurrent analysis returns 409 | Yes | Yes | Checks `processing` dict in action-state.json before starting. Test verifies with pre-seeded processing state. |
| 8C-AC4: Processing state tracked | Yes | Yes | Set before thread start (types + started_at), cleared in `finally` block. Test `test_sets_processing_state` verifies. |
| 8C-AC5: Keyboard picker (a/j/k/Enter/Esc) | Yes | Yes | `a` opens when `focusPane === 2`. Picker captures all keys while open (swallow pattern). j/k navigate, Enter confirms, Esc closes. |
| 8C-AC6: Force mode toggle (f key) | Yes | Yes | `f` toggles `forceMode` boolean. `renderAnalysisPicker()` uses it to enable/disable already-analyzed types. Status badge changes from "done" to "re-run". |
| 8C-AC7: linkedin_post hidden | Yes | Yes | Included in `_INTERNAL_ANALYSIS_TYPES` set. Test `test_returns_user_facing_types` asserts `linkedin_post` not in names. |

---

## Issues Found

### Critical
None.

### Major
None.

### Minor

1. **Force mode not passed through to auto-judge types**
   - File: `kb/serve.py:1632-1643`
   - Problem: The `force` flag from the request body is passed to `analyze_transcript_file()` for regular types, but not to `run_with_judge_loop()` for auto-judge types. Since `run_with_judge_loop` always appends a new round (it doesn't skip existing), force is effectively a no-op for auto-judge types. The UI's `f` key toggle creates a misleading expectation that force re-analysis applies uniformly.
   - Impact: Low -- auto-judge types always run a new round regardless. No functional bug, just a UX consistency concern.
   - Recommendation: Either document this in the picker footer, or add a comment in the code explaining the asymmetry.

2. **Analysis polling has no timeout/max-retries**
   - File: `kb/templates/browse.html:1388-1418`
   - Problem: `pollAnalysisCompletion()` polls `/api/processing` every 2-3 seconds indefinitely. If the server restarts and leaves stale `processing` state in `action-state.json`, the polling never stops. No max retry count or timeout exists.
   - Impact: Low -- single-user tool, and the `finally` block in `_run_analysis` should clear state in normal operation. Only a concern on server crash/restart.
   - Recommendation: Add a max poll count (e.g., 150 polls = ~5 minutes) or timestamp-based timeout. Alternatively, add a "cancel" action.

3. **Force mode hint not shown in picker UI**
   - File: `kb/templates/browse.html:813-824`
   - Problem: The picker header shows hints for `j/k`, `Enter`, and `Esc`, but does not mention the `f` key for force mode. The footer says "Types already analyzed are greyed out" but does not mention how to override this.
   - Impact: Low -- discoverability issue for the force toggle feature.
   - Recommendation: Add `<span class="key-hint">f</span> force re-run` to the picker footer.

4. **Score progression uses array index instead of entry.round**
   - File: `kb/templates/posting_queue.html:1498` (approx)
   - Problem: The score progression renders `R${i}` using the array index rather than `entry.round`. If `score_history` entries ever have gaps or don't start at round 0, the displayed labels would be inaccurate.
   - Impact: Very low -- `_build_score_history` creates sequential entries in practice.
   - Recommendation: Use `entry.round` if available: `R${entry.round ?? i}`.

---

## What's Good

- **Strengths API fix is minimal and correct**: Two lines added in parallel locations (versioned path + backward-compat path). Both use `.get("strengths", [])` with safe default.
- **Decimal filter propagation is thorough**: All 7 callsites that previously used `queueData.items` directly were updated to use `getFilteredItems()` -- entity list rendering, selectEntity, fetchQueue, keyboard nav, updateStatusBar, stageItem, and publishItem.
- **Input validation on analyze endpoint is comprehensive**: Regex check on transcript_id, presence check on body, type check on `analysis_types`, non-empty check, string type check, valid name check against `list_analysis_types()`. Five distinct 400 error paths.
- **XSS protection consistently applied**: All dynamic content in both templates goes through `escapeHtml()`.
- **Test quality is high**: Tests use `tmp_path` fixtures with realistic data structures (versioned judge data, backward-compat paths, empty states). Thread is properly mocked in the analyze tests. 7 + 12 = 19 tests covering both happy and error paths.
- **Deviations from plan are well-justified**: Task 8C.3 skip (different function signatures), 8C.1+8C.5 consolidation (processing state inline), and the semicolon test approach (Flask routing limitation) all make sense.

---

## Required Actions (for REVISE)
N/A -- PASS gate.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Force mode semantics differ between analysis pipelines (regular: skip-or-rerun, judge: always-new-round) | Any future force-mode UX | Document asymmetry or unify behavior |
| Polling without timeout is a latent reliability risk | All polling patterns in browse.html/posting_queue.html | Consider adding max-retry to existing poll loops too |
| Keyboard hint discoverability matters for hidden features | All keyboard-driven UIs | Always show all available keybinds in the UI chrome |
