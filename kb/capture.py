#!/usr/bin/env python3
"""
Cap Recordings Capture Script

Lists Cap recordings and allows multi-select transcription to knowledge base.

Usage:
    python kb/capture.py           # Interactive selection
    python kb/capture.py --list    # Just list recordings
"""

import sys
import os
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# Add project root to path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
import questionary
from questionary import Style

from kb.transcribe import transcribe_to_kb, load_registry
from kb.cli import run_interactive_cli, custom_style

console = Console()

# Cap recordings location
CAP_RECORDINGS_DIR = Path.home() / "Library" / "Application Support" / "so.cap.desktop.dev" / "recordings"


def get_cap_recordings() -> list[dict]:
    """Get all Cap recordings sorted by date (newest first)."""
    recordings = []

    if not CAP_RECORDINGS_DIR.exists():
        return recordings

    for cap_dir in CAP_RECORDINGS_DIR.glob("*.cap"):
        meta_file = cap_dir / "recording-meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file) as f:
                meta = json.load(f)

            # Get modification time for sorting
            mtime = cap_dir.stat().st_mtime

            # Count segments
            segments = meta.get("segments", [])

            # Calculate total duration by checking audio files
            total_duration = 0
            audio_files = []
            for i, seg in enumerate(segments):
                mic_path = seg.get("mic", {}).get("path", "")
                if mic_path:
                    full_path = cap_dir / mic_path
                    if full_path.exists():
                        audio_files.append(str(full_path))
                        # Get duration via ffprobe
                        try:
                            result = subprocess.run([
                                'ffprobe', '-v', 'quiet',
                                '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1',
                                str(full_path)
                            ], capture_output=True, text=True, timeout=10)
                            if result.returncode == 0:
                                total_duration += float(result.stdout.strip())
                        except Exception:
                            pass

            recordings.append({
                "path": str(cap_dir),
                "name": cap_dir.name,
                "pretty_name": meta.get("pretty_name", cap_dir.name),
                "mtime": mtime,
                "date": datetime.fromtimestamp(mtime),
                "segments": len(segments),
                "duration": int(total_duration),
                "audio_files": audio_files,
            })
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {cap_dir.name}: {e}[/yellow]")

    # Sort by date, newest first
    recordings.sort(key=lambda x: x["mtime"], reverse=True)
    return recordings


def merge_audio_files(audio_files: list[str], output_path: str) -> bool:
    """Merge multiple audio files into one using ffmpeg."""
    if len(audio_files) == 1:
        # Just convert single file
        try:
            subprocess.run([
                'ffmpeg', '-i', audio_files[0],
                '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                '-y', output_path
            ], capture_output=True, timeout=120)
            return True
        except Exception:
            return False

    # Create concat file for ffmpeg
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for audio in audio_files:
            f.write(f"file '{audio}'\n")
        concat_file = f.name

    try:
        subprocess.run([
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file,
            '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            '-y', output_path
        ], capture_output=True, timeout=300)
        return True
    except Exception:
        return False
    finally:
        os.unlink(concat_file)


