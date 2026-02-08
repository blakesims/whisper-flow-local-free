# Task: Architectural Cleanup & Technical Debt

## Task ID
T025

## Meta
- **Status:** COMPLETE
- **Last Updated:** 2026-02-08
- **Priority:** 3 (important but not blocking current work)

## Overview

The repo has grown organically from a whisper transcription app into 4 distinct systems. Architectural debt is causing real bugs (config path confusion wasted 30+ min debugging carousel_slides). This task plans a careful, incremental cleanup.

## Audit Findings (2026-02-08)

### Critical Issues

1. **Config hub anti-pattern** — `kb/__main__.py` is both the CLI entry point AND the config provider. 11 modules import `load_config`/`get_paths` from it, creating a structural circular dependency with `kb/core.py` and `kb/analyze.py`.

2. **Config loaded 8x independently** — Each module calls `_config = load_config()` at import time. No caching, no singleton. Different modules may see different state.

3. **Config path vs repo path** — Analysis type configs in `kb/config/` are NOT what the runtime uses. Runtime reads from `KB_ROOT/config/` (mac-sync). Already documented in CLAUDE.md but architecturally unsound.

4. **God files** — `serve.py` (2,372 lines, 7 responsibilities), `analyze.py` (2,095 lines, 6 responsibilities), `videos.py` (1,425 lines).

### Moderate Issues

5. **1,830 lines dead code in `app/core/`** — 6 files only imported by `_legacy/`: gemini_service.py, transcript_enhancer.py, transcript_sectioner.py, meeting_transcript.py, transcription_service_ext.py, video_extractor.py.

6. **Cross-system coupling** — `kb/` imports from `app.core` in 4 places, all for the same 2 things (transcription_service_cpp, config_manager). Should be a single wrapper.

7. **Zero tests on shared infrastructure** — `kb/core.py` (589 lines), all source handlers, entire `app/` system.

8. **`dashboard.py`** — 550 lines of inline HTML/CSS/JS as Python f-strings.

### Low Priority

9. **Dead top-level scripts** — `setup.py`, `compare_whisper_implementations.py`, `test_cpu_optimization.py`, `create_icon.py`.

10. **`requirements.txt` vs `pyproject.toml` out of sync** — Different dependency lists.

11. **3 ways to invoke each command** — `kb analyze`, `kb-analyze`, `python -m kb.analyze`.

---

## Plan

### Objective

Extract config concerns from `kb/__main__.py` into a dedicated `kb/config.py` module with caching, then update all 14 importing files (11 source + 3 test) to use the new module. Zero behavior change -- pure structural refactor.

### Scope
- **In:** Creating `kb/config.py`, moving config functions/constants, updating all imports, adding config caching
- **Out:** Phases 2-6 (dead code removal, transcription wrapper, god file splits, test coverage). No behavior changes, no config path redesign, no changes to `COMMANDS` dict or CLI entry point logic.

### Phases

#### Phase 1: Create `kb/config.py` with config caching

- **Objective:** Create the new config module containing all config-related functions and constants, with a caching layer so config is loaded at most once per process.
- **Tasks:**
  - [ ] Task 1.1: Create `kb/config.py` containing the following items moved from `kb/__main__.py`:
    - `CONFIG_FILE` constant (line 30 of `__main__.py`)
    - `DEFAULTS` dict (lines 33-133)
    - `load_config()` function (lines 136-181)
    - `expand_path()` function (lines 184-186)
    - `get_paths()` function (lines 189-202)
    - Module-level computed exports: `_config`, `_paths`, `KB_ROOT`, `CONFIG_DIR`, `VOLUME_SYNC_PATH`, `CAP_RECORDINGS_DIR` (lines 205-213)
  - [ ] Task 1.2: Add config caching via module-level singleton pattern:
    ```python
    _cached_config: dict | None = None

    def load_config() -> dict:
        """Load config from YAML file, falling back to defaults. Cached after first call."""
        global _cached_config
        if _cached_config is not None:
            return _cached_config

        config = DEFAULTS.copy()
        # ... existing merge logic unchanged ...

        _cached_config = config
        return config
    ```
    Also add a `_reset_config_cache()` function for testing:
    ```python
    def _reset_config_cache():
        """Reset cached config. Only for testing."""
        global _cached_config
        _cached_config = None
    ```
  - [ ] Task 1.3: Handle the `console.print()` dependency in `load_config()`. Currently line 179 uses `console` from Rich. In the new module, replace with `import warnings; warnings.warn(f"Could not load config: {e}")` or create a local `Console()` instance. Using `warnings.warn` is preferable because it avoids importing Rich in a low-level config module, and matches Python conventions for non-fatal configuration issues.
  - [ ] Task 1.4: Verify the new module has no circular import risk. `kb/config.py` should import ONLY from stdlib (`pathlib`, `os`, `warnings`). The `yaml` import is already done lazily inside `load_config()`. No imports from `kb.*` modules.
- **Acceptance Criteria:**
  - [ ] `kb/config.py` exists and contains `CONFIG_FILE`, `DEFAULTS`, `load_config()`, `expand_path()`, `get_paths()`, and computed path exports
  - [ ] `load_config()` returns cached result on second call (same `id()`)
  - [ ] `_reset_config_cache()` exists for test use
  - [ ] `kb/config.py` has zero imports from any `kb.*` module
  - [ ] `python3 -c "from kb.config import load_config, get_paths, DEFAULTS, CONFIG_FILE, expand_path"` succeeds
- **Files:**
  - `kb/config.py` -- NEW file, ~220 lines
- **Dependencies:** None (first phase)

#### Phase 2: Update `kb/__main__.py` to import from `kb.config`

- **Objective:** Remove config definitions from `__main__.py` and replace with imports from the new module. Keep `COMMANDS`, CLI logic, and interactive menu functions in place.
- **Tasks:**
  - [ ] Task 2.1: Remove from `kb/__main__.py`:
    - `CONFIG_FILE` constant (line 30)
    - `DEFAULTS` dict (lines 33-133)
    - `load_config()` function (lines 136-181)
    - `expand_path()` function (lines 184-186)
    - `get_paths()` function (lines 189-202)
    - Module-level `_config`, `_paths`, `KB_ROOT`, `CONFIG_DIR`, `VOLUME_SYNC_PATH`, `CAP_RECORDINGS_DIR` (lines 205-213)
  - [ ] Task 2.2: Add to `kb/__main__.py` near the top (after existing stdlib imports):
    ```python
    from kb.config import (
        load_config, get_paths, expand_path,
        DEFAULTS, CONFIG_FILE,
        KB_ROOT, CONFIG_DIR, VOLUME_SYNC_PATH, CAP_RECORDINGS_DIR,
    )
    ```
  - [ ] Task 2.3: Verify `__main__.py` still works as CLI entry point. The functions `show_config()`, `manage_decimals()`, `add_decimal()`, `edit_decimal()`, `delete_decimal()`, `view_analysis_types()` all reference `CONFIG_FILE`, `DEFAULTS`, `load_config()`, `get_paths()` -- these will now resolve via the import.
  - [ ] Task 2.4: The `pyproject.toml` entry point `kb = "kb.__main__:main"` requires no change since `main()` stays in `__main__.py`.
