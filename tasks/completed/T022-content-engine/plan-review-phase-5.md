# Plan Review: Phase 5 — Iterative Judge Loop with Versioned History

## Gate Decision: NEEDS_WORK

**Summary:** The core concept is sound and well-motivated (versioned outputs, full history injection, score deltas). However, there are 2 critical issues that would cause bugs or broken downstream behavior if implemented as-is, and 3 major gaps that need specification before an executor can work without ambiguity.

---

## Issues Found

### Critical (Must Fix Before Execution)

**C1: Versioned keys will pollute `scan_actionable_items()` and create phantom posting queue entries.**

`scan_actionable_items()` in `serve.py` (line 375) iterates over ALL keys in `analysis`, then checks each against the action_mapping. The action_mapping currently maps `linkedin_v2 -> LinkedIn`. After Phase 5, the analysis dict will contain `linkedin_v2`, `linkedin_v2_0`, `linkedin_v2_1`, etc. Since `scan_actionable_items()` does `for analysis_name in analysis.keys()`, it will also try to match `linkedin_v2_0`, `linkedin_v2_1` against the action_mapping. These versioned keys will NOT match (action_mapping only has `linkedin_v2`), so they are silently skipped -- which is fine. BUT: `linkedin_judge_0`, `linkedin_judge_1`, and the metadata keys (`linkedin_v2_rounds`, `linkedin_v2_history`) will also be iterated over. The history dict will cause `get_destination_for_action()` to be called with it as a key name, which is harmless but wasteful.

The REAL issue: the Phase 5 spec says `linkedin_v2` always points to latest. But `scan_actionable_items()` also builds the action_id as `{transcript_id}--{analysis_name}`. If `linkedin_v2` is overwritten on each improvement round, the action_id stays the same (`transcript_id--linkedin_v2`) but the content changes. This means:
- The action-state.json entry for `transcript_id--linkedin_v2` (status: "approved", visual_status: "ready") persists from a prior round.
- When Blake hits "Improve" and `linkedin_v2` is overwritten with a newer version, the posting queue will show the NEW content but the OLD visual_status (still "ready" from the previous carousel).
- The carousel PDF was generated from the old `linkedin_v2` content, but the posting queue now shows new text. The text and the carousel are out of sync.

**Fix required:** Phase 5 must specify that after an "Improve" round succeeds, `visual_status` must be reset to "pending" (or a new status like "outdated"), and the visual pipeline must be re-triggered for the new content. The spec currently says nothing about visual re-generation after improvement.

---

**C2: "Always auto-judge" is a silent breaking change for CLI and background pipeline.**

Phase 5 AC1 says: `kb analyze -t linkedin_v2` generates draft AND auto-runs judge (no separate `--judge` flag needed).

Currently:
- `kb analyze -t linkedin_v2` calls `analyze_transcript_file()` which calls `run_analysis_with_deps()` -- this runs a single analysis pass, no judge.
- `kb analyze -t linkedin_v2 --judge` enters the judge loop code path.
- `run_visual_pipeline()` in `serve.py` (line 216) does NOT call `run_with_judge_loop()` at all -- it only runs `visual_format` and `carousel_slides`, both of which `require: ["linkedin_v2"]` and call `run_analysis_with_deps()`.

If Phase 5 makes `linkedin_v2` always auto-judge, the executor needs to decide:
1. Does the auto-judge happen inside `run_analysis_with_deps()` (every caller gets it automatically, including `run_visual_pipeline()`)? This would mean the background visual pipeline on approve suddenly takes 3x longer (draft + judge + improvement) instead of just running visual_format.
2. Does the auto-judge happen only in the CLI `analyze` entry point? Then `run_visual_pipeline()` and `kb publish` would NOT auto-judge.
3. Does the auto-judge happen inside a new wrapper function that both CLI and serve call?

The spec says "always" but doesn't address where in the call stack this behavior lives. This is not a detail the executor should guess at -- it changes the approve-time latency significantly (adding 2 extra LLM calls to the background pipeline).

**Fix required:** Specify whether auto-judge applies to: (a) CLI only, (b) CLI + background visual pipeline, or (c) all callers. Recommendation: CLI only (option a), with the background pipeline left as-is since it was just built in Phase 4 and the user already approved the content before the visual pipeline runs.

---

### Major (Should Fix)

**M1: Full history injection has no prompt template specification.**

The spec says "Each improvement round receives the FULL history: all prior drafts, all prior judge evaluations, and all prior feedback." But the current `linkedin_v2.json` prompt has only a single `{{#if judge_feedback}}` block that accepts a single JSON blob. For full history injection, the plan needs to specify:

- What format does the history take? Is it a single `judge_feedback` variable containing ALL rounds concatenated? Or a new template variable like `{{#if improvement_history}}`?
- How large can this get? By round 3, you have: draft_0 (1200-1800 chars) + judge_0 (structured JSON ~500 chars) + draft_1 + judge_1 + draft_2 + judge_2. That's potentially 6000+ chars of history injected into the prompt ON TOP of the transcript.
- Does this risk hitting Gemini's context window limits for long transcripts?

**Fix required:** Specify the format of the history injection. Recommendation: single `judge_feedback` variable containing a structured JSON array of all rounds (not concatenated text), and add a note about context window considerations.

---

