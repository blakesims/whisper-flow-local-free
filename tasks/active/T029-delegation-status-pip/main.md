# Task: Delegation Status Pip — Visual Feedback on Pill Indicator

## Task ID
T029

## Status: CODE_REVIEW

## Overview
After an Opt+F delegation recording, the whisper daemon's floating pill should show a small pip that visually tracks the delegation lifecycle through cc-triage's filesystem signals. The pip appears after delegation is saved, pulses during processing, flashes green on success, and shows red on failure. It coexists with normal recording without interfering.

## Objectives
- Add a `DelegationPip` widget to the pill that tracks delegation state
- Poll cc-triage's filesystem to detect state transitions (sent → processing → complete/failed)
- Support multiple concurrent delegations
- Ensure normal Ctrl+F recording works alongside active delegation pips

## Dependencies
- None (builds on delegation rename already done in this session)

## Rules Required
- None

## Resources & References
- Mockup: `/tmp/whisper-pill-mockup-v1.html`
- cc-triage dirs: `inbox/`, `reports/`, `failed/` under delegation_path parent
- cc-triage report naming: `triage_<original_stem>.json`
- cc-triage failed naming: `<original_stem>_<timestamp>.txt` (moved to `failed/`)
- Existing pill code: `app/daemon/recording_indicator.py`
- Daemon orchestration: `app/daemon/whisper_daemon.py`

## Plan

### Objective
After Opt+F delegation, show a subtle pip on the pill that tracks the delegation through cc-triage processing, providing at-a-glance feedback without interfering with normal recording.

### Scope
- **In:** DelegationPip widget, filesystem polling, state transitions, coexistence with recording states, multiple concurrent delegations
- **Out:** Changes to cc-triage itself, IPC/socket communication, delegation history/logs UI

### Phases

#### Phase 1: DelegationPip Widget
- **Objective:** Create the pip widget with all visual states
- **Tasks:**
  - [ ] Task 1.1: Create `DelegationPip` class in `recording_indicator.py` — a 7px dot widget with color/opacity/animation support
  - [ ] Task 1.2: Implement pip states: `SENT` (solid orange), `PROCESSING` (orange pulse), `COMPLETE` (green flash → fade out), `FAILED` (red flash → dim)
  - [ ] Task 1.3: Add `set_state()` method that transitions between visual states with appropriate animations using QTimer (follow existing PulsingDot patterns)
- **Acceptance Criteria:**
  - [ ] AC1: DelegationPip renders as 7px dot with correct colors for each state
  - [ ] AC2: Pulse animation for PROCESSING state matches existing PulsingDot timing pattern
  - [ ] AC3: COMPLETE state fades out over 3s then emits a `finished` signal
  - [ ] AC4: FAILED state flashes red then settles at 0.35 opacity
- **Files:** `app/daemon/recording_indicator.py` — add DelegationPip class
- **Dependencies:** None

#### Phase 2: Pill Layout Integration
- **Objective:** Integrate pips into the pill layout so they appear to the right of existing content in all states
- **Tasks:**
  - [ ] Task 2.1: Add a pip container area to RecordingIndicator layout (right-aligned, holds 0-N pips)
  - [ ] Task 2.2: Adjust pill sizing — idle goes from 36px to 44px when pip(s) present, recording pill adds ~12px for pip area
  - [ ] Task 2.3: Add `add_delegation_pip()` and `remove_delegation_pip()` methods to RecordingIndicator
  - [ ] Task 2.4: Handle pip cleanup — remove pip widget after COMPLETE fade-out, or on user interaction for FAILED
- **Acceptance Criteria:**
  - [ ] AC1: Pip appears to the right of cyan dot in idle state
  - [ ] AC2: Pip appears to the right of waveform during recording
  - [ ] AC3: Multiple pips stack horizontally with 3px spacing
  - [ ] AC4: Pill width adjusts smoothly when pips are added/removed
- **Files:** `app/daemon/recording_indicator.py` — modify RecordingIndicator layout and sizing methods
- **Dependencies:** Phase 1

#### Phase 3: Filesystem Polling & State Machine
- **Objective:** Poll cc-triage directories to detect delegation state transitions
- **Tasks:**
  - [ ] Task 3.1: Create `DelegationTracker` class in `whisper_daemon.py` — manages active delegations and polls filesystem
  - [ ] Task 3.2: Track each delegation by its filename (e.g., `delegation_20260215_171033.txt`) and derive expected report path (`reports/triage_delegation_20260215_171033.json`) and failed pattern (`failed/delegation_20260215_*`)
  - [ ] Task 3.3: Implement polling via QTimer (every 2s) that checks: file in inbox → SENT; file gone from inbox → PROCESSING; report exists → COMPLETE; file in failed → FAILED
  - [ ] Task 3.4: Emit signals on state transitions that connect to RecordingIndicator's pip management
  - [ ] Task 3.5: Auto-cleanup: stop tracking delegations after COMPLETE/FAILED + fade-out time
