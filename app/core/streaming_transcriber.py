"""
Streaming Transcriber - Transcribes audio segments while recording continues.

Instead of waiting for recording to finish, this component:
1. Receives audio chunks as they're recorded
2. Accumulates them into segments using VAD to find natural speech pauses
3. Transcribes each segment in a background thread
4. Merges results with overlap handling
5. On recording stop, only the final untranscribed audio needs processing

VAD (Voice Activity Detection) finds natural speech pauses for segment boundaries
instead of cutting at fixed intervals. Falls back to fixed intervals if VAD
library is not installed.

Result: perceived transcription time drops from "entire recording" to "last segment only".
"""

import threading
import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


# Tuning constants
SEGMENT_DURATION = 3.0  # seconds of new audio before triggering transcription (fallback)
OVERLAP_DURATION = 0.5  # seconds of overlap between segments for boundary coherence
MIN_SEGMENT_LENGTH = 1.0  # minimum seconds of audio worth transcribing
MAX_SEGMENT_DURATION = 5.0  # maximum seconds before forcing transcription (VAD mode)
SAMPLE_RATE = 16000

# VAD constants
VAD_WINDOW_SAMPLES = 512  # 32ms at 16kHz (silero-vad-lite window size)
VAD_SPEECH_THRESHOLD = 0.5  # probability above which audio is considered speech
VAD_SILENCE_DURATION = 0.3  # seconds of silence to trigger a segment boundary

# Try to import VAD library (optional dependency)
try:
    from silero_vad_lite import SileroVAD
    _VAD_AVAILABLE = True
except ImportError:
    _VAD_AVAILABLE = False

# Whisper hallucination tokens to filter out (not real speech)
HALLUCINATION_TOKENS = {
    "[BLANK_AUDIO]", "(blank audio)", "[SILENCE]", "(silence)",
    "(eerie music)", "(humming)", "(music)", "(birds chirping)",
    "(wind blowing)", "(footsteps)", "(door closing)",
}


