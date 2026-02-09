#!/usr/bin/env python3
"""
KB Inbox - File Inbox and Auto-Processing

Watches ~/.kb/inbox/<decimal>/ directories for media files,
transcribes them, runs configured analyses, and archives/deletes.

Usage:
    kb process-inbox              # Process all files in inbox
    kb process-inbox --dry-run    # Show what would be processed
    kb process-inbox --verbose    # Show detailed progress
"""

import sys
import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.config import load_config, get_paths, DEFAULTS
from kb.core import (
    SUPPORTED_FORMATS,
    load_registry,
    transcribe_to_kb,
    detect_source_type,
    print_status,
)
from kb.analyze import analyze_transcript_file, list_analysis_types

console = Console()

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]

# Default inbox paths
DEFAULT_INBOX_PATH = Path.home() / ".kb" / "inbox"
DEFAULT_ARCHIVE_PATH = Path.home() / ".kb" / "archive"


def get_inbox_config() -> dict:
    """Get inbox configuration from config file.

    Returns config with keys:
    - path: Path to inbox directory
    - archive_path: Path to archive directory (or None to delete)
    - decimal_defaults: Dict mapping decimal codes to analysis configs
    """
    inbox_config = _config.get("inbox", {})

    # Expand paths
    inbox_path = inbox_config.get("path", str(DEFAULT_INBOX_PATH))
    inbox_path = Path(os.path.expanduser(inbox_path))

    archive_path = inbox_config.get("archive_path", str(DEFAULT_ARCHIVE_PATH))
    if archive_path:
        archive_path = Path(os.path.expanduser(archive_path))
    else:
        archive_path = None  # Delete after processing

    decimal_defaults = inbox_config.get("decimal_defaults", {})

    return {
        "path": inbox_path,
        "archive_path": archive_path,
        "decimal_defaults": decimal_defaults,
    }


def ensure_inbox_dirs(inbox_path: Path) -> list[Path]:
    """Create inbox directory structure if needed.

    Creates inbox subdirectories for each decimal in the registry.
    Returns list of created directories.
    """
    inbox_path.mkdir(parents=True, exist_ok=True)

    registry = load_registry()
    decimals = registry.get("decimals", {})

    created = []
    for decimal in decimals.keys():
        decimal_dir = inbox_path / decimal
        if not decimal_dir.exists():
            decimal_dir.mkdir(parents=True)
            created.append(decimal_dir)

    return created


def scan_inbox(inbox_path: Path) -> list[dict]:
    """Scan inbox for media files to process.

    Returns list of dicts with:
    - path: Path to file
    - decimal: Decimal code from directory name
    - filename: Original filename
    """
    if not inbox_path.exists():
        return []

    files = []

    # Scan each decimal subdirectory
    for decimal_dir in inbox_path.iterdir():
        if not decimal_dir.is_dir():
            continue

        decimal = decimal_dir.name

        # Skip non-decimal directories
        if not decimal.replace(".", "").isdigit():
            continue

        # Find supported media files
        for file_path in decimal_dir.iterdir():
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in SUPPORTED_FORMATS:
                    files.append({
                        "path": file_path,
                        "decimal": decimal,
                        "filename": file_path.name,
                    })

    # Sort by decimal, then filename
    files.sort(key=lambda x: (x["decimal"], x["filename"]))

    return files


def get_analyses_for_decimal(decimal: str, config: dict) -> list[str]:
    """Get list of analyses to run for a decimal category.

    Uses decimal_defaults from config, falling back to just ["summary"].
    """
    decimal_defaults = config.get("decimal_defaults", {})

    # Try exact match first
    if decimal in decimal_defaults:
        return decimal_defaults[decimal].get("analyses", ["summary"])

    # Try prefix match (e.g., "50.01" matches "50.01.01")
    for prefix, settings in decimal_defaults.items():
        if decimal.startswith(prefix + ".") or decimal == prefix:
            return settings.get("analyses", ["summary"])

    # Default to summary only
    return ["summary"]


def generate_title_from_filename(filename: str) -> str:
    """Generate a title from a filename.

    Examples:
        "skool-call-01.mp4" -> "Skool Call 01"
        "2026-01-30-alpha-session.mp4" -> "Alpha Session"
    """
    # Remove extension
    name = Path(filename).stem

    # Replace hyphens and underscores with spaces
    name = name.replace("-", " ").replace("_", " ")

    # Remove common date patterns (YYYY-MM-DD or YYMMDD)
    import re
    name = re.sub(r'^\d{4}[ -]?\d{2}[ -]?\d{2}\s*', '', name)
    name = re.sub(r'^\d{6}\s*', '', name)

    # Title case
    name = name.title()

    return name.strip() or "Untitled"


