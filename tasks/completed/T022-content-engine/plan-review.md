# Plan Review: T022 Content Engine

## Round 2

## Gate Decision: READY

**Summary:** All 3 critical and 5 major issues from Round 1 have been properly addressed. The judge loop mechanism is well-specified using the existing conditional template system. The async pipeline strategy uses a proven pattern from videos.py. The carousel_slides dependency is clearly delineated (config in Phase 2, wiring in Phase 4). Two minor issues remain but are non-blocking.

---

## Round 1 Issue Verification

### Critical Issues -- All Resolved

| # | Issue | Fix Applied | Verification |
|---|-------|------------|--------------|
| C1 | Judge loop has no implementation path | Added `run_with_judge_loop()` function spec to Phase 1 with detailed 5-step mechanism. Uses `{{judge_feedback}}` conditional variable via `render_conditional_template()`. | VERIFIED. The `render_conditional_template()` function at analyze.py:672 supports exactly this pattern: `{{#if judge_feedback}}...{{/if}}`. The approach of re-running the analysis with feedback injected via prerequisite_context is consistent with how `analyze_transcript()` (line 734) accepts `prerequisite_context` and passes it to `render_conditional_template()`. The mechanism is sound. |
| C2 | Flask blocking on approve | Phase 4 now specifies background thread execution. Approve returns immediately. `visual_status` field tracks progress. Posting queue polls with spinner. | VERIFIED. The `threading.Thread(target=..., daemon=True)` pattern from videos.py (line 945) is a proven precedent in this codebase. The `visual_status` state machine ("generating" / "ready" / "failed") in action-state.json is the right approach. The plan correctly specifies that errors set "failed" without blocking the post. |
| C3 | carousel_slides dependency wrong | Clarified: config JSON created in Phase 2, wiring into pipeline in Phase 4 | VERIFIED. Phase 2 now explicitly states: "Note: carousel_slides analysis type is created here as a config file, but it requires linkedin_v2 output as input. It will be wired into the pipeline in Phase 4." Phase 4 step 4 references it: "If CAROUSEL: run carousel_slides (requires linkedin_v2 output)". Dependency chain is clear. |

### Major Issues -- All Resolved

| # | Issue | Fix Applied | Verification |
|---|-------|------------|--------------|
| M1 | No rendering tools installed | Phase 3 includes installation tasks. User context confirms both already working on server. | VERIFIED. mmdc v11.12.0 installed at /home/blake/.npm-global/bin/mmdc. Playwright 1.58.0 installed with Chromium v1208 at /home/blake/.cache/ms-playwright/chromium-1208. Both confirmed working on this server. |
| M2 | Template location conflicts with Flask | Changed to `kb/carousel_templates/` | VERIFIED. Flask templates are in `kb/templates/` (action_queue.html, posting_queue.html, etc.). Carousel templates in `kb/carousel_templates/` avoids any conflict. Plan is consistent in all references. |
| M3 | action_mapping not updated | Added to Phase 1 (testing) and Phase 4 (transition) | VERIFIED. Phase 1 explicitly states: "Add linkedin_v2 to action_mapping config so it appears in kb serve action queue." Phase 4 states: "Remove linkedin_post from action_mapping (replaced by linkedin_v2)." The action_mapping in __main__.py (line 52) shows where the config lives. |
| M4 | linkedin_post transition unaddressed | Phase 4 specifies removal from action_mapping, old items remain, batch reprocess via kb publish | VERIFIED. Phase 4 states: "Old linkedin_post items remain in state but won't appear in queue. Can batch-reprocess old transcripts via kb publish." |
| M5 | No way to serve visual files | Phase 4 adds Flask route `GET /visuals/<path:filepath>` | VERIFIED. serve.py currently has no `send_from_directory` or `send_file` usage. The plan correctly identifies this gap and adds a new route. The executor will need to use Flask's `send_from_directory` or `send_file` from the KB_ROOT to serve generated PDFs and thumbnails. |

### Minor Issues -- All Addressed

| # | Fix | Status |
|---|-----|--------|
| Carousel dimensions unresolved | Defaulted to 1080x1350px (portrait) | OK |
| Jinja2 not committed to | Committed to Jinja2 | OK |
| "1 session" time estimates | Normalized to hour estimates (3-4h, 4-6h) | OK |
| No mermaid failure handling | Added: "skip mermaid slide and log warning" | OK |
| Jinja2 dependency for render.py | Noted as already installed (v3.1.6) | OK |
| action_queue.html typo | Fixed -- posting_queue.html is the correct file | OK |

---

