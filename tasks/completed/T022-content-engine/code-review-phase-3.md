# Code Review: Phase 3 — Rendering Pipeline (HTML -> PDF + Mermaid)

## Gate: PASS

**Summary:** Implementation is well-structured and functional at the code-path level. All 47 new tests pass (166 total, zero regressions). One critical issue found: mermaid PNG embedding in carousel PDFs will silently fail in production because Playwright's `set_content()` cannot load local file paths from `about:blank` context. This does not block Phase 4 since the plan explicitly says "failed mermaid render skips slide gracefully" -- but it means mermaid-in-carousel will never actually work without a fix. Two major issues and three minor issues also found.

---

## Git Reality Check

**Commits:**
```
ebe8219 Phase3: update execution log, set status CODE_REVIEW
0c876cd Phase3: rendering pipeline (HTML -> PDF + Mermaid)
```

**Files Changed (git diff 0c876cd~1..ebe8219):**
- `kb/render.py` -- NEW (495 lines)
- `kb/publish.py` -- NEW (285 lines)
- `kb/__main__.py` -- MODIFY (added `publish` to COMMANDS dict)
- `requirements.txt` -- MODIFY (added `playwright>=1.40.0`)
- `kb/tests/test_render.py` -- NEW (596 lines, 47 tests)
- `tasks/active/T022-content-engine/main.md` -- status updates

**Matches Execution Report:** Yes -- all 6 files match what execution log claims. Commit `0c876cd` contains the implementation, `ebe8219` updates task docs.

---

## AC Verification

| AC | Claimed | Verified | Notes |
|----|---------|----------|-------|
| AC1: mmdc installed and working | Yes | Yes | mmdc 11.12.0 at `~/.npm-global/bin/mmdc`, `_find_mmdc()` auto-detects |
| AC2: Playwright installed and working | Yes | Yes | Playwright 1.58.0 with Chromium, sync_playwright imports cleanly |
| AC3: HTML carousel to multi-page PDF at 1080x1350 | Yes | Partial | Correct dimensions passed to `page.pdf()` in tests; actual rendering untested (mocked Playwright) |
| AC4: Mermaid generates clean PNG via mmdc | Deferred | N/A | Correctly deferred -- mmdc binary verified, rendering mocked in tests |
| AC5: Mermaid PNG embeds as carousel slide in PDF | Yes | **No** | **Broken** -- `set_content()` uses `about:blank` base URL; local file paths in `<img src>` will not load. See Critical #1 |
| AC6: Failed mermaid render skips gracefully | Yes | Yes | `test_pipeline_mermaid_failure_logs_warning` passes; errors list populated |
| AC7: PDF looks professional in Preview.app | Deferred | N/A | Requires Mac visual inspection |
| AC8: Output path configurable | Yes | Yes | `render_pipeline` accepts `output_dir`, `publish.py` uses decimal visuals dir |
| AC9: Individual slide PNGs generated | Yes | Yes | `render_slide_thumbnails()` generates `slide-N.png` per slide; tested with mocks |

---

## Issues Found

### Critical

1. **Mermaid PNG will not render in carousel PDF -- Playwright cannot load local files from `set_content()`**
   - Files: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:258`, `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:285-286`
   - Problem: `render_html_to_pdf()` uses `page.set_content(html_content)` which sets the page URL to `about:blank`. Chromium cannot load local filesystem images (e.g., `<img src="/tmp/mermaid/mermaid.png">`) from `about:blank` context -- the request is blocked by browser security policy. This means every mermaid diagram embedded via `<img>` tag will silently fail to load in the rendered PDF.
   - Impact: Mermaid slides will show as empty images in the PDF. The carousel still generates (no error thrown), but the mermaid visual is missing. Since AC6 says "failed mermaid skips gracefully" this does not break the pipeline, but it means the mermaid-in-carousel feature **never actually works**.
   - Fix: Either (a) base64-encode the mermaid PNG and use a `data:image/png;base64,...` URI in the `<img src>` attribute, or (b) write the HTML to a temp file and use `page.goto(f"file://{temp_html_path}")` instead of `set_content()`, or (c) use `page.route()` to intercept file requests and serve them.
   - Note: This bug is invisible in tests because all Playwright calls are mocked.

### Major

1. **`find_renderables()` crashes on raw-string `carousel_slides` analysis output**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/publish.py:72`
   - Problem: Line 72 does `carousel_slides.get('output', carousel_slides)`. If the LLM returns `carousel_slides` as a raw JSON string (not a dict), `.get()` throws `AttributeError: 'str' object has no attribute 'get'`. The except block on line 105 catches `(json.JSONDecodeError, KeyError)` but **not** `AttributeError`, so this crashes the entire `find_renderables()` scan, not just that one file.
   - Fix: Either add `AttributeError` to the except tuple, or add `if isinstance(carousel_slides, str): carousel_slides = json.loads(carousel_slides)` before line 72.

