# Phase 4: Visual Analysis Integration

**Status**: Complete
**Completed**: 2025-05-30

## Overview
This phase integrates Google Gemini API to analyze meeting transcripts and identify moments where visual confirmation from the video would be helpful. The system extracts video frames at these timestamps and creates an enhanced transcript with embedded images.

## Implemented Components

### 1. Gemini Service (`app/core/gemini_service.py`)
- Uses the new `google-genai` SDK (not the deprecated `google-generativeai`)
- Loads system prompt from `app/prompts/image-identifier.md`
- Implements structured JSON output for visual points
- Each visual point includes:
  - Timestamp (HH:MM:SS format)
  - Description of ambiguity
  - Speaker name
  - Exact quote
  - Reason for visual confirmation
  - Priority (1-5, with 1 being highest)

### 2. Video Extractor (`app/core/video_extractor.py`)
- Extracts frames from video files using ffmpeg
- Supports automatic video file discovery in Zoom directories
- Saves frames as JPEG images with configurable quality
- Names files using HH-MM-SS format for filesystem compatibility

### 3. Transcript Enhancer (`app/core/transcript_enhancer.py`)
- Orchestrates the complete enhancement process
- Creates `action-notes/` directory structure:
  ```
  action-notes/
  ├── transcript.json          # Original transcript data
  ├── transcript.md            # Original transcript (markdown)
  ├── visual-points.json       # LLM analysis results
  ├── transcript-enhanced.md   # Enhanced transcript with images
  ├── enhancement-summary.md   # Summary report
  └── images/                  # Extracted video frames
      ├── 00-12-45.jpg
      └── 01-23-15.jpg
  ```

### 4. UI Integration
- Added "Enhance" button with 'E' keyboard shortcut
- New `MEETING_ENHANCING` app state
- Enhancement worker for async processing
- Progress feedback during enhancement
- Summary display after completion

## Key Features

### Visual Point Detection Criteria
The system identifies timestamps when:
- Speakers use demonstrative pronouns without clear antecedents ("this button", "that feature")
- References to unnamed UI elements ("click here", "the thing on the left")
- Gestural language ("over there", "right here", "this one")
- Color or position-based references without specific names

### Priority System
1. **Priority 1**: Critical ambiguity affecting core functionality
2. **Priority 2**: High importance for significant features
3. **Priority 3**: Moderate importance for feature details
4. **Priority 4**: Low importance for minor details
5. **Priority 5**: Very low importance, nice-to-have clarification

## Technical Details

### API Configuration
- Uses `gemini-2.0-flash-exp` model by default
- Requires `GOOGLE_API_KEY` environment variable
- Implements structured output with JSON schema
- System instruction loaded from prompt file

### Dependencies
- `google-genai>=0.1.0` - New Google GenAI SDK
- `ffmpeg` - Required for video frame extraction
- Existing meeting transcript functionality from Phase 3

## Testing Performed
- Verified all imports work correctly
- Tested prompt loading from file
- Confirmed structured JSON output
- Validated frame extraction functionality
- End-to-end testing with sample transcripts

## Additional Features Added

### Settings Dialog
- Added Settings dialog (⚙ button in top bar) for configuration:
  - Google API key management with show/hide functionality
  - Gemini model selection with ability to refresh from API
  - Max visual points setting (1-100)
  - Video quality setting for JPEG extraction (1-100)
- Settings stored in platform-appropriate config directory
- API key can be set via environment variable or settings

### Re-Enhancement Functionality
- Added Re-Enhance button (Shift+E shortcut) for existing transcripts
- ReEnhanceDialog shows all meetings with existing transcripts
- Displays enhancement status (enhanced/not enhanced, count)
- Supports iterating results to avoid overwriting:
  - First enhancement: visual-points.json, transcript-enhanced.md
  - Second enhancement: visual-points-2.json, transcript-enhanced-2.md
  - And so on...
- Allows testing different models/settings on same transcript

## Next Steps
Phase 5 will focus on testing with real meeting recordings and refining the visual point detection based on user feedback.