# T018: KB Missing Analyses Detection

## Meta
- **Status:** EXECUTING_PHASE_1
- **Created:** 2026-02-02
- **Last Updated:** 2026-02-02
- **Blocked Reason:** —

## Task

Add a "missing analyses" feature to the KB system that detects which videos are missing their decimal's default analysis types and allows batch reanalysis.

### Context

Each decimal category has `default_analyses` configured in registry.json (e.g., `50.01.01` defaults to `["summary", "guide", "resources"]`). When a new analysis type is added to a decimal's defaults, existing videos in that decimal won't have that analysis run yet.

Currently there's no way to:
1. See which videos are missing their decimal's default analyses
2. Trigger batch reanalysis for just the missing ones

### User Stories

1. **As Blake**, when I add `linkedin_post` to `50.01.01` default analyses, I want to see "5 videos missing `linkedin_post`" so I can decide whether to batch-run them.

2. **As Blake**, I want `kb missing` or `kb status` to show a summary of videos missing their decimal-specific default analyses.

3. **As Blake**, I want to trigger batch analysis for just the missing analyses (not re-run ones that already exist).

### Requirements

- New CLI command: `kb missing` or integrated into existing `kb` menu
- Per-decimal breakdown showing which videos need which analyses
- Option to run missing analyses (interactive selection or batch all)
- Should respect the compound analysis `requires` field (auto-run dependencies)
- Should integrate with existing `analyze.py` infrastructure

### References

- `kb/analyze.py` — existing analysis infrastructure with `run_analysis_with_deps()`
- `kb/__main__.py` — existing CLI menu and decimal config UI
- `config/registry.json` — decimal definitions with `default_analyses`
- `config/analysis_types/*.json` — analysis type definitions with `requires` field

---

## Plan

### Overview

Add a "missing analyses" feature to detect which transcripts are missing their decimal category's default analysis types and allow batch reanalysis. This is distinct from the existing "pending" feature in `analyze.py` which checks if ANY analysis type is missing — this new feature specifically checks against each decimal's configured `default_analyses`.

### Architecture

**Core Concept:**
```
For each transcript in KB:
  1. Get its decimal category
  2. Get that decimal's default_analyses from registry
  3. Check which of those defaults are missing from transcript.analysis
  4. Report and optionally batch-run the missing ones
```

**Data Flow:**
```
kb missing
  └─ scan_missing_analyses()
       ├─ load_registry() → get decimals with default_analyses
       ├─ get_all_transcripts() → get all transcript files
       └─ For each transcript:
            └─ Compare transcript.analysis keys vs decimal.default_analyses
  └─ Display summary by decimal
  └─ Option to run missing → run_analysis_with_deps() for each
```

**Key Files:**
- `kb/analyze.py` — Add `get_missing_analyses()`, `scan_missing_by_decimal()`, `run_missing_batch()` functions
- `kb/__main__.py` — Add `"missing"` command to COMMANDS dict

### Decision Matrix

| Decision | Options | Recommendation | Rationale |
|----------|---------|----------------|-----------|
| CLI Interface | A) New command `kb missing` B) Add to existing `kb analyze` | **A) New command** | Clearer separation of concerns; `analyze` is already complex |
| Output Format | A) Simple list B) Per-decimal grouping C) Both | **C) Both** | Summary first, then detailed breakdown on request |
| Batch Mode | A) Confirm each B) Batch all C) Interactive select | **C) Interactive select** | Most flexible; user can review and choose |
| Re-run existing? | A) Skip if done B) Option to re-run | **A) Skip if done** | Consistent with existing `analyze.py` behavior; use `--force` for re-run |

### Phases

---

### Phase 1: Core Detection Logic
**Objective**: Implement the core function to detect missing analyses per transcript and per decimal.

**Tasks**:
1. Add `get_decimal_defaults(decimal: str) -> list[str]` function in `kb/analyze.py`:
   - Loads registry, gets `default_analyses` for the given decimal
   - Falls back to empty list if decimal not found or no defaults

2. Add `get_transcript_missing_analyses(transcript_data: dict) -> list[str]` function:
   - Gets decimal from transcript
   - Gets decimal's default_analyses
   - Returns list of analysis types that are in defaults but NOT in `transcript_data["analysis"]`

3. Add `scan_missing_by_decimal() -> dict[str, list[dict]]` function:
   - Iterates all transcripts via `get_all_transcripts()`
   - For each, calls `get_transcript_missing_analyses()`
   - Groups results by decimal: `{ "50.01.01": [{"path": ..., "title": ..., "missing": [...]}] }`
   - Returns the grouped dict

**Acceptance Criteria**:
- [ ] `get_decimal_defaults()` returns correct defaults for known decimals
- [ ] `get_transcript_missing_analyses()` correctly identifies missing analyses
- [ ] `scan_missing_by_decimal()` returns properly grouped results
- [ ] Functions work with both populated and empty registries

---

### Phase 2: CLI Command & Display
**Objective**: Add `kb missing` command with summary and detailed output.

**Tasks**:
1. Add `"missing"` entry to `COMMANDS` dict in `kb/__main__.py`:
   ```python
   "missing": {
       "label": "Missing",
       "description": "Show transcripts missing their decimal's default analyses",
       "module": "kb.analyze",
   }
   ```

2. Add `show_missing_analyses()` function in `kb/analyze.py`:
   - Calls `scan_missing_by_decimal()`
   - Displays Rich table summary:
     - Column: Decimal
     - Column: Decimal Name
     - Column: Total Transcripts
     - Column: Missing Analysis Types (comma-separated unique types)
     - Column: Count Needing Analysis
   - Shows "All transcripts have their default analyses!" if nothing missing