- **Acceptance Criteria:**
  - [ ] AC1: State transitions detected within 2-4 seconds of filesystem change
  - [ ] AC2: Polling stops when no active delegations (no unnecessary work)
  - [ ] AC3: Multiple concurrent delegations tracked independently
  - [ ] AC4: Stale delegations (cc-triage not running) show as SENT indefinitely — no false positives
- **Files:** `app/daemon/whisper_daemon.py` — add DelegationTracker, integrate with _handle_delegation_output
- **Dependencies:** Phase 2

#### Phase 4: Wiring & Polish
- **Objective:** Connect all components and test end-to-end
- **Tasks:**
  - [ ] Task 4.1: Wire `_handle_delegation_output` to create tracker entry + pip on save
  - [ ] Task 4.2: Wire DelegationTracker signals → RecordingIndicator pip state updates
  - [ ] Task 4.3: Verify composite states: normal recording while delegation processing, new delegation while one pending
  - [ ] Task 4.4: Add log messages for all state transitions for debugging
- **Acceptance Criteria:**
  - [ ] AC1: Full Opt+F → pip appears → pip pulses → pip flashes green/fades flow works
  - [ ] AC2: Ctrl+F normal recording doesn't interfere with active delegation pip
  - [ ] AC3: Multiple Opt+F delegations show multiple pips
  - [ ] AC4: Daemon logs show delegation state transitions clearly
- **Files:** `app/daemon/whisper_daemon.py` — wiring code
- **Dependencies:** Phase 3

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | How to resolve cc-triage base path for reports/failed dirs? | A) Derive from delegation_path (go up one level from inbox/) B) Add `cc_triage_root` config key C) Read cc-triage's own config.json | Store `cc_triage_root` in whisper settings, read cc-triage's `config/config.json` for inbox/reports/failed paths | RESOLVED → `cc_triage_root` config key, read cc-triage's config as single source of truth |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Polling vs watchdog for cc-triage dirs | Polling (QTimer, 2s) | Lightweight, no extra dependency, matches cc-triage's own stability interval |
| Pip size | 7px diameter | Per mockup, small enough to be subtle |
| Pip placement | Right of existing content via layout | Follows existing HBoxLayout pattern in RecordingIndicator |
| DelegationTracker location | whisper_daemon.py | Filesystem logic belongs in daemon, not UI |
| Failed file detection | Glob for `failed/delegation_<stem>_*` | cc-triage appends timestamp when moving to failed, so exact match won't work |

## Execution Log

### Phase 1: DelegationPip Widget
- **Status:** COMPLETE
- **Started:** 2026-02-15
- **Completed:** 2026-02-15
- **Files Modified:**
  - `app/daemon/recording_indicator.py` — Added `DelegationPip` class (7px dot with SENT/PROCESSING/COMPLETE/FAILED states), added `'red'` to COLORS dict

### Tasks Completed
- [x] Task 1.1: Created `DelegationPip` class — 7px dot widget with color/opacity/animation support
- [x] Task 1.2: Implemented all pip states: SENT (solid orange 0.85), PROCESSING (orange pulse 0.4-1.0), COMPLETE (green flash → 3s fade → finished signal), FAILED (red flash → settle at 0.35)
- [x] Task 1.3: Added `set_state()` method with timer-based animations following PulsingDot patterns (40ms tick interval)

### Acceptance Criteria
- [x] AC1: DelegationPip renders as 7px dot (11px widget with margin) with correct colors — verified via import test + 4 state tests
- [x] AC2: Pulse animation for PROCESSING uses same 40ms/0.04 increment pattern as PulsingDot
- [x] AC3: COMPLETE state fades out over 3s (75 ticks x 40ms) then emits `finished` signal exactly once — verified by test
- [x] AC4: FAILED state flashes red then settles at 0.35 opacity, never emits `finished` — verified by test

