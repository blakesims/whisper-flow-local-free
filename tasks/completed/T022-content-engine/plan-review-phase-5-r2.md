# Plan Review: Phase 5 — Iterative Judge Loop with Versioned History (Round 2)

## Gate Decision: READY

**Summary:** All 5 required fixes from Round 1 have been adequately addressed. The spec is now implementable without ambiguity on the critical paths. 0 critical issues, 0 major issues, 3 minor issues found (all non-blocking).

---

## Round 1 Fix Verification

### C1: Visual pipeline re-trigger after Improve -- VERIFIED

**Round 1 issue:** After Improve overwrites `linkedin_v2` content, the carousel PDF generated from the old content would be stale. No mechanism to regenerate.

**Fix applied (Key behavior #6, line 447):** "After an Improve round succeeds and `linkedin_v2` is updated with the new content, `visual_status` is reset to 'pending' and the visual pipeline is automatically re-triggered in a background thread (same pattern as approve)."

**Also in Improve API endpoint spec (line 483):** "...resets `visual_status` to 'pending', triggers visual pipeline re-run."

**State transitions documented (line 484):** `visual_status: ready/text_only` -> `improving` -> `pending` -> `generating` -> `ready/text_only`

**Assessment:** Adequately specified. The "improving" status is a new addition to the visual_status state machine (currently: pending, generating, ready, text_only, failed). The spec explicitly calls out this new status in both the state transitions and the Files section (`serve.py` modification: "add `improving` to visual_status state machine"). The re-trigger uses the same `run_visual_pipeline()` background thread pattern from Phase 4, which is a known working pattern.

**One nuance to note for executor:** The `run_visual_pipeline()` function checks `if "visual_format" not in existing_analysis` and `if "carousel_slides" not in existing_analysis` before running those analyses (lines 243, 276 in serve.py). After an Improve round changes the `linkedin_v2` content, `visual_format` and `carousel_slides` from the PREVIOUS round will still be in the analysis dict. The executor should either (a) clear these before re-triggering the visual pipeline, or (b) ensure `run_visual_pipeline()` re-runs them when content has changed. The most natural approach is to clear `visual_format` and `carousel_slides` from the analysis dict when content changes, forcing re-classification. This is an implementation detail, not a spec gap -- the AC "After Improve completes, visual_status resets to 'pending' and visual pipeline re-triggers" (AC #8) makes the intent clear.

---

### C2: Auto-judge scope -- VERIFIED

**Round 1 issue:** "Always auto-judge" was ambiguous about where in the call stack it lives. Could triple approve-time latency if it runs in `run_visual_pipeline()`.

**Fix applied (Key behavior #1, line 417):** "This auto-judge happens in a new wrapper function `run_analysis_with_auto_judge()` called from the CLI entry point only. [...] Other callers (`run_visual_pipeline()`, `run_analysis_with_deps()`, `kb publish`) do NOT auto-judge -- they use the existing `linkedin_v2` result as-is."

**Assessment:** Adequately specified. The scope is explicitly narrowed to CLI only. The rationale is included: "the approve flow in kb serve already approved the content, and adding 2 extra LLM calls to background visual pipeline would triple the latency for no benefit." The wrapper function name (`run_analysis_with_auto_judge()`) is specified, and it is listed in the Files section under `kb/analyze.py` modifications. The `--judge` flag backward compat is addressed (kept but effectively no-op for linkedin_v2). AC #2 covers this: "Auto-judge happens in CLI only -- `run_visual_pipeline()` and `run_analysis_with_deps()` do NOT auto-judge."

---

### M1: History injection format -- VERIFIED

**Round 1 issue:** Current `{{#if judge_feedback}}` block accepts a single JSON blob. Full history injection format was unspecified.

**Fix applied (Key behavior #3, lines 419-444):** Explicit JSON array format defined with `{round, draft, judge}` objects. Uses the existing `judge_feedback` template variable (no new template variable needed). Context window estimation included: "at ~2KB per round (draft + judge), 5 rounds = ~10KB of history -- well within Gemini's context limits even with a long transcript."

**Fix also in Files section (line 492):** "MODIFY: update `{{#if judge_feedback}}` block instruction to tell LLM it receives a JSON array of all prior rounds and should consider the full history."

**Assessment:** Adequately specified. The format is concrete with a full JSON example. The approach of reusing `judge_feedback` (rather than adding a new template variable) is correct -- the existing `{{#if judge_feedback}}` conditional block in `linkedin_v2.json` (line 6 of the config) will render when `judge_feedback` is truthy. The context window estimation is reasonable. The config file modification is called out. AC #9 covers this: "Each improvement round receives full history JSON array (all prior drafts + all prior feedback)."

---

### M2: Improve API endpoint -- VERIFIED

**Round 1 issue:** No API endpoint spec for the Improve button. No sync/async decision. No state transitions.

**Fix applied (lines 481-486):** Complete endpoint spec:
- Endpoint: `POST /api/action/<action_id>/improve`
- Behavior: background thread (same pattern as visual pipeline)
- Step-by-step: load transcript -> determine round N -> run improvement with history -> save versioned outputs -> auto-judge -> update alias -> reset visual_status -> trigger visual pipeline
- State transitions: `ready/text_only` -> `improving` -> `pending` -> `generating` -> `ready/text_only`
- Error handling: revert visual_status to previous state, error logged, post remains usable
- Response: `{"status": "improving"}`, frontend polls

**Assessment:** Adequately specified. The endpoint follows the established pattern from the approve handler (line 740 in serve.py) and visual pipeline (line 216). The step-by-step behavior eliminates ambiguity. The error handling is explicit (revert to previous state, not just "failed"). AC #7 covers this: "POST /api/action/<action_id>/improve triggers next round in background thread."

---

### M3: Metadata location -- VERIFIED

**Round 1 issue:** `linkedin_v2_rounds` and `linkedin_v2_history` as top-level analysis keys would confuse `scan_actionable_items()` and the browse view.

**Fix applied (Storage model, lines 454-477):** Metadata (`_round` and `_history`) now lives INSIDE the `linkedin_v2` dict using the `_` prefix convention that already exists for `_model` and `_analyzed_at`.

**Explicitly noted (line 477):** "This avoids polluting the top-level analysis namespace with non-analysis metadata that would confuse `scan_actionable_items()` and the browse view."

**Assessment:** Adequately specified. This follows the existing codebase convention. In `scan_actionable_items()` at line 413-414 of serve.py, `raw_data` is built by filtering out `_` prefixed keys: `raw_data = {k: v for k, v in analysis_data.items() if not k.startswith("_")}`. So `_round` and `_history` will be automatically excluded from `raw_data`, which is correct behavior. AC #5 covers this: "`_round` and `_history` are inside `linkedin_v2` dict (not top-level analysis keys)."

---

## Minor Issues Addressed from Round 1

### m1 (Backward compat) -- VERIFIED

Line 479: "Existing `linkedin_v2` results (from Phase 1-4 usage) will not have `_round` or `_history`. The Improve button handles this gracefully -- if no `_round` exists, treat the current `linkedin_v2` as round 0 and create `linkedin_v2_0` retroactively before starting round 1."

AC #12 covers this.

### m2 (Zero judge results fallback) -- VERIFIED

Line 491 (Files section): "fallback 'Not judged' display for pre-Phase-5 posts."

AC #6 covers this: "kb serve posting queue shows judge scores alongside the post (fallback 'Not judged' for old posts)."

### m3 (--judge flag redundancy) -- VERIFIED

Line 417: "The `--judge` flag is kept for backward compatibility but is effectively a no-op for linkedin_v2 (since judge always runs)."

AC #14 covers this: "`--judge` flag still works but is no-op for linkedin_v2 (auto-judge is default)."

---

## New Issues Found (Round 2)

### Critical
None.

### Major
None.

### Minor

**m1: Stale visual_format/carousel_slides after Improve round.**

As noted in the C1 verification above, `run_visual_pipeline()` has `if "visual_format" not in existing_analysis` and `if "carousel_slides" not in existing_analysis` guard clauses (serve.py lines 243, 276). After Improve changes `linkedin_v2` content, these old results remain in the analysis dict. The visual pipeline would skip re-classification and re-slide-generation, rendering the old carousel with potentially wrong format/slides.

This is an implementation detail, not a spec gap. The executor should clear `visual_format` and `carousel_slides` from the analysis dict before re-triggering the visual pipeline. The spec's intent (AC #8: visual pipeline re-triggers, AC #13: downstream consumers read from latest `linkedin_v2`) makes this implicit. Calling it out here so the executor does not miss it.

**m2: The `_history.scores` structure is lighter than the full history injected into the prompt.**

The storage model (line 461-466) shows `_history` containing only `scores` (an array of `{round, overall, scores}`), but Key behavior #3 (line 419-443) shows the full history injected into the prompt includes `draft` (full post text) and complete `judge` output for every round. These are two different structures serving different purposes:
- `_history.scores` in storage: compact, for UI score display
- Full history JSON array for prompt: comprehensive, for LLM context

This is fine as designed -- the full draft/judge data lives in the versioned keys (`linkedin_v2_0`, `linkedin_judge_0`, etc.) and can be reconstituted from there. The executor should understand that building the prompt history array requires reading from the versioned keys, not from `_history`.

**m3: The `improving` visual_status is not handled in the posting queue UI.**

The current `renderVisualBadge()` function in `posting_queue.html` (line 923) handles: generating, ready, text_only, failed, pending. The new `improving` status is not in this switch statement. The spec lists `posting_queue.html` as a file to modify (line 491), so this will be addressed during implementation. Just noting it for the executor's awareness -- the `improving` badge should probably look similar to `generating` (a spinner with "Improving..." text).

---

## Plan Strengths

- All 5 required fixes are directly traceable to the original issues and have explicit acceptance criteria.
- The auto-judge scoping (CLI only) is well-reasoned with a clear rationale that shows understanding of the existing pipeline's latency characteristics.
- The `_` prefix metadata convention reuses existing codebase patterns instead of inventing new ones.
- The Improve API endpoint spec follows the same background-thread pattern established in Phase 4, reducing implementation risk.
- The history injection format is concrete (full JSON example) with context window budget estimation.
- Backward compatibility is explicitly addressed for existing Phase 1-4 data.
- The 14 acceptance criteria are specific and verifiable.

---

## Recommendations

### For the Executor
- When implementing the Improve endpoint's visual pipeline re-trigger, clear `visual_format` and `carousel_slides` from the analysis dict before calling `run_visual_pipeline()` (see m1 above).
- When building the prompt history array from versioned keys, remember the full draft text lives in `linkedin_v2_N.post` and judge output in `linkedin_judge_N`, not in the compact `_history.scores`.
- Add `improving` to the `renderVisualBadge()` switch statement in the posting queue HTML.

### Consider Later
- Thread safety: the `_update_visual_status()` function has no actual locking (noted in Phase 4 code review). With Improve adding another background thread that writes to action-state.json, the risk of concurrent writes increases slightly. Not a blocker for single-user usage.
