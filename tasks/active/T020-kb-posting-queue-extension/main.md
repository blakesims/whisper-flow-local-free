# T020: KB Posting Queue Extension

## Meta
- **Status:** CODE_REVIEW
- **Created:** 2026-02-04
- **Last Updated:** 2026-02-04
- **Blocked Reason:** N/A

## Task

Extend the KB system with:
1. **Flexible analysis inputs**: Allow analysis types like `linkedin_post` to work without rigid dependencies (e.g., work with just transcript when `key_points` is unavailable for short content)
2. **Posting queue workflow**: Add `pending -> approved -> posted` workflow for content with a "Posting Queue" tab in the dashboard

**Problem being solved:**
- Short voice notes fail `linkedin_post` analysis because it requires `key_points` (timestamps, quotes) that don't exist for brief content
- No runway of pre-approved posts - everything is reviewed and posted immediately
- No way to track what's been posted vs what's still pending

---

## Plan

### Objective

Enable content generation from any transcript length and create a two-stage workflow (approve first, post later) for building a posting runway.

### Scope
- **In:**
  - Conditional template rendering for prompts (`{{#if var}}...{{else}}...{{/if}}`)
  - Optional inputs field for analysis types with smart fallback
  - New status states: `approved`, `posted` (in addition to existing `pending`, `done`, `skipped`)
  - Approve/Posted API endpoints
  - Posting Queue tab in dashboard
  - Runway counter display
- **Out:**
  - Automatic posting to LinkedIn/Skool APIs (future work)
  - Mermaid diagram generation (deferred to Phase 3)
  - Complex scheduling system

### Phases

#### Phase 1: Conditional Template Rendering
- **Objective:** Add Handlebars-style conditional blocks to prompt templates
- **Tasks:**
  - [ ] Task 1.1: Create `render_conditional_template(prompt, context)` function in `kb/analyze.py`
    - Handle `{{#if var}}content{{/if}}` blocks
    - Handle `{{#if var}}content{{else}}fallback{{/else}}` blocks
    - Must work with existing `{{var}}` substitution
  - [ ] Task 1.2: Write unit tests for conditional template rendering
    - Test simple if blocks
    - Test if/else blocks
    - Test nested variables inside conditionals
    - Test missing variable handling
- **Acceptance Criteria:**
  - [ ] AC1: `{{#if summary}}Has summary{{/if}}` renders content when summary is in context, nothing when absent
  - [ ] AC2: `{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}` correctly falls back
  - [ ] AC3: Existing `substitute_template_vars()` behavior unchanged for backwards compatibility
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/analyze.py` - add `render_conditional_template()` function
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/tests/test_conditional_template.py` - new test file
- **Dependencies:** None

#### Phase 2: Optional Inputs for Analysis Types
- **Objective:** Allow analysis types to specify optional dependencies that enhance but don't block execution
- **Tasks:**
  - [ ] Task 2.1: Add `resolve_optional_inputs()` function in `kb/analyze.py`
    - Check which optional inputs exist in transcript's analysis
    - Smart fallback: if `key_points` missing, include raw `transcript`
  - [ ] Task 2.2: Modify `run_analysis_with_deps()` to handle `optional_inputs` field
    - Required deps: must exist or auto-run (current behavior)
    - Optional deps: include if available, skip if not
  - [ ] Task 2.3: Update `linkedin_post.json` config to use conditionals
    - Change `"requires": ["summary", "key_points"]` to `"requires": [], "optional_inputs": ["summary", "key_points"]`
    - Update prompt to use conditional blocks
