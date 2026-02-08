# T022 Content Engine — Smoke Test

Run on Mac after `git pull` on `feat/content-engine`.

---

## Round 1: Does it run?

### 1.1 Imports and setup

```bash
cd ~/repos/personal/whisper-transcribe-ui
python3 -c "from kb.render import render_pipeline, render_carousel, render_mermaid; print('render.py OK')"
python3 -c "from kb.publish import find_renderables, render_one; print('publish.py OK')"
python3 -c "from playwright.sync_api import sync_playwright; print('playwright OK')"
python3 -c "import jinja2; print(f'jinja2 {jinja2.__version__} OK')"
```

- [ ] All 4 print OK with no errors

### 1.2 Tests pass

```bash
python3 -m pytest kb/tests/ -v --tb=short 2>&1 | tail -20
```

- [ ] 188 tests pass, 0 failures

### 1.3 CLI commands exist

```bash
python3 -m kb analyze --help | grep -q "judge" && echo "judge flag OK"
python3 -m kb publish --help
```

- [ ] `--judge` flag exists in analyze help
- [ ] `kb publish` shows help with `--pending`, `--regenerate`, `--dry-run`

---

## Round 1: LLM pipeline (needs GEMINI_API_KEY)

Pick a transcript that already has analysis. Find one:

```bash
# List some decimals with existing analyses
python3 -m kb analyze --list-types
```

### 1.4 linkedin_v2 analysis

```bash
# Pick a decimal with a transcript, e.g. 50.10.01
python3 -m kb analyze -t linkedin_v2 -d <DECIMAL>
```

- [ ] Runs without error
- [ ] Output is a LinkedIn post (1200-1800 chars, has a hook)
- [ ] Output stored in transcript JSON under `linkedin_v2` key

### 1.5 Judge loop

```bash
python3 -m kb analyze -t linkedin_v2 --judge -d <DECIMAL>
```

- [ ] Runs linkedin_v2 first
- [ ] Then runs linkedin_judge (shows scores)
- [ ] Then re-runs linkedin_v2 with feedback injected
- [ ] Final post is stored (overwrites first draft)
- [ ] Judge output preserved alongside final post

### 1.6 Visual format classifier

```bash
python3 -m kb analyze -t visual_format -d <DECIMAL>
```

- [ ] Returns `CAROUSEL` or `TEXT_ONLY`
- [ ] Has `confidence` score and `reasoning`
- [ ] If CAROUSEL: has `include_mermaid` and `suggested_slide_count`

### 1.7 Carousel slides (only if 1.6 returned CAROUSEL)

```bash
python3 -m kb analyze -t carousel_slides -d <DECIMAL>
```

- [ ] Returns JSON with `slides` array
- [ ] Each slide has `slide_number`, `type`, `content`, `words`
- [ ] Slide types include `hook` (first) and `cta` (last)
- [ ] 6-10 slides total
- [ ] Words per slide: 10-30

---

## Round 1: Rendering pipeline

### 1.8 Render a carousel (after 1.7 completes)

```bash
python3 -m kb publish --decimal <DECIMAL>
```

- [ ] Generates PDF in the decimal's visuals folder
- [ ] Generates slide thumbnail PNGs
- [ ] No errors in output

### 1.9 Check the PDF

- [ ] Open the generated PDF
- [ ] 1080x1350px per page (portrait)
- [ ] Dark purple gradient background (or light if configured)
- [ ] Hook slide: large bold text, accent bar
- [ ] Content slides: numbered, clean typography
- [ ] CTA slide: brand name at bottom
- [ ] Footer on each slide: "Blake Sims" + slide count (e.g. "3 / 8")
- [ ] Text is readable, not cramped or overflowing
- [ ] If mermaid slide exists: diagram renders (not blank or raw code)

### 1.10 Style verdict

Rate 1-5:
- [ ] Professional enough to post on LinkedIn? ___
- [ ] Would you swipe through this carousel? ___
- [ ] Colors/fonts feel right? ___
- [ ] Any slides that feel too empty or too full? Note which: ___

---

## Round 2: kb serve integration

### 2.1 Start the server

```bash
python3 -m kb serve
```

### 2.2 Posting queue shows linkedin_v2

- [ ] Open posting queue in browser
- [ ] `linkedin_v2` items appear (not old `linkedin_post`)
- [ ] Items have visual status badge (pending/generating/ready/text_only)

### 2.3 Approve triggers visual pipeline

- [ ] Click approve on a linkedin_v2 item
- [ ] Returns immediately (not blocking)
- [ ] Status shows "Generating..." spinner
- [ ] After pipeline completes: shows "Ready" with thumbnail
- [ ] PDF download link works

### 2.4 Text-only posts

- [ ] If visual_format classified as TEXT_ONLY: shows "Text Only" badge
- [ ] No carousel generated (expected)
- [ ] Post is still copy-pasteable from the preview

### 2.5 Error handling

- [ ] If anything fails: shows "Failed" badge with reason
- [ ] Post is NOT blocked — can still be manually posted

### 2.6 Batch publish

```bash
# Dry run first
python3 -m kb publish --pending --dry-run

# Then for real
python3 -m kb publish --pending
```

- [ ] Dry run shows list of what would be rendered
- [ ] Actual run processes all pending items
- [ ] Each item gets a PDF or "text_only" skip

---

## Known issues (non-blocking)

These were flagged in code reviews and are expected:

1. **Thread safety**: If you approve 2+ posts within seconds, the second may lose its visual_status update. Approve one at a time for now.
2. **Google Fonts**: If offline, Inter font falls back to system sans-serif. Looks slightly different but functional.
3. **Double browser launch**: Each carousel render starts Chromium twice (once for PDF, once for thumbnails). Slightly slow but works.

---

## After testing

If everything passes, the branch is ready to merge:

```bash
git checkout main
git merge feat/content-engine
git push
```

If style needs tweaking, the template files are:
- `kb/carousel_templates/dark-purple.html` — CSS styling
- `kb/carousel_templates/light.html` — alternate template
- `kb/carousel_templates/config.json` — colors, fonts, brand
