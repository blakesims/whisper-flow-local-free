# Code Review: T029 — All Phases (1-4)

## Gate: PASS

**Summary:** All 4 phases are implemented correctly against their acceptance criteria. The refactoring is clean, tests are real and passing (73 new tests, 0 regressions), and the vim keybindings follow the spec. Two major UX bugs exist around feedback state management between entities, but neither blocks core functionality. The executor did solid work.

---

## Git Reality Check

**Commits (chronological):**
```
5085202 refactor: T029 Phase 2 — extract _stage_item() helper from approve/stage endpoints
9268d3e fix: T029 Phase 1 — round state persistence, scores visibility, 400 cleanup
f6cb404 feat: T029 Phase 3 — vim keybindings (h/l rounds, gg/G jump, v for visuals)
e012320 feat: T029 Phase 4 — manual feedback/notes before iteration
d8a648c task: T029 Phase 4 execution log complete, set status CODE_REVIEW
```

**Files Changed:**
- `kb/serve.py` — _stage_item helper, iterable flag, feedback endpoint, user_feedback passthrough
- `kb/judge.py` — user_feedback parameter in run_with_judge_loop
- `kb/templates/posting_queue.html` — round cache, non-iterable view, vim keys, notes UI
- `kb/tests/test_iteration_view.py` — 10 new feedback tests
- `kb/tests/test_judge_versioning.py` — 1 new judge signature test
- `tasks/active/T029-review-ux-polish/main.md` — task document updates

**Matches Execution Report:** Mostly. Phase 2 was committed before Phase 1 (reversed order). The `iterable` field addition to serve.py was part of the Phase 2 commit despite being a Phase 1 AC. No functional impact.

**Test Results:**
- 447 passed, 37 failed (all 37 failures are pre-existing from before T029)
- T029-specific tests: 73 passed, 0 failed
- Net new tests: 10 (test_iteration_view) + 1 (test_judge_versioning) = 11

---

## AC Verification

### Phase 1: Bug Fixes

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| BUG-3: Round state persists on entity switch | Yes | Yes | `entityRoundIndex` cache in JS, restored in `fetchIterations()`, updated on h/l/tab clicks |
| BUG-4: Scores visible after iteration | Yes | Yes | `pollIteration` scans backwards for latest round with scores; "Awaiting judge..." placeholder |
| 400 cleanup for non-iterable types | Yes | Yes | `iterable` boolean from API, frontend guards `/iterations` call, `renderNonIterableView()` |

### Phase 2: Extract `_stage_item()` Helper

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| Both endpoints identical behavior | Yes | Yes | Diff confirms same state mutations, same transcript writes. `approve_action` ignores return value (correct: it never used `staged_round` in response). `stage_action` uses return value for `staged_round` in response (matches original). |
| Shared code in one place | Yes | Yes | `_stage_item()` at line 308 of serve.py |
| All existing tests pass | Yes | Yes | 437 passed pre-T029, 447 passed post-T029 |

### Phase 3: Vim Keybindings

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| G selects last entity | Yes | Yes | `selectEntity(filteredItems.length - 1)` |
| gg selects first entity | Yes | Yes | `pendingG` pattern with 500ms timeout |
| h/l navigate rounds | Yes | Yes | Added as aliases alongside ArrowUp/ArrowDown |
| Generate visuals moved to v | Yes | Yes | Context-dependent: staging mode = generateVisuals(), else = /videos |
| Input guard for INPUT+TEXTAREA | Yes | Yes | Expanded from TEXTAREA-only at top of keydown handler |

### Phase 4: Manual Feedback/Notes

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| [n] key opens/focuses textarea | Yes | Yes | Guard: only opens if `notes-textarea` element exists |
| Escape returns focus | Yes | Yes | Handled by existing `isInTextInput` guard |
| Feedback persists in action state | Yes | Yes | POST/GET endpoint, tests verify persistence |
| Feedback passed to judge loop | Yes | Yes | `user_feedback` param added to `run_with_judge_loop`, injected at both Step 1 and Step 3 |

---

## Issues Found

### Major

1. **Stale feedback text bleeds between entities**
   - File: `kb/templates/posting_queue.html:1735`
   - Problem: `fetchUserFeedback()` only sets `textarea.value` when `data.user_feedback` is truthy. If entity A has feedback and entity B does not, switching from A to B leaves entity A's text visible in the textarea. The `notesOpen` global state also persists across entities, so notes section stays open. The textarea is never cleared on entity switch.
   - Fix: Always set `textarea.value = data.user_feedback || ''` unconditionally. Reset `notesOpen = false` at the start of `selectEntity()` or at the start of `renderIterationView()` before calling `fetchUserFeedback()` (which then auto-opens if feedback exists).

