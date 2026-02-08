#!/usr/bin/env python3
"""
Zoom Source - Transcribe Zoom meeting recordings with multiple participants.

Zoom records each participant's audio separately in the "Audio Record" subfolder.
This source transcribes all participant files, merges segments by timestamp,
and produces a unified meeting transcript.

Folder structure:
    ~/Documents/Zoom/
    └── 2024-03-11 21.54.11 Blake Sims's Personal Meeting Room/
        ├── Audio Record/
        │   ├── audioBlakeSims21759316641.m4a
        │   └── audioHonedInTutoring11759316641.m4a
        ├── chat.txt
        └── recording.conf

Speaker name extraction:
    audioBlakeSims21759316641.m4a -> "Blake Sims"
    audioHonedInTutoring11759316641.m4a -> "Honed In Tutoring"

Usage:
    kb transcribe zoom                     # Interactive mode
    kb transcribe zoom --list              # List unprocessed meetings
    kb transcribe zoom "2024-03-11..."     # Specific meeting folder
    kb transcribe zoom --decimal 50.03.01 --title "Alpha S5" "2024-03-11..."
"""

import sys
import os
import re
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import questionary
from questionary import Style

# Add project root to path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kb.core import (
    transcribe_to_kb, load_registry, save_registry, print_status,
    slugify, format_timestamp, KB_ROOT, DEFAULT_WHISPER_MODEL
)
from kb.config import load_config

console = Console()

custom_style = Style([
    ('qmark', 'fg:cyan bold'),
    ('question', 'fg:white bold'),
    ('answer', 'fg:green bold'),
    ('pointer', 'fg:cyan bold'),
    ('highlighted', 'fg:cyan bold'),
    ('selected', 'fg:green'),
])

# Constants
ZOOM_DIR = Path.home() / "Documents" / "Zoom"
AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav'}


def get_ignore_list() -> list[str]:
    """Get list of participant names to ignore from config."""
    config = load_config()
    return config.get("zoom", {}).get("ignore_participants", [])


def should_ignore_participant(speaker_name: str, ignore_list: list[str] | None = None) -> bool:
    """Check if a speaker should be ignored (case-insensitive partial match)."""
    if ignore_list is None:
        ignore_list = get_ignore_list()

    speaker_lower = speaker_name.lower()
    for pattern in ignore_list:
        if pattern.lower() in speaker_lower:
            return True
    return False


def convert_to_wav(audio_file: Path, temp_dir: str) -> str:
    """
    Convert audio file to WAV format for whisper.cpp.

    whisper.cpp only supports WAV (RIFF) format, so we need to convert
    m4a, mp3, and other formats using ffmpeg.

    Args:
        audio_file: Path to source audio file
        temp_dir: Directory to store converted file

    Returns:
        Path to converted WAV file

    Raises:
        RuntimeError: If conversion fails
    """
    output_path = os.path.join(temp_dir, f"{audio_file.stem}.wav")

    try:
        result = subprocess.run([
            'ffmpeg', '-i', str(audio_file),
            '-vn',                    # No video
            '-acodec', 'pcm_s16le',   # 16-bit PCM (required by whisper.cpp)
            '-ar', '16000',           # 16kHz sample rate (optimal for Whisper)
            '-ac', '1',               # Mono
            '-y',                     # Overwrite
            output_path
        ], capture_output=True, text=True, timeout=300)  # 5 min timeout

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {result.stderr}")

        return output_path

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found - please install ffmpeg")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Audio conversion timed out")


def parse_date_from_folder(folder_name: str) -> str:
    """
    Extract date from Zoom folder name.

    Pattern: YYYY-MM-DD HH.MM.SS ...
    Example: "2024-03-11 21.54.11 Blake Sims's Personal Meeting Room" -> "2024-03-11"
    """
    match = re.match(r'^(\d{4}-\d{2}-\d{2})', folder_name)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y-%m-%d")


