# Plan Review: T023 Content Curation Workflow

## Gate Decision: NEEDS_WORK

**Summary:** The plan is well-structured with strong design decisions and clear phasing. However, it has 2 critical issues that would cause breakage during implementation: the versioned analysis keys (`linkedin_v2_0`, `linkedin_judge_0`, etc.) will be picked up by `scan_actionable_items()` and appear as separate actionable items in the queue, and the state machine has a gap where the `approve` handler's visual pipeline auto-trigger conflicts with the new "approve = stage" semantics. There are also 2 major issues around the action_id format and the new `stage` endpoint's relationship to the existing `approve` endpoint. These must be addressed in the plan before execution begins.

---

## Open Questions Validation

### Valid (Need Human Input)

| # | Question | Why Valid |
|---|----------|-----------|
| Q1 | Judge transcript access -- how much transcript context? | Token cost vs. quality tradeoff with real budget implications. Full transcript could be 10K+ tokens per judge call. The plan already decided "judge gets transcript access" (D6) but didn't resolve HOW MUCH, which affects prompt design and cost. |
| Q2 | Edit sub-versioning display -- how to show edit history in kb serve? | Directly affects UI complexity in Phase 3. All three options are viable but produce meaningfully different UX. |
| Q3 | Keyboard shortcut for "generate visuals" in staging? | Minor but genuinely a user preference. Recommend defaulting to 'g' and marking as resolved, since it does not conflict with existing shortcuts. |

**Recommendation for Q3:** Auto-decide 'g' for generate visuals. The existing posting queue shortcuts are j/k (navigate), c (copy), m (mark posted), q/r/b/v/p (mode switch). 'g' is unused and semantically clear. This frees the human to focus on Q1 and Q2.

### New Questions Discovered

| # | Question | Options | Impact |
|---|----------|---------|--------|
| N1 | Should the "stage" action reuse the existing `approve` endpoint with modified behavior, or be a brand new endpoint? | A) Modify approve to mean "stage" (breaking change) B) New `/api/action/<id>/stage` endpoint, deprecate approve | Affects backward compat if anyone has automated the approve flow. B is safer but creates two similar endpoints. |
| N2 | What happens to already-approved items when T023 ships? | A) Grandfathered as "published-ready" (old flow) B) Retroactively moved to "staged" status C) Left as-is, new items use new flow | Data migration concern. Existing action-state.json has items with status "approved" that went through auto-visual. |

---

## Issues Found

### Critical (Must Fix Before Execution)

**C1: Versioned analysis keys will pollute `scan_actionable_items()` and create ghost entries in the queue.**

The versioning schema stores `linkedin_v2_0`, `linkedin_v2_1`, `linkedin_judge_0`, `linkedin_judge_1`, `linkedin_v2_1_0`, `linkedin_v2_1_1` as top-level keys in the `analysis` dict (plan lines 101-106). `scan_actionable_items()` at `kb/serve.py` line 375 iterates over ALL `analysis.keys()` and calls `get_destination_for_action()` for each one. The action_mapping has `linkedin_v2: LinkedIn` as a plain match, but `linkedin_v2_0`, `linkedin_v2_1` etc. will NOT match this mapping exactly because `get_destination_for_action()` does exact string comparison (serve.py line 96).

However, the linkedin_judge keys WILL potentially match if a `linkedin_judge` mapping is ever added. And more critically, the versioned `linkedin_v2_N` keys create noise -- they exist as analysis keys but are NOT actionable and should not appear anywhere.

The real danger: if someone adds `linkedin_v2_0` or similar to the action_mapping for debugging, or if a future pattern-match enhancement makes partial matches work, every versioned copy becomes a separate queue item.

**Fix required:** The plan must specify:
1. How `scan_actionable_items()` should be modified to skip versioned keys (e.g., regex filter for `_\d+` suffix patterns, or an explicit exclusion list, or a `_versioned: true` metadata flag).
2. Alternatively, do NOT store versioned keys as top-level analysis entries. Store them inside a `_versions` dict within `linkedin_v2` itself. This would be cleaner and avoids the problem entirely.

