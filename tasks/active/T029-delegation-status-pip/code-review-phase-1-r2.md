# Code Review: Phase 1 (Re-review after REVISE)

## Gate: PASS

**Summary:** The critical dual-handler signal accumulation bug is fixed correctly. All five required actions from the initial review are addressed. 16 tests pass and directly verify the bug cannot recur. Two minor observations remain but neither blocks progress.

---

## Git Reality Check

**Commits:**
```
e1b7410 T029 Phase 1 REVISE: fix _fade_timer dual-handler signal accumulation
```

**Files Changed (in commit):**
- `app/daemon/recording_indicator.py` -- DelegationPip class rewritten with dynamic-only timer connections
- `tests/test_delegation_pip.py` -- 16 new tests

**Unstaged files (from prior work, not Phase 1 scope):**
- `app/daemon/whisper_daemon.py` -- issue_capture -> delegation rename + formatter churn
- `app/daemon/hotkey_listener.py` -- issue_capture -> delegation rename
- `CLAUDE.md` -- docs update for Option+F hotkey
- `tasks/global-task-manager.md` -- task tracking

**Matches Execution Report:** Yes. Commit `e1b7410` contains exactly the two files claimed. Unstaged rename work is documented separately in Notes section.

---

## Previous Required Actions Verification

| # | Required Action | Status | Verification |
|---|----------------|--------|-------------|
| 1 | Restructure `_fade_timer` -- no connect in `__init__`, dynamic only | DONE | Line 309: `self._fade_timer = QTimer(self)` with no `.connect()`. Handlers connected in `_start_complete_fade` (line 382) and `_start_failed_settle` (line 403) |
| 2 | `_stop_all_timers` must disconnect `_fade_timer.timeout` | DONE | Lines 353-356: `self._fade_timer.timeout.disconnect()` with try/except |
| 3 | Correct "2s" comment to "200ms" | DONE | Line 345: "Settle to dim after brief flash (200ms)" |
| 4 | FAILED state must NOT emit `finished` | VERIFIED | Test `test_settle_tick_does_not_emit_finished` runs 100 ticks, asserts 0 emissions. Code path confirmed: `_settle_tick` clamps at 0.35 and stops timer, never calls `finished.emit()` |
| 5 | FAILED->COMPLETE transition fades correctly without `_settle_tick` interference | VERIFIED | Test `test_no_dual_handlers_complete_after_failed` confirms: after FAILED settle, transitioning to COMPLETE yields 0 receivers, then `_start_complete_fade` yields exactly 1 receiver |

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: 7px dot, correct colors | Yes | YES | Widget 11px (7+4), colors: orange/SENT, orange/PROCESSING, green/COMPLETE, red/FAILED. Test coverage for all four states. |
| AC2: Pulse matches PulsingDot | Yes | YES | Same 40ms interval, 0.04 step, 0.4-1.0 range |
| AC3: COMPLETE fades 3s + finished signal | Yes | YES | 75 ticks x 40ms, 0.013 decrement. `test_fade_tick_emits_finished_once` verifies exactly 1 emission at opacity 0.0 |
| AC4: FAILED settles at 0.35, no finished | Yes | YES | `test_failed_opacity_settles_at_035` verifies. `test_settle_tick_does_not_emit_finished` confirms no signal |

---

## Issues Found

### Minor

1. **RuntimeWarnings from disconnect-when-nothing-connected pattern**
   - File: `app/daemon/recording_indicator.py:354,358,379,400`
   - Problem: `_stop_all_timers` and `_start_*` methods call `.timeout.disconnect()` even when no handler is connected. Qt emits `RuntimeWarning: Failed to disconnect (None) from signal "timeout()"`. Produces 33 warnings during the test run. Not a functional issue -- the try/except catches it. But noisy in test output.
   - Fix: Could check `receivers(SIGNAL("timeout()"))` before disconnecting, or suppress the warning. Low priority -- does not affect behavior.

2. **Unstaged rename churn in whisper_daemon.py**
   - The `issue_capture -> delegation` rename and auto-formatter changes in `whisper_daemon.py` remain unstaged from before the REVISE commit. This is documented in the task notes and is not Phase 1 scope, but should be committed as part of Phase 2 or a separate cleanup commit to avoid an ever-growing unstaged diff.

---

## What's Good

- The fix is exactly what the review asked for -- no over-engineering, no under-engineering
- Dynamic connection pattern with disconnect-before-connect is the right Qt idiom for shared timers
- Tests directly target the specific bug: receiver counts, cross-state transitions, signal emission guarantees
- Test structure is well-organized into logical groups (Init, States, FadeTimerConnections, FailedDoesNotEmitFinished, CompleteFadeEmitsFinished)
- The `_stop_all_timers` method is now comprehensive -- disconnects both `_fade_timer` and `_flash_timer`

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Qt `disconnect()` on unconnected signal emits RuntimeWarning even inside try/except | PySide6 signal management | Check `receivers()` count before disconnect, or accept the warnings |
| Testing receiver counts via `receivers(SIGNAL("timeout()"))` is an effective way to verify signal wiring | Qt widget unit testing | Reuse this pattern for future timer-based widget tests |
