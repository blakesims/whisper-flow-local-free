# Code Review: T028 Content Lifecycle (Phases 1-4)

## Gate: PASS

**Summary:** Solid implementation. All 4 phases delivered correctly with proper status migration, type-aware approve, done-blocking, iterate guard, view filtering, and 29 comprehensive tests. Zero regressions (39 pre-existing failures unchanged, 434 passed). The code has no critical issues. Two major issues found (duplicated staging logic, stale frontend toast text) and three minor issues. None are blocking for production use.

---

## Git Reality Check

**Commits:**
```
ac1ed07 T028 Phase 4: add 29 lifecycle tests covering all state transitions
5d1debe T028 Phase 3: remove orphaned draft CSS from posting_queue.html
4aed58b T028 Phase 2: block [d] for complex types, add toast on 400
6db413b T028 Phase 1: Status migration + comprehensive status audit
```

**Files Changed (across all 4 commits):**
- `kb/serve.py` -- approve rewrite, done blocking, iterate guard, status audit, migration call
- `kb/serve_state.py` -- migration function
- `kb/serve_scanner.py` -- default status change (pending -> new)
- `kb/templates/action_queue.html` -- header, status bar, toast on 400
- `kb/templates/posting_queue.html` -- removed draft badge + CSS
- `kb/tests/test_iteration_view.py` -- updated for new statuses
- `kb/tests/test_serve_integration.py` -- updated for new statuses
- `kb/tests/test_staging.py` -- updated for new statuses
- `kb/tests/test_t028_lifecycle.py` -- new, 29 lifecycle tests

**Matches Execution Report:** Yes. All files and commit descriptions match the execution log in main.md. The deviation (Phase 2 tasks 2.1, 2.4, 2.5, 2.6 executed in Phase 1 for atomicity) is correctly documented.

---

## AC Verification

### Phase 1: Status Migration + Comprehensive Status Audit

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| Queue API returns only `new` items | Yes | Yes | `get_queue()` line 129: filters on `item_state["status"] == "new"`. Staged/ready items explicitly excluded at line 131. |
| Review API returns only `staged`/`ready` items | Yes | Yes | `get_posting_queue_v2()` line 1227: `if status in ("staged", "ready")`. No new items leak through. |
| Existing data migrates cleanly without data loss | Yes | Yes | `migrate_to_t028_statuses()` preserves `posted_at`, converts `approved_at` to `staged_at`. 8 migration tests verify all paths. |
| grep returns zero matches (except comments) | Yes | Yes | Verified: `grep -r '"pending"\|"approved"\|"draft"\|"skipped"\|"posted"' kb/serve.py` returns only the legacy `migrate_approved_to_draft()` function (marked with `# noqa`) and the `"pending":` JSON key (API compat). Test 4.8 also verifies this. |
| Migration is idempotent | Yes | Yes | `test_idempotent`: run 1 returns count=1, run 2 returns count=0. New status values ("new", "staged", etc.) don't match any migration branch. |

### Phase 2: Queue View - Type-Aware Approve + Done Blocking

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| `linkedin_v2` items move to Review on `[a]` | Yes | Yes | `approve_action()` line 344: `AUTO_JUDGE_TYPES` branch sets status `staged`. Test `test_approve_linkedin_v2_sets_staged` passes. |
| `skool_post` items copy+done on `[a]` | Yes | Yes | `approve_action()` line 395-416: else branch copies + sets `done`. Test `test_approve_skool_post_sets_done` passes. |
| `[d]` on `linkedin_v2` returns 400 + shows toast | Yes | Yes | `mark_done()` line 230-233: blocks `AUTO_JUDGE_TYPES`. Frontend line 1503: shows error from response JSON on non-ok. Test `test_done_blocked_for_linkedin_v2` passes. |
| `[i]` iterate rejects non-staged with 400 | Yes | Yes | `iterate_action()` line 1067: `if current_status != "staged"` returns 400. Three rejection tests pass (new, done, skip). |
| Items disappear from Queue after any action | Yes | Yes | Queue filters `new` only; approve sets to `staged`/`done`, done sets to `done`, skip sets to `skip`. Cross-view tests confirm. |

### Phase 3: Review View - Filter + Publish + Stage Key Fix

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| Review view shows only staged and ready items | Yes | Yes | `get_posting_queue_v2()` line 1227 filters `staged`+`ready`. Frontend `posting_queue.html` status checks reference `staged`/`ready` (lines 1292, 1296). |
| Publish sets status to `done` with `posted_at` | Yes | Yes | `mark_posted()` line 1317-1319: sets `done`, `posted_at`, `completed_at`. Test `test_publish_staged_item` passes. |
| Published items disappear from Review | Yes | Yes | Test `test_published_item_not_in_review` verifies. Status `done` not in `("staged", "ready")` filter. |
| `[a]` key in Review works for staged items | Yes | Yes | `stage_action()` line 451: accepts `("new", "staged")`. Staged items can be re-staged (after iteration). No 400 errors for `staged` items. |