def extract_speaker_name(filename: str) -> str:
    """
    Extract speaker name from Zoom audio filename.

    Patterns:
        audio{CamelCaseName}{ID}.ext -> "Camel Case Name"
        audio{name.with.dots}{ID}.ext -> "name with dots"
        audio{lowercase}{ID}.ext -> "lowercase"

    Examples:
        audioBlakeSims21759316641.m4a -> "Blake Sims"
        audioHonedInTutoring11759316641.m4a -> "Honed In Tutoring"
        audiothuypham11810213635.m4a -> "thuypham"
        audioFireflies.aiNote31086167729.m4a -> "Fireflies.ai Note"
    """
    # First try: Match audio + name (allowing dots) + digits + extension
    # Pattern: audio{name}{digits}.{ext}
    match = re.match(r'audio([A-Za-z][A-Za-z0-9.]*?)\d{8,}\.\w+', filename)
    if match:
        name = match.group(1)

        # Handle names with dots (e.g., Fireflies.ai) - convert dots to spaces
        if '.' in name:
            name = name.replace('.', ' ')

        # Insert spaces before capitals: BlakeSims -> Blake Sims
        spaced_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)

        # Clean up multiple spaces and strip
        spaced_name = re.sub(r'\s+', ' ', spaced_name).strip()
        return spaced_name

    # Fallback: use filename without extension
    return Path(filename).stem


def discover_meetings(zoom_dir: Path = ZOOM_DIR) -> list[dict]:
    """
    Find all Zoom meeting folders with Audio Record subdirs.

    Returns list of meeting dicts with:
        - path: Full path to meeting folder
        - name: Folder name
        - date: Extracted date (YYYY-MM-DD)
        - participants: List of speaker names (excluding ignored)
        - audio_files: List of audio file paths (excluding ignored)
        - ignored_participants: List of ignored speaker names
    """
    if not zoom_dir.exists():
        return []

    ignore_list = get_ignore_list()
    meetings = []

    for folder in zoom_dir.iterdir():
        if not folder.is_dir():
            continue

        audio_dir = folder / "Audio Record"
        if not audio_dir.exists():
            continue

        # Find audio files starting with 'audio'
        all_audio_files = [
            f for f in audio_dir.iterdir()
            if f.suffix.lower() in AUDIO_EXTENSIONS
            and f.name.lower().startswith('audio')
        ]

        # Filter out ignored participants
        audio_files = []
        participants = []
        ignored_participants = []

        for f in all_audio_files:
            speaker = extract_speaker_name(f.name)
            if should_ignore_participant(speaker, ignore_list):
                ignored_participants.append(speaker)
            else:
                audio_files.append(f)
                participants.append(speaker)

        if audio_files:
            meetings.append({
                "path": folder,
                "name": folder.name,
                "date": parse_date_from_folder(folder.name),
                "participants": participants,
                "audio_files": sorted(audio_files, key=lambda f: f.name),
                "ignored_participants": ignored_participants,
            })

    # Sort by date (most recent first)
    return sorted(meetings, key=lambda m: m["date"], reverse=True)


def get_unprocessed_meetings(zoom_dir: Path = ZOOM_DIR) -> list[dict]:
    """Get meetings not yet in registry."""
    registry = load_registry()
    processed = set(registry.get("transcribed_zoom_meetings", []))

    all_meetings = discover_meetings(zoom_dir)
    return [m for m in all_meetings if str(m["path"]) not in processed]