- **Acceptance Criteria:**
  - [ ] AC1: `kb analyze -t linkedin_post` works on short voice notes without key_points
  - [ ] AC2: `kb analyze -t linkedin_post` on long content still uses key_points when available
  - [ ] AC3: Existing analysis types without optional_inputs continue working unchanged
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/analyze.py` - modify `run_analysis_with_deps()`, add `resolve_optional_inputs()`
  - Analysis config (synced from mac): `linkedin_post.json` - update to use optional_inputs
- **Dependencies:** Phase 1 complete

#### Phase 3: Posting Queue Backend
- **Objective:** Add API endpoints for approve/posted workflow
- **Tasks:**
  - [ ] Task 3.1: Update `load_action_state()` / `save_action_state()` to handle new status values
    - Add `approved_at` and `posted_at` timestamp fields
    - Support statuses: `pending`, `approved`, `posted`, `skipped`, `flagged`
  - [ ] Task 3.2: Add `POST /api/action/<id>/approve` endpoint
    - Set status to `approved`, record `approved_at` timestamp
    - Validate action ID format
  - [ ] Task 3.3: Add `GET /api/posting-queue` endpoint
    - Return only `approved` items
    - Filter to actionable types (linkedin_post, skool_post)
    - Include runway count by platform
  - [ ] Task 3.4: Add `POST /api/action/<id>/posted` endpoint
    - Set status to `posted`, record `posted_at` timestamp
- **Acceptance Criteria:**
  - [ ] AC1: Approve endpoint transitions item from `pending` to `approved`
  - [ ] AC2: Posting queue endpoint returns only approved items with correct structure
  - [ ] AC3: Posted endpoint transitions item from `approved` to `posted`
  - [ ] AC4: action-state.json correctly persists new fields
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py` - add 3 new endpoints
- **Dependencies:** None (can run in parallel with Phase 1-2)

#### Phase 4: Posting Queue UI
- **Objective:** Add "Posting Queue" tab to the dashboard with approve/posted workflow
- **Tasks:**
  - [ ] Task 4.1: Add "Approve" button to pending items in action_queue.html
    - Keyboard shortcut: `a` for approve
    - Styled as secondary button alongside existing actions
  - [ ] Task 4.2: Add "Posting Queue" tab/view
    - New mode button in header alongside q/b/v/p
    - Show approved items grouped by platform (LinkedIn, Skool)
    - Display runway counter at top
  - [ ] Task 4.3: Add "Copy & Mark Posted" action in posting queue
    - Copies content to clipboard
    - Marks as posted in one action
    - Keyboard shortcut: `p` for post (copy + mark)
  - [ ] Task 4.4: Style posting queue view
    - Platform badges (LinkedIn blue, Skool green)
    - Post preview (first 100 chars)
    - Word count display
- **Acceptance Criteria:**
  - [ ] AC1: "Approve" button visible and functional on pending items
  - [ ] AC2: Posting Queue tab accessible via `r` keyboard shortcut (for "runway")
  - [ ] AC3: Runway counter shows accurate counts per platform
  - [ ] AC4: "Copy & Mark Posted" works correctly
