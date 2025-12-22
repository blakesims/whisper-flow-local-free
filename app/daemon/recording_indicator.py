"""
Recording Indicator - Always-present floating widget for quick transcribe

Features:
- Always visible: collapsed dot when idle, expands when recording
- Draggable: move anywhere on screen, position persists
- Click to start/stop recording
- Right-click menu for settings/model selection
- Sleek rounded design with Tokyo Night theme
"""

import subprocess
import os
import json
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QApplication,
    QGraphicsOpacityEffect, QMenu, QGraphicsDropShadowEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    Property, QRect, Signal, QPoint, QSize, QParallelAnimationGroup
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont,
    QCursor, QAction, QLinearGradient
)


# macOS system sounds
SOUND_TOGGLE = "/System/Library/Sounds/Pop.aiff"

# Settings file for position persistence
SETTINGS_DIR = os.path.expanduser("~/Library/Application Support/WhisperTranscribeUI")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# Tokyo Night color palette
COLORS = {
    'bg_dark': QColor(26, 27, 38, 240),      # #1a1b26 with alpha
    'bg_highlight': QColor(36, 40, 59, 250), # #24283b
    'blue': QColor(122, 162, 247),           # #7aa2f7
    'cyan': QColor(125, 207, 255),           # #7dcfff
    'purple': QColor(187, 154, 247),         # #bb9af7
    'green': QColor(158, 206, 106),          # #9ece6a
    'text': QColor(192, 202, 245),           # #c0caf5
    'text_dim': QColor(86, 95, 137),         # #565f89
    'border': QColor(41, 46, 66, 180),       # subtle border
}


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
            pass


def load_settings():
    """Load settings from file"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Indicator] Error loading settings: {e}")
    return {}


def save_settings(settings):
    """Save settings to file"""
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        # Load existing settings first to preserve other values
        existing = load_settings()
        existing.update(settings)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        print(f"[Indicator] Error saving settings: {e}")


class MiniWaveform(QWidget):
    """A sleek monochrome waveform visualization"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 28)
        self._samples = [0.0] * 20
        self._max_samples = 20

    def update_audio(self, audio_chunk):
        """Update with new audio data"""
        import numpy as np
        if audio_chunk is not None and len(audio_chunk) > 0:
            rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))
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
        """Paint sleek waveform bars"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_width = 3
        bar_spacing = 2
        max_height = self.height() - 6
        center_y = self.height() // 2

        for i, amplitude in enumerate(self._samples):
            x = i * (bar_width + bar_spacing)
            bar_height = max(3, int(amplitude * max_height))

            # Gradient based on amplitude
            color = QColor(COLORS['blue'])
            opacity = 0.4 + (amplitude * 0.6)
            color.setAlphaF(opacity)

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)

            y = center_y - bar_height // 2
            painter.drawRoundedRect(x, y, bar_width, bar_height, 1.5, 1.5)


class PulsingDot(QWidget):
    """A sleek pulsing dot indicator"""

    def __init__(self, size=12, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size + 4, size + 4)
        self._opacity = 1.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_direction = -1
        self._is_pulsing = False
        self._glow_radius = 0.0

    def _get_opacity(self):
        return self._opacity

    def _set_opacity(self, value):
        self._opacity = value
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def start_pulsing(self):
        if not self._is_pulsing:
            self._is_pulsing = True
            self._pulse_timer.start(40)

    def stop_pulsing(self):
        self._is_pulsing = False
        self._pulse_timer.stop()
        self._opacity = 1.0
        self._glow_radius = 0.0
        self.update()

    def _pulse(self):
        self._opacity += self._pulse_direction * 0.04
        self._glow_radius += self._pulse_direction * 0.5
        if self._opacity <= 0.4:
            self._pulse_direction = 1
            self._opacity = 0.4
        elif self._opacity >= 1.0:
            self._pulse_direction = -1
            self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = self.rect().center()
        radius = self._size // 2

        # Outer glow when pulsing
        if self._is_pulsing and self._glow_radius > 0:
            glow_color = QColor(COLORS['cyan'])
            glow_color.setAlphaF(0.2 * self._opacity)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.NoPen)
            glow_r = radius + self._glow_radius
            painter.drawEllipse(center, glow_r, glow_r)

        # Main dot
        color = QColor(COLORS['cyan'])
        color.setAlphaF(self._opacity)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)


class SpinnerWidget(QWidget):
    """A sleek spinning indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._is_spinning = False

    def start_spinning(self):
        if not self._is_spinning:
            self._is_spinning = True
            self._timer.start(40)

    def stop_spinning(self):
        self._is_spinning = False
        self._timer.stop()
        self._angle = 0
        self.update()

    def _rotate(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)

        color = QColor(COLORS['blue'])
        pen = QPen(color)
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)

        radius = 5
        for i in range(8):
            alpha = 1.0 - (i * 0.11)
            color.setAlphaF(max(0.15, alpha))
            pen.setColor(color)
            painter.setPen(pen)
            painter.rotate(45)
            painter.drawLine(0, -radius, 0, -radius - 2)


