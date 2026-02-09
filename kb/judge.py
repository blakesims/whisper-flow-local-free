"""
KB Judge Loop Orchestration

Manages the LLM judge improvement loop for analysis types that support
iterative refinement (e.g., linkedin_v2 with linkedin_judge).

Handles versioned drafts, score history, and alias management.
"""

import json
import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

from kb.config import load_config, DEFAULTS
from kb.prompts import (
    format_prerequisite_output,
    resolve_optional_inputs,
)

console = Console()

# Default model from config
_config = load_config()
DEFAULT_MODEL = _config.get("defaults", {}).get("gemini_model", DEFAULTS["defaults"]["gemini_model"])


# Mapping of analysis types that should auto-run a judge loop
AUTO_JUDGE_TYPES = {
    "linkedin_v2": "linkedin_judge",
}


def _get_starting_round(existing_analysis: dict, analysis_type: str) -> int:
    """Determine the starting round number for versioned judge loop.

    If there are already versioned keys (e.g., linkedin_v2_0, linkedin_v2_1),
    returns the next round number. If the alias exists without _round metadata,
    treats it as round 0 (backward compat).

    Returns:
        The round number to start from (0 if fresh, N if continuing).
    """
    # Check for existing versioned keys
    max_round = -1
    for key in existing_analysis:
        if key.startswith(f"{analysis_type}_"):
            suffix = key[len(f"{analysis_type}_"):]
            # Match linkedin_v2_N (not linkedin_v2_N_M which is edit versions)
            if suffix.isdigit():
                max_round = max(max_round, int(suffix))

    if max_round >= 0:
        return max_round + 1

    # Check if alias exists without _round (backward compat: treat as round 0)
    alias_data = existing_analysis.get(analysis_type)
    if alias_data and isinstance(alias_data, dict) and "_round" not in alias_data:
        return 0

    return 0


def _build_history_from_existing(existing_analysis: dict, analysis_type: str, judge_type: str) -> list[dict]:
    """Build history array from existing versioned keys.

    Returns list of dicts with round, draft, and judge data for all
    completed rounds found in existing_analysis.
    """
    history = []
    round_num = 0
    while True:
        draft_key = f"{analysis_type}_{round_num}"
        judge_key = f"{judge_type}_{round_num}"

        if draft_key not in existing_analysis:
            break

        entry = {
            "round": round_num,
            "draft": existing_analysis[draft_key].get("post", ""),
        }

        if judge_key in existing_analysis:
            judge_data = existing_analysis[judge_key]
            entry["judge"] = {
                "overall_score": judge_data.get("overall_score", 0),
                "scores": judge_data.get("scores", {}),
                "improvements": judge_data.get("improvements", []),
                "rewritten_hook": judge_data.get("rewritten_hook"),
            }

        history.append(entry)
        round_num += 1

    return history


def _build_score_history(existing_analysis: dict, judge_type: str) -> list[dict]:
    """Build score history array for _history metadata in alias.

    Returns list of dicts with round, overall, and criteria scores.
    """
    scores = []
    round_num = 0
    while True:
        judge_key = f"{judge_type}_{round_num}"
        if judge_key not in existing_analysis:
            break
        judge_data = existing_analysis[judge_key]
        scores.append({
            "round": round_num,
            "overall": judge_data.get("overall_score", 0),
            "criteria": judge_data.get("scores", {}),
        })
        round_num += 1
    return scores


def _update_alias(existing_analysis: dict, analysis_type: str, judge_type: str,
                  draft_result: dict, current_round: int):
    """Update the alias key (e.g., linkedin_v2) to point to the latest version.

    Adds _round and _history metadata to the alias.
    """
    alias = dict(draft_result)  # shallow copy
    alias["_round"] = current_round
    alias["_history"] = {
        "scores": _build_score_history(existing_analysis, judge_type),
    }
    existing_analysis[analysis_type] = alias


