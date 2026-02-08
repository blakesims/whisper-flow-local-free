# Task: Architectural Cleanup & Technical Debt

## Task ID
T025

## Meta
- **Status:** PLANNING
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

## Proposed Phases

### Phase 1: Extract `kb/config.py` (LOW RISK)
- Move `load_config()`, `get_paths()`, `expand_path()`, `DEFAULTS` from `kb/__main__.py` to `kb/config.py`
- Update all 11 importing modules to use `from kb.config import ...`
- Eliminates circular dependency, no behavior change
- Add config caching (load once, not 8x)

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
