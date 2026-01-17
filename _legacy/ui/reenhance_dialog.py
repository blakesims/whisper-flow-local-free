"""
Dialog for selecting existing meeting transcripts to re-enhance.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QGroupBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal


class ReEnhanceDialog(QDialog):
    """Dialog for selecting existing transcripts to re-enhance."""
    
    # Signal emitted when a transcript is selected: (meeting_dir, transcript_path)
    transcript_selected = Signal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Re-Enhance Existing Transcript")
        self.setModal(True)
        self.resize(600, 400)
        
        # Store transcript data
        self.transcripts: List[Dict] = []
        self.selected_transcript: Optional[Dict] = None
        
        # Setup UI
        self._setup_ui()
        
        # Apply parent window style if available
        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
        
        # Scan for existing transcripts
        self._scan_for_transcripts()
    
    def _setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel("Select a meeting with existing transcript to re-enhance:")
        layout.addWidget(instructions)
        
        # Meeting list
        self.transcript_list = QListWidget()
        self.transcript_list.itemSelectionChanged.connect(self._on_transcript_selected)
        layout.addWidget(self.transcript_list)
        
        # Details group
        details_group = QGroupBox("Details")
        details_layout = QVBoxLayout()
        self.details_label = QLabel("Select a meeting to see details")
        self.details_label.setWordWrap(True)
        details_layout.addWidget(self.details_label)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _scan_for_transcripts(self):
        """Scan ~/Documents/Zoom for meetings with action-notes/transcript.json."""
        zoom_dir = Path.home() / "Documents" / "Zoom"
        
        if not zoom_dir.exists():
            self.details_label.setText(
                f"Zoom directory not found: {zoom_dir}\n"
                "Please ensure Zoom is configured to save recordings to the default location."
            )
            return
        
        transcripts = []
        
        # Look for meetings with existing transcripts
        for folder in sorted(zoom_dir.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            
            # Check for action-notes/transcript.json
            transcript_path = folder / "action-notes" / "transcript.json"
            if not transcript_path.exists():
                continue
            
            try:
                # Load transcript to get metadata
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    transcript_data = json.load(f)
                
                meeting_info = transcript_data.get("meeting", {})
                
                # Check if already enhanced
                visual_points_path = folder / "action-notes" / "visual-points.json"
                enhanced_path = folder / "action-notes" / "transcript-enhanced.md"
                
                # Count existing enhancements
                enhancement_count = 0
                for file in (folder / "action-notes").iterdir():
                    if file.name.startswith("visual-points") and file.suffix == ".json":
                        enhancement_count += 1
                
                transcripts.append({
                    'folder': folder,
                    'transcript_path': transcript_path,
                    'date': meeting_info.get('date', 'Unknown'),
                    'participants': meeting_info.get('participants', []),
                    'duration': meeting_info.get('duration_seconds', 0),
                    'has_enhancement': visual_points_path.exists(),
                    'enhancement_count': enhancement_count,
                    'folder_name': folder.name
                })
                
            except Exception as e:
                print(f"Error reading transcript from {folder}: {e}")
                continue
        
        self.transcripts = transcripts
        self._populate_transcript_list()
    
    def _populate_transcript_list(self):
        """Populate the transcript list widget."""
        self.transcript_list.clear()
        
        if not self.transcripts:
            item = QListWidgetItem("No meetings with transcripts found")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.transcript_list.addItem(item)
            return
        
        for transcript in self.transcripts:
            # Format display text
            folder_name = transcript['folder_name']
            participants = ", ".join(transcript['participants'][:2])  # Show first 2
            if len(transcript['participants']) > 2:
                participants += f" +{len(transcript['participants']) - 2}"
            
            status = "✓ Enhanced" if transcript['has_enhancement'] else "○ Not enhanced"
            if transcript['enhancement_count'] > 1:
                status += f" ({transcript['enhancement_count']}x)"
            
            text = f"{folder_name} - {participants} {status}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, transcript)
            self.transcript_list.addItem(item)
    
    def _on_transcript_selected(self):
        """Handle transcript selection."""
        current_item = self.transcript_list.currentItem()
        if not current_item:
            return
        
        transcript = current_item.data(Qt.ItemDataRole.UserRole)
        if not transcript:
            return
        
        self.selected_transcript = transcript
        self.ok_button.setEnabled(True)
        
        # Update details
        details = f"Folder: {transcript['folder_name']}\n"
        details += f"Date: {transcript['date']}\n"
        details += f"Participants: {', '.join(transcript['participants'])}\n"
        details += f"Duration: {self._format_duration(transcript['duration'])}\n"
        details += f"Status: {'Enhanced' if transcript['has_enhancement'] else 'Not enhanced'}\n"
        
        if transcript['enhancement_count'] > 1:
            details += f"Previous enhancements: {transcript['enhancement_count']}"
        
        self.details_label.setText(details)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def _on_accept(self):
        """Handle OK button click."""
        if self.selected_transcript:
            self.transcript_selected.emit(
                str(self.selected_transcript['folder']),
                str(self.selected_transcript['transcript_path'])
            )
            self.accept()
    
    def get_selected_transcript(self) -> Optional[Tuple[str, str]]:
        """Get the selected transcript info."""
        if self.selected_transcript:
            return (
                str(self.selected_transcript['folder']),
                str(self.selected_transcript['transcript_path'])
            )
        return None