# Phase 0: Data Capture & Root Cause Analysis

**Date:** 2026-02-09
**Transcript tested:** `50.03.01/260206-alpha-jeremy-krystosik-blake-sims-1.json`
**Template:** brand-purple
**Model:** gemini-3-pro-preview

---

## 1. What Was Sent to the Model

### System Instruction
```
You produce carousel slide data for PDF rendering. STRICT RULES you must follow:
1. Every content and mermaid slide MUST have a non-empty 'title' field of 2-5 words. Empty titles are FORBIDDEN. Examples: 'Set Up Recording', 'Run Analysis', 'The Results'.
2. The 'content' field MUST use bullet-point format with each line starting with '- ' (dash space). NEVER use paragraphs or prose.
3. Do NOT copy text verbatim from the source post. Restructure and condense into fresh, scannable bullet points.
4. Each bullet point should be 8-15 words with one specific insight, tool name, number, or command.
```

### Prompt (truncated)
```
Transform this LinkedIn post into a visual carousel.

SOURCE POST:
Stop writing end-to-end tests manually.

I showed a founder how to automate this yesterday.

We were staring at a "brownfield" SaaS codebase.
377 API routes. [... full linkedin_v2 post ...]

---

Create 6-10 slides following this structure:

Slide 1 (hook): Short punchy title, 5-12 words. Add a subtitle with supporting context.
Slides 2-N (content): Each needs a 2-5 word TITLE and 3-4 BULLET POINTS starting with '- '.
Optional mermaid slide: If the post describes a workflow/pipeline. Max 10 nodes.
Last slide (cta): Engaging question, 8-20 words.

EXAMPLE content slide:
{
  "slide_number": 2,
  "type": "content",
  "title": "Set Up Recording",
  "content": "- Run npx playwright codegen to open a browser recorder\n- Click through your app's key user flows manually\n- Capture sign-up, login, dashboard, and core features\n- Save the raw recording as your test seed script",
  "words": 30
}
```

### API Configuration
```python
response_mime_type = "application/json"
response_schema = { ... }  # Full output_schema from carousel_slides.json
system_instruction = "You produce carousel slide data..."  # See above
model = "gemini-3-pro-preview"
```

### Output Schema (JSON Schema)
```json
{
  "type": "object",
  "properties": {
    "slides": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "slide_number": { "type": "integer" },
          "type": { "type": "string", "enum": ["hook", "content", "mermaid", "cta"] },
          "title": { "type": "string", "description": "2-5 word label..." },
          "content": { "type": "string" },
          "words": { "type": "integer" },
          "subtitle": { "type": "string" }
        },
        "required": ["slide_number", "type", "title", "content", "words"]
      }
    },
    "total_slides": { "type": "integer" },
    "has_mermaid": { "type": "boolean" }
  },
  "required": ["slides", "total_slides", "has_mermaid"]
}
```

---

## 2. What the Model Returned

### Raw JSON output (verbatim from transcript JSON)

Every single slide is missing the `title` field entirely. The content is prose, not bullet points.

```json
{
  "slides": [
    {
      "slide_number": 1,
      "type": "hook",
      "content": "Stop writing end-to-end tests manually.",
      "words": 6
    },
    {
      "slide_number": 2,
      "type": "content",
      "content": "We faced a \"brownfield\" SaaS codebase:\n\n• 377 API routes\n• Years of \"MVP\" code piled up\n• Goal: Clean it up without destroying the business",
      "words": 23
    },
    {
      "slide_number": 3,
      "type": "content",
      "content": "You cannot refactor what you cannot test.\n\nBut writing legacy tests is miserable work. So we didn't write them.\n\nWe recorded them using \"Seed Scripts.\"",
      "words": 25
    },
    {
      "slide_number": 4,
      "type": "content",
      "content": "Step 1: The Context Anchor\n\nWe created a `Global Task Manager` file to ground the `Claude Code` CLI agent with specific status definitions.",
      "words": 22
    },
    {
      "slide_number": 5,
      "type": "content",
      "content": "Step 2: The Human Recording\n\nWe ran `npx playwright codegen`. Jeremy clicked through the app (Sign up, Log in) to capture the *intent* without touching code.",
      "words": 23
    },
    {
      "slide_number": 6,
      "type": "content",
      "content": "Step 3: The AI Execution\n\nWe fed that raw recording into the `Playwright MCP` tool. A sub-agent turned the recording into a resilient test suite.",
      "words": 21
    },
    {
      "slide_number": 7,
      "type": "mermaid",
      "content": "graph LR\n    A[Human Clicks] --> B[Playwright Codegen]\n    B --> C[Raw Script]\n    C --> D[Claude MCP]\n    D --> E[Resilient Test Suite]",
      "words": 0
    },
    {
      "slide_number": 8,
      "type": "content",
      "content": "The Result: A Safety Net\n\nWe can now delete those 377 API routes.\n\nDon't read the code. Run the app. Let `Claude Code` write the test.",
      "words": 25
    },
    {
      "slide_number": 9,
      "type": "cta",
      "content": "What is the single oldest file in your codebase that everyone is too scared to touch?",
      "words": 16
    }
  ],
  "total_slides": 9,
  "has_mermaid": true
}
```