## New Issues Found (Round 2)

### Minor (Non-Blocking)

1. **D1 decision says "Mac" but tools are on server** -- The D1 decision in the Decision Matrix states "Mac. KB serve runs on Mac. mmdc runs on Mac. Pipeline is local." However, this repo exists on the server (hostname: `server`), and the rendering tools (mmdc, Playwright + Chromium) are verified installed on the server. The user context also says "both already verified working on server." The D1 decision text appears to be outdated or aspirational. This does not block execution -- the executor should simply run on whichever machine has the tools (currently the server). The executor will notice this immediately and it does not affect the plan structure. **Recommendation:** Update D1 text to reflect reality, or note that the pipeline runs wherever `kb serve` runs.

2. **`run_with_judge_loop()` needs to handle the save-to-disk step** -- The judge loop mechanism specifies: generate draft -> judge evaluates -> re-run with feedback -> overwrite original. The function `analyze_transcript_file()` (line 960) handles saving results to the transcript JSON. But `run_with_judge_loop()` will need to either: (a) call `analyze_transcript_file()` which has its own save logic, or (b) manage saves manually. The plan says "overwrites the original draft with improved version" but does not specify when the intermediate results are saved. If the process crashes between judge evaluation and re-generation, the draft could be lost. **Recommendation:** The executor can handle this -- the natural approach is to save after each step (generate saves, judge saves, improved version saves and overwrites the draft). This is a normal implementation detail, not a planning gap.

---

## Open Questions Validation

### Valid (Need Human Input)
| # | Question | Why Valid |
|---|----------|-----------|
| A3 | CTA pattern? | Correctly deferred. Blake is still learning LinkedIn. The prompt template can include a configurable CTA section. Not a build blocker. |

### Round 1 New Questions -- All Resolved

| # | Question | Resolution |
|---|----------|------------|
| N1 | How does linkedin_v2 get triggered for existing content? | Resolved: Phase 4 specifies `kb publish --pending` for batch processing and `--regenerate` for re-rendering. Old transcripts can be reprocessed. |
| N2 | Where does judge loop run? | Resolved: New `run_with_judge_loop()` function in analyze.py. Detailed 5-step mechanism specified in Phase 1. |
| N3 | CCA brand assets (hex, logo)? | Partially resolved: Default `#2D1B69` specified. Blake to confirm. Phase 2 AC includes "Blake approves visual design." |

### New Questions Discovered
| # | Question | Options | Impact |
|---|----------|---------|--------|
| None | -- | -- | No new questions requiring human input. The two minor issues above are executor-level details. |

---

## Plan Strengths

- The judge loop mechanism leveraging the existing `render_conditional_template()` and `{{#if judge_feedback}}` pattern is elegant. It reuses proven infrastructure rather than inventing new concepts.
- The background thread pattern from videos.py is well-referenced. The executor has a concrete codebase precedent to follow.
- Phase boundaries are clean: Phase 1 is pure LLM/analysis work (no rendering), Phase 2 is pure template/classification work (no pipeline), Phase 3 is pure rendering (no integration), Phase 4 ties everything together. This allows focused execution.
- The `visual_status` state machine ("generating" / "ready" / "failed") in action-state.json is the right abstraction -- it extends the existing state pattern rather than introducing a new state store.
- Time estimates (3-4h, 3-4h, 3-4h, 4-6h = ~15h total) are reasonable for the scope. Monday target is achievable.
- The decision to produce PDF carousels (not images) based on LinkedIn reach data is well-researched.
- `kb publish` CLI with `--pending`, `--regenerate`, `--dry-run` flags provides good operational control.

---

## Recommendations

### Before Proceeding
- [ ] Optionally update D1 decision text to reflect that rendering tools are on the server (non-blocking -- executor will see this immediately)
- [ ] Confirm CCA brand hex (`#2D1B69`) and whether a logo file exists (needed in Phase 2)

### Consider Later
- Thread safety: the background pipeline writes to transcript JSON files and action-state.json. If Blake approves two posts in quick succession, two background threads could race on action-state.json. A simple file lock or sequential queue would prevent this. The videos.py worker pattern uses a queue -- consider the same approach.
- `kb publish --preview` mode that opens generated PDF in the default viewer would be useful for template iteration in Phase 2.
- Quality guardrails: what if the judge loop produces a WORSE post on round 2? Consider keeping both versions and letting Blake choose, or only overwriting if judge scores improve.

---

## Round 1 Review (preserved for history)

Gate: NEEDS_WORK | 3 critical, 5 major, 6 minor | All addressed in Round 2.
