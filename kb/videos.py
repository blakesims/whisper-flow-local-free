#!/usr/bin/env python3
"""
KB Videos - Video inventory management and transcript matching.

This module handles:
- Scanning configured video source directories
- Smart matching videos to existing transcripts via partial transcription
- Video file reorganization to mirror decimal structure
- Inventory persistence

Usage:
    kb scan-videos              # Full scan with smart matching
    kb scan-videos --quick      # Quick scan (no matching, just inventory)
    kb scan-videos --reorganize # Scan + move files to decimal structure
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# Add parent to path for app imports (module level per pattern)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from core to maintain patterns
from kb.core import (
    KB_ROOT,
    VIDEO_FORMATS,
    get_audio_duration,
    print_status,
    load_registry,
)
from kb.__main__ import load_config, expand_path

console = Console()

# Inventory file location
INVENTORY_PATH = Path.home() / ".kb" / "video-inventory.json"

# Match confidence threshold
MATCH_THRESHOLD = 0.7

# Sample duration for smart matching (seconds)
SAMPLE_DURATION = 60


def generate_video_id(path: str) -> str:
    """
    Generate stable video ID from path hash.

    IMPORTANT: Always pass the ORIGINAL path, not current_path.
    This ensures IDs remain stable after files are reorganized.
    """
    # Use MD5 of the path for a short, stable ID
    return hashlib.md5(path.encode()).hexdigest()[:12]


def extract_video_metadata(path: str) -> dict:
    """Extract metadata from a video file."""
    stat = os.stat(path)
    return {
        "filename": os.path.basename(path),
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "duration_seconds": get_audio_duration(path),
    }


def scan_video_sources(config: dict, existing_inventory: dict | None = None) -> list[dict]:
    """
    Scan all configured video source directories.

    Args:
        config: KB config dict
        existing_inventory: Existing inventory to preserve original_path for ID stability

    Returns list of video dicts with metadata.
    """
    video_sources = list(config.get("video_sources", []))
    videos = []

    # CRITICAL: Also scan video_target to find reorganized files
    # Without this, files moved during reorganization would be marked as missing
    video_target = config.get("video_target")
    if video_target:
        target_path = expand_path(video_target)
        if target_path.exists():
            video_sources.append({
                "path": str(target_path),
                "label": "Reorganized"
            })

    # Build lookup of existing videos by current_path for ID preservation
    existing_by_path = {}
    if existing_inventory:
        for video in existing_inventory.get("videos", {}).values():
            if video.get("current_path"):
                existing_by_path[video["current_path"]] = video

    for source in video_sources:
        source_path = expand_path(source["path"])
        source_label = source.get("label", source_path.name)

        if not source_path.exists():
            console.print(f"[yellow]Warning: Source not found: {source_path}[/yellow]")
            continue

        # Find all video files recursively
        for ext in VIDEO_FORMATS:
            for video_path in source_path.rglob(f"*{ext}"):
                path_str = str(video_path)

                # CRITICAL: Preserve original_path for ID stability
                # If this file exists in inventory, use its original_path for ID
                existing = existing_by_path.get(path_str)
                if existing and existing.get("original_path"):
                    original_path = existing["original_path"]
                    video_id = generate_video_id(original_path)
                else:
                    # New file: current path becomes original path
                    original_path = path_str
                    video_id = generate_video_id(path_str)

                try:
                    metadata = extract_video_metadata(path_str)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not read {video_path}: {e}[/yellow]")
                    continue

                videos.append({
                    "id": video_id,
                    "original_path": original_path,
                    "current_path": path_str,
                    "source_label": source_label,
                    **metadata,
                })

    return videos


def transcribe_sample(video_path: str, duration: int = SAMPLE_DURATION) -> Optional[str]:
    """
    Transcribe first N seconds of a video for matching.

    Uses ffmpeg to extract audio sample, then whisper to transcribe.
    Returns transcript text or None on failure.
    """
    try:
        from app.core.transcription_service_cpp import get_transcription_service
        from app.utils.config_manager import ConfigManager
    except ImportError as e:
        console.print(f"[yellow]Warning: Could not import transcription service: {e}[/yellow]")
        return None

    temp_dir = None
    try:
        # Extract audio sample
        temp_dir = tempfile.mkdtemp(prefix='kb_sample_')
        sample_path = os.path.join(temp_dir, 'sample.wav')

        # Extract first N seconds of audio
        result = subprocess.run([
            'ffmpeg', '-i', video_path,
            '-t', str(duration),  # Duration limit
            '-vn',                # No video
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            '-y',
            sample_path
        ], capture_output=True, text=True, timeout=60)

        if result.returncode != 0 or not os.path.exists(sample_path):
            return None

        # Transcribe sample with tiny model for speed
        config = ConfigManager()
        service = get_transcription_service(config)
        service.set_target_model_config("tiny", "cpu", "int8")
        service.load_model()

        result = service.transcribe(
            sample_path,
            language=None,
            beam_size=1,
            progress_callback=lambda *args: None  # Silent
        )

        return result.get("text", "").strip()

    except Exception as e:
        console.print(f"[dim]Sample transcription failed for {os.path.basename(video_path)}: {e}[/dim]")
        return None
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def load_all_transcripts() -> list[dict]:
    """Load all transcript metadata from KB for matching."""
    transcripts = []

    for decimal_dir in KB_ROOT.iterdir():
        if not decimal_dir.is_dir():
            continue
        if decimal_dir.name in ("config", "examples"):
            continue

        for json_file in decimal_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)

                transcripts.append({
                    "id": data.get("id", json_file.stem),
                    "title": data.get("title", ""),
                    "decimal": data.get("decimal", ""),
                    "transcript": data.get("transcript", ""),
                    "source_files": data.get("source_files", []),
                    "file_path": str(json_file),
                })
            except Exception:
                continue

    return transcripts


def text_similarity(text1: str, text2: str, max_chars: int = 500) -> float:
    """Calculate similarity between two texts (first N chars)."""
    if not text1 or not text2:
        return 0.0

    # Normalize: lowercase, strip extra whitespace
    t1 = ' '.join(text1.lower().split())[:max_chars]
    t2 = ' '.join(text2.lower().split())[:max_chars]

    return SequenceMatcher(None, t1, t2).ratio()


def find_matching_transcript(
    sample_text: str,
    transcripts: list[dict],
    threshold: float = MATCH_THRESHOLD
) -> Optional[tuple[dict, float]]:
    """
    Find best matching transcript for a video sample.

    Returns (transcript, confidence) or None if no match above threshold.
    """
    best_match = None
    best_score = 0.0

    for transcript in transcripts:
        # Compare sample against start of transcript
        transcript_text = transcript.get("transcript", "")
        if not transcript_text:
            continue

        score = text_similarity(sample_text, transcript_text)

        if score > best_score:
            best_score = score
            best_match = transcript

    if best_match and best_score >= threshold:
        return (best_match, best_score)

    return None


def path_similarity(path1: str, path2: str) -> float:
    """
    Calculate similarity between two paths based on common path components.

    Returns a score from 0.0 to 1.0 based on how many path components match.
    """
    parts1 = Path(path1).parts
    parts2 = Path(path2).parts

    if not parts1 or not parts2:
        return 0.0

    # Count matching components (from end, as filenames are most significant)
    matches = 0
    for p1, p2 in zip(reversed(parts1), reversed(parts2)):
        if p1 == p2:
            matches += 1
        else:
            break

    # Score based on proportion of shorter path that matches
    min_len = min(len(parts1), len(parts2))
    return matches / min_len if min_len > 0 else 0.0


def check_source_path_match(
    video_path: str,
    transcripts: list[dict],
    linked_transcript_ids: set[str] | None = None
) -> Optional[dict]:
    """
    Check if video path matches a transcript's source_files.

    Matching priority:
    1. Exact path match (highest confidence)
    2. Filename + path similarity > 0.5 (handles reorganized files)

    Args:
        video_path: Path to the video file
        transcripts: List of transcript dicts
        linked_transcript_ids: Set of transcript IDs already linked (to avoid duplicates)

    Returns:
        Matching transcript dict or None
    """
    video_path_abs = os.path.abspath(video_path)
    video_filename = os.path.basename(video_path)
    linked_ids = linked_transcript_ids or set()

    best_match = None
    best_similarity = 0.0

    for transcript in transcripts:
        # Skip already-linked transcripts to avoid duplicates
        if transcript["id"] in linked_ids:
            continue

        source_files = transcript.get("source_files", [])
        for source in source_files:
            # Priority 1: Direct path match
            if os.path.abspath(source) == video_path_abs:
                return transcript

            # Priority 2: Filename match with path similarity check
            if os.path.basename(source) == video_filename:
                similarity = path_similarity(source, video_path)
                # Require at least 50% path similarity (not just filename)
                # This prevents matching "dir1/session.mp4" to "dir2/session.mp4"
                if similarity > 0.5 and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = transcript

    return best_match


def load_inventory() -> dict:
    """Load video inventory from disk."""
    if INVENTORY_PATH.exists():
        try:
            with open(INVENTORY_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"videos": {}, "last_scan": None}


def save_inventory(inventory: dict):
    """Save video inventory to disk."""
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVENTORY_PATH, 'w') as f:
        json.dump(inventory, f, indent=2)


def scan_videos(
    quick: bool = False,
    reorganize: bool = False,
    yes: bool = False,
    cron: bool = False
) -> dict:
    """
    Main scan function.

    Args:
        quick: Skip smart matching, just inventory files
        reorganize: Move files to decimal structure after matching
        yes: Skip confirmation prompts
        cron: Silent mode for cron jobs

    Returns:
        Summary dict with counts
    """
    config = load_config()

    if not cron:
        console.print("\n[bold cyan]Scanning video sources...[/bold cyan]\n")

    # Load existing inventory FIRST for ID stability
    inventory = load_inventory()
    existing_videos = inventory.get("videos", {})

    # Scan all sources (pass inventory for ID stability)
    videos = scan_video_sources(config, existing_inventory=inventory)

    if not videos:
        if not cron:
            console.print("[yellow]No videos found in configured sources.[/yellow]")
        return {"found": 0, "linked": 0, "unlinked": 0, "missing": 0}

    if not cron:
        console.print(f"Found [bold]{len(videos)}[/bold] videos\n")

    # Load transcripts for matching
    transcripts = load_all_transcripts()

    linked = 0
    unlinked = 0

    # Track which transcript IDs are already linked (to avoid duplicates)
    linked_transcript_ids: set[str] = set()

    # Process each video
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        disable=cron
    ) as progress:
        task = progress.add_task("Matching videos...", total=len(videos))

        for video in videos:
            video_id = video["id"]

            # Check if already in inventory with a link
            if video_id in existing_videos:
                existing = existing_videos[video_id]
                if existing.get("status") == "linked" and existing.get("transcript_id"):
                    # Keep existing link
                    video["status"] = "linked"
                    video["transcript_id"] = existing["transcript_id"]
                    video["match_confidence"] = existing.get("match_confidence", 1.0)
                    video["linked_at"] = existing.get("linked_at")
                    linked_transcript_ids.add(existing["transcript_id"])
                    linked += 1
                    progress.advance(task)
                    continue

            # Try direct path match first (pass linked IDs to avoid duplicates)
            path_match = check_source_path_match(
                video["current_path"], transcripts, linked_transcript_ids
            )
            if path_match:
                video["status"] = "linked"
                video["transcript_id"] = path_match["id"]
                video["match_confidence"] = 1.0
                video["linked_at"] = datetime.now().isoformat()
                linked_transcript_ids.add(path_match["id"])
                linked += 1
                progress.advance(task)
                continue

            # Smart matching via partial transcription (unless quick mode)
            if not quick:
                # Check for cached sample_text from previous scan
                existing = existing_videos.get(video_id, {})
                cached_sample = existing.get("sample_text")
                cached_mtime = existing.get("scanned_mtime")

                # Use cache if sample exists and mtime hasn't changed
                if cached_sample and cached_mtime == video.get("mtime"):
                    sample_text = cached_sample
                else:
                    progress.update(task, description=f"Transcribing sample: {video['filename'][:30]}...")
                    sample_text = transcribe_sample(video["current_path"])

                if sample_text:
                    match_result = find_matching_transcript(sample_text, transcripts)

                    if match_result:
                        transcript, confidence = match_result
                        video["status"] = "linked"
                        video["transcript_id"] = transcript["id"]
                        video["match_confidence"] = round(confidence, 3)
                        video["linked_at"] = datetime.now().isoformat()
                        linked_transcript_ids.add(transcript["id"])
                        linked += 1
                        progress.advance(task)
                        continue

            # No match found - cache sample_text for next scan
            video["status"] = "unlinked"
            video["transcript_id"] = None
            video["match_confidence"] = None
            video["linked_at"] = None
            if not quick:
                if sample_text:
                    video["sample_text"] = sample_text
                    video["scanned_mtime"] = video.get("mtime")
            unlinked += 1
            progress.advance(task)

    # Build set of scanned video IDs
    scanned_ids = {v["id"] for v in videos}

    # Update inventory with scanned videos
    for video in videos:
        inventory["videos"][video["id"]] = video

    # Mark stale entries as 'missing' (videos in inventory but not found in scan)
    missing = 0
    for video_id, video in list(inventory["videos"].items()):
        if video_id not in scanned_ids:
            # Video was in inventory but not found in this scan
            if video.get("status") != "missing":
                video["status"] = "missing"
                video["missing_since"] = datetime.now().isoformat()
                missing += 1

    inventory["last_scan"] = datetime.now().isoformat()
    save_inventory(inventory)

    # Summary
    if not cron:
        console.print()
        table = Table(title="Scan Results")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Total videos", str(len(videos)))
        table.add_row("Linked", f"[green]{linked}[/green]")
        table.add_row("Unlinked", f"[yellow]{unlinked}[/yellow]")
        if missing > 0:
            table.add_row("Marked missing", f"[red]{missing}[/red]")
        console.print(table)

    # Reorganize if requested
    if reorganize:
        reorganize_videos(inventory, yes=yes, cron=cron)

    return {"found": len(videos), "linked": linked, "unlinked": unlinked, "missing": missing}


def reorganize_videos(inventory: dict, yes: bool = False, cron: bool = False):
    """
    Move videos to decimal structure.

    Linked videos → /Volumes/BackupArchive/kb-videos/{decimal}/
    Unlinked videos → /Volumes/BackupArchive/kb-videos/_unlinked/
    """
    config = load_config()
    target_base = expand_path(config.get("video_target", "/Volumes/BackupArchive/kb-videos"))

    if not cron:
        console.print(f"\n[bold cyan]Reorganizing videos to {target_base}[/bold cyan]\n")

    videos = inventory.get("videos", {})
    to_move = []

    for video_id, video in videos.items():
        current_path = video.get("current_path")
        if not current_path or not os.path.exists(current_path):
            continue

        # Determine target directory
        if video.get("status") == "linked" and video.get("transcript_id"):
            # Extract decimal from transcript_id (format: "50.01.01-YYMMDD-slug")
            parts = video["transcript_id"].split("-")
            decimal = parts[0] if parts else "_unlinked"
            target_dir = target_base / decimal
        else:
            target_dir = target_base / "_unlinked"

        target_path = target_dir / video["filename"]

        # Skip if already in target location
        if os.path.abspath(current_path) == os.path.abspath(str(target_path)):
            continue

        # Handle duplicate filenames
        if target_path.exists():
            base, ext = os.path.splitext(video["filename"])
            counter = 1
            while target_path.exists():
                target_path = target_dir / f"{base}_{counter}{ext}"
                counter += 1

        to_move.append({
            "video_id": video_id,
            "from": current_path,
            "to": str(target_path),
            "target_dir": str(target_dir),
        })

    if not to_move:
        if not cron:
            console.print("[green]All videos already organized![/green]")
        return

    if not cron:
        console.print(f"[bold]{len(to_move)}[/bold] videos to move:\n")
        for item in to_move[:10]:
            console.print(f"  {os.path.basename(item['from'])} → {item['to']}")
        if len(to_move) > 10:
            console.print(f"  ... and {len(to_move) - 10} more")

    # Confirm
    if not yes and not cron:
        import questionary
        if not questionary.confirm("Proceed with move?", default=False).ask():
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Move files
    moved = 0
    for item in to_move:
        try:
            # Create target directory
            Path(item["target_dir"]).mkdir(parents=True, exist_ok=True)

            # Move file
            shutil.move(item["from"], item["to"])

            # Update inventory
            inventory["videos"][item["video_id"]]["current_path"] = item["to"]
            moved += 1

        except Exception as e:
            if not cron:
                console.print(f"[red]Failed to move {item['from']}: {e}[/red]")

    save_inventory(inventory)

    if not cron:
        console.print(f"\n[green]Moved {moved} files[/green]")


# --- Transcription Queue ---

QUEUE_PATH = Path.home() / ".kb" / "transcription-queue.json"

# Background worker state
import threading
_worker_lock = threading.Lock()
_worker_thread = None
_worker_running = False


def load_queue() -> dict:
    """Load transcription queue from disk."""
    if QUEUE_PATH.exists():
        try:
            with open(QUEUE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"jobs": {}, "completed": []}


def save_queue(queue: dict):
    """Save transcription queue to disk."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_PATH, 'w') as f:
        json.dump(queue, f, indent=2)


