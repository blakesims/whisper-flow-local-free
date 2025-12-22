"""
Recording Indicator - Floating UI for quick transcribe feedback

A minimal, always-on-top indicator that shows:
- Recording state (pulsing red dot)
- Transcribing state (spinner)
- Auto-hides when idle
"""

import subprocess
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QApplication, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QRect
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QScreen


# macOS system sounds - simple and minimal
# Same sound for start and stop (consistent feedback)
SOUND_TOGGLE = "/System/Library/Sounds/Pop.aiff"


def play_sound(sound_path: str):
    """Play a system sound non-blocking"""
    if os.path.exists(sound_path):
        try:
            subprocess.Popen(
                ["afplay", sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass  # Silently fail if sound doesn't work


class MiniWaveform(QWidget):
    """A simple monochrome waveform visualization"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 32)  # Larger size for better visibility
        self._samples = [0.0] * 24  # Store 24 amplitude samples
        self._max_samples = 24

    def update_audio(self, audio_chunk):
        """Update with new audio data"""
        import numpy as np
        if audio_chunk is not None and len(audio_chunk) > 0:
            # Calculate RMS amplitude of the chunk
            rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))
            # Normalize to 0-1 range - sensitivity 3x (multiplier = 15)
            normalized = min(1.0, rms * 15)
            self._samples.append(normalized)
            if len(self._samples) > self._max_samples:
                self._samples.pop(0)
            self.update()

    def clear(self):
        """Clear the waveform"""
        self._samples = [0.0] * self._max_samples
        self.update()

    def paintEvent(self, event):
        """Paint the waveform bars"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Bar settings
        bar_width = 3
        bar_spacing = 1
        max_height = self.height() - 4
        center_y = self.height() // 2

        # Draw bars
        for i, amplitude in enumerate(self._samples):
            x = i * (bar_width + bar_spacing)
            bar_height = max(2, int(amplitude * max_height))

            # Gradient from gray to red based on amplitude
            if amplitude > 0.6:
                color = QColor(255, 59, 48)  # Red for loud
            elif amplitude > 0.3:
                color = QColor(255, 149, 0)  # Orange for medium
            else:
                color = QColor(142, 142, 147)  # Gray for quiet

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)

            # Draw bar centered vertically
            y = center_y - bar_height // 2
            painter.drawRoundedRect(x, y, bar_width, bar_height, 1, 1)


class PulsingDot(QWidget):
    """A pulsing red dot indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._opacity = 1.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_direction = -1  # -1 = fading, 1 = brightening
        self._is_pulsing = False

    def _get_opacity(self):
        return self._opacity

    def _set_opacity(self, value):
        self._opacity = value
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def start_pulsing(self):
        """Start the pulsing animation"""
        if not self._is_pulsing:
            self._is_pulsing = True
            self._pulse_timer.start(50)  # 50ms interval for smooth animation

    def stop_pulsing(self):
        """Stop the pulsing animation"""
        self._is_pulsing = False
        self._pulse_timer.stop()
        self._opacity = 1.0
        self.update()

    def _pulse(self):
        """Animate the pulse"""
        self._opacity += self._pulse_direction * 0.05
        if self._opacity <= 0.3:
            self._pulse_direction = 1
            self._opacity = 0.3
        elif self._opacity >= 1.0:
            self._pulse_direction = -1
            self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        """Paint the pulsing dot"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Red color with current opacity
        color = QColor(255, 59, 48)  # iOS-style red
        color.setAlphaF(self._opacity)

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)

        # Draw circle centered in widget
        margin = 2
        painter.drawEllipse(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)


class SpinnerWidget(QWidget):
    """A simple spinning indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._is_spinning = False

    def start_spinning(self):
        """Start the spinner"""
        if not self._is_spinning:
            self._is_spinning = True
            self._timer.start(50)

    def stop_spinning(self):
        """Stop the spinner"""
        self._is_spinning = False
        self._timer.stop()
        self._angle = 0
        self.update()

    def _rotate(self):
        """Rotate the spinner"""
        self._angle = (self._angle + 15) % 360
        self.update()

    def paintEvent(self, event):
        """Paint the spinner"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Translate to center and rotate
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)

        # Draw arc segments with varying opacity
        color = QColor(0, 122, 255)  # iOS-style blue
        pen = QPen(color)
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)

        radius = 5
        for i in range(8):
            alpha = 1.0 - (i * 0.12)
            color.setAlphaF(max(0.1, alpha))
            pen.setColor(color)
            painter.setPen(pen)

            angle = i * 45
            painter.rotate(45)
            painter.drawLine(0, -radius, 0, -radius - 2)


