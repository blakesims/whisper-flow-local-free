# Smoke Test: T025 Architectural Cleanup Refactor

## Instructions for Claude

You are running a verification smoke test on the `refactor/architectural-cleanup` branch. This branch extracted modules from 3 god files and deleted dead code. Your job is to verify nothing is broken.

**Do not modify any source code.** Only run tests and commands. If you find issues, create an issue report at the end.

---

## Step 1: Setup

```bash
cd ~/repos/personal/whisper-transcribe-ui   # adjust if repo is elsewhere
git fetch origin
git checkout refactor/architectural-cleanup
git pull origin refactor/architectural-cleanup
```

Confirm you're on the right branch and it's up to date.

---

## Step 2: Run the full test suite

```bash
python3 -m pytest kb/tests/ -q
```

**Expected result:** 395 passed, 2 failed

The 2 known failures are:
- `test_carousel_templates.py::TestCarouselSlidesConfig::test_prompt_has_markdown_formatting_instruction`
- `test_carousel_templates.py::TestConfigBrandCtaText::test_prompt_mentions_title_and_subtitle`

These are pre-existing and NOT caused by the refactor. Any failures BEYOND these 2 are regressions.

---

## Step 3: Verify imports work

Run each of these in a single Python process. All should succeed with no errors:

```python
python3 -c "
from kb.config import load_config, KB_ROOT, CONFIG_DIR, DEFAULTS
from kb.transcription import get_transcription_service, ConfigManager
from kb.prompts import format_prerequisite_output, substitute_template_vars, render_conditional_template, resolve_optional_inputs
from kb.judge import run_with_judge_loop, run_analysis_with_auto_judge, AUTO_JUDGE_TYPES
from kb.serve_state import load_action_state, save_action_state, load_prompt_feedback, save_prompt_feedback
from kb.serve_scanner import get_action_mapping, scan_actionable_items, validate_action_id, ACTION_ID_SEP
from kb.serve_visual import run_visual_pipeline, _find_transcript_file, _update_visual_status
print('All direct imports OK')
"
```

Then verify backward-compatible imports (these should re-export from the original modules):

```python
python3 -c "
from kb.analyze import format_prerequisite_output, run_with_judge_loop, AUTO_JUDGE_TYPES
from kb.serve import load_action_state, get_action_mapping, run_visual_pipeline, ACTION_STATE_PATH, KB_ROOT
print('All backward-compat imports OK')
"
```

---

## Step 4: Smoke test CLI commands

Run each command and verify it doesn't crash. You don't need to check output correctness — just that it runs without import errors or tracebacks.

### 4a. Config loads
```bash
python3 -m kb config
```
Should print config paths and settings. Verify KB_ROOT points to a valid directory.

### 4b. Missing analyses
```bash
python3 -m kb missing --summary
```
Should print a summary of transcripts and their analysis status. May show "no missing analyses" if everything is up to date.

### 4c. Serve starts
```bash
timeout 5 python3 -m kb serve 2>&1 || true
```
Should show Flask starting on port 8765 (or similar). The `timeout` will kill it after 5 seconds. Look for import errors or tracebacks — those are failures.

### 4d. Dashboard starts
```bash
timeout 5 python3 -m kb dashboard 2>&1 || true
```
Should start without import errors.

### 4e. Transcription imports work (Mac-specific)
```bash
python3 -c "
from kb.transcription import get_transcription_service, ConfigManager
config = ConfigManager()
service = get_transcription_service(config)
print(f'Transcription service loaded: {type(service).__name__}')
print('Whisper-cpp integration OK')
"
```
This verifies the whisper-cpp transcription service can be instantiated on Mac.

### 4f. (Optional) Transcribe a short file
Only if there's a small audio/video file available for testing:
```bash
python3 -m kb transcribe file <path-to-short-audio> --decimal 50.00.01 --title "smoke-test" --dry-run
```
If `--dry-run` isn't supported, skip this step to avoid creating test data in the real KB.

---

## Step 5: Report results

### If everything passes:

Create a brief confirmation:
```
All smoke tests passed on Mac.
- Test suite: 395 pass, 2 known failures
- All imports (direct + backward-compat): OK
- CLI commands (config, missing, serve, dashboard): OK
- Transcription service instantiation: OK
```

Commit this as a note and push:
```bash
echo "T025 smoke test passed on Mac $(date +%Y-%m-%d)" >> tasks/smoke-test-t025-refactor.md
git add tasks/smoke-test-t025-refactor.md
git commit -m "verify: T025 refactor smoke test passed on Mac"
git push origin refactor/architectural-cleanup
```

### If any test fails or command crashes:

Create an issue report file at `tasks/t025-smoke-test-issues.md` with:
- Which step failed
- Full error output (traceback)
- Your assessment of severity (blocker vs minor)

Then commit and push:
```bash
git add tasks/t025-smoke-test-issues.md tasks/smoke-test-t025-refactor.md
git commit -m "verify: T025 smoke test found issues on Mac"
git push origin refactor/architectural-cleanup
```

---

## What was changed in T025

For context if you need to debug:

| Phase | Change | New Files |
|-------|--------|-----------|
| 1 | Config extracted from `__main__.py` | `kb/config.py` |
| 2 | 11 dead files deleted (2,462 lines) | — |
| 3 | Transcription imports centralized | `kb/transcription.py` |
| 4 | `analyze.py` split | `kb/prompts.py`, `kb/judge.py` |
| 5 | `serve.py` split | `kb/serve_state.py`, `kb/serve_scanner.py`, `kb/serve_visual.py` |