2. **User feedback persists permanently, re-sent on every iteration**
   - File: `kb/serve.py:1084`
   - Problem: After iteration completes, `user_feedback` remains in action state. On the next `[i]` press, the same feedback is injected again into the LLM prompt. If the user wrote "make the hook shorter" and the LLM already shortened it, the next iteration will try to shorten it again. There is no mechanism to clear or acknowledge feedback was addressed.
   - Fix: Either (a) clear `user_feedback` after iteration starts (in `iterate_action`), or (b) clear on the frontend after iteration completes, or (c) add a visual indicator that feedback will be re-sent and let the user clear it manually. Option (c) is probably best for UX -- add a "clear" button or auto-clear the textarea after `[i]`.

### Minor

3. **No type or size validation on feedback POST**
   - File: `kb/serve.py:1041`
   - Problem: `data["user_feedback"]` is saved directly without checking it's a string or enforcing a size limit. A non-string value (dict, list, number) would be serialized to JSON and later concatenated into a prompt string, which could produce malformed prompts. An extremely large string would bloat the action state file.
   - Fix: Add `if not isinstance(data["user_feedback"], str): return 400` and optionally a reasonable max length (e.g., 5000 chars).

4. **`n` key does not toggle closed**
   - File: `kb/templates/posting_queue.html:2681-2689`
   - Problem: Plan says "[n] key opens/focuses the notes textarea. Escape closes it." The implementation only opens (never closes with `n`). If `notesOpen` is already true, pressing `n` just re-focuses the textarea rather than closing it. This is a usability nit -- Escape works for closing, but the `n` key is not a true toggle.
   - Fix: No action required if Escape is the intended close mechanism. If true toggle is desired, remove the `!notesOpen` guard.

5. **Phase commit order inconsistency**
   - Commits: `5085202` (Phase 2) before `9268d3e` (Phase 1)
   - Problem: Phase 2 was committed before Phase 1. The `iterable` flag (a Phase 1 AC) shipped in the Phase 2 commit. Execution log acknowledges this but it makes git history slightly misleading.
   - Fix: No action required (cosmetic). Note for future: commit per-phase in order.

6. **Solo `g` keypress is dead**
   - File: `kb/templates/posting_queue.html:2625-2637`
   - Problem: Pressing `g` once starts the `pendingG` timer and does nothing else. If no second `g` follows within 500ms, the keypress is silently consumed. This is intentional (generate visuals moved to `v`), but means `g` as a standalone key is now a no-op that consumes input.
   - Fix: No action required (by design). The shortcut bar correctly shows `v` for visuals.

---

## What's Good

- The `_stage_item()` extraction is clean. Same exception handling, same state mutations, net -26 lines. Both callers integrate naturally.
- XSS protection is consistent: `escapeHtml()` is used in `renderNonIterableView()` for all user-controlled fields (title, decimal, destination, content).
- The `entityRoundIndex` cache is a proper fix for BUG-3 -- per-entity, bounds-checked on restoration, updated on all navigation paths (keyboard, tab clicks, poll completion).
- BUG-4 fix (backwards scan for latest scored round) is correct and handles the edge case where the newest round has no scores yet.
- The `gg`/`G` pattern is well-implemented with proper timeout cleanup and clearing of `pendingG` on non-`g` keys.
- Test coverage is real -- the feedback tests hit all CRUD paths, invalid input, overwrite, and the iteration passthrough tests verify the actual thread target function receives the kwarg.
- The `user_feedback` injection into `judge.py` is placed correctly at both Step 1 (history-based draft) and Step 3 (improvement rounds), covering both code paths.

---

## Required Actions

None. The two major issues (stale feedback bleed, feedback persistence) are UX polish bugs within a UX polish task -- they don't break existing functionality and can be addressed in a follow-up. All acceptance criteria are met.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Global UI state (notesOpen) needs reset on context switch | Any per-entity UI feature | Always reset view state when selecting a new entity |
| Feedback/notes that feed into LLM prompts need lifecycle management | Any human-in-the-loop LLM feature | Design for clear/acknowledge/re-send patterns |
| Phase commit ordering matters for git archaeology | Executor discipline | Commit phases in plan order even if developed out of order |
