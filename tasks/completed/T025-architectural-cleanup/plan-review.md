# Plan Review: T025 Architectural Cleanup (Phase 1)

## Gate Decision: READY

**Summary:** The plan is thorough and well-researched. All 14 import sites are correctly identified with accurate line numbers. The phased approach is sound. I found one major issue (naming collision risk), one moderate issue (caching behavior change), and several minor items that should be addressed but do not block execution.

---

## Open Questions Validation

### Resolved Questions
| # | Question | Resolution | Assessment |
|---|----------|------------|------------|
| 1 | How to handle `console.print()` warning in `load_config()` when it moves to `config.py`? | Use `warnings.warn()` (Option A) | Correct choice. `warnings.warn()` is stdlib-only, avoids coupling a low-level config module to Rich, and matches Python conventions for non-fatal issues. The original Rich markup (`[yellow]...[/yellow]`) would be stripped by `warnings.warn()` -- the executor should use a plain string like `f"Could not load config: {e}"` without Rich markup. |

### New Questions Discovered
None. All decisions can be made autonomously.

---

## Issues Found

### Critical (Must Fix)
None.

### Major (Should Fix)

1. **`kb/config/` directory naming collision** -- The repo already contains a `kb/config/` directory (holding `analysis_types/*.json` data files). Creating `kb/config.py` means the filesystem will have both `kb/config.py` (file) and `kb/config/` (directory) as siblings. This works at the filesystem level, and Python will resolve `import kb.config` to the `.py` file (since the directory lacks `__init__.py`). However:
   - `kb/tests/test_carousel_templates.py:31` accesses `kb/config/analysis_types` via a hardcoded filesystem path (`os.path.join(REPO_ROOT, "kb", "config", "analysis_types")`). This will still work fine since it's a filesystem path, not a Python import.
   - `kb/tests/test_judge_versioning.py:718,735` also access `kb/config/analysis_types` via `Path(__file__).parent.parent / "config" / "analysis_types"`. This also works fine since it's a `Path` join, not an import.
   - No code does `import kb.config.analysis_types` or similar Python imports.
   - **Verdict:** This will work, but it is confusing. The executor should add a comment at the top of `kb/config.py` noting this distinction (e.g., `# Note: kb/config/ directory (sibling) contains analysis_types JSON data files -- it is NOT this Python module.`). An alternative name like `kb/settings.py` or `kb/conf.py` would avoid the collision entirely, but `config.py` is the most conventional name and the plan should proceed with it.
   - **Fix:** Add clarifying comment to `kb/config.py`. No name change needed.

2. **Caching introduces shared-object semantics** -- Currently each module's `_config = load_config()` gets an independent dict (via `DEFAULTS.copy()` + merge). With caching, all 8 modules that call `load_config()` at module level will receive the **same dict object**. I verified that no module currently mutates `_config` (no `_config[...] = ...`, no `.update()`, no `.pop()`), so this is safe today. But it is a subtle behavior change that should be documented.
   - **Fix:** Add a comment in the caching design section or in the `load_config()` docstring: "Note: returns the same cached dict to all callers. Do not mutate the returned dict; call `_reset_config_cache()` + `load_config()` if fresh config is needed."

### Minor

1. **`DEFAULTS.copy()` shallow copy analysis is correct but incomplete** -- The plan notes that `DEFAULTS.copy()` is shallow and that merge logic replaces top-level key dicts entirely. This is accurate. However, the `DEFAULTS` dict itself is a module-level constant that should not be mutated. Currently `load_config()` starts with `config = DEFAULTS.copy()`, which creates a new top-level dict. But if no config file exists, `config` shares all nested dicts with `DEFAULTS` (shallow copy). With caching, this means the cached config and `DEFAULTS` share nested objects. Since nothing mutates the cached config, this is fine. No fix needed, but worth being aware of.

2. **Rich markup in `warnings.warn()` output** -- Line 179 currently outputs `[yellow]Warning: Could not load config: {e}[/yellow]`. When switching to `warnings.warn()`, the Rich markup brackets must be stripped. The executor should use: `warnings.warn(f"Could not load config: {e}")`. The plan text in Task 1.3 mentions this but does not show the exact replacement string.

3. **`remote_mounts` uses `DEFAULTS.get()` not `DEFAULTS[]`** -- At line 177 of `__main__.py`, the merge for `remote_mounts` uses `DEFAULTS.get("remote_mounts", {})` while all other merges use `DEFAULTS["key"]`. This inconsistency suggests `remote_mounts` was added later. The new `config.py` should preserve this exact behavior (it is intentional defensiveness, not a bug). The plan correctly says "existing merge logic unchanged" which covers this.

