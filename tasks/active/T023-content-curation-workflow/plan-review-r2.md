# Plan Review Round 2: T023 Content Curation Workflow

## Gate Decision: READY

**Summary:** All four Round 1 issues (C1, C2, M1, M2) have been adequately addressed. The versioned key filter is specified with concrete regex patterns, the approve-handler rewire is correctly moved to Phase 2, alias-based action_ids are formalized as D14, and the transcript resolution is correctly scoped as a verification task. One minor conflict introduced by the fixes (duplicate /stage endpoint between Phase 2 and Phase 3) and a few pre-existing minor issues remain, but none block execution.

---

## Round 1 Fix Verification

### C1: Versioned key filtering in scan_actionable_items() -- ADEQUATE

The fix adds a pattern filter to Phase 1 that skips keys matching `linkedin_v2_\d+`, `linkedin_judge_\d+`, `linkedin_v2_\d+_\d+`. This is formalized as D13.

**Verification against codebase:** `scan_actionable_items()` at serve.py line 375 iterates `analysis.keys()` and calls `get_destination_for_action()` for each. The `get_destination_for_action()` function (serve.py line 87) does exact string matching against the action_mapping dict. Since the action_mapping only contains `"linkedin_v2": "LinkedIn"` (not versioned variants), versioned keys would already fail to match today. However, the explicit filter is still the right call because:
1. It prevents future action_mapping additions from accidentally picking up versioned keys.
2. It avoids unnecessary `get_destination_for_action()` lookups for keys that are structurally never actionable.
3. It documents the intent clearly.

The regex patterns cover all versioned key formats from the versioning schema. No gaps found.

### C2: Approve handler rewire moved to Phase 2 -- ADEQUATE

Phase 2 now explicitly:
- Creates `POST /api/action/<action_id>/stage` as a new endpoint (line 211).
- Wires the 'a' keyboard shortcut to call `/stage` NOT `/approve` (lines 185, 194, 216).
- States it must modify the existing approve endpoint to remove `run_visual_pipeline()` for linkedin_v2 items (line 214).

This correctly eliminates the Phase 2/Phase 3 dependency gap. The approve endpoint modification is specified as "remove `run_visual_pipeline()` call for linkedin_v2 items (or gate behind a check)" -- the "or gate behind a check" option is preferable since other analysis types (skool_post) may still want auto-visual on approve.

**One issue introduced (see m1 below):** The /stage endpoint now appears in both Phase 2 and Phase 3 file listings with different descriptions.

### M1: Alias-based action_id -- ADEQUATE

D14 states: "All API endpoints use alias-based action_id (`transcript_id--linkedin_v2`). Versioned keys are internal storage only, never exposed as action_ids." This is also reflected in Phase 2 (line 198). Combined with the `ACTION_ID_PATTERN` regex at serve.py line 40, this is clean. The server will resolve alias to current version internally.

### M2: Judge transcript access -- ADEQUATE

D8 states `{{transcript}}` already resolves via `resolve_optional_inputs()`. Phase 1 scope is "verify, not modify."

**Verification against codebase:** `resolve_optional_inputs()` at analyze.py line 874 unconditionally sets `context["transcript"] = transcript_text`. This means ANY analysis type whose prompt uses `{{transcript}}` gets the transcript resolved -- regardless of whether `transcript` is listed in `optional_inputs`. The linkedin_judge.json prompt does use `{{transcript}}` on line 6. So D8 is correct: the judge already receives transcript text today. Phase 1 task to "verify and test" is the right scope.

---

## New Issues Introduced by Fixes

### Minor

**m1: /stage endpoint defined in both Phase 2 (line 211) and Phase 3 (line 268) with different descriptions.**

Phase 2 line 211: `POST /api/action/<action_id>/stage -- NEW: stages an iteration (replaces approve for workflow items). Does NOT trigger visual pipeline.`

Phase 3 line 268: `POST /api/action/<action_id>/stage -- move iteration to staging, create edit version _N_0`

