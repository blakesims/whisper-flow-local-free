#!/usr/bin/env python3
"""
Rich CLI for Knowledge Base Transcription

Provides interactive prompts for selecting metadata:
- Decimal category selection
- Tag multi-select with ability to add new tags
- Optional recording date input
- Analysis type toggles
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import print as rprint
import questionary
from questionary import Style

# Import from core to avoid duplication
from kb.core import load_registry, save_registry, KB_ROOT, CONFIG_DIR
from kb.__main__ import load_config

console = Console()

# Custom style for questionary
custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
    ('instruction', 'fg:white'),
])


# --- Preset Functions ---

def get_presets_for_source(source_type: str) -> dict[str, dict]:
    """
    Get presets that apply to a specific source type.

    Args:
        source_type: One of 'file', 'cap', 'volume', 'zoom', 'paste'

    Returns:
        Dict of preset_key -> preset_data for matching presets
    """
    config = load_config()
    presets = config.get("presets", {})

    matching = {}
    for key, preset in presets.items():
        sources = preset.get("sources", [])
        if source_type in sources or not sources:  # Empty sources = all
            matching[key] = preset

    return matching


def apply_title_template(
    template: str,
    participants: list[str] | None = None,
    date: str | None = None,
    filename: str | None = None,
) -> str:
    """
    Apply a title template with variable substitution.

    Supported placeholders:
        {participants} - First 2 participants joined by " & "
        {date} - Recording date (YYYY-MM-DD)
        {filename} - Original filename without extension
    """
    result = template

    if "{participants}" in result and participants:
        if len(participants) == 1:
            p_str = participants[0]
        elif len(participants) == 2:
            p_str = f"{participants[0]} & {participants[1]}"
        else:
            p_str = f"{participants[0]} & {participants[1]} +{len(participants)-2}"
        result = result.replace("{participants}", p_str)

    if "{date}" in result:
        result = result.replace("{date}", date or datetime.now().strftime("%Y-%m-%d"))

    if "{filename}" in result:
        result = result.replace("{filename}", filename or "Untitled")

    return result


def select_preset(
    source_type: str,
    participants: list[str] | None = None,
    date: str | None = None,
    filename: str | None = None,
) -> dict | None:
    """
    Interactive preset selection for a source type.

    Args:
        source_type: One of 'file', 'cap', 'volume', 'zoom', 'paste'
        participants: List of participant names (for title template)
        date: Recording date (for title template)
        filename: Original filename (for title template)

    Returns:
        Dict with keys: decimal, title, tags, analyses (from registry defaults)
        Or None if user selects "Custom..."
    """
    presets = get_presets_for_source(source_type)

    if not presets:
        return None  # No presets for this source, use full flow

    registry = load_registry()

    console.print("\n[bold cyan]Select preset:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Enter to select[/dim]\n")

    # Build choices
    choices = []
    for key, preset in presets.items():
        decimal = preset.get("decimal", "")
        label = preset.get("label", key)

        # Show preview of what title would be
        title_preview = apply_title_template(
            preset.get("title_template", ""),
            participants=participants,
            date=date,
            filename=filename,
        )

        # Format: "Alpha Cohort Session (50.03.01) → Alpha - Blake & John"
        display = f"{label} ({decimal})"
        if title_preview:
            display += f"  [dim]→ {title_preview[:40]}{'...' if len(title_preview) > 40 else ''}[/dim]"

        choices.append(questionary.Choice(title=display, value=key))

    # Add custom option at the end
    choices.append(questionary.Choice(title="[Custom...]", value=None))

    selected_key = questionary.select(
        "Preset:",
        choices=choices,
        style=custom_style,
        instruction="(up/down to move, Enter to select)"
    ).ask()

    if selected_key is None:
        return None  # User selected Custom

    # Build result from preset
    preset = presets[selected_key]
    decimal = preset.get("decimal", "")

    # Get default analyses from registry for this decimal
    decimal_info = registry.get("decimals", {}).get(decimal, {})
    default_analyses = decimal_info.get("default_analyses", ["summary"])

    title = apply_title_template(
        preset.get("title_template", ""),
        participants=participants,
        date=date,
        filename=filename,
    )

    result = {
        "decimal": decimal,
        "title": title,
        "tags": preset.get("tags", []),
        "analyses": preset.get("analyses") or default_analyses,
        "preset_key": selected_key,
        "preset_label": preset.get("label", selected_key),
    }

    console.print(f"[green]Using preset: {preset.get('label', selected_key)}[/green]")

    return result


def confirm_preset(
    preset_result: dict,
    participants: list[str] | None = None,
) -> dict | None:
    """
    Quick confirmation for preset with option to edit title.

    Returns updated result dict or None if cancelled.
    """
    console.print(f"\n[bold]Preset: {preset_result['preset_label']}[/bold]")
    console.print(f"  Decimal: {preset_result['decimal']}")
    console.print(f"  Tags: {', '.join(preset_result['tags']) or '(none)'}")
    console.print(f"  Analyses: {', '.join(preset_result['analyses'])}")

    # Allow editing title
    console.print(f"\n[bold cyan]Title:[/bold cyan]")
    title = questionary.text(
        "Title:",
        default=preset_result["title"],
        style=custom_style,
    ).ask()

    if title is None:
        return None

    preset_result["title"] = title

    # Quick confirm
    if not questionary.confirm(
        "Proceed?",
        default=True,
        style=custom_style,
    ).ask():
        return None

    return preset_result


def select_decimal(registry: dict) -> str:
    """Interactive decimal category selection."""
    decimals = registry.get("decimals", {})

    console.print("\n[bold cyan]Select decimal category:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Enter to select[/dim]\n")

    # Build choices for questionary
    choices = []
    for dec, info in decimals.items():
        label = f"{dec}: {info.get('name', '')}"
        choices.append(questionary.Choice(title=label, value=dec))

    selected = questionary.select(
        "Category:",
        choices=choices,
        style=custom_style,
        instruction="(up/down to move, Enter to select)"
    ).ask()

    if selected is None:
        # User cancelled
        sys.exit(0)

    console.print(f"[green]Selected: {selected}[/green]")
    return selected


def select_tags(registry: dict) -> list[str]:
    """Interactive multi-select tag picker with checkbox UI."""
    available_tags = sorted(registry.get("tags", []))

    console.print("\n[bold cyan]Select tags:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Space to select, 'a' to add new, Enter when done[/dim]\n")

    while True:
        # Use questionary checkbox for selection
        choices = [questionary.Choice(tag, value=tag) for tag in available_tags]

        selected = questionary.checkbox(
            "Tags:",
            choices=choices,
            style=custom_style,
            instruction="(Space to select, Enter to confirm)"
        ).ask()

        if selected is None:
            # User cancelled (Ctrl+C)
            return []

        # Ask if they want to add new tags
        if Confirm.ask("\n[bold]Add new tag?[/bold]", default=False):
            new_tag = Prompt.ask("[bold]Enter new tag[/bold]").strip().lower()
            new_tag = new_tag.replace(" ", "-")
            if new_tag and new_tag not in available_tags:
                available_tags.append(new_tag)
                available_tags.sort()
                selected.append(new_tag)
                console.print(f"[green]Added: {new_tag}[/green]")
                # Ask if they want to continue adding/selecting
                if Confirm.ask("[bold]Continue selecting tags?[/bold]", default=False):
                    continue
            elif new_tag in available_tags:
                console.print(f"[yellow]Tag already exists[/yellow]")
                if Confirm.ask("[bold]Continue selecting tags?[/bold]", default=False):
                    continue

        break

    console.print(f"\n[bold green]Selected tags: {selected if selected else '(none)'}[/bold green]")
    return selected


def get_recording_date() -> str | None:
    """Optional recording date input."""
    console.print("\n[bold cyan]Recording date:[/bold cyan]")

    if not Confirm.ask("Set recording date?", default=False):
        return None

    while True:
        date_str = Prompt.ask(
            "[bold]Enter date[/bold]",
            default=datetime.now().strftime("%Y-%m-%d")
        )

        # Validate format
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            console.print("[red]Invalid format. Use YYYY-MM-DD.[/red]")


def select_analysis_types(registry: dict, decimal: str) -> list[str]:
    """Select which analysis types to run."""
    import json

    # Get default analyses for this decimal
    decimal_info = registry.get("decimals", {}).get(decimal, {})
    default_analyses = decimal_info.get("default_analyses", ["summary"])

    # Load available analysis types
    analysis_dir = CONFIG_DIR / "analysis_types"
    available_analyses = []

    if analysis_dir.exists():
        for f in analysis_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    available_analyses.append({
                        "name": data.get("name", f.stem),
                        "description": data.get("description", "")
                    })
            except Exception:
                pass

    if not available_analyses:
        console.print("[yellow]No analysis types configured.[/yellow]")
        return []

    console.print("\n[bold cyan]Select analysis types:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Space to toggle, Enter when done[/dim]")
    console.print("[dim]Defaults pre-selected based on category[/dim]\n")

    # Build choices with defaults pre-selected
    choices = []
    for analysis in available_analyses:
        is_default = analysis["name"] in default_analyses
        label = f"{analysis['name']}: {analysis['description']}"
        choices.append(questionary.Choice(
            title=label,
            value=analysis["name"],
            checked=is_default
        ))

    selected = questionary.checkbox(
        "Analyses:",
        choices=choices,
        style=custom_style,
        instruction="(Space to toggle, Enter to confirm)"
    ).ask()

    if selected is None:
        return default_analyses

    console.print(f"\n[bold green]Selected analyses: {selected if selected else '(none)'}[/bold green]")
    return selected


def get_title(default: str = "") -> str:
    """Get transcript title."""
    console.print("\n[bold cyan]Title:[/bold cyan]")
    title = Prompt.ask("[bold]Enter title[/bold]", default=default)
    return title


def confirm_metadata(
    file_path: str,
    decimal: str,
    title: str,
    tags: list[str],
    date: str | None,
    analyses: list[str]
) -> bool:
    """Show summary and confirm."""
    console.print("\n")

    panel_content = f"""
