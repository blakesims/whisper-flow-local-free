# Phase 5: Transcript Sectioning for Long Meetings

**Status**: Not Started
**Started**: TBD
**Completed**: TBD

## Overview
This phase introduces intelligent transcript sectioning to handle long meetings more effectively. When transcripts exceed a configurable line threshold, a new Google Gemini agent will analyze and split the transcript into logical sections based on topic changes, natural breaks, or time intervals.

## Design Specifications

### JSON Structure for Sectioned Transcripts

The sectioning agent should return a JSON structure like this:

```json
{
  "sections": [
    {
      "section_id": 1,
      "title": "Project Status Update",
      "description": "Discussion of current project milestones and blockers",
      "start_segment_index": 0,
      "end_segment_index": 45,
      "start_time": 0.0,
      "end_time": 542.3,
      "start_timestamp": "00:00:00",
      "end_timestamp": "00:09:02",
      "participants": ["Blake Sims", "John Doe"],
      "key_topics": ["milestone review", "Q3 targets", "resource allocation"]
    },
    {
      "section_id": 2,
      "title": "Technical Architecture Discussion",
      "description": "Deep dive into the new microservices architecture",
      "start_segment_index": 46,
      "end_segment_index": 120,
      "start_time": 542.3,
      "end_time": 1205.7,
      "start_timestamp": "00:09:02",
      "end_timestamp": "00:20:06",
      "participants": ["Blake Sims", "Jane Smith", "John Doe"],
      "key_topics": ["microservices", "API design", "database schema"]
    }
  ],
  "metadata": {
    "total_sections": 2,
    "total_duration": 1205.7,
    "sectioning_strategy": "topic_based",
    "average_section_duration": 602.85
  }
}
```

### Settings Configuration

Add to settings dialog:
- **Transcript Line Threshold**: Number of lines before triggering sectioning (default: 500)
- **Sectioning Strategy**: 
  - Topic-based (intelligent grouping by discussion topics)
  - Time-based (fixed duration sections)
  - Hybrid (topic-aware with max duration limits)
- **Max Section Duration**: For time-based/hybrid strategies (default: 15 minutes)

### Implementation Components

1. **New Prompt File**: `app/prompts/transcript-sectioner.md`
   - System instructions for intelligent section detection
   - Guidelines for identifying topic transitions
   - Instructions for generating descriptive titles and summaries

2. **New Service Class**: `app/core/transcript_sectioner.py`
   - `TranscriptSectioner` class
   - Method: `section_transcript(transcript_json, strategy, max_duration)`
   - Returns structured sections JSON

3. **Settings Dialog Updates**:
   - Add sectioning configuration group
   - Line threshold input
   - Strategy dropdown
   - Max duration input

4. **Enhancement Workflow Integration**:
   - Check transcript line count before visual analysis
   - If above threshold, call sectioning service
   - Store sections in `action-notes/transcript-sections.json`
   - Pass sections individually to visual analysis

## Workflow Changes

### Current Flow:
1. Load transcript
2. Send entire transcript to visual analysis
3. Extract frames
4. Generate enhanced transcript

### New Flow (for long transcripts):
1. Load transcript
2. Check line count against threshold
3. If above threshold:
   - Call sectioning service
   - Get structured sections
   - Save sections JSON
4. For each section:
   - Send section to visual analysis
   - Collect visual points
5. Merge all visual points
6. Extract frames for all points
7. Generate enhanced transcript with section headers

## Benefits

1. **Performance**: Smaller chunks process faster and more reliably
2. **Parallelization**: Sections can be analyzed concurrently
3. **Better Organization**: Long meetings become more navigable
4. **Reduced API Timeouts**: Smaller payloads less likely to timeout
5. **Cost Efficiency**: Can stop processing after key sections

## Testing Considerations

- Test with meetings of various lengths (30min, 1hr, 2hr+)
- Verify section boundaries don't split mid-sentence
- Ensure participant tracking across sections
- Test all three sectioning strategies
- Verify visual points maintain correct timestamps relative to full meeting

## Next Steps

1. Create the transcript-sectioner.md prompt
2. Implement TranscriptSectioner service
3. Update settings dialog
4. Modify enhancement workflow
5. Implement section merging logic
6. Update UI progress indicators for multi-section processing