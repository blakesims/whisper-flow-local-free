# Plan Review: Phase 4 -- Split `kb/analyze.py`

## Gate Decision: READY (with required fix)

**Summary:** The plan is well-structured, line numbers are verified accurate, the circular dependency strategy is sound, and external consumer analysis is complete. One critical gap found: `DEFAULT_MODEL` is missing from `kb/judge.py` imports, which would cause a `NameError` at module load time. This is a simple fix (add one import line). The post-split line count estimates are inaccurate by ~270 lines but that is documentation-only. All three open questions can be resolved autonomously without human input.

---

## Verification Results

### Function Line Numbers -- ALL CORRECT

Every function start/end line claimed in the plan was independently verified against the live code on the `refactor/architectural-cleanup` branch:

| Function | Plan Claims | Actual | Status |
|---|---|---|---|
| `format_prerequisite_output` | 619-655 | 619-655 | MATCH |
| `substitute_template_vars` | 658-678 | 658-678 | MATCH |
| `render_conditional_template` | 681-740 | 681-740 | MATCH |
| `resolve_optional_inputs` | 868-909 | 868-909 | MATCH |
| `_get_starting_round` | 984-1011 | 984-1011 | MATCH |
| `_build_history_from_existing` | 1014-1046 | 1014-1046 | MATCH |
| `_build_score_history` | 1049-1067 | 1049-1067 | MATCH |
| `_update_alias` | 1070-1081 | 1070-1081 | MATCH |
| `run_with_judge_loop` | 1084-1322 | 1084-1322 | MATCH |
| `AUTO_JUDGE_TYPES` | 1326-1328 | 1326-1328 | MATCH |
| `run_analysis_with_auto_judge` | 1331-1431 | 1331-1431 | MATCH |

### External Consumer Imports -- ALL CORRECT

| Consumer | Plan Claims | Verified | Status |
|---|---|---|---|
| `kb/serve.py:33` | `list_analysis_types`, `load_analysis_type`, `ANALYSIS_TYPES_DIR`, `AUTO_JUDGE_TYPES`, `run_with_judge_loop` (module-level) | Line 33: exact match | MATCH |
| `kb/serve.py:280` | `run_analysis_with_deps`, `analyze_transcript_file`, `_save_analysis_to_file`, `DEFAULT_MODEL` (lazy) | Line 280: exact match | MATCH |
| `kb/inbox.py:37` | `analyze_transcript_file`, `list_analysis_types` (module-level) | Line 37: exact match | MATCH |
| `kb/sources/paste.py:253` | `analyze_transcript_file` (lazy) | Line 253: exact match | MATCH |
| `kb/sources/file.py:191` | `analyze_transcript_file` (lazy) | Line 191: exact match | MATCH |
| `kb/sources/zoom.py:514` | `analyze_transcript_file` (lazy) | Line 514: exact match | MATCH |
| `kb/sources/cap_clean.py:327` | `analyze_transcript` (lazy) | Line 327: exact match | MATCH |
| `kb/videos.py:793` | `get_decimal_defaults`, `analyze_transcript_file` (lazy) | Line 793: exact match | MATCH |
| `kb/__main__.py:220` | `scan_missing_by_decimal` (lazy) | Line 220: exact match | MATCH |
| `kb/__main__.py:365` | `list_analysis_types` (lazy) | Line 365: exact match | MATCH |
| `kb/__main__.py:491` | `list_analysis_types` (lazy) | Line 491: exact match | MATCH |
| `kb/__init__.py:31` | `analyze_transcript`, `analyze_transcript_file`, `list_analysis_types` (lazy via `__getattr__`) | Line 30-32: exact match | MATCH |

### Test File Imports -- ALL CORRECT

| Test File | Plan Claims | Verified | Status |
|---|---|---|---|
| `test_compound_analysis.py` | `substitute_template_vars`, `format_prerequisite_output`, `load_analysis_type`, `run_analysis_with_deps` | Confirmed via grep (lines 23, 33, 47, 61, 71, 89, 100, 128, 155, 215) | MATCH |
| `test_conditional_template.py` | `render_conditional_template`, `substitute_template_vars`, `resolve_optional_inputs` | Confirmed: module-level import at line 17, plus lazy imports at 210, 221, 236, 248, 259 | MATCH |
| `test_judge_versioning.py` | `_get_starting_round`, `_build_history_from_existing`, `_build_score_history`, `_update_alias`, `run_with_judge_loop`, `AUTO_JUDGE_TYPES`, `resolve_optional_inputs`, `render_conditional_template` | Confirmed via grep (40+ import sites) | MATCH |

### Test Patch Targets -- VERIFIED

