"""
Global Hotkey Listener

Uses pynput to listen for system-wide keyboard shortcuts.
On macOS, this requires Accessibility permissions.
"""

from PySide6.QtCore import QObject, Signal, QThread
from pynput import keyboard
import platform


class HotkeyListener(QObject):
    """
    Listens for global hotkey (Ctrl+F by default) and emits signal when triggered.

    Note: On macOS, the app needs Accessibility permissions for global hotkeys.
    The user will be prompted to grant access in System Preferences > Privacy & Security > Accessibility.
    """

    hotkey_triggered = Signal()

    def __init__(self, hotkey: str = "<ctrl>+f", parent=None):
        """
        Initialize the hotkey listener.

        Args:
            hotkey: The hotkey combination in pynput format.
                    Default is "<ctrl>+f" (Ctrl+F on Mac)
        """
        super().__init__(parent)

        self._hotkey_str = hotkey
        self._listener = None
        self._is_listening = False

        # Track key states for combination detection
        self._ctrl_pressed = False
        self._hotkey_active = False

    def start(self):
        """Start listening for the global hotkey"""
        if self._is_listening:
            print("[Hotkey] Already listening")
            return

        try:
            # Use the keyboard listener with callbacks
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._listener.start()
            self._is_listening = True
            print(f"[Hotkey] Listening for {self._hotkey_str}")

            # Check for accessibility permissions on macOS
            if platform.system() == "Darwin":
                self._check_macos_permissions()

        except Exception as e:
            print(f"[Hotkey] Error starting listener: {e}")
            self._is_listening = False

    def stop(self):
        """Stop listening for hotkeys"""
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._is_listening = False
        self._ctrl_pressed = False
        self._hotkey_active = False
        print("[Hotkey] Stopped listening")

    def _on_key_press(self, key):
        """Handle key press events"""
        try:
            # Check for Ctrl key
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = True
                return

            # Check for 'f' key while Ctrl is held
            if self._ctrl_pressed and not self._hotkey_active:
                # Check if it's the 'f' key
                if hasattr(key, 'char') and key.char and key.char.lower() == 'f':
                    self._hotkey_active = True
                    print("[Hotkey] Ctrl+F detected!")
                    self.hotkey_triggered.emit()

        except AttributeError:
            # Some keys don't have the 'char' attribute
            pass

    def _on_key_release(self, key):
        """Handle key release events"""
        try:
            # Reset Ctrl state on release
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = False
                self._hotkey_active = False

            # Reset hotkey active state when 'f' is released
            if hasattr(key, 'char') and key.char and key.char.lower() == 'f':
                self._hotkey_active = False

        except AttributeError:
            pass

    def _check_macos_permissions(self):
        """Check and warn about macOS accessibility permissions"""
        try:
            # Try to detect if we have permission by the behavior
            # pynput will work but not capture all keys without permission
            print("[Hotkey] macOS detected - ensure Accessibility permission is granted")
            print("[Hotkey] Go to: System Preferences > Privacy & Security > Accessibility")
            print("[Hotkey] Add Terminal (or Python) to the allowed apps")
        except Exception:
            pass

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    def set_hotkey(self, hotkey: str):
        """
        Change the hotkey combination.
        Must call stop() and start() for changes to take effect.
        """
        self._hotkey_str = hotkey
        print(f"[Hotkey] Hotkey set to: {hotkey}")


class HotkeyListenerThread(QThread):
    """
    Alternative implementation that runs the listener in a separate QThread.
    Use this if the main implementation causes issues with the Qt event loop.
    """

    hotkey_triggered = Signal()

    def __init__(self, hotkey: str = "<ctrl>+f", parent=None):
        super().__init__(parent)
        self._hotkey_str = hotkey
        self._running = False
        self._ctrl_pressed = False
        self._hotkey_active = False

    def run(self):
        """Thread run method"""
        self._running = True

        def on_press(key):
            if not self._running:
                return False  # Stop listener

            try:
                if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    self._ctrl_pressed = True
                    return

                if self._ctrl_pressed and not self._hotkey_active:
                    if hasattr(key, 'char') and key.char and key.char.lower() == 'f':
                        self._hotkey_active = True
                        self.hotkey_triggered.emit()
            except AttributeError:
                pass

        def on_release(key):
            if not self._running:
                return False  # Stop listener

            try:
                if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    self._ctrl_pressed = False
                    self._hotkey_active = False

                if hasattr(key, 'char') and key.char and key.char.lower() == 'f':
                    self._hotkey_active = False
            except AttributeError:
                pass

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    def stop(self):
        """Stop the listener thread"""
        self._running = False
        self.quit()
        self.wait(1000)


# Test the hotkey listener
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    listener = HotkeyListener()

    def on_hotkey():
        print(">>> HOTKEY TRIGGERED! <<<")

    listener.hotkey_triggered.connect(on_hotkey)
    listener.start()

    print("Press Ctrl+F to trigger hotkey. Ctrl+C to exit.")

    sys.exit(app.exec())
