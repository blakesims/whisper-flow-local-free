import sys
from PySide6.QtWidgets import QApplication
# Removed QMainWindow import as it's now defined in main_window.py

from app.ui.main_window import MainWindow
# from app.utils.config_manager import ConfigManager # For later use

# class MainWindow(QMainWindow): # This class is now in app.ui.main_window.py
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("Whisper Transcription UI")
#         # Further initialization will go here

def main():
    app = QApplication(sys.argv)
    
    # config_manager = ConfigManager() # Initialize config manager if needed at startup
    
    window = MainWindow() # Use the MainWindow from main_window.py
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 