| Test File | Patches `kb.analyze.*` | Will Re-export Work? |
|---|---|---|
| `test_compound_analysis.py` | `kb.analyze._config`, `kb.analyze._paths`, `kb.analyze.ANALYSIS_TYPES_DIR`, `kb.analyze.analyze_transcript` | Yes -- these stay in or are re-exported from `kb.analyze` |
| `test_judge_versioning.py` | `kb.analyze.run_analysis_with_deps`, `kb.analyze.analyze_transcript` | Yes -- but see Critical Issue below |

### Circular Dependency Analysis -- CORRECT

The plan's analysis is sound:
- `kb/prompts.py` imports only from stdlib (`re`, `json`) -- leaf module, no cycles possible
- `kb/judge.py` imports from `kb/prompts.py` at module level (safe -- prompts is a leaf)
- `kb/judge.py` lazy-imports from `kb/analyze.py` inside function bodies (safe -- resolved at call time, after all modules loaded)
- `kb/analyze.py` imports from `kb/prompts.py` and `kb/judge.py` at module level for re-export (safe -- one direction at load time)
- The `analyze -> judge -> analyze` cycle is broken by the lazy import pattern

This matches the existing codebase convention (lazy imports used throughout `kb/`).

---

## Open Questions Validation

### Q1: Should "missing analyses" feature (~355 lines) be extracted to `kb/missing.py`?

**Recommendation: Auto-decide -- Option B (leave in `kb/analyze.py` for now)**

This is not a genuine user-level decision. It is a scope/timing question that should be decided by the executor based on risk appetite. The correct answer is B: leave it in `analyze.py` for now. Reasons:
- The missing analyses functions are tightly coupled to `get_all_transcripts`, `analyze_transcript_file`, and `load_registry` -- all in analyze.py
- Adding a 4th sub-phase increases the scope and risk of an already MEDIUM RISK phase
- The functions can be extracted in a future phase if needed
- Even without extracting missing analyses, analyze.py drops from 2,095 to ~1,498 lines -- a meaningful improvement

### Q2: Should Sub-phase 4.3 (updating external imports) be mandatory or optional?

**Recommendation: Auto-decide -- Option B (optional/deferred)**

This is not a genuine user-level decision. The re-exports guarantee backward compatibility, so 4.3 is purely cosmetic. Making it optional reduces risk and scope. If the user wants cleaner imports later, it can be done as a separate micro-task. The plan already labels it "optional optimization" which is the right framing.

### Q3: Should `console = Console()` in `kb/judge.py` be shared or separate?

**Recommendation: Auto-decide -- Option A (separate instance)**

This is definitively not a user-level decision. The plan itself notes that "every `kb/*.py` file already creates its own `Console()` instance." Creating a new one is consistent with the existing pattern and avoids adding a shared-state module. The answer is obvious: follow the existing pattern.

**All 3 open questions resolved. No human input needed.**

---

## Issues Found

### CRITICAL (Must Fix Before Execution)

1. **`DEFAULT_MODEL` missing from `kb/judge.py` imports**

   Both `run_with_judge_loop` (line 1088) and `run_analysis_with_auto_judge` (line 1334) use `DEFAULT_MODEL` as a **default parameter value** in their function signatures:
   ```python
   def run_with_judge_loop(..., model: str = DEFAULT_MODEL, ...):
   def run_analysis_with_auto_judge(..., model: str = DEFAULT_MODEL, ...):
   ```

   Default parameter values are evaluated at function definition time (module load time), NOT at call time. This means `DEFAULT_MODEL` must be available when `kb/judge.py` is first imported.

   The plan's Task 4.2.2 lists the module-level imports for `kb/judge.py` as:
   ```python
   import json
   import time
   from datetime import datetime
   from rich.console import Console
   from rich.panel import Panel
   from kb.prompts import format_prerequisite_output, resolve_optional_inputs
   ```

   `DEFAULT_MODEL` is missing. Without it, importing `kb/judge.py` will raise a `NameError`.

   **Fix:** Add `DEFAULT_MODEL` to the module-level imports in `kb/judge.py`. Since `DEFAULT_MODEL` depends on `kb.config` (which is a leaf module with no circular import risk), the cleanest approach is:
   ```python
   from kb.config import load_config, DEFAULTS
   _config = load_config()
   DEFAULT_MODEL = _config.get("defaults", {}).get("gemini_model", DEFAULTS["defaults"]["gemini_model"])
   ```
   Or alternatively, import it from `kb.analyze`:
   ```python
   from kb.analyze import DEFAULT_MODEL
   ```
   The second option is simpler but creates a module-level import from `kb.analyze` into `kb.judge`, which the plan was trying to avoid. However, since `kb.analyze` already imports from `kb.judge` for re-exports, this would create a genuine circular import at module load time.

   Therefore, the correct fix is to compute `DEFAULT_MODEL` from `kb.config` directly in `kb/judge.py`, or to change the function signatures to use `model: str | None = None` with a body-level default resolution pattern:
   ```python
   def run_with_judge_loop(..., model: str | None = None, ...):
       if model is None:
           from kb.analyze import DEFAULT_MODEL
           model = DEFAULT_MODEL
   ```

   The `kb.config` approach is recommended since it is simple, has no circular import risk, and follows the same pattern already used by `kb/analyze.py` line 54.