def list_recordings():
    """Display recordings in a table."""
    recordings = get_cap_recordings()

    if not recordings:
        console.print("[yellow]No Cap recordings found.[/yellow]")
        return

    table = Table(title="Cap Recordings", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", style="cyan")
    table.add_column("Name")
    table.add_column("Duration", justify="right")
    table.add_column("Segments", justify="right")

    for i, rec in enumerate(recordings, 1):
        duration_str = f"{rec['duration'] // 60}m {rec['duration'] % 60}s"
        table.add_row(
            str(i),
            rec["date"].strftime("%Y-%m-%d %H:%M"),
            rec["pretty_name"][:40],
            duration_str,
            str(rec["segments"])
        )

    console.print(table)


def select_recordings(recordings: list[dict]) -> list[dict]:
    """Interactive multi-select for recordings."""
    console.print("\n[bold cyan]Select recordings to transcribe:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Space to select, Enter when done[/dim]\n")

    choices = []
    for rec in recordings:
        duration_str = f"{rec['duration'] // 60}m {rec['duration'] % 60}s"
        label = f"{rec['date'].strftime('%Y-%m-%d %H:%M')} | {rec['pretty_name'][:35]} ({duration_str})"
        choices.append(questionary.Choice(title=label, value=rec))

    selected = questionary.checkbox(
        "Recordings:",
        choices=choices,
        style=custom_style,
        instruction="(Space to select, Enter to confirm)"
    ).ask()

    return selected or []


def transcribe_cap_recording(recording: dict, metadata: dict) -> bool:
    """Transcribe a single Cap recording."""
    console.print(f"\n[bold]Transcribing: {recording['pretty_name']}[/bold]")

    if not recording["audio_files"]:
        console.print("[red]No audio files found in recording.[/red]")
        return False

    # Create temp file for merged audio
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_audio = f.name

    try:
        # Merge audio segments
        console.print(f"[dim]Merging {len(recording['audio_files'])} audio segment(s)...[/dim]")
        if not merge_audio_files(recording["audio_files"], temp_audio):
            console.print("[red]Failed to merge audio files.[/red]")
            return False

        # Transcribe
        result = transcribe_to_kb(
            file_path=temp_audio,
            decimal=metadata["decimal"],
            title=metadata["title"],
            tags=metadata["tags"],
            recorded_at=metadata.get("date") or recording["date"].strftime("%Y-%m-%d"),
            speakers=metadata.get("speakers"),
            model_name=metadata.get("model", "medium")
        )

        console.print(f"[green]done Transcribed: {result['id']}[/green]")
        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False
    finally:
        if os.path.exists(temp_audio):
            os.unlink(temp_audio)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Transcribe Cap recordings to knowledge base")
    parser.add_argument("--list", "-l", action="store_true", help="List recordings only")
    args = parser.parse_args()

    console.print(Panel("[bold]Cap Recordings Capture[/bold]", border_style="cyan"))

    recordings = get_cap_recordings()

    if not recordings:
        console.print("[yellow]No Cap recordings found.[/yellow]")
        console.print(f"[dim]Looking in: {CAP_RECORDINGS_DIR}[/dim]")
        return

    if args.list:
        list_recordings()
        return

    # Show table first
    list_recordings()

    # Multi-select recordings
    selected = select_recordings(recordings)

    if not selected:
        console.print("[yellow]No recordings selected.[/yellow]")
        return

    console.print(f"\n[bold]Selected {len(selected)} recording(s)[/bold]")

    # Get metadata for all (using first recording's name as default title)
    # For Cap recordings, default to 50.00.01 (raw captures)
    console.print("\n[bold cyan]Configure transcription settings:[/bold cyan]")

    registry = load_registry()

    # Simplified metadata collection for batch
    from kb.cli import select_decimal, select_tags

    decimal = select_decimal(registry)
    tags = select_tags(registry)

    model = questionary.select(
        "Model:",
        choices=["medium", "small", "large-v2"],
        default="medium",
        style=custom_style
    ).ask()

    # Confirm
    console.print(f"\n[bold]Will transcribe {len(selected)} recording(s) with:[/bold]")
    console.print(f"  Decimal: {decimal}")
    console.print(f"  Tags: {tags}")
    console.print(f"  Model: {model}")

    if not Confirm.ask("\n[bold]Proceed?[/bold]", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Transcribe each
    success = 0
    for rec in selected:
        metadata = {
            "decimal": decimal,
            "title": rec["pretty_name"],
            "tags": tags,
            "date": rec["date"].strftime("%Y-%m-%d"),
            "model": model,
        }

        if transcribe_cap_recording(rec, metadata):
            success += 1

    console.print(f"\n[bold green]Done! Transcribed {success}/{len(selected)} recordings.[/bold green]")


if __name__ == "__main__":
    main()
