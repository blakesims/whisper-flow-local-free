# Task: Architectural Cleanup & Technical Debt

## Task ID
T025

## Meta
- **Status:** COMPLETE
- **Last Updated:** 2026-02-08
- **Current Sub-phase:** All phases (1-5) COMPLETE. All code reviews PASS. Phase 6 (test coverage) is optional future work.
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

### Phase 4 Sub-phase 4.1: Extract template rendering to `kb/prompts.py`
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `7600a13`
- **Files Created:**
  - `kb/prompts.py` -- NEW module (~170 lines), 4 pure template functions with `__all__`
- **Files Modified:**
  - `kb/analyze.py` -- removed 4 function definitions (~168 lines), added 5-line import from `kb.prompts` for re-export
- **Notes:** All 4 functions are pure stdlib (re, json). Re-export from kb.analyze ensures backward compat. Test baseline unchanged: 395 pass, 2 pre-existing failures.
- **Blockers:** None

### Tasks Completed (Phase 4 Sub-phase 4.1)
- [x] Task 4.1.1: Created `kb/prompts.py` with format_prerequisite_output, substitute_template_vars, render_conditional_template, resolve_optional_inputs
- [x] Task 4.1.2: Replaced 4 function defs in `kb/analyze.py` with `from kb.prompts import ...`
- [x] Task 4.1.3: Full test suite passed (395 pass, 2 pre-existing failures)
- [x] Task 4.1.4: Verified re-exports from both `kb.analyze` and `kb.prompts`
- [x] Task 4.1.5: Committed `7600a13`

### Acceptance Criteria (Phase 4 Sub-phase 4.1)
- [x] AC1: `kb/prompts.py` exists with 4 functions -- verified
- [x] AC2: `kb/prompts.py` imports ONLY from stdlib (`re`, `json`) -- verified by inspection
- [x] AC3: All 4 functions re-exported from `kb/analyze.py` -- verified via `from kb.analyze import ...`
- [x] AC4: 395 tests pass (same 2 pre-existing failures) -- verified
- [x] AC5: Existing `patch('kb.analyze.substitute_template_vars', ...)` patterns still work -- verified (tests pass)

### Phase 4 Sub-phase 4.2: Extract judge loop to `kb/judge.py`
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `16ff9d1`
- **Files Created:**
  - `kb/judge.py` -- NEW module (~340 lines), 7 judge loop functions + AUTO_JUDGE_TYPES constant
- **Files Modified:**
  - `kb/analyze.py` -- removed 7 function definitions + AUTO_JUDGE_TYPES (~448 lines), added 8-line import from `kb.judge` for re-export
- **Notes:** DEFAULT_MODEL computed from kb.config at module level in judge.py (avoids circular import). Lazy imports from kb.analyze inside run_with_judge_loop() and run_analysis_with_auto_judge() function bodies. Test baseline unchanged: 395 pass, 2 pre-existing failures. kb/serve.py import verified working.
- **Blockers:** None

### Tasks Completed (Phase 4 Sub-phase 4.2)
- [x] Task 4.2.1: Read kb/analyze.py -- identified all 7 functions + AUTO_JUDGE_TYPES + DEFAULT_MODEL definition
- [x] Task 4.2.2: Created `kb/judge.py` with module-level imports (json, time, datetime, Rich, kb.prompts, kb.config)
- [x] Task 4.2.3: Added lazy imports inside run_with_judge_loop() (analyze_transcript, run_analysis_with_deps, load_analysis_type, _save_analysis_to_file)
- [x] Task 4.2.4: Added lazy import inside run_analysis_with_auto_judge() (analyze_transcript_file)
- [x] Task 4.2.5: Replaced 7 function defs + AUTO_JUDGE_TYPES in kb/analyze.py with `from kb.judge import ...`
- [x] Task 4.2.6: Full test suite passed (395 pass, 2 pre-existing failures)
- [x] Task 4.2.7: Verified re-exports from both `kb.analyze` and `kb.judge`
- [x] Task 4.2.8: Verified `from kb.serve import app` works
- [x] Task 4.2.9: Committed `16ff9d1`
- [x] Task 4.2.10: Updated main.md execution log

### Acceptance Criteria (Phase 4 Sub-phase 4.2)
- [x] AC1: `kb/judge.py` exists with 7 functions + 1 constant -- verified
- [x] AC2: `kb/judge.py` imports prompts from `kb.prompts` (not `kb.analyze`) -- verified by inspection
- [x] AC3: `kb/judge.py` uses lazy imports from `kb.analyze` inside function bodies -- verified (run_with_judge_loop, run_analysis_with_auto_judge)
- [x] AC4: All 7 functions + AUTO_JUDGE_TYPES are re-exported from `kb/analyze.py` -- verified via `from kb.analyze import ...`
- [x] AC5: 395 tests pass (same 2 pre-existing failures) -- verified
- [x] AC6: All `patch('kb.analyze.run_with_judge_loop', ...)` patterns in tests still work -- verified (tests pass)
- [x] AC7: `kb/serve.py` module-level import succeeds -- verified via `from kb.serve import app`

### Phase 5 Sub-phase 5.1: Extract state persistence to `kb/serve_state.py`
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `7a81f45`
- **Files Created:**
  - `kb/serve_state.py` -- NEW module (~100 lines), 4 state persistence functions with optional path param + lazy import from kb.serve
- **Files Modified:**
  - `kb/serve.py` -- removed 4 function definitions (~62 lines), added import from `kb.serve_state` for re-export. ACTION_STATE_PATH and PROMPT_FEEDBACK_PATH remain defined in serve.py.
- **Notes:** Each function accepts optional `path` parameter; when None, lazy-imports the path constant from `kb.serve`. This preserves 74+ test patches targeting `kb.serve.ACTION_STATE_PATH`. Test baseline unchanged: 395 pass, 2 pre-existing failures.
- **Blockers:** None

### Tasks Completed (Phase 5 Sub-phase 5.1)
- [x] Task 5.1.1: Read kb/serve.py -- identified 4 functions (lines 135-220) and 2 constants (lines 71-72)
- [x] Task 5.1.2: Created `kb/serve_state.py` with load_action_state, save_action_state, load_prompt_feedback, save_prompt_feedback
- [x] Task 5.1.3: Replaced 4 function defs in `kb/serve.py` with `from kb.serve_state import ...`
- [x] Task 5.1.4: Full test suite passed (395 pass, 2 pre-existing failures)
- [x] Task 5.1.5: Verified re-exports from both `kb.serve` and `kb.serve_state`
- [x] Task 5.1.6: Committed `7a81f45`

### Acceptance Criteria (Phase 5 Sub-phase 5.1)
- [x] AC1: `kb/serve_state.py` exists with 4 functions -- verified
- [x] AC2: Functions accept optional `path` param, lazy-import from `kb.serve` when None -- verified by inspection
- [x] AC3: `ACTION_STATE_PATH` and `PROMPT_FEEDBACK_PATH` remain defined in `kb/serve.py` -- verified (lines 71-72)
- [x] AC4: All 4 functions re-exported from `kb/serve.py` -- verified via `from kb.serve import load_action_state, save_action_state, ACTION_STATE_PATH`
- [x] AC5: 395 tests pass (same 2 pre-existing failures) -- verified

### Phase 5 Sub-phase 5.2: Extract scanner + action mapping to `kb/serve_scanner.py`
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `f0d58c5`
- **Files Created:**
  - `kb/serve_scanner.py` -- NEW module (~230 lines), 3 constants + 6 functions for scanning/action mapping
- **Files Modified:**
  - `kb/serve.py` -- removed 3 constant definitions, 1 internal function (_build_versioned_key_pattern), 6 function definitions (~222 lines removed), added import from `kb.serve_scanner` for re-export
