"""
Setup script for packaging the Whisper Transcription UI app with py2app.
"""
from setuptools import setup

APP = ['app/main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,  # Faster startup
    'packages': ['PySide6', 'sounddevice', 'numpy', 'scipy', 'pyperclip'],
    'includes': ['app', 'app.core', 'app.ui', 'app.utils', 'app.core.audio_recorder', 
                 'app.core.transcription_service', 'app.core.fabric_service',
                 'app.ui.main_window', 'app.ui.waveform_widget', 'app.ui.workers',
                 'app.ui.pattern_selection_dialog', 'app.utils.config_manager'],
    'excludes': ['matplotlib', 'PIL', 'IPython', 'jupyter', 'pytest', 'test'],
    'semi_standalone': True,  # Use system Python to avoid some issues
    'site_packages': True,
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