import threading
import keyboard

class HotkeyListener:
    def __init__(self, on_mute_callback=None, on_toggle_callback=None):
        self.on_mute_callback = on_mute_callback
        self.on_toggle_callback = on_toggle_callback
        self._running = False

    def start(self):
        """Starts listening for global hotkeys in a background thread."""
        self._running = True

        # Hotkey 1: Press 'F4' or 'Ctrl + Space' to immediately interrupt/mute CYRUS speech
        try:
            keyboard.add_hotkey("f4", self._trigger_mute)
            keyboard.add_hotkey("ctrl+space", self._trigger_mute)
        except Exception as e:
            print(f"[Hotkey Warning - Speech Mute]: {e}")

        # Hotkey 2: Press 'Ctrl + M' or 'F3' to toggle microphone on/off
        if self.on_toggle_callback:
            try:
                keyboard.add_hotkey("ctrl+m", self._trigger_toggle)
                keyboard.add_hotkey("f3", self._trigger_toggle)
            except Exception as e:
                print(f"[Hotkey Warning - Mic Toggle]: {e}")

        print("[System] Global Hotkey Listener active (F4/Ctrl+Space=Stop Speech, F3/Ctrl+M=Mic Toggle).")

    def _trigger_mute(self):
        if self.on_mute_callback:
            print("\n[Hotkey Intercept]: Mute/Stop speech triggered via hotkey.")
            self.on_mute_callback()

    def _trigger_toggle(self):
        if self.on_toggle_callback:
            print("\n[Hotkey Intercept]: Mic Toggle triggered via hotkey.")
            self.on_toggle_callback()

    def stop(self):
        """Removes all global hotkey hooks."""
        if self._running:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            self._running = False
