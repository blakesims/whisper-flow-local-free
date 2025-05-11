# Task: UI Implementation

## Task ID
T002

## Overview
Develop the user interface components for the Whisper Transcription App, focusing on the recording interface, waveform visualization, and control elements. This task involves creating a clean, minimal UI that provides clear visual feedback during recording and processing.

## Objectives
- Implement the main window with proper positioning and styling
- Create live waveform visualization for audio input
- Develop control buttons with keyboard shortcut support
- Implement status indicators for recording/processing states
- Ensure the UI remains responsive during all operations

## Dependencies
- T001

## Rules Required
- task-documentation

## Resources & References
- Project specification: `tasks/init-Project-Spec.md`
- PySide6 documentation: https://doc.qt.io/qtforpython-6/
- Tokyo Night color palette references
- Qt Signals and Slots documentation for threading

## Phases Breakdown

### Phase 1: Main Window Implementation
**Status**: Completed

**Objectives**:
- Create frameless, always-on-top main window
- Implement draggable behavior for window repositioning
- Apply Tokyo Night or pastel color palette styling
- Ensure proper window layering and focus behavior
- Add minimize/close functionality

**Estimated Time**: 2 days

**Resources Needed**:
- PySide6 documentation for window management
- Qt stylesheet examples

**Dependencies**:
- T001 completion

