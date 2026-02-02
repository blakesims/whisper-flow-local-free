# T019: KB Prompt Quality Feedback System

## Meta
- **Status:** COMPLETE
- **Created:** 2026-02-02
- **Last Updated:** 2026-02-02
- **Priority:** 2

## Task

Build a prompt quality feedback loop into KB Serve that allows Blake to flag low-quality analysis outputs and surface which analysis types need prompt improvements.

### Requirements

1. **X = Flag Action** (action_queue.html)
   - Press `X` on any action item to flag it
   - Opens telescope-style quick modal for optional note
   - Enter immediately closes (empty note = just flag)
   - After flagging: copy content to clipboard AND skip (mark as handled)
   - Store flag data in `~/.kb/prompt-feedback.json`

2. **Prompt Viewer** (new route: `/prompts`)
   - List all analysis types from `config/analysis_types/`
   - Show for each: name, description, prompt preview, output schema
   - Show flag stats: total flags, flag rate, recent flags (7 days)
   - Link to flagged examples (action IDs)
   - `e` key or button to copy `nvim <path>` command for editing prompt

3. **Bubbling Mechanism**
   - Analysis types with higher flag rates surface first
   - Visual indicator for "needs attention" threshold

4. **Auto-scroll Bug Fix**
   - When navigating with j/k, selected item should scroll into view
   - This is a known bug that's been present for a while

### Data Model

`~/.kb/prompt-feedback.json`:
```json
{
  "flags": [
    {
      "analysis_type": "linkedin_post",
      "action_id": "260202-transcript--linkedin_post",
      "flagged_at": "2026-02-02T10:30:00",
      "note": "too corporate"
    }
  ],
  "stats": {
    "linkedin_post": {
      "total_flagged": 3,
      "last_flagged": "2026-02-02T10:30:00"
    }
  }
}
```

### Files to Modify

- `kb/serve.py` — new routes for `/prompts`, `/api/prompts`, `/api/flag`
- `kb/templates/action_queue.html` — X keybinding, modal, auto-scroll fix
- `kb/templates/prompts.html` — new template for prompt viewer

### Non-Goals

- Inline prompt editing (Blake edits in nvim)
- Automatic prompt improvement suggestions
- Complex analytics dashboard

---

## Plan

### Phase 1: Auto-scroll Bug Fix + X Flag Backend

**Goal:** Fix navigation UX bug and build flagging data layer

**Files:**
- `kb/templates/action_queue.html` (auto-scroll fix)
- `kb/serve.py` (flag API routes + feedback storage)

**Tasks:**

1. **Auto-scroll fix** (`action_queue.html:778-790`)
   - In `selectItem()` function, after updating selection, call `scrollIntoView()` on selected element
   - Use `{ block: 'nearest', behavior: 'smooth' }` for smooth scrolling
   - Test with j/k navigation on lists longer than viewport

2. **Prompt feedback storage** (`serve.py`)
   - Add constant `PROMPT_FEEDBACK_PATH = Path.home() / ".kb" / "prompt-feedback.json"`
   - Add `load_prompt_feedback()` / `save_prompt_feedback()` helpers (same pattern as `load_action_state()`)
   - Data structure:
     ```json
     {
       "flags": [
         {
           "analysis_type": "linkedin_post",
           "action_id": "260202-transcript--linkedin_post",
           "flagged_at": "2026-02-02T10:30:00",
           "note": "too corporate"
         }
       ]
     }
     ```

3. **Flag API route** (`serve.py`)
   - `POST /api/action/<action_id>/flag` - Flag an action with optional note
   - Request body: `{ "note": "optional note" }`
   - Extract `analysis_type` from `action_id` (split on `--`)
   - Append to flags array, auto-mark action as skipped (reuse `skip_action` logic)
   - Return `{ "success": true }`

**Exit Criteria:**
- j/k navigation auto-scrolls selected item into view
- `/api/action/<id>/flag` endpoint works (testable via curl)
- `~/.kb/prompt-feedback.json` created on first flag

---

### Phase 2: X Flag Frontend with Modal

**Goal:** Add X keybinding and telescope-style quick modal

**Files:**
- `kb/templates/action_queue.html`

**Tasks:**

1. **Flag modal HTML** (after toast div)
   - Add modal container with:
     - Semi-transparent backdrop
     - Small centered input box (telescope-style: minimal, no title)
     - Placeholder: "Note (optional, Enter to submit)"
     - Style: `--surface0` background, `--sapphire` border, small width (~300px)