- **Notes:** Functions needing `KB_ROOT` or `_config` accept optional parameters and lazy-import from `kb.serve` when None (same pattern as serve_state.py). `_build_versioned_key_pattern()` imports `AUTO_JUDGE_TYPES` directly from `kb.analyze` (not via lazy import -- it runs at module init to compute `VERSIONED_KEY_PATTERN`). Pure functions (get_destination_for_action, get_action_status, format_relative_time, validate_action_id) have no lazy imports. Test baseline unchanged: 395 pass, 2 pre-existing failures.
- **Blockers:** None

### Tasks Completed (Phase 5 Sub-phase 5.2)
- [x] Task 5.2.1: Read kb/serve.py -- identified all 3 constants + 6 functions + 1 internal builder function
- [x] Task 5.2.2: Created `kb/serve_scanner.py` with ACTION_ID_SEP, ACTION_ID_PATTERN, VERSIONED_KEY_PATTERN, get_action_mapping, get_destination_for_action, scan_actionable_items, get_action_status, format_relative_time, validate_action_id
- [x] Task 5.2.3: Replaced definitions in `kb/serve.py` with `from kb.serve_scanner import ...`
- [x] Task 5.2.4: Full test suite passed (395 pass, 2 pre-existing failures)
- [x] Task 5.2.5: Verified re-exports from both `kb.serve` and `kb.serve_scanner`
- [x] Task 5.2.6: Committed `f0d58c5`

### Acceptance Criteria (Phase 5 Sub-phase 5.2)
- [x] AC1: `kb/serve_scanner.py` exists with 3 constants + 6 functions -- verified
- [x] AC2: `get_action_mapping` accepts optional `config` param, lazy-imports `_config` from `kb.serve` when None -- verified by inspection
- [x] AC3: `scan_actionable_items` accepts optional `kb_root` param, lazy-imports `KB_ROOT` from `kb.serve` when None -- verified by inspection
- [x] AC4: `_build_versioned_key_pattern()` imports `AUTO_JUDGE_TYPES` from `kb.analyze` -- verified
- [x] AC5: `KB_ROOT` and `_config` remain defined in `kb/serve.py` -- verified
- [x] AC6: All constants + functions re-exported from `kb/serve.py` -- verified via `from kb.serve import scan_actionable_items, VERSIONED_KEY_PATTERN, ACTION_ID_SEP`
- [x] AC7: 395 tests pass (same 2 pre-existing failures) -- verified

### Phase 5 Sub-phase 5.3: Extract visual pipeline to `kb/serve_visual.py`
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `451331d`
- **Files Modified:**
  - `kb/serve_visual.py` -- NEW: contains `_update_visual_status`, `_find_transcript_file`, `run_visual_pipeline`
  - `kb/serve.py` -- replaced 3 function defs (162 lines) with import from `kb.serve_visual`
  - `kb/tests/test_serve_integration.py` -- fixed patch target `kb.serve._update_visual_status` -> `kb.serve_visual._update_visual_status`
- **Notes:**
  - `_find_transcript_file` accepts optional `kb_root` param; lazy-imports `KB_ROOT` from `kb.serve` when None
  - `_update_visual_status` imports `load_action_state`/`save_action_state` directly from `kb.serve_state` (no circular dep)
  - `run_visual_pipeline` retains its existing lazy imports for `kb.analyze` and `kb.render`

### Tasks Completed (Phase 5 Sub-phase 5.3)
- [x] Task 5.3.1: Read serve.py, identified functions at lines 97-258
- [x] Task 5.3.2: Created `kb/serve_visual.py` with 3 functions + proper imports
- [x] Task 5.3.3: Replaced 3 function defs in `kb/serve.py` with `from kb.serve_visual import ...`
- [x] Task 5.3.4: Fixed test patch `kb.serve._update_visual_status` -> `kb.serve_visual._update_visual_status`
- [x] Task 5.3.5: Tests pass: 395 passed, 2 failed (pre-existing)
- [x] Task 5.3.6: Re-exports verified from both `kb.serve` and `kb.serve_visual`
- [x] Task 5.3.7: Committed as `451331d`
- [x] Task 5.3.8: Updated main.md

### Acceptance Criteria (Phase 5 Sub-phase 5.3)
- [x] AC1: `kb/serve_visual.py` exists with 3 functions -- verified
- [x] AC2: `_find_transcript_file` accepts optional `kb_root` param, lazy-imports from `kb.serve` when None -- verified
- [x] AC3: `_update_visual_status` imports `load_action_state`/`save_action_state` from `kb.serve_state` directly -- verified
- [x] AC4: `run_visual_pipeline` retains lazy imports for `kb.analyze` and `kb.render` -- verified
- [x] AC5: All 3 functions re-exported from `kb/serve.py` -- verified via import test
- [x] AC6: Test patch updated to `kb.serve_visual._update_visual_status` -- verified (line 626)
- [x] AC7: 395 tests pass (same 2 pre-existing failures) -- verified

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

### Phase 4 (Split analyze.py)
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 0 major, 4 minor (unused `import time` in judge.py, mid-file import placement, commit message count off-by-one, test baseline reporting)
- **Summary:** Clean extraction of 11 functions + 1 constant into kb/prompts.py and kb/judge.py. All ACs verified. Zero new test failures (confirmed via git stash baseline comparison). Circular import strategy is sound. Re-exports maintain full backward compat.

-> Details: `code-review-phase-4.md`

### Phase 5 (Split serve.py)
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 1 major (dead imports shutil/Optional left in serve.py), 3 minor (dead variables in serve_visual.py, unused analyze_transcript_file import, import placement inconsistency)
- **Summary:** Solid extraction of 13 functions + 3 constants from the 2,372-line kb/serve.py into 3 focused utility modules. Parameterized lazy-import pattern correctly preserves 74+ test patch targets. One test patch updated (serve_visual._update_visual_status). Test baseline maintained: 395 pass, 2 pre-existing failures.

-> Details: `code-review-phase-5.md`

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

## Phase 4 Plan: Split `kb/analyze.py` (MEDIUM RISK)

### Objective

Split the 2,096-line `kb/analyze.py` god file into 3 focused modules (`kb/prompts.py`, `kb/judge.py`, and a thin CLI in `kb/analyze.py`) while keeping the Gemini API core and analysis orchestration in `kb/analyze.py`. Zero behavior change -- pure structural refactor.

### Current State Analysis

`kb/analyze.py` contains **31 functions** across **6 distinct responsibilities** totaling 2,096 lines:

| Responsibility | Functions | Lines | Dependencies |
|---|---|---|---|
| Template/prompt rendering | `format_prerequisite_output`, `substitute_template_vars`, `render_conditional_template`, `resolve_optional_inputs` | ~145 | Pure functions, no API calls, no IO. Only import is `re` (stdlib). |
| Judge loop orchestration | `_get_starting_round`, `_build_history_from_existing`, `_build_score_history`, `_update_alias`, `run_with_judge_loop`, `run_analysis_with_auto_judge`, `AUTO_JUDGE_TYPES` | ~350 | Depends on: `analyze_transcript`, `run_analysis_with_deps`, `load_analysis_type`, `resolve_optional_inputs`, `format_prerequisite_output`, `_save_analysis_to_file`, console |
| Gemini API + analysis core | `load_analysis_type`, `list_analysis_types`, `analyze_transcript`, `run_analysis_with_deps`, `_save_analysis_to_file`, `analyze_transcript_file` | ~350 | Depends on: template functions, config, `google.genai` |
| Missing analyses feature | `get_decimal_defaults`, `get_transcript_missing_analyses`, `scan_missing_by_decimal`, `get_missing_summary`, `show_missing_analyses`, `run_missing_analyses`, `run_missing_interactive` | ~355 | Depends on: `get_all_transcripts`, `analyze_transcript_file`, `load_registry`, config |
| CLI selectors/formatters | `get_all_transcripts`, `format_analysis_status`, `select_transcripts`, `select_analysis_types_interactive` | ~100 | Depends on: `list_analysis_types`, questionary, Rich |
| CLI entry point | `run_interactive_mode`, `run_batch_pending`, `main` | ~380 | Depends on everything above |
| Module-level config | Constants + imports | ~66 | `kb.config`, `kb.core` |

