#!/usr/bin/env python3
"""
KB Transcribe - Source dispatcher for transcription commands.

This module provides a submenu for selecting transcription sources:
- file: Transcribe a single audio/video file
- cap: Batch process Cap recordings
- volume: Auto-transcribe from mounted volume
- zoom: Transcribe Zoom meeting recordings (placeholder)
- paste: Import transcript from clipboard

Usage:
    kb transcribe           # Interactive source selection menu
    kb transcribe file      # Run file source
    kb transcribe cap       # Run cap source
    kb transcribe volume    # Run volume source
    kb transcribe paste     # Run paste source
    kb transcribe file /path/to/file.mp4 --decimal 50.01  # Non-interactive
"""

import sys
import importlib

from rich.console import Console
from rich.panel import Panel
import questionary
from questionary import Style

from kb.sources import SOURCES, get_source_choices, run_source

console = Console()

custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
])


def show_source_menu() -> str | None:
    """Show source selection menu and return selected source key."""
    console.print(Panel(
        "[bold]Transcribe to Knowledge Base[/bold]\n\n"
        "Select a source:",
        border_style="cyan"
    ))

    choices = []
    for key, label, description in get_source_choices():
        choices.append(questionary.Choice(
            title=f"{label:12} - {description}",
            value=key
        ))
    choices.append(questionary.Choice(title="Back", value=None))

    return questionary.select(
        "",
        choices=choices,
        style=custom_style,
        instruction="(up/down to move, Enter to select)"
    ).ask()


def main():
    """Main entry point for kb transcribe command."""
    args = sys.argv[1:]

    # Non-interactive: kb transcribe file /path/to/file.mp4
    if args and args[0] in SOURCES:
        source_key = args[0]
        source_args = args[1:]

        # Check if it's a placeholder source
        if SOURCES[source_key].get("placeholder"):
            console.print(f"[yellow]{SOURCES[source_key]['label']} source not yet implemented.[/yellow]")
            return

        run_source(source_key, source_args, interactive=False)
        return

    # Help for subcommands
    if args and args[0] in ["--help", "-h"]:
        print(__doc__)
        print("\nAvailable sources:")
        for key, info in SOURCES.items():
            placeholder = " (not implemented)" if info.get("placeholder") else ""
            print(f"  {key:12} - {info['description']}{placeholder}")
        print("\nExamples:")
        print("  kb transcribe file /path/to/video.mp4 --decimal 50.01 --title 'My Video'")
        print("  kb transcribe cap --list")
        print("  kb transcribe volume --dry-run")
        print("  kb transcribe paste")
        return

    # Unknown subcommand
    if args and args[0] not in SOURCES:
        console.print(f"[red]Unknown source: {args[0]}[/red]")
        console.print("\nAvailable sources: " + ", ".join(SOURCES.keys()))
        sys.exit(1)

    # Interactive: show source menu
    selected = show_source_menu()

    if selected is None:
        console.print("[dim]Back to main menu.[/dim]")
        return

    # Run selected source in interactive mode
    run_source(selected, [], interactive=True)


if __name__ == "__main__":
    main()
