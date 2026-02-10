# Plan Review: T026 Phase 7 -- KB Serve Frontend Fixes

## Round 2 Review

## Gate Decision: READY

**Summary:** All 5 round 1 issues (2 critical, 3 major) are genuinely resolved in the revision. Format dropdown is now fully specified with conversion logic and 4 new ACs. canGenerate is properly split into two variables. Mermaid save exclusion, template-only switching, and paragraph-to-bullets behavior are all explicitly addressed. Only minor implementation notes remain, none of which should block execution.

---

## Round 1 Issue Verification

### CRITICAL #1: Format dropdown -- RESOLVED

Evidence in revision:
- Phase 1 Task 1.4: `convertContentForFormatChange(text, oldFormat, newFormat)` helper with explicit rules for all conversions (bullets-to-paragraph joins with `. `, paragraph-to-bullets splits by `\n`, single-line becomes one bullet)
- Phase 2 Task 2.2: Full `<select>` dropdown per content slide with `onchange` handler that calls the conversion function and updates textarea content
- Phase 1 Task 1.2: `editableTextToSlideFields()` now takes `selectedFormat` parameter from the dropdown, not from `slide.format`
- Phase 2 ACs 6-9: Cover format switching behavior, content conversion, and persistence
- Decision Matrix "Decisions Made" row: Documents paragraph-to-bullets as "single-line paragraph becomes one bullet"

Verified against source: Current `buildSlideEditorHtml()` at line 1881 has no format dropdown. Plan correctly adds one.

### CRITICAL #2: canGenerate split -- RESOLVED

Evidence in revision:
- Phase 4 Task 4.1: Explicit split into `canGenerate = status === 'staged' && !isGenerating` and `canReRender = (status === 'staged' || status === 'ready' || visualStatus === 'stale') && !isGenerating`
- Phase 4 Task 4.2: Maps each variable to the correct button HTML
- Phase 4 ACs 1-2: "When ready, Re-render enabled but Generate Visuals disabled" and "When staged, both enabled"
- Decision Matrix: Documents the rationale (generateVisuals internal guard would create misleading UX)

Verified against source: `generateVisuals()` at line 1664 has `status !== 'staged'` guard, confirming the split is necessary. Current `canGenerate` at line 1535 indeed controls both buttons.

### MAJOR #3: Mermaid save exclusion -- RESOLVED

Evidence in revision:
- Phase 2 Task 2.5: "Exclude mermaid slides from save collection entirely (mermaid textareas are readonly, so there is nothing to save; including them risks sending malformed data without a format field)"
- Phase 2 AC9: "Mermaid slides are excluded from the save payload"
- Decision Matrix: "Mermaid in save flow: Exclude mermaid slides from save collection"
- Phase 1 Task 1.2 also lists mermaid handling: returns `{content: text}` as pass-through

Both approaches are documented -- exclusion in save AND pass-through in the serializer. Belt and suspenders.

### MAJOR #4: Template-only switch -- RESOLVED

Evidence in revision:
- Phase 4 AC5: "Template-only switch (no save, just pick new template and re-render) works correctly: re-render does NOT require a save first, and the item transitions back to ready status after render completes (confirmed: render endpoint line 929 sets status = 'ready')"
- Phase 5 Task 5.3: "Test template-only switch (no content edits): from ready status, change template dropdown, click Re-render directly WITHOUT saving first. Verify render succeeds and item returns to ready status (no status downgrade to staged)"

Verified against source: Render endpoint at line 861 accepts `staged` or `ready`. Line 929 sets status to `ready` after successful render. `reRender()` at line 1847 does not call save first. Workflow is correct.

### MAJOR #5: Paragraph-to-bullets behavior -- RESOLVED

Evidence in revision:
- Phase 1 Task 1.4: "paragraph to bullets/numbered: split by `\n`, if only one line (no newlines), keep as single bullet (user can manually add line breaks to create more bullets)"
- Phase 1 AC4: Tests the conversion function
- Phase 5 Task 5.6: "single-line paragraph converted to bullets (becomes one bullet)"
- Decision Matrix: "Paragraph-to-bullets conversion: Split by newline; single-line paragraph becomes one bullet. Keep it simple. User can manually add newlines to create more bullets before switching format. Sentence-splitting is fragile and surprising."

Pragmatic and well-reasoned approach.

---

## Round 1 Minor Issues (also addressed)

- **Minor #6 (format dropdown ACs):** Now has ACs 6-9 covering format switching.
- **Minor #7 (validation specifics):** Task 3.3 now lists `["bullets", "numbered", "paragraph"]` explicitly.
- **Minor #8 (content fallback):** Task 1.2 and Task 3.2 both document setting `content = bullets.join('. ')` as fallback. Decision Matrix row confirms the rationale.

All 8 original issues resolved.

---

## New Issues (Round 2)

### Minor

**1. Format dropdown onchange needs oldFormat tracking**

Phase 2 Task 2.2's `onchange` handler calls `convertContentForFormatChange(text, oldFormat, newFormat)`. The standard DOM `onchange` fires AFTER the select value has changed, so `this.value` is the new value. The handler needs a way to know the previous format -- either via a `data-current-format` attribute on the select that gets updated after each change, or by reading the slide's original format from `slidesData`.

Impact: Low. The executor will notice this during implementation. The plan's intent is clear even if the tracking mechanism is not specified. This is a normal implementation detail.

**2. editableTextToSlideFields selectedFormat parameter for non-content slides**

Phase 1 Task 1.2 takes `selectedFormat` as a parameter, but hook/CTA/mermaid slides have no format dropdown. The function should check `slide.type` first and only use `selectedFormat` for content slides. The plan implies this (listing separate handling per type) but does not explicitly state that `selectedFormat` is ignored for non-content types.

Impact: Low. The function signature and per-type handling make the intent obvious.

**3. canReRender includes redundant visualStatus check**

`canReRender = (status === 'staged' || status === 'ready' || visualStatus === 'stale') && !isGenerating`. The `visualStatus === 'stale'` case is redundant because the save endpoint always sets BOTH `status = 'staged'` and `visual_status = 'stale'` together (serve.py lines 830-832). So `status === 'staged'` already covers the stale case.

Impact: None. Redundant but harmless. Defensive coding is fine.

---

## Plan Strengths

- All round 1 issues addressed thoroughly with specific task descriptions, ACs, and Decision Matrix entries
- Root cause analyses remain accurate -- every line reference verified against actual source code
- Phase sequencing is logical: data layer (Phase 1) -> UI (Phase 2) -> backend (Phase 3) -> button logic (Phase 4) -> integration testing (Phase 5)
- Phase 4 can be done in parallel with Phases 1-3 as correctly noted
- Backwards compatibility explicitly handled (old slides without `bullets` array)
- The Decision Matrix "Decisions Made" section is comprehensive and well-reasoned
- Format conversion approach (paragraph-to-bullets = split by newline, single line = one bullet) is the simplest correct solution
- Two-file scope keeps the risk low

---

## Recommendations

### During Implementation (not blocking)
- [ ] Track previous format value on the format dropdown select (e.g., `data-current-format` attribute) so `convertContentForFormatChange` gets the correct `oldFormat`
- [ ] In `editableTextToSlideFields`, add an early return for non-content slide types before checking `selectedFormat`
