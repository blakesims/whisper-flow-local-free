"""
Streaming Transcriber - Transcribes audio segments while recording continues.

Instead of waiting for recording to finish, this component:
1. Receives audio chunks as they're recorded
2. Accumulates them into segments using VAD to find natural speech pauses
3. Transcribes each segment in a background thread
4. Merges results with overlap deduplication
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
_HALLUCINATION_LOWER = {h.lower() for h in HALLUCINATION_TOKENS}

# Minimum word overlap to strip (avoids false positives on common single words)
MIN_DEDUP_WORDS = 2


def _deduplicate_overlap(previous_text: str, new_text: str) -> str:
    """
    Remove duplicated words at the boundary between two overlapping segments.

    When segments overlap by OVERLAP_DURATION, whisper re-transcribes the overlap
    region. This function finds the longest suffix of previous_text that matches
    a prefix of new_text and strips it to avoid doubled words.

    Requires at least MIN_DEDUP_WORDS matching to avoid false positives from
    common single words like "the", "a", "is".
    """
    if not previous_text or not new_text:
        return new_text

    prev_words = previous_text.split()
    new_words = new_text.split()

    if not prev_words or not new_words:
        return new_text

    # Try matching progressively longer suffixes of prev against prefixes of new
    # Limit search to a reasonable window (overlap is ~0.5s ≈ 2-5 words)
    max_overlap_words = min(len(prev_words), len(new_words), 10)

    best_match = 0
    for length in range(MIN_DEDUP_WORDS, max_overlap_words + 1):
        suffix = prev_words[-length:]
        prefix = new_words[:length]
        if [w.lower() for w in suffix] == [w.lower() for w in prefix]:
            best_match = length

    if best_match >= MIN_DEDUP_WORDS:
        return " ".join(new_words[best_match:])
    return new_text


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
        # _buffer_samples is an absolute counter that only grows (never decremented).
        # This keeps sample indices consistent across segments without needing to
        # adjust _transcribed_up_to when trimming. We accept O(N) memory for the
        # recording duration — ~10MB per 5 minutes at 16kHz int16 mono.
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0
        self._buffer_lock = threading.Lock()

        # Tracking what's been transcribed (protected by _transcribe_lock)
        self._transcribed_up_to = 0  # absolute sample index
        self._confirmed_texts: list[str] = []
        self._last_segment_text = ""

        # Threading
        self._transcribe_lock = threading.Lock()
        self._is_transcribing = threading.Event()
        self._active = False

        # VAD state (lazy-initialized on first chunk)
        self._vad = None
        self._vad_initialized = False
        self._vad_buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._silence_start_sample = 0

    def start_session(self):
        """Reset state for a new recording session."""
        with self._buffer_lock:
            self._buffer = []
            self._buffer_samples = 0

        with self._transcribe_lock:
            self._transcribed_up_to = 0
            self._confirmed_texts = []
            self._last_segment_text = ""

        self._is_transcribing.clear()
        self._active = True

        # Reset VAD state — re-create model to clear internal RNN hidden state
        self._vad_buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._silence_start_sample = 0
        if self._vad_initialized and _VAD_AVAILABLE:
            try:
                self._vad = SileroVAD(sample_rate=SAMPLE_RATE)
            except Exception:
                pass  # keep existing instance if re-creation fails

    def cancel(self):
        """Cancel the streaming session, discarding all results."""
        self._active = False

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

    def _process_vad(self, chunk: np.ndarray, current_buffer_samples: int) -> bool:
        """
        Process chunk through VAD, return True if a speech pause boundary is detected.
        The chunk is int16; VAD needs float32 in [-1, 1].

        current_buffer_samples is passed in to avoid reading _buffer_samples without lock.
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

            # Pass numpy array directly (silero-vad-lite accepts array-like)
            score = self._vad.process(window)
            is_speech = score >= VAD_SPEECH_THRESHOLD

            if is_speech:
                if not self._is_speaking:
                    self._is_speaking = True
                self._silence_start_sample = current_buffer_samples
            else:
                if self._is_speaking:
                    self._is_speaking = False
                    self._silence_start_sample = current_buffer_samples

                silence_samples = current_buffer_samples - self._silence_start_sample
                silence_duration = silence_samples / SAMPLE_RATE
                if silence_duration >= VAD_SILENCE_DURATION:
                    pause_detected = True

        return pause_detected

    def feed_chunk(self, chunk: np.ndarray):
        """
        Feed an audio chunk from the recorder.
        Called from the Qt main thread via signal — must not raise.
        """
        if not self._active:
            return

        try:
            self._feed_chunk_inner(chunk)
        except Exception as e:
            print(f"[StreamingTranscriber] Error in feed_chunk: {e}")

    def _feed_chunk_inner(self, chunk: np.ndarray):
        """Inner feed logic, wrapped by feed_chunk's exception guard."""
        # Lazy-init VAD on first chunk
        if not self._vad_initialized:
            self._init_vad()

        with self._buffer_lock:
            self._buffer.append(chunk.copy())
            self._buffer_samples += len(chunk)
            current_buffer_samples = self._buffer_samples

        # Don't trigger if already transcribing
        if self._is_transcribing.is_set():
            return

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to

        new_samples = current_buffer_samples - transcribed_up_to
        new_duration = new_samples / SAMPLE_RATE

        if self._vad is not None:
            # VAD mode: trigger on speech pause (with min/max duration guards)
            pause_detected = self._process_vad(chunk, current_buffer_samples)

            if pause_detected and new_duration >= MIN_SEGMENT_LENGTH:
                self._transcribe_next_segment()
            elif new_duration >= MAX_SEGMENT_DURATION:
                self._transcribe_next_segment()
        else:
            # Fixed-interval fallback (no VAD)
            if new_duration >= SEGMENT_DURATION:
                self._transcribe_next_segment()

    def _snapshot_buffer(self) -> tuple[np.ndarray, int]:
        """Thread-safe snapshot of the audio buffer."""
        with self._buffer_lock:
            if not self._buffer:
                return np.array([], dtype=np.int16), 0
            audio = np.concatenate(self._buffer)
            return audio, self._buffer_samples

    def _transcribe_next_segment(self):
        """Trigger transcription of the next segment in a background thread."""
        self._is_transcribing.set()

        # Thread-safe snapshot of buffer and state
        full_audio, buffer_len = self._snapshot_buffer()
        overlap_samples = int(OVERLAP_DURATION * SAMPLE_RATE)

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to

        # Start from (transcribed_up_to - overlap) to capture boundary context
        seg_start = max(0, transcribed_up_to - overlap_samples)
        segment = full_audio[seg_start:buffer_len].copy()

        new_transcribed_up_to = buffer_len

        with self._transcribe_lock:
            initial_prompt = self._last_segment_text[-200:] if self._last_segment_text else None

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

            is_hallucination = text.lower() in _HALLUCINATION_LOWER

            with self._transcribe_lock:
                self._transcribed_up_to = up_to

                if text and not is_hallucination:
                    if self._confirmed_texts:
                        text = _deduplicate_overlap(self._confirmed_texts[-1], text)
                    if text:
                        self._confirmed_texts.append(text)
                        self._last_segment_text = text

            with self._transcribe_lock:
                full_so_far = " ".join(self._confirmed_texts)
            if full_so_far:
                self.partial_text_updated.emit(full_so_far)

            print(f"[StreamingTranscriber] Segment done ({duration:.2f}s): '{text[:60]}'")

        except Exception as e:
            print(f"[StreamingTranscriber] Segment transcription error: {e}")
            with self._transcribe_lock:
                self._transcribed_up_to = up_to
        finally:
            self._is_transcribing.clear()

    def flush(self) -> str:
        """
        Finalize transcription after recording stops.

        Transcribes any remaining untranscribed audio, then returns the full text.
        This is the only part the user has to wait for.
        """
        self._active = False

        # Wait for any in-progress transcription to finish
        if self._is_transcribing.is_set():
            deadline = time.time() + 15
            while self._is_transcribing.is_set() and time.time() < deadline:
                time.sleep(0.01)

            if self._is_transcribing.is_set():
                print("[StreamingTranscriber] WARNING: background transcription timed out")
                with self._transcribe_lock:
                    return " ".join(self._confirmed_texts).strip()

        # Get remaining untranscribed audio (thread-safe snapshot)
        full_audio, total_samples = self._snapshot_buffer()

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to
            had_prior_results = len(self._confirmed_texts) > 0

        remaining_samples = total_samples - transcribed_up_to

        if remaining_samples > int(MIN_SEGMENT_LENGTH * SAMPLE_RATE):
            overlap_samples = int(OVERLAP_DURATION * SAMPLE_RATE)
            seg_start = max(0, transcribed_up_to - overlap_samples)
            final_segment = full_audio[seg_start:]

            with self._transcribe_lock:
                initial_prompt = self._last_segment_text[-200:] if self._last_segment_text else None

            try:
                flush_start = time.time()
                result = self._service.transcribe_array(
                    final_segment,
                    language=self._language,
                    initial_prompt=initial_prompt,
                )
                text = result.get("text", "").strip()
                is_hallucination = text.lower() in _HALLUCINATION_LOWER

                if text and not is_hallucination:
                    with self._transcribe_lock:
                        if self._confirmed_texts:
                            text = _deduplicate_overlap(self._confirmed_texts[-1], text)
                        if text:
                            self._confirmed_texts.append(text)

                print(f"[StreamingTranscriber] Flush segment ({time.time()-flush_start:.2f}s): '{text[:60]}'")
            except Exception as e:
                print(f"[StreamingTranscriber] Final segment error: {e}")

        elif total_samples > 0 and not had_prior_results:
            # Very short recording — transcribe everything
            try:
                result = self._service.transcribe_array(
                    full_audio,
                    language=self._language,
                )
                text = result.get("text", "").strip()
                is_hallucination = text.lower() in _HALLUCINATION_LOWER
                if text and not is_hallucination:
                    with self._transcribe_lock:
                        self._confirmed_texts.append(text)
            except Exception as e:
                print(f"[StreamingTranscriber] Short recording error: {e}")

        with self._transcribe_lock:
            return " ".join(self._confirmed_texts).strip()

    def get_partial_text(self) -> str:
        """Get the current partial transcription text."""
        with self._transcribe_lock:
            return " ".join(self._confirmed_texts).strip()

    @property
    def has_results(self) -> bool:
        """Whether any segments have been transcribed."""
        with self._transcribe_lock:
            return len(self._confirmed_texts) > 0

    @property
    def is_active(self) -> bool:
        return self._active