### External Consumers (Who imports from `kb.analyze`)

| Consumer | Imports | Import Style |
|---|---|---|
| `kb/serve.py:33` | `list_analysis_types`, `load_analysis_type`, `ANALYSIS_TYPES_DIR`, `AUTO_JUDGE_TYPES`, `run_with_judge_loop` | Module-level |
| `kb/serve.py:280` | `run_analysis_with_deps`, `analyze_transcript_file`, `_save_analysis_to_file`, `DEFAULT_MODEL` | Lazy (inside function) |
| `kb/inbox.py:37` | `analyze_transcript_file`, `list_analysis_types` | Module-level |
| `kb/sources/paste.py:253` | `analyze_transcript_file` | Lazy |
| `kb/sources/file.py:191` | `analyze_transcript_file` | Lazy |
| `kb/sources/zoom.py:514` | `analyze_transcript_file` | Lazy |
| `kb/sources/cap_clean.py:327` | `analyze_transcript` | Lazy |
| `kb/videos.py:793` | `get_decimal_defaults`, `analyze_transcript_file` | Lazy |
| `kb/__main__.py:220` | `scan_missing_by_decimal` | Lazy |
| `kb/__main__.py:365,491` | `list_analysis_types` | Lazy |
| `kb/__init__.py:31` | `analyze_transcript`, `analyze_transcript_file`, `list_analysis_types` | Lazy (`__getattr__`) |

### Test Files Affected

| Test File | Functions Imported from `kb.analyze` |
|---|---|
| `test_compound_analysis.py` | `substitute_template_vars`, `format_prerequisite_output`, `load_analysis_type`, `run_analysis_with_deps` |
| `test_conditional_template.py` | `render_conditional_template`, `substitute_template_vars`, `resolve_optional_inputs` |
| `test_judge_versioning.py` | `_get_starting_round`, `_build_history_from_existing`, `_build_score_history`, `_update_alias`, `run_with_judge_loop`, `AUTO_JUDGE_TYPES`, `resolve_optional_inputs`, `render_conditional_template` |

### Scope

- **In:** Extracting template rendering to `kb/prompts.py`, judge loop to `kb/judge.py`, and updating all imports across source files, test files, and re-exports in `kb/analyze.py`.
- **Out:** Not splitting the CLI `main()` function into a separate file (it can stay in `analyze.py` since COMMANDS references `kb.analyze` module). Not refactoring the missing analyses feature out (it is tightly coupled to `get_all_transcripts` and `analyze_transcript_file`). Not changing any behavior.

### Sub-Phases

#### Sub-phase 4.1: Extract template rendering to `kb/prompts.py`

- **Objective:** Move the 4 pure template functions to a new `kb/prompts.py` module. These have zero external dependencies (only `re` from stdlib and `json` from stdlib), making this the safest extraction.
- **Tasks:**
  - [ ] Task 4.1.1: Create `kb/prompts.py` containing:
    - `format_prerequisite_output(analysis_result: dict) -> str` (lines 619-655)
    - `substitute_template_vars(prompt: str, context: dict) -> str` (lines 658-678)
    - `render_conditional_template(prompt: str, context: dict) -> str` (lines 681-740)
    - `resolve_optional_inputs(analysis_def: dict, existing_analysis: dict, transcript_text: str) -> dict` (lines 868-909)
    - Add module docstring explaining purpose.
    - Imports needed: `import re`, `import json` (both stdlib only).
  - [ ] Task 4.1.2: In `kb/analyze.py`, replace the 4 function definitions with imports from `kb.prompts`:
    ```python
    from kb.prompts import (
        format_prerequisite_output,
        substitute_template_vars,
        render_conditional_template,
        resolve_optional_inputs,
    )
    ```
    This re-export ensures all external consumers that currently import these from `kb.analyze` continue to work unchanged.
  - [ ] Task 4.1.3: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 4.1.4: Verify the re-exports work: `python3 -c "from kb.analyze import substitute_template_vars, format_prerequisite_output, render_conditional_template, resolve_optional_inputs; print('OK')"` AND `python3 -c "from kb.prompts import substitute_template_vars, format_prerequisite_output, render_conditional_template, resolve_optional_inputs; print('OK')"`
- **Acceptance Criteria:**
  - [ ] `kb/prompts.py` exists with 4 functions
  - [ ] `kb/prompts.py` imports ONLY from stdlib (`re`, `json`)
  - [ ] All 4 functions are re-exported from `kb/analyze.py` (backward compat)
  - [ ] All 395 tests pass (same 2 pre-existing failures)
  - [ ] All existing `patch('kb.analyze.substitute_template_vars', ...)` patterns in tests still work because the functions are re-exported
- **Files:**
  - `kb/prompts.py` -- NEW file, ~130 lines
  - `kb/analyze.py` -- MODIFY: remove ~130 lines of function bodies, add 5-line import
- **Dependencies:** Phases 1-3 of T025 COMPLETE
- **Risk:** LOW. These are pure functions with no side effects, no IO, no external API calls.

**Note on test patches:** The tests use `patch('kb.analyze.substitute_template_vars', ...)` etc. Because the re-export from `kb.analyze` means these names still exist in the `kb.analyze` module namespace, the patches will continue to work without any test changes. However, patches will affect the `kb.analyze` module's reference, not the `kb.prompts` module's original. This is the correct behavior because callers within `kb/analyze.py` resolve these names from their own module namespace.

#### Sub-phase 4.2: Extract judge loop to `kb/judge.py`

- **Objective:** Move the judge loop orchestration (7 functions + 1 constant) to `kb/judge.py`. This is the most complex extraction because `run_with_judge_loop` calls back into `analyze_transcript` and `run_analysis_with_deps`.
- **Tasks:**
  - [ ] Task 4.2.1: Create `kb/judge.py` containing:
    - `AUTO_JUDGE_TYPES` dict (line 1326-1328)
    - `_get_starting_round(existing_analysis, analysis_type)` (lines 984-1011)
    - `_build_history_from_existing(existing_analysis, analysis_type, judge_type)` (lines 1014-1046)
    - `_build_score_history(existing_analysis, judge_type)` (lines 1049-1067)
    - `_update_alias(existing_analysis, analysis_type, judge_type, draft_result, current_round)` (lines 1070-1081)
    - `run_with_judge_loop(...)` (lines 1084-1322)
    - `run_analysis_with_auto_judge(...)` (lines 1331-1431)
    - Module docstring explaining purpose.
  - [ ] Task 4.2.2: Set up imports in `kb/judge.py`:
    ```python
    import json
    import time
    from datetime import datetime
    from rich.console import Console
    from rich.panel import Panel

    from kb.prompts import (
        format_prerequisite_output,
        resolve_optional_inputs,
    )
    # Lazy imports to avoid circular dependency:
    # analyze_transcript, run_analysis_with_deps, load_analysis_type,
    # _save_analysis_to_file, analyze_transcript_file are imported
    # inside function bodies.

    console = Console()
    ```
    **Critical design decision -- circular import avoidance:** `kb/judge.py` needs `analyze_transcript` and `run_analysis_with_deps` from `kb/analyze.py`, but `kb/analyze.py` currently defines these and calls judge functions. The solution: `kb/judge.py` uses lazy imports (inside function bodies) for the functions it needs from `kb/analyze.py`. This matches the existing pattern already used throughout the codebase.
  - [ ] Task 4.2.3: Inside `run_with_judge_loop()` in `kb/judge.py`, add lazy imports at the top of the function body:
    ```python
    from kb.analyze import (
        analyze_transcript, run_analysis_with_deps,
        load_analysis_type, _save_analysis_to_file,
    )
    ```
  - [ ] Task 4.2.4: Inside `run_analysis_with_auto_judge()` in `kb/judge.py`, add lazy imports at the top of the function body:
    ```python
    from kb.analyze import analyze_transcript_file
    ```
  - [ ] Task 4.2.5: In `kb/analyze.py`, replace the 7 function definitions and `AUTO_JUDGE_TYPES` with re-exports:
    ```python
    from kb.judge import (
        AUTO_JUDGE_TYPES,
        _get_starting_round,
        _build_history_from_existing,
        _build_score_history,
        _update_alias,
        run_with_judge_loop,
        run_analysis_with_auto_judge,
    )
    ```
  - [ ] Task 4.2.6: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 4.2.7: Verify re-exports work: `python3 -c "from kb.analyze import run_with_judge_loop, AUTO_JUDGE_TYPES; print('OK')"` AND `python3 -c "from kb.judge import run_with_judge_loop, AUTO_JUDGE_TYPES; print('OK')"`
  - [ ] Task 4.2.8: Verify `kb/serve.py` still works (it imports `run_with_judge_loop` and `AUTO_JUDGE_TYPES` from `kb.analyze`): `python3 -c "from kb.serve import app; print('OK')"`
