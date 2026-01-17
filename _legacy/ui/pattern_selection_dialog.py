from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QPushButton, QListWidgetItem
from PySide6.QtCore import Qt, Signal

class PatternSelectionDialog(QDialog):
    pattern_selected = Signal(str) # Emits the name of the selected pattern

    def __init__(self, patterns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Fabric Pattern")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        self.setModal(True)

        self.all_patterns = sorted(patterns)
        self.selected_pattern_name = None

        layout = QVBoxLayout(self)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search patterns...")
        self.search_input.textChanged.connect(self._filter_patterns)
        layout.addWidget(self.search_input)

        # Pattern list
        self.pattern_list_widget = QListWidget()
        self.pattern_list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.pattern_list_widget)

        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept) # QDialog's accept()
        self.ok_button.setEnabled(False) # Enabled when a pattern is selected

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject) # QDialog's reject()

        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.pattern_list_widget.currentItemChanged.connect(self._on_current_item_changed)
        
        self._populate_patterns(self.all_patterns)

    def _populate_patterns(self, patterns_to_show):
        self.pattern_list_widget.clear()
        for pattern_name in patterns_to_show:
            QListWidgetItem(pattern_name, self.pattern_list_widget)
        if self.pattern_list_widget.count() > 0:
            self.pattern_list_widget.setCurrentRow(0) # Select first item by default

    def _filter_patterns(self):
        search_text = self.search_input.text().lower()
        if not search_text:
            self._populate_patterns(self.all_patterns)
            return

        # Simple fuzzy search (substring matching)
        # For more advanced, consider libraries like thefuzz
        filtered_patterns = [
            p_name for p_name in self.all_patterns if search_text in p_name.lower()
        ]
        self._populate_patterns(filtered_patterns)

    def _on_current_item_changed(self, current_item, previous_item):
        self.ok_button.setEnabled(current_item is not None)
        if current_item:
            self.selected_pattern_name = current_item.text()
        else:
            self.selected_pattern_name = None
            
    def _accept_selection(self, item): # Connected to itemDoubleClicked
        self.selected_pattern_name = item.text()
        self.accept()

    def accept(self): # Override QDialog.accept()
        if self.selected_pattern_name:
            self.pattern_selected.emit(self.selected_pattern_name)
            super().accept()
        # else: user might click OK without selection if not careful, but button is disabled

    def get_selected_pattern(self):
        return self.selected_pattern_name

if __name__ == '__main__':
    # Example Usage
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    # Sample patterns
    sample_patterns = [
        "summarize_text", "extract_keywords", "analyze_sentiment", 
        "translate_to_french", "explain_code_snippet", "generate_story_idea",
        "debug_python_error", "create_email_draft", "validate_json_data"
    ]
    dialog = PatternSelectionDialog(sample_patterns * 10) # More items for scroll/search test
    
    def on_selection(pattern):
        print(f"Pattern selected from dialog: {pattern}")

    dialog.pattern_selected.connect(on_selection)

    if dialog.exec():
        print(f"Dialog accepted. Selected: {dialog.get_selected_pattern()}")
    else:
        print("Dialog cancelled.")
    
    sys.exit() # Wont be reached if app.exec() is called, but fine for direct script test 