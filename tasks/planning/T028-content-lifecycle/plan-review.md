# Plan Review: T028 Content Lifecycle -- Queue/Review State Machine

## Round 2 Review

## Gate Decision: READY

**Summary:** All 3 critical and 4 major issues from Round 1 have been resolved. The plan now includes comprehensive status literal audit (12+ locations), correct migration startup handling, `[d]` blocking with frontend toast, iterate status guard, detailed approve endpoint rewrite spec, and `[a]` key fix in Review. Two minor issues remain (JSON key rename and sort priority map) but both are trivially caught during Phase 1 execution. The plan is ready for execution.

---

## Round 1 Issue Resolution Verification

### C1 (R1): `[d]` blocking for complex types missing -- RESOLVED
- **Fix applied:** Tasks 2.2 and 2.3 added.
- **Verification:** Task 2.2 specifies modifying `/api/action/<id>/done` (line 220) to reject AUTO_JUDGE_TYPES with 400. Task 2.3 specifies frontend toast on 400 response.
- **Confirmed against codebase:** Current `mark_done()` (line 220-240) has no type checking and unconditionally sets status to `done`. Current frontend `markDone()` (line 1482-1506) has no error handling for non-ok responses. Both tasks correctly target the right code.
- **Status:** Fully resolved.

### C2 (R1): Only ~5 status changes identified -- RESOLVED
- **Fix applied:** Task 1.3 added with comprehensive 12+ location audit. Grep AC added to Phase 1.
- **Verification:** Task 1.3 lists all 12 endpoints/locations I identified in R1, including `/api/action/<id>/copy`, `/api/action/<id>/flag`, `/api/action/<id>/iterate`, `/api/action/<id>/stage`, `/api/action/<id>/posted`, and both templates.
- **Confirmed against codebase:** Cross-referencing against actual grep results:
  - `copy_action` line 202: `"pending"` -- listed in 1.3
  - `skip_action` line 253: `"skipped"` -- listed in 1.3
  - `flag_action` line 1370: `"skipped"` -- listed in 1.3
  - `iterate_action` line 1077: `"pending"` -- listed in 1.3
  - `approve_action` line 381-382: `"pending"` -- listed in 1.3
  - `stage_action` line 459-460: `"pending", "draft"` -- listed in 1.3
  - `mark_posted` line 1325: `"approved", "ready"` -- listed in 1.3
  - `get_posting_queue_v2` line 1238: `"pending", "draft"` -- listed in 1.3
  - `get_action_status` line 218: `"pending"` -- listed in 1.3
  - `posting_queue.html` line 1299-1300: `draft` badge -- listed in 1.3
  - `action_queue.html` line 1148+: section header -- listed in 1.3
- **Grep AC:** `grep -r '"pending"\|"approved"\|"draft"\|"skipped"\|"posted"' kb/serve.py` returns zero matches (except comments). Good verifiable acceptance criterion.
- **Status:** Fully resolved.

### C3 (R1): Migration/filter atomicity -- RESOLVED
- **Fix applied:** Note added to Phase 1: "Tasks 1.1 + 1.4 + 1.5 must deploy together."
- **Verification:** The note is on line 136 of main.md. This ensures migration and both filter changes happen in the same deployment.
- **Status:** Fully resolved.

### M1 (R1): Wrong startup migration assumption -- RESOLVED
- **Fix applied:** Task 1.2 rewritten to acknowledge this is the FIRST startup migration.
- **Verification:** Task 1.2 now reads: "Call migration in `main()` before `app.run()` -- this is the FIRST startup migration (no existing pattern to chain after; `migrate_approved_to_draft()` is CLI-only)."
- **Confirmed against codebase:** `main()` (line 2111-2135) has no existing migration call. `migrate_approved_to_draft()` (line 68-89) is defined in serve.py but only callable via CLI `kb migrate --reset-approved`. The plan correctly identifies this.
- **Status:** Fully resolved.