- **Acceptance Criteria:**
  - [ ] `kb/judge.py` exists with 7 functions + 1 constant
  - [ ] `kb/judge.py` imports prompts from `kb.prompts` (not `kb.analyze`)
  - [ ] `kb/judge.py` uses lazy imports from `kb.analyze` inside function bodies (no circular import at module level)
  - [ ] All 7 functions + `AUTO_JUDGE_TYPES` are re-exported from `kb/analyze.py`
  - [ ] All 395 tests pass (same 2 pre-existing failures)
  - [ ] All `patch('kb.analyze.run_with_judge_loop', ...)` and `patch('kb.analyze.analyze_transcript', ...)` patterns in `test_judge_versioning.py` still work
  - [ ] `kb/serve.py` module-level import succeeds
- **Files:**
  - `kb/judge.py` -- NEW file, ~380 lines
  - `kb/analyze.py` -- MODIFY: remove ~380 lines, add 8-line import
- **Dependencies:** Sub-phase 4.1 COMPLETE
- **Risk:** MEDIUM. The circular dependency between `judge.py` and `analyze.py` requires careful lazy import placement. The existing tests use `patch('kb.analyze.run_with_judge_loop', ...)` which relies on re-export behavior.

**Circular dependency analysis:**
- `kb/analyze.py` needs: nothing from `kb/judge.py` at runtime (it re-exports via import but no function in analyze.py calls judge functions directly)
- `kb/judge.py` needs from `kb/analyze.py`: `analyze_transcript`, `run_analysis_with_deps`, `load_analysis_type`, `_save_analysis_to_file`, `analyze_transcript_file`
- Direction: `judge -> analyze` (one-way at function call time), `analyze -> judge` (only at import time for re-export)
- This is safe because Python handles circular imports when one side only imports at module level for re-export, and the other imports lazily inside functions.

**Test patch analysis:** `test_judge_versioning.py` patches `kb.analyze.run_with_judge_loop`, `kb.analyze.analyze_transcript`, and `kb.analyze.run_analysis_with_deps`. Because `kb/judge.py` does lazy imports inside function bodies (`from kb.analyze import analyze_transcript`), patching `kb.analyze.analyze_transcript` will be seen by `kb/judge.py` because the lazy import resolves from the `kb.analyze` module namespace where the mock is installed. This works correctly.

#### Sub-phase 4.3: Update external imports (optional optimization)

- **Objective:** Update external consumers to import directly from `kb.prompts` or `kb.judge` where appropriate, reducing coupling. This is optional -- re-exports mean everything works without it -- but improves clarity.
- **Tasks:**
  - [ ] Task 4.3.1: Update `kb/serve.py:33`:
    - FROM: `from kb.analyze import list_analysis_types, load_analysis_type, ANALYSIS_TYPES_DIR, AUTO_JUDGE_TYPES, run_with_judge_loop`
    - TO: `from kb.analyze import list_analysis_types, load_analysis_type, ANALYSIS_TYPES_DIR` and `from kb.judge import AUTO_JUDGE_TYPES, run_with_judge_loop`
  - [ ] Task 4.3.2: Update `kb/__init__.py:31` -- NO CHANGE needed. It imports `analyze_transcript`, `analyze_transcript_file`, `list_analysis_types` which all remain in `kb/analyze.py`.
  - [ ] Task 4.3.3: Update test files to import from canonical locations (optional, can be deferred):
    - `test_compound_analysis.py`: `substitute_template_vars`, `format_prerequisite_output` -> from `kb.prompts`
    - `test_conditional_template.py`: `render_conditional_template`, `substitute_template_vars`, `resolve_optional_inputs` -> from `kb.prompts`
    - `test_judge_versioning.py`: `_get_starting_round`, `_build_history_from_existing`, `_build_score_history`, `_update_alias`, `AUTO_JUDGE_TYPES` -> from `kb.judge`
    - **BUT** keep `run_with_judge_loop` imports and patches targeting `kb.analyze` because they need to patch the name in the namespace where it is called.
  - [ ] Task 4.3.4: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 4.3.5: Verify no regressions in `kb serve` startup: `python3 -c "from kb.serve import app; print('OK')"`
- **Acceptance Criteria:**
  - [ ] `kb/serve.py` imports judge functions from `kb.judge` directly
  - [ ] All 395 tests pass (same 2 pre-existing failures)
  - [ ] All test patches still function correctly
- **Files:**
  - `kb/serve.py` -- MODIFY: split one import line into two
  - `kb/tests/test_compound_analysis.py` -- MODIFY: change import sources (optional)
  - `kb/tests/test_conditional_template.py` -- MODIFY: change import sources (optional)
  - `kb/tests/test_judge_versioning.py` -- MODIFY: change import sources for helpers (optional)
- **Dependencies:** Sub-phase 4.2 COMPLETE
- **Risk:** LOW. Only changing import sources, all functions remain the same.

### Post-Split File Sizes (Estimated)

| File | Before | After | Change |
|---|---|---|---|
| `kb/analyze.py` | 2,096 lines | ~1,230 lines | -866 lines (functions removed, import re-exports added) |
| `kb/prompts.py` | NEW | ~130 lines | Template rendering functions |
| `kb/judge.py` | NEW | ~380 lines | Judge loop orchestration |

`kb/analyze.py` retains: module-level config (66 lines), analysis type loading (20 lines), Gemini API call (125 lines), dependency resolution (70 lines), file save (5 lines), analyze_transcript_file (115 lines), missing analyses feature (355 lines), CLI selectors/formatters (100 lines), CLI entry point (380 lines), re-export imports (~15 lines).

### Import Dependency Graph (After Split)

```
kb/prompts.py        (stdlib only: re, json)
     ^
     |
kb/judge.py          (imports from kb.prompts at module level)
     |               (lazy imports from kb.analyze inside function bodies)
     v
kb/analyze.py        (imports from kb.prompts and kb.judge at module level for re-export)
                     (imports from kb.config, kb.core)
```

