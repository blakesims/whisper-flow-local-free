from PySide6.QtCore import QThread, Signal
import numpy as np
import sounddevice as sd
import time
import tempfile
import os
from scipy.io import wavfile

class AudioRecorder(QThread):
    """
    Handles audio recording in a separate thread.
    Communicates with the main thread via signals.
    """
    recording_started_signal = Signal()
    recording_stopped_signal = Signal(str) # payload: final status message
    recording_paused_signal = Signal()
    recording_resumed_signal = Signal()
    error_signal = Signal(str)
    new_audio_chunk_signal = Signal(np.ndarray)

    def __init__(self, parent=None, device=None):
        super().__init__(parent)

        self.sample_rate = 16000
        self.channels = 1
        self.device = device  # None = system default, or device index/name
        self.dtype = 'float32' # Corresponds to np.float32 for wavfile.write
        self.chunk_size = 1024

        self._is_recording = False
        self._is_paused = False
        self._audio_stream = None
        self._recording_actually_started = False
        self._audio_buffer = [] # For accumulating recorded audio data

    def set_device(self, device):
        """Set the input device (index or name). None = system default."""
        self.device = device

    @staticmethod
    def refresh_devices():
        """Force refresh of audio device list (handles hot-plug)."""
        try:
            # Reset sounddevice to re-query PortAudio devices
            sd._terminate()
            sd._initialize()
            print("AudioRecorder: Device list refreshed")
        except Exception as e:
            print(f"AudioRecorder: Could not refresh devices: {e}")

    @staticmethod
    def get_input_devices(refresh=False):
        """Get list of available input devices as (index, name) tuples."""
        if refresh:
            AudioRecorder.refresh_devices()
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                devices.append((i, dev['name']))
        return devices

    @staticmethod
    def get_default_input_device(refresh=False):
        """Get the default input device index and name."""
        if refresh:
            AudioRecorder.refresh_devices()
        try:
            dev = sd.query_devices(kind='input')
            return (dev['index'] if 'index' in dev else None, dev['name'])
        except Exception:
            return (None, "Unknown")

    def _find_working_device(self):
        """Find a working input device with fallback logic.

        Priority:
        1. Configured device (self.device) if it exists and works
        2. System default input device
        3. Any available input device

        Returns device index/name or None if nothing works.
        """
        # Refresh device list to handle hot-plug
        AudioRecorder.refresh_devices()

        available_devices = AudioRecorder.get_input_devices()
        if not available_devices:
            print("AudioRecorder: No input devices available!")
            return None

        available_indices = {idx for idx, name in available_devices}
        available_names = {name for idx, name in available_devices}

        # Try 1: Configured device
        if self.device is not None:
            # Check if configured device is available
            if isinstance(self.device, int) and self.device in available_indices:
                try:
                    sd.check_input_settings(device=self.device, channels=self.channels,
                                           samplerate=self.sample_rate, dtype=self.dtype)
                    print(f"AudioRecorder: Using configured device index {self.device}")
                    return self.device
                except Exception as e:
                    print(f"AudioRecorder: Configured device {self.device} failed: {e}")
            elif isinstance(self.device, str) and self.device in available_names:
                try:
                    sd.check_input_settings(device=self.device, channels=self.channels,
                                           samplerate=self.sample_rate, dtype=self.dtype)
                    print(f"AudioRecorder: Using configured device '{self.device}'")
                    return self.device
                except Exception as e:
                    print(f"AudioRecorder: Configured device '{self.device}' failed: {e}")
            else:
                print(f"AudioRecorder: Configured device {self.device} not found in available devices")

        # Try 2: System default (device=None)
        try:
            sd.check_input_settings(device=None, channels=self.channels,
                                   samplerate=self.sample_rate, dtype=self.dtype)
            default_idx, default_name = AudioRecorder.get_default_input_device()
            print(f"AudioRecorder: Using system default device: {default_name}")
            return None  # None means system default in sounddevice
        except Exception as e:
            print(f"AudioRecorder: System default device failed: {e}")

        # Try 3: Any available input device
        for idx, name in available_devices:
            try:
                sd.check_input_settings(device=idx, channels=self.channels,
                                       samplerate=self.sample_rate, dtype=self.dtype)
                print(f"AudioRecorder: Falling back to device: {name} (index {idx})")
                return idx
            except Exception as e:
                print(f"AudioRecorder: Device {name} (index {idx}) failed: {e}")

        print("AudioRecorder: No working input device found!")
        return None

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            # Make it clear this status is from the stream callback
            self.error_signal.emit(f"Audio Stream Status: {status}")
            # Potentially serious errors might require stopping the stream or recording
            # For now, we just report.
        
        if self._is_recording and not self._is_paused and indata.size > 0:
            # Always work with a copy of indata
            chunk_copy = indata.copy()
            self.new_audio_chunk_signal.emit(chunk_copy)
            self._audio_buffer.append(chunk_copy)

    def _save_recording_to_file(self, file_path):
        """Saves the content of _audio_buffer to a WAV file."""
        if not self._audio_buffer:
            print("AudioRecorder: Audio buffer is empty. Nothing to save.")
            return False
        
        try:
            concatenated_data = np.concatenate(self._audio_buffer)
            # Ensure data is in a format scipy.io.wavfile.write expects.
            # If self.dtype is 'float32', data should be between -1 and 1.
            # If integer types were used, they'd need to be scaled to their respective ranges.
            # Current setup with float32 is fine.
            wavfile.write(file_path, self.sample_rate, concatenated_data)
            print(f"AudioRecorder: Recording saved to {file_path}")
            return True
        except Exception as e:
            self.error_signal.emit(f"Error saving WAV file: {str(e)}")
            print(f"AudioRecorder: Error saving WAV file to {file_path}: {e}")
            return False

    def run(self):
        if not self._is_recording:
            self.error_signal.emit("Recording not properly initiated (is_recording is false).")
            return

        self._recording_actually_started = False
        self._audio_buffer = [] # Reset buffer for the new recording session
        self._is_paused = False # Ensure recording starts in unpaused state

        try:
            # Find a working device with hot-plug support and fallback
            working_device = self._find_working_device()
            if working_device is None and self.device is not None:
                # _find_working_device returns None for system default, but also if nothing works
                # Check if we actually have any devices
                if not AudioRecorder.get_input_devices():
                    self.error_signal.emit("No audio input devices available")
                    self._is_recording = False
                    return

            self._audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=working_device,
                dtype=self.dtype,
                blocksize=self.chunk_size,
                callback=self._audio_callback
            )
            self._audio_stream.start() # This starts invoking the callback
            self.recording_started_signal.emit()
            self._recording_actually_started = True
            
            # The thread needs to stay alive while the stream is active and recording is ongoing.
            # The callback handles the data. This loop checks flags and allows the thread to yield.
            while self._is_recording and self._audio_stream and self._audio_stream.active:
                time.sleep(0.05) # Sleep for a short duration

        except sd.PortAudioError as pae:
            self.error_signal.emit(f"PortAudio Error: {str(pae)}. Check audio device & permissions.")
            self._is_recording = False 
        except ValueError as ve: # Often from check_input_settings or invalid stream params
            self.error_signal.emit(f"ValueError (invalid audio parameters): {str(ve)}")
            self._is_recording = False
        except Exception as e: # Catch-all for other unexpected errors
            self.error_signal.emit(f"Unexpected error in AudioRecorder run: {str(e)}")
            self._is_recording = False # Critical error, stop recording
        finally:
            if self._audio_stream:
                stream_was_active = self._audio_stream.active
                try:
                    if stream_was_active:
                        self._audio_stream.stop()
                except Exception as e: # Broad catch as stream operations can fail variously
                    print(f"AudioRecorder: Exception during stream.stop(): {e}")
                try:
                    self._audio_stream.close()
                except Exception as e:
                    print(f"AudioRecorder: Exception during stream.close(): {e}")
                self._audio_stream = None
            
            saved_file_path = None
            if self._recording_actually_started and self._is_recording: # Indicates an error stopped an active recording
                final_status_message = "Recording terminated due to error. No file saved."
            elif self._recording_actually_started and not self._is_recording: # Normal stop via stop_recording()
                if self._audio_buffer:
                    try:
                        # Create a temporary file to save the recording
                        temp_dir = tempfile.gettempdir()
                        temp_file_name = f"recording_{int(time.time())}_{np.random.randint(1000, 9999)}.wav"
                        saved_file_path = os.path.join(temp_dir, temp_file_name)
                        if self._save_recording_to_file(saved_file_path):
                            final_status_message = saved_file_path # Success: message is the path
                        else:
                            final_status_message = "Recording finished, but failed to save file."
                            saved_file_path = None # Ensure path is None if save failed
                    except Exception as e:
                        print(f"AudioRecorder: Error creating temp file name or path: {e}")
                        final_status_message = "Recording finished, but error during temp file setup."
                        saved_file_path = None
                else:
                    final_status_message = "Recording finished, but no audio data was captured."
            elif not self._recording_actually_started:
                 final_status_message = "Recording failed to start or was stopped before activation. No file saved."
            else: # Should not be reached if logic is correct
                final_status_message = "Recording process terminated with unknown state."

            if self._recording_actually_started or not self._is_recording:
                 # Emit stopped signal if recording was ever started OR if it's a clean stop (even if it never fully started due to quick stop)
                self.recording_stopped_signal.emit(final_status_message if saved_file_path is None else saved_file_path)
            
            self._is_recording = False
            self._is_paused = False
            self._recording_actually_started = False
            # self._audio_buffer is cleared at the start of the next run()

    def start_recording(self):
        if self.isRunning():
            if self._is_recording:
                print("AudioRecorder: start_recording called but already recording.")
                return
            else: # Thread is running, but not _is_recording (e.g., after a stop or error)
                print("AudioRecorder: Thread active but not recording. Waiting for previous run to complete...")
                self.wait() # Wait for run() to finish its cleanup

        # After wait, or if not running initially, check _is_recording again
        if self._is_recording: # Should be false now if wait() was effective
             print("AudioRecorder: Still in recording state after wait. Aborting start.")
             return

        self._is_recording = True # Set the flag that run() will check
        # self._audio_buffer = [] # Moved to the beginning of run()
        print("AudioRecorder: Starting QThread for recording...")
        self.start() # Calls the run() method in a new thread

    def stop_recording(self):
        if not self._is_recording and not self.isRunning():
            print("AudioRecorder: stop_recording called but not recording or thread not active.")
            return
        
        print("AudioRecorder: Setting _is_recording to False to signal thread termination...")
        self._is_recording = False # Signal the run() loop to terminate
        # The run() method's finally block will handle stream cleanup and emit recording_stopped_signal.
        # For critical cleanup or UI updates that depend on thread finishing, call self.wait() from the main thread.

    def pause_recording(self):
        if not self._is_recording or self._is_paused:
            # print("AudioRecorder: Not recording or already paused.")
            return
        self._is_paused = True
        self.recording_paused_signal.emit()
        print("AudioRecorder: Recording PAUSED.")

    def resume_recording(self):
        if not self._is_recording or not self._is_paused:
            # print("AudioRecorder: Not recording or not currently paused.")
            return
        self._is_paused = False
        self.recording_resumed_signal.emit()
        print("AudioRecorder: Recording RESUMED.")

    def get_recorded_data(self):
        """
        Returns the concatenated audio data from the last complete recording.
        Returns an empty array if no data was buffered.
        """
        if not self._audio_buffer:
            return np.array([], dtype=self.dtype)
        try:
            return np.concatenate(self._audio_buffer)
        except ValueError: # If buffer is empty or contains non-compatible shapes (should not happen with current logic)
            return np.array([], dtype=self.dtype)

