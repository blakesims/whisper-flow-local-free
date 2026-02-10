# Plan Review: Phase 5 -- Split kb/serve.py

## Gate Decision: NEEDS_WORK

**Summary:** The plan is well-structured with 100% accurate line numbers and logical function groupings. However, it has one critical defect: the `ACTION_STATE_PATH` patching problem. The plan proposes moving `ACTION_STATE_PATH` to `serve_state.py` alongside the functions that use it, but 74+ test patches target `kb.serve.ACTION_STATE_PATH`. Re-exporting the constant does NOT fix this because the extracted functions resolve the variable from their own module namespace (`serve_state`), not from `kb.serve`. This same class of problem affects `_update_visual_status` in Sub-phase 5.3. The plan correctly identifies this class of problem for `KB_ROOT`/`_config` in the scanner section but fails to apply the same analysis to `ACTION_STATE_PATH` in Sub-phase 5.1 and `_update_visual_status` in Sub-phase 5.3.

---

## Verification Results

### Line Numbers
All 16 function/constant line number claims verified against the live code. Every single one is accurate.

### Function Groupings
The three extraction targets are logically coherent:
- **serve_state.py**: Pure file I/O (state + feedback persistence) -- clean separation
- **serve_scanner.py**: Scanner + action mapping -- depends on state, correct ordering
- **serve_visual.py**: Visual pipeline -- depends on state, correct ordering

### External Consumer Table
Verified against grep results. The plan's table at lines 1178-1191 is accurate. All import sites confirmed:
- `kb/publish.py:126` -- `load_action_state`, `ACTION_ID_SEP` (lazy) -- confirmed
- `kb/migrate.py:38` -- `migrate_approved_to_draft` (lazy) -- confirmed
- All 7 test files -- confirmed with correct import lists

### Post-Split File Size Estimates
The plan estimates `kb/serve.py` drops from 2,372 to ~1,952 lines (-420). This arithmetic checks out: ~76 (state) + ~187 (scanner) + ~157 (visual) = ~420 lines extracted, replaced by ~20 lines of import statements.

---

## Open Questions Validation

### Q1: KB_ROOT/_config access strategy -- AUTO-DECIDE

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | How should extracted functions access `KB_ROOT` and `_config`? | **Option A (Parameterize)** -- but this must ALSO apply to `ACTION_STATE_PATH` and `PROMPT_FEEDBACK_PATH`, which the plan currently misses. See Critical Issue #1 below. |

**Rationale:** Option A (parameterize with lazy-import defaults) is the only approach that preserves test patching behavior without updating 100+ patch sites. Option B (lazy import always) works too but is slightly less testable. Option C (move to serve_state.py, update patches) requires updating 74+ `ACTION_STATE_PATH` patches, 83+ `KB_ROOT` patches, and 5 `_config` patches -- a massive scope increase the plan does not account for.

**Recommendation:** Use Option A universally. Functions accept optional parameters; when None, they lazy-import from `kb.serve`. This pattern:
- Preserves ALL existing test patches (they target `kb.serve.*`)
- Allows direct testing with explicit values
- Adds minimal signature noise (defaults handle it transparently)
- Is consistent across all three extraction modules

### Q2: File naming convention -- AUTO-DECIDE

| # | Question | Recommendation |
|---|----------|----------------|
| 2 | `serve_state.py` / `serve_scanner.py` / `serve_visual.py` vs shorter names? | **Option A (`serve_` prefix)** -- the plan's reasoning is sound. |

**Rationale:** The `serve_` prefix is the correct choice. The `kb/` directory already has `config.py`, `core.py`, `videos.py`, etc. Using bare names like `state.py` or `scanner.py` would be ambiguous. The `serve_` prefix clearly communicates these are extracted utilities from `serve.py`, not standalone modules. No functional impact either way, but developer clarity matters for a codebase this size.

---

## Issues Found

### CRITICAL (Must Fix Before Execution)

**1. ACTION_STATE_PATH patching will break 74+ tests**

The plan proposes moving `ACTION_STATE_PATH` to `serve_state.py` (Task 5.1.1) and re-exporting it from `serve.py` (Task 5.1.2). The plan states this "ensures all external consumers... continue to work unchanged." This is WRONG for patch targets.

Re-exporting creates a new binding in `kb.serve`'s namespace, but the functions `load_action_state()` and `save_action_state()` that USE `ACTION_STATE_PATH` will now live in `serve_state.py` and resolve the variable from `serve_state`'s namespace. When tests do:

```python
with patch("kb.serve.ACTION_STATE_PATH", state_file):
    # call route handler -> calls load_action_state() in serve_state.py
    # load_action_state() reads serve_state.ACTION_STATE_PATH (UNPATCHED)
```

The patch targets `kb.serve.ACTION_STATE_PATH` but `load_action_state()` reads `serve_state.ACTION_STATE_PATH` -- a different binding. The test's temp file will be ignored and the function will try to read the REAL `~/.kb/action-state.json`.

