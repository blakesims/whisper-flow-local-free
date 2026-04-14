"""
Global Hotkey Listener

Uses pynput to listen for system-wide keyboard shortcuts.
On macOS, this requires Accessibility permissions.
"""

import time
from PySide6.QtCore import QObject, Signal, QThread
from pynput import keyboard
import platform


class HotkeyListener(QObject):
    """
    Listens for global hotkeys and emits signals when triggered.

    Hotkeys:
    - Ctrl+F: Toggle recording
    - Ctrl+F double-tap: Stop recording + post-process
    - Ctrl+D: Show diff view (original vs post-processed)
    - Ctrl+Option+F: Transcribe file from clipboard
    - Option+F: Delegation mode
    - Escape: Cancel recording
    """

    hotkey_triggered = Signal()
    file_transcribe_requested = Signal()  # Ctrl+Option+F for file transcription
    escape_pressed = Signal()  # For cancelling recording
    delegation_requested = Signal()  # Option+F for delegation mode
    post_process_requested = Signal()  # Double Ctrl+F to post-process
    diff_view_requested = Signal()  # Ctrl+D to show diff

    def __init__(self, hotkey: str = "<ctrl>+f", parent=None):
        super().__init__(parent)

        self._hotkey_str = hotkey
        self._listener = None
        self._is_listening = False

        # Track key states for combination detection
        self._ctrl_pressed = False
        self._option_pressed = False  # Option/Alt key
        self._hotkey_active = False

        # Double-tap detection for Ctrl+F
        self._last_ctrl_f_time = 0.0
        self._double_tap_window = 0.6  # seconds

    def start(self):
        """Start listening for the global hotkey"""
        if self._is_listening:
            print("[Hotkey] Already listening")
            return

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._listener.start()
            self._is_listening = True
            print(f"[Hotkey] Listening for {self._hotkey_str}")

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
        self._option_pressed = False
        self._hotkey_active = False
        print("[Hotkey] Stopped listening")

    def _on_key_press(self, key):
        """Handle key press events"""
        try:
            # Check for Escape key
            if key == keyboard.Key.esc:
                print("[Hotkey] Escape detected!")
                self.escape_pressed.emit()
                return

            # Check for Ctrl key
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = True
                return

            # Check for Option/Alt key
            if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                self._option_pressed = True
                return

            char = getattr(key, 'char', None)
            vk = getattr(key, 'vk', None)

            # Check for Ctrl+D (diff view)
            if (char and char.lower() == 'd') or vk == 2:  # macOS vk=2 for 'd'
                if self._ctrl_pressed and not self._option_pressed:
                    print("[Hotkey] Ctrl+D detected! (diff view)")
                    self.diff_view_requested.emit()
                    return

            # Check for 'f' key combinations
            # On macOS, Option+F produces 'ƒ' (function symbol)
            if not self._hotkey_active:
                is_f_key = (
                    (char and char.lower() in ('f', 'ƒ')) or
                    vk == 3  # macOS virtual key code for 'f'
                )

                if is_f_key:
                    if self._ctrl_pressed:
                        self._hotkey_active = True
                        if self._option_pressed:
                            print("[Hotkey] Ctrl+Option+F detected! (file transcribe)")
                            self.file_transcribe_requested.emit()
                        else:
                            # Ctrl+F: check for double-tap
                            now = time.time()
                            elapsed = now - self._last_ctrl_f_time
                            self._last_ctrl_f_time = now

                            if elapsed < self._double_tap_window:
                                # Double-tap: post-process
                                print(f"[Hotkey] Double Ctrl+F detected! ({elapsed*1000:.0f}ms gap, post-process)")
                                self.post_process_requested.emit()
                            else:
                                # Single tap: normal toggle
                                print("[Hotkey] Ctrl+F detected! (toggle recording)")
                                self.hotkey_triggered.emit()
                    elif self._option_pressed:
                        self._hotkey_active = True
                        print("[Hotkey] Option+F detected! (delegation mode)")
                        self.delegation_requested.emit()

        except AttributeError:
            pass

    def _on_key_release(self, key):
        """Handle key release events"""
        try:
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = False
                self._hotkey_active = False

            if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                self._option_pressed = False

            char = getattr(key, 'char', None)
            vk = getattr(key, 'vk', None)
            if (char and char.lower() in ('f', 'ƒ')) or vk == 3:
                self._hotkey_active = False

        except AttributeError:
            pass

    def _check_macos_permissions(self):
        """Check and warn about macOS accessibility permissions"""
        try:
            print("[Hotkey] macOS detected - ensure Accessibility permission is granted")
            print("[Hotkey] Go to: System Preferences > Privacy & Security > Accessibility")
            print("[Hotkey] Add Terminal (or Python) to the allowed apps")
        except Exception:
            pass

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    def set_hotkey(self, hotkey: str):
        """Change the hotkey combination."""
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
                return False

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
                return False

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

    def on_post_process():
        print(">>> DOUBLE-TAP: POST-PROCESS! <<<")

    def on_diff():
        print(">>> DIFF VIEW! <<<")

    listener.hotkey_triggered.connect(on_hotkey)
    listener.post_process_requested.connect(on_post_process)
    listener.diff_view_requested.connect(on_diff)
    listener.start()

    print("Press Ctrl+F to trigger hotkey. Double Ctrl+F for post-process. Ctrl+D for diff. Ctrl+C to exit.")

    sys.exit(app.exec())