def process_file(
    file_info: dict,
    config: dict,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Process a single inbox file.

    1. Transcribe to KB
    2. Run configured analyses
    3. Archive or delete original

    Returns dict with:
    - success: bool
    - transcript_path: Path to created transcript (if successful)
    - analyses_run: List of analysis types run
    - error: Error message (if failed)
    """
    file_path = file_info["path"]
    decimal = file_info["decimal"]
    filename = file_info["filename"]

    result = {
        "success": False,
        "transcript_path": None,
        "analyses_run": [],
        "error": None,
    }

    # Validate decimal exists in registry
    registry = load_registry()
    if decimal not in registry.get("decimals", {}):
        result["error"] = f"Unknown decimal: {decimal}"
        return result

    # Generate title
    title = generate_title_from_filename(filename)

    if verbose:
        console.print(f"  [dim]Title: {title}[/dim]")
        console.print(f"  [dim]Decimal: {decimal}[/dim]")

    if dry_run:
        result["success"] = True
        result["analyses_run"] = get_analyses_for_decimal(decimal, config)
        return result

    try:
        # Step 1: Transcribe
        print_status(f"Transcribing: {filename}")

        source_type = detect_source_type(str(file_path))
        transcript_data = transcribe_to_kb(
            file_path=str(file_path),
            decimal=decimal,
            title=title,
            tags=[],  # No tags for inbox items
            source_type=source_type,
        )

        transcript_path = KB_ROOT / decimal / f"{transcript_data['id'].split('-', 1)[1]}.json"
        # Actually the path is built differently in transcribe_to_kb
        # Let's find it from the ID
        date_slug = transcript_data["id"].replace(f"{decimal}-", "")
        transcript_path = KB_ROOT / decimal / f"{date_slug}.json"

        if not transcript_path.exists():
            # Try alternate path construction
            from kb.core import slugify
            date_str = datetime.now().strftime("%y%m%d")
            slug = slugify(title)
            transcript_path = KB_ROOT / decimal / f"{date_str}-{slug}.json"

        result["transcript_path"] = str(transcript_path)

        # Step 2: Run analyses
        analyses_to_run = get_analyses_for_decimal(decimal, config)
        available_types = [t["name"] for t in list_analysis_types()]

        # Filter to only available analysis types
        valid_analyses = [a for a in analyses_to_run if a in available_types]

        if valid_analyses:
            print_status(f"Running analyses: {', '.join(valid_analyses)}")

            analyze_transcript_file(
                transcript_path=str(transcript_path),
                analysis_types=valid_analyses,
                save=True,
                skip_existing=True,
            )

            result["analyses_run"] = valid_analyses

        # Step 3: Archive or delete
        archive_path = config.get("archive_path")

        if archive_path:
            # Archive: move to archive directory with same structure
            archive_dest = archive_path / decimal / filename
            archive_dest.parent.mkdir(parents=True, exist_ok=True)

            # Handle existing files in archive
            if archive_dest.exists():
                base = archive_dest.stem
                ext = archive_dest.suffix
                counter = 1
                while archive_dest.exists():
                    archive_dest = archive_path / decimal / f"{base}-{counter}{ext}"
                    counter += 1

            shutil.move(str(file_path), str(archive_dest))
            print_status(f"Archived: {archive_dest}")
        else:
            # Delete
            file_path.unlink()
            print_status(f"Deleted: {filename}")

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error: {e}[/red]")

    return result


def process_inbox(
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Process all files in the inbox.

    Returns dict with:
    - processed: Number of files successfully processed
    - failed: Number of files that failed
    - skipped: Number of files skipped (dry run)
    - results: List of individual results
    """
    config = get_inbox_config()
    inbox_path = config["path"]

    # Ensure inbox directories exist
    ensure_inbox_dirs(inbox_path)

    # Scan for files
    files = scan_inbox(inbox_path)

    if not files:
        console.print("[dim]No files in inbox[/dim]")
        return {
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
        }

    console.print(Panel(
        f"[bold]Inbox Processing[/bold]\n\n"
        f"Found {len(files)} file(s) to process",
        border_style="cyan"
    ))

    if dry_run:
        console.print("[yellow]Dry run - no changes will be made[/yellow]\n")

    results = []
    processed = 0
    failed = 0

    for i, file_info in enumerate(files, 1):
        console.print(f"\n[bold cyan]({i}/{len(files)}) {file_info['filename']}[/bold cyan]")
        console.print(f"  [dim]Decimal: {file_info['decimal']}[/dim]")

        result = process_file(file_info, config, dry_run=dry_run, verbose=verbose)
        results.append({**file_info, **result})

        if result["success"]:
            processed += 1
            if dry_run:
                analyses = result.get("analyses_run", [])
                console.print(f"  [green]Would process[/green]")
                console.print(f"  [dim]Analyses: {', '.join(analyses)}[/dim]")
            else:
                console.print(f"  [green]Processed successfully[/green]")
        else:
            failed += 1
            console.print(f"  [red]Failed: {result.get('error', 'Unknown error')}[/red]")

    # Summary
    console.print("\n" + "─" * 40)
    if dry_run:
        console.print(f"[bold]Would process:[/bold] {processed} file(s)")
    else:
        console.print(f"[bold green]Processed:[/bold green] {processed} file(s)")
        if failed > 0:
            console.print(f"[bold red]Failed:[/bold red] {failed} file(s)")

    return {
        "processed": processed,
        "failed": failed,
        "skipped": len(files) if dry_run else 0,
        "results": results,
    }


def show_inbox_status():
    """Display current inbox status."""
    config = get_inbox_config()
    inbox_path = config["path"]
    archive_path = config["archive_path"]

    console.print(Panel("[bold]Inbox Status[/bold]", border_style="cyan"))

    # Paths
    console.print(f"\n[bold cyan]Paths[/bold cyan]")
    console.print(f"  Inbox:   {inbox_path}")
    console.print(f"  Archive: {archive_path or '[red]delete after processing[/red]'}")

    # Ensure directories exist
    if not inbox_path.exists():
        created = ensure_inbox_dirs(inbox_path)
        if created:
            console.print(f"\n[green]Created {len(created)} inbox directories[/green]")

    # Scan for files
    files = scan_inbox(inbox_path)

    if not files:
        console.print(f"\n[dim]No files pending in inbox[/dim]")
    else:
        console.print(f"\n[bold cyan]Pending Files ({len(files)})[/bold cyan]")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Decimal", style="cyan")
        table.add_column("Filename")
        table.add_column("Size", justify="right")
        table.add_column("Analyses")

        for f in files:
            size = f["path"].stat().st_size
            size_str = f"{size / (1024*1024):.1f} MB" if size > 1024*1024 else f"{size / 1024:.0f} KB"
            analyses = get_analyses_for_decimal(f["decimal"], config)

            table.add_row(
                f["decimal"],
                f["filename"],
                size_str,
                ", ".join(analyses),
            )

        console.print(table)

    # Decimal defaults info
    decimal_defaults = config.get("decimal_defaults", {})
    if decimal_defaults:
        console.print(f"\n[bold cyan]Configured Defaults[/bold cyan]")
        for decimal, settings in decimal_defaults.items():
            analyses = settings.get("analyses", ["summary"])
            console.print(f"  {decimal}: {', '.join(analyses)}")
    else:
        console.print(f"\n[dim]No decimal defaults configured (using summary for all)[/dim]")


def show_cron_instructions():
    """Display cron job setup instructions."""
    console.print(Panel("[bold]Cron Job Setup[/bold]", border_style="cyan"))

    console.print("""
[bold cyan]To auto-process inbox files on a schedule:[/bold cyan]

1. Open crontab editor:
   [green]crontab -e[/green]

2. Add one of these lines:

   [dim]# Every 15 minutes[/dim]
   [green]*/15 * * * * /usr/bin/python3 -m kb process-inbox >> ~/.kb/inbox.log 2>&1[/green]

   [dim]# Every hour at :00[/dim]
   [green]0 * * * * /usr/bin/python3 -m kb process-inbox >> ~/.kb/inbox.log 2>&1[/green]

   [dim]# Daily at 6 AM[/dim]
   [green]0 6 * * * /usr/bin/python3 -m kb process-inbox >> ~/.kb/inbox.log 2>&1[/green]

3. Alternative: systemd timer (Linux) or launchd (macOS)

[bold cyan]Monitor processing:[/bold cyan]
   [green]tail -f ~/.kb/inbox.log[/green]

[bold cyan]Manual processing:[/bold cyan]
   [green]kb process-inbox[/green]
   [green]kb process-inbox --dry-run[/green]
""")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="KB Inbox - Process files dropped in inbox directories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kb process-inbox              # Process all inbox files
  kb process-inbox --dry-run    # Preview what would be processed
  kb process-inbox --status     # Show inbox status
  kb process-inbox --cron       # Show cron job setup instructions
        """
    )
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show what would be processed without making changes")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed progress")
    parser.add_argument("--status", "-s", action="store_true",
                        help="Show inbox status and pending files")
    parser.add_argument("--cron", action="store_true",
                        help="Show cron job setup instructions")
    parser.add_argument("--init", action="store_true",
                        help="Initialize inbox directories")

    args = parser.parse_args()

    if args.cron:
        show_cron_instructions()
        return

    if args.status:
        show_inbox_status()
        return

    if args.init:
        config = get_inbox_config()
        created = ensure_inbox_dirs(config["path"])
        if created:
            console.print(f"[green]Created {len(created)} inbox directories:[/green]")
            for d in created:
                console.print(f"  {d}")
        else:
            console.print("[dim]All inbox directories already exist[/dim]")
        return

    # Default: process inbox
    process_inbox(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