**Affected test files and patch counts:**
- `test_staging.py`: 20 `ACTION_STATE_PATH` patches
- `test_iteration_view.py`: 21 `ACTION_STATE_PATH` patches
- `test_slide_editing.py`: 17 `ACTION_STATE_PATH` patches
- `test_serve_integration.py`: 12 `ACTION_STATE_PATH` patches
- `test_judge_versioning.py`: 4 `ACTION_STATE_PATH` patches
- **Total: 74 `ACTION_STATE_PATH` patches across 5 test files**

The plan's "Module-Level Patch Targets in Tests" section (lines 1192-1198) only mentions `KB_ROOT` (11 in test_browse) and `_config` (5 in test_action_mapping), completely missing the 74 `ACTION_STATE_PATH` patches. The plan also misses that `KB_ROOT` is patched in test_staging (20x), test_iteration_view (21x), test_slide_editing (17x), test_serve_integration (13x), and test_judge_versioning (1x) -- totaling 83 `KB_ROOT` patches, not just 11.

**Fix:** Apply the same parameterization strategy (Option A from Q1) to ALL module-level variables used by extracted functions:
- `ACTION_STATE_PATH` and `PROMPT_FEEDBACK_PATH` must stay defined in `kb/serve.py`
- `serve_state.py` functions accept these as optional parameters with lazy-import defaults
- Same pattern as proposed for `KB_ROOT`/`_config` in the scanner section

---

**2. _update_visual_status patch in test_serve_integration.py will break**

Line 626 of `test_serve_integration.py` patches `kb.serve._update_visual_status` with a `side_effect=track_status` to intercept status update calls from within `run_visual_pipeline`. After extraction:

- `run_visual_pipeline()` moves to `serve_visual.py`
- `_update_visual_status()` also moves to `serve_visual.py`
- `run_visual_pipeline()` calls `_update_visual_status()` via direct name resolution within `serve_visual` module
- Patching `kb.serve._update_visual_status` replaces the re-exported binding in `kb.serve` but does NOT affect the call from within `serve_visual.py`

This will cause `test_sets_ready_on_successful_carousel_render` to fail silently (the `track_status` side effect will never fire, and the assertion `assert "generating" in statuses` will fail).

**Fix:** Either:
- (a) Keep `_update_visual_status` in `kb/serve.py` (extract only `_find_transcript_file` and `run_visual_pipeline`). But then `run_visual_pipeline` in `serve_visual.py` needs to import it from `kb.serve`, creating a circular-ish dependency.
- (b) In `serve_visual.py`, have `run_visual_pipeline` reference `_update_visual_status` via a lazy import from `kb.serve` (not via direct module-level reference). This way, patching `kb.serve._update_visual_status` will be seen by `run_visual_pipeline`.
- (c) Update the 1 test to patch `kb.serve_visual._update_visual_status` instead. Minimal scope, clearly correct.

**Recommended:** Option (c) -- update the 1 test patch to target `kb.serve_visual._update_visual_status`. It is the only occurrence, and it is the cleanest fix. If the plan's scope says "zero test changes," this is a minor exception worth making explicit.

### MAJOR (Should Fix)

**3. Missing `PROMPT_FEEDBACK_PATH` from patching analysis**

The plan treats `PROMPT_FEEDBACK_PATH` identically to `ACTION_STATE_PATH` (both move to `serve_state.py`). While no tests currently patch `PROMPT_FEEDBACK_PATH` (verified: 0 occurrences), the functions `load_prompt_feedback()` and `save_prompt_feedback()` reference it. If ANY test patches `kb.serve.PROMPT_FEEDBACK_PATH` in the future, the same breakage applies.

**Fix:** Apply the same strategy: keep `PROMPT_FEEDBACK_PATH` defined in `kb/serve.py`, pass as parameter to `serve_state.py` functions. This is not blocking now but is a consistency issue -- the plan should treat all extracted module-level variables the same way.

**4. Plan's "16 KB_ROOT/config patches" count is severely wrong**

The plan states there are "16 test patch targets (11 KB_ROOT, 5 _config)" in the Patch Targets section and references this count in the Open Question #1 Option C analysis. The actual count is:

| Patch Target | test_browse | test_staging | test_iteration_view | test_slide_editing | test_serve_integration | test_judge_versioning | test_action_mapping | TOTAL |
|---|---|---|---|---|---|---|---|---|
| `kb.serve.KB_ROOT` | 11 | 20 | 21 | 17 | 13 | 1 | 0 | **83** |
| `kb.serve._config` | 0 | 0 | 0 | 0 | 0 | 0 | 5 | **5** |
| `kb.serve.ACTION_STATE_PATH` | 0 | 20 | 21 | 17 | 12 | 4 | 0 | **74** |

This means Option C ("move to serve_state.py, update patches") would require updating **162 patch sites**, not 16. This makes Option C essentially impractical and validates the parameterization approach (Option A). The plan should correct this count to avoid misleading the executor.

### MINOR

**5. serve_state.py stdlib-only claim is aspirational, not achievable as written**

