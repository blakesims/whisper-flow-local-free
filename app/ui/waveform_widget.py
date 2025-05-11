import sys
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QColor, QPolygonF
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
        self._background_color = QColor("#1a1b26")
        
        self._idle_color = QColor("#7aa2f7")      # Tokyo Night blue
        self._recording_color = QColor("#f7768e") # Tokyo Night red/pink
        # self._processing_color = QColor("#73daca") # Tokyo Night cyan/teal
        
        self._current_waveform_color = self._idle_color
        self._status = WaveformStatus.IDLE
        
        self.num_display_points = 200 # How many points to show in the waveform display

        # Generate some initial test data (raw audio like)
        self.update_waveform_data(self.generate_sample_raw_audio(self.num_display_points * 10)) # Generate more raw samples

    def set_status(self, status):
        if status == WaveformStatus.IDLE:
            self._current_waveform_color = self._idle_color
        elif status == WaveformStatus.RECORDING:
            self._current_waveform_color = self._recording_color
        # elif status == WaveformStatus.PROCESSING:
        #     self._current_waveform_color = self._processing_color
        else:
            self._current_waveform_color = self._idle_color # Default to idle
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
        painter.fillRect(self.rect(), self._background_color)

        if self._display_amplitudes.size == 0:
            return

        width = self.width()
        height = self.height()
        mid_y = height / 2
        num_points_to_draw = len(self._display_amplitudes)
        
        if num_points_to_draw < 2:
            return

        points = QPolygonF()
        points.append(QPointF(0, mid_y))

        for i, amp in enumerate(self._display_amplitudes):
            x = (i / (num_points_to_draw -1)) * width if num_points_to_draw > 1 else 0
            # Amplitude is now expected to be positive (from np.max(np.abs(segment)))
            # So, we draw it upwards from mid_y and can mirror for a symmetric look if desired
            # For now, just simple positive amplitude representation.
            y = mid_y - (amp * (height / 2.5)) 
            points.append(QPointF(x, y))
        
        points.append(QPointF(width, mid_y))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._current_waveform_color) # Use status-dependent color
        painter.drawPolygon(points)

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