3. Add `--detailed` flag to show per-transcript breakdown:
   - Shows each transcript title and its specific missing types
   - Grouped under decimal headers

4. Wire up CLI argument parsing in `analyze.py:main()` to route `kb missing` to `show_missing_analyses()`

**Acceptance Criteria**:
- [ ] `kb missing` shows summary table of decimals with missing analyses
- [ ] `kb missing --detailed` shows per-transcript breakdown
- [ ] Clear messaging when nothing is missing
- [ ] Styling consistent with rest of KB CLI (Rich tables, cyan/green colors)

---

### Phase 3: Batch Analysis Execution
**Objective**: Allow running all missing analyses in batch mode.

**Tasks**:
1. Add `run_missing_analyses()` function in `kb/analyze.py`:
   - Takes optional `decimal_filter: str` to limit to one decimal
   - Shows summary of what will be analyzed
   - Confirmation prompt before proceeding
   - For each transcript with missing analyses:
     - Calls `analyze_transcript_file()` with just the missing types
     - Uses `run_analysis_with_deps()` internally (already handles requires)
   - Shows progress and results

2. Add interactive selection mode:
   - After showing summary, offer options:
     - "Run all missing analyses"
     - "Select specific decimal to run"
     - "Cancel"
   - If specific decimal selected, filter to just that decimal's transcripts

3. Add `--run` flag to `kb missing`:
   - `kb missing --run` — run all missing with confirmation
   - `kb missing --run --decimal 50.01.01` — run only for specific decimal

4. Add `--yes` flag to skip confirmation (for scripting/cron)

**Acceptance Criteria**:
- [ ] `kb missing --run` shows summary and prompts before running
- [ ] `kb missing --run --decimal X` filters to specific decimal
- [ ] `kb missing --run --yes` runs without prompting (for automation)
- [ ] Progress displayed during batch run
- [ ] Handles API rate limiting gracefully (existing retry logic in `analyze_transcript`)
- [ ] Summary of results shown at end

---

### Phase 4: Integration & Polish
**Objective**: Integrate into main menu and add finishing touches.

**Tasks**:
1. Add "Missing Analyses" option to main `kb` menu:
   - Position after "Analyze" in menu
   - Opens `show_missing_analyses()` with interactive mode

2. Add to `show_config()` status display:
   - Show count of transcripts missing default analyses (quick health check)
   - Example: "Missing analyses: 5 transcripts across 2 decimals"

3. Add `--summary` flag for compact output (useful in scripts):
   - Just prints "X transcripts missing Y analyses across Z decimals"
   - Exit code 0 if none missing, 1 if some missing (for scripting)

4. Documentation:
   - Add usage examples to docstring in `analyze.py`
   - Update CLAUDE.md if helpful patterns emerge

**Acceptance Criteria**:
- [ ] "Missing Analyses" appears in main `kb` menu
- [ ] Config status shows quick missing count
- [ ] `kb missing --summary` returns scriptable output with exit codes
- [ ] All new functionality documented in module docstring

---

### Implementation Notes

**Existing Patterns to Follow:**

From `kb/analyze.py`:
```python
# Getting transcripts with analysis status
transcripts = get_all_transcripts()  # Returns list with "done_types", "pending_types"

# Running analysis with dependency handling
result, prerequisites_run = run_analysis_with_deps(
    transcript_data=transcript_data,
    analysis_type=analysis_type,
    model=model,
    existing_analysis=existing_analysis
)
```

From `kb/__main__.py`:
```python
# Adding new command
COMMANDS = {
    "missing": {
        "label": "Missing",
        "description": "Show transcripts missing default analyses",
        "module": "kb.analyze",
    }
}
```

**Key Insight:**
The existing `get_all_transcripts()` in `analyze.py` already computes `pending_types` but it's based on ALL analysis types, not decimal-specific defaults. The new code needs to compute "missing from defaults" which is a subset.

**Edge Cases:**
- Transcript with decimal not in registry (skip, warn)
- Decimal with no `default_analyses` configured (empty list = nothing missing)
- Transcript with no decimal field (legacy data, skip with warning)
- Analysis type in defaults but not available in system (skip, warn)

### Estimated Complexity
- Phase 1: Low (~60 lines) — Core detection functions
- Phase 2: Medium (~100 lines) — CLI display and formatting
- Phase 3: Medium (~80 lines) — Batch execution logic
- Phase 4: Low (~40 lines) — Integration and polish
- Total: ~280 lines of new code, primarily in `kb/analyze.py`

---

## Plan Review

**Reviewed:** 2026-02-02
**Reviewer:** Plan Review Agent
**Gate Decision:** READY ✅

### Summary

Solid, well-structured plan. The planner correctly identified the distinction between the existing "pending" feature (checks against ALL analysis types) and the new "missing" feature (checks against decimal-specific defaults). The architecture follows existing patterns and the phased approach is appropriate.

### Findings

**Strengths:**
- Correctly uses `load_registry()` from `kb.core`
- Leverages existing `run_analysis_with_deps()` for dependency handling
- Follows established patterns in `kb/analyze.py` and `kb/__main__.py`
- Edge cases are well-considered

**Minor Issues (2):**
1. Phase 2 mentions routing via `analyze.py:main()` but should use COMMANDS dict pattern (already shown in plan)
2. Registry path reference should clarify it's at `KB_ROOT/config/` not project config/

**No Critical Issues Found.**

### Gate Verdict

**READY** — Plan is implementable as-is. Minor issues are clarifications only.

---

## Execution Log

{Executor fills this section}

---

## Code Review Log

{Code Reviewer fills this section}

---

## Completion

{Final summary when done}