No circular import at module load time. The `judge -> analyze` lazy imports resolve at function call time, after both modules are fully loaded.

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Should the "missing analyses" feature (~355 lines) also be extracted to a separate module (e.g., `kb/missing.py`)? | A) Extract now as Sub-phase 4.4 B) Leave in `kb/analyze.py` for now, extract in a future phase C) Leave permanently (it is tightly coupled to analyze) | The missing analyses functions depend on `get_all_transcripts`, `analyze_transcript_file`, and `load_registry`. Extracting them would reduce `kb/analyze.py` by another 355 lines (from ~1,498 to ~1,143). However, it adds scope and risk to this phase. | RESOLVED: B. Leave in analyze.py for now. Reduces scope/risk. Can extract in future phase if needed. |
| 2 | Should Sub-phase 4.3 (updating external imports to canonical locations) be mandatory or optional? | A) Mandatory -- do it as part of this phase B) Optional -- defer to a future cleanup pass | If mandatory, external consumers import from the "right" module immediately. If optional, re-exports handle everything and we reduce scope/risk. Test file import changes are particularly low-value since tests already work via re-exports. | RESOLVED: B. Optional/deferred. Re-exports guarantee backward compatibility, so 4.3 is purely cosmetic. |
| 3 | Should the `console = Console()` instance in `kb/judge.py` be shared with `kb/analyze.py` or be a separate instance? | A) Create a new `Console()` instance in `kb/judge.py` (simple, matches existing pattern where multiple modules create their own console) B) Share a single console instance via a common module | Every `kb/*.py` file already creates its own `Console()` instance. Creating a new one is consistent with the existing pattern. | RESOLVED: A. Separate instance. Matches existing codebase pattern. |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Re-export all moved functions from `kb/analyze.py` | Yes | Backward compatibility. External consumers import from `kb.analyze` and test patches target `kb.analyze`. Changing all import sites is risky and unnecessary. |
| Use lazy imports in `kb/judge.py` for `kb.analyze` functions | Yes | Avoids circular import at module load time. Matches existing codebase pattern (lazy imports are used throughout `kb/`). |
| Template functions go to `kb/prompts.py` (not `kb/templates.py`) | `kb/prompts.py` | The functions deal with LLM prompt construction and variable substitution. "prompts" describes the responsibility better than "templates" which could be confused with HTML/Jinja templates. Also matches the original proposed name from the task description. |
| Judge functions go to `kb/judge.py` | `kb/judge.py` | Matches the original proposed name from the task description. The judge loop is a distinct orchestration pattern. |
| CLI `main()` stays in `kb/analyze.py` | Yes | The COMMANDS dict in `kb/__main__.py` references `kb.analyze` as the module, and calls `module.main()`. Moving `main()` would require changing COMMANDS entries. Not worth the risk for this phase. |
| `_save_analysis_to_file` stays in `kb/analyze.py` | Yes | It is a simple 4-line utility used by both `analyze_transcript_file` (in analyze.py) and `run_with_judge_loop` (moving to judge.py). Keeping it in analyze.py avoids an additional dependency direction. judge.py will lazy-import it. |
| Order of extraction: prompts first, then judge | Yes | Prompts are pure functions with zero dependencies -- safest to extract first. Judge depends on prompts, so extracting prompts first means judge.py can import from kb.prompts directly (not from kb.analyze). |
| `get_all_transcripts` stays in `kb/analyze.py` | Yes | Used by both the missing analyses feature and the CLI interactive mode. Both remain in analyze.py. |

### Test Baseline
```bash
# Current baseline (confirmed 2026-02-08):
# 395 passed, 2 failed (pre-existing carousel template tests)
python3 -m pytest kb/tests/ -v
```

### Phase 4 Plan Review
- **Gate:** READY (with required fix)
- **Reviewed:** 2026-02-08
- **Summary:** Plan is well-verified with 100% accurate line numbers and complete external consumer analysis. One critical gap: `DEFAULT_MODEL` missing from `kb/judge.py` imports (would cause NameError). Simple fix: compute from `kb.config` directly. Post-split line estimates off by ~270 lines (documentation only). All 3 open questions resolved autonomously (no human input needed).
- **Issues:** 1 critical, 1 major, 4 minor
- **Open Questions Finalized:**
  - Q1: Leave "missing analyses" in analyze.py (Option B -- reduces scope/risk)
  - Q2: Sub-phase 4.3 is optional (Option B -- re-exports handle everything)
  - Q3: Separate Console() instance in judge.py (Option A -- matches existing pattern)
- **Required Fix Before Execution:** Add `DEFAULT_MODEL` computation to `kb/judge.py` module-level imports. Recommended approach: compute from `kb.config` (no circular import risk). See plan-review-phase4.md for details.

-> Details: `plan-review-phase4.md`

---

## Phase 5 Plan: Split `kb/serve.py` (MEDIUM RISK)

### Objective

Split the 2,372-line `kb/serve.py` god file into focused modules by extracting non-route utility functions while keeping all Flask route handlers in `kb/serve.py`. Zero behavior change -- pure structural refactor.

### Recommendation: Do NOT Convert to Flask Package

The original task doc proposed converting `kb/serve.py` into `kb/serve/__init__.py` with `routes/` subdirectory. After thorough analysis, this is **not recommended** for these reasons:

1. **Every test and external consumer imports `from kb.serve import app`** -- 6 test files (test_serve_integration, test_iteration_view, test_browse, test_slide_editing, test_staging, test_action_mapping) plus `kb/publish.py` and `kb/migrate.py`. Converting to a package changes the import semantics.
2. **COMMANDS dict in `__main__.py` references `"module": "kb.serve"`** -- changing to a package requires COMMANDS update.
3. **Route handlers are tightly coupled to shared state** (`_config`, `KB_ROOT`, `ACTION_STATE_PATH`, `load_action_state()`, `save_action_state()`, `ACTION_ID_SEP`, `AUTO_JUDGE_TYPES`). Splitting routes across files would require passing these through or creating a shared state module, adding complexity for minimal gain.
4. **The real value is extracting non-route utilities** -- the scanner, visual pipeline, state management, and action mapping are the cleanly separable pieces. Route handlers are inherently coupled to Flask and to each other via shared state.

**Recommended approach:** Extract 3 utility modules from `kb/serve.py`, keep all route handlers in `kb/serve.py`, re-export extracted symbols for backward compatibility.

### Current State Analysis

`kb/serve.py` contains **68 top-level definitions** across **7 distinct responsibility groups** totaling 2,372 lines:

| Responsibility | Functions/Constants | Lines | Dependencies |
|---|---|---|---|
| Module-level state/config | `_config`, `_paths`, `KB_ROOT`, `CONFIG_DIR`, `ACTION_STATE_PATH`, `PROMPT_FEEDBACK_PATH`, `ACTION_ID_SEP`, `ACTION_ID_PATTERN`, `VERSIONED_KEY_PATTERN`, `_build_versioned_key_pattern()` | ~72 | `kb.config`, `kb.analyze.AUTO_JUDGE_TYPES` |
| Action mapping | `get_action_mapping()`, `get_destination_for_action()` | ~53 | `_config` (module-level) |
| State persistence | `load_action_state()`, `save_action_state()`, `migrate_approved_to_draft()`, `load_prompt_feedback()`, `save_prompt_feedback()` | ~76 | `ACTION_STATE_PATH`, `PROMPT_FEEDBACK_PATH`, json, shutil |
| Visual pipeline | `_update_visual_status()`, `_find_transcript_file()`, `run_visual_pipeline()` | ~157 | `load_action_state`, `save_action_state`, `ACTION_ID_SEP`, `KB_ROOT`, lazy: `kb.analyze`, `kb.render` |
| Scanner | `scan_actionable_items()`, `get_action_status()`, `format_relative_time()`, `validate_action_id()` | ~134 | `KB_ROOT`, `ACTION_ID_SEP`, `ACTION_ID_PATTERN`, `VERSIONED_KEY_PATTERN`, `get_action_mapping()`, `get_destination_for_action()` |
| Route handlers (39 routes) | All `@app.route` decorated functions | ~1,830 | Everything above + Flask + pyperclip |
| CLI | `check_and_auto_scan()`, `main()` | ~41 | `app`, `kb.videos` |

### External Consumers (Who imports from `kb.serve`)

