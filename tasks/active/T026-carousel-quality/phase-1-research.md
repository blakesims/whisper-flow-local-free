# Phase 1 Research: Schema + Prompt Redesign

## Problem
Gemini returned empty titles, prose content, wrong mermaid styling. Root cause: weak schema + prompt, not model limitations.

## Key Findings

### Gemini Structured Output Enforcement
Verified via research agents + manual testing:

| Schema feature | Enforced? | Notes |
|----------------|-----------|-------|
| `required` | Key presence only | Empty string `""` is valid |
| `minLength`, `maxLength`, `pattern` | **Silently ignored** | All SDK versions |
| `enum` | Yes | Restricts to listed values |
| `format` | Yes | e.g. date formats |
| `type: array` + `items` | Yes | Forces structured items |

**`response_json_schema` (SDK v1.22.0+) vs `response_schema` (v1.17.0):** Identical enforcement behavior. Upgrading SDK does not improve structured output quality.

### Incremental Bisection Testing (5 levels)
Built from minimal → full config to find where titles break:

| Level | Config | Result |
|-------|--------|--------|
| 1 | Minimal schema, fake post | PASS — 5/5 titles |
| 2 | + bullets array, + enum types | PASS — 5/5 titles, 4 bullets each |
| 3 | Full schema + system instruction + fake post | PASS — 6/6 titles |
| 4 | Full schema + system instruction + real post | PASS — 8/8 titles |
| 5 | Same as 4 (reproducibility) | PASS — 7/7 titles |

No breakpoint found. The redesigned schema works at all complexity levels.

### What Fixed It
1. **`bullets: array<string>`** instead of `content: string` — structurally prevents prose
2. **3 few-shot examples** in prompt (content, hook, mermaid) — old prompt had 1
3. **System instruction** with explicit rules per slide type
4. **Removed `words` from required** — unnecessary field that added noise

### End-to-End Verification
Generated carousel for real transcript (`50.03.01/260206-alpha-...`):
- 8 slides, all with populated titles
- 5 content slides with 4 bullets each
- Mermaid slide with `%%{init}` brand theming
- PDF rendered and visually confirmed: major improvement over old output

### Remaining Visual Issues (Phase 2)
- Timeline dot highlight: square on steps 2-5 (CSS `border-radius` bug)
- Font: generic, needs brand font
- Timeline label clutter: full titles may be too long

### Config Runtime Gotcha
Pipeline loads configs from `KB_ROOT/config/analysis_types/`, NOT `kb/config/` in repo. After editing `carousel_slides.json` in repo, must copy to runtime path. This caused a false "nothing changed" result during initial testing.