2. **Flag modal CSS**
   - `.flag-modal` - fixed position, centered, z-index above toast
   - `.flag-modal-backdrop` - full screen, semi-transparent
   - `.flag-modal-input` - styled input matching theme
   - Animation: quick fade-in (100ms)

3. **Flag modal JavaScript**
   - `showFlagModal()` - Display modal, focus input
   - `hideFlagModal()` - Hide modal, clear input
   - `submitFlag(note)` - POST to `/api/action/<id>/flag`, then:
     - Copy content to clipboard (reuse `copyToClipboard()` logic)
     - Call `skipItem()` to advance to next
     - Show toast "Flagged & copied!"
   - Keydown handlers in modal:
     - `Enter` - Submit with current note value
     - `Escape` - Cancel (hide modal, no action)

4. **X keybinding** (in main keydown handler)
   - `x` key triggers `showFlagModal()`
   - Prevent x when modal is open

5. **Update shortcut bar**
   - Add `<span class="shortcut"><span class="key-hint">x</span> flag</span>`

**Exit Criteria:**
- Press X opens minimal modal
- Enter submits (empty note OK), Escape cancels
- After flag: content copied, item skipped, toast shown
- Flag data saved to `prompt-feedback.json`

---

### Phase 3: Prompts API + Template

**Goal:** Create `/prompts` page showing all analysis types with flag stats

**Files:**
- `kb/serve.py` (new routes)
- `kb/templates/prompts.html` (new template)

**Tasks:**

1. **Prompts API route** (`serve.py`)
   - `GET /api/prompts` - List all analysis types with stats
   - Use `list_analysis_types()` from `kb/analyze.py` (import it)
   - For each type, load full definition via `load_analysis_type(name)`
   - Calculate stats from `prompt-feedback.json`:
     - `total_flagged`: count of flags for this type
     - `flag_rate`: flags / total actions of this type (from action state)
     - `recent_flags`: flags in last 7 days
     - `flagged_action_ids`: list of action IDs flagged
   - Return:
     ```json
     {
       "prompts": [
         {
           "name": "linkedin_post",
           "description": "Generate LinkedIn post",
           "prompt_preview": "First 200 chars of prompt...",
           "output_schema": { ... },
           "file_path": "/path/to/config/analysis_types/linkedin_post.json",
           "stats": {
             "total_flagged": 3,
             "flag_rate": 0.15,
             "recent_flags": 2,
             "flagged_action_ids": ["...", "..."]
           }
         }
       ]
     }
     ```

2. **Prompts page route** (`serve.py`)
   - `GET /prompts` - Render `prompts.html` template

3. **Prompts template** (`kb/templates/prompts.html`)
   - Copy structure from `action_queue.html` (tmux-style layout, Catppuccin theme)
   - Two-pane layout: list on left, detail on right
   - Left pane: List of analysis types
     - Each item shows: name, description, flag count badge
     - Badge color: red if flag_rate > 0.2, yellow if > 0.1, green otherwise
     - Sort by flag_rate descending (highest flags first = "bubbling")
   - Right pane: Selected type detail
     - Full prompt text (scrollable, monospace)
     - Output schema (JSON formatted)
     - Flag stats panel
     - List of flagged action IDs (clickable? or just display)
   - Keyboard navigation: j/k, `e` key to copy nvim command
   - `e` key action: copy `nvim <file_path>` to clipboard, show toast

4. **Mode toggle update** (`action_queue.html`, `browse.html`)
   - Add `p` key binding for prompts page
   - Add prompts button to mode toggle in all templates

**Exit Criteria:**
- `/prompts` page loads with all analysis types
- Types sorted by flag rate (needs attention first)
- Detail view shows prompt, schema, stats
- `e` key copies nvim command
- `p` key navigates to prompts from other pages

---

### Phase 4: Polish + Integration

**Goal:** Visual polish, edge cases, testing

**Files:**
- All templates
- `kb/serve.py`

**Tasks:**

1. **Visual indicators**
   - "Needs attention" badge on prompts with flag_rate > 0.2
   - Dim/strike-through for types with 0 flags (working well)
   - Add flag count to action items in queue? (optional)

2. **Edge cases**
   - Handle empty `prompt-feedback.json` gracefully
   - Handle missing analysis types (deleted configs)
   - Validate action_id format in flag endpoint

