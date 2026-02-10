# Plan Review: Phase 8 -- KB Serve Iteration View + Processing UX

## Gate Decision: NEEDS_WORK

**Summary:** Plan is well-structured with accurate source code references (all line numbers verified against actual files). Three issues need fixing before execution: an acceptance criterion contradicts Blake's "no buttons" UX rule, Task 8A.4 description contradicts the resolved decision (text-only, not chart), and "retire linkedin_post" is underspecified. No tests are planned despite all previous phases including test requirements.

---

## Open Questions Validation

All 3 open questions were resolved by Blake. Validated below.

### Resolved Questions -- Verification

| # | Question | Resolution | Verified? |
|---|----------|------------|-----------|
| 1 | Score progression chart style | Text-only (keep simple) | Valid resolution. Score per round is already shown in round tabs (R0 (3.2), R1 (4.1)). Adding redundant visualization would be noise. |
| 2 | Where should "Analyze" trigger live? | Browse detail only, keyboard-triggered (`a` key) | Valid. `a` is not currently bound in browse.html (verified). No conflict. |
| 3 | Which analysis types to expose? | Non-internal only: linkedin_v2, skool_post, skool_weekly_catchup. Hide: visual_format, carousel_slides, linkedin_judge, linkedin_post. | Valid. These 3 + 4 hidden = all 7 types in `config/analysis_types/`. `summary` is not a formal analysis type (no JSON config file), so correctly excluded. |

### New Questions Discovered

| # | Question | Options | Impact |
|---|----------|---------|--------|
| 1 | What does "retire linkedin_post v1" mean concretely? | A) Delete `linkedin_post.json` from analysis_types B) Keep file but filter from UI only C) Add a `retired: true` flag to the JSON | Affects scope of 8C. Deleting the file changes `list_analysis_types()` output globally, which may break existing CLI commands or tests that reference it. Filtering UI-only is safer. |

---

## Issues Found

### Critical (Must Fix Before Execution)

1. **AC-8C.3 says "Analyze button" -- contradicts Blake's UX rule**
   - AC-8C.3 reads: "Browse transcript detail shows 'Analyze' **button** with type selector"
   - Blake explicitly stated: "NO BUTTONS -- everything keyboard"
   - Task 8C.4 correctly says keyboard-triggered, but the AC contradicts this
   - **Fix:** Reword AC-8C.3 to: "Pressing `a` in browse transcript detail opens a keyboard-navigable analysis type picker"

### Major (Should Fix Before Execution)

1. **Task 8A.4 description contradicts resolved decision**
   - The resolution for Q1 says "Text-only -- keep simple"
   - But Task 8A.4 still says "Render a simple ASCII/CSS bar chart or inline sparkline"
   - The task description needs to match the resolution
   - **Fix:** Rewrite Task 8A.4 to render a text-only score progression (e.g., "R0: 2.8 -> R1: 3.4 -> R2: 4.1") rather than any chart/sparkline

2. **No tests specified for any sub-phase**
   - Phases 6 and 7 both included explicit test tasks and test acceptance criteria
   - Phase 8 has zero test tasks across all three sub-phases
   - 8A (API bug fix) is highly testable -- the missing `strengths` field can be verified with a unit test
   - 8C (new endpoints) absolutely needs tests for the analyze endpoint (valid types, invalid types, concurrent request rejection)
   - **Fix:** Add at minimum: (a) test for `strengths` in iteration API response, (b) tests for `/api/transcript/<id>/analyze` endpoint validation (400 for invalid type, 404 for missing transcript, 409 for concurrent)

3. **"Retire linkedin_post v1" is ambiguous**
   - The plan says to retire `linkedin_post` but does not specify the concrete action
   - `linkedin_post.json` exists at `kb/config/analysis_types/linkedin_post.json`
   - Deleting it changes `list_analysis_types()` output globally and may break existing tests (there are references in `test_action_mapping.py` and `test_serve_integration.py`)
   - The safer approach is to filter it in the UI alongside the other internal types, but the plan does not specify this
   - **Fix:** Clarify in Task 8C.4 whether `linkedin_post` should be (a) deleted from disk, (b) added to a `RETIRED_TYPES` constant and filtered in the `/api/analysis-types` response, or (c) both

### Minor

1. **Task 8C.1 and 8C.5 overlap on processing state tracking**
   - Task 8C.1 says "Track processing state in action-state.json (new `analyzing` flag per transcript)"
   - Task 8C.5 separately describes processing state tracking with a different structure: `state["processing"][transcript_id] = {"types": [...], "started_at": "..."}`
   - These are two different proposed implementations for the same concept
   - **Recommendation:** Consolidate into Task 8C.5 only. Task 8C.1 should reference 8C.5 for state tracking rather than defining its own schema.

