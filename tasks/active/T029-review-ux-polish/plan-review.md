# Plan Review: T029 — Review UX Polish

## Gate Decision: READY

**Summary:** Solid 5-phase plan with accurate bug diagnoses, correct root cause analysis, and sensible fix approaches. The code references are verified against the actual codebase. A few issues need attention: one task references a non-existent codebase, Phase 4 requires a non-trivial change to `run_with_judge_loop()` that is underspecified, and the `g` key conflict with the existing "generate visuals" binding is a blocker for Phase 3. None of these are plan-level blockers -- they can be resolved during execution.

---

## Codebase Verification

### Line Number Accuracy

| Plan Reference | Claimed | Actual | Verdict |
|---|---|---|---|
| `selectedRoundIndex` state | ~1099 | 1105 | Close enough |
| `fetchIterations()` | ~1350 | 1351 | Accurate |
| `selectEntity()` | ~1321 | 1322 | Accurate |
| Scores rendering | ~1405 | 1405 | Exact |
| `pollIteration()` | ~1615 | 1623 | Close |
| Keydown handler | ~2413 | 2413 | Exact |
| `approve_action()` | ~355 | 309 | Off by 46 lines |
| `stage_action()` | ~428 | 420 | Off by 8 lines |

The serve.py line numbers for Phase 2 are noticeably off. Not a problem since the plan names the functions, but worth noting for the executor.

### Bug Root Cause Verification

**BUG-3 (Round state loss):** CONFIRMED. `fetchIterations()` at line 1357-1358 unconditionally sets `selectedRoundIndex = iterationsData.iterations.length - 1`. Every call to `selectEntity()` calls `fetchIterations()`, which resets the round. The proposed fix (per-entity cache map) is the correct approach.

**BUG-4 (Judge scores intermittent):** CONFIRMED. `pollIteration()` at line 1637 sets `selectedRoundIndex = data.iterations.length - 1` when iteration completes. The `renderIterationView()` function at line 1441-1447 already handles the null scores case with a "Not judged" fallback, but the issue is that the latest round may not have judge data yet when the poll completes. The plan's approach (scan backwards for round with scores) is correct.

**400 errors for non-iterable types:** CONFIRMED. `selectEntity()` at line 1341-1346 calls `fetchIterations()` for ALL items regardless of type. The `/api/action/<id>/iterations` endpoint at serve.py line 1126-1127 rejects types not in `AUTO_JUDGE_TYPES` with a 400. Currently `AUTO_JUDGE_TYPES = {"linkedin_v2": "linkedin_judge"}`, so any other type (e.g. `linkedin_post`) triggers the error.

---

## Issues Found

### Critical (Must Fix)

None.

### Major (Should Fix)

1. **`g` key conflict in Phase 3** -- The plan proposes using `gg` (double-g) for jump-to-first. However, the existing keydown handler already binds `g` to "generate visuals" in staging mode (line 2447-2450: `if (e.key === 'g') { if (isStagingMode()) { generateVisuals(); } }`). The `gg` sequence handler would fire `generateVisuals()` on the first `g` press before the second `g` arrives. The executor must either: (a) change "generate visuals" to a different key, or (b) implement a timer-based debounce where a single `g` waits 500ms before triggering generate visuals, and `gg` within that window cancels it and jumps to first. This is a non-trivial interaction that the plan does not address.

2. **Phase 4: `run_with_judge_loop()` does not accept user feedback** -- The plan says to "check if it accepts user feedback param" (Task 4.2). It does not. The function signature is `run_with_judge_loop(transcript_data, analysis_type, judge_type, model, max_rounds, existing_analysis, save_path)`. Passing user feedback requires either: (a) adding a `user_feedback` parameter that gets injected into the prompt context alongside `judge_feedback`, or (b) pre-injecting it into `existing_analysis` under a convention key. This is a real code change to `judge.py` that the plan leaves as a "check" rather than specifying the approach. The executor needs clarity on which approach to take.

3. **Task 3.3 references non-existent codebase** -- The plan says to "inspect Blake's calendar/planner frontend for vim motion patterns." No such codebase exists under `/home/blake/repos/personal/`. This task cannot be executed as written. Recommend removing it and using standard vim conventions directly (which is already what the plan describes in Tasks 3.1 and 3.2).

### Minor

1. **Phase 2 line numbers off by ~46 lines** -- `approve_action()` is at line 309, not ~355. `stage_action()` is at line 420, not ~428. Minor since the functions are named, but could slow the executor if they search by line number.

2. **Phase 1.3 hardcoding approach is fragile** -- The plan suggests hardcoding `['linkedin_v2']` client-side as iterable types. This duplicates the server-side `AUTO_JUDGE_TYPES` dict. The "better" approach (adding an `iterable` boolean to the posting-queue-v2 API response) is clearly superior and should be the primary approach, not an afterthought. The server already has the `analysis_type in AUTO_JUDGE_TYPES` check right there in the endpoint at line 1242.

3. **No `skip` handler in Review view** -- The Review view (`posting_queue.html`) has no skip functionality currently. The plan does not address this, but it was called out in T028's design as a needed feature. If skip from Review is expected (the task description mentions "vim nav" for the Review view), the executor might wonder about it. Not in scope for T029 but worth noting.

4. **BUG-4 fix part 2 is partially already handled** -- The plan says "scores section is blank when `current.scores` is null" and proposes showing "Judging..." instead. Looking at `renderIterationView()` lines 1441-1447, there is already a "Not judged" fallback for when `current.scores` is null. The actual issue is specifically about `pollIteration()` selecting a round without scores, not about missing fallback rendering. The fix description is slightly misleading -- the fix is primarily about the round selection logic in `pollIteration()`, not about adding a new UI state.

5. **Phase 5 tests for "gg/G navigation" are frontend-only** -- Testing keyboard navigation sequences (gg, G) in a Flask app's test suite is not straightforward since these are client-side JavaScript behaviors. The plan should clarify whether these are Selenium/Playwright tests, or if they're manual verification only. The existing test file (`test_t028_lifecycle.py`) uses Flask's test client for API tests, not browser automation.

---

## Plan Strengths

- Accurate bug diagnosis with confirmed root causes in the actual codebase
- Clear acceptance criteria for each task
- Sensible phase ordering: bugs first, cleanup second, features last
- Phase 2 extraction is a good refactoring target -- the duplicated code between `approve_action()` (lines 344-384) and `stage_action()` (lines 454-498) is nearly identical
- BUG-3 fix approach (per-entity cache map) is clean and idiomatic for SPA state management

---

## Recommendations

### Before Proceeding
- [ ] Resolve the `g` key conflict between "generate visuals" and "gg jump to first" (Major issue #1). Decide on a keybinding before execution starts.
- [ ] Remove Task 3.3 (calendar/planner study) -- the codebase does not exist
- [ ] Specify the approach for passing user feedback to `run_with_judge_loop()` (Major issue #2) -- add a `user_feedback` parameter or use a different injection mechanism

### Consider Later
- Prefer the `iterable` boolean in the API response over client-side hardcoding for Task 1.3
- Frontend keyboard tests may need a separate test approach (Playwright or manual checklist)
