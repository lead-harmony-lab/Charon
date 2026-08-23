import os
import urllib.parse
import webbrowser
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, Gio, GLib
from charon.config.paths import CHARON_ENV_FILE

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
except (ValueError, ImportError):
    Gtk4LayerShell = None


class AvatarContextMenu:
    """Manages the right-click popover menu and window state actions for the Avatar."""

    def __init__(self, window: Gtk.Window, target_widget: Gtk.Widget):
        self.window = window
        self.target_widget = target_widget
        self._last_event = None  # Cache event for Wayland security rules

        # 1. Define the menu model
        menu = Gio.Menu.new()
        menu.append("Command Center V2", "win.open_dashboard")
        menu.append("Settings (Coming Soon)", "win.dummy")
        menu.append("System Window Controls...", "win.show_sys_menu")

        # 2. Create PopoverMenu attached to target widget
        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.popover.set_parent(self.target_widget)
        self.popover.set_has_arrow(False)

        # 3. Register actions
        action_dashboard = Gio.SimpleAction.new("open_dashboard", None)
        action_dashboard.connect("activate", self._on_open_dashboard)
        self.window.add_action(action_dashboard)

        action_dummy = Gio.SimpleAction.new("dummy", None)
        self.window.add_action(action_dummy)

        action_sys_menu = Gio.SimpleAction.new("show_sys_menu", None)
        action_sys_menu.connect("activate", self._on_show_sys_menu)
        self.window.add_action(action_sys_menu)

        # 4. Right-click gesture controller
        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)
        right_click.connect("pressed", self._on_target_right_click)
        self.target_widget.add_controller(right_click)

    def _on_target_right_click(self, gesture, n_press, x, y):
        seq = gesture.get_current_sequence()
        self._last_event = gesture.get_last_event(seq)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1

        self.popover.set_pointing_to(rect)
        self.popover.popup()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def _on_open_dashboard(self, action, param):
        """Hides the menu and launches Dashboard V2 auto-authenticated."""
        self.popover.popdown()

        base_url = os.getenv("CHARON_DASHBOARD_URL", "http://localhost:8000")
        api_key = os.getenv("CHARON_API_KEY", "")

        # Parse XDG env file if not set in active shell environment
        if not api_key and CHARON_ENV_FILE.exists():
            try:
                with open(CHARON_ENV_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or not line:
                            continue
                        if line.startswith("CHARON_API_KEY="):
                            api_key = line.split("=", 1)[1].strip(' "\'')
                            break
            except Exception as e:
                print(f"[Charon.Avatar] Warning: Failed to parse {CHARON_ENV_FILE}: {e}")

        # Construct full V2 Dashboard authentication URL
        if api_key:
            encoded_key = urllib.parse.quote(api_key)
            full_url = f"{base_url.rstrip('/')}/?api_key={encoded_key}"
        else:
            full_url = base_url

        # Native GTK non-blocking browser dispatch with fallback
        try:
            Gtk.show_uri(self.window, full_url, Gdk.CURRENT_TIME)
        except Exception:
            webbrowser.open(full_url)

    def _on_show_sys_menu(self, action, param):
        self.popover.popdown()
        native = self.window.get_native()
        if not native:
            return

        surface = native.get_surface()
        if surface and isinstance(surface, Gdk.Toplevel) and self._last_event:
            surface.show_window_menu(self._last_event)