def queue_transcription(
    video_id: str,
    decimal: str,
    title: str,
    tags: list[str] | None = None,
) -> dict:
    """
    Add a video to the transcription queue.

    Args:
        video_id: Video ID from inventory
        decimal: Decimal category (e.g., "50.01.01")
        title: Title for the transcript
        tags: Optional list of tags

    Returns:
        Job dict with id, status, etc.
    """
    queue = load_queue()
    inventory = load_inventory()

    video = inventory.get("videos", {}).get(video_id)
    if not video:
        raise ValueError(f"Video not found: {video_id}")

    if video.get("status") == "processing":
        raise ValueError(f"Video already processing: {video_id}")

    # Create job
    job = {
        "id": video_id,
        "video_path": video.get("current_path"),
        "filename": video.get("filename"),
        "decimal": decimal,
        "title": title,
        "tags": tags or [],
        "status": "pending",
        "queued_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "transcript_id": None,
    }

    queue["jobs"][video_id] = job
    save_queue(queue)

    # Update video status in inventory
    inventory["videos"][video_id]["status"] = "processing"
    save_inventory(inventory)

    # Start worker if not running
    start_worker()

    return job


def get_queue_status() -> dict:
    """Get current queue status."""
    queue = load_queue()
    jobs = queue.get("jobs", {})

    pending = [j for j in jobs.values() if j.get("status") == "pending"]
    processing = [j for j in jobs.values() if j.get("status") == "processing"]
    failed = [j for j in jobs.values() if j.get("status") == "failed"]

    return {
        "pending": len(pending),
        "processing": len(processing),
        "failed": len(failed),
        "completed": len(queue.get("completed", [])),
        "jobs": jobs,
        "worker_running": _worker_running,
    }


