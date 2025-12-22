"""
LLM Post-Processor Service

Uses MLX with Phi-3.2 mini for cleaning up transcriptions:
- Remove filler words (um, uh, like, you know)
- Format lists
- Light grammar cleanup

Lazy loading: Model loads on first use or can be preloaded.
"""

import os
import time
import threading
from typing import Optional, Callable

from app.utils.config_manager import ConfigManager


class PostProcessor:
    """
    Local LLM post-processor for cleaning transcriptions.

    Features:
    - Lazy loading (loads on first use)
    - Async preloading (start loading while recording)
    - Auto-unload after idle timeout
    - Toggle on/off via settings
    """

    # Default model - good balance of speed and quality
    DEFAULT_MODEL = "mlx-community/Phi-3.5-mini-instruct-4bit"

    # Cleanup prompt template
    CLEANUP_PROMPT = """Clean up this transcribed speech. Rules:
- Remove filler words: um, uh, like, you know, kind of, sort of, I mean, basically, actually, literally, right, so, well
- Remove repeated words/phrases
- Format numbered items as a bullet list (use - for bullets)
- Fix obvious grammar issues
- Keep the original meaning and tone
- Do NOT add any commentary or explanations
- Return ONLY the cleaned text

Text to clean:
{text}

Cleaned text:"""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.model = None
        self.tokenizer = None
        self._loading = False
        self._loaded = False
        self._load_lock = threading.Lock()
        self._last_used = 0
        self._idle_timeout = 120  # Unload after 2 minutes idle

        # Check if enabled in settings
        self._enabled = self.config_manager.get("post_processing_enabled", False)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        self.config_manager.set("post_processing_enabled", value)
        print(f"[PostProcessor] {'Enabled' if value else 'Disabled'}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self.model is not None

    def preload_async(self):
        """Start loading the model in background (non-blocking)."""
        if self._loaded or self._loading or not self._enabled:
            return

        def load_in_background():
            try:
                self._load_model()
            except Exception as e:
                print(f"[PostProcessor] Background load failed: {e}")

        thread = threading.Thread(target=load_in_background, daemon=True)
        thread.start()
        print("[PostProcessor] Preloading model in background...")

    def _load_model(self):
        """Load the MLX model (blocking)."""
        with self._load_lock:
            if self._loaded:
                return

            if self._loading:
                # Wait for other thread to finish loading
                while self._loading:
                    time.sleep(0.1)
                return

            self._loading = True
            print(f"[PostProcessor] Loading model: {self.DEFAULT_MODEL}")
            start = time.time()

            try:
                from mlx_lm import load

                self.model, self.tokenizer = load(self.DEFAULT_MODEL)
                self._loaded = True
                self._last_used = time.time()
                elapsed = time.time() - start
                print(f"[PostProcessor] Model loaded in {elapsed:.1f}s")

            except Exception as e:
                print(f"[PostProcessor] Error loading model: {e}")
                self.model = None
                self.tokenizer = None
                raise
            finally:
                self._loading = False

    def unload(self):
        """Unload the model to free memory."""
        with self._load_lock:
            if self.model is not None:
                del self.model
                del self.tokenizer
                self.model = None
                self.tokenizer = None
                self._loaded = False
                print("[PostProcessor] Model unloaded")

    def check_idle_unload(self):
        """Check if model should be unloaded due to inactivity."""
        if self._loaded and (time.time() - self._last_used) > self._idle_timeout:
            print("[PostProcessor] Idle timeout - unloading model")
            self.unload()

    def process(self, text: str, timeout: float = 30.0) -> str:
        """
        Clean up transcribed text using the LLM.

        Args:
            text: Raw transcription text
            timeout: Maximum time to wait for processing

        Returns:
            Cleaned text, or original if processing fails
        """
        if not self._enabled:
            return text

        if not text or len(text.strip()) < 10:
            return text  # Too short to process

        # Load model if needed
        if not self._loaded:
            try:
                self._load_model()
            except Exception as e:
                print(f"[PostProcessor] Could not load model: {e}")
                return text

        self._last_used = time.time()

        try:
            from mlx_lm import generate

            prompt = self.CLEANUP_PROMPT.format(text=text)

            print(f"[PostProcessor] Processing {len(text.split())} words...")
            start = time.time()

            # Generate with conservative settings
            result = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=min(len(text.split()) * 2, 500),  # Reasonable limit
                temp=0.1,  # Low temperature for consistent output
            )

            elapsed = time.time() - start
            print(f"[PostProcessor] Processed in {elapsed:.1f}s")

            # Extract just the cleaned text (remove any extra commentary)
            cleaned = result.strip()

            # Basic validation - if result is empty or way too different, return original
            if not cleaned or len(cleaned) < len(text) * 0.3:
                print("[PostProcessor] Result too short, using original")
                return text

            return cleaned

        except Exception as e:
            print(f"[PostProcessor] Processing error: {e}")
            return text  # Return original on error


# Singleton instance
_processor: Optional[PostProcessor] = None


def get_post_processor(config_manager: Optional[ConfigManager] = None) -> PostProcessor:
    """Get the singleton post-processor instance."""
    global _processor
    if _processor is None:
        _processor = PostProcessor(config_manager)
    return _processor