- **Acceptance Criteria:**
  - [ ] `kb/__main__.py` no longer defines `load_config`, `get_paths`, `expand_path`, `DEFAULTS`, or `CONFIG_FILE`
  - [ ] `kb/__main__.py` imports these from `kb.config`
  - [ ] `python3 -m kb --config` still works (manual test)
- **Files:**
  - `kb/__main__.py` -- MODIFY (remove ~180 lines, add ~5 lines of imports)
- **Dependencies:** Phase 1 complete

#### Phase 3: Update all 11 source modules to import from `kb.config`

- **Objective:** Change every `from kb.__main__ import ...` to `from kb.config import ...` across all source modules.
- **Tasks:**
  - [ ] Task 3.1: Update `kb/core.py` line 20:
    - FROM: `from kb.__main__ import load_config, get_paths, DEFAULTS`
    - TO: `from kb.config import load_config, get_paths, DEFAULTS`
  - [ ] Task 3.2: Update `kb/analyze.py` line 40:
    - FROM: `from kb.__main__ import load_config, get_paths, DEFAULTS`
    - TO: `from kb.config import load_config, get_paths, DEFAULTS`
  - [ ] Task 3.3: Update `kb/serve.py` line 63:
    - FROM: `from kb.__main__ import load_config, get_paths`
    - TO: `from kb.config import load_config, get_paths`
  - [ ] Task 3.4: Update `kb/dashboard.py` line 21:
    - FROM: `from kb.__main__ import load_config, get_paths, DEFAULTS, CONFIG_FILE`
    - TO: `from kb.config import load_config, get_paths, DEFAULTS, CONFIG_FILE`
  - [ ] Task 3.5: Update `kb/cli.py` line 30:
    - FROM: `from kb.__main__ import load_config`
    - TO: `from kb.config import load_config`
  - [ ] Task 3.6: Update `kb/publish.py` line 24:
    - FROM: `from kb.__main__ import load_config, get_paths`
    - TO: `from kb.config import load_config, get_paths`
  - [ ] Task 3.7: Update `kb/inbox.py` line 29:
    - FROM: `from kb.__main__ import load_config, get_paths, DEFAULTS`
    - TO: `from kb.config import load_config, get_paths, DEFAULTS`
  - [ ] Task 3.8: Update `kb/videos.py` line 44:
    - FROM: `from kb.__main__ import load_config, expand_path`
    - TO: `from kb.config import load_config, expand_path`
  - [ ] Task 3.9: Update `kb/sources/cap.py` line 29:
    - FROM: `from kb.__main__ import load_config, get_paths`
    - TO: `from kb.config import load_config, get_paths`
  - [ ] Task 3.10: Update `kb/sources/volume.py` line 31:
    - FROM: `from kb.__main__ import load_config, get_paths, DEFAULTS`
    - TO: `from kb.config import load_config, get_paths, DEFAULTS`
  - [ ] Task 3.11: Update `kb/sources/zoom.py` line 52:
    - FROM: `from kb.__main__ import load_config`
    - TO: `from kb.config import load_config`
- **Acceptance Criteria:**
  - [ ] `grep -r "from kb.__main__ import" kb/ --include="*.py"` returns ONLY test files importing `COMMANDS` (which stays in `__main__.py`)
  - [ ] All 11 source files import from `kb.config` instead
- **Files:**
  - `kb/core.py` -- line 20
  - `kb/analyze.py` -- line 40
  - `kb/serve.py` -- line 63
  - `kb/dashboard.py` -- line 21
  - `kb/cli.py` -- line 30
  - `kb/publish.py` -- line 24
  - `kb/inbox.py` -- line 29
  - `kb/videos.py` -- line 44
  - `kb/sources/cap.py` -- line 29
  - `kb/sources/volume.py` -- line 31
  - `kb/sources/zoom.py` -- line 52
- **Dependencies:** Phase 2 complete

#### Phase 4: Update test files and verify

- **Objective:** Update test imports for `DEFAULTS` (keep `COMMANDS` in `__main__`), then run the full test suite.
- **Tasks:**
  - [ ] Task 4.1: Update `kb/tests/test_serve_integration.py` -- 3 occurrences at lines 465, 472, 478:
    - FROM: `from kb.__main__ import DEFAULTS`
    - TO: `from kb.config import DEFAULTS`
  - [ ] Task 4.2: Leave `kb/tests/test_judge_versioning.py` line 685 UNCHANGED -- it imports `COMMANDS` which correctly stays in `__main__.py`
  - [ ] Task 4.3: Leave `kb/tests/test_render.py` line 581 UNCHANGED -- it imports `COMMANDS` which correctly stays in `__main__.py`
  - [ ] Task 4.4: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 4.5: Run smoke test: `python3 -c "from kb.config import load_config; c = load_config(); print('OK:', list(c.keys()))"`
  - [ ] Task 4.6: Run import verification: `python3 -c "from kb.__main__ import COMMANDS; print('COMMANDS still in __main__:', list(COMMANDS.keys())[:3])"`
  - [ ] Task 4.7: Verify caching works: `python3 -c "from kb.config import load_config; c1 = load_config(); c2 = load_config(); print('Cached:', id(c1) == id(c2))"`
- **Acceptance Criteria:**
  - [ ] All existing tests pass (0 failures)
  - [ ] `COMMANDS` is still importable from `kb.__main__`
  - [ ] `DEFAULTS` is importable from `kb.config`
  - [ ] Config caching returns same object on repeated calls
  - [ ] `grep -r "from kb.__main__ import" kb/ --include="*.py"` returns only: `COMMANDS` imports in test files + the re-export in `__main__.py` itself
- **Files:**
  - `kb/tests/test_serve_integration.py` -- 3 import lines
- **Dependencies:** Phase 3 complete

### Caching Design Details

**Why module-level singleton (not `functools.lru_cache`):**
- `lru_cache` would cache based on arguments, but `load_config()` takes no args and reads from disk + env. A simple global variable is clearer.
- The `_reset_config_cache()` escape hatch allows tests to get fresh config without module reload hacks.
- `DEFAULTS.copy()` is a shallow copy. This is intentional and matches current behavior -- each top-level key's dict is replaced entirely by the merge logic, never mutated in place.

**What gets cached:**
- The merged config dict returned by `load_config()` is cached.
- `get_paths()` is NOT cached separately -- it's a pure function of the config dict and callers can cache its result locally if needed (which they already do via `_paths = get_paths(_config)` at module level).

