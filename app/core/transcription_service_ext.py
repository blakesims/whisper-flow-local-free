"""
Extended transcription service that returns timestamped segments.
"""

from typing import List, Dict, Optional, Callable
import os
from app.core.transcription_service import TranscriptionService
from app.core.meeting_transcript import TranscriptSegment


class TranscriptionServiceExt(TranscriptionService):
    """Extended transcription service with timestamp support."""
    
    def transcribe_with_timestamps(
        self, 
        audio_path: str, 
        speaker_name: str = "Speaker",
        language: str = None, 
        task: str = "transcribe", 
        beam_size: int = 1,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None
    ) -> Optional[Dict]:
        """
        Transcribe audio and return timestamped segments.
        
        Returns:
            Dictionary with:
            - 'segments': List of TranscriptSegment objects
            - 'text': Full concatenated text
            - 'detected_language': Detected or specified language
            - 'language_probability': Confidence of language detection
        """
        if not self.model:
            print("Transcription model is not loaded or is invalid. Cannot transcribe.")
            return None
            
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return None

        try:
            msg = f"Transcribing with timestamps: {audio_path} (speaker: {speaker_name})..."
            print(msg)
            if log_callback:
                log_callback(msg)
            
            # Get settings from config
            from app.utils.config_manager import ConfigManager
            config = ConfigManager()
            
            # Get advanced transcription settings
            enable_filter = config.get("enable_hallucination_filter", True)
            no_speech_threshold = config.get("no_speech_threshold", 0.3)
            compression_ratio = config.get("compression_ratio_threshold", 2.4)
            
            # Transcribe with optimized settings and anti-hallucination parameters
            segments_generator, info = self.model.transcribe(
                audio_path,
                language=language, 
                task=task,
                beam_size=beam_size,
                best_of=1,
                patience=1.0,
                length_penalty=1.0,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.5,
                    min_speech_duration_ms=250,
                    max_speech_duration_s=float('inf'),
                    min_silence_duration_ms=2000,
                    speech_pad_ms=400
                ),
                word_timestamps=True,  # Enable for hallucination detection
                condition_on_previous_text=False,  # Prevent hallucinations from previous context
                no_speech_threshold=no_speech_threshold,  # Configurable threshold
                compression_ratio_threshold=compression_ratio  # Configurable compression ratio
            )

            detected_lang_info = None
            if language is None: 
                msg = f"Detected language: {info.language} (probability: {info.language_probability:.2f})"
                print(msg)
                if log_callback:
                    log_callback(msg)
                detected_lang_info = {
                    "language": info.language,
                    "probability": info.language_probability
                }
            
            # Collect segments with timestamps
            transcript_segments = []
            text_parts = []
            total_duration_ms = info.duration * 1000
            
            for segment in segments_generator:
                # Filter out potential hallucinations if enabled
                segment_text = segment.text.strip()
                if enable_filter and self._is_hallucination(segment_text, config):
                    msg = f"Filtered hallucination at {segment.start:.1f}s: {segment_text[:50]}..."
                    print(msg)
                    if log_callback:
                        log_callback(msg)
                else:
                    # Create TranscriptSegment
                    ts = TranscriptSegment(
                        speaker=speaker_name,
                        text=segment_text,
                        start_time=segment.start,
                        end_time=segment.end,
                        confidence=1.0  # Could be enhanced with actual confidence scores
                    )
                    transcript_segments.append(ts)
                    text_parts.append(segment.text)
                
                # Progress callback
                if progress_callback and total_duration_ms > 0:
                    progress = min(100, int((segment.end * 1000 / total_duration_ms) * 100))
                    current_text = "".join(text_parts)
                    progress_callback(progress, current_text, detected_lang_info)
            
            # Final callback
            full_text = "".join(text_parts)
            if progress_callback:
                progress_callback(100, full_text, detected_lang_info)
            
            msg = f"Transcription complete. {len(transcript_segments)} segments extracted."
            print(msg)
            if log_callback:
                log_callback(msg)
            
            return {
                "segments": transcript_segments,
                "text": full_text,
                "detected_language": detected_lang_info["language"] if detected_lang_info else language,
                "language_probability": detected_lang_info["probability"] if detected_lang_info else None,
                "duration": info.duration
            }
            
        except Exception as e:
            print(f"Error during transcription with timestamps: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _is_hallucination(self, text: str, config=None) -> bool:
        """
        Detect potential hallucinations in transcribed text.
        
        Args:
            text: The transcribed text segment
            config: ConfigManager instance for getting settings
            
        Returns:
            True if the text appears to be a hallucination
        """
        if not text or len(text.strip()) < 3:
            return True
            
        text = text.lower().strip()
        
        # Get min repetitions from config if available
        min_repetitions = 3
        if config:
            min_repetitions = config.get("min_word_repetitions", 3)
        
        # Common hallucination patterns
        hallucination_patterns = [
            "thank you for watching",
            "thanks for watching", 
            "please subscribe",
            "like and subscribe",
            "subtitles by",
            "transcribed by",
            "captions by",
            "♪",  # Music notation
            "[music]",
            "[applause]",
            "www.",
            "http"
        ]
        
        # Check for common hallucination phrases
        for pattern in hallucination_patterns:
            if pattern in text:
                return True
        
        # Check for repetitive patterns (like "I mean I mean I mean...")
        words = text.split()
        if len(words) >= min_repetitions:
            # Check if the same word/phrase repeats min_repetitions times consecutively
            for i in range(len(words) - min_repetitions + 1):
                # Check if all words in the window are the same
                all_same = True
                first_word = words[i]
                for j in range(1, min_repetitions):
                    if words[i + j] != first_word:
                        all_same = False
                        break
                if all_same:
                    return True
                    
            # Check for alternating patterns (like "a b a b a b")
            if len(words) >= 6:
                pattern_length = 2
                for start in range(len(words) - pattern_length * 3):
                    pattern = words[start:start + pattern_length]
                    is_repeating = True
                    for rep in range(1, 3):  # Check 2 more repetitions
                        next_pattern = words[start + pattern_length * rep:start + pattern_length * (rep + 1)]
                        if pattern != next_pattern:
                            is_repeating = False
                            break
                    if is_repeating:
                        return True
        
        # Check for very short repetitive segments
        if len(text) > 20 and len(set(text.replace(' ', ''))) < 5:
            return True
            
        return False