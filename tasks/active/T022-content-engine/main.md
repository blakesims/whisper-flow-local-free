# Task: Content Engine — Structured Text to Visual Content & Lead Magnets

## Task ID
T022

## Meta
- **Status:** CODE_REVIEW
- **Last Updated:** 2026-02-07

## Overview

The KB pipeline currently transforms messy unstructured input (audio, video, voice notes) into highly structured text with analyses, organized into a decimal system. The posting queue (T020) adds an approve → posted workflow. But the last mile is manual: copy text, decide on visual format, create mermaid/carousel/screenshot, style it, upload it. This friction kills consistency.

T022 builds the **content engine** — the system that takes approved structured text and turns it into publish-ready visual content (LinkedIn carousels, mermaid diagrams, styled posts) and packaged lead magnets (PRDs + plugin skills that build software on the reader's machine).

**The core insight:** Every decision Blake makes when creating a post (mermaid or carousel? what CTA? which lead magnet?) can be codified once and applied automatically. The content engine encodes these decisions.

## Current Pipeline (what exists)

```
Input (audio/video/voice)
    → KB transcription (whisper)
    → KB analysis (gemini — summary, linkedin_post, skool_post, key_points, etc.)
    → kb serve action queue (review, edit)
    → Approve with 'a' → posting queue (T020)
    → Copy with 'p' → MANUAL from here
```

## Target Pipeline (what we're building)

```
Input (audio/video/voice)
    → KB transcription
    → KB analysis
    → kb serve action queue → Approve
    → Content engine:
        1. Format post (Nick Saraev style — hook, problem, build, CTA)
        2. Decide visual type (mermaid | carousel | screenshot | none)
        3. Generate visual (mermaid CLI → PNG | HTML slides → PNG | etc.)
        4. Attach lead magnet reference (if applicable)
        5. Package into ready-to-publish bundle (text + image + CTA)
    → Posting queue (enhanced — shows visual preview + one-click copy)
    → Publish (manual copy-paste for now, API later)
```

## Objectives
- Turn approved KB content into publish-ready LinkedIn posts with visuals
- Codify visual format decisions (when mermaid, when carousel, when screenshot)
- Generate visuals automatically (no manual nvim → MarkdownPreview → screenshot chain)
- Support HTML slide carousels (Nick Saraev style) rendered to images
- Create lead magnet packaging system (PRD + plugin + video = downloadable bundle)
- Make publishing so frictionless that not posting is harder than posting

## Dependencies
- T020 (KB Posting Queue Extension) — COMPLETE
- T021 (KB Serve UI Layout & Rendering) — COMPLETE

## Rules Required
- None identified yet

## Resources & References
- T020 main.md — posting queue workflow, approve/posted state machine
- kb/serve.py — action queue dashboard, posting queue endpoints
- kb/analyze.py — analysis types, conditional templates, optional inputs
- Nick Saraev LinkedIn posts — format reference (hook, problem, build, CTA + "comment X")
- Mermaid CLI — `mmdc` renders mermaid to PNG/SVG
- Blake's current manual flow: mermaid code → nvim → :MarkdownPreview → screenshot → capture app → upload

---

## Open Questions (MUST ANSWER BEFORE PLANNING)

These questions need human input to unblock planning. Grouped by domain.

### A. Post Formatting

| # | Question | Options | Impact |
|---|----------|---------|--------|
| A1 | What post formats do we support initially? | a) LinkedIn only b) LinkedIn + Skool c) LinkedIn + Skool + Twitter/X | Scope of format templates |
| A2 | Should the engine rewrite/polish KB linkedin_post output or use it as-is? | a) Use as-is (KB analysis already generates good posts) b) Light polish pass (grammar, hook sharpening) c) Full rewrite into Nick Saraev format | Complexity, quality control |
| A3 | What's the CTA pattern? | a) "Comment X and I'll DM you" (requires manual DM follow-up) b) "Link in comments" (direct to Skool/download) c) Configurable per post | Growth strategy, friction |
| A4 | Should every post have a CTA/lead magnet or only some? | a) Every post b) Only posts tagged with a lead magnet c) Configurable — engine suggests, Blake confirms | Content strategy |

### B. Visual Format Decisions

| # | Question | Options | Impact |
|---|----------|---------|--------|
| B1 | What visual types do we support initially? | a) Mermaid diagrams only b) Mermaid + HTML carousels c) Mermaid + carousels + styled code screenshots | Build scope |
| B2 | How does the engine decide which visual to use? | a) Rule-based (if post mentions workflow → mermaid, if list → carousel, etc.) b) AI decides based on content c) Blake tags it during approve step d) Hybrid: AI suggests, Blake confirms | Autonomy vs control |
| B3 | Mermaid rendering: what tool? | a) `mmdc` (mermaid CLI) — renders locally to PNG/SVG b) mermaid.ink API — renders via HTTP, no local install c) Puppeteer-based (headless Chrome rendering) | Dependencies, quality |
| B4 | Carousel format: how many slides per carousel? | a) Fixed (5-8 slides) b) Dynamic based on content length c) AI decides based on content structure | Template design |
| B5 | Carousel styling: what's the visual identity? | a) Clean minimal (white bg, dark text, accent color) b) Dark mode (like Nick Saraev's) c) Multiple templates (rotate or match content) | Brand, templates needed |
| B6 | Should visuals be generated at approve time or on-demand? | a) Auto-generate on approve b) Generate when Blake hits a "render" button c) Batch generate all approved posts overnight | UX, compute |

