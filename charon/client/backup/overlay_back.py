"""
charon/client/overlay.py
System Version: v3.9.0 | File Revision: 3.9.13

Module: Native GTK4 Desktop HUD Overlay with comic book speech bubble interjections,
Wheatley aperture core visualizer, cursor gaze tracking, and click-through regions.
"""

import argparse
import base64
import cairo
import json
import os
import signal
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

from gi.repository import Gdk, GLib, Gtk

# Import the wrapper widget to preserve do_contains hit-testing behavior
from charon.client.avatar_widget import AvatarVisualizer, AvatarWidget
from charon.client.ws_listener import OverlayWSListener
from charon.client.avatar_states import EXPRESSIVE_STATES
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

        self.connect("realize", lambda win: self._on_realize())

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # --- AVATAR CONTAINER LAYOUT ---
        self.avatar_overlay = Gtk.Overlay()

        self.avatar_container = AvatarWidget()
        self.avatar = self.avatar_container.visualizer
        self.avatar_container.set_cursor_from_name("grab")
        self._setup_avatar_drag_feedback()

        # Transparent padding container to offset layout coordinates
        self.avatar_align_box = Gtk.Box()
        self.avatar_align_box.set_margin_top(25)
        self.avatar_align_box.set_margin_end(35)
        self.avatar_align_box.append(self.avatar_container)

        self.avatar_overlay.set_child(self.avatar_align_box)

        # The badge button overlay
        self.badge_button = Gtk.Button()
        self.badge_button.add_css_class("speech-bubble-btn")
        self.badge_button.set_halign(Gtk.Align.END)
        self.badge_button.set_valign(Gtk.Align.START)
        self.badge_button.set_margin_end(14)
        self.badge_button.set_margin_top(14)
        self.badge_button.connect("clicked", self._toggle_thought_bubble)

        self.avatar_overlay.add_overlay(self.badge_button)
        self.main_box.append(self.avatar_overlay)

        # Comic Book Speech Bubble
        self.bubble = ComicSpeechBubble()
        self.bubble.set_visible(False)
        self.bubble.set_margin_start(12)
        self.main_box.append(self.bubble)

        self.set_child(self.main_box)
        self._apply_css()

        # Update input shape when speech bubble visibility toggles
        self.bubble.connect("notify::visible", lambda *args: GLib.idle_add(self.update_input_region))

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

    def _on_realize(self):
        """Triggered when GDK surface is created."""
        self._restore_position_if_saved()
        GLib.idle_add(self.update_input_region)

    def update_input_region(self):
        """Update Wayland input region so empty space passes clicks through to desktop."""
        native = self.get_native()
        if not native:
            return
        surface = native.get_surface()
        if not surface:
            return

        region = cairo.Region()

        # 1. Add specific visible Avatar bounds (bypassing transparent margin boxes)
        res, avatar_rect = self.avatar_container.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(avatar_rect.origin.x),
                int(avatar_rect.origin.y),
                int(avatar_rect.size.width),
                int(avatar_rect.size.height)
            ))

        # 2. Add Badge Button bounds independently
        res, badge_rect = self.badge_button.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(badge_rect.origin.x),
                int(badge_rect.origin.y),
                int(badge_rect.size.width),
                int(badge_rect.size.height)
            ))

        # 3. Add Speech Bubble bounds if visible
        if self.bubble.get_visible():
            res, bubble_rect = self.bubble.compute_bounds(self)
            if res:
                region.union(cairo.RectangleInt(
                    int(bubble_rect.origin.x),
                    int(bubble_rect.origin.y),
                    int(bubble_rect.size.width),
                    int(bubble_rect.size.height)
                ))

        # Apply the exact mask to the Wayland/X11 surface
        surface.set_input_region(region)

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
        GLib.idle_add(self.update_input_region)

    def set_indicator_type(self, msg_type: str):
        self.badge_button.remove_css_class("indicator-warning")
        self.badge_button.remove_css_class("indicator-urgent")
        self.badge_button.remove_css_class("indicator-inbox")

        if msg_type == "warning":
            self.badge_button.add_css_class("indicator-warning")
        elif msg_type == "urgent":
            self.badge_button.add_css_class("indicator-urgent")
        elif msg_type == "inbox":
            self.badge_button.add_css_class("indicator-inbox")

    def _setup_avatar_drag_feedback(self):
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
                win_w = self.get_width()
                win_h = self.get_height()
                avatar_w = self.avatar_container.get_width()
                avatar_h = self.avatar_container.get_height()

                win_top_left_x = float(window_center["x"]) - (win_w / 2.0)
                win_top_left_y = float(window_center["y"]) - (win_h / 2.0)

                eye_center_x = win_top_left_x + (avatar_w / 2.0)
                eye_center_y = win_top_left_y + 15.0 + (avatar_h / 2.0)

                self.avatar.set_target_gaze_relative(
                    mouse_x=float(cursor["x"]),
                    mouse_y=float(cursor["y"]),
                    center_x=eye_center_x,
                    center_y=eye_center_y,
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
                state_name if state_name in EXPRESSIVE_STATES else "expressing")
        else:
            self.avatar.set_expressive_state("observing")

        self.set_indicator_type(category)

        if "text" in payload:
            text = payload["text"]
            self.bubble.set_text(text)
            self.bubble.set_visible(True)
            GLib.idle_add(self.update_input_region)

    def _apply_css(self):
        def get_svg_uri(stroke_color: str, fill_color: str = "rgba(15, 23, 42, 0.92)") -> str:
            svg = f"""<svg viewBox="69 78 85 50" xmlns="http://www.w3.org/2000/svg">
              <path fill="{fill_color}" stroke="{stroke_color}" stroke-width="2"
                    d="m 76.03705,79.224564 h 70.86015 c 3.13351,0 5.65615,2.522644 5.65615,5.656152 v 15.218714 c 0,3.13351 -2.52264,5.65615 -5.65615,5.65615 H 89.675042 l -19.478391,20.63523 6.816997,-20.63523 H 76.03705 c -3.133509,0 -5.656152,-2.52264 -5.656152,-5.65615 V 84.880716 c 0,-3.133508 2.522643,-5.656152 5.656152,-5.656152 z"/>
            </svg>"""
            b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
            return f"url('data:image/svg+xml;base64,{b64}')"

        css_provider = Gtk.CssProvider()
        css = f"""
        window {{
            background-color: transparent;
            box-shadow: none;
        }}

        .comic-speech-bubble {{
            background-color: rgba(15, 23, 42, 0.92);
            border: 2px solid #38BDF8;
            border-radius: 16px;
            padding: 12px 16px;
            box-shadow: 0px 8px 24px rgba(0, 0, 0, 0.6), 0px 0px 14px rgba(56, 189, 248, 0.4);
        }}

        .bubble-title {{
            font-weight: bold;
            font-size: 12px;
            color: #38BDF8;
            letter-spacing: 0.5px;
        }}

        .bubble-text {{
            font-size: 13px;
            color: #F8FAFC;
        }}

        .speech-bubble-btn {{
            background-image: {get_svg_uri("#38BDF8")};
            background-size: contain;
            background-repeat: no-repeat;
            background-position: center;
            background-color: transparent;
            border: none;
            min-width: 50px;
            min-height: 30px; 
            padding: 0px;
            box-shadow: none;
            transition: all 0.2s ease-in-out;
            filter: drop-shadow(0px 0px 4px rgba(56, 189, 248, 0.8));
        }}
        
        .speech-bubble-btn:hover {{
            background-image: {get_svg_uri("#F472B6")};
            filter: drop-shadow(0px 0px 6px rgba(244, 114, 182, 1.0));
        }}
        
        .indicator-warning {{
            background-image: {get_svg_uri("#FBBF24")};
            filter: drop-shadow(0px 0px 5px rgba(251, 191, 36, 0.9));
        }}

        .indicator-urgent {{
            background-image: {get_svg_uri("#EF4444")};
            filter: drop-shadow(0px 0px 5px rgba(239, 68, 68, 0.9));
        }}

        .indicator-inbox {{
            background-image: {get_svg_uri("#A855F7")};
            filter: drop-shadow(0px 0px 5px rgba(168, 85, 247, 0.9));
        }}

        .collapse-btn {{
            background: transparent;
            border: none;
            padding: 0px;
            min-width: 16px;
            min-height: 16px;
            opacity: 0.7;
        }}

        .collapse-btn:hover {{
            opacity: 1.0;
        }}
        """
        css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def main():
    parser = argparse.ArgumentParser(description="Charon Concierge Overlay")
    parser.add_argument("--map-width", type=float, default=None, help="Total desktop stage width")
    parser.add_argument("--map-height", type=float, default=None, help="Total desktop stage height")
    args, residual_args = parser.parse_known_args()

    app = Gtk.Application(application_id="com.charon.concierge.overlay")

    def on_activate(app_instance):
        map_w = args.map_width
        map_h = args.map_height

        if map_w is None or map_h is None:
            display = Gdk.Display.get_default()
            max_x, max_y = 0, 0

            if display:
                monitors = display.get_monitors()
                for i in range(monitors.get_n_items()):
                    monitor = monitors.get_item(i)
                    geom = monitor.get_geometry()

                    right_edge = geom.x + geom.width
                    bottom_edge = geom.y + geom.height

                    if right_edge > max_x: max_x = right_edge
                    if bottom_edge > max_y: max_y = bottom_edge

            if map_w is None:
                map_w = float(max_x) if max_x > 0 else 1920.0
            if map_h is None:
                map_h = float(max_y) if max_y > 0 else 1080.0

        win = CharonOverlayWindow(
            app=app_instance,
            map_width=map_w,
            map_height=map_h
        )
        win.present()

    app.connect("activate", on_activate)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.run([sys.argv[0]] + residual_args)


if __name__ == "__main__":
    main()