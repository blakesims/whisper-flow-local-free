# Plan Review: Phase 2 - Delete Confirmed Dead Code

## Gate Decision: READY

**Summary:** The deletion plan is thorough and the dead code verification is accurate. All 6 app/core files are genuinely dead -- independently verified via grep across the entire repo. The 4 dead scripts and 1 build script are also confirmed unreferenced. One major gap found: `.cursor/rules/` files reference `setup.py` extensively and are not addressed in the plan. Two minor line count discrepancies. Open questions resolved.

---

## Open Questions Validation

### Invalid (Auto-Decide)

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Should `scripts/build_app.sh` be deleted alongside `setup.py`? | Yes, delete both. `build_app.sh` runs `python setup.py py2app`, and `setup.py` references `app/main.py` which does not exist. The entire chain is dead. No reason to keep a broken script for reference when git history preserves it. |
| 2 | Should `APPLE_SILICON_OPTIMIZATION.md` be deleted too? | No, keep it. Despite the planner's note that "it documents the benchmark scripts being deleted," this is incorrect. The doc contains general Apple Silicon optimization knowledge for `faster-whisper` (device config, compute types, performance notes, alternatives). It does NOT reference `compare_whisper_implementations.py` or `test_cpu_optimization.py`. The content is useful reference material independent of the deleted scripts. |

### New Questions Discovered

None. Both open questions have clear answers.

---

## Verification Results

### Spot-Check: Dead Code Claims (3 of 6 files independently verified)

**1. `app/core/gemini_service.py`** -- CONFIRMED DEAD
- Grep for `gemini_service` across entire repo: Only referenced by `app/core/transcript_enhancer.py` (line 13, relative import). No other Python files import it. Task docs mention it but that is documentation only.

**2. `app/core/meeting_transcript.py`** -- CONFIRMED DEAD
- Grep for `meeting_transcript` across entire repo: Imported by `app/core/transcript_enhancer.py` (dead), `app/core/transcription_service_ext.py` (dead), `_legacy/ui/enhancement_worker.py`, `_legacy/ui/meeting_worker.py`, and `_legacy/ui/main_window.py` (all `_legacy/`). Zero live importers.
- The planner's audit correctly identified all 5 import sites.

**3. `app/core/video_extractor.py`** -- CONFIRMED DEAD
- Grep for `video_extractor` across entire repo: Only imported by `app/core/transcript_enhancer.py` (line 14, relative import). Zero live importers.

**4. `app/core/transcription_service_ext.py`** -- CONFIRMED DEAD (bonus check)
- Grep confirmed: Only imported by `_legacy/ui/meeting_worker.py` (line 10) and `_legacy/ui/main_window.py` (line 16). Both are legacy dead code.

### Class Name Cross-Reference

Grepped for all class names (`GeminiService`, `TranscriptEnhancer`, `TranscriptSectioner`, `MeetingTranscript`, `TranscriptionServiceExt`, `VideoExtractor`) restricted to `*.py` files. Every reference is either:
- Within the dead files themselves (definitions and internal usage)
- Within `_legacy/ui/` files

Zero references from any live code path.

### Top-Level Scripts

**`transcribe_file.py`** -- CORRECTLY EXCLUDED
- Referenced in `pyproject.toml` (`py-modules = ["transcribe_file"]`), `CLAUDE.md` (Raycast file transcription section), and `README.md`. This is live code.

**Dead scripts** -- CONFIRMED UNREFERENCED
- `compare_whisper_implementations.py`: Standalone benchmark. No project imports in or out.
- `test_cpu_optimization.py`: Standalone benchmark. No project imports in or out.
- `create_icon.py`: One-off generator. No project imports in or out.
- `setup.py`: References `app/main.py` which does not exist. Only referenced by dead `build_app.sh` and stale `.cursor/rules/` docs.

### Symlink Verification

