# T029: Review UX Polish — Bugs + Vim Nav + Manual Feedback

## Meta
- **Status:** ACTIVE
- **Created:** 2026-02-10
- **Priority:** 2
- **Depends on:** T028

## Task

Fix bugs found during T028 smoke testing and add UX improvements to the Review/posting queue view. Covers: round navigation state persistence, judge scores visibility, 400 cleanup for non-iterable types, duplicated staging logic extraction, vim-style keybindings (h/l for rounds, gg/G for jump), and manual feedback/notes input before iteration.

## Context

After T028 shipped (Queue/Review state machine), Blake smoke-tested on Mac and found:
- BUG-2 (CRITICAL) — already fixed in `9a91d37`
- BUG-3: Round navigation state resets when switching between items
- BUG-4: Judge scores only visible intermittently
- 400 errors from frontend calling /iterations for non-iterable types
- UX: Arrow keys for rounds should be h/l (vim-consistent)
- UX: No gg/G to jump to top/bottom of entity list
- UX: No way to input manual feedback/notes before triggering iteration

Blake's design preference: Study the vim motion patterns from his calendar/planner frontend for inspiration on navigation consistency.

---

## Phase 1: Bug Fixes (BUG-3 + BUG-4 + 400 cleanup)

**Goal:** Fix the three remaining bugs from smoke testing.

### Task 1.1: Fix round navigation state loss (BUG-3)
- **Problem:** `selectedRoundIndex` resets to latest round every time `fetchIterations()` is called. When user navigates away and back, `selectEntity()` re-calls `fetchIterations()` which resets the index.
- **Fix:** Cache `selectedRoundIndex` per entity in a map (e.g. `entityRoundIndex = {}`). On `fetchIterations()`, restore from cache if available instead of defaulting to latest. On arrow key round change, update the cache.
- **Files:** `kb/templates/posting_queue.html` (~line 1099 state, ~line 1350 fetchIterations, ~line 1321 selectEntity)
- **AC:** Navigate to item A round 2, switch to item B, switch back to A → still shows round 2.

### Task 1.2: Fix judge scores visibility (BUG-4)
- **Problem:** After iteration completes, `selectedRoundIndex` resets to latest round via `pollIteration()`. If latest round doesn't have judge data yet, scores disappear. Also, scores section is blank when `current.scores` is null.
- **Fix:**
  1. After poll completion, set `selectedRoundIndex` to the latest round that HAS scores (scan backwards from end)
  2. Always show scores section — if no scores, show "Judging..." or "Awaiting judge" instead of blank
- **Files:** `kb/templates/posting_queue.html` (~line 1405 scores rendering, ~line 1615 pollIteration)
- **AC:** After iteration completes, view shows the round with scores. No blank scores sections.

### Task 1.3: Fix 400s for non-iterable types
- **Problem:** Frontend calls `/api/action/{id}/iterations` for ALL items in Review, including `linkedin_post` which returns 400 because it's not in `AUTO_JUDGE_TYPES`.
- **Fix:** In `selectEntity()` or `fetchIterations()`, check if the entity's analysis type supports iteration before calling the endpoint. The entity data from `/api/posting-queue-v2` includes the analysis type.
- **Approach:** Extract analysis type from action ID (split on `--`, take second part). Skip `/iterations` call if type is not in a client-side list of iterable types. For now, hardcode `['linkedin_v2']` — or better, add an `iterable` boolean to the queue API response.
- **Files:** `kb/templates/posting_queue.html` (fetchIterations), optionally `kb/serve.py` (posting-queue-v2 endpoint to add `iterable` flag)
- **AC:** No 400 errors in server logs when browsing Review items. Non-iterable items show clean "Not iterable" state instead of error.

### Phase 1 AC
- All three bugs verified fixed
- No test regressions (run full test suite)

---

## Phase 2: Code Cleanup — Extract Duplicated Staging Logic

**Goal:** DRY up the shared staging logic between `approve_action()` and `stage_action()`.

### Task 2.1: Extract `_stage_item()` helper
- **Problem:** `approve_action()` and `stage_action()` share ~30 lines of edit version creation code (both set status to "staged", set staged_at, create initial edit version from analysis content).
- **Fix:** Extract a shared helper `_stage_item(action_id, state, transcript_path)` that handles:
  1. Set status to "staged" + staged_at timestamp
  2. Create initial edit version from analysis content
  3. Save state
- Both `approve_action()` (for AUTO_JUDGE_TYPES) and `stage_action()` call this helper.
- **Files:** `kb/serve.py` (~line 355 approve_action, ~line 428 stage_action)
- **AC:** Both endpoints produce identical behavior to before. Shared code in one place. All existing tests pass.

---

## Phase 3: Vim Keybindings — h/l for Rounds, gg/G for Jump

**Goal:** Make Review navigation consistent with vim conventions.

### Task 3.1: Replace ArrowUp/ArrowDown with h/l for round navigation
- **Current:** ArrowDown = next round, ArrowUp = prev round
- **New:** `l` = next round (right = forward in time), `h` = prev round (left = back in time)
- Keep ArrowUp/ArrowDown as aliases for backwards compat
- **Files:** `kb/templates/posting_queue.html` (~line 2413 keydown handler)

### Task 3.2: Add gg/G for jump to top/bottom of entity list
- **Problem:** No way to quickly jump to first/last item
- **Fix:** Track key sequences. `G` = jump to last item. `gg` (two g presses within 500ms) = jump to first item.
- Implementation: track `lastKeyTime` and `lastKey`. On `g` press, if last key was also `g` within 500ms, jump to first. On `G` (shift+g), jump to last.
- **Files:** `kb/templates/posting_queue.html` (keydown handler)
- **AC:** `G` selects last entity, `gg` selects first entity, `h/l` navigate rounds.

### Task 3.3: Study calendar/planner app for additional patterns
- Before implementing, inspect Blake's calendar/planner frontend for vim motion patterns
- Look for: key sequence handling, modal states, navigation consistency
- Apply any relevant patterns found

---

## Phase 4: Manual Feedback/Notes Input

**Goal:** Allow Blake to type manual feedback before triggering iteration.

### Task 4.1: Add notes textarea to iteration view
- **Concept:** When viewing a staged item, show a collapsible text area for "Your feedback". Content persists per-entity in action state.
- **Trigger:** `[n]` key opens/focuses the notes textarea. `Escape` closes it and returns focus to main navigation.
- **Storage:** Save notes to `state["actions"][action_id]["user_feedback"]` via new endpoint `POST /api/action/{id}/feedback`
- **Files:** `kb/templates/posting_queue.html` (UI), `kb/serve.py` (endpoint)

### Task 4.2: Pass user feedback to iteration
- When `[i]` is pressed and user_feedback exists, include it in the iteration prompt as additional context
- The judge loop should consider user feedback alongside its own evaluation
- **Files:** `kb/serve.py` (iterate_action), `kb/judge.py` (run_with_judge_loop — check if it accepts user feedback param)
- **AC:** User types "make the hook shorter", presses [i], iteration produces a version that addresses the feedback.

---

## Phase 5: Test + Verify

### Task 5.1: Add tests for new functionality
- Round state persistence (mock entity switching)
- gg/G navigation
- Manual feedback storage endpoint
- Feedback passed to iteration

### Task 5.2: Full regression test
- Run full test suite
- Verify no regressions

---

## Execution Log

_(to be filled during execution)_