class RecordingIndicator(QWidget):
    """
    Floating indicator window for recording/transcribing status.

    Features:
    - Frameless, always-on-top window
    - Positioned at top-center of screen
    - Dark theme matching the main app
    - Auto-hides when idle
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Window flags: frameless, always on top, never take focus
        # Using SplashScreen type which is designed for non-interactive overlays
        self.setWindowFlags(
            Qt.SplashScreen |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus
        )

        # Prevent window from activating the application
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        # Setup UI
        self._setup_ui()

        # Position at top-center
        self._position_window()

        # Fade animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(200)
        self._fade_animation.setEasingCurve(QEasingCurve.InOutQuad)

    def _setup_ui(self):
        """Setup the UI components"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Pulsing dot for recording
        self.dot = PulsingDot()
        self.dot.hide()
        layout.addWidget(self.dot)

        # Spinner for transcribing
        self.spinner = SpinnerWidget()
        self.spinner.hide()
        layout.addWidget(self.spinner)

        # Mini waveform for audio visualization
        self.waveform = MiniWaveform()
        self.waveform.hide()
        layout.addWidget(self.waveform)

        # Status label
        self.label = QLabel("Recording...")
        self.label.setFont(QFont("SF Pro Text", 13, QFont.Medium))
        self.label.setStyleSheet("color: white;")
        layout.addWidget(self.label)

        self.setLayout(layout)

        # Fixed size for consistent appearance
        self.setFixedHeight(36)

    def _position_window(self):
        """Position the window at bottom-center of the screen where cursor is"""
        from PySide6.QtGui import QCursor

        # Get the screen where the cursor currently is
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)

        # Fallback to primary screen if cursor screen not found
        if not screen:
            screen = QApplication.primaryScreen()

        if screen:
            geometry = screen.availableGeometry()
            # Center horizontally, 100px from bottom
            x = geometry.x() + (geometry.width() - self.width()) // 2
            y = geometry.y() + geometry.height() - self.height() - 100
            self.move(x, y)
            print(f"[Indicator] Screen: {screen.name()}, Position: ({x}, {y})")

    def paintEvent(self, event):
        """Paint the rounded background"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dark semi-transparent background
        bg_color = QColor(30, 30, 32, 230)  # Tokyo Night-ish dark
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)

        # Rounded rectangle
        painter.drawRoundedRect(self.rect(), 10, 10)

    def show_recording(self):
        """Show the recording indicator"""
        # Play toggle sound (same for start/stop)
        play_sound(SOUND_TOGGLE)

        # Hide label during recording - just show dot + waveform
        self.label.hide()

        self.spinner.hide()
        self.spinner.stop_spinning()

        self.dot.show()
        self.dot.start_pulsing()

        # Show waveform for audio feedback
        self.waveform.clear()
        self.waveform.show()

        self.adjustSize()
        self._position_window()
        self._fade_in()

    def show_transcribing(self, progress: int = 0):
        """Show the transcribing indicator with progress"""
        # Play toggle sound (same for start/stop)
        play_sound(SOUND_TOGGLE)

        # Show label for progress percentage
        self.label.show()
        self.update_progress(progress)

        self.dot.hide()
        self.dot.stop_pulsing()

        self.waveform.hide()

        self.spinner.show()
        self.spinner.start_spinning()

        self.adjustSize()
        self._position_window()
        self._fade_in()

    def update_progress(self, progress: int):
        """Update transcription progress percentage"""
        self.label.setText(f"Transcribing... {progress}%")
        self.label.setStyleSheet("color: #007AFF;")  # Blue

    def hide_indicator(self):
        """Hide the indicator with fade animation"""
        self._fade_out()

    def update_waveform(self, audio_chunk):
        """Update waveform with new audio data"""
        if self.waveform.isVisible():
            self.waveform.update_audio(audio_chunk)

    def _fade_in(self):
        """Fade in animation"""
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)

        # Save the currently focused app and restore focus after showing
        try:
            from AppKit import NSWorkspace, NSApp, NSRunningApplication
            # Get the frontmost app before we show anything
            frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()

            # Ensure our app stays hidden from dock/switcher
            NSApp.setActivationPolicy_(2)

            # Show our window
            self.show()
            self.raise_()

            # Immediately restore focus to the previous app
            if frontmost:
                frontmost.activateWithOptions_(0)  # 0 = activate normally

        except Exception as e:
            print(f"[Indicator] AppKit focus handling failed: {e}")
            self.show()
            self.raise_()

        self._fade_animation.start()
        print(f"[Indicator] Showing at position: {self.pos().x()}, {self.pos().y()}")

    def _fade_out(self):
        """Fade out animation"""
        self._fade_animation.stop()
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_out_finished)
        self._fade_animation.start()

    def _on_fade_out_finished(self):
        """Handle fade out completion"""
        self._fade_animation.finished.disconnect(self._on_fade_out_finished)
        if self._opacity_effect.opacity() < 0.1:
            self.hide()
            self.dot.stop_pulsing()
            self.spinner.stop_spinning()


# Test the indicator
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    indicator = RecordingIndicator()

    # Test cycle: recording -> transcribing -> hide
    def cycle():
        print("Showing recording...")
        indicator.show_recording()
        QTimer.singleShot(3000, lambda: (print("Showing transcribing..."), indicator.show_transcribing()))
        QTimer.singleShot(5000, lambda: (print("Hiding..."), indicator.hide_indicator()))
        QTimer.singleShot(7000, cycle)  # Repeat

    cycle()

    sys.exit(app.exec())