| Consumer | What it imports | Import Style |
|---|---|---|
| `kb/publish.py:126` | `load_action_state`, `ACTION_ID_SEP` | Lazy (inside function) |
| `kb/migrate.py:38` | `migrate_approved_to_draft` | Lazy (inside function) |
| `kb/tests/test_serve_integration.py` | `app`, `_update_visual_status`, `get_destination_for_action`, `get_action_mapping`, `run_visual_pipeline` | Lazy (inside test methods) |
| `kb/tests/test_action_mapping.py` | `get_destination_for_action`, `get_action_mapping` | Lazy; also patches `kb.serve._config` |
| `kb/tests/test_judge_versioning.py` | `VERSIONED_KEY_PATTERN`, `scan_actionable_items`, `migrate_approved_to_draft` | Lazy |
| `kb/tests/test_browse.py` | `app`; also patches `kb.serve.KB_ROOT` | Lazy |
| `kb/tests/test_iteration_view.py` | `app` | Lazy |
| `kb/tests/test_slide_editing.py` | `app` | Lazy |
| `kb/tests/test_staging.py` | `app` | Lazy |

### Module-Level Patch Targets in Tests

Tests patch these `kb.serve` module-level variables:
- `kb.serve.KB_ROOT` -- patched in `test_browse.py` (11 occurrences)
- `kb.serve._config` -- patched in `test_action_mapping.py` (5 occurrences)

These patches must continue to target the `kb.serve` namespace for correct behavior, so any extracted functions that read `KB_ROOT` or `_config` must either: (a) take them as parameters, or (b) be re-exported in `kb.serve` where the patches land. See design decisions below.

### What to Extract

Three utility modules, extracted in order of increasing dependency complexity:

1. **`kb/serve_state.py`** (~76 lines) -- Action state and prompt feedback persistence
2. **`kb/serve_scanner.py`** (~187 lines) -- Actionable item scanning + action mapping
3. **`kb/serve_visual.py`** (~157 lines) -- Visual pipeline (background thread)

### Why NOT `kb/state.py`, `kb/scanner.py`, `kb/visual.py`

The `kb/` namespace already has many modules. Using the `serve_` prefix:
- Makes the relationship to `serve.py` obvious
- Avoids naming collisions (e.g., `kb/scanner.py` could be confused with general KB scanning)
- Follows the same pattern used by `kb/transcription.py` (domain-specific wrapper)

### Scope

- **In:** Extracting state persistence, scanner, and visual pipeline to 3 new modules. Re-exporting all symbols from `kb/serve.py` for backward compatibility. Running tests after each extraction.
- **Out:** NOT converting to Flask package. NOT splitting route handlers into multiple files. NOT changing any behavior. NOT updating test import targets (re-exports handle it). NOT extracting CLI (`main()` / `check_and_auto_scan()` are trivial and tightly coupled to Flask app startup).

### Sub-Phases

#### Sub-phase 5.1: Extract state persistence to `kb/serve_state.py`

- **Objective:** Move action state and prompt feedback persistence functions to a dedicated module. These have zero dependency on Flask, routes, or the scanner -- they are pure file I/O utilities.
- **Tasks:**
  - [ ] Task 5.1.1: Create `kb/serve_state.py` containing:
    - Constants: `ACTION_STATE_PATH`, `PROMPT_FEEDBACK_PATH` (currently L71-72)
    - `load_action_state()` (L135-159, 25 lines)
    - `save_action_state()` (L162-166, 5 lines)
    - `migrate_approved_to_draft()` (L169-190, 22 lines)
    - `load_prompt_feedback()` (L195-213, 19 lines)
    - `save_prompt_feedback()` (L216-220, 5 lines)
    - Imports needed: `json`, `shutil`, `logging`, `pathlib.Path`
    - Module docstring: "Action state and prompt feedback persistence for kb serve."
  - [ ] Task 5.1.2: In `kb/serve.py`, replace the 5 function definitions + 2 constants with imports from `kb.serve_state`:
    ```python
    from kb.serve_state import (
        ACTION_STATE_PATH, PROMPT_FEEDBACK_PATH,
        load_action_state, save_action_state,
        migrate_approved_to_draft,
        load_prompt_feedback, save_prompt_feedback,
    )
    ```
    This re-export ensures all external consumers (`kb/publish.py`, `kb/migrate.py`, tests) that import from `kb.serve` continue to work unchanged.
  - [ ] Task 5.1.3: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 5.1.4: Verify re-exports work: `python3 -c "from kb.serve import load_action_state, save_action_state, ACTION_STATE_PATH; print('OK')"` AND `python3 -c "from kb.serve_state import load_action_state, save_action_state; print('OK')"`
- **Acceptance Criteria:**
  - [ ] `kb/serve_state.py` exists with 5 functions + 2 constants
  - [ ] `kb/serve_state.py` imports ONLY from stdlib (json, shutil, logging, pathlib)
  - [ ] All 5 functions + 2 constants re-exported from `kb/serve.py`
  - [ ] All tests pass (same baseline as Phase 4: 395 pass, 2 pre-existing failures)
  - [ ] `from kb.serve import load_action_state, ACTION_STATE_PATH` still works
  - [ ] `from kb.publish import publish` still works (it lazy-imports `load_action_state` from `kb.serve`)
- **Files:**
  - `kb/serve_state.py` -- NEW file, ~76 lines
  - `kb/serve.py` -- MODIFY: remove ~76 lines of function bodies, add 7-line import
- **Dependencies:** Phases 1-4 COMPLETE
- **Risk:** LOW. These are pure file I/O functions with no Flask, no route, no external API dependency.

#### Sub-phase 5.2: Extract scanner to `kb/serve_scanner.py`

