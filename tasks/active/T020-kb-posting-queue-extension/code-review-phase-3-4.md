# Code Review: Phase 3-4

## Gate: REVISE

**Reviewed:** 2026-02-04
**Commit:** `1d7622a`
**Summary:** Backend endpoints and UI are implemented and functional. Two significant issues found: state transition validation missing on /posted endpoint (allowing bypass of approval workflow) and XSS vulnerability in unescaped content rendering. All 73 existing tests pass.

---

## Git Reality Check

**Commits:**
```
1d7622a Phase3-4: Add posting queue backend and UI
```

**Files Changed:**
- `kb/serve.py` - Added 3 endpoints: `/api/posting-queue`, `/api/action/<id>/approve`, `/api/action/<id>/posted`, HTML route `/posting-queue`
- `kb/templates/action_queue.html` - Added approve button (`a` shortcut), runway link (`r` shortcut)
- `kb/templates/posting_queue.html` - New 1000-line template with full posting queue UI

**Matches Execution Report:** Yes

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC3.1: Approve endpoint transitions pending -> approved | Yes | Yes | Code sets status to "approved" with `approved_at` timestamp |
| AC3.2: Posting queue returns only approved items | Yes | Yes | Filter checks `status == "approved"` |
| AC3.3: Posted endpoint transitions approved -> posted | Yes | **PARTIAL** | Sets status but no validation of previous state |
| AC3.4: action-state.json persists new fields | Yes | Yes | Both `approved_at` and `posted_at` fields saved |
| AC4.1: Approve button visible and functional | Yes | Yes | Button with `a` shortcut works |
| AC4.2: Posting Queue accessible via `r` shortcut | Yes | Yes | Navigation works from action queue |
| AC4.3: Runway counter shows counts per platform | Yes | Yes | Groups by destination correctly |
| AC4.4: Copy & Mark Posted works | Yes | Yes | `copyAndMarkPosted()` function handles both actions |

---

## Issues Found

### Major (2)

1. **No state transition validation on /posted endpoint**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py:560-583`
   - Problem: The `/api/action/<id>/posted` endpoint allows marking ANY item as posted, bypassing the approval step. Expected workflow is `pending -> approved -> posted`, but code allows `pending -> posted` directly.
   - Impact: Data integrity - items can be marked posted without ever being approved
   - Fix: Add check that `state["actions"][action_id]["status"] == "approved"` before allowing transition to "posted". Return 400 error if not approved.

2. **XSS vulnerability in content rendering**
   - Files:
     - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html:853,789`
     - `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/action_queue.html:906,815`
   - Problem: LLM-generated content inserted directly into DOM via template literals without HTML escaping
   - Code:
     ```javascript
     <div class="preview-text">${item.content}</div>
     <div class="action-preview">${preview}...</div>
     ```
   - Impact: If analysis output contains HTML/script tags, they execute in browser
   - Fix: Create an `escapeHtml()` helper function and apply to all dynamic content:
     ```javascript
     function escapeHtml(text) {
         const div = document.createElement('div');
         div.textContent = text;
         return div.innerHTML;
     }
     ```

### Minor (2)

3. **Keyboard shortcut `p` overloaded in posting queue**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/templates/posting_queue.html:968-990`
   - Problem: `p` means "mark posted" when items exist, "go to prompts" when empty. Other pages use `p` consistently for prompts.
   - Impact: UX inconsistency, potential for accidental posts
   - Suggestion: Consider using different key for mark posted (e.g., `m` or `Enter`)

4. **Approve endpoint does not verify pending state**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/serve.py:514-557`
   - Problem: Can approve already-approved, posted, or skipped items
   - Impact: Minor - mostly cosmetic, resets approved_at timestamp
   - Suggestion: Consider adding validation if strict state machine desired

---

## What's Good

- **Security:** `validate_action_id()` properly validates action ID format with regex
- **Fallback handling:** Both client and server clipboard copy with graceful degradation
- **UI consistency:** Tmux-style layout, Catppuccin colors match existing pages
- **Runway logic:** Correctly groups and counts by destination platform
- **Polling intervals:** 10s for runway vs 5s for main queue (appropriate)
- **Tests:** All 73 existing tests pass
- **Empty states:** Good UX for empty queue with helpful messaging

---

## Required Actions (for REVISE)

- [ ] Add state validation to `/api/action/<id>/posted` - require status == "approved"
- [ ] Add `escapeHtml()` helper function to both templates
- [ ] Apply HTML escaping to `item.content` and `preview` in both templates
- [ ] (Optional) Consider changing posting queue `p` shortcut to avoid confusion

---

## Test Recommendations

After fixes, manually verify:
1. Try to mark a pending item as posted directly (should fail with 400)
2. Create an analysis with content containing `<script>alert('xss')</script>` and verify it renders as text, not executes
3. Verify `p` shortcut still works correctly in posting queue after any changes

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| State machines need validation at each transition | All status-based workflows | Add guards on state transitions |
| User-generated content (even from LLM) needs escaping | All template-rendered content | Always escape before innerHTML |
| Keyboard shortcut consistency matters | Multi-page apps | Document shortcut meanings centrally |