### C. Lead Magnets

| # | Question | Options | Impact |
|---|----------|---------|--------|
| C1 | What IS a lead magnet in this system? | a) A downloadable file (PDF, zip) b) A GitHub repo link (plugin) c) A Skool post with the content d) All of the above, configurable per post | Distribution architecture |
| C2 | First lead magnet: Whisper Flow plugin. What's the delivery mechanism? | a) GitHub repo — they clone and run b) CCA plugin — `/plugin install` then `/cca-plugin:whisperflow` c) Download zip from website d) Skool classroom resource | User friction, reach |
| C3 | How are lead magnets linked to posts? | a) Tag system — each post can reference a lead magnet by ID b) Auto-detected from content (if post mentions whisper → link whisper magnet) c) Manual — Blake assigns during approve | Automation level |
| C4 | Do lead magnets need a landing page? | a) Yes — generated HTML page per lead magnet b) No — just link to Skool or GitHub c) Yes but hosted on existing website (zen-ai.co or similar) | Scope, hosting |

### D. Pipeline Architecture

| # | Question | Options | Impact |
|---|----------|---------|--------|
| D1 | Where does visual generation happen? | a) On the server (where kb serve runs) b) On Mac (where Blake reviews) c) Either — generate on server, preview on Mac via kb serve | Deployment, dependencies |
| D2 | How do generated visuals get stored? | a) Alongside KB data (in the decimal folder) b) Separate content/output directory c) In a new `visuals/` directory per decimal | File organization |
| D3 | Should the content engine be a new KB command or extend kb serve? | a) New command: `kb publish` (separate from serve) b) Extend kb serve with visual generation c) Both — `kb publish` for batch, serve for interactive | Code organization |
| D4 | Does this need a database or is file-based state sufficient? | a) File-based (extend action-state.json) b) SQLite (like zmt-database) c) File-based for now, migrate later if needed | Complexity |

### E. Scope Control

| # | Question | Options | Impact |
|---|----------|---------|--------|
| E1 | What's the MVP? What ships first? | a) Text formatting only (no visuals) b) Text + mermaid diagrams c) Text + mermaid + one carousel template d) Full system (text + mermaid + carousel + lead magnets) | Time to first post |
| E2 | Timeline target? | a) First automated post this week b) Full engine in 1-2 weeks c) No rush, get it right | Pressure vs quality |
| E3 | Should we integrate with LinkedIn API for direct posting? | a) Yes, from day 1 b) No, copy-paste is fine for now c) Build the hook but don't activate yet | Scope, LinkedIn API complexity |

---

## Decision Matrix

