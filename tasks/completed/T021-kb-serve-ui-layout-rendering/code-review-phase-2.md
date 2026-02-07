# Code Review: Phase 2

## Gate: PASS

**Summary:** Clean, minimal 8-line change that does what it claims. No bugs found. The issues are minor (payload size, no test coverage, nesting inconsistency for downstream consumers). All three acceptance criteria verified against the actual code.

---

## Git Reality Check

**Commits:**
```
76ec6cc Phase2: add raw_data field to action items for structured rendering
```

**Files Changed:**
- `kb/serve.py` (8 lines added)

**Matches Execution Report:** Yes -- single file, single commit, matches exactly.

**Discrepancy:** Execution log says "All 73 existing tests pass." This is true but misleading -- zero of those 73 tests cover `scan_actionable_items()`, `/api/queue`, or `/api/action/<id>/content`. The tests pass because they test unrelated functionality (action_mapping, inbox, browse, conditional_template, compound_analysis).

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: API responses include both `content` (string) and `raw_data` (object) | Yes | Yes | `/api/queue` passes through full item dict (inherits `raw_data`). `/api/action/<id>/content` explicitly returns `raw_data` at line 388. |
| AC2: Existing clipboard copy still uses `content` string | Yes | Yes | `/api/action/<id>/copy` at line 412 uses `pyperclip.copy(item["content"])` -- unchanged. |
| AC3: `raw_data` excludes `_` prefixed metadata keys | Yes | Yes | Dict comprehension `{k: v for k, v in analysis_data.items() if not k.startswith("_")}` at line 245. For non-dict analysis data, `raw_data` is `None`. |

---

## Issues Found

### Critical
None.

### Major
None.

### Minor

1. **No test coverage for changed code**
   - File: `kb/tests/` (absent)
   - Problem: Zero tests cover `scan_actionable_items()`, `/api/queue`, or `/api/action/<id>/content`. The "73 tests pass" claim is technically true but provides zero verification of the change. All 73 tests cover other modules (action_mapping, inbox, browse, conditional_template, compound_analysis).
   - Fix: Acceptable for now -- this is a pre-existing gap, not introduced by this change. Phase 3/4 would be a better time to add integration tests.

2. **Payload bloat on `/api/queue` listing endpoint**
   - File: `kb/serve.py:363`
   - Problem: The queue listing endpoint sends `raw_data` (structured object) AND `content` (string) for every item in the list. This is effectively double-sending the same data. The `/api/action/<id>/content` endpoint exists for fetching full content on demand.
   - Fix: Pre-existing design issue (it already sent `content` in the list). Not a regression. If performance becomes a concern, strip `content` and `raw_data` from the list response and rely on the per-item content endpoint.

3. **`raw_data` preserves inconsistent nesting structure**
   - File: `kb/serve.py:245`
   - Problem: For a `guide` analysis, `raw_data` will be `{"guide": {"title": "...", "steps": [...]}}` (nested under its own name). For a `linkedin_post`, it might be `{"post": "...", "hook": "...", "cta": "..."}` (flat). Phase 3 renderers will need to handle this inconsistency -- some types are wrapped in a key matching the analysis name, others are not.
   - Fix: Not a bug -- `raw_data` faithfully represents the stored data. Phase 3 renderers should be designed to check for the nested key pattern. Document this for the Phase 3 executor.

---

## What's Good

- Minimal, focused change -- 8 lines, single file, no unnecessary modifications
- Defensive handling of non-dict analysis data (`raw_data = None`)
- Preserves backward compatibility completely -- `content` field unchanged, existing endpoints unmodified
- The `_` prefix convention for metadata is a clean, simple filtering approach
- Dict comprehension is efficient and readable

---

## Required Actions (for REVISE)
N/A -- PASS gate.

---

## Note for Phase 3 Executor
The `raw_data` object has inconsistent nesting depending on analysis type. Some types wrap their content under a key matching the analysis name (e.g., `raw_data.guide` contains the actual guide data), while others have flat structures (e.g., `raw_data.post`, `raw_data.hook`). Renderers must handle both patterns.

---

## Learnings
| Learning | Applies To | Action |
|----------|-----------|--------|
| "Tests pass" claims need scrutiny -- check WHAT the tests actually cover | All code reviews | Always grep test files for coverage of changed functions |
| Pre-existing design debt (payload bloat) gets worse incrementally | Future phases | Consider refactoring `/api/queue` to exclude content/raw_data from list responses |
