# Code Review: Phase 2 -- Visual Classifier + Carousel Templates

## Gate: PASS

**Summary:** Solid implementation. All 6 files match the execution report. 46 tests pass. Config files follow existing codebase patterns. Templates are well-structured HTML/CSS that will render correctly at 1080x1350px. Found 1 major issue (summary slide type mismatch between template and schema) and 4 minor issues. Nothing blocks Phase 3.

---

## Git Reality Check

**Commits:**
```
f74649e Phase2: update execution log, set status CODE_REVIEW
24d0292 Phase2: visual classifier + carousel templates
```

**Files Changed (24d0292):**
```
kb/carousel_templates/config.json             |  64 ++++
kb/carousel_templates/dark-purple.html        | 287 +++++++++++++
kb/carousel_templates/light.html              | 292 +++++++++++++
kb/config/analysis_types/carousel_slides.json |  48 +++
kb/config/analysis_types/visual_format.json   |  39 ++
kb/tests/test_carousel_templates.py           | 510 +++++++++++++++++++
6 files changed, 1240 insertions(+)
```

**Files Changed (f74649e):**
```
tasks/active/T022-content-engine/main.md | 49 ++++
1 file changed, 49 insertions(+)
```

**Matches Execution Report:** Yes. All 6 claimed files present. Commit messages accurate.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: visual_format classifies 5+ posts | Deferred (no LLM) | N/A | Config validated -- prompt is comprehensive, schema correct. Cannot verify without LLM. Acceptable deferral. |
| AC2: visual_format flags workflow posts with include_mermaid | Deferred (no LLM) | N/A | Prompt explicitly covers pipeline/workflow/cycle/decision-tree detection. Schema has include_mermaid boolean + mermaid_type enum. |
| AC3: Template renders clean HTML at 1080x1350px | Claimed YES | YES | Verified: CSS sets `width: 1080px; height: 1350px` on html/body and .slide. Page breaks between slides. Jinja2 rendering produces valid HTML with correct dimensions. |
| AC4: Slide count 6-10 range | Claimed YES | YES | Config enforces `slide_range: {min: 6, max: 10}`. Prompt instructs 6-10. Test verifies 6-slide minimum rendering. Note: enforcement is prompt-based only, no hard validation in code -- acceptable since LLM output parsing happens in Phase 4. |
| AC5: Template configurable via config.json | Claimed YES | YES | Verified: both templates consume `colors`, `fonts`, `brand` from config.json. Test validates all required color keys present in both templates. |
| AC6: Blake approves visual design | Deferred (needs Mac) | N/A | Requires Playwright rendering + visual inspection. Not possible on server. |

---

## Issues Found

### Critical

None.

### Major

1. **Summary slide type exists in templates but NOT in carousel_slides schema**
   - File: `kb/config/analysis_types/carousel_slides.json:22` and `kb/carousel_templates/dark-purple.html:268`
   - Problem: Both HTML templates handle a `summary` slide type with dedicated CSS styling (`.slide-summary`). The test file even has a dedicated `TestTemplateSummarySlide` class. However, the `carousel_slides.json` output schema only defines `enum: ["hook", "content", "mermaid", "cta"]` -- the LLM will NEVER generate a `summary` slide because it is not in the schema. This means dead template code and a test that passes but tests something unreachable in production.
   - Fix: Either add `"summary"` to the `carousel_slides.json` enum and update the prompt to explain when to use it, OR remove the summary CSS and test class. Given that the plan mentions "Hook slide -> Content slides -> Mermaid slide (optional) -> CTA slide" with no summary, removing is probably correct. But if summary slides are desired, the schema must include them.

### Minor

1. **No Jinja2 autoescaping -- XSS in rendered HTML**
   - File: `kb/tests/test_carousel_templates.py:243` (Environment creation)
   - Problem: The Jinja2 Environment is created with default settings (autoescape=False). If slide content contains HTML tags (e.g., from LLM output), they render unescaped. Tested: `<script>alert(1)</script>` passes through raw.
   - Mitigation: This is low-severity because: (a) the HTML is rendered by Playwright headless, not served to users, (b) content comes from LLM output, not user input. However, the Phase 3 renderer should create the Environment with `autoescape=True` or use `|e` filter. Not a Phase 2 blocker.