def transcribe_meeting(meeting: dict, model_name: str = "medium") -> tuple[str, list[str], int]:
    """
    Transcribe all audio files in a meeting and merge by timestamp.

    Args:
        meeting: Meeting dict from discover_meetings()
        model_name: Whisper model to use

    Returns:
        tuple of (transcript_text, speakers, duration_seconds)

    Raises:
        RuntimeError: If no segments could be transcribed
    """
    from app.core.transcription_service_cpp import get_transcription_service
    from app.utils.config_manager import ConfigManager

    config = ConfigManager()
    service = get_transcription_service(config)
    service.set_target_model_config(model_name, "cpu", "int8")

    print_status(f"Loading model: {model_name}...")
    service.load_model()

    all_segments = []
    speakers = []
    max_duration = 0
    successful_files = 0

    # Create temp directory for WAV conversions
    temp_dir = tempfile.mkdtemp(prefix='kb_zoom_')

    try:
        for audio_file in meeting["audio_files"]:
            speaker = extract_speaker_name(audio_file.name)
            if speaker not in speakers:
                speakers.append(speaker)

            print_status(f"Transcribing {speaker}...")
            try:
                # Convert to WAV if not already WAV
                # whisper.cpp only supports WAV (RIFF) format
                if audio_file.suffix.lower() != '.wav':
                    print_status(f"  Converting {audio_file.suffix} to WAV...")
                    wav_path = convert_to_wav(audio_file, temp_dir)
                else:
                    wav_path = str(audio_file)

                result = service.transcribe(wav_path)

                # Extract segments with timestamps
                # pywhispercpp returns Segment objects with t0/t1 (centiseconds) and text
                for seg in result.get("segments", []):
                    start = seg.t0 / 100.0  # centiseconds to seconds
                    end = seg.t1 / 100.0
                    text = seg.text.strip()

                    if text:  # Skip empty segments
                        all_segments.append({
                            "speaker": speaker,
                            "start": start,
                            "end": end,
                            "text": text,
                        })
                        max_duration = max(max_duration, end)

                successful_files += 1
                print_status(f"  {speaker}: {len([s for s in all_segments if s['speaker'] == speaker])} segments")

            except Exception as e:
                console.print(f"[yellow]Warning: Failed to transcribe {speaker}: {e}[/yellow]")
                continue

    finally:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    if not all_segments:
        raise RuntimeError("No segments transcribed from any participant")

    print_status(f"Transcribed {successful_files}/{len(meeting['audio_files'])} files, {len(all_segments)} total segments")

    # Sort by start timestamp
    all_segments.sort(key=lambda s: s["start"])

    # Format transcript with timestamps
    # Use MM:SS for < 1 hour, HH:MM:SS for >= 1 hour
    lines = []
    for seg in all_segments:
        ts = format_timestamp(seg["start"])
        lines.append(f"[{ts}] {seg['speaker']}: {seg['text']}")

    transcript_text = "\n".join(lines)
    return transcript_text, speakers, int(max_duration)


def select_meeting(meetings: list[dict]) -> dict | None:
    """Interactive meeting selection."""
    if not meetings:
        console.print("[yellow]No unprocessed Zoom meetings found.[/yellow]")
        return None

    console.print("\n[bold cyan]Select meeting:[/bold cyan]")
    console.print("[dim]up/down/jk to move, Enter to select[/dim]\n")

    choices = []
    for m in meetings:
        participant_str = ", ".join(m["participants"][:3])
        if len(m["participants"]) > 3:
            participant_str += f" (+{len(m['participants']) - 3} more)"

        label = f"{m['date']} - {participant_str}"
        choices.append(questionary.Choice(title=label, value=m))

    selected = questionary.select(
        "Meeting:",
        choices=choices,
        style=custom_style,
        instruction="(up/down to move, Enter to select)"
    ).ask()

    return selected


