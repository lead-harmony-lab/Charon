"""
charon/client/overlay.py
System Version: v3.9.0 | File Revision: 3.9.16

Module: Native GTK4 Desktop HUD Overlay with elastic speech badge interjections,
Wheatley aperture core visualizer, cursor gaze tracking, and click-through regions.
"""

import argparse
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
from charon.client.elastic_badge import ElasticBadge


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

        # Primary Spatial Container
        self.avatar_overlay = Gtk.Overlay()

        self.avatar_container = AvatarWidget()
        self.avatar = self.avatar_container.visualizer
        self.avatar_container.set_cursor_from_name("grab")

        self._setup_avatar_drag_feedback()

        # Transparent padding container to offset layout coordinates
        # We enforce a permanent runway here so the badge has room to expand to 250x120
        # without triggering Wayland window resizes.
        self.avatar_align_box = Gtk.Box()
        self.avatar_align_box.set_margin_top(130)  # Runway for height expansion
        self.avatar_align_box.set_margin_end(260)  # Runway for width expansion

        self.avatar_align_box.append(self.avatar_container)
        self.avatar_overlay.set_child(self.avatar_align_box)

        # The Elastic Badge Component
        self.badge = ElasticBadge()
        self.badge.set_halign(Gtk.Align.END)
        self.badge.set_valign(Gtk.Align.END)
        self.badge.set_margin_end(14)
        self.badge.set_margin_bottom(14)
        self.badge.connect("clicked", self._on_badge_clicked)

        self.avatar_overlay.add_overlay(self.badge)
        self.set_child(self.avatar_overlay)

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

    def _queue_input_region_update(self, *args):
        """
        Wait 50ms for GTK's layout engine to finish shifting widgets
        before recalculating the Wayland click-through input boundaries.
        """
        GLib.timeout_add(50, self.update_input_region)

    def _on_realize(self):
        self._restore_position_if_saved()
        self._queue_input_region_update()

    def update_input_region(self):
        native = self.get_native()
        if not native:
            return
        surface = native.get_surface()
        if not surface:
            return

        region = cairo.Region()

        # 1. Avatar Click Region
        res, avatar_rect = self.avatar_container.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(avatar_rect.origin.x),
                int(avatar_rect.origin.y),
                int(avatar_rect.size.width),
                int(avatar_rect.size.height)
            ))

        # 2. Dynamic Elastic Badge Click Region
        # Because ElasticBadge scales natively in GTK, compute_bounds instantly
        # fetches the new 250x120 box when expanded.
        res, badge_rect = self.badge.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(badge_rect.origin.x),
                int(badge_rect.origin.y),
                int(badge_rect.size.width),
                int(badge_rect.size.height)
            ))

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

    def _on_badge_clicked(self, button):
        # Collapse the badge when clicked and recalculate Wayland bounds
        self.badge.collapse()
        self._queue_input_region_update()

    def set_indicator_type(self, msg_type: str):
        self.badge.remove_css_class("indicator-warning")
        self.badge.remove_css_class("indicator-urgent")
        self.badge.remove_css_class("indicator-inbox")
        if msg_type == "warning":
            self.badge.add_css_class("indicator-warning")
        elif msg_type == "urgent":
            self.badge.add_css_class("indicator-urgent")
        elif msg_type == "inbox":
            self.badge.add_css_class("indicator-inbox")

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

                win_top_left_x = float(window_center["x"]) - (win_w / 2.0)
                win_top_left_y = float(window_center["y"]) - (win_h / 2.0)

                res, avatar_rect = self.avatar_container.compute_bounds(self)
                if res:
                    eye_center_x = win_top_left_x + avatar_rect.origin.x + (avatar_rect.size.width / 2.0)
                    eye_center_y = win_top_left_y + avatar_rect.origin.y + (avatar_rect.size.height / 2.0)
                else:
                    avatar_w = self.avatar_container.get_width()
                    avatar_h = self.avatar_container.get_height()
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
            # Trigger the CSS expansion and text injection
            self.badge.show_message(text)
            self._queue_input_region_update()

    def _apply_css(self):
        css_provider = Gtk.CssProvider()

        # Swapped from rigid SVG backgrounds to fluid CSS boundaries to ensure
        # the 300% scale morphs perfectly and respects the border-radius transitions.
        css = """
        window {
            background-color: transparent;
            box-shadow: none;
        }

        .elastic-badge {
            background-color: rgba(15, 23, 42, 0.92);
            border: 2px solid #38BDF8;
            border-radius: 25px;
            min-width: 50px;
            min-height: 50px;
            padding: 0px;
            box-shadow: none;
            
            transform-origin: top right; 
            transition: all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
            filter: drop-shadow(0px 0px 4px rgba(56, 189, 248, 0.8));
        }
        
        .elastic-badge:hover {
            filter: drop-shadow(0px 0px 6px rgba(56, 189, 248, 1.0));
        }

        .elastic-badge.expanded {
            min-width: 250px;
            min-height: 120px;
            padding: 16px;
            border-radius: 16px;
            border-color: #F472B6; 
            background-color: rgba(15, 23, 42, 0.98);
            filter: drop-shadow(0px 0px 8px rgba(244, 114, 182, 0.8));
        }

        .badge-text {
            color: white;
            font-size: 14px;
            transition: opacity 0.3s ease-in-out;
        }

        .indicator-warning {
            border-color: #FBBF24;
            filter: drop-shadow(0px 0px 5px rgba(251, 191, 36, 0.9));
        }

        .indicator-urgent {
            border-color: #EF4444;
            filter: drop-shadow(0px 0px 5px rgba(239, 68, 68, 0.9));
        }

        .indicator-inbox {
            border-color: #A855F7;
            filter: drop-shadow(0px 0px 5px rgba(168, 85, 247, 0.9));
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