2. **Google Fonts @import may fail in offline/headless rendering**
   - File: `kb/carousel_templates/dark-purple.html:7` and `kb/carousel_templates/light.html:7`
   - Problem: Both templates use `@import url('https://fonts.googleapis.com/css2?family=Inter:...')`. In Phase 3, Playwright will render these to PDF. If rendering happens offline or Google Fonts is slow, the font will fall back to system fonts. The fallback chain (`'Inter', 'Segoe UI', system-ui, sans-serif`) is good, but the result may look different than intended.
   - Fix: Phase 3 should either pre-download Inter font and load locally, or ensure Playwright has network access. Not a Phase 2 blocker.

3. **Duplicate transcript in LLM prompt (pre-existing pattern)**
   - File: `kb/config/analysis_types/visual_format.json:6` and `kb/config/analysis_types/carousel_slides.json:6`
   - Problem: Both prompts include `{{transcript}}` which gets substituted by `render_conditional_template()`. Then `analyze_transcript()` ALSO appends `TRANSCRIPT:\n{transcript_text}` at the end of every prompt (line 787). Result: transcript appears twice, wasting tokens. This is a pre-existing pattern (also in `linkedin_post.json`, `linkedin_v2.json`) but compounds here since `carousel_slides` primarily needs the post content, not the raw transcript at all.
   - Fix: Not a Phase 2 fix -- this is a systemic issue. Could be addressed by either removing `{{transcript}}` from prompts that already get it appended, or making the append conditional. Note for future.

4. **Test file reads config.json from disk in every single test method**
   - File: `kb/tests/test_carousel_templates.py` (throughout TestVisualFormatConfig, TestCarouselSlidesConfig, TestCarouselConfig)
   - Problem: Each test method independently opens and reads the JSON config file. In the config test classes alone, the same file is opened 7+ times. The template test classes use fixtures correctly, but the config classes do not.
   - Fix: Use a `@pytest.fixture` or class-level `setup_class` to load config once per class. Not blocking, just messy.

---

## What's Good

- **Config files are well-structured.** `visual_format.json` and `carousel_slides.json` follow the exact same schema pattern as existing analysis types. The `requires`, `prompt`, and `output_schema` fields are all correct and will work with the existing `run_analysis_with_deps()` function without modification.
- **Template HTML/CSS is professional quality.** Proper use of flexbox, absolute positioning for decorative elements, z-indexing for layered content. The content numbering Jinja2 trick (using list-append to count only content-type slides) is clever and works correctly -- verified with interleaved mermaid slides.
- **Two templates diverge intentionally.** The three differences between dark-purple and light (content-number opacity, summary title color, border-bottom) are appropriate stylistic variations, not copy-paste errors.
- **Graceful degradation for mermaid slides.** If `mermaid_image_path` is None or missing entirely, the template falls back to rendering raw mermaid code as monospace text. Tested both cases.
- **Correct page-break handling.** `page-break-after: always` between slides (not after last slide) is exactly what Playwright needs for multi-page PDF output.
- **46 tests with meaningful coverage.** Config validation, template rendering, all slide types, mermaid with/without image, minimal slide set, page breaks. Not just existence checks.

---

## Required Actions

None -- gate is PASS. The major issue (summary slide mismatch) should be addressed but is not blocking because:
1. Summary slides will never appear in production (LLM cannot generate them with current schema).
2. The dead template code is harmless -- it just never triggers.
3. The executor can clean this up in Phase 3 or 4 when wiring the pipeline.

Recommended cleanup (not required):
- [ ] Decide: add `summary` to carousel_slides schema, or remove from templates
- [ ] Phase 3 renderer: create Jinja2 Environment with `autoescape=True`
- [ ] Phase 3 renderer: handle Google Fonts offline fallback

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Template slide types and schema enums must stay in sync | Phase 4 pipeline wiring | Verify schema types match template handling at integration time |
| Duplicate transcript in prompt is a systemic pattern | All analysis types | Consider refactoring `analyze_transcript()` to skip appending transcript when prompt already substitutes it |
| Tests that only validate config structure tend to miss schema-template mismatches | Future test design | Add cross-validation tests (e.g., "all types in schema appear in template") |