class RecordingIndicator(QWidget):
    """
    Always-present floating indicator widget.

    States:
    - IDLE: Small dot, subtle, draggable
    - RECORDING: Expanded with waveform, pulsing dot
    - TRANSCRIBING: Spinner with progress

    Interactions:
    - Click: Toggle recording
    - Right-click: Settings menu
    - Drag: Move anywhere
    """

    # Signals for daemon communication
    toggle_recording_requested = Signal()
    model_change_requested = Signal(str)
    quit_requested = Signal()

    # State constants
    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_TRANSCRIBING = "transcribing"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = self.STATE_IDLE
        self._current_model = "base"
        self._available_models = ["tiny", "base", "small", "medium", "large-v2"]

        # Window flags for always-on-top, frameless, no focus stealing
        # Using SplashScreen type for overlay-style behavior on macOS
        self.setWindowFlags(
            Qt.SplashScreen |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        # Drag state
        self._drag_position = None
        self._is_dragging = False

        # Setup UI
        self._setup_ui()

        # Size animation for expand/collapse
        self._size_animation = QPropertyAnimation(self, b"minimumWidth")
        self._size_animation.setDuration(200)
        self._size_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Opacity for fade effects
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # Load saved position or use default
        self._load_position()

        # Cursor following timer (only during recording)
        self._follow_cursor_timer = QTimer(self)
        self._follow_cursor_timer.timeout.connect(self._check_screen_change)
        self._last_screen = None

        # Hover state for visual feedback
        self._is_hovered = False
        self.setMouseTracking(True)

        # Start in idle state
        self._set_idle_state()

    def _setup_ui(self):
        """Setup the UI components"""
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(6)

        # Recording dot (for recording state only)
        self.recording_dot = PulsingDot(size=10)
        self.recording_dot.hide()
        self._layout.addWidget(self.recording_dot)

        # Spinner for transcribing
        self.spinner = SpinnerWidget()
        self.spinner.hide()
        self._layout.addWidget(self.spinner)

        # Waveform (recording state only)
        self.waveform = MiniWaveform()
        self.waveform.hide()
        self._layout.addWidget(self.waveform)

        # Status label
        self.label = QLabel("")
        self.label.setFont(QFont(".AppleSystemUIFont", 11, QFont.Medium))
        self.label.setStyleSheet(f"color: {COLORS['text'].name()};")
        self.label.hide()
        self._layout.addWidget(self.label)

        self.setLayout(self._layout)

    def _load_position(self):
        """Load saved position from settings"""
        settings = load_settings()
        x = settings.get('indicator_x')
        y = settings.get('indicator_y')

        if x is not None and y is not None:
            # Validate position is on a screen
            point = QPoint(x, y)
            screen = QApplication.screenAt(point)
            if screen:
                self.move(x, y)
                print(f"[Indicator] Restored position: ({x}, {y})")
                return

        # Default position: bottom center of primary screen
        self._position_default()

    def _position_default(self):
        """Position at bottom center of current screen (near cursor)"""
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if not screen:
            screen = QApplication.primaryScreen()

        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            # Very bottom with minimal padding (12px from bottom)
            y = geo.y() + geo.height() - self.height() - 12
            self.move(x, y)
            print(f"[Indicator] Position: ({x}, {y}) on {screen.name()}")

    def _save_position(self):
        """Save current position to settings"""
        save_settings({
            'indicator_x': self.x(),
            'indicator_y': self.y()
        })

    def _set_idle_state(self):
        """Set to collapsed idle state - small pill, no animation"""
        self._state = self.STATE_IDLE

        # Hide all elements - idle is just the pill background
        self.recording_dot.hide()
        self.recording_dot.stop_pulsing()
        self.spinner.hide()
        self.spinner.stop_spinning()
        self.waveform.hide()
        self.label.hide()

        # Small pill size (no inner elements shown)
        self.setFixedHeight(20)
        self.setMinimumWidth(36)
        self.setMaximumWidth(36)
        self.adjustSize()

        # Follow cursor to active screen even in idle
        self._follow_cursor_timer.start(1000)  # Check every 1s
        self.update()

    def _set_recording_state(self):
        """Set to expanded recording state"""
        self._state = self.STATE_RECORDING
        play_sound(SOUND_TOGGLE)

        # Show recording elements
        self.spinner.hide()
        self.spinner.stop_spinning()
        self.label.hide()

        self.recording_dot.show()
        self.recording_dot.start_pulsing()
        self.waveform.clear()
        self.waveform.show()

        # Expand
        self.setFixedHeight(28)
        self.setMinimumWidth(130)
        self.setMaximumWidth(250)
        self.adjustSize()

        # Reposition for new size
        self._position_default()

        # Keep checking for screen changes
        self._follow_cursor_timer.start(500)

        self.update()

    def _set_transcribing_state(self):
        """Set to transcribing state"""
        self._state = self.STATE_TRANSCRIBING
        play_sound(SOUND_TOGGLE)

        # Hide other elements
        self.recording_dot.hide()
        self.recording_dot.stop_pulsing()
        self.waveform.hide()

        # Show spinner and label
        self.spinner.show()
        self.spinner.start_spinning()
        self.label.setText("0%")
        self.label.setStyleSheet(f"color: {COLORS['blue'].name()};")
        self.label.show()

        # Compact size for transcribing
        self.setFixedHeight(24)
        self.setMinimumWidth(60)
        self.setMaximumWidth(100)
        self.adjustSize()

        # Reposition for new size
        self._position_default()

        self._follow_cursor_timer.stop()
        self.update()

    def _check_screen_change(self):
        """Check if we should move to a different screen (follows cursor)"""
        cursor_pos = QCursor.pos()
        current_screen = QApplication.screenAt(cursor_pos)

        if current_screen and current_screen != self._last_screen:
            self._last_screen = current_screen
            # Move to bottom center of new screen
            geo = current_screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() - self.height() - 12
            self.move(x, y)
            print(f"[Indicator] Moved to screen: {current_screen.name()}")

    # === Public API for daemon ===

    def show_recording(self):
        """Called by daemon to show recording state"""
        self._set_recording_state()
        self._ensure_visible()

    def show_transcribing(self, progress: int = 0):
        """Called by daemon to show transcribing state"""
        self._set_transcribing_state()
        self.update_progress(progress)
        self._ensure_visible()

    def show_idle(self):
        """Called by daemon to return to idle state"""
        self._set_idle_state()
        self._ensure_visible()

    def hide_indicator(self):
        """Legacy method - now just returns to idle"""
        self.show_idle()

    def update_progress(self, progress: int):
        """Update transcription progress"""
        self.label.setText(f"{progress}%")
        QApplication.processEvents()

    def update_waveform(self, audio_chunk):
        """Update waveform with audio data"""
        if self._state == self.STATE_RECORDING and self.waveform.isVisible():
            self.waveform.update_audio(audio_chunk)

    def set_current_model(self, model: str):
        """Set the current model name"""
        self._current_model = model

    def set_available_models(self, models: list):
        """Set the list of available models"""
        self._available_models = models

    # === Event handlers ===

    def _ensure_visible(self):
        """Ensure the widget is visible without stealing focus"""
        try:
            from AppKit import NSWorkspace, NSApp
            frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
            # Accessory policy (1) - hidden from dock but windows visible
            NSApp.setActivationPolicy_(1)

            self.show()
            self.raise_()

            if frontmost:
                frontmost.activateWithOptions_(0)
        except Exception:
            self.show()
            self.raise_()

    def paintEvent(self, event):
        """Paint sleek rounded background"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        # Subtle outer glow on hover
        if self._is_hovered:
            glow = QColor(COLORS['cyan'])
            glow.setAlphaF(0.25)
            painter.setBrush(Qt.NoBrush)
            pen = QPen(glow)
            pen.setWidth(2)
            painter.setPen(pen)
            radius = rect.height() // 2  # Pill shape
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

        # Background - solid dark for idle, gradient for active states
        if self._state == self.STATE_IDLE:
            bg_color = QColor(COLORS['bg_dark'])
            bg_color.setAlphaF(0.9)
            painter.setBrush(QBrush(bg_color))
        else:
            gradient = QLinearGradient(0, 0, 0, rect.height())
            gradient.setColorAt(0, COLORS['bg_highlight'])
            gradient.setColorAt(1, COLORS['bg_dark'])
            painter.setBrush(QBrush(gradient))

        # Subtle border
        border_color = QColor(COLORS['border'])
        border_pen = QPen(border_color)
        border_pen.setWidth(1)
        painter.setPen(border_pen)

        # Pill shape (full radius for height)
        radius = rect.height() // 2
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

        # For idle state, draw a small centered dot
        if self._state == self.STATE_IDLE:
            dot_color = QColor(COLORS['cyan'])
            dot_color.setAlphaF(0.7)
            painter.setBrush(QBrush(dot_color))
            painter.setPen(Qt.NoPen)
            center = rect.center()
            painter.drawEllipse(center, 4, 4)

    def enterEvent(self, event):
        """Mouse entered widget"""
        self._is_hovered = True
        self.setCursor(Qt.PointingHandCursor)
        self.update()

    def leaveEvent(self, event):
        """Mouse left widget"""
        self._is_hovered = False
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        """Handle mouse press for dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = False
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if event.buttons() & Qt.LeftButton and self._drag_position:
            # Mark as dragging if moved more than a few pixels
            if not self._is_dragging:
                delta = event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_position
                if delta.manhattanLength() > 5:
                    self._is_dragging = True

            if self._is_dragging:
                new_pos = event.globalPosition().toPoint() - self._drag_position
                self.move(new_pos)
                event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.LeftButton:
            if self._is_dragging:
                # Save position after drag
                self._save_position()
                print(f"[Indicator] Position saved: ({self.x()}, {self.y()})")
            else:
                # Click to toggle recording
                self.toggle_recording_requested.emit()

            self._drag_position = None
            self._is_dragging = False
            event.accept()

    def _show_context_menu(self, pos):
        """Show right-click context menu"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1b26;
                border: 1px solid #3b4261;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                color: #c0caf5;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b4261;
            }
            QMenu::separator {
                height: 1px;
                background: #3b4261;
                margin: 4px 8px;
            }
        """)

        # Recording toggle
        if self._state == self.STATE_RECORDING:
            action_record = menu.addAction("Stop Recording")
        else:
            action_record = menu.addAction("Start Recording")
        action_record.triggered.connect(self.toggle_recording_requested.emit)

        menu.addSeparator()

        # Model submenu
        model_menu = menu.addMenu("Model")
        model_menu.setStyleSheet(menu.styleSheet())

        for model in self._available_models:
            action = model_menu.addAction(model)
            action.setCheckable(True)
            if model == self._current_model:
                action.setChecked(True)
            action.triggered.connect(lambda checked, m=model: self.model_change_requested.emit(m))

        menu.addSeparator()

        # Status info
        status_action = menu.addAction(f"Status: {self._state.capitalize()}")
        status_action.setEnabled(False)

        menu.addSeparator()

        # Quit
        quit_action = menu.addAction("Quit Daemon")
        quit_action.triggered.connect(self.quit_requested.emit)

        # Show menu at cursor position
        menu.exec(pos)


# Test the indicator
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    indicator = RecordingIndicator()

    def on_toggle():
        if indicator._state == RecordingIndicator.STATE_IDLE:
            print(">>> Starting recording...")
            indicator.show_recording()
        elif indicator._state == RecordingIndicator.STATE_RECORDING:
            print(">>> Stopping, transcribing...")
            indicator.show_transcribing()
            # Simulate progress
            for i in range(0, 101, 20):
                QTimer.singleShot(i * 50, lambda p=i: indicator.update_progress(p))
            QTimer.singleShot(3000, indicator.show_idle)
        else:
            indicator.show_idle()

    def on_model_change(model):
        print(f">>> Model change requested: {model}")
        indicator.set_current_model(model)

    def on_quit():
        print(">>> Quit requested")
        app.quit()

    indicator.toggle_recording_requested.connect(on_toggle)
    indicator.model_change_requested.connect(on_model_change)
    indicator.quit_requested.connect(on_quit)

    indicator.show_idle()
    indicator.show()

    print("Click to toggle recording, right-click for menu, drag to move")

    sys.exit(app.exec())
