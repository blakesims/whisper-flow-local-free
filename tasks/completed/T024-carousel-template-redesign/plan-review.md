# Plan Review: T024 Carousel Template Redesign

## Gate Decision: NEEDS_WORK

**Summary:** The plan is well-structured with a solid mockup-first approach and clear phase ordering. However, there are critical technical gaps around SVG embedding conflicting with Jinja2 autoescape, missing schema changes for structured slide content (bullets/lists), and an underspecified profile photo delivery mechanism. These need to be addressed before execution.

---

## Open Questions Validation

### Valid (Need Human Input)
| # | Question | Why Valid |
|---|----------|-----------|
| Q1 | Profile photo placement on title page? | Directly affects brand presence and visual identity. Only Blake can decide what represents his brand correctly. |
| Q3 | Color palette expansion? | Strategic decision: single brand vs multi-palette flexibility. Affects mockup scope in Phase 0 (if answer is "multiple palettes," 5 mockups might not be enough variety within each). |

### Borderline (Recommend a Default)
| # | Question | Recommendation |
|---|----------|----------------|
| Q2 | Timeline indicator style? | This is what Phase 0 mockups are for -- each mockup should explore a different timeline style. Let Blake pick from the 5 mockups rather than deciding upfront. Remove as standalone question; embed in Phase 0 spec (each mockup uses a different indicator style). |
| Q4 | Font choice? | Same as Q2 -- mockup each with a different font and let Blake pick visually. Recommending Poppins, Outfit, Inter, DM Sans, and JetBrains Mono accent across the 5 mockups. Remove as standalone question. |

### Invalid (Auto-Decide)
None -- the remaining questions (Q1, Q3) are genuinely user-level.

### New Questions Discovered
| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q5 | Where does profile.png come from and when? | A) Blake provides before Phase 0 starts (needed for mockups) B) Blake provides before Phase 1 (mockups use placeholder) C) Already exists somewhere | **Blocks Phase 0 if answer is A.** Phase 0 says "profile photo placeholder (gray circle)" but Phase 1 says "profile.png from Blake." Clarify timing so there is no surprise block. |
| Q6 | Should the carousel_slides.json schema be updated to support structured content (bullets, numbered lists)? | A) Yes, add a `content_items` array field alongside `content` B) Keep flat `content` string, use markdown-like parsing in template C) Keep flat content, structure only in template HTML | The plan lists "bullet points, numbered lists, line breaks" as objectives (Phase 2) but the current LLM prompt and schema only have a flat `content` string. The template currently renders `{{ slide.content }}` as a single block. Without schema changes, the executor has no way to render bullets vs numbered lists vs paragraphs differently. |

---

## Issues Found

### Critical (Must Fix)

1. **Jinja2 autoescape will break inline SVG embedding** -- `render.py` line 195 uses `select_autoescape(["html"])`, which means any inline SVG content injected into templates via `{{ slide.mermaid_svg }}` or similar will be HTML-escaped, rendering the SVG as visible markup text instead of a rendered diagram. The plan (Phase 3) says "embed SVG directly in HTML (inline, not as img src)" but does not address the autoescape conflict. Fix: Phase 3 must either (a) use Jinja2's `|safe` filter on the SVG variable, (b) use `Markup()` wrapping in render.py before passing to template, or (c) switch mermaid to base64 data URI with `data:image/svg+xml;base64,...` in an `<img>` tag (avoiding the autoescape issue entirely while still being SVG). Option (c) is safest since it avoids the XSS surface of `|safe` while still getting crisp SVG rendering.

2. **No schema support for structured content (bullets/lists/line breaks)** -- The plan repeatedly states content slides should support "bullet points, numbered lists, line breaks -- not block text." But `carousel_slides.json` only has a flat `content: string` field. The current templates render `{{ slide.content }}` as a single text block. There is no mechanism for the LLM to output structured content (array of items with type markers) and no template logic to render them differently. The plan's Phase 2 AC says "Bullet points render as actual bullets (not raw text)" but does not specify how the data flows from LLM -> JSON -> template. Fix: Either (a) extend carousel_slides.json schema to add a `content_format` field (`"bullets"`, `"numbered"`, `"text"`) and a `content_items` array, then update the LLM prompt, OR (b) define a simple markdown-like convention in the `content` string (lines starting with `- ` become bullets, lines starting with `1. ` become numbered) and add template parsing logic. Option (b) is simpler and doesn't require LLM prompt changes.

3. **render_pipeline base64 encoding assumes PNG** -- `render_pipeline()` at line 463 hardcodes `data:image/png;base64,{img_data}`. When Phase 3 switches to SVG output, this line must change to `data:image/svg+xml;base64,{img_data}`. The plan's Phase 3 file list says "MODIFY: render_mermaid() outputs SVG instead of PNG" but the corresponding render_pipeline changes needed (MIME type, file extension check, possibly raw SVG reading instead of base64) are not called out. Fix: Phase 3 must explicitly include render_pipeline() modifications alongside render_mermaid() changes.

