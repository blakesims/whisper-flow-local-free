# Placeholder for main_window.py 

import sys
from PySide6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QTextEdit, QProgressBar, QComboBox, QDialog, QFileDialog
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPoint, QEvent, QThreadPool
from PySide6.QtGui import QKeySequence, QShortcut, QColor
import numpy as np
import os # Added for os.remove
import pyperclip # For clipboard
import subprocess # For running paste command

from .waveform_widget import WaveformWidget, WaveformStatus
from app.core.audio_recorder import AudioRecorder # Import AudioRecorder
from app.core.transcription_service import TranscriptionService
from app.core.transcription_service_ext import TranscriptionServiceExt
from app.core.fabric_service import FabricService # <-- ADDED IMPORT
from .workers import TranscriptionWorker, FabricListPatternsWorker, LoadModelWorker, FabricRunPatternWorker # <-- IMPORTED LoadModelWorker, FabricRunPatternWorker
from .pattern_selection_dialog import PatternSelectionDialog # <-- IMPORTED PatternSelectionDialog
from .zoom_meeting_dialog import ZoomMeetingDialog # <-- IMPORTED ZoomMeetingDialog
from .meeting_worker import MeetingTranscriptionWorker # <-- IMPORTED MeetingTranscriptionWorker

# from app.utils.config_manager import ConfigManager # Will be used later