**Computed module-level exports:**
- `kb/config.py` will compute `KB_ROOT`, `CONFIG_DIR`, `VOLUME_SYNC_PATH`, `CAP_RECORDINGS_DIR` at module load time, exactly as `__main__.py` does today. These use the cached config automatically since they call `load_config()` which populates the cache on first call.

### Import Mapping Reference

| File | Old Import | New Import |
|------|-----------|------------|
| `kb/core.py:20` | `from kb.__main__ import load_config, get_paths, DEFAULTS` | `from kb.config import load_config, get_paths, DEFAULTS` |
| `kb/analyze.py:40` | `from kb.__main__ import load_config, get_paths, DEFAULTS` | `from kb.config import load_config, get_paths, DEFAULTS` |
| `kb/serve.py:63` | `from kb.__main__ import load_config, get_paths` | `from kb.config import load_config, get_paths` |
| `kb/dashboard.py:21` | `from kb.__main__ import load_config, get_paths, DEFAULTS, CONFIG_FILE` | `from kb.config import load_config, get_paths, DEFAULTS, CONFIG_FILE` |
| `kb/cli.py:30` | `from kb.__main__ import load_config` | `from kb.config import load_config` |
| `kb/publish.py:24` | `from kb.__main__ import load_config, get_paths` | `from kb.config import load_config, get_paths` |
| `kb/inbox.py:29` | `from kb.__main__ import load_config, get_paths, DEFAULTS` | `from kb.config import load_config, get_paths, DEFAULTS` |
| `kb/videos.py:44` | `from kb.__main__ import load_config, expand_path` | `from kb.config import load_config, expand_path` |
| `kb/sources/cap.py:29` | `from kb.__main__ import load_config, get_paths` | `from kb.config import load_config, get_paths` |
| `kb/sources/volume.py:31` | `from kb.__main__ import load_config, get_paths, DEFAULTS` | `from kb.config import load_config, get_paths, DEFAULTS` |
| `kb/sources/zoom.py:52` | `from kb.__main__ import load_config` | `from kb.config import load_config` |
| `kb/tests/test_serve_integration.py:465,472,478` | `from kb.__main__ import DEFAULTS` | `from kb.config import DEFAULTS` |
| `kb/tests/test_judge_versioning.py:685` | `from kb.__main__ import COMMANDS` | NO CHANGE (COMMANDS stays in __main__) |
| `kb/tests/test_render.py:581` | `from kb.__main__ import COMMANDS` | NO CHANGE (COMMANDS stays in __main__) |

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | How to handle the `console.print()` warning in `load_config()` (line 179 of `__main__.py`) when it moves to `config.py`? | A) Use `warnings.warn()` (stdlib, no Rich dependency) B) Create a local `Console()` in config.py (keeps Rich output but adds dependency) C) Use `print()` to stderr | A) is cleanest for a config module -- no UI dependency in a data module. B) preserves current visual appearance but couples config to Rich. | OPEN |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| `COMMANDS` dict stays in `__main__.py` | Keep in `__main__.py` | It's CLI-specific, not config. Only 2 test files import it and they correctly reference the CLI module. |
| Caching approach | Module-level global with `_reset_config_cache()` | Simpler than `lru_cache`, matches existing pattern of module-level `_config` variables, testable. |
| `kb/__main__.py` re-exports config symbols | Yes, via `from kb.config import ...` | Ensures any external code that happens to import from `__main__` still works. Backward compatible. |
| `get_paths()` not cached separately | Correct | It's a pure transform of config dict. Callers already cache locally with `_paths = get_paths(_config)`. |
| Module-level computed exports (`KB_ROOT`, etc.) in config.py | Yes | Maintains exact same pattern as current `__main__.py` lines 205-213. Downstream modules already expect these as importable names. |
| Comment in `__main__.py` referencing defaults | Update to point to `kb/config.py` | The config editor template (line 454) says "See defaults in kb/__main__.py" -- update to say "See defaults in kb/config.py". |

### Test Command
```bash
# From repo root:
python3 -m pytest kb/tests/ -v
```

---

## Plan Review
- **Gate:** READY
- **Reviewed:** 2026-02-08
- **Summary:** Plan is thorough and well-verified. All 14 import sites confirmed with correct line numbers. No circular import risk. Caching design is sound. Two major items (naming collision awareness, shared-object semantics documentation) and four minor items identified -- none block execution.
- **Issues:** 0 critical, 2 major, 4 minor
- **Open Questions Finalized:** The `console.print()` to `warnings.warn()` question is resolved (use `warnings.warn()` with plain text, no Rich markup). No remaining open questions needing human input.

-> Details: `plan-review.md`

---

## Execution Log

### Phase 1: Create `kb/config.py` with config caching
- **Status:**
- **Started:**
- **Completed:**
- **Commits:**
- **Files Modified:**
- **Notes:**
- **Blockers:**

### Phase 2: Update `kb/__main__.py` to import from `kb.config`
- **Status:**
- **Started:**
- **Completed:**
- **Commits:**
- **Files Modified:**
- **Notes:**
- **Blockers:**

### Phase 3: Update all 11 source modules to import from `kb.config`
- **Status:**
- **Started:**
- **Completed:**
- **Commits:**
- **Files Modified:**
- **Notes:**
- **Blockers:**

### Phase 4: Update test files and verify
- **Status:**
- **Started:**
- **Completed:**
- **Commits:**
- **Files Modified:**
- **Notes:**
- **Blockers:**

### Phase 2 (Dead Code Deletion): Delete confirmed dead code
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `c346a69` (sub-phase 1: 6 dead app/core files), `678ad46` (sub-phase 2: 5 dead scripts + doc updates)
- **Files Deleted:**
  - `app/core/gemini_service.py` -- 319 lines, dead (only imported by dead transcript_enhancer)
  - `app/core/transcript_enhancer.py` -- 467 lines, dead (only imported by _legacy/)
  - `app/core/transcript_sectioner.py` -- 344 lines, dead (only imported by dead transcript_enhancer)
  - `app/core/meeting_transcript.py` -- 179 lines, dead (only imported by dead files + _legacy/)
  - `app/core/transcription_service_ext.py` -- 221 lines, dead (only imported by _legacy/)
  - `app/core/video_extractor.py` -- 212 lines, dead (only imported by dead transcript_enhancer)
  - `setup.py` -- 36 lines, dead (references non-existent app/main.py)
  - `scripts/build_app.sh` -- 42 lines, dead (depends on dead setup.py)
  - `compare_whisper_implementations.py` -- 353 lines, standalone dead benchmark
  - `test_cpu_optimization.py` -- 108 lines, standalone dead benchmark
  - `create_icon.py` -- 145 lines, one-off dead icon generator
