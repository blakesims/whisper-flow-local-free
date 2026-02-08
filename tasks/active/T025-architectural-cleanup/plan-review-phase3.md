# Plan Review: Phase 3 -- Extract Shared Transcription Wrapper

## Gate Decision: READY

**Summary:** Plan is accurate and well-verified. All 4 call sites (8 import lines) independently confirmed via grep. Line numbers match live code. sys.path handling is correct. Naming question resolved. Three minor issues found, none blocking.

---

## Open Questions Validation

### Invalid (Auto-Decide)
| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Wrapper module name: `kb/transcription.py` vs `kb/whisper_service.py` | Resolved per user instruction: use `kb/transcription.py`. The verb (transcribe.py = CLI dispatcher) vs noun (transcription.py = service wrapper) distinction is a standard naming convention. No confusion risk in practice -- developers will see the docstrings. |

### New Questions Discovered

None.

---

## Verification Results

### 1. All app.* imports found?

Confirmed. `grep -r "from app[. ]|import app[. ]" kb/ --include="*.py"` returns exactly 8 lines across 4 files:

| File | Line | Import |
|------|------|--------|
| `kb/core.py` | 419 | `from app.core.transcription_service_cpp import get_transcription_service` |
| `kb/core.py` | 420 | `from app.utils.config_manager import ConfigManager` |
| `kb/sources/zoom.py` | 261 | `from app.core.transcription_service_cpp import get_transcription_service` |
| `kb/sources/zoom.py` | 262 | `from app.utils.config_manager import ConfigManager` |
| `kb/sources/cap_clean.py` | 113 | `from app.core.transcription_service_cpp import get_transcription_service` |
| `kb/sources/cap_clean.py` | 114 | `from app.utils.config_manager import ConfigManager` |
| `kb/videos.py` | 190 | `from app.core.transcription_service_cpp import get_transcription_service` |
| `kb/videos.py` | 191 | `from app.utils.config_manager import ConfigManager` |

All match the plan exactly. No missed call sites.

### 2. Line numbers correct?

Spot-checked all 4 call sites (not just 2). Every line number in the plan matches the live code:

- **kb/core.py:416-420** -- Confirmed. Line 416 has the comment, 417 has `import sys`, 418 has `sys.path.insert`, 419-420 have the app imports.
- **kb/sources/cap_clean.py:111-114** -- Confirmed. Line 111 has `import sys`, 112 has `sys.path.insert`, 113-114 have the app imports.
- **kb/sources/zoom.py:261-262** -- Confirmed. Lines 261-262 have the app imports with no inline sys.path (module-level at line 46).
- **kb/videos.py:189-191** -- Confirmed. Line 189 has `try:`, 190-191 have the app imports inside the try block.

### 3. sys.path handling

The plan correctly identifies:

**Remove inline sys.path hacks from 2 files:**
- `kb/core.py` lines 417-418: `import sys` + `sys.path.insert(0, ...)` inside `transcribe_audio()`. Safe to remove because (a) `sys` has no other usage in this function, and (b) the wrapper handles path setup.
- `kb/sources/cap_clean.py` lines 111-112: `import sys` + `sys.path.insert(0, ...)` inside function. Safe to remove because (a) `sys` is already imported at module level (line 13) for other uses (stdin, exit), and (b) the wrapper handles path setup.

**Keep module-level sys.path in 2 files:**
- `kb/sources/zoom.py` line 46: Module-level `sys.path.insert` -- serves `from kb.core import ...` at line 48. Correct to keep.
- `kb/videos.py` line 34: Module-level `sys.path.insert` -- serves `from kb.core import ...` at line 37. Correct to keep.

**Wrapper path calculation:** `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` from `kb/transcription.py` yields the project root. This matches `kb/core.py`'s calculation (also 2 levels up). The `kb/sources/` files use 3 levels because they are one directory deeper. The wrapper at `kb/` level using 2 levels is correct.

### 4. Naming question

Resolved: use `kb/transcription.py`. The existing `kb/transcribe.py` is a CLI dispatcher (verb form). The new `kb/transcription.py` is a service wrapper (noun form). Standard convention, no conflict.

### 5. Wrapper design

The ~15 line wrapper is correct and minimal. Analysis:

- **Re-exports at module level:** When a call site does `from kb.transcription import get_transcription_service`, Python loads the wrapper module, which triggers the `app.core` import. Since all 4 call sites use lazy imports (inside functions), this import-time cost only occurs when transcription is actually needed. Correct.
- **Error handling:** The wrapper deliberately does NOT add error handling. This is the right choice because:
  - `kb/videos.py` already wraps the import in try/except ImportError (line 189-194). This will still work because a failed wrapper module load raises ImportError.
  - The other 3 call sites do not catch ImportError, which is intentional -- they expect the transcription service to be available.
  - Adding error handling in the wrapper would suppress errors that call sites need to see.
- **`__all__` export list:** Correct -- makes the public API explicit.
- **No `kb.*` imports:** Correct -- the wrapper only imports from `app.*` and stdlib.

---

## Issues Found

### Critical (Must Fix)

None.

### Major (Should Fix)

None.

### Minor

1. **cap_clean.py `import sys` at line 111 is redundant but harmless** -- The plan says to remove `import sys` at line 111. This is safe because `sys` is already imported at module level (line 13). However, the plan description in Task 2.3 says "REMOVE: `import sys` (line 111)" -- the executor should be aware that `sys` remains available from the module-level import and should NOT be confused into thinking `sys` is being removed entirely from the file.

2. **Acceptance criteria says "zero `from app.*` imports in `kb/`"** -- This is correct for the current state, but if future phases add new `app.*` imports, this AC would need updating. Not a current issue, just noting for context.

3. **Plan references line numbers from current branch** -- The plan was written against the current state of `refactor/architectural-cleanup` branch. If any other changes land on this branch before Phase 3 executes, line numbers could drift. Low risk since this is an active cleanup task with sequential phases.

---

## Plan Strengths

- Exhaustive verification of all 4 call sites with correct line numbers
- Clear distinction between inline sys.path hacks to remove vs module-level ones to keep
- Correct decision to keep lazy import pattern at call sites
- Proper handling of the try/except ImportError in videos.py
- Minimal wrapper design -- no over-engineering
- Risk assessment is realistic (low risk, trivial rollback)

---

## Recommendations

### Before Proceeding

- [x] Resolve naming question (resolved: `kb/transcription.py`)
- No other blockers

### Consider Later

- The broader sys.path hack pattern across kb/ modules (6+ files with module-level sys.path.insert) could be addressed by proper package installation (`pip install -e .`), but that is out of scope for this phase.
