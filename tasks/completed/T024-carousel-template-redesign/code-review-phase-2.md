# Code Review: Phase 2

## Gate: PASS

**Summary:** Solid implementation. The markdown_to_html filter works correctly for the intended use case (LLM-generated content), the lstrip hack is gone, header.show_on_all_slides guard is properly applied to all 3 templates, tests are real and comprehensive (111 pass, 342 full suite). One major issue (no HTML escaping inside list items) is real but low-risk given the content source is LLM-generated, not user input. Hardcoded strings remain from Phase 1 (deferred to Phase 4). No critical issues block Phase 3.

---

## Git Reality Check

**Commits:**
- `2c493cc` T024 Phase2: content slide template + markdown parsing + timeline indicators (6 files, +440/-39)
- `a163572` T024: update execution log for Phase 2, set status CODE_REVIEW (1 file, +50)

**Files Changed:**
- `kb/render.py` -- added markdown_to_html(), registered filter
- `kb/carousel_templates/brand-purple.html` -- replaced lstrip with markdown_to_html, added .content p CSS
- `kb/carousel_templates/modern-editorial.html` -- same + header.show_on_all_slides guard
- `kb/carousel_templates/tech-minimal.html` -- same + header.show_on_all_slides guard
- `kb/config/analysis_types/carousel_slides.json` -- added CONTENT FORMATTING section to LLM prompt
- `kb/tests/test_carousel_templates.py` -- 111 tests (was 69), autoescape added to test env

**Matches Execution Report:** Yes. All 6 files match. Commit hashes match. No untracked code files.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Content slides render with timeline indicator showing position | Yes | Yes | brand-purple: numbered circles + connecting lines. modern-editorial: editorial big numbers (01/02) + pip bar. tech-minimal: breadcrumb path + colored bar segments. All verified in rendered HTML. |
| AC2: Timeline fills in as slides progress | Yes | Yes | active/filled/unfilled states present across all 3 templates. Tested with multi-content-slide data. |
| AC3: Bullet points render as actual bullets (not raw text) | Yes | Yes | `- ` lines parsed to `<ul><li>` by markdown_to_html. Raw `- ` prefix not in output. Verified via tests and manual check. |
| AC4: Numbered lists render with proper numbering | Yes | Yes | `1. ` lines parsed to `<ol><li>`. Raw number prefix stripped. Verified. |
| AC5: Free-form text has line breaks (not single block) | Yes | Yes | Plain text parsed to `<p>` with `<br>` between lines within same block. Empty lines separate blocks. |
| AC6: Header bar consistent across all slides | Yes | Yes | `header.show_on_all_slides` guard correctly added to content/mermaid/CTA on modern-editorial and tech-minimal. brand-purple already had it. Hook slide always shows header (no guard, correct). |
| AC7: Text is readable at 1080x1350 dimensions | Yes | Partial | Font sizes set (26-27px body, 44-50px titles). Visual verification deferred to Phase 4 (requires Playwright render). Reasonable for now. |

---

## Issues Found

### Critical
None.

### Major

1. **No HTML escaping of text content inside markdown_to_html**
   - File: `kb/render.py:259` (and similar lines for ol/p)
   - Problem: `markdown_to_html()` takes the text content from list items and inserts it directly into HTML without escaping. The function returns `Markup()`, which tells Jinja2 "this is safe HTML, do not escape." But the *text content within the list items* is never escaped. For example, `- <script>alert(1)</script>` renders as `<ul><li><script>alert(1)</script></li></ul>`. Similarly, `&` is not escaped to `&amp;`, and `<input>` tags pass through raw. While the content source is LLM-generated (trusted), not user input, this is still a correctness issue -- an LLM could easily output `&` or angle brackets in legitimate content like "Use Claude's Q&A feature" or "The <select> element."
   - Fix: Use `markupsafe.escape()` on each `item_text` before inserting into the HTML string. E.g., `current_items.append(escape(item_text))`. Import `escape` from `markupsafe`. This way the wrapper tags (`<ul>`, `<li>`, `<p>`) are safe HTML, but the text content within them is properly escaped.

2. **carousel_slides.json schema missing `title` and `subtitle` fields**
   - File: `kb/config/analysis_types/carousel_slides.json:14-33`
   - Problem: All 3 templates reference `slide.title` and `slide.subtitle` extensively (title pages, content slide headers, CTA subtexts), and the SAMPLE_SLIDES test data includes these fields. But the output schema in carousel_slides.json does not declare `title` or `subtitle` as properties, and the prompt does not instruct the LLM to output them. The LLM will only produce `slide_number`, `type`, `content`, and `words`. In production, `slide.title` will always be undefined/falsy, so content slides will render without their title headers, the timeline step labels will show "Step N" fallback text instead of meaningful labels, and CTA slides will have no subtitle. This is a schema/prompt gap, not a template bug.
   - Fix: Add `title` (optional string) and `subtitle` (optional string) to the slide item schema and add instructions in the prompt for when to use them. Alternatively, accept that titles come from a different source and document this clearly. This could be addressed in Phase 4 (Polish).

