# Task: Content Curation Workflow

## Task ID
T023

## Meta
- **Status:** CODE_REVIEW
- **Last Updated:** 2026-02-08

## Overview

T022 built the content engine pipeline: linkedin_v2 analysis → judge loop → visual classifier → carousel rendering → kb serve integration. But the workflow is still one-shot: approve → auto-generate visuals → done. Blake wants a richer curation workflow where posts go through iterative judging, human review of scores, manual editing in a staging area, and only then visual generation. This task builds that workflow.

The core insight: the current pipeline treats content generation as automated, but Blake wants to stay in the loop — seeing judge scores, deciding whether to iterate, editing text, and only publishing when satisfied. The engine should make iteration effortless, not eliminate human judgment.

## Objectives
- Retire `linkedin_post` analysis type — `linkedin_v2` becomes the default for all new transcriptions
- Auto-judge every `linkedin_v2` output (generate + score in one pass)
- Build iteration workflow in kb serve: view scores → iterate ('i') → see deltas → pick winner ('a' to stage)
- Build staging area: edit post text → edit slide content → generate visuals → publish
- Version everything: judge iterations (linkedin_v2_0, _1, _2), human edits (linkedin_v2_2_0, _2_1), diffs tracked
- Display iterations as a single entity with history, not separate items

## Dependencies
- `T022` — Content Engine (Phases 1-4 COMPLETE, provides linkedin_v2, judge loop, visual pipeline, carousel templates, kb serve integration)

## Rules Required
- None

## Resources & References
- `kb/analyze.py` line 960 — `run_with_judge_loop()` (current judge implementation)
- `kb/serve.py` line 216 — `run_visual_pipeline()` (current approve → visual flow)
- `kb/serve.py` line 348 — `scan_actionable_items()` (builds posting queue)
- `kb/__main__.py` line 52 — DEFAULTS with `action_mapping` and `default_analyses`
- `kb/config/analysis_types/linkedin_v2.json` — current prompt with `{{#if judge_feedback}}`
- `kb/config/analysis_types/linkedin_judge.json` — 7-criterion evaluation
- T022 main.md — Phase 5 spec (SUPERSEDED by this task, but contains useful design work)
- T022 plan-review-phase-5.md / plan-review-phase-5-r2.md — review findings to incorporate

## Open Questions

*All resolved — see Decision Matrix.*

## Decision Matrix

### Resolved (from Blake's feedback)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Auto-judge runs at CLI level only (not in visual pipeline or run_analysis_with_deps) | Approve flow stays fast. Judge runs during transcription and CLI analyze. |
| D2 | Approve = stage, not publish. Visuals only after staging edits. | Blake wants to curate before visual generation. Current auto-visual-on-approve gets rewired. |
| D3 | Iterations display as single entity with history, not separate items | Blake wants to see progression and deltas, not a cluttered list. |
| D4 | Edit versioning: linkedin_v2_N_M (N=judge round, M=edit number, 0-indexed) | Distinguishes LLM iterations from human edits. Enables diff tracking. |
| D5 | Visual generation from both serve UI and CLI (`kb publish`), but CLI is lower priority | Editing happens in serve, so serve trigger is primary. |
| D6 | Judge gets transcript access | Enables catching cliches, finding unused specifics, referencing transcript portions. |
| D7 | `linkedin_post` retired — linkedin_v2 becomes default analysis for new transcriptions | Single analysis type, always judged. |
| D8 | Judge gets full transcript (not truncated) | `{{transcript}}` already resolves in judge prompt via `resolve_optional_inputs()`. Gemini handles it fine. |
| D9 | 'g' for generate visuals shortcut in staging | No conflict with existing shortcuts (j/k/c/m/q/r/b/v/p/a/i). |
| D10 | New `/api/action/<id>/stage` endpoint, separate from approve | Clean separation. Approve handler rewired in Phase 2 (not Phase 3) to avoid auto-visual trigger. |
| D11 | Existing approved items reset to draft when T023 ships | Migration script clears approved status. Forces everything through new iteration workflow. |
| D12 | Edit sub-versioning: show latest edit only, with diff indicator | Collapsed by default. Full edit history accessible but not primary UI. |
| D13 | Versioned keys filtered in `scan_actionable_items()` | Skip keys matching `linkedin_v2_\d+`, `linkedin_judge_\d+`, `linkedin_v2_\d+_\d+` patterns. Only `linkedin_v2` (alias) matches action_mapping. |
| D14 | All API endpoints use alias-based action_id (`transcript_id--linkedin_v2`) | Versioned keys are internal storage only, never exposed as action_ids. |

