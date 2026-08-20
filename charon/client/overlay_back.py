"""
charon/client/overlay.py
System Version: v3.9.0 | File Revision: 3.9.9

Module: Native GTK4 Desktop HUD Overlay with comic book speech bubble interjections,
Wheatley aperture core visualizer, cursor gaze tracking, and click-through regions.
"""

import argparse
import json
import os
import sys
from pathlib import Path

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

from gi.repository import Gdk, Gtk, GLib

# Import the wrapper widget to preserve do_contains hit-testing behavior
from charon.client.avatar_widget import AvatarVisualizer, AvatarWidget
from charon.client.ws_listener import OverlayWSListener
from charon.config import CHARON_API_KEY


class OverlaySettings:
    """Manages JSON configuration and window bounds state stored alongside overlay.py."""

    def __init__(self, filename: str = "settings.json"):
        self.filepath = Path(__file__).resolve().parent / filename
        self.data = self._load()

    def _load(self) -> dict:
        if not self.filepath.exists():
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            print(f"[Charon] Failed to load settings: {e}")
            return {}

    def _save(self, data: dict) -> dict:
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"[Charon] Failed to save settings: {e}")
        return data

    def update(self, **kwargs):
        self.data.update(kwargs)
        self._save(self.data)

    def get(self, key, default=None):
        return self.data.get(key, default)


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

    def __init__(self, app: Gtk.Application, map_width: float = 1920.0, map_height: float = 1080.0):
        super().__init__(application=app)

        self.settings = OverlaySettings()
        self.map_width = map_width
        self.map_height = map_height

        self._pending_telemetry = None
        self._telemetry_idle_queued = False

        self.settings.update(map_width=map_width, map_height=map_height)
        self.set_title("Charon Concierge Overlay")

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

        self.connect("realize", lambda win: self._restore_position_if_saved())

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.main_box.set_margin_top(0)
        self.main_box.set_margin_bottom(0)
        self.main_box.set_margin_start(0)
        self.main_box.set_margin_end(0)

        # 1. Avatar Container
        self.avatar_overlay = Gtk.Overlay()
        self.avatar_container = AvatarWidget()
        self.avatar = self.avatar_container.visualizer

        self.avatar_container.set_cursor_from_name("grab")
        self._setup_avatar_drag_feedback()
        self.avatar_overlay.set_child(self.avatar_container)

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

        # We append the overlay directly. Gtk.WindowHandle is entirely removed to
        # stop it from creating a rectangular hit-box and capturing scroll events.
        self.main_box.append(self.avatar_overlay)

        # 2. Comic Book Speech Bubble
        self.bubble = ComicSpeechBubble()
        self.bubble.set_visible(False)
        self.bubble.set_margin_start(12)
        self.main_box.append(self.bubble)

        self.set_child(self.main_box)
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

    def get_settings(self) -> OverlaySettings:
        return self.settings

    def clamp_coordinates(self, x: float, y: float) -> tuple[int, int]:
        win_w = self.get_width() if self.get_width() > 0 else 150
        win_h = self.get_height() if self.get_height() > 0 else 150

        max_x = max(0, int(self.map_width - win_w))
        max_y = max(0, int(self.map_height - win_h))

        clamped_x = max(0, min(int(x), max_x))
        clamped_y = max(0, min(int(y), max_y))

        return clamped_x, clamped_y

    def _apply_position(self, x: int, y: int):
        use_layer_shell = Gtk4LayerShell is not None and Gtk4LayerShell.is_supported()
        if use_layer_shell:
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, x)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, y)
        else:
            native = self.get_native()
            surface = native.get_surface() if native else None
            if surface:
                try:
                    from gi.repository import GdkX11
                    if isinstance(surface, GdkX11.X11Surface):
                        surface.move(x, y)
                except (ImportError, TypeError, AttributeError):
                    pass

    def _restore_position_if_saved(self):
        saved_x = self.settings.get("x")
        saved_y = self.settings.get("y")

        if saved_x is None or saved_y is None:
            return

        clamped_x, clamped_y = self.clamp_coordinates(saved_x, saved_y)
        self._apply_position(clamped_x, clamped_y)

    def _toggle_thought_bubble(self, button):
        is_visible = self.bubble.get_visible()
        self.bubble.set_visible(not is_visible)

    def set_indicator_type(self, msg_type: str):
        icon_name = self.MESSAGE_ICONS.get(msg_type, "dialog-information-symbolic")
        self.badge_image.set_from_icon_name(icon_name)

    def _setup_avatar_drag_feedback(self):
        # Natively handles dragging while completely ignoring scrolls and respecting
        # the precise visual bounds of the AvatarWidget's do_contains method.
        drag_gesture = Gtk.GestureDrag.new()
        drag_gesture.set_button(1)

        def on_drag_begin(gesture, start_x, start_y):
            native = self.avatar_container.get_native()
            if not native: return

            surface = native.get_surface()
            if surface and isinstance(surface, Gdk.Toplevel):
                seq = gesture.get_current_sequence()
                event = gesture.get_last_event(seq)
                if event:
                    # Pass off to the window manager explicitly
                    surface.begin_move(
                        event.get_device(),
                        1,
                        start_x,
                        start_y,
                        event.get_time()
                    )
                    gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                    self.avatar_container.set_cursor_from_name("grabbing")

        def on_drag_end(gesture, offset_x, offset_y):
            self.avatar_container.set_cursor_from_name("grab")

        drag_gesture.connect("drag-begin", on_drag_begin)
        drag_gesture.connect("drag-end", on_drag_end)
        self.avatar_container.add_controller(drag_gesture)

        # Retain standard clicking feedback
        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(1)
        click_gesture.connect("pressed", lambda g, n, x, y: self.avatar_container.set_cursor_from_name("grabbing"))
        click_gesture.connect("released", lambda g, n, x, y: self.avatar_container.set_cursor_from_name("grab"))
        self.avatar_container.add_controller(click_gesture)

    def handle_stream_event(self, event: dict):
        if event.get("event_type") == "pointer_telemetry":
            if event.get("data", {}).get("action"):
                GLib.idle_add(self._process_stream_event_ui, event)
                return

            self._pending_telemetry = event
            if not self._telemetry_idle_queued:
                self._telemetry_idle_queued = True
                GLib.idle_add(self._flush_telemetry)
        else:
            GLib.idle_add(self._process_stream_event_ui, event)

    def _flush_telemetry(self):
        self._telemetry_idle_queued = False
        if self._pending_telemetry:
            self._process_stream_event_ui(self._pending_telemetry)
            self._pending_telemetry = None
        return False

    def _process_stream_event_ui(self, event: dict):
        if event.get("event_type") == "pointer_telemetry":
            data = event.get("data", {})
            cursor = data.get("cursor", {})
            window_center = data.get("window_center")

            if cursor and window_center and "x" in cursor and "y" in cursor and "x" in window_center and "y" in window_center:
                self.avatar.set_target_gaze_relative(
                    mouse_x=float(cursor["x"]),
                    mouse_y=float(cursor["y"]),
                    center_x=float(window_center["x"]),
                    center_y=float(window_center["y"]),
                    map_width=self.map_width,
                    map_height=self.map_height,
                )

                if data.get("action") == "click":
                    self.avatar.set_expressive_state("alert")
            return

        payload = event.get("payload", {})
        state_name = payload.get("state", "expressing")
        category = payload.get("category", "thought")

        if category in ("warning", "urgent"):
            self.avatar.set_expressive_state("alert")
        elif "text" in payload:
            self.avatar.set_expressive_state(
                state_name if state_name in AvatarVisualizer.EXPRESSIVE_STATES else "expressing")
        else:
            self.avatar.set_expressive_state("observing")

        self.set_indicator_type(category)

        if "text" in payload:
            text = payload["text"]
            self.bubble.set_text(text)
            self.bubble.set_visible(True)

    def _apply_css(self):
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
    parser = argparse.ArgumentParser(description="Charon Concierge Overlay")
    parser.add_argument("--map-width", type=float, default=1920.0, help="Total desktop stage width")
    parser.add_argument("--map-height", type=float, default=1080.0, help="Total desktop stage height")
    args, residual_args = parser.parse_known_args()

    app = Gtk.Application(application_id="com.charon.concierge.overlay")

    def on_activate(app_instance):
        win = CharonOverlayWindow(
            app=app_instance,
            map_width=args.map_width,
            map_height=args.map_height
        )
        win.present()

    app.connect("activate", on_activate)
    app.run([sys.argv[0]] + residual_args)


if __name__ == "__main__":
    main()