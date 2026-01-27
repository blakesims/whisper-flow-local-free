#!/usr/bin/env python3
"""
Cap Clean - Clean up Cap recordings by removing junk segments.

Usage:
    kb clean                    # Interactive selection
    kb clean "recording.cap"    # Direct path
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm
import questionary
from questionary import Style

# Reuse from existing cap.py
from kb.sources.cap import get_cap_recordings, CAP_RECORDINGS_DIR

# Reuse from core
from kb.core import format_timestamp, get_audio_duration


def convert_to_wav(input_path: str, output_path: str) -> bool:
    """Convert audio file to WAV format using ffmpeg.

    Args:
        input_path: Path to input audio file (e.g., .ogg)
        output_path: Path for output WAV file

    Returns:
        True if conversion succeeded, False otherwise
    """
    try:
        result = subprocess.run([
            'ffmpeg', '-i', input_path,
            '-acodec', 'pcm_s16le',   # 16-bit PCM
            '-ar', '16000',           # 16kHz sample rate
            '-ac', '1',               # Mono
            '-y',                     # Overwrite
            '-loglevel', 'error',     # Suppress output
            output_path
        ], capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except Exception:
        return False

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

    # Silent progress callback to suppress internal whisper output
    def silent_progress(percent, text, lang_info):
        pass  # Suppress all internal progress output

    # Sequential transcription with progress display
    results = []
    temp_dir = tempfile.mkdtemp(prefix='kb_clean_')

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,  # Clear progress bar on completion
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
                    # Convert .ogg to .wav (whisper.cpp needs WAV format)
                    audio_str = str(audio_path)
                    if audio_str.lower().endswith('.ogg'):
                        wav_path = os.path.join(temp_dir, f"segment-{idx}.wav")
                        if not convert_to_wav(audio_str, wav_path):
                            raise RuntimeError(f"Failed to convert {audio_path} to WAV")
                        transcribe_path = wav_path
                    else:
                        transcribe_path = audio_str

                    result = service.transcribe(
                        transcribe_path,
                        language=config.get("transcription_language", None),
                        beam_size=1,
                        progress_callback=silent_progress  # Suppress internal progress
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

    finally:
        # Clean up temp WAV files
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

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


def analyze_segments_for_cleanup(segments: list[dict]) -> list[dict]:
    """
    Use Gemini LLM to analyze segments for cleanup suggestions.

    Identifies:
    - Dead air (silence, no speech)
    - Filler/stumbles (excessive um, uh, like)
    - Duplicate takes (similar content, recommend which to keep)

    Args:
        segments: List of segment dicts with "text" and "duration" fields

    Returns:
        List of suggestion dicts with:
        - action: "delete" | "duplicate"
        - segment_index: int (for delete)
        - segment_indices: [int, int] (for duplicate)
        - keep_index: int (for duplicate)
        - confidence: float (0.0-1.0)
        - reason: "dead_air" | "filler" | "stumble" | "duplicate" | "incomplete"
        - explanation: str
    """
    from kb.analyze import analyze_transcript

    # Skip segments already marked for auto-delete (trigger phrases)
    segments_to_analyze = [s for s in segments if not s.get("auto_delete", False)]

    if not segments_to_analyze:
        console.print("[dim]All segments already marked for deletion by triggers.[/dim]")
        return []

    # Build context string for LLM
    context_lines = []
    for seg in segments_to_analyze:
        text = seg.get("text", "").strip() or "[silence]"
        context_lines.append(
            f"Segment {seg['index']} ({seg['duration']:.1f}s): \"{text}\""
        )

    context = "\n".join(context_lines)

    console.print("\n[bold]🤖 Analyzing segments with Gemini...[/bold]")

    try:
        result = analyze_transcript(
            transcript_text=context,
            analysis_type="cap_clean",
            title="Cap Recording Cleanup Analysis",
        )

        suggestions = result.get("suggestions", [])

        if suggestions:
            console.print(f"[green]Found {len(suggestions)} suggestion(s)[/green]")
        else:
            console.print("[dim]No cleanup suggestions - recording looks clean![/dim]")

        return suggestions

    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[dim]Install with: pip install google-genai[/dim]")
        return []
    except ValueError as e:
        console.print(f"[red]Analysis error: {e}[/red]")
        return []
    except Exception as e:
        console.print(f"[red]LLM analysis failed: {e}[/red]")
        return []


def is_cap_running() -> bool:
    """Check if Cap app is currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Cap"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def play_audio(audio_path: str, timeout: int = None) -> None:
    """Play audio file using afplay (macOS).

    Args:
        audio_path: Path to audio file
        timeout: Optional timeout in seconds (plays first N seconds)
    """
    try:
        if timeout:
            # Use timeout command to limit playback
            subprocess.run(
                ["timeout", str(timeout), "afplay", audio_path],
                capture_output=True
            )
        else:
            subprocess.run(["afplay", audio_path], capture_output=True)
    except FileNotFoundError:
        console.print("[yellow]afplay not available (macOS only)[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Could not play audio: {e}[/yellow]")


