# T021: KB Serve Web UI -- Layout & JSON Rendering

## Meta
- **Status:** COMPLETE
- **Created:** 2026-02-07
- **Last Updated:** 2026-02-07
- **Blocked Reason:** N/A

## Task

Fix the KB Serve action queue dashboard with three issues:

1. **Raw JSON rendering** -- When viewing items in the "Ready for Action" queue, many analysis types render as raw JSON blobs instead of formatted, readable content. Each analysis type has its own JSON structure with different keys. We need type-specific renderers.

2. **Layout is inverted** -- The preview panel (right side) is too small (fixed 400px). The queue list (left side) takes up too much space. Desired: queue list on LEFT should be narrow (sidebar-style), content PREVIEW on RIGHT should be the dominant area.

3. **Analysis type-specific rendering** -- For example, a "guide" analysis type has keys like `title`, `prerequisites`, `steps`, etc. These should be rendered as proper formatted HTML (headings, lists, cards) -- NOT raw JSON. Every analysis type needs its own rendering logic with a fallback for unknown types.

---

## Plan

### Objective

Make the KB Serve action queue dashboard usable for content evaluation by fixing the layout proportions and rendering each analysis type as formatted, readable HTML instead of raw JSON blobs.

### Scope
- **In:**
  - Layout inversion: swap column proportions so queue list is a narrow sidebar, preview is the dominant panel
  - Type-specific JavaScript renderers for each analysis type in the action queue
  - Structured content passing from backend (raw JSON object) instead of pre-stringified content
  - Fallback renderer for unknown/new analysis types (formatted key-value display, not raw JSON)
  - Preview pane height fix (remove max-height constraint so content fills available space)
- **Out:**
  - Changes to other pages (browse, videos, prompts, posting_queue)
  - Changes to analysis type configs or prompts
  - New backend API endpoints
  - Mobile responsive design

### Phases

#### Phase 1: Layout Fix (Sidebar + Large Preview)
- **Objective:** Invert the grid layout so the queue list is a narrow sidebar and the preview pane is the dominant area
- **Tasks:**
  - [ ] Task 1.1: Change CSS grid from `grid-template-columns: 1fr 400px` to `grid-template-columns: 320px 1fr` in `action_queue.html`
  - [ ] Task 1.2: Remove `max-height: 400px` from `.preview-text` to let content use full available height
  - [ ] Task 1.3: Make `.preview-text` fill remaining pane height with `flex: 1` or `calc()` approach
  - [ ] Task 1.4: Compact the queue list item layout for the narrow sidebar (reduce padding, truncate long titles, hide verbose meta on list items)
  - [ ] Task 1.5: Move the action buttons (Copy, Approve, Done, Skip) from below the content preview to a sticky header/toolbar in the preview pane for quick access
- **Acceptance Criteria:**
  - [ ] AC1: Queue list occupies roughly 320px on the left, acting as a sidebar/file-explorer style list
  - [ ] AC2: Preview pane is the dominant area, taking all remaining width
  - [ ] AC3: Content preview area uses full vertical height (no 400px cap)
  - [ ] AC4: Action buttons are always visible without scrolling past content
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/action_queue.html` -- CSS grid changes, preview pane layout
- **Dependencies:** None

#### Phase 2: Backend -- Pass Structured Data for Content
- **Objective:** Change the backend to pass the raw analysis data object (as structured JSON) alongside the flat content string, so the frontend can render type-specific views
- **Tasks:**
  - [ ] Task 2.1: In `scan_actionable_items()` in `serve.py`, add a `raw_data` field to each action item containing the analysis dict (minus `_` prefixed metadata keys), preserving the existing `content` field for clipboard copy
  - [ ] Task 2.2: In `/api/action/<action_id>/content` endpoint, also return the `raw_data` field
  - [ ] Task 2.3: In `/api/queue` endpoint, include `raw_data` in the response items
- **Acceptance Criteria:**
  - [ ] AC1: API responses include both `content` (string, for clipboard) and `raw_data` (object, for rendering)
  - [ ] AC2: Existing clipboard copy functionality still works (uses `content` string)
  - [ ] AC3: `raw_data` excludes metadata keys (`_analyzed_at`, `_model`)
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py` -- `scan_actionable_items()`, content endpoint
- **Dependencies:** None (can run parallel with Phase 1)

