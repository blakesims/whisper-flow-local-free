"""
Data structures and utilities for meeting transcripts with timestamps.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import json
import re


@dataclass
class TranscriptSegment:
    """A single segment of transcribed speech with timing information."""
    speaker: str
    text: str
    start_time: float  # seconds
    end_time: float    # seconds
    confidence: float = 1.0
    
    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end_time - self.start_time
    
    def overlaps_with(self, other: 'TranscriptSegment') -> bool:
        """Check if this segment overlaps with another."""
        return not (self.end_time <= other.start_time or self.start_time >= other.end_time)
    
    def format_timestamp(self, time_seconds: float) -> str:
        """Format timestamp as HH:MM:SS."""
        hours = int(time_seconds // 3600)
        minutes = int((time_seconds % 3600) // 60)
        seconds = int(time_seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def to_markdown_line(self) -> str:
        """Convert to markdown format line."""
        timestamp = self.format_timestamp(self.start_time)
        return f"[{timestamp}] **{self.speaker}**: {self.text}"


@dataclass
class MeetingTranscript:
    """Container for a complete meeting transcript."""
    date: datetime
    participants: List[str]
    segments: List[TranscriptSegment] = field(default_factory=list)
    audio_files: Dict[str, str] = field(default_factory=dict)  # speaker -> file path
    duration: float = 0.0
    
    def add_segment(self, segment: TranscriptSegment):
        """Add a segment and update duration."""
        self.segments.append(segment)
        if segment.end_time > self.duration:
            self.duration = segment.end_time
    
    def sort_segments(self):
        """Sort segments by start time."""
        self.segments.sort(key=lambda s: s.start_time)
    
    def get_speaker_stats(self) -> Dict[str, Dict[str, float]]:
        """Calculate speaking time statistics for each participant."""
        stats = {}
        for speaker in self.participants:
            speaker_segments = [s for s in self.segments if s.speaker == speaker]
            total_time = sum(s.duration for s in speaker_segments)
            percentage = (total_time / self.duration * 100) if self.duration > 0 else 0
            stats[speaker] = {
                'total_seconds': total_time,
                'percentage': percentage,
                'segment_count': len(speaker_segments)
            }
        return stats
    
    def find_overlaps(self) -> List[Tuple[TranscriptSegment, TranscriptSegment]]:
        """Find all overlapping segments."""
        overlaps = []
        for i in range(len(self.segments)):
            for j in range(i + 1, len(self.segments)):
                if self.segments[i].overlaps_with(self.segments[j]):
                    overlaps.append((self.segments[i], self.segments[j]))
        return overlaps
    
    def to_markdown(self) -> str:
        """Export to markdown format."""
        lines = []
        
        # Header
        lines.append("# Meeting Transcript")
        lines.append(f"Date: {self.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Participants: {', '.join(self.participants)}")
        lines.append(f"Duration: {self._format_duration(self.duration)}")
        lines.append("")
        
        # Audio files
        if self.audio_files:
            lines.append("## Audio Files")
            for speaker, path in self.audio_files.items():
                lines.append(f"- {speaker}: {path}")
            lines.append("")
        
        # Transcript
        lines.append("## Transcript")
        lines.append("")
        
        self.sort_segments()
        for segment in self.segments:
            lines.append(segment.to_markdown_line())
            lines.append("")
        
        # Statistics
        lines.append("## Summary Statistics")
        stats = self.get_speaker_stats()
        lines.append(f"- Total Duration: {self._format_duration(self.duration)}")
        
        for speaker, stat in stats.items():
            duration_str = self._format_duration(stat['total_seconds'])
            lines.append(f"- {speaker}: {duration_str} ({stat['percentage']:.1f}%)")
        
        # Overlap statistics
        overlaps = self.find_overlaps()
        if overlaps:
            overlap_time = sum(
                min(s1.end_time, s2.end_time) - max(s1.start_time, s2.start_time)
                for s1, s2 in overlaps
            )
            overlap_pct = (overlap_time / self.duration * 100) if self.duration > 0 else 0
            lines.append(f"- Overlapping speech: {self._format_duration(overlap_time)} ({overlap_pct:.1f}%)")
        
        return "\n".join(lines)
    
    def to_json(self) -> dict:
        """Export to JSON format."""
        return {
            "meeting": {
                "date": self.date.isoformat(),
                "participants": self.participants,
                "duration_seconds": self.duration,
                "audio_files": self.audio_files
            },
            "segments": [
                {
                    "speaker": s.speaker,
                    "text": s.text,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "confidence": s.confidence
                }
                for s in self.segments
            ],
            "statistics": self.get_speaker_stats()
        }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"


def extract_speaker_name(filename: str) -> str:
    """Extract speaker name from audio filename."""
    # Zoom pattern: audioNameNumbers.m4a
    zoom_pattern = r'audio([A-Za-z]+)(\d+)\.(m4a|mp3|wav)'
    match = re.match(zoom_pattern, filename)
    
    if match:
        name = match.group(1)
        # Add spaces before capital letters: BlakeSims -> Blake Sims
        return re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    
    # Fallback: use filename without extension
    import os
    return os.path.splitext(filename)[0]