# Meeting Summary Feature

## Description
Extend the recent "Upload" feature to support a "Meeting" summary capability. 

## Key Requirements
- Allow uploading multiple audio files (typically 2 - one for each meeting participant)
- Example: Zoom meeting recordings with separate audio tracks for each participant
  - e.g., `audioBlakeSims21667483884.m4a` and `audioMichaelChan11667483884.m4a`
- Use Whisper's timestamp capability to create a unified transcription
- Splice audio transcriptions together programmatically 
- Include speaker identification in the final transcript
- Maintain chronological order based on timestamps

## Technical Approach
- Leverage existing upload functionality
- Process multiple audio files with timestamp information
- Merge transcriptions based on timestamp alignment
- Output a single transcript with speaker labels

## Use Case
After a Zoom meeting, users often have separate audio recordings for each participant saved in their Zoom folders. This feature would allow them to upload both files and get a unified, speaker-labeled transcript.