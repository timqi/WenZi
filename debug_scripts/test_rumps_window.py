"""Minimal test to debug rumps.Window in menu callbacks."""

import rumps
from AppKit import NSApp, NSApplication


class TestApp(rumps.App):
    def __init__(self):
        super().__init__("Test", title="T")

        self.menu = [
            rumps.MenuItem("Alert (no fix)", callback=self._on_alert_raw),
            rumps.MenuItem("Alert (with policy)", callback=self._on_alert_fix),
            rumps.MenuItem("Window (with policy)", callback=self._on_window_fix),
        ]

    def _activate_for_dialog(self):
        """Set activation policy so modal dialogs can show."""
        NSApp.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
        NSApp.activateIgnoringOtherApps_(True)

    def _restore_accessory(self):
        """Restore accessory policy (statusbar-only)."""
        NSApp.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    def _on_alert_raw(self, _):
        print("[raw] callback fired", flush=True)
        result = rumps.alert("Test", "No fix applied")
        print(f"[raw] result: {result}", flush=True)

    def _on_alert_fix(self, _):
        print("[fix] callback fired", flush=True)
        self._activate_for_dialog()
        result = rumps.alert("Test", "With activation policy fix")
        self._restore_accessory()
        print(f"[fix] result: {result}", flush=True)

    def _on_window_fix(self, _):
        print("[window] callback fired", flush=True)
        self._activate_for_dialog()
        w = rumps.Window("Test Window", "Enter text:", "hello", ok="OK", cancel="Cancel")
        resp = w.run()
        self._restore_accessory()
        print(f"[window] clicked={resp.clicked}, text={resp.text}", flush=True)


if __name__ == "__main__":
    TestApp().run()
