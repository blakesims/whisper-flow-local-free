#!/usr/bin/env python3
"""
Whisper Daemon - Background service for instant transcription

This daemon:
1. Keeps the Whisper model pre-loaded in memory
2. Listens for global hotkey (Ctrl+F) to toggle recording
3. Shows a floating indicator during recording
4. Auto-pastes transcription to the active application
"""

import glob
import json
import os
import signal
import sys
import tempfile
import time
from enum import Enum
from pathlib import Path
from typing import Optional

# Daemon version — bump on performance-relevant changes
DAEMON_VERSION = "2.0.0"  # v2: streaming transcription + VAD segmentation + base.en

# Unbuffered output for daemon logging
sys.stdout = sys.stderr  # Redirect stdout to stderr for immediate output
os.environ["PYTHONUNBUFFERED"] = "1"

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pyperclip
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.core.audio_recorder import AudioRecorder
from app.core.post_processor import get_post_processor
from app.core.streaming_transcriber import StreamingTranscriber
from app.core.transcription_service_cpp import (
    WhisperCppService,
    get_transcription_service,
)
from app.daemon.hotkey_listener import HotkeyListener
from app.daemon.recording_indicator import RecordingIndicator
from app.utils.config_manager import ConfigManager


class PerfTrace:
    """Captures timing metadata for a single recording→transcription cycle."""

    def __init__(self):
        self.hotkey_pressed = 0.0      # when hotkey was pressed to start
        self.recording_started = 0.0   # when audio stream actually started
        self.stop_requested = 0.0      # when hotkey was pressed to stop
        self.recording_stopped = 0.0   # when audio stream fully stopped
        self.transcribe_start = 0.0    # when transcription begins (flush or file)
        self.transcribe_end = 0.0      # when transcription text is ready
        self.post_process_end = 0.0    # after LLM post-processing (if enabled)
        self.clipboard_done = 0.0      # after clipboard copy
        self.paste_done = 0.0          # after auto-paste

        self.streaming_segments = 0    # segments transcribed during recording
        self.streaming_flush_time = 0.0  # time spent in flush() only
        self.used_streaming = False
        self.used_vad = False
        self.recording_mode = "normal"
        self.model_name = ""
        self.text_length = 0

    def recording_duration(self) -> float:
        if self.recording_started and self.stop_requested:
            return self.stop_requested - self.recording_started
        return 0.0

    def log_summary(self):
        """Print a structured performance summary."""
        rec_dur = self.recording_duration()
        hotkey_to_rec = (self.recording_started - self.hotkey_pressed) if self.hotkey_pressed else 0
        stop_to_stopped = (self.recording_stopped - self.stop_requested) if self.stop_requested else 0
        transcribe_time = (self.transcribe_end - self.transcribe_start) if self.transcribe_start else 0
        post_time = (self.post_process_end - self.transcribe_end) if self.post_process_end and self.transcribe_end else 0
        total_latency = (self.paste_done or self.clipboard_done or self.transcribe_end) - self.stop_requested if self.stop_requested else 0

        print(f"\n{'='*60}")
        print(f"  PERF TRACE  v{DAEMON_VERSION}  [{self.recording_mode}]  model={self.model_name}")
        print(f"{'='*60}")
        print(f"  Hotkey → Recording started:  {hotkey_to_rec*1000:6.0f}ms")
        print(f"  Recording duration:           {rec_dur:6.2f}s")
        print(f"  Stop → Stream fully stopped:  {stop_to_stopped*1000:6.0f}ms")
        if self.used_streaming:
            print(f"  Streaming segments (during):  {self.streaming_segments}")
            print(f"  VAD segmentation:             {'yes' if self.used_vad else 'no (fixed interval)'}")
            print(f"  Flush time (user waits):      {self.streaming_flush_time*1000:6.0f}ms")
        print(f"  Transcription time:           {transcribe_time*1000:6.0f}ms")
        if post_time > 0:
            print(f"  Post-processing time:         {post_time*1000:6.0f}ms")
        print(f"  Text length:                  {self.text_length} chars")
        print(f"  ─────────────────────────────")
        print(f"  TOTAL LATENCY (stop→done):    {total_latency*1000:6.0f}ms")
        print(f"{'='*60}\n")


class DaemonState(Enum):
    """State machine for the daemon"""

    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


class RecordingMode(Enum):
    """Mode determines output handling after transcription"""

    NORMAL = "normal"  # Ctrl+F: clipboard + auto-paste
    DELEGATION = "delegation"  # Option+F: save to cc-triage inbox for routing


# Supported audio/video formats for file transcription
SUPPORTED_AUDIO_FORMATS = (
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
    ".mp4",
    ".m4v",
    ".mov",
    ".aac",
    ".wma",
)


class DelegationState(Enum):
    """State machine for delegation lifecycle tracking"""

    SENT = "sent"  # File in inbox, waiting for cc-triage
    PROCESSING = "processing"  # File picked up (gone from inbox)
    COMPLETE = "complete"  # Report exists in reports dir
    FAILED = "failed"  # File moved to failed dir