class AppState:
    IDLE = 0
    RECORDING = 1
    PAUSED = 2
    CANCELLING = 3 # Recording is stopping, will delete file
    STOPPING_FOR_ACTION = 4 # Generic stopping before a post-action
    TRANSCRIBING = 5 # Whisper service will be triggered
    FABRIC_PROCESSING = 6 # Fabric post-processing will be triggered
    PREPARING_FABRIC = 7      # New: Listing patterns, possibly transcribing for Fabric
    RUNNING_FABRIC_PATTERN = 8 # New: Executing the selected Fabric pattern
    MEETING_TRANSCRIBING = 9  # New: Transcribing meeting with multiple files

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Transcription UI")
        self.app_state = AppState.IDLE # Initialize app state
        self.last_saved_audio_path = None # To store path for post-processing
        self.close_after_transcription = False # New flag
        self.current_model_size = "base" # Initialize before model selector
        self.is_model_loading_busy = False # Flag for model loading
        
        # Meeting mode attributes
        self.meeting_audio_files = []  # List of selected audio files for meeting
        self.meeting_participant_names = []  # List of participant names
        self.is_meeting_mode = False  # Flag to track if we're in meeting mode

        # New attributes for Fabric workflow
        self.fabric_patterns = None
        self.selected_fabric_pattern = None
        self.last_transcribed_text_for_fabric = None
        self.pattern_selection_dialog = None
        self.is_transcribing_for_fabric = False
        # self.close_after_fabric = False # Decided against this for now

        # Set window flags: frameless and always on top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # Basic content for now
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        
        # Waveform display area
        self.waveform_widget = WaveformWidget()
        main_layout.addWidget(self.waveform_widget) # Add waveform widget to layout

        # Top bar layout for model selector and minimize button
        top_bar_layout = QHBoxLayout()
        
        # Model Size Selector
        self.model_label = QLabel("Model:")
        top_bar_layout.addWidget(self.model_label)
        
        self.model_size_selector = QComboBox()
        self.model_size_selector.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_size_selector.setCurrentText(self.current_model_size)
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

        # Control buttons layout
        controls_layout = QHBoxLayout()
        self.rec_button = QPushButton("Rec")
        self.stop_button = QPushButton("Stop")
        self.pause_button = QPushButton("Pause")
        self.cancel_button = QPushButton("Cancel")
        self.transcribe_button = QPushButton("Transcribe")
        self.fabric_button = QPushButton("Fabric")
        self.upload_button = QPushButton("Upload")
        self.meeting_button = QPushButton("Meeting")

        self.rec_button.setToolTip("Start/Resume Recording (R)")
        self.stop_button.setToolTip("Stop Recording (S)")
        self.pause_button.setToolTip("Pause Recording (P)")
        self.cancel_button.setToolTip("Cancel Recording (C)")
        self.transcribe_button.setToolTip("Transcribe last recording, or current if active (T)")
        self.fabric_button.setToolTip("Process with Fabric last recording, or current if active (F)")
        self.upload_button.setToolTip("Upload audio file for transcription (U)")
        self.meeting_button.setToolTip("Select Zoom meeting for summary (M)")

        self.rec_button.clicked.connect(self._on_rec_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.transcribe_button.clicked.connect(self._on_transcribe_keypress)
        self.fabric_button.clicked.connect(self._on_fabric_keypress)
        self.upload_button.clicked.connect(self._on_upload_clicked)
        self.meeting_button.clicked.connect(self._on_meeting_clicked)

        controls_layout.addWidget(self.rec_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.cancel_button)
        controls_layout.addWidget(self.transcribe_button)
        controls_layout.addWidget(self.fabric_button)
        controls_layout.addWidget(self.upload_button)
        controls_layout.addWidget(self.meeting_button)
        main_layout.addLayout(controls_layout)

        # Status/Error Label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # Initialize AudioRecorder
        self.audio_recorder = AudioRecorder(parent=self)
        self._connect_audio_recorder_signals()

        # Initialize TranscriptionService and thread pool
        self.transcription_service = TranscriptionServiceExt()  # Use extended service for timestamps
        self.fabric_service = FabricService() # <-- INITIALIZED SERVICE
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
        self.resize(450, 350) # Adjusted initial size for status label and extra buttons

        # Make the window draggable (since it's frameless)
        self._drag_pos = None

        # Keyboard Shortcuts
        self._setup_shortcuts()

        self._initiate_initial_model_load() # Trigger async model load

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key.Key_R), self, self._on_rec_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self._on_stop_clicked)
        # Toggle pause/resume with P
        QShortcut(QKeySequence(Qt.Key.Key_P), self, self._on_pause_clicked) 
        QShortcut(QKeySequence(Qt.Key.Key_C), self, self._on_cancel_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)
        # M is now used for Meeting, not minimize
        # New shortcuts for Transcribe and Fabric
        QShortcut(QKeySequence(Qt.Key.Key_T), self, self._on_transcribe_keypress)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._on_fabric_keypress)
        QShortcut(QKeySequence(Qt.Key.Key_U), self, self._on_upload_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_M), self, self._on_meeting_clicked)  # M for Meeting
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
                elif current_intended_next_state == AppState.PREPARING_FABRIC: # <-- MODIFIED for new state
                    self._change_app_state(AppState.PREPARING_FABRIC)
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

    def _on_upload_clicked(self):
        self._clear_status_message()
        self.close_after_transcription = False
        
        # Show file dialog to select audio file
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.webm);;All Files (*.*)"
        )
        
        if file_path and os.path.exists(file_path):
            self.last_saved_audio_path = file_path
            self._set_status_message(f"File selected: {os.path.basename(file_path)}")
            # Automatically start transcription
            self._change_app_state(AppState.TRANSCRIBING)
        elif file_path:
            self._set_status_message(f"File not found: {file_path}", is_error=True)
        else:
            self._set_status_message("No file selected.")

    def _on_meeting_clicked(self):
        self._clear_status_message()
        self.close_after_transcription = False
        self.is_meeting_mode = True
        
        # Show Zoom meeting selection dialog
        dialog = ZoomMeetingDialog(self)
        dialog.files_selected.connect(self._on_zoom_meeting_selected)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Files were selected, handled by signal
            pass
        else:
            # Dialog was cancelled
            self.is_meeting_mode = False
            self._set_status_message("Meeting selection cancelled.")
    
    def _on_zoom_meeting_selected(self, file_paths: list, participant_names: list):
        """Handle Zoom meeting selection from dialog."""
        if file_paths and len(file_paths) >= 2:
            self.meeting_audio_files = file_paths
            self.meeting_participant_names = participant_names  # Store participant names
            
            self._set_status_message(f"Selected meeting with {len(file_paths)} participants")
            
            # Show selected meeting info in the transcription text area
            meeting_info = "Selected Zoom meeting:\n\n"
            meeting_info += "Participants:\n"
            for i, (name, path) in enumerate(zip(participant_names, file_paths), 1):
                file_name = os.path.basename(path)
                meeting_info += f"{i}. {name} - {file_name}\n"
            
            self.transcription_text.setPlainText(meeting_info)
            
            # Start meeting transcription process
            self._change_app_state(AppState.MEETING_TRANSCRIBING)
        else:
            self._set_status_message("Invalid meeting selection.", is_error=True)
            self.is_meeting_mode = False
    
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
        # self.close_after_fabric = False # Not closing after Fabric for now
        self._clear_status_message()
        self.is_transcribing_for_fabric = False # Reset flag
        self.last_transcribed_text_for_fabric = None # Reset text
        self.selected_fabric_pattern = None # Reset selection
        self.fabric_patterns = None # Reset list

        if self.app_state == AppState.RECORDING or self.app_state == AppState.PAUSED:
            self._set_status_message("Stopping for Fabric preparation...")
            self.pending_action = AppState.PREPARING_FABRIC # Store intended next state
            self._change_app_state(AppState.STOPPING_FOR_ACTION) # Go through stopping first
            self.audio_recorder.stop_recording()
        elif self.app_state == AppState.IDLE and self.last_saved_audio_path:
            self._change_app_state(AppState.PREPARING_FABRIC)
        elif self.app_state == AppState.IDLE and not self.last_saved_audio_path and self.transcription_text.toPlainText():
            # If idle, no audio file, but there is text in the box, use that directly
            self.last_transcribed_text_for_fabric = self.transcription_text.toPlainText()
            self._change_app_state(AppState.PREPARING_FABRIC)
        else:
            self._set_status_message("Not recording and no previous audio/text for Fabric. Press R or T first.", is_error=True)

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
        model_ready = (hasattr(self, 'transcription_service') and 
                       self.transcription_service.model is not None and 
                       not self.is_model_loading_busy)
        
        can_transcribe_or_fabric = model_ready or (self.app_state == AppState.IDLE and bool(self.last_saved_audio_path) and model_ready)
        can_record = not self.is_model_loading_busy # Can record even if model loading for later use

        # Initial state if model is loading
        if self.is_model_loading_busy:
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self.model_size_selector.setEnabled(False)
            # Status message is set by _request_model_load
            return # Skip further state updates while model is loading

        if self.app_state == AppState.IDLE:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(can_record)
            self.rec_button.setText("Rec")
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(False)
            # Enable Transcribe/Fabric if model is ready AND (there's a last saved path OR there's text in the box for Fabric)
            self.transcribe_button.setEnabled(model_ready and bool(self.last_saved_audio_path))
            self.fabric_button.setEnabled(model_ready and (bool(self.last_saved_audio_path) or bool(self.transcription_text.toPlainText())))
            self.upload_button.setEnabled(model_ready)
            self.meeting_button.setEnabled(model_ready)
            if not self.status_label.property("is_error") and not self.is_model_loading_busy:
                 self._clear_status_message_after_delay()
        elif self.app_state == AppState.RECORDING:
            self.waveform_widget.set_status(WaveformStatus.RECORDING)
            self.rec_button.setEnabled(False) 
            self.rec_button.setText("Rec") # Keep it as Rec, just disabled
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(True)
            self.transcribe_button.setEnabled(model_ready)
            self.fabric_button.setEnabled(model_ready)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self._set_status_message("Recording...")
        elif self.app_state == AppState.PAUSED:
            self.waveform_widget.set_status(WaveformStatus.IDLE) # Or a specific PAUSED color
            self.rec_button.setEnabled(can_record)
            self.rec_button.setText("Resume") 
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            # self.pause_button.setText("Resume") # Pause button does not resume in this logic
            self.cancel_button.setEnabled(True)
            self.transcribe_button.setEnabled(model_ready)
            self.fabric_button.setEnabled(model_ready)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self._set_status_message("Paused.")
        elif self.app_state == AppState.CANCELLING:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self._set_status_message("Cancelling recording...")
        elif self.app_state == AppState.STOPPING_FOR_ACTION:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
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
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self.model_size_selector.setEnabled(False) # Disable model selection during transcription
            self._set_status_message(f"Transcribing ({self.current_model_size}): {os.path.basename(self.last_saved_audio_path) if self.last_saved_audio_path else '...'}")
            
            # --- Actual TranscriptionWorker Launch --- 
            if self.is_model_loading_busy or self.transcription_service.model is None:
                self._handle_transcription_error("Model is not ready or is currently loading.")
                # No return here, _handle_transcription_error calls _post_action_cleanup which resets state
                # Ensure _post_action_cleanup correctly enables model_selector if an error occurs mid-transcription setup
                if self.app_state != AppState.IDLE: # If error handling didn't go to IDLE
                     self._change_app_state(AppState.IDLE) # Force IDLE on critical error
                self.model_size_selector.setEnabled(True) # Re-enable selector on error here
                return # Critical: stop further execution in TRANSCRIBING if model not ready

            # ... (rest of TranscriptionWorker setup from previous state, ensure it's still valid) ...
            if not self.last_saved_audio_path or not os.path.exists(self.last_saved_audio_path):
                self._handle_transcription_error("Audio file path is missing or invalid for transcription.")
                return 
            # ... (transcription_service and thread_pool checks should be fine as they are core attributes)
            if hasattr(self, 'transcription_text'): self.transcription_text.clear()
            if hasattr(self, 'progress_bar'): self.progress_bar.setValue(0); self.progress_bar.show()
            
            worker = TranscriptionWorker(
                transcription_service=self.transcription_service, 
                audio_path=self.last_saved_audio_path, 
                language=None, 
                task="transcribe"
            )
            worker.signals.progress.connect(self._handle_transcription_progress)
            worker.signals.finished.connect(self._handle_transcription_finished)
            worker.signals.error.connect(self._handle_transcription_error)
            self.thread_pool.start(worker)

        elif self.app_state == AppState.PREPARING_FABRIC:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self.model_size_selector.setEnabled(False)

            # Logic to decide whether to transcribe or go straight to listing patterns
            if not self.last_transcribed_text_for_fabric and self.last_saved_audio_path and os.path.exists(self.last_saved_audio_path):
                if self.is_model_loading_busy or self.transcription_service.model is None:
                    self._handle_fabric_error("Model not ready for transcription needed for Fabric.") # Use fabric error handler
                    return
                self._set_status_message(f"Transcribing for Fabric ({self.current_model_size})...", clear_automatically=False)
                self.is_transcribing_for_fabric = True
                
                if hasattr(self, 'transcription_text'): self.transcription_text.clear() # Clear main display for this
                if hasattr(self, 'progress_bar'): self.progress_bar.setValue(0); self.progress_bar.show()

                worker = TranscriptionWorker(
                    transcription_service=self.transcription_service,
                    audio_path=self.last_saved_audio_path,
                    language=None, task="transcribe"
                )
                # Connect to specific handlers for Fabric context if needed, or reuse.
                # For now, reusing general transcription handlers but with is_transcribing_for_fabric flag.
                worker.signals.progress.connect(self._handle_transcription_progress) # Can reuse
                worker.signals.finished.connect(self._handle_transcription_finished) # Reused, will check flag
                worker.signals.error.connect(self._handle_transcription_error)       # Reused, will check flag
                self.thread_pool.start(worker)
            elif self.last_transcribed_text_for_fabric or (not self.last_saved_audio_path and not self.transcription_text.toPlainText()):
                # Text already available (from direct input or previous step) OR no audio and no text box text (error case handled by _on_fabric_keypress)
                # Proceed to list patterns
                self._set_status_message("Listing Fabric patterns...", clear_automatically=False)
                if not hasattr(self, 'fabric_service') or self.fabric_service is None:
                    self._handle_fabric_error("Fabric service not initialized.")
                    return
                fabric_list_worker = FabricListPatternsWorker(fabric_service=self.fabric_service)
                fabric_list_worker.signals.finished.connect(self._handle_fabric_patterns_listed)
                fabric_list_worker.signals.error.connect(self._handle_fabric_error) # General Fabric error
                self.thread_pool.start(fabric_list_worker)
            else: # Should not be reached if _on_fabric_keypress is correct
                 self._handle_fabric_error("Cannot prepare Fabric: No audio to transcribe and no existing text.")

        elif self.app_state == AppState.RUNNING_FABRIC_PATTERN:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False); self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False); self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False); self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self.model_size_selector.setEnabled(False)
            self._set_status_message(f"Running Fabric pattern: {self.selected_fabric_pattern}...", clear_automatically=False)

            if not self.selected_fabric_pattern or self.last_transcribed_text_for_fabric is None:
                 self._handle_fabric_run_error("Missing pattern or text for Fabric execution.")
                 return
            
            run_worker = FabricRunPatternWorker(
                fabric_service=self.fabric_service,
                pattern_name=self.selected_fabric_pattern,
                text_input=self.last_transcribed_text_for_fabric
            )
            run_worker.signals.finished.connect(self._handle_fabric_run_finished)
            run_worker.signals.error.connect(self._handle_fabric_run_error)
            self.thread_pool.start(run_worker)

        elif self.app_state == AppState.MEETING_TRANSCRIBING:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.fabric_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.meeting_button.setEnabled(False)
            self.model_size_selector.setEnabled(False)
            
            # Check if we have the necessary data
            if not self.meeting_audio_files or len(self.meeting_audio_files) < 2:
                self._handle_meeting_error("No audio files selected for meeting transcription")
                return
            
            if self.is_model_loading_busy or self.transcription_service.model is None:
                self._handle_meeting_error("Model is not ready for meeting transcription")
                return
            
            self._set_status_message(f"Transcribing meeting with {len(self.meeting_audio_files)} participants...")
            
            # Show progress bar
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setValue(0)
                self.progress_bar.show()
            
            # Create and start meeting transcription worker
            meeting_worker = MeetingTranscriptionWorker(
                transcription_service=self.transcription_service,
                audio_files=self.meeting_audio_files,
                participant_names=self.meeting_participant_names,
                language=None,  # Auto-detect
                task="transcribe"
            )
            
            meeting_worker.signals.progress.connect(self._handle_meeting_progress)
            meeting_worker.signals.file_progress.connect(self._handle_meeting_file_progress)
            meeting_worker.signals.finished.connect(self._handle_meeting_finished)
            meeting_worker.signals.error.connect(self._handle_meeting_error)
            
            self.thread_pool.start(meeting_worker)

        # Make sure model_size_selector gets re-enabled if not in a blocking state
        if self.app_state not in [AppState.TRANSCRIBING, AppState.PREPARING_FABRIC, AppState.RUNNING_FABRIC_PATTERN, AppState.STOPPING_FOR_ACTION, AppState.CANCELLING, AppState.MEETING_TRANSCRIBING] and not self.is_model_loading_busy:
            self.model_size_selector.setEnabled(True)

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
        self.upload_button.setStyleSheet(button_style)
        self.meeting_button.setStyleSheet(button_style)
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

    def _set_status_message(self, message, is_error=False, clear_automatically=True):
        self.status_label.setText(message)
        self.status_label.setProperty("is_error", is_error) # Store error state
        if is_error:
            self.status_label.setStyleSheet("color: #f7768e; margin: 2px;") # Tokyo Night Red
        else:
            self.status_label.setStyleSheet("color: #c0caf5; margin: 2px;") # Tokyo Night Text
        
        # Manage auto-clearing timer
        if hasattr(self, '_status_clear_timer') and self._status_clear_timer.isActive():
            self._status_clear_timer.stop()

        if not is_error and clear_automatically and message:
            if not hasattr(self, '_status_clear_timer'):
                self._status_clear_timer = QTimer()
                self._status_clear_timer.setSingleShot(True)
                self._status_clear_timer.timeout.connect(self._clear_status_label_if_not_error)
            
            # Store the message that triggered this timer to avoid clearing a newer message
            self._message_for_auto_clear = message 
            self._status_clear_timer.start(5000) # Default 5s, can be parameter if needed
        elif is_error or not clear_automatically:
            # If it's an error or auto-clear is off, ensure no pending clear for a *previous* message happens
            if hasattr(self, '_status_clear_timer') and self._status_clear_timer.isActive():
                 self._status_clear_timer.stop()
            self._message_for_auto_clear = None # No message is pending auto-clear

    def _clear_status_label_if_not_error(self):
        # Only clear if the current message is the one that scheduled the clear and it's not an error
        if (hasattr(self, '_message_for_auto_clear') and 
            self.status_label.text() == self._message_for_auto_clear and 
            not self.status_label.property("is_error")):
            self.status_label.setText("")
            self._message_for_auto_clear = None # Reset

    def _clear_status_message(self):
        self.status_label.setText("")
        self.status_label.setProperty("is_error", False)
        if hasattr(self, '_status_clear_timer') and self._status_clear_timer.isActive():
            self._status_clear_timer.stop()
        self._message_for_auto_clear = None

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
        
        # Reset Fabric specific state if coming from a Fabric operation
        if self.app_state == AppState.RUNNING_FABRIC_PATTERN or self.app_state == AppState.PREPARING_FABRIC:
            self.selected_fabric_pattern = None
            # self.last_transcribed_text_for_fabric = None # Keep for potential re-use if user cancels dialog then re-runs F
            self.fabric_patterns = None
            self.is_transcribing_for_fabric = False
            if self.pattern_selection_dialog and self.pattern_selection_dialog.isVisible():
                self.pattern_selection_dialog.reject() # Close it if open

        if not self.is_model_loading_busy:
            self.model_size_selector.setEnabled(True)
        
        # Conditional return to IDLE
        # Avoid auto-IDLE if we are closing, or if a dialog should remain, etc.
        # Fabric handlers now manage their own transition to IDLE mostly.
        if not (hasattr(self, 'close_after_transcription') and self.close_after_transcription and not success):
             # If closing after transcription AND it was successful, normal close handles it.
             # If closing and it FAILED, then we might want to go to IDLE to show error before closing.
             # This logic is getting complex. The main idea is Fabric flow controls its own IDLE transition.
             if self.app_state not in [AppState.PREPARING_FABRIC]: # PREPARING_FABRIC leads to dialog or error
                self._change_app_state(AppState.IDLE)

    def _clear_status_message_after_delay(self, delay_ms=3000):
        # This method is now largely superseded by the logic in _set_status_message
        # but is still called by _update_ui_for_state for IDLE state.
        # We can simplify it or make _set_status_message handle this path too.
        # For now, let it call _set_status_message with an empty string to trigger its logic.
        if not self.status_label.property("is_error") and self.status_label.text():
            # Call _set_status_message which will schedule a clear if appropriate
            # This feels a bit indirect. Let's refine _set_status_message or this one.
            # Keeping existing timer logic here for now to minimize disruption for IDLE state clearing
            if hasattr(self, '_status_idle_clear_timer') and self._status_idle_clear_timer.isActive():
                self._status_idle_clear_timer.stop()
            
            if not hasattr(self, '_status_idle_clear_timer'):
                self._status_idle_clear_timer = QTimer()
                self._status_idle_clear_timer.setSingleShot(True)
                self._status_idle_clear_timer.timeout.connect(self._clear_status_label_if_not_error_idle)
            self._message_for_idle_clear = self.status_label.text()
            self._status_idle_clear_timer.start(delay_ms)

    def _clear_status_label_if_not_error_idle(self):
        if (hasattr(self, '_message_for_idle_clear') and 
            self.status_label.text() == self._message_for_idle_clear and 
            not self.status_label.property("is_error")):
            self.status_label.setText("")
            self._message_for_idle_clear = None

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
        lang = result.get("detected_language")
        prob = result.get("language_probability")
        status_suffix = ""

        if self.is_transcribing_for_fabric:
            self.is_transcribing_for_fabric = False
            self.last_transcribed_text_for_fabric = text
            
            prob_str = f"{prob:.2f}" if prob is not None else "N/A"
            lang_str = lang if lang else "Unknown"
            self._set_status_message(f"Transcription for Fabric complete ({lang_str}: {prob_str}). Listing patterns...")
            
            # Now trigger pattern listing
            if not hasattr(self, 'fabric_service') or self.fabric_service is None:
                self._handle_fabric_error("Fabric service not initialized after transcription for Fabric.")
                return
            fabric_list_worker = FabricListPatternsWorker(fabric_service=self.fabric_service)
            fabric_list_worker.signals.finished.connect(self._handle_fabric_patterns_listed)
            fabric_list_worker.signals.error.connect(self._handle_fabric_error)
            self.thread_pool.start(fabric_list_worker)
            return # Do not proceed with normal transcription cleanup (clipboard, paste, close)

        # --- Normal 'T' key transcription finish ---
        self.transcription_text.setPlainText(text) # Update main text box
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
        
        base_message = f"Transcription complete ({lang}: {prob:.2f})" if lang else "Transcription complete"
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
        if self.is_transcribing_for_fabric:
            self.is_transcribing_for_fabric = False
            self._set_status_message(f"Transcription for Fabric failed: {error_message}", is_error=True)
            self._change_app_state(AppState.IDLE) # Go to IDLE on critical failure
            self.model_size_selector.setEnabled(not self.is_model_loading_busy)
            return

        self.close_after_transcription = False 
        self._post_action_cleanup(False, error_message)

    @Slot(list) 
    def _handle_fabric_patterns_listed(self, patterns):
        if self.app_state != AppState.PREPARING_FABRIC: # Ensure we are in the correct state
            return 

        if patterns:
            self.fabric_patterns = patterns
            self._set_status_message(f"Found {len(patterns)} Fabric patterns. Select one.")
            self._show_pattern_selection_dialog()
        else:
            self._set_status_message("No Fabric patterns found or error listing.", is_error=True)
            QTimer.singleShot(2000, lambda: self._change_app_state(AppState.IDLE) if not self.is_model_loading_busy else None)
            if not self.is_model_loading_busy : self.model_size_selector.setEnabled(True)

    @Slot(str) 
    def _handle_fabric_error(self, error_message): # General errors from FabricListPatternsWorker
        print(f"Fabric Service Error (List/Prepare): {error_message}")
        self._set_status_message(f"Fabric Error: {error_message}", is_error=True)
        self.is_transcribing_for_fabric = False # Reset flag
        QTimer.singleShot(2000, lambda: self._change_app_state(AppState.IDLE) if not self.is_model_loading_busy else None)
        if not self.is_model_loading_busy : self.model_size_selector.setEnabled(True)

    # --- New methods for Pattern Selection Dialog and Running Fabric Pattern ---
    def _show_pattern_selection_dialog(self):
        if not self.fabric_patterns:
            self._handle_fabric_error("Pattern list not available to show dialog.")
            return
        
        # Ensure text is ready if we didn't transcribe specifically for fabric earlier
        if not self.last_transcribed_text_for_fabric:
            current_text_in_box = self.transcription_text.toPlainText()
            if current_text_in_box:
                self.last_transcribed_text_for_fabric = current_text_in_box
            # If still no text, an error will be caught before running the pattern.
            # Or, we could show an error here if last_transcribed_text_for_fabric is None.
            # For now, let _on_pattern_dialog_accepted handle it.

        self.pattern_selection_dialog = PatternSelectionDialog(self.fabric_patterns, self)
        self.pattern_selection_dialog.pattern_selected.connect(self._on_pattern_dialog_accepted)
        self.pattern_selection_dialog.finished.connect(self._on_pattern_dialog_finished)
        # Apply styles to dialog if needed, or ensure it inherits them
        # self.pattern_selection_dialog.setStyleSheet(self.styleSheet()) # Basic inheritance
        self.pattern_selection_dialog.show() # Use show() for non-blocking if other tasks, but exec() for modal
        # Using exec() to make it modal and block until selection
        # self.pattern_selection_dialog.exec() 
        # ^ Handled by self.pattern_selection_dialog.finished connection

    @Slot(str)
    def _on_pattern_dialog_accepted(self, pattern_name):
        self.selected_fabric_pattern = pattern_name
        self._set_status_message(f"Pattern '{pattern_name}' selected.")
        
        if not self.last_transcribed_text_for_fabric:
            # This might happen if user had no audio, no text in box, then pressed F
            # and somehow listing patterns succeeded (e.g. if it doesn't depend on text).
            # However, _on_fabric_keypress should prevent this state.
            # Or if transcription for fabric was skipped and main text box was empty.
            self._handle_fabric_run_error("No text available to process with Fabric.")
            return

        self._change_app_state(AppState.RUNNING_FABRIC_PATTERN)

    @Slot(int)
    def _on_pattern_dialog_finished(self, result_code):
        # This slot is connected to QDialog.finished(int)
        if self.pattern_selection_dialog: # Ensure dialog exists
            self.pattern_selection_dialog.deleteLater() # Clean up dialog
            self.pattern_selection_dialog = None

        if result_code == QDialog.DialogCode.Rejected:
            if not self.selected_fabric_pattern: # Only if OK wasn't clicked (i.e., proper cancel)
                self._set_status_message("Fabric pattern selection cancelled.")
                self.last_transcribed_text_for_fabric = None # Clear if cancelled
                self.fabric_patterns = None
                self._change_app_state(AppState.IDLE)
        # If accepted, _on_pattern_dialog_accepted already handled setting selected_fabric_pattern
        # and triggering the next state.

    @Slot(object) # Receives processed_text (str) from FabricRunPatternWorker
    def _handle_fabric_run_finished(self, processed_text):
        output_text = str(processed_text) # Ensure it's a string
        self._set_status_message("Fabric processing successful!")
        self.transcription_text.setPlainText(output_text) # Display result

        status_suffix_fabric = ""
        if output_text:
            try:
                pyperclip.copy(output_text)
                print("Fabric output copied to clipboard.")
                paste_command = """
                osascript -e 'tell application "System Events" to keystroke "v" using command down'
                """
                subprocess.run(paste_command, shell=True, check=False)
                print("Paste command executed for Fabric output.")
                status_suffix_fabric = " (copied & pasted)"
            except Exception as e:
                print(f"Error with clipboard/paste for Fabric output: {e}")
                self._set_status_message(f"Fabric complete, clipboard error: {e}", is_error=True)
                status_suffix_fabric = " (clipboard error)"
        
        final_fabric_message = f"Fabric processing complete{status_suffix_fabric}"
        self._post_action_cleanup(True, final_fabric_message) # Resets state to IDLE

    @Slot(str)
    def _handle_fabric_run_error(self, error_message):
        print(f"Fabric Run Error: {error_message}")
        self._set_status_message(f"Fabric Run Error: {error_message}", is_error=True)
        self._post_action_cleanup(False, f"Fabric run failed: {error_message}") # Resets state to IDLE
        # Ensure self.selected_fabric_pattern etc. are reset by _post_action_cleanup

    # --- Meeting Transcription Handlers ---
    @Slot(int, str)
    def _handle_meeting_progress(self, progress: int, status: str):
        """Handle overall meeting transcription progress."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(progress)
        self._set_status_message(status)
    
    @Slot(str, int, str)
    def _handle_meeting_file_progress(self, speaker: str, progress: int, text: str):
        """Handle individual file transcription progress."""
        # Could update UI to show per-file progress if desired
        pass
    
    @Slot(object)
    def _handle_meeting_finished(self, meeting_transcript):
        """Handle completed meeting transcription."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.hide()
        
        # Display the transcript
        markdown_text = meeting_transcript.to_markdown()
        self.transcription_text.setPlainText(markdown_text)
        
        # Copy to clipboard
        try:
            import pyperclip
            pyperclip.copy(markdown_text)
            print("Meeting transcript copied to clipboard.")
            
            # Auto-paste
            paste_command = """
            osascript -e 'tell application "System Events" to keystroke "v" using command down'
            """
            subprocess.run(paste_command, shell=True, check=False)
            print("Paste command executed.")
            
            self._set_status_message("Meeting transcript complete (copied & pasted)")
        except Exception as e:
            print(f"Error with clipboard/paste: {e}")
            self._set_status_message("Meeting transcript complete", is_error=False)
        
        # Reset meeting mode
        self.is_meeting_mode = False
        self.meeting_audio_files = []
        self.meeting_participant_names = []
        
        # Return to idle state
        self._change_app_state(AppState.IDLE)
    
    @Slot(str)
    def _handle_meeting_error(self, error_message: str):
        """Handle meeting transcription error."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.hide()
        
        self._set_status_message(f"Meeting transcription error: {error_message}", is_error=True)
        
        # Reset meeting mode
        self.is_meeting_mode = False
        self.meeting_audio_files = []
        self.meeting_participant_names = []
        
        # Return to idle state
        self._change_app_state(AppState.IDLE)
        if not self.is_model_loading_busy:
            self.model_size_selector.setEnabled(True)
    
    @Slot(str)
    def _on_model_size_changed(self, selected_model):
        self.current_model_size = selected_model
        print(f"UI: Model size selection changed to: {self.current_model_size}")
        # Trigger reload using the service's current device/compute_type settings
        self._request_model_load(self.current_model_size, 
                                 self.transcription_service.device, 
                                 self.transcription_service.compute_type)

    def _initiate_initial_model_load(self):
        initial_model = self.model_size_selector.currentText() # or self.current_model_size
        # Use device/compute_type from service, which are its defaults or from config
        self._request_model_load(initial_model, 
                                 self.transcription_service.device, 
                                 self.transcription_service.compute_type)

    def _request_model_load(self, model_name, device, compute_type):
        if self.is_model_loading_busy:
            print(f"Model loading is already busy. Request to load {model_name} ignored for now.")
            # Optionally, could queue requests or cancel previous, but keep it simple first.
            return

        self.is_model_loading_busy = True
        self._set_status_message(f"Loading model: {model_name}...", clear_automatically=False)
        self._update_ui_for_state() # Reflect loading state (buttons disabled etc)

        worker = LoadModelWorker(self.transcription_service, model_name, device, compute_type)
        # The finished signal from LoadModelWorker emits a tuple: (bool_success, str_message)
        worker.signals.finished.connect(self._handle_model_load_finished)
        # If LoadModelWorker also has an error signal for setup issues:
        # worker.signals.error.connect(self._handle_model_load_error_slot) # Or handle in finished
        self.thread_pool.start(worker)

    @Slot(object) # Receives tuple (bool, str) from LoadModelWorker's finished signal
    def _handle_model_load_finished(self, result_tuple):
        self.is_model_loading_busy = False
        success, message = result_tuple # Unpack the tuple

        if success:
            loaded_model_name = message # On success, message is the model name
            self._set_status_message(f"Model '{loaded_model_name}' loaded.", clear_automatically=True)
            print(f"Model {loaded_model_name} loaded successfully via worker.")
        else:
            error_detail = message # On failure, message is the error string
            self._set_status_message(f"Error loading model: {error_detail}", is_error=True, clear_automatically=False)
            print(f"Failed to load model via worker: {error_detail}")
        
        self._update_ui_for_state() # Refresh UI based on new model state

if __name__ == '__main__':
    # This is for testing the window directly
    # Ensure paths are correct if running directly, or run via app/main.py
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 
