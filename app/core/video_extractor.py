"""
Service for extracting frames from video files at specific timestamps.
"""

import os
import subprocess
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import json
from datetime import timedelta


class VideoExtractor:
    """Extract frames from video files at specific timestamps."""
    
    def __init__(self, output_quality: int = 95):
        """
        Initialize video extractor.
        
        Args:
            output_quality: JPEG quality (1-100, default 95)
        """
        self.output_quality = output_quality
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Check if ffmpeg is available."""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg not found. Please install ffmpeg to use video extraction.")
    
    def extract_frames_at_timestamps(
        self,
        video_path: str,
        timestamps: List[Tuple[str, float]],  # [(HH:MM:SS, seconds), ...]
        output_dir: str,
        name_prefix: str = ""
    ) -> Dict[str, str]:
        """
        Extract frames from video at specific timestamps.
        
        Args:
            video_path: Path to video file
            timestamps: List of tuples (timestamp_str, timestamp_seconds)
            output_dir: Directory to save extracted frames
            name_prefix: Optional prefix for output filenames
        
        Returns:
            Dictionary mapping timestamp to output file path
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        extracted_frames = {}
        
        for timestamp_str, timestamp_seconds in timestamps:
            # Format filename: HH-MM-SS.jpg (using dashes for filesystem compatibility)
            safe_timestamp = timestamp_str.replace(":", "-")
            if name_prefix:
                output_filename = f"{name_prefix}_{safe_timestamp}.jpg"
            else:
                output_filename = f"{safe_timestamp}.jpg"
            
            output_path = os.path.join(output_dir, output_filename)
            
            try:
                # Use ffmpeg to extract frame at specific timestamp
                cmd = [
                    "ffmpeg",
                    "-ss", str(timestamp_seconds),  # Seek to timestamp
                    "-i", video_path,
                    "-frames:v", "1",  # Extract only one frame
                    "-q:v", str(100 - self.output_quality),  # Quality (lower is better for ffmpeg)
                    "-y",  # Overwrite output file
                    output_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0 and os.path.exists(output_path):
                    extracted_frames[timestamp_str] = output_path
                    print(f"Extracted frame at {timestamp_str} -> {output_filename}")
                else:
                    print(f"Failed to extract frame at {timestamp_str}: {result.stderr}")
                    
            except Exception as e:
                print(f"Error extracting frame at {timestamp_str}: {e}")
        
        return extracted_frames
    
    def find_video_file(self, meeting_dir: str) -> Optional[str]:
        """
        Find video file in Zoom meeting directory.
        
        Args:
            meeting_dir: Path to Zoom meeting directory
        
        Returns:
            Path to video file if found, None otherwise
        """
        # Common Zoom recording patterns
        video_patterns = ["*.mp4", "*.m4v", "*.mov", "zoom_0.mp4", "video*.mp4"]
        
        meeting_path = Path(meeting_dir)
        
        # Look for video files
        for pattern in video_patterns:
            matches = list(meeting_path.glob(pattern))
            if matches:
                # Return the first match (usually there's only one main recording)
                return str(matches[0])
        
        # Also check in subdirectories
        for subdir in meeting_path.iterdir():
            if subdir.is_dir():
                for pattern in video_patterns:
                    matches = list(subdir.glob(pattern))
                    if matches:
                        return str(matches[0])
        
        return None
    
    def extract_thumbnail(
        self,
        video_path: str,
        output_path: str,
        timestamp_seconds: float = 5.0,
        size: Optional[Tuple[int, int]] = None
    ) -> bool:
        """
        Extract a thumbnail from video.
        
        Args:
            video_path: Path to video file
            output_path: Path for output thumbnail
            timestamp_seconds: Time to extract thumbnail from (default 5 seconds)
            size: Optional (width, height) to resize thumbnail
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                "ffmpeg",
                "-ss", str(timestamp_seconds),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", str(100 - self.output_quality)
            ]
            
            if size:
                cmd.extend(["-vf", f"scale={size[0]}:{size[1]}"])
            
            cmd.extend(["-y", output_path])
            
            result = subprocess.run(cmd, capture_output=True)
            return result.returncode == 0 and os.path.exists(output_path)
            
        except Exception as e:
            print(f"Error extracting thumbnail: {e}")
            return False
    
    def get_video_info(self, video_path: str) -> Optional[dict]:
        """
        Get video information using ffprobe.
        
        Args:
            video_path: Path to video file
        
        Returns:
            Dictionary with video information or None if failed
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            
        except Exception as e:
            print(f"Error getting video info: {e}")
        
        return None
    
    @staticmethod
    def format_timestamp_for_filename(timestamp: str) -> str:
        """Convert HH:MM:SS to HH-MM-SS for safe filenames."""
        return timestamp.replace(":", "-")
    
    @staticmethod
    def timestamp_to_seconds(timestamp: str) -> float:
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