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


# macOS system sounds - use same sound for start/stop, different for success
SOUND_TOGGLE = "/System/Library/Sounds/Pop.aiff"   # Used for start AND stop
SOUND_DONE = "/System/Library/Sounds/Glass.aiff"   # Success sound


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

        # Window flags: frameless, always on top, tool window (no dock icon)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )

        # Transparent background for rounded corners
        self.setAttribute(Qt.WA_TranslucentBackground)

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
            # Center horizontally, 80px from bottom
            x = geometry.x() + (geometry.width() - self.width()) // 2
            y = geometry.y() + geometry.height() - self.height() - 80
            self.move(x, y)
            print(f"[Indicator] Screen: {screen.name()}, Geometry: {geometry}")

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

        self.label.setText("Recording...")
        self.label.setStyleSheet("color: #FF3B30;")  # Red

        self.spinner.hide()
        self.spinner.stop_spinning()

        self.dot.show()
        self.dot.start_pulsing()

        self.adjustSize()
        self._position_window()
        self._fade_in()

    def show_transcribing(self):
        """Show the transcribing indicator"""
        # Play toggle sound (same for start/stop)
        play_sound(SOUND_TOGGLE)

        self.label.setText("Transcribing...")
        self.label.setStyleSheet("color: #007AFF;")  # Blue

        self.dot.hide()
        self.dot.stop_pulsing()

        self.spinner.show()
        self.spinner.start_spinning()

        self.adjustSize()
        self._position_window()
        self._fade_in()

    def hide_indicator(self):
        """Hide the indicator with fade animation"""
        self._fade_out()

    def play_done_sound(self):
        """Play the success/done sound"""
        play_sound(SOUND_DONE)

    def _fade_in(self):
        """Fade in animation"""
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self.show()
        self.raise_()  # Bring to front
        self.activateWindow()  # Make sure it's active
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