**C2: The approve handler at serve.py line 789-802 auto-triggers `run_visual_pipeline()`. The plan says "approve = stage, not publish" (D2) and "visual generation only triggers from staging" (Phase 3 AC). But the plan does not specify HOW the approve handler gets rewired.**

Phase 3 says (line 259): "Rewire approve handler: approve no longer triggers visual pipeline." But Phase 2 introduces the 'a' shortcut for staging, and Phase 2's files section says nothing about modifying the approve handler. Phase 3's files section lists this rewire. This means during Phase 2, if the executor wires 'a' to the existing `/api/action/<action_id>/approve` endpoint, the visual pipeline WILL auto-trigger on stage -- contradicting D2.

The plan needs to clarify whether Phase 2's 'a' shortcut:
- (a) Calls the existing `/approve` endpoint (which auto-triggers visuals -- wrong behavior until Phase 3 rewires it), or
- (b) Calls a new `/stage` endpoint from the start (requiring the endpoint to exist in Phase 2 even though "staging area" is Phase 3).

This is a dependency ordering problem. Phase 2 depends on the approve rewire that is scheduled for Phase 3. Either the rewire needs to move to Phase 2, or the 'a' shortcut in Phase 2 should call a new endpoint.

---

### Major (Should Fix)

**M1: Action ID format will break with versioned analysis names.**

Action IDs are constructed as `{transcript_id}--{analysis_name}` (serve.py line 383). The `ACTION_ID_PATTERN` regex is `r'^[\w\.\-]+--[a-z0-9_]+$'` (serve.py line 40). If the versioned key `linkedin_v2_0` somehow becomes an actionable analysis name, the action ID would be `transcript_id--linkedin_v2_0`. This would work syntactically, but the plan doesn't clarify whether action IDs reference the `linkedin_v2` alias or a specific version. The iterate and stage endpoints use `<action_id>` -- do they operate on `transcript_id--linkedin_v2` (the alias) and internally resolve to the correct version?

**Fix:** Explicitly state that ALL API endpoints use the action_id based on the ALIAS (`linkedin_v2`), not versioned keys. The server resolves the alias to the current version internally.

**M2: The linkedin_judge.json prompt already includes `{{transcript}}` on line 6 of the config ("ORIGINAL TRANSCRIPT (for context on available material): {{transcript}}").**

The plan says (Phase 1, line 124): "Judge gets transcript access: modify `linkedin_judge.json` to include transcript text as optional input." But the judge already gets the transcript via the `resolve_optional_inputs()` function -- `linkedin_judge.json` has `"optional_inputs": []` (empty), but `transcript` is always resolved as a special case in `resolve_optional_inputs()`. The prompt template already uses `{{transcript}}`.

Looking at the judge config more carefully: the prompt hardcodes `{{transcript}}` in the template text, and `resolve_optional_inputs()` would only inject it if `transcript` were listed in `optional_inputs`. This means the judge currently gets an un-interpolated `{{transcript}}` placeholder OR the template engine handles it differently.

**Fix:** Verify whether `{{transcript}}` in `linkedin_judge.json` actually resolves to transcript content today. If it already works, the Phase 1 task "add transcript as optional_input" is unnecessary. If it does NOT work today (because `transcript` is not in `optional_inputs`), then the judge has been running without transcript context all along, which means the existing judge quality may change significantly when transcript access is actually added.

---

### Minor

**m1: The versioning schema diagram (plan lines 85-108) shows both an alias (`linkedin_v2`) AND versioned copies (`linkedin_v2_0`, `linkedin_v2_1`). The alias always points to the latest. But the `_round` and `_edit` metadata in the alias duplicates information derivable from the versioned keys.**