def run_with_judge_loop(
    transcript_data: dict,
    analysis_type: str,
    judge_type: str,
    model: str = DEFAULT_MODEL,
    max_rounds: int = 1,
    existing_analysis: dict | None = None,
    save_path: str | None = None
) -> tuple[dict, dict]:
    """
    Run an analysis type with an LLM judge improvement loop, saving versioned outputs.

    Produces versioned keys:
    - {analysis_type}_0: initial draft
    - {judge_type}_0: judge evaluation of draft 0
    - {analysis_type}_1: improved draft after judge feedback
    - {judge_type}_1: judge evaluation of draft 1
    - ...
    - {analysis_type}: alias pointing to latest, with _round and _history metadata

    History injection: each improvement round receives a JSON array of all prior
    drafts + judge evaluations via the {{judge_feedback}} template variable.

    Backward compat: if the alias exists without _round, it is preserved as-is
    and the versioned loop starts from round 0.

    Args:
        transcript_data: Full transcript data dict
        analysis_type: Name of the analysis type to run (e.g., 'linkedin_v2')
        judge_type: Name of the judge analysis type (e.g., 'linkedin_judge')
        model: Gemini model to use
        max_rounds: Number of judge improvement rounds (default 1)
        existing_analysis: Existing analysis results (updated in-place)
        save_path: Path to transcript file for saving results

    Returns:
        Tuple of (final_analysis_result, final_judge_result)
    """
    # Lazy imports to avoid circular dependency
    from kb.analyze import (
        analyze_transcript, run_analysis_with_deps,
        load_analysis_type, _save_analysis_to_file,
    )

    if existing_analysis is None:
        existing_analysis = transcript_data.get("analysis", {})

    transcript_text = transcript_data.get("transcript", "")

    # Determine starting round (handles backward compat)
    start_round = _get_starting_round(existing_analysis, analysis_type)

    # If alias exists without versioned keys, migrate it to round 0
    alias_data = existing_analysis.get(analysis_type)
    if start_round == 0 and alias_data and isinstance(alias_data, dict) and "_round" not in alias_data:
        # Existing unversioned result: save as _0 for history, then continue
        existing_analysis[f"{analysis_type}_0"] = dict(alias_data)
        # Check if there's also an unversioned judge
        if judge_type in existing_analysis:
            judge_data = existing_analysis[judge_type]
            if isinstance(judge_data, dict):
                existing_analysis[f"{judge_type}_0"] = dict(judge_data)
        start_round = 1  # Next round will be 1

    current_round = start_round

    # Step 1: Generate initial draft (round N)
    console.print(f"\n[bold cyan]Round {current_round}: Generating initial draft...[/bold cyan]")

    # Build history for judge_feedback injection (all prior rounds)
    history = _build_history_from_existing(existing_analysis, analysis_type, judge_type)

    if history:
        # We have prior rounds, inject history as judge_feedback
        judge_feedback_text = json.dumps(history, indent=2)

        analysis_def = load_analysis_type(analysis_type)
        prompt_context = resolve_optional_inputs(analysis_def, existing_analysis, transcript_text)
        prompt_context["judge_feedback"] = judge_feedback_text

        for req in analysis_def.get("requires", []):
            if req in existing_analysis:
                prompt_context[req] = format_prerequisite_output(existing_analysis[req])

        draft_result = analyze_transcript(
            transcript_text=transcript_text,
            analysis_type=analysis_type,
            title=transcript_data.get("title", ""),
            model=model,
            prerequisite_context=prompt_context
        )
    else:
        # Fresh start, no history
        draft_result, prereqs = run_analysis_with_deps(
            transcript_data=transcript_data,
            analysis_type=analysis_type,
            model=model,
            existing_analysis=existing_analysis
        )

    if "error" in draft_result:
        raise ValueError(f"Initial analysis failed: {draft_result.get('error')}")

    # Add metadata and save as versioned key
    draft_result["_model"] = model
    draft_result["_analyzed_at"] = datetime.now().isoformat()

    versioned_draft_key = f"{analysis_type}_{current_round}"
    existing_analysis[versioned_draft_key] = draft_result

    # Update alias to point to latest
    _update_alias(existing_analysis, analysis_type, judge_type, draft_result, current_round)

    # Save after draft
    if save_path:
        _save_analysis_to_file(save_path, transcript_data, existing_analysis)

    console.print(f"[green]Draft generated (round {current_round}).[/green] Character count: {draft_result.get('character_count', 'N/A')}")

    # Step 2: Always judge the initial draft
    console.print(f"\n[bold cyan]Round {current_round}: Running judge evaluation...[/bold cyan]")
    judge_result, _ = run_analysis_with_deps(
        transcript_data=transcript_data,
        analysis_type=judge_type,
        model=model,
        existing_analysis=existing_analysis
    )

    if "error" in judge_result:
        console.print(f"[yellow]Judge evaluation failed: {judge_result.get('error')}. Keeping current draft.[/yellow]")
        if save_path:
            _save_analysis_to_file(save_path, transcript_data, existing_analysis)
        return draft_result, judge_result

    # Display judge scores
    scores = judge_result.get("scores", {})
    overall = judge_result.get("overall_score", 0)
    console.print(f"[bold]Judge scores (overall: {overall:.1f}/5.0):[/bold]")
    for criterion, score in scores.items():
        color = "green" if score >= 4 else "yellow" if score >= 3 else "red"
        console.print(f"  [{color}]{criterion}: {score}/5[/{color}]")

    improvements = judge_result.get("improvements", [])
    if improvements:
        console.print(f"\n[bold]Improvements suggested: {len(improvements)}[/bold]")
        for imp in improvements:
            console.print(f"  [yellow]- {imp.get('criterion', '')}: {imp.get('suggestion', '')[0:100]}...[/yellow]")

    # Save judge as versioned key
    judge_result["_model"] = model
    judge_result["_analyzed_at"] = datetime.now().isoformat()
    versioned_judge_key = f"{judge_type}_{current_round}"
    existing_analysis[versioned_judge_key] = judge_result
    # Also store under the base judge key so run_analysis_with_deps can find it
    existing_analysis[judge_type] = judge_result

    # Update alias history with new judge score
    _update_alias(existing_analysis, analysis_type, judge_type, draft_result, current_round)

    if save_path:
        _save_analysis_to_file(save_path, transcript_data, existing_analysis)

    # Step 3: Improvement rounds (only if max_rounds > 0)
    for i in range(max_rounds):
        current_round += 1
        console.print(f"\n[bold cyan]Round {current_round}: Improving draft with feedback...[/bold cyan]")

        # Build full history for injection
        history = _build_history_from_existing(existing_analysis, analysis_type, judge_type)
        judge_feedback_text = json.dumps(history, indent=2)

        # Build context with judge_feedback for conditional template
        analysis_def = load_analysis_type(analysis_type)
        prompt_context = resolve_optional_inputs(analysis_def, existing_analysis, transcript_text)
        prompt_context["judge_feedback"] = judge_feedback_text

        # Add required prerequisites to context
        for req in analysis_def.get("requires", []):
            if req in existing_analysis:
                prompt_context[req] = format_prerequisite_output(existing_analysis[req])

        # Run the improved analysis
        improved_result = analyze_transcript(
            transcript_text=transcript_text,
            analysis_type=analysis_type,
            title=transcript_data.get("title", ""),
            model=model,
            prerequisite_context=prompt_context
        )

        if "error" not in improved_result:
            improved_result["_model"] = model
            improved_result["_analyzed_at"] = datetime.now().isoformat()

            # Save as versioned key
            versioned_draft_key = f"{analysis_type}_{current_round}"
            existing_analysis[versioned_draft_key] = improved_result
            draft_result = improved_result

            # Update alias
            _update_alias(existing_analysis, analysis_type, judge_type, draft_result, current_round)

            if save_path:
                _save_analysis_to_file(save_path, transcript_data, existing_analysis)

            console.print(f"[green]Improved draft generated (round {current_round}).[/green] Character count: {improved_result.get('character_count', 'N/A')}")

            # Judge the improved draft
            console.print(f"\n[bold cyan]Round {current_round}: Running judge evaluation...[/bold cyan]")
            judge_result, _ = run_analysis_with_deps(
                transcript_data=transcript_data,
                analysis_type=judge_type,
                model=model,
                existing_analysis=existing_analysis
            )

            if "error" not in judge_result:
                scores = judge_result.get("scores", {})
                overall = judge_result.get("overall_score", 0)
                console.print(f"[bold]Judge scores (overall: {overall:.1f}/5.0):[/bold]")
                for criterion, score in scores.items():
                    color = "green" if score >= 4 else "yellow" if score >= 3 else "red"
                    console.print(f"  [{color}]{criterion}: {score}/5[/{color}]")

                judge_result["_model"] = model
                judge_result["_analyzed_at"] = datetime.now().isoformat()
                existing_analysis[f"{judge_type}_{current_round}"] = judge_result
                existing_analysis[judge_type] = judge_result
                _update_alias(existing_analysis, analysis_type, judge_type, draft_result, current_round)

                if save_path:
                    _save_analysis_to_file(save_path, transcript_data, existing_analysis)
            else:
                console.print(f"[yellow]Judge evaluation failed for round {current_round}.[/yellow]")
        else:
            console.print(f"[yellow]Improvement round failed. Keeping previous draft.[/yellow]")
            current_round -= 1  # Revert round increment
            break

    # Final save
    if save_path:
        _save_analysis_to_file(save_path, transcript_data, existing_analysis)
        console.print(f"\n[green]Results saved to {save_path}[/green]")

    return draft_result, judge_result


