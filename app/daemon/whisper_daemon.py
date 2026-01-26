#!/usr/bin/env python3
"""
Whisper Daemon - Background service for instant transcription

This daemon:
1. Keeps the Whisper model pre-loaded in memory
2. Listens for global hotkey (Ctrl+F) to toggle recording
3. Shows a floating indicator during recording
4. Auto-pastes transcription to the active application
"""

import sys
import os
import signal
import json
import tempfile
import time
from enum import Enum
from pathlib import Path

# Unbuffered output for daemon logging
sys.stdout = sys.stderr  # Redirect stdout to stderr for immediate output
os.environ['PYTHONUNBUFFERED'] = '1'

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Slot, QTimer

from app.core.transcription_service_cpp import WhisperCppService, get_transcription_service
from app.core.audio_recorder import AudioRecorder
from app.core.post_processor import get_post_processor
from app.utils.config_manager import ConfigManager
from app.daemon.recording_indicator import RecordingIndicator
from app.daemon.hotkey_listener import HotkeyListener

import pyperclip


class DaemonState(Enum):
    """State machine for the daemon"""
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


class RecordingMode(Enum):
    """Mode determines output handling after transcription"""
    NORMAL = "normal"         # Ctrl+F: clipboard + auto-paste
    ISSUE_CAPTURE = "issue"   # Option+F: capture to file


