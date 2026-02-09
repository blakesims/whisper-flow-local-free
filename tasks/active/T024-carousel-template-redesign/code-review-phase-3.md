# Code Review: Phase 3

## Gate: PASS

**Summary:** Clean, focused implementation. SVG rendering replaces PNG correctly, Markup() wrapping is appropriate for trusted mmdc output, HTML escaping added to markdown_to_html(), title/subtitle fields added to schema. Both Phase 2 review issues (M1: escaping, M2: schema fields) addressed. 370 tests pass across full suite. No critical or major issues. 4 minor issues found, all deferrable to Phase 4.

---

## Git Reality Check

**Commit:** `4d11c21` — Phase3: Mermaid SVG + rendering quality + Phase 2 review fixes

**Files Changed (8):**
- `kb/render.py`
- `kb/carousel_templates/brand-purple.html`
- `kb/carousel_templates/modern-editorial.html`
- `kb/carousel_templates/tech-minimal.html`
- `kb/config/analysis_types/carousel_slides.json`
- `kb/tests/test_render.py`
- `kb/tests/test_carousel_templates.py`
- `kb/tests/test_serve_integration.py`

**Matches Execution Report:** Yes. All 8 files match exactly. No uncommitted changes related to this phase.

**Old references cleaned up:**
- `mermaid_image_path` only remains in archived templates (`_archive/dark-purple.html`, `_archive/light.html`) -- correct, those are archived.
- `mermaid_path` (old render_pipeline return key) fully removed from all active code.
- Callers in `publish.py` and `serve.py` never referenced `mermaid_path` or `mermaid_image_path` from the return dict, so the key rename is safe.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: mmdc generates SVG output (not PNG) | Yes | Yes | `output_file = output_dir / "mermaid.svg"` at render.py:99. Test `test_passes_correct_args_to_mmdc` verifies `.svg` extension in command args. |
| AC2: SVG embedded inline via Markup() | Yes | Yes | `slide["mermaid_svg"] = Markup(svg_content)` at render.py:609. Templates use `{{ slide.mermaid_svg }}` which renders unescaped due to Markup type. Test `test_mermaid_svg_all_templates` verifies across all 3 templates. |
| AC3: Crisp at 1080x1350 (no pixelation) | Yes | Deferred | SVG is resolution-independent by nature. Visual QA deferred to Phase 4 (requires actual mmdc + Playwright render). Reasonable. |
| AC4: Mermaid colors match template brand | Yes | Yes | Theme selection: "dark" for brand-purple/tech-minimal, "neutral" for modern-editorial (render.py:595-597). Hardcoded but correct for current templates. |
| AC5: Failed SVG render gracefully skips slide | Yes | Yes | When `render_mermaid()` returns None, error appended, slide falls through to `{% else %}` in template showing raw mermaid code. Tests verify: `test_pipeline_mermaid_failure_logs_warning`, `test_mermaid_failure_sets_no_svg`. |
| AC6: Non-mermaid slides unaffected | Yes | Yes | 370 tests pass. All Phase 1/2 template tests continue to pass. |
| AC7: No XSS risk | Yes | Yes | mmdc SVG is trusted source. `markdown_to_html()` now escapes via `markupsafe.escape()` on all text: list items (line 256, 263), plain text (line 273). Three test cases verify: `test_escapes_html_in_list_items`, `test_escapes_html_in_numbered_items`, `test_escapes_html_in_plain_text`. |

---

## Phase 2 Review Issues Addressed

| Issue | Status | Verification |
|-------|--------|-------------|
| M1: No HTML escaping in markdown_to_html() list items | Fixed | `escape()` applied at render.py:256, 263, 273. Three test cases confirm `<script>`, `<b>`, `<em>` tags are escaped to entities. |
| M2: carousel_slides.json missing title/subtitle fields | Fixed | Fields added at carousel_slides.json:33-40. Test `test_schema_has_title_and_subtitle_fields` confirms. |

---

## Issues Found

### Critical
None.

### Major
None.

### Minor

1. **m1: Mermaid theme selection is hardcoded, not config-driven**
   - File: `kb/render.py:595-597`
   - The theme mapping (`dark` for brand-purple/tech-minimal, `neutral` for modern-editorial) is a hardcoded if/else in `render_pipeline()`. If a new template is added, the developer must remember to update this logic. Could be a `mermaid_theme` field in each template's config.json entry.
   - Defer to Phase 4 (Polish).

2. **m2: LLM prompt does not mention title/subtitle fields**
   - File: `kb/config/analysis_types/carousel_slides.json:6` (prompt text)
   - The prompt tells the LLM "For each slide, specify: slide_number, type, content, words" but does not mention `title` or `subtitle`. The fields exist in the output_schema, which some LLM providers use for structured output, but the natural language prompt does not instruct the LLM to produce them. Templates handle the absence gracefully (`{% if slide.title %}`), so this is not a bug, but the LLM may inconsistently produce these fields.
   - Defer to Phase 4 (Polish) -- add `title` and `subtitle` to the prompt's "For each slide, specify:" list.

3. **m3: render_mermaid() always writes to same filename**
   - File: `kb/render.py:99`
   - `output_file = output_dir / "mermaid.svg"` means multiple mermaid slides in one carousel overwrite the same file. Not a bug because the SVG content is read into a string and assigned to the slide before the next call, but it is a code smell. The top-level `mermaid_svg` return value also only captures the last mermaid slide's content.
   - Acceptable: the LLM prompt limits carousels to ONE mermaid slide.

4. **m4: CSS removes object-fit:contain but SVG may need overflow control**
   - Files: `brand-purple.html:344`, `modern-editorial.html:363`, `tech-minimal.html:369`
   - `object-fit: contain` was removed (correct -- it is an `<img>` property, not applicable to inline `<svg>`). However, no `overflow: hidden` or `overflow: auto` was added to `.mermaid-container` or the `svg` selector. If mmdc produces an SVG with a viewBox larger than the container, it could overflow.
   - Low risk: `max-width: 860px; max-height: 800px` on the `svg` selector should constrain it. Visual QA in Phase 4 will catch any overflow issues.

---

## What's Good

- The SVG transition is clean and complete. Every reference to `mermaid_image_path`, `data:image/png;base64`, and `mermaid_path` has been properly replaced in active code.
- The HTML escaping fix is thorough -- applied to all three text paths (bullets, numbered lists, plain text) with matching test cases for each.
- Fallback behavior is preserved and well-tested: failed SVG renders show raw mermaid code.
- No callers of `render_pipeline()` in `publish.py` or `serve.py` referenced the old `mermaid_path` key, so the return dict change is backwards-compatible.
- Test coverage is strong: 187 tests across the 3 test files, 370 full suite, covering SVG rendering, Markup wrapping, escaping, schema fields, and cross-template verification.

---

## Required Actions (for REVISE)
N/A -- PASS.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| When changing return dict keys, verify all callers | Any API change | Grep for old key name across entire codebase before shipping |
| Hardcoded theme mappings become maintenance debt | Config-driven systems | Add mermaid_theme to template config in Phase 4 |
| Schema fields without prompt instructions may be ignored by LLM | LLM structured output | Always mirror schema fields in natural language prompt text |
