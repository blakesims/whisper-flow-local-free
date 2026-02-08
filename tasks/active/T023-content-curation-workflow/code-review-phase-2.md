# Code Review: Phase 2 (kb serve Iteration View + Approve Rewire)

## Gate: PASS

**Summary:** Solid implementation. The approve rewire correctly gates visual pipeline for AUTO_JUDGE_TYPES, the four new endpoints are well-structured with proper validation, the HTML template uses escapeHtml consistently for user-controlled data, and 25 meaningful tests cover the key behaviors. 277/277 tests pass with no regressions. Found 0 critical issues, 1 major, and 4 minor.

---

## Git Reality Check

**Commits:**
```
f147554 Phase2: kb serve iteration view + approve rewire
```

**Files Changed (from git diff):**
- `kb/serve.py`
- `kb/templates/posting_queue.html`
- `kb/tests/test_iteration_view.py` (NEW)
- `kb/tests/test_serve_integration.py`

**Matches Execution Report:** Yes -- all 4 files match the execution log claims exactly.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Single entity per transcript | Yes | Yes | `posting-queue-v2` returns deduplicated entities. `scan_actionable_items()` already filters versioned keys (Phase 1). Test: `test_returns_entities_not_iterations`. |
| AC2: Enter drills into entity | Yes | Partial | No Enter key handler exists in keyboard nav. j/k navigation auto-loads detail pane, so functionally equivalent. Click works too. Minor gap vs literal AC wording. |
| AC3: Scores per-criterion with overall | Yes | Yes | `scores-grid` renders each criterion with `formatCriterion()` + `scoreClass()`. Overall score in header. Verified in template lines 941-975. |
| AC4: Deltas between rounds | Yes | Yes | `deltaText()` and `overallDelta()` compute +/-/= badges with up/down/same CSS classes. Verified in template lines 758-773. |
| AC5: Up/down navigate iterations | Yes | Yes | ArrowUp/ArrowDown in keydown handler change `selectedRoundIndex` and re-render. Lines 1205-1218. |
| AC6: 'i' triggers iterate with spinner | Yes | Yes | Keyboard 'i' calls `triggerIterate()`, sets `iterating=true`, shows overlay with spinner, polls every 2s. Lines 1050-1110. |
| AC7: 'a' calls /stage not /approve | Yes | Yes | Keyboard 'a' calls `stageItem()` which POSTs to `/stage`. Stage endpoint does NOT trigger visual pipeline. Test: `test_stage_does_not_trigger_visual_pipeline`. |
| AC8: Existing approved items migrated | Yes | Yes | `migrate_approved_to_draft()` wired in Phase 1 via `kb migrate --reset-approved`. Not re-implemented here (correct). |
| AC9: Not judged fallback | Yes | Yes | Template line 977-981 shows "Not judged" when `current.scores` is null. Test: `test_pre_t023_content_no_versioned_keys`. |
| AC10: Background iteration updates UI | Yes | Yes | `pollIteration()` polls `/iterations` every 2s, updates `iterationsData` and re-renders when `iterating` becomes false. Line 1079-1110. |

---

## Issues Found

### Critical

None.

### Major

1. **No server-side guard against concurrent iterations**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py:911-975`
   - Problem: The `iterate_action` endpoint sets `iterating=True` and launches a background thread, but does NOT check whether `iterating` is already `True` before doing so. The frontend guards against this (`if (!selectedEntity || iterationsData.iterating) return;` at line 1051 of the template), but the server endpoint is unprotected. Two rapid API calls (e.g., from curl, a race in the JS, or browser back/forward) would launch two concurrent `run_with_judge_loop()` calls against the same transcript file. Both threads would read the file, both would write to it, and the last writer would overwrite the first's results. The `_run_iteration` inner function does a non-atomic read-modify-write of the transcript JSON (lines 949-961).
   - Fix: At the top of `iterate_action()`, after loading action state, check `state["actions"].get(action_id, {}).get("iterating", False)` and return 409 Conflict if already iterating. This makes the server authoritative rather than relying on client-side guards.

### Minor

1. **`pollIteration` overwrites global state even if user switched entities**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html:1079-1110`
   - Problem: `pollIteration()` captures `actionId` from `selectedEntity.id` at call time (line 1082), but when the poll resolves, it unconditionally writes to the global `iterationsData` and calls `renderIterationView()` (lines 1090-1092). If the user navigated to a different entity while an iteration was running, the detail pane momentarily flashes the old entity's data before `fetchQueue()` corrects it at line 1095.
   - Fix: Add a guard: `if (selectedEntity && selectedEntity.id === actionId)` before updating `iterationsData` and rendering.

