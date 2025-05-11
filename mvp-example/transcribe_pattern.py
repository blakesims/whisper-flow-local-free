import argparse
import os
import queue
import subprocess
import threading
import time

import numpy as np
import pyperclip
import sounddevice as sd

# Import Faster Whisper
from faster_whisper import WhisperModel
from scipy.io.wavfile import write

# Get the directory of the script
script_directory = os.path.dirname(os.path.abspath(__file__))

# Configuration
CONFIG = {
    "recording": {
        "sample_rate": 16000,
        "channels": 1,
        "audio_directory": os.path.join(script_directory, "recordings"),
    },
    "transcription": {
        "model": "base",  # You can use "base", "small", "medium", "large-v2", "large-v3", etc.
        "transcription_directory": os.path.join(script_directory, "transcriptions"),
    },
    "fabric": {
        "enable_fabric": True,
        "output_directory": os.path.join(script_directory, "fabric_outputs"),
        "directory": "/Users/blake/fabric",
    },
}

stop_recording = threading.Event()
cancel_recording = threading.Event()


def record_audio(sample_rate, channels, filename):
    print("Recording...")
    frames = []
    audio_queue = queue.Queue()

    def callback(indata, frames, time, status):
        audio_queue.put(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate, channels=channels, callback=callback
    )
    with stream:
        while not stop_recording.is_set():
            if cancel_recording.is_set():
                cancel_recording.clear()
                frames = []
                continue
            frame = audio_queue.get()
            frames.append(frame)

    recording = np.concatenate(frames)
    recording = np.int16(recording / np.max(np.abs(recording)) * 32767)

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    write(filename, sample_rate, recording)
    print(f"Recording saved to {filename}")

    return filename


def transcribe_audio(recording_filepath, model_name, language, translate):
    print("Transcribing audio with Faster Whisper...")

    # Set device and compute_type for Macbook Pro (CPU)
    device = "cpu"
    compute_type = (
        "int8"  # Use int8 for best CPU speed; try "float32" if you want max accuracy
    )

    # Load the model
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    # Map language to code (faster-whisper expects ISO codes)
    lang_map = {"english": "en", "thai": "th"}
    language_code = lang_map.get(language.lower(), "en")

    # Transcribe
    segments, info = model.transcribe(
        recording_filepath,
        beam_size=5,
        language=language_code,
        task="translate" if translate else "transcribe",
    )

    # Collect the text from all segments
    transcription_text = "".join([segment.text for segment in segments])

    print(
        f"Detected language: {info.language} (probability: {info.language_probability:.2f})"
    )
    return transcription_text


def generate_fabric_response(transcription_text, prompt, output_directory):
    print("Generating Fabric response...")
    command = f'echo "{transcription_text}" | fabric --pattern "{prompt}"'
    output = subprocess.check_output(command, shell=True, universal_newlines=True)
    if output_directory:
        output_filename = os.path.join(output_directory, "fabric_output.txt")
        os.makedirs(output_directory, exist_ok=True)
        with open(output_filename, "w") as file:
            file.write(output)
        print(f"Fabric response saved to {output_filename}")
    else:
        print("Fabric response:")
        print(output)
    pyperclip.copy(output)
    print("Fabric response copied to clipboard.")


def main():
    parser = argparse.ArgumentParser(description="Record and transcribe audio")
    parser.add_argument(
        "--language", choices=["english", "thai"], help="Language of the spoken audio"
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Translate the transcription to English",
    )
    parser.add_argument(
        "--transcribe_only",
        action="store_true",
        help="Only transcribe the audio without generating Fabric response",
    )
    parser.add_argument(
        "--model",
        default=CONFIG["transcription"]["model"],
        help="Whisper model to use for transcription",
    )
    parser.add_argument(
        "--automated",
        action="store_true",
        help="Automated mode (don't ask for user input - script is being run from a shell script)",
    )
    parser.add_argument(
        "--prompt", help="Fabric prompt to use for generating Fabric response"
    )
    args = parser.parse_args()

    if args.automated:
        recording_filepath = os.path.join(
            CONFIG["recording"]["audio_directory"], "recording.wav"
        )
        stop_recording_filepath = os.path.join(
            CONFIG["recording"]["audio_directory"], "stop_recording.txt"
        )

        os.makedirs(CONFIG["recording"]["audio_directory"], exist_ok=True)
        if os.path.exists(stop_recording_filepath):
            os.remove(stop_recording_filepath)

        recording_thread = threading.Thread(
            target=record_audio,
            args=(
                CONFIG["recording"]["sample_rate"],
                CONFIG["recording"]["channels"],
                recording_filepath,
            ),
        )
        recording_thread.start()

        print("Recording started. Waiting for stop recording file...")

        while True:
            if os.path.exists(stop_recording_filepath):
                stop_recording.set()
                recording_thread.join()
                break
            time.sleep(0.1)

        print("Recording stopped.")

        if os.path.exists(recording_filepath):
            transcription_text = transcribe_audio(
                recording_filepath, args.model, args.language, args.translate
            )
            print("Transcription:")
            print(transcription_text)
            pyperclip.copy(transcription_text)
            # show a notification to the user
            notification_command = """
            osascript -e 'display notification "Transcription copied to clipboard." with title "Transcription"'
            """
            subprocess.run(notification_command, shell=True)
            paste_command = """
            osascript -e 'tell application "System Events" to keystroke "v" using command down'
            """
            subprocess.run(paste_command, shell=True)
            print("Transcription copied to clipboard.")
        else:
            print("Error: Recording file not found.")
        return

    if args.language:
        language = args.language
    else:
        language = input(
            "Enter the language of the spoken audio (e for English, t for Thai): "
        )
        if language.lower() == "e":
            language = "english"
        elif language.lower() == "t":
            language = "thai"
        else:
            print("Invalid language input. Defaulting to English.")
            language = "english"

    if args.translate:
        translate = True
    elif language.lower() != "english":
        translate_input = input(
            "Do you want to translate the transcription to English? (y/n): "
        )
        translate = translate_input.lower() == "y"
    else:
        translate = False

    recording_filepath = os.path.join(
        CONFIG["recording"]["audio_directory"], "recording.wav"
    )

    print(
        "Press 'c' to cancel and restart the recording, or 's' to stop the recording."
    )
    while True:
        recording_thread = threading.Thread(
            target=record_audio,
            args=(
                CONFIG["recording"]["sample_rate"],
                CONFIG["recording"]["channels"],
                recording_filepath,
            ),
        )
        recording_thread.start()

        while True:
            key = input()
            if key.lower() == "c":
                cancel_recording.set()
                recording_thread.join()
                break
            elif key.lower() == "s":
                stop_recording.set()
                recording_thread.join()
                break

        if stop_recording.is_set():
            break

    transcription_text = transcribe_audio(
        recording_filepath, args.model, language, translate
    )
    print("Transcription:")
    print(transcription_text)
    pyperclip.copy(transcription_text)
    print("Transcription copied to clipboard.")

    if not args.transcribe_only and CONFIG["fabric"]["enable_fabric"]:
        if args.prompt:
            prompt = args.prompt
        else:
            print("Available prompts:")
            favourite_prompts_dir = os.path.join(
                CONFIG["fabric"]["directory"], "favourite-patterns"
            )
            favourite_prompts = os.listdir(favourite_prompts_dir)
            for prompt in favourite_prompts:
                print(f"- {prompt}")
            prompt = input("Enter the prompt number or name: ")
        generate_fabric_response(
            transcription_text, prompt, CONFIG["fabric"]["output_directory"]
        )


if __name__ == "__main__":
    main()
