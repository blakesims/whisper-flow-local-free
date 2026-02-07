# Code Review: Phase 3 - Dashboard Videos Tab

**Reviewer**: Code Review Agent
**Date**: 2026-01-31
**Verdict**: REVISE

---

## Git Reality Check

```bash
$ git status --porcelain
 M kb/__main__.py
 M kb/serve.py
 M kb/templates/action_queue.html
 M kb/templates/browse.html
 M tasks/global-task-manager.md
?? kb/templates/videos.html
?? kb/videos.py
?? tasks/active/T016-kb-video-pipeline/
```

**Observation**: `kb/templates/videos.html` and `kb/videos.py` are untracked (new files). All claimed modifications are present.

---

## Acceptance Criteria Verification

| AC | Criteria | Status | Evidence |
|----|----------|--------|----------|
| AC1 | `/videos` shows all videos grouped by status/decimal | ✅ PASS | Route exists (line 642-645), template renders groupings via `/api/video-inventory` |
| AC2 | Linked videos show transcript preview | ✅ PASS | `/api/video/<id>` returns `transcript_preview` (lines 706-730) |
| AC3 | Can manually link/unlink videos | ✅ PASS | POST endpoints exist (lines 733-779) with validation |

---

## Findings

### CRITICAL: XSS Vulnerability via Filenames

**Location**: `kb/templates/videos.html` lines 775-777, 841-851, 930-970

**Issue**: User-controllable data (`filename`, `source_label`, `current_path`, `original_path`, `key`) is rendered via template literals directly into `innerHTML` without escaping.

```javascript
// Line 841-851 - filename not escaped
div.innerHTML = \`
    <div class="video-title">\${v.filename}</div>
    ...
\`;

// Line 930-970 - multiple unescaped fields
detailPane.innerHTML = \`
    ...
    <div class="detail-title">\${video.filename}</div>
    ...
    <div class="detail-path">\${video.source_label}</div>
    ...
    <div class="detail-path">\${video.current_path}</div>
    ...
\`;
```

**Attack Vector**: A malicious video file named `<img src=x onerror=alert(1)>.mp4` would execute JavaScript when the videos tab is viewed.

**Risk**: Medium-High. While this is a local tool, the KB dashboard is network-accessible. An attacker with file-write access to video source directories could inject XSS.

**Fix Required**: Apply `escapeHtml()` to all user-controllable strings:
```javascript
div.innerHTML = \`
    <div class="video-title">\${escapeHtml(v.filename)}</div>
    ...
\`;
```

### MEDIUM: Error Message Information Disclosure

**Location**: `kb/serve.py` line 792-793

**Issue**: The rescan endpoint returns raw exception messages to the client:
```python
except Exception as e:
    return jsonify({"error": str(e)}), 500
```

This could leak sensitive path information or internal error details.

**Fix**: Return generic error message, log details server-side:
```python
except Exception as e:
    print(f"[KB Serve] Rescan error: {e}")
    return jsonify({"error": "Video scan failed"}), 500
```

### LOW: Missing Transcript Existence Validation on Link

**Location**: `kb/serve.py` lines 733-759

**Issue**: The `/api/video/<id>/link` endpoint accepts any valid transcript ID format but doesn't verify the transcript actually exists. Users can link to non-existent transcripts.

**Impact**: Low - causes confusing UI state but no security risk.

**Fix**: Add transcript existence check before linking.

### LOW: Auto-scan Timezone Handling

**Location**: `kb/serve.py` lines 807-811

**Issue**: `datetime.now()` vs `datetime.fromisoformat()` comparison may have timezone issues if `last_scan` was stored with timezone info.

```python
last_scan_dt = datetime.fromisoformat(last_scan)
age_hours = (datetime.now() - last_scan_dt).total_seconds() / 3600
```

If `last_scan` contains timezone (e.g., `2026-01-31T10:00:00+07:00`), comparing with timezone-naive `datetime.now()` will raise `TypeError`.

**Current mitigation**: Caught by `except (ValueError, TypeError): pass` - but this silently skips auto-scan.

**Fix**: Use consistent timezone handling:
```python
from datetime import timezone
age_hours = (datetime.now(timezone.utc) - last_scan_dt).total_seconds() / 3600
```

---

## Security Review Summary

| Area | Status | Notes |
|------|--------|-------|
| API ID Validation | ✅ GOOD | All endpoints validate video_id format `^[a-f0-9]{12}$` |
| Transcript ID Validation | ✅ GOOD | Pattern `^[\w\.\-]+$` blocks path traversal |
| Path Traversal | ✅ GOOD | IDs are hashes, not user paths |
| XSS | ❌ FAIL | Multiple unescaped innerHTML injections |
| Error Disclosure | ⚠️ WARN | Raw exceptions returned to client |

---

## Comparison with Existing Patterns

**Good**: Video ID validation follows the same pattern as `validate_action_id()` for action endpoints.

**Gap**: The existing `action_queue.html` and `browse.html` templates also use innerHTML but typically display data from JSON files that are internally generated (analysis outputs, transcript text). The `videos.html` template displays **filesystem-derived data** (filenames, paths) which has higher XSS risk.

---

## Verdict: REVISE

### Must Fix Before Advancing (Blocking)
1. **XSS in videos.html** - Escape all user-controllable strings in innerHTML assignments

### Should Fix (Non-blocking)
2. Error message disclosure in rescan endpoint
3. Transcript existence validation on link

---

## Test Commands Executed

```bash
python3 -m py_compile kb/serve.py    # OK
python3 -m py_compile kb/videos.py   # OK
python3 -c "from kb.serve import app, check_and_auto_scan; print('Import OK')"  # OK
```

---

## Files Reviewed

- `kb/serve.py` (lines 640-815) - Routes, API endpoints, auto-scan
- `kb/templates/videos.html` (all 1226 lines) - Three-pane layout, JS
- `kb/templates/action_queue.html` (diff only) - Nav link
- `kb/templates/browse.html` (diff only) - Nav link
