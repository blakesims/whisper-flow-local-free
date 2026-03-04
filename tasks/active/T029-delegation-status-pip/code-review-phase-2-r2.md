# Code Review: Phase 2 (Re-review)

## Gate: PASS

**Summary:** Both REVISE items fixed correctly. Timer cleanup on removal verified by test and code inspection. Idle spacer geometry confirmed: pip renders at x=30, clearing the cyan dot (x=14-22) with margin. All 41 tests pass. One minor test quality nit carried over from prior review.

---

## Git Reality Check

**Commits:**
```
23e528a T029 Phase 2 REVISE: stop pip timers on removal, add idle spacer for cyan dot
4042e1e T029: update main.md with Phase 2 REVISE log, set status CODE_REVIEW
```

**Files Changed:**
- `app/daemon/recording_indicator.py` -- spacer widget, timer stop in remove, spacer show/hide in state setters and refresh
- `tests/test_pip_layout.py` -- 6 new tests (timer cleanup + spacer)

**Matches Execution Report:** Yes. All claimed changes verified in diff.

---

## REVISE Item Verification

| REVISE Item | Fix Claimed | Verified | Notes |
|-------------|-------------|----------|-------|
| Pip timers not stopped on removal | `pip._stop_all_timers()` before `deleteLater()` | Yes | Line 919: called before list removal. Test `test_processing_pip_timers_stopped_on_remove` confirms `_pulse_timer.isActive()` is False after removal. |
| Idle cyan dot overlaps pip position | 16px `_idle_pip_spacer` before `_pip_layout` | Yes | Spacer at x=8 (left margin) spans to x=24. Layout spacing 6px. Pip starts at x=30, which clears cyan dot right edge (x=22) by 8px. |

---

## AC Re-verification

| AC | Verified | Notes |
|----|----------|-------|
| AC1: Pip right of cyan dot in idle | Yes | Spacer pushes pip to x=30, past cyan dot at x=14-22. |
| AC2: Pip right of waveform during recording | Yes | Unchanged from initial review. Spacer hidden in recording state. |
| AC3: Multiple pips stack with 3px spacing | Yes | Unchanged. |
| AC4: Pill width adjusts on add/remove | Yes | `_refresh_pill_size` manages spacer visibility for idle state. |

---

## Test Results

All 41 tests pass (25 layout + 16 pip):
```
41 passed, 49 warnings in 0.20s
```

RuntimeWarnings from `_fade_timer.timeout.disconnect()` persist (cosmetic only, noted in Phase 1 re-review as accepted minor).

---

## Issues Found

### Critical
None.

### Major
None.

### Minor

1. **Tautological spacer test in recording state**
   - File: `/Users/blake/projects/whisper-transcribe-ui/tests/test_pip_layout.py:184-189`
   - `test_spacer_hidden_in_recording_state` manually sets `_state = STATE_RECORDING` and manually calls `_idle_pip_spacer.hide()`, then asserts `isHidden()`. This proves the `.hide()` method works, not that `_set_recording_state()` hides the spacer. Should call the real state setter instead.
   - Severity: Genuinely minor. The actual wiring is correct (verified in diff: `_set_recording_state` calls `self._idle_pip_spacer.hide()` at line 687). The test just does not exercise that path.

---

## What's Good

- Timer cleanup is in the right place: before list removal, before `deleteLater()`. Clean ordering.
- Spacer approach is minimal and non-invasive. Hidden in all non-idle states. No layout engine hacks.
- `_refresh_pill_size` correctly mirrors the spacer logic from `_set_idle_state`, handling the case where pips are removed while in idle state.
- New tests directly target the exact bugs from the REVISE (timer active check, spacer visibility lifecycle).

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Test state transitions through public methods, not by manually setting internal state | All Qt widget tests | Prefer calling real state setters in tests |
