"""
Worker for processing meeting transcriptions with multiple audio files.
"""

from typing import List, Dict, Optional
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from app.core.transcription_service_ext import TranscriptionServiceExt
from app.core.meeting_transcript import MeetingTranscript, extract_speaker_name


class MeetingTranscriptionSignals(QObject):
    """Signals for meeting transcription worker."""
    progress = Signal(int, str)  # overall_progress, status_message
    file_progress = Signal(str, int, str)  # file_name, progress, text
    finished = Signal(object)  # MeetingTranscript
    error = Signal(str)


class MeetingTranscriptionWorker(QRunnable):
    """Worker for transcribing multiple audio files and creating meeting transcript."""
    
    def __init__(
        self,
        transcription_service: TranscriptionServiceExt,
        audio_files: List[str],
        participant_names: Optional[List[str]] = None,
        language: str = None,
        task: str = "transcribe"
    ):
        super().__init__()
        self.transcription_service = transcription_service
        self.audio_files = audio_files
        self.participant_names = participant_names or [
            extract_speaker_name(f) for f in audio_files
        ]
        self.language = language
        self.task = task
        self.signals = MeetingTranscriptionSignals()
        self._is_cancelled = False
    
    def run(self):
        """Process all audio files and create meeting transcript."""
        try:
            # Create meeting transcript
            meeting = MeetingTranscript(
                date=datetime.now(),
                participants=self.participant_names,
                audio_files=dict(zip(self.participant_names, self.audio_files))
            )
            
            total_files = len(self.audio_files)
            
            # Process each audio file
            for idx, (audio_file, speaker_name) in enumerate(zip(self.audio_files, self.participant_names)):
                if self._is_cancelled:
                    self.signals.error.emit("Transcription cancelled")
                    return
                
                # Update overall progress
                overall_progress = int((idx / total_files) * 100)
                self.signals.progress.emit(
                    overall_progress,
                    f"Processing {speaker_name}... ({idx + 1}/{total_files})"
                )
                
                # Create progress callback for this file
                def file_progress_callback(progress, text, lang_info):
                    self.signals.file_progress.emit(speaker_name, progress, text)
                
                # Transcribe with timestamps
                result = self.transcription_service.transcribe_with_timestamps(
                    audio_file,
                    speaker_name=speaker_name,
                    language=self.language,
                    task=self.task,
                    progress_callback=file_progress_callback
                )
                
                if not result:
                    self.signals.error.emit(f"Failed to transcribe {speaker_name}'s audio")
                    return
                
                # Add segments to meeting transcript
                for segment in result['segments']:
                    meeting.add_segment(segment)
            
            # Sort segments by timestamp
            meeting.sort_segments()
            
            # Update final progress
            self.signals.progress.emit(100, "Processing complete!")
            
            # Emit the completed transcript
            self.signals.finished.emit(meeting)
            
        except Exception as e:
            import traceback
            error_msg = f"Meeting transcription error: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.signals.error.emit(str(e))
    
    def cancel(self):
        """Cancel the transcription process."""
        self._is_cancelled = True