def process_next_job() -> bool:
    """
    Process the next pending job in the queue.

    Returns True if a job was processed, False if queue is empty.
    """
    queue = load_queue()
    jobs = queue.get("jobs", {})

    # Find next pending job (oldest first)
    pending = [(jid, j) for jid, j in jobs.items() if j.get("status") == "pending"]
    if not pending:
        return False

    pending.sort(key=lambda x: x[1].get("queued_at", ""))
    job_id, job = pending[0]

    # Mark as processing
    job["status"] = "processing"
    job["started_at"] = datetime.now().isoformat()
    save_queue(queue)

    try:
        # Import transcribe_to_kb here to avoid circular imports
        from kb.core import transcribe_to_kb

        video_path = job["video_path"]
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        console.print(f"[cyan]Transcribing: {job['filename']}[/cyan]")

        # Transcribe and save to KB
        result = transcribe_to_kb(
            file_path=video_path,
            decimal=job["decimal"],
            title=job["title"],
            tags=job["tags"],
            source_type="video",
        )

        transcript_id = result.get("id")

        # Update job as completed
        job["status"] = "completed"
        job["completed_at"] = datetime.now().isoformat()
        job["transcript_id"] = transcript_id

        # Move to completed list
        queue["completed"].append(job)
        del queue["jobs"][job_id]
        save_queue(queue)

        # Update video inventory: mark as linked
        inventory = load_inventory()
        if job_id in inventory.get("videos", {}):
            inventory["videos"][job_id]["status"] = "linked"
            inventory["videos"][job_id]["transcript_id"] = transcript_id
            inventory["videos"][job_id]["match_confidence"] = 1.0
            inventory["videos"][job_id]["linked_at"] = datetime.now().isoformat()
            save_inventory(inventory)

        console.print(f"[green]✓ Completed: {job['filename']} → {transcript_id}[/green]")
        return True

    except Exception as e:
        # Mark job as failed
        job["status"] = "failed"
        job["error"] = str(e)
        job["completed_at"] = datetime.now().isoformat()
        save_queue(queue)

        # Revert video status to unlinked
        inventory = load_inventory()
        if job_id in inventory.get("videos", {}):
            inventory["videos"][job_id]["status"] = "unlinked"
            save_inventory(inventory)

        console.print(f"[red]✗ Failed: {job['filename']} - {e}[/red]")
        return True