2. **Task 8C.1 lacks detail on `run_with_judge_loop` invocation**
   - The task says "For types in `AUTO_JUDGE_TYPES`: call `run_with_judge_loop()`" but does not specify how to get the `judge_type` parameter
   - The mapping is in `AUTO_JUDGE_TYPES` dict: `{"linkedin_v2": "linkedin_judge"}`
   - Also does not mention loading `transcript_data` from the found file (need to `json.load` the file path)
   - **Recommendation:** Add explicit note: "Look up `judge_type` from `AUTO_JUDGE_TYPES[analysis_type]`. Load transcript data with `json.load(open(file_path))`."

3. **Task 8C.3 helper extraction may be premature refactoring**
   - The plan proposes extracting `find_transcript_by_id()` as a shared helper, refactoring existing callsites
   - `_find_transcript_file()` in `serve_visual.py` takes an `action_id` (format: `transcript_id--analysis_type`), not a raw `transcript_id`
   - `get_transcript()` in `serve.py` searches by `transcript_id` directly
   - These have slightly different signatures and concerns (one parses action IDs, one takes transcript IDs)
   - **Recommendation:** The new endpoint can reuse the `get_transcript()` search pattern inline. A shared helper is nice-to-have, not blocking. Mark as optional.

4. **8B filter dropdown uses `source_decimal` but no confirmation items have this field**
   - Verified: `source_decimal` is populated in `scan_actionable_items()` at serve_scanner.py line 198
   - This is fine, but the plan should note that the dropdown values come from `item.source_decimal`, not `item.decimal`

5. **AC-8A.3 condition "hook_strength < 4" is not enforceable in frontend**
   - The acceptance criterion says "Rewritten hook appears when the judge provided one (hook_strength < 4)"
   - The frontend should simply check `if (current.scores.rewritten_hook)` -- it should not reimplement the judge's scoring logic
   - The `< 4` threshold is the judge's decision; the frontend just renders what exists
   - **Recommendation:** Reword to "Rewritten hook appears when present in judge data (non-null)"

---

## Verified Source Code References

All line numbers and function names in the plan were checked against the actual source files:

| Reference | Plan Says | Actual | Status |
|-----------|-----------|--------|--------|
| serve.py strengths omission | Lines 1170-1175 | Lines 1170-1175 (scores dict built without `strengths`) | CORRECT |
| serve.py duplicate block | Lines 1191-1197 | Lines 1191-1197 (pre-T023 backward compat path) | CORRECT |
| posting_queue.html `</style>` | Line 926 | Line 926 | CORRECT |
| posting_queue.html `renderIterationView()` | Lines 1200-1336 | Lines 1200-1336 | CORRECT |
| posting_queue.html `${scoresHtml}` insertion point | Line 1305 | Line 1305 | CORRECT |
| posting_queue.html JS state section | Line 998 | Lines 998-1007 | CORRECT |
| posting_queue.html entity list section header | Line 1093 | Lines 1091-1100 | CORRECT |
| serve.py `"processing": [] # Phase 2` | Line 155 | Line 155 | CORRECT |
| serve.py after `/api/transcript/<id>` route | Around line 1527 | Line 1527 (404 return at end of `get_transcript()`) | CORRECT |
| serve_visual.py `_find_transcript_file()` | Lines 26-55 | Lines 26-55 | CORRECT |
| serve.py `get_transcript()` search loop | Lines 1463-1475 | Lines 1463-1475 | CORRECT |
| linkedin_judge.json `strengths` field | Lines 39-43 | Lines 39-43 | CORRECT |
| `a` key available in browse.html | Not bound | Not bound (verified full keydown handler) | CORRECT |

---

## Plan Strengths

- Execution order (8A -> 8B -> 8C) is well-reasoned: 8A is most contained, 8B helps test 8A, 8C is largest
- Source code references are remarkably accurate -- every line number checked out
- The scope exclusions are clear (no batch processing, no streaming, no new analysis type creation)
- The API bug fix (missing `strengths`) is a genuine bug -- verified the schema defines it and the API omits it
- Client-side filtering for 8B is the right call -- all items are already loaded
- Keyboard-first UX in 8C.4 aligns with the existing browse.html patterns (j/k/Enter/Escape all vim-style)

---

## Recommendations

### Before Proceeding (Must Fix)
- [ ] Reword AC-8C.3 to remove "button" -- use keyboard language consistent with Blake's UX directive
- [ ] Reconcile Task 8A.4 with Q1 resolution -- change from chart/sparkline to text-only
- [ ] Clarify what "retire linkedin_post" means concretely (delete file vs. filter in UI vs. both)
- [ ] Add test tasks for 8A (API strengths field) and 8C (endpoint validation)