### Phase 4: Test + Verify

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| No item appears in both Queue and Review | Yes | Yes | Two cross-view tests pass (`test_new_item_only_in_queue`, `test_staged_item_only_in_review`). |
| Simple types never appear in Review | Yes | Yes | `test_simple_type_never_in_review` verifies `skool_post` not in posting-queue-v2 after approve. |
| Complex types cannot be quick-done from Queue | Yes | Yes | `test_done_blocked_for_linkedin_v2` verifies 400 response. |
| Iteration requires staged status | Yes | Yes | Three rejection tests (new, done, skip) all return 400. |
| All new tests pass, zero regressions | Yes | Yes | 29/29 new tests pass. Full suite: 434 passed, 39 failed (pre-existing, confirmed same failures on commit before T028). |

---

## Issues Found

### Major

1. **Duplicated staging logic between `approve_action()` and `stage_action()`**
   - File: `kb/serve.py:357-381` and `kb/serve.py:465-494`
   - Problem: The edit version creation logic (read transcript, create `_N_0` edit key, write transcript) is copy-pasted between `approve_action()` (for complex types from Queue) and `stage_action()` (for re-staging from Review). These are 30+ lines of near-identical code. If one is updated (e.g., edge case fix), the other will be missed. The plan explicitly said "absorb logic from `stage_action()`" which implies reuse, not duplication.
   - Fix: Extract a shared helper function like `_create_initial_edit_version(action_id, transcript_path, analysis_type, state)` that both endpoints call. Not blocking production, but a maintenance hazard.

2. **Frontend `approveItem()` toast does not distinguish staged vs done**
   - File: `kb/templates/action_queue.html:1548`
   - Problem: After the type-aware approve rewrite, `[a]` on a `skool_post` copies + marks done, while `[a]` on a `linkedin_v2` stages it. But the frontend toast says "Approved & copied!" for both. The response JSON now includes `data.action` ("staged" or "done") which the frontend ignores. For a `skool_post`, the user gets "Approved & copied!" when the item is actually done and will never appear in Review. Should say something like "Copied & done!" for simple types and "Staged & copied!" for complex types.
   - Fix: Use `data.action` to differentiate: `const msg = data.action === 'done' ? 'Copied & done!' : 'Staged & copied!';`

### Minor

1. **`approve_action()` does not increment `copied_count` despite copying to clipboard**
   - File: `kb/serve.py:387-392` and `kb/serve.py:410-414`
   - Problem: Both branches of `approve_action()` call `pyperclip.copy()` but never increment `copied_count` on the action state. The `copy_action()` endpoint does increment it. This means `copied_count` will be inaccurate for items approved via `[a]`. Pre-existing behavior (old approve also didn't increment), but worth fixing now that approve is the primary Queue action.

2. **`skip_action()` has no status guard -- can skip from any status**
   - File: `kb/serve.py:252-272`
   - Problem: Unlike `mark_done()` (which blocks complex types), `mark_posted()` (which requires staged/ready), and `iterate_action()` (which requires staged), the `skip_action()` endpoint accepts any status. A `ready` item (visuals already generated) could be silently skipped. This is arguably by design (plan says "`[s]` skip is permanent"), but it means a user could accidentally skip a ready-to-publish item with no confirmation.
   - Note: Documented as intentional in plan review, but worth noting for awareness.

3. **Section header emoji removed in Phase 1 diff but not documented**
   - File: `kb/templates/action_queue.html` diff line: `"Ready for Action"` changed to `"Ready for Triage"` (emoji removed)
   - Problem: The clipboard emoji was removed from the section header. This is aesthetically fine but was not called out in the task list. Trivial.

---

## What's Good

- **Migration is clean and well-tested.** 8 tests covering all old statuses, idempotency, empty state, and the all-at-once multi-status migration. The `approved_at -> staged_at` preservation is a nice detail.
- **Grep-based AC is a smart verification strategy.** The `TestNoOldStatusLiterals` test class with its docstring-aware, comment-aware, noqa-aware line scanning is thorough. It will catch future regressions if someone introduces an old status literal.
- **Type-aware approve is well-structured.** The branching is clear: AUTO_JUDGE_TYPES goes to staged with edit version creation, everything else goes to copy+done. The plan's "absorb stage logic" directive was followed (albeit via duplication rather than extraction).
- **Cross-view isolation tests are excellent.** The `TestNoItemInBothViews` class verifies the core invariant that no item appears in both Queue and Review simultaneously. This is the most important behavioral guarantee.
- **API contract preservation.** Keeping the JSON key `"pending"` while changing the internal status to `"new"` avoids breaking the frontend without a full rename pass. Good pragmatic decision from plan-review m1.
- **Legacy function properly annotated.** The `migrate_approved_to_draft()` function is kept for CLI compat with `# noqa: old status` markers, clear docstring, and the test's grep scanner correctly exempts it.
- **Zero regressions verified independently.** I confirmed the 39 failures exist on the commit before T028 (same test_carousel_templates, test_render, test_staging failures). No new failures introduced.

---

## Required Actions

None -- PASS. The two major issues are maintenance/UX quality concerns, not correctness bugs. They should be addressed in a follow-up but do not block this task.

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| When plan says "absorb logic from X", extract a shared helper instead of copy-pasting | Future refactoring tasks | Add to plan review checklist: flag "absorb" language and recommend extraction |
| Frontend toast messages should adapt to backend response variants | All type-aware endpoints | Executor should update toast when endpoint returns different `action` values |
| Grep-based AC is effective for status rename tasks | Future migration tasks | Reuse this pattern for any codebase-wide literal rename |
