# T028: Content Lifecycle — Queue/Review State Machine

## Meta
- **Status:** COMPLETE
- **Created:** 2026-02-10
- **Last Updated:** 2026-02-10
- **Priority:** 2

## Task

Implement the content lifecycle state machine for `kb serve`. Currently Queue and Review show the same items with no real state transitions. Need to separate them into distinct workflow stages with proper keyboard-driven navigation.

## Context (from Blake, 2026-02-10)

The current flow:
1. **Transcribe**: `kb` CLI on Mac → categorize with decimal → default analysis types run
2. **Queue (Inbox)**: Open `kb serve` → all actionable items appear → triage
3. **Review (Refine)**: Only approved items → iterate, edit slides, generate visuals
4. **Done**: Published (manual copy for now, API auto-publish future)

### Problems today:
- Queue and Review show the **same items** — no state transition between them
- No status field tracking lifecycle stage (new vs triaged vs staged vs ready)
- Simple types (skool_post → copy → done) clog the Review page
- No distinction between "I haven't looked at this" and "I approved this for refinement"

### Content Lifecycle States

```
                    ┌─────────────────────────────────────────────┐
                    │              CONTENT STATES                  │
                    │                                             │
  kb CLI ──▶  [ new ]  ──queue──▶  [ triaged ]                   │
                                       │                          │
                          ┌────────────┼────────────┐             │
                          ▼            ▼            ▼             │
                      [ skip ]    [ done ]    [ staged ]          │
                      (hidden)    (copied,    (needs work)        │
                                  archived)       │               │
                                              iterate,            │
                                              edit slides,        │
                                              generate visuals    │
                                                  │               │
                                              [ ready ]           │
                                              (publish)           │
                                                  │               │
                                              [ done ]            │
                    └─────────────────────────────────────────────┘
```

### UX Principles
- **No buttons — keyboard only** for all actions
- **Queue view** = items in `new` state (inbox triage)
- **Review view** = items in `staged` state only (approved, needs work)
- Keyboard actions in Queue: `a` approve → staged, `d` done, `s` skip, `c` copy
- Keyboard actions in Review: `i` iterate, `v` generate visuals, `e` edit slides
- **Publish = manual** for now (copy and post). Future: auto-publish via API.
- **Visuals are optional** — linkedin_v2 defaults to generating visuals, but user can choose text-only

### Different types have different paths

| Type | Needs refinement? | Path |
|------|------------------|------|
| `linkedin_v2` | Yes — iterate, judge, visuals | Queue → Review → Iterate → Visuals → Done |
| `skool_post` | No — copy and post | Queue → Copy → Done |
| `skool_weekly_catchup` | No — copy and post | Queue → Copy → Done |
| guides/summaries | Maybe read, mostly skip | Queue → Skip/Done |

## Scope
- **In:**
  - Content state machine (new → staged → ready → done → skip)
  - Queue view filtering (only `new` items)
  - Review view filtering (only `staged`/`ready` items)
  - State transition endpoints
  - Keyboard navigation for state changes
  - Different paths per analysis type
- **Out:**
  - Auto-publish via API (future)
  - Batch operations
  - Analytics/metrics on content pipeline

## Dependencies
- T026 Phase 8 (KB Serve iteration view + analysis trigger) — should complete first
- Builds on existing `action-state.json` status tracking

---

## UX Exploration

Full UX exploration with state machine diagrams, screen mockups, keyboard maps, data model analysis, and gap analysis:

**See:** [`ux-exploration.md`](./ux-exploration.md)

Contents:
1. State Machine Diagram (mermaid) with per-type paths
2. Screen-by-Screen ASCII Mockups (Queue, Review, Browse)
3. Keyboard Interaction Map with conflict analysis
4. Data Model changes to `action-state.json` with migration strategy
5. Gap Analysis: edge cases, missing features, spec ambiguities
6. Decision Matrix: 6 open questions needing human input

---

## Plan

### Objective
Separate Queue and Review into distinct lifecycle stages so new content appears only in Queue (inbox triage) and approved content appears only in Review (refinement), with type-aware shortcuts that route simple types directly to done.

