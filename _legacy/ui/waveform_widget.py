import sys
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QColor, QPolygonF, QPen
from PySide6.QtCore import Qt, QPointF
import numpy as np

class WaveformStatus:
    IDLE = 0
    RECORDING = 1
    # PROCESSING = 2 # For future use

class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 100)
        self._display_amplitudes = np.array([], dtype=np.float32) # Renamed for clarity
        self._background_color = QColor("#1a1b26") # Transparent, effectively
        
        self._idle_color = QColor("#a9b1d6")      # Light blue for idle/waveform line
        self._recording_color = QColor("#f7768e") # Red/pink for recording line (can be same as idle if preferred)
        # self._processing_color = QColor("#73daca") # Tokyo Night cyan/teal
        
        self._current_waveform_pen_color = self._idle_color
        self._status = WaveformStatus.IDLE
        self.visual_gain = 3.0 # Added visual gain
        self.waveform_pen_width = 2 # Pen width for the waveform line
        
        self.num_display_points = 200 # How many points to show in the waveform display

        # Generate some initial test data (raw audio like)
        self.update_waveform_data(self.generate_sample_raw_audio(self.num_display_points * 10)) # Generate more raw samples

    def set_status(self, status):
        if status == WaveformStatus.IDLE:
            self._current_waveform_pen_color = self._idle_color
        elif status == WaveformStatus.RECORDING:
            # Let's use a different color for recording to keep that feature, e.g., a brighter blue or the red
            self._current_waveform_pen_color = self._recording_color 
        # elif status == WaveformStatus.PROCESSING:
        #     self._current_waveform_color = self._processing_color
        else:
            self._current_waveform_pen_color = self._idle_color # Default to idle
        self._status = status
        self.update() # Trigger repaint to show new color

    def update_waveform_data(self, raw_audio_chunk):
        """Process a chunk of raw audio data and update the display amplitudes."""
        if not isinstance(raw_audio_chunk, np.ndarray) or raw_audio_chunk.ndim != 1:
            self._display_amplitudes = np.zeros(self.num_display_points, dtype=np.float32)
            self.update()
            return

        if raw_audio_chunk.size == 0:
            self._display_amplitudes = np.zeros(self.num_display_points, dtype=np.float32)
            self.update()
            return

        # Downsample/aggregate raw audio to fit num_display_points
        # This is a simple way: take max absolute value in segments
        segment_length = max(1, raw_audio_chunk.size // self.num_display_points)
        processed_amps = []
        for i in range(self.num_display_points):
            start = i * segment_length
            end = start + segment_length
            if start < raw_audio_chunk.size:
                segment = raw_audio_chunk[start:end]
                if segment.size > 0:
                    processed_amps.append(np.max(np.abs(segment)))
                else:
                    processed_amps.append(0)
            else:
                processed_amps.append(0)
        
        self._display_amplitudes = np.array(processed_amps, dtype=np.float32)
        self.update() # Trigger a repaint

    def generate_sample_raw_audio(self, num_samples):
        """Generates some random raw audio data for testing (values between -1 and 1)."""
        # Simulates some variance in amplitude
        data = np.random.rand(num_samples).astype(np.float32) * 2 - 1 
        # Modulate amplitude to make it look more like a waveform
        envelope = np.sin(np.linspace(0, np.pi * 2, num_samples))**2 
        return data * envelope 

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Background is part of the main window now, or could be set here if needed
        # For a truly transparent widget background to see main window, ensure parent styling allows it,
        # or set Qt.WA_StyledBackground and use transparent background-color in stylesheet for this widget.
        # For now, let's assume the main window bg provides the dark theme and this widget is clear.
        # painter.fillRect(self.rect(), self._background_color) # This would fill it with #1a1b26
        # To make the widget itself transparent to what's behind it (if nested), more complex styling is needed.
        # We will draw on the existing background from MainWindow.

        if self._display_amplitudes.size == 0:
            return

        width = self.width()
        height = self.height()
        mid_y = height / 2
        num_points_to_draw = len(self._display_amplitudes)
        
        if num_points_to_draw < 2:
            return

        points_top = QPolygonF()
        points_bottom = QPolygonF()

        for i, amp in enumerate(self._display_amplitudes):
            x = (i / (num_points_to_draw -1)) * width if num_points_to_draw > 1 else 0
            scaled_amp_h = amp * self.visual_gain * (height / 2.5) # Scaled amplitude for half-height
            
            y_top = mid_y - scaled_amp_h
            y_bottom = mid_y + scaled_amp_h
            
            # Ensure y does not go out of bounds due to gain
            y_top = max(0, min(height, y_top)) 
            y_bottom = max(0, min(height, y_bottom))

            points_top.append(QPointF(x, y_top))
            points_bottom.append(QPointF(x, y_bottom))
        
        pen = QPen(self._current_waveform_pen_color)
        pen.setWidth(self.waveform_pen_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush) # No fill for the waveform itself
        
        painter.drawPolyline(points_top)
        painter.drawPolyline(points_bottom)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    widget = WaveformWidget()
    widget.setStyleSheet("border: 1px solid #24283b;")
    widget.show()
    
    # Using a list to hold the index, to avoid nonlocal issues in this scope
    test_status_tracker = {"index": 0}
    test_statuses = [WaveformStatus.IDLE, WaveformStatus.RECORDING]

    def update_test_data_and_status():
        num_raw_samples = np.random.randint(500, 5000) 
        new_data = widget.generate_sample_raw_audio(num_raw_samples)
        widget.update_waveform_data(new_data)
        
        # Cycle through statuses
        test_status_tracker["index"] = (test_status_tracker["index"] + 1) % len(test_statuses)
        widget.set_status(test_statuses[test_status_tracker["index"]])

    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(update_test_data_and_status)
    timer.start(1000) 
    
    sys.exit(app.exec()) 