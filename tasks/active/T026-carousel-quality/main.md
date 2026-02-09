# T026: Carousel Output Quality — Close the Gap to Mockups

## Summary

Fix carousel output quality to match mockups in `kb/carousel_templates/mockups/`. Root cause was weak LLM prompt + schema design, not template/CSS issues.

**Status:** ACTIVE — Phase 1-3 COMPLETE, Phase 4 remaining

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