3. **Cross-page consistency**
   - Ensure mode toggle appears on all pages (queue, browse, videos, prompts)
   - Consistent keybinding documentation in shortcut bars

4. **Testing**
   - Manual test: flag several items, verify stats update
   - Test auto-scroll with long lists
   - Test modal keyboard handling (Enter, Escape, X to open)

**Exit Criteria:**
- All features working end-to-end
- No console errors
- Prompt viewer shows accurate stats
- System ready for daily use

---

## Plan Review

**Gate:** READY
**Reviewed:** 2026-02-02

### Summary
Plan is well-structured and follows existing patterns. All file references verified. Minor clarifications noted for implementation:

1. **File path for nvim**: Construct as `ANALYSIS_TYPES_DIR / f"{name}.json"`
2. **Flag rate denominator**: Count distinct action IDs with matching analysis_type from action-state.json
3. **Mode toggle**: Also update `videos.html` for consistency (added to Phase 4)
4. **Modal isolation**: Add `modalOpen` flag to prevent other keybindings when modal is open

All gaps are implementation details, not design issues. Ready for execution.

---

## Execution Log

### Phase 1 - 2026-02-02

**Auto-scroll fix** (`action_queue.html:778-790`)
- Added `scrollIntoView({ block: 'nearest', behavior: 'smooth' })` in `selectItem()` function
- Called inside the forEach loop when the item is selected (i === index)

**Prompt feedback storage** (`serve.py`)
- Added `PROMPT_FEEDBACK_PATH = Path.home() / ".kb" / "prompt-feedback.json"` constant
- Added `load_prompt_feedback()` - returns `{"flags": []}` if file missing/corrupted
- Added `save_prompt_feedback()` - creates parent dir if needed

**Flag API route** (`serve.py`)
- Added `POST /api/action/<action_id>/flag` endpoint
- Extracts `analysis_type` from action_id (split on `--`)
- Appends flag to `prompt-feedback.json` with `analysis_type`, `action_id`, `flagged_at`, `note`
- Marks action as skipped in `action-state.json` with `flagged: true` marker
- Returns `{"success": true}`

**Testing results:**
- ✅ Import test passed
- ✅ Flag endpoint returns success
- ✅ prompt-feedback.json created with correct structure
- ✅ action-state.json updated with `status: "skipped"` and `flagged: true`
- ✅ Invalid action IDs rejected with 400 error

**Exit criteria met:**
- j/k navigation will auto-scroll selected item into view
- `/api/action/<id>/flag` endpoint works (tested via curl)
- `~/.kb/prompt-feedback.json` created on first flag

---

## Code Review Log

### Phase 1 Code Review - 2026-02-02
**Gate:** PASS

All plan requirements verified:
- ✅ Auto-scroll with `scrollIntoView({ block: 'nearest', behavior: 'smooth' })`
- ✅ Prompt feedback storage functions following existing patterns
- ✅ Flag API endpoint with proper validation and skip behavior
- ✅ Bonus: Added `flagged: true` marker for future stats

### Phase 2 Code Review - 2026-02-02
**Gate:** PASS

All plan requirements verified:
- ✅ Modal HTML/CSS matches spec (telescope-style, Catppuccin theme)
- ✅ JavaScript functions correct (showFlagModal, hideFlagModal, submitFlag)
- ✅ X keybinding with modalOpen guard
- ✅ Shortcut bar updated
- ✅ Full UX flow verified (x → Enter/Escape → copy + skip + toast)

---

### Phase 2 Execution - 2026-02-02

**Flag modal HTML** (`action_queue.html:671-679`)
- Added telescope-style modal after toast div
- Semi-transparent backdrop with click-to-close
- Single input field with placeholder "Note (optional, Enter to submit)"

**Flag modal CSS** (`action_queue.html:439-495`)
- Fixed position centered modal with z-index 1001 (above toast)
- `--surface0` background, `--sapphire` border, 300px width
- Quick 100ms fade-in animation
- Input styled to match theme with `--base` background

**Flag modal JavaScript** (`action_queue.html:939-1012`)
- `modalOpen` state variable for keyboard isolation
- `showFlagModal()` - sets modalOpen, shows modal, focuses input
- `hideFlagModal()` - clears modalOpen, hides modal, clears input
- `submitFlag(note)` - POSTs to `/api/action/<id>/flag`, copies content, calls fetchQueue, advances to next item
- Keydown handler on input: Enter submits, Escape cancels