### Scope
- **In:** Status migration, API filter changes, type-aware approve, Review filter update
- **Out:** Auto-publish API, batch operations, Browse/Videos/Prompts changes

### Phases

#### Phase 1: Status Migration + Comprehensive Status Audit
- **Objective:** Migrate all status values and update every hardcoded status literal across the codebase
- **Tasks:**
  - [ ] 1.1: Add idempotent `migrate_to_t028_statuses()` function in `serve_state.py` (pending→new, approved→staged, draft→new, posted→done with posted_at preserved, skipped→skip)
  - [ ] 1.2: Call migration in `main()` before `app.run()` — this is the FIRST startup migration (no existing pattern to chain after; `migrate_approved_to_draft()` is CLI-only)
  - [ ] 1.3: **Comprehensive status literal audit** — update ALL hardcoded status strings across serve.py, serve_scanner.py, and templates. Known locations (12+):
    - `/api/queue` filters: `pending`→`new`, `skipped`→`skip`, `posted`→`done`
    - `/api/action/<id>/copy`: creates state with `pending`→`new`
    - `/api/action/<id>/skip`: writes `skipped`→`skip`
    - `/api/action/<id>/flag`: writes `skipped`→`skip`
    - `/api/action/<id>/iterate`: creates with `pending`→`new`
    - `/api/action/<id>/approve`: `pending`→`new` check (full rewrite in Phase 2)
    - `/api/action/<id>/stage`: `pending`/`draft`→`new` acceptance
    - `/api/action/<id>/posted`: merge into done flow (Phase 3)
    - `/api/posting-queue-v2`: filter `staged`+`ready` only (remove `pending`/`draft`)
    - `get_action_status()` default: `pending`→`new`
    - `posting_queue.html`: `draft` status badge
    - `action_queue.html`: section header, status labels
  - [ ] 1.4: Change `/api/queue` to filter `new` items only
  - [ ] 1.5: Change `/api/posting-queue-v2` to filter `staged` + `ready` only
  - [ ] 1.6: Deprecate `/api/posting-queue` v1 endpoint (return empty or redirect to v2)
  - **Note:** Tasks 1.1 + 1.4 + 1.5 must deploy together (migration and filters are atomic)
- **Acceptance Criteria:**
  - [ ] Queue API returns only `new` items
  - [ ] Review API returns only `staged`/`ready` items (no `new` items leak through)
  - [ ] Existing data migrates cleanly without data loss
  - [ ] `grep -r '"pending"\|"approved"\|"draft"\|"skipped"\|"posted"' kb/serve.py` returns zero matches (except comments)
  - [ ] Migration is idempotent (running twice produces same result)
- **Files:** `kb/serve.py`, `kb/serve_state.py`, `kb/serve_scanner.py`, `kb/templates/posting_queue.html`, `kb/templates/action_queue.html`
- **Dependencies:** None