### Consider Later
- Consolidate 8C.1 and 8C.5 state tracking into a single task with one schema
- Add explicit `run_with_judge_loop` parameter notes to 8C.1
- Mark 8C.3 (helper extraction) as optional/nice-to-have

---

# Round 2 Review (2026-02-10)

## Gate Decision: READY

**Summary:** All 4 R1 issues (1 critical, 3 major) have been resolved. The plan is now internally consistent, has test coverage planned, and the linkedin_post retirement strategy is clearly specified. No new critical or major issues found. 3 minor carry-forward notes from R1 remain as non-blocking implementation details.

---

## R1 Issue Resolution Verification

### 1. CRITICAL: AC-8C.3 "Analyze button" contradicts "no buttons" UX rule
- **Status:** RESOLVED
- **Verification:** AC-8C.3 now reads: "Browse transcript detail: pressing `a` opens keyboard-navigable analysis type picker"
- No remaining mention of "button" in any acceptance criteria for 8C

### 2. MAJOR: Task 8A.4 description contradicts resolved decision (text-only, not chart)
- **Status:** RESOLVED
- **Verification:** Task 8A.4 is now titled "Add text-only score progression" and describes rendering as plain text (e.g., "Round 1: 3.2 -> Round 2: 3.8 -> Round 3: 4.1") with color-coded `<span>` elements. No reference to chart, sparkline, or canvas.

### 3. MAJOR: No tests specified for any sub-phase
- **Status:** RESOLVED
- **Verification:** Task 8A.5 added with 3 specific test cases (strengths in API response, no-judge-data safety, score_history structure). 8C has 3 explicit test items (POST validation, GET analysis-types filtering, concurrent rejection 409).

### 4. MAJOR: "Retire linkedin_post v1" underspecified
- **Status:** RESOLVED
- **Verification:** Decision Matrix Q3 resolution now explicitly states: "linkedin_post (v1) config stays but is filtered out of staging/review and analysis picker. Existing v1 items remain in queue for triage. Config default update (decimals -> linkedin_v2) is a separate manual step." AC-8C.8 added: "linkedin_post (v1) items filtered out of staging/review views and analysis type picker." This is the UI-only filter approach (option B from R1), which is the safest -- `linkedin_post.json` stays on disk, `list_analysis_types()` is unaffected globally, CLI and existing tests continue to work.

---

## New Issues Check (R2)

### Critical (Must Fix)
None.

### Major (Should Fix)
None.

### Minor (Carry-forward from R1, non-blocking)

1. **Task 8C.1 and 8C.5 still overlap on processing state tracking** (R1 Minor #1)
   - 8C.1 mentions "Track processing state in action-state.json (new `analyzing` flag per transcript)"
   - 8C.5 describes a different schema: `state["processing"][transcript_id] = {"types": [...], "started_at": "..."}`
   - Not blocking: executor can consolidate during implementation. The 8C.5 schema is more complete; 8C.1's mention is just a note that state tracking is needed.

2. **Task 8C.1 lacks detail on `run_with_judge_loop` parameters** (R1 Minor #2)
   - `run_with_judge_loop()` takes `transcript_data: dict` (loaded JSON, not a file path) and `save_path: str` (for persisting results)
   - `analyze_transcript_file()` takes `transcript_path: str` (file path, loads internally)
   - Not blocking: the function signatures are clear from the source, and existing call sites in `serve.py` (lines 409, 480, 1063, 1132) demonstrate the correct invocation pattern.

3. **Task 8C.3 helper extraction is optional refactoring** (R1 Minor #3)
   - `_find_transcript_file()` in serve_visual.py takes an action_id (parses `--` separator), `get_transcript()` in serve.py takes raw transcript_id
   - These have different contracts. The new endpoint can inline the search pattern.
   - Not blocking: executor can decide to extract or inline based on what feels cleaner during implementation.

---

## R2 Open Questions

No new questions requiring human input. The R1 question about linkedin_post retirement was resolved by the planner with a clear, safe strategy (UI-only filter, config stays).

---

## Final Assessment

The plan is ready for execution. The three sub-phases are well-scoped and sequenced:
- **8A** is contained (API bug fix + frontend rendering, ~4 tasks + 1 test task)
- **8B** is small and isolated (client-side filter, 3 tasks, no backend changes)
- **8C** is the largest but well-decomposed (5 tasks + explicit tests, new endpoints + UI)

All acceptance criteria are verifiable. Source code references remain accurate (verified in R1, no file changes since). The UX principles are consistently applied -- keyboard-only throughout.
