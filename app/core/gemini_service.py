"""
Google Gemini API service for analyzing meeting transcripts.
"""

import os
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from google import genai
from google.genai.types import GenerateContentConfig, Tool, FunctionDeclaration, Schema


@dataclass
class VisualPoint:
    """Represents a point in the transcript that needs visual confirmation."""
    timestamp: str  # HH:MM:SS format
    timestamp_seconds: float
    description: str
    speaker: str
    quote: str
    reason: str
    priority: int = 3  # 1-5, with 1 being highest priority
    
    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "timestamp": self.timestamp,
            "timestamp_seconds": self.timestamp_seconds,
            "description": self.description,
            "speaker": self.speaker,
            "quote": self.quote,
            "reason": self.reason,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VisualPoint':
        """Create from dictionary."""
        return cls(**data)


class GeminiService:
    """Service for interacting with Google Gemini API."""
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize Gemini service.
        
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
        prompt_path = module_path / "prompts" / "image-identifier.md"
        
        if not prompt_path.exists():
            # Fallback to a basic prompt if file not found
            return """You are an expert meeting analysis assistant specialized in identifying ambiguous visual references in meeting transcripts.
            Analyze transcripts with timestamps and determine where video screengrabs are essential for clarity.
            Return your analysis as a JSON array with objects containing: timestamp, description, speaker, quote, reason, and priority (1-5)."""
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Remove the "# Input:" line if present
            lines = content.split('\n')
            # Filter out the "# Input:" line
            filtered_lines = [line for line in lines if line.strip() != "# Input:"]
            return '\n'.join(filtered_lines).strip()
    
    def analyze_transcript_for_visual_points(
        self,
        transcript_json: dict,
        custom_prompt: Optional[str] = None,
        max_points: Optional[int] = None
    ) -> List[VisualPoint]:
        """
        Analyze a meeting transcript to identify points needing visual confirmation.
        
        Args:
            transcript_json: Meeting transcript in JSON format (from MeetingTranscript.to_json())
            custom_prompt: Optional custom prompt to override default
            max_points: Optional maximum number of points to return
        
        Returns:
            List of VisualPoint objects
        """
        # Prepare the transcript text with timestamps
        transcript_text = self._format_transcript_for_analysis(transcript_json)
        
        # Use custom prompt or loaded system instruction
        system_prompt = custom_prompt or self.system_instruction
        
        # Build the user prompt
        user_prompt = f"Analyze this meeting transcript and identify points requiring visual confirmation:\n\n{transcript_text}"
        
        if max_points:
            user_prompt += f"\n\nPlease limit your response to the {max_points} most important points."
        
        try:
            # Create the generation config for JSON output with system instruction
            config = GenerateContentConfig(
                temperature=0.3,  # Lower temperature for more consistent output
                response_mime_type="application/json",
                response_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "timestamp": {"type": "string"},
                            "description": {"type": "string"},
                            "speaker": {"type": "string"},
                            "quote": {"type": "string"},
                            "reason": {"type": "string"},
                            "priority": {"type": "integer", "minimum": 1, "maximum": 5}
                        },
                        "required": ["timestamp", "description", "speaker", "quote", "reason", "priority"]
                    }
                },
                system_instruction=system_prompt  # System instruction goes in config
            )
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config
            )
            
            # Parse the JSON response
            result = json.loads(response.text)
            
            # Convert to VisualPoint objects and add timestamp_seconds
            visual_points = []
            for point_data in result:
                # Calculate timestamp_seconds from HH:MM:SS format
                timestamp_seconds = self._timestamp_to_seconds(point_data["timestamp"])
                point_data["timestamp_seconds"] = timestamp_seconds
                visual_points.append(VisualPoint.from_dict(point_data))
            
            # Sort by priority (1 is highest) and timestamp
            visual_points.sort(key=lambda p: (p.priority, p.timestamp_seconds))
            
            # Limit points if requested
            if max_points and len(visual_points) > max_points:
                visual_points = visual_points[:max_points]
            
            return visual_points
            
        except Exception as e:
            print(f"Error analyzing transcript: {e}")
            raise
    
    def _format_transcript_for_analysis(self, transcript_json: dict) -> str:
        """Format transcript JSON for LLM analysis."""
        lines = []
        
        # Add meeting metadata
        meeting_info = transcript_json.get("meeting", {})
        lines.append(f"Meeting Date: {meeting_info.get('date', 'Unknown')}")
        lines.append(f"Participants: {', '.join(meeting_info.get('participants', []))}")
        lines.append(f"Duration: {self._format_duration(meeting_info.get('duration_seconds', 0))}")
        lines.append("\n--- TRANSCRIPT ---\n")
        
        # Add transcript segments
        segments = transcript_json.get("segments", [])
        for segment in segments:
            timestamp = self._seconds_to_timestamp(segment["start_time"])
            speaker = segment["speaker"]
            text = segment["text"]
            lines.append(f"[{timestamp}] {speaker}: {text}")
        
        return "\n".join(lines)
    
    def _seconds_to_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _timestamp_to_seconds(self, timestamp: str) -> float:
        """Convert HH:MM:SS timestamp to seconds."""
        parts = timestamp.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        else:
            return float(timestamp)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def export_visual_points(self, visual_points: List[VisualPoint], output_path: str):
        """Export visual points to JSON file."""
        data = {
            "analysis_timestamp": os.environ.get("TZ", "UTC"),
            "model": self.model_name,
            "visual_points": [point.to_dict() for point in visual_points]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def set_custom_prompt(self, prompt_template: str):
        """Set a custom prompt template for visual analysis."""
        self.system_instruction = prompt_template