def run_interactive_review(
    segments: list[dict],
    suggestions: list[dict]
) -> set[int]:
    """
    Interactive CLI review of LLM suggestions.

    Args:
        segments: List of segment dicts
        suggestions: LLM suggestions to review

    Returns:
        Set of segment indices to delete
    """
    to_delete = set()

    # First: collect auto-deletes from triggers
    for seg in segments:
        if seg.get("auto_delete"):
            to_delete.add(seg["index"])

    # If no suggestions to review, return early
    if not suggestions:
        return to_delete

    console.print("\n[bold]━━━ Interactive Review ━━━[/bold]\n")

    for i, sug in enumerate(suggestions):
        action = sug.get("action", "delete")
        confidence = sug.get("confidence", 0) * 100
        reason = sug.get("reason", "unknown")
        explanation = sug.get("explanation", "")

        if action == "delete":
            idx = sug.get("segment_index")
            if idx is None:
                continue

            seg = next((s for s in segments if s["index"] == idx), None)
            if not seg:
                continue

            console.print(f"[bold]Segment {idx}[/bold] ({seg['duration']:.1f}s) — DELETE? ({confidence:.0f}%)")
            console.print(Panel(seg["text"][:200] or "[silence]", border_style="dim"))
            console.print(f"[dim]Reason: {explanation}[/dim]\n")

            choice = questionary.select(
                "Action:",
                choices=[
                    questionary.Choice("play audio", "p"),
                    questionary.Choice("delete", "d"),
                    questionary.Choice("keep", "k"),
                ],
                style=custom_style
            ).ask()

            if choice == "p":
                console.print("[dim]Playing...[/dim]")
                play_audio(seg["path"])
                # Ask again after playing
                choice = questionary.select(
                    "After listening:",
                    choices=[
                        questionary.Choice("delete", "d"),
                        questionary.Choice("keep", "k"),
                    ],
                    style=custom_style
                ).ask()

            if choice == "d":
                to_delete.add(idx)
                console.print("[green]✓ Marked for deletion[/green]\n")
            else:
                console.print("[dim]Keeping segment[/dim]\n")

        elif action == "duplicate":
            indices = sug.get("segment_indices", [])
            keep_idx = sug.get("keep_index")

            if len(indices) != 2 or keep_idx is None:
                continue

            delete_idx = indices[0] if indices[1] == keep_idx else indices[1]

            console.print(f"[bold]DUPLICATE TAKES[/bold]: Segments {indices[0]} & {indices[1]}")
            console.print(f"[dim]LLM recommends keeping segment {keep_idx}[/dim]\n")

            for idx in indices:
                seg = next((s for s in segments if s["index"] == idx), None)
                if seg:
                    marker = " [KEEP]" if idx == keep_idx else ""
                    console.print(f"Segment {idx} ({seg['duration']:.1f}s){marker}:")
                    console.print(Panel(seg["text"][:150] or "[silence]", border_style="dim"))

            console.print(f"[dim]{explanation}[/dim]\n")

            choice = questionary.select(
                "Action:",
                choices=[
                    questionary.Choice(f"play segment {indices[0]}", "1"),
                    questionary.Choice(f"play segment {indices[1]}", "2"),
                    questionary.Choice("accept LLM recommendation", "a"),
                    questionary.Choice("swap (keep other)", "s"),
                    questionary.Choice("keep both", "b"),
                ],
                style=custom_style
            ).ask()

            if choice == "1":
                seg = next((s for s in segments if s["index"] == indices[0]), None)
                if seg:
                    console.print("[dim]Playing...[/dim]")
                    play_audio(seg["path"])
            elif choice == "2":
                seg = next((s for s in segments if s["index"] == indices[1]), None)
                if seg:
                    console.print("[dim]Playing...[/dim]")
                    play_audio(seg["path"])

            if choice in ("1", "2"):
                choice = questionary.select(
                    "After listening:",
                    choices=[
                        questionary.Choice("accept LLM recommendation", "a"),
                        questionary.Choice("swap (keep other)", "s"),
                        questionary.Choice("keep both", "b"),
                    ],
                    style=custom_style
                ).ask()

            if choice == "a":
                to_delete.add(delete_idx)
                console.print(f"[green]✓ Deleting segment {delete_idx}, keeping {keep_idx}[/green]\n")
            elif choice == "s":
                to_delete.add(keep_idx)
                console.print(f"[green]✓ Deleting segment {keep_idx}, keeping {delete_idx}[/green]\n")
            else:
                console.print("[dim]Keeping both segments[/dim]\n")

    return to_delete


