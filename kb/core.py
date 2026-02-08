#!/usr/bin/env python3
"""
KB Core - Shared utilities for all KB sources.

This module contains shared functions and classes used across all KB source modules
to prevent import breakage and code duplication.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# Import paths from __main__ to maintain single source of truth
from kb.config import load_config, get_paths, DEFAULTS

# Load paths from config
_config = load_config()
_paths = get_paths(_config)

KB_ROOT = _paths["kb_output"]
CONFIG_DIR = _paths["config_dir"]
REGISTRY_PATH = CONFIG_DIR / "registry.json"

# Default whisper model from config
DEFAULT_WHISPER_MODEL = _config.get("defaults", {}).get("whisper_model", DEFAULTS["defaults"]["whisper_model"])

# Supported file formats
SUPPORTED_FORMATS = (
    '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm',
    '.mp4', '.m4v', '.mov', '.aac', '.wma', '.mkv', '.avi'
)

VIDEO_FORMATS = ('.mp4', '.m4v', '.mov', '.webm', '.mkv', '.avi')
AUDIO_FORMATS = ('.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.aac', '.wma')

# Network volume prefixes
NETWORK_VOLUME_PREFIXES = (
    '/Volumes/',      # macOS mounted volumes (except Macintosh HD)
    '/mnt/',          # Linux mount points
    '/media/',        # Linux media mounts
)


# --- Progress Reporting (unified) ---

def print_status(msg: str):
    """Print status message with consistent format."""
    print(f"[KB] {msg}", flush=True)


# --- Registry Functions (consolidated from transcribe.py + cli.py) ---

def load_registry() -> dict:
    """Load the registry.json file."""
    default = {
        "decimals": {},
        "tags": [],
        "transcribed_files": [],
        "transcribed_zoom_meetings": []
    }
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, 'r') as f:
                data = json.load(f)
                # Ensure required keys exist (merge with defaults)
                for key in default:
                    if key not in data:
                        data[key] = default[key]
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"[KB] Warning: Could not load registry.json: {e}")
            print(f"[KB] Using defaults. Fix or remove: {REGISTRY_PATH}")
            return default
    return default


def save_registry(registry: dict) -> bool:
    """Save the registry.json file. Returns True on success, False on error."""
    try:
        # Ensure config directory exists
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_PATH, 'w') as f:
            json.dump(registry, f, indent=2)
        return True
    except (IOError, OSError) as e:
        print(f"[KB] Error: Could not save registry.json: {e}")
        return False


# --- Transcription Utilities ---

def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'[^a-z0-9\-]', '', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


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


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


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


def detect_source_type(file_path: str, explicit_type: str | None = None) -> str:
    """
    Detect the source type from file extension.

    Returns: 'video', 'audio', 'meeting', 'paste', or 'cap'
    """
    if explicit_type:
        return explicit_type

    ext = os.path.splitext(file_path)[1].lower()
    if ext in VIDEO_FORMATS:
        return "video"
    elif ext in AUDIO_FORMATS:
        return "audio"
    return "video"  # Default to video for unknown


# --- LocalFileCopy for network volumes ---

def get_remote_mount_info(file_path: str) -> tuple[str, str, str] | None:
    """
    Check if file path matches a configured remote mount.

    Returns (ssh_host, remote_path, local_mount) if matched, None otherwise.
    """
    remote_mounts = _config.get("remote_mounts", {})

    for local_mount, mount_info in remote_mounts.items():
        if file_path.startswith(local_mount):
            ssh_host = mount_info.get("host")
            remote_base = mount_info.get("path")
            if ssh_host and remote_base:
                # Map local path to remote path
                relative_path = file_path[len(local_mount):]
                remote_path = remote_base + relative_path
                return (ssh_host, remote_path, local_mount)

    return None


class LocalFileCopy:
    """Context manager to extract audio from video files and handle network volumes."""

    def __init__(self, file_path: str):
        self.original_path = file_path
        self.local_path = None
        self.temp_dir = None
        self.remote_temp_file = None  # Track remote temp file for cleanup
        self.ssh_host = None
        ext = os.path.splitext(file_path)[1].lower()
        self.is_video = ext in VIDEO_FORMATS
        self.is_network = is_network_path(file_path)
        self.remote_mount_info = get_remote_mount_info(file_path)

    def __enter__(self) -> str:
        # Video files always need audio extraction (whisper can't read video containers)
        # Network files need local copy for performance
        if not self.is_video and not self.is_network:
            return self.original_path

        self.temp_dir = tempfile.mkdtemp(prefix='kb_whisper_')

        if self.is_video:
            self.local_path = os.path.join(self.temp_dir, 'audio.wav')
            size_mb = os.path.getsize(self.original_path) / (1024 * 1024)

            # Try SSH extraction for remote mounts (most efficient)
            if self.remote_mount_info:
                ssh_host, remote_path, _ = self.remote_mount_info
                result = self._extract_via_ssh(ssh_host, remote_path, size_mb)
                if result:
                    return result
                # Fall through to local extraction on failure

            # Local ffmpeg extraction
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

    def _extract_via_ssh(self, ssh_host: str, remote_path: str, size_mb: float) -> str | None:
        """
        Extract audio via SSH on the remote server.

        Returns local path to audio file on success, None on failure.
        """
        import shlex
        import uuid
        import time
        import sys

        print(f"\n[SSH] Extracting audio from {size_mb:.0f} MB video on server...")

        # Generate unique temp filename on server
        temp_name = f"/tmp/kb_audio_{uuid.uuid4().hex[:8]}.wav"
        self.remote_temp_file = temp_name
        self.ssh_host = ssh_host

        # Safely quote the remote path
        quoted_remote_path = shlex.quote(remote_path)
        quoted_temp_name = shlex.quote(temp_name)

        # Run ffmpeg on remote server with progress
        # Use -stats to show progress on stderr
        ssh_cmd = [
            'ssh', ssh_host,
            f'ffmpeg -i {quoted_remote_path} -vn -acodec pcm_s16le -ar 16000 -ac 1 -y {quoted_temp_name} 2>&1 | grep -E "^(size=|video:|Duration:)" | tail -3'
        ]

        try:
            start_time = time.time()
            print(f"[SSH] Running ffmpeg on {ssh_host}...", end="", flush=True)

            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=1800)  # 30 min timeout

            extract_time = time.time() - start_time

            if result.returncode != 0:
                print(f" failed!")
                print_status(f"SSH extraction failed, falling back to local...")
                self._cleanup_remote_temp()
                return None

            print(f" done ({extract_time:.1f}s)")

            # Show ffmpeg output if any
            if result.stdout.strip():
                for line in result.stdout.strip().split('\n')[-2:]:
                    if line.strip():
                        print(f"[SSH] {line.strip()}")

            # Get audio file size from server
            size_cmd = ['ssh', ssh_host, f'ls -lh {quoted_temp_name} 2>/dev/null | awk "{{print \\$5}}"']
            size_result = subprocess.run(size_cmd, capture_output=True, text=True, timeout=30)
            remote_size = size_result.stdout.strip() or "?"

            # SCP the audio file back with progress
            print(f"[SSH] Copying {remote_size} audio file to Mac...", end="", flush=True)
            start_time = time.time()

            scp_cmd = ['scp', '-q', f'{ssh_host}:{temp_name}', self.local_path]
            scp_result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=300)

            scp_time = time.time() - start_time

            if scp_result.returncode != 0:
                print(f" failed!")
                print_status("SCP failed, falling back to local...")
                self._cleanup_remote_temp()
                return None

            # Verify file was copied
            if not os.path.exists(self.local_path):
                print(f" failed!")
                self._cleanup_remote_temp()
                return None

            audio_size_mb = os.path.getsize(self.local_path) / (1024 * 1024)
            transfer_speed = audio_size_mb / scp_time if scp_time > 0 else 0
            print(f" done ({scp_time:.1f}s, {transfer_speed:.1f} MB/s)")

            # Cleanup remote temp file
            self._cleanup_remote_temp()

            print(f"[SSH] ✓ Audio ready: {audio_size_mb:.1f} MB")

            return self.local_path

        except subprocess.TimeoutExpired:
            print(f" timeout!")
            print_status("SSH extraction timed out, falling back to local...")
            self._cleanup_remote_temp()
            return None
        except Exception as e:
            print(f" error!")
            print_status(f"SSH extraction error: {e}, falling back to local...")
            self._cleanup_remote_temp()
            return None

    def _cleanup_remote_temp(self):
        """Clean up temporary file on remote server."""
        if self.ssh_host and self.remote_temp_file:
            try:
                subprocess.run(
                    ['ssh', self.ssh_host, f'rm -f {shlex.quote(self.remote_temp_file)}'],
                    capture_output=True, timeout=30
                )
            except Exception:
                pass  # Best effort cleanup
            self.remote_temp_file = None

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
        # Cleanup remote temp file if still exists
        self._cleanup_remote_temp()

        # Cleanup local temp dir
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
        return False


# --- Core Transcription Function ---

def transcribe_audio(
    file_path: str,
    model_name: str = "medium",
    progress_callback: callable = None,
) -> dict:
    """
    Transcribe an audio/video file using Whisper.

    Args:
        file_path: Path to audio/video file
        model_name: Whisper model to use (default: "medium")
        progress_callback: Optional callback function(percent, text, lang_info)

    Returns:
        Dictionary with:
        - "text": Full concatenated text
        - "segments": Raw pywhispercpp Segment objects (with .t0, .t1, .text attributes)
        - "duration": Duration in seconds from ffprobe
        - "formatted": Timestamp-formatted text like "[MM:SS] text\\n[MM:SS] text\\n..."

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is unsupported
        RuntimeError: If transcription produces no result
    """
    # Import here to avoid circular imports
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.core.transcription_service_cpp import get_transcription_service
    from app.utils.config_manager import ConfigManager

    # Validate file
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {ext}")

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

    # Default progress callback if none provided
    def default_progress_callback(percent, text, lang_info):
        if percent % 10 == 0:
            print_status(f"Transcribing: {percent}%")

    callback = progress_callback or default_progress_callback

    # Handle network volumes and video files
    print_status("Starting transcription...")
    with LocalFileCopy(file_path) as local_path:
        result = service.transcribe(
            local_path,
            language=config.get("transcription_language", None),
            beam_size=1,
            progress_callback=callback
        )

    # Extract segments and format transcript with timestamps
    segments = result.get("segments", [])
    full_text = result.get("text", "").strip()

    if not segments and not full_text:
        raise RuntimeError("No transcription result")

    # Format transcript with timestamps from segments
    formatted_lines = []
    if segments:
        for seg in segments:
            # pywhispercpp segments have t0/t1 in centiseconds
            start_seconds = seg.t0 / 100.0
            ts = format_timestamp(start_seconds)
            text = seg.text.strip()
            if text:
                formatted_lines.append(f"[{ts}] {text}")

    formatted_text = "\n".join(formatted_lines) if formatted_lines else full_text

    return {
        "text": full_text,
        "segments": segments,
        "duration": duration,
        "formatted": formatted_text,
    }


def transcribe_to_kb(
    file_path: str,
    decimal: str,
    title: str,
    tags: list[str],
    recorded_at: str | None = None,
    speakers: list[str] | None = None,
    source_type: str | None = None,  # video, audio, meeting, paste, cap
    model_name: str = "medium",
    transcript_text: str | None = None,  # For paste source (already has transcript)
) -> dict:
    """
    Transcribe a file (or save existing transcript) to the knowledge base.

    Args:
        file_path: Path to audio/video file (or placeholder for paste source)
        decimal: Decimal category (e.g., "50.01.01")
        title: Title for the transcript
        tags: List of tags
        recorded_at: Recording date (YYYY-MM-DD), defaults to today
        speakers: List of speaker names
        source_type: Type of source (video, audio, meeting, paste, cap)
        model_name: Whisper model to use
        transcript_text: Pre-existing transcript text (for paste source)

    Returns:
        The saved transcript data dict.
    """
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

    # Detect source type if not provided
    if source_type is None:
        source_type = detect_source_type(file_path)

    # Handle transcript text (either provided or transcribe)
    if transcript_text is not None:
        # Paste source - transcript already provided
        print_status("Using provided transcript text")
        duration = 0  # Unknown for paste
    else:
        # Need to transcribe the file - use transcribe_audio()
        result = transcribe_audio(file_path, model_name=model_name)
        transcript_text = result["formatted"]
        duration = result["duration"]

    # Build transcript data
    transcript_data = {
        "id": transcript_id,
        "decimal": decimal,
        "title": title,
        "type": source_type,  # NEW: source type field
        "source_files": [os.path.abspath(file_path)] if file_path else [],
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
    if file_path:
        abs_path = os.path.abspath(file_path)
        if abs_path not in registry["transcribed_files"]:
            registry["transcribed_files"].append(abs_path)

    for tag in tags:
        if tag not in registry["tags"]:
            registry["tags"].append(tag)

    save_registry(registry)

    return transcript_data