---

## State Machine

```
transcribe
    → linkedin_v2_0 generated (auto, as default analysis)
    → linkedin_judge_0 generated (auto-judge)
    → appears in kb serve iteration view with scores

kb serve iteration view:
    [draft] → 'i' iterate → [iterating...] → linkedin_v2_1 + linkedin_judge_1 → [draft]
    [draft] → 'a' stage → [staged]

kb serve staging area:
    [staged] → edit text → save (linkedin_v2_N_0 → _N_1 → ...) → [staged]
    [staged] → generate visuals → [generating...] → [ready]
    [ready] → edit slides → save → re-render → [ready]
    [ready] → 'p' publish/copy → [published]
```

## Versioning Schema

```json
{
  "analysis": {
    "linkedin_v2": {
      "post": "...",
      "_round": 2,
      "_edit": 1,
      "_history": {
        "scores": [
          {"round": 0, "overall": 3.4, "criteria": {...}},
          {"round": 1, "overall": 4.1, "criteria": {...}}
        ]
      },
      "_model": "gemini-2.0-flash",
      "_analyzed_at": "2026-02-08T..."
    },
    "linkedin_v2_0": { "post": "...", "_model": "...", "_analyzed_at": "..." },
    "linkedin_judge_0": { "overall_score": 3.4, "scores": {...}, "improvements": [...] },
    "linkedin_v2_1": { "post": "...", "_model": "...", "_analyzed_at": "..." },
    "linkedin_judge_1": { "overall_score": 4.1, "scores": {...}, "improvements": [...] },
    "linkedin_v2_1_0": { "post": "...", "_edited_at": "...", "_source": "linkedin_v2_1" },
    "linkedin_v2_1_1": { "post": "...", "_edited_at": "...", "_diff_from": "linkedin_v2_1_0" }
  }
}
```

Note: `linkedin_v2` is always an alias pointing to the latest version (whether LLM-generated or human-edited). `_round` tracks judge iteration, `_edit` tracks human edits within that round.

---

## Phases Breakdown

### Phase 1: Judge Versioning + Auto-Judge Pipeline
**Status**: Not Started

**Objectives:**
- Refactor `run_with_judge_loop()` in `analyze.py` to save versioned outputs (linkedin_v2_0, linkedin_judge_0, etc.)
- `linkedin_v2` alias always points to latest version with `_round` and `_history` metadata inside it
- Auto-judge: new `run_analysis_with_auto_judge()` wrapper called from CLI entry point. When `kb analyze -t linkedin_v2` runs, it generates the draft AND runs the judge automatically. No separate `--judge` flag needed (kept for backward compat, no-op for linkedin_v2).
- Judge transcript access: verify `{{transcript}}` already resolves in `linkedin_judge.json` via `resolve_optional_inputs()` (likely a no-op — just confirm and test)
- Full history injection: each improvement round receives JSON array of all prior drafts + judge evaluations via `{{#if judge_feedback}}` template variable
- Retire `linkedin_post`: update default action_mapping and default_analyses references. Old results preserved but no longer generated.
- Backward compat: existing linkedin_v2 results without `_round` treated as round 0 on first iteration
- Filter versioned keys in `scan_actionable_items()`: add pattern filter to skip `linkedin_v2_\d+`, `linkedin_judge_\d+`, `linkedin_v2_\d+_\d+` — only the `linkedin_v2` alias matches action_mapping
- Migration: reset existing approved items to draft state (one-time migration on first run or via CLI command)

**History injection format (passed as `judge_feedback` template variable):**
```json
[
  {
    "round": 0,
    "draft": "full post text from round 0",
    "judge": {
      "overall_score": 3.4,
      "scores": {"hook_strength": 3, "structure": 4, ...},
      "improvements": ["...", "..."],
      "rewritten_hook": "..."
    }
  }
]
```

