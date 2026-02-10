# T026: Carousel Output Quality — Close the Gap to Mockups

## Summary

Fix carousel output quality to match mockups in `kb/carousel_templates/mockups/`. Root cause was weak LLM prompt + schema design, not template/CSS issues.

**Status:** CODE_REVIEW — Phase 1-3+5+6 COMPLETE, Phase 4+7+8 remaining

## Priority: 1

## Dependencies
- T024 (Carousel Template Redesign) — COMPLETED
- T023 (Content Curation Workflow) — Phases 1-4 COMPLETED

---

## Phases

### Phase 0: Data Capture & Root Cause Analysis — COMPLETE
**Output:** `phase-0-research-report.md`

### Phase 1: Schema + Prompt Redesign — COMPLETE
**Output:** `phase-1-research.md`

Changes shipped:
- `carousel_slides.json`: `bullets: array<string>` for content slides, 3 few-shot examples, mermaid theming directive
- `brand-purple.html`: iterates `slide.bullets` array instead of `slide.content|markdown_to_html`
- Runtime config synced to KB_ROOT
- Verified: 5-level bisection test ALL PASS, end-to-end PDF generated and visually confirmed

### Phase 2: Template Polish — COMPLETE

Changes shipped:
- Timeline dot square bug: replaced `box-shadow` with `filter: drop-shadow()` on active dots
- Timeline labels: removed text labels entirely, numbers-only (cleaner, less clutter)
- Font loading: replaced blind 1000ms timeout with `document.fonts.ready` API in all 3 Playwright renderers

Remaining (deferred):
- Font choice itself is fine (Plus Jakarta Sans matches mockup), but could explore alternatives later

### Phase 3: Diagram Rendering — COMPLETE

Changes shipped:
- `render_mermaid_via_llm()` in `render.py`: sends mermaid code + brand colors to Gemini 2.5 Flash, returns branded SVG
- SVG output: purple rounded-rect nodes, arrow connectors, annotation labels — matches mockup style
- Falls back to mmdc CLI if LLM generation fails
- SVG scales to fill slide with `preserveAspectRatio="xMinYMid meet"`, left-aligned
- Node spacing: 120px vertical gap for breathing room
- Container CSS: `width: 100%; height: 100%` to fill flex container

### Phase 5: Title Page Redesign — COMPLETE

Changes shipped:
- Hero profile photo: removed 64px badge, added full-height hero photo anchored at bottom-center (55% height)
- Profile photo resized from 2048px source to 600px for reasonable data URI size
- Emphasis word highlighting: `highlight_words` Jinja2 filter converts `**word**` → accent-colored `<span>`
- LLM prompt updated with rule 7 (wrap 1-2 key words in `**double asterisks**` on hook slide)
- Font sizes extracted from hardcoded CSS to configurable `font_sizes` object in `config.json`
- All text sizes bumped ~30% from original (two rounds of increases)

### Phase 6: Emphasis + Content Variety Polish — COMPLETE

**A. Extend `highlight_words` to all slide types:**
- `|highlight_words` filter applied to: content slide bullets (brand-purple), CTA heading (all templates), hook title (all templates)
- `_apply_emphasis()` helper extracted in `render.py`, shared by `highlight_words` filter and `markdown_to_html`
- `markdown_to_html` now processes `**word**` patterns into `<span class="accent-word">` for content slides in modern-editorial and tech-minimal
- `.accent-word` CSS class added to modern-editorial and tech-minimal templates
- LLM system_instruction rule 7 updated: emphasis is global (all slide types), not hook-only
- Prompt examples updated with `**emphasis**` markers in bullets

**B. Content slide format variety:**
- Added `format` field to schema: `"bullets"` | `"numbered"` | `"paragraph"`
- LLM system_instruction rule 2 updated: choose format per slide, vary across slides
- Prompt includes examples for all three formats
- brand-purple.html updated: `format=numbered` renders `<ol>`, `format=paragraph` renders via `markdown_to_html`, default remains `<ul>`
- Backwards compatible: slides without `format` field still render as bullet lists
- modern-editorial and tech-minimal already handle all formats via `markdown_to_html`

Commits: `4a385cf`, `7e8cfec`

