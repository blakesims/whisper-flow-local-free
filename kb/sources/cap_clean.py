#!/usr/bin/env python3
"""
Cap Clean - Clean up Cap recordings by removing junk segments.

Usage:
    kb clean                    # Interactive selection
    kb clean "recording.cap"    # Direct path
"""

import json
import os
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
import questionary
from questionary import Style

# Reuse from existing cap.py
from kb.sources.cap import get_cap_recordings, CAP_RECORDINGS_DIR

# Reuse from core
from kb.core import format_timestamp, get_audio_duration

# Default trigger phrases for auto-deletion
DEFAULT_TRIGGERS = ["delete delete", "cut cut", "delete this"]

console = Console()

custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
])


def load_recording_meta(cap_path: Path) -> dict:
    """Load recording-meta.json from a Cap recording.

    Raises:
        FileNotFoundError: If recording-meta.json doesn't exist
        ValueError: If JSON is malformed
    """
    meta_path = cap_path / "recording-meta.json"
    try:
        with open(meta_path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"recording-meta.json not found in {cap_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid recording-meta.json in {cap_path}: {e}")


def transcribe_segments(cap_path: Path, model_name: str = "medium") -> list[dict]:
    """
    Transcribe all segments in a Cap recording.

    Uses sequential transcription with a single shared model instance
    for efficiency (model loading is expensive, ~1.5GB for medium).

    Note: Parallel transcription was considered but rejected because
    the whisper.cpp model is not thread-safe and loading multiple
    model instances would use excessive memory.

    Returns:
        [{
            "index": 0,
            "path": "/path/to/audio-input.ogg",
            "duration": 12.3,
            "text": "Transcribed text...",
            "formatted": "[00:00] Transcribed text...",
            "status": "success" | "failed",
            "error": "..." (only if status == "failed"),
        }, ...]
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.core.transcription_service_cpp import get_transcription_service
    from app.utils.config_manager import ConfigManager
    from kb.core import LocalFileCopy

    # Load recording metadata
    meta = load_recording_meta(cap_path)
    segments_meta = meta.get("segments", [])

    # Gather audio files with their indices
    audio_files = []
    for i, seg in enumerate(segments_meta):
        mic_info = seg.get("mic", {})
        mic_path = mic_info.get("path", "")
        if mic_path:
            full_path = cap_path / mic_path
            if full_path.exists():
                audio_files.append((i, full_path))
            else:
                console.print(f"[yellow]⚠ Segment {i}: audio missing, skipping[/yellow]")
        else:
            console.print(f"[yellow]⚠ Segment {i}: no mic path, skipping[/yellow]")

    if not audio_files:
        console.print("[red]No audio files found in recording.[/red]")
        return []

    # Load model ONCE (critical for performance)
    config = ConfigManager()
    service = get_transcription_service(config)

    console.print(f"[dim]Loading whisper model: {model_name}...[/dim]")
    service.set_target_model_config(model_name, "cpu", "int8")
    service.load_model()
    console.print("[dim]Model loaded![/dim]")

    # Sequential transcription with progress display
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Transcribing {len(audio_files)} segments...",
            total=len(audio_files)
        )

        for idx, audio_path in audio_files:
            progress.update(task, description=f"Segment {idx}...")

            # Get duration first (before try block to ensure it's always set)
            duration = get_audio_duration(str(audio_path))

            # Transcribe single segment
            try:
                with LocalFileCopy(str(audio_path)) as local_path:
                    result = service.transcribe(
                        local_path,
                        language=config.get("transcription_language", None),
                        beam_size=1,
                        progress_callback=None  # No nested progress
                    )

                # Extract and format transcript
                segments = result.get("segments", [])
                full_text = result.get("text", "").strip()

                # Format with timestamps
                formatted_lines = []
                if segments:
                    for seg in segments:
                        start_seconds = seg.t0 / 100.0
                        ts = format_timestamp(start_seconds)
                        text = seg.text.strip()
                        if text:
                            formatted_lines.append(f"[{ts}] {text}")

                formatted_text = "\n".join(formatted_lines) if formatted_lines else full_text

                results.append({
                    "index": idx,
                    "path": str(audio_path),
                    "duration": duration,
                    "text": full_text,
                    "formatted": formatted_text,
                    "status": "success",
                })

            except Exception as e:
                console.print(f"[red]Error transcribing segment {idx}: {e}[/red]")
                results.append({
                    "index": idx,
                    "path": str(audio_path),
                    "duration": duration,
                    "text": "",
                    "formatted": "",
                    "status": "failed",
                    "error": str(e),
                })

            progress.advance(task)

    return results


def display_segments_table(segments: list[dict], triggers: list[str] = None) -> None:
    """Display transcribed segments in a table."""
    table = Table(title="Segment Transcripts", show_header=True, header_style="bold magenta")
    table.add_column("Seg", style="dim", width=4)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Preview", width=60)

    triggers = triggers or []
    triggers_lower = [t.lower() for t in triggers]

    for seg in segments:
        idx = seg["index"]
        duration = f"{seg['duration']:.1f}s"
        text = seg["text"][:55] + "..." if len(seg["text"]) > 55 else seg["text"]

        # Check for triggers
        has_trigger = any(t in seg["text"].lower() for t in triggers_lower)
        if has_trigger:
            idx_str = f"{idx} ⚡"
            text = f"[yellow]{text}[/yellow]"
        else:
            idx_str = str(idx)

        table.add_row(idx_str, duration, f'"{text}"')

    console.print(table)


def detect_triggers(segments: list[dict], triggers: list[str] = None) -> list[dict]:
    """
    Scan transcripts for trigger phrases that mark segments for auto-deletion.

    Args:
        segments: List of segment dicts with "text" field
        triggers: List of trigger phrases (default: DEFAULT_TRIGGERS)

    Returns:
        The same segments list with added fields:
        - auto_delete: bool - True if trigger phrase found
        - trigger_match: str | None - The matched trigger phrase
    """
    triggers = triggers or DEFAULT_TRIGGERS
    triggers_lower = [t.lower().strip() for t in triggers]

    auto_delete_count = 0
    for seg in segments:
        text_lower = seg.get("text", "").lower()
        seg["auto_delete"] = False
        seg["trigger_match"] = None

        for trigger in triggers_lower:
            if trigger in text_lower:
                seg["auto_delete"] = True
                seg["trigger_match"] = trigger
                auto_delete_count += 1
                break

    if auto_delete_count > 0:
        console.print(f"\n[yellow]⚡ Auto-delete triggered for {auto_delete_count} segment(s)[/yellow]")
        for seg in segments:
            if seg["auto_delete"]:
                console.print(f"  • Segment {seg['index']}: \"{seg['trigger_match']}\"")

    return segments


def select_recording() -> Path | None:
    """Interactive selection of Cap recording."""
    recordings = get_cap_recordings()

    if not recordings:
        console.print("[yellow]No Cap recordings found.[/yellow]")
        console.print(f"[dim]Looking in: {CAP_RECORDINGS_DIR}[/dim]")
        return None

    # Display table
    table = Table(title="Cap Recordings", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Name", width=40)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Segments", justify="right", width=8)

    for i, rec in enumerate(recordings, 1):
        duration_str = f"{rec['duration'] // 60}m {rec['duration'] % 60}s"
        table.add_row(
            str(i),
            rec["pretty_name"][:38],
            duration_str,
            str(rec["segments"])
        )

    console.print(table)

    # Select
    choices = [
        questionary.Choice(
            f"{rec['pretty_name'][:40]} ({rec['segments']} segs)",
            value=rec
        )
        for rec in recordings
    ]

    selected = questionary.select(
        "Select recording:",
        choices=choices,
        style=custom_style
    ).ask()

    if selected:
        return Path(selected["path"])
    return None


def main():
    """Main entry point for kb clean."""
    console.print(Panel("[bold]Cap Recording Cleanup[/bold]", border_style="cyan"))

    # Select recording
    cap_path = select_recording()
    if not cap_path:
        return

    console.print(f"\n[bold]Selected:[/bold] {cap_path.name}\n")

    # Transcribe segments
    segments = transcribe_segments(cap_path)

    if not segments:
        return

    # Detect trigger phrases for auto-deletion
    segments = detect_triggers(segments)

    # Display results with trigger highlighting
    display_segments_table(segments, triggers=DEFAULT_TRIGGERS)


if __name__ == "__main__":
    main()
