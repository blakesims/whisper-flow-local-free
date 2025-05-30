"""
Custom dialog for selecting Zoom meeting recordings.
Automatically scans ~/Documents/Zoom for meeting folders and audio files.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QGroupBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal


class ZoomMeetingDialog(QDialog):
    """Dialog for selecting Zoom meeting recordings."""
    
    # Signal emitted when files are selected: (file_paths, participant_names, meeting_dir)
    files_selected = Signal(list, list, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Zoom Meeting")
        self.setModal(True)
        self.resize(600, 400)
        
        # Store meeting data
        self.meetings: List[Dict] = []
        self.selected_meeting: Optional[Dict] = None
        
        # Setup UI
        self._setup_ui()
        
        # Apply parent window style if available
        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
        
        # Scan for meetings
        self._scan_zoom_meetings()
    
    def _setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel("Select a Zoom meeting from the list below:")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Meeting list
        self.meeting_list = QListWidget()
        self.meeting_list.itemClicked.connect(self._on_meeting_selected)
        layout.addWidget(self.meeting_list)
        
        # Meeting details group
        self.details_group = QGroupBox("Meeting Details")
        details_layout = QVBoxLayout(self.details_group)
        
        self.details_label = QLabel("Select a meeting to see details")
        self.details_label.setWordWrap(True)
        details_layout.addWidget(self.details_label)
        
        layout.addWidget(self.details_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        
        # Disable OK until a meeting is selected
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        
        layout.addWidget(button_box)
    
    def _scan_zoom_meetings(self):
        """Scan ~/Documents/Zoom for meeting folders."""
        zoom_dir = Path.home() / "Documents" / "Zoom"
        
        if not zoom_dir.exists():
            self.details_label.setText(
                f"Zoom directory not found: {zoom_dir}\n"
                "Please ensure Zoom is configured to save recordings to the default location."
            )
            return
        
        # Pattern to match Zoom meeting folders
        # Format: YYYY-MM-DD HH.MM.SS Name's Personal Meeting Room
        folder_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2}) (\d{2}\.\d{2}\.\d{2}) (.+?)\'s Personal Meeting Room$'
        )
        
        meetings = []
        
        for folder in sorted(zoom_dir.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            
            match = folder_pattern.match(folder.name)
            if not match:
                continue
            
            date_str, time_str, host_name = match.groups()
            
            # Check for audio files
            audio_dir = folder / "Audio Record"
            if not audio_dir.exists():
                continue
            
            # Find audio files
            audio_files = list(audio_dir.glob("audio*.m4a"))
            if len(audio_files) < 2:
                continue  # Need at least 2 participants
            
            # Parse participant names from audio files
            participants = []
            file_paths = []
            
            for audio_file in audio_files:
                # Pattern: audioNameNumbers.m4a
                file_match = re.match(r'^audio([A-Za-z]+)(\d+)\.m4a$', audio_file.name)
                if file_match:
                    name = file_match.group(1)
                    # Add spaces before capital letters: BlakeSims -> Blake Sims
                    name = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
                    participants.append(name)
                    file_paths.append(str(audio_file))
            
            if len(participants) >= 2:
                # Parse datetime
                datetime_str = f"{date_str} {time_str.replace('.', ':')}"
                meeting_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
                
                meetings.append({
                    'datetime': meeting_dt,
                    'date_str': date_str,
                    'time_str': time_str.replace('.', ':'),
                    'host': host_name,
                    'participants': participants,
                    'file_paths': file_paths,
                    'folder': folder
                })
        
        self.meetings = meetings
        self._populate_meeting_list()
    
    def _populate_meeting_list(self):
        """Populate the meeting list widget."""
        self.meeting_list.clear()
        
        if not self.meetings:
            item = QListWidgetItem("No Zoom meetings found with multiple participants")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.meeting_list.addItem(item)
            return
        
        for meeting in self.meetings:
            # Format: 2025-05-29 11:14:48 - Blake Sims, Michael Chan
            participants_str = ", ".join(meeting['participants'])
            text = f"{meeting['date_str']} {meeting['time_str']} - {participants_str}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, meeting)
            self.meeting_list.addItem(item)
    
    def _on_meeting_selected(self, item: QListWidgetItem):
        """Handle meeting selection."""
        meeting = item.data(Qt.ItemDataRole.UserRole)
        if not meeting:
            return
        
        self.selected_meeting = meeting
        self.ok_button.setEnabled(True)
        
        # Update details
        details = f"Date: {meeting['date_str']}\n"
        details += f"Time: {meeting['time_str']}\n"
        details += f"Host: {meeting['host']}\n"
        details += f"Participants: {', '.join(meeting['participants'])}\n"
        details += f"Audio files: {len(meeting['file_paths'])}"
        
        self.details_label.setText(details)
    
    def _on_accept(self):
        """Handle OK button click."""
        if self.selected_meeting:
            self.files_selected.emit(
                self.selected_meeting['file_paths'],
                self.selected_meeting['participants'],
                self.selected_meeting['path']
            )
            self.accept()
    
    def get_selected_files(self) -> Optional[Tuple[List[str], List[str]]]:
        """Get the selected files and participant names."""
        if self.selected_meeting:
            return (
                self.selected_meeting['file_paths'],
                self.selected_meeting['participants']
            )
        return None