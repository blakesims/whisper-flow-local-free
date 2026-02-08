"""
Transcription service wrapper.

Centralizes all app.core and app.utils imports used by kb/ modules.
If the app/ transcription backend changes, only this file needs updating.
"""
import os
import sys

# Ensure project root is on path for app.* imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.transcription_service_cpp import get_transcription_service
from app.utils.config_manager import ConfigManager

__all__ = ["get_transcription_service", "ConfigManager"]