# Supported audio/video formats for file transcription
SUPPORTED_AUDIO_FORMATS = (
    '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.webm',
    '.mp4', '.m4v', '.mov', '.aac', '.wma'
)


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
        self._is_temp_file = True  # Whether current audio is temp (should be deleted after)
        self._recording_mode = RecordingMode.NORMAL  # Mode for current recording session

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
        self.hotkey_listener.file_transcribe_requested.connect(self._on_file_transcribe_requested)
        self.hotkey_listener.escape_pressed.connect(self._on_escape_pressed)
        self.hotkey_listener.issue_capture_requested.connect(self._on_issue_capture_hotkey)

        # Directory for cancelled recordings
        self._cancelled_recordings_dir = os.path.expanduser("~/Documents/WhisperRecordings")
        os.makedirs(self._cancelled_recordings_dir, exist_ok=True)

        # Track cancelled recording for undo functionality
        self._cancelled_audio_path = None

        # Connect state changes to indicator
        self.state_changed.connect(self._update_indicator)

        # Model loading state
        self._model_loaded = False
        self._model_loading = False

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
        self.indicator.issue_capture_requested.connect(self._on_issue_capture_hotkey)
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
        """Handle new audio chunk for waveform visualization"""
        self.indicator.update_waveform(chunk)

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
        print("[Daemon] Starting whisper daemon...")

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
        print("[Daemon]   Option+F: Toggle recording (issue capture mode)")
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
            with open(self.PID_FILE, 'w') as f:
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
            model_name = self.config_manager.get("transcription_model_name", "base")
            device = self.config_manager.get("transcription_device", "cpu")
            compute_type = self.config_manager.get("transcription_compute_type", "int8")

            # Update indicator with current model
            self.indicator.set_current_model(model_name)

            # Set config and load
            self.transcription_service.set_target_model_config(model_name, device, compute_type)
            self.transcription_service._load_model()

            if self.transcription_service.model is not None:
                self._model_loaded = True
                print(f"[Daemon] Model '{model_name}' loaded successfully!")
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
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
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
    def _on_issue_capture_hotkey(self):
        """Handle Option+F hotkey press - toggle recording (issue capture mode)"""
        print(f"[Daemon] Issue capture hotkey triggered! Current state: {self.state.value}")

        # Save the frontmost app BEFORE we do anything
        try:
            from AppKit import NSWorkspace
            self._frontmost_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        except:
            self._frontmost_app = None

        if self.state == DaemonState.IDLE:
            self._recording_mode = RecordingMode.ISSUE_CAPTURE
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            self._stop_recording()
        elif self.state == DaemonState.TRANSCRIBING:
            print("[Daemon] Already transcribing, please wait...")
        elif self.state == DaemonState.ERROR:
            print("[Daemon] Attempting to recover from error state...")
            self.state = DaemonState.IDLE
            self._recording_mode = RecordingMode.ISSUE_CAPTURE
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
        if not self._cancelled_audio_path or not os.path.exists(self._cancelled_audio_path):
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
                print(f"[Daemon] Cleaned up expired cancelled recording: {self._cancelled_audio_path}")
            except Exception as e:
                print(f"[Daemon] Could not clean up cancelled recording: {e}")
        self._cancelled_audio_path = None

        if not self._model_loaded:
            print("[Daemon] Model not loaded, cannot record")
            self.error_occurred.emit("Model not loaded")
            return

        print("[Daemon] Starting recording...")
        self.state = DaemonState.RECORDING
        self.audio_recorder.start_recording()

        # Preload LLM in background while recording (if enabled)
        if self.post_processor.enabled:
            self.post_processor.preload_async()

    def _stop_recording(self):
        """Stop audio recording - will trigger transcription"""
        print("[Daemon] Stopping recording...")
        self.audio_recorder.stop_recording()
        # State will be updated in _on_recording_stopped

    @Slot()
    def _on_recording_started(self):
        """Handle recording started signal"""
        print("[Daemon] Recording started")
        self.state = DaemonState.RECORDING

    @Slot(str)
    def _on_recording_stopped(self, audio_path_or_message: str):
        """Handle recording stopped signal"""
        print(f"[Daemon] Recording stopped: {audio_path_or_message}")

        # Wait for recorder thread to fully stop
        if self.audio_recorder.isRunning():
            self.audio_recorder.wait(2000)

        # Check if we got a valid audio path
        if audio_path_or_message and os.path.exists(audio_path_or_message):
            # Check if recording was cancelled
            if getattr(self, '_cancel_recording', False):
                self._cancel_recording = False
                # Keep the audio file for potential undo
                self._cancelled_audio_path = audio_path_or_message
                self._is_temp_file = True
                print(f"[Daemon] Recording cancelled, undo available for 10s")
                self.state = DaemonState.IDLE
                # Show cancelled state with undo option
                self.indicator.show_cancelled()
            else:
                self._current_audio_path = audio_path_or_message
                self._transcribe_audio()
        else:
            print(f"[Daemon] No valid audio file: {audio_path_or_message}")
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

    def _transcribe_audio(self):
        """Transcribe the recorded audio"""
        if not self._current_audio_path:
            print("[Daemon] No audio path to transcribe")
            self.state = DaemonState.IDLE
            return

        print(f"[Daemon] Transcribing: {self._current_audio_path}")
        self.state = DaemonState.TRANSCRIBING

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
                progress_callback=progress_callback
            )

            if result and result.get("text"):
                text = result["text"].strip()
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
        # Apply post-processing if enabled
        if self.post_processor.enabled:
            print("[Daemon] Applying post-processing...")
            text = self.post_processor.process(text)
            print(f"[Daemon] Post-processed: '{text[:50]}...'")

        # Branch based on recording mode
        if self._recording_mode == RecordingMode.ISSUE_CAPTURE:
            self._handle_issue_capture_output(text)
        else:
            self._handle_normal_output(text)

        # Reset mode for next recording
        self._recording_mode = RecordingMode.NORMAL

    def _handle_normal_output(self, text: str):
        """Normal mode output: clipboard + auto-paste"""
        # Copy to clipboard
        try:
            pyperclip.copy(text)
            print("[Daemon] Text copied to clipboard")
        except Exception as e:
            print(f"[Daemon] Clipboard error: {e}")

        # Emit signal
        self.transcription_complete.emit(text)

        # Return to idle FIRST (before pasting to avoid indicator focus issues)
        self.state = DaemonState.IDLE

        # Small delay to let indicator settle
        time.sleep(0.05)

        # Auto-paste using Cmd+V simulation
        self._auto_paste()

    def _handle_issue_capture_output(self, text: str):
        """Issue capture mode output: save to file, no auto-paste"""
        print(f"[Daemon] Issue capture mode: '{text[:50]}...'")

        # Capture to file
        filepath = self._capture_issue(text)

        # Also copy to clipboard (useful but don't auto-paste)
        try:
            pyperclip.copy(text)
            print("[Daemon] Text also copied to clipboard")
        except Exception as e:
            print(f"[Daemon] Clipboard error: {e}")

        # Emit signal
        self.transcription_complete.emit(text)

        # Return to idle
        self.state = DaemonState.IDLE

        if filepath:
            print(f"[Daemon] Issue captured successfully to: {filepath}")

    def _capture_issue(self, text: str) -> str:
        """
        Capture issue text to file.

        Returns the filepath where the issue was saved, or None on error.

        Path is configurable via settings.json key "issue_capture_path".
        Future: Could integrate with GitHub Issues, Linear, Jira, etc.
        """
        from datetime import datetime

        # Get capture directory from config (default: ~/Documents/WhisperIssues)
        capture_dir = self.config_manager.get("issue_capture_path", "~/Documents/WhisperIssues")
        capture_dir = os.path.expanduser(capture_dir)
        os.makedirs(capture_dir, exist_ok=True)

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"issue_{timestamp}.txt"
        filepath = os.path.join(capture_dir, filename)

        try:
            with open(filepath, 'w') as f:
                f.write(text)
            print(f"[Daemon] Issue saved to: {filepath}")
            return filepath
        except Exception as e:
            print(f"[Daemon] Error saving issue: {e}")
            return None

    def _auto_paste(self):
        """Simulate Cmd+V to paste at cursor"""
        try:
            # First, restore focus to the original app
            if hasattr(self, '_frontmost_app') and self._frontmost_app:
                try:
                    self._frontmost_app.activateWithOptions_(0)
                    time.sleep(0.15)  # Give time for app to become active
                    print(f"[Daemon] Restored focus to: {self._frontmost_app.localizedName()}")
                except Exception as e:
                    print(f"[Daemon] Could not restore focus: {e}")

            # Small delay to ensure focus is settled
            time.sleep(0.1)

            # Use pynput to simulate Cmd+V
            from pynput.keyboard import Controller, Key
            keyboard = Controller()

            # Press Cmd+V
            keyboard.press(Key.cmd)
            keyboard.press('v')
            keyboard.release('v')
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
                with open(cls.PID_FILE, 'r') as f:
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
                with open(cls.PID_FILE, 'r') as f:
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
        from AppKit import NSApplication, NSApp
        # NSApplicationActivationPolicyAccessory = 1 (hidden from dock, but windows still visible)
        NSApp.setActivationPolicy_(1)
        print("[Daemon] Set activation policy to Accessory (hidden from dock, windows visible)")
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

    parser = argparse.ArgumentParser(description="Whisper Daemon - Quick Transcription Service")
    parser.add_argument("command", nargs="?", default="start",
                       choices=["start", "stop", "status", "restart"],
                       help="Command to run (default: start)")

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