- **Files Modified:**
  - `CLAUDE.md` -- removed "Build macOS App" section (lines 78-81)
  - `.cursor/rules/project-architecture.mdc` -- removed setup.py reference (line 36)
  - `.cursor/rules/integration-points.mdc` -- removed py2app section (lines 36-50), removed setup.py reference (line 82), renumbered sections
- **Notes:** 2,462 lines deleted total. All tests pass (395 pass, 2 pre-existing carousel template failures). `transcribe_file.py` and `APPLE_SILICON_OPTIMIZATION.md` confirmed NOT deleted. Live imports (`transcription_service_cpp`, `post_processor`) verified working.
- **Blockers:** None

### Tasks Completed (Phase 2 Dead Code)
- [x] Task 1.1-1.6: Deleted 6 dead app/core/ files
- [x] Task 1.7: Test suite verified (395 pass, 2 pre-existing failures)
- [x] Task 1.8-1.9: Live imports verified working (via venv)
- [x] Task 2.1-2.5: Deleted 5 dead scripts
- [x] Task 2.6: Updated CLAUDE.md (removed Build macOS App section)
- [x] Task 2.6b: Updated .cursor/rules/ docs (removed setup.py and py2app references)
- [x] Task 2.7: Test suite verified again (395 pass, 2 pre-existing failures)

### Acceptance Criteria (Phase 2 Dead Code)
- [x] AC1: 6 files deleted from app/core/ -- verified via `ls app/core/` (retains __init__.py, audio_recorder.py, fabric_service.py, post_processor.py, transcription_service.py, transcription_service_cpp.py)
- [x] AC2: 5 dead scripts deleted -- verified via git rm
- [x] AC3: Test suite passes (395 pass, 2 pre-existing failures) -- verified after each sub-phase
- [x] AC4: CLAUDE.md no longer references build_app.sh or setup.py -- verified
- [x] AC5: .cursor/rules/ docs no longer reference setup.py or py2app -- verified
- [x] AC6: transcribe_file.py is NOT deleted -- verified exists
- [x] AC7: APPLE_SILICON_OPTIMIZATION.md is NOT deleted -- verified exists
- [x] AC8: All live app.core imports work -- verified via venv

### Phase 3 (Transcription Wrapper): Extract Shared Transcription Wrapper
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `e94ee6a`
- **Files Created:**
  - `kb/transcription.py` -- NEW wrapper module (~15 lines), re-exports `get_transcription_service` and `ConfigManager`
- **Files Modified:**
  - `kb/core.py` -- removed inline sys.path hack (lines 417-418), changed imports to use `kb.transcription`
  - `kb/sources/zoom.py` -- changed imports to use `kb.transcription` (kept module-level sys.path at line 46)
  - `kb/sources/cap_clean.py` -- removed inline sys.path hack (lines 111-112), changed imports to use `kb.transcription`
  - `kb/videos.py` -- changed imports to use `kb.transcription` (kept try/except ImportError pattern, kept module-level sys.path at line 34)
- **Notes:** All 4 call sites updated. Only `kb/transcription.py` itself imports from `app.*`. Test suite: 395 pass, 2 pre-existing failures (carousel templates).
- **Blockers:** None

### Tasks Completed (Phase 3 Transcription Wrapper)
- [x] Task 1.1: Created `kb/transcription.py` wrapper module
- [x] Task 1.2: Verified wrapper imports successfully via venv
- [x] Task 2.1: Updated `kb/core.py` -- removed sys.path hack, imports from wrapper
- [x] Task 2.2: Updated `kb/sources/zoom.py` -- imports from wrapper
- [x] Task 2.3: Updated `kb/sources/cap_clean.py` -- removed sys.path hack, imports from wrapper
- [x] Task 2.4: Updated `kb/videos.py` -- imports from wrapper (kept try/except)
- [x] Task 3.1: Full test suite passed (395 pass, 2 pre-existing failures)
- [x] Task 3.2: Verified no `from app.*` imports in kb/ (only in wrapper itself)
- [x] Task 3.3: Verified wrapper import works via venv

### Acceptance Criteria (Phase 3 Transcription Wrapper)
- [x] AC1: Wrapper module exists and exports both symbols -- verified via `from kb.transcription import get_transcription_service, ConfigManager`
- [x] AC2: Wrapper has zero imports from any other `kb.*` module -- verified by inspection
- [x] AC3: `grep -r "from app\." kb/ --include="*.py"` returns only `kb/transcription.py` -- verified
- [x] AC4: All 4 call sites import from `kb.transcription` -- verified
- [x] AC5: `kb/core.py:transcribe_audio()` no longer has inline `sys.path.insert` -- verified
- [x] AC6: `kb/sources/cap_clean.py` transcription function no longer has inline `sys.path.insert` -- verified
- [x] AC7: `kb/videos.py:transcribe_sample()` still has try/except ImportError wrapping -- verified
- [x] AC8: Test suite passes (395 pass, 2 pre-existing failures) -- verified

---

## Code Review Log

### Phase 1
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 0 major, 1 minor (process: blank execution log)
- **Summary:** Clean extraction. All acceptance criteria verified. All plan review recommendations followed. 395/397 tests pass (2 failures are pre-existing carousel template tests, unrelated). No code issues found.

-> Details: `code-review-phase-1.md`

### Phase 2 (Dead Code Deletion)
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 0 major, 2 minor (both pre-existing, not introduced by this phase)
- **Summary:** Clean deletion of 11 dead files (2,462 lines). All 8 acceptance criteria verified independently. Test suite matches baseline (395 pass, 2 pre-existing failures). Live imports confirmed working via venv. Doc updates complete -- no stale references remain.

-> Details: `code-review-phase-2.md`

### Phase 3 (Transcription Wrapper)
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 0 major, 3 minor (test count reporting, stale comment from Phase 1, sys.path side effect -- all non-blocking)
- **Summary:** Clean wrapper extraction. All 8 ACs verified independently. Zero new test failures (baseline confirmed via git stash comparison). Wrapper is minimal, correct, and has no circular import risk.

-> Details: `code-review-phase-3.md`

---

## Phase 2 Plan: Delete Confirmed Dead Code

### Objective

Remove 1,742 lines of confirmed dead code from `app/core/` (6 files), 4 dead top-level scripts, and 1 dead build script. Pure deletion -- no behavior change for any live code path.

### Scope
- **In:** Deleting 6 dead `app/core/` files, 4 dead top-level scripts, 1 dead build script (`scripts/build_app.sh`)
- **Out:** NOT deleting `_legacy/` itself (separate decision), NOT touching any live `app/core/` files, NOT modifying `pyproject.toml` packaging config

### Verification Audit (completed during planning)

Each file below was verified dead by searching the ENTIRE codebase (not just `kb/`) for all import statements, string references, class name references, and dynamic import paths.

