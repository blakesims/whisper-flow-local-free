# T026: Carousel Output Quality — Close the Gap to Mockups

## Summary

Fix carousel output quality to match mockups in `kb/carousel_templates/mockups/`. Root cause was weak LLM prompt + schema design, not template/CSS issues.

**Status:** ACTIVE — Phase 1 COMPLETE, Phase 2-4 remaining

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

### Phase 2: Template Polish — NOT STARTED
Known issues from visual QA:
- Timeline dot highlight renders as square on steps 2-5 (step 1 correct) — CSS bug
- Font needs updating (currently generic, looks boring vs mockups)
- Timeline labels may be too cluttered with full titles — consider number-only or shorter labels

Config vs code:
- Fonts: configurable in `kb/carousel_templates/config.json` → `templates.brand-purple.fonts`
- Colors: configurable in config.json → `templates.brand-purple.colors`
- Timeline layout/highlight: hardcoded in `brand-purple.html` CSS — needs code fix

### Phase 3: Diagram Rendering — NOT STARTED
Replace mmdc mermaid rendering with LLM-generated HTML/SVG diagrams matching brand style. The mockups use hand-crafted SVG, not mermaid. mmdc output looks rigid and doesn't match the brand.

### Phase 4: End-to-End Validation — NOT STARTED
Test across multiple transcripts, compare to mockups, update other templates.

---

## Notes
- 2026-02-09: Phase 0+1 complete. See `phase-1-research.md` for detailed findings.
- Key learning: Gemini `minLength`/`pattern` silently ignored in ALL SDK versions. Use `array<string>` schema + few-shot examples instead.
- SDK upgrade (v1.17→v1.62): good hygiene but does NOT fix carousel quality.
- Runtime config gotcha: pipeline loads from `KB_ROOT/config/`, not `kb/config/` in repo. Must sync after edits.
