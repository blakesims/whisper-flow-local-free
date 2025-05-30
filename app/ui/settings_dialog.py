"""
Settings dialog for configuring API keys and model selection.
"""

import os
import json
from typing import List, Dict, Optional
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel,
    QGroupBox, QMessageBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal

from google import genai
from app.utils.config_manager import ConfigManager


class SettingsDialog(QDialog):
    """Settings dialog for API configuration."""
    
    settings_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(500, 400)
        
        # Load config
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # Available models cache
        self.available_models = []
        
        # Setup UI
        self._setup_ui()
        
        # Load current settings
        self._load_current_settings()
        
        # Apply parent window style if available
        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
    
    def _setup_ui(self):
        """Create the settings UI."""
        layout = QVBoxLayout(self)
        
        # Google API Settings
        google_group = QGroupBox("Google Gemini API")
        google_layout = QFormLayout()
        
        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter your Google API key")
        google_layout.addRow("API Key:", self.api_key_edit)
        
        # Show/Hide API key button
        self.toggle_api_key_btn = QPushButton("Show")
        self.toggle_api_key_btn.setMaximumWidth(60)
        self.toggle_api_key_btn.clicked.connect(self._toggle_api_key_visibility)
        
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(self.api_key_edit)
        api_key_layout.addWidget(self.toggle_api_key_btn)
        google_layout.setLayout(0, QFormLayout.ItemRole.FieldRole, api_key_layout)
        
        # Model selection
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)  # Allow custom model names
        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_models_list)
        
        model_layout.addWidget(self.model_combo)
        model_layout.addWidget(self.refresh_models_btn)
        google_layout.addRow("Model:", model_layout)
        
        # Model info label
        self.model_info_label = QLabel("Enter API key and click 'Refresh Models' to see available models")
        self.model_info_label.setWordWrap(True)
        self.model_info_label.setStyleSheet("color: #888; font-size: 12px;")
        google_layout.addRow("", self.model_info_label)
        
        google_group.setLayout(google_layout)
        layout.addWidget(google_group)
        
        # Enhancement Settings
        enhance_group = QGroupBox("Enhancement Settings")
        enhance_layout = QFormLayout()
        
        # Max visual points
        self.max_points_spin = QLineEdit()
        self.max_points_spin.setPlaceholderText("20")
        self.max_points_spin.setMaximumWidth(100)
        enhance_layout.addRow("Max Visual Points:", self.max_points_spin)
        
        # Video quality
        self.video_quality_spin = QLineEdit()
        self.video_quality_spin.setPlaceholderText("95")
        self.video_quality_spin.setMaximumWidth(100)
        enhance_layout.addRow("JPEG Quality (1-100):", self.video_quality_spin)
        
        enhance_group.setLayout(enhance_layout)
        layout.addWidget(enhance_group)
        
        # Add stretch
        layout.addStretch()
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _toggle_api_key_visibility(self):
        """Toggle API key visibility."""
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_api_key_btn.setText("Hide")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_api_key_btn.setText("Show")
    
    def _load_current_settings(self):
        """Load current settings from config and environment."""
        # API Key - check env first, then config
        api_key = os.getenv("GOOGLE_API_KEY") or self.config.get("google_api_key", "")
        if api_key:
            self.api_key_edit.setText(api_key)
        
        # Model
        current_model = self.config.get("gemini_model", "gemini-2.0-flash-exp")
        self.model_combo.addItem(current_model)
        self.model_combo.setCurrentText(current_model)
        
        # Enhancement settings
        max_points = self.config.get("max_visual_points", 20)
        self.max_points_spin.setText(str(max_points))
        
        video_quality = self.config.get("video_quality", 95)
        self.video_quality_spin.setText(str(video_quality))
    
    def _refresh_models_list(self):
        """Fetch available models from Google API."""
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "No API Key", "Please enter your Google API key first.")
            return
        
        try:
            # Create client with the API key
            client = genai.Client(api_key=api_key)
            
            # List models
            self.model_info_label.setText("Fetching models...")
            models_response = client.models.list()
            
            # Clear and populate combo box
            current_text = self.model_combo.currentText()
            self.model_combo.clear()
            
            # Add models that support content generation
            generation_models = []
            for model in models_response:
                # Check if model supports generateContent
                if hasattr(model, 'supported_generation_methods') and \
                   'generateContent' in model.supported_generation_methods:
                    model_name = model.name
                    # Remove 'models/' prefix if present
                    if model_name.startswith('models/'):
                        model_name = model_name[7:]
                    
                    # Add to list with description
                    display_name = model_name
                    if hasattr(model, 'display_name') and model.display_name:
                        display_name = f"{model_name} ({model.display_name})"
                    
                    generation_models.append((model_name, display_name))
            
            # Sort by model name
            generation_models.sort(key=lambda x: x[0])
            
            # Add to combo box
            for model_name, display_name in generation_models:
                self.model_combo.addItem(display_name, model_name)
            
            # Restore previous selection if available
            index = self.model_combo.findData(current_text)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            elif current_text:
                # Add custom model if not in list
                self.model_combo.addItem(current_text, current_text)
                self.model_combo.setCurrentText(current_text)
            
            self.model_info_label.setText(f"Found {len(generation_models)} models with content generation support")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch models: {str(e)}")
            self.model_info_label.setText("Error fetching models")
    
    def accept(self):
        """Save settings and close dialog."""
        # Validate inputs
        try:
            max_points = int(self.max_points_spin.text()) if self.max_points_spin.text() else 20
            if max_points < 1 or max_points > 100:
                raise ValueError("Max points must be between 1 and 100")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", str(e))
            return
        
        try:
            video_quality = int(self.video_quality_spin.text()) if self.video_quality_spin.text() else 95
            if video_quality < 1 or video_quality > 100:
                raise ValueError("Video quality must be between 1 and 100")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", str(e))
            return
        
        # Save settings
        api_key = self.api_key_edit.text().strip()
        if api_key:
            self.config["google_api_key"] = api_key
            # Also set environment variable for current session
            os.environ["GOOGLE_API_KEY"] = api_key
        
        # Get model name (from data if available, otherwise from text)
        model_index = self.model_combo.currentIndex()
        if model_index >= 0 and self.model_combo.itemData(model_index):
            model_name = self.model_combo.itemData(model_index)
        else:
            model_name = self.model_combo.currentText()
            # Remove display name if present
            if ' (' in model_name:
                model_name = model_name.split(' (')[0]
        
        self.config["gemini_model"] = model_name
        self.config["max_visual_points"] = max_points
        self.config["video_quality"] = video_quality
        
        # Save config
        self.config_manager.save_config()
        
        # Emit signal
        self.settings_changed.emit()
        
        # Close dialog
        super().accept()
    
    def get_current_settings(self) -> dict:
        """Get current settings as a dictionary."""
        return {
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_combo.currentText(),
            "max_visual_points": int(self.max_points_spin.text()) if self.max_points_spin.text() else 20,
            "video_quality": int(self.video_quality_spin.text()) if self.video_quality_spin.text() else 95
        }