#### Phase 2: Queue View - Type-Aware Approve + Done Blocking
- **Objective:** Make `[a]` route items correctly per type, block `[d]` for complex types, enforce staging before iteration
- **Tasks:**
  - [ ] 2.1: **Rewrite `/api/action/<id>/approve`** to be type-aware (this is a full rewrite, not a modification):
    - Validate `current_status == "new"` (was `pending`)
    - For AUTO_JUDGE_TYPES: set status to `staged`, set `staged_at`, create initial edit version (absorb logic from `stage_action()` lines 428-500)
    - For simple types: copy to clipboard, set status to `done`, set `completed_at`
    - Do NOT trigger visual pipeline (that's triggered from staging view)
  - [ ] 2.2: **Block `[d]` for complex types** — modify `/api/action/<id>/done` (line 220) to reject AUTO_JUDGE_TYPES with 400 + message "Use [a] to stage or [s] to skip"
  - [ ] 2.3: Update `action_queue.html` frontend `markDone()` to show toast on 400 response
  - [ ] 2.4: **Add iterate status guard** — modify `/api/action/<id>/iterate` to require `status == "staged"`. Return 400 "Item must be staged before iterating" otherwise. (Enforces Q3: must stage first)
  - [ ] 2.5: Update `action_queue.html` section header ("Ready for Triage"), status bar text (`new` not `pending`)
  - [ ] 2.6: Note: `stage_action()` remains for Review view re-staging (after iteration). Update its status acceptance from `("pending", "draft")` to `("new")` — though in practice Review items will already be `staged`, this keeps the endpoint consistent.
- **Acceptance Criteria:**
  - [ ] `linkedin_v2` items move to Review on `[a]` (status → `staged`)
  - [ ] `skool_post` items copy+done on `[a]` (status → `done`, never enters Review)
  - [ ] `[d]` on `linkedin_v2` in Queue returns 400 + shows toast
  - [ ] `[i]` iterate rejects non-staged items with 400
  - [ ] Items disappear from Queue after any action
- **Files:** `kb/serve.py`, `kb/templates/action_queue.html`
- **Dependencies:** Phase 1

#### Phase 3: Review View - Filter + Publish + Stage Key Fix
- **Objective:** Review shows only staged/ready items, publish → done, fix `[a]` key behavior post-migration
- **Tasks:**
  - [ ] 3.1: Update `posting_queue.html` status filtering logic (show only `staged` + `ready`)
  - [ ] 3.2: Merge `/api/action/<id>/posted` into done flow — set status `done` (not `posted`), preserve `posted_at` timestamp
  - [ ] 3.3: Update status bar counts and labels
  - [ ] 3.4: **Fix `[a]` key in Review post-migration** — after migration, all Review items are already `staged`. The current `stageItem()` calls `/api/action/<id>/stage` which rejects non-new items. Either: (a) make `[a]` a no-op/toast when already staged, or (b) repurpose `[a]` in Review to mean "stage this iteration round" (current behavior for selecting which round to stage). Investigate actual current behavior and ensure it works with `staged` items.
  - [ ] 3.5: Remove `draft` status badge from `posting_queue.html`
- **Acceptance Criteria:**
  - [ ] Review view shows only staged and ready items
  - [ ] Publish sets status to `done` with `posted_at` timestamp
  - [ ] Published items disappear from Review
  - [ ] `[a]` key in Review works correctly for `staged` items (no 400 errors)
- **Files:** `kb/serve.py`, `kb/templates/posting_queue.html`
- **Dependencies:** Phase 1

#### Phase 4: Test + Verify
- **Objective:** Verify all state transitions work end-to-end with automated tests
- **Tasks:**
  - [ ] 4.1: Test migration function (idempotent, handles all old statuses, preserves posted_at)
  - [ ] 4.2: Test Queue → staged flow for linkedin_v2 (`[a]` → status=staged, appears in Review)
  - [ ] 4.3: Test Queue → done flow for skool_post (`[a]` → status=done, copied, never in Review)
  - [ ] 4.4: Test `[d]` blocked for complex types (400 response)
  - [ ] 4.5: Test iterate rejected for non-staged items (400 response)
  - [ ] 4.6: Test staged → iterate → ready → publish → done flow
  - [ ] 4.7: Test skip from both views (Queue and Review)
  - [ ] 4.8: Test no old status literals remain in serve.py (grep assertion)
- **Acceptance Criteria:**
  - [ ] No item appears in both Queue and Review simultaneously
  - [ ] Simple types never appear in Review
  - [ ] Complex types cannot be quick-done from Queue
  - [ ] Iteration requires staged status
  - [ ] All new tests pass, zero regressions
- **Files:** `kb/tests/test_t028_lifecycle.py`
- **Dependencies:** Phases 1-3

### Decision Matrix

#### Open Questions (Need Human Input)
| # | Question | Options | Impact | Resolution |
|---|----------|---------|--------|------------|
| Q1 | Merge `posted` into `done`? | A) Merge with optional `posted_at`. B) Keep separate. | Status bar counts, filtering | **A) Merge** — `done` with optional `posted_at` timestamp to track what was actually published |
| Q2 | Should `[a]` auto-handle simple types? | A) Always stage. B) Type-aware: complex -> staged, simple -> copy+done. C) Always stage + add Enter shortcut. | Core UX for simple types | **B) Type-aware** — complex → staged, simple → copy+done |
| Q3 | Allow iteration before staging? | A) Yes, iterate from Queue. B) No, must stage first. | Flexibility vs workflow enforcement | **B) Must stage first** — iteration is a refinement process |
| Q4 | Add un-stage (staged -> new)? | A) Add `[u]` keybind. B) No, just skip+re-analyze. | Recovery from accidental stage | **B) No** — unnecessary for now |
| Q5 | Quick-done for `linkedin_v2` from Queue? | A) Allow `[d]` on any type. B) Block for complex types. | Quality enforcement | **B) Block** — complex types must go through full Review flow. `[s]` skip is the dismiss action. |
| Q6 | Rename statuses or keep backward compatible? | A) Rename with migration. B) Keep old names, change display only. | Code cleanliness vs migration risk | **A) Rename with migration** — clean codebase. Migration idempotent, JSON is version-controlled. |