- **Objective:** Move the scanning and action mapping logic to a dedicated module. This includes the scanner, action mapping, action status helpers, and related constants.
- **Tasks:**
  - [ ] Task 5.2.1: Create `kb/serve_scanner.py` containing:
    - Constants: `ACTION_ID_SEP`, `ACTION_ID_PATTERN`, `VERSIONED_KEY_PATTERN`, `_build_versioned_key_pattern()` (L37-58)
    - `get_action_mapping()` (L74-102, 29 lines)
    - `get_destination_for_action()` (L105-128, 24 lines)
    - `scan_actionable_items()` (L390-489, 100 lines)
    - `get_action_status()` (L492-500, 9 lines)
    - `format_relative_time()` (L503-524, 22 lines)
    - `validate_action_id()` (L585-587, 3 lines)
    - Imports needed: `re`, `json`, `logging`, `pathlib.Path`, `datetime.datetime`, `typing.Optional`
    - **Key design point:** `scan_actionable_items()` and `get_action_mapping()` depend on `KB_ROOT` and `_config` which are module-level state in `kb/serve.py`. These functions should accept these as parameters with defaults that read from the module-level variables, OR they should import them from `kb.serve`. See open question #1.
  - [ ] Task 5.2.2: Handle the `KB_ROOT` and `_config` dependency. Two options (see Open Question #1):
    - **Option A (Parameterize):** Change `scan_actionable_items(kb_root=None)` and `get_action_mapping(config=None)` to accept optional parameters. If None, import from `kb.serve` lazily. Tests that currently patch `kb.serve.KB_ROOT` and `kb.serve._config` would still work because the route handlers in `kb/serve.py` call these functions without arguments, and the defaults would read from `kb.serve`.
    - **Option B (Import from config):** `kb/serve_scanner.py` imports `KB_ROOT` from `kb.config` directly and `_config` from `kb.config.load_config()`. Tests would need their patches updated to target `kb.serve_scanner.KB_ROOT` etc.
  - [ ] Task 5.2.3: In `kb/serve.py`, replace the function definitions + constants with imports from `kb.serve_scanner`:
    ```python
    from kb.serve_scanner import (
        ACTION_ID_SEP, ACTION_ID_PATTERN, VERSIONED_KEY_PATTERN,
        get_action_mapping, get_destination_for_action,
        scan_actionable_items, get_action_status,
        format_relative_time, validate_action_id,
    )
    ```
  - [ ] Task 5.2.4: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 5.2.5: Verify re-exports work: `python3 -c "from kb.serve import scan_actionable_items, VERSIONED_KEY_PATTERN, ACTION_ID_SEP; print('OK')"` AND `python3 -c "from kb.serve_scanner import scan_actionable_items, VERSIONED_KEY_PATTERN; print('OK')"`
  - [ ] Task 5.2.6: Verify test patches still work: `python3 -m pytest kb/tests/test_action_mapping.py kb/tests/test_browse.py -v`
- **Acceptance Criteria:**
  - [ ] `kb/serve_scanner.py` exists with 7 functions + 3 constants/patterns
  - [ ] All functions + constants re-exported from `kb/serve.py`
  - [ ] All tests pass (same baseline)
  - [ ] `patch('kb.serve._config', ...)` in test_action_mapping.py still works
  - [ ] `patch('kb.serve.KB_ROOT', ...)` in test_browse.py still works
  - [ ] `from kb.serve import VERSIONED_KEY_PATTERN` still works (test_judge_versioning.py)
- **Files:**
  - `kb/serve_scanner.py` -- NEW file, ~187 lines
  - `kb/serve.py` -- MODIFY: remove ~187 lines, add 9-line import
- **Dependencies:** Sub-phase 5.1 COMPLETE (scanner uses `load_action_state` from serve_state)
- **Risk:** MEDIUM. The `KB_ROOT` and `_config` dependency requires careful handling to not break test patches. The re-export strategy in `kb/serve.py` means patches targeting `kb.serve.KB_ROOT` and `kb.serve._config` still work because the route handlers reference these names in the `kb.serve` module namespace.

**Critical design note on `KB_ROOT` and `_config` patching:**

The scanner functions (`scan_actionable_items`, `get_action_mapping`) reference module-level variables `KB_ROOT` and `_config`. When we move these functions to `kb/serve_scanner.py`, the functions will reference `kb.serve_scanner.KB_ROOT` etc. But tests patch `kb.serve.KB_ROOT`. This creates a mismatch.

**Solution:** Keep `KB_ROOT` and `_config` definitions in `kb/serve.py` (do NOT move them). The scanner functions should accept them as parameters:
```python
def scan_actionable_items(kb_root=None, config=None):
    """..."""
    if kb_root is None:
        from kb.serve import KB_ROOT
        kb_root = KB_ROOT
    ...
```
Route handlers in `kb/serve.py` call `scan_actionable_items()` without arguments, which triggers the lazy import from `kb.serve` where the patched values live. Direct callers (test_judge_versioning.py) that import `scan_actionable_items` from `kb.serve` get the re-exported function, and when they call it without arguments, it reads from `kb.serve.KB_ROOT` -- matching the test patches.

Alternatively, the scanner functions could read `KB_ROOT` and `_config` at call time from `kb.serve` via lazy import. Either way, the tests continue to work.

#### Sub-phase 5.3: Extract visual pipeline to `kb/serve_visual.py`

- **Objective:** Move the visual pipeline (background thread) functions to a dedicated module. These handle carousel rendering in background threads.
- **Tasks:**
  - [ ] Task 5.3.1: Create `kb/serve_visual.py` containing:
    - `_update_visual_status()` (L225-232, 8 lines)
    - `_find_transcript_file()` (L235-255, 21 lines)
    - `run_visual_pipeline()` (L258-385, 128 lines)
    - Imports needed: `json`, `logging`, `pathlib.Path`, `datetime.datetime`
    - Dependencies on extracted modules: `from kb.serve_state import load_action_state, save_action_state`
    - Dependencies on `kb.serve`: `KB_ROOT`, `ACTION_ID_SEP` (via lazy import or parameter)
    - Lazy imports inside `run_visual_pipeline()`: `from kb.analyze import run_analysis_with_deps, analyze_transcript_file, _save_analysis_to_file, DEFAULT_MODEL` and `from kb.render import render_pipeline` (already lazy in current code)
  - [ ] Task 5.3.2: Handle `KB_ROOT` and `ACTION_ID_SEP` dependency the same way as scanner (lazy import from `kb.serve` or parameterization).
  - [ ] Task 5.3.3: In `kb/serve.py`, replace the function definitions with imports from `kb.serve_visual`:
    ```python
    from kb.serve_visual import (
        _update_visual_status, _find_transcript_file,
        run_visual_pipeline,
    )
    ```
  - [ ] Task 5.3.4: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 5.3.5: Verify re-exports work: `python3 -c "from kb.serve import run_visual_pipeline, _update_visual_status; print('OK')"` AND `python3 -c "from kb.serve_visual import run_visual_pipeline; print('OK')"`
- **Acceptance Criteria:**
  - [ ] `kb/serve_visual.py` exists with 3 functions
  - [ ] All 3 functions re-exported from `kb/serve.py`
  - [ ] All tests pass (same baseline)
  - [ ] `from kb.serve import _update_visual_status` still works (test_serve_integration.py)
  - [ ] `from kb.serve import run_visual_pipeline` still works (test_serve_integration.py)
- **Files:**
  - `kb/serve_visual.py` -- NEW file, ~157 lines
  - `kb/serve.py` -- MODIFY: remove ~157 lines, add 4-line import
- **Dependencies:** Sub-phase 5.1 COMPLETE (visual pipeline uses `load_action_state`, `save_action_state`)
- **Risk:** LOW-MEDIUM. The lazy imports from `kb.analyze` and `kb.render` inside `run_visual_pipeline()` are already the correct pattern and transfer cleanly. The `KB_ROOT` dependency needs the same treatment as the scanner.

#### Sub-phase 5.4: Verify and clean up

- **Objective:** Final verification that everything works end-to-end.
- **Tasks:**
  - [ ] Task 5.4.1: Run full test suite: `python3 -m pytest kb/tests/ -v`
  - [ ] Task 5.4.2: Verify Flask app starts: `python3 -c "from kb.serve import app; print('Routes:', len(app.url_map._rules))"`
  - [ ] Task 5.4.3: Verify all external imports work:
    - `python3 -c "from kb.serve import load_action_state, ACTION_ID_SEP; print('publish OK')"`
    - `python3 -c "from kb.serve import migrate_approved_to_draft; print('migrate OK')"`
    - `python3 -c "from kb.serve import VERSIONED_KEY_PATTERN, scan_actionable_items; print('judge_versioning OK')"`
    - `python3 -c "from kb.serve import get_action_mapping, get_destination_for_action; print('action_mapping OK')"`
    - `python3 -c "from kb.serve import _update_visual_status, run_visual_pipeline; print('visual OK')"`
  - [ ] Task 5.4.4: Verify COMMANDS entry still works: `python3 -c "from kb.__main__ import COMMANDS; print('serve' in COMMANDS)"`
- **Acceptance Criteria:**
  - [ ] All tests pass (same baseline: 395 pass, 2 pre-existing failures)
  - [ ] Flask app creates successfully with all 39 routes
  - [ ] All external imports resolve correctly
  - [ ] `kb serve` COMMANDS entry unchanged
- **Files:** None (verification only)
- **Dependencies:** Sub-phases 5.1-5.3 COMPLETE

### Post-Split File Sizes (Estimated)

| File | Before | After | Change |
|---|---|---|---|
| `kb/serve.py` | 2,372 lines | ~1,952 lines | -420 lines (functions removed, import re-exports added) |
| `kb/serve_state.py` | NEW | ~76 lines | State persistence |
| `kb/serve_scanner.py` | NEW | ~187 lines | Scanner + action mapping |
| `kb/serve_visual.py` | NEW | ~157 lines | Visual pipeline |

Note: `kb/serve.py` at ~1,952 lines is still large, but the remaining code is 39 Flask route handlers + Flask app setup + CLI entry point. Route handlers are inherently coupled to the Flask app and to shared state. Further splitting (e.g., into blueprints) would require a Flask package conversion which is higher risk for lower reward at this point.

### Import Dependency Graph (After Split)

```
kb/serve_state.py     (stdlib only: json, shutil, logging, pathlib)
     ^
     |
kb/serve_scanner.py   (stdlib + kb.serve_state; lazy: kb.serve for KB_ROOT/_config)
     ^
     |
kb/serve_visual.py    (stdlib + kb.serve_state; lazy: kb.serve for KB_ROOT/ACTION_ID_SEP,
     |                 kb.analyze, kb.render)
     |
kb/serve.py           (Flask + all above via imports; keeps routes + app + CLI)
```

No circular imports at module load time. The `serve_scanner -> kb.serve` and `serve_visual -> kb.serve` lazy imports resolve at function call time, after all modules are fully loaded.

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | How should extracted functions access `KB_ROOT` and `_config` (module-level state that stays in `kb/serve.py`)? | A) **Parameterize**: Functions accept optional `kb_root=None`, `config=None` parameters; default to lazy-importing from `kb.serve` B) **Lazy import always**: Functions always do `from kb.serve import KB_ROOT` inside function body C) **Move KB_ROOT/_config to serve_state.py**: Centralize state; update patches | A) is most testable (callers can pass explicit values), but adds function signature noise. B) is simplest, but slightly magical. C) requires updating 16 test patch targets (11 `KB_ROOT`, 5 `_config`). | OPEN |
| 2 | File naming: `serve_state.py` / `serve_scanner.py` / `serve_visual.py` vs shorter names like `state.py` / `scanner.py` / `visual.py`? | A) `serve_` prefix (clear relationship to serve.py) B) No prefix (shorter, relies on context) C) Subdirectory `serve/` (package approach, rejected above for routes but could be used for utilities only -- `kb/serve/state.py` etc.) | Naming preference only. No functional impact. | OPEN |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Do NOT convert to Flask package | Keep as `kb/serve.py` | Too many import consumers, COMMANDS entry, and test patches reference `kb.serve`. Converting would require updating ~100 import lines across 8 test files + 2 source files, with risk of breaking patches. |
| Re-export all moved functions from `kb/serve.py` | Yes | Backward compatibility. External consumers and tests import from `kb.serve`. The re-export pattern worked well in Phase 4 (analyze.py split). |
| Extract state persistence first | Yes | It has zero dependencies on other serve.py functions. Scanner and visual pipeline depend on it. Natural foundation. |
| Keep route handlers in `kb/serve.py` | Yes | 39 route handlers are tightly coupled to Flask `app`, shared state, and each other. Splitting them across files adds complexity (Blueprint registration, cross-file state sharing) without meaningful benefit. The ~1,950 remaining lines are all routes + CLI -- dense but cohesive. |
| Keep `_config` and `KB_ROOT` definitions in `kb/serve.py` | Yes | Tests patch `kb.serve._config` and `kb.serve.KB_ROOT`. Moving these would break all test patches (16 occurrences). |
| Order: state -> scanner -> visual | Yes | Dependency chain: scanner uses `load_action_state` from state; visual uses `load_action_state`/`save_action_state` from state. |
| Keep `check_and_auto_scan()` and `main()` in `kb/serve.py` | Yes | They are trivial (41 lines combined) and tightly coupled to Flask `app.run()` and startup logic. Not worth extracting. |
| Keep `app = Flask(...)` in `kb/serve.py` | Yes | The app instance must be in the same module as route decorators. Moving it would require Blueprint refactoring. |