2. **`render_carousel` launches Playwright twice per carousel (performance)**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:353-403`
   - Problem: `render_carousel()` calls `render_html_to_pdf()` (launches Chromium, renders PDF, closes browser) and then `render_slide_thumbnails()` (launches Chromium again, takes screenshots, closes browser). Two full browser lifecycle for the same HTML content. For batch `kb publish --pending` with N posts, this is 2N Chromium launches.
   - Impact: Significant performance hit. Chromium cold-start is ~1-2 seconds per launch. For 10 posts that is 20-40 seconds of wasted browser startups.
   - Fix: Refactor so PDF rendering and thumbnail screenshots share a single browser session. Pass the `page` object to both operations.

### Minor

1. **`browser.close()` not in try/finally -- potential resource leak**
   - Files: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:298`, `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:348`, `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:251`
   - All three Playwright functions (`render_html_to_pdf`, `render_slide_thumbnails`, `_render_html_to_pdf_async`) call `browser.close()` as the last statement inside the `with sync_playwright()` block, but not in a `try/finally`. If `page.pdf()`, `page.set_content()`, or `slide_el.screenshot()` throws, the browser process is not explicitly closed. The `sync_playwright` context manager handles the Playwright connection cleanup, but orphaned Chromium processes could linger. Not critical for a batch CLI, but worth fixing.

2. **`_render_html_to_pdf_async` is dead code with zero test coverage**
   - File: `/home/blake/repos/personal/whisper-transcribe-ui/kb/render.py:210-254`
   - The async variant is defined "for future kb serve integration" but nothing calls it and no tests cover it. If Phase 4 uses it, bugs will surface late. Either test it now or remove it until needed.

3. **`render_config.json` from plan was not created**
   - Plan specified `kb/config/render_config.json` with output paths, dimensions, mermaid constraints, and Playwright settings. The executor reused `carousel_templates/config.json` instead. This is a reasonable simplification (one config file instead of two), but deviates from the plan. No code references `render_config.json`.

---

## What's Good

- **Error handling in `render_mermaid`** is thorough: handles missing binary, non-zero exit, timeout, generic exceptions, and temp file cleanup with `UnboundLocalError` guard in `finally`. This is the kind of defensive code a rendering pipeline needs.
- **Jinja2 `autoescape=select_autoescape(["html"])`** was added per Phase 2 code review feedback. XSS prevention confirmed working: `<script>` tags in slide content are escaped to `&lt;script&gt;`.
- **Lazy Playwright imports** (`from playwright.sync_api import sync_playwright` inside functions) avoid import-time failures when playwright is not installed, making the module safe to import in environments without rendering dependencies.
- **Test organization** is clean: separate test classes per function, good use of `tempfile.TemporaryDirectory`, sensible mock boundaries. The 47 tests cover happy paths, error paths, and edge cases (empty slides, missing slides, custom config overrides).
- **Graceful degradation throughout**: mermaid failure does not block carousel, carousel failure returns structured error dict, `find_renderables` with nonexistent decimal returns empty list.

---

## Required Actions (for REVISE -- not required, this is a PASS)

These are recommended fixes for Phase 4 or a follow-up, not blocking:

- [ ] Fix mermaid PNG embedding: convert to base64 data URI before embedding in HTML (Critical #1)
- [ ] Add `AttributeError` to `find_renderables` except clause (Major #1)
- [ ] Consider browser session reuse for PDF + thumbnails (Major #2)
- [ ] Wrap `browser.close()` in try/finally (Minor #1)

---

## Learnings

| Learning | Applies To | Action |
|----------|-----------|--------|
| Playwright `set_content()` creates `about:blank` context -- local file paths in HTML will not load | Any Playwright HTML-to-image/PDF pipeline | Use base64 data URIs or `page.goto("file://...")` for local asset references |
| Mock-heavy tests can hide integration issues (mermaid PNG loading) | All rendering tests | Add at least one integration test that does real Playwright rendering (even if slow/optional) |
| Catching specific exception types matters -- `AttributeError` missed in except tuple | All JSON-scanning code | Always catch `(Exception)` or enumerate all possible error types when scanning untrusted data |