### M2 (R1): No iterate status guard -- RESOLVED
- **Fix applied:** Task 2.4 added requiring `status == "staged"`.
- **Verification:** Task 2.4: "Add iterate status guard -- modify `/api/action/<id>/iterate` to require `status == "staged"`. Return 400."
- **Confirmed against codebase:** Current `iterate_action()` (line 1048-1107) has zero status checking. It creates a state entry with `"pending"` if none exists (line 1075-1080) and sets `iterating: True` regardless of current status. The task correctly targets this gap.
- **Status:** Fully resolved.

### M3 (R1): Approve endpoint needs full rewrite -- RESOLVED
- **Fix applied:** Task 2.1 completely rewritten with detailed spec.
- **Verification:** Task 2.1 now specifies:
  - Validate `current_status == "new"` (was `pending`)
  - For AUTO_JUDGE_TYPES: set status to `staged`, set `staged_at`, create initial edit version (absorb from `stage_action()` lines 428-500)
  - For simple types: copy to clipboard, set status to `done`, set `completed_at`
  - Do NOT trigger visual pipeline
- **Confirmed against codebase:** Current `approve_action()` (line 355-425) sets `"approved"`, auto-copies, and triggers visual pipeline for non-AUTO_JUDGE_TYPES. Current `stage_action()` (line 428-507) handles staging with edit version creation. The plan correctly identifies that approve needs to absorb stage logic for complex types.
- **Note on stage_action() survival:** Task 2.6 correctly notes that `stage_action()` remains for Review view re-staging after iteration. This is correct -- the Review view `[a]` key calls `/api/action/<id>/stage` (posting_queue.html line 2435).
- **Status:** Fully resolved.

