"""
Whisper.cpp Transcription Service

Uses pywhispercpp for 5-6x faster transcription on Apple Silicon.
Drop-in replacement for TranscriptionService with compatible API.
"""

import os
import time
from pathlib import Path
from typing import Optional, Callable

from pywhispercpp.model import Model

from app.utils.config_manager import ConfigManager


class WhisperCppService:
    """
    Transcription service using whisper.cpp via pywhispercpp.

    Benefits over faster-whisper:
    - 5-6x faster on Apple Silicon
    - Automatic Metal GPU acceleration
    - Lower memory footprint
    """

    # Model name mapping (whisper.cpp uses different names)
    MODEL_NAMES = {
        "tiny": "tiny",
        "tiny.en": "tiny.en",
        "base": "base",
        "base.en": "base.en",
        "small": "small",
        "small.en": "small.en",
        "medium": "medium",
        "medium.en": "medium.en",
        "large": "large-v2",
        "large-v2": "large-v2",
        "large-v3": "large-v3",
    }

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.model: Optional[Model] = None
        self.model_name: str = "base"
        self._model_loaded = False

    def set_target_model_config(self, model_name: str, device: str = "cpu", compute_type: str = "int8"):
        """Set model configuration. Device/compute_type ignored (whisper.cpp auto-optimizes)."""
        # Map to whisper.cpp model name
        self.model_name = self.MODEL_NAMES.get(model_name, model_name)
        print(f"[WhisperCpp] Target model: {self.model_name}")

    def load_model(self):
        """Load the whisper.cpp model."""
        if self._model_loaded and self.model is not None:
            return

        print(f"[WhisperCpp] Loading model: {self.model_name}")
        start = time.time()

        try:
            # pywhispercpp auto-downloads models to ~/.cache/whisper/
            self.model = Model(self.model_name)
            self._model_loaded = True
            elapsed = time.time() - start
            print(f"[WhisperCpp] Model loaded in {elapsed:.2f}s")
        except Exception as e:
            print(f"[WhisperCpp] Error loading model: {e}")
            raise

    def _load_model(self):
        """Alias for load_model() for API compatibility."""
        self.load_model()

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        beam_size: int = 5,
        progress_callback: Optional[Callable] = None,
        **kwargs
    ) -> dict:
        """
        Transcribe audio file using whisper.cpp.

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., "en") or None for auto-detect
            beam_size: Beam size (passed to whisper.cpp)
            progress_callback: Optional callback(percent, text, lang_info)

        Returns:
            dict with "text" key containing transcription
        """
        if not self._model_loaded or self.model is None:
            self.load_model()

        print(f"[WhisperCpp] Transcribing: {audio_path}")
        start = time.time()

        # Notify progress start
        if progress_callback:
            progress_callback(0, "", None)

        try:
            # Transcribe with whisper.cpp
            # Note: pywhispercpp returns a list of Segment objects
            segments = self.model.transcribe(
                audio_path,
                language=language if language else None,
                n_threads=self._get_thread_count(),
            )

            # Combine segment texts
            text_parts = []
            for i, segment in enumerate(segments):
                text_parts.append(segment.text)
                # Report progress
                if progress_callback and len(segments) > 0:
                    percent = int((i + 1) / len(segments) * 100)
                    progress_callback(percent, segment.text, None)

            full_text = " ".join(text_parts).strip()
            elapsed = time.time() - start

            print(f"[WhisperCpp] Transcription complete in {elapsed:.2f}s")
            print(f"[WhisperCpp] Text: '{full_text[:80]}...'")

            # Final progress callback
            if progress_callback:
                progress_callback(100, full_text, None)

            return {
                "text": full_text,
                "segments": segments,
                "language": language or "auto",
                "duration": elapsed,
            }

        except Exception as e:
            print(f"[WhisperCpp] Transcription error: {e}")
            raise

    def _get_thread_count(self) -> int:
        """Get optimal thread count for Apple Silicon."""
        import os
        cpu_count = os.cpu_count() or 4
        # Use all cores minus 1 for Apple Silicon
        return max(1, cpu_count - 1)

    def unload_model(self):
        """Unload model to free memory."""
        self.model = None
        self._model_loaded = False
        print("[WhisperCpp] Model unloaded")


# Factory function to get the best available service
def get_transcription_service(config_manager: Optional[ConfigManager] = None):
    """
    Get the best available transcription service.

    Tries whisper.cpp first, falls back to faster-whisper.
    """
    try:
        service = WhisperCppService(config_manager)
        print("[Transcription] Using whisper.cpp (faster)")
        return service
    except ImportError:
        print("[Transcription] whisper.cpp not available, using faster-whisper")
        from app.core.transcription_service import TranscriptionService
        return TranscriptionService(config_manager)
