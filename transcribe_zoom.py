#!/usr/bin/env python3
"""
Transcribe a Zoom meeting folder (with separate per-speaker audio files)
and copy the merged transcript to clipboard.

Does NOT save to knowledge base - just transcribes and copies.

Usage:
    python transcribe_zoom.py                          # Latest Zoom meeting
    python transcribe_zoom.py "2026-03-03 10.31.13"    # Partial folder name match
    python transcribe_zoom.py --list                   # List recent meetings
"""

import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pyperclip

from kb.sources.zoom import (
    discover_meetings, find_meeting_by_name, extract_speaker_name,
    transcribe_meeting, ZOOM_DIR
)


def main():
    parser = argparse.ArgumentParser(description="Transcribe Zoom meeting to clipboard")
    parser.add_argument("folder_name", nargs="?", help="Zoom folder name (partial match). Omit for latest.")
    parser.add_argument("--list", action="store_true", help="List recent meetings")
    parser.add_argument("--model", "-m", default="medium",
                        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                        help="Whisper model (default: medium)")
    args = parser.parse_args()

    if args.list:
        meetings = discover_meetings()
        if not meetings:
            print("No Zoom meetings found.")
            return
        for m in meetings[:10]:
            speakers = ", ".join(m["participants"])
            print(f"  {m['date']}  {speakers}  ({len(m['audio_files'])} files)")
        return

    # Find meeting
    if args.folder_name:
        meeting = find_meeting_by_name(args.folder_name)
        if not meeting:
            print(f"Meeting not found: {args.folder_name}", file=sys.stderr)
            sys.exit(1)
    else:
        # Use most recent meeting
        meetings = discover_meetings()
        if not meetings:
            print("No Zoom meetings found.", file=sys.stderr)
            sys.exit(1)
        meeting = meetings[0]

    # Show what we're transcribing
    speakers = ", ".join(meeting["participants"])
    print(f"Meeting: {meeting['date']}", file=sys.stderr)
    print(f"Speakers: {speakers}", file=sys.stderr)
    print(f"Files: {len(meeting['audio_files'])}", file=sys.stderr)
    print(f"Model: {args.model}", file=sys.stderr)
    print("---", file=sys.stderr)

    # Transcribe
    transcript_text, speaker_list, duration = transcribe_meeting(meeting, args.model)

    # Copy to clipboard
    try:
        pyperclip.copy(transcript_text)
        print("Copied to clipboard!", file=sys.stderr)
    except Exception as e:
        print(f"Clipboard error: {e}", file=sys.stderr)

    # Print transcript to stdout
    print(transcript_text)

    # Summary
    mins, secs = divmod(duration, 60)
    print(f"---", file=sys.stderr)
    print(f"Duration: {mins}m {secs}s | Speakers: {', '.join(speaker_list)} | Words: {len(transcript_text.split())}", file=sys.stderr)


if __name__ == "__main__":
    main()