#### Dead File 1: `app/core/gemini_service.py` (319 lines)
- **Imported by:** `app/core/transcript_enhancer.py` (line 13, relative import)
- **Class `GeminiService` referenced by:** `app/core/transcript_enhancer.py` only
- **Live importers:** NONE. Only imported by another dead file.
- **Dynamic import risk:** NONE. No `importlib` usage references this module.
- **Confidence:** HIGH -- safe to delete.

#### Dead File 2: `app/core/transcript_enhancer.py` (467 lines)
- **Imported by:** `_legacy/ui/enhancement_worker.py` (line 9)
- **Class `TranscriptEnhancer` referenced by:** `_legacy/ui/enhancement_worker.py` only
- **Internal imports FROM this file:** `gemini_service`, `meeting_transcript`, `video_extractor`, `transcript_sectioner` (all also dead)
- **Live importers:** NONE. Only imported by `_legacy/` which is explicitly deprecated dead code.
- **Dynamic import risk:** NONE.
- **Confidence:** HIGH -- safe to delete.

#### Dead File 3: `app/core/transcript_sectioner.py` (344 lines)
- **Imported by:** `app/core/transcript_enhancer.py` (line 15, relative import)
- **Class `TranscriptSectioner` referenced by:** `app/core/transcript_enhancer.py` only
- **Live importers:** NONE. Only imported by another dead file.
- **Dynamic import risk:** NONE.
- **Confidence:** HIGH -- safe to delete.

#### Dead File 4: `app/core/meeting_transcript.py` (179 lines)
- **Imported by:**
  - `app/core/transcript_enhancer.py` (line 12, relative import) -- DEAD
  - `app/core/transcription_service_ext.py` (line 8) -- DEAD
  - `_legacy/ui/enhancement_worker.py` (line 8) -- DEAD (`_legacy/`)
  - `_legacy/ui/meeting_worker.py` (line 11) -- DEAD (`_legacy/`)
  - `_legacy/ui/main_window.py` (line 1610, dynamic import inside function) -- DEAD (`_legacy/`)
- **Live importers:** NONE. All importers are dead files or `_legacy/`.
- **Dynamic import risk:** The import in `main_window.py:1610` is inside a function but still in `_legacy/`.
- **Confidence:** HIGH -- safe to delete.

#### Dead File 5: `app/core/transcription_service_ext.py` (221 lines)
- **Imported by:**
  - `_legacy/ui/meeting_worker.py` (line 10) -- DEAD (`_legacy/`)
  - `_legacy/ui/main_window.py` (line 16) -- DEAD (`_legacy/`)
- **NOTE:** This file imports from `app.core.transcription_service` (the base class). The base class is NOT dead -- it is used by `transcription_service_cpp.py`. Only the `_ext` variant is dead.
- **Live importers:** NONE.
- **Dynamic import risk:** NONE.
- **Confidence:** HIGH -- safe to delete.

#### Dead File 6: `app/core/video_extractor.py` (212 lines)
- **Imported by:** `app/core/transcript_enhancer.py` (line 14, relative import)
- **Class `VideoExtractor` referenced by:** `app/core/transcript_enhancer.py` only
- **Live importers:** NONE. Only imported by another dead file.
- **Dynamic import risk:** NONE.
- **Confidence:** HIGH -- safe to delete.

#### Dead Script: `setup.py` (36 lines)
- **References `app/main.py`** which does NOT exist (verified: `ls` returns "No such file or directory").
- **Referenced by:** `scripts/build_app.sh` (line 31: `python setup.py py2app`) -- also dead.
- **Referenced in `CLAUDE.md`:** Yes, indirectly via the build script documentation (line 80).
- **In `pyproject.toml`:** NOT referenced. `pyproject.toml` uses `setuptools.build_meta`, not `setup.py`.
- **Purpose:** Was for py2app packaging of the old PySide6 Full UI. That UI is deprecated (`_legacy/`).
- **Confidence:** HIGH -- safe to delete.

#### Dead Script: `scripts/build_app.sh` (42 lines)
- **Runs `python setup.py py2app`** -- depends on `setup.py` which itself depends on non-existent `app/main.py`.
- **Referenced by:** `CLAUDE.md` line 80 ("Build macOS App" section).
- **Purpose:** Built the old PySide6 Full UI as a macOS .app bundle. That UI is deprecated.
- **Confidence:** HIGH -- safe to delete alongside `setup.py`.

#### Dead Script: `compare_whisper_implementations.py` (353 lines)
- **Standalone benchmark.** Imports only from `whisper`, `faster_whisper`, `psutil`, `numpy` (external libs).
- **No imports from project code.** No project code imports from it.
- **Not referenced in `pyproject.toml`, CI, or scripts.**
- **Confidence:** HIGH -- safe to delete.

#### Dead Script: `test_cpu_optimization.py` (108 lines)
- **Standalone benchmark.** Imports from `faster_whisper`, `psutil` (external libs).
- **No imports from project code.** No project code imports from it.
- **Not referenced in `pyproject.toml`, CI, or scripts.**
- **Confidence:** HIGH -- safe to delete.

#### Dead Script: `create_icon.py` (145 lines)
- **One-off icon generator.** Imports from `PIL`, `subprocess` (external/stdlib).
- **No imports from project code.** No project code imports from it.
- **Not referenced in `pyproject.toml`, CI, or scripts.**
- **Output (`resources/app_icon.icns`) already exists** -- the icon was generated and committed.
- **Confidence:** HIGH -- safe to delete.

### Additional Findings

1. **`_legacy/app/core` is a symlink to `../../app/core`** -- Deleting files from `app/core/` will cause broken symlinks inside `_legacy/app/core/`. This is fine because `_legacy/` is dead code. The symlinks that survive (for live files like `transcription_service.py`) will still work.

2. **`_legacy/app/` also has symlinks** for `prompts` and `utils`. These are unaffected by this phase.

3. **`CLAUDE.md` references `scripts/build_app.sh`** in a "Build macOS App" section. This doc reference should be removed when the script is deleted.

4. **`app/core/__init__.py`** is empty (just whitespace). No re-exports of any dead modules. Safe.

5. **Test baseline:** 395 passed, 2 failed (pre-existing carousel template failures, unrelated). This is the same baseline as after Phase 1.

6. **`transcribe_file.py` is NOT dead** -- it is referenced in `pyproject.toml` as `py-modules = ["transcribe_file"]` and documented in `CLAUDE.md` for Raycast file transcription. Do NOT delete.

### Phases

#### Phase 1: Delete the 6 dead `app/core/` files

