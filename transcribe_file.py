#!/usr/bin/env python3
"""
Transcribe a single audio/video file using whisper.cpp

Usage: python transcribe_file.py /path/to/audio.mp3

Outputs progress to stderr, final transcription to stdout.
Also copies result to clipboard.

Features:
- 24-hour cache to avoid re-transcribing the same file
- Transcripts saved to ~/.cache/whisper-transcripts/
"""

import sys
import os
import json
import hashlib
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.transcription_service_cpp import get_transcription_service
from app.core.post_processor import get_post_processor
from app.utils.config_manager import ConfigManager

import pyperclip

SUPPORTED_FORMATS = (
    '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm',
    '.mp4', '.m4v', '.mov', '.aac', '.wma'
)

# Cache settings
CACHE_DIR = Path.home() / ".cache" / "whisper-transcripts"
CACHE_EXPIRY_HOURS = 24


def print_progress(msg: str):
    """Print progress to stderr (visible in Raycast)"""
    print(msg, file=sys.stderr, flush=True)


def get_cache_key(file_path: str) -> str:
    """Generate a cache key based on file path and modification time."""
    abs_path = os.path.abspath(file_path)
    mtime = os.path.getmtime(file_path)
    size = os.path.getsize(file_path)
    # Hash of path + mtime + size ensures cache invalidates if file changes
    key_str = f"{abs_path}|{mtime}|{size}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def get_cache_path(cache_key: str) -> Path:
    """Get the cache file path for a given key."""
    return CACHE_DIR / f"{cache_key}.json"


def load_from_cache(file_path: str) -> tuple[str | None, Path | None]:
    """
    Try to load transcript from cache.
    Returns (transcript, cache_path) if found and valid, (None, None) otherwise.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_key = get_cache_key(file_path)
    cache_path = get_cache_path(cache_key)

    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)

            # Check if cache is expired
            cached_time = data.get('timestamp', 0)
            age_hours = (time.time() - cached_time) / 3600

            if age_hours < CACHE_EXPIRY_HOURS:
                print_progress(f"Found cached transcript ({age_hours:.1f}h old)")
                return data.get('transcript'), cache_path
            else:
                print_progress(f"Cache expired ({age_hours:.1f}h old)")
        except (json.JSONDecodeError, KeyError):
            pass

    return None, cache_path


def save_to_cache(file_path: str, transcript: str) -> Path:
    """Save transcript to cache. Returns the cache file path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_key = get_cache_key(file_path)
    cache_path = get_cache_path(cache_key)

    data = {
        'file_path': os.path.abspath(file_path),
        'file_name': os.path.basename(file_path),
        'timestamp': time.time(),
        'transcript': transcript,
    }

    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2)

    print_progress(f"Saved to cache: {cache_path}")
    return cache_path


def transcribe_file(file_path: str, force: bool = False) -> str:
    """Transcribe an audio/video file and return the text."""

    # Validate file exists
    if not os.path.isfile(file_path):
        print_progress(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Check extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        print_progress(f"Error: Unsupported format: {ext}")
        print_progress(f"Supported: {', '.join(SUPPORTED_FORMATS)}")
        sys.exit(1)

    # Get file size for info
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print_progress(f"File: {os.path.basename(file_path)} ({size_mb:.1f} MB)")

    # Check cache first (unless force re-transcribe)
    if not force:
        cached_text, cache_path = load_from_cache(file_path)
        if cached_text:
            print_progress("Using cached transcript")
            return cached_text

    # Initialize services
    config = ConfigManager()
    service = get_transcription_service(config)
    post_processor = get_post_processor(config)

    # Get model name
    model_name = config.get("transcription_model_name", "base")
    print_progress(f"Loading model: {model_name}...")

    # Load model
    service.set_target_model_config(model_name, "cpu", "int8")
    service.load_model()
    print_progress("Model loaded!")

    # Progress callback
    last_percent = [0]
    def progress_callback(percent, text, lang_info):
        if percent > last_percent[0]:
            last_percent[0] = percent
            print_progress(f"Transcribing: {percent}%")

    # Transcribe
    print_progress("Transcribing...")
    result = service.transcribe(
        file_path,
        language=config.get("transcription_language", None),
        beam_size=1,
        progress_callback=progress_callback
    )

    text = result.get("text", "").strip()

    # Apply post-processing if enabled
    if post_processor.enabled and text:
        print_progress("Cleaning up text...")
        text = post_processor.process(text)

    # Save to cache
    if text:
        save_to_cache(file_path, text)

    return text


def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_file.py [--force] <audio_file_path>", file=sys.stderr)
        print("\nOptions:", file=sys.stderr)
        print("  --force    Bypass cache and re-transcribe", file=sys.stderr)
        print("\nSupported formats:", ", ".join(SUPPORTED_FORMATS), file=sys.stderr)
        print(f"\nCache location: {CACHE_DIR}", file=sys.stderr)
        sys.exit(1)

    # Parse arguments
    force = False
    file_path = None

    for arg in sys.argv[1:]:
        if arg == '--force':
            force = True
        else:
            file_path = arg

    if not file_path:
        print("Error: No file path provided", file=sys.stderr)
        sys.exit(1)

    # Handle paths with spaces or quotes
    file_path = file_path.strip().strip('"').strip("'")

    # Expand ~ to home directory
    file_path = os.path.expanduser(file_path)

    # Transcribe
    text = transcribe_file(file_path, force=force)

    if text:
        # Copy to clipboard
        try:
            pyperclip.copy(text)
            print_progress("Copied to clipboard!")
        except Exception as e:
            print_progress(f"Clipboard error: {e}")

        # Output final text to stdout
        print(text)
        print_progress("Done!")
    else:
        print_progress("No transcription result")
        sys.exit(1)


if __name__ == "__main__":
    main()
