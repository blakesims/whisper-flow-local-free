# Placeholder for main_window.py 

import sys
from PySide6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton
from PySide6.QtCore import Qt, QTimer
import numpy as np

from .waveform_widget import WaveformWidget, WaveformStatus # Added WaveformStatus

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
        layout = QVBoxLayout(self.central_widget)
        
        # Waveform display area
        self.waveform_widget = WaveformWidget()
        layout.addWidget(self.waveform_widget) # Add waveform widget to layout

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
        layout.addLayout(controls_layout) # Add controls layout to main vertical layout

        # Minimize button
        self.minimize_button = QPushButton("Min") # Renamed from "-"
        self.minimize_button.setToolTip("Minimize Window")
        self.minimize_button.setFixedSize(40, 28)
        self.minimize_button.clicked.connect(self.showMinimized)
        layout.addWidget(self.minimize_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        # Setup timer for live waveform testing
        self._test_waveform_timer = QTimer(self)
        self._test_waveform_timer.timeout.connect(self._update_live_waveform_test)
        self._test_waveform_timer.start(1000) # Match waveform_widget test timer for status changes
        self._test_status_cycle = [WaveformStatus.IDLE, WaveformStatus.RECORDING]
        self._current_test_status_idx = 0

        self._apply_button_styles() # Apply styles to all buttons
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
        self.resize(300, 150)

        # Make the window draggable (since it's frameless)
        self._drag_pos = None

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

    def _update_live_waveform_test(self):
        # Generate a random number of samples for the raw audio chunk
        # This calls the method now present in WaveformWidget
        num_raw_samples = np.random.randint(500, 5000) 
        test_audio_chunk = self.waveform_widget.generate_sample_raw_audio(num_raw_samples)
        self.waveform_widget.update_waveform_data(test_audio_chunk)

        # Cycle and set status for the waveform widget
        self._current_test_status_idx = (self._current_test_status_idx + 1) % len(self._test_status_cycle)
        self.waveform_widget.set_status(self._test_status_cycle[self._current_test_status_idx])

    # Placeholder methods for button clicks
    def _on_rec_clicked(self):
        print("Record button clicked")
        if self._app_state == AppState.IDLE or self._app_state == AppState.PAUSED:
            self._change_app_state(AppState.RECORDING)
        # elif self._app_state == AppState.RECORDING: # Could be a toggle to Pause
            # self._change_app_state(AppState.PAUSED)

    def _on_stop_clicked(self):
        print("Stop button clicked")
        if self._app_state == AppState.RECORDING or self._app_state == AppState.PAUSED:
            self._change_app_state(AppState.IDLE) # Or a "PROCESSING" state before IDLE

    def _on_pause_clicked(self):
        print("Pause button clicked")
        if self._app_state == AppState.RECORDING:
            self._change_app_state(AppState.PAUSED)
        elif self._app_state == AppState.PAUSED:
            self._change_app_state(AppState.RECORDING) # Resume

    def _on_cancel_clicked(self):
        print("Cancel button clicked") # Typically resets to IDLE
        if self._app_state == AppState.RECORDING or self._app_state == AppState.PAUSED:
            self._change_app_state(AppState.IDLE)

    def _change_app_state(self, new_state):
        if self._app_state == new_state: return
        print(f"Changing app state from {self._app_state} to {new_state}")
        self._app_state = new_state
        self._update_ui_for_state()
        
        # Stop test timer when user interacts, if it's running
        if self._test_waveform_timer.isActive():
            self._test_waveform_timer.stop()
            # Optionally set a default waveform state when stopping test timer
            # self.waveform_widget.set_status(WaveformStatus.IDLE) 
            # self.waveform_widget.update_waveform_data(np.zeros(self.waveform_widget.num_display_points, dtype=np.float32))

    def _update_ui_for_state(self):
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
            self.rec_button.setEnabled(False) # Or change to a "Pause" icon/text
            # self.rec_button.setText("PauseRec") 
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.cancel_button.setEnabled(True)
        elif self._app_state == AppState.PAUSED:
            self.waveform_widget.set_status(WaveformStatus.IDLE) # Or a specific PAUSED color
            self.rec_button.setEnabled(True) # To resume
            self.rec_button.setText("Resume") 
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(False) # Or change text to "Resumed by Rec button"
            # self.pause_button.setText("Resume") # If pause button also resumes
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
                background-color: #20202a; /* Darker, less prominent */
                color: #50505a;
                border: 1px solid #40404a;
            }
        """
        self.rec_button.setStyleSheet(button_style)
        self.stop_button.setStyleSheet(button_style)
        self.pause_button.setStyleSheet(button_style)
        self.cancel_button.setStyleSheet(button_style)
        # self.minimize_button can have its own specific style or share this
        # For now, let minimize button keep its more compact style from before
        # Or, apply this and adjust its padding/min-width if needed.
        # Let's update minimize button to use this style too for consistency, adjusting size via layout later if needed.
        self.minimize_button.setStyleSheet(button_style)
        self.minimize_button.setText("Min") # More descriptive than "-"
        self.minimize_button.setFixedSize(40, 28) # Adjust fixed size for new padding

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
            if self.pause_button.isEnabled(): # If pause button itself handles resume, this is fine
                self._on_pause_clicked()
            # If Pause button becomes disabled and Rec becomes Resume when paused, 
            # then P might also need to trigger _on_rec_clicked if app_state is PAUSED.
            # For now, P only triggers _on_pause_clicked if pause_button is enabled.
            # Let's refine: if P is pressed and state is PAUSED, treat as resume (same as Rec button)
            elif self._app_state == AppState.PAUSED and self.rec_button.isEnabled(): # rec_button is "Resume"
                 self._on_rec_clicked() # P for resume
        elif event.key() == Qt.Key.Key_C:
            if self.cancel_button.isEnabled():
                self._on_cancel_clicked()
        else:
            super().keyPressEvent(event)

if __name__ == '__main__':
    # This is for testing the window directly
    # Ensure paths are correct if running directly, or run via app/main.py
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 