- **Objective:** Remove 1,742 lines of dead code from `app/core/`.
- **Tasks:**
  - [ ] Task 1.1: Delete `app/core/gemini_service.py` (319 lines)
  - [ ] Task 1.2: Delete `app/core/transcript_enhancer.py` (467 lines)
  - [ ] Task 1.3: Delete `app/core/transcript_sectioner.py` (344 lines)
  - [ ] Task 1.4: Delete `app/core/meeting_transcript.py` (179 lines)
  - [ ] Task 1.5: Delete `app/core/transcription_service_ext.py` (221 lines)
  - [ ] Task 1.6: Delete `app/core/video_extractor.py` (212 lines)
  - [ ] Task 1.7: Run `python3 -m pytest kb/tests/ -v` -- verify 395 pass, same 2 pre-existing failures
  - [ ] Task 1.8: Verify live imports still work: `python3 -c "from app.core.transcription_service_cpp import get_transcription_service; print('OK')"`
  - [ ] Task 1.9: Verify live imports still work: `python3 -c "from app.core.post_processor import get_post_processor; print('OK')"`
- **Acceptance Criteria:**
  - [ ] 6 files deleted from `app/core/`
  - [ ] `app/core/` retains: `__init__.py`, `audio_recorder.py`, `fabric_service.py`, `post_processor.py`, `transcription_service.py`, `transcription_service_cpp.py`
  - [ ] Test suite passes (395 pass, 2 pre-existing failures)
  - [ ] All live `app.core` imports work
- **Files:**
  - DELETE: `app/core/gemini_service.py`
  - DELETE: `app/core/transcript_enhancer.py`
  - DELETE: `app/core/transcript_sectioner.py`
  - DELETE: `app/core/meeting_transcript.py`
  - DELETE: `app/core/transcription_service_ext.py`
  - DELETE: `app/core/video_extractor.py`
- **Dependencies:** Phase 1 (config extraction) COMPLETE

#### Phase 2: Delete dead top-level scripts and build script

- **Objective:** Remove 4 dead top-level scripts and 1 dead build script.
- **Tasks:**
  - [ ] Task 2.1: Delete `setup.py` (36 lines)
  - [ ] Task 2.2: Delete `scripts/build_app.sh` (42 lines)
  - [ ] Task 2.3: Delete `compare_whisper_implementations.py` (353 lines)
  - [ ] Task 2.4: Delete `test_cpu_optimization.py` (108 lines)
  - [ ] Task 2.5: Delete `create_icon.py` (145 lines)
  - [ ] Task 2.6: Update `CLAUDE.md` to remove the "Build macOS App" section (lines 78-81) that references the deleted `scripts/build_app.sh`
  - [ ] Task 2.7: Run `python3 -m pytest kb/tests/ -v` -- verify 395 pass, same 2 pre-existing failures
- **Acceptance Criteria:**
  - [ ] 5 files deleted
  - [ ] `CLAUDE.md` no longer references `build_app.sh` or `setup.py`
  - [ ] `transcribe_file.py` is NOT deleted (it is live)
  - [ ] Test suite passes (395 pass, 2 pre-existing failures)
- **Files:**
  - DELETE: `setup.py`
  - DELETE: `scripts/build_app.sh`
  - DELETE: `compare_whisper_implementations.py`
  - DELETE: `test_cpu_optimization.py`
  - DELETE: `create_icon.py`
  - MODIFY: `CLAUDE.md` -- remove "Build macOS App" section
- **Dependencies:** Phase 1 of this plan complete

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Should `scripts/build_app.sh` be deleted alongside `setup.py`? | A) Delete both B) Keep build_app.sh for reference | Deleting both is cleaner. Keeping it leaves a script that cannot work. | RESOLVED: Delete both. `build_app.sh` runs `setup.py` which targets non-existent `app/main.py`. Entire chain is dead. Git history preserves it. |
| 2 | The `APPLE_SILICON_OPTIMIZATION.md` doc at repo root -- should it be deleted too? | A) Delete it B) Keep it | Low impact either way. | RESOLVED: Keep it. The doc covers general `faster-whisper` Apple Silicon optimization knowledge (device config, compute types, alternatives). It does NOT reference the benchmark scripts being deleted. Useful reference material. |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Do NOT delete `transcribe_file.py` | Keep | Referenced in `pyproject.toml` `py-modules` and documented in `CLAUDE.md` for Raycast usage. Active file. |
| Do NOT delete `_legacy/` directory | Keep | Out of scope per task description. Separate decision with different risk profile. |
| Update `CLAUDE.md` when deleting build script | Yes | Prevents stale documentation referencing deleted files. |
| Delete files in two phases (core files first, then scripts) | Yes | Allows running tests between each batch to isolate any issues. |
| Broken symlinks in `_legacy/app/core/` are acceptable | Yes | `_legacy/` is explicitly deprecated dead code. Broken symlinks inside it do not affect any live functionality. |

### Phase 2 Plan Review
- **Gate:** READY
- **Reviewed:** 2026-02-08
- **Summary:** Deletion plan is thorough and verified. All 6 dead app/core files independently confirmed dead via grep. Test baseline confirmed (395 pass, 2 pre-existing failures). One major gap: `.cursor/rules/` files reference `setup.py` and should be cleaned up. Both open questions resolved (delete build_app.sh: yes; keep APPLE_SILICON_OPTIMIZATION.md: yes).
- **Issues:** 0 critical, 1 major, 3 minor
- **Open Questions Finalized:** Both resolved autonomously. No human input needed.
- **Action Required:** Add a task to Phase 2 to update/remove `setup.py` references in `.cursor/rules/project-architecture.mdc` (line 36) and `.cursor/rules/integration-points.mdc` (lines 36-50, 82).

-> Details: `plan-review-phase2.md`

### Deletion Summary

| File | Lines | Category | Only Importers |
|------|-------|----------|---------------|
| `app/core/gemini_service.py` | 319 | Dead core module | `transcript_enhancer.py` (dead) |
| `app/core/transcript_enhancer.py` | 467 | Dead core module | `_legacy/ui/enhancement_worker.py` |
| `app/core/transcript_sectioner.py` | 344 | Dead core module | `transcript_enhancer.py` (dead) |
| `app/core/meeting_transcript.py` | 179 | Dead core module | Dead files + `_legacy/` only |
| `app/core/transcription_service_ext.py` | 221 | Dead core module | `_legacy/` only |
| `app/core/video_extractor.py` | 212 | Dead core module | `transcript_enhancer.py` (dead) |
| `setup.py` | 36 | Dead build config | `scripts/build_app.sh` (dead) |
| `scripts/build_app.sh` | 42 | Dead build script | `CLAUDE.md` (doc reference) |
| `compare_whisper_implementations.py` | 353 | Dead benchmark | Nothing |
| `test_cpu_optimization.py` | 108 | Dead benchmark | Nothing |
| `create_icon.py` | 145 | Dead generator | Nothing |
| **TOTAL** | **2,426** | | |

---

## Phase 3 Plan: Extract Shared Transcription Wrapper

### Objective

Create `kb/transcription.py` to encapsulate all `app.core` and `app.utils` imports used by `kb/`, then update the 4 call sites to import from the wrapper instead. This decouples `kb/` from `app/` internal module structure -- future changes to `app.core` only need updating in one place.

