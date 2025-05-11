from faster_whisper import WhisperModel
import os
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
        self.model_name = "base"
        self.device = "cpu"
        self.compute_type = "int8"
        self.model = None
        
        if self.config_manager:
            self.model_name = self.config_manager.get("transcription_model_name", self.model_name)
            self.device = self.config_manager.get("transcription_device", self.device)
            self.compute_type = self.config_manager.get("transcription_compute_type", self.compute_type)
        
        self._load_model()

    def _load_model(self):
        print(f"Loading Whisper model: {self.model_name} (compute: {self.compute_type} on device: {self.device})")
        try:
            # faster-whisper handles its own model caching.
            self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            print(f"Model {self.model_name} loaded successfully.")
        except Exception as e:
            print(f"Error loading Whisper model {self.model_name}: {e}")
            self.model = None

    def reload_model_with_config(self):
        """
        Reloads the model based on current settings from ConfigManager or defaults.
        Useful if transcription settings (model_name, device, compute_type) are changed.
        """
        if self.config_manager:
            new_model_name = self.config_manager.get("transcription_model_name", "base")
            new_device = self.config_manager.get("transcription_device", "cpu")
            new_compute_type = self.config_manager.get("transcription_compute_type", "int8")
        else:
            # Fallback to current or default if no config manager
            new_model_name = self.model_name
            new_device = self.device
            new_compute_type = self.compute_type

        if (new_model_name != self.model_name or
            new_device != self.device or
            new_compute_type != self.compute_type or
            self.model is None):
            
            self.model_name = new_model_name
            self.device = new_device
            self.compute_type = new_compute_type
            self._load_model()
        else:
            print("Model configuration hasn't changed. Not reloading.")

    def get_model_details(self):
        """Returns current model details."""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "loaded": self.model is not None
        }

    def set_model(self, model_name: str, device: str = None, compute_type: str = None):
        """
        Sets a new model name and reloads the model.
        Device and compute_type can also be updated, otherwise existing ones are used.
        """
        should_reload = False
        if model_name != self.model_name:
            self.model_name = model_name
            should_reload = True
        
        # Use existing if None is passed for device/compute_type
        current_device = device if device is not None else self.device
        current_compute_type = compute_type if compute_type is not None else self.compute_type

        if current_device != self.device:
            self.device = current_device
            should_reload = True
        
        if current_compute_type != self.compute_type:
            self.compute_type = current_compute_type
            should_reload = True
            
        if should_reload or self.model is None:
            # self.model_name is already updated if it changed
            print(f"Setting new model configuration: {self.model_name}, Device: {self.device}, Compute: {self.compute_type}")
            self._load_model() # _load_model uses self.model_name, self.device, self.compute_type
        else:
            print(f"Model configuration ({model_name}) hasn't changed significantly. Not reloading.")

    def transcribe(self, audio_path: str, language: str = None, task: str = "transcribe", beam_size: int = 5, progress_callback=None):
        """
        Transcribes the given audio file.

        Args:
            audio_path (str): Path to the audio file.
            language (str, optional): Language code (e.g., "en", "es"). Defaults to None (auto-detect).
            task (str, optional): "transcribe" or "translate". Defaults to "transcribe".
            beam_size (int, optional): Beam size for transcription. Defaults to 5.
            progress_callback (function, optional): A function to call with progress updates.
                                                  It receives (percentage, current_text, detected_language_info dict or None).

        Returns:
            dict: A dictionary containing {
                'text': str, 
                'detected_language': str or None, 
                'language_probability': float or None
            }, or None if transcription fails.
        """
        if not self.model:
            print("Transcription model is not loaded. Cannot transcribe.")
            return None
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return None

        try:
            print(f"Transcribing {audio_path} (lang: {language or 'auto'}, task: {task})...")
            segments_generator, info = self.model.transcribe(
                audio_path,
                language=language, # Pass explicitly specified language
                task=task,
                beam_size=beam_size
            )

            detected_lang_info = None
            if language is None: # Auto-detection was used
                # info.language and info.language_probability are available after the first segment
                # For now, we will report it once at the beginning and at the end.
                # A more sophisticated approach might update it if it changes (though unlikely for a single file)
                print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
                detected_lang_info = {
                    "language": info.language,
                    "probability": info.language_probability
                }
            
            transcription_text_parts = []
            total_duration_ms = info.duration * 1000  # Convert to milliseconds
            first_segment = True

            for segment in segments_generator:
                transcription_text_parts.append(segment.text)
                current_text = "".join(transcription_text_parts)
                progress_percentage = 0
                if total_duration_ms > 0:
                    progress_percentage = min(100, int((segment.end * 1000 / total_duration_ms) * 100))
                
                if progress_callback:
                    # Pass detected_lang_info. It becomes available after the first call to transcribe internal logic.
                    # If language was specified, detected_lang_info remains None (or could be set to the specified lang).
                    # For simplicity, only passing it when auto-detected.
                    callback_lang_info = detected_lang_info if language is None and first_segment else None
                    progress_callback(progress_percentage, current_text, callback_lang_info)
                    if first_segment and callback_lang_info:
                        first_segment = False # Sent it once
            
            transcription_text = "".join(transcription_text_parts)
            
            final_detected_language = None
            final_language_probability = None
            if detected_lang_info: # If auto-detection was on
                final_detected_language = detected_lang_info["language"]
                final_language_probability = detected_lang_info["probability"]
            elif language: # If a language was specified by the user
                final_detected_language = language # Reflect the user's choice as the "effective" language

            if progress_callback:
                # For the final callback, pass the consolidated detected language info
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