4. **The `os.environ.get("EDITOR")` call at line 418 stays in `__main__.py`** -- This is NOT part of config loading and correctly stays. No action needed, but noting it for completeness since the user asked about env variables.

5. **Template comment at line 454** -- The plan's Decision Matrix correctly identifies that the config editor template at `__main__.py:454` says `# See defaults in kb/__main__.py` and should be updated to `# See defaults in kb/config.py`. This is in Phase 2 (Task 2.3 implicitly covers it via "verify __main__.py still works") but should be an explicit task item to avoid being overlooked.
   - **Fix:** Add an explicit task under Phase 2 to update the string at line 454 from `kb/__main__.py` to `kb/config.py`.

6. **No `__all__` in `kb/config.py`** -- The plan does not mention adding `__all__` to the new module. The existing `__main__.py` also lacks `__all__` (confirmed by grep), so this is consistent. However, since `kb/config.py` will also export internal names (`_cached_config`, `_reset_config_cache`), an `__all__` would clarify the public API. This is optional and low priority.

---

## Verification Results

### Import Site Completeness: PASS
Grep for `from kb.__main__ import` across all `.py` files found exactly the 14 sites (11 source + 3 test) listed in the plan. No missed imports. No shell scripts or other file types reference `kb.__main__`.

### Line Number Accuracy: PASS (all 14 spot-checked)
| File | Plan Says | Actual | Match |
|------|-----------|--------|-------|
| `kb/core.py` | line 20 | line 20 | YES |
| `kb/analyze.py` | line 40 | line 40 | YES |
| `kb/serve.py` | line 63 | line 63 | YES |
| `kb/dashboard.py` | line 21 | line 21 | YES |
| `kb/cli.py` | line 30 | line 30 | YES |
| `kb/publish.py` | line 24 | line 24 | YES |
| `kb/inbox.py` | line 29 | line 29 | YES |
| `kb/videos.py` | line 44 | line 44 | YES |
| `kb/sources/cap.py` | line 29 | line 29 | YES |
| `kb/sources/volume.py` | line 31 | line 31 | YES |
| `kb/sources/zoom.py` | line 52 | line 52 | YES |
| `kb/tests/test_serve_integration.py` | lines 465,472,478 | lines 465,472,478 | YES |
| `kb/tests/test_judge_versioning.py` | line 685 | line 685 | YES |
| `kb/tests/test_render.py` | line 581 | line 581 | YES |

### Import Content Accuracy: PASS
All import statements match exactly what the plan documents (checked the imported names against actual source).

### Circular Import Risk: PASS
`kb/config.py` will import only: `pathlib.Path`, `os`, `warnings`, and `yaml` (lazily inside `load_config()`). No imports from `kb.*`. Confirmed that `load_config()`, `expand_path()`, and `get_paths()` have no dependencies on any `kb.*` module.

### Backward Compatibility: PASS
- `pyproject.toml` entry point (`kb = "kb.__main__:main"`) stays unchanged.
- `__main__.py` re-exports all config symbols, so `from kb.__main__ import load_config` continues to work.
- `COMMANDS` stays in `__main__.py`.
- No external scripts or shell scripts import from `kb.__main__`.

### Test Coverage: PASS
- Phase 4 includes running `python3 -m pytest kb/tests/ -v`.
- Test file imports are correctly categorized: 3 `DEFAULTS` imports to update, 2 `COMMANDS` imports to leave unchanged.
- No tests mock `load_config()`, so the caching change won't break test isolation.

---

## Plan Strengths

- Extremely detailed import mapping table -- every file, line number, old import, and new import is specified. This leaves no ambiguity for the executor.
- Correct decision to keep `COMMANDS` in `__main__.py` -- it's CLI-specific, not config.
- The 4-phase structure (create, update source, update importers, verify) is the right order of operations.
- The caching design is simple and appropriate (global variable vs `lru_cache` reasoning is sound).
- Backward compatibility via re-export is the right call for a safe refactor.
- The plan correctly identifies that `yaml` is imported lazily and that this pattern should be preserved.

---

## Recommendations

### Before Proceeding
- [ ] Executor should add a clarifying comment at the top of `kb/config.py` noting the `kb/config/` directory is a sibling data directory, not this module
- [ ] Add explicit task in Phase 2 to update the template string at `__main__.py:454` from `kb/__main__.py` to `kb/config.py`
- [ ] Strip Rich markup from the `warnings.warn()` message (no `[yellow]...[/yellow]`)
- [ ] Add a note in the `load_config()` docstring that the returned dict is cached and should not be mutated

### Consider Later
- Adding `__all__` to `kb/config.py` to clarify public API
- Consider renaming `kb/config/` data directory to `kb/config_data/` or similar in a future phase to eliminate the naming ambiguity (low priority, purely cosmetic)
