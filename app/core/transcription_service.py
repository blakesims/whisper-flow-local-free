from faster_whisper import WhisperModel
import os

# Determine a sensible cache directory for models if needed,
# faster-whisper might handle this by default in user's cache.
# For PySide6 apps, using app-specific data/cache dirs is good.
# from app.utils.config_manager import ConfigManager # For model path/settings

class TranscriptionService:
    def __init__(self, model_name="base", device="cpu", compute_type="int8"):
        """
        Initializes the TranscriptionService.

        Args:
            model_name (str): Name of the faster-whisper model (e.g., "base", "small", "medium").
            device (str): Device to use for computation ("cpu", "cuda").
            compute_type (str): Type of computation (e.g., "int8", "float16", "float32").
        """
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self._load_model() # Load model on initialization

    def _load_model(self):
        print(f"Loading Whisper model: {self.model_name} ({self.compute_type} on {self.device})")
        try:
            # Consider making the model download path configurable via ConfigManager
            # For now, faster-whisper will use its default cache path.
            self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            print(f"Model {self.model_name} loaded successfully.")
        except Exception as e:
            print(f"Error loading Whisper model {self.model_name}: {e}")
            # Optionally, re-raise or handle more gracefully (e.g., fallback model)
            self.model = None 

    def transcribe(self, audio_path: str, language: str = None, task: str = "transcribe", beam_size: int = 5):
        """
        Transcribes the given audio file.

        Args:
            audio_path (str): Path to the audio file.
            language (str, optional): Language code (e.g., "en", "es"). Defaults to None (auto-detect).
            task (str, optional): "transcribe" or "translate". Defaults to "transcribe".
            beam_size (int, optional): Beam size for transcription. Defaults to 5.

        Returns:
            str: The transcribed text, or None if transcription fails.
        """
        if not self.model:
            print("Transcription model is not loaded. Cannot transcribe.")
            return None
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return None

        try:
            print(f"Transcribing {audio_path} (lang: {language or 'auto'}, task: {task})...")
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                task=task,
                beam_size=beam_size
            )

            if language is None:
                print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
            
            transcription_text = "".join([segment.text for segment in segments])
            # Add a space between segments for better readability if needed, depends on whisper output
            # transcription_text = " ".join([segment.text.strip() for segment in segments if segment.text.strip()])
            print("Transcription complete.")
            return transcription_text
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
    transcription_service = TranscriptionService(model_name="tiny") # Using "tiny" for faster first test
    
    if transcription_service.model:
        audio_file = "test_audio.wav" # Ensure this file exists or change path
        print(f"\n--- Transcribing {audio_file} (English, default model) ---")
        result = transcription_service.transcribe(audio_file, language="en")
        if result:
            print(f"Transcription Result: {result}")
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