### Test Baseline
```bash
# Current baseline (confirmed during Phase 4):
# 395 passed, 2 failed (pre-existing carousel template tests)
python3 -m pytest kb/tests/ -v
```

### Test Files Affected

All tests import `from kb.serve import app` (or other symbols) lazily inside test methods. The re-export strategy means **zero test file changes are required**. Tests will continue to import from `kb.serve` and get the re-exported functions.

| Test File | Imports from `kb.serve` | Patches `kb.serve.*` | Change Needed |
|---|---|---|---|
| `test_serve_integration.py` | `app`, `_update_visual_status`, `get_destination_for_action`, `get_action_mapping`, `run_visual_pipeline` | None | None (re-exports) |
| `test_action_mapping.py` | `get_destination_for_action`, `get_action_mapping` | `kb.serve._config` (5x) | None (re-exports; `_config` stays in kb.serve) |
| `test_judge_versioning.py` | `VERSIONED_KEY_PATTERN`, `scan_actionable_items`, `migrate_approved_to_draft` | None | None (re-exports) |
| `test_browse.py` | `app` | `kb.serve.KB_ROOT` (11x) | None (re-exports; `KB_ROOT` stays in kb.serve) |
| `test_iteration_view.py` | `app` | None | None |
| `test_slide_editing.py` | `app` | None | None |
| `test_staging.py` | `app` | None | None |

### Risk Assessment
- **Risk:** MEDIUM overall (LOW for state, MEDIUM for scanner, LOW-MEDIUM for visual)
- **Rollback:** Delete 3 new files, revert import changes in `kb/serve.py`. Git makes this trivial.
- **Key risk:** The `KB_ROOT`/`_config` dependency between scanner functions and `kb/serve.py` module-level state. Requires careful handling to preserve test patching behavior.
- **Mitigation:** Run full test suite after each sub-phase. The re-export pattern is proven (worked in Phase 4).

### Phase 5 Plan Review
- **Gate:** NEEDS_WORK
- **Reviewed:** 2026-02-08
- **Summary:** Plan has accurate line numbers and logical groupings, but a critical defect: moving `ACTION_STATE_PATH` to `serve_state.py` will break 74+ test patches that target `kb.serve.ACTION_STATE_PATH`. The re-export strategy does NOT fix patch targets for variables used by extracted functions (they resolve from their new module namespace, not from `kb.serve`). The plan correctly identifies this class of problem for `KB_ROOT`/`_config` in the scanner section but fails to apply the same analysis to `ACTION_STATE_PATH` in Sub-phase 5.1 and `_update_visual_status` in Sub-phase 5.3. Patch count claim of "16" is severely wrong (actual: 162). Both open questions resolved autonomously.
- **Issues:** 2 critical, 2 major, 4 minor
- **Open Questions Finalized:**
  - Q1: Use Option A (parameterize with lazy-import defaults) -- apply universally to ALL module-level variables
  - Q2: Use `serve_` prefix naming (Option A)
- **Required Fixes Before Execution:**
  1. Keep `ACTION_STATE_PATH` + `PROMPT_FEEDBACK_PATH` defined in `kb/serve.py`; `serve_state.py` functions accept them as parameters
  2. Handle `_update_visual_status` patch in test_serve_integration.py (update 1 test or restructure lazy import)
  3. Correct patch count from 16 to 162
  4. Fix scanner dependency claim (scan_actionable_items does NOT call load_action_state)
  5. Add `AUTO_JUDGE_TYPES` to serve_scanner.py imports (needed by `_build_versioned_key_pattern`)

--> Details: `plan-review-phase5.md`

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
- **Completed:** 2026-02-08
- **Summary:** Phases 1-5 delivered: extracted kb/config.py, deleted 2,462 lines dead code, created kb/transcription.py wrapper, split kb/analyze.py into kb/prompts.py + kb/judge.py, split kb/serve.py into kb/serve_state.py + kb/serve_scanner.py + kb/serve_visual.py. All 5 phases passed code review. Test suite baseline maintained throughout (395 pass, 2 pre-existing failures). Phase 6 (test coverage for kb/core.py) remains as optional future work.
- **Learnings:** Parameterized lazy imports are the key pattern for extracting from god files without breaking test patches. Always verify dead imports are cleaned up in the source file after extraction.
