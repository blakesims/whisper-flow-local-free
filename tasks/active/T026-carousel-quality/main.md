# T026: Carousel Output Quality — Close the Gap to Mockups

## Summary

The carousel rendering pipeline (T022-T024) is functional end-to-end, but the actual output quality is far below the mockup designs. This task is dedicated to systematically identifying every gap between mockups and generated output, understanding root causes at each layer (LLM output, template rendering, PDF conversion), and fixing them.

**Status:** ACTIVE — Phase 0 (Data Capture) complete

## Priority: 1

## Dependencies
- T024 (Carousel Template Redesign) — COMPLETED
- T023 (Content Curation Workflow) — Phases 1-4 COMPLETED

## Problem Statement

The mockups in `kb/carousel_templates/mockups/` look professional and polished. The actual generated carousels look like first drafts: empty titles, prose instead of bullets, raw backticks, mermaid diagrams with wrong styling, massive empty space. The gap is not subtle — it's immediately obvious.

---

## Phases Breakdown

### Phase 0: Data Capture & Root Cause Analysis
**Status:** COMPLETE
**Output:** `phase-0-research-report.md` (in this directory)

Objectives:
- Capture the exact prompt, schema, and settings sent to Gemini
- Capture the raw JSON model output
- Compare generated HTML to mockup HTML line-by-line
- List every visual difference
- Identify root causes at each layer
- Produce a research report with findings and open questions

### Phase 1: LLM Output Quality
**Status:** Not Started

Objectives:
- Fix empty titles (Gemini ignores `required` in structured output)
- Fix content format (prose → bullet points with `- ` prefix)
- Fix timeline labels (generic "Step N" → descriptive from titles)
- Consider: post-processing validation + retry on malformed output
- Consider: stronger prompt engineering vs. code-level enforcement

Research needed:
- Gemini structured output enforcement limitations (what actually works?)
- Alternative approaches: few-shot examples in prompt, validation + retry loop
- Whether `response_schema` vs `response_json_schema` matters for enforcement

### Phase 2: Template Rendering Fixes
**Status:** Not Started

Objectives:
- Handle inline code (backticks → styled `<code>` elements)
- Handle `•` bullet character as well as `- ` prefix
- Handle `*italic*` markdown in content
- Ensure `.slide-title` and `.slide-subtitle-line` render when title exists
- Timeline labels should use slide titles, not just "Step N"

### Phase 3: Mermaid → Custom SVG
**Status:** Not Started

Objectives:
- Replace mmdc-generated mermaid SVGs with brand-matched custom SVGs
- The mockup uses hand-crafted SVG with brand colors (#8B5CF6, #A78BFA)
- mmdc output uses dark theme with wrong colors and tiny 70px height
- Options: custom mermaid theme, post-process SVG, or generate SVG directly

### Phase 4: Polish & Validation
**Status:** Not Started

Objectives:
- End-to-end validation: generate → render → open → visual QA
- Post-processing pipeline: validate JSON, retry on empty titles, enforce bullet format
- Test across multiple transcripts
- Compare final output against mockups

---

## Notes & Updates
- 2026-02-09: Task created after smoke testing revealed carousel quality issues
- 2026-02-09: Phase 0 complete — research report written with full data capture
- Bug found during testing: `response_json_schema` → `response_schema` (wrong parameter name in analyze.py, fixed)