Confirmed: `_legacy/app/core` is a symlink to `../../app/core` (directory-level symlink). After deleting 6 files from `app/core/`, the corresponding paths under `_legacy/app/core/` will resolve to nothing. Remaining live files (e.g., `transcription_service.py`, `transcription_service_cpp.py`) will still be accessible. Since `_legacy/` is entirely dead code, broken symlinks inside it have zero impact on live functionality or tests.

### `app/core/__init__.py`

Verified: Contains only whitespace. No re-exports of any dead modules. Deletion of the 6 files will not break any `__init__.py` imports.

### Test Baseline

Ran `python3 -m pytest kb/tests/ -v` and confirmed:
- 395 passed
- 2 failed (pre-existing `test_carousel_templates.py` failures, unrelated to this work)
- Matches the plan's stated baseline exactly.

### Line Count Audit

The 6 app/core files total exactly 1,742 lines as claimed. Individual counts all match.

For the 5 scripts, minor discrepancies (off by 1-2 lines each, likely trailing newline counting differences):
- `setup.py`: 35 actual vs 36 claimed
- `build_app.sh`: 41 actual vs 42 claimed
- `compare_whisper_implementations.py`: 352 actual vs 353 claimed
- `test_cpu_optimization.py`: 107 actual vs 108 claimed
- `create_icon.py`: 147 actual vs 145 claimed

These are cosmetic and do not affect the plan.

---

## Issues Found

### Critical (Must Fix)

None.

### Major (Should Fix)

1. **`.cursor/rules/` files reference `setup.py` extensively** -- The plan updates `CLAUDE.md` but misses two `.cursor/rules/` files:
   - `.cursor/rules/project-architecture.mdc` line 36: lists `setup.py` as the build script
   - `.cursor/rules/integration-points.mdc` lines 36-50: entire "Application Packaging (py2app)" section references `setup.py`, its options, and the build workflow. Line 82 also references `setup.py` in the Raycast integration section.

   **Fix:** Add a task to either update or remove these stale `.cursor/rules/` sections. If the project no longer uses Cursor, consider whether these files should be cleaned up entirely (separate scope). At minimum, the `setup.py` references should be removed to avoid confusion.

### Minor

1. **Script line counts are slightly off** -- `setup.py` claimed 36 lines (actual: 35), `build_app.sh` claimed 42 (actual: 41), etc. This is purely cosmetic and has zero impact on execution.

2. **`APPLE_SILICON_OPTIMIZATION.md` question is mis-framed** -- The planner said "it documents the benchmark scripts being deleted" but the doc actually covers `faster-whisper` Apple Silicon optimization knowledge and does not reference the benchmark scripts at all. The question should be answered "Keep" and closed, not left open.

3. **Total deletion line count discrepancy** -- The plan claims 2,426 total lines. Actual total across all 11 files is 1,742 + 682 = 2,424. Off by 2, matching the per-file discrepancies above. Not material.

---

## Plan Strengths

- Exhaustive verification audit for each file with import tracing, class reference tracing, and dynamic import risk assessment.
- Correct identification and exclusion of `transcribe_file.py` as live code.
- Smart two-phase approach (core files first, then scripts) to isolate issues between test runs.
- Proper handling of the symlink situation with clear rationale.
- Good acceptance criteria including specific import smoke tests for live `app.core` modules.

---

## Recommendations

### Before Proceeding
- [x] Resolve Q1: Delete `build_app.sh` alongside `setup.py` -- YES (auto-decided)
- [x] Resolve Q2: Keep `APPLE_SILICON_OPTIMIZATION.md` -- it is not related to the benchmark scripts (auto-decided)
- [ ] Add task to Phase 2 to clean up `.cursor/rules/project-architecture.mdc` and `.cursor/rules/integration-points.mdc` references to `setup.py`

### Consider Later
- The `.cursor/rules/` files appear to be auto-generated and quite stale (still reference `app/main.py` which does not exist). A broader cleanup of these files may be warranted but is out of scope for this task.