def soft_delete_segments(cap_path: Path, indices_to_delete: set[int]) -> dict:
    """
    Soft-delete segments by renaming folders and updating metadata.

    Instead of permanently deleting, renames segment folders to
    _deleted_segment-N so they can be recovered if needed.

    Args:
        cap_path: Path to the .cap recording
        indices_to_delete: Set of segment indices to delete

    Returns:
        Audit data dict with deletion details
    """
    segments_dir = cap_path / "content" / "segments"
    meta_path = cap_path / "recording-meta.json"
    config_path = cap_path / "project-config.json"

    # Load current metadata
    with open(meta_path) as f:
        meta = json.load(f)

    original_count = len(meta.get("segments", []))
    indices_to_delete = sorted(indices_to_delete)

    audit_data = {
        "original_segment_count": original_count,
        "deleted_segments": [],
        "kept_segments": [],
        "triggers_used": DEFAULT_TRIGGERS,
    }

    console.print("\n[bold]🗑️  Soft-deleting segments...[/bold]")

    # Step 1: Rename deleted segment folders to _deleted_segment-N
    for idx in indices_to_delete:
        src = segments_dir / f"segment-{idx}"
        dst = segments_dir / f"_deleted_segment-{idx}"
        if src.exists():
            src.rename(dst)
            console.print(f"   segment-{idx} → _deleted_segment-{idx}")

            # Record in audit
            seg_meta = meta["segments"][idx] if idx < len(meta["segments"]) else {}
            audit_data["deleted_segments"].append({
                "original_index": idx,
                "reason": "user_confirmed",  # Could be more specific
            })

    # Step 2: Identify remaining segments and prepare for renumbering
    remaining = []
    for i, seg in enumerate(meta.get("segments", [])):
        if i not in indices_to_delete:
            remaining.append((i, seg))

    console.print("\n[bold]📁 Renumbering remaining segments...[/bold]")

    # Step 3: Renumber folders (process in reverse to avoid conflicts)
    # First pass: rename to temp names to avoid collisions
    temp_mapping = {}
    for new_idx, (old_idx, _) in enumerate(remaining):
        if new_idx != old_idx:
            src = segments_dir / f"segment-{old_idx}"
            tmp = segments_dir / f"_temp_segment-{new_idx}"
            if src.exists():
                src.rename(tmp)
                temp_mapping[new_idx] = tmp

    # Second pass: rename from temp to final
    for new_idx, tmp_path in temp_mapping.items():
        dst = segments_dir / f"segment-{new_idx}"
        if tmp_path.exists():
            tmp_path.rename(dst)
            old_idx = remaining[new_idx][0]
            console.print(f"   segment-{old_idx} → segment-{new_idx}")

    # Step 4: Update metadata with new paths
    console.print("\n[bold]📝 Updating recording-meta.json...[/bold]")

    new_segments = []
    for new_idx, (old_idx, seg) in enumerate(remaining):
        # Update all paths in the segment to reflect new index
        updated_seg = _update_segment_paths(seg, new_idx)
        new_segments.append(updated_seg)

        audit_data["kept_segments"].append({
            "original_index": old_idx,
            "new_index": new_idx,
        })

    meta["segments"] = new_segments

    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    # Step 5: Delete project-config.json (Cap will regenerate)
    if config_path.exists():
        config_path.unlink()
        console.print("[bold]🧹 Removed project-config.json[/bold] (Cap will regenerate)")

    audit_data["remaining_segment_count"] = len(new_segments)

    return audit_data


