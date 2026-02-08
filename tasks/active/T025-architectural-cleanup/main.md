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

---

## Code Review Log

### Phase 1
- **Gate:** PASS
- **Reviewed:** 2026-02-08
- **Issues:** 0 critical, 0 major, 1 minor (process: blank execution log)
- **Summary:** Clean extraction. All acceptance criteria verified. All plan review recommendations followed. 395/397 tests pass (2 failures are pre-existing carousel template tests, unrelated). No code issues found.

-> Details: `code-review-phase-1.md`

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