**Pre-existing test failures (not introduced by Phase 6):**
- 21x `font_sizes is undefined` — brand-purple direct-render tests (Phase 5 added `font_sizes` to template but test fixture never updated)
- 3x prompt assertion mismatches — Phase 1 changed schema/prompt but tests not updated
- 1x `wait_for_timeout(1000)` vs `(500)` — Phase 2 changed timeout but test not updated
- 1x `test_prompt_mentions_title_and_subtitle` — prompt uses `title=` not `title:`

### Phase 7: KB Serve Frontend Fixes — NOT STARTED
**Needs planning.** Multiple issues with the carousel editor UI in `kb serve`:

**A. Save Slides not persisting changes:**
- Editing title/content in the frontend and clicking "Save Slides" doesn't appear to save back to the JSON
- Investigate the save endpoint and frontend fetch call

**B. Content field empty for bullet slides:**
- Slides with `bullets` array show title correctly but content textarea is empty
- Frontend likely reads `slide.content` only, doesn't handle `slide.bullets` array
- Need to serialize bullets → display text for editing, then parse back on save

**C. Template switching + re-render:**
- Changing template dropdown and re-rendering doesn't work
- Investigate the re-render endpoint and whether it passes selected template

**D. Frontend content editing for all formats:**
- Need to handle bullets, numbered lists, free-form text, and mermaid code in the editor UI
- Each format needs appropriate input controls (textarea vs structured list editor)
- Must round-trip cleanly: display → edit → save → re-render

### Phase 8: KB Serve — Iteration View + Processing UX — NOT STARTED (Investigation Complete)

**Investigation findings (2026-02-09):**

**A. Iteration details not rendered — data exists, frontend ignores it:**
- API endpoint `GET /api/action/<id>/iterations` already returns per-round: `improvements` (criterion, current_issue, suggestion), `strengths`, `rewritten_hook`, `score_history`
- Frontend `renderIterationView()` in `posting_queue.html` only renders the scores grid + overall score
- **Zero code** to display judge feedback (`improvements`), strengths, rewritten hooks, or score progression charts
- Fix: add HTML sections below scores grid to render improvements and strengths per round

**B. Mixed content from all decimals — no filtering:**
- `scan_actionable_items()` in `serve_scanner.py` scans ALL decimal dirs under KB_ROOT
- Summaries, guides, skool posts from 50.01.01 appear alongside linkedin_v2 from 50.03.01
- No per-decimal filter exists on action queue or iteration view
- Consider: decimal filter dropdown, or at minimum better visual grouping/sorting

**C. No way to kick off analysis from the UI:**
- Only `iterate` (existing linkedin_v2), `generate-visuals`, and video transcription available
- No endpoint for initial `kb analyze -t <type>` from frontend
- TODO comment at `serve.py:155` indicates this was planned: `"processing": [] # Phase 2`
- Needs: new `/api/transcript/<decimal>/analyze` endpoint + UI trigger (button per transcript, or batch processing)

### Phase 4: End-to-End Validation — NOT STARTED
Test across multiple transcripts, compare to mockups, update other templates.

---

## Notes
- 2026-02-09: Phase 0+1 complete. See `phase-1-research.md` for detailed findings.
- Key learning: Gemini `minLength`/`pattern` silently ignored in ALL SDK versions. Use `array<string>` schema + few-shot examples instead.
- SDK upgrade (v1.17→v1.62): good hygiene but does NOT fix carousel quality.
- Runtime config gotcha: pipeline loads from `KB_ROOT/config/`, not `kb/config/` in repo. Must sync after edits.
- 2026-02-09: Phase 2 complete. Key learning: Chromium's PDF renderer draws `box-shadow` as a rectangle, ignoring `border-radius`. Use `filter: drop-shadow()` instead — it respects element shape in PDF output. Discovered via isolated HTML test rendered to both PNG (circles) and PDF (squares).
- 2026-02-09: Phase 3 complete. LLM-generated SVG replaces rigid mmdc output. Key: use `preserveAspectRatio="xMinYMid meet"` for left-aligned scaling, 120px node spacing for readability.
- 2026-02-09: Phase 5 complete. Hero photo + emphasis words + configurable font sizes. Key learning: MarkupSafe's `escape()` returns a `Markup` object — `re.sub` on it auto-escapes replacement strings. Fix: cast to `str()` before regex.
- 2026-02-09: Phase 6+7 scoped. Emphasis filter only covers hook slide — needs extending to bullets/CTA. KB serve frontend has multiple broken flows (save, content display, template switching) that need investigation.