def _update_segment_paths(seg: dict, new_index: int) -> dict:
    """Update all paths in a segment dict to reflect new index."""
    new_seg = {}
    for key, value in seg.items():
        if isinstance(value, dict) and "path" in value:
            # Handle nested objects with path (display, camera, mic)
            old_path = value["path"]
            # Replace segment-N with segment-{new_index}
            import re
            new_path = re.sub(
                r'segment-\d+',
                f'segment-{new_index}',
                old_path
            )
            new_seg[key] = {**value, "path": new_path}
        elif key == "cursor" and isinstance(value, str):
            # cursor is just a string path
            import re
            new_seg[key] = re.sub(
                r'segment-\d+',
                f'segment-{new_index}',
                value
            )
        else:
            new_seg[key] = value
    return new_seg


def save_audit_log(cap_path: Path, audit_data: dict, segments: list[dict]) -> None:
    """Save cleanup audit log to the recording directory."""
    audit_path = cap_path / "_clean_audit.json"

    # Add transcripts to deleted segments
    for del_info in audit_data.get("deleted_segments", []):
        idx = del_info["original_index"]
        seg = next((s for s in segments if s["index"] == idx), None)
        if seg:
            del_info["duration"] = seg.get("duration", 0)
            del_info["transcript"] = seg.get("text", "")[:500]

    audit_data["cleaned_at"] = datetime.now().isoformat()

    with open(audit_path, 'w') as f:
        json.dump(audit_data, f, indent=2)

    console.print(f"[bold]💾 Saved audit log:[/bold] {audit_path.name}")


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


