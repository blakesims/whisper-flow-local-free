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
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import print as rprint
import questionary
from questionary import Style

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

# Knowledge base paths
KB_ROOT = Path.home() / "Obsidian" / "zen-ai" / "knowledge-base" / "transcripts"
CONFIG_DIR = KB_ROOT / "config"
REGISTRY_PATH = CONFIG_DIR / "registry.json"


def load_registry() -> dict:
    """Load the registry.json file."""
    import json
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {"decimals": {}, "tags": [], "transcribed_files": []}


def save_registry(registry: dict):
    """Save the registry.json file."""
    import json
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)


def select_decimal(registry: dict) -> str:
    """Interactive decimal category selection."""
    decimals = registry.get("decimals", {})

    console.print("\n[bold cyan]Select decimal category:[/bold cyan]")
    console.print("[dim]↑↓/jk to move, Enter to select[/dim]\n")

    # Build choices for questionary
    choices = []
    for dec, info in decimals.items():
        label = f"{dec}: {info.get('name', '')}"
        choices.append(questionary.Choice(title=label, value=dec))

    selected = questionary.select(
        "Category:",
        choices=choices,
        style=custom_style,
        instruction="(↑↓ to move, Enter to select)"
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
    console.print("[dim]↑↓/jk to move, Space to select, 'a' to add new, Enter when done[/dim]\n")

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
    console.print("[dim]↑↓/jk to move, Space to toggle, Enter when done[/dim]")
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
        print("Usage: python kb_cli.py <file_path>")
        sys.exit(1)

    result = run_interactive_cli(sys.argv[1])
    if result:
        console.print(f"\n[bold green]Result:[/bold green] {result}")


if __name__ == "__main__":
    main()
