# Plan Review Round 2: T024 Carousel Template Redesign

## Gate Decision: READY

**Summary:** All 7 Round 1 issues (3 critical, 4 major) have been addressed adequately. The plan is now executable. Round 2 found 0 critical issues, 2 major issues (both easily resolved during execution), and 3 minor notes. The remaining issues are implementation-level details that the executor can handle with the guidance below -- they do not require replanning.

---

## Round 1 Fix Verification

### C1: Jinja2 autoescape breaks inline SVG -- RESOLVED
Decision D8 specifies `Markup()` wrapping for trusted mmdc SVG output. Phase 3 objectives explicitly call this out. The approach is correct -- `Markup()` marks the string as safe before it reaches Jinja2, avoiding the `|safe` filter's template-level XSS surface.

### C2: No schema for structured content -- RESOLVED
Decision D7 specifies markdown-in-string approach. Phase 2 explicitly describes parsing `- ` as bullets, `1. ` as numbered list, and `\n` as line breaks. A Jinja2 custom filter or macro is specified. No schema change needed -- the `content` field stays a string. This is the simpler, better approach.

### C3: render_pipeline hardcodes PNG MIME type -- RESOLVED
Phase 3 file list now explicitly includes `render.py` with three specific changes: (1) `render_mermaid()` outputs SVG instead of PNG, (2) `render_pipeline()` passes SVG as `Markup()` to template instead of base64 data URI, (3) fix hardcoded `data:image/png` MIME type. The entire mermaid data flow change is documented.

### M1: Profile photo contradiction Phase 1 vs Phase 4 -- RESOLVED
D10 consolidates all profile photo work in Phase 1. Phase 4 no longer mentions profile photo integration, only polish/QA. Clean separation.

### M2: Config schema unspecified -- RESOLVED
Phase 1 now includes a concrete JSON schema block showing `brand.author_name`, `brand.community_name`, `brand.profile_photo_path`, and `header` settings with specific fields (`show_on_all_slides`, `author_position`, `community_position`). Executor has enough to implement.

### M3: No mockup-to-Jinja2 guidance -- RESOLVED
Phase 1 now includes explicit conversion steps: "extract hardcoded text into `{{ variables }}`, move colors/fonts into config.json, replace static content with `{% for slide in slides %}` loops, add conditional blocks for optional elements." This sets the right expectation that the conversion IS the work.

### M4: Dead summary slide type -- RESOLVED
Phase 4 explicitly includes "Remove dead `summary` slide type from templates (not in carousel_slides.json enum)." Paired with the existing `TestTemplateSummarySlide` test class that will need removal.

---

## New Issues Found (Round 2)

### Critical (Must Fix)
None.

### Major (Should Fix)

1. **`brand.author_name` vs existing `brand.name` conflict** -- The proposed config schema adds `brand.author_name` and `brand.community_name`, but the current `config.json` already has `brand.name` (value: "Blake Sims"), `brand.tagline`, `brand.handle`, and `brand.primary_color`. The current templates use `{{ brand.name }}` in the footer and CTA slide. The plan does not specify whether `author_name` replaces `name` or coexists alongside it.

   Impact: If the executor adds `author_name` without updating `brand.name` references, existing template logic still works but the new header bar would reference a field that doesn't exist yet. If they rename `name` to `author_name`, the existing CTA slide `{{ brand.name }}` breaks until updated.

   Recommendation: Treat `author_name` as a rename of `brand.name` during the Phase 1 config migration. Add `community_name` as new. Update all template references from `brand.name` to `brand.author_name`. The executor can handle this without replanning -- just note it as a Phase 1 implementation detail.

2. **LLM prompt does not produce markdown-formatted content** -- D7 says the LLM outputs markdown (`- item` for bullets, `1. item` for numbered). The Phase 2 Jinja2 filter parses these prefixes to render structured content. But the current `carousel_slides.json` prompt only says "Use short sentences or bullet fragments, not paragraphs." It does not instruct the LLM to use markdown syntax. The LLM may or may not produce `- ` prefixed lines -- it is not deterministic.

   Impact: If the LLM outputs "Step 1: Voice note transcription" instead of "- Step 1: Voice note transcription", the markdown parser will not detect it as a bullet and will render it as plain text -- defeating the purpose of D7.

   Recommendation: Phase 2 should include a minor update to the `carousel_slides.json` prompt to tell the LLM to use markdown formatting in content fields. Add to the prompt something like: "Format content using markdown: use `- ` prefix for bullet points, `1. ` for numbered lists." This is a one-line change and does not require replanning.