def main(triggers_only: bool = False, dry_run: bool = False):
    """Main entry point for kb clean.

    Args:
        triggers_only: If True, skip LLM analysis (only use trigger phrases)
        dry_run: If True, show what would be deleted but don't modify files
    """
    console.print(Panel("[bold]Cap Recording Cleanup[/bold]", border_style="cyan"))

    # Check if Cap is running
    if is_cap_running():
        console.print("\n[yellow]⚠️  Cap appears to be running.[/yellow]")
        console.print("[dim]Close Cap before cleaning to avoid file conflicts.[/dim]")
        if not Confirm.ask("\nContinue anyway?", default=False):
            return

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

    # LLM analysis (unless triggers_only)
    suggestions = []
    if not triggers_only:
        if Confirm.ask("\n[bold]Continue to LLM analysis?[/bold]", default=True):
            suggestions = analyze_segments_for_cleanup(segments)

    # Interactive review
    to_delete = run_interactive_review(segments, suggestions)

    # Summary
    if not to_delete:
        console.print("\n[green]No segments to delete. Recording is clean![/green]")
        return

    # Show summary
    console.print("\n[bold]━━━ Summary ━━━[/bold]")
    console.print(f"\nTo DELETE ({len(to_delete)} segments):")
    for idx in sorted(to_delete):
        seg = next((s for s in segments if s["index"] == idx), None)
        if seg:
            reason = "trigger" if seg.get("auto_delete") else "reviewed"
            console.print(f"  • Segment {idx} ({seg['duration']:.1f}s) — {reason}")

    kept = [s["index"] for s in segments if s["index"] not in to_delete]
    console.print(f"\nTo KEEP: {', '.join(map(str, kept))}")
    console.print(f"\nResult: {len(segments)} → {len(kept)} segments")

    if dry_run:
        console.print("\n[yellow]DRY RUN: No changes made.[/yellow]")
        return

    # Confirm and execute
    if not Confirm.ask("\n[bold]Proceed with cleanup?[/bold]", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Execute soft-delete
    audit_data = soft_delete_segments(cap_path, to_delete)

    # Save audit log
    save_audit_log(cap_path, audit_data, segments)

    console.print(f"\n[green]✓ Done! {len(kept)} segments remain.[/green]")
    console.print("[dim]Open in Cap to see the clean timeline.[/dim]")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up Cap recording by removing junk segments"
    )
    parser.add_argument(
        "recording",
        nargs="?",
        help="Path to .cap recording (interactive selection if not provided)"
    )
    parser.add_argument(
        "--triggers-only",
        action="store_true",
        help="Only use trigger phrases, skip LLM analysis"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without making changes"
    )

    args = parser.parse_args()

    # If recording path provided, use it directly instead of interactive selection
    if args.recording:
        cap_path = Path(args.recording)
        if not cap_path.exists():
            console.print(f"[red]Recording not found: {cap_path}[/red]")
            sys.exit(1)

        console.print(Panel("[bold]Cap Recording Cleanup[/bold]", border_style="cyan"))

        # Check if Cap is running
        if is_cap_running():
            console.print("\n[yellow]⚠️  Cap appears to be running.[/yellow]")
            if not Confirm.ask("Continue anyway?", default=False):
                sys.exit(0)

        console.print(f"\n[bold]Recording:[/bold] {cap_path.name}\n")

        # Run the cleanup flow directly
        segments = transcribe_segments(cap_path)
        if segments:
            segments = detect_triggers(segments)
            display_segments_table(segments, triggers=DEFAULT_TRIGGERS)

            suggestions = []
            if not args.triggers_only:
                if Confirm.ask("\n[bold]Continue to LLM analysis?[/bold]", default=True):
                    suggestions = analyze_segments_for_cleanup(segments)

            to_delete = run_interactive_review(segments, suggestions)

            if to_delete:
                console.print("\n[bold]━━━ Summary ━━━[/bold]")
                console.print(f"\nTo DELETE: {sorted(to_delete)}")
                kept = [s["index"] for s in segments if s["index"] not in to_delete]
                console.print(f"To KEEP: {kept}")
                console.print(f"\nResult: {len(segments)} → {len(kept)} segments")

                if args.dry_run:
                    console.print("\n[yellow]DRY RUN: No changes made.[/yellow]")
                elif Confirm.ask("\n[bold]Proceed?[/bold]", default=True):
                    audit_data = soft_delete_segments(cap_path, to_delete)
                    save_audit_log(cap_path, audit_data, segments)
                    console.print(f"\n[green]✓ Done! {len(kept)} segments remain.[/green]")
            else:
                console.print("\n[green]No segments to delete.[/green]")
    else:
        main(triggers_only=args.triggers_only, dry_run=args.dry_run)