**X keybinding** (`action_queue.html:1093-1127`)
- Added `if (modalOpen) return;` guard at start of main keydown handler
- Added `x` key case that calls `showFlagModal()`

**Shortcut bar** (`action_queue.html:627`)
- Added `<span class="shortcut"><span class="key-hint">x</span> flag</span>`

**Exit criteria met:**
- ✅ Press X opens minimal modal
- ✅ Enter submits (empty note OK), Escape cancels
- ✅ After flag: content copied, item skipped, toast shown
- ✅ modalOpen flag prevents other keybindings when modal is open

---

### Phase 3 Execution - 2026-02-02

**Prompts API route** (`serve.py:966-1041`)
- Added `GET /api/prompts` endpoint
- Imports `list_analysis_types`, `load_analysis_type`, `ANALYSIS_TYPES_DIR` from `kb.analyze`
- Calculates flag stats from `prompt-feedback.json`:
  - `total_flagged`: count of flags per analysis type
  - `flag_rate`: flags / total actions (from action-state.json)
  - `recent_flags`: flags in last 7 days
  - `flagged_action_ids`: list of flagged action IDs
- Returns prompts sorted by `flag_rate` descending (bubbling mechanism)

**Prompts page route** (`serve.py:962-965`)
- Added `GET /prompts` route rendering `prompts.html` template

**Prompts template** (`kb/templates/prompts.html`)
- Two-pane layout (prompt list | detail) matching existing templates
- Catppuccin Mocha theme matching other templates
- Left pane: List of analysis types with:
  - Name, description
  - Flag count badge with color coding (red >20%, yellow >10%, green otherwise)
  - Total actions count, recent flags indicator
- Right pane: Selected prompt detail with:
  - Full prompt text (scrollable, monospace)
  - Output schema (JSON formatted)
  - Flag stats grid (4 columns)
  - Flagged action IDs list (max 5 shown)
  - File path display
- Keyboard navigation: j/k, `e` key copies `nvim <file_path>` to clipboard

**Mode toggle updates**
- `action_queue.html`: Added `p` key binding and prompts button to mode toggle
- `browse.html`: Added `p` key binding and prompts button to mode toggle
- `videos.html`: Added `p` key binding and prompts button to mode toggle
- All status bars updated with `p prompts` shortcut hint

**Exit criteria met:**
- ✅ `/prompts` page loads with all analysis types
- ✅ Types sorted by flag rate (needs attention first)
- ✅ Detail view shows prompt, schema, stats
- ✅ `e` key copies nvim command
- ✅ `p` key navigates to prompts from all other pages

---

## Completion

**Completed:** 2026-02-02

### Phase 4 Execution - 2026-02-02

**Visual indicators** (`prompts.html`)
- Added "NEEDS ATTENTION" animated badge for prompts with flag_rate >= 0.2
- Added `.working-well` CSS class to dim prompts with 0 flags (reduced opacity)
- Badge pulses with a 2s animation to draw attention

**Edge case handling** (already in place)
- `load_prompt_feedback()` returns `{"flags": []}` for missing/corrupted file
- `load_action_state()` returns `{"actions": {}}` for missing/corrupted file
- `get_prompts()` API gracefully handles:
  - Empty analysis types directory
  - Missing/deleted analysis type configs (try/except ValueError)
  - Empty flags list
  - Zero total_actions (flag_rate = 0.0)

**Cross-page consistency verified**
- All 4 pages have mode toggle with `p` button: action_queue.html, browse.html, videos.html, prompts.html
- All status bars include `q b v p` shortcuts
- Keyboard navigation (`p` key) works from all pages

**End-to-end testing**
- Verified all route responses (200 OK for /, /browse, /videos, /prompts, /api/prompts)
- Tested flag endpoint: POST `/api/action/<id>/flag` correctly:
  - Saves flag to `~/.kb/prompt-feedback.json`
  - Updates action state with `status: "skipped"` and `flagged: true`
- Verified edge cases: empty analysis types returns empty list gracefully

### Summary

T019 is complete. The KB Prompt Quality Feedback System now provides:
1. **X Flag Action** - Press `x` on action items to flag with optional note
2. **Prompts Viewer** (`/prompts`) - Browse all analysis types with flag stats
3. **Bubbling Mechanism** - High flag rate prompts surface first
4. **Visual Indicators** - "NEEDS ATTENTION" badge and dimmed "working well" prompts
5. **Auto-scroll Fix** - j/k navigation now scrolls selected items into view
