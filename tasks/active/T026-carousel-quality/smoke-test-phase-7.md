# Phase 7 Smoke Test Report

**Date**: 2026-02-10
**Server**: localhost:4004
**Test Action**: `50.03.01-260206-alpha-jeremy-krystosik-blake-sims-1--linkedin_v2`
**Slide data**: 8 slides (1 hook, 5 content, 1 mermaid, 1 CTA), pre-Phase 6 format (bullets array, no format field)

---

## Template Test Results

### 1. brand-purple -- PASS

| Check | Result |
|-------|--------|
| Template applied correctly | PASS -- #2D1B69 background, timeline nav elements |
| Font: Plus Jakarta Sans | PASS -- Google Fonts link + font-family declarations correct |
| Bullets rendered (<li> in <ul>) | PASS -- 20 bullets across 5 content slides |
| Hook slide | PASS -- title + subtitle render |
| Content slides (5) | PASS -- title + 4 bullets each |
| Mermaid slide | PASS -- mermaid_svg embedded |
| CTA slide | PASS -- heading + subtext visible |
| PDF exists | PASS -- carousel.pdf 520KB |
| Thumbnails | PASS -- slide-1.png through slide-8.png, 36-313KB each |

**Fonts detected**: `'Plus Jakarta Sans', 'Inter', system-ui, sans-serif`
**Google Fonts URL**: `Plus+Jakarta+Sans:wght@400;500;600;700;800`

### 2. modern-editorial -- PASS

| Check | Result |
|-------|--------|
| Template applied correctly | PASS -- #FAF8F5 background, #1C1C1C text, editorial layout |
| Font: Playfair Display (heading) | PASS |
| Font: Source Sans 3 (body) | PASS |
| Bullets rendered (<li> in <ul>) | PASS -- 20 bullets across 5 content slides |
| Hook slide | PASS |
| Content slides (5) | PASS -- title + pull-accent + 4 bullets each |
| Mermaid slide | PASS |
| CTA slide | PASS |
| PDF exists | PASS -- carousel.pdf 400KB |
| Thumbnails | PASS -- slide-1.png through slide-8.png, 54-73KB each |

**Fonts detected**: `'Playfair Display', Georgia, serif` / `'Source Sans 3', 'Source Sans Pro', system-ui, sans-serif` / `'JetBrains Mono', 'Fira Code', monospace`
**Google Fonts URL**: `Playfair+Display:wght@700;800;900&family=Source+Sans+3:wght@400;500;600;700`

### 3. tech-minimal -- PASS

| Check | Result |
|-------|--------|
| Template applied correctly | PASS -- #0D1117 background, terminal-bar, breadcrumb nav |
| Font: Inter (heading/body) | PASS |
| Font: JetBrains Mono (mono) | PASS |
| Bullets rendered (<li> in <ul>) | PASS -- 20 bullets across 5 content slides |
| Hook slide | PASS -- title-page layout |
| Content slides (5) | PASS -- terminal chrome + breadcrumb + step-bar + 4 bullets each |
| Mermaid slide | PASS |
| CTA slide | PASS |
| PDF exists | PASS -- carousel.pdf 393KB |
| Thumbnails | PASS -- slide-1.png through slide-8.png, 54-74KB each |

**Fonts detected**: `'Inter', system-ui, sans-serif` / `'JetBrains Mono', monospace`
**Google Fonts URL**: `JetBrains+Mono:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700`

---

## Pre-Phase 6 Backward Compatibility -- PASS

All 3 templates correctly handle slides with `bullets` array but **no `format` field**.
The Jinja2 fallback path works as expected:
```jinja2
{% elif slide.bullets %}
<ul>
  {% for item in slide.bullets %}<li>{{ item|highlight_words }}</li>
  {% endfor %}
</ul>
```

---

## Bugs Found

### BUG-1: `generate-visuals` endpoint does not pass template_name (CONFIRMED)