---

## 3. Difference Analysis: Generated HTML vs Mockup HTML

### Visual Comparison Table

| Element | Mockup (3-brand-purple.html) | Generated (carousel.html) | Gap |
|---------|------------------------------|---------------------------|-----|
| **Slide title** | `<div class="slide-title">Set Up Transcription</div>` — 46px, bold, styled | **MISSING** — no `.slide-title` element rendered | CRITICAL |
| **Title accent line** | `<div class="slide-subtitle-line"></div>` — purple underline | **MISSING** — not rendered when title is empty | CRITICAL |
| **Timeline labels** | Descriptive: "Transcribe", "Analyze", "Classify", "Generate", "Publish" | Generic: "Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6" | HIGH |
| **Bullet points** | `<ul><li>` with purple dots, left border, proper spacing | `<p>` tags — prose paragraphs, no list styling | CRITICAL |
| **Bullet format** | Each line starts with `- ` in JSON → parsed by `markdown_to_html()` as `<ul>` | Uses `•` character or plain prose → parsed as `<p>` text | HIGH |
| **Content density** | 4 bullet points per slide, 8-15 words each | 1-3 short sentences with lots of whitespace | HIGH |
| **Backticks** | Not used in mockup (tool names in plain text) | Literal backticks visible: `` `Global Task Manager` `` renders as text | MEDIUM |
| **Mermaid diagram** | Hand-crafted SVG: brand purple (#8B5CF6), vertical layout, labels | mmdc-generated: dark theme, horizontal, 70px height, wrong colors | HIGH |
| **Empty space** | Content fills ~60% of slide area | Content fills ~20%, massive void below | CRITICAL |
| **Slide count** | 6 slides (5 content + 1 CTA) | 9 slides (hook + 6 content + mermaid + CTA) — too many, too sparse | MEDIUM |
| **Hook page subtitle** | Present: "From raw transcription to polished LinkedIn carousels" | **MISSING** — no subtitle field returned | LOW |
| **Decorative number** | Large "5" in background (`.title-page-deco`) | **MISSING** — template supports it but no data to show | LOW |

### Root Cause Chain

```
LLM returns empty titles
  → Template skips .slide-title and .slide-subtitle-line
  → Timeline labels fall back to "Step N" (no title to use)
  → Content area starts at top without title section = massive empty space

LLM returns prose content (not "- " bullets)
  → markdown_to_html() parses as <p> tags
  → No <ul><li> elements = no purple bullets, no left border, no spacing
  → Content appears as dense paragraph or sparse text

LLM uses • character instead of - prefix
  → markdown_to_html() doesn't recognize • as bullet marker
  → Renders as paragraph with • as text character

LLM embeds backticks in content
  → markdown_to_html() doesn't handle inline code formatting
  → Raw ` characters appear in rendered output

mmdc renders mermaid with default dark theme
  → Colors don't match brand purple palette
  → SVG is horizontally laid out (graph LR) → tiny height (70px)
  → Mockup uses vertical layout with brand-matched hand-crafted SVG
```

---

## 4. Layer-by-Layer Analysis

### Layer 1: LLM Output (Gemini)

**Problems:**
1. `title` field missing on ALL slides despite being in `required` array
2. Content is prose, not `- ` bullet format despite system instruction + prompt example
3. Content copies verbatim phrases from the LinkedIn post despite "do NOT copy" instruction
4. Uses `•` Unicode bullet instead of `- ` prefix
5. Embeds step labels in content text ("Step 1: The Context Anchor") instead of in `title` field

**Root cause:** Gemini's structured output enforcement is weak:
- `required` fields in JSON Schema: enforces field existence but allows empty string `""`
- `description` text constraints: completely ignored (minLength, pattern, etc.)
- System instruction compliance: moderate — model follows some rules, ignores others
- The prompt has ONE example but needs stronger few-shot demonstration

**Research questions:**
- Does adding multiple few-shot examples in the prompt improve compliance?
- Does using `enum` for the bullet format prefix improve enforcement?
- Can we use a validation + retry loop (check output, reject if empty titles)?
- Would Gemini Flash or a different model be more compliant?
- Does the `response_json_schema` parameter (which doesn't exist in v1.17.0) work differently in newer SDK versions?

### Layer 2: Template Rendering (Jinja2 + markdown_to_html)

**Problems:**
1. `markdown_to_html()` only handles `- `, `* `, and `N. ` — not `•`, not prose
2. No inline code processing (backticks → `<code>` elements)
3. No `*italic*` processing
4. Timeline label text comes from... where? The template generates "Step N" when title is empty
5. When `.slide-title` is empty, the title section is completely omitted (no fallback)

**Root cause:** The `markdown_to_html()` function was written for well-formatted input. It doesn't handle the messy output that Gemini actually produces.

**Research questions:**
- Should we use a real Markdown parser (e.g., `markdown` library) instead of custom parsing?
- Should we normalize LLM output before template rendering (pre-processing step)?
- Should the template have fallback rendering for missing titles?

### Layer 3: Mermaid Rendering (mmdc CLI)

**Problems:**
1. mmdc uses dark theme — colors don't match brand palette
2. `graph LR` produces horizontal layout → very short height (70px vs 1000px available)
3. No labels/annotations like the mockup has
4. The mockup doesn't use mermaid at all — it uses hand-crafted SVG

**Root cause:** The mermaid→SVG pipeline was designed for generic diagrams, not brand-matched visuals.

**Research questions:**
- Can we create a custom mermaid theme that matches the brand palette?
- Should we generate SVG directly instead of using mermaid?
- Should the LLM generate vertical (`graph TD`) instead of horizontal (`graph LR`)?
- Can we post-process the SVG to replace colors?

### Layer 4: PDF Rendering (Playwright)

**No major issues found.** Playwright renders the HTML faithfully. The problems are all upstream.

---

## 5. What Needs Research (Phase 1 Prerequisites)

1. **Gemini structured output limits**: What exactly does `response_schema` enforce in google-genai v1.17.0? Test with explicit constraints.

2. **Prompt engineering for compliance**: Test with:
   - Multiple few-shot examples (3-5 slides shown explicitly)
   - Explicit negative examples ("DO NOT: { content: 'Step 1: ...' }")
   - Stronger formatting constraints in system instruction

3. **Validation + retry pattern**: Design a post-processing validation that:
   - Checks each slide has non-empty title
   - Checks content starts with `- ` on each line
   - If validation fails, retry with feedback injected into prompt

4. **Markdown normalization**: Research if a pre-processing step can convert messy LLM output to clean markdown before template rendering:
   - `•` → `- `
   - Remove "Step N:" prefix from content → move to title
   - `` `code` `` → leave as-is (handle in template)

5. **Mermaid theming**: Research custom mermaid themes to match brand colors, or alternative diagram rendering approaches.

---

## 6. Files Involved

| File | Role | Issues Found |
|------|------|-------------|
| `kb/config/analysis_types/carousel_slides.json` | LLM prompt + schema | Prompt needs more examples; schema `required` not enforced |
| `kb/analyze.py` | API call to Gemini | Fixed `response_json_schema` → `response_schema` |
| `kb/render.py::markdown_to_html()` | Content parsing | Only handles `- `, `* `, `N. `; no inline code/italic |
| `kb/carousel_templates/brand-purple.html` | Jinja2 template | Template is fine — problem is data it receives |
| `kb/carousel_templates/config.json` | Template settings | Mermaid theme setting exists but doesn't match brand |
| `kb/publish.py` | CLI for rendering | No issues found |

---

## 7. Generated HTML Artifacts

The full generated HTML is saved at:
`~/Obsidian/zen-ai/knowledge-base/transcripts/50.03.01/visuals/carousel.html`

Key observations from the HTML:
- Slide 2-8: No `.slide-title` div, no `.slide-subtitle-line` div
- Content is wrapped in `<p>` tags (not `<ul><li>`)
- Timeline shows "Step 1" through "Step 6" (generic labels)
- Mermaid SVG inline: 1049px wide × 70px tall (horizontally squished)
- HTML entity encoding is correct (`&#34;`, `&#39;`, etc.)
- CSS styling matches brand-purple template (colors, fonts, layout correct)

---

## Summary

The template and CSS are fine. The pipeline mechanics work. **The problem is almost entirely in the LLM output quality.** Gemini returns:
1. Empty titles (despite `required` + system instruction)
2. Prose content (despite bullet format instruction)
3. Verbatim copied text (despite explicit "do NOT copy" instruction)
4. Wrong bullet characters (`•` instead of `- `)
5. Embedded structural info in content (step labels should be in title field)

Secondary issues:
- `markdown_to_html()` doesn't handle edge cases (backticks, `•`, italic)
- Mermaid styling doesn't match brand
- No post-processing validation or retry on bad output

The fix path is: **improve LLM prompt → add output validation → fix markdown parser → fix mermaid theming**.
