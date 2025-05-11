"""
Setup script for packaging the Whisper Transcription UI app with py2app.
"""
from setuptools import setup

APP = ['app/main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'packages': ['PySide6', 'faster_whisper', 'sounddevice', 'numpy', 'scipy', 'pyperclip', 'rapidfuzz'],
    'plist': {
        'CFBundleName': 'Whisper Transcription UI',
        'CFBundleDisplayName': 'Whisper Transcription UI',
        'CFBundleIdentifier': 'com.user.whisper-transcribe-ui',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'NSMicrophoneUsageDescription': 'This app requires microphone access to record audio for transcription.',
        'LSUIElement': True,  # Makes the app a "faceless" application (no dock icon)
    },
    'iconfile': 'resources/app_icon.icns',
}

setup(
    name='WhisperTranscriptionUI',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
) 