"""
Service for enhancing meeting transcripts with visual elements.
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .meeting_transcript import MeetingTranscript, TranscriptSegment
from .gemini_service import GeminiService, VisualPoint
from .video_extractor import VideoExtractor
from .transcript_sectioner import TranscriptSectioner, TranscriptSection


class TranscriptEnhancer:
    """Enhance meeting transcripts with visual confirmation points and extracted images."""
    
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        video_quality: int = 95,
        model_name: Optional[str] = None
    ):
        """
        Initialize transcript enhancer.
        
        Args:
            gemini_api_key: Google API key for Gemini
            video_quality: JPEG quality for extracted frames (1-100)
            model_name: Gemini model to use
        """
        self.gemini_service = GeminiService(api_key=gemini_api_key, model_name=model_name) if model_name else GeminiService(api_key=gemini_api_key)
        self.transcript_sectioner = TranscriptSectioner(api_key=gemini_api_key, model_name=model_name) if model_name else TranscriptSectioner(api_key=gemini_api_key)
        self.video_extractor = VideoExtractor(output_quality=video_quality)
        self._progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates."""
        self._progress_callback = callback
    
    def enhance_meeting_transcript(
        self,
        meeting_dir: str,
        transcript: MeetingTranscript,
        custom_prompt: Optional[str] = None,
        max_visual_points: Optional[int] = 20
    ) -> Dict[str, any]:
        """
        Enhance a meeting transcript with visual analysis and extracted frames.
        
        Args:
            meeting_dir: Path to Zoom meeting directory
            transcript: MeetingTranscript object
            custom_prompt: Optional custom prompt for Gemini
            max_visual_points: Maximum number of visual points to extract
        
        Returns:
            Dictionary with paths to created files and analysis results
        """
        meeting_path = Path(meeting_dir)
        action_notes_dir = meeting_path / "action-notes"
        images_dir = action_notes_dir / "images"
        
        # Create directories
        action_notes_dir.mkdir(exist_ok=True)
        images_dir.mkdir(exist_ok=True)
        
        # Check for existing enhancements and iterate filenames
        enhancement_num = self._get_next_enhancement_number(action_notes_dir)
        
        results = {
            "meeting_dir": str(meeting_path),
            "action_notes_dir": str(action_notes_dir),
            "files_created": [],
            "visual_points": [],
            "extracted_frames": {},
            "errors": []
        }
        
        try:
            # Step 1: Save original transcript
            transcript_json_path = action_notes_dir / "transcript.json"
            transcript_data = transcript.to_json()
            with open(transcript_json_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
            results["files_created"].append(str(transcript_json_path))
            
            # Save markdown version too
            transcript_md_path = action_notes_dir / "transcript.md"
            with open(transcript_md_path, 'w', encoding='utf-8') as f:
                f.write(transcript.to_markdown())
            results["files_created"].append(str(transcript_md_path))
            
            # Step 2: Check if sectioning is needed
            # Get settings from config
            from app.utils.config_manager import ConfigManager
            config = ConfigManager()
            line_threshold = config.get("transcript_line_threshold", 500)
            sectioning_strategy = config.get("sectioning_strategy", "topic_based")
            max_section_duration_minutes = config.get("max_section_duration_minutes", 15)
            
            # Count lines in transcript
            transcript_lines = sum(1 for segment in transcript.segments)
            print(f"Transcript has {transcript_lines} segments/lines")
            
            sections = None
            section_metadata = None
            
            if transcript_lines > line_threshold:
                print(f"Transcript exceeds {line_threshold} line threshold, initiating sectioning...")
                if self._progress_callback:
                    self._progress_callback(f"Transcript has {transcript_lines} lines, sectioning for better processing...")
                
                # Create sectioning progress callback
                def section_progress(msg):
                    print(f"Sectioner: {msg}")
                    if self._progress_callback:
                        self._progress_callback(f"Sectioner: {msg}")
                
                # Convert minutes to seconds for max duration
                max_duration_seconds = max_section_duration_minutes * 60 if sectioning_strategy != "topic_based" else None
                
                # Section the transcript
                sections, section_metadata = self.transcript_sectioner.section_transcript(
                    transcript_data,
                    max_section_duration=max_duration_seconds,
                    progress_callback=section_progress
                )
                
                # Save sections to file
                sections_path = action_notes_dir / f"transcript-sections{'-' + str(enhancement_num) if enhancement_num > 1 else ''}.json"
                self.transcript_sectioner.export_sections(sections, section_metadata, str(sections_path))
                results["files_created"].append(str(sections_path))
                results["sections"] = [section.to_dict() for section in sections]
                results["section_metadata"] = section_metadata
                
                print(f"Created {len(sections)} sections")
                if self._progress_callback:
                    self._progress_callback(f"Created {len(sections)} sections for analysis")
            
            # Step 3: Analyze transcript for visual points
            print("Analyzing transcript for visual confirmation points...")
            
            # Create a progress callback for visual analysis
            def gemini_progress(msg):
                print(f"Visual Analysis: {msg}")
                if hasattr(self, '_progress_callback') and self._progress_callback:
                    self._progress_callback(f"Visual Analysis: {msg}")
            
            visual_points = []
            
            if sections:
                # Process each section separately
                for i, section in enumerate(sections):
                    if self._progress_callback:
                        self._progress_callback(f"Analyzing section {i+1}/{len(sections)}: {section.title}")
                    
                    # Create a sub-transcript for this section
                    section_segments = transcript_data["segments"][section.start_segment_index:section.end_segment_index + 1]
                    section_transcript_data = {
                        "meeting": transcript_data["meeting"],
                        "segments": section_segments
                    }
                    
                    # Analyze this section
                    section_visual_points = self.gemini_service.analyze_transcript_for_visual_points(
                        section_transcript_data,
                        custom_prompt=custom_prompt,
                        max_points=max_visual_points // len(sections) if max_visual_points else None,  # Distribute points across sections
                        progress_callback=lambda msg: gemini_progress(f"Section {i+1}: {msg}")
                    )
                    
                    visual_points.extend(section_visual_points)
                    print(f"Section {i+1} yielded {len(section_visual_points)} visual points")
            else:
                # Process entire transcript as one
                visual_points = self.gemini_service.analyze_transcript_for_visual_points(
                    transcript_data,
                    custom_prompt=custom_prompt,
                    max_points=max_visual_points,
                    progress_callback=gemini_progress
                )
            
            # Sort all visual points by priority and timestamp
            visual_points.sort(key=lambda p: (p.priority, p.timestamp_seconds))
            
            # Limit total points if needed
            if max_visual_points and len(visual_points) > max_visual_points:
                visual_points = visual_points[:max_visual_points]
            
            results["visual_points"] = [point.to_dict() for point in visual_points]
            
            # Save visual points analysis with iteration number
            if enhancement_num > 1:
                visual_points_path = action_notes_dir / f"visual-points-{enhancement_num}.json"
            else:
                visual_points_path = action_notes_dir / "visual-points.json"
            self.gemini_service.export_visual_points(visual_points, str(visual_points_path))
            results["files_created"].append(str(visual_points_path))
            
            # Step 3: Find video file
            video_path = self.video_extractor.find_video_file(str(meeting_path))
            if not video_path:
                results["errors"].append("No video file found in meeting directory")
                print("Warning: No video file found, skipping frame extraction")
            else:
                # Step 4: Extract frames at visual points
                print(f"Extracting frames from video: {os.path.basename(video_path)}")
                timestamps = [(point.timestamp, point.timestamp_seconds) for point in visual_points]
                
                extracted_frames = self.video_extractor.extract_frames_at_timestamps(
                    video_path,
                    timestamps,
                    str(images_dir)
                )
                results["extracted_frames"] = extracted_frames
                
                # Step 5: Create enhanced transcript with image references
                enhanced_md = self._create_enhanced_transcript(
                    transcript,
                    visual_points,
                    extracted_frames,
                    str(action_notes_dir),
                    sections=sections  # Pass sections if available
                )
                
                # Use iteration number for enhanced transcript
                if enhancement_num > 1:
                    enhanced_path = action_notes_dir / f"transcript-enhanced-{enhancement_num}.md"
                else:
                    enhanced_path = action_notes_dir / "transcript-enhanced.md"
                with open(enhanced_path, 'w', encoding='utf-8') as f:
                    f.write(enhanced_md)
                results["files_created"].append(str(enhanced_path))
            
            # Step 6: Create summary report
            summary = self._create_summary_report(results, transcript, visual_points)
            if enhancement_num > 1:
                summary_path = action_notes_dir / f"enhancement-summary-{enhancement_num}.md"
            else:
                summary_path = action_notes_dir / "enhancement-summary.md"
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            results["files_created"].append(str(summary_path))
            
        except Exception as e:
            results["errors"].append(f"Enhancement error: {str(e)}")
            print(f"Error during enhancement: {e}")
        
        return results
    
    def _create_enhanced_transcript(
        self,
        transcript: MeetingTranscript,
        visual_points: List[VisualPoint],
        extracted_frames: Dict[str, str],
        action_notes_dir: str,
        sections: Optional[List[TranscriptSection]] = None
    ) -> str:
        """Create enhanced markdown transcript with embedded images."""
        lines = []
        
        # Header
        lines.append("# Enhanced Meeting Transcript")
        lines.append(f"Date: {transcript.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Participants: {', '.join(transcript.participants)}")
        lines.append(f"Duration: {self._format_duration(transcript.duration)}")
        lines.append("")
        
        # Visual points summary
        lines.append("## Visual Confirmation Points")
        lines.append(f"*{len(visual_points)} points identified requiring visual context*")
        lines.append("")
        
        # Sections summary if available
        if sections:
            lines.append("## Meeting Sections")
            lines.append(f"*Meeting divided into {len(sections)} sections for clarity*")
            lines.append("")
            for section in sections:
                lines.append(f"- **{section.title}** ({section.start_timestamp} - {section.end_timestamp})")
                lines.append(f"  - {section.description}")
            lines.append("")
        
        # Create a map of timestamps to visual points
        visual_map = {point.timestamp_seconds: point for point in visual_points}
        
        # Transcript with embedded visuals
        lines.append("## Enhanced Transcript")
        lines.append("")
        
        transcript.sort_segments()
        
        # If we have sections, track current section
        current_section_idx = 0 if sections else None
        
        for i, segment in enumerate(transcript.segments):
            # Check if we need to add a section header
            if sections and current_section_idx < len(sections):
                current_section = sections[current_section_idx]
                # Check if this segment starts a new section
                if i == current_section.start_segment_index:
                    lines.append("")
                    lines.append(f"### 📌 Section {current_section.section_id}: {current_section.title}")
                    lines.append(f"*{current_section.description}*")
                    lines.append(f"*Duration: {current_section.start_timestamp} - {current_section.end_timestamp}*")
                    lines.append("")
                
                # Move to next section if we've passed the current one
                if i > current_section.end_segment_index and current_section_idx < len(sections) - 1:
                    current_section_idx += 1
            
            # Check if this segment has a visual point
            visual_point = None
            for vp in visual_points:
                if abs(segment.start_time - vp.timestamp_seconds) < 2:  # Within 2 seconds
                    visual_point = vp
                    break
            
            # Add transcript line
            timestamp = segment.format_timestamp(segment.start_time)
            lines.append(f"[{timestamp}] **{segment.speaker}**: {segment.text}")
            
            # Add visual element if applicable
            if visual_point and visual_point.timestamp in extracted_frames:
                lines.append("")
                lines.append(f"> 🎯 **Visual Context Required**")
                lines.append(f"> *{visual_point.reason}*")
                lines.append(f">")
                
                # Add image with relative path
                image_path = extracted_frames[visual_point.timestamp]
                relative_path = os.path.relpath(image_path, action_notes_dir)
                lines.append(f"> ![{visual_point.description}]({relative_path})")
                lines.append(f">")
                lines.append(f"> *Priority: {visual_point.priority}/5*")
                lines.append("")
            
            lines.append("")
        
        # Appendix with all visual points
        lines.append("## Appendix: All Visual Points")
        lines.append("")
        
        for i, vp in enumerate(visual_points, 1):
            lines.append(f"### {i}. [{vp.timestamp}] {vp.description}")
            lines.append(f"**Speaker:** {vp.speaker}")
            lines.append(f"**Quote:** \"{vp.quote}\"")
            lines.append(f"**Reason:** {vp.reason}")
            lines.append(f"**Priority:** {vp.priority}/5")
            
            if vp.timestamp in extracted_frames:
                image_path = extracted_frames[vp.timestamp]
                relative_path = os.path.relpath(image_path, action_notes_dir)
                lines.append(f"**Image:** [{os.path.basename(image_path)}]({relative_path})")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _create_summary_report(
        self,
        results: dict,
        transcript: MeetingTranscript,
        visual_points: List[VisualPoint]
    ) -> str:
        """Create a summary report of the enhancement process."""
        lines = []
        
        lines.append("# Meeting Enhancement Summary")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        lines.append("## Meeting Information")
        lines.append(f"- Date: {transcript.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- Participants: {', '.join(transcript.participants)}")
        lines.append(f"- Duration: {self._format_duration(transcript.duration)}")
        lines.append(f"- Total Segments: {len(transcript.segments)}")
        lines.append("")
        
        lines.append("## Enhancement Results")
        
        # Add sectioning info if available
        if 'sections' in results and results['sections']:
            lines.append(f"- Transcript Sections: {len(results['sections'])}")
            lines.append(f"- Sectioning Strategy: {results.get('section_metadata', {}).get('sectioning_strategy', 'N/A')}")
        
        lines.append(f"- Visual Points Identified: {len(visual_points)}")
        lines.append(f"- Frames Extracted: {len(results['extracted_frames'])}")
        lines.append(f"- Files Created: {len(results['files_created'])}")
        lines.append("")
        
        if visual_points:
            lines.append("## Top Priority Visual Points")
            top_points = sorted(visual_points, key=lambda p: p.priority)[:5]
            for i, vp in enumerate(top_points, 1):
                lines.append(f"{i}. [{vp.timestamp}] {vp.description} (Priority: {vp.priority})")
            lines.append("")
        
        lines.append("## Files Generated")
        for file_path in results['files_created']:
            lines.append(f"- {os.path.basename(file_path)}")
        lines.append("")
        
        if results['errors']:
            lines.append("## Errors")
            for error in results['errors']:
                lines.append(f"- {error}")
            lines.append("")
        
        lines.append("## Directory Structure")
        lines.append("```")
        lines.append("action-notes/")
        lines.append("├── transcript.json          # Original transcript data")
        lines.append("├── transcript.md            # Original transcript (markdown)")
        lines.append("├── visual-points.json       # LLM analysis results")
        lines.append("├── transcript-enhanced.md   # Enhanced transcript with images")
        lines.append("├── enhancement-summary.md   # This file")
        lines.append("└── images/                  # Extracted video frames")
        
        if len(results['extracted_frames']) > 0:
            for timestamp in sorted(results['extracted_frames'].keys())[:3]:
                filename = os.path.basename(results['extracted_frames'][timestamp])
                lines.append(f"    ├── {filename}")
            if len(results['extracted_frames']) > 3:
                lines.append(f"    └── ... ({len(results['extracted_frames']) - 3} more)")
        
        lines.append("```")
        
        return "\n".join(lines)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def set_gemini_prompt(self, prompt: str):
        """Set custom Gemini prompt for visual analysis."""
        self.gemini_service.set_custom_prompt(prompt)
    
    def _get_next_enhancement_number(self, action_notes_dir: Path) -> int:
        """Get the next enhancement number for iterating results."""
        # Look for existing visual-points files
        existing_files = list(action_notes_dir.glob("visual-points*.json"))
        
        if not existing_files:
            return 1
        
        # Extract numbers from filenames
        numbers = [1]  # Start with 1 for the base file
        for file in existing_files:
            if file.name == "visual-points.json":
                continue
            # Extract number from visual-points-N.json
            match = re.search(r'visual-points-(\d+)\.json', file.name)
            if match:
                numbers.append(int(match.group(1)))
        
        return max(numbers) + 1