# Code Review: Phase 1

## Gate: PASS

**Summary:** The layout inversion is correctly implemented. The grid swap, flex chain, compacted sidebar, and sticky action bar all deliver the four acceptance criteria. Four issues found -- two major (truncation won't fire, double-scrollbar risk) and two minor (selection jitter, unescaped word_count). None are blockers for Phase 1 since they are polish-level problems that Phase 4 (styling and polish) can absorb.

---

## Git Reality Check

**Commits:**
```
b6af563 Phase1: fix action queue layout -- sidebar + large preview
```

**Files Changed:**
- `kb/templates/action_queue.html`

**Matches Execution Report:** Yes. Single file, single commit, matches exactly.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: Queue list 320px sidebar | Yes | Yes | `grid-template-columns: 320px 1fr` confirmed at line 56 |
| AC2: Preview takes remaining width | Yes | Yes | `1fr` takes remaining space |
| AC3: No 400px cap, full vertical height | Yes | Yes | `max-height: 400px` removed, flex chain fills height |
| AC4: Action buttons always visible | Yes | Yes | `.preview-actions` is outside `.preview-content` in the flex column with `flex-shrink: 0` |

---

## Issues Found

### Critical
None.

### Major

1. **`.action-label` text-overflow truncation will never trigger**
   - File: `kb/templates/action_queue.html:175-182`
   - Problem: `.action-label` has `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` but it is inside `.action-type` (a flex container child of `.action-item-header` with `justify-content: space-between`). The `.action-type` div has no `min-width: 0` and no `overflow: hidden`. In flexbox, children default to `min-width: auto`, so `.action-type` will expand to fit its content, never allowing `.action-label` to truncate. Long action type names will push the destination badge off-screen or cause horizontal overflow in the 320px sidebar.
   - Fix: Add `min-width: 0; overflow: hidden;` to `.action-type` (line 165-168).

2. **Double-scrollbar risk from competing overflow regions**
   - File: `kb/templates/action_queue.html:238-244` and `kb/templates/action_queue.html:272-278`
   - Problem: `.preview-content` has `overflow-y: auto` (outer scroll) and `.preview-text` inside `.preview-section-content` (which has `overflow: hidden`) also has `overflow-y: auto` (inner scroll). This creates two nested scrollable regions. When content is tall, users may see two scrollbars -- the outer one for `.preview-content` and the inner one for `.preview-text`. The intent is clearly for only `.preview-text` to scroll while action buttons stay pinned, but the outer `overflow-y: auto` on `.preview-content` defeats this by scrolling the meta grid and title away too.
   - Fix: Either (a) change `.preview-content` from `overflow-y: auto` to `overflow: hidden` so only `.preview-text` scrolls, or (b) remove scroll from `.preview-text` and let `.preview-content` be the single scroll container (but then the meta grid scrolls away). Option (a) is cleaner for the stated goal.

### Minor

1. **Selected item border-left causes 3px content shift** -- `.action-item.selected` adds `border-left: 3px solid var(--green)` but the base `.action-item` has no left border. This causes a 3px rightward shift of all content when an item is selected, creating visible jitter during keyboard navigation. Fix: add `border-left: 3px solid transparent` to `.action-item`.

2. **`word_count` not escaped in preview meta grid** -- Line 917: `` ~${item.word_count} words `` uses raw interpolation. Every other dynamic field in the preview uses `escapeHtml()`. While `word_count` is likely always numeric, this is an inconsistency with the XSS protection pattern used everywhere else. Fix: use `escapeHtml(String(item.word_count))`.

---

## What's Good

- The flex chain from `.preview-body` down to `.preview-text` is structurally sound -- the intent is correct and will work once the double-scroll is resolved.
- Moving `.preview-actions` outside `.preview-content` is the right architectural choice for sticky buttons.
- Using `display: none` instead of removing the `.action-meta` and `.action-preview` HTML preserves data for later phases -- pragmatic decision.
- All backend tests (73/73) pass.
- XSS protection via `escapeHtml()` is consistently applied (with the one `word_count` exception noted).

---

## Required Actions (for Phase 4 -- these are polish items)

- [ ] Fix `.action-type` to add `min-width: 0; overflow: hidden` so text truncation works
- [ ] Resolve double-scrollbar: change `.preview-content` `overflow-y: auto` to `overflow: hidden`
- [ ] Add `border-left: 3px solid transparent` to base `.action-item`
- [ ] Escape `word_count` in the meta grid template

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Flex children need `min-width: 0` for text truncation to work | Any flex-based truncation | Verify in future CSS reviews |
| Nested `overflow-y: auto` creates double-scrollbar UX problems | Flex layout chains | Audit scroll containers when nesting flex columns |
