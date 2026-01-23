#!/usr/bin/env python3
"""
File Source - Transcribe a single audio/video file.

Usage:
    kb transcribe file /path/to/file.mp4
    kb transcribe file --decimal 50.01.01 --title "My Video" /path/to/file.mp4
    kb transcribe file  # Interactive mode
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
import questionary
from questionary import Style

from kb.core import (
    transcribe_to_kb, load_registry, save_registry,
    print_status, slugify, SUPPORTED_FORMATS, KB_ROOT,
    DEFAULT_WHISPER_MODEL
)

console = Console()

custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
])

# Configurable recent directories
RECENT_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
]

SUPPORTED_EXTENSIONS = set(SUPPORTED_FORMATS)


def format_age(mtime: float) -> str:
    """Format file age as human-readable string."""
    age_seconds = datetime.now().timestamp() - mtime
    if age_seconds < 3600:
        return f"{int(age_seconds // 60)}m ago"
    elif age_seconds < 86400:
        return f"{int(age_seconds // 3600)}h ago"
    else:
        return f"{int(age_seconds // 86400)}d ago"


def find_recent_media(directory: Path, limit: int = 10) -> list[Path]:
    """Find recent audio/video files in a directory."""
    files = []
    if directory.exists():
        for f in directory.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(f)
    # Sort by modification time, most recent first
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:limit]


def run_interactive():
    """Interactive file selection and transcription flow."""
    from kb.cli import select_decimal, select_tags, get_title, get_recording_date, select_analysis_types

    console.print(Panel("[bold]Transcribe File[/bold]", border_style="cyan"))

    # Build choices: recent files from configured dirs + free-form entry
    choices = []

    for directory in RECENT_DIRS:
        recent = find_recent_media(directory)
        if recent:
            for f in recent[:3]:  # Top 3 from each directory
                try:
                    rel_path = f"~/{f.relative_to(Path.home())}"
                except ValueError:
                    rel_path = str(f)
                age = format_age(f.stat().st_mtime)
                choices.append(questionary.Choice(
                    title=f"{rel_path}  ({age})",
                    value=str(f)
                ))

    choices.append(questionary.Choice(
        title="[Enter path manually...]",
        value="__manual__"
    ))

    selected = questionary.select(
        "Select file:",
        choices=choices,
        style=custom_style,
    ).ask()

    if selected is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    if selected == "__manual__":
        file_path = questionary.text("File path:").ask()
        if not file_path:
            console.print("[yellow]Cancelled.[/yellow]")
            return
        file_path = Path(file_path.strip().strip("'\"")).expanduser()
    else:
        file_path = Path(selected)

    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    # Get metadata
    registry = load_registry()

    decimal = select_decimal(registry)
    if decimal is None:
        return

    default_title = file_path.stem
    title = get_title(default_title)
    if not title:
        return

    tags = select_tags(registry)

    date = get_recording_date()

    # Select analysis types
    analyses = select_analysis_types(registry, decimal)

    # Confirm
    console.print(f"\n[bold]Will transcribe:[/bold]")
    console.print(f"  File: {file_path}")
    console.print(f"  Decimal: {decimal}")
    console.print(f"  Title: {title}")
    console.print(f"  Tags: {tags}")
    console.print(f"  Analyses: {analyses}")

    if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Transcribe
    try:
        result = transcribe_to_kb(
            file_path=str(file_path),
            decimal=decimal,
            title=title,
            tags=tags,
            recorded_at=date,
            model_name=DEFAULT_WHISPER_MODEL
        )

        print_status("Transcription complete!")
        print_status(f"ID: {result['id']}")
        print_status(f"Words: {len(result['transcript'].split())}")

        # Run analysis if requested
        if analyses:
            _run_analysis(result, decimal, title, analyses)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _run_analysis(result: dict, decimal: str, title: str, analysis_types: list[str]):
    """Run analysis on completed transcript."""
    from kb.core import slugify, KB_ROOT

    date_str = result.get("recorded_at", "")
    if len(date_str) == 10:  # YYYY-MM-DD format
        date_str = datetime.strptime(date_str, "%Y-%m-%d").strftime("%y%m%d")
    slug = slugify(title)
    filename = f"{date_str}-{slug}.json"
    transcript_path = KB_ROOT / decimal / filename

    print_status(f"Running analysis: {', '.join(analysis_types)}")

    try:
        from kb.analyze import analyze_transcript_file
        analyze_transcript_file(
            transcript_path=str(transcript_path),
            analysis_types=analysis_types,
            save=True
        )
    except ImportError as e:
        print(f"Warning: Could not run analysis - {e}")
    except Exception as e:
        print(f"Warning: Analysis failed - {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe a single audio/video file to knowledge base"
    )
    parser.add_argument("file_path", nargs="?", help="Path to audio/video file")
    parser.add_argument("--decimal", "-d", help="Decimal category (e.g., 50.01.01)")
    parser.add_argument("--title", "-t", help="Title for the transcript")
    parser.add_argument("--tags", nargs="+", help="Tags (space-separated)")
    parser.add_argument("--date", help="Recording date (YYYY-MM-DD)")
    parser.add_argument("--speakers", nargs="+", help="Speaker names")
    parser.add_argument("--model", "-m", default=DEFAULT_WHISPER_MODEL,
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help=f"Whisper model (default: {DEFAULT_WHISPER_MODEL})")
    parser.add_argument("--analyze", "-a", nargs="*", metavar="TYPE",
                        help="Run LLM analysis after transcription (e.g., --analyze summary key_points)")
    parser.add_argument("--list-decimals", action="store_true", help="List available decimal categories")
    parser.add_argument("--list-tags", action="store_true", help="List available tags")

    args = parser.parse_args()

    registry = load_registry()

    if args.list_decimals:
        print("\nAvailable decimal categories:")
        for dec, info in registry["decimals"].items():
            print(f"  {dec}: {info['name']}")
        return

    if args.list_tags:
        print("\nAvailable tags:")
        for tag in sorted(registry["tags"]):
            print(f"  {tag}")
        return

    # If no file path, run interactive mode
    if not args.file_path:
        run_interactive()
        return

    # Non-interactive mode
    if not args.decimal:
        print("Error: --decimal is required (or run without arguments for interactive mode)")
        print("\nAvailable decimal categories:")
        for dec, info in registry["decimals"].items():
            print(f"  {dec}: {info['name']}")
        sys.exit(1)

    if not args.title:
        args.title = os.path.splitext(os.path.basename(args.file_path))[0]
        print_status(f"Using filename as title: {args.title}")

    tags = args.tags or []

    try:
        result = transcribe_to_kb(
            file_path=args.file_path,
            decimal=args.decimal,
            title=args.title,
            tags=tags,
            recorded_at=args.date,
            speakers=args.speakers,
            model_name=args.model
        )

        print_status("Transcription complete!")
        print_status(f"ID: {result['id']}")
        print_status(f"Words: {len(result['transcript'].split())}")

        # Run analysis if requested
        if args.analyze is not None:
            if len(args.analyze) == 0:
                analysis_types = ["summary"]
            else:
                analysis_types = args.analyze

            _run_analysis(result, args.decimal, args.title, analysis_types)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