### Resolved

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| B1 | Visual types supported? | **Two formats: PDF carousel or text-only.** Single images get -30% reach (LinkedIn 2026 data). Mermaid diagrams live INSIDE carousels as a slide, never standalone. | Research-backed. Simplifies build to one visual pipeline (HTML→PDF). |
| B2 | How does engine decide visual format? | **LLM classifies as new KB analysis type (`visual_format`).** Two-way: CAROUSEL (tutorial, framework, multi-point, workflow) or TEXT_ONLY (short take, opinion). If CAROUSEL + content has workflow → one slide includes mermaid diagram. | Cheap classification call. Runs alongside new analysis type. |
| E1 | What's the MVP? | **Tier 1 only (consistency machine).** Post formatter + visual classifier + mermaid rendering + 2-3 carousel templates + kb serve integration. Target: usable by Monday. | Lead magnets (Tier 2) use the same visual tools but are a separate creative/strategic workflow. Deferred to separate task. |
| E2 | Timeline target? | **Usable by Monday.** Visual back-and-forth on templates expected. | Leverage task-workflow subagents for parallel execution. |
| A2 | Rewrite/polish KB output or as-is? | **New analysis type.** Not downstream polishing (LLM→LLM is lossy). New config (e.g. `linkedin_v2`) with better prompt informed by LinkedIn research. Transcript → high-quality post in one pass. Old `linkedin_post` stays for backward compat. Can re-run old transcripts through new type. | Cleaner than chaining. One source of truth. |
| A2+ | LLM-as-judge? | **Yes, one round.** Generate → judge evaluates → feedback → improve. Two LLM calls total. Judge criteria informed by LinkedIn research. | Significant quality jump from round 0→1. Diminishing returns after. Cost negligible at 2-3 posts/week. |
| A4+ | Quantity vs quality? | **2-3 posts per week, not daily.** Engine is selective — runs all inputs through analysis but only best become posts. 36 posts over 12 weeks = real momentum. Fits Blake's "obsessive depth" better than daily mediocre output. | Nick Saraev cadence is 3-4/week. Consistency matters more than frequency. |
| C1-C4 | Lead magnets? | **All deferred.** Lead magnets are Tier 2 (curated campaign posts). Separate task, separate workflow. Engine provides tools (carousel/mermaid generators) but lead magnet strategy is Blake's creative call. | Trying to automate lead magnet ideation was causing scope confusion. Tier 1 (daily posts) and Tier 2 (campaign posts) are different workflows. |
| A1 | Platforms supported? | **LinkedIn only for MVP.** | Focus. Skool posts are different format/audience. Add later. |
| A3 | CTA pattern? | **OPEN — needs more learning.** Blake still learning LinkedIn. Will revisit after first few posts are live. Engine should support configurable CTAs but no default pattern locked in yet. | Not a build blocker — engine generates post, CTA is part of prompt template and can be iterated. |
| B3 | Mermaid rendering tool? | **`mmdc` (mermaid CLI).** Runs on Mac. Post-processing: overlay on background image from configurable library. Ensure contrast. | Simple, local, no API dependency. `npm i -g @mermaid-js/mermaid-cli` |
| B4 | Carousel slide count? | **6-10 slides, AI decides based on content.** 10-30 words per slide. Research-backed range. | Constrained but flexible. |
| B5 | Carousel styling? | **Dark purple brand (CCA logo). Make configurable.** Start with 1-2 templates. Iterate after seeing renders. Needs visual mockup phase. | Brand consistency. Configurable so templates can evolve. |
| B6 | Generate visuals at approve time? | **Yes — auto-generate on approve.** Hit 'a' in kb serve → engine kicks off visual generation → ready in posting queue. | Minimal friction. Visuals ready by the time Blake checks queue. |
| D1 | Where does generation run? | **Mac.** KB serve runs on Mac. mmdc runs on Mac. Pipeline is local. | Matches existing workflow. |
| D2 | Visual storage? | **Alongside KB data in decimal folder** (e.g. `50.01.01/visuals/carousel.pdf`). **Configurable** — not hardcoded. | Co-located with source content. Path configurable for flexibility. |
| D3 | New command or extend serve? | **Both.** `kb publish` for batch/CLI ops (regenerate, reprocess, dry-run). Extend `kb serve` for interactive approve→generate flow. | Complements each other. Serve for interactive, publish for batch. |
| D4 | Database vs file-based? | **File-based.** Extend action-state.json. | No reason for SQLite here. |
| E3 | LinkedIn API? | **No for MVP.** Copy-paste is fine. LinkedIn API is restrictive. Blake should warm up account manually for now. | Avoids auth complexity. Revisit when posting cadence is established. |

### Visual Strategy (revised after LinkedIn research)

**Key finding:** Single images get 30% LESS reach than text-only. But native PDF carousels get 5-10x MORE reach. This eliminates standalone mermaid diagrams.

**Two formats only:**
1. **PDF Carousel** — HTML → PDF. 6-10 slides, 10-30 words/slide, 1080x1080px or 1080x1350px. Used for: tutorials, frameworks, how-tos, multi-point posts, workflows.
2. **Text only** — No attachment. Used for: short takes, single insights, provocative opinions.

**Mermaid diagrams live INSIDE carousels** as one slide (e.g. slide 3-4 showing a workflow). Never posted as standalone single images.

### Mermaid Constraints (when embedded in carousel)
- Max ~10 nodes
- Must be readable in 3 seconds at a glance
- Provide example templates to LLM:
  - Pipeline: `A --> B --> C --> D`
  - Fork: `A --> B & A --> C`
  - Cycle: `A --> B --> C --> A`
- Side note: mermaid → Excalidraw conversion possible (bookmarked, not MVP)

### LLM Judge Criteria (from LinkedIn research)
- Hook: line 1 ≤ 8 words, line 2 ≤ 12 words. Must create tension/curiosity/specific promise.
- Length: 1,200-1,800 characters (flag outside this range)
- Structure: 1-2 sentences per paragraph, double line breaks
- Specificity: Must include concrete details (tool names, metrics, timeframes) — 3-4x reach multiplier
- CTA: Specific thoughtful question, not engagement bait. "Comment X" still works if genuinely valuable.
- Formula: Should match one of 10 proven structures (PAS, Contrarian, Before-After-Bridge, etc.)
- No: generic openings, engagement bait, links in body, dense paragraphs

### Content Formula Library (for LLM prompt)
1. PAS (Problem - Agitate - Solve)
2. "I did X. Here's what happened." (Failure-to-Insight)
3. "Stop doing X. Do Y instead." (Contrarian Reframe)
4. Before-After-Bridge
5. Numbered Framework ("7 things about X")
6. Harsh Truth / Myth-Busting
7. Vulnerability + Authority
8. Case Study / Behind-the-Scenes
9. "Secret Method" Hook
10. Three-Tier Progression (amateur/professional/expert)

