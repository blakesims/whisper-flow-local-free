import json
import os
from pathlib import Path
import sys

APP_NAME = "WhisperTranscribeUI"

class ConfigManager:
    def __init__(self):
        self.config_path = self._get_config_path()
        self.config = self._load_config()

    def _get_config_path(self) -> Path:
        if sys.platform == "darwin": # macOS
            app_support_dir = Path.home() / "Library" / "Application Support" / APP_NAME
        elif sys.platform == "win32": # Windows
            app_support_dir = Path(os.getenv("APPDATA")) / APP_NAME
        else: # Linux and other OS
            app_support_dir = Path.home() / ".config" / APP_NAME
        
        app_support_dir.mkdir(parents=True, exist_ok=True)
        return app_support_dir / "settings.json"

    def _load_config(self) -> dict:
        default_config = {
            "model_size": "base",
            "language": "en",
            # Add other default settings here
        }
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    # Ensure all default keys exist
                    for key, value in default_config.items():
                        config.setdefault(key, value)
                    return config
            except json.JSONDecodeError:
                print(f"Error decoding JSON from {self.config_path}. Using default config.")
                # Potentially backup corrupted file here
                return default_config
        return default_config

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self._save_config()

    def _save_config(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except IOError as e:
            print(f"Error saving config to {self.config_path}: {e}")
    
    def save_config(self):
        """Public method to save config."""
        self._save_config()

# Example usage (optional, for testing)
if __name__ == '__main__':
    # This needs to be run from the project root for `import sys` to work correctly in _get_config_path, 
    # or sys needs to be imported in _get_config_path
    manager = ConfigManager()
    print(f"Config loaded from: {manager.config_path}")
    print(f"Current model size: {manager.get('model_size')}")
    manager.set("language", "fr")
    print(f"New language: {manager.get('language')}") 