def run_interactive():
    """Interactive Zoom meeting transcription flow with preset support."""
    from kb.cli import (
        select_preset, confirm_preset,
        select_decimal, select_tags, get_title, select_analysis_types
    )

    console.print(Panel("[bold]Zoom Meeting Transcription[/bold]", border_style="cyan"))

    # Check Zoom directory exists
    if not ZOOM_DIR.exists():
        console.print(f"[red]Zoom directory not found: {ZOOM_DIR}[/red]")
        return

    # Get unprocessed meetings
    meetings = get_unprocessed_meetings()

    if not meetings:
        console.print("[yellow]No unprocessed Zoom meetings found.[/yellow]")
        console.print(f"[dim]Looking in: {ZOOM_DIR}[/dim]")
        return

    # Select meeting
    meeting = select_meeting(meetings)
    if meeting is None:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Show meeting details
    console.print(f"\n[bold]Selected meeting:[/bold]")
    console.print(f"  Date: {meeting['date']}")
    console.print(f"  Participants: {', '.join(meeting['participants'])}")
    console.print(f"  Files: {len(meeting['audio_files'])}")
    if meeting.get('ignored_participants'):
        console.print(f"  [dim]Ignored: {', '.join(meeting['ignored_participants'])}[/dim]")

    # Try preset flow first
    preset_result = select_preset(
        source_type="zoom",
        participants=meeting["participants"],
        date=meeting["date"],
    )

    if preset_result:
        # Quick preset flow - just confirm title
        confirmed = confirm_preset(preset_result, meeting["participants"])
        if confirmed is None:
            console.print("[yellow]Cancelled.[/yellow]")
            return

        decimal = confirmed["decimal"]
        title = confirmed["title"]
        tags = confirmed["tags"]
        analyses = confirmed["analyses"]
    else:
        # Full custom flow
        registry = load_registry()

        decimal = select_decimal(registry)
        if decimal is None:
            return

        # Generate default title from participants
        if len(meeting["participants"]) == 1:
            default_title = f"Meeting with {meeting['participants'][0]}"
        elif len(meeting["participants"]) == 2:
            default_title = f"Meeting - {meeting['participants'][0]} & {meeting['participants'][1]}"
        else:
            default_title = f"Meeting - {meeting['participants'][0]} et al"

        title = get_title(default_title)
        if not title:
            return

        tags = select_tags(registry)

        # Select analysis types
        analyses = select_analysis_types(registry, decimal)

        # Confirm
        console.print(f"\n[bold]Will transcribe:[/bold]")
        console.print(f"  Meeting: {meeting['date']}")
        console.print(f"  Participants: {', '.join(meeting['participants'])}")
        console.print(f"  Decimal: {decimal}")
        console.print(f"  Title: {title}")
        console.print(f"  Tags: {tags}")
        console.print(f"  Analyses: {analyses}")

        if not questionary.confirm("Proceed?", default=True, style=custom_style).ask():
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Transcribe
    try:
        transcript_text, speakers, duration = transcribe_meeting(meeting, DEFAULT_WHISPER_MODEL)

        # Save to KB using transcribe_to_kb with transcript_text parameter
        result = transcribe_to_kb(
            file_path=str(meeting["audio_files"][0]),  # Use first file as reference
            decimal=decimal,
            title=title,
            tags=tags,
            recorded_at=meeting["date"],
            speakers=speakers,
            source_type="meeting",
            transcript_text=transcript_text,
        )

        # Update registry with processed meeting
        registry = load_registry()
        if "transcribed_zoom_meetings" not in registry:
            registry["transcribed_zoom_meetings"] = []
        registry["transcribed_zoom_meetings"].append(str(meeting["path"]))
        save_registry(registry)

        print_status("Transcription complete!")
        print_status(f"ID: {result['id']}")
        print_status(f"Speakers: {', '.join(speakers)}")
        print_status(f"Duration: {duration // 60}m {duration % 60}s")
        print_status(f"Words: {len(transcript_text.split())}")

        # Run analysis if requested
        if analyses:
            _run_analysis(result, decimal, title, analyses)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


def _run_analysis(result: dict, decimal: str, title: str, analysis_types: list[str]):
    """Run analysis on completed transcript."""
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


def list_meetings(zoom_dir: Path = ZOOM_DIR, unprocessed_only: bool = True):
    """Print a table of Zoom meetings."""
    if unprocessed_only:
        meetings = get_unprocessed_meetings(zoom_dir)
        title = "Unprocessed Zoom Meetings"
    else:
        meetings = discover_meetings(zoom_dir)
        title = "All Zoom Meetings"

    if not meetings:
        console.print(f"[yellow]No {'unprocessed ' if unprocessed_only else ''}meetings found.[/yellow]")
        console.print(f"[dim]Looking in: {zoom_dir}[/dim]")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Date", style="cyan")
    table.add_column("Participants")
    table.add_column("Files", justify="right")
    table.add_column("Ignored", style="dim", justify="right")
    table.add_column("Folder Name", style="dim")

    for m in meetings:
        participants = ", ".join(m["participants"][:2])
        if len(m["participants"]) > 2:
            participants += f" (+{len(m['participants']) - 2})"

        ignored_count = len(m.get("ignored_participants", []))
        ignored_str = str(ignored_count) if ignored_count > 0 else ""

        table.add_row(
            m["date"],
            participants,
            str(len(m["audio_files"])),
            ignored_str,
            m["name"][:50] + "..." if len(m["name"]) > 50 else m["name"]
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(meetings)} meeting(s)[/dim]")

    # Show ignore list info
    ignore_list = get_ignore_list()
    if ignore_list:
        console.print(f"[dim]Ignoring: {', '.join(ignore_list)}[/dim]")


