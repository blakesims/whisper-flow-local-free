# Carousel System Overview

## Pipeline

```
LinkedIn post (text) → Gemini LLM → slides JSON → Jinja2 template + config → HTML → Playwright → PDF + PNGs
```

## What the LLM Outputs (per slide)

| Field | Used by | Description |
|-------|---------|-------------|
| `slide_number` | Rendering | Position (1, 2, 3...) |
| `type` | Template routing | `hook`, `content`, `mermaid`, or `cta` |
| `title` | Slide header | 2-5 word label |
| `content` | Varies by type | Hook: headline. Mermaid: diagram code. CTA: question. |
| `bullets` | Content slides | Array of 3-4 plain text strings |
| `subtitle` | Hook + CTA | Supporting text |

## What's in Config (`kb/carousel_templates/config.json`)

| Area | Controls |
|------|----------|
| `colors.*` | All colors — backgrounds, accents, text, timeline dots, borders |
| `fonts.*` | Font families + Google Fonts URL |
| `brand.*` | Author name, handle, community name, CTA text, profile photo |
| `header.*` | Header visibility on all slides, author left/right position |
| `dimensions` | 1080x1350px |

## What's Hardcoded in Templates

Layout/structure: timeline bar, bullet styling, font sizes, spacing, corner glow, slide footer format, title page badge layout, CTA centered layout.

## The 4 Slide Types

1. **hook** — Author badge + big headline + accent line + subtitle
2. **content** — Timeline progress dots + title + bullet list
3. **mermaid** — Title + rendered SVG diagram
4. **cta** — Centered question + subtitle + follow button

## Key Files

| File | Purpose |
|------|---------|
| `kb/config/analysis_types/carousel_slides.json` | LLM prompt + schema |
| `kb/carousel_templates/config.json` | Colors, fonts, brand, layout config |
| `kb/carousel_templates/brand-purple.html` | Jinja2 template (primary) |
| `kb/render.py` | Mermaid rendering + HTML generation + Playwright PDF/PNG |
| `kb/publish.py` | CLI entry point (`kb publish`) |

## Commands

```bash
kb publish --staged              # Render staged items
kb publish --decimal 50.01.01    # Render specific transcript
kb publish --regenerate          # Re-render all existing
kb publish --dry-run             # Preview only
```
