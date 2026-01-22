#!/usr/bin/env python3
"""
Knowledge Base Transcription Script

Transcribes audio/video files and saves structured JSON to the knowledge base.

Usage:
    python kb_transcribe.py /path/to/file.mp4
    python kb_transcribe.py --decimal 50.01.01 --title "My Video" /path/to/file.mp4

The script will prompt for metadata using a rich CLI interface.
"""

import sys
import os
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.transcription_service_cpp import get_transcription_service
from app.utils.config_manager import ConfigManager

# Knowledge base paths
KB_ROOT = Path.home() / "Obsidian" / "zen-ai" / "knowledge-base" / "transcripts"
CONFIG_DIR = KB_ROOT / "config"
REGISTRY_PATH = CONFIG_DIR / "registry.json"

SUPPORTED_FORMATS = (
    '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm',
    '.mp4', '.m4v', '.mov', '.aac', '.wma', '.mkv', '.avi'
)

VIDEO_FORMATS = ('.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi')

# Network volume prefixes
NETWORK_VOLUME_PREFIXES = (
    '/Volumes/',      # macOS mounted volumes (except Macintosh HD)
    '/mnt/',          # Linux mount points
    '/media/',        # Linux media mounts
)


def print_status(msg: str):
    """Print status message."""
    print(f"[KB] {msg}", flush=True)


def is_network_path(file_path: str) -> bool:
    """Check if file is on a network/external volume."""
    abs_path = os.path.abspath(file_path)

    if abs_path.startswith('/Volumes/'):
        volume_name = abs_path.split('/')[2] if len(abs_path.split('/')) > 2 else ''
        if volume_name in ('Macintosh HD', 'Macintosh HD - Data'):
            return False
        return True

    for prefix in NETWORK_VOLUME_PREFIXES[1:]:
        if abs_path.startswith(prefix):
            return True

    return False


class LocalFileCopy:
    """Context manager to extract audio from network files for faster processing."""

    def __init__(self, file_path: str):
        self.original_path = file_path
        self.local_path = None
        self.temp_dir = None
        self.needs_extraction = is_network_path(file_path)

    def __enter__(self) -> str:
        if not self.needs_extraction:
            return self.original_path

        ext = os.path.splitext(self.original_path)[1].lower()
        is_video = ext in VIDEO_FORMATS

        self.temp_dir = tempfile.mkdtemp(prefix='kb_whisper_')

        if is_video:
            self.local_path = os.path.join(self.temp_dir, 'audio.wav')
            size_mb = os.path.getsize(self.original_path) / (1024 * 1024)
            print_status(f"Extracting audio from video ({size_mb:.1f} MB)...")

            try:
                result = subprocess.run([
                    'ffmpeg', '-i', self.original_path,
                    '-vn',                    # No video
                    '-acodec', 'pcm_s16le',   # 16-bit PCM
                    '-ar', '16000',           # 16kHz sample rate
                    '-ac', '1',               # Mono
                    '-y',                     # Overwrite
                    self.local_path
                ], capture_output=True, text=True, timeout=900)  # 15 min timeout

                if result.returncode != 0:
                    print_status(f"ffmpeg error, falling back to copy...")
                    return self._copy_whole_file()

                audio_size_mb = os.path.getsize(self.local_path) / (1024 * 1024)
                print_status(f"Audio extracted ({audio_size_mb:.1f} MB)")
                return self.local_path

            except FileNotFoundError:
                print_status("ffmpeg not found, copying file...")
                return self._copy_whole_file()
            except subprocess.TimeoutExpired:
                print_status("Extraction timed out, copying file...")
                return self._copy_whole_file()
        else:
            return self._copy_whole_file()

    def _copy_whole_file(self) -> str:
        """Fallback: copy the entire file."""
        filename = os.path.basename(self.original_path)
        self.local_path = os.path.join(self.temp_dir, filename)

        size_mb = os.path.getsize(self.original_path) / (1024 * 1024)
        print_status(f"Copying from network ({size_mb:.1f} MB)...")

        shutil.copy2(self.original_path, self.local_path)
        print_status("File copied locally")
        return self.local_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
        return False


def load_registry() -> dict:
    """Load the registry.json file."""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, 'r') as f:
            return json.load(f)
    return {"decimals": {}, "tags": [], "transcribed_files": []}


def save_registry(registry: dict):
    """Save the registry.json file."""
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(registry, f, indent=2)


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text