### Major (Should Fix)

1. **Phase 4 profile photo integration is too late** -- Phase 4 lists "Profile photo integration: load profile.png, render circular cutout on title page" but Phase 1 already lists as AC: "Profile photo renders as circular cutout." These contradict each other. If Phase 1 implements the title page WITH profile photo, Phase 4 shouldn't re-implement it. If Phase 1 uses a placeholder and Phase 4 swaps in the real photo, that should be explicit. Fix: Clarify -- Phase 1 implements the photo integration (CSS circular clip, config path), Phase 4 does final QA polish only.

2. **config.json schema expansion is unspecified** -- The plan mentions adding `profile_photo_path`, `community_name`, header settings to config.json (Phase 1), but never specifies the actual schema. The current config has no `community_name` field -- the header bar concept (Blake's name left, "Claude Code Architects" right) requires new config fields. The executor needs to know the exact structure. Fix: Add a concrete config.json diff showing the new fields: `brand.community_name`, `brand.profile_photo_path`, and any `header` settings.

3. **Mockups are static HTML but templates are Jinja2** -- Phase 0 produces "self-contained HTML files viewable in a browser" but Phases 1-3 produce Jinja2 templates. There is no plan for how the chosen mockup design gets translated into a Jinja2 template. This is a non-trivial step -- the mockup will have hardcoded colors/fonts/dimensions, but the template needs `{{ colors.accent }}`, `{{ brand.name }}`, `{% for slide in slides %}` loops, etc. Fix: Add explicit guidance in Phase 1 that the executor must convert the static mockup into a parameterized Jinja2 template, and note this is the bulk of the work (not just "implement the chosen design").

4. **`summary` slide type exists in templates but not in schema** -- Both dark-purple.html and light.html have CSS and Jinja2 logic for a `summary` slide type, but carousel_slides.json only defines `["hook", "content", "mermaid", "cta"]` in the enum. The plan's Phase 2 does not address whether `summary` should be added to the schema or removed from templates. Fix: Decide -- either add `summary` to the slide type enum in carousel_slides.json or remove it from the new templates.

### Minor

1. **Multiple mermaid slides not handled** -- `render_pipeline()` iterates over all mermaid slides but writes output to the same path (`mermaid.png`). If a carousel has 2 mermaid slides, the second overwrites the first. The plan doesn't introduce multiple mermaid support, but doesn't acknowledge this limitation either.

2. **Google Fonts dependency** -- Both current templates use `@import url('https://fonts.googleapis.com/css2?family=Inter...')`. Phase 4 mentions "font tuning: ensure chosen fonts load reliably (local fallbacks if Google Fonts unavailable)" but this is buried at the end. For mockups (Phase 0), if Blake reviews on a machine without internet or with slow connection, fonts may not load. Consider bundling fonts or using system fonts for mockup review.

3. **Test strategy is vague** -- Phases 1-4 each mention "MODIFY: tests" but don't specify what new test patterns are needed. The new templates will have fundamentally different HTML structure (header bar, timeline indicator, profile photo). The existing test suite checks for specific CSS class names (`hook-text`, `content-number`, `brand-name`) that will change. The test plan should acknowledge that existing tests will break and new tests must be written, not just modified.

4. **Phase 0 README.md** -- The plan lists `kb/carousel_templates/mockups/README.md` as a new file. Per Blake's instructions, documentation files should only be created when explicitly requested. Recommend skipping this unless Blake specifically asks for it.

---

## Plan Strengths

- The mockup-first approach (Phase 0) is excellent -- designing visually before implementing avoids the "boring layout" problem that prompted this task.
- Phase ordering is logical: mockup -> title page -> content slides -> mermaid SVG -> polish. Each builds on the previous.
- Clear separation from T023 with well-identified parallelism windows (Phases 0-2 independent of T023).
- Decisions already made (D1-D6) are sound and well-rationalized.
- Time estimates seem reasonable (3-4h for 5 mockups, 2-3h per implementation phase).

---

## Recommendations

### Before Proceeding (Must Address)
- [ ] Phase 3: Document the Jinja2 autoescape conflict and choose a resolution approach (recommended: SVG base64 data URI in img tag)
- [ ] Phase 2: Define how structured content (bullets/lists) flows through the system -- schema change or parsing convention
- [ ] Phase 3: Add render_pipeline() to the modification list (base64 MIME type, file extension changes)
- [ ] Clarify profile photo timing: Phase 1 vs Phase 4 contradiction
- [ ] Add concrete config.json schema diff for new fields (community_name, profile_photo_path)
- [ ] Phase 1: Add explicit note about converting static mockup HTML to parameterized Jinja2 template

### Consider Later
- Decide on `summary` slide type: keep in schema or remove from templates
- Address multiple mermaid slide limitation (or document as known constraint)
- Consider font bundling strategy for offline/slow-network mockup review
- Plan for existing test suite breakage when template HTML structure changes
- Skip the README.md in mockups directory (per Blake's documentation preferences)
