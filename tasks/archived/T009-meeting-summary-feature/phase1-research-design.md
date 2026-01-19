# Phase 1: Research & Design - Meeting Summary Feature

## Research Findings

### 1. Faster-Whisper Timestamp Capabilities

Based on research of the faster-whisper library:

- **Segment-level timestamps**: Each segment has `.start` and `.end` attributes (in seconds)
- **Word-level timestamps**: Available when `word_timestamps=True` is passed to transcribe()
- **VAD (Voice Activity Detection)**: Already enabled in our implementation, helps segment speech
- **Segment structure**: Each segment typically represents a sentence or phrase

### 2. Current Implementation Analysis

Our `TranscriptionService` currently:
- Returns only the concatenated text without timestamp information
- Uses VAD for better segmentation
- Has progress callbacks but doesn't expose segment data

### 3. UI Capabilities

Current upload functionality:
- Single file selection via `QFileDialog.getOpenFileName()`
- PySide6 supports multi-file selection via `QFileDialog.getOpenFileNames()`
- Current UI shows single file processing

## Design Decisions

### 1. Multi-File Upload UI Design

```
┌─────────────────────────────────────┐
│ Whisper Transcription UI            │
├─────────────────────────────────────┤
│ [Model: base ▼]              [Min]  │
├─────────────────────────────────────┤
│         ░░░░░░░░░░░░░░░░            │
│         ░ Waveform Area ░           │
│         ░░░░░░░░░░░░░░░░            │
├─────────────────────────────────────┤
│ [Rec] [Stop] [Pause] [Cancel]       │
│ [Transcribe] [Fabric] [Upload]      │
│ [Meeting]  <- NEW BUTTON            │
├─────────────────────────────────────┤
│ Status: Ready                       │
├─────────────────────────────────────┤
│ Selected files for meeting:         │
│ • Blake_Sims_audio.m4a              │
│ • Michael_Chan_audio.m4a            │
├─────────────────────────────────────┤
│ Transcribed text will appear here...│
│                                     │
└─────────────────────────────────────┘
```

### 2. Data Structures

```python
# Segment with timestamp and speaker
@dataclass
class TranscriptSegment:
    speaker: str
    text: str
    start_time: float  # seconds
    end_time: float
    confidence: float = 1.0

# Meeting transcript container
@dataclass
class MeetingTranscript:
    date: datetime
    participants: List[str]
    segments: List[TranscriptSegment]
    audio_files: Dict[str, str]  # speaker -> file path
    duration: float
    
    def to_markdown(self) -> str:
        """Export to markdown format"""
        pass
    
    def to_json(self) -> dict:
        """Export to JSON format"""
        pass
```

### 3. Speaker Name Extraction

From filename patterns:
- Zoom: `audio{Name}{ID}.m4a` -> extract via regex
- Generic: Use filename without extension as speaker name
- Allow manual override in UI

```python
def extract_speaker_name(filename: str) -> str:
    """Extract speaker name from audio filename."""
    # Zoom pattern: audioBlakeSims21667483884.m4a
    zoom_pattern = r'audio([A-Za-z]+)(\d+)\.(m4a|mp3|wav)'
    match = re.match(zoom_pattern, os.path.basename(filename))
    
    if match:
        name = match.group(1)
        # Add spaces before capital letters: BlakeSims -> Blake Sims
        return re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    
    # Fallback: use filename without extension
    return Path(filename).stem
```

### 4. Transcript Merging Algorithm

```python
def merge_transcripts(transcripts: Dict[str, List[TranscriptSegment]]) -> List[TranscriptSegment]:
    """Merge multiple speaker transcripts by timestamp."""
    # 1. Combine all segments
    all_segments = []
    for speaker, segments in transcripts.items():
        all_segments.extend(segments)
    
    # 2. Sort by start time
    all_segments.sort(key=lambda s: s.start_time)
    
    # 3. Handle overlaps (optional: merge or mark as simultaneous)
    merged = []
    for segment in all_segments:
        if merged and segment.start_time < merged[-1].end_time:
            # Overlapping speech - could merge or mark specially
            overlap_duration = merged[-1].end_time - segment.start_time
            if overlap_duration > 0.5:  # Significant overlap
                # Mark as simultaneous speech
                segment.text = f"[Simultaneous] {segment.text}"
        merged.append(segment)
    
    return merged
```

### 5. Output Format Specification

**Markdown Format** (Primary):
```markdown
# Meeting Transcript
Date: 2025-05-29 11:14:48
Participants: Blake Sims, Michael Chan
Duration: 45:32

## Audio Files
- Blake Sims: audioBlakeSims21667483884.m4a
- Michael Chan: audioMichaelChan11667483884.m4a

## Transcript

[00:00:05] **Blake Sims**: Hello Michael, can you hear me okay?

[00:00:08] **Michael Chan**: Yes, I can hear you clearly. How's everything going?

[00:00:12] **Blake Sims**: Great! Let's discuss the new feature implementation...

## Summary Statistics
- Total Duration: 45:32
- Blake Sims: 23:15 (51%)
- Michael Chan: 22:17 (49%)
- Overlapping speech: 2:34 (5.6%)
```

**JSON Format** (For programmatic use):
```json
{
  "meeting": {
    "date": "2025-05-29T11:14:48",
    "participants": ["Blake Sims", "Michael Chan"],
    "duration_seconds": 2732,
    "audio_files": {
      "Blake Sims": "audioBlakeSims21667483884.m4a",
      "Michael Chan": "audioMichaelChan11667483884.m4a"
    }
  },
  "segments": [
    {
      "speaker": "Blake Sims",
      "text": "Hello Michael, can you hear me okay?",
      "start_time": 5.0,
      "end_time": 7.5,
      "confidence": 0.98
    }
  ],
  "statistics": {
    "speaker_time": {
      "Blake Sims": {"seconds": 1395, "percentage": 51},
      "Michael Chan": {"seconds": 1337, "percentage": 49}
    },
    "overlap_duration": 154
  }
}
```

## Implementation Plan Summary

1. **Phase 2**: Add "Meeting" button and multi-file selection UI
2. **Phase 3**: Extend TranscriptionService to return timestamped segments
3. **Phase 4**: Implement merging algorithm and speaker identification
4. **Phase 5**: Add export options and polish the feature

## Next Steps

Proceed to Phase 2: UI Implementation for Multi-File Upload