These describe the same endpoint but with different behavior. Phase 2 creates it as a simple status change (draft -> staged). Phase 3 adds the edit versioning behavior (creating linkedin_v2_N_0 on stage). The executor will need to understand that Phase 3 EXTENDS the Phase 2 endpoint, not creates a new one.

**Impact:** Low. The executor should be able to infer this from context. The Phase 3 description is an enhancement of the Phase 2 endpoint, not a conflict. But it would be cleaner if Phase 3 said "MODIFY" instead of listing it as if new.

**m2: The "Round 1 Fixes Applied" section (line 348) says "Phase 3 no longer has approve rewire" but Phase 3 still contains "Visual generation only triggers from staging (not on approve)" as an AC (line 280).** This AC is now redundant with Phase 2's work but not harmful -- it serves as a regression check. No action needed.

---

## Pre-existing Issues (Carried Forward from Round 1)

These were noted as minor in Round 1 and remain unchanged. None block execution.

**m3 (was m1): Metadata duplication in alias.** The `linkedin_v2` alias stores `_round` and `_history` metadata that duplicates information derivable from versioned keys. Acceptable bookkeeping overhead for fast lookups.

**m4 (was m4): No un-stage transition in state machine.** The state machine shows no path from `[staged]` back to `[draft]` for additional LLM iterations. This is a deliberate design choice (staging is forward-only) or an oversight. The executor should add a TODO comment if not implementing it.

**m5 (was m5): Thread safety for concurrent file writes.** With iterate (background thread), stage, save-edit, and generate-visuals all potentially writing to the same JSON files, there is a corruption risk. Acceptable for single-user usage. A file-level lock would be the proper fix if this becomes multi-user.

**m6 (was m3): Phase 2 time estimate (6-8 hours) may be aggressive.** The current posting_queue.html is 1178 lines. Adding entity grouping, score display, delta badges, iteration navigation, background iterate with polling, and spinner is substantial. 8-12 hours is more realistic.

**m7 (was m2): publish.py version resolution.** The plan does not specify how `kb publish --decimal X` resolves which version of a post to render. Deferred to Phase 4 execution.

---

## Open Questions Validation

All open questions from Round 1 have been resolved with decisions:
- Q1 -> D8 (full transcript, already resolves)
- Q2 -> D12 (show latest edit only, diff indicator)
- Q3 -> D9 ('g' for generate visuals)
- N1 -> D10 (new /stage endpoint, separate from approve)
- N2 -> D11 (reset existing approved items to draft)

No new questions requiring human input.

---

## Plan Strengths

- All 14 decisions (D1-D14) are well-reasoned and internally consistent.
- The versioning schema cleanly separates LLM iterations (N) from human edits (M).
- Phase ordering is correct: backend versioning (P1) -> iteration UI + approve rewire (P2) -> staging + editing (P3) -> slide editing (P4). Each phase is independently testable.
- The `linkedin_v2` alias convention means downstream consumers (visual_format, carousel_slides, visual pipeline) require zero changes.
- The explicit regex patterns for versioned key filtering (D13) are concrete and testable.
- Migration strategy (D11: reset approved items to draft) is clean and avoids mixed-state confusion.

---

## Recommendations

### Before Execution (Nice-to-Have, Not Blocking)

- [ ] **m1:** Clarify in Phase 3 files section that `/stage` is MODIFY (extending Phase 2 endpoint), not NEW. This prevents the executor from trying to create a duplicate route.
- [ ] **m6:** Adjust Phase 2 estimate from 6-8h to 8-12h to set realistic expectations.

### During Execution

- The executor should gate the `run_visual_pipeline()` removal in the approve handler behind an analysis-type check (not a blanket removal), since skool_post may still want auto-visual on approve.
- Phase 1 should include a test that explicitly verifies `{{transcript}}` resolution in the judge prompt -- do not just assume it works.
- Thread safety: add a brief comment in serve.py noting the single-user assumption near the iterate/stage/save endpoints.

---

## Issue Summary

| Severity | Count | Details |
|----------|-------|---------|
| Critical | 0 | -- |
| Major | 0 | -- |
| Minor | 7 | m1 (dup /stage), m2 (redundant AC), m3-m7 (carried forward from R1) |
