# Task: Meeting Summary Feature

## Task ID
T009

## Overview
Extend the existing upload functionality to support multi-file uploads for meeting summaries. This feature will allow users to upload multiple audio files (typically from Zoom meetings with separate tracks per participant) and generate a unified, speaker-labeled transcript using Whisper's timestamp capabilities.

## Objectives
- Enable multi-file audio upload in the UI (2+ files simultaneously)
- Extract timestamps from Whisper transcriptions for each audio file
- Implement transcript merging algorithm based on timestamp alignment
- Add speaker identification to merged transcripts
- Provide a cohesive meeting summary output with speaker labels

## Dependencies
- T002#P3 (UI Implementation - specifically the upload feature)
- T004 (Transcription Engine Integration - for Whisper functionality)

## Rules Required
- task-documentation
- code-conventions
- project-architecture

## Resources & References
- Existing upload functionality: `app/ui/main_window.py:_on_upload_clicked()`
- Whisper transcription service: `app/core/transcription_service.py`
- faster-whisper documentation for timestamp extraction
- Example Zoom audio files: `~/Documents/Zoom/*/Audio Record/`

## Phases Breakdown

### Phase 1: Research & Design
**Status**: Complete

**Objectives**:
- Research faster-whisper's timestamp extraction capabilities
- Design UI changes for multi-file selection
- Plan transcript merging algorithm
- Define output format for speaker-labeled transcripts

**Estimated Time**: 2 days

**Resources Needed**:
- faster-whisper documentation
- UI/UX mockups for multi-file upload
- Sample Zoom meeting recordings for testing

**Dependencies**:
- None

### Phase 2: UI Implementation for Multi-File Upload
**Status**: Complete

**Objectives**:
- Modify upload dialog to accept multiple files
- Update UI to show multiple files being processed
- Add progress indication for each file
- Implement new "Meeting Summary" button/mode

**Estimated Time**: 3 days

**Resources Needed**:
- PySide6 QFileDialog documentation
- Access to main_window.py
- UI design guidelines

**Dependencies**:
- Phase 1 completion
- T002#P3 (existing upload feature)

### Phase 3: Timestamp-Based Transcription
**Status**: Complete

**Objectives**:
- Modify transcription service to return segment-level timestamps
- Create data structure to store timestamped segments
- Implement parallel transcription for multiple files
- Handle different audio formats and sample rates

**Estimated Time**: 3 days

**Resources Needed**:
- faster-whisper API documentation
- Audio processing libraries
- Test audio files with various formats

**Dependencies**:
- Phase 1 completion
- T004 (transcription engine)

### Phase 4: Visual Analysis Integration
**Status**: Complete

**Objectives**:
- ✓ Integrate Google Gemini for LLM analysis
- ✓ Identify points requiring visual confirmation
- ✓ Extract video frames at specific timestamps
- ✓ Create enhanced transcript with embedded images
- ✓ Generate action-notes directory structure

**Estimated Time**: 4 days

**Resources Needed**:
- Google Gemini API key
- ffmpeg for video frame extraction
- Structured output documentation

**Dependencies**:
- Phase 3 completion

**Implementation Details**:
- Created `gemini_service.py` for LLM integration with structured output
- Created `video_extractor.py` for frame extraction using ffmpeg
- Created `transcript_enhancer.py` to orchestrate the enhancement process
- Added "Enhance" button and shortcut (E) to UI
- Outputs to `~/Documents/Zoom/[Meeting]/action-notes/` directory

### Phase 5: Transcript Sectioning for Long Meetings
**Status**: Not Started

**Objectives**:
- Implement configurable line length threshold in settings
- Create new Google Gemini prompt for intelligent transcript sectioning
- Design JSON structure for sectioned transcripts
- Implement parallel processing of sections for visual analysis
- Integrate sectioning into the enhancement workflow

**Estimated Time**: 3 days

**Resources Needed**:
- New prompt file: `app/prompts/transcript-sectioner.md`
- Google Gemini API with structured output
- Settings dialog extension

**Dependencies**:
- Phase 4 completion

### Phase 6: Parallel Visual Analysis for Sections
**Status**: Not Started

**Objectives**:
- Modify visual analysis to work with transcript sections
- Implement parallel API calls for each section
- Merge visual points from all sections
- Update enhanced transcript generation for sectioned format
- Handle section boundaries in frame extraction

**Estimated Time**: 2 days

**Resources Needed**:
- Threading/async utilities for parallel processing
- Section merging algorithm
- Progress tracking for multiple sections

**Dependencies**:
- Phase 5 completion

### Phase 7: Testing & Refinement
**Status**: Not Started

**Objectives**:
- Test with various meeting recordings
- Handle edge cases (silence, overlapping speech, audio sync issues)
- Test sectioning with very long meetings (2+ hours)
- Optimize performance for long meetings
- Add user preferences for output formatting
- Implement error handling and user feedback

**Estimated Time**: 3 days

**Resources Needed**:
- Diverse test audio samples
- Long meeting recordings for section testing
- User feedback mechanism
- Performance profiling tools

**Dependencies**:
- Phase 6 completion

## Notes & Updates
- 2025-05-30: Task created based on user request for meeting summary functionality
- Key consideration: Need to extract participant names from filenames (e.g., "audioBlakeSims21667483884.m4a")
- 2025-05-30: Phase 4 completed - Added visual analysis feature using Google Gemini API
  - Integrated structured output for identifying ambiguous references
  - Added video frame extraction at specified timestamps
  - Created enhanced transcript with embedded images
  - Output structure: action-notes/transcript.json, visual-points.json, transcript-enhanced.md, images/
- 2025-05-31: Added Phase 5 & 6 for transcript sectioning
  - Phase 5: Implement intelligent sectioning for long transcripts
  - Phase 6: Parallel processing of sections for improved performance
  - Will add configurable line threshold in settings
  - Sections will be processed in parallel for visual analysis