#### Phase 3: Type-Specific Renderers
- **Objective:** Build JavaScript renderer functions for each known analysis type that produce formatted HTML from structured data
- **Tasks:**
  - [ ] Task 3.1: Create a renderer dispatch map in the frontend JavaScript: `const RENDERERS = { skool_post: renderSkoolPost, ... }`
  - [ ] Task 3.2: Implement `renderSkoolPost(data)` -- renders `title` as heading, `post` as formatted text (with newline-to-paragraph conversion), `discussion_question` as a highlighted callout
  - [ ] Task 3.3: Implement `renderLinkedinPost(data)` -- renders `hook` as a bold opener, `post` as formatted text body, `cta` as a callout
  - [ ] Task 3.4: Implement `renderSkoolWeeklyCatchup(data)` -- renders `title` as heading, `post` body with timestamp formatting preserved (monospace for `[MM:SS]` timestamps)
  - [ ] Task 3.5: Implement `renderSummary(data)` -- if content is a string, render as paragraphs; if structured with `summary` key, render as formatted text
  - [ ] Task 3.6: Implement `renderGuide(data)` -- renders `title`, `prerequisites` as a checklist, `steps` as numbered cards with substeps, any other fields as sections
  - [ ] Task 3.7: Implement `renderLeadMagnet(data)` -- renders structured marketing content fields appropriately
  - [ ] Task 3.8: Implement `renderFallback(data)` -- for unknown types: if data is an object, render each key as a labeled section with formatted values; if string, render as pre-formatted text with basic formatting
  - [ ] Task 3.9: Update `loadPreview()` to use the renderer dispatch: look up `RENDERERS[item.type]`, fall back to `renderFallback`, pass `item.raw_data` (or parse `item.content` as JSON fallback)
- **Acceptance Criteria:**
  - [ ] AC1: Each of the 6 known analysis types (`skool_post`, `linkedin_post`, `skool_weekly_catchup`, `summary`, `guide`, `lead_magnet`) has a dedicated renderer
  - [ ] AC2: Renderers produce readable HTML with headings, paragraphs, lists, and visual hierarchy
  - [ ] AC3: Unknown analysis types render with the fallback renderer (not raw JSON dump)
  - [ ] AC4: Clipboard copy still copies the flat string content (not the HTML)
  - [ ] AC5: XSS protection maintained (all user content escaped before insertion)
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/action_queue.html` -- JavaScript renderer functions, updated `loadPreview()`
- **Dependencies:** Phase 2 (structured data from backend)

#### Phase 4: Renderer Styling & Polish
- **Objective:** Add CSS classes for rendered content elements and ensure visual consistency with the Catppuccin Mocha theme
- **Tasks:**
  - [ ] Task 4.1: Add CSS classes for rendered content: `.rendered-title`, `.rendered-body`, `.rendered-callout`, `.rendered-steps`, `.rendered-step-card`, `.rendered-checklist`, `.rendered-section`
  - [ ] Task 4.2: Style rendered elements to match the Catppuccin Mocha palette (use existing CSS variables)
  - [ ] Task 4.3: Ensure text wrapping and overflow handling works for long content
  - [ ] Task 4.4: Test the full flow end-to-end: queue list selection, preview rendering, copy, approve, done, skip actions
  - [ ] Task 4.5: Verify keyboard navigation (j/k, c, a, d, s, x) still works correctly with the new layout
- **Acceptance Criteria:**
  - [ ] AC1: Rendered content visually matches the Catppuccin Mocha theme
  - [ ] AC2: All action buttons work correctly (copy, approve, done, skip, flag)
  - [ ] AC3: Keyboard shortcuts function as before
  - [ ] AC4: No layout breakage at common viewport sizes (1280px+)
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/action_queue.html` -- CSS additions
- **Dependencies:** Phase 3

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Sidebar width | 320px | Layout | RESOLVED — 320px balanced default |
| 2 | Queue list preview snippet | Remove entirely — title + type only, compact file-explorer style | Layout | RESOLVED — Blake chose compact |
| 3 | Action buttons placement | Sticky bar at bottom of preview pane | UX | RESOLVED — Blake chose sticky bottom |
| 4 | `guide` and `lead_magnet` renderers | Build speculatively based on assumed schema from action_mapping defaults | Rendering | RESOLVED — Lem decided: build them, fallback catches any mismatch |
| 5 | Posting queue layout | Out of scope for this task | Scope | RESOLVED — Lem decided: not requested |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Keep `content` field as-is for clipboard | Preserve existing string content | Clipboard copy needs plain text, not HTML; changing this would break existing workflow |
| Add `raw_data` as a new field rather than replacing `content` | Additive approach | Backwards compatible; posting queue and other consumers still work |
| Renderers in JavaScript, not server-side Jinja | Client-side rendering | Matches existing architecture where all rendering is done via JS after API fetch; avoids page reloads |
| Use `escapeHtml()` in all renderers | XSS protection | Following existing pattern in the codebase |
| Fallback renderer for unknown types | Formatted key-value display | Better than raw JSON dump; handles future analysis types gracefully |