**Estimated Time**: 4-6 hours

**Resources Needed:**
- `kb/analyze.py` — refactor run_with_judge_loop(), add run_analysis_with_auto_judge()
- `kb/__main__.py` — update DEFAULTS (action_mapping, default_analyses references)
- `kb/config/analysis_types/linkedin_judge.json` — add transcript as optional_input
- `kb/config/analysis_types/linkedin_v2.json` — update judge_feedback block for history array

**Dependencies:** T022 (complete)

**Files:**
- `kb/analyze.py` — MODIFY: refactor run_with_judge_loop() for versioned saves, add run_analysis_with_auto_judge() wrapper
- `kb/serve.py` — MODIFY: add pattern filter in scan_actionable_items() to skip versioned keys
- `kb/__main__.py` — MODIFY: linkedin_v2 replaces linkedin_post in all DEFAULTS, auto-judge wiring for CLI
- `kb/config/analysis_types/linkedin_judge.json` — VERIFY: confirm {{transcript}} resolves via resolve_optional_inputs()
- `kb/config/analysis_types/linkedin_v2.json` — MODIFY: update judge_feedback instruction for JSON array history
- `kb/tests/test_judge_versioning.py` — NEW: tests for versioned saves, auto-judge, history injection, backward compat, versioned key filtering

**Acceptance Criteria:**
- [ ] `kb analyze -t linkedin_v2 -d X` generates linkedin_v2_0 + linkedin_judge_0 automatically
- [ ] linkedin_v2 alias points to latest with _round, _history metadata
- [ ] `--judge` flag still works but is no-op for linkedin_v2
- [ ] Judge receives transcript text alongside the post (via existing {{transcript}} resolution)
- [ ] History injection: round 2+ receives full JSON array of all prior rounds
- [ ] Existing linkedin_v2 results without _round handled gracefully
- [ ] linkedin_post retired from default action_mapping
- [ ] Versioned keys (linkedin_v2_0, linkedin_judge_0, etc.) do NOT appear as separate items in scan_actionable_items()
- [ ] All existing tests still pass

---

### Phase 2: kb serve Iteration View + Approve Rewire
**Status**: Not Started

**Objectives:**
- **Rewire approve handler:** Disconnect approve from auto-visual-pipeline. The 'a' shortcut now calls `POST /api/action/<id>/stage` (new endpoint) instead of the existing approve endpoint. This must happen in Phase 2 (not Phase 3) to avoid 'a' accidentally triggering visual generation.
- **Migration:** Reset existing approved items in action-state.json to draft state. One-time migration on first run or via `kb migrate` CLI command.
- Redesign posting queue to show linkedin_v2 iterations as a single entity with history
- Left panel (file explorer): shows items grouped by entity, not by individual iteration
- Drill into an entity (Enter): focus moves to content pane showing the post text and judge scores
- Score display: per-criterion scores (hook_strength, structure, specificity, etc.) + overall
- Delta display: between rounds show ↑/↓/= per criterion and overall delta
- Navigate between iterations: up/down arrows move through linkedin_v2_0, _1, _2 etc.
- 'i' keyboard shortcut: triggers next improvement round (background LLM call)
- 'a' keyboard shortcut: stages the currently-viewed iteration (calls `/stage`, NOT `/approve`)
- "Iterating..." spinner while background improvement runs
- Judge scores shown as metadata alongside post preview (not raw JSON dump)
- Posts without judge scores (pre-T023) show "Not judged" fallback
- All API endpoints use alias-based action_id (`transcript_id--linkedin_v2`), not versioned keys

**Estimated Time**: 6-8 hours

**Resources Needed:**
- `kb/serve.py` — posting queue API modifications, approve handler rewire
- `kb/templates/posting_queue.html` — major UI redesign
- `kb/analyze.py` — expose improvement trigger as callable function for serve

**Dependencies:** Phase 1