**M2: "Improve" button in kb serve has no API endpoint or backend handler specified.**

The spec says: "Blake reviews draft + scores in kb serve, then decides whether to trigger a round of improvement. Could be a button: 'Improve' or keyboard shortcut."

But the Files section only lists modifications to `serve.py` as "MODIFY: show judge scores in posting queue, 'Improve' button triggers next round." There is no specification of:
- What API endpoint does the Improve button call? (e.g., `POST /api/action/<action_id>/improve`)
- What does this endpoint do? Load transcript, call `run_with_judge_loop()` with the next round number, save, update visual status?
- Does the improvement run synchronously (blocking the Flask request) or in a background thread like the visual pipeline?
- What happens to the posting queue item state during improvement? Does it stay "approved"? Does it go back to a new status?

**Fix required:** Add an API endpoint spec for the Improve action, including whether it runs sync/async and what state transitions occur.

---

**M3: `linkedin_v2_rounds` and `linkedin_v2_history` are not analysis results -- they are metadata.**

The storage model puts `linkedin_v2_rounds: 2` and `linkedin_v2_history: {...}` as top-level keys in the `analysis` dict alongside real analysis results. But analysis results are expected to be dicts with keys like `_model`, `_analyzed_at`, content keys, etc. The `linkedin_v2_rounds` is an integer (2) and `linkedin_v2_history` is a metadata structure.

This will cause issues in:
- `scan_actionable_items()` line 389: `if isinstance(analysis_data, dict)` -- `linkedin_v2_rounds` is an int, falls to `else: content = str(analysis_data)`. Not harmful but produces a pointless "2" string.
- `get_transcript()` API at line 975: iterates `for name, content in data.get("analysis", {}).items()` and will try to display `linkedin_v2_rounds` and `linkedin_v2_history` as analysis results in the browse view.
- Any future code that assumes all keys in `analysis` are analysis type names.

**Fix required:** Either (a) nest the metadata inside the `linkedin_v2` result dict (e.g., `linkedin_v2._rounds`, `linkedin_v2._history`), or (b) use a separate top-level key outside `analysis` (e.g., `judge_history`). Option (a) is cleaner -- it follows the existing `_model`, `_analyzed_at` prefix convention.

---

### Minor

**m1: The spec does not address backward compatibility with existing linkedin_v2 results.**

Transcripts that already have `linkedin_v2` analysis results (from Phase 1-4 usage) will not have `linkedin_v2_0`, `linkedin_v2_rounds`, or `linkedin_v2_history`. The "Improve" button would need to handle this gracefully -- treating the existing `linkedin_v2` as round 0 and creating `linkedin_v2_0` retroactively, or just starting fresh.

**m2: No specification for what kb serve shows when there are zero judge results.**

The spec says "kb serve posting queue shows judge scores alongside the post." But posts that were run without the judge (pre-Phase 5, or if judge fails) will have no scores. The UI needs a fallback for this case.

**m3: The `--judge` CLI flag becomes redundant if auto-judge is always on.**

The spec says "no separate --judge flag needed" but doesn't explicitly say to deprecate/remove the flag. If left in place, what does `--judge` do when judge already runs automatically? Nothing? An extra round? This needs clarification for the executor.

---

## Plan Strengths

- The versioned storage model (linkedin_v2_0, linkedin_v2_1, etc.) is a clean approach that preserves the audit trail without breaking the alias pattern.
- Full history injection is a smart way to prevent ping-ponging between contradictory judge feedback across rounds.
- Score deltas visible in the UI give Blake immediate feedback on whether improvement rounds are working.
- Indefinite rounds with explicit opt-in (not auto-looping) is the right UX -- Blake stays in control.
- The "future vision" section correctly scopes analytics and A/B testing as out-of-scope.

---

## Open Questions Validation

Phase 5 has no explicit open questions in the decision matrix. However, two decisions embedded in the spec need human input:

### New Questions Discovered

| # | Question | Options | Impact |
|---|----------|---------|--------|
| 1 | Should auto-judge apply to the background visual pipeline (approve flow) or CLI only? | A) CLI only -- approve flow stays fast, user runs judge manually before approving. B) CLI + approve flow -- every approve triggers judge loop first, adding ~30s latency. C) Configurable via flag. | Approve-time latency. Option A recommended. |
| 2 | After "Improve" in kb serve, should the visual pipeline automatically re-run? | A) Yes, always re-generate carousel from new content. B) No, mark visual as "outdated" and let user manually regenerate. C) Ask user (modal: "Content changed. Regenerate carousel?"). | UX and compute cost. Option A recommended for consistency. |

---

## Recommendations

### Before Proceeding (Must Fix)
- [ ] C1: Specify visual pipeline re-trigger behavior after Improve round
- [ ] C2: Specify where auto-judge behavior lives in the call stack (CLI only vs. all callers)
- [ ] M1: Define the format of full history injection into the prompt template
- [ ] M2: Add API endpoint spec for the Improve button (endpoint, sync/async, state transitions)
- [ ] M3: Move `linkedin_v2_rounds` and `linkedin_v2_history` inside the `linkedin_v2` dict using `_` prefix convention

### Consider Later
- Backward compat migration for existing linkedin_v2 results (m1)
- `--judge` flag deprecation or repurposing (m3)
- Context window budget estimation for multi-round history injection (part of M1)
