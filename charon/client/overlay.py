"""
charon/client/overlay.py
System Version: v3.5.0 | File Revision: 3.5.0

Module: Native GTK4 Desktop HUD Overlay with comic book speech bubble interjections,
Wheatley aperture core visualizer, and cursor gaze tracking.
"""

import os
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
is_gnome = any(de in desktop_env for de in ["gnome", "ubuntu"])

Gtk4LayerShell = None
if not is_gnome:
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell  # type: ignore # noqa: F401
    except (ValueError, ImportError):
        Gtk4LayerShell = None

from gi.repository import Gdk, Gtk

from charon.client.avatar_widget import AvatarVisualizer
from charon.client.ws_listener import OverlayWSListener
from charon.config import CHARON_API_KEY


class ComicSpeechBubble(Gtk.Box):
    """Comic Book Style Speech Bubble with directional tail pointing left toward Avatar."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("comic-speech-bubble")
        self.set_valign(Gtk.Align.CENTER)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.title_label = Gtk.Label(label="Charon Concierge")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.add_css_class("bubble-title")
        self.title_label.set_hexpand(True)

        collapse_btn = Gtk.Button.new_from_icon_name("window-minimize-symbolic")
        collapse_btn.add_css_class("collapse-btn")
        collapse_btn.connect("clicked", lambda x: self.set_visible(False))

        header_box.append(self.title_label)
        header_box.append(collapse_btn)

        self.content_label = Gtk.Label(label="")
        self.content_label.set_halign(Gtk.Align.START)
        self.content_label.set_wrap(True)
        self.content_label.set_max_width_chars(32)
        self.content_label.add_css_class("bubble-text")

        self.append(header_box)
        self.append(self.content_label)

    def set_text(self, text: str):
        self.content_label.set_text(text)


class CharonOverlayWindow(Gtk.Window):
    """HUD Overlay Window featuring Wheatley Core Visualizer and Cursor Gaze Tracking."""

    MESSAGE_ICONS = {
        "inbox": "mail-unread-symbolic",
        "warning": "dialog-warning-symbolic",
        "thought": "dialog-information-symbolic",
        "urgent": "emblem-important-symbolic",
    }

    def __init__(self, app: Gtk.Application):
        super().__init__(application=app)
        self.set_title("Charon Concierge Overlay")
        self.set_default_size(420, 160)

        use_layer_shell = Gtk4LayerShell is not None and Gtk4LayerShell.is_supported()

        if use_layer_shell:
            Gtk4LayerShell.init_for_window(self)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
            Gtk4LayerShell.set_namespace(self, "charon-concierge-hud")
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, True)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, 24)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 24)
            Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
        else:
            self.set_decorated(False)
            self.set_resizable(False)

        # Root Horizontal Container
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.main_box.set_margin_top(12)
        self.main_box.set_margin_bottom(12)
        self.main_box.set_margin_start(12)
        self.main_box.set_margin_end(12)

        # 1. Avatar Orb Stack with Indicator Badge
        self.avatar_overlay = Gtk.Overlay()

        self.avatar = AvatarVisualizer()
        self.avatar.set_cursor_from_name("grab")
        self._setup_avatar_drag_feedback()
        self.avatar_overlay.set_child(self.avatar)

        # Indicator Badge resting directly on Orb surface
        self.badge_button = Gtk.Button()
        self.badge_button.add_css_class("indicator-badge")
        self.badge_image = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        self.badge_button.set_child(self.badge_image)
        self.badge_button.set_halign(Gtk.Align.END)
        self.badge_button.set_valign(Gtk.Align.START)
        self.badge_button.set_margin_end(14)
        self.badge_button.set_margin_top(14)
        self.badge_button.connect("clicked", self._toggle_thought_bubble)

        self.avatar_overlay.add_overlay(self.badge_button)
        self.main_box.append(self.avatar_overlay)

        # 2. Comic Book Speech Bubble (Collapsed by default)
        self.bubble = ComicSpeechBubble()
        self.bubble.set_visible(False)
        self.main_box.append(self.bubble)

        # Native Dragging Container Wrapper
        self.window_handle = Gtk.WindowHandle()
        self.window_handle.set_child(self.main_box)
        self.set_child(self.window_handle)

        # 3. Mouse Event Controller for Window-Wide Gaze Tracking
        motion_ctrl = Gtk.EventControllerMotion.new()
        motion_ctrl.connect("motion", self._on_mouse_motion)
        motion_ctrl.connect("leave", self._on_mouse_leave)
        self.add_controller(motion_ctrl)

        self._apply_css()

        # Connect WebSocket Stream Listener
        ws_uri = "ws://localhost:8000/v1/concierge/stream?client_id=gtk_overlay"
        if CHARON_API_KEY:
            ws_uri += f"&api_key={CHARON_API_KEY}"

        self.ws_thread = OverlayWSListener(
            uri=ws_uri,
            api_key=CHARON_API_KEY,
            on_event_callback=self.handle_stream_event
        )
        self.ws_thread.start()

    def _on_mouse_motion(self, controller, x, y):
        """Tracks mouse cursor coordinates across overlay window and dispatches gaze signal."""
        self.avatar.set_target_gaze(x, y, self.get_width(), self.get_height())

    def _on_mouse_leave(self, controller):
        """Resets eye gaze back to idle center when mouse leaves window bounds."""
        self.avatar.reset_gaze_to_idle()

    def _toggle_thought_bubble(self, button):
        is_visible = self.bubble.get_visible()
        self.bubble.set_visible(not is_visible)

    def set_indicator_type(self, msg_type: str):
        icon_name = self.MESSAGE_ICONS.get(msg_type, "dialog-information-symbolic")
        self.badge_image.set_from_icon_name(icon_name)

    def _setup_avatar_drag_feedback(self):
        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(1)
        click_gesture.connect(
            "pressed",
            lambda gesture, n_press, x, y: self.avatar.set_cursor_from_name("grabbing")
        )
        click_gesture.connect(
            "released",
            lambda gesture, n_press, x, y: self.avatar.set_cursor_from_name("grab")
        )
        self.avatar.add_controller(click_gesture)

    def handle_stream_event(self, event: dict):
        """Handles stream events and updates expressive aperture core states."""
        payload = event.get("payload", {})

        state_name = payload.get("state", "expressing")
        category = payload.get("category", "thought")

        if category in ("warning", "urgent"):
            self.avatar.set_expressive_state("alert")
        elif "text" in payload:
            self.avatar.set_expressive_state(state_name if state_name in AvatarVisualizer.EXPRESSIVE_STATES else "expressing")
        else:
            self.avatar.set_expressive_state("observing")

        self.set_indicator_type(category)

        if "text" in payload:
            text = payload["text"]
            self.bubble.set_text(text)
            self.bubble.set_visible(True)

    def _apply_css(self):
        """Applies transparent canvas styling and glowing comic speech bubble CSS."""
        css_provider = Gtk.CssProvider()
        css = """
        window {
            background-color: transparent;
            box-shadow: none;
        }

        .comic-speech-bubble {
            background-color: rgba(15, 23, 42, 0.92);
            border: 2px solid #38BDF8;
            border-radius: 16px;
            padding: 12px 16px;
            box-shadow: 0px 8px 24px rgba(0, 0, 0, 0.6), 0px 0px 14px rgba(56, 189, 248, 0.4);
        }

        .bubble-title {
            font-weight: bold;
            font-size: 12px;
            color: #38BDF8;
            letter-spacing: 0.5px;
        }

        .bubble-text {
            font-size: 13px;
            color: #F8FAFC;
        }

        .indicator-badge {
            background-color: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(56, 189, 248, 0.7);
            border-radius: 50%;
            min-width: 20px;
            min-height: 20px;
            padding: 2px;
            box-shadow: 0px 0px 10px rgba(56, 189, 248, 0.6);
        }

        .indicator-badge:hover {
            background-color: rgba(30, 41, 59, 0.95);
            border-color: #F472B6;
            box-shadow: 0px 0px 12px rgba(244, 114, 182, 0.8);
        }

        .collapse-btn {
            background: transparent;
            border: none;
            padding: 0px;
            min-width: 16px;
            min-height: 16px;
            opacity: 0.7;
        }

        .collapse-btn:hover {
            opacity: 1.0;
        }
        """
        css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def main():
    app = Gtk.Application(application_id="com.charon.concierge.overlay")

    def on_activate(app_instance):
        win = CharonOverlayWindow(app_instance)
        win.present()

    app.connect("activate", on_activate)
    app.run(sys.argv)


if __name__ == "__main__":
    main()