class DelegationTracker(QObject):
    """
    Polls cc-triage filesystem to track delegation lifecycle.

    Reads cc-triage's own config/config.json for directory paths.
    Emits signals on state transitions for UI pip updates.
    Auto-starts/stops polling based on active delegation count.
    """

    delegation_state_changed = Signal(str, str)  # (delegation_id, new_state)

    POLL_INTERVAL_MS = 2000  # 2 seconds
    COMPLETE_CLEANUP_DELAY_MS = 5000  # 5s after COMPLETE before stop tracking
    FAILED_CLEANUP_DELAY_MS = 1000  # ~1s after FAILED before stop tracking

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)

        self._config_manager = config_manager
        # {delegation_id: DelegationState}
        self._active: dict[str, DelegationState] = {}

        # Resolved cc-triage directories (lazily loaded)
        self._inbox_dir: str | None = None
        self._reports_dir: str | None = None
        self._failed_dir: str | None = None
        self._dirs_resolved = False

        # Polling timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)

    def _resolve_dirs(self) -> bool:
        """
        Resolve cc-triage directories from its config.json.

        Returns True if directories were resolved successfully.
        """
        cc_triage_root = self._config_manager.get("cc_triage_root", None)
        if not cc_triage_root:
            print("[DelegationTracker] No cc_triage_root configured")
            return False

        cc_triage_root = os.path.expanduser(cc_triage_root)
        config_path = os.path.join(cc_triage_root, "config", "config.json")

        try:
            with open(config_path, "r") as f:
                cc_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[DelegationTracker] Cannot read cc-triage config: {e}")
            return False

        # Resolve relative paths against cc_triage_root
        inbox_rel = cc_config.get("inbox_path", "./inbox")
        reports_rel = cc_config.get("reports_path", "./reports")
        failed_rel = cc_config.get("failed_path", "./failed")

        self._inbox_dir = os.path.normpath(os.path.join(cc_triage_root, inbox_rel))
        self._reports_dir = os.path.normpath(os.path.join(cc_triage_root, reports_rel))
        self._failed_dir = os.path.normpath(os.path.join(cc_triage_root, failed_rel))
        self._dirs_resolved = True

        print(f"[DelegationTracker] Resolved dirs: inbox={self._inbox_dir}, reports={self._reports_dir}, failed={self._failed_dir}")
        return True

    def track(self, delegation_id: str):
        """
        Start tracking a delegation by its filename (e.g. 'delegation_20260215_171033.txt').

        Immediately sets state to SENT and starts polling if not already running.
        """
        if not self._dirs_resolved:
            if not self._resolve_dirs():
                print(f"[DelegationTracker] Cannot track {delegation_id}: dirs not resolved")
                return

        self._active[delegation_id] = DelegationState.SENT
        self.delegation_state_changed.emit(delegation_id, DelegationState.SENT.value)
        print(f"[DelegationTracker] Tracking: {delegation_id} -> SENT")

        # Start polling if not already running
        if not self._poll_timer.isActive():
            self._poll_timer.start(self.POLL_INTERVAL_MS)
            print("[DelegationTracker] Polling started")

    def _poll(self):
        """Check filesystem for state transitions on all active delegations."""
        if not self._active:
            self._poll_timer.stop()
            print("[DelegationTracker] No active delegations, polling stopped")
            return

        for delegation_id in list(self._active.keys()):
            try:
                current_state = self._active[delegation_id]
                new_state = self._check_state(delegation_id, current_state)

                if new_state and new_state != current_state:
                    self._active[delegation_id] = new_state
                    self.delegation_state_changed.emit(delegation_id, new_state.value)
                    print(f"[DelegationTracker] {delegation_id}: {current_state.value} -> {new_state.value}")

                    # Schedule cleanup for terminal states
                    if new_state == DelegationState.COMPLETE:
                        QTimer.singleShot(
                            self.COMPLETE_CLEANUP_DELAY_MS,
                            lambda did=delegation_id: self._cleanup(did),
                        )
                    elif new_state == DelegationState.FAILED:
                        QTimer.singleShot(
                            self.FAILED_CLEANUP_DELAY_MS,
                            lambda did=delegation_id: self._cleanup(did),
                        )
            except Exception as e:
                print(f"[DelegationTracker] Error checking state for {delegation_id}: {e}")

    def _check_state(self, delegation_id: str, current: DelegationState) -> DelegationState | None:
        """
        Determine current filesystem state for a delegation.

        State machine:
        - SENT: file exists in inbox
        - PROCESSING: file gone from inbox (picked up by cc-triage)
        - COMPLETE: report file exists in reports dir
        - FAILED: file exists in failed dir (glob pattern for timestamp suffix)

        Returns new state or None if no change.
        """
        stem = os.path.splitext(delegation_id)[0]  # e.g. 'delegation_20260215_171033'
        inbox_path = os.path.join(self._inbox_dir, delegation_id)
        report_path = os.path.join(self._reports_dir, f"triage_{stem}.json")
        failed_pattern = os.path.join(self._failed_dir, f"{stem}_*")

        # Check terminal states first (report or failed)
        if os.path.exists(report_path):
            if current != DelegationState.COMPLETE:
                return DelegationState.COMPLETE
            return None

        if glob.glob(failed_pattern):
            if current != DelegationState.FAILED:
                return DelegationState.FAILED
            return None

        # Check if file still in inbox
        if os.path.exists(inbox_path):
            # File still in inbox -> SENT
            if current != DelegationState.SENT:
                return DelegationState.SENT
            return None

        # File gone from inbox, no report/failed yet -> PROCESSING
        if current == DelegationState.SENT:
            return DelegationState.PROCESSING

        return None

    def _cleanup(self, delegation_id: str):
        """Stop tracking a delegation after terminal state + delay."""
        if delegation_id in self._active:
            del self._active[delegation_id]
            print(f"[DelegationTracker] Stopped tracking: {delegation_id}")

            # Stop polling if no more active delegations
            if not self._active and self._poll_timer.isActive():
                self._poll_timer.stop()
                print("[DelegationTracker] No active delegations, polling stopped")

    @property
    def active_count(self) -> int:
        """Number of actively tracked delegations."""
        return len(self._active)

    @property
    def is_polling(self) -> bool:
        """Whether the poll timer is currently active."""
        return self._poll_timer.isActive()


