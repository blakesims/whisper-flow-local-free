# Code Review: Phase 7

## Gate: PASS

**Summary:** Solid implementation. The data serialization layer, backend save-slides overhaul, and canGenerate/canReRender split all work correctly. 8 new backend tests cover the important paths. 54 tests passing, zero regressions. 3 minor issues found, none blocking.

---

## Git Reality Check

**Commits:**
```
69cee16 Phase7.1: Add slide data serialization layer
b6effd8 Phase7.2: Update slide editor UI for format-aware editing
7325671 Phase7.3: Backend save-slides handles bullets, format, subtitle
7b9a9ae Phase7.4: Split canGenerate/canReRender for button enable logic
```

**Files Changed:**
- `kb/serve.py` -- backend save-slides validation + field handling
- `kb/templates/posting_queue.html` -- serialization functions, UI, saveSlides(), button split
- `kb/tests/test_slide_editing.py` -- 8 new tests

**Matches Execution Report:** Yes. All 4 commits match, all 3 files match, all tasks/ACs claimed are verifiable.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| P1-AC1: slideToEditableText round-trips | Yes | Yes | bullets.join('\n') -> split('\n') -> identical array (filter empty lines) |
| P1-AC2: Empty lines/whitespace stripped | Yes | Yes | `map(l => l.trim()).filter(l => l.length > 0)` in editableTextToSlideFields |
| P1-AC3: Mermaid pass-through | Yes | Yes | editableTextToSlideFields returns `{content: text}` for mermaid type |
| P1-AC4: convertContentForFormatChange | Yes | Yes | lines.join('. ') for bullets->paragraph, pass-through for paragraph->bullets |
| P2-AC1: Bullet display as line-separated | Yes | Yes | slideToEditableText uses slide.bullets.join('\n') |
| P2-AC2: Numbered with dropdown selected | Yes | Yes | format dropdown pre-selects slide.format |
| P2-AC3: Paragraph display | Yes | Yes | slideToEditableText falls back to slide.content |
| P2-AC4: Hook/CTA subtitle fields | Yes | Yes | subtitleHtml rendered for hook/cta types |
| P2-AC5: Mermaid read-only monospace | Yes | Yes | readonly attr + monospace style applied |
| P2-AC6: Format change bullets->paragraph | Yes | Yes | handleFormatChange calls convertContentForFormatChange |
| P2-AC7: Format change paragraph->bullets | Yes | Yes | Returns text as-is (user controls newlines) |
| P2-AC8: Format change persists | Yes | Yes | saveSlides reads formatSelect.value, passes to editableTextToSlideFields |
| P2-AC9: Mermaid excluded from save | Yes | Yes | `if (slideType === 'mermaid') return;` in saveSlides forEach |
| P3-AC1: Bullet edits persist | Yes | Yes | test_save_bullets verifies bullets array + content fallback |
| P3-AC2: Paragraph clears bullets | Yes | Yes | test_save_paragraph_clears_bullets verifies bullets removed |
| P3-AC3: Subtitle persists | Yes | Yes | test_save_subtitle verifies hook + CTA subtitles |
| P3-AC4: Re-render uses updated data | Yes | Yes | test_save_and_refetch_bullets verifies round-trip |
| P3-AC5: Invalid format returns 400 | Yes | Yes | test_invalid_format_returns_400 |
| P4-AC1: Ready: Re-render enabled, Generate disabled | Yes | Yes | canGenerate requires staged; canReRender includes ready |
| P4-AC2: Staged: both enabled | Yes | Yes | Both conditions satisfied when status=staged |
| P4-AC3: Template switch + Re-render | Yes | Yes | reRender() sends selectedTemplate, backend accepts it |
| P4-AC4: Thumbnail updates | Yes | Yes | pollVisualGeneration -> renderStagingView (existing flow) |
| P4-AC5: Template-only switch works | Yes | Yes | reRender() allows status=ready, no save required |

---

## Issues Found

### Critical
None.

### Major
None.

### Minor

1. **Unescaped slideType in CSS class attribute**
   - File: `kb/templates/posting_queue.html:2026`
   - Problem: `class="slide-type-badge ${slideType}"` injects `slideType` without escaping. While the text content IS escaped via `${escapeHtml(slideType)}` and `data-slide-type` IS escaped, the CSS class is not. If `slideType` contained a `"` character, it could break out of the attribute. Low risk because: (a) this is a pre-existing pattern, not introduced by Phase 7, (b) `slide.type` is LLM-generated server data, not user-editable, (c) the field is not included in save payloads.
   - Fix: Use `${escapeHtml(slideType)}` in the class attribute too, or keep as-is given the controlled data source.

2. **Empty bullets array accepted by backend**
   - File: `kb/serve.py:799-800`
   - Problem: Validation accepts `bullets: []` (empty list passes `isinstance` + `all` checks). This would set `existing["bullets"] = []` and `existing["content"] = ""`, resulting in a slide with no content. The frontend strips empty lines before sending, so this would only occur via direct API call or if user deletes all content. No test covers this edge case.
   - Fix: Either reject empty bullets with a 400, or silently convert to a single empty bullet. Low priority -- the user would see an empty slide and re-edit.

3. **Double period in bullets-to-paragraph conversion**
   - File: `kb/templates/posting_queue.html:1824`
   - Problem: `convertContentForFormatChange` joins lines with `'. '`. If a bullet already ends with a period (e.g., `"First point."`), the result is `"First point.. Second point"`. Same issue exists in the backend's `". ".join(edited["bullets"])` at `serve.py:830`.
   - Fix: Strip trailing period before joining, or use a smarter joiner. Very minor -- users can manually fix the text after conversion.

---

## What's Good

- **Clean separation of concerns:** The 3 serialization functions (slideToEditableText, editableTextToSlideFields, convertContentForFormatChange) are well-structured and easy to reason about. Each has a single responsibility.
- **Backend validation is thorough:** Format, bullets, and subtitle are all validated with appropriate 400 errors. The validation loop runs before the update loop, so invalid data never partially writes.
- **canGenerate/canReRender split is correct:** The executor properly analyzed that `generateVisuals()` has an internal `status !== 'staged'` guard, and splitting the enable variables prevents a misleading UX where the button appears clickable but silently does nothing.
- **Backwards compatibility preserved:** `slideToEditableText` falls back to `slide.content` when `slide.bullets` is missing. The backend writes `content` as a fallback string when saving bullets.
- **8 new tests cover all major backend paths:** Bullets save, paragraph clears bullets, subtitle persistence, numbered format, invalid format/bullets/subtitle returning 400, and a full save-refetch round-trip.
- **Mermaid exclusion is explicit and correct:** Excluded from save payload on the frontend side, preventing accidental overwrites of diagram code.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Pre-existing unescaped class attributes should be cleaned up in a hygiene pass | All templates with dynamic class names | Consider a future cleanup task |
| Frontend conversion functions should handle trailing punctuation | Any text transformation utility | Document as known limitation in plan |