### MAJOR (Should Fix)

2. **Post-split line count estimates are significantly wrong**

   The plan claims:
   - `kb/analyze.py` goes from 2,096 to ~1,230 lines (-866 lines)

   Independent calculation:
   - Prompt functions removed: 164 lines (619-740 + 868-909, including inter-function blanks)
   - Judge functions removed: 448 lines (984-1431, including inter-function blanks)
   - Total removed: ~612 lines
   - Re-export imports added: ~15 lines
   - Net reduction: ~597 lines
   - Actual remaining: 2,095 - 597 = ~1,498 lines

   The plan overestimates the reduction by ~270 lines. This does not affect correctness of the extraction, but the "Post-Split File Sizes" table in the plan is misleading. The executor should not expect a ~1,230 line result.

### MINOR

3. **Sub-phase 4.1 claims prompts.py imports "ONLY from stdlib (`re`, `json`)"**

   This is correct, but worth noting that `substitute_template_vars` and `render_conditional_template` both do `import re` inside the function body (not at module level). When extracting to `kb/prompts.py`, these should be moved to a single module-level `import re` for cleanliness. The plan's Task 4.1.1 already specifies this ("Imports needed: `import re`, `import json`"), so this is just an implementation note.

4. **`resolve_optional_inputs` calls `format_prerequisite_output` internally**

   The plan does not explicitly note that `resolve_optional_inputs` (line 907: `context[opt_input] = format_prerequisite_output(existing_analysis[opt_input])`) calls `format_prerequisite_output`, which means both must be in the same module or one must import the other. Since both are going to `kb/prompts.py`, this works naturally. But if the executor were to split them differently (e.g., putting `resolve_optional_inputs` elsewhere), it would break. This is covered implicitly by the plan but could be documented for clarity.

5. **Plan does not mention `run_with_judge_loop` also uses `Panel` from Rich**

   The plan's Task 4.2.2 lists `from rich.panel import Panel` in the imports, so this is actually accounted for. But the plan's narrative about what `run_with_judge_loop` depends on (in the "Judge loop orchestration" row of the responsibility table, line 828) says "Depends on: `analyze_transcript`, `run_analysis_with_deps`, `load_analysis_type`, `resolve_optional_inputs`, `format_prerequisite_output`, `_save_analysis_to_file`, console" -- it does not mention `Panel`, `json`, `time`, or `datetime`. This is a documentation completeness issue only.

6. **`run_analysis_with_auto_judge` also uses `console` and `Panel` directly**

   These are accounted for in the import list (Task 4.2.2) but not in the dependency narrative.

---

## Plan Strengths

- Function line numbers are 100% accurate across all 31 functions
- External consumer analysis is complete and correct -- every import site verified
- Test file analysis is thorough, covering both direct imports and patch targets
- The circular dependency strategy (lazy imports inside function bodies) is well-reasoned and matches existing codebase patterns
- The re-export strategy for backward compatibility is correct and ensures zero breakage for external consumers
- The sub-phase ordering (prompts first, then judge) is correct since judge depends on prompts
- The decision to keep `_save_analysis_to_file` in `kb/analyze.py` is correct -- it avoids creating an additional dependency direction
- Test patch semantics are correctly analyzed -- patches on `kb.analyze.analyze_transcript` will be seen by `kb/judge.py`'s lazy imports

---

## Recommendations

### Before Proceeding (Required)
- [ ] Fix the `DEFAULT_MODEL` gap in `kb/judge.py` -- add `DEFAULT_MODEL` computation from `kb.config` to the module-level imports in Task 4.2.2
- [ ] Update the post-split line count estimates (documentation only, does not block execution, but the executor should know the real numbers)

### Resolve Open Questions (as recommended above)
- [ ] Q1: Leave "missing analyses" in `analyze.py` (Option B)
- [ ] Q2: Make Sub-phase 4.3 optional (Option B)
- [ ] Q3: Create separate `Console()` instance (Option A)

### Consider Later
- The "missing analyses" feature (~355 lines) is a good candidate for a future Phase 4.5 extraction if the codebase continues growing
- If Sub-phase 4.3 is deferred, consider doing it as the first task of Phase 5 planning to clean up import paths before the `kb/serve.py` split