# Example usage (for testing purposes, remove or comment out for production)
if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget, QTextEdit, QHBoxLayout

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    class TestApp(QWidget):
        def __init__(self):
            super().__init__()
            self.recorder = AudioRecorder()
            self.log_area = QTextEdit()
            self.log_area.setReadOnly(True)
            
            self.start_button = QPushButton("Start Recording")
            self.stop_button = QPushButton("Stop Recording")
            self.pause_button = QPushButton("Pause Recording")
            self.resume_button = QPushButton("Resume Recording")
            self.get_data_button = QPushButton("Get Buffered Data") # For testing

            self.update_button_states() # Initial state

            button_layout = QHBoxLayout()
            button_layout.addWidget(self.start_button)
            button_layout.addWidget(self.stop_button)
            button_layout.addWidget(self.pause_button)
            button_layout.addWidget(self.resume_button)
            button_layout.addWidget(self.get_data_button)

            main_layout = QVBoxLayout()
            main_layout.addWidget(self.log_area)
            main_layout.addLayout(button_layout)
            self.setLayout(main_layout)

            self.start_button.clicked.connect(self.do_start)
            self.stop_button.clicked.connect(self.do_stop) 
            self.pause_button.clicked.connect(self.recorder.pause_recording)
            self.resume_button.clicked.connect(self.recorder.resume_recording)
            self.get_data_button.clicked.connect(self.do_get_data)

            self.recorder.recording_started_signal.connect(self.on_recording_started)
            self.recorder.recording_stopped_signal.connect(self.on_recording_stopped)
            self.recorder.recording_paused_signal.connect(self.on_recording_paused)
            self.recorder.recording_resumed_signal.connect(self.on_recording_resumed)
            self.recorder.error_signal.connect(self.on_error)
            self.recorder.new_audio_chunk_signal.connect(self.on_new_chunk)
            
            self.setWindowTitle("AudioRecorder Test")
            self.resize(600, 400)

        def update_button_states(self):
            is_recording = self.recorder._is_recording
            is_paused = self.recorder._is_paused
            is_running = self.recorder.isRunning() # QThread.isRunning()

            self.start_button.setEnabled(not is_recording and not is_running) # Enable if not recording AND thread not stuck
            self.stop_button.setEnabled(is_recording or is_running) # Enable if recording OR thread is active
            self.pause_button.setEnabled(is_recording and not is_paused)
            self.resume_button.setEnabled(is_recording and is_paused)
            self.get_data_button.setEnabled(not is_recording and not is_running) # Only allow if fully stopped

        def do_start(self):
            self.log_area.append("Attempting to start recording...")
            self.recorder.start_recording()
            # self.update_button_states() # State updates handled by signals mostly

        def do_stop(self):
            self.log_area.append("Attempting to stop recording...")
            self.recorder.stop_recording()
            # self.update_button_states()

        def do_get_data(self):
            self.log_area.append("Attempting to get recorded data...")
            data = self.recorder.get_recorded_data()
            if data.size > 0:
                duration = len(data) / self.recorder.sample_rate
                self.log_area.append(f"Retrieved {data.size} samples. Duration: {duration:.2f}s. Dtype: {data.dtype}.")
            else:
                self.log_area.append("No data in buffer or buffer empty.")
            self.update_button_states()


        def on_recording_started(self):
            self.log_area.append("Signal: Recording STARTED.")
            self.update_button_states()

        def on_recording_stopped(self, message):
            self.log_area.append(f"Signal: Recording STOPPED. Message: {message}")
            # Ensure thread is fully finished.
            if self.recorder.isRunning():
                self.log_area.append("Waiting for recorder QThread to finish...")
                self.recorder.wait() 
                self.log_area.append("Recorder QThread finished.")
            self.update_button_states()

        def on_error(self, error_message):
            self.log_area.append(f"Signal: ERROR - {error_message}")
            if self.recorder.isRunning():
                self.log_area.append("Error occurred. Waiting for recorder QThread to finish...")
                self.recorder.wait()
                self.log_area.append("Recorder QThread finished after error.")
            self.update_button_states()

        def on_new_chunk(self, chunk_data):
            # Limit logging frequency for performance if many chunks
            # For testing, logging every chunk is fine.
            self.log_area.append(f"Signal: New audio chunk (Size: {chunk_data.size})")

        def on_recording_paused(self):
            self.log_area.append("Signal: Recording PAUSED.")
            self.update_button_states()
        
        def on_recording_resumed(self):
            self.log_area.append("Signal: Recording RESUMED.")
            self.update_button_states()

        def closeEvent(self, event):
            if self.recorder.isRunning():
                self.log_area.append("Closing App: Stopping recorder...")
                self.recorder.stop_recording()
                if not self.recorder.wait(3000): 
                    self.log_area.append("Closing App: Recorder thread did not finish gracefully!")
                else:
                    self.log_area.append("Closing App: Recorder thread finished.")
            super().closeEvent(event)

    window = TestApp()
    window.show()
    sys.exit(app.exec()) 