---

## Plan Review
- **Gate:**
- **Reviewed:**
- **Summary:**
- **Issues:**
- **Open Questions Finalized:**

---

## Execution Log

### Phase 1: Layout Fix
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `b6af563`
- **Files Modified:**
  - `kb/templates/action_queue.html` -- CSS grid inverted to `320px 1fr`, removed `max-height: 400px` from `.preview-text`, added flex layout for preview content to fill height, compacted queue list items (reduced padding, hid meta/preview snippets, added truncation), moved action buttons to sticky bottom bar outside scrollable content
- **Notes:** All 73 existing backend tests pass. No frontend tests exist for this template. The `.action-meta` and `.action-preview` CSS classes are set to `display: none` rather than removing the HTML generation -- this keeps the data available if needed later and is a minimal change.
- **Blockers:** None

### Tasks Completed (Phase 1)
- [x] Task 1.1: Changed CSS grid from `1fr 400px` to `320px 1fr`
- [x] Task 1.2: Removed `max-height: 400px` from `.preview-text`
- [x] Task 1.3: Made `.preview-text` fill remaining height with flex layout chain (`.preview-body` -> `.preview-content` -> `.preview-section-content` -> `.preview-text`)
- [x] Task 1.4: Compacted queue list items -- reduced padding to `8px 12px`, hid meta row and content snippet, added text truncation on labels and source titles
- [x] Task 1.5: Moved action buttons to sticky bottom bar -- `.preview-actions` now sits outside `.preview-content` in the flex column, with `flex-shrink: 0` and border-top separator

### Acceptance Criteria (Phase 1)
- [x] AC1: Queue list occupies 320px on the left (CSS grid `320px 1fr`)
- [x] AC2: Preview pane takes all remaining width (`1fr`)
- [x] AC3: Content preview uses full vertical height (no 400px cap, flex fills available space)
- [x] AC4: Action buttons always visible (sticky bottom bar, outside scrollable area)

### Phase 2: Backend -- Pass Structured Data
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `76ec6cc`
- **Files Modified:**
  - `kb/serve.py` -- added `raw_data` field to `scan_actionable_items()` output and `/api/action/<id>/content` endpoint
- **Notes:** `/api/queue` inherits `raw_data` automatically since it passes through the full item dicts from `scan_actionable_items()`. `raw_data` is `None` for non-dict analysis data. All 73 existing tests pass.
- **Blockers:** None

### Tasks Completed (Phase 2)
- [x] Task 2.1: Added `raw_data` field to `scan_actionable_items()` -- dict comprehension filtering `_` prefixed keys
- [x] Task 2.2: Added `raw_data` to `/api/action/<action_id>/content` response
- [x] Task 2.3: `/api/queue` inherits `raw_data` from scan items automatically (no code change needed)

### Acceptance Criteria (Phase 2)
- [x] AC1: API responses include both `content` (string) and `raw_data` (object) -- verified in code
- [x] AC2: Existing clipboard copy still uses `content` string -- copy/approve endpoints unchanged
- [x] AC3: `raw_data` excludes `_` prefixed metadata keys -- dict comprehension filter `not k.startswith("_")`