### Scope
- **In:** Creating `kb/transcription.py` wrapper module, updating 4 call sites in `kb/` to use it, removing inline `sys.path.insert` hacks from transcription functions
- **Out:** Not changing transcription behavior, not refactoring the usage pattern (ConfigManager + get_transcription_service), not touching `app/core/` or `app/utils/` source code, not addressing the `sys.path.insert` hacks at module level in other files (that is a separate concern)

### Current State (Verified Against Live Code)

All 4 call sites import the same 2 things:
1. `get_transcription_service` from `app.core.transcription_service_cpp`
2. `ConfigManager` from `app.utils.config_manager`

All 4 use the identical pattern:
```python
config = ConfigManager()
service = get_transcription_service(config)
service.set_target_model_config(model_name, "cpu", "int8")
service.load_model()
```

| File | Line(s) | Import Style | sys.path hack? |
|------|---------|-------------|----------------|
| `kb/core.py` | 417-420 | Lazy (inside `transcribe_audio()`) | Yes, lines 417-418 inside function |
| `kb/sources/zoom.py` | 261-262 | Lazy (inside `transcribe_meeting()`) | No (module-level at line 46) |
| `kb/sources/cap_clean.py` | 112-114 | Lazy (inside function) | Yes, line 112 inside function |
| `kb/videos.py` | 189-191 | Lazy (inside `transcribe_sample()`, with try/except ImportError) | No (module-level at line 34) |

### Naming Consideration

The task doc originally proposed `kb/transcription.py`. However, `kb/transcribe.py` already exists as the CLI dispatcher for the `kb transcribe` subcommand. The names `transcribe.py` vs `transcription.py` are confusingly similar. This is surfaced as an open question below.

### Phases

#### Sub-phase 1: Create the wrapper module

- **Objective:** Create the new wrapper module that re-exports `get_transcription_service` and `ConfigManager` from `app.*`, centralizing the cross-system imports in one place.
- **Tasks:**
  - [ ] Task 1.1: Create the wrapper module (name TBD per open question -- default: `kb/transcription.py`) with the following content:
    ```python
    """
    Transcription service wrapper.

    Centralizes all app.core and app.utils imports used by kb/ modules.
    If the app/ transcription backend changes, only this file needs updating.
    """
    import os
    import sys

    # Ensure project root is on path for app.* imports
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.core.transcription_service_cpp import get_transcription_service
    from app.utils.config_manager import ConfigManager

    __all__ = ["get_transcription_service", "ConfigManager"]
    ```
  - [ ] Task 1.2: Verify the wrapper imports successfully: `python3 -c "from kb.transcription import get_transcription_service, ConfigManager; print('OK')"`
- **Acceptance Criteria:**
  - [ ] Wrapper module exists and exports both `get_transcription_service` and `ConfigManager`
  - [ ] Wrapper has zero imports from any other `kb.*` module
  - [ ] The `sys.path` fix is done once at module level, not repeated in each call site
- **Files:**
  - `kb/transcription.py` -- NEW file, ~15 lines
- **Dependencies:** Phase 2 (dead code deletion) COMPLETE

#### Sub-phase 2: Update all 4 call sites

- **Objective:** Replace all `from app.core...` and `from app.utils...` imports in `kb/` with imports from the new wrapper module.
- **Tasks:**
  - [ ] Task 2.1: Update `kb/core.py` lines 416-420 (inside `transcribe_audio()`):
    - REMOVE: `import sys` (line 417)
    - REMOVE: `sys.path.insert(0, ...)` (line 418)
    - CHANGE: `from app.core.transcription_service_cpp import get_transcription_service` -> `from kb.transcription import get_transcription_service`
    - CHANGE: `from app.utils.config_manager import ConfigManager` -> `from kb.transcription import ConfigManager`
    - Can combine to single line: `from kb.transcription import get_transcription_service, ConfigManager`
    - Keep the comment `# Import here to avoid circular imports` (still true -- lazy import is intentional)
  - [ ] Task 2.2: Update `kb/sources/zoom.py` lines 261-262 (inside `transcribe_meeting()`):
    - CHANGE: `from app.core.transcription_service_cpp import get_transcription_service` -> `from kb.transcription import get_transcription_service`
    - CHANGE: `from app.utils.config_manager import ConfigManager` -> `from kb.transcription import ConfigManager`
    - Can combine to single line: `from kb.transcription import get_transcription_service, ConfigManager`
    - NOTE: The module-level `sys.path.insert` at line 46 stays -- it is used by other imports (e.g. `from kb.core import ...`)
  - [ ] Task 2.3: Update `kb/sources/cap_clean.py` lines 111-114 (inside function):
    - REMOVE: `import sys` (line 111)
    - REMOVE: `sys.path.insert(0, ...)` (line 112)
    - CHANGE: `from app.core.transcription_service_cpp import get_transcription_service` -> `from kb.transcription import get_transcription_service`
    - CHANGE: `from app.utils.config_manager import ConfigManager` -> `from kb.transcription import ConfigManager`
    - Can combine to single line: `from kb.transcription import get_transcription_service, ConfigManager`
  - [ ] Task 2.4: Update `kb/videos.py` lines 189-191 (inside `transcribe_sample()`):
    - CHANGE: `from app.core.transcription_service_cpp import get_transcription_service` -> `from kb.transcription import get_transcription_service`
    - CHANGE: `from app.utils.config_manager import ConfigManager` -> `from kb.transcription import ConfigManager`
    - Can combine to single line: `from kb.transcription import get_transcription_service, ConfigManager`
    - KEEP the `try/except ImportError` wrapper around the import -- this function gracefully handles missing transcription deps by returning `None`
- **Acceptance Criteria:**
  - [ ] `grep -r "from app\." kb/ --include="*.py"` returns zero results
  - [ ] All 4 call sites import from `kb.transcription` instead
  - [ ] `kb/core.py:transcribe_audio()` no longer has inline `sys.path.insert`
  - [ ] `kb/sources/cap_clean.py` transcription function no longer has inline `sys.path.insert`
  - [ ] `kb/videos.py:transcribe_sample()` still has try/except ImportError wrapping
- **Files:**
  - `kb/core.py` -- lines 416-420
  - `kb/sources/zoom.py` -- lines 261-262
  - `kb/sources/cap_clean.py` -- lines 111-114
  - `kb/videos.py` -- lines 189-191
- **Dependencies:** Sub-phase 1 complete

#### Sub-phase 3: Verify

- **Objective:** Confirm all tests pass and no `app.*` imports remain in `kb/`.
- **Tasks:**
  - [ ] Task 3.1: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 3.2: Verify no `app.*` imports remain in `kb/`: `grep -r "from app\.\|import app\." kb/ --include="*.py"` returns nothing
  - [ ] Task 3.3: Verify wrapper import works: `python3 -c "from kb.transcription import get_transcription_service, ConfigManager; print('OK')"`
  - [ ] Task 3.4: Verify `kb/core.py` transcribe_audio function still works (imports resolve correctly)