[bold]File:[/bold] {file_path}
[bold]Decimal:[/bold] {decimal}
[bold]Title:[/bold] {title}
[bold]Tags:[/bold] {', '.join(tags) if tags else '(none)'}
[bold]Date:[/bold] {date or '(today)'}
[bold]Analyses:[/bold] {', '.join(analyses) if analyses else '(none)'}
"""

    console.print(Panel(panel_content, title="[bold green]Transcription Summary[/bold green]", border_style="green"))

    return Confirm.ask("\n[bold]Proceed with transcription?[/bold]", default=True)


def run_interactive_cli(file_path: str) -> dict | None:
    """
    Run the full interactive CLI flow.

    Returns dict with: decimal, title, tags, date, analyses
    Or None if cancelled.
    """
    import os

    console.print(Panel(
        f"[bold]Knowledge Base Transcription[/bold]\n\nFile: {os.path.basename(file_path)}",
        border_style="cyan"
    ))

    registry = load_registry()

    # Step 1: Select decimal
    decimal = select_decimal(registry)

    # Step 2: Get title
    default_title = os.path.splitext(os.path.basename(file_path))[0]
    title = get_title(default_title)

    # Step 3: Select tags
    tags = select_tags(registry)

    # Step 4: Optional date
    date = get_recording_date()

    # Step 5: Select analyses
    analyses = select_analysis_types(registry, decimal)

    # Step 6: Confirm
    if not confirm_metadata(file_path, decimal, title, tags, date, analyses):
        console.print("[yellow]Cancelled.[/yellow]")
        return None

    # Save any new tags to registry
    for tag in tags:
        if tag not in registry["tags"]:
            registry["tags"].append(tag)
    save_registry(registry)

    return {
        "decimal": decimal,
        "title": title,
        "tags": tags,
        "date": date,
        "analyses": analyses
    }


def main():
    """Test the CLI."""
    if len(sys.argv) < 2:
        print("Usage: python -m kb.cli <file_path>")
        print("       python kb/cli.py <file_path>")
        sys.exit(1)

    result = run_interactive_cli(sys.argv[1])
    if result:
        console.print(f"\n[bold green]Result:[/bold green] {result}")


if __name__ == "__main__":
    main()