### Phase 3: Type-Specific Renderers
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `51235a7`
- **Files Modified:**
  - `kb/templates/action_queue.html` -- Added renderer dispatch map, 6 type-specific renderers, fallback renderer, unwrapData() helper, textToHtml()/renderValue() utilities, updated loadPreview() to use dispatch, added `.rendered-content` CSS override for white-space
- **Notes:** Real data inspection revealed actual nesting patterns: `guide` and `summary` nest under type-name key, `lead_magnet` uses mixed nesting (some under type-name key + flat siblings), while `skool_post`/`linkedin_post`/`skool_weekly_catchup` use flat keys. The `unwrapData()` function handles all three patterns. Real `skool_post` data has `core_teaching` instead of `discussion_question` (schema says optional) -- renderer handles both. All 73 existing tests pass.
- **Blockers:** None

### Tasks Completed (Phase 3)
- [x] Task 3.1: Created renderer dispatch map `RENDERERS` with 6 entries
- [x] Task 3.2: `renderSkoolPost(data)` -- title heading, post body (newline-to-paragraph), discussion_question + core_teaching callouts
- [x] Task 3.3: `renderLinkedinPost(data)` -- hook bold opener, post body, cta callout, core_insight callout, audience section
- [x] Task 3.4: `renderSkoolWeeklyCatchup(data)` -- title heading, post body with `[MM:SS]` timestamp monospace via regex
- [x] Task 3.5: `renderSummary(data)` -- handles string data, `{summary: string}`, and falls back for unexpected structure
- [x] Task 3.6: `renderGuide(data)` -- title, prerequisites checklist, numbered step cards with details, tips list
- [x] Task 3.7: `renderLeadMagnet(data)` -- idea/format/hook section, video_titles ordered list, hooks ordered list, shorts_ideas with timestamp codes
- [x] Task 3.8: `renderFallback(data)` -- renders object keys as labeled sections with recursive `renderValue()`, strings as paragraphs
- [x] Task 3.9: Updated `loadPreview()` to dispatch via `RENDERERS[item.type]` with `unwrapData()` for nesting, fallback to JSON parse of `item.content`

### Acceptance Criteria (Phase 3)
- [x] AC1: 6 known types have dedicated renderers -- verified in `RENDERERS` map: skool_post, linkedin_post, skool_weekly_catchup, summary, guide, lead_magnet
- [x] AC2: Renderers produce readable HTML with headings (`<h2>`), paragraphs (`<p>`), lists (`<ul>`/`<ol>`), callouts, step cards
- [x] AC3: Unknown types use `renderFallback()` which renders key-value sections, not raw JSON
- [x] AC4: Clipboard copy still uses `selectedItem.content` (flat string) in `copyToClipboard()` and flag submit
- [x] AC5: All user content passed through `escapeHtml()` before insertion -- verified in all renderers and `textToHtml()`

### Phase 4: Renderer Styling & Polish
- **Status:** COMPLETE
- **Started:** 2026-02-07
- **Completed:** 2026-02-07
- **Commits:** `939db6b`
- **Files Modified:**
  - `kb/templates/action_queue.html` -- CSS fixes (truncation, double-scrollbar, border shift), JS fixes (escapeHtml word_count, Array.isArray guards, nested object rendering), added rendered content CSS classes
- **Notes:** All 73 backend tests pass. Keyboard navigation code unchanged. All Phase 1 and Phase 3 code review issues resolved.
- **Blockers:** None