**Files:**
- `kb/serve.py` — MODIFY: new API endpoints:
  - `POST /api/action/<action_id>/stage` — NEW: stages an iteration (replaces approve for workflow items). Does NOT trigger visual pipeline.
  - `POST /api/action/<action_id>/iterate` — NEW: triggers next improvement round in background thread
  - `GET /api/action/<action_id>/iterations` — NEW: returns all iterations with scores for an entity
  - Modify existing approve endpoint: remove `run_visual_pipeline()` call for linkedin_v2 items (or gate behind a check)
  - Modify posting queue API to return iterations grouped by entity
- `kb/templates/posting_queue.html` — MODIFY: iteration view UI (entity grouping, score display, delta badges, keyboard shortcuts 'i' and 'a', spinner). 'a' calls /stage not /approve.
- `kb/tests/test_iteration_view.py` — NEW: tests for iteration API, grouping, stage endpoint, migration

**Acceptance Criteria:**
- [ ] Posting queue shows linkedin_v2 as single entity (not one item per iteration)
- [ ] Enter drills into entity, showing post text + judge scores
- [ ] Scores displayed per-criterion with overall score
- [ ] Deltas shown between rounds (↑3→4, =4→4, ↓4→3)
- [ ] Up/down arrows navigate between iterations within an entity
- [ ] 'i' triggers improvement round, shows "Iterating..." spinner
- [ ] 'a' calls /stage (NOT /approve), does NOT trigger visual pipeline
- [ ] Existing approved items migrated to draft state
- [ ] Posts without scores show "Not judged" fallback
- [ ] Background iteration completes and updates UI without page refresh

---

### Phase 3: Staging Area + Text Editing
**Status**: Not Started

**Objectives:**
- Build staging area in kb serve: approved/staged posts land here for curation
- Post text displayed in an editable textarea
- Each save creates a new edit version (linkedin_v2_N_M where N=round, M=edit number, 0-indexed)
- Edit 0 = the raw LLM output (or approved iteration), saved automatically when staged
- Subsequent saves increment M
- Diff tracking: store what changed between edits (for future prompt improvement)
- Visual generation trigger: 'g' keyboard shortcut to kick off visual pipeline from staging
- Visual pipeline runs in background (same pattern as current approve flow, but triggered explicitly from staging via 'g')
- After visuals generated: status changes to "ready"
- Only "ready" posts can be published/copied

**State transitions in staging:**
```
staged → editing (textarea focused)
editing → staged (save: creates linkedin_v2_N_M+1)
staged → generating (trigger visuals)
generating → ready (visuals complete)
ready → published (copy/export)
```

**Estimated Time**: 5-7 hours

**Resources Needed:**
- `kb/serve.py` — staging endpoints
- `kb/templates/posting_queue.html` — staging area UI
- `kb/serve.py` line 216 — rewire visual pipeline trigger (currently on approve, now on explicit action)

**Dependencies:** Phase 2

**Files:**
- `kb/serve.py` — MODIFY: new API endpoints:
  - `POST /api/action/<action_id>/stage` — move iteration to staging, create edit version _N_0
  - `POST /api/action/<action_id>/save-edit` — save text edit, create _N_M+1
  - `POST /api/action/<action_id>/generate-visuals` — trigger visual pipeline from staging ('g' shortcut)
  - `GET /api/action/<action_id>/edit-history` — return edit versions for staged item
- `kb/templates/posting_queue.html` — MODIFY: staging area with textarea editor, save button, generate visuals button/shortcut, visual status indicators
- `kb/tests/test_staging.py` — NEW: tests for staging flow, edit versioning, visual trigger

**Acceptance Criteria:**
- [ ] 'a' in iteration view stages the post (creates linkedin_v2_N_0 edit version)
- [ ] Staging area shows post text in editable textarea
- [ ] Saving creates new edit version (linkedin_v2_N_1, _N_2, etc.)
- [ ] Edit versions preserved in transcript JSON
- [ ] Visual generation only triggers from staging (not on approve)
- [ ] "Generating..." spinner while visuals render
- [ ] "Ready" status with visual preview when complete
- [ ] Published/copy action available only when ready

---

### Phase 4: Slide Editing + Template Selection
**Status**: Not Started

