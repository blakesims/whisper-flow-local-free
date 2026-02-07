# Code Review: Phase 1 - Video Discovery & Smart Matching

**Reviewer**: Claude (Code Review Agent)
**Date**: 2026-01-31
**Status**: REVISE

---

## Summary

Phase 1 introduces `kb/videos.py` and modifies `kb/__main__.py` to add the `scan-videos` command. The core functionality is present but there are **critical bugs**, **edge cases**, and **pattern violations** that need addressing before proceeding.

---

## Files Reviewed

| File | Changes | Verdict |
|------|---------|---------|
| `kb/videos.py` | New file (536 lines) | REVISE |
| `kb/__main__.py` | +21 lines (config, command) | OK with minor issues |

---

## Critical Findings

### 1. **BUG: Circular Import Risk** (HIGH)
**Location**: `kb/videos.py:40`

```python
from kb.__main__ import load_config, expand_path
```

This import pattern works BUT creates fragility. When `kb/core.py` already imports from `kb/__main__`, adding another module that does the same increases the risk of circular import during future changes.

**Concern**: The `videos.py` module could be called from `serve.py` (Phase 3), which also imports from `__main__`. If any refactoring happens, this could break.

**Recommendation**: Consider importing `load_config` and `expand_path` from a centralized location or through `kb/core.py`.

---

### 2. **BUG: `expand_path` Returns Path, Used as String** (HIGH)
**Location**: `kb/videos.py:422`

```python
target_base = expand_path(config.get("video_target", "/Volumes/BackupArchive/kb-videos"))
```

`expand_path()` returns a `Path` object. On line 440:
```python
target_dir = target_base / decimal
```

This works. BUT on line 422, if the config returns `None`, the fallback `/Volumes/BackupArchive/kb-videos` is a string that would be passed to `expand_path()` which is fine.

**However**, line 447 does:
```python
if os.path.abspath(current_path) == os.path.abspath(str(target_path)):
```

The `str(target_path)` is correct, but there's inconsistency - some places use Path, others string. Not a bug per se but fragile.

---

### 3. **BUG: Video ID Changes When File Moves** (HIGH)
**Location**: `kb/videos.py:54-57`

```python
def generate_video_id(path: str) -> str:
    """Generate stable video ID from path hash."""
    return hashlib.md5(path.encode()).hexdigest()[:12]
```

**Problem**: The ID is generated from the *path*. When `reorganize_videos()` moves a file, its `current_path` changes. If you rescan:
1. The file at the new path gets a **new ID** (hash of new path)
2. The old entry in inventory becomes orphaned
3. Duplicates appear in the inventory

**Plan says**: "Video ID: Hash of original path - Stable even after reorganization"

**Reality**: The scan uses `current_path` at scan time, not `original_path`.

**Fix needed**: Either:
- Generate ID from `original_path` (stored) rather than scanned path
- Or generate ID from file content hash (first N bytes)
- Or use filename + size + mtime as composite key

---

### 4. **BUG: Inventory Doesn't Remove Missing Videos** (MEDIUM)
**Location**: `kb/videos.py:389-394`

```python
# Update inventory
for video in videos:
    inventory["videos"][video["id"]] = video

inventory["last_scan"] = datetime.now().isoformat()
```

If a video was in the inventory but is now deleted/moved, it remains in the inventory forever. The scan only *adds/updates* entries, never removes stale ones.

**Missing logic**: Mark videos not found in scan as "missing" or purge them.

---

### 5. **EDGE CASE: Filename Match is Too Loose** (MEDIUM)
**Location**: `kb/videos.py:256-257`

```python
# Filename match (handles moved files)
if os.path.basename(source) == video_filename:
    return transcript
```

This matches ANY transcript that has the same filename in `source_files`. If you have two videos named `session.mp4` in different directories, they'll both match to the same transcript.

**Should at least**: Compare file size or check if transcript is already linked.

---

### 6. **EDGE CASE: Silent Failure on Import Error** (MEDIUM)
**Location**: `kb/videos.py:124-126`

```python
except ImportError as e:
    console.print(f"[yellow]Warning: Could not import transcription service: {e}[/yellow]")
    return None
```

If the transcription service can't be imported, `transcribe_sample` returns `None` silently. The caller in `scan_videos` then skips smart matching with no indication that it's degraded.

**Better**: Log clearly that "Smart matching disabled - transcription service unavailable"

---

### 7. **PATTERN VIOLATION: sys.path Manipulation** (LOW)
**Location**: `kb/videos.py:118-119`

```python
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

This is inside the function, executed every time `transcribe_sample` is called. Other modules do this at module level (`inbox.py:27`, `serve.py:33`).

**Should**: Move to module level OR use proper relative imports.

---

### 8. **MISSING: Config Load Happens Twice** (LOW)
**Location**: `kb/videos.py:298`

```python
def scan_videos(...):
    config = load_config()
```

And again in `reorganize_videos` (line 421):
```python
def reorganize_videos(...):
    config = load_config()
```

Each function reloads config. While not a bug, it is:
1. Wasteful (config does not change mid-session)
2. Could cause issues if config file is modified between calls

**Pattern in other modules**: Load config once at module level (see `serve.py:38-43`).

---

### 9. **EDGE CASE: Progress Bar During `--cron` Mode** (LOW)
**Location**: `kb/videos.py:325-332`

```python
with Progress(
    ...
    disable=cron
) as progress:
```

Good - disabled in cron mode. But line 364:
```python
progress.update(task, description=f"Transcribing sample: {video['filename'][:30]}...")
```

This still runs (no-op when disabled) but the string formatting happens. Minor inefficiency.

---

## Acceptance Criteria Check

| AC | Description | Status | Notes |
|----|-------------|--------|-------|
| AC1 | `kb scan-videos` finds all videos in configured paths | PASS | Works per code review |
| AC2 | Existing transcripts are correctly matched via partial transcription | PARTIAL | Works but has edge cases |
| AC3 | Inventory JSON tracks link status and transcript IDs | PARTIAL | Does not handle ID stability or stale entries |

---

## Code Quality

| Aspect | Rating | Notes |
|--------|--------|-------|
| Documentation | Good | Docstrings present, clear usage |
| Error handling | Medium | Some silent failures |
| Pattern consistency | Medium | Import style differs from other modules |
| Edge cases | Poor | Several unhandled scenarios |

---

## Recommendations

### Must Fix (REVISE)
1. **Fix Video ID stability** - Use `original_path` or content hash instead of current path
2. **Handle stale inventory entries** - Mark missing or remove
3. **Make filename matching stricter** - Check if already linked or compare metadata

### Should Fix
4. Move `sys.path.insert` to module level
5. Load config once at module level
6. Better logging when smart matching is unavailable

### Nice to Have
7. Add `--force` flag to rescan even if linked
8. Add inventory stats to summary table
9. Consider using `click` or `argparse` groups for consistency with other modules

---

## Gate Decision

**REVISE** - Return to executor to fix critical video ID stability bug and inventory stale entry handling.

These are fundamental to the inventory concept and will cause data corruption if not addressed before Phase 2 (reorganization) which moves files.

---

## Test Commands (for Mac)

```bash
# Basic scan (should work with missing volumes as warnings)
kb scan-videos --quick

# Check inventory file
cat ~/.kb/video-inventory.json | jq '.videos | keys | length'

# Verify config loaded
kb config  # Should show video_sources
```
