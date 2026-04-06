"""
Streaming Transcriber - Transcribes audio segments while recording continues.

Architecture:
1. Receives audio chunks as they're recorded
2. Accumulates into ~7s segments, using VAD to find natural speech pauses
3. Transcribes each segment in a background thread (first pass)
4. After every pair [0,1], [2,3] etc, re-transcribes the combined audio (refinement pass)
5. On recording stop, only the final untranscribed audio needs processing

The refinement pass fixes boundary artifacts where segments were cut mid-phrase.
Delta tracking shows how many words changed between first-pass and refined text.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


# Tuning constants
SEGMENT_DURATION = 7.0  # seconds for fixed-interval fallback
OVERLAP_DURATION = 0.5  # seconds of overlap between segments
MIN_SEGMENT_LENGTH = 5.0  # minimum seconds of audio worth transcribing
MAX_SEGMENT_DURATION = 10.0  # maximum seconds before forcing transcription (VAD mode)
SAMPLE_RATE = 16000

# VAD constants
VAD_WINDOW_SAMPLES = 512
VAD_SPEECH_THRESHOLD = 0.5
VAD_SILENCE_DURATION = 0.6  # sentence-level pauses, not breath pauses

try:
    from silero_vad_lite import SileroVAD
    _VAD_AVAILABLE = True
except ImportError:
    _VAD_AVAILABLE = False

HALLUCINATION_TOKENS = {
    "[BLANK_AUDIO]", "(blank audio)", "[SILENCE]", "(silence)",
    "(eerie music)", "(humming)", "(music)", "(birds chirping)",
    "(wind blowing)", "(footsteps)", "(door closing)",
}
_HALLUCINATION_LOWER = {h.lower() for h in HALLUCINATION_TOKENS}


def _count_word_deltas(old_text: str, new_text: str) -> int:
    """Count word-level differences between two texts."""
    old_words = old_text.lower().split()
    new_words = new_text.lower().split()
    # Simple: count words that differ using longest common subsequence length
    # For speed, just use set symmetric difference as approximation
    if not old_words and not new_words:
        return 0
    if not old_words or not new_words:
        return max(len(old_words), len(new_words))
    # Word-by-word diff (aligned by position)
    max_len = max(len(old_words), len(new_words))
    deltas = 0
    for i in range(max_len):
        old_w = old_words[i] if i < len(old_words) else ""
        new_w = new_words[i] if i < len(new_words) else ""
        if old_w != new_w:
            deltas += 1
    return deltas


@dataclass
class SegmentInfo:
    """Tracks audio range and text for each transcribed segment."""
    audio_start: int  # absolute sample index
    audio_end: int    # absolute sample index
    text: str = ""
    refined: bool = False  # whether this segment has been refined as part of a pair


class StreamingTranscriber(QObject):
    """
    Transcribes audio segments progressively while recording continues.
    After every pair of segments, re-transcribes the combined audio for better quality.
    """

    partial_text_updated = Signal(str)

    def __init__(self, transcription_service, language: str = "en"):
        super().__init__()
        self._service = transcription_service
        self._language = language

        # Audio buffer
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0
        self._buffer_lock = threading.Lock()

        # Segment tracking (protected by _transcribe_lock)
        self._segments: list[SegmentInfo] = []
        self._transcribed_up_to = 0
        self._last_segment_text = ""

        # Refinement stats
        self._total_deltas = 0
        self._refinements_done = 0

        # Threading
        self._transcribe_lock = threading.Lock()
        self._model_lock = threading.Lock()  # whisper.cpp is NOT thread-safe
        self._is_transcribing = threading.Event()
        self._is_refining = threading.Event()
        self._active = False

        # VAD state
        self._vad = None
        self._vad_initialized = False
        self._vad_buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._silence_start_sample = 0

    @property
    def _confirmed_texts(self) -> list[str]:
        """Compatibility: return segment texts as a list."""
        return [s.text for s in self._segments if s.text]

    def start_session(self):
        """Reset state for a new recording session."""
        with self._buffer_lock:
            self._buffer = []
            self._buffer_samples = 0

        with self._transcribe_lock:
            self._segments = []
            self._transcribed_up_to = 0
            self._last_segment_text = ""
            self._total_deltas = 0
            self._refinements_done = 0

        self._is_transcribing.clear()
        self._is_refining.clear()
        self._active = True

        self._vad_buffer = np.array([], dtype=np.float32)
        self._is_speaking = False
        self._silence_start_sample = 0
        if self._vad_initialized and _VAD_AVAILABLE:
            try:
                self._vad = SileroVAD(sample_rate=SAMPLE_RATE)
            except Exception:
                pass

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
        """Process chunk through VAD, return True if speech pause detected."""
        if self._vad is None:
            return False

        float_chunk = chunk.astype(np.float32) / 32768.0
        self._vad_buffer = np.concatenate([self._vad_buffer, float_chunk])

        pause_detected = False
        while len(self._vad_buffer) >= VAD_WINDOW_SAMPLES:
            window = self._vad_buffer[:VAD_WINDOW_SAMPLES].copy()
            self._vad_buffer = self._vad_buffer[VAD_WINDOW_SAMPLES:]

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
                if silence_samples / SAMPLE_RATE >= VAD_SILENCE_DURATION:
                    pause_detected = True

        return pause_detected

    def feed_chunk(self, chunk: np.ndarray):
        """Feed an audio chunk from the recorder. Must not raise."""
        if not self._active:
            return
        try:
            if chunk.ndim > 1:
                chunk = chunk.ravel()
            self._feed_chunk_inner(chunk)
        except Exception as e:
            print(f"[StreamingTranscriber] Error in feed_chunk: {e}")

    def _feed_chunk_inner(self, chunk: np.ndarray):
        if not self._vad_initialized:
            self._init_vad()

        with self._buffer_lock:
            self._buffer.append(chunk.copy())
            self._buffer_samples += len(chunk)
            current_buffer_samples = self._buffer_samples

        if self._is_transcribing.is_set():
            return

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to

        new_samples = current_buffer_samples - transcribed_up_to
        new_duration = new_samples / SAMPLE_RATE

        if self._vad is not None:
            pause_detected = self._process_vad(chunk, current_buffer_samples)
            if pause_detected and new_duration >= MIN_SEGMENT_LENGTH:
                self._transcribe_next_segment()
            elif new_duration >= MAX_SEGMENT_DURATION:
                self._transcribe_next_segment()
        else:
            if new_duration >= SEGMENT_DURATION:
                self._transcribe_next_segment()

    def _snapshot_buffer(self) -> tuple[np.ndarray, int]:
        """Thread-safe snapshot of the audio buffer."""
        with self._buffer_lock:
            if not self._buffer:
                return np.array([], dtype=np.int16), 0
            return np.concatenate(self._buffer), self._buffer_samples

    def _transcribe_next_segment(self):
        """Trigger transcription of the next segment in a background thread."""
        self._is_transcribing.set()

        full_audio, buffer_len = self._snapshot_buffer()
        overlap_samples = int(OVERLAP_DURATION * SAMPLE_RATE)

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to
            initial_prompt = self._last_segment_text[-200:] if self._last_segment_text else None

        seg_start = max(0, transcribed_up_to - overlap_samples)
        segment = full_audio[seg_start:buffer_len].copy()
        new_transcribed_up_to = buffer_len

        # Record the audio range for this segment (without overlap)
        seg_info = SegmentInfo(audio_start=transcribed_up_to, audio_end=buffer_len)

        thread = threading.Thread(
            target=self._do_transcribe,
            args=(segment, new_transcribed_up_to, initial_prompt, seg_info),
            daemon=True,
        )
        thread.start()

    def _do_transcribe(self, segment: np.ndarray, up_to: int,
                       initial_prompt: Optional[str], seg_info: SegmentInfo):
        """Run first-pass transcription, then trigger pair refinement if applicable."""
        try:
            with self._model_lock:
                result = self._service.transcribe_array(
                    segment, language=self._language, initial_prompt=initial_prompt,
                )
            text = result.get("text", "").strip()
            duration = result.get("duration", 0)

            is_hallucination = text.lower() in _HALLUCINATION_LOWER

            seg_index = -1
            with self._transcribe_lock:
                self._transcribed_up_to = up_to

                if text and not is_hallucination:
                    seg_info.text = text
                    self._segments.append(seg_info)
                    self._last_segment_text = text
                    seg_index = len(self._segments) - 1

            # Emit partial text
            with self._transcribe_lock:
                full_so_far = " ".join(s.text for s in self._segments if s.text)
            if full_so_far:
                self.partial_text_updated.emit(full_so_far)

            print(f"[StreamingTranscriber] Segment {seg_index} done ({duration:.2f}s): '{text[:60]}'")

            # Trigger pair refinement after every even-indexed segment (i.e., pairs [0,1], [2,3]...)
            if seg_index >= 1 and seg_index % 2 == 1 and not self._is_refining.is_set():
                self._refine_pair(seg_index - 1, seg_index)

        except Exception as e:
            print(f"[StreamingTranscriber] Segment transcription error: {e}")
            with self._transcribe_lock:
                self._transcribed_up_to = up_to
        finally:
            self._is_transcribing.clear()

    def _refine_pair(self, idx_a: int, idx_b: int):
        """Re-transcribe segments [idx_a, idx_b] combined for better quality."""
        self._is_refining.set()

        thread = threading.Thread(
            target=self._do_refine_pair,
            args=(idx_a, idx_b),
            daemon=True,
        )
        thread.start()

    def _do_refine_pair(self, idx_a: int, idx_b: int):
        """Run pair refinement in background thread."""
        try:
            with self._transcribe_lock:
                if idx_a >= len(self._segments) or idx_b >= len(self._segments):
                    return
                seg_a = self._segments[idx_a]
                seg_b = self._segments[idx_b]
                old_text = seg_a.text + " " + seg_b.text
                # Get initial_prompt from the segment before the pair
                if idx_a > 0:
                    initial_prompt = self._segments[idx_a - 1].text[-200:]
                else:
                    initial_prompt = None

            # Get the combined audio range
            full_audio, _ = self._snapshot_buffer()
            combined = full_audio[seg_a.audio_start:seg_b.audio_end].copy()

            with self._model_lock:
                result = self._service.transcribe_array(
                    combined, language=self._language, initial_prompt=initial_prompt,
                )
            new_text = result.get("text", "").strip()
            duration = result.get("duration", 0)

            if not new_text or new_text.lower() in _HALLUCINATION_LOWER:
                return

            # Count deltas
            deltas = _count_word_deltas(old_text, new_text)

            # Quality gate: reject if text length changed too much or too many words differ
            old_words = len(old_text.split())
            new_words = len(new_text.split())
            ratio = new_words / max(old_words, 1)
            delta_rate = deltas / max(old_words, 1)
            # Reject if: too short/long, or >50% of words changed (likely different interpretation)
            accepted = 0.80 <= ratio <= 1.25 and delta_rate <= 0.50

            with self._transcribe_lock:
                self._total_deltas += deltas
                self._refinements_done += 1

                if accepted:
                    self._segments[idx_a].text = new_text
                    self._segments[idx_a].audio_end = seg_b.audio_end
                    self._segments[idx_a].refined = True
                    self._segments[idx_b].text = ""
                    self._segments[idx_b].refined = True

            if accepted:
                with self._transcribe_lock:
                    full_text = " ".join(s.text for s in self._segments if s.text)
                if full_text:
                    self.partial_text_updated.emit(full_text)

            status = "accepted" if accepted else f"rejected (ratio={ratio:.2f})"
            print(f"[StreamingTranscriber] Refined [{idx_a},{idx_b}] ({duration:.2f}s, {deltas} deltas, {status}): '{new_text[:60]}'")

        except Exception as e:
            print(f"[StreamingTranscriber] Refinement error: {e}")
        finally:
            self._is_refining.clear()

    def flush(self) -> str:
        """Finalize transcription. Transcribes remaining audio, waits for refinements."""
        self._active = False

        # Wait for in-progress transcription AND refinement
        # (whisper.cpp model is NOT thread-safe — only one call at a time)
        for event, name in [(self._is_transcribing, "transcription"), (self._is_refining, "refinement")]:
            if event.is_set():
                deadline = time.time() + 15
                while event.is_set() and time.time() < deadline:
                    time.sleep(0.01)
                if event.is_set():
                    print(f"[StreamingTranscriber] WARNING: {name} timed out")

        # Transcribe remaining audio
        full_audio, total_samples = self._snapshot_buffer()

        with self._transcribe_lock:
            transcribed_up_to = self._transcribed_up_to
            had_prior = len(self._segments) > 0

        remaining_samples = total_samples - transcribed_up_to
        remaining_duration = remaining_samples / SAMPLE_RATE

        if remaining_duration > 0.3 and had_prior:
            # Re-transcribe from last segment's start through the tail.
            # This gives whisper full context for the ending — no short orphan segments
            # that lack context and produce bad quality.
            with self._transcribe_lock:
                last_seg = self._segments[-1]
                if len(self._segments) >= 2:
                    initial_prompt = self._segments[-2].text[-200:]
                else:
                    initial_prompt = None
                old_last_text = last_seg.text
                flush_start_sample = last_seg.audio_start

            final_segment = full_audio[flush_start_sample:]

            try:
                flush_start = time.time()
                with self._model_lock:
                    result = self._service.transcribe_array(
                        final_segment, language=self._language, initial_prompt=initial_prompt,
                    )
                text = result.get("text", "").strip()
                is_hallucination = text.lower() in _HALLUCINATION_LOWER
                elapsed = time.time() - flush_start

                if text and not is_hallucination:
                    deltas = _count_word_deltas(old_last_text, text)
                    with self._transcribe_lock:
                        last_seg.text = text
                        last_seg.audio_end = total_samples
                        self._total_deltas += deltas
                    print(f"[StreamingTranscriber] Flush: re-transcribed last seg + {remaining_duration:.1f}s tail ({elapsed:.2f}s, {deltas} deltas): '{text[:60]}'")
                else:
                    print(f"[StreamingTranscriber] Flush: tail produced no text ({elapsed:.2f}s)")
            except Exception as e:
                print(f"[StreamingTranscriber] Flush error: {e}")

        elif total_samples > 0 and not had_prior:
            # No prior segments — short recording, transcribe everything
            try:
                with self._model_lock:
                    result = self._service.transcribe_array(full_audio, language=self._language)
                text = result.get("text", "").strip()
                if text and text.lower() not in _HALLUCINATION_LOWER:
                    with self._transcribe_lock:
                        seg = SegmentInfo(audio_start=0, audio_end=total_samples, text=text)
                        self._segments.append(seg)
            except Exception as e:
                print(f"[StreamingTranscriber] Short recording error: {e}")

        # Wait for any in-flight refinement to finish
        if self._is_refining.is_set():
            deadline = time.time() + 10
            while self._is_refining.is_set() and time.time() < deadline:
                time.sleep(0.01)

        with self._transcribe_lock:
            result_text = " ".join(s.text for s in self._segments if s.text).strip()
            print(f"[StreamingTranscriber] Refinement stats: {self._refinements_done} pairs, {self._total_deltas} total word deltas")
            return result_text

    def get_partial_text(self) -> str:
        with self._transcribe_lock:
            return " ".join(s.text for s in self._segments if s.text).strip()

    @property
    def has_results(self) -> bool:
        with self._transcribe_lock:
            return any(s.text for s in self._segments)

    @property
    def is_active(self) -> bool:
        return self._active