**Objectives:**
- After visual generation, allow editing individual carousel slides in kb serve
- Slides are structured JSON: each slide has `type` (hook/content/mermaid/cta) and `content` fields
- Content types within slides: bullets, numbered lists, free-form text, mermaid (standalone type)
- Editor: simple textarea per slide — edit title and content text, not the type
- Template selection: choose from available templates before rendering (dark-purple, light, or future templates from T024)
- Re-render after slide edits: trigger re-render with same or different template
- `kb publish` CLI support: `kb publish --decimal X` renders staged+edited content

**Estimated Time**: 4-6 hours

**Resources Needed:**
- `kb/serve.py` — slide editing endpoints
- `kb/templates/posting_queue.html` — slide editor UI
- `kb/render.py` — re-render support
- `kb/publish.py` — CLI integration

**Dependencies:** Phase 3, T024 (template redesign — can proceed in parallel, slide editing is format-agnostic)

**Files:**
- `kb/serve.py` — MODIFY: new API endpoints:
  - `GET /api/action/<action_id>/slides` — return carousel slide data
  - `POST /api/action/<action_id>/save-slides` — save edited slide data
  - `POST /api/action/<action_id>/render` — re-render with specified template
  - `GET /api/templates` — list available carousel templates
- `kb/templates/posting_queue.html` — MODIFY: slide editor (per-slide textarea for title/content), template selector dropdown, re-render button
- `kb/publish.py` — MODIFY: support rendering from staged+edited content
- `kb/tests/test_slide_editing.py` — NEW: tests for slide edit, re-render, template selection

