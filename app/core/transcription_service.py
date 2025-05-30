from faster_whisper import WhisperModel
import os
import sys
import platform
from app.utils.config_manager import ConfigManager

# Determine a sensible cache directory for models if needed,
# faster-whisper might handle this by default in user's cache.
# For PySide6 apps, using app-specific data/cache dirs is good.
# from app.utils.config_manager import ConfigManager # For model path/settings

class TranscriptionService:
    def __init__(self, config_manager: ConfigManager = None):
        """
        Initializes the TranscriptionService.
        It will attempt to use the provided ConfigManager to get model settings.
        If no ConfigManager is provided, or settings are missing, it falls back to defaults.

        Args:
            config_manager (ConfigManager, optional): Instance of ConfigManager.
        """
        self.config_manager = config_manager
        self.model_name = "base"  # Default model name
        # On Apple Silicon, faster-whisper only supports CPU device
        # MPS (Metal Performance Shaders) is not supported by CTranslate2
        self.device = "cpu"       # Only supported device on Apple Silicon
        # int8 provides best performance on Apple Silicon CPU
        # float32 is the fallback option, but int8 is faster
        self.compute_type = "int8" # Optimal for Apple Silicon
        self.cpu_threads = 0      # Default (auto-detect)
        self.model = None         # Model will be loaded on demand

        if self.config_manager:
            self.model_name = self.config_manager.get("transcription_model_name", self.model_name)
            self.device = self.config_manager.get("transcription_device", self.device)
            self.compute_type = self.config_manager.get("transcription_compute_type", self.compute_type)
            self.cpu_threads = self.config_manager.get("transcription_cpu_threads", self.cpu_threads)
        
        # DO NOT load model here: self._load_model() 

    def _load_model(self):
        """
        Synchronously loads the Whisper model based on current attributes.
        This is intended to be called by a background worker.
        """
        if self.model_name is None: # Should not happen if set_target_model_config is called first
            print("Error: Model name not specified for loading.")
            self.model = None
            return

        # Optimize CPU thread usage
        cpu_threads = self.cpu_threads  # Use configured value
        if self.device == "cpu" and cpu_threads == 0:
            # Auto-detect optimal thread count
            logical_cores = os.cpu_count() or 4
            
            # Apple Silicon optimization
            # M1/M2/M3 have high-performance and efficiency cores
            # Using all logical cores on Apple Silicon is actually beneficial
            if sys.platform == "darwin" and "arm" in platform.machine().lower():
                # Apple Silicon detected - use more aggressive threading
                cpu_threads = logical_cores - 1  # Leave 1 core for system
                print(f"Apple Silicon detected: Using {cpu_threads} threads ({logical_cores} cores total)")
            else:
                # Intel/AMD - use conservative approach
                cpu_threads = max(4, min(logical_cores - 2, logical_cores // 2))
                print(f"CPU mode: Auto-detected {cpu_threads} threads (detected {logical_cores} logical cores)")
        elif self.device == "cpu":
            print(f"CPU mode: Using configured {cpu_threads} threads")

        print(f"Loading Whisper model: {self.model_name} (compute: {self.compute_type} on device: {self.device})")
        try:
            # Note: On Apple Silicon (M1/M2/M3), faster-whisper only supports CPU device
            # MPS is not supported by the underlying CTranslate2 library
            # However, CPU performance is still excellent due to:
            # 1. CTranslate2's optimized inference engine
            # 2. int8 quantization support on ARM64
            # 3. Apple Accelerate framework integration
            self.model = WhisperModel(
                self.model_name, 
                device=self.device, 
                compute_type=self.compute_type,
                cpu_threads=cpu_threads,
                num_workers=1  # Keep at 1 for stability with Qt
            )
            print(f"Model {self.model_name} loaded successfully with {cpu_threads} CPU threads.")
        except Exception as e:
            print(f"Error loading Whisper model {self.model_name}: {e}")
            self.model = None # Ensure model is None on failure

    def set_target_model_config(self, model_name: str, device: str = None, compute_type: str = None):
        """
        Updates the target model configuration. Does not load the model.
        Sets self.model to None as the configuration has changed.
        """
        print(f"Setting target model config to: Name={model_name}, Device={device or self.device}, Compute={compute_type or self.compute_type}")
        self.model_name = model_name
        if device is not None:
            self.device = device
        if compute_type is not None:
            self.compute_type = compute_type
        self.model = None # Configuration changed, invalidate currently loaded model (if any)

    def reload_model_with_config(self): # This method might need re-evaluation or become a trigger for async load
        """
        Reloads the model based on current settings from ConfigManager or defaults.
        This should ideally trigger an asynchronous load process if used.
        For now, it's less relevant if MainWindow controls loading via set_target_model_config + worker.
        """
        # This method's direct call to _load_model is problematic for async UI.
        # It's better if MainWindow handles triggering reloads.
        # Consider deprecating or refactoring this if MainWindow manages all load triggers.
        print("reload_model_with_config: This method should be used cautiously or refactored for async operation via MainWindow.")
        # For now, let's make it update config and MainWindow would have to notice or be told to reload.
        current_model_name = self.model_name
        current_device = self.device
        current_compute_type = self.compute_type

        if self.config_manager:
            self.model_name = self.config_manager.get("transcription_model_name", self.model_name)
            self.device = self.config_manager.get("transcription_device", self.device)
            self.compute_type = self.config_manager.get("transcription_compute_type", self.compute_type)
        
        if (self.model_name != current_model_name or 
            self.device != current_device or 
            self.compute_type != current_compute_type):
            self.model = None # Config changed
            print("Model configuration updated from ConfigManager. UI should trigger reload if needed.")
        else:
            print("Model configuration from ConfigManager matches current. No change to service state.")

    def get_model_details(self):
        """Returns current model details."""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "loaded": self.model is not None
        }

    def transcribe(self, audio_path: str, language: str = None, task: str = "transcribe", beam_size: int = 1, progress_callback=None):
        if not self.model:
            # This check is now more critical as model loading is deferred
            print("Transcription model is not loaded or is invalid. Cannot transcribe.")
            # Try to load the configured model synchronously as a last resort?
            # Or better, ensure UI prevents transcription if model isn't loaded.
            # For now, just return None. The UI should manage this state.
            # self._load_model() # Avoid synchronous load here during a transcribe call if UI expects async
            # if not self.model:
            return None # Return None if model isn't ready
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return None

        try:
            print(f"Transcribing {audio_path} (lang: {language or 'auto'}, task: {task})...")
            # Optimized settings for Apple Silicon
            segments_generator, info = self.model.transcribe(
                audio_path,
                language=language, 
                task=task,
                beam_size=beam_size,
                best_of=1,  # Reduce computation, minimal quality impact
                patience=1.0,  # Faster beam search termination
                length_penalty=1.0,  # Neutral length penalty
                temperature=0.0,  # Deterministic, faster
                vad_filter=True,  # Voice Activity Detection for faster processing
                vad_parameters=dict(
                    threshold=0.5,
                    min_speech_duration_ms=250,
                    max_speech_duration_s=float('inf'),
                    min_silence_duration_ms=2000,
                    window_size_samples=1024,
                    speech_pad_ms=400
                )
            )

            detected_lang_info = None
            if language is None: 
                print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
                detected_lang_info = {
                    "language": info.language,
                    "probability": info.language_probability
                }
            
            transcription_text_parts = []
            total_duration_ms = info.duration * 1000
            first_segment = True

            for segment in segments_generator:
                transcription_text_parts.append(segment.text)
                current_text = "".join(transcription_text_parts)
                progress_percentage = 0
                if total_duration_ms > 0:
                    progress_percentage = min(100, int((segment.end * 1000 / total_duration_ms) * 100))
                
                if progress_callback:
                    callback_lang_info = detected_lang_info if language is None and first_segment else None
                    progress_callback(progress_percentage, current_text, callback_lang_info)
                    if first_segment and callback_lang_info:
                        first_segment = False
            
            transcription_text = "".join(transcription_text_parts)
            
            final_detected_language = None
            final_language_probability = None
            if detected_lang_info:
                final_detected_language = detected_lang_info["language"]
                final_language_probability = detected_lang_info["probability"]
            elif language: 
                final_detected_language = language

            if progress_callback:
                final_cb_lang_info = {"language": final_detected_language, "probability": final_language_probability} if final_detected_language else None
                progress_callback(100, transcription_text, final_cb_lang_info)

            print("Transcription complete.")
            return {
                "text": transcription_text,
                "detected_language": final_detected_language,
                "language_probability": final_language_probability
            }
        except Exception as e:
            print(f"Error during transcription: {e}")
            return None

# Example Usage (for testing the service directly)
if __name__ == '__main__':
    # This example assumes you have an audio file named 'test_audio.wav'
    # in the same directory as this script, or provide a full path.
    # You also need to have faster-whisper installed and models downloaded (first run will download).
    
    # Create a dummy wav file for testing if one doesn't exist
    if not os.path.exists("test_audio.wav"):
        print("Creating a dummy test_audio.wav as it was not found.")
        import numpy as np
        from scipy.io.wavfile import write as write_wav
        sample_rate = 16000
        duration = 2  # seconds
        frequency = 440 # Hz (A4 note)
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = 0.5 * np.sin(2 * np.pi * frequency * t)
        # Convert to 16-bit PCM
        audio_data_int16 = np.int16(audio_data * 32767)
        write_wav("test_audio.wav", sample_rate, audio_data_int16)
        print("Dummy test_audio.wav created.")

    print("Testing TranscriptionService...")
    # Test with default base model
    transcription_service = TranscriptionService() # Using "base" for faster first test
    
    if transcription_service.model:
        audio_file = "test_audio.wav" # Ensure this file exists or change path
        print(f"\n--- Transcribing {audio_file} (English, default model) ---")
        
        def my_progress_logger(percentage, text, lang_info):
            progress_msg = f"Progress: {percentage}% - Current text (partial): {text[:50]}..."
            if lang_info:
                progress_msg += f" (Detected Lang: {lang_info['language']} P: {lang_info['probability']:.2f})"
            print(progress_msg)

        result_dict = transcription_service.transcribe(audio_file, language="en", progress_callback=my_progress_logger) # Test with specified language
        # result_dict = transcription_service.transcribe(audio_file, progress_callback=my_progress_logger) # Test auto-detect
        
        if result_dict:
            print(f"Final Transcription Result: {result_dict['text']}")
            if result_dict["detected_language"]:
                print(f"Detected Language: {result_dict['detected_language']} (Probability: {result_dict['language_probability']})")
        else:
            print("Transcription failed or returned None.")

        # Example: Transcribe and translate (if model supports it and audio is not English)
        # print(f"\n--- Translating {audio_file} (assuming non-English audio) ---")
        # result_translate = transcription_service.transcribe(audio_file, task="translate", language="es") # Example with Spanish
        # if result_translate:
        #     print(f"Translation Result: {result_translate}")
        # else:
        #     print("Translation failed or returned None.")
    else:
        print("Failed to initialize TranscriptionService model. Cannot run tests.") 