# Placeholder for main_window.py 

import sys
from PySide6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QTextEdit, QProgressBar, QComboBox
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPoint, QEvent, QThreadPool
from PySide6.QtGui import QKeySequence, QShortcut, QColor
import numpy as np
import os # Added for os.remove
import pyperclip # For clipboard
import subprocess # For running paste command

from .waveform_widget import WaveformWidget, WaveformStatus
from app.core.audio_recorder import AudioRecorder # Import AudioRecorder
from app.core.transcription_service import TranscriptionService
from .workers import TranscriptionWorker

# from app.utils.config_manager import ConfigManager # Will be used later

class AppState:
    IDLE = 0
    RECORDING = 1
    PAUSED = 2
    # States for managing transitions and post-recording actions
    CANCELLING = 3 # Recording is stopping, will delete file
    STOPPING_FOR_ACTION = 4 # Generic stopping before a post-action
    TRANSCRIBING = 5 # Whisper service will be triggered
    FABRIC_PROCESSING = 6 # Fabric post-processing will be triggered

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Transcription UI")
        self.app_state = AppState.IDLE # Initialize app state
        self.last_saved_audio_path = None # To store path for post-processing
        self.close_after_transcription = False # New flag

        # Set window flags: frameless and always on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # Basic content for now
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        
        # Waveform display area
        self.waveform_widget = WaveformWidget()
        main_layout.addWidget(self.waveform_widget) # Add waveform widget to layout

        # Control buttons layout
        controls_layout = QHBoxLayout()
        self.rec_button = QPushButton("Rec")
        self.stop_button = QPushButton("Stop")
        self.pause_button = QPushButton("Pause")
        self.cancel_button = QPushButton("Cancel")
        self.transcribe_button = QPushButton("Transcribe")
        self.fabric_button = QPushButton("Fabric")

        self.rec_button.setToolTip("Start/Resume Recording (R)")
        self.stop_button.setToolTip("Stop Recording (S)")
        self.pause_button.setToolTip("Pause Recording (P)")
        self.cancel_button.setToolTip("Cancel Recording (C)")
        self.transcribe_button.setToolTip("Transcribe last recording, or current if active (T)")
        self.fabric_button.setToolTip("Process with Fabric last recording, or current if active (F)")

        self.rec_button.clicked.connect(self._on_rec_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.transcribe_button.clicked.connect(self._on_transcribe_keypress)
        self.fabric_button.clicked.connect(self._on_fabric_keypress)

        controls_layout.addWidget(self.rec_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.cancel_button)
        controls_layout.addWidget(self.transcribe_button)
        controls_layout.addWidget(self.fabric_button)
        main_layout.addLayout(controls_layout) # Add controls layout to main vertical layout

        # Status/Error Label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # Top bar layout for model selector and minimize button
        top_bar_layout = QHBoxLayout()
        
        # Model Size Selector
        self.model_label = QLabel("Model:")
        top_bar_layout.addWidget(self.model_label)
        
        self.model_size_selector = QComboBox()
        self.model_size_selector.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_size_selector.setCurrentText("base") # Default model
        self.current_model_size = self.model_size_selector.currentText()
        self.model_size_selector.setToolTip("Select Whisper model size for transcription")
        self.model_size_selector.currentTextChanged.connect(self._on_model_size_changed)
        top_bar_layout.addWidget(self.model_size_selector)
        
        top_bar_layout.addStretch() # Pushes minimize button to the right

        # Minimize button
        self.minimize_button = QPushButton("Min") # Renamed from "-"
        self.minimize_button.setToolTip("Minimize Window")
        self.minimize_button.setFixedSize(40, 28)
        self.minimize_button.clicked.connect(self.showMinimized)
        # Place minimize button in a dedicated layout if more top-bar controls are needed
        # For now, let's ensure it's distinct. A QHBoxLayout for top controls would be better.
        top_bar_layout.addWidget(self.minimize_button)
        main_layout.insertLayout(0, top_bar_layout) # Insert at the top

        # Initialize AudioRecorder
        self.audio_recorder = AudioRecorder(parent=self)
        self._connect_audio_recorder_signals()

        # Initialize TranscriptionService and thread pool
        self.transcription_service = TranscriptionService()
        self.thread_pool = QThreadPool.globalInstance()

        # Transcription display
        self.transcription_text = QTextEdit()
        self.transcription_text.setReadOnly(True)
        self.transcription_text.setPlaceholderText("Transcribed text will appear here...")
        main_layout.addWidget(self.transcription_text)

        # Progress bar for transcription
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        self._apply_button_styles() # Apply styles to all buttons
        self._apply_status_label_style()
        self._apply_control_specific_styles() # New method for model selector etc.
        self._update_ui_for_state() # Set initial UI state based on AppState.IDLE

        # Apply a base background color for Tokyo Night theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1b26;
                border: 1px solid #24283b; /* Subtle border */
            }
        """)

        self.minimize_button.setStyleSheet("""
            QPushButton {
                color: #c0caf5;
                background-color: #24283b; /* Slightly lighter than main bg */
                border: 1px solid #7aa2f7; /* A Tokyo Night blue for border */
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #414868; /* Darker accent for hover */
            }
            QPushButton:pressed {
                background-color: #7aa2f7; /* Blue when pressed */
                color: #1a1b26;
            }
        """)

        # Set initial size (can be configurable later)
        self.resize(350, 250) # Adjusted initial size for status label

        # Make the window draggable (since it's frameless)
        self._drag_pos = None

        # Keyboard Shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_R), self, self._on_rec_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self._on_stop_clicked)
        # Toggle pause/resume with P
        QShortcut(QKeySequence(Qt.Key.Key_P), self, self._on_pause_clicked) 
        QShortcut(QKeySequence(Qt.Key.Key_C), self, self._on_cancel_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, self._on_minimize_clicked)
        # New shortcuts for Transcribe and Fabric
        QShortcut(QKeySequence(Qt.Key.Key_T), self, self._on_transcribe_keypress)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._on_fabric_keypress)
        QShortcut(QKeySequence(Qt.Key.Key_Q), self, self.close) # Q to quit

    def _connect_audio_recorder_signals(self):
        self.audio_recorder.new_audio_chunk_signal.connect(self._handle_new_audio_chunk)
        self.audio_recorder.recording_started_signal.connect(self._handle_recording_started)
        self.audio_recorder.recording_stopped_signal.connect(self._handle_recording_stopped)
        self.audio_recorder.recording_paused_signal.connect(self._handle_recording_paused)
        self.audio_recorder.recording_resumed_signal.connect(self._handle_recording_resumed)
        self.audio_recorder.error_signal.connect(self._handle_audio_error)

    # --- AudioRecorder Signal Handlers ---
    def _handle_new_audio_chunk(self, audio_chunk):
        # print(f"UI: Received audio chunk. Shape: {audio_chunk.shape}, Min: {np.min(audio_chunk):.2f}, Max: {np.max(audio_chunk):.2f}, dtype: {audio_chunk.dtype}")
        if audio_chunk is not None and audio_chunk.size > 0:
            # Ensure audio_chunk is 1D for WaveformWidget
            if audio_chunk.ndim > 1:
                # Squeeze will remove single-dimensional entries from the shape
                # If shape is (N, 1) or (1, N), it becomes (N,)
                processed_chunk = np.squeeze(audio_chunk)
                # If after squeeze it's still not 1D (e.g. was (N, M) with M > 1), then it's an issue
                if processed_chunk.ndim != 1:
                    print(f"UI: Audio chunk has unexpected shape {audio_chunk.shape} after squeeze, not processing for waveform.")
                    return 
            else:
                processed_chunk = audio_chunk
            self.waveform_widget.update_waveform_data(processed_chunk)
            # else:
            # print("UI: Received empty or None audio chunk.")

    def _handle_recording_started(self):
        print("UI: Recording started")
        self._change_app_state(AppState.RECORDING)

    def _handle_recording_stopped(self, message_or_path):
        current_intended_next_state = getattr(self, 'pending_action', None)
        delattr(self, 'pending_action') if hasattr(self, 'pending_action') else None

        if self.app_state == AppState.CANCELLING:
            if os.path.exists(str(message_or_path)): # Check if it's a path
                try:
                    os.remove(str(message_or_path))
                    self._set_status_message("Recording cancelled and deleted.")
                    print(f"Canceled recording, deleted: {message_or_path}")
                except OSError as e:
                    self._set_status_message(f"Cancelled, but error deleting file: {e}", is_error=True)
                    print(f"Error deleting canceled file {message_or_path}: {e}")
            else: # Message might be an error or status
                self._set_status_message(f"Recording cancelled. ({message_or_path})")
            self.last_saved_audio_path = None
            self._change_app_state(AppState.IDLE)

        elif self.app_state == AppState.STOPPING_FOR_ACTION:
            self.last_saved_audio_path = None # Reset
            if os.path.exists(str(message_or_path)): # Successfully saved
                self.last_saved_audio_path = str(message_or_path)
                self._set_status_message(f"Recording saved: {os.path.basename(self.last_saved_audio_path)}")
                if current_intended_next_state == AppState.TRANSCRIBING:
                    self._change_app_state(AppState.TRANSCRIBING)
                elif current_intended_next_state == AppState.FABRIC_PROCESSING:
                    self._change_app_state(AppState.FABRIC_PROCESSING)
                else: # Normal stop
                    self._change_app_state(AppState.IDLE)
            else: # Failed to save or was stopped before data
                self._set_status_message(f"Recording stopped. ({message_or_path})", is_error=not "finished" in message_or_path.lower())
                self._change_app_state(AppState.IDLE)
        
        else: # Should be an unexpected case or a direct stop not through STOPPING_FOR_ACTION
             self._set_status_message(f"Recording stopped unexpectedly. Status: {message_or_path}")
             self.last_saved_audio_path = None
             self._change_app_state(AppState.IDLE)

    def _handle_recording_paused(self):
        print("UI: Recording paused")
        self._change_app_state(AppState.PAUSED)

    def _handle_recording_resumed(self):
        print("UI: Recording resumed")
        self._change_app_state(AppState.RECORDING)

    def _handle_audio_error(self, error_message):
        print(f"UI Audio Error: {error_message}")
        self._set_status_message(error_message, is_error=True)
        self._change_app_state(AppState.IDLE)

    # --- Button Click Handlers (now control AudioRecorder) ---
    def _on_rec_clicked(self):
        self._clear_status_message()
        self.close_after_transcription = False # Reset flag
        if self.app_state == AppState.IDLE:
            self.audio_recorder.start_recording()
        elif self.app_state == AppState.PAUSED:
            self.audio_recorder.resume_recording()

    def _on_stop_clicked(self):
        if self.app_state == AppState.RECORDING or self.app_state == AppState.PAUSED:
            self._set_status_message("Stopping recording...")
            # No specific post-action, just a normal stop.
            # We can use STOPPING_FOR_ACTION generally, or rely on _handle_recording_stopped to go to IDLE
            self._change_app_state(AppState.STOPPING_FOR_ACTION)
            self.audio_recorder.stop_recording()
            self._set_status_message("Stopping recording...") # Message for STOPPING_FOR_ACTION

    def _on_pause_clicked(self):
        self._clear_status_message()
        if self.app_state == AppState.RECORDING:
            self.audio_recorder.pause_recording()

    def _on_cancel_clicked(self):
        self._clear_status_message()
        self.close_after_transcription = False # Reset flag
        if self.app_state == AppState.RECORDING or self.app_state == AppState.PAUSED:
            self._change_app_state(AppState.CANCELLING)
            self.audio_recorder.stop_recording() # Corrected: No 'cancel' argument

    def _on_minimize_clicked(self):
        self.showMinimized()

    def _on_transcribe_keypress(self):
        if self.app_state == AppState.RECORDING or self.app_state == AppState.PAUSED:
            self.close_after_transcription = True # Set flag to close after this transcription
            self._change_app_state(AppState.STOPPING_FOR_ACTION)
            self._set_status_message("Stopping for Transcription...")
            self.pending_action = AppState.TRANSCRIBING # Store intended next state
            self.audio_recorder.stop_recording()
        elif self.app_state == AppState.IDLE and self.last_saved_audio_path:
            self.close_after_transcription = True # Set flag for re-processing too
            self._change_app_state(AppState.TRANSCRIBING)
            # Transcribe last saved file if idle and a path exists
        else:
            self.close_after_transcription = False # Ensure it's false if no action taken
            self._set_status_message("Not recording. Press R to record first.", is_error=True)

    def _on_fabric_keypress(self):
        self.close_after_transcription = False # Fabric does not close app for now
        if self.app_state == AppState.RECORDING or self.app_state == AppState.PAUSED:
            self._change_app_state(AppState.STOPPING_FOR_ACTION)
            self._set_status_message("Stopping for Fabric processing...")
            self.pending_action = AppState.FABRIC_PROCESSING # Store intended next state
            self.audio_recorder.stop_recording()
        elif self.app_state == AppState.IDLE and self.last_saved_audio_path:
            self._change_app_state(AppState.FABRIC_PROCESSING)
             # Process last saved file if idle and a path exists
        else:
            self.close_after_transcription = False # Ensure it's false if no action taken
            self._set_status_message("Not recording. Press R to record first.", is_error=True)

    def _change_app_state(self, new_state):
        if self.app_state == new_state and not (new_state == AppState.RECORDING and self.rec_button.text() == "Resume") : # allow re-setting RECORDING if resuming
            # avoid redundant UI updates if state is truly the same
            # but allow _update_ui_for_state to run if text needs to change (e.g. Resume to Rec)
            if not (self.app_state == AppState.PAUSED and new_state == AppState.RECORDING): # from pause to record
                 return

        print(f"Changing app state from {self.app_state} to {new_state}")
        old_state = self.app_state
        self.app_state = new_state
        self._update_ui_for_state(old_state)
        
        # Test timer already removed
        # if self._test_waveform_timer.isActive():
            # self._test_waveform_timer.stop()

    def _update_ui_for_state(self, old_state=None): # old_state can be used for more nuanced UI updates if needed
        if self.app_state == AppState.IDLE:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(True)
            self.rec_button.setText("Rec")
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(bool(self.last_saved_audio_path))
            self.fabric_button.setEnabled(bool(self.last_saved_audio_path))
            # Clear status message gently if it's not an error message
            if not self.status_label.property("is_error"):
                self._clear_status_message_after_delay()
        elif self.app_state == AppState.RECORDING:
            self.waveform_widget.set_status(WaveformStatus.RECORDING)
            self.rec_button.setEnabled(False) 
            self.rec_button.setText("Rec") # Keep it as Rec, just disabled
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(True)
            self.transcribe_button.setEnabled(True)
            self.fabric_button.setEnabled(True)
            self._set_status_message("Recording...")
        elif self.app_state == AppState.PAUSED:
            self.waveform_widget.set_status(WaveformStatus.IDLE) # Or a specific PAUSED color
            self.rec_button.setEnabled(True)
            self.rec_button.setText("Resume") 
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            # self.pause_button.setText("Resume") # Pause button does not resume in this logic
            self.cancel_button.setEnabled(True)
            self.transcribe_button.setEnabled(True)
            self.fabric_button.setEnabled(True)
            self._set_status_message("Paused.")
        elif self.app_state == AppState.CANCELLING:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self._set_status_message("Cancelling recording...")
        elif self.app_state == AppState.STOPPING_FOR_ACTION:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            # Specific message will be set by caller
            # self._set_status_message("Stopping for action...")
        elif self.app_state == AppState.TRANSCRIBING:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.model_size_selector.setEnabled(False) # Disable model selection during transcription
            self._set_status_message(f"Transcribing ({self.current_model_size}): {os.path.basename(self.last_saved_audio_path) if self.last_saved_audio_path else '...'}")
            
            # --- Reinstating TranscriptionWorker --- 
            if not self.last_saved_audio_path or not os.path.exists(self.last_saved_audio_path):
                self._handle_transcription_error("Audio file path is missing or invalid for transcription.")
                return
            if not hasattr(self, 'transcription_service') or self.transcription_service is None:
                self._handle_transcription_error("Transcription service not initialized.")
                return
            if not hasattr(self, 'thread_pool'):
                self._handle_transcription_error("Thread pool not initialized for transcription worker.")
                return
            
            # Ensure UI elements exist before trying to use them
            if hasattr(self, 'transcription_text'):
                self.transcription_text.clear()
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setValue(0)
                self.progress_bar.show()
            
            worker = TranscriptionWorker(
                transcription_service=self.transcription_service, 
                audio_path=self.last_saved_audio_path, 
                language=None, # Explicitly set language to None for auto-detection
                task="transcribe" # task is already a parameter in TranscriptionWorker
            )
            worker.signals.progress.connect(self._handle_transcription_progress)
            worker.signals.finished.connect(self._handle_transcription_finished)
            worker.signals.error.connect(self._handle_transcription_error)
            self.thread_pool.start(worker)
            # --- End Reinstating TranscriptionWorker ---
            
            # QTimer.singleShot(3000, lambda: self._post_action_cleanup(True, "Transcription complete (simulated).")) # This was the incorrect simulation

        elif self.app_state == AppState.FABRIC_PROCESSING:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            # self.model_size_selector.setEnabled(False) # Similarly for Fabric
            self._set_status_message(f"Fabric Processing: {os.path.basename(self.last_saved_audio_path) if self.last_saved_audio_path else '...'}")
            # Placeholder: Fabric processing (fuzzy search, etc.)
            # For now, simulate work and go back to IDLE
            QTimer.singleShot(3000, lambda: self._post_action_cleanup(True, "Fabric processing complete (simulated)."))

    def _apply_button_styles(self):
        button_style = """
            QPushButton {
                color: #c0caf5;
                background-color: #24283b;
                border: 1px solid #7aa2f7;
                padding: 5px;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: #414868;
            }
            QPushButton:pressed {
                background-color: #7aa2f7;
                color: #1a1b26;
            }
            QPushButton:disabled {
                background-color: #20202a;
                color: #50505a;
                border: 1px solid #40404a;
            }
        """
        self.rec_button.setStyleSheet(button_style)
        self.stop_button.setStyleSheet(button_style)
        self.pause_button.setStyleSheet(button_style)
        self.cancel_button.setStyleSheet(button_style)
        self.minimize_button.setStyleSheet(button_style)
        self.transcribe_button.setStyleSheet(button_style)
        self.fabric_button.setStyleSheet(button_style)
        self.minimize_button.setText("Min")
        self.minimize_button.setFixedSize(40, 28)

    def _apply_status_label_style(self):
        # Initial style, color will be set by _set_status_message
        self.status_label.setStyleSheet("color: #c0caf5; padding: 2px; min-height: 2em;") # min-height for 2 lines

    def _apply_control_specific_styles(self):
        self.model_label.setStyleSheet("color: #c0caf5; margin-right: 5px;")
        self.model_size_selector.setStyleSheet("""
            QComboBox {
                color: #c0caf5;
                background-color: #24283b;
                border: 1px solid #7aa2f7;
                padding: 3px 5px;
                min-width: 70px;
            }
            QComboBox:hover {
                background-color: #414868;
            }
            QComboBox:disabled {
                background-color: #20202a;
                color: #50505a;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 1px;
                border-left-color: #7aa2f7;
                border-left-style: solid;
            }
            /* Arrow styling can be tricky; often better to let Qt default handle it for consistency */
            /* QComboBox::down-arrow { image: url(path/to/your/arrow-icon.svg); } */
            QComboBox QAbstractItemView { /* The dropdown list itself */
                color: #c0caf5;
                background-color: #1a1b26; /* Same as main window background */
                border: 1px solid #7aa2f7; /* Consistent border */
                selection-background-color: #414868; /* Hover/selection in dropdown */
                outline: 0px; /* Removes focus dotted rect for a cleaner look */
            }
        """)
        # Minimize button styling is already applied directly in __init__ because it's more unique
        # If it were to become more standard, it could be moved here or to _apply_button_styles

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    def keyPressEvent(self, event: QEvent):
        # This method is now primarily for modifier keys or complex events
        # if simple shortcuts are handled by QShortcut.
        # We keep it for reference or future complex key handling.
        # Note: QShortcut handles most of these now.
        # Leaving the structure here for potential future use or if QShortcut fails for some reason.

        # Example: Allow Escape to close if not handled by QShortcut (it is)
        # if event.key() == Qt.Key.Key_Escape:
        #     self.close()
        #     return

        super().keyPressEvent(event) # Important to call base class

    def closeEvent(self, event):
        print("UI: Close event triggered. Stopping audio recorder.")
        # Assuming AudioRecorder manages its QThread instance as self.thread
        # and that self.audio_recorder.thread is accessible, or AudioRecorder
        # provides a method to check if its underlying thread is running.
        # If AudioRecorder itself is a QThread subclass, self.audio_recorder.isRunning() is fine.
        # For now, let's assume a direct isRunning() on the recorder object that proxies to its thread.
        # Or, more directly, just try to stop and wait.
        
        # Safest approach: just call stop and wait. The stop method should handle internal thread state.
        self.audio_recorder.stop_recording() # Ensure recording is stopped
        # The wait() call is crucial if AudioRecorder's operations (like saving file) happen in its thread.
        # If AudioRecorder is a QObject moved to a QThread, self.audio_recorder.thread.wait() might be needed
        # if wait() is not exposed on AudioRecorder itself. Assuming AudioRecorder handles this internally or is a QThread.
        if hasattr(self.audio_recorder, 'wait') and callable(self.audio_recorder.wait):
            self.audio_recorder.wait()
        elif hasattr(self.audio_recorder, 'thread') and hasattr(self.audio_recorder.thread, 'wait') and callable(self.audio_recorder.thread.wait):
             self.audio_recorder.thread.wait()
        super().closeEvent(event)

    def _set_status_message(self, message, is_error=False):
        self.status_label.setText(message)
        if is_error:
            self.status_label.setStyleSheet("color: #f7768e; margin: 2px;") # Tokyo Night Red
        else:
            self.status_label.setStyleSheet("color: #c0caf5; margin: 2px;") # Tokyo Night Text
        # Optionally, clear message after a delay for non-errors
        if not is_error and message: 
            QTimer.singleShot(5000, lambda: self.status_label.setText("") if self.status_label.text() == message else None)

    def _clear_status_message(self):
        self.status_label.setText("")

    def _post_action_cleanup(self, success, message):
        """Called after transcribe/fabric (simulated) to reset state."""
        if success:
            self._set_status_message(message)
            # Optionally delete self.last_saved_audio_path here if needed
            # For now, we keep it for potential re-processing
        else:
            self._set_status_message(message, is_error=True)
            # If the action failed, maybe we should delete the temp audio file?
            # if self.last_saved_audio_path and os.path.exists(self.last_saved_audio_path):
            #     try:
            #         os.remove(self.last_saved_audio_path)
            #         print(f"Cleaned up temp file: {self.last_saved_audio_path}")
            #         self.last_saved_audio_path = None
            #     except OSError as e:
            #         print(f"Error deleting temp file {self.last_saved_audio_path}: {e}")
        
        self._change_app_state(AppState.IDLE)

    def _clear_status_message_after_delay(self, delay_ms=3000):
        if hasattr(self, '_status_clear_timer') and self._status_clear_timer.isActive():
            self._status_clear_timer.stop()
        
        self._status_clear_timer = QTimer()
        self._status_clear_timer.setSingleShot(True)
        # Only clear if it's not an error and current message is the one we set
        # This check is tricky if messages update rapidly. A simpler approach is to clear if not an error.
        self._status_clear_timer.timeout.connect(lambda: {
            self.status_label.setText(""),
            self.status_label.setProperty("is_error", False) # Reset error state
        } if not self.status_label.property("is_error") else None)
        self._status_clear_timer.start(delay_ms)

    @Slot(int, str, dict)
    def _handle_transcription_progress(self, percentage, current_text, lang_info):
        # Update progress bar and transcription text
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        self.progress_bar.setValue(percentage)
        self.transcription_text.setPlainText(current_text)
        self._set_status_message(f"Transcribing... {percentage}%")

    @Slot(dict)
    def _handle_transcription_finished(self, result):
        self.progress_bar.hide()
        text = result.get("text", "")
        self.transcription_text.setPlainText(text)
        lang = result.get("detected_language")
        prob = result.get("language_probability")
        status_suffix = ""
        
        if text:
            try:
                pyperclip.copy(text)
                print("Transcription copied to clipboard.")
                paste_command = """
                osascript -e 'tell application "System Events" to keystroke "v" using command down'
                """
                subprocess.run(paste_command, shell=True, check=False)
                print("Paste command executed.")
                status_suffix = " (copied & pasted)"
            except Exception as e:
                print(f"Error with clipboard/paste: {e}")
                self._set_status_message(f"Transcription complete, but error with clipboard: {e}", is_error=True)
                status_suffix = " (clipboard error)"
        
        base_message = ""
        if lang:
            base_message = f"Transcription complete ({lang}: {prob:.2f})"
        else:
            base_message = "Transcription complete"
        
        final_ui_message = f"{base_message}{status_suffix}"

        if self.close_after_transcription:
            self.close_after_transcription = False # Reset flag immediately
            # Update status one last time before scheduling close
            self._set_status_message(f"{final_ui_message} Closing...", is_error="(clipboard error)" in status_suffix) 
            QTimer.singleShot(1200, self.close) # Slightly longer delay to read status
            # _post_action_cleanup will not be called to change state to IDLE if we are closing.
        else:
            self._post_action_cleanup(True, final_ui_message)

    @Slot(str)
    def _handle_transcription_error(self, error_message):
        self.progress_bar.hide()
        self.close_after_transcription = False # Reset flag on error
        self._post_action_cleanup(False, error_message)

    @Slot(str)
    def _on_model_size_changed(self, selected_model):
        self.current_model_size = selected_model
        print(f"UI: Model size changed to: {self.current_model_size}")
        if hasattr(self, 'transcription_service') and self.transcription_service is not None:
            # Call the new set_model method. Assuming default device and compute_type
            # unless we want to make those configurable in the UI as well.
            self.transcription_service.set_model(model_name=self.current_model_size)
        else:
            print("UI Warning: Transcription service not available to set model.")
        # Future: May trigger saving to config or notifying other components.

if __name__ == '__main__':
    # This is for testing the window directly
    # Ensure paths are correct if running directly, or run via app/main.py
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 