### Minor

1. **Hardcoded decorative strings in templates (carried from Phase 1)**
   - Files: `modern-editorial.html:401` ("A Step-by-Step Guide"), `modern-editorial.html:467` ("Key Points"), `modern-editorial.html:495` ("Architecture"), `tech-minimal.html:399` ("content-pipeline.md"), `tech-minimal.html:426` ("cat pipeline-guide.md"), `tech-minimal.html:530` ("// Architecture overview"), all 3 templates: "Follow for More" CTA button text
   - Note: Phase 1 review flagged this as Major and deferred to Phase 4. Still present. Confirming it remains on the Phase 4 cleanup list.

2. **Bold/italic markdown not supported**
   - File: `kb/render.py:206-275`
   - Problem: `markdown_to_html()` does not handle `**bold**` or `*italic*` markdown. If the LLM outputs `**Important**: Do this`, it will render as literal asterisks. The Phase 2 plan only specified bullets, numbered lists, and plain text, so this is not an AC miss -- but it is a natural expectation once you tell the LLM "use markdown."
   - Note: Low priority. The prompt says "Use markdown in the content string" but only specifies `- ` and `1. ` syntax, so the LLM is unlikely to use bold/italic. Monitor in production.

3. **Hardcoded rgba values in brand-purple.html CSS**
   - File: `kb/carousel_templates/brand-purple.html:76,84,168,228`
   - Problem: Several CSS rules use hardcoded `rgba(139,92,246,...)` instead of config color variables. E.g., `.tl-dot.filled { background: rgba(139,92,246,0.4); }` and `.tl-dot.active { box-shadow: 0 0 20px rgba(139,92,246,0.5); }`. Phase 1 review flagged this. Still present.
   - Note: Deferred to Phase 4 (Polish). Not introduced by Phase 2.

4. **tech-minimal step-bar has hardcoded box-shadow color**
   - File: `kb/carousel_templates/tech-minimal.html:108`
   - Problem: `.step-bar-segment.active { box-shadow: 0 0 8px rgba(88,166,255,0.3); }` is hardcoded rather than using a config color variable.
   - Note: Minor, deferred to Phase 4.

---

## What's Good

- The `markdown_to_html()` function is well-structured with a clean state machine (flush pattern) that correctly groups adjacent lines of the same type. Edge cases like empty input, whitespace-only input, None input, and lines that look like but are not list items ("42 is the answer", "-no space") are all handled correctly.
- The lstrip hack from Phase 1 is completely removed from all 3 templates. Content now goes through a proper parsing pipeline.
- The `header.show_on_all_slides` guard placement is correct in all 3 templates: hook slide always shows header, content/mermaid/CTA slides respect the config flag. For tech-minimal, the guard correctly wraps both the terminal-bar and the header together.
- Test environment now uses `autoescape=select_autoescape(["html"])` matching production, with the markdown_to_html filter registered. This was a Phase 1 review finding, now fixed.
- The CONTENT FORMATTING section in the LLM prompt is clear and specific about the exact syntax to use.
- 42 new tests are real, not placeholders. The `TestAllTemplatesContentTypes` class uses pytest parametrize to test all 3 templates with the same content type scenarios -- good coverage pattern.
- 342 tests pass across the full suite. No regressions.

---

## Phase 4 Backlog (Accumulated)

Items deferred from Phase 1 and Phase 2 reviews for Phase 4 (Polish):
- [ ] Hardcoded decorative strings in templates (Phase 1 M1)
- [ ] Hardcoded rgba color values in CSS (Phase 1 M2)
- [ ] HTML escaping in markdown_to_html item text (Phase 2 M1)
- [ ] Schema/prompt gap for title and subtitle fields (Phase 2 M2)
- [ ] Bold/italic markdown support consideration (Phase 2 minor)

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| When returning Markup (safe HTML), always escape the text content within the wrapper tags | Any Jinja2 filter that constructs HTML | Add to template dev guidelines |
| Schema and prompt must match template expectations -- if templates use `slide.title`, the schema/prompt must produce it | carousel_slides.json, template development | Verify schema-template alignment in future phases |
| Test env must mirror production env settings (autoescape, filters) | All template tests | Already fixed in this phase |