def find_meeting_by_name(folder_name: str, zoom_dir: Path = ZOOM_DIR) -> dict | None:
    """Find a meeting by partial folder name match."""
    meetings = discover_meetings(zoom_dir)

    # Try exact match first
    for m in meetings:
        if m["name"] == folder_name:
            return m

    # Try partial match
    for m in meetings:
        if folder_name in m["name"]:
            return m

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe Zoom meeting recordings to knowledge base"
    )
    parser.add_argument("folder_name", nargs="?", help="Zoom meeting folder name (or partial match)")
    parser.add_argument("--decimal", "-d", help="Decimal category (e.g., 50.03.01)")
    parser.add_argument("--title", "-t", help="Title for the transcript")
    parser.add_argument("--tags", nargs="+", help="Tags (space-separated)")
    parser.add_argument("--analyze", "-a", nargs="*", metavar="TYPE",
                        help="Run LLM analysis after transcription")
    parser.add_argument("--list", action="store_true", help="List unprocessed meetings")
    parser.add_argument("--list-all", action="store_true", help="List all meetings (including processed)")
    parser.add_argument("--zoom-dir", help="Custom Zoom recordings directory")
    parser.add_argument("--model", "-m", default=DEFAULT_WHISPER_MODEL,
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help=f"Whisper model (default: {DEFAULT_WHISPER_MODEL})")

    args = parser.parse_args()

    # Set custom Zoom directory if provided
    zoom_dir = Path(args.zoom_dir) if args.zoom_dir else ZOOM_DIR

    # List mode
    if args.list:
        list_meetings(zoom_dir, unprocessed_only=True)
        return

    if args.list_all:
        list_meetings(zoom_dir, unprocessed_only=False)
        return

    # If no folder name, run interactive
    if not args.folder_name:
        run_interactive()
        return

    # Non-interactive mode
    meeting = find_meeting_by_name(args.folder_name, zoom_dir)
    if not meeting:
        console.print(f"[red]Meeting not found: {args.folder_name}[/red]")
        console.print("[dim]Use --list to see available meetings[/dim]")
        sys.exit(1)

    if not args.decimal:
        console.print("[red]Error: --decimal is required for non-interactive mode[/red]")
        console.print("[dim]Or run without arguments for interactive mode[/dim]")
        sys.exit(1)

    # Validate decimal
    registry = load_registry()
    if args.decimal not in registry.get("decimals", {}):
        console.print(f"[red]Unknown decimal: {args.decimal}[/red]")
        console.print("\nAvailable decimals:")
        for dec, info in registry.get("decimals", {}).items():
            console.print(f"  {dec}: {info.get('name', '')}")
        sys.exit(1)

    # Generate default title if not provided
    if not args.title:
        if len(meeting["participants"]) == 1:
            args.title = f"Meeting with {meeting['participants'][0]}"
        elif len(meeting["participants"]) == 2:
            args.title = f"Meeting - {meeting['participants'][0]} & {meeting['participants'][1]}"
        else:
            args.title = f"Meeting - {meeting['participants'][0]} et al"
        print_status(f"Using default title: {args.title}")

    tags = args.tags or []

    # Transcribe
    try:
        console.print(f"\n[bold]Transcribing meeting:[/bold]")
        console.print(f"  Date: {meeting['date']}")
        console.print(f"  Participants: {', '.join(meeting['participants'])}")
        if meeting.get('ignored_participants'):
            console.print(f"  [dim]Ignored: {', '.join(meeting['ignored_participants'])}[/dim]")
        console.print(f"  Model: {args.model}")

        transcript_text, speakers, duration = transcribe_meeting(meeting, args.model)

        # Save to KB
        result = transcribe_to_kb(
            file_path=str(meeting["audio_files"][0]),
            decimal=args.decimal,
            title=args.title,
            tags=tags,
            recorded_at=meeting["date"],
            speakers=speakers,
            source_type="meeting",
            transcript_text=transcript_text,
        )

        # Update registry
        registry = load_registry()
        if "transcribed_zoom_meetings" not in registry:
            registry["transcribed_zoom_meetings"] = []
        registry["transcribed_zoom_meetings"].append(str(meeting["path"]))
        save_registry(registry)

        print_status("Transcription complete!")
        print_status(f"ID: {result['id']}")
        print_status(f"Speakers: {', '.join(speakers)}")
        print_status(f"Duration: {duration // 60}m {duration % 60}s")

        # Run analysis if requested
        if args.analyze is not None:
            analysis_types = args.analyze if args.analyze else ["summary"]
            _run_analysis(result, args.decimal, args.title, analysis_types)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