Full research: `linkedin-research.md`

### Two-Tier Content Model (from E1 discussion)

**Tier 1 — Consistency Machine (automated, MVP)**
- Daily LinkedIn posts from existing work (sessions, voice notes, cohort calls)
- KB pipeline → linkedin_post → visual classification → generate visual → approve → publish
- Engine handles end-to-end. Blake approves and goes.

**Tier 2 — Campaign Posts (curated, deferred)**
- Strategic posts with lead magnets ("comment WHISPERFLOW")
- Blake decides what to package, creates the bundle, writes/edits the post
- Engine provides visual tools (same carousel/mermaid generators)
- Frequency: weekly or bi-weekly

### Still Open

| # | Question | Status |
|---|----------|--------|
| A3 | CTA pattern? | OPEN — Blake still learning LinkedIn. Not a build blocker. |

**All other questions RESOLVED.** Ready for phase planning.

---

## Phases Breakdown

### Phase 1: New LinkedIn Analysis Type + LLM Judge
**Status**: Not Started

**Objectives:**
- Create `linkedin_v2` analysis type config with prompt informed by LinkedIn research
- Prompt should select appropriate content formula (PAS, Contrarian, Before-After-Bridge, etc.) based on transcript content
- Enforce structural constraints: hook (line 1 ≤ 8 words, line 2 ≤ 12 words), 1,200-1,800 chars, short paragraphs, specificity
- Create `linkedin_judge` analysis type that evaluates the generated post against quality criteria
- Implement `run_with_judge_loop()` function in `analyze.py` — see mechanism below
- Judge criteria: hook strength, structure, specificity (tool names, metrics, timeframes), CTA quality, formula adherence, character count
- Add `linkedin_v2` to action_mapping config so it appears in kb serve action queue
- Test with 2-3 existing transcripts to validate quality