- **Acceptance Criteria:**
  - [ ] All existing tests pass (395 pass, 2 pre-existing failures)
  - [ ] Zero `from app.*` imports anywhere in `kb/`
  - [ ] Wrapper module loads cleanly
- **Files:** None (verification only)
- **Dependencies:** Sub-phase 2 complete

### Import Mapping Reference

| File | Line(s) | Old Import | New Import |
|------|---------|-----------|------------|
| `kb/core.py` | 419 | `from app.core.transcription_service_cpp import get_transcription_service` | `from kb.transcription import get_transcription_service, ConfigManager` |
| `kb/core.py` | 420 | `from app.utils.config_manager import ConfigManager` | (merged into line above) |
| `kb/sources/zoom.py` | 261 | `from app.core.transcription_service_cpp import get_transcription_service` | `from kb.transcription import get_transcription_service, ConfigManager` |
| `kb/sources/zoom.py` | 262 | `from app.utils.config_manager import ConfigManager` | (merged into line above) |
| `kb/sources/cap_clean.py` | 113 | `from app.core.transcription_service_cpp import get_transcription_service` | `from kb.transcription import get_transcription_service, ConfigManager` |
| `kb/sources/cap_clean.py` | 114 | `from app.utils.config_manager import ConfigManager` | (merged into line above) |
| `kb/videos.py` | 190 | `from app.core.transcription_service_cpp import get_transcription_service` | `from kb.transcription import get_transcription_service, ConfigManager` |
| `kb/videos.py` | 191 | `from app.utils.config_manager import ConfigManager` | (merged into line above) |

### Lines Removed (sys.path hacks inside functions)

| File | Lines Removed | Why Safe |
|------|--------------|----------|
| `kb/core.py` | 417-418 (`import sys` + `sys.path.insert`) | The wrapper module handles path setup at its own module level |
| `kb/sources/cap_clean.py` | 111-112 (`import sys` + `sys.path.insert`) | The wrapper module handles path setup at its own module level |

Note: `kb/sources/zoom.py` line 46 and `kb/videos.py` line 34 have module-level `sys.path.insert` -- these are NOT removed because they serve broader purposes (other non-transcription imports from the project).

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Wrapper module name: `kb/transcription.py` exists alongside `kb/transcribe.py` (the CLI dispatcher). These names differ by one suffix but could cause confusion. | A) `kb/transcription.py` (as originally proposed -- clear noun form, "transcription service wrapper") B) `kb/whisper_service.py` (more specific, avoids name collision with transcribe.py) C) Keep `kb/transcription.py` and accept the naming similarity | Low impact on functionality, moderate impact on developer clarity. `transcribe.py` = CLI entry point, `transcription.py` = service wrapper. The semantic difference (verb vs noun) is intentional but subtle. | RESOLVED: Use `kb/transcription.py`. Verb (transcribe.py) vs noun (transcription.py) is standard convention. |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Keep lazy imports at call sites | Yes -- imports stay inside functions, not moved to module level | All 4 sites use lazy imports deliberately (the `# Import here to avoid circular imports` comment in core.py, the try/except in videos.py). Moving to module level would change import timing and could trigger circular imports or fail-at-import-time for optional deps. |
| Remove inline sys.path hacks from transcription functions | Yes | The wrapper module handles sys.path setup once. Removing from `core.py:417-418` and `cap_clean.py:111-112` eliminates redundant path manipulation. |
| Keep module-level sys.path hacks in zoom.py and videos.py | Yes | These serve other imports beyond transcription (e.g., `from kb.core import ...`). Out of scope to refactor all sys.path usage. |
| Wrapper does NOT add higher-level helpers (e.g., `create_service(model)`) | Correct | The task scope is decoupling imports, not refactoring the usage pattern. Each call site has slightly different model/callback configuration. A higher-level helper would be a behavior change. |
| Wrapper re-exports both symbols via `__all__` | Yes | Makes the public API explicit. Consumers can `from kb.transcription import get_transcription_service, ConfigManager`. |

### Risk Assessment
- **Risk:** LOW. Pure import reorganization. No behavior change.
- **Rollback:** Delete wrapper module, revert 4 import lines. Git makes this trivial.
- **Test coverage:** Transcription functions are not unit-tested directly (they require whisper model loading), but the import chain is validated by the test suite not crashing on import.

### Phase 3 Plan Review
- **Gate:** READY
- **Reviewed:** 2026-02-08
- **Summary:** Plan is accurate and well-verified. All 4 call sites (8 import lines) independently confirmed via grep with correct line numbers. sys.path handling is correct (remove inline hacks from core.py and cap_clean.py, keep module-level ones in zoom.py and videos.py). Wrapper design is minimal and correct. Naming question resolved: use `kb/transcription.py`.
- **Issues:** 0 critical, 0 major, 3 minor
- **Open Questions Finalized:** Naming question resolved (use `kb/transcription.py`). No remaining open questions needing human input.

-> Details: `plan-review-phase3.md`

---

## Proposed Phases (Full T025 -- Phases 2-6 for future work)

### Phase 2: Delete confirmed dead code (LOW RISK)
- Remove 6 dead `app/core/` files (1,830 lines)
- Remove `setup.py` (references non-existent `app/main.py`)
- Remove one-off benchmark scripts
- Verify nothing imports these files first

### Phase 3: Extract shared transcription wrapper (LOW RISK)
- Create `kb/transcription.py` wrapping the 2 `app.core` imports
- Update 4 call sites in `kb/` to use the wrapper
- Decouples `kb/` from `app/` internal structure

### Phase 4: Split `kb/analyze.py` (MEDIUM RISK)
- Extract 380-line CLI to thin wrapper
- Extract judge loop to `kb/judge.py`
- Extract template rendering to `kb/prompts.py`
- Keep Gemini API + analysis type loading together
- Run full test suite after each extraction

### Phase 5: Split `kb/serve.py` (MEDIUM RISK)
- Convert to Flask app package: `kb/serve/__init__.py`
- Extract: `routes/`, `state.py`, `visual.py`, `scanner.py`
- Most complex phase — many route handlers with shared state
- Run full test suite after each extraction

### Phase 6: Test coverage for `kb/core.py` (LOW RISK)
- Add tests for registry, transcription orchestration, file handling
- Foundation for safe future refactoring

## Risks & Notes

- **Phase 4-5 are the riskiest** — extracting code from god files with many cross-references
- **Config path issue** is the most impactful to fix but requires a design decision: should the repo's `kb/config/` be authoritative, or should runtime always read from `KB_ROOT`?
- **Don't do everything at once** — each phase should be a separate PR with passing tests
- **`_legacy/` and `mvp-example/`** — keep for now, not hurting anything

## Completion
- **Status:** Not started