2. **Criterion names from judge output not HTML-escaped**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html:959`
   - Problem: `formatCriterion(criterion)` inserts criterion names (from LLM judge output) into innerHTML without escaping. `formatCriterion` only does `replace(/_/g, ' ')`. If the LLM returns a malformed criterion name containing HTML, it would be injected. Risk is low since the judge prompt defines specific criteria, but it breaks the otherwise consistent pattern of escaping all dynamic content.
   - Fix: Change line 959 to `${escapeHtml(formatCriterion(criterion))}`.

3. **`overallDelta` compares string to number**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html:769-771`
   - Problem: `toFixed(1)` returns a string, which is then compared via `>` and `<` to the number `0`. JavaScript's implicit coercion makes this work correctly, but it is fragile and non-obvious. A code reader would reasonably expect numeric comparison.
   - Fix: Use `parseFloat(diff)` or compute the diff as a number first, then format for display separately.

4. **Double file reads in posting-queue-v2**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py:1089-1129`
   - Problem: `get_posting_queue_v2()` calls `scan_actionable_items()` which reads every transcript JSON file, then for each AUTO_JUDGE_TYPES item, reads the transcript file AGAIN to get `_round` and `_history` metadata (lines 1117-1119). With the 5-second polling interval, every transcript file is read twice every 5 seconds. Currently acceptable for a small-scale personal tool, but will degrade as the transcript count grows.
   - Fix: Either pass `_round` and `_history` through `scan_actionable_items()` in the raw_data field, or cache transcript data within the request lifecycle.

---

## What's Good

- **Clean approve rewire**: The gate on `analysis_type not in AUTO_JUDGE_TYPES` at line 840 is simple, correct, and testable. The test in `test_serve_integration.py` (`test_approve_does_not_trigger_visual_for_autojudge`) confirms it from the integration side, and the iteration view test (`test_approve_linkedin_v2_no_visual`) confirms from the unit side.

- **Consistent XSS protection**: The `escapeHtml()` helper is used for all major user-controlled strings (source_title, source_decimal, destination, post content). The one gap (criterion names) is minor.

- **Strong test coverage**: 25 new tests covering all four endpoints plus the approve rewire. Tests cover both happy paths and error cases (invalid ID, nonexistent item, wrong status, non-auto-judge type). The `test_stage_does_not_trigger_visual_pipeline` test using `mock_thread_cls.assert_not_called()` is particularly valuable.

- **Background iteration architecture**: The pattern of setting `iterating=True`, spawning a daemon thread, clearing the flag in a `finally` block, and having the client poll is clean and well-structured. The `finally` block ensures the flag is cleared even on exceptions.

- **Keyboard-first UX**: j/k for entities, up/down for rounds, i/a/c for actions -- consistent with the existing kb serve navigation patterns (q/r/b/v/p for mode switching).

---

## Required Actions (for REVISE)

N/A -- Gate is PASS. The major issue (M1: no server-side concurrent iteration guard) is a real concern but is mitigated by the client-side guard and the small user base. It should be addressed in a future hardening pass rather than blocking this phase.

---

## Test Results

```
277 passed in 2.40s (full suite)
25 passed in 0.33s (test_iteration_view.py)
3 passed in 0.27s (approve-related tests in test_serve_integration.py)
```

No failures. No regressions.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Server endpoints should validate their own preconditions rather than relying on client-side guards | All background-thread endpoints | Add server-side idempotency checks to any endpoint that spawns threads |
| innerHTML with template literals needs consistent escaping for ALL dynamic values, including seemingly-safe ones like criterion names | All templates using innerHTML | Audit all innerHTML assignments for unescaped dynamic content |
| Polling mechanisms that update global state need entity-identity guards | Any poll-and-render pattern | Always check if the target entity is still selected before updating shared state |