**Implementation notes from review:**
- `[d]` on complex types in Queue: show toast "Use [a] to stage or [s] to skip" (graceful, not silent)
- Migration must be idempotent (safe to run multiple times — Mac and server share same JSON data via version control)
- Simple type `[a]` = copy+done is instant, no confirmation. Acceptable for MVP.
- `[s]` skip is permanent (hidden from all views). Re-analyze from Browse to recover.

#### Decisions Made (Autonomous)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Drop `triaged` state | No intermediate state | `[a]`/`[d]`/`[s]` actions ARE the triage decision |
| Keep "runway" label in UI | Existing term | Already in codebase and status bar |
| No Browse/Videos/Prompts changes | Out of scope | Only Queue and Review affected |
| Migration at server startup | Run once in `main()` | First startup migration — no existing pattern to chain after. `migrate_approved_to_draft()` is CLI-only. |
| Rewrite approve endpoint | Type-aware, absorb stage logic | Cleaner than having Queue call different endpoints per type |
| Deprecate posting-queue v1 | Return empty/redirect | Dead code after migration, no items will match `approved` filter |

---

## Plan Review
- **Gate:** READY
- **Reviewed:** 2026-02-10 (R2)
- **Summary:** All R1 critical/major issues resolved. Plan has comprehensive status audit (12+ locations with grep AC), correct migration startup handling, `[d]` blocking, iterate guard, detailed approve rewrite spec, and `[a]` key fix. 4 minor issues noted for executor awareness.
- **Issues:** 0 critical, 0 major, 4 minor
- **Open Questions Finalized:** All 6 resolved by Blake, no new questions needed.
- **R2 Minor Notes:** (1) Keep `pending` JSON key in `/api/queue` response, (2) update sort priority map in posting-queue-v2, (3) update `mark_posted` acceptance to `("staged", "ready")` in Phase 1, (4) verify iterate keeps status as `staged`.

-> Details: `plan-review.md`

---

## Execution Log

### Phase 1: Status Migration + Comprehensive Status Audit (commit `6db413b`)
- 1.1: Added `migrate_to_t028_statuses()` in `kb/serve_state.py` -- idempotent, all 5 old->new mappings
- 1.2: Migration call in `main()` before `app.run()` in `kb/serve.py`
- 1.3: Comprehensive status audit -- updated 12+ locations across `serve.py`, `serve_scanner.py`, both templates
- 1.4: `/api/queue` filters `new` items only; keeps `"pending"` JSON key for API compat (plan-review m1)
- 1.5: `/api/posting-queue-v2` filters `staged`+`ready` only; updated sort priority map (m2)
- 1.6: Deprecated `/api/posting-queue` v1 (returns empty)
- Also completed atomically: 2.1 (approve rewrite), 2.4 (iterate guard), 2.5 (header/status), 2.6 (stage acceptance)
- Updated `mark_posted` to accept `staged`/`ready` (m3); iterate keeps status as `staged` (m4)
- Tests: updated `test_iteration_view.py`, `test_serve_integration.py`, `test_staging.py` for new statuses
- Result: 39 failed (pre-existing), 405 passed -- zero regressions