This is not wrong but adds bookkeeping overhead. If the alias's `_round` ever gets out of sync with the actual number of versioned keys, it creates a confusing state. The plan should note that `_round` is the source of truth and versioned keys are the history, or vice versa.

**m2: Phase 4 lists `kb/publish.py` as a file to modify for `kb publish --decimal X` support. The current `publish.py` searches for `carousel_slides` analysis (line 40-41). If the staged/edited content is stored in a different key (e.g., the edit version `linkedin_v2_2_1`), `publish.py` would need to know which version of the post to use for slide generation. The plan does not specify how `publish.py` resolves which version to render.**

**m3: Phase 2 estimated time (6-8 hours) seems aggressive for a "major UI redesign" of `posting_queue.html` that includes: entity grouping, score display, delta badges, iteration navigation (up/down), iterate trigger with background LLM call and polling, spinner, and "Not judged" fallback. The current posting_queue.html is 1178 lines of monolithic HTML/JS. Adding iteration view, score panels, delta badges, and a new keyboard mode on top of this is substantial.**

**m4: The state machine (plan lines 66-81) shows `[draft] -> 'a' stage -> [staged]` but does not show a transition back from `[staged]` to `[draft]`. If a user stages a post, starts editing, then decides they want another LLM iteration instead, can they un-stage? The state machine should address this or explicitly declare it one-way.**

**m5: Thread safety concern carried forward from T022 plan-review-phase-5-r2.md (line 149). With T023 adding iterate (background thread), stage, save-edit, and generate-visuals operations -- all potentially writing to the same transcript JSON and action-state.json concurrently -- the risk of file corruption increases. The plan should acknowledge this risk and either (a) accept it for single-user usage or (b) add a file-level lock.**

---

## Plan Strengths

- The state machine design (transcribe -> iterate -> stage -> edit -> generate -> publish) is well-conceived and matches the user's stated workflow preferences.
- Decision D1 (auto-judge CLI only, not in visual pipeline) shows correct understanding of latency constraints in the existing architecture.
- The versioning schema's separation of LLM iterations (N) from human edits (M) in `linkedin_v2_N_M` is a clean conceptual model that enables meaningful diff tracking.
- The plan incorporates lessons from T022 Phase 5 review rounds -- particularly the metadata-inside-alias convention with `_` prefix, backward compatibility for existing data, and the "Not judged" fallback.
- Phase ordering is mostly sensible: backend versioning first (Phase 1), then UI for iteration (Phase 2), then staging/editing (Phase 3), then slide editing (Phase 4). Each phase is independently testable.
- The decision to keep `linkedin_v2` as an alias pointing to latest is good -- downstream consumers (visual_format, carousel_slides, visual pipeline) do not need to change.

---

## Recommendations

### Before Proceeding (Must Address)

- [ ] **C1:** Decide how versioned analysis keys (`linkedin_v2_0`, `linkedin_judge_0`, etc.) are excluded from `scan_actionable_items()`. Either: (a) add a skip-pattern for `_\d+` suffixed keys, (b) store versions inside a nested `_versions` dict within the alias, or (c) add a `_is_version: true` metadata flag and filter on it.
- [ ] **C2:** Resolve the Phase 2/Phase 3 dependency on the approve handler rewire. Either move the visual pipeline de-coupling into Phase 2, or have Phase 2's 'a' shortcut call a new `/stage` endpoint that does NOT trigger visuals.
- [ ] **M1:** Clarify that all API endpoints use the alias-based action_id (`transcript_id--linkedin_v2`), not versioned keys.
- [ ] **M2:** Verify whether `{{transcript}}` in `linkedin_judge.json` actually resolves today, and adjust Phase 1 scope accordingly.

### Consider Later

- Thread safety for concurrent file writes (m5) -- acceptable for single-user but worth a TODO comment.
- Un-stage transition (m4) -- decide whether staging is reversible.
- Publish.py version resolution (m2) -- can be decided during Phase 4 execution.
- Phase 2 time estimate may need revision upward (m3).
