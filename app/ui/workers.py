from PySide6.QtCore import QObject, Signal, Slot, QRunnable

class WorkerSignals(QObject):
    """
    Defines signals available from a QRunnable worker.
    Supported signals are:
    - progress: int, str, dict (percentage, current_text, lang_info)
    - finished: dict (result from transcription)
               OR bool, str (success, model_name_or_error for model loading)
               OR list (patterns for fabric listing)
    - error: str (error_message)
    """
    progress = Signal(int, str, dict)
    finished = Signal(object) # Using generic object to handle different finished payloads
    error = Signal(str)

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
        self.signals = WorkerSignals()
        # Connect internal signals to the class-level signals (or rather, the user connects to these)
        # These direct assignments were problematic. User should connect to self.signals.progress etc.
        # self.progressUpdated = self.signals.progress 
        # self.transcriptionFinished = self.signals.finished
        # self.transcriptionError = self.signals.error

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
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """
        Execute the pattern listing task.
        """
        if not self.fabric_service:
            self.signals.error.emit("Fabric service not properly initialized for worker.")
            return
        try:
            patterns = self.fabric_service.list_patterns()
            self.signals.finished.emit(patterns) # Emits list for fabric patterns
        except Exception as e:
            self.signals.error.emit(f"Error listing Fabric patterns: {str(e)}")

class LoadModelWorker(QRunnable):
    """
    Worker thread for loading the transcription model to avoid blocking the UI.
    """
    def __init__(self, transcription_service, model_name, device, compute_type):
        super().__init__()
        self.transcription_service = transcription_service
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Execute the model loading task."""
        if not self.transcription_service:
            self.signals.error.emit("LoadModelWorker: Transcription service instance not provided.")
            # Or self.signals.finished.emit(False, "Transcription service not provided") if using finished for status
            return

        try:
            # Configure the service with the target model details
            self.transcription_service.set_target_model_config(
                model_name=self.model_name, 
                device=self.device, 
                compute_type=self.compute_type
            )
            # Perform the synchronous (blocking) load within this worker thread
            self.transcription_service._load_model()
            
            success = self.transcription_service.model is not None
            if success:
                # Emit model_name as the success message part
                self.signals.finished.emit((True, self.model_name)) 
            else:
                self.signals.finished.emit((False, f"Failed to load {self.model_name}"))
        except Exception as e:
            error_msg = f"Error during model load ({self.model_name}): {str(e)}"
            print(error_msg) # Also print to console for debugging
            self.signals.finished.emit((False, error_msg))
            # Or: self.signals.error.emit(error_msg) if we want separate error signal handling 