class WhisperDaemon(QObject):
    """
    Main daemon class that orchestrates:
    - Model loading and management
    - Audio recording
    - Transcription
    - Hotkey handling
    - UI indicator updates
    """

    state_changed = Signal(DaemonState)
    transcription_complete = Signal(str)  # Emitted with transcribed text
    error_occurred = Signal(str)

    # Socket path for IPC
    SOCKET_PATH = "/tmp/whisper-daemon.sock"
    PID_FILE = "/tmp/whisper-daemon.pid"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = DaemonState.IDLE
        self._current_audio_path = None
        self._is_temp_file = (
            True  # Whether current audio is temp (should be deleted after)
        )
        self._recording_mode = RecordingMode.NORMAL
        self._cancel_recording = False

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Initialize transcription service (whisper.cpp for speed)
        self.transcription_service = get_transcription_service(self.config_manager)

        # Initialize post-processor (lazy loading)
        self.post_processor = get_post_processor(self.config_manager)

        # Initialize audio recorder with configured device
        input_device = self.config_manager.get("input_device", None)
        self.audio_recorder = AudioRecorder(device=input_device)
        self._connect_recorder_signals()
        self._log_audio_device()

        # Initialize UI indicator (always visible)
        self.indicator = RecordingIndicator()
        self._connect_indicator_signals()

        # Initialize hotkey listener
        self.hotkey_listener = HotkeyListener()
        self.hotkey_listener.hotkey_triggered.connect(self._on_hotkey_triggered)
        self.hotkey_listener.file_transcribe_requested.connect(
            self._on_file_transcribe_requested
        )
        self.hotkey_listener.escape_pressed.connect(self._on_escape_pressed)
        self.hotkey_listener.delegation_requested.connect(
            self._on_delegation_hotkey
        )
        self.hotkey_listener.post_process_requested.connect(
            self._on_double_ctrl_f
        )
        self.hotkey_listener.diff_view_requested.connect(
            self._on_diff_view_requested
        )

        # Post-process-on-demand: double Ctrl+F triggers post-processing
        self._post_process_this_transcription = False

        # Diff view: store last original + processed text
        self._last_original_text = ""
        self._last_processed_text = ""
        self._last_transcription_time = 0.0
        self._diff_view = None

        # Initialize delegation tracker for pip status updates
        self.delegation_tracker = DelegationTracker(self.config_manager)
        self.delegation_tracker.delegation_state_changed.connect(
            self._on_delegation_state_changed
        )
        # Map delegation_id -> DelegationPip widget
        self._delegation_pips: dict = {}

        # Directory for cancelled recordings
        self._cancelled_recordings_dir = os.path.expanduser(
            "~/Documents/WhisperRecordings"
        )
        os.makedirs(self._cancelled_recordings_dir, exist_ok=True)

        # Track cancelled recording for undo functionality
        self._cancelled_audio_path = None

        # Connect state changes to indicator
        self.state_changed.connect(self._update_indicator)

        # Model loading state
        self._model_loaded = False
        self._model_loading = False

        # Streaming transcriber — pre-created, reused across recordings
        self._streaming_transcriber: Optional[StreamingTranscriber] = None
        self._streaming_language: Optional[str] = None

        # Performance tracing
        self._perf: Optional[PerfTrace] = None

    def _connect_recorder_signals(self):
        """Connect audio recorder signals"""
        self.audio_recorder.recording_started_signal.connect(self._on_recording_started)
        self.audio_recorder.recording_stopped_signal.connect(self._on_recording_stopped)
        self.audio_recorder.error_signal.connect(self._on_recorder_error)
        # Connect audio chunks to waveform visualization
        self.audio_recorder.new_audio_chunk_signal.connect(self._on_audio_chunk)

    def _connect_indicator_signals(self):
        """Connect indicator UI signals"""
        self.indicator.toggle_recording_requested.connect(self._on_hotkey_triggered)
        self.indicator.delegation_requested.connect(self._on_delegation_hotkey)
        self.indicator.model_change_requested.connect(self._on_model_change_requested)
        self.indicator.post_processing_toggled.connect(self._on_post_processing_toggled)
        self.indicator.input_device_changed.connect(self._on_input_device_changed)
        self.indicator.quit_requested.connect(self._on_quit_requested)
        self.indicator.undo_cancel_requested.connect(self._on_undo_cancel)

    @Slot(str)
    def _on_model_change_requested(self, model_name: str):
        """Handle model change from indicator menu"""
        print(f"[Daemon] Model change requested: {model_name}")

        # Save to config
        self.config_manager.set("transcription_model_name", model_name)

        # Update indicator display
        self.indicator.set_current_model(model_name)

        # Reload model
        self._model_loaded = False
        print(f"[Daemon] Reloading model to '{model_name}'...")
        self._load_model()

    @Slot(bool)
    def _on_post_processing_toggled(self, enabled: bool):
        """Handle post-processing toggle from indicator menu"""
        self.post_processor.enabled = enabled
        self.indicator.set_post_processing_enabled(enabled)
        print(f"[Daemon] Post-processing {'enabled' if enabled else 'disabled'}")

    @Slot()
    def _on_double_ctrl_f(self):
        """Handle double Ctrl+F - stop recording AND post-process."""
        if self.state == DaemonState.TRANSCRIBING:
            self._post_process_this_transcription = True
            print("[Daemon] Double Ctrl+F: post-processing enabled for this transcription")
        elif self.state == DaemonState.RECORDING:
            # The first Ctrl+F already stopped recording via hotkey_triggered,
            # and the double-tap was detected. Flag for post-processing.
            self._post_process_this_transcription = True
            print("[Daemon] Double Ctrl+F: post-processing enabled for this transcription")
        else:
            print(f"[Daemon] Double Ctrl+F ignored (state={self.state.value})")

    @Slot()
    def _on_diff_view_requested(self):
        """Handle Ctrl+D - toggle diff view."""
        # Always allow dismiss if visible
        if self._diff_view is not None and self._diff_view.isVisible():
            print("[Daemon] Ctrl+D: hiding diff view")
            self._diff_view.hide()
            return

        # For showing, check we have something to diff
        if not self._last_original_text:
            print("[Daemon] Ctrl+D: no transcription to diff")
            return
        if self._last_original_text == self._last_processed_text:
            print("[Daemon] Ctrl+D: no post-processing was applied, nothing to diff")
            return

        print("[Daemon] Ctrl+D: showing diff view")
        if self._diff_view is None:
            from app.daemon.diff_view import DiffView
            self._diff_view = DiffView()
            self._diff_view.reprocess_requested.connect(self._on_reprocess_requested)
        self._diff_view.show_diff(self._last_original_text, self._last_processed_text)

    @Slot(str)
    def _on_reprocess_requested(self, new_prompt: str):
        """Re-run post-processing with an updated prompt from the diff view."""
        if not self._last_original_text:
            return

        print(f"[Daemon] Re-processing with edited prompt ({len(new_prompt)} chars)...")

        # Run post-processing with the edited prompt (don't save to disk yet)
        was_enabled = self.post_processor.enabled
        if not was_enabled:
            self.post_processor._enabled = True
        result = self.post_processor.process(self._last_original_text, prompt_override=new_prompt)
        if not was_enabled:
            self.post_processor._enabled = False

        previous = self._last_processed_text
        self._last_processed_text = result
        print(f"[Daemon] Re-processed: '{result}'")

        # Update diff view with 3-way comparison
        if self._diff_view is not None and self._diff_view.isVisible():
            self._diff_view.show_3way(self._last_original_text, previous, result)
            self._diff_view._reset_rerun_btn()

    def _log_audio_device(self):
        """Log the current audio input device"""
        if self.audio_recorder.device is not None:
            print(f"[Daemon] Using audio input device: {self.audio_recorder.device}")
        else:
            _, name = AudioRecorder.get_default_input_device()
            print(f"[Daemon] Using default audio input: {name}")

    @Slot(object)
    def _on_input_device_changed(self, device):
        """Handle input device change from indicator menu"""
        print(f"[Daemon] Input device change requested: {device}")

        # Save to config (None for default, otherwise device index)
        self.config_manager.set("input_device", device)

        # Update recorder
        self.audio_recorder.set_device(device)
        self._log_audio_device()

        # Update indicator with available devices
        self._update_indicator_devices()

    def _update_indicator_devices(self):
        """Update indicator with available input devices"""
        devices = AudioRecorder.get_input_devices()
        current = self.audio_recorder.device
        self.indicator.set_input_devices(devices, current)

    @Slot()
    def _on_quit_requested(self):
        """Handle quit request from indicator menu"""
        print("[Daemon] Quit requested from indicator")
        self.stop()
        QApplication.instance().quit()

    @Slot(object)
    def _on_audio_chunk(self, chunk):
        """Handle new audio chunk for waveform visualization and streaming transcription"""
        self.indicator.update_waveform(chunk)
        # Feed chunk to streaming transcriber for progressive transcription
        if self._streaming_transcriber and self._streaming_transcriber.is_active:
            self._streaming_transcriber.feed_chunk(chunk)

    @property
    def state(self) -> DaemonState:
        return self._state

    @state.setter
    def state(self, new_state: DaemonState):
        if self._state != new_state:
            print(f"[Daemon] State: {self._state.value} -> {new_state.value}")
            self._state = new_state
            self.state_changed.emit(new_state)

    def start(self):
        """Start the daemon - load model and begin listening for hotkeys"""
        print(f"[Daemon] Starting whisper daemon v{DAEMON_VERSION}...")

        # Write PID file
        self._write_pid_file()

        # Show indicator in idle state immediately
        self.indicator.show_idle()
        self.indicator.set_post_processing_enabled(self.post_processor.enabled)
        self.indicator.set_llm_model(self.post_processor._get_model_name())
        self._update_indicator_devices()
        print("[Daemon] Indicator shown in idle state")

        # Load model synchronously on startup
        self._load_model()

        # Start hotkey listener
        self.hotkey_listener.start()
        print("[Daemon] Hotkey listener started:")
        print("[Daemon]   Ctrl+F: Toggle recording (normal mode)")
        print("[Daemon]   Option+F: Toggle recording (delegation mode)")
        print("[Daemon]   Ctrl+Option+F: Transcribe file from clipboard")
        print("[Daemon] Click indicator dot to toggle, right-click for menu")

        print("[Daemon] Daemon ready and waiting...")

    def stop(self):
        """Stop the daemon gracefully"""
        print("[Daemon] Stopping daemon...")

        # Stop hotkey listener
        self.hotkey_listener.stop()

        # Stop any active recording
        if self.state == DaemonState.RECORDING:
            self.audio_recorder.stop_recording()
            self.audio_recorder.wait(3000)

        # Hide indicator
        self.indicator.hide()

        # Remove PID file
        self._remove_pid_file()

        print("[Daemon] Daemon stopped.")

    def _write_pid_file(self):
        """Write PID to file for daemon management"""
        try:
            with open(self.PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            print(f"[Daemon] Warning: Could not write PID file: {e}")

    def _remove_pid_file(self):
        """Remove PID file"""
        try:
            if os.path.exists(self.PID_FILE):
                os.remove(self.PID_FILE)
        except Exception as e:
            print(f"[Daemon] Warning: Could not remove PID file: {e}")

    def _load_model(self):
        """Load the Whisper model synchronously"""
        if self._model_loaded or self._model_loading:
            return

        self._model_loading = True
        print("[Daemon] Loading Whisper model...")

        try:
            # Get model config from settings
            model_name = self.config_manager.get("transcription_model_name", "base.en")
            device = self.config_manager.get("transcription_device", "cpu")
            compute_type = self.config_manager.get("transcription_compute_type", "int8")

            # Update indicator with current model
            self.indicator.set_current_model(model_name)

            # Set config and load
            self.transcription_service.set_target_model_config(
                model_name, device, compute_type
            )
            self.transcription_service._load_model()

            if self.transcription_service.model is not None:
                self._model_loaded = True
                print(f"[Daemon] Model '{model_name}' loaded successfully!")

                # Pre-create streaming transcriber + VAD so first recording is fast
                language = self.config_manager.get("transcription_language", "en")
                if language == "auto":
                    language = "en"
                self._streaming_transcriber = StreamingTranscriber(
                    self.transcription_service, language=language
                )
                self._streaming_transcriber._init_vad()
                self._streaming_language = language
                print("[Daemon] Streaming transcriber + VAD pre-initialized")
            else:
                print("[Daemon] ERROR: Failed to load model")
                self.state = DaemonState.ERROR

        except Exception as e:
            print(f"[Daemon] ERROR loading model: {e}")
            self.state = DaemonState.ERROR
        finally:
            self._model_loading = False

    @Slot()
    def _on_hotkey_triggered(self):
        """Handle Ctrl+F hotkey press - toggle recording (normal mode)"""
        hotkey_time = time.time()
        print(f"[Daemon] Hotkey triggered! Current state: {self.state.value}")

        # Save the frontmost app BEFORE we do anything
        # This ensures we can restore focus after showing indicator
        try:
            from AppKit import NSWorkspace

            self._frontmost_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        except:
            self._frontmost_app = None

        if self.state == DaemonState.IDLE:
            self._recording_mode = RecordingMode.NORMAL
            self._perf = PerfTrace()
            self._perf.hotkey_pressed = hotkey_time
            self._perf.recording_mode = "normal"
            self._perf.model_name = getattr(self.transcription_service, 'model_name', '?')
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            if self._perf:
                self._perf.stop_requested = hotkey_time
            self._stop_recording()
        elif self.state == DaemonState.TRANSCRIBING:
            print("[Daemon] Already transcribing, please wait...")
        elif self.state == DaemonState.ERROR:
            # Try to recover from error state
            print("[Daemon] Attempting to recover from error state...")
            self.state = DaemonState.IDLE
            self._recording_mode = RecordingMode.NORMAL
            self._start_recording()

    @Slot()
    def _on_delegation_hotkey(self):
        """Handle Option+F hotkey press - toggle recording (delegation mode)"""
        hotkey_time = time.time()
        print(
            f"[Daemon] Delegation hotkey triggered! Current state: {self.state.value}"
        )

        # Save the frontmost app BEFORE we do anything
        try:
            from AppKit import NSWorkspace

            self._frontmost_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        except:
            self._frontmost_app = None

        if self.state == DaemonState.IDLE:
            self._recording_mode = RecordingMode.DELEGATION
            self._perf = PerfTrace()
            self._perf.hotkey_pressed = hotkey_time
            self._perf.recording_mode = "delegation"
            self._perf.model_name = getattr(self.transcription_service, 'model_name', '?')
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            if self._perf:
                self._perf.stop_requested = hotkey_time
            self._stop_recording()
        elif self.state == DaemonState.TRANSCRIBING:
            print("[Daemon] Already transcribing, please wait...")
        elif self.state == DaemonState.ERROR:
            print("[Daemon] Attempting to recover from error state...")
            self.state = DaemonState.IDLE
            self._recording_mode = RecordingMode.DELEGATION
            self._start_recording()

    @Slot()
    def _on_file_transcribe_requested(self):
        """Handle double-tap Ctrl+F - transcribe audio file from clipboard"""
        print("[Daemon] File transcribe requested (double-tap Ctrl+F)")

        # Don't interrupt if already busy
        if self.state != DaemonState.IDLE:
            print(f"[Daemon] Cannot transcribe file - busy ({self.state.value})")
            return

        # Read clipboard
        try:
            clipboard_text = pyperclip.paste()
            if clipboard_text:
                clipboard_text = clipboard_text.strip()
        except Exception as e:
            print(f"[Daemon] Error reading clipboard: {e}")
            return

        if not clipboard_text:
            print("[Daemon] Clipboard is empty")
            return

        # Validate it's a file path that exists
        if not os.path.isfile(clipboard_text):
            print(f"[Daemon] Clipboard is not a valid file path: {clipboard_text[:80]}")
            return

        # Check file extension
        ext = os.path.splitext(clipboard_text)[1].lower()
        if ext not in SUPPORTED_AUDIO_FORMATS:
            print(f"[Daemon] Unsupported audio format: {ext}")
            print(f"[Daemon] Supported formats: {', '.join(SUPPORTED_AUDIO_FORMATS)}")
            return

        # Save frontmost app for auto-paste later
        try:
            from AppKit import NSWorkspace

            self._frontmost_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        except:
            self._frontmost_app = None

        # Set up for transcription
        print(f"[Daemon] Transcribing file: {clipboard_text}")
        self._current_audio_path = clipboard_text
        self._is_temp_file = False  # Don't delete user's file!
        self._transcribe_audio()

    @Slot()
    def _on_escape_pressed(self):
        """Handle Escape key - cancel recording but save the audio"""
        if self.state != DaemonState.RECORDING:
            return  # Only cancel if recording

        print("[Daemon] Escape pressed - cancelling recording (saving audio)")
        self._cancel_recording = True
        self.audio_recorder.stop_recording()

    @Slot()
    def _on_undo_cancel(self):
        """Handle undo request - transcribe the cancelled recording"""
        if not self._cancelled_audio_path or not os.path.exists(
            self._cancelled_audio_path
        ):
            print("[Daemon] No cancelled recording to undo")
            self.indicator.show_idle()
            return

        print(f"[Daemon] Undo cancel - transcribing: {self._cancelled_audio_path}")
        self._current_audio_path = self._cancelled_audio_path
        self._cancelled_audio_path = None
        self._is_temp_file = True
        self._transcribe_audio()

    def _start_recording(self):
        """Start audio recording"""
        self._cancel_recording = False  # Reset cancel flag
        self._is_temp_file = True  # Recording creates temp file

        # Clean up any pending cancelled audio (undo timed out)
        if self._cancelled_audio_path and os.path.exists(self._cancelled_audio_path):
            try:
                os.remove(self._cancelled_audio_path)
                print(
                    f"[Daemon] Cleaned up expired cancelled recording: {self._cancelled_audio_path}"
                )
            except Exception as e:
                print(f"[Daemon] Could not clean up cancelled recording: {e}")
        self._cancelled_audio_path = None

        if not self._model_loaded:
            print("[Daemon] Model not loaded, cannot record")
            self.error_occurred.emit("Model not loaded")
            return

        print("[Daemon] Starting recording...")

        # Reuse streaming transcriber (avoid re-creating VAD model each time)
        language = self.config_manager.get("transcription_language", "en")
        if language == "auto":
            language = "en"
        if self._streaming_transcriber is None or self._streaming_language != language:
            self._streaming_transcriber = StreamingTranscriber(
                self.transcription_service, language=language
            )
            self._streaming_language = language
        self._streaming_transcriber.start_session()

        self.state = DaemonState.RECORDING
        self.audio_recorder.start_recording()

        # Preload LLM in background while recording (if enabled)
        if self.post_processor.enabled:
            self.post_processor.preload_async()

    def _stop_recording(self):
        """Stop audio recording - will trigger transcription"""
        if self.state != DaemonState.RECORDING:
            print(f"[Daemon] _stop_recording called but state is {self.state.value}, ignoring")
            return
        print("[Daemon] Stopping recording...")
        self._post_process_this_transcription = False
        # Set state immediately to prevent double-stop from rapid Ctrl+F presses
        self.state = DaemonState.TRANSCRIBING
        self.audio_recorder.stop_recording()

    @Slot()
    def _on_recording_started(self):
        """Handle recording started signal"""
        if self._perf:
            self._perf.recording_started = time.time()
        print("[Daemon] Recording started")
        self.state = DaemonState.RECORDING

    @Slot(str)
    def _on_recording_stopped(self, audio_path_or_message: str):
        """Handle recording stopped signal"""
        if self._perf:
            self._perf.recording_stopped = time.time()
        print(f"[Daemon] Recording stopped: {audio_path_or_message}")

        # Wait for recorder thread to fully stop
        if self.audio_recorder.isRunning():
            self.audio_recorder.wait(2000)

        # Check if we got a valid audio path
        if audio_path_or_message and os.path.exists(audio_path_or_message):
            # Check if recording was cancelled
            if self._cancel_recording:
                self._cancel_recording = False
                # Keep the audio file for potential undo
                self._cancelled_audio_path = audio_path_or_message
                self._is_temp_file = True
                # Stop streaming transcriber without using results
                if self._streaming_transcriber:
                    self._streaming_transcriber.cancel()
                    self._streaming_transcriber = None
                print(f"[Daemon] Recording cancelled, undo available for 10s")
                self.state = DaemonState.IDLE
                # Show cancelled state with undo option
                self.indicator.show_cancelled()
            else:
                self._current_audio_path = audio_path_or_message
                # Use streaming transcriber if it has been processing segments
                if self._streaming_transcriber:
                    self._transcribe_streaming()
                else:
                    self._transcribe_audio()
        else:
            print(f"[Daemon] No valid audio file: {audio_path_or_message}")
            if self._streaming_transcriber:
                self._streaming_transcriber.cancel()
            self.state = DaemonState.IDLE

    def _save_cancelled_recording(self, audio_path: str):
        """Save a cancelled recording to the recordings folder"""
        try:
            import shutil
            from datetime import datetime

            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.wav"
            dest_path = os.path.join(self._cancelled_recordings_dir, filename)

            # Copy the file
            shutil.copy2(audio_path, dest_path)
            print(f"[Daemon] Cancelled recording saved to: {dest_path}")

            # Clean up temp file
            os.remove(audio_path)

        except Exception as e:
            print(f"[Daemon] Error saving cancelled recording: {e}")

    @Slot(str)
    def _on_recorder_error(self, error_msg: str):
        """Handle recorder error"""
        print(f"[Daemon] Recorder error: {error_msg}")
        self.indicator.play_error_sound()
        self.error_occurred.emit(error_msg)
        self.state = DaemonState.ERROR
        # Try to recover after a delay
        QTimer.singleShot(1000, lambda: self._set_state_if_error(DaemonState.IDLE))

    def _set_state_if_error(self, new_state: DaemonState):
        """Set state only if currently in error state"""
        if self.state == DaemonState.ERROR:
            self.state = new_state

    def _transcribe_streaming(self):
        """Flush the streaming transcriber and handle the result.

        Most of the audio was already transcribed during recording.
        This only processes the final untranscribed segment.
        """
        print("[Daemon] Flushing streaming transcriber...")
        self.state = DaemonState.TRANSCRIBING

        if self._perf:
            self._perf.transcribe_start = time.time()
            self._perf.used_streaming = True
            self._perf.used_vad = self._streaming_transcriber._vad is not None
            with self._streaming_transcriber._transcribe_lock:
                self._perf.streaming_segments = len(self._streaming_transcriber._confirmed_texts)

        try:
            flush_start = time.time()
            text = self._streaming_transcriber.flush()
            flush_elapsed = time.time() - flush_start
            print(f"[Daemon] Streaming flush took {flush_elapsed:.2f}s")

            if self._perf:
                self._perf.streaming_flush_time = flush_elapsed
                self._perf.transcribe_end = time.time()

            if text:
                print(f"[Daemon] Streaming transcription: '{text}'")
                self._handle_transcription_result(text)
                self._cleanup_audio_file()
            else:
                print("[Daemon] Streaming produced no text, falling back to full transcription")
                if self._perf:
                    self._perf.used_streaming = False
                self._transcribe_audio()

        except Exception as e:
            print(f"[Daemon] Streaming transcription error: {e}")
            self._streaming_transcriber = None  # discard on error
            if self._perf:
                self._perf.used_streaming = False
            self._transcribe_audio()

    def _transcribe_audio(self):
        """Transcribe the recorded audio (file-based fallback)"""
        if not self._current_audio_path:
            print("[Daemon] No audio path to transcribe")
            self.state = DaemonState.IDLE
            return

        print(f"[Daemon] Transcribing: {self._current_audio_path}")
        self.state = DaemonState.TRANSCRIBING

        if self._perf and not self._perf.transcribe_start:
            self._perf.transcribe_start = time.time()

        try:
            # Get language setting
            language = self.config_manager.get("transcription_language", None)
            if language == "auto":
                language = None

            # Progress callback to update indicator
            def progress_callback(percentage, text, lang_info):
                self.indicator.update_progress(percentage)
                # Force UI update during long transcriptions
                QApplication.processEvents()

            # Transcribe with progress
            result = self.transcription_service.transcribe(
                self._current_audio_path,
                language=language,
                beam_size=1,  # Fast mode
                progress_callback=progress_callback,
            )

            if result and result.get("text"):
                text = result["text"].strip()
                if self._perf:
                    self._perf.transcribe_end = time.time()
                print(f"[Daemon] Transcription complete: '{text[:50]}...'")
                self._handle_transcription_result(text)
            else:
                print("[Daemon] Transcription returned no text")
                self.state = DaemonState.IDLE

        except Exception as e:
            print(f"[Daemon] Transcription error: {e}")
            self.error_occurred.emit(str(e))
            self.state = DaemonState.ERROR
            QTimer.singleShot(1000, lambda: self._set_state_if_error(DaemonState.IDLE))
        finally:
            # Clean up temp audio file
            self._cleanup_audio_file()

    def _handle_transcription_result(self, text: str):
        """Handle successful transcription - output depends on recording mode"""
        if self._perf:
            self._perf.text_length = len(text)

        # Store original for diff view
        self._last_original_text = text
        self._last_processed_text = text  # default: same as original

        # Apply post-processing if enabled globally OR triggered with double Ctrl+F
        should_post_process = self.post_processor.enabled or self._post_process_this_transcription
        if should_post_process:
            trigger = "double-Ctrl+F" if self._post_process_this_transcription else "always-on"
            print(f"[Daemon] Applying post-processing ({trigger})...")
            # Temporarily enable if triggered on-demand
            was_enabled = self.post_processor.enabled
            if not was_enabled:
                self.post_processor._enabled = True
            text = self.post_processor.process(text)
            if not was_enabled:
                self.post_processor._enabled = False
            self._last_processed_text = text
            print(f"[Daemon] Post-processed: '{text}'")
            if self._perf:
                self._perf.post_process_end = time.time()

        # Record completion time for diff view window
        self._last_transcription_time = time.time()
        # Reset per-transcription flag
        self._post_process_this_transcription = False

        # Branch based on recording mode
        if self._recording_mode == RecordingMode.DELEGATION:
            self._handle_delegation_output(text)
        else:
            self._handle_normal_output(text)

        # Log performance summary
        if self._perf:
            self._perf.log_summary()
            self._perf = None

        # Reset mode for next recording
        self._recording_mode = RecordingMode.NORMAL

    def _handle_normal_output(self, text: str):
        """Normal mode output: clipboard + auto-paste"""
        # Copy to clipboard
        try:
            pyperclip.copy(text)
            if self._perf:
                self._perf.clipboard_done = time.time()
            print("[Daemon] Text copied to clipboard")
        except Exception as e:
            print(f"[Daemon] Clipboard error: {e}")

        # Emit signal
        self.transcription_complete.emit(text)

        # Return to idle FIRST (before pasting to avoid indicator focus issues)
        self.state = DaemonState.IDLE

        # Auto-paste using Cmd+V simulation
        QApplication.processEvents()  # let indicator update before paste
        self._auto_paste()
        if self._perf:
            self._perf.paste_done = time.time()

    def _handle_delegation_output(self, text: str):
        """Delegation mode output: save to cc-triage inbox, no auto-paste"""
        print(f"[Daemon] Delegation mode: '{text[:50]}...'")

        # Save to cc-triage inbox
        filepath = self._save_delegation(text)

        # Track delegation AFTER file write completes (race condition guard)
        if filepath:
            filename = os.path.basename(filepath)
            pip = self.indicator.add_delegation_pip()
            self._delegation_pips[filename] = pip
            self.delegation_tracker.track(filename)
            print(f"[Daemon] Delegation tracked: {filename}")

        # Also copy to clipboard (useful but don't auto-paste)
        try:
            pyperclip.copy(text)
            if self._perf:
                self._perf.clipboard_done = time.time()
                self._perf.paste_done = time.time()  # no auto-paste in delegation
            print("[Daemon] Text also copied to clipboard")
        except Exception as e:
            print(f"[Daemon] Clipboard error: {e}")

        # Emit signal
        self.transcription_complete.emit(text)

        # Return to idle
        self.state = DaemonState.IDLE

        if filepath:
            print(f"[Daemon] Delegation saved to: {filepath}")

    def _save_delegation(self, text: str) -> str:
        """
        Save delegation text to cc-triage inbox.

        Returns the filepath where the delegation was saved, or None on error.

        Path is configurable via settings.json key "delegation_path".
        cc-triage daemon watches this directory and routes the transcript.
        """
        from datetime import datetime

        # Get cc-triage inbox directory from config
        capture_dir = self.config_manager.get(
            "delegation_path", "/Users/blake/projects/cc-triage/inbox/"
        )
        capture_dir = os.path.expanduser(capture_dir)
        os.makedirs(capture_dir, exist_ok=True)

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"delegation_{timestamp}.txt"
        filepath = os.path.join(capture_dir, filename)

        try:
            with open(filepath, "w") as f:
                f.write(text)
            print(f"[Daemon] Delegation saved to: {filepath}")
            return filepath
        except Exception as e:
            print(f"[Daemon] Error saving delegation: {e}")
            return None

    @Slot(str, str)
    def _on_delegation_state_changed(self, delegation_id: str, new_state: str):
        """Handle delegation state change — update the corresponding pip."""
        pip = self._delegation_pips.get(delegation_id)
        if not pip:
            print(f"[Daemon] No pip found for delegation {delegation_id}, ignoring state {new_state}")
            return

        print(f"[Daemon] Delegation pip update: {delegation_id} -> {new_state}")
        pip.set_state(new_state)

        # Clean up pip reference on terminal states (pip auto-removes via finished signal)
        if new_state in ("complete", "failed"):
            self._delegation_pips.pop(delegation_id, None)

    def _auto_paste(self):
        """Simulate Cmd+V to paste at cursor"""
        try:
            # First, restore focus to the original app
            if hasattr(self, "_frontmost_app") and self._frontmost_app:
                try:
                    self._frontmost_app.activateWithOptions_(0)
                    time.sleep(0.15)  # Give time for app to become active
                    print(
                        f"[Daemon] Restored focus to: {self._frontmost_app.localizedName()}"
                    )
                except Exception as e:
                    print(f"[Daemon] Could not restore focus: {e}")

            # Small delay to ensure focus is settled
            time.sleep(0.1)

            # Use pynput to simulate Cmd+V
            from pynput.keyboard import Controller, Key

            keyboard = Controller()

            # Press Cmd+V
            keyboard.press(Key.cmd)
            keyboard.press("v")
            keyboard.release("v")
            keyboard.release(Key.cmd)

            print("[Daemon] Auto-paste executed (Cmd+V)")

        except Exception as e:
            print(f"[Daemon] Auto-paste error: {e}")
            print("[Daemon] Text is in clipboard - use Cmd+V to paste manually")

    def _cleanup_audio_file(self):
        """Clean up temporary audio file (only if it's a temp file, not user's file)"""
        if self._current_audio_path and os.path.exists(self._current_audio_path):
            if self._is_temp_file:
                try:
                    os.remove(self._current_audio_path)
                    print(f"[Daemon] Cleaned up temp file: {self._current_audio_path}")
                except Exception as e:
                    print(f"[Daemon] Could not clean up temp file: {e}")
            else:
                print(f"[Daemon] Keeping user file: {self._current_audio_path}")
        self._current_audio_path = None
        self._is_temp_file = True  # Reset for next operation

    @Slot(DaemonState)
    def _update_indicator(self, state: DaemonState):
        """Update the floating indicator based on state"""
        if state == DaemonState.RECORDING:
            self.indicator.show_recording(mode=self._recording_mode.value)
        elif state == DaemonState.TRANSCRIBING:
            self.indicator.show_transcribing()
        else:
            # Return to idle (always visible, collapsed)
            self.indicator.show_idle()

    @classmethod
    def is_running(cls) -> bool:
        """Check if daemon is already running"""
        if os.path.exists(cls.PID_FILE):
            try:
                with open(cls.PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                # Check if process is actually running
                os.kill(pid, 0)  # Doesn't kill, just checks if exists
                return True
            except (ProcessLookupError, ValueError, FileNotFoundError):
                # Process not running or invalid PID
                return False
        return False

    @classmethod
    def get_pid(cls) -> int:
        """Get the PID of the running daemon"""
        if os.path.exists(cls.PID_FILE):
            try:
                with open(cls.PID_FILE, "r") as f:
                    return int(f.read().strip())
            except (ValueError, FileNotFoundError):
                pass
        return None


def run_daemon():
    """Main entry point for the daemon"""
    # Check if already running
    if WhisperDaemon.is_running():
        print("Whisper daemon is already running!")
        print(f"PID: {WhisperDaemon.get_pid()}")
        sys.exit(1)

    # Create Qt application (needed for signals/slots and UI)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running even when indicator hides

    # Prevent app from appearing in Dock and App Switcher (Alt+Tab) on macOS
    # MUST be set AFTER QApplication is created
    try:
        from AppKit import NSApp, NSApplication

        # NSApplicationActivationPolicyAccessory = 1 (hidden from dock, but windows still visible)
        NSApp.setActivationPolicy_(1)
        print(
            "[Daemon] Set activation policy to Accessory (hidden from dock, windows visible)"
        )
    except Exception as e:
        print(f"[Daemon] Warning: Could not set activation policy: {e}")

    # Create daemon
    daemon = WhisperDaemon()

    # Flag for shutdown
    shutdown_requested = [False]

    # Handle signals for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[Daemon] Received signal {signum}, shutting down...")
        shutdown_requested[0] = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Timer to check for shutdown requests (needed because Qt blocks signal delivery)
    def check_shutdown():
        if shutdown_requested[0]:
            print("[Daemon] Performing graceful shutdown...")
            daemon.stop()
            app.quit()

    shutdown_timer = QTimer()
    shutdown_timer.timeout.connect(check_shutdown)
    shutdown_timer.start(100)  # Check every 100ms

    # Start daemon
    daemon.start()

    # Run event loop
    sys.exit(app.exec())


def stop_daemon():
    """Stop a running daemon"""
    if not WhisperDaemon.is_running():
        print("Whisper daemon is not running.")
        return

    pid = WhisperDaemon.get_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to daemon (PID: {pid})")
            # Wait a bit for graceful shutdown
            time.sleep(1)
            # Check if still running
            try:
                os.kill(pid, 0)
                # Still running, send SIGKILL
                os.kill(pid, signal.SIGKILL)
                print("Daemon didn't stop gracefully, sent SIGKILL")
            except ProcessLookupError:
                print("Daemon stopped successfully.")
        except ProcessLookupError:
            print("Daemon process not found.")
        except PermissionError:
            print("Permission denied to stop daemon.")


def status_daemon():
    """Check daemon status"""
    if WhisperDaemon.is_running():
        pid = WhisperDaemon.get_pid()
        print(f"Whisper daemon is RUNNING (PID: {pid})")
    else:
        print("Whisper daemon is NOT running.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Whisper Daemon - Quick Transcription Service"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "stop", "status", "restart"],
        help="Command to run (default: start)",
    )

    args = parser.parse_args()

    if args.command == "start":
        run_daemon()
    elif args.command == "stop":
        stop_daemon()
    elif args.command == "status":
        status_daemon()
    elif args.command == "restart":
        stop_daemon()
        time.sleep(1)
        run_daemon()