def worker_loop():
    """Background worker loop that processes the queue."""
    global _worker_running

    _worker_running = True
    try:
        while True:
            # Process jobs until queue is empty
            if not process_next_job():
                break
            # Small delay between jobs
            import time
            time.sleep(1)
    finally:
        _worker_running = False


def start_worker():
    """Start the background worker thread if not already running."""
    global _worker_thread, _worker_running

    with _worker_lock:
        if _worker_running:
            return

        if _worker_thread is not None and _worker_thread.is_alive():
            return

        _worker_thread = threading.Thread(target=worker_loop, daemon=True)
        _worker_thread.start()


def categorize_unlinked_videos():
    """
    Interactive loop to categorize unlinked videos.

    Shows list of unlinked videos, lets user select one,
    prompts for decimal/title, and queues for background transcription.
    """
    import questionary
    from questionary import Style

    custom_style = Style([
        ('qmark', 'fg:cyan bold'),
        ('question', 'fg:white bold'),
        ('answer', 'fg:green bold'),
        ('pointer', 'fg:cyan bold'),
        ('highlighted', 'fg:cyan bold'),
        ('selected', 'fg:green'),
    ])

    # Load registry for decimal choices
    registry = load_registry()
    decimals = registry.get("decimals", {})

    # Build decimal choices
    decimal_choices = [
        questionary.Choice(
            title=f"{code}: {info.get('name', info) if isinstance(info, dict) else info}",
            value=code
        )
        for code, info in sorted(decimals.items())
    ]

    if not decimal_choices:
        console.print("[yellow]No decimal categories defined. Add some first with 'kb --decimals'[/yellow]")
        return

    while True:
        # Reload inventory to get current state
        inventory = load_inventory()
        videos = inventory.get("videos", {})

        # Filter to unlinked videos
        unlinked = [
            v for v in videos.values()
            if v.get("status") == "unlinked" and v.get("current_path") and os.path.exists(v.get("current_path", ""))
        ]

        if not unlinked:
            console.print("\n[green]✓ No unlinked videos remaining![/green]\n")
            break

        # Sort by mtime (newest first)
        unlinked.sort(key=lambda v: v.get("mtime", ""), reverse=True)

        # Show queue status
        queue_status = get_queue_status()
        if queue_status["pending"] > 0 or queue_status["processing"] > 0:
            console.print(f"\n[dim]Background queue: {queue_status['pending']} pending, {queue_status['processing']} processing[/dim]")

        console.print(f"\n[bold cyan]Unlinked Videos ({len(unlinked)} remaining)[/bold cyan]\n")

        # Build video choices
        video_choices = []
        for v in unlinked[:20]:  # Limit to 20 for usability
            filename = v.get("filename", "Unknown")
            source = v.get("source_label", "")
            duration = v.get("duration_seconds", 0)
            duration_str = f"{int(duration // 60)}m" if duration else ""
            size = v.get("size_mb", 0)
            size_str = f"{size}MB" if size else ""

            # Show sample text preview if available
            sample = v.get("sample_text", "")
            preview = ""
            if sample:
                preview = f" [dim]({sample[:40]}...)[/dim]"

            title = f"{filename[:40]:<40} [{source}] {duration_str:>5} {size_str:>8}{preview}"
            video_choices.append(questionary.Choice(title=title, value=v["id"]))

        if len(unlinked) > 20:
            video_choices.append(questionary.Choice(
                title=f"[dim]... and {len(unlinked) - 20} more[/dim]",
                value=None,
                disabled="Showing first 20 only"
            ))

        video_choices.insert(0, questionary.Choice(title="← Done categorizing", value="exit"))

        # Select video
        selected = questionary.select(
            "Select video to categorize:",
            choices=video_choices,
            style=custom_style,
            instruction="(↑/↓ navigate, Enter select)",
        ).ask()

        if selected == "exit" or selected is None:
            break

        # Get the selected video
        video = videos.get(selected)
        if not video:
            console.print("[red]Video not found in inventory[/red]")
            continue

        console.print(f"\n[bold]Selected:[/bold] {video.get('filename')}")
        console.print(f"[dim]Path: {video.get('current_path')}[/dim]")
        console.print(f"[dim]Duration: {video.get('duration_seconds', 0) // 60}m, Size: {video.get('size_mb', 0)}MB[/dim]")

        if video.get("sample_text"):
            console.print(f"\n[bold]Sample transcript:[/bold]")
            console.print(f"[dim]{video['sample_text'][:200]}...[/dim]")

        # Select decimal category
        console.print()
        decimal = questionary.select(
            "Category (decimal):",
            choices=decimal_choices,
            style=custom_style,
        ).ask()

        if decimal is None:
            continue

        # Suggest title from filename
        default_title = Path(video.get("filename", "")).stem
        # Clean up common prefixes/suffixes
        default_title = default_title.replace("_", " ").replace("-", " ")

        title = questionary.text(
            "Title:",
            default=default_title,
            style=custom_style,
        ).ask()

        if title is None:
            continue

        title = title.strip()
        if not title:
            console.print("[yellow]Title is required[/yellow]")
            continue

        # Select tags (multi-select from registry with option to add new)
        from kb.cli import select_tags
        tags = select_tags(registry)

        # Confirm and queue
        console.print(f"\n[bold cyan]Summary[/bold cyan]")
        console.print(f"  Video: {video.get('filename')}")
        console.print(f"  Category: [cyan]{decimal}[/cyan]")
        console.print(f"  Title: {title}")
        if tags:
            console.print(f"  Tags: {', '.join(tags)}")

        confirm = questionary.confirm(
            "\nQueue for transcription?",
            default=True,
            style=custom_style,
        ).ask()

        if confirm:
            try:
                job = queue_transcription(
                    video_id=selected,
                    decimal=decimal,
                    title=title,
                    tags=tags,
                )
                console.print(f"[green]✓ Queued for transcription![/green]")
                console.print(f"[dim]Job will process in background. Check queue status with 'kb serve'[/dim]")
            except Exception as e:
                console.print(f"[red]Failed to queue: {e}[/red]")

    # Final queue status
    queue_status = get_queue_status()
    if queue_status["pending"] > 0 or queue_status["processing"] > 0:
        console.print(f"\n[bold cyan]Queue Status[/bold cyan]")
        console.print(f"  Pending: {queue_status['pending']}")
        console.print(f"  Processing: {queue_status['processing']}")
        console.print(f"  Completed: {queue_status['completed']}")
        console.print(f"\n[dim]Background worker is running. View progress at kb serve dashboard.[/dim]")


