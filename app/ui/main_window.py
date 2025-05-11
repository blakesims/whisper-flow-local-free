# Placeholder for main_window.py 

import sys
from PySide6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, QTimer, Signal # Added Signal for consistency if MainWindow were to emit its own
import numpy as np

from .waveform_widget import WaveformWidget, WaveformStatus
from app.core.audio_recorder import AudioRecorder # Import AudioRecorder

# from app.utils.config_manager import ConfigManager # Will be used later

class AppState:
    IDLE = 0
    RECORDING = 1
    PAUSED = 2
    # PROCESSING = 3 # Future state

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Transcription UI")
        self._app_state = AppState.IDLE # Initialize app state

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

        self.rec_button.setToolTip("Start/Resume Recording (R)")
        self.stop_button.setToolTip("Stop Recording (S)")
        self.pause_button.setToolTip("Pause Recording (P)")
        self.cancel_button.setToolTip("Cancel Recording (C)")

        self.rec_button.clicked.connect(self._on_rec_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        controls_layout.addWidget(self.rec_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.cancel_button)
        main_layout.addLayout(controls_layout) # Add controls layout to main vertical layout

        # Status/Error Label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # Minimize button
        self.minimize_button = QPushButton("Min") # Renamed from "-"
        self.minimize_button.setToolTip("Minimize Window")
        self.minimize_button.setFixedSize(40, 28)
        self.minimize_button.clicked.connect(self.showMinimized)
        # Place minimize button in a dedicated layout if more top-bar controls are needed
        # For now, let's ensure it's distinct. A QHBoxLayout for top controls would be better.
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.minimize_button)
        main_layout.insertLayout(0, top_bar_layout) # Insert at the top

        # Initialize AudioRecorder
        self.audio_recorder = AudioRecorder(parent=self)
        self._connect_audio_recorder_signals()

        self._apply_button_styles() # Apply styles to all buttons
        self._apply_status_label_style()
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

    def _connect_audio_recorder_signals(self):
        self.audio_recorder.new_audio_chunk_signal.connect(self._handle_new_audio_chunk)
        self.audio_recorder.recording_started_signal.connect(self._handle_recording_started)
        self.audio_recorder.recording_stopped_signal.connect(self._handle_recording_stopped)
        self.audio_recorder.recording_paused_signal.connect(self._handle_recording_paused)
        self.audio_recorder.recording_resumed_signal.connect(self._handle_recording_resumed)
        self.audio_recorder.error_signal.connect(self._handle_audio_error)

    # --- AudioRecorder Signal Handlers ---
    def _handle_new_audio_chunk(self, audio_chunk):
        print(f"UI: Received audio chunk. Shape: {audio_chunk.shape}, Min: {np.min(audio_chunk):.2f}, Max: {np.max(audio_chunk):.2f}, dtype: {audio_chunk.dtype}")
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
        else:
            print("UI: Received empty or None audio chunk.")

    def _handle_recording_started(self):
        print("UI: Recording started")
        self._change_app_state(AppState.RECORDING)

    def _handle_recording_stopped(self, file_path_or_message):
        print(f"UI: Recording stopped. Info: {file_path_or_message}")
        if "Error:" in file_path_or_message or "Failed" in file_path_or_message: # Heuristic for error
            self._set_status_message(file_path_or_message, is_error=True)
        else:
            self._set_status_message(f"Saved: {file_path_or_message.split('/')[-1]}", is_error=False)
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
        if self._app_state == AppState.IDLE:
            self.audio_recorder.start_recording()
        elif self._app_state == AppState.PAUSED:
            self.audio_recorder.resume_recording()

    def _on_stop_clicked(self):
        # Status message will be set by _handle_recording_stopped
        if self._app_state == AppState.RECORDING or self._app_state == AppState.PAUSED:
            self.audio_recorder.stop_recording()

    def _on_pause_clicked(self):
        self._clear_status_message()
        if self._app_state == AppState.RECORDING:
            self.audio_recorder.pause_recording()

    def _on_cancel_clicked(self):
        self._clear_status_message()
        if self._app_state == AppState.RECORDING or self._app_state == AppState.PAUSED:
            print("UI: Cancel clicked, stopping recording.")
            self.audio_recorder.stop_recording(cancel=True)

    def _change_app_state(self, new_state):
        if self._app_state == new_state and not (new_state == AppState.RECORDING and self.rec_button.text() == "Resume") : # allow re-setting RECORDING if resuming
            # avoid redundant UI updates if state is truly the same
            # but allow _update_ui_for_state to run if text needs to change (e.g. Resume to Rec)
            if not (self._app_state == AppState.PAUSED and new_state == AppState.RECORDING): # from pause to record
                 return

        print(f"Changing app state from {self._app_state} to {new_state}")
        old_state = self._app_state
        self._app_state = new_state
        self._update_ui_for_state(old_state)
        
        # Test timer already removed
        # if self._test_waveform_timer.isActive():
            # self._test_waveform_timer.stop()

    def _update_ui_for_state(self, old_state=None): # old_state can be used for more nuanced UI updates if needed
        if self._app_state == AppState.IDLE:
            self.waveform_widget.set_status(WaveformStatus.IDLE)
            self.rec_button.setEnabled(True)
            self.rec_button.setText("Rec")
            self.stop_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(False)
        elif self._app_state == AppState.RECORDING:
            self.waveform_widget.set_status(WaveformStatus.RECORDING)
            self.rec_button.setEnabled(False) 
            self.rec_button.setText("Rec") # Keep it as Rec, just disabled
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(True)
        elif self._app_state == AppState.PAUSED:
            self.waveform_widget.set_status(WaveformStatus.IDLE) # Or a specific PAUSED color
            self.rec_button.setEnabled(True)
            self.rec_button.setText("Resume") 
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            # self.pause_button.setText("Resume") # Pause button does not resume in this logic
            self.cancel_button.setEnabled(True)

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
        self.minimize_button.setText("Min")
        self.minimize_button.setFixedSize(40, 28)

    def _apply_status_label_style(self):
        # Initial style, color will be set by _set_status_message
        self.status_label.setStyleSheet("color: #c0caf5; padding: 2px; min-height: 2em;") # min-height for 2 lines

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return # Consume event

        # Keyboard shortcuts for recording controls
        # Check if button is enabled before triggering its action via shortcut
        if event.key() == Qt.Key.Key_R:
            if self.rec_button.isEnabled():
                self._on_rec_clicked()
        elif event.key() == Qt.Key.Key_S:
            if self.stop_button.isEnabled():
                self._on_stop_clicked()
        elif event.key() == Qt.Key.Key_P:
            if self.pause_button.isEnabled():
                self._on_pause_clicked()
            elif self._app_state == AppState.PAUSED and self.rec_button.isEnabled(): 
                 self._on_rec_clicked() 
        elif event.key() == Qt.Key.Key_C:
            if self.cancel_button.isEnabled():
                self._on_cancel_clicked()
        else:
            super().keyPressEvent(event)

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

if __name__ == '__main__':
    # This is for testing the window directly
    # Ensure paths are correct if running directly, or run via app/main.py
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 
