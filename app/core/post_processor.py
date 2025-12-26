"""
LLM Post-Processor Service

Uses MLX for cleaning up transcriptions:
- Remove filler words (um, uh, like, you know)
- Format lists
- Light grammar cleanup

Lazy loading: Model loads on first use or can be preloaded.

Config files (in ~/Library/Application Support/WhisperTranscribeUI/):
- cleanup_prompt.txt: The prompt template (use {text} as placeholder)
- settings.json: Set "post_processing_model" to change model
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Callable

from app.utils.config_manager import ConfigManager

# Config directory
CONFIG_DIR = Path.home() / "Library" / "Application Support" / "WhisperTranscribeUI"
PROMPT_FILE = CONFIG_DIR / "cleanup_prompt.txt"


class PostProcessor:
    """
    Local LLM post-processor for cleaning transcriptions.

    Features:
    - Lazy loading (loads on first use)
    - Async preloading (start loading while recording)
    - Auto-unload after idle timeout
    - Toggle on/off via settings
    - External prompt file for easy editing
    """

    # Default model - Llama 3.2 3B is the mlx-lm default, reliable and fast
    DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

    # Default cleanup prompt (used if external file not found)
    DEFAULT_PROMPT = """You are a text editor. Clean up this transcribed speech by:
1. Remove filler words (um, uh, like, you know, kind of, sort of, I mean, basically, actually, literally)
2. Remove repeated words or phrases
3. Format any numbered items as bullet points using "-"
4. Fix grammar errors

Important: Output ONLY the cleaned text. No explanations, no markdown headers, no commentary.

Input: {text}

Output:"""

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

    def _get_model_name(self) -> str:
        """Get model name from settings or use default."""
        return self.config_manager.get("post_processing_model", self.DEFAULT_MODEL)

    def _get_prompt_template(self) -> str:
        """Load prompt from external file or use default."""
        if PROMPT_FILE.exists():
            try:
                prompt = PROMPT_FILE.read_text().strip()
                # Support multiple placeholder formats
                if "{text}" in prompt or "{{user_transcription_input}}" in prompt or "{user_transcription_input}" in prompt:
                    return prompt
                else:
                    print(f"[PostProcessor] Warning: {PROMPT_FILE} missing placeholder, using default")
                    print(f"[PostProcessor] Use {{text}} or {{{{user_transcription_input}}}} as placeholder")
            except Exception as e:
                print(f"[PostProcessor] Error reading prompt file: {e}")
        return self.DEFAULT_PROMPT

    def _format_prompt(self, template: str, text: str) -> str:
        """Format prompt template with the input text."""
        # Handle different placeholder formats
        if "{{user_transcription_input}}" in template:
            return template.replace("{{user_transcription_input}}", text)
        elif "{user_transcription_input}" in template:
            return template.replace("{user_transcription_input}", text)
        else:
            return template.format(text=text)

    def _strip_preamble(self, text: str) -> str:
        """Strip common LLM preambles/commentary from output."""
        import re

        # Common preamble patterns to remove
        preambles = [
            r"^I'd be happy to[^.]*\.\s*",
            r"^I can help[^.]*\.\s*",
            r"^Here's the cleaned[^:]*:\s*",
            r"^Here is the cleaned[^:]*:\s*",
            r"^The cleaned text[^:]*:\s*",
            r"^Sure[,!]?\s*",
            r"^Of course[,!]?\s*",
            r"^Certainly[,!]?\s*",
        ]

        result = text.strip()
        for pattern in preambles:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        # Also strip trailing commentary
        trailing = [
            r"\s*Let me know if[^.]*\.?\s*$",
            r"\s*I hope this helps[^.]*\.?\s*$",
            r"\s*Feel free to[^.]*\.?\s*$",
        ]
        for pattern in trailing:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        # Remove quotes if the entire output is quoted
        result = result.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]

        return result.strip()

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
            model_name = self._get_model_name()
            print(f"[PostProcessor] Loading model: {model_name}")
            start = time.time()

            try:
                from mlx_lm import load

                self.model, self.tokenizer = load(model_name)
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
            from mlx_lm.sample_utils import make_sampler

            # Load prompt from external file (re-read each time for hot-reload)
            prompt_template = self._get_prompt_template()
            prompt = self._format_prompt(prompt_template, text)

            print(f"[PostProcessor] Processing {len(text.split())} words...")
            start = time.time()

            # Create sampler with low temperature for consistent output
            sampler = make_sampler(temp=0.1)

            # Generate with conservative settings
            result = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=min(len(text.split()) * 2, 500),  # Reasonable limit
                sampler=sampler,
            )

            elapsed = time.time() - start
            print(f"[PostProcessor] Processed in {elapsed:.1f}s")

            # Extract just the cleaned text (remove any extra commentary)
            cleaned = result.strip()

            # Strip any preambles the model might have added
            cleaned = self._strip_preamble(cleaned)

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
