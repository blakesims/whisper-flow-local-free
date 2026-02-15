# Code Review: Phase 1

## Gate: REVISE

**Summary:** The DelegationPip widget is structurally sound and follows existing patterns well, but has a critical signal-accumulation bug on `_fade_timer` that causes FAILED state to animate at the wrong speed and corrupts behavior across state transitions. The rename refactor bundled alongside is clean but uncommitted. No tests.

---

## Git Reality Check

**Commits:** None for T029. All changes are unstaged working-tree modifications.

**Files Changed (unstaged):**
- `app/daemon/recording_indicator.py` -- DelegationPip class + issue->delegation renames
- `app/daemon/whisper_daemon.py` -- issue_capture->delegation renames + formatting
- `app/daemon/hotkey_listener.py` -- issue_capture->delegation rename
- `CLAUDE.md` -- docs update for Option+F hotkey
- `tasks/global-task-manager.md` -- task tracking

**Matches Execution Report:** Partially. Execution log only mentions `recording_indicator.py` but 4 other files were also modified (rename refactor). The execution log claims Phase 1 Status: COMPLETE but `main.md` Status field still says `EXECUTING_PHASE_1` (should be `CODE_REVIEW`).

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: 7px dot, correct colors | Yes | YES | Widget is 11px (7+4 margin), draws 7px circle. Colors correct: orange/SENT, orange/PROCESSING, green/COMPLETE, red/FAILED |
| AC2: Pulse matches PulsingDot | Yes | YES | Same 40ms interval, 0.04 step, 0.4-1.0 range as PulsingDot._pulse() |
| AC3: COMPLETE fades 3s + finished signal | Yes | PARTIAL | Fade math is correct (75 ticks x 40ms x 0.013 decrement). Signal emits. But see bug below -- if FAILED preceded COMPLETE, `_settle_tick` is still connected and corrupts the fade. |
| AC4: FAILED settles at 0.35 | Yes | NO | Due to dual-handler bug, FAILED settle runs _fade_tick (0.013/tick) AND _settle_tick (0.033/tick) simultaneously = 0.046/tick total. Reaches 0.35 in ~14 ticks (~0.56s) instead of intended ~20 ticks (~0.8s). More critically, _fade_tick will keep decrementing past 0.35 to 0.0 and emit `finished` signal -- meaning FAILED pips emit `finished` as if they were COMPLETE. |

---

## Issues Found

### Critical

1. **`_fade_timer` dual-handler signal accumulation**
   - File: `app/daemon/recording_indicator.py:310,395`
   - Problem: `_fade_timer.timeout` is permanently connected to `_fade_tick` in `__init__` (line 310). When `_start_failed_settle` runs (line 395), it connects `_settle_tick` to the same timer WITHOUT disconnecting `_fade_tick`. Both handlers fire on every tick. This causes:
     - FAILED state: fade is 2x faster than intended (0.046/tick instead of 0.033)
     - FAILED state: `_fade_tick` decrements past 0.35 to 0.0 and emits `finished` signal -- parent will remove FAILED pips as if they completed successfully
     - COMPLETE after FAILED: `_settle_tick` remains connected, corrupting the COMPLETE fade
   - Fix: Do not connect `_fade_tick` in `__init__`. Instead, manage `_fade_timer` connections dynamically in `_start_complete_fade` and `_start_failed_settle`, always disconnecting first. Or use two separate timers. The cleanest fix is to have `_stop_all_timers` also disconnect `_fade_timer.timeout` (like it does for `_flash_timer`), and have `_start_complete_fade` explicitly connect `_fade_tick`.
   - Verified: Ran manual test -- after `_start_failed_settle()`, calling `_fade_tick` and `_settle_tick` independently both execute, confirming combined decrement of 0.046 per tick.

### Major

1. **Misleading comment on FAILED flash hold duration**
   - File: `app/daemon/recording_indicator.py:346`
   - Problem: Comment says "Settle to dim after flash (2s)" but the timer is set to 200ms. The 200ms value is likely correct (a brief visual flash), but the comment is confusing and suggests the implementer may have intended a longer hold.
   - Fix: Change comment to "Settle to dim after brief flash (200ms)".

2. **No cleanup of `_settle_tick` connection across state transitions**
   - File: `app/daemon/recording_indicator.py:350-358`
   - Problem: `_stop_all_timers` disconnects `_flash_timer.timeout` but does NOT disconnect `_fade_timer.timeout`. The `_settle_tick` handler added by `_start_failed_settle` persists across transitions. If a pip goes FAILED -> PROCESSING -> COMPLETE, the `_settle_tick` from the FAILED phase is still connected to `_fade_timer` and will fire during the COMPLETE fade.
   - Fix: Add `self._fade_timer.timeout.disconnect()` (with try/except) to `_stop_all_timers`, alongside the flash timer disconnect. Then reconnect the appropriate handler in each `_start_*` method.

3. **No tests for DelegationPip**
   - Problem: No unit tests were written for this widget. The AC were "verified via import test" per the execution log, which is not a real test. State transition logic, timer behavior, and signal emission should all have tests given this is Phase 1 -- later phases will build on this foundation.
   - Fix: Add tests covering at minimum: initial state, each state transition's color/opacity, the finished signal emission on COMPLETE, and that FAILED does NOT emit finished.

### Minor

1. **Scope creep: issue_capture -> delegation rename across 4 files**
   - The execution log for Phase 1 claims only `recording_indicator.py` was modified. In reality, `whisper_daemon.py`, `hotkey_listener.py`, and `CLAUDE.md` also received substantial rename refactoring (issue_capture -> delegation). This is fine work but is not Phase 1 scope and should be documented separately or acknowledged in the execution log.

2. **`whisper_daemon.py` formatting churn**
   - The diff includes extensive quote-style changes (single to double quotes), import reordering, and line wrapping that are unrelated to T029. This appears to be auto-formatter output. Not harmful but muddies the diff.

---

## What's Good

- The widget structure closely mirrors `PulsingDot`, making it easy to understand for anyone familiar with the codebase
- State constants as class attributes is clean
- The `_stop_all_timers` pattern (even if incomplete) shows awareness of timer lifecycle management
- Pulse animation parameters exactly match PulsingDot (40ms/0.04/0.4-1.0), fulfilling AC2 precisely
- The `finished` signal design for parent cleanup is well-thought-out
- The `paintEvent` is minimal and correct

---

## Required Actions (for REVISE)

- [ ] Fix: Restructure `_fade_timer` connection management -- do NOT connect `_fade_tick` in `__init__`. Connect handlers dynamically in `_start_complete_fade` and `_start_failed_settle`, with full disconnection in `_stop_all_timers`
- [ ] Fix: Update `_stop_all_timers` to also disconnect `_fade_timer.timeout`
- [ ] Fix: Correct the "2s" comment on line 346 to "200ms"
- [ ] Verify: After fix, FAILED state must NOT emit `finished` signal
- [ ] Verify: After fix, FAILED -> COMPLETE transition fades correctly without `_settle_tick` interference

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Shared QTimers with dynamically-connected slots need full disconnect on state change | Any timer-based animation | Always disconnect ALL slots from shared timers before reconnecting |
| `__init__` signal connections persist across state changes | Qt signal/slot patterns | Prefer dynamic connection management for timers shared across states, or use separate timers per state |