### REVISE (from code-review-phase-1.md)
- **Commit:** `e1b7410`
- **Fixes applied:**
  1. Removed `_fade_timer.timeout.connect(self._fade_tick)` from `__init__` (critical dual-handler bug)
  2. `_start_complete_fade` now dynamically disconnects then connects `_fade_tick`
  3. `_stop_all_timers` now disconnects `_fade_timer.timeout` (was only disconnecting `_flash_timer`)
  4. Fixed comment: "2s" -> "200ms" for FAILED flash hold
  5. Added `tests/test_delegation_pip.py` — 16 tests covering init, states, timer connections, cross-state transitions, signal emission
- **Verified:** FAILED state does NOT emit `finished`. FAILED->COMPLETE transition has exactly 1 handler (no `_settle_tick` interference). All 16 tests pass.

### Phase 2: Pill Layout Integration
- **Status:** COMPLETE
- **Started:** 2026-02-15
- **Completed:** 2026-02-15
- **Commits:** `3cf87df`
- **Files Modified:**
  - `app/daemon/recording_indicator.py` — Added pip container layout, _pip_width_extra(), add/remove_delegation_pip(), _remove_failed_pips(), _refresh_pill_size(); adjusted all 4 state setters for dynamic width; shifted idle cyan dot when pips present
  - `tests/test_pip_layout.py` — 19 new tests covering container, add/remove, sizing, cleanup, refresh

### Tasks Completed
- [x] Task 2.1: Added _pip_layout (QHBoxLayout, 3px spacing) and _delegation_pips list to _setup_ui
- [x] Task 2.2: Idle grows 36->44px+ with pips; recording/transcribing/cancelled add pip_extra to min/max width
- [x] Task 2.3: add_delegation_pip() returns pip with finished auto-connect; remove_delegation_pip() cleans up widget
- [x] Task 2.4: COMPLETE pips auto-remove via finished signal; FAILED pips removed on recording start via _remove_failed_pips()

### Acceptance Criteria
- [x] AC1: Pip appears right of cyan dot in idle — verified: idle dot shifts to x=18, pip in layout to the right
- [x] AC2: Pip appears right of waveform during recording — verified: pip_layout after waveform in QHBoxLayout
- [x] AC3: Multiple pips stack horizontally with 3px spacing — verified: test_add_multiple_pips (3 pips, layout.count()==3)
- [x] AC4: Pill width adjusts when pips added/removed — verified: test_idle_shrinks_back_after_pip_removed, test_idle_with_two_pips_wider_than_one

## Code Review Log

### Phase 1 (Initial)
- **Gate:** REVISE
- **Reviewed:** 2026-02-15
- **Issues:** 1 critical, 3 major, 2 minor
- **Summary:** Critical signal-accumulation bug on `_fade_timer`. Needs timer connection management rework.

-> Details: `code-review-phase-1.md`

### Phase 1 (Re-review)
- **Gate:** PASS
- **Reviewed:** 2026-02-15
- **Issues:** 0 critical, 0 major, 2 minor
- **Summary:** All five required actions addressed. Critical bug verified fixed. 16 tests pass and directly prevent regression. Minor RuntimeWarnings from disconnect pattern are cosmetic only.

-> Details: `code-review-phase-1-r2.md`

### Phase 2
- **Gate:** REVISE
- **Reviewed:** 2026-02-15
- **Issues:** 0 critical, 2 major, 2 minor
- **Summary:** Core layout solid but pip timers not stopped on removal (ghost callbacks) and idle cyan dot overlaps layout-positioned pips. Two fixes required.

-> Details: `code-review-phase-2.md`

### REVISE (from code-review-phase-2.md)
- **Commit:** `23e528a`
- **Fixes applied:**
  1. `remove_delegation_pip()` now calls `pip._stop_all_timers()` before `deleteLater()` -- prevents ghost timer callbacks from PROCESSING pips
  2. Added `_idle_pip_spacer` (16px QWidget) before `_pip_layout` in `_setup_ui` -- shown only in idle state with pips, pushes pips right of the manually-painted cyan dot (center x=18, radius 4)
  3. All 4 state setters (`_set_idle_state`, `_set_recording_state`, `_set_transcribing_state`, `_set_cancelled_state`) and `_refresh_pill_size` manage spacer visibility
  4. Added 6 new tests: `TestTimerCleanupOnRemoval` (2 tests) and `TestIdlePipSpacer` (4 tests)
- **Verified:** All 41 tests pass (25 layout + 16 pip). PROCESSING pip's `_pulse_timer.isActive()` is `False` after removal. Spacer is shown/hidden correctly per state.

## Notes & Updates
- 2026-02-15: Plan created. Delegation rename (issue_capture → delegation) already applied in this session.
