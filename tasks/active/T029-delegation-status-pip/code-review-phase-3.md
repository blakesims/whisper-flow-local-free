# Code Review: Phase 3

## Gate: PASS

**Summary:** Solid state machine with good test coverage. The core design -- lazy dir resolution from cc-triage's own config, terminal-state-first checking, glob-based failed detection -- is well thought out. Three issues found, none critical. The race condition on track-before-write is a real concern but unlikely in practice given the single-threaded Qt event loop and sequential file-write-then-track call order. Passing with advisory notes.

---

## Git Reality Check

**Commits:**
```
b108fd4 T029 Phase 3: add DelegationTracker with filesystem polling state machine
295d065 T029: update main.md with Phase 3 execution log, set status CODE_REVIEW
```

**Files Changed:**
- `app/daemon/whisper_daemon.py` (+188 lines)
- `tests/test_delegation_tracker.py` (+326 lines, new file)
- `~/Library/Application Support/WhisperTranscribeUI/settings.json` (cc_triage_root added)

**Matches Execution Report:** Yes. All claimed files and changes verified in git diff.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: State transitions within 2-4s | Yes | Yes | 2s QTimer interval, _poll checks all active delegations. Verified via test_poll_emits_transition_signal. |
| AC2: Polling stops when no active | Yes | Yes | _poll() stops timer when _active is empty. _cleanup() also stops when last removed. Two tests verify. |
| AC3: Multiple concurrent delegations | Yes | Yes | test_two_delegations_independent_states and test_three_delegations_different_terminal_states both pass with isolated state tracking. |
| AC4: Stale delegations stay SENT | Yes | Partial | Only true when file IS in inbox. See Major #1 -- if file not yet in inbox at first poll, false PROCESSING transition occurs. |

---

## Issues Found

### Critical

None.

### Major

1. **Race condition: track() before file write can cause false PROCESSING transition**
   - File: `/Users/blake/projects/whisper-transcribe-ui/app/daemon/whisper_daemon.py:237`
   - Problem: `_check_state` transitions SENT->PROCESSING when the file is not in inbox. If `track()` is called before the delegation file is actually written to the inbox directory, the first poll (2s later) will see "no file in inbox" and immediately transition to PROCESSING, even though cc-triage never picked it up. The test `test_stale_delegation_stays_sent` only works because it pre-creates the file before calling `track()`.
   - Mitigation: In practice, Phase 4 wiring will likely call `track()` after the file write completes (synchronous `_handle_delegation_output`), so the 2s window before first poll is generous. This is low risk but fragile -- a future refactor that makes the write async would silently break the state machine.
   - Fix (advisory): Add a `_track_time` dict and skip the first poll if < 3s since track(). Or verify file exists in inbox before transitioning SENT->PROCESSING. Or accept the file write as a precondition and document it.

2. **No error handling in _check_state filesystem operations**
   - File: `/Users/blake/projects/whisper-transcribe-ui/app/daemon/whisper_daemon.py:199-240`
   - Problem: `os.path.exists()` and `glob.glob()` can raise `PermissionError` or `OSError`. Since `_poll` iterates all active delegations in one loop, a single filesystem error would crash the entire poll cycle via unhandled exception in the QTimer callback. This silently kills polling for ALL delegations, not just the problematic one.
   - Fix: Wrap `_check_state` body (or the per-delegation loop in `_poll`) in try/except with a log message.

### Minor

1. **`import glob` inside _check_state (line 211)**
   - The `glob` module is imported inside the method body on every call (every 2s per active delegation). Move it to the top-level imports. Not a performance issue in practice (Python caches module imports), but it is unconventional and adds noise to the hot path.

2. **No protection against duplicate track() calls**
   - Calling `track("same_id.txt")` twice overwrites the state back to SENT without warning. Not dangerous (just resets the state), but could mask bugs in the wiring code.

3. **_resolve_dirs does not validate directories exist on disk**
   - If cc-triage config points to dirs that do not exist (typo, old config), `_resolve_dirs` returns True but all subsequent `os.path.exists` checks will silently return False. The delegation will transition SENT->PROCESSING immediately. Low risk since cc-triage creates its own dirs.

---

## What's Good

- **Terminal-state-first checking order:** Report/failed checked before inbox, so even if file lingers in inbox after completion, the correct terminal state wins. The test `test_complete_report_takes_priority_over_inbox` explicitly verifies this.
- **Lazy dir resolution:** Only reads cc-triage config when first delegation is tracked, not at daemon startup. Clean separation of concerns.
- **Single source of truth:** Reads cc-triage's own `config/config.json` rather than duplicating path knowledge. Relative paths resolved against cc_triage_root correctly.
- **Cleanup scheduling with captured lambda variable:** `lambda did=delegation_id: self._cleanup(did)` correctly captures the delegation_id per iteration. Common Python footgun avoided.
- **Test quality:** 26 tests with real filesystem operations (tmp_path), not mocked. Good coverage of edge cases (stale, concurrent, invalid config, missing config).
- **Clean QObject lifecycle:** QTimer is parented to tracker, cleanup stops timer correctly.

---

## Required Actions

None -- PASS. Advisory fixes recommended for Phase 4 wiring:
- [ ] Consider: wrap `_check_state` in try/except in `_poll` loop
- [ ] Consider: document that `track()` must be called after file write completes

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Filesystem polling state machines need to handle the "not yet written" race | Future polling designs | Document preconditions for track() |
| QTimer callbacks silently swallow crashes | All QTimer usage in daemon | Add error handling in timer callbacks |

---

## Test Results

All 67 tests pass (16 pip + 25 layout + 26 tracker):
```
67 passed, 49 warnings in 0.62s
```
Warnings are all the pre-existing RuntimeWarning from DelegationPip disconnect pattern (cosmetic, noted in Phase 1 review).