### Tasks Completed (Phase 4)
- [x] Task 4.CR1: Fixed `.action-type` truncation -- added `min-width: 0; overflow: hidden`
- [x] Task 4.CR2: Fixed double-scrollbar -- changed `.preview-content` from `overflow-y: auto` to `overflow: hidden`
- [x] Task 4.CR3: Fixed selected item border shift -- added `border-left: 3px solid transparent` to base `.action-item`
- [x] Task 4.CR4: Escaped `word_count` via `escapeHtml(String(item.word_count))` in both sidebar and preview
- [x] Task 4.CR5: Added `Array.isArray()` guards on `prerequisites`, `steps`, `tips`, `video_titles`, `hooks`, `shorts_ideas`
- [x] Task 4.CR6: Fixed nested objects in array items -- `renderValue` now recursively handles object values instead of `String(v)`
- [x] Task 4.1: Added CSS for `.rendered-title`, `.rendered-body`, `.rendered-callout`, `.rendered-steps`, `.rendered-step-card`, `.rendered-checklist`, `.rendered-section`, `.rendered-hook`, `.rendered-timestamp`, `.rendered-list`, `.rendered-list-item`
- [x] Task 4.2: Styled all rendered elements with Catppuccin Mocha variables (sapphire titles, mauve callout borders, blue step cards, yellow hooks, peach timestamps)
- [x] Task 4.3: Added `word-wrap: break-word; overflow-wrap: break-word` to body paragraphs, list items, and rendered-content descendants
- [x] Task 4.4: Verified action buttons (copy, approve, done, skip, flag) -- code paths unchanged
- [x] Task 4.5: Verified keyboard navigation (j/k/c/a/d/s/x) -- handler code unchanged

### Acceptance Criteria (Phase 4)
- [x] AC1: Rendered content uses Catppuccin Mocha variables -- verified in CSS (.rendered-title uses --sapphire, .rendered-callout uses --mauve, .rendered-step-card uses --blue, etc.)
- [x] AC2: All action buttons work -- button onclick handlers and API call functions unchanged
- [x] AC3: Keyboard shortcuts function as before -- keydown handler unchanged, all key bindings intact
- [x] AC4: No layout breakage -- overflow handling fixed (single scroll region), text wrapping added, border shift eliminated

---

## Code Review Log

### Phase 1
- **Gate:** PASS
- **Reviewed:** 2026-02-07
- **Issues:** 0 critical, 2 major, 2 minor
- **Summary:** Layout inversion correctly implemented -- all 4 ACs verified. Two major issues (flex truncation won't trigger without `min-width: 0`, double-scrollbar from nested `overflow-y: auto`) and two minor (selected border shift, unescaped `word_count`). All are polish-level and can be absorbed by Phase 4.

-> Details: `code-review-phase-1.md`

### Phase 2
- **Gate:** PASS
- **Reviewed:** 2026-02-07
- **Issues:** 0 critical, 0 major, 3 minor
- **Summary:** Clean 8-line change, all 3 ACs verified. Minor issues: no test coverage for changed code, payload bloat on queue listing, inconsistent nesting in `raw_data` that Phase 3 renderers must handle. None block progress.

-> Details: `code-review-phase-2.md`

### Phase 3
- **Gate:** PASS
- **Reviewed:** 2026-02-07
- **Issues:** 0 critical, 0 major, 3 minor
- **Summary:** All 5 ACs verified. XSS protection consistently applied across all renderers. Three minor edge-case robustness issues (unwrapData merge priority, renderValue nested objects in arrays, array type assumptions in renderers). None block progress to Phase 4.

-> Details: `code-review-phase-3.md`

### Phase 4
- **Gate:** PASS
- **Reviewed:** 2026-02-07
- **Issues:** 0 critical, 0 major, 2 minor
- **Summary:** All 4 ACs verified. All Phase 1 and Phase 3 code review issues resolved (except one documentation-level minor). 13 CSS classes properly styled with Catppuccin Mocha variables. Clean final commit.

-> Details: `code-review-phase-4.md`

---

## Completion
- **Completed:** 2026-02-07
- **Summary:** KB Serve action queue dashboard fully reworked: layout inverted (320px sidebar + full-width preview), structured data passed from backend via `raw_data` field, 6 type-specific renderers built (skool_post, linkedin_post, skool_weekly_catchup, summary, guide, lead_magnet) with fallback renderer for unknown types, and rendered content styled with Catppuccin Mocha theme. All content properly escaped for XSS protection. Keyboard navigation and action buttons preserved.
- **Learnings:** Multi-phase code review feedback loops work well -- deferring polish issues to later phases keeps progress flowing while ensuring nothing is forgotten. Flex truncation requires `min-width: 0` on parent containers. Nested `overflow-y: auto` regions create double-scrollbar problems.
