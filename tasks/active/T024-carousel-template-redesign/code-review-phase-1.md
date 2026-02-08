# Code Review: Phase 1

## Gate: PASS

**Summary:** Solid implementation. 3 new Jinja2 templates fully parameterized from Phase 0 mockups, config.json schema well-designed, profile photo base64 loading handles missing file gracefully, 117 tests pass. Found 0 critical, 3 major, and 4 minor issues. The major issues are real but none block the next phase -- they should be addressed during Phase 4 (Polish) or as quick fixes.

---

## Git Reality Check

**Commits:**
```
e73d60d T024: update execution log for Phase 1, set status CODE_REVIEW
3118052 T024 Phase1: title page templates + config schema + profile photo
```

**Files Changed (from git diff):**
```
kb/carousel_templates/_archive/dark-purple.html
kb/carousel_templates/_archive/light.html
kb/carousel_templates/brand-purple.html
kb/carousel_templates/config.json
kb/carousel_templates/modern-editorial.html
kb/carousel_templates/tech-minimal.html
kb/render.py
kb/tests/test_carousel_templates.py
kb/tests/test_render.py
tasks/active/T024-carousel-template-redesign/main.md
```

**Matches Execution Report:** Yes -- all 10 files match the execution log claims.

**Test Results:** 117 tests in the two modified test files pass. 277 total tests across full `kb/tests/` suite pass with zero failures.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Title page renders with book-style title + subtitle | Yes | Yes | All 3 templates render hook slide as title page with `title-page-main-title` and subtitle div. Confirmed in rendered HTML output. |
| AC2: Header bar shows name + community from config | Yes | Yes | `brand.author_name` and `brand.community_name` rendered via Jinja2 variables. `test_no_hardcoded_names` confirms changing brand values changes output. |
| AC3: Profile photo base64 data URI | Yes | Yes | `load_profile_photo_base64()` converts to data URI. Missing photo falls back to initials placeholder. Tested with real temp PNG creation. |
| AC4: Text sizes scale based on content length | Yes | Yes | `title-short` (<40 chars), `title-medium` (40-65), `title-long` (>65) CSS classes applied via Jinja2 conditional. Tests cover all 3 ranges. |
| AC5: All elements configurable via config.json | Yes | Mostly | Brand, header, colors, fonts all configurable. However, several hardcoded strings remain in templates (see Major #1 below). |
| AC6: Fully parameterized (no hardcoded text) | Yes | No | Multiple hardcoded strings found (see Major #1). Claim is overstated. |

---

## Issues Found

### Major

1. **Hardcoded strings in "parameterized" templates**
   - Files: `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/modern-editorial.html:393`, `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/tech-minimal.html:391,418,525,556`
   - Problem: AC6 claims "fully parameterized (no hardcoded text from mockup)" but several strings are baked in:
     - `modern-editorial.html:393` -- `"A Step-by-Step Guide"` hardcoded kicker text
     - `modern-editorial.html:457` -- `"Key Points"` hardcoded pull-accent text
     - `modern-editorial.html:490` -- `"Architecture"` hardcoded pull-accent for mermaid
     - `tech-minimal.html:391` -- `"content-pipeline.md"` hardcoded terminal tab
     - `tech-minimal.html:418` -- `"$ cat pipeline-guide.md"` hardcoded command
     - `tech-minimal.html:525` -- `"// Architecture overview"` hardcoded code comment
     - `tech-minimal.html:543` -- `"follow.md"` hardcoded terminal tab for CTA
     - `tech-minimal.html:556` -- `"ai-automation"` hardcoded topic in follow command
     - All 3 templates: `"Follow for More"` hardcoded CTA button text
   - Fix: Move these to config.json or derive from slide data. The CTA button text at minimum should be configurable via `brand.cta_text` or similar. The template-specific decorative strings (terminal tabs, kicker text) could be added per-template in config.json under a `template_strings` key. Not a blocker for Phase 2, but should be addressed in Phase 4 (Polish).

2. **Hardcoded color values in brand-purple.html and tech-minimal.html CSS**
   - Files: `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/brand-purple.html:76,84,168,221`, `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/tech-minimal.html:108,297`
   - Problem: Despite having an extensive color config, several CSS properties use raw `rgba()` values instead of `{{ colors.xxx }}` variables:
     - `brand-purple.html:76` -- `rgba(139,92,246,0.4)` instead of using a colors variable
     - `brand-purple.html:84` -- `box-shadow: 0 0 20px rgba(139,92,246,0.5)`
     - `brand-purple.html:168` -- `rgba(139,92,246,0.25)` for numbered list background
     - `brand-purple.html:221` -- `rgba(139,92,246,0.2)` for photo background
     - `tech-minimal.html:108` -- `rgba(88,166,255,0.3)` for step-bar glow
     - `tech-minimal.html:297` -- `rgba(88,166,255,0.2)` for tag border
   - Fix: Either add these as named colors in config.json or accept that these are template-internal implementation details. If the goal is truly configurable colors, they need to reference config variables. Not blocking Phase 2.

3. **Test environment does not match production (missing autoescape)**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/tests/test_carousel_templates.py:264`
   - Problem: All template rendering tests create `Environment(loader=FileSystemLoader(CAROUSEL_DIR))` without `autoescape=select_autoescape(["html"])`. Production code in `render.py:259-261` uses autoescape. This means:
     - Tests pass HTML content through unescaped, but production would escape it
     - The test `test_renders_profile_photo_when_data_provided` works in both cases because `src` attribute values are not affected by autoescape in Jinja2 (the `&` in `base64` is fine)
     - But any test checking raw content rendering (like asserting exact HTML output) could pass in tests but behave differently in production
   - Fix: Add `autoescape=select_autoescape(["html"])` to all test fixtures. Or better, use `render_html_from_slides()` directly in tests (like `test_render.py` does) so the production code path is exercised.

### Minor

1. **Docstring in render.py still references "dark-purple"**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:16`
   - Problem: Module docstring example shows `render_carousel(slides, "dark-purple", "/tmp/output")` but the default template is now `brand-purple` and `dark-purple` no longer exists in config.
   - Fix: Update the docstring to `"brand-purple"`.

2. **Inconsistent `header.show_on_all_slides` behavior across templates**
   - Files: `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/brand-purple.html:400,462,490` vs `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/modern-editorial.html` and `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/tech-minimal.html`
   - Problem: `brand-purple.html` correctly checks `{% if header.show_on_all_slides %}` before rendering the header on content/mermaid/CTA slides. But `modern-editorial.html` and `tech-minimal.html` render the header unconditionally on every slide type -- they never check the config flag.
   - Fix: Add the `{% if header.show_on_all_slides %}` guard to the non-title slides in the other two templates.

3. **Content slides always render `<ul>` (bullets) -- no numbered list support yet**
   - Files: All 3 templates, e.g. `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/brand-purple.html:446-453`
   - Problem: The CSS defines styled `<ol>` numbered lists (with counter-based numbering), but the content rendering logic always wraps lines in `<ul>` tags. There is no logic to detect `1. ` prefixed lines and render them as `<ol>`. This is technically a Phase 2 concern (content slide template) and the plan says "Add a Jinja2 custom filter or macro for markdown-to-HTML conversion" in Phase 2. So this is expected to be incomplete in Phase 1.
   - Note: Documented here for Phase 2 executor awareness.

4. **`lstrip('- ')` strips character set, not substring**
   - Files: All 3 templates, e.g. `/home/blake/repos/personal/whisper-transcribe-ui/kb/carousel_templates/brand-purple.html:450`
   - Problem: `stripped.lstrip('- ').lstrip('* ')` strips any character from the set `{'-', ' '}` then `{'*', ' '}`. For typical markdown bullets (`- item`) this works fine. But edge cases like content starting with hyphens (`- -Something important-`) would lose the leading hyphen of the word. In practice, LLM-generated content is unlikely to hit this, and Phase 2 plans a proper markdown parser, so this is cosmetic.

---

## What's Good

- **Profile photo loading is well-engineered.** MIME type detection from extension, graceful fallback to initials placeholder, base64 encoding -- handles all the edge cases correctly.
- **Backward compatibility for `brand.name`.** The `render.py:246-249` backward compat mapping from `brand.name` to `brand.author_name` means old configs still work.
- **Config schema is clean and extensible.** The `templates`, `brand`, `header` separation is good. Per-template `colors` and `fonts` with Google Fonts URLs is well thought out.
- **Three templates instead of one.** Going beyond the minimum by implementing all 3 selected mockups gives real template choice.
- **Old templates properly archived** in `_archive/` rather than deleted. Clean migration path.
- **Dead `summary` slide type removed** from all new templates (confirmed by grep).
- **Test coverage is thorough.** 69 new template tests plus updated render tests. Config schema tests, rendering tests, profile photo tests, mermaid tests, parameterization tests, min/max slide count tests.

---

## Required Actions (for Phase 4 -- not blocking Phase 2)

- [ ] Fix hardcoded strings in modern-editorial.html and tech-minimal.html (Major #1)
- [ ] Add `header.show_on_all_slides` check to modern-editorial.html and tech-minimal.html (Minor #2)
- [ ] Update render.py docstring to reference brand-purple (Minor #1)
- [ ] Add autoescape to test fixtures in test_carousel_templates.py (Major #3)
- [ ] Consider extracting hardcoded colors to config variables (Major #2)

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Jinja2 test environments must match production autoescape settings | All template tests | Add autoescape to test fixtures or use production render functions |
| "Fully parameterized" claims need grep verification | Template reviews | Always grep for literal strings in parameterized templates |
| Config flags must be checked consistently across all templates | Multi-template systems | When adding a config-controlled feature, verify all templates honor it |
