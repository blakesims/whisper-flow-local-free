from PySide6.QtCore import QObject, Signal, Slot, QRunnable

class WorkerSignals(QObject):
    """ Generic signals for workers """
    finished = Signal(object)  # Can emit various types of results
    error = Signal(str)
    progress = Signal(int, str, dict) # Kept for TranscriptionWorker compatibility, can be adapted

class TranscriptionWorker(QRunnable):
    """
    Worker thread for running transcription to avoid blocking the UI.
    Inherits from QRunnable to be used with QThreadPool.
    """
    # Signal arguments: progress_percentage (int), current_text (str), detected_language_info (dict or None)
    progressUpdated = Signal(int, str, dict)
    
    # Signal arguments: result_dict (dict from TranscriptionService.transcribe)
    transcriptionFinished = Signal(dict)
    
    # Signal arguments: error_message (str)
    transcriptionError = Signal(str)

    def __init__(self, transcription_service, audio_path, language=None, task="transcribe"):
        super().__init__()
        self.transcription_service = transcription_service
        self.audio_path = audio_path
        self.language = language
        self.task = task
        self.signals = WorkerSignals() # Use the generic signals object
        
        # Connect internal signals to the class-level signals (or rather, the user connects to these)
        self.progressUpdated = self.signals.progress
        self.transcriptionFinished = self.signals.finished
        self.transcriptionError = self.signals.error

    def _progress_callback(self, percentage, current_text, detected_lang_info):
        self.signals.progress.emit(percentage, current_text, detected_lang_info)

    @Slot()
    def run(self):
        """
        Execute the transcription task.
        """
        if not self.transcription_service or not self.audio_path:
            self.signals.error.emit("Transcription worker not properly initialized.")
            return

        try:
            result = self.transcription_service.transcribe(
                self.audio_path,
                language=self.language,
                task=self.task,
                progress_callback=self._progress_callback
            )
            if result:
                self.signals.finished.emit(result)
            else:
                self.signals.error.emit("Transcription failed or returned no result.")
        except Exception as e:
            self.signals.error.emit(f"Transcription error: {str(e)}")


class FabricListPatternsWorker(QRunnable):
    """
    Worker thread for listing Fabric patterns to avoid blocking the UI.
    """
    def __init__(self, fabric_service):
        super().__init__()
        self.fabric_service = fabric_service
        self.signals = WorkerSignals() # Use the generic signals object

    @Slot()
    def run(self):
        """
        Execute the pattern listing task.
        """
        if not self.fabric_service:
            self.signals.error.emit("FabricService not provided to worker.")
            return
        try:
            patterns = self.fabric_service.list_patterns()
            if patterns is not None: # list_patterns returns None on error, or [] if empty but successful
                self.signals.finished.emit(patterns) # Emit list of patterns
            else:
                self.signals.error.emit("Failed to list Fabric patterns. Service returned None.")
        except Exception as e:
            self.signals.error.emit(f"Error listing Fabric patterns: {str(e)}") 