### Phase 2: Queue View - Type-Aware Approve + Done Blocking (commit `4aed58b`)
- 2.2: `mark_done()` blocks AUTO_JUDGE_TYPES with 400 + "Use [a] to stage or [s] to skip"
- 2.3: Frontend `markDone()` in `action_queue.html` shows toast on non-ok response
- Tasks 2.1, 2.4, 2.5, 2.6 completed in Phase 1 (atomicity requirement)
- Result: 39 failed (pre-existing), 405 passed -- zero regressions

### Phase 3: Review View - Filter + Publish + Stage Key Fix (commit `5d1debe`)
- 3.1: Backend already filters staged+ready (Phase 1); frontend entity list already handles these statuses
- 3.2: `mark_posted` already sets done+posted_at (Phase 1)
- 3.3: Status bar counts correct (no old labels)
- 3.4: `[a]` key works for staged items -- `stage_action()` accepts `("new", "staged")`
- 3.5: Removed orphaned `.entity-status.draft` CSS class from `posting_queue.html`
- Result: 39 failed (pre-existing), 405 passed -- zero regressions

### Phase 4: Test + Verify (commit `ac1ed07`)
- Created `kb/tests/test_t028_lifecycle.py` with 29 tests across 9 test classes:
  - TestMigration (8 tests): idempotent, all old statuses, preserves posted_at, empty state
  - TestApproveComplexType (3): linkedin_v2 -> staged, not in queue, rejects non-new
  - TestApproveSimpleType (2): skool_post -> done+copied, never in review
  - TestDoneBlockedForComplexTypes (2): 400 for linkedin_v2, allowed for simple
  - TestIterateRequiresStaged (3): rejects new, done, skip
  - TestPublishFlow (4): staged->done, ready->done, rejects new, not in review after
  - TestSkipFromBothViews (4): skip new, skip staged, not in queue, not in review
  - TestNoOldStatusLiterals (1): grep assertion on serve.py
  - TestNoItemInBothViews (2): new only in queue, staged only in review
- Result: 39 failed (pre-existing), 434 passed (29 new) -- zero regressions

### Files Modified
- `kb/serve_state.py` -- migration function
- `kb/serve.py` -- approve rewrite, done blocking, iterate guard, status audit, migration call
- `kb/serve_scanner.py` -- default status change
- `kb/templates/action_queue.html` -- header, status bar, toast on 400
- `kb/templates/posting_queue.html` -- removed draft badge + CSS
- `kb/tests/test_iteration_view.py` -- updated for new statuses
- `kb/tests/test_serve_integration.py` -- updated for new statuses
- `kb/tests/test_staging.py` -- updated for new statuses
- `kb/tests/test_t028_lifecycle.py` -- new, 29 lifecycle tests

### Deviations
- Phase 2 tasks 2.1, 2.4, 2.5, 2.6 executed with Phase 1 (plan noted "1.1 + 1.4 + 1.5 must deploy together" and approve rewrite was atomically required)
- Phase 3 tasks were largely pre-completed by Phase 1; only orphaned CSS removal was new work

---

## Code Review Log

### Phases 1-4 (combined review)
- **Gate:** PASS
- **Reviewed:** 2026-02-10
- **Issues:** 0 critical, 2 major, 3 minor
- **Summary:** All ACs verified, 29/29 new tests pass, zero regressions (434 passed, 39 pre-existing failures). Major issues are maintenance/UX quality (duplicated staging logic, stale toast text) -- not blocking production.

-> Details: `code-review.md`

---

## Completion
- **Completed:** 2026-02-10
- **Summary:** Content lifecycle state machine fully implemented. Queue shows only `new` items, Review shows only `staged`/`ready` items. Type-aware approve routes simple types to copy+done and complex types to staged. `[d]` blocked for complex types with toast. Iterate requires staged status. Idempotent migration at server startup. 29 new lifecycle tests.
- **Learnings:** Extract shared helpers when "absorbing" logic between endpoints to avoid duplication. Frontend toasts should adapt to backend response variants. Grep-based ACs are effective for codebase-wide rename tasks.