def main():
    """CLI entry point for kb scan-videos."""
    import argparse

    parser = argparse.ArgumentParser(description="Scan and manage video inventory")
    parser.add_argument("--quick", action="store_true", help="Skip smart matching")
    parser.add_argument("--reorganize", action="store_true", help="Move files to decimal structure")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--cron", action="store_true", help="Silent mode for cron jobs")
    parser.add_argument("--categorize", "-c", action="store_true", help="After scan, interactively categorize unlinked videos")

    args = parser.parse_args()

    result = scan_videos(
        quick=args.quick,
        reorganize=args.reorganize,
        yes=args.yes,
        cron=args.cron
    )

    # Log for cron mode
    if args.cron:
        log_path = Path.home() / ".kb" / "scan.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - Found: {result['found']}, Linked: {result['linked']}, Unlinked: {result['unlinked']}\n")
        return

    # Interactive categorization if requested or if there are unlinked videos
    if args.categorize and result.get("unlinked", 0) > 0:
        categorize_unlinked_videos()
    elif result.get("unlinked", 0) > 0 and not args.quick:
        # Offer to categorize if there are unlinked videos
        import questionary
        if questionary.confirm(
            f"\n{result['unlinked']} unlinked video(s). Categorize them now?",
            default=True
        ).ask():
            categorize_unlinked_videos()


if __name__ == "__main__":
    main()