class StreamingTranscriber(QObject):
    """
    Transcribes audio segments progressively while recording continues.

    Usage:
        streamer = StreamingTranscriber(transcription_service)
        streamer.start_session()
        # Feed audio chunks as they arrive:
        streamer.feed_chunk(chunk)  # int16 numpy array
        # When recording stops:
        final_text = streamer.flush()
    """

    partial_text_updated = Signal(str)  # emitted when new partial text is available

    def __init__(self, transcription_service, language: str = "en"):
        super().__init__()
        self._service = transcription_service
        self._language = language

        # Audio buffer (int16 samples at 16kHz)
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0  # total samples in buffer

        # Tracking what's been transcribed
        self._transcribed_up_to = 0  # sample index up to which we've transcribed
        self._confirmed_texts: list[str] = []  # completed segment texts
        self._last_segment_text = ""  # last segment text (for initial_prompt)

        # Threading
        self._transcribe_lock = threading.Lock()
        self._is_transcribing = False  # a segment is currently being transcribed
        self._active = False

        # VAD state (lazy-initialized on first chunk)
        self._vad = None  # SileroVAD instance or None
        self._vad_initialized = False  # whether we've attempted init
        self._vad_buffer = np.array([], dtype=np.float32)  # accumulates samples for VAD windows
        self._is_speaking = False  # current speech state
        self._silence_start_sample = 0  # sample index when silence began

    def start_session(self):
        """Reset state for a new recording session."""
        self._buffer = []
        self._buffer_samples = 0
        self._transcribed_up_to = 0
        self._confirmed_texts = []
        self._last_segment_text = ""
        self._is_transcribing = False
        self._active = True

        # Reset VAD state (keep the initialized model)
        self._vad_buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._silence_start_sample = 0

    def _init_vad(self):
        """Lazy-initialize VAD model on first use."""
        if self._vad_initialized:
            return
        self._vad_initialized = True

        if not _VAD_AVAILABLE:
            print("[StreamingTranscriber] silero-vad-lite not installed, using fixed-interval segmentation")
            return

        try:
            self._vad = SileroVAD(sample_rate=SAMPLE_RATE)
            print("[StreamingTranscriber] VAD initialized (silero-vad-lite)")
        except Exception as e:
            print(f"[StreamingTranscriber] VAD init failed, using fixed intervals: {e}")
            self._vad = None

    def _process_vad(self, chunk: np.ndarray) -> bool:
        """
        Process chunk through VAD, return True if a speech pause boundary is detected.
        The chunk is int16; VAD needs float32 in [-1, 1].
        """
        if self._vad is None:
            return False

        # Convert int16 to float32 normalized
        float_chunk = chunk.astype(np.float32) / 32768.0

        # Append to VAD buffer
        self._vad_buffer = np.concatenate([self._vad_buffer, float_chunk])

        # Process complete VAD windows (512 samples = 32ms each)
        pause_detected = False
        while len(self._vad_buffer) >= VAD_WINDOW_SAMPLES:
            window = self._vad_buffer[:VAD_WINDOW_SAMPLES].copy()
            self._vad_buffer = self._vad_buffer[VAD_WINDOW_SAMPLES:]

            score = self._vad.process(memoryview(window.data))
            is_speech = score >= VAD_SPEECH_THRESHOLD

            if is_speech:
                if not self._is_speaking:
                    self._is_speaking = True
                # Reset silence tracking while speaking
                self._silence_start_sample = self._buffer_samples
            else:
                if self._is_speaking:
                    # Transition: speaking -> silence
                    self._is_speaking = False
                    self._silence_start_sample = self._buffer_samples

                # Check if silence has lasted long enough
                silence_samples = self._buffer_samples - self._silence_start_sample
                silence_duration = silence_samples / SAMPLE_RATE
                if silence_duration >= VAD_SILENCE_DURATION:
                    pause_detected = True

        return pause_detected

    def feed_chunk(self, chunk: np.ndarray):
        """
        Feed an audio chunk from the recorder.
        Called from the audio callback — must be fast.
        """
        if not self._active:
            return

        # Lazy-init VAD on first chunk
        if not self._vad_initialized:
            self._init_vad()

        self._buffer.append(chunk.copy())
        self._buffer_samples += len(chunk)

        # Don't trigger if already transcribing
        if self._is_transcribing:
            return

        new_samples = self._buffer_samples - self._transcribed_up_to
        new_duration = new_samples / SAMPLE_RATE

        if self._vad is not None:
            # VAD mode: trigger on speech pause (with min/max duration guards)
            pause_detected = self._process_vad(chunk)

            if pause_detected and new_duration >= MIN_SEGMENT_LENGTH:
                self._transcribe_next_segment()
            elif new_duration >= MAX_SEGMENT_DURATION:
                # Fallback: force transcription after max duration
                self._transcribe_next_segment()
        else:
            # Fixed-interval fallback (no VAD)
            if new_duration >= SEGMENT_DURATION:
                self._transcribe_next_segment()

    def _get_full_buffer(self) -> np.ndarray:
        """Concatenate all buffered chunks into one array."""
        if not self._buffer:
            return np.array([], dtype=np.int16)
        return np.concatenate(self._buffer)

    def _transcribe_next_segment(self):
        """Trigger transcription of the next segment in a background thread."""
        self._is_transcribing = True

        # Grab the audio segment: overlap + new audio
        full_audio = self._get_full_buffer()
        overlap_samples = int(OVERLAP_DURATION * SAMPLE_RATE)

        # Start from (transcribed_up_to - overlap) to capture boundary context
        seg_start = max(0, self._transcribed_up_to - overlap_samples)
        segment = full_audio[seg_start:self._buffer_samples]

        # Mark where we've now covered
        new_transcribed_up_to = self._buffer_samples

        # Build initial_prompt from last confirmed text for context continuity
        initial_prompt = self._last_segment_text[-200:] if self._last_segment_text else None

        # Run transcription in a thread to not block the audio callback
        thread = threading.Thread(
            target=self._do_transcribe,
            args=(segment, new_transcribed_up_to, initial_prompt),
            daemon=True,
        )
        thread.start()

    def _do_transcribe(self, segment: np.ndarray, up_to: int, initial_prompt: Optional[str]):
        """Run transcription (called in background thread)."""
        try:
            result = self._service.transcribe_array(
                segment,
                language=self._language,
                initial_prompt=initial_prompt,
            )
            text = result.get("text", "").strip()
            duration = result.get("duration", 0)

            # Filter out hallucination tokens (not real speech)
            is_hallucination = text.lower() in {h.lower() for h in HALLUCINATION_TOKENS}

            with self._transcribe_lock:
                # Always advance the pointer to avoid re-processing
                self._transcribed_up_to = up_to

                if text and not is_hallucination:
                    self._confirmed_texts.append(text)
                    self._last_segment_text = text

            if text:
                full_so_far = " ".join(self._confirmed_texts)
                self.partial_text_updated.emit(full_so_far)

            print(f"[StreamingTranscriber] Segment done ({duration:.2f}s): '{text[:60]}'")

        except Exception as e:
            print(f"[StreamingTranscriber] Segment transcription error: {e}")
            # Still advance pointer on error to avoid stuck retries
            with self._transcribe_lock:
                self._transcribed_up_to = up_to
        finally:
            self._is_transcribing = False

    def flush(self) -> str:
        """
        Finalize transcription after recording stops.

        Transcribes any remaining untranscribed audio, then returns the full text.
        This is the only part the user has to wait for.
        """
        self._active = False

        # Wait for any in-progress transcription to finish
        deadline = time.time() + 10  # 10s safety timeout
        while self._is_transcribing and time.time() < deadline:
            time.sleep(0.01)

        # Get remaining untranscribed audio
        full_audio = self._get_full_buffer()
        remaining_samples = self._buffer_samples - self._transcribed_up_to

        if remaining_samples > int(MIN_SEGMENT_LENGTH * SAMPLE_RATE):
            # Transcribe the final segment with overlap
            overlap_samples = int(OVERLAP_DURATION * SAMPLE_RATE)
            seg_start = max(0, self._transcribed_up_to - overlap_samples)
            final_segment = full_audio[seg_start:]

            initial_prompt = self._last_segment_text[-200:] if self._last_segment_text else None

            try:
                flush_start = time.time()
                result = self._service.transcribe_array(
                    final_segment,
                    language=self._language,
                    initial_prompt=initial_prompt,
                )
                text = result.get("text", "").strip()
                is_hallucination = text.lower() in {h.lower() for h in HALLUCINATION_TOKENS}
                if text and not is_hallucination:
                    self._confirmed_texts.append(text)
                print(f"[StreamingTranscriber] Flush segment ({time.time()-flush_start:.2f}s): '{text[:60]}'")
            except Exception as e:
                print(f"[StreamingTranscriber] Final segment error: {e}")

        elif self._buffer_samples > 0 and not self._confirmed_texts:
            # Very short recording (< MIN_SEGMENT_LENGTH) — transcribe everything
            try:
                result = self._service.transcribe_array(
                    full_audio,
                    language=self._language,
                )
                text = result.get("text", "").strip()
                is_hallucination = text.lower() in {h.lower() for h in HALLUCINATION_TOKENS}
                if text and not is_hallucination:
                    self._confirmed_texts.append(text)
            except Exception as e:
                print(f"[StreamingTranscriber] Short recording error: {e}")

        return " ".join(self._confirmed_texts).strip()

    def get_partial_text(self) -> str:
        """Get the current partial transcription text."""
        with self._transcribe_lock:
            return " ".join(self._confirmed_texts).strip()

    @property
    def has_results(self) -> bool:
        """Whether any segments have been transcribed."""
        return len(self._confirmed_texts) > 0

    @property
    def is_active(self) -> bool:
        return self._active
