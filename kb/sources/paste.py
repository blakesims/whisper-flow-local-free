#!/usr/bin/env python3
"""
Paste Source - Import transcript from clipboard.

Parses transcript text from clipboard (e.g., from Google Meet browser script)
and saves to knowledge base without needing audio transcription.

Expected formats:
    [00:25] Blake Sims: It.
    [03:57] Nemanja Pavlovic: Hey there.
    [01:23:45] Speaker: For longer meetings...

Usage:
    kb transcribe paste           # Read from clipboard
    kb transcribe paste --file transcript.txt  # Read from file instead
"""

import sys
import os
import re
import subprocess
import argparse
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
import questionary
from questionary import Style

from kb.core import (
    transcribe_to_kb, load_registry, save_registry, print_status,
    slugify, KB_ROOT
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

# Regex handles both [MM:SS] and [HH:MM:SS] formats
TRANSCRIPT_PATTERN = re.compile(
    r'^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s+([^:]+):\s+(.+)$',
    re.MULTILINE
)


def get_clipboard() -> str:
    """Get clipboard contents (macOS)."""
    try:
        result = subprocess.run(['pbpaste'], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        console.print(f"[red]Failed to read clipboard: {e}[/red]")
        return ""


def normalize_timestamp(ts: str) -> str:
    """
    Normalize timestamp format.

    Keeps MM:SS for short timestamps, HH:MM:SS for longer ones.
    This matches the format_timestamp() output.
    """
    parts = ts.split(':')
    if len(parts) == 2:
        # MM:SS - keep as is (zeropad if needed)
        return f"{int(parts[0]):02d}:{parts[1]}"
    elif len(parts) == 3:
        # HH:MM:SS
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{parts[2]}"
    return ts


def validate_transcript(text: str) -> tuple[bool, list[dict]]:
    """
    Validate clipboard text is a transcript.

    Returns (is_valid, parsed_segments).
    """
    matches = TRANSCRIPT_PATTERN.findall(text)
    if not matches:
        return False, []

    segments = [
        {
            "timestamp": normalize_timestamp(m[0]),
            "speaker": m[1].strip(),
            "text": m[2].strip()
        }
        for m in matches
    ]
    return True, segments


def extract_speakers(segments: list[dict]) -> list[str]:
    """Extract unique speakers in order of appearance."""
    seen = set()
    speakers = []
    for seg in segments:
        if seg["speaker"] not in seen:
            seen.add(seg["speaker"])
            speakers.append(seg["speaker"])
    return speakers


def format_transcript_text(segments: list[dict]) -> str:
    """Format segments as plain text transcript."""
    lines = []
    for seg in segments:
        lines.append(f"[{seg['timestamp']}] {seg['speaker']}: {seg['text']}")
    return "\n".join(lines)


def estimate_duration(segments: list[dict]) -> int:
    """Estimate duration in seconds from last timestamp."""
    if not segments:
        return 0

    last_ts = segments[-1]["timestamp"]
    parts = last_ts.split(':')

    if len(parts) == 2:
        # MM:SS
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        # HH:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

    return 0


def run_interactive():
    """Interactive paste import flow."""
    from kb.cli import select_decimal, select_tags, get_title, get_recording_date, select_analysis_types

    console.print(Panel("[bold]Import Transcript from Clipboard[/bold]", border_style="cyan"))

    # Get clipboard
    text = get_clipboard()
    if not text.strip():
        console.print("[red]Clipboard is empty[/red]")
        return

    # Validate format
    is_valid, segments = validate_transcript(text)
    if not is_valid:
        console.print("[red]Clipboard does not contain valid transcript format[/red]")
        console.print("[dim]Expected: [MM:SS] Speaker: Text  or  [HH:MM:SS] Speaker: Text[/dim]")
        console.print("\n[dim]First 200 chars of clipboard:[/dim]")
        console.print(f"[dim]{text[:200]}...[/dim]")
        return

    # Show preview
    speakers = extract_speakers(segments)
    duration = estimate_duration(segments)

    console.print(f"\n[green]Found {len(segments)} segments from {len(speakers)} speakers:[/green]")
    for speaker in speakers:
        console.print(f"  * {speaker}")

    console.print(f"\n[dim]Estimated duration: {duration // 60}m {duration % 60}s[/dim]")

    console.print(f"\n[dim]Preview (first 3 lines):[/dim]")
    for seg in segments[:3]:
        preview_text = seg['text'][:50] + "..." if len(seg['text']) > 50 else seg['text']
        console.print(f"  [{seg['timestamp']}] {seg['speaker']}: {preview_text}")

    # Get metadata
    registry = load_registry()

    decimal = select_decimal(registry)
    if decimal is None:
        return

    # Generate default title from speakers
    if len(speakers) == 1:
        default_title = f"Meeting with {speakers[0]}"
    elif len(speakers) == 2:
        default_title = f"Meeting - {speakers[0]} & {speakers[1]}"
    else:
        default_title = f"Meeting - {speakers[0]} et al"

    title = get_title(default_title)
    if not title:
        return

    tags = select_tags(registry)
    date = get_recording_date()

    # Select analysis types
    analyses = select_analysis_types(registry, decimal)

    # Format the transcript text (plain format, no markdown)
    transcript_text = format_transcript_text(segments)

    # Confirm
    console.print(f"\n[bold]Will save transcript:[/bold]")
    console.print(f"  Decimal: {decimal}")
    console.print(f"  Title: {title}")
    console.print(f"  Tags: {tags}")
    console.print(f"  Speakers: {speakers}")
    console.print(f"  Segments: {len(segments)}")
    console.print(f"  Analyses: {analyses}")

    if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Save to KB - use placeholder path since we don't have an actual file
    try:
        result = transcribe_to_kb(
            file_path="clipboard",  # Placeholder
            decimal=decimal,
            title=title,
            tags=tags,
            recorded_at=date,
            speakers=speakers,
            source_type="paste",
            transcript_text=transcript_text,  # Pre-existing transcript
        )

        print_status("Transcript saved!")
        print_status(f"ID: {result['id']}")
        print_status(f"Words: {len(transcript_text.split())}")

        # Run analysis if requested
        if analyses:
            _run_analysis(result, decimal, title, analyses)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _run_analysis(result: dict, decimal: str, title: str, analysis_types: list[str]):
    """Run analysis on saved transcript."""
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
        description="Import transcript from clipboard to knowledge base"
    )
    parser.add_argument("--file", "-f", help="Read from file instead of clipboard")
    parser.add_argument("--decimal", "-d", help="Decimal category (e.g., 50.01.01)")
    parser.add_argument("--title", "-t", help="Title for the transcript")
    parser.add_argument("--tags", nargs="+", help="Tags (space-separated)")
    parser.add_argument("--date", help="Recording date (YYYY-MM-DD)")
    parser.add_argument("--analyze", "-a", nargs="*", metavar="TYPE",
                        help="Run LLM analysis after import")

    args = parser.parse_args()

    # If minimal args provided, run interactive
    if not args.decimal:
        run_interactive()
        return

    # Non-interactive mode
    if args.file:
        with open(args.file, 'r') as f:
            text = f.read()
    else:
        text = get_clipboard()

    if not text.strip():
        console.print("[red]No transcript text found[/red]")
        sys.exit(1)

    is_valid, segments = validate_transcript(text)
    if not is_valid:
        console.print("[red]Invalid transcript format[/red]")
        sys.exit(1)

    speakers = extract_speakers(segments)
    transcript_text = format_transcript_text(segments)

    if not args.title:
        args.title = f"Meeting - {datetime.now().strftime('%Y-%m-%d')}"

    try:
        result = transcribe_to_kb(
            file_path="clipboard",
            decimal=args.decimal,
            title=args.title,
            tags=args.tags or [],
            recorded_at=args.date,
            speakers=speakers,
            source_type="paste",
            transcript_text=transcript_text,
        )

        print_status("Transcript saved!")
        print_status(f"ID: {result['id']}")

        # Run analysis if requested
        if args.analyze is not None:
            analysis_types = args.analyze if args.analyze else ["summary"]
            _run_analysis(result, args.decimal, args.title, analysis_types)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
