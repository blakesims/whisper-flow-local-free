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

from app.core.transcription_service import TranscriptionService
from app.core.audio_recorder import AudioRecorder
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

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Initialize transcription service
        self.transcription_service = TranscriptionService(self.config_manager)

        # Initialize audio recorder
        self.audio_recorder = AudioRecorder()
        self._connect_recorder_signals()

        # Initialize UI indicator (always visible)
        self.indicator = RecordingIndicator()
        self._connect_indicator_signals()

        # Initialize hotkey listener
        self.hotkey_listener = HotkeyListener()
        self.hotkey_listener.hotkey_triggered.connect(self._on_hotkey_triggered)
        self.hotkey_listener.escape_pressed.connect(self._on_escape_pressed)

        # Directory for cancelled recordings
        self._cancelled_recordings_dir = os.path.expanduser("~/Documents/WhisperRecordings")
        os.makedirs(self._cancelled_recordings_dir, exist_ok=True)

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
        self.indicator.model_change_requested.connect(self._on_model_change_requested)
        self.indicator.quit_requested.connect(self._on_quit_requested)

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
        print("[Daemon] Indicator shown in idle state")

        # Load model synchronously on startup
        self._load_model()

        # Start hotkey listener
        self.hotkey_listener.start()
        print("[Daemon] Hotkey listener started (Ctrl+F to toggle recording)")
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
        """Handle hotkey press - toggle recording"""
        print(f"[Daemon] Hotkey triggered! Current state: {self.state.value}")

        # Save the frontmost app BEFORE we do anything
        # This ensures we can restore focus after showing indicator
        try:
            from AppKit import NSWorkspace
            self._frontmost_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        except:
            self._frontmost_app = None

        if self.state == DaemonState.IDLE:
            self._start_recording()
        elif self.state == DaemonState.RECORDING:
            self._stop_recording()
        elif self.state == DaemonState.TRANSCRIBING:
            print("[Daemon] Already transcribing, please wait...")
        elif self.state == DaemonState.ERROR:
            # Try to recover from error state
            print("[Daemon] Attempting to recover from error state...")
            self.state = DaemonState.IDLE
            self._start_recording()

    @Slot()
    def _on_escape_pressed(self):
        """Handle Escape key - cancel recording but save the audio"""
        if self.state != DaemonState.RECORDING:
            return  # Only cancel if recording

        print("[Daemon] Escape pressed - cancelling recording (saving audio)")
        self._cancel_recording = True
        self.audio_recorder.stop_recording()

    def _start_recording(self):
        """Start audio recording"""
        self._cancel_recording = False  # Reset cancel flag
        if not self._model_loaded:
            print("[Daemon] Model not loaded, cannot record")
            self.error_occurred.emit("Model not loaded")
            return

        print("[Daemon] Starting recording...")
        self.state = DaemonState.RECORDING
        self.audio_recorder.start_recording()

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
                self._save_cancelled_recording(audio_path_or_message)
                self._cancel_recording = False
                self.state = DaemonState.IDLE
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
        """Handle successful transcription - copy to clipboard and paste"""
        # Copy to clipboard
        try:
            pyperclip.copy(text)
            print("[Daemon] Text copied to clipboard")
        except Exception as e:
            print(f"[Daemon] Clipboard error: {e}")

        # Emit signal
        self.transcription_complete.emit(text)

        # Auto-paste using Cmd+V simulation
        self._auto_paste()

        # Return to idle
        self.state = DaemonState.IDLE

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
        """Clean up temporary audio file"""
        if self._current_audio_path and os.path.exists(self._current_audio_path):
            try:
                os.remove(self._current_audio_path)
                print(f"[Daemon] Cleaned up temp file: {self._current_audio_path}")
            except Exception as e:
                print(f"[Daemon] Could not clean up temp file: {e}")
        self._current_audio_path = None

    @Slot(DaemonState)
    def _update_indicator(self, state: DaemonState):
        """Update the floating indicator based on state"""
        if state == DaemonState.RECORDING:
            self.indicator.show_recording()
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
        # NSApplicationActivationPolicyProhibited = 2 (completely hidden from dock/switcher)
        NSApp.setActivationPolicy_(2)
        print("[Daemon] Set activation policy to Prohibited (hidden from Alt+Tab)")
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