AC for Sub-phase 5.1 states: "`kb/serve_state.py` imports ONLY from stdlib (json, shutil, logging, pathlib)." This is only true if `ACTION_STATE_PATH` and `PROMPT_FEEDBACK_PATH` are passed as parameters. If they are defined IN `serve_state.py` (as the current plan proposes), then the module is indeed stdlib-only. But if the fix for Critical Issue #1 is applied (parameterization with lazy import from `kb.serve`), then `serve_state.py` will have a runtime dependency on `kb.serve` inside function bodies. The AC should be updated to reflect this: "imports only from stdlib at module level; lazy-imports from `kb.serve` at function call time for defaults."

**6. Scanner dependency on `load_action_state` not clearly handled**

The plan states Sub-phase 5.2 "depends on Sub-phase 5.1" because scanner uses `load_action_state` from serve_state. But scanning through the actual code, `scan_actionable_items()` does NOT call `load_action_state()`. It reads JSON files directly from `KB_ROOT`. Only the route handler `get_queue()` (line 542-582) calls both `scan_actionable_items()` and `load_action_state()`. The plan's dependency graph claim at line 1299 ("scanner uses load_action_state from serve_state") appears incorrect.

Looking at the scanner functions:
- `scan_actionable_items()` -- depends on `KB_ROOT`, `get_action_mapping()`, `get_destination_for_action()`, `ACTION_ID_SEP`, `VERSIONED_KEY_PATTERN`
- `get_action_mapping()` -- depends on `_config`
- `get_action_status()` -- takes `state` as parameter (no module-level dependency)
- `format_relative_time()` -- pure function
- `validate_action_id()` -- depends on `ACTION_ID_PATTERN`

None of these call `load_action_state()`. The dependency ordering (state before scanner) is still sensible because it reduces per-phase risk, but the stated reason is wrong.

**7. `_build_versioned_key_pattern()` location unclear**

The plan lists `_build_versioned_key_pattern()` as moving to `serve_scanner.py` (Task 5.2.1), but this function depends on `AUTO_JUDGE_TYPES` which is imported from `kb.analyze` at module level in `serve.py` (line 33). The plan does not mention this dependency. If `_build_versioned_key_pattern()` moves to `serve_scanner.py`, it needs `AUTO_JUDGE_TYPES` imported there too, which means `serve_scanner.py` would import from `kb.analyze` -- not just stdlib. This needs to be documented in the imports list.

**8. Plan section numbering conflict with Proposed Phases**

Lines 1451-1476 contain "Proposed Phases" from the original task document that describe Phase 5 differently (Flask package conversion). These stale descriptions directly contradict the detailed Phase 5 plan above them. While this is a documentation-only issue, it could confuse the executor. The stale section should be updated or annotated.

---

## Plan Strengths

- All function line numbers are 100% accurate (verified against live code)
- Function groupings are logical and follow dependency ordering
- Decision NOT to convert to Flask package is well-reasoned and correct
- Re-export strategy for backward compatibility is proven (worked in Phase 4)
- The plan's analysis of circular import avoidance via lazy imports is correct
- Sub-phase ordering (state -> scanner -> visual) follows dependency chain
- Rollback strategy is trivial (delete 3 files, revert imports)
- The plan correctly identifies that `KB_ROOT` and `_config` need special handling for the scanner; it just fails to apply the same analysis to `ACTION_STATE_PATH` for state functions

---

## Recommendations

### Before Proceeding (Required)

- [ ] **Fix Critical Issue #1:** Keep `ACTION_STATE_PATH` and `PROMPT_FEEDBACK_PATH` defined in `kb/serve.py`. Have `serve_state.py` functions accept them as parameters (with lazy-import defaults from `kb.serve`). This is the same strategy the plan already proposes for `KB_ROOT`/`_config` in the scanner -- apply it consistently.
- [ ] **Fix Critical Issue #2:** Document that the 1 test patching `kb.serve._update_visual_status` needs updating to target `kb.serve_visual._update_visual_status`, OR restructure `serve_visual.py` so `run_visual_pipeline` lazy-imports `_update_visual_status` from `kb.serve`.
- [ ] **Correct patch count:** Update the "16 KB_ROOT/config patches" claim to reflect the actual 162 total patches across all test files. This changes the risk assessment for Option C.
- [ ] **Resolve Open Questions:** Both can be auto-decided: Q1 = Option A (parameterize), Q2 = Option A (serve_ prefix). Mark as RESOLVED in the plan.
- [ ] **Fix scanner dependency claim:** `scan_actionable_items()` does not call `load_action_state()`. Correct the stated dependency reason for Sub-phase 5.2.
- [ ] **Add `AUTO_JUDGE_TYPES` to scanner imports:** `_build_versioned_key_pattern()` needs `AUTO_JUDGE_TYPES` from `kb.analyze`.

### Consider Later

- Update the stale "Proposed Phases" section (lines 1451-1476) to avoid confusion with the detailed Phase 5 plan.
- Consider whether `serve_state.py` functions should accept path parameters OR do lazy imports. Both work, but parameterization is more explicit and testable.