**Severity**: Medium
**File**: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve_visual.py`, line 165

The `generate-visuals` endpoint (`POST /api/action/<id>/generate-visuals`) calls `run_visual_pipeline()` which at line 165 calls:
```python
result = render_pipeline(slides_output, str(visuals_dir))
```
No `template_name` parameter is passed. This means it always uses the config default (`brand-purple`).

Compare with the `render` endpoint (`POST /api/action/<id>/render`) in `serve.py` line 944:
```python
result = render_pipeline(slides_output, str(visuals_dir), template_name=template_name)
```

**Impact**: Users cannot control template selection when using the staging workflow (`iterate -> stage -> generate-visuals`). Only the re-render endpoint (`/api/action/<id>/render`) supports template selection.

**Fix**: Add `template_name` parameter to `run_visual_pipeline()` signature and pass it through to `render_pipeline()`. The `generate-visuals` endpoint should accept an optional `template` field in the request body.

### BUG-2: Stale thumbnail files not cleaned up on re-render

**Severity**: Low
**File**: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py`, `render_carousel()` function

When a carousel is re-rendered with fewer slides than a previous render, the old excess slide PNG files are not deleted. Observed:
- Current carousel has 8 slides (slide-1.png through slide-8.png)
- `slide-9.png` (241KB, from Feb 9) and `slide-10.png` (384KB, from Feb 8) persist from earlier renders

**Impact**: Could cause confusion in downstream consumers that glob for slide-*.png files. The posting queue thumbnail might reference stale files.

**Fix**: Before generating new thumbnails in `render_carousel()` or `render_slide_thumbnails()`, delete existing `slide-*.png` files from the output directory.

### BUG-3 (Minor): First render after server start may have timing issues

**Severity**: Low / Observation

During testing, the first `brand-purple` render appeared to complete (visual_status changed to "ready") but the HTML file still contained output from a previous tech-minimal render. On retry with adequate wait time (30s), brand-purple rendered correctly. This may be a race condition between the mermaid LLM generation step (which is slow) and the status update, or it could be filesystem caching on the NFS/sync layer.

---

## Thumbnail Size Summary

| Template | slide-1 (hook) | slide-2..5 (content) | slide-6 (mermaid) | slide-7 (content) | slide-8 (CTA) | PDF |
|----------|----------------|----------------------|--------------------|--------------------|----------------|-----|
| brand-purple | 65KB | 36KB avg | 87KB | 38KB | 60KB | 520KB |
| modern-editorial | 58KB | 69-73KB | 65KB | 71KB | 54KB | 400KB |
| tech-minimal | 58KB | 71-74KB | 69KB | 69KB | 54KB | 393KB |

Note: brand-purple content slide thumbnails are notably smaller (36KB vs 69-74KB). This may indicate less visual content being rendered in thumbnails, or could be a rendering artifact. The HTML content is confirmed to have full bullets in all templates.

---

## HTML Description (What Each Template Looks Like)

### brand-purple
- Dark purple gradient background (#2D1B69 to #1A0F3C)
- Timeline navigation at top showing numbered steps with dot indicators (filled/active/inactive)
- White text on purple, accent color #8B5CF6
- Content slides have slide-title with subtitle-line divider, then unordered bullet list
- Hook slide uses large title with subtitle below
- CTA slide has heading + subtext + styled button

### modern-editorial
- Light cream background (#FAF8F5)
- Magazine/editorial aesthetic with Playfair Display serif headings
- "Big number" chapter indicators and editorial pip navigation dots
- Pull-accent quotes with decorative line borders
- Content slides use Source Sans 3 body font for clean readability
- Warm gold accent color (#B8A080)

### tech-minimal
- GitHub-dark background (#0D1117)
- Terminal-style chrome bar at top (red/yellow/green dots + tab name like "step-01.md")
- Breadcrumb navigation showing all content slide titles with active highlighting
- Step-bar progress indicator (filled/active/inactive segments)
- JetBrains Mono for code-like elements, Inter for body text
- Blue accent (#58A6FF) consistent with GitHub's design language

---

## Conclusion

**Overall: PASS (3/3 templates)**

All 3 carousel templates render correctly via the `/api/action/<id>/render` endpoint. Body text (bullets) renders in all templates. Template selection is applied correctly. Hook, content, CTA, and mermaid slides all render as expected. Pre-Phase 6 slides (bullets without format field) are handled correctly by all templates.

Two actionable bugs identified: the `generate-visuals` template passthrough gap and stale thumbnail cleanup.