**Acceptance Criteria:**
- [ ] After visual generation, slides are viewable and editable in kb serve
- [ ] Each slide shows title and content in textarea fields
- [ ] Slide type is read-only (can't change hook to mermaid)
- [ ] Save edits updates the carousel_slides analysis data
- [ ] Template selector shows available templates
- [ ] Re-render produces new PDF/PNGs with edited content and chosen template
- [ ] `kb publish --decimal X` works with staged content
- [ ] Slide edits persist across page refreshes

---

## Plan Review

### Round 1
- **Gate:** NEEDS_WORK
- **Reviewed:** 2026-02-08
- **Summary:** Strong design with clean state machine and good phasing. However, versioned analysis keys will pollute scan_actionable_items(), and the approve-handler rewire is scheduled in Phase 3 but needed by Phase 2.
- **Issues:** 2 critical, 2 major, 5 minor
- **Required Fixes:**
  1. C1: Versioned keys in scan_actionable_items() — add pattern filter
  2. C2: Approve handler rewire must be in Phase 2, not Phase 3
  3. M1: API endpoints must use alias-based action_id
  4. M2: Judge transcript access may already work (verify)

-> Details: `plan-review.md`

### Round 1 Fixes Applied
- **C1:** Added pattern filter in scan_actionable_items() to Phase 1. Skip keys matching `linkedin_v2_\d+`, `linkedin_judge_\d+`, `linkedin_v2_\d+_\d+`.
- **C2:** Moved approve handler rewire to Phase 2. 'a' now calls `/stage` not `/approve`. Phase 3 no longer has approve rewire.
- **M1:** Added D14: all API endpoints use alias-based action_id. Versioned keys are internal storage only.
- **M2:** Added D8: `{{transcript}}` already resolves via resolve_optional_inputs(). Phase 1 verifies, not modifies.
- **Open questions resolved:** Q1→D8 (full transcript), Q2→D12 (latest edit only with diff indicator), Q3→D9 ('g'), N1→D10 (new /stage endpoint), N2→D11 (reset to draft).

### Round 2
- **Gate:** READY
- **Reviewed:** 2026-02-08
- **Summary:** All Round 1 issues adequately addressed. Versioned key filter uses concrete regex patterns, approve rewire correctly placed in Phase 2, alias-based action_ids formalized, transcript resolution scoped as verification. No critical or major issues remain.
- **Issues:** 0 critical, 0 major, 7 minor (1 new, 6 carried forward)
- **Open Questions Finalized:** None -- all resolved with decisions D1-D14.

-> Details: `plan-review-r2.md`

---

## Execution Log

### Phase 1: Judge Versioning + Auto-Judge Pipeline
- **Status:** COMPLETE
- **Started:** 2026-02-08
- **Completed:** 2026-02-08
- **Commits:** `d292bde`
- **Files Modified:**
  - `kb/analyze.py` -- Refactored `run_with_judge_loop()` for versioned saves; added `_get_starting_round()`, `_build_history_from_existing()`, `_build_score_history()`, `_update_alias()` helpers; added `AUTO_JUDGE_TYPES` mapping and `run_analysis_with_auto_judge()` wrapper; updated CLI `main()` to route linkedin_v2 through auto-judge pipeline
  - `kb/serve.py` -- Added `VERSIONED_KEY_PATTERN` regex; added filter in `scan_actionable_items()` to skip versioned keys; added `migrate_approved_to_draft()` function
  - `kb/config/analysis_types/linkedin_v2.json` -- Updated `judge_feedback` template section to reference JSON array history format
  - `kb/tests/test_judge_versioning.py` -- NEW: 34 tests covering versioned saves, alias updates, history injection, backward compat, key filtering, migration, template verification, transcript access
- **Notes:**
  - D8 verified: `{{transcript}}` in linkedin_judge.json already resolves via `resolve_optional_inputs()` which always includes transcript. No modification needed.
  - D7/Task 6: `linkedin_post` was already removed from DEFAULTS action_mapping in T022. No change needed.
  - Backward compat migration: when existing unversioned linkedin_v2 detected, it is saved as `_0` and the loop continues from round 1. The new draft at round 1 receives the old draft as history.
  - VERSIONED_KEY_PATTERN is broad (`^.+_\d+$|^.+_\d+_\d+$`) to catch versioned keys for any analysis type. Verified no existing analysis type names end with `_\d+`.

### Tasks Completed
- [x] Task 1.1: Refactored run_with_judge_loop() for versioned saves (linkedin_v2_0, linkedin_judge_0, etc.)
- [x] Task 1.2: linkedin_v2 alias always points to latest with _round and _history metadata
- [x] Task 1.3: Added run_analysis_with_auto_judge() wrapper; CLI auto-judges linkedin_v2
- [x] Task 1.4: Verified judge has transcript access via {{transcript}} (no-op, already works)
- [x] Task 1.5: History injection: improvement rounds receive full JSON array of all prior rounds
- [x] Task 1.6: linkedin_post already retired from action_mapping (done in T022)
- [x] Task 1.7: Backward compat: existing linkedin_v2 without _round handled gracefully
- [x] Task 1.8: Pattern filter in scan_actionable_items() skips versioned keys
- [x] Task 1.9: Migration mechanism: migrate_approved_to_draft() added

### Acceptance Criteria
- [x] AC1: `kb analyze -t linkedin_v2 -d X` generates linkedin_v2_0 + linkedin_judge_0 automatically -- verified via run_analysis_with_auto_judge() routing to run_with_judge_loop()
- [x] AC2: linkedin_v2 alias points to latest with _round, _history metadata -- verified via _update_alias() and test_sets_round_and_history
- [x] AC3: --judge flag still works but is no-op for linkedin_v2 -- verified via CLI logic: has_auto_judge types bypass --judge check
- [x] AC4: Judge receives transcript text -- verified: linkedin_judge.json uses {{transcript}}, resolve_optional_inputs always includes it
- [x] AC5: History injection: round 2+ receives full JSON array -- verified via test_history_injection_format
- [x] AC6: Existing linkedin_v2 results without _round handled -- verified via test_backward_compat_existing_unversioned
- [x] AC7: linkedin_post retired from default action_mapping -- already done in T022
- [x] AC8: Versioned keys not in scan_actionable_items() -- verified via test_scan_skips_versioned_keys
- [x] AC9: All tests pass -- 222 tests (188 original + 34 new)

---

## Notes & Updates
- 2026-02-08: Task created from Blake's feedback on T022 Phase 5. Supersedes T022 Phase 5 (iterative judge). Incorporates workflow redesign: iterate → stage → edit → generate visuals → publish.
- 2026-02-08: Key design decisions: auto-judge CLI only, approve=stage not publish, edit versioning as linkedin_v2_N_M, judge gets transcript access.