- **Files:**
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/action_queue.html` - modify
  - `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py` - add `/posting-queue` route for HTML
- **Dependencies:** Phase 3 complete

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| 1 | Should "Approve" auto-copy to clipboard? | A) Yes, approve copies automatically B) No, approve just changes status | UX: workflow efficiency vs. explicit actions | OPEN |
| 2 | Posting Queue tab - separate HTML or mode within action_queue.html? | A) Same page, different mode (like browse) B) New template `/posting-queue` | Code organization, maintenance | OPEN - recommend A for consistency |
| 3 | Should approved items still show in main queue? | A) Yes, with "approved" badge B) No, move entirely to posting queue | UX: visibility of approval status | OPEN - recommend B for cleaner separation |
| 4 | Keyboard shortcut for posting queue? | A) `r` for runway B) `a` for approved C) New letter | Consistency with existing shortcuts | OPEN - recommend `r` |
| 5 | Should we auto-run missing `summary` for optional inputs on short content? | A) Yes, auto-run summary if content > 100 words B) No, just use raw transcript | Consistency vs. simplicity | OPEN - recommend B for Phase 1, consider A later |

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Template syntax | `{{#if var}}...{{else}}...{{/if}}` | Follows Handlebars convention, readable |
| Status values | Add `approved`, `posted` to existing | Additive change, no breaking changes |
| API structure | REST endpoints following existing pattern | Consistent with `/api/action/<id>/done`, `/api/action/<id>/skip` |
| Keep existing `requires` behavior | `requires` still triggers auto-run | Backwards compatible, `optional_inputs` is additive |

---

## Plan Review
- **Gate:** PENDING
- **Reviewed:** -
- **Summary:** -
- **Issues:** -
- **Open Questions Finalized:** -

---

## Execution Log

### Phase 1: Conditional Template Rendering
- **Status:** COMPLETE
- **Started:** 2026-02-04
- **Completed:** 2026-02-04
- **Commits:** `47540d2`
- **Files Modified:**
  - `kb/analyze.py` - Added `render_conditional_template()` function with regex-based Handlebars-style if/else support
  - `kb/tests/test_conditional_template.py` - New test file with 20 tests covering all cases
- **Notes:** Function handles `{{#if var}}content{{/if}}` and `{{#if var}}content{{else}}fallback{{/if}}` blocks with multiline support via re.DOTALL
- **Blockers:** None

### Tasks Completed
- [x] Task 1.1: Created `render_conditional_template(prompt, context)` function
- [x] Task 1.2: Wrote 15 unit tests for conditional template rendering

### Acceptance Criteria
- [x] AC1: `{{#if summary}}Has summary{{/if}}` works correctly (test_simple_if_true/false)
- [x] AC2: `{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}` falls back correctly (test_if_else_true/false)
- [x] AC3: Existing `substitute_template_vars()` unchanged, still called by render_conditional_template

### Phase 2: Optional Inputs for Analysis Types
- **Status:** COMPLETE
- **Started:** 2026-02-04
- **Completed:** 2026-02-04
- **Commits:** `47540d2`
- **Files Modified:**
  - `kb/analyze.py` - Added `resolve_optional_inputs()`, modified `run_analysis_with_deps()` to handle optional_inputs
  - `kb/tests/test_conditional_template.py` - Added 5 tests for resolve_optional_inputs
  - `mac-sync/.../linkedin_post.json` - Changed to `requires: []`, `optional_inputs: []`, prompt uses `{{transcript}}` directly
  - `mac-sync/.../skool_post.json` - Changed to `requires: []`, `optional_inputs: ["key_points"]`, prompt uses conditional for key_points
- **Notes:**
  - Per Blake's clarification: LinkedIn post uses raw transcript directly (no summary/key_points needed)
  - Skool post is the ONLY type that uses another analysis as optional input (key_points for timestamps)
  - All 72 existing tests still pass
- **Blockers:** None

### Tasks Completed
- [x] Task 2.1: Added `resolve_optional_inputs()` function
- [x] Task 2.2: Modified `run_analysis_with_deps()` to handle `optional_inputs` field
- [x] Task 2.3: Updated `linkedin_post.json` and `skool_post.json` configs

### Acceptance Criteria
- [x] AC1: linkedin_post now works without requiring key_points (uses transcript directly)
- [x] AC2: skool_post uses key_points when available via conditional template
- [x] AC3: Existing analysis types without optional_inputs continue working (72 tests pass)

### Phase 3: Posting Queue Backend
- **Status:** NOT_STARTED
- **Started:** -
- **Completed:** -
- **Commits:** -
- **Files Modified:** -
- **Notes:** -
- **Blockers:** -

### Phase 4: Posting Queue UI
- **Status:** NOT_STARTED
- **Started:** -
- **Completed:** -
- **Commits:** -
- **Files Modified:** -
- **Notes:** -
- **Blockers:** -

---

## Code Review Log

### Phase 1
- **Gate:** PENDING
- **Reviewed:** -
- **Issues:** -
- **Summary:** -

### Phase 2
- **Gate:** PENDING
- **Reviewed:** -
- **Issues:** -
- **Summary:** -

### Phase 3
- **Gate:** PENDING
- **Reviewed:** -
- **Issues:** -
- **Summary:** -

### Phase 4
- **Gate:** PENDING
- **Reviewed:** -
- **Issues:** -
- **Summary:** -

---

## Completion
- **Completed:** -
- **Summary:** -
- **Learnings:** -