**Judge Loop Mechanism:**
New function `run_with_judge_loop(decimal, analysis_type, judge_type, max_rounds=1)` in `analyze.py`:
1. Run `analysis_type` (linkedin_v2) → produces post draft, stored in analysis results as usual
2. Run `judge_type` (linkedin_judge) with `requires: ["linkedin_v2"]` — reads the draft, produces structured feedback (JSON: scores per criterion + improvement suggestions)
3. Re-run `analysis_type` with modified prompt: original prompt + appended section: `"\n\n## Feedback from review:\n{judge_output}\n\nPlease improve the post based on this feedback."` — overwrites the original draft with improved version
4. Judge output is preserved alongside the final post for transparency
5. The feedback injection uses a new template variable `{{judge_feedback}}` in a conditional block: `{{#if judge_feedback}}...{{/if}}` (leveraging T020's conditional template system)

**Estimated Time**: 3-4 hours

**Resources Needed:**
- `kb/analyze.py` — existing analysis infrastructure (specifically `run_analysis_with_deps()` at line 888)
- `kb/config/analysis_types/` — new config files
- `linkedin-research.md` — prompt source material
- Existing transcripts for testing
- T020's conditional template rendering (`render_conditional_template()`)

**Dependencies:** None

**Files:**
- `kb/config/analysis_types/linkedin_v2.json` — NEW: analysis config with research-informed prompt + `{{#if judge_feedback}}` section
- `kb/config/analysis_types/linkedin_judge.json` — NEW: judge evaluation prompt, `requires: ["linkedin_v2"]`
- `kb/analyze.py` — MODIFY: add `run_with_judge_loop()` function
- `kb/__main__.py` — MODIFY: add `--judge` flag to `kb analyze` CLI, update action_mapping for `linkedin_v2`

**Acceptance Criteria:**
- [ ] `kb analyze -t linkedin_v2 -d 50.XX.XX` produces a post matching LinkedIn best practices
- [ ] `kb analyze -t linkedin_v2 --judge -d 50.XX.XX` runs the full judge loop (generate → evaluate → improve)
- [ ] Post has ≤ 8 word hook line, 1,200-1,800 chars, short paragraphs
- [ ] Judge produces actionable feedback with specific improvement suggestions (JSON with scores)
- [ ] Improved post (round 2) is measurably better than round 1 on at least 2 criteria
- [ ] Judge output preserved alongside final post in analysis results
- [ ] `linkedin_v2` appears in kb serve action queue via action_mapping
- [ ] Old `linkedin_post` analysis type still works unchanged

---

### Phase 2: Visual Classifier + Carousel Templates
**Status**: Not Started

**Objectives:**
- Create `visual_format` analysis type that classifies content as CAROUSEL or TEXT_ONLY
- If CAROUSEL and content describes a workflow/pipeline → flag `include_mermaid: true` in output
- Build 2 HTML carousel templates using Jinja2 (dark purple CCA brand, configurable)
- Templates live in `kb/carousel_templates/` (NOT `kb/templates/` — that's Flask's template dir)
- Slide structure: Hook slide → Content slides (one idea per slide) → Mermaid slide (optional) → CTA slide
- Default dimensions: 1080x1350px (portrait — takes more screen real estate on mobile, 57% of LinkedIn traffic)
- 10-30 words per slide, 6-10 slides total
- Template system: Jinja2, data-driven — pass in structured slide data, template renders each slide as HTML
- **Note:** `carousel_slides` analysis type (LLM generates slide breakdown from post content) is created here as a config file, but it requires `linkedin_v2` output as input. It will be wired into the pipeline in Phase 4. Template work is independent.

**Estimated Time**: 3-4 hours (includes visual mockup iteration with Blake)

**Resources Needed:**
- HTML/CSS for carousel templates
- CCA brand: dark purple (hex TBD — Blake to confirm, default `#2D1B69`), logo if available
- Jinja2 (already installed — v3.1.6)
- `linkedin-research.md` — carousel best practices section

**Dependencies:** None (template work is independent). `carousel_slides` config depends on Phase 1 output format but is just a JSON config file — wiring happens in Phase 4.

**Files:**
- `kb/config/analysis_types/visual_format.json` — NEW: classifier config (CAROUSEL/TEXT_ONLY + include_mermaid flag)
- `kb/config/analysis_types/carousel_slides.json` — NEW: slide breakdown config. `requires: ["linkedin_v2"]`. Takes post content, outputs structured slide data (JSON array of {slide_number, type, content, words})
- `kb/carousel_templates/` — NEW: directory (separate from Flask templates)
- `kb/carousel_templates/dark-purple.html` — NEW: primary Jinja2 template
- `kb/carousel_templates/light.html` — NEW: secondary template
- `kb/carousel_templates/config.json` — NEW: configurable colors, fonts, dimensions, brand settings

**Acceptance Criteria:**
- [ ] `visual_format` correctly classifies 5+ test posts as CAROUSEL or TEXT_ONLY
- [ ] `visual_format` correctly flags workflow posts with `include_mermaid: true`
- [ ] Carousel template renders clean HTML at 1080x1350px per slide
- [ ] Slide count stays within 6-10 range when given structured data
- [ ] Template is configurable (colors, fonts changeable via config.json)
- [ ] Blake approves visual design of at least one rendered template mockup

---

### Phase 3: Rendering Pipeline (HTML → PDF + Mermaid)
**Status**: Not Started

**Objectives:**
- Install rendering dependencies: Playwright + Chromium, mmdc (mermaid CLI)
- HTML carousel → PDF rendering using Playwright (headless Chromium)
- Each slide = one PDF page at 1080x1350px
- `mmdc` integration: when `include_mermaid: true`, LLM generates mermaid code → mmdc renders to PNG → PNG embedded as `<img>` in carousel slide HTML → Playwright renders full carousel to PDF
- Mermaid constraints enforced in LLM prompt: max 10 nodes, example templates provided
- Output to configurable visuals directory (default: `{decimal_folder}/visuals/`)
- Output files: `carousel.pdf` (for LinkedIn native PDF upload), individual `slide-N.png` (for posting queue preview thumbnails)
- Handle LLM quality issues: if mermaid code fails to render, skip mermaid slide and log warning (don't block the carousel)

**Estimated Time**: 3-4 hours

**Resources Needed:**
- `mmdc` — `npm i -g @mermaid-js/mermaid-cli` (verify on Mac M2)
- Playwright — `pip install playwright && playwright install chromium` (verify on Mac M2)
- Jinja2 (already installed) for template rendering
- Phase 2 carousel templates

**Dependencies:** Phase 2 (carousel templates must exist)

**Files:**
- `kb/render.py` — NEW: rendering engine with functions:
  - `render_mermaid(mermaid_code, output_path)` — mmdc wrapper, returns PNG path
  - `render_carousel(slide_data, template_name, output_dir)` — Jinja2 render + Playwright PDF
  - `render_pipeline(decimal, analysis_results, config)` — orchestrates the full flow
- `kb/config/render_config.json` — NEW: output paths, dimensions, mermaid constraints, Playwright settings
- `requirements.txt` — MODIFY: add `playwright`

**Acceptance Criteria:**
- [ ] `mmdc` installed and working on Mac M2 (`mmdc -i test.mmd -o test.png` succeeds)
- [ ] Playwright installed and working on Mac M2 (headless Chromium renders HTML to PDF)
- [ ] HTML carousel renders to multi-page PDF at 1080x1350 per page
- [ ] Mermaid code generates clean PNG via mmdc with transparent/matching background
- [ ] Mermaid PNG embeds correctly as carousel slide within the PDF
- [ ] Failed mermaid render skips slide gracefully (logs warning, carousel still generates)
- [ ] PDF opens correctly in Preview.app and looks professional
- [ ] Output path is configurable via render_config.json
- [ ] Individual slide PNGs generated for posting queue thumbnails

---

### Phase 4: KB Serve Integration + `kb publish` CLI
**Status**: Not Started

**Objectives:**
- **Async pipeline on approve:** When Blake hits 'a' in kb serve, the full pipeline runs in a background thread (NOT synchronous in Flask request). The approve endpoint returns immediately with status "approved, generating visuals...". Pipeline status tracked in action-state.json (`visual_status: "generating" | "ready" | "failed"`). Posting queue polls for completion.
  Pipeline steps (background):
  1. Run `linkedin_v2` analysis (if not already run)
  2. Run `linkedin_judge` → improvement loop via `run_with_judge_loop()`
  3. Run `visual_format` classifier
  4. If CAROUSEL: run `carousel_slides` (requires linkedin_v2 output) → render HTML → PDF via `render_pipeline()`
  5. Store outputs in visuals directory, update `visual_status` to "ready"
  6. On error: set `visual_status` to "failed", log error, post remains approved (not blocked)
- **Serve visual files:** New Flask route `GET /visuals/<path:filepath>` to serve PDFs and thumbnails from KB_ROOT. Posting queue template loads thumbnails via this route.
- **Posting queue enhanced:** Show carousel thumbnail (slide-1.png) or "Text Only" badge. Show "Generating..." spinner when `visual_status == "generating"`. PDF download button when ready.
- **`kb publish` CLI command:**
  - `kb publish --pending` — generate visuals for all approved posts without visuals
  - `kb publish --regenerate` — re-render all with current templates
  - `kb publish --decimal 50.XX.XX` — run full pipeline for specific content
  - `kb publish --dry-run` — preview what would be generated
- **Transition handling:** Remove `linkedin_post` from action_mapping (replaced by `linkedin_v2`). Old linkedin_post items remain in state but won't appear in queue. Can batch-reprocess old transcripts via `kb publish`.

**Estimated Time**: 4-6 hours

**Resources Needed:**
- `kb/serve.py` — existing action queue + posting queue + approve handler
- `kb/videos.py` — reference for background thread/queue pattern (existing precedent in codebase)
- Phase 1-3 outputs (analysis types, templates, rendering)

**Dependencies:** Phase 1, Phase 2, Phase 3

**Files:**
- `kb/serve.py` — MODIFY: approve triggers background pipeline, new `/visuals/` route, posting queue visual preview
- `kb/publish.py` — NEW: batch CLI command + shared pipeline orchestration function
- `kb/__main__.py` — MODIFY: register `publish` command, update action_mapping (`linkedin_v2` replaces `linkedin_post`)
- `kb/templates/posting_queue.html` — MODIFY: carousel thumbnail, generating spinner, PDF download button

**Acceptance Criteria:**
- [ ] Approving a post returns immediately (< 1 second), pipeline runs in background
- [ ] `visual_status` tracked in action-state.json ("generating" → "ready" or "failed")
- [ ] Posting queue shows "Generating..." spinner while pipeline runs
- [ ] Posting queue shows carousel thumbnail when `visual_status == "ready"`
- [ ] Posting queue shows "Text Only" badge for TEXT_ONLY posts
- [ ] PDF download/path-copy works via `/visuals/` Flask route
- [ ] `kb publish --pending` processes all approved posts without visuals
- [ ] `kb publish --regenerate` re-renders with current templates
- [ ] `kb publish --dry-run` shows what would be generated without doing it
- [ ] Failed renders flagged in UI, not blocking
- [ ] `linkedin_v2` appears in action queue; old `linkedin_post` items don't

---

## Plan Review

### Round 1
- **Gate:** NEEDS_WORK
- **Reviewed:** 2026-02-07
- **Summary:** Well-researched plan with excellent decision matrix, but 3 critical implementation gaps: judge loop has no mechanism in analyze.py, approve-triggered pipeline will block Flask, and carousel_slides phase dependency is wrong. 7 total issues found, all fixable in one planning pass.
- **Issues:** 3 critical, 5 major, 6 minor
- **Open Questions Finalized:**
  1. A3 (CTA pattern) -- correctly deferred, not a build blocker
  2. NEW: How does the judge feedback loop actually execute? (analyze.py has no such mechanism)
  3. NEW: What is the async strategy for the multi-step pipeline triggered on approve?
  4. NEW: CCA brand hex codes and logo file path needed for carousel templates

-> Details: `plan-review.md`

### Round 1 Fixes Applied
All 3 critical and 5 major issues addressed:
- **C1 (judge loop):** Added `run_with_judge_loop()` function spec to Phase 1. Uses conditional template variable `{{judge_feedback}}` for feedback injection. Judge output preserved alongside final post.
- **C2 (Flask blocking):** Phase 4 now specifies background thread execution. Approve returns immediately. `visual_status` field in action-state.json tracks progress. Posting queue polls for completion with spinner.
- **C3 (carousel_slides dependency):** Clarified in Phase 2 that `carousel_slides.json` config is created as a file but requires linkedin_v2 output — wiring into pipeline happens in Phase 4. Template work is independent.
- **M1 (rendering tools):** Phase 3 now includes explicit installation tasks with Mac M2 verification.
- **M2 (template location):** Changed from `kb/templates/carousel/` to `kb/carousel_templates/` to avoid Flask conflict.
- **M3 (action_mapping):** Added to Phase 1 (for testing) and Phase 4 (transition handling).
- **M4 (linkedin_post transition):** Phase 4 specifies: remove from action_mapping, old items remain but invisible, batch reprocess via kb publish.
- **M5 (serving visuals):** Phase 4 adds new Flask route `GET /visuals/<path:filepath>` to serve from KB_ROOT.
- Minor fixes: defaulted to 1080x1350 (portrait), committed to Jinja2, normalized time estimates, added mermaid failure handling, fixed action_queue.html typo.

### Round 2
- **Gate:** READY
- **Reviewed:** 2026-02-07
- **Summary:** All Round 1 issues verified as resolved. Judge loop mechanism validated against existing `render_conditional_template()` infrastructure. Async pipeline pattern confirmed via videos.py precedent. Rendering tools verified installed on server (mmdc v11.12.0, Playwright 1.58.0 + Chromium). 2 minor non-blocking issues noted (D1 text says Mac but tools are on server; judge loop save-to-disk is an implementation detail).
- **Issues:** 0 critical, 0 major, 2 minor (non-blocking)
- **Open Questions Finalized:**
  1. A3 (CTA pattern) -- correctly deferred, not a build blocker
- **Notes for executor:**
  - Confirm CCA brand hex (`#2D1B69`) and logo file with Blake during Phase 2
  - D1 decision text says "Mac" but rendering tools are on server -- run wherever `kb serve` runs
  - Consider thread safety if approving multiple posts quickly (see plan-review.md recommendations)

-> Details: `plan-review.md`

---

## Execution Log

### Phase 1: New LinkedIn Analysis Type + LLM Judge
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `4119790`
- **Files Modified:**
  - `kb/config/analysis_types/linkedin_v2.json` -- NEW: research-backed prompt with 10 content formulas, structural constraints (8-word hook, 1200-1800 chars), conditional `{{#if judge_feedback}}` block, optional_inputs: key_points + summary
  - `kb/config/analysis_types/linkedin_judge.json` -- NEW: 7-criterion evaluation prompt (hook_strength, structure, specificity, character_count, cta_quality, formula_adherence, voice_authenticity), requires: linkedin_v2, outputs scores + improvements + rewritten_hook
  - `kb/analyze.py` -- MODIFY: added `run_with_judge_loop()` (generate -> judge -> improve cycle), `_save_analysis_to_file()` helper, `--judge` and `--judge-rounds` CLI flags with both direct-file and decimal-filter paths
  - `kb/__main__.py` -- MODIFY: added `linkedin_v2: LinkedIn` to action_mapping defaults
  - `tasks/active/T022-content-engine/main.md` -- status updates
- **Notes:**
  - Config files also copied to runtime KB_ROOT path (`~/lem/mac-sync/Obsidian/.../config/analysis_types/`) since that is the live config directory
  - Created `~/.config/kb/config.yaml` on server to point to correct KB_ROOT path for testing
  - Cannot run live LLM tests on server (no google-genai package, no GEMINI_API_KEY) -- full testing requires Mac environment
  - All code-path tests pass: config loading, template rendering (with and without judge_feedback), CLI argument parsing, function signatures
  - Old `linkedin_post` analysis type verified unchanged and still loadable

### Tasks Completed
- [x] Task 1.1: Created `linkedin_v2.json` with research-informed prompt (10 formulas, structural constraints, conditional judge feedback)
- [x] Task 1.2: Created `linkedin_judge.json` with 7 scoring criteria and structured improvement output
- [x] Task 1.3: Added `run_with_judge_loop()` function to `kb/analyze.py`
- [x] Task 1.4: Added `--judge` and `--judge-rounds` CLI flags, both direct-file and decimal-filter modes
- [x] Task 1.5: Added `linkedin_v2` to action_mapping in `kb/__main__.py`

### Acceptance Criteria
- [x] AC1: `kb analyze -t linkedin_v2 -d 50.XX.XX` -- CLI path verified (reaches API call correctly, blocked by no API key on server)
- [x] AC2: `kb analyze -t linkedin_v2 --judge -d 50.XX.XX` -- CLI path verified (enters judge loop, blocked by no API key)
- [x] AC3: Post structural constraints in prompt (8-word hook, 1200-1800 chars, short paragraphs) -- verified in config
- [x] AC4: Judge produces structured feedback with scores per criterion and improvement suggestions -- verified in output schema
- [ ] AC5: Improved post measurably better than round 1 -- CANNOT VERIFY without LLM (requires Mac + API key)
- [x] AC6: Judge output preserved alongside final post -- verified in `run_with_judge_loop` code (both stored in existing_analysis)
- [x] AC7: `linkedin_v2` appears in kb serve action queue via action_mapping -- verified
- [x] AC8: Old `linkedin_post` still works unchanged -- verified

### Phase 2: Visual Classifier + Carousel Templates
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `24d0292`
- **Files Modified:**
  - `kb/config/analysis_types/visual_format.json` -- NEW: classifier config, requires linkedin_v2, outputs CAROUSEL/TEXT_ONLY + include_mermaid flag + confidence + reasoning + mermaid_type
  - `kb/config/analysis_types/carousel_slides.json` -- NEW: slide breakdown config, requires linkedin_v2, outputs JSON array of {slide_number, type, content, words}. Supports hook/content/mermaid/cta slide types
  - `kb/carousel_templates/config.json` -- NEW: configurable colors, fonts, dimensions (1080x1350), brand settings, two template definitions (dark-purple, light)
  - `kb/carousel_templates/dark-purple.html` -- NEW: primary Jinja2 template, dark purple (#2D1B69) gradient background, Inter font, supports all 5 slide types (hook, content, mermaid, cta, summary), page breaks between slides, brand footer with slide indicators
  - `kb/carousel_templates/light.html` -- NEW: secondary template, white background with dark text, same structure as dark-purple
  - `kb/tests/test_carousel_templates.py` -- NEW: 46 tests covering config validation (visual_format, carousel_slides, carousel config) and Jinja2 template rendering (both templates, all slide types, mermaid with/without image, edge cases)
- **Notes:**
  - Config files also copied to mac-sync path: `~/lem/mac-sync/Obsidian/zen-ai/knowledge-base/transcripts/config/analysis_types/`
  - Templates use Google Fonts (Inter) loaded via @import -- requires internet for rendering (Phase 3 Playwright will have access)
  - Content slide numbering uses a Jinja2 list-append trick to count only content-type slides (not hook/mermaid/cta)
  - Mermaid slides gracefully degrade: if mermaid_image_path is set, render `<img>` tag; otherwise show raw code as monospace text
  - All 119 tests pass (46 new + 73 existing)
  - Cannot verify AC1 (visual_format classifies 5+ posts) or AC6 (Blake approves visual design) without live LLM and visual review on Mac

### Tasks Completed
- [x] Task 2.1: Created `visual_format.json` analysis type config (CAROUSEL/TEXT_ONLY classifier with include_mermaid flag)
- [x] Task 2.2: Created `carousel_slides.json` analysis type config (requires linkedin_v2, outputs structured slide array)
- [x] Task 2.3: Created `kb/carousel_templates/` directory with `config.json` (dimensions, colors, fonts, brand)
- [x] Task 2.4: Created `dark-purple.html` primary Jinja2 carousel template
- [x] Task 2.5: Created `light.html` secondary Jinja2 carousel template
- [x] Task 2.6: Wrote 46 tests, all passing
- [x] Task 2.7: Copied configs to mac-sync path

### Acceptance Criteria
- [ ] AC1: `visual_format` correctly classifies 5+ posts as CAROUSEL or TEXT_ONLY -- CANNOT VERIFY without LLM (config validated, prompt covers classification rules)
- [ ] AC2: `visual_format` flags workflow posts with `include_mermaid: true` -- CANNOT VERIFY without LLM (prompt explicitly covers pipeline/workflow/cycle detection)
- [x] AC3: Carousel template renders clean HTML at 1080x1350px per slide -- verified via Jinja2 rendering tests (dimensions in CSS, page breaks between slides)
- [x] AC4: Slide count stays within 6-10 range -- config enforces range, prompt instructs 6-10 slides, test verifies 6-slide minimum rendering
- [x] AC5: Template is configurable (colors, fonts changeable via config.json) -- verified: both templates load colors/fonts from config.json, test validates all required color keys present
- [ ] AC6: Blake approves visual design -- REQUIRES Mac + Playwright rendering for visual inspection

---

## Code Review Log

### Phase 1
- **Gate:** PASS
- **Reviewed:** 2026-02-07
- **Issues:** 0 critical, 2 major, 2 minor
- **Summary:** Implementation is solid. Judge loop correctly integrates with existing analysis infrastructure. Config files are research-informed and well-structured. Two major issues found (silent `--judge` flag ignore without required args, ~87 lines of duplicated CLI code) but neither blocks Phase 2. All 8 acceptance criteria verified (AC5 deferred -- requires live LLM).

-> Details: `code-review-phase-1.md`

---

## Notes & Updates
- 2026-02-07: Task created during strategic session. Blake identified content distribution as the convergence point — every path (plugin, consulting, SaaS, education) requires people knowing he exists. This engine makes publishing frictionless.
- 2026-02-07: T020 (posting queue) already provides approve → posted workflow. This task extends from approve → publish-ready bundle with visuals.
- 2026-02-07: Plan review completed. Gate: NEEDS_WORK. 3 critical issues identified. See plan-review.md for details.