### Minor

1. **Template variable rename: `mermaid_image_path` to `mermaid_svg`** -- Phase 3 mentions the template should render `{{ slide.mermaid_svg }}` but the current template checks `{% if slide.mermaid_image_path %}` and uses `<img class="mermaid-img" src="{{ slide.mermaid_image_path }}">`. The structural change from `<img>` to inline SVG element is significant. The executor should know this is a coordinated change across `render_pipeline()` (which currently sets `slide["mermaid_image_path"]`) and the template. Phase 3 file list does cover both files, so this is just an implementation note, not a gap.

2. **Profile photo uses base64, mermaid uses inline SVG -- different patterns** -- Phase 1 says profile photo is "converted to base64 data URI in Python before passing to template (same pattern as mermaid in Phase 3)." But Phase 3 actually removes the base64 pattern and switches to inline SVG via `Markup()`. These are different embedding strategies: profile photo = binary image = base64 data URI in `<img src="data:image/png;base64,...">`, mermaid = XML/SVG = inline `<svg>` via `Markup()`. The "(same pattern as mermaid in Phase 3)" note in Phase 1 is misleading but the actual approach described (base64 data URI) is correct for a binary image.

3. **Existing test breakage scope** -- Several existing tests will break during execution: `TestTemplateSummarySlide` (Phase 4 removes summary), `test_pipeline_embeds_mermaid_path_in_slide` which asserts `mermaid_slide["mermaid_image_path"]` (Phase 3 changes to `mermaid_svg`), `test_mermaid_with_image_path` which checks `<img>` tag presence (Phase 3 switches to inline SVG). The plan says "MODIFY: tests" for each phase, which is sufficient direction -- the executor will encounter these naturally. Not a planning gap, just an observation.

---

## Open Questions Status

All open questions from Round 1 have been resolved:
- Q1 (profile photo placement): Deferred to Phase 0 mockups -- correct, visual decision.
- Q3 (color palette): Deferred to Phase 0 mockups -- correct, visual decision.
- Q2, Q4: Folded into Phase 0 scope -- correct.
- Q5 (profile.png timing): Resolved as D9 -- stored at `kb/carousel_templates/profile.png`, Phase 0 uses placeholder.
- Q6 (structured content schema): Resolved as D7 -- markdown in string.

No new questions requiring human input.

---

## Plan Strengths

- The mockup-first approach (Phase 0) remains the strongest aspect -- it directly addresses the "boring layout" problem that prompted this task.
- Phase ordering is logical with clear dependencies: mockup -> title page -> content slides -> mermaid SVG -> polish.
- Decision matrix is now comprehensive (D1-D10) with clear rationale for each.
- The markdown-in-string approach (D7) is pragmatic -- avoids schema changes, keeps the LLM interface simple.
- The `Markup()` approach (D8) is the right choice for trusted SVG -- cleaner than base64 data URI for SVG content.
- Config schema is now concrete and implementable.
- Phase 3 render.py changes are now fully specified with the three-part modification list.

---

## Recommendations

### For Executor (implementation notes, not plan changes)
- Phase 1: Treat `brand.author_name` as a rename of existing `brand.name`. Update template references accordingly. Add `community_name` and `profile_photo_path` as new fields.
- Phase 2: Add a brief markdown formatting instruction to the `carousel_slides.json` prompt so the LLM reliably outputs `- ` and `1. ` prefixes.
- Phase 3: Coordinate the `mermaid_image_path` -> `mermaid_svg` rename across `render_pipeline()`, the template, and the test file in a single commit.
- Phase 4: Remove `TestTemplateSummarySlide` test class when removing summary slide type.

### Consider Later
- Multiple mermaid slides: current code overwrites `mermaid.png` for each mermaid slide. Phase 3 switches to SVG strings (not files), which naturally fixes this since each slide gets its own `mermaid_svg` value.
- Font bundling for offline mockup review (Phase 0) -- low risk, Google Fonts will likely work.