def get_audio_duration(file_path: str) -> int:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', file_path
        ], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return int(float(result.stdout.strip()))
    except Exception:
        pass
    return 0


def transcribe_to_kb(
    file_path: str,
    decimal: str,
    title: str,
    tags: list[str],
    recorded_at: str | None = None,
    speakers: list[str] | None = None,
    model_name: str = "medium"
) -> dict:
    """
    Transcribe a file and save to the knowledge base.

    Returns the saved transcript data.
    """
    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {ext}")

    # Load registry
    registry = load_registry()

    # Validate decimal
    if decimal not in registry["decimals"]:
        raise ValueError(f"Unknown decimal category: {decimal}")

    # Generate ID and filename
    date_str = recorded_at or datetime.now().strftime("%y%m%d")
    if len(date_str) == 10:  # YYYY-MM-DD format
        date_str = datetime.strptime(date_str, "%Y-%m-%d").strftime("%y%m%d")

    slug = slugify(title)
    transcript_id = f"{decimal}-{date_str}-{slug}"
    filename = f"{date_str}-{slug}.json"

    # Destination path
    dest_dir = KB_ROOT / decimal
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    print_status(f"File: {os.path.basename(file_path)}")
    print_status(f"Destination: {dest_path}")

    # Get duration
    duration = get_audio_duration(file_path)
    print_status(f"Duration: {duration}s ({duration // 60}m {duration % 60}s)")

    # Initialize transcription service
    config = ConfigManager()
    service = get_transcription_service(config)

    print_status(f"Loading model: {model_name}...")

    service.set_target_model_config(model_name, "cpu", "int8")
    service.load_model()
    print_status("Model loaded!")

    # Progress callback
    def progress_callback(percent, text, lang_info):
        if percent % 10 == 0:
            print_status(f"Transcribing: {percent}%")

    # Handle network volumes
    print_status("Starting transcription...")
    with LocalFileCopy(file_path) as local_path:
        result = service.transcribe(
            local_path,
            language=config.get("transcription_language", None),
            beam_size=1,
            progress_callback=progress_callback
        )

    transcript_text = result.get("text", "").strip()

    if not transcript_text:
        raise RuntimeError("No transcription result")

    # Build transcript data
    transcript_data = {
        "id": transcript_id,
        "decimal": decimal,
        "title": title,
        "source_files": [os.path.abspath(file_path)],
        "recorded_at": recorded_at or datetime.now().strftime("%Y-%m-%d"),
        "duration_seconds": duration,
        "speakers": speakers or ["Blake Sims"],
        "tags": tags,
        "transcript": transcript_text,
        "analysis": {},
        "created_at": datetime.now().isoformat(),
    }

    # Save transcript
    with open(dest_path, 'w') as f:
        json.dump(transcript_data, f, indent=2, ensure_ascii=False)

    print_status(f"Saved: {dest_path}")

    # Update registry
    abs_path = os.path.abspath(file_path)
    if abs_path not in registry["transcribed_files"]:
        registry["transcribed_files"].append(abs_path)

    for tag in tags:
        if tag not in registry["tags"]:
            registry["tags"].append(tag)

    save_registry(registry)

    return transcript_data


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Transcribe audio/video to knowledge base JSON"
    )
    parser.add_argument("file_path", nargs="?", help="Path to audio/video file")
    parser.add_argument("--decimal", "-d", help="Decimal category (e.g., 50.01.01)")
    parser.add_argument("--title", "-t", help="Title for the transcript")
    parser.add_argument("--tags", nargs="+", help="Tags (space-separated)")
    parser.add_argument("--date", help="Recording date (YYYY-MM-DD)")
    parser.add_argument("--speakers", nargs="+", help="Speaker names")
    parser.add_argument("--model", "-m", default="medium",
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help="Whisper model (default: medium for quality)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode with rich CLI")
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

    if not args.file_path:
        print("Error: file_path is required")
        parser.print_help()
        sys.exit(1)

    # Interactive mode
    if args.interactive:
        try:
            from kb_cli import run_interactive_cli
            result = run_interactive_cli(args.file_path)
            if result is None:
                sys.exit(0)  # User cancelled

            args.decimal = result["decimal"]
            args.title = result["title"]
            args.tags = result["tags"]
            args.date = result["date"]
            # analyses stored for future Phase 6
        except ImportError:
            print("Error: rich library required for interactive mode")
            print("Install with: pip install rich")
            sys.exit(1)

    if not args.decimal:
        print("Error: --decimal is required (or use --interactive)")
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

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