### M4 (R1): `[a]` in Review breaks post-migration -- RESOLVED
- **Fix applied:** Task 3.4 added to fix stage key behavior.
- **Verification:** Task 3.4 identifies the problem: after migration all Review items are `staged`, and `stageItem()` calls `/api/action/<id>/stage` which rejects non-new items. Offers two options: (a) make `[a]` a no-op/toast when already staged, or (b) repurpose for "stage this iteration round."
- **Confirmed against codebase:** `stage_action()` (line 458-461) validates `current_status not in ("pending", "draft")`. After T028, Review items will be `staged` or `ready`. Task 2.6 updates acceptance to `("new")` only, which means staged items are still rejected. The `[a]` key in posting_queue.html (line 2433-2435) calls `stageItem()` unconditionally.
- **Observation:** The task correctly identifies this needs investigation. In practice, `[a]` in Review is used to stage a NEW iteration round (after `[i]` iterate produces a new round at status `new`... wait, no -- after T028, iterate sets `iterating: True` but does not change status. The item stays `staged`. So `[a]` in Review would need to re-stage after iteration completes, which means `stage_action()` must accept `staged` items too. Task 3.4 covers this investigation.
- **Status:** Resolved (investigation task is appropriate here -- the exact behavior depends on the iteration flow details).

---

## New Issues Found (Round 2)

### m1: Minor -- `/api/queue` JSON response key `pending` vs status name `new`

The `/api/queue` endpoint (line 152-156) returns JSON with key `"pending"`:
```python
return jsonify({
    "pending": pending,
    "completed": completed,
    "processing": [],
})
```

The frontend `action_queue.html` (line 849) initializes `queueData = { pending: [], completed: [], processing: [] }` and references `queueData.pending` in 15+ locations (lines 1126, 1142, 1148, 1153, 1271, 1274, 1366, 1430-1433, 1494-1497, 1521-1524, 1550-1553, 1587).

The plan's task 1.3 covers changing the status filter from `"pending"` to `"new"`, and task 2.5 covers updating section header text. But the plan does not explicitly mention whether to rename the JSON response key from `"pending"` to `"new"` (which would require updating all 15+ frontend references), or to keep `"pending"` as a legacy JSON key that now contains `new` status items.

**Recommendation:** Keep the JSON key as `"pending"` for Phase 1. The key name is an API contract detail, not a status value. Renaming it would touch 15+ lines in `action_queue.html` for zero functional benefit. The executor can decide this during implementation. Not a blocking issue.

### m2: Minor -- `posting_queue_v2` sort priority map references old statuses

The sort priority map at line 1297:
```python
status_priority = {"ready": 0, "staged": 1, "pending": 2, "draft": 3}
```

After migration, `"pending"` and `"draft"` statuses will not exist. The sort map should be updated to `{"ready": 0, "staged": 1, "new": 2}`. This is covered implicitly by the task 1.3 comprehensive audit, but the specific line is not called out.

**Recommendation:** The executor will catch this during the grep AC verification (the grep searches for `"pending"` and `"draft"` literals). Not blocking.

### m3: Minor -- `mark_posted` endpoint acceptance list needs update

Task 1.3 lists `/api/action/<id>/posted` with note "merge into done flow (Phase 3)". The current code (line 1325) accepts `("approved", "ready")`. After migration in Phase 1, `"approved"` becomes `"staged"`, so the acceptance should be `("staged", "ready")`. But task 3.2 specifies merging this into done flow in Phase 3.

**Risk:** Between Phase 1 deploy and Phase 3 deploy, the `mark_posted` endpoint will still check for `"approved"` which no longer exists after migration. Users pressing publish in Review during this window would get a 400 error.

**Mitigation:** Phase 1 task 1.3 should update the acceptance to `("staged", "ready")` as part of the comprehensive audit. Phase 3 then does the full merge into done flow. The task 1.3 audit already lists this endpoint, so the executor should catch it. Not blocking, but worth noting.

### m4: Minor -- `iterate_action` creates state with `"pending"` (line 1077) -- interaction with task 2.4 guard

Task 2.4 adds a status guard requiring `status == "staged"` before iterating. But the current iterate endpoint also creates a new state entry with `"status": "pending"` (line 1075-1080) if none exists. After T028, this should be `"new"` (covered by task 1.3 audit). However, there is a subtle interaction: if the item is `staged` and passes the guard, should iteration change the status? Currently it just sets `iterating: True` without changing status. After iteration completes, the item stays `staged`. This is likely correct -- the item stays staged throughout iteration -- but the executor should verify this is intentional.

**Recommendation:** Not blocking. The executor should confirm: after `[i]` iterate on a `staged` item, does the item stay `staged`? If yes, then `[a]` in Review (task 3.4) needs to handle re-staging a new round for an already-staged item.

---

## Plan Strengths
- Comprehensive 12+ location status audit (task 1.3) is thorough and matches codebase reality
- Grep-based AC for Phase 1 provides a hard verification gate
- Approve endpoint rewrite spec (task 2.1) is detailed enough for an executor to implement without guessing
- Atomic deploy note (tasks 1.1 + 1.4 + 1.5) prevents partial-migration bugs
- Correct identification that `stage_action()` survives for Review re-staging (task 2.6)
- Task 3.4 appropriately defers `[a]` key behavior investigation to Phase 3 (when Review flow is being modified)
- Clean 4-phase dependency chain: Phase 1 (data/filters), Phase 2 (Queue UX), Phase 3 (Review UX), Phase 4 (tests)

---

## Recommendations

### Consider During Execution
- [ ] Keep `/api/queue` JSON key as `"pending"` (not `"new"`) to minimize frontend churn -- rename in a future task if desired (m1)
- [ ] Update sort priority map in `posting_queue_v2` during Phase 1 audit (m2)
- [ ] Update `mark_posted` acceptance to `("staged", "ready")` in Phase 1 audit, before Phase 3 full rewrite (m3)
- [ ] Verify iterate does not change status (stays `staged` throughout iteration cycle) (m4)

---

## Round 1 vs Round 2 Comparison

| Metric | Round 1 | Round 2 |
|--------|---------|---------|
| Critical issues | 3 | 0 |
| Major issues | 4 | 0 |
| Minor issues | 5 | 4 |
| Gate decision | NEEDS_WORK | READY |
| Open questions | All resolved | All resolved |
