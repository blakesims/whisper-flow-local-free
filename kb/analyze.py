#!/usr/bin/env python3
"""
Knowledge Base LLM Analysis Module

Analyzes transcripts using Google Gemini API with structured output.

Usage (via kb command):
    kb analyze                              # Interactive: select transcripts + types
    kb analyze -p                           # Only show transcripts with pending analysis
    kb analyze --all-pending                # Batch: analyze all pending with defaults
    kb analyze /path/to/file.json           # Direct: analyze specific file
    kb analyze --list-types                 # Show available analysis types

    kb missing                              # Show transcripts missing decimal defaults
    kb missing --detailed                   # Show per-transcript breakdown
    kb missing --summary                    # One-line output (for scripts, exit code 1 if missing)
    kb missing --run                        # Run all missing analyses
    kb missing --run --decimal 50.01.01     # Run only for specific decimal
    kb missing --run --yes                  # Run without confirmation (automation)
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary
from questionary import Style

from kb.__main__ import load_config, get_paths, DEFAULTS
from kb.core import load_registry

console = Console()

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
ANALYSIS_TYPES_DIR = CONFIG_DIR / "analysis_types"

# Default model from config
DEFAULT_MODEL = _config.get("defaults", {}).get("gemini_model", DEFAULTS["defaults"]["gemini_model"])

# Questionary style (matching kb.cli)
custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:cyan'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
    ('separator', 'fg:gray'),
    ('instruction', 'fg:gray'),
])


def load_analysis_type(name: str) -> dict:
    """Load an analysis type definition from config."""
    path = ANALYSIS_TYPES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown analysis type: {name}")

    with open(path) as f:
        return json.load(f)


def list_analysis_types() -> list[dict]:
    """Get all available analysis types."""
    types = []
    for path in sorted(ANALYSIS_TYPES_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
            types.append({
                "name": data["name"],
                "description": data["description"]
            })
    return types


def get_decimal_defaults(decimal: str) -> list[str]:
    """
    Get the default_analyses list for a given decimal category.

    Args:
        decimal: Decimal code (e.g., "50.01.01")

    Returns:
        List of analysis type names that are defaults for this decimal.
        Empty list if decimal not found or has no defaults configured.
    """
    registry = load_registry()
    decimals = registry.get("decimals", {})

    if decimal not in decimals:
        return []

    decimal_info = decimals[decimal]

    # Handle both dict format and legacy string format
    if isinstance(decimal_info, dict):
        return decimal_info.get("default_analyses", [])

    # Legacy string format (just name, no defaults)
    return []


def get_transcript_missing_analyses(transcript_data: dict) -> list[str]:
    """
    Get list of missing default analyses for a transcript.

    Compares the transcript's existing analyses against its decimal's
    configured default_analyses.

    Args:
        transcript_data: Transcript dict with 'decimal' and 'analysis' keys

    Returns:
        List of analysis type names that are in the decimal's defaults
        but NOT in the transcript's existing analysis.
        Empty list if all defaults are present or decimal has no defaults.
    """
    decimal = transcript_data.get("decimal")
    if not decimal:
        return []

    defaults = get_decimal_defaults(decimal)
    if not defaults:
        return []

    existing = transcript_data.get("analysis", {})
    missing = [t for t in defaults if t not in existing]

    return missing


def scan_missing_by_decimal() -> dict[str, list[dict]]:
    """
    Scan all transcripts and find those missing their decimal's default analyses.

    Returns:
        Dict grouped by decimal code:
        {
            "50.01.01": [
                {"path": "/path/to/file.json", "title": "...", "missing": ["summary", "guide"]},
                ...
            ],
            ...
        }
        Only includes decimals that have transcripts with missing analyses.
    """
    transcripts = get_all_transcripts()
    results: dict[str, list[dict]] = {}

    for t in transcripts:
        # Load full transcript to get analysis data
        try:
            with open(t["path"]) as f:
                transcript_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        missing = get_transcript_missing_analyses(transcript_data)
        if not missing:
            continue

        decimal = t["decimal"]
        if decimal not in results:
            results[decimal] = []

        results[decimal].append({
            "path": t["path"],
            "title": t["title"],
            "missing": missing,
        })

    return results


def get_missing_summary() -> tuple[int, int, int]:
    """
    Get a quick summary of missing analyses counts.

    Returns:
        Tuple of (total_transcripts, total_analyses, total_decimals)
    """
    missing_by_decimal = scan_missing_by_decimal()

    if not missing_by_decimal:
        return (0, 0, 0)

    total_transcripts = sum(len(ts) for ts in missing_by_decimal.values())
    total_analyses = sum(len(t["missing"]) for ts in missing_by_decimal.values() for t in ts)
    total_decimals = len(missing_by_decimal)

    return (total_transcripts, total_analyses, total_decimals)


def show_missing_analyses(
    detailed: bool = False,
    decimal_filter: str | None = None,
    summary_only: bool = False
) -> dict[str, list[dict]]:
    """
    Display summary of transcripts missing their decimal's default analyses.

    Args:
        detailed: If True, show per-transcript breakdown under each decimal
        decimal_filter: If provided, only show this decimal
        summary_only: If True, just print one-line summary and return

    Returns:
        Dict of missing analyses by decimal (for use by run_missing_analyses)
    """
    # Scan for missing analyses first (needed for all modes)
    missing_by_decimal = scan_missing_by_decimal()

    # Apply decimal filter if provided
    if decimal_filter and decimal_filter in missing_by_decimal:
        missing_by_decimal = {decimal_filter: missing_by_decimal[decimal_filter]}
    elif decimal_filter:
        missing_by_decimal = {}

    # Summary-only mode: one-line output, exit codes
    if summary_only:
        if not missing_by_decimal:
            console.print("0 transcripts missing analyses")
            return {}

        total_transcripts = sum(len(ts) for ts in missing_by_decimal.values())
        total_analyses = sum(len(t["missing"]) for ts in missing_by_decimal.values() for t in ts)
        total_decimals = len(missing_by_decimal)
        console.print(f"{total_transcripts} transcripts missing {total_analyses} analyses across {total_decimals} decimals")
        return missing_by_decimal

    console.print(Panel("[bold]Missing Default Analyses[/bold]", border_style="cyan"))

    if not missing_by_decimal:
        console.print("\n[green]✓ All transcripts have their default analyses![/green]\n")
        return {}

    # Load registry for decimal names
    registry = load_registry()
    decimals_info = registry.get("decimals", {})

    # Build summary table
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Decimal", style="cyan")
    table.add_column("Name")
    table.add_column("Transcripts", justify="right")
    table.add_column("Missing Types", style="yellow")

    total_transcripts = 0
    total_missing_count = 0

    for decimal in sorted(missing_by_decimal.keys()):
        transcripts = missing_by_decimal[decimal]
        total_transcripts += len(transcripts)

        # Get decimal name
        decimal_data = decimals_info.get(decimal, {})
        name = decimal_data.get("name", "") if isinstance(decimal_data, dict) else decimal_data

        # Collect unique missing types across all transcripts in this decimal
        all_missing_types = set()
        for t in transcripts:
            all_missing_types.update(t["missing"])
            total_missing_count += len(t["missing"])

        missing_str = ", ".join(sorted(all_missing_types))

        table.add_row(
            decimal,
            name[:30] if name else "[dim]unnamed[/dim]",
            str(len(transcripts)),
            missing_str
        )

    console.print("\n")
    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {total_transcripts} transcripts missing {total_missing_count} analyses across {len(missing_by_decimal)} decimals\n")

    # Detailed per-transcript breakdown
    if detailed:
        console.print("[bold cyan]Detailed Breakdown:[/bold cyan]\n")

        for decimal in sorted(missing_by_decimal.keys()):
            transcripts = missing_by_decimal[decimal]
            decimal_data = decimals_info.get(decimal, {})
            name = decimal_data.get("name", "") if isinstance(decimal_data, dict) else decimal_data

            console.print(f"[bold cyan]{decimal}[/bold cyan] - {name}")

            for t in transcripts:
                missing_str = ", ".join(t["missing"])
                title_short = t["title"][:50] + "..." if len(t["title"]) > 50 else t["title"]
                console.print(f"  [dim]•[/dim] {title_short}")
                console.print(f"    [yellow]Missing:[/yellow] {missing_str}")

            console.print()

    return missing_by_decimal


def run_missing_analyses(
    decimal_filter: str | None = None,
    model: str = DEFAULT_MODEL,
    skip_confirm: bool = False
) -> None:
    """
    Run all missing default analyses in batch mode.

    Args:
        decimal_filter: If provided, only process this decimal
        model: Gemini model to use for analysis
        skip_confirm: If True, skip confirmation prompt (for automation)
    """
    # Get missing analyses (also displays summary)
    missing_by_decimal = show_missing_analyses(decimal_filter=decimal_filter)

    if not missing_by_decimal:
        return

    # Count total work
    total_transcripts = sum(len(ts) for ts in missing_by_decimal.values())
    total_analyses = sum(len(t["missing"]) for ts in missing_by_decimal.values() for t in ts)

    console.print(f"[bold]Will run {total_analyses} analyses on {total_transcripts} transcript(s)[/bold]")
    console.print(f"  Model: {model}")

    # Confirmation
    if not skip_confirm:
        if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Run analyses
    success_count = 0
    error_count = 0
    current = 0

    for decimal in sorted(missing_by_decimal.keys()):
        transcripts = missing_by_decimal[decimal]

        for t in transcripts:
            current += 1
            title_short = t["title"][:40] + "..." if len(t["title"]) > 40 else t["title"]
            console.print(f"\n[bold cyan]({current}/{total_transcripts}) {title_short}[/bold cyan]")
            console.print(f"  [dim]Missing: {', '.join(t['missing'])}[/dim]")

            try:
                results = analyze_transcript_file(
                    transcript_path=t["path"],
                    analysis_types=t["missing"],
                    model=model,
                    save=True,
                    skip_existing=True,
                    force=False
                )

                # Count successes/errors in this batch
                successes = sum(1 for r in results.values() if "error" not in r)
                errors = sum(1 for r in results.values() if "error" in r)

                if successes > 0:
                    success_count += successes
                if errors > 0:
                    error_count += errors

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                error_count += len(t["missing"])

    # Summary
    console.print(f"\n[bold green]Done![/bold green]")
    console.print(f"  [green]Successful:[/green] {success_count} analyses")
    if error_count > 0:
        console.print(f"  [red]Failed:[/red] {error_count} analyses")


def run_missing_interactive() -> None:
    """
    Interactive mode for running missing analyses.

    Shows summary, then offers options:
    - Run all missing analyses
    - Select specific decimal to run
    - Cancel
    """
    # First show summary
    missing_by_decimal = show_missing_analyses()

    if not missing_by_decimal:
        return

    # Build choices
    decimals = sorted(missing_by_decimal.keys())
    registry = load_registry()
    decimals_info = registry.get("decimals", {})

    choices = [
        questionary.Choice(
            title="Run all missing analyses",
            value="all"
        ),
    ]

    # Add per-decimal options
    for decimal in decimals:
        decimal_data = decimals_info.get(decimal, {})
        name = decimal_data.get("name", "") if isinstance(decimal_data, dict) else decimal_data
        count = len(missing_by_decimal[decimal])
        label = f"Run only {decimal} ({name[:20]}...) - {count} transcript(s)" if len(name) > 20 else f"Run only {decimal} ({name}) - {count} transcript(s)"
        choices.append(questionary.Choice(title=label, value=decimal))

    choices.append(questionary.Choice(title="Cancel", value="cancel"))

    # Ask user
    console.print("\n[bold cyan]What would you like to do?[/bold cyan]")
    selection = questionary.select(
        "Action:",
        choices=choices,
        style=custom_style
    ).ask()

    if not selection or selection == "cancel":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Run based on selection
    if selection == "all":
        run_missing_analyses(skip_confirm=True)
    else:
        # Specific decimal
        run_missing_analyses(decimal_filter=selection, skip_confirm=True)


def get_all_transcripts(
    decimal_filter: str | None = None,
    limit: int | None = None
) -> list[dict]:
    """
    Scan knowledge base for all transcript files.

    Returns list of transcript info dicts sorted by date (newest first).
    """
    transcripts = []
    all_analysis_types = [t["name"] for t in list_analysis_types()]

    # Scan all decimal directories
    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name == "config" or decimal_dir.name == "examples":
            continue
        if decimal_filter and decimal_dir.name != decimal_filter:
            continue

        # Find all JSON files in this decimal
        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)

                # Get analysis status
                existing_analysis = data.get("analysis", {})
                done_types = [t for t in all_analysis_types if t in existing_analysis]
                pending_types = [t for t in all_analysis_types if t not in existing_analysis]

                # Parse date from filename or data
                recorded_at = data.get("recorded_at", "")
                if recorded_at:
                    try:
                        date = datetime.strptime(recorded_at, "%Y-%m-%d")
                    except ValueError:
                        date = datetime.fromtimestamp(json_file.stat().st_mtime)
                else:
                    date = datetime.fromtimestamp(json_file.stat().st_mtime)

                transcripts.append({
                    "path": str(json_file),
                    "title": data.get("title", json_file.stem),
                    "decimal": decimal_dir.name,
                    "date": date,
                    "done_types": done_types,
                    "pending_types": pending_types,
                    "has_pending": len(pending_types) > 0,
                    "word_count": len(data.get("transcript", "").split()),
                    "analysis": existing_analysis,  # Include full analysis data for model checking
                })
            except (json.JSONDecodeError, KeyError) as e:
                console.print(f"[yellow]Warning: Could not read {json_file}: {e}[/yellow]")

    # Sort by date (newest first)
    transcripts.sort(key=lambda x: x["date"], reverse=True)

    if limit:
        transcripts = transcripts[:limit]

    return transcripts


def format_analysis_status(done: list[str], pending: list[str]) -> str:
    """Format analysis status for display."""
    if not done and not pending:
        return "[dim]no types configured[/dim]"

    parts = []
    for t in done:
        parts.append(f"[green]{t}[/green]")

    if not done and pending:
        return "[yellow]o no analysis[/yellow]"

    return " ".join(parts) if parts else "[yellow]o pending[/yellow]"


def select_transcripts(
    transcripts: list[dict],
    pending_only: bool = False
) -> list[dict]:
    """Interactive multi-select for transcripts."""
    if pending_only:
        transcripts = [t for t in transcripts if t["has_pending"]]

    if not transcripts:
        console.print("[yellow]No transcripts found matching criteria.[/yellow]")
        return []

    console.print("\n[bold cyan]Select transcripts to analyze:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Space to select, Enter when done[/dim]\n")

    choices = []
    for t in transcripts:
        date_str = t["date"].strftime("%Y-%m-%d")
        status = format_analysis_status(t["done_types"], t["pending_types"])
        # Strip rich markup for questionary (it doesn't support it)
        status_plain = status.replace("[green]", "").replace("[/green]", "")
        status_plain = status_plain.replace("[yellow]", "").replace("[/yellow]", "")
        status_plain = status_plain.replace("[dim]", "").replace("[/dim]", "")

        label = f"{date_str} | {t['title'][:30]:<30} | {t['decimal']} | {status_plain}"
        choices.append(questionary.Choice(title=label, value=t))

    selected = questionary.checkbox(
        "Transcripts:",
        choices=choices,
        style=custom_style,
        instruction="(Space to select, Enter to confirm)"
    ).ask()

    return selected or []


def select_analysis_types_interactive(
    available: list[dict],
    existing_analysis: dict | None = None,
    current_model: str = DEFAULT_MODEL
) -> list[str]:
    """Interactive multi-select for analysis types.

    Shows model info for already-done analyses and allows re-running with different model.
    """
    existing_analysis = existing_analysis or {}

    console.print("\n[bold cyan]Select analysis types:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Space to select, Enter when done[/dim]\n")

    choices = []
    for t in available:
        if t["name"] in existing_analysis:
            # Get the model used for this analysis
            analysis_data = existing_analysis[t["name"]]
            done_model = analysis_data.get("_model", "unknown")

            if done_model == current_model:
                # Same model - show as done, disabled
                label = f"{t['name']}: {t['description']} [done with {done_model}]"
                choices.append(questionary.Choice(title=label, value=t["name"], disabled="already done"))
            else:
                # Different model - allow re-running
                label = f"{t['name']}: {t['description']} [done with {done_model}, re-run with {current_model}?]"
                choices.append(questionary.Choice(title=label, value=t["name"], checked=False))
        else:
            label = f"{t['name']}: {t['description']}"
            # Pre-select summary by default
            choices.append(questionary.Choice(
                title=label,
                value=t["name"],
                checked=(t["name"] == "summary")
            ))

    selected = questionary.checkbox(
        "Analysis types:",
        choices=choices,
        style=custom_style,
        instruction="(Space to select, Enter to confirm)"
    ).ask()

    return selected or []


def format_prerequisite_output(analysis_result: dict) -> str:
    """
    Format an analysis result for injection into a compound prompt.

    Handles various output structures by extracting the main content.
    Returns a clean string representation.
    """
    if not analysis_result:
        return ""

    # Filter out metadata keys (those starting with _)
    content = {k: v for k, v in analysis_result.items() if not k.startswith("_")}

    # If there's a single key with a string value, return that directly
    if len(content) == 1:
        value = list(content.values())[0]
        if isinstance(value, str):
            return value
        elif isinstance(value, list):
            # Format list items nicely (e.g., key_points)
            formatted_items = []
            for item in value:
                if isinstance(item, dict):
                    # Format dict items (e.g., {"quote": "...", "insight": "..."})
                    parts = [f"- {v}" if k in ("quote", "insight") else f"  {k}: {v}"
                             for k, v in item.items()]
                    formatted_items.append("\n".join(parts))
                else:
                    formatted_items.append(f"- {item}")
            return "\n\n".join(formatted_items)

    # Multiple keys - return JSON representation
    return json.dumps(content, indent=2, ensure_ascii=False)


def substitute_template_vars(prompt: str, context: dict) -> str:
    """
    Replace {{variable}} placeholders in a prompt with context values.

    Args:
        prompt: The prompt template with {{variable}} placeholders
        context: Dict mapping variable names to their formatted values

    Returns:
        The prompt with placeholders substituted
    """
    import re

    def replacer(match):
        var_name = match.group(1)
        if var_name in context:
            return context[var_name]
        # Leave unmatched placeholders as-is (for debugging)
        return match.group(0)

    return re.sub(r'\{\{(\w+)\}\}', replacer, prompt)


def render_conditional_template(prompt: str, context: dict) -> str:
    """
    Render Handlebars-style conditional blocks in a prompt template.

    Supports:
    - {{#if var}}content{{/if}} - renders content when var exists and is truthy
    - {{#if var}}content{{else}}fallback{{/if}} - renders fallback when var missing/falsy

    After processing conditionals, also substitutes {{variable}} placeholders.

    Note: Nested {{#if}} blocks are NOT supported. The regex matches the first
    {{/if}} it finds, which breaks nesting. For complex logic, use multiple
    sequential conditionals instead of nesting them.

    Args:
        prompt: The prompt template with conditional blocks
        context: Dict mapping variable names to their values

    Returns:
        The prompt with conditionals resolved and variables substituted

    Example:
        >>> render_conditional_template(
        ...     "{{#if key_points}}{{key_points}}{{else}}{{transcript}}{{/if}}",
        ...     {"transcript": "Hello world"}
        ... )
        'Hello world'
    """
    import re

    # Pattern for {{#if var}}...{{/if}} with optional {{else}}
    # Note: Non-greedy matching means nested {{#if}} blocks are NOT supported.
    # The regex matches the first {{/if}} it finds, breaking nested structures.
    if_pattern = re.compile(
        r'\{\{#if\s+(\w+)\}\}'   # {{#if varname}}
        r'(.*?)'                  # content (non-greedy)
        r'(?:\{\{else\}\}(.*?))?' # optional {{else}}fallback
        r'\{\{/if\}\}',           # {{/if}}
        re.DOTALL                 # Allow . to match newlines
    )

    def if_replacer(match):
        var_name = match.group(1)
        if_content = match.group(2)
        else_content = match.group(3) or ""

        # Check if variable exists and is truthy
        value = context.get(var_name)
        if value:
            return if_content
        else:
            return else_content

    # Process all conditional blocks
    result = if_pattern.sub(if_replacer, prompt)

    # Now substitute any remaining {{variable}} placeholders
    result = substitute_template_vars(result, context)

    return result


def analyze_transcript(
    transcript_text: str,
    analysis_type: str,
    title: str = "",
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
    prerequisite_context: dict | None = None
) -> dict:
    """
    Run a single analysis type on a transcript.

    Args:
        transcript_text: The transcript text to analyze
        analysis_type: Name of the analysis type to run
        title: Optional title for context
        model: Gemini model to use
        max_retries: Number of retries on transient failures
        prerequisite_context: Dict of {analysis_name: formatted_output} for compound analyses

    Returns the structured analysis result.
    """
    # Import here to avoid import errors if google-genai not installed
    try:
        from google import genai
        from google.genai import types, errors
    except ImportError:
        raise ImportError(
            "google-genai package not installed. "
            "Install with: pip install google-genai"
        )

    # Check for API key
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set. "
            "Get an API key from https://aistudio.google.com/app/apikey"
        )

    # Load analysis type config
    config = load_analysis_type(analysis_type)

    # Get the prompt and render conditionals + substitute variables
    prompt_template = config['prompt']
    if prerequisite_context:
        prompt_template = render_conditional_template(prompt_template, prerequisite_context)

    # Build the prompt with schema instruction
    title_context = f"Title: {title}\n\n" if title else ""
    schema_json = json.dumps(config['output_schema'], indent=2)

    full_prompt = f"""{prompt_template}

{title_context}TRANSCRIPT:
{transcript_text}

---

Respond with valid JSON matching this schema:
{schema_json}

Output ONLY the JSON, no markdown code blocks or explanation."""

    # Initialize client
    client = genai.Client(api_key=api_key)

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.3,  # Lower for more consistent structured output
                ),
            )

            # Parse and return the result
            result = json.loads(response.text)
            return result

        except errors.ClientError as e:
            if e.code == 429:  # Rate limited
                wait_time = 2 ** attempt
                console.print(f"[yellow]Rate limited, waiting {wait_time}s...[/yellow]")
                time.sleep(wait_time)
                continue
            elif e.code == 400:
                raise ValueError(f"Invalid request: {e.message}")
            elif e.code == 401:
                raise PermissionError(f"API key invalid: {e.message}")
            else:
                raise

        except errors.ServerError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

        except json.JSONDecodeError as e:
            console.print(f"[yellow]Warning: Failed to parse response as JSON[/yellow]")
            if attempt < max_retries - 1:
                continue
            raise ValueError(f"Failed to get valid JSON response: {e}")

    raise RuntimeError("Max retries exceeded")


def resolve_optional_inputs(
    analysis_def: dict,
    existing_analysis: dict,
    transcript_text: str
) -> dict:
    """
    Resolve optional inputs for an analysis type.

    Optional inputs are included in the context if they exist in the transcript's
    existing analysis, but don't trigger auto-run if missing. This allows analysis
    types to gracefully handle varying input availability.

    Always includes 'transcript' as a fallback for when optional inputs aren't available.

    Args:
        analysis_def: The analysis type definition (with optional_inputs field)
        existing_analysis: Dict of existing analysis results for this transcript
        transcript_text: The raw transcript text (always included as fallback)

    Returns:
        Dict of {input_name: formatted_value} for available optional inputs.
        Always includes 'transcript' key.

    Example:
        analysis_def = {"optional_inputs": ["key_points", "summary"]}
        existing = {"key_points": {"key_points": [...]}}
        result = resolve_optional_inputs(analysis_def, existing, "raw text...")
        # Returns {"transcript": "raw text...", "key_points": "formatted..."}
        # (summary not included because it wasn't in existing)
    """
    context = {
        "transcript": transcript_text
    }

    optional_inputs = analysis_def.get("optional_inputs", [])

    for opt_input in optional_inputs:
        if opt_input in existing_analysis:
            # Format the optional input for injection into the prompt
            context[opt_input] = format_prerequisite_output(existing_analysis[opt_input])

    return context


def run_analysis_with_deps(
    transcript_data: dict,
    analysis_type: str,
    model: str = DEFAULT_MODEL,
    existing_analysis: dict | None = None
) -> tuple[dict, list[str]]:
    """
    Run an analysis type, automatically running any required prerequisites first.

    Handles both required dependencies (auto-run if missing) and optional inputs
    (included if available, skipped if not).

    Args:
        transcript_data: Full transcript data dict (with 'transcript', 'title', 'analysis')
        analysis_type: Name of the analysis type to run
        model: Gemini model to use
        existing_analysis: Existing analysis results (updated in-place with prerequisites)

    Returns:
        Tuple of (result_dict, list_of_prerequisites_run)
    """
    if existing_analysis is None:
        existing_analysis = transcript_data.get("analysis", {})

    # Load the analysis type definition
    analysis_def = load_analysis_type(analysis_type)
    required = analysis_def.get("requires", [])
    prerequisites_run = []

    # Check and run any missing prerequisites (required deps)
    for req in required:
        if req not in existing_analysis:
            console.print(f"[dim]Running prerequisite: {req}[/dim]")
            # Recursively handle prerequisites (they might have their own deps)
            req_result, req_prereqs = run_analysis_with_deps(
                transcript_data=transcript_data,
                analysis_type=req,
                model=model,
                existing_analysis=existing_analysis
            )
            if "error" not in req_result:
                # Add metadata
                req_result["_model"] = model
                req_result["_analyzed_at"] = datetime.now().isoformat()
                existing_analysis[req] = req_result
                prerequisites_run.append(req)
                prerequisites_run.extend(req_prereqs)
            else:
                # Prerequisite failed - can't continue
                raise ValueError(f"Prerequisite '{req}' failed: {req_result.get('error')}")

    # Build context for the prompt, starting with optional inputs (includes transcript)
    transcript_text = transcript_data.get("transcript", "")
    prompt_context = resolve_optional_inputs(analysis_def, existing_analysis, transcript_text)

    # Add required prerequisites to context (these are guaranteed to exist now)
    for req in required:
        if req in existing_analysis:
            prompt_context[req] = format_prerequisite_output(existing_analysis[req])

    # Run the actual analysis
    result = analyze_transcript(
        transcript_text=transcript_text,
        analysis_type=analysis_type,
        title=transcript_data.get("title", ""),
        model=model,
        prerequisite_context=prompt_context if prompt_context else None
    )

    return result, prerequisites_run


def analyze_transcript_file(
    transcript_path: str,
    analysis_types: list[str],
    model: str = DEFAULT_MODEL,
    save: bool = True,
    skip_existing: bool = True,
    force: bool = False
) -> dict:
    """
    Run multiple analysis types on a transcript file.

    Args:
        transcript_path: Path to the transcript JSON file
        analysis_types: List of analysis type names to run
        model: Gemini model to use
        save: Whether to save results back to the transcript file
        skip_existing: Skip analysis types that already exist (unless force=True)
        force: Force re-run all requested analyses regardless of existing

    Returns:
        Dict of analysis results keyed by type name
    """
    # Load transcript
    with open(transcript_path) as f:
        transcript_data = json.load(f)

    transcript_text = transcript_data.get("transcript", "")
    title = transcript_data.get("title", "")
    existing_analysis = transcript_data.get("analysis", {})

    if not transcript_text:
        raise ValueError("Transcript file has no transcript text")

    # Filter out already-done types if requested (unless force)
    if skip_existing and not force:
        # Only skip if same model was used
        types_to_run = []
        skipped = []
        for t in analysis_types:
            if t in existing_analysis:
                existing_model = existing_analysis[t].get("_model", "unknown")
                if existing_model == model:
                    skipped.append(f"{t} ({existing_model})")
                else:
                    # Different model, re-run
                    types_to_run.append(t)
                    console.print(f"[dim]Re-running {t}: {existing_model} → {model}[/dim]")
            else:
                types_to_run.append(t)
        if skipped:
            console.print(f"[dim]Skipping (same model): {', '.join(skipped)}[/dim]")
    else:
        types_to_run = analysis_types
        if force and analysis_types:
            console.print(f"[dim]Force re-running: {', '.join(analysis_types)}[/dim]")

    if not types_to_run:
        console.print("[green]All requested analyses already complete.[/green]")
        return {}

    results = {}

    # Track prerequisites that were auto-run
    all_prerequisites_run = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for analysis_type in types_to_run:
            task = progress.add_task(f"Analyzing: {analysis_type}...", total=None)

            try:
                # Use run_analysis_with_deps to handle compound analyses
                result, prerequisites_run = run_analysis_with_deps(
                    transcript_data=transcript_data,
                    analysis_type=analysis_type,
                    model=model,
                    existing_analysis=existing_analysis
                )
                results[analysis_type] = result
                all_prerequisites_run.extend(prerequisites_run)

                # Update existing_analysis so later analyses see new results
                if "error" not in result:
                    result["_model"] = model
                    result["_analyzed_at"] = datetime.now().isoformat()
                    existing_analysis[analysis_type] = result

                progress.update(task, description=f"[green]done[/green] {analysis_type}")

            except Exception as e:
                progress.update(task, description=f"[red]x[/red] {analysis_type}: {e}")
                results[analysis_type] = {"error": str(e)}

    # Include auto-run prerequisites in results
    for prereq in all_prerequisites_run:
        if prereq in existing_analysis and prereq not in results:
            results[prereq] = existing_analysis[prereq]

    # Save results back to transcript file
    if save and results:
        if "analysis" not in transcript_data:
            transcript_data["analysis"] = {}

        for name, result in results.items():
            if "error" not in result:
                # Metadata already added during run_analysis_with_deps
                transcript_data["analysis"][name] = result

        with open(transcript_path, 'w') as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        console.print(f"[green]Analysis saved to {transcript_path}[/green]")

    return results


def run_interactive_mode(
    pending_only: bool = False,
    decimal_filter: str | None = None,
    recent_limit: int | None = None,
    model: str = DEFAULT_MODEL,
    force: bool = False
):
    """Run the interactive transcript selector and analyzer."""
    console.print(Panel("[bold]Transcript Analyzer[/bold]", border_style="cyan"))

    # Get all transcripts
    transcripts = get_all_transcripts(
        decimal_filter=decimal_filter,
        limit=recent_limit
    )

    if not transcripts:
        console.print("[yellow]No transcripts found in knowledge base.[/yellow]")
        return

    # Show summary
    total = len(transcripts)
    pending = sum(1 for t in transcripts if t["has_pending"])
    console.print(f"[dim]Found {total} transcripts, {pending} with pending analysis[/dim]")

    # Select transcripts
    selected_transcripts = select_transcripts(transcripts, pending_only=pending_only)

    if not selected_transcripts:
        console.print("[yellow]No transcripts selected.[/yellow]")
        return

    console.print(f"\n[bold]Selected {len(selected_transcripts)} transcript(s)[/bold]")

    # If single transcript, pass full analysis data for model-aware selection
    if len(selected_transcripts) == 1:
        t = selected_transcripts[0]
        existing_analysis = t.get("analysis", {})
    else:
        # For multiple transcripts, we can't show per-transcript model info
        # Just show what's commonly done (conservative approach)
        existing_analysis = {}

    # Select analysis types
    available_types = list_analysis_types()
    selected_types = select_analysis_types_interactive(
        available_types,
        existing_analysis=existing_analysis,
        current_model=model
    )

    if not selected_types:
        console.print("[yellow]No analysis types selected.[/yellow]")
        return

    # Confirm
    console.print(f"\n[bold]Will analyze {len(selected_transcripts)} transcript(s) with:[/bold]")
    console.print(f"  Types: {', '.join(selected_types)}")
    console.print(f"  Model: {model}")

    if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Run analysis
    success_count = 0
    for i, transcript in enumerate(selected_transcripts, 1):
        console.print(f"\n[bold cyan]({i}/{len(selected_transcripts)}) {transcript['title']}[/bold cyan]")

        try:
            results = analyze_transcript_file(
                transcript_path=transcript["path"],
                analysis_types=selected_types,
                model=model,
                save=True,
                skip_existing=True,
                force=force
            )

            # Count successes
            successes = sum(1 for r in results.values() if "error" not in r)
            if successes > 0:
                success_count += 1

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    console.print(f"\n[bold green]Done! Analyzed {success_count}/{len(selected_transcripts)} transcript(s).[/bold green]")


def run_batch_pending(
    analysis_types: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    force: bool = False
):
    """Batch analyze all transcripts with pending analysis."""
    console.print(Panel("[bold]Batch Analysis - All Pending[/bold]", border_style="cyan"))

    transcripts = get_all_transcripts()
    pending = [t for t in transcripts if t["has_pending"]]

    if not pending:
        console.print("[green]No transcripts with pending analysis.[/green]")
        return

    # Default to summary if no types specified
    if not analysis_types:
        analysis_types = ["summary"]

    console.print(f"[bold]Found {len(pending)} transcript(s) with pending analysis[/bold]")
    console.print(f"  Types: {', '.join(analysis_types)}")
    console.print(f"  Model: {model}")
    if force:
        console.print(f"  [yellow]Force mode: re-running all[/yellow]")

    if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    success_count = 0
    for i, transcript in enumerate(pending, 1):
        console.print(f"\n[bold cyan]({i}/{len(pending)}) {transcript['title']}[/bold cyan]")

        try:
            results = analyze_transcript_file(
                transcript_path=transcript["path"],
                analysis_types=analysis_types,
                model=model,
                save=True,
                skip_existing=True,
                force=force
            )

            successes = sum(1 for r in results.values() if "error" not in r)
            if successes > 0:
                success_count += 1

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    console.print(f"\n[bold green]Done! Analyzed {success_count}/{len(pending)} transcript(s).[/bold green]")


def main():
    import argparse

    # Check if this is the 'missing' subcommand (invoked via kb missing)
    # sys.argv[0] will be 'missing' when called via COMMANDS dispatch
    if len(sys.argv) > 0 and sys.argv[0] == "missing":
        # Parse missing-specific args
        parser = argparse.ArgumentParser(
            prog="kb missing",
            description="Show transcripts missing their decimal's default analyses",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  kb missing                    # Show summary table
  kb missing --detailed         # Show per-transcript breakdown
  kb missing --summary          # One-line output (for scripts)
  kb missing --run              # Run all missing with confirmation
  kb missing --run --decimal X  # Run only for specific decimal
  kb missing --run --yes        # Run without prompting (automation)
            """
        )
        parser.add_argument("--detailed", action="store_true",
                            help="Show per-transcript breakdown under each decimal")
        parser.add_argument("--summary", "-s", action="store_true",
                            help="Compact one-line output; exit code 0 if none missing, 1 if some")
        parser.add_argument("--run", action="store_true",
                            help="Run missing analyses in batch mode")
        parser.add_argument("--decimal", "-d",
                            help="Filter to specific decimal category")
        parser.add_argument("--yes", "-y", action="store_true",
                            help="Skip confirmation prompt (for automation)")
        parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                            help=f"Gemini model (default: {DEFAULT_MODEL})")
        args = parser.parse_args(sys.argv[1:])

        if args.run:
            run_missing_analyses(
                decimal_filter=args.decimal,
                model=args.model,
                skip_confirm=args.yes
            )
        elif args.summary:
            # Summary mode: one-line output, exit code based on results
            missing = show_missing_analyses(
                decimal_filter=args.decimal,
                summary_only=True
            )
            sys.exit(1 if missing else 0)
        else:
            show_missing_analyses(detailed=args.detailed, decimal_filter=args.decimal)
        return

    parser = argparse.ArgumentParser(
        description="Analyze transcripts with LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kb/analyze.py                    # Interactive mode
  python kb/analyze.py -p                 # Only show pending transcripts
  python kb/analyze.py --all-pending      # Batch analyze all pending
  python kb/analyze.py /path/to/file.json # Analyze specific file
  python kb/analyze.py --list-types       # Show analysis types
        """
    )
    parser.add_argument("transcript", nargs="?", help="Path to transcript JSON file (optional)")
    parser.add_argument("--type", "-t", action="append", dest="types",
                        help="Analysis type to run (can specify multiple)")
    parser.add_argument("--pending", "-p", action="store_true",
                        help="Only show transcripts with pending analysis")
    parser.add_argument("--all-pending", action="store_true",
                        help="Batch analyze all pending transcripts")
    parser.add_argument("--decimal", "-d", help="Filter to specific decimal category")
    parser.add_argument("--recent", "-r", type=int, help="Only show N most recent transcripts")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force re-run analyses even if already done with same model")
    parser.add_argument("--no-save", action="store_true",
                        help="Don't save results to transcript file")
    parser.add_argument("--list-types", "-l", action="store_true",
                        help="List available analysis types")
    parser.add_argument("--list", action="store_true",
                        help="List all transcripts and their analysis status")

    args = parser.parse_args()

    # List analysis types
    if args.list_types:
        console.print(Panel("[bold]Available Analysis Types[/bold]", border_style="cyan"))
        for t in list_analysis_types():
            console.print(f"  [cyan]{t['name']}[/cyan]: {t['description']}")
        return

    # List transcripts
    if args.list:
        transcripts = get_all_transcripts(
            decimal_filter=args.decimal,
            limit=args.recent
        )

        table = Table(title="Transcripts", show_header=True, header_style="bold magenta")
        table.add_column("Date", style="cyan")
        table.add_column("Title")
        table.add_column("Decimal")
        table.add_column("Analysis Status")

        for t in transcripts:
            status = format_analysis_status(t["done_types"], t["pending_types"])
            table.add_row(
                t["date"].strftime("%Y-%m-%d"),
                t["title"][:35],
                t["decimal"],
                status
            )

        console.print(table)

        total = len(transcripts)
        pending = sum(1 for t in transcripts if t["has_pending"])
        console.print(f"\n[bold]Total:[/bold] {total} transcripts, {pending} with pending analysis")
        return

    # Batch mode
    if args.all_pending:
        run_batch_pending(
            analysis_types=args.types,
            model=args.model,
            force=args.force
        )
        return

    # Direct file mode
    if args.transcript:
        if not os.path.isfile(args.transcript):
            console.print(f"[red]File not found: {args.transcript}[/red]")
            sys.exit(1)

        # Determine which types to run
        if args.types:
            analysis_types = args.types
        else:
            analysis_types = ["summary"]

        console.print(Panel(
            f"[bold]Transcript Analysis[/bold]\n"
            f"File: {args.transcript}\n"
            f"Types: {', '.join(analysis_types)}\n"
            f"Model: {args.model}",
            border_style="cyan"
        ))

        try:
            results = analyze_transcript_file(
                transcript_path=args.transcript,
                analysis_types=analysis_types,
                model=args.model,
                save=not args.no_save,
                skip_existing=True,
                force=args.force
            )

            console.print("\n[bold]Results:[/bold]")
            for name, result in results.items():
                if "error" in result:
                    console.print(f"  [red]x {name}[/red]: {result['error']}")
                else:
                    console.print(f"  [green]done {name}[/green]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
        return

    # Interactive mode (default)
    run_interactive_mode(
        pending_only=args.pending,
        decimal_filter=args.decimal,
        recent_limit=args.recent,
        model=args.model,
        force=args.force
    )


if __name__ == "__main__":
    main()
