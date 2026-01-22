#!/usr/bin/env python3
"""
Volume Auto-Transcriber

Scans a mounted volume for videos and transcribes any not already in the ledger.
Runs without manual input - uses filename as title and configured defaults.

Usage:
    python kb/volume_sync.py                    # Scan and transcribe new files
    python kb/volume_sync.py --list             # List files and their status
    python kb/volume_sync.py --dry-run          # Show what would be transcribed
    python kb/volume_sync.py --decimal 50.01.01 # Override default decimal
"""

import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime

# Add project root to path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm

from kb.transcribe import transcribe_to_kb, load_registry, save_registry

console = Console()

# Default volume path
DEFAULT_VOLUME_PATH = "/Volumes/BackupArchive/skool-videos"

# Default settings for auto-transcription
DEFAULT_DECIMAL = "50.01.01"  # Skool classroom content
DEFAULT_MODEL = "medium"

# Supported video formats
VIDEO_FORMATS = ('.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi')


def get_volume_videos(volume_path: str) -> list[dict]:
    """Get all video files from the volume."""
    videos = []
    volume = Path(volume_path)

    if not volume.exists():
        return videos

    for ext in VIDEO_FORMATS:
        for video_path in volume.glob(f"*{ext}"):
            if video_path.is_file():
                stat = video_path.stat()
                videos.append({
                    "path": str(video_path),
                    "name": video_path.name,
                    "stem": video_path.stem,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "mtime": stat.st_mtime,
                    "date": datetime.fromtimestamp(stat.st_mtime),
                })

    # Sort by date, newest first
    videos.sort(key=lambda x: x["mtime"], reverse=True)
    return videos


def get_transcribed_files(registry: dict) -> set[str]:
    """Get set of already transcribed file paths."""
    return set(registry.get("transcribed_files", []))


def title_from_filename(filename: str) -> str:
    """Generate a nice title from filename."""
    # Remove extension
    name = Path(filename).stem

    # Replace common separators with spaces
    name = re.sub(r'[-_]+', ' ', name)

    # Remove common prefixes like "skool-cc-"
    name = re.sub(r'^skool\s*(cc)?\s*', '', name, flags=re.IGNORECASE)

    # Title case
    name = name.strip().title()

    return name


def list_videos(volume_path: str):
    """Display videos and their transcription status."""
    videos = get_volume_videos(volume_path)
    registry = load_registry()
    transcribed = get_transcribed_files(registry)

    if not videos:
        console.print(f"[yellow]No videos found in {volume_path}[/yellow]")
        return

    table = Table(title=f"Videos in {volume_path}", show_header=True, header_style="bold magenta")
    table.add_column("Status", width=6)
    table.add_column("Date", style="cyan")
    table.add_column("Name")
    table.add_column("Size", justify="right")

    pending = 0
    for video in videos:
        is_transcribed = video["path"] in transcribed
        status = "[green]done[/green]" if is_transcribed else "[yellow]o[/yellow]"
        if not is_transcribed:
            pending += 1

        table.add_row(
            status,
            video["date"].strftime("%Y-%m-%d"),
            video["name"][:45],
            f"{video['size_mb'] / 1024:.1f} GB" if video['size_mb'] > 1024 else f"{video['size_mb']:.0f} MB"
        )

    console.print(table)
    console.print(f"\n[bold]Summary:[/bold] {len(videos)} total, {len(videos) - pending} transcribed, [yellow]{pending} pending[/yellow]")


def sync_volume(
    volume_path: str,
    decimal: str,
    model: str,
    dry_run: bool = False,
    tags: list[str] | None = None
) -> int:
    """
    Sync all new videos from volume to knowledge base.

    Returns number of files transcribed.
    """
    videos = get_volume_videos(volume_path)
    registry = load_registry()
    transcribed = get_transcribed_files(registry)

    # Filter to only new files
    pending = [v for v in videos if v["path"] not in transcribed]

    if not pending:
        console.print("[green]All videos already transcribed![/green]")
        return 0

    console.print(f"\n[bold]Found {len(pending)} new video(s) to transcribe:[/bold]")
    for video in pending:
        console.print(f"  * {video['name']} ({video['size_mb']:.1f} MB)")

    if dry_run:
        console.print("\n[yellow]Dry run - no transcriptions performed.[/yellow]")
        return 0

    if not Confirm.ask(f"\n[bold]Transcribe {len(pending)} video(s)?[/bold]", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return 0

    # Transcribe each
    success = 0
    for i, video in enumerate(pending, 1):
        console.print(f"\n[bold cyan]({i}/{len(pending)}) {video['name']}[/bold cyan]")

        title = title_from_filename(video["name"])

        try:
            result = transcribe_to_kb(
                file_path=video["path"],
                decimal=decimal,
                title=title,
                tags=tags or [],
                recorded_at=video["date"].strftime("%Y-%m-%d"),
                model_name=model
            )

            console.print(f"[green]done Saved: {result['id']}[/green]")
            success += 1

        except Exception as e:
            console.print(f"[red]x Error: {e}[/red]")
            # Continue with next file

    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto-transcribe videos from mounted volume")
    parser.add_argument("--volume", "-v", default=DEFAULT_VOLUME_PATH,
                        help=f"Volume path (default: {DEFAULT_VOLUME_PATH})")
    parser.add_argument("--decimal", "-d", default=DEFAULT_DECIMAL,
                        help=f"Decimal category (default: {DEFAULT_DECIMAL})")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help=f"Whisper model (default: {DEFAULT_MODEL})")
    parser.add_argument("--tags", nargs="+", help="Tags to apply to all transcripts")
    parser.add_argument("--list", "-l", action="store_true", help="List videos and status only")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be transcribed")

    args = parser.parse_args()

    console.print(Panel(f"[bold]Volume Auto-Transcriber[/bold]\n{args.volume}", border_style="cyan"))

    # Check volume exists
    if not Path(args.volume).exists():
        console.print(f"[red]Volume not found: {args.volume}[/red]")
        console.print("[dim]Is the drive mounted?[/dim]")
        sys.exit(1)

    if args.list:
        list_videos(args.volume)
        return

    # Validate decimal
    registry = load_registry()
    if args.decimal not in registry.get("decimals", {}):
        console.print(f"[red]Unknown decimal: {args.decimal}[/red]")
        console.print("\nAvailable:")
        for dec, info in registry.get("decimals", {}).items():
            console.print(f"  {dec}: {info['name']}")
        sys.exit(1)

    # Show current status
    list_videos(args.volume)

    # Sync
    count = sync_volume(
        volume_path=args.volume,
        decimal=args.decimal,
        model=args.model,
        dry_run=args.dry_run,
        tags=args.tags
    )

    if count > 0:
        console.print(f"\n[bold green]Successfully transcribed {count} video(s)![/bold green]")


if __name__ == "__main__":
    main()
