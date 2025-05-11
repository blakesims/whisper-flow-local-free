from PySide6.QtCore import QObject, Signal, Slot, QRunnable

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
        
        # QRunnable does not inherit from QObject, so signals must be defined
        # on a QObject instance. We create one internally.
        class WorkerSignals(QObject):
            progress = Signal(int, str, dict)
            finished = Signal(dict)
            error = Signal(str)
        
        self.signals = WorkerSignals()
        
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