def run_analysis_with_auto_judge(
    transcript_path: str,
    analysis_types: list[str],
    model: str = DEFAULT_MODEL,
    save: bool = True,
    skip_existing: bool = True,
    force: bool = False,
    judge_rounds: int = 0,
) -> dict:
    """
    Run analyses, auto-invoking the judge loop for types that have one.

    For analysis types in AUTO_JUDGE_TYPES (e.g., linkedin_v2), this runs
    run_with_judge_loop() instead of the plain analyze_transcript_file().
    Other types fall through to the standard pipeline.

    judge_rounds=0 (default): generate draft + judge scores only, no improvement.
    Improvement rounds happen interactively via kb serve 'i' shortcut.

    Called from CLI when `kb analyze -t linkedin_v2` is invoked.

    Args:
        transcript_path: Path to transcript JSON file
        analysis_types: List of analysis type names to run
        model: Gemini model to use
        save: Whether to save results
        skip_existing: Skip types already done with same model
        force: Force re-run
        judge_rounds: Number of judge improvement rounds

    Returns:
        Dict of analysis results keyed by type name
    """
    # Lazy import to avoid circular dependency
    from kb.analyze import analyze_transcript_file

    # Split into auto-judge types and regular types
    auto_judge = []
    regular = []
    for t in analysis_types:
        if t in AUTO_JUDGE_TYPES:
            auto_judge.append(t)
        else:
            regular.append(t)

    results = {}

    # Load transcript once
    with open(transcript_path) as f:
        transcript_data = json.load(f)

    existing_analysis = transcript_data.get("analysis", {})

    # Handle auto-judge types
    for analysis_type in auto_judge:
        judge_type = AUTO_JUDGE_TYPES[analysis_type]

        # Check skip_existing
        if skip_existing and not force:
            alias = existing_analysis.get(analysis_type)
            if alias and isinstance(alias, dict) and alias.get("_model") == model:
                # Already has a versioned result from same model
                if alias.get("_round") is not None:
                    console.print(f"[dim]Skipping {analysis_type} (already at round {alias['_round']} with {model})[/dim]")
                    continue

        console.print(Panel(
            f"[bold]Auto-Judge: {analysis_type}[/bold]\n"
            f"Judge: {judge_type}\n"
            f"Rounds: {judge_rounds}\n"
            f"Model: {model}",
            border_style="cyan"
        ))

        try:
            final_result, judge_result = run_with_judge_loop(
                transcript_data=transcript_data,
                analysis_type=analysis_type,
                judge_type=judge_type,
                model=model,
                max_rounds=judge_rounds,
                existing_analysis=existing_analysis,
                save_path=transcript_path if save else None
            )
            results[analysis_type] = final_result
            if judge_result:
                results[judge_type] = judge_result
        except Exception as e:
            console.print(f"[red]Auto-judge failed for {analysis_type}: {e}[/red]")
            results[analysis_type] = {"error": str(e)}

    # Handle regular types
    if regular:
        regular_results = analyze_transcript_file(
            transcript_path=transcript_path,
            analysis_types=regular,
            model=model,
            save=save,
            skip_existing=skip_existing,
            force=force
        )
        results.update(regular_results)

    return results
