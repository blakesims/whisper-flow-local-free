"""
Service for sectioning long meeting transcripts into logical parts.
"""

import os
import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig


@dataclass
class TranscriptSection:
    """Represents a logical section of a meeting transcript."""
    section_id: int
    title: str
    description: str
    start_segment_index: int
    end_segment_index: int
    start_time: float
    end_time: float
    start_timestamp: str
    end_timestamp: str
    participants: List[str]
    key_topics: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "section_id": self.section_id,
            "title": self.title,
            "description": self.description,
            "start_segment_index": self.start_segment_index,
            "end_segment_index": self.end_segment_index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "participants": self.participants,
            "key_topics": self.key_topics
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TranscriptSection':
        """Create from dictionary."""
        return cls(**data)


class TranscriptSectioner:
    """Service for sectioning meeting transcripts using Google Gemini."""
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize transcript sectioner.
        
        Args:
            api_key: Google API key. If None, will look for GOOGLE_API_KEY env var
            model_name: Gemini model to use (default: gemini-2.0-flash-exp)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided. Set GOOGLE_API_KEY environment variable or pass api_key parameter.")
        
        # Initialize client
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model_name
        
        # Load system prompt from file
        self.system_instruction = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """Load the system prompt from the prompts directory."""
        # Find the prompt file relative to this module
        module_path = Path(__file__).parent.parent  # app directory
        prompt_path = module_path / "prompts" / "separator.md"
        
        if not prompt_path.exists():
            # Fallback to a basic prompt if file not found
            return """You are an expert meeting analysis assistant that sections long transcripts into logical parts.
            Analyze transcripts and group segments into coherent sections based on topic changes, agenda items, or natural breaks.
            Return your analysis as a JSON object with sections array and metadata."""
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Remove the "# INPUT:" line if present
            lines = content.split('\n')
            # Filter out the "# INPUT:" line
            filtered_lines = [line for line in lines if not line.strip().startswith("# INPUT:")]
            return '\n'.join(filtered_lines).strip()
    
    def section_transcript(
        self,
        transcript_json: dict,
        max_section_duration: Optional[float] = None,
        progress_callback: Optional[callable] = None
    ) -> Tuple[List[TranscriptSection], dict]:
        """
        Section a meeting transcript into logical parts.
        
        Args:
            transcript_json: Meeting transcript in JSON format (from MeetingTranscript.to_json())
            max_section_duration: Optional maximum duration per section in seconds
            progress_callback: Optional callback function for progress updates
        
        Returns:
            Tuple of (list of TranscriptSection objects, metadata dict)
        """
        # Prepare the transcript text with segment information
        if progress_callback:
            progress_callback("Formatting transcript for sectioning analysis...")
        
        transcript_text = self._format_transcript_for_sectioning(transcript_json)
        
        # Calculate approximate token count
        approx_tokens = len(transcript_text) // 4
        print(f"Transcript for sectioning: {len(transcript_text)} chars, ~{approx_tokens} tokens")
        
        # Build the user prompt
        user_prompt = transcript_text
        
        if max_section_duration:
            minutes = int(max_section_duration // 60)
            user_prompt = f"Maximum section duration: {minutes} minutes\n\n{user_prompt}"
        
        try:
            if progress_callback:
                progress_callback("Creating sectioning request...")
            
            # Create the generation config for JSON output
            config = GenerateContentConfig(
                temperature=0.3,  # Lower temperature for consistent sectioning
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "section_id": {"type": "integer"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "start_segment_index": {"type": "integer"},
                                    "end_segment_index": {"type": "integer"},
                                    "start_time": {"type": "number"},
                                    "end_time": {"type": "number"},
                                    "start_timestamp": {"type": "string"},
                                    "end_timestamp": {"type": "string"},
                                    "participants": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    },
                                    "key_topics": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": [
                                    "section_id", "title", "description",
                                    "start_segment_index", "end_segment_index",
                                    "start_time", "end_time",
                                    "start_timestamp", "end_timestamp",
                                    "participants", "key_topics"
                                ]
                            }
                        },
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "total_sections": {"type": "integer"},
                                "sectioning_strategy": {"type": "string"}
                            },
                            "required": ["total_sections", "sectioning_strategy"]
                        }
                    },
                    "required": ["sections", "metadata"]
                },
                system_instruction=self.system_instruction
            )
            
            if progress_callback:
                progress_callback("Sending sectioning request to Gemini API...")
            
            # Generate response with streaming for progress
            import time
            start_time = time.time()
            
            try:
                # Use streaming for better progress feedback
                stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=user_prompt,
                    config=config
                )
                
                # Collect all chunks
                full_response = ""
                chunk_count = 0
                last_progress_time = time.time()
                
                for chunk in stream:
                    if hasattr(chunk, 'text') and chunk.text:
                        full_response += chunk.text
                        chunk_count += 1
                        
                        # Update progress every 2 seconds
                        current_time = time.time()
                        if current_time - last_progress_time > 2.0 and progress_callback:
                            elapsed = current_time - start_time
                            progress_callback(f"Receiving sectioning response... ({elapsed:.0f}s, {chunk_count} chunks)")
                            last_progress_time = current_time
                
                elapsed_time = time.time() - start_time
                print(f"Sectioning API response received in {elapsed_time:.1f} seconds ({chunk_count} chunks)")
                
            except Exception as api_error:
                elapsed_time = time.time() - start_time
                error_msg = f"Sectioning API error after {elapsed_time:.1f} seconds: {str(api_error)}"
                print(error_msg)
                raise Exception(f"Sectioning API Error: {str(api_error)}")
            
            if progress_callback:
                progress_callback("Parsing sectioning response...")
            
            # Parse the JSON response
            try:
                result = json.loads(full_response)
            except json.JSONDecodeError as e:
                print(f"Failed to parse sectioning JSON response: {full_response[:500]}...")
                raise Exception(f"Invalid JSON response from sectioning API: {str(e)}")
            
            # Validate response structure
            if not isinstance(result, dict) or "sections" not in result or "metadata" not in result:
                raise Exception("Invalid response structure: missing sections or metadata")
            
            sections_data = result["sections"]
            metadata = result["metadata"]
            
            if progress_callback:
                progress_callback(f"Processing {len(sections_data)} sections...")
            
            # Convert to TranscriptSection objects
            sections = []
            for section_data in sections_data:
                try:
                    section = TranscriptSection.from_dict(section_data)
                    sections.append(section)
                except Exception as e:
                    print(f"Error processing section {section_data.get('section_id', '?')}: {e}")
                    raise
            
            # Sort sections by section_id to ensure proper order
            sections.sort(key=lambda s: s.section_id)
            
            # Validate section continuity
            self._validate_section_continuity(sections, transcript_json)
            
            return sections, metadata
            
        except Exception as e:
            print(f"Error sectioning transcript: {e}")
            raise
    
    def _format_transcript_for_sectioning(self, transcript_json: dict) -> str:
        """Format transcript JSON for sectioning analysis."""
        lines = []
        
        # Add meeting metadata
        meeting_info = transcript_json.get("meeting", {})
        lines.append(f"Meeting Date: {meeting_info.get('date', 'Unknown')}")
        lines.append(f"Participants: {', '.join(meeting_info.get('participants', []))}")
        lines.append(f"Duration: {self._format_duration(meeting_info.get('duration_seconds', 0))}")
        lines.append("\n--- TRANSCRIPT SEGMENTS ---\n")
        
        # Add transcript segments with indices
        segments = transcript_json.get("segments", [])
        for i, segment in enumerate(segments):
            timestamp = self._seconds_to_timestamp(segment["start_time"])
            speaker = segment["speaker"]
            text = segment["text"]
            lines.append(f"[Segment {i}] [{timestamp}] {speaker}: {text}")
        
        lines.append(f"\nTotal segments: {len(segments)}")
        
        return "\n".join(lines)
    
    def _validate_section_continuity(self, sections: List[TranscriptSection], transcript_json: dict):
        """Validate that sections cover the entire transcript without gaps or overlaps."""
        segments = transcript_json.get("segments", [])
        if not segments:
            return
        
        # Check first section starts at 0
        if sections and sections[0].start_segment_index != 0:
            raise ValueError(f"First section doesn't start at segment 0 (starts at {sections[0].start_segment_index})")
        
        # Check last section ends at last segment
        if sections and sections[-1].end_segment_index != len(segments) - 1:
            raise ValueError(f"Last section doesn't end at last segment {len(segments) - 1} (ends at {sections[-1].end_segment_index})")
        
        # Check continuity between sections
        for i in range(1, len(sections)):
            prev_section = sections[i - 1]
            curr_section = sections[i]
            
            if curr_section.start_segment_index != prev_section.end_segment_index + 1:
                raise ValueError(
                    f"Gap or overlap between section {prev_section.section_id} "
                    f"(ends at {prev_section.end_segment_index}) and section {curr_section.section_id} "
                    f"(starts at {curr_section.start_segment_index})"
                )
    
    def _seconds_to_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def export_sections(self, sections: List[TranscriptSection], metadata: dict, output_path: str):
        """Export sections to JSON file."""
        output_data = {
            "sections": [section.to_dict() for section in sections],
            "metadata": metadata
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"Sections exported to: {output_path}")