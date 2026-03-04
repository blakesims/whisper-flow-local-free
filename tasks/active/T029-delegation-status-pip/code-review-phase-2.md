# Code Review: Phase 2

## Gate: REVISE

**Summary:** Core layout infrastructure is solid and tests are comprehensive, but two issues need fixing: pip timers are not stopped on removal (resource leak / ghost callbacks), and the idle-state cyan dot can visually overlap with pip widgets due to conflicting manual paint vs. layout positioning.

---

## Git Reality Check

**Commits:**
```
3cf87df T029 Phase 2: integrate DelegationPip into RecordingIndicator layout
279042b T029: update main.md with Phase 2 execution log, set status CODE_REVIEW
```

**Files Changed:**
- `app/daemon/recording_indicator.py` -- pip container, add/remove methods, sizing adjustments, idle dot shift
- `tests/test_pip_layout.py` -- 19 new tests

**Matches Execution Report:** Yes. All claimed files and changes match the diff.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Pip right of cyan dot in idle | Yes | Partially | Cyan dot is manually painted at x=18; pip_layout starts at x=8 from left margin. Hidden widgets take 0 space, so layout places pips starting near x=8. The 11px pip (x=8 to x=19) overlaps the 8px cyan dot (x=14 to x=22). See Issue 1. |
| AC2: Pip right of waveform during recording | Yes | Yes | pip_layout is added to _layout after waveform widget. During recording, waveform is visible and takes space, pushing pip_layout to the right. Correct. |
| AC3: Multiple pips stack with 3px spacing | Yes | Yes | `_pip_layout.setSpacing(3)` confirmed. `test_add_multiple_pips` verifies layout.count()==3. |
| AC4: Pill width adjusts on add/remove | Yes | Yes | `_refresh_pill_size` called from both add and remove. Tests verify width grows and shrinks. No animation (just instant resize), but AC says "adjusts" not "animates." |

---

## Issues Found

### Critical
None.

### Major

1. **Pip timers not stopped on removal**
   - File: `/Users/blake/projects/whisper-transcribe-ui/app/daemon/recording_indicator.py:901-908`
   - Problem: `remove_delegation_pip()` calls `pip.deleteLater()` but never stops the pip's active timers (`_pulse_timer`, `_fade_timer`, `_flash_timer`). Between `deleteLater()` and actual deletion, timers keep firing. Verified: a PROCESSING pip's `_pulse_timer.isActive()` remains `True` after `remove_delegation_pip()`. This means `_pulse_tick` fires on a pip that's been removed from the list and unparented -- a ghost callback that could cause issues if the pip references parent state.
   - Fix: Call `pip._stop_all_timers()` at the start of `remove_delegation_pip()`, before removing from the list.

2. **Idle cyan dot overlaps pip position**
   - File: `/Users/blake/projects/whisper-transcribe-ui/app/daemon/recording_indicator.py:997-1009` and the layout setup
   - Problem: In idle state, the cyan dot is painted manually at x=18 in `paintEvent`. But the `_pip_layout` is positioned by Qt's layout engine starting from x=8 (the left margin). Since all widgets before `_pip_layout` are hidden (and take 0 space), pips render starting at x=8. An 11px-wide pip (x=8 to x=19) overlaps the cyan dot (center x=18, radius 4, spanning x=14 to x=22). AC1 says "pip appears to the right of cyan dot" -- this won't look right.
   - Fix: Add a fixed-width spacer (or invisible QWidget) before `_pip_layout` that is shown only in idle state to push pips past the cyan dot area. Alternatively, shift the cyan dot further left or add the dot as a real widget so the layout handles positioning.

### Minor

1. **Test `test_failed_pips_removed_on_recording_start` calls `_remove_failed_pips()` directly instead of `_set_recording_state()`**
   - The test claims to verify "FAILED pips cleared when user starts a new recording" but calls the private method directly, not the actual `_set_recording_state()` path. While `_set_recording_state` does call `_remove_failed_pips()` (verified separately), the test would be more valuable testing the real entry point. Low severity since the wiring is confirmed working.

2. **Duplicated sizing logic between `_set_*_state()` methods and `_refresh_pill_size()`**
   - The idle/recording/transcribing/cancelled width calculations exist in both the state setters and in `_refresh_pill_size()`. If base widths change, both need updating. Consider having the state setters call `_refresh_pill_size()` instead of duplicating the math. This is minor since Phase 2 is self-consistent.

---

## What's Good

- `_pip_width_extra()` calculation is clean and correct: `4 + (n * 11) + ((n - 1) * 3)`
- `remove_delegation_pip` handles the "not in list" case gracefully
- Lambda closure in `add_delegation_pip` correctly captures the pip reference (verified: middle-of-list removal works)
- All 4 states (idle, recording, transcribing, cancelled) properly account for pip width
- `_remove_failed_pips` correctly filters by state -- SENT and PROCESSING pips survive
- Test coverage is good: 19 tests cover container setup, add/remove, sizing, cleanup, and refresh in all states

---

## Required Actions (for REVISE)

- [ ] Fix: Call `pip._stop_all_timers()` in `remove_delegation_pip()` before `deleteLater()`
- [ ] Fix: Prevent idle-state visual overlap between manually-painted cyan dot and layout-positioned pips (spacer, widget, or repositioned dot)
- [ ] Optional: Add a test for timer cleanup on removal

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| `deleteLater()` does not stop QTimers -- they fire until event loop processes deletion | Any Qt widget removal | Always stop timers before deleteLater |
| Manually-painted elements don't participate in layout positioning -- mixing approaches causes overlap | Qt paintEvent + QHBoxLayout | Use real widgets or explicit spacers when layout matters |
