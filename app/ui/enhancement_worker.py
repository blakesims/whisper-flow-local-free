"""
Worker for enhancing meeting transcripts with visual analysis.
"""

from PySide6.QtCore import QObject, Signal, QRunnable
from typing import Optional, Dict, Any

from app.core.meeting_transcript import MeetingTranscript
from app.core.transcript_enhancer import TranscriptEnhancer


class EnhancementSignals(QObject):
    """Signals for enhancement worker."""
    progress = Signal(str)  # status message
    finished = Signal(dict)  # enhancement results
    error = Signal(str)


class MeetingEnhancementWorker(QRunnable):
    """Worker for enhancing meeting transcripts with visual elements."""
    
    def __init__(
        self,
        meeting_dir: str,
        transcript: MeetingTranscript,
        gemini_api_key: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        max_visual_points: int = 20
    ):
        """
        Initialize enhancement worker.
        
        Args:
            meeting_dir: Path to Zoom meeting directory
            transcript: MeetingTranscript object to enhance
            gemini_api_key: Optional Gemini API key
            custom_prompt: Optional custom prompt for visual analysis
            max_visual_points: Maximum visual points to identify
        """
        super().__init__()
        self.meeting_dir = meeting_dir
        self.transcript = transcript
        self.gemini_api_key = gemini_api_key
        self.custom_prompt = custom_prompt
        self.max_visual_points = max_visual_points
        self.signals = EnhancementSignals()
        self._is_cancelled = False
    
    def run(self):
        """Run the enhancement process."""
        try:
            # Initialize enhancer
            self.signals.progress.emit("Initializing enhancement service...")
            enhancer = TranscriptEnhancer(gemini_api_key=self.gemini_api_key)
            
            if self._is_cancelled:
                return
            
            # Run enhancement
            self.signals.progress.emit("Analyzing transcript for visual points...")
            results = enhancer.enhance_meeting_transcript(
                self.meeting_dir,
                self.transcript,
                custom_prompt=self.custom_prompt,
                max_visual_points=self.max_visual_points
            )
            
            if self._is_cancelled:
                return
            
            # Report results
            visual_count = len(results.get("visual_points", []))
            frame_count = len(results.get("extracted_frames", {}))
            
            if results.get("errors"):
                error_msg = "; ".join(results["errors"])
                self.signals.progress.emit(f"Enhancement completed with errors: {error_msg}")
            else:
                self.signals.progress.emit(
                    f"Enhancement complete: {visual_count} visual points, "
                    f"{frame_count} frames extracted"
                )
            
            # Emit results
            self.signals.finished.emit(results)
            
        except Exception as e:
            import traceback
            error_msg = f"Enhancement error: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.signals.error.emit(str(e))
    
    def cancel(self):
        """Cancel the enhancement process."""
        self._is_cancelled = True