**Updates & Progress**:
- Initial frameless, always-on-top window with drag functionality confirmed (was pre-existing).
- Applied a base background color (#1a1b26) and label text color (#c0caf5) as a first step towards Tokyo Night styling.
- Refined styling: added a subtle border (#24283b) to the main window and made label style more specific (transparent background, no border).
- Added functionality to close the window using the Escape key.
- Added a basic minimize button with initial styling and functionality.
- Core functionalities for the main window are in place. Advanced styling refinements and specific focus/layering tests can be revisited if issues arise or further enhancements are desired.

### Phase 2: Waveform Visualization Development
**Status**: Completed

**Objectives**:
- Implement real-time audio waveform visualization component
- Create amplitude calculation from audio input
- Develop color changes based on recording status
- Ensure proper scaling and responsiveness
- Optimize performance for continuous display

**Estimated Time**: 3 days

**Resources Needed**:
- sounddevice documentation for audio capture
- Qt graphics/drawing documentation
- Examples of audio visualization implementations

**Dependencies**:
- Phase 1 completion

**Updates & Progress**:
- Began planning for the waveform visualization component.
- Initial considerations: will likely require a custom QWidget, a paintEvent for drawing, and a way to receive audio amplitude data.
- Created `app/ui/waveform_widget.py` with a `WaveformWidget` class.
  - Implemented basic `paintEvent` to draw a waveform from sample data.
  - Added `update_waveform_data` method and test data generation.
  - Included a standalone test block (`if __name__ == '__main__':`).
- Integrated `WaveformWidget` into `MainWindow` in `app/ui/main_window.py`, replacing the placeholder label.
- Refactored `WaveformWidget` (`app/ui/waveform_widget.py`):
  - Renamed `update_waveform` to `update_waveform_data` and modified it to accept and process raw audio chunks (calculating display amplitudes by segmenting and taking max absolute values).
  - Renamed `generate_sample_data` to `generate_sample_raw_audio` to produce more realistic test data.
  - Adjusted `paintEvent` to use the new display amplitudes.
  - Updated standalone test timer for smoother preview.
- Added a `QTimer` to `MainWindow` (`app/ui/main_window.py`) to periodically generate sample raw audio data and call `WaveformWidget.update_waveform_data()`, simulating live audio input for testing purposes.
- Implemented status-based color changes in `WaveformWidget`:
  - Added `WaveformStatus` class (IDLE, RECORDING).
  - `WaveformWidget` now has a `set_status` method to change waveform color.
  - `paintEvent` uses the status-dependent color.
  - Updated test blocks in both `WaveformWidget` and `MainWindow` to cycle and demonstrate these status color changes.
- Core functionality for waveform visualization and status display is in place, ready for real audio data and further refinement on scaling/performance as needed.

### Phase 3: Control Elements Implementation
**Status**: Completed

**Objectives**:
- Create minimal control buttons (record, stop, pause, cancel, transcribe, fabric)
- Implement keyboard shortcut handling for all controls
- Develop status indicators for application state
- Design and implement tooltip/hint system
- Create smooth transition effects between states

**Estimated Time**: 2 days

**Resources Needed**:
- Qt documentation for input handling
- UI/UX design patterns for minimal interfaces

**Dependencies**:
- Phase 2 completion

**Updates & Progress**:
- Began planning for control elements.
- Added control buttons (Rec, Stop, Pause, Cancel) to `MainWindow` using `QHBoxLayout`.
- Connected buttons to placeholder click handler methods (`_on_rec_clicked`, etc.).
- Created a common styling method `_apply_button_styles` and applied initial Tokyo Night theme styles to the new buttons and the existing minimize button.
- Implemented application state management (`AppState`) in `MainWindow`.
  - Button click handlers now call `_change_app_state`.
  - A new `_update_ui_for_state` method manages UI changes based on the current application state (e.g., enabling/disabling buttons, changing button text, setting `WaveformWidget` status).
  - Test data timer in `MainWindow` is now stopped upon user interaction with control buttons.
- Implemented keyboard shortcuts in `MainWindow` (using `QShortcut` for most) for main control actions (R for Rec/Resume, S for Stop, P for Pause, C for Cancel, M for Minimize, Escape for Close).
- Added tooltips to control buttons (Rec, Stop, Pause, Cancel) and the Minimize button, indicating their function and shortcuts.
- State transitions are currently immediate (color changes, button enable/disable). Smooth animated transitions are considered a potential future refinement if deemed necessary for UX, but not implemented in this phase for core functionality.
- Added "Transcribe" (T) and "Fabric" (F) buttons and corresponding `QShortcut`s. These actions currently stop an active recording (saving it) and then transition to placeholder states.
- Corrected `_on_cancel_clicked` to no longer pass an unexpected argument to `audio_recorder.stop_recording()`.
- Core control elements, state management, keyboard shortcuts, and tooltips are implemented.

### Phase 4: Integration and Usability Testing
**Status**: In Progress

**Objectives**:
- Integrate all UI components into a cohesive interface
- Test UI responsiveness during various operations
- Implement error visualization for user feedback
- Refine keyboard navigation and shortcuts
- Conduct basic usability testing
- Prepare for and integrate with T004 (Transcription) and T005 (Fabric) services.

**Estimated Time**: 2 days

**Resources Needed**:
- Test plan for UI functionality
- Reference usability heuristics
- T004 and T005 interface specifications (when available)

**Dependencies**:
- Phase 3 completion
- T003 (Audio Recording) for ongoing testing
- T004, T005 (for full integration testing of Transcribe/Fabric flows)

**Updates & Progress**:
- Core UI components (main window, waveform display, control buttons, state management) are implemented.
- This phase will now focus on:
  - Ensuring smooth integration as dependent services (like Audio Recording T003) become available.
  - Implementing basic error visualization mechanisms.
  - Conducting usability reviews and refining keyboard navigation/shortcuts as needed.
  - Testing UI responsiveness, especially once real audio data processing is integrated.
- Further work on this phase is pending the progress of T003 (Audio Recording Implementation) for full end-to-end testing of UI interactions with live audio.
- **Integrated `AudioRecorder` (from T003) into `MainWindow`:**
  - Imported and instantiated `AudioRecorder` in `app/ui/main_window.py`.
  - Removed the previous test timer and associated logic for simulating waveform data.
  - Connected `AudioRecorder` signals (`new_audio_chunk_signal`, `recording_started_signal`, `recording_stopped_signal`, `recording_paused_signal`, `recording_resumed_signal`, `error_signal`) to new handler slots in `MainWindow`.
  - These handler slots now update the application state (`app_state`) and UI (via `_update_ui_for_state`) based on actual events from the `AudioRecorder`.
  - UI control button click handlers (`_on_rec_clicked`, etc.) now call corresponding methods on the `audio_recorder` instance (e.g., `start_recording()`, `stop_recording()`).
  - Added a `closeEvent` to `MainWindow` to attempt to stop the `audio_recorder` and clean up its thread upon application exit.
  - Basic error messages from `AudioRecorder` are printed to the console; UI display of errors is a next step.
- Added a `QLabel` (`status_label`) to `MainWindow` for displaying status and error messages.
  - Implemented `_set_status_message(message, is_error)` to update the label's text and color (errors in red, normal status in default text color).
  - Non-error status messages automatically clear after a 5-second delay.
  - `_handle_audio_error` and `_handle_recording_stopped` now use this label to provide feedback.
  - User action initiating methods (e.g., `_on_rec_clicked`) now clear the status label.
- **New Application States & Workflow for Cancel/Transcribe/Fabric:**
  - `AppState` in `app/ui/main_window.py` now includes:
    - `CANCELLING`: Used when the cancel action is triggered.
    - `STOPPING_FOR_ACTION`: A general intermediate state when stopping a recording before a post-processing action (like Transcribe or Fabric).
    - `TRANSCRIBING`: State for when transcription is supposed to occur.
    - `FABRIC_PROCESSING`: State for when Fabric processing is supposed to occur.
  - **Cancel Workflow (`_on_cancel_clicked`, `_handle_recording_stopped`):**
    - Clicking Cancel or pressing 'C' sets state to `AppState.CANCELLING`.
    - `audio_recorder.stop_recording()` is called.
    - In `_handle_recording_stopped`, if state is `CANCELLING` and the `message_or_path` received from `audio_recorder` is a valid file path, `os.remove()` is used to delete the recorded audio file. The UI then transitions to `IDLE`.
  - **Transcribe/Fabric Workflow (`_on_transcribe_keypress`, `_on_fabric_keypress`, `_handle_recording_stopped`):**
    - Pressing 'T'/'F' or clicking respective buttons, if recording/paused, sets state to `AppState.STOPPING_FOR_ACTION`, sets `self.pending_action` to `AppState.TRANSCRIBING` or `AppState.FABRIC_PROCESSING`, and calls `audio_recorder.stop_recording()`.
    - If IDLE and `self.last_saved_audio_path` exists, it directly transitions to `TRANSCRIBING` or `FABRIC_PROCESSING`.
    - In `_handle_recording_stopped`, if the state was `STOPPING_FOR_ACTION` and recording was saved successfully (path received), `self.last_saved_audio_path` is updated. The application then transitions to the state stored in `self.pending_action` (i.e., `TRANSCRIBING` or `FABRIC_PROCESSING`).
    - Currently, the `TRANSCRIBING` and `FABRIC_PROCESSING` states in `_update_ui_for_state` use a `QTimer.singleShot` to simulate work and then call `_post_action_cleanup` to return to `IDLE`. **These are the primary integration points for T004 and T005.**
  - `self.last_saved_audio_path` in `MainWindow` stores the file path of the most recently saved audio, intended for use by transcription or Fabric processing.

## Notes & Updates 
- **Key Integration Points for T004 (Transcription) & T005 (Fabric):**
  - **`AppState.TRANSCRIBING` / `AppState.FABRIC_PROCESSING`:** The `MainWindow` transitions to these states after a recording is successfully stopped via the 'T' or 'F' actions (or corresponding buttons). The UI will display a relevant status message.
  - **`MainWindow.last_saved_audio_path`:** This attribute will hold the string path to the temporarily saved WAV file that needs to be transcribed or processed.
  - **`MainWindow._update_ui_for_state()`:** The sections for `AppState.TRANSCRIBING` and `AppState.FABRIC_PROCESSING` currently contain `QTimer.singleShot(...)` calls for simulation. These should be replaced with the actual calls to the transcription/Fabric services. The service should ideally run asynchronously. Upon completion (success or failure), `_post_action_cleanup(success_bool, message_str)` should be called to update the UI and return to `IDLE`.
  - **Error Handling:** If the transcription/Fabric service reports an error, `_post_action_cleanup(False, "Error message from service")` should be used.
  - **File Management:** Decide if `last_saved_audio_path` should be deleted after successful transcription/processing or if it's kept (currently, `_post_action_cleanup` keeps it). This might become a user setting.
- The `cancel` functionality ensures that if a user cancels a recording, the audio data is discarded.
- The UI now has dedicated "Transcribe" and "Fabric" buttons in addition to the 'T' and 'F' keyboard shortcuts. 