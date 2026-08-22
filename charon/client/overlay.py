"""
charon/client/overlay.py
System Version: v3.9.0 | File Revision: 3.9.16

Module: Native GTK4 Desktop HUD Overlay with Cairo-drawn dynamic badges,
Wheatley aperture core visualizer, cursor gaze tracking, and click-through regions.
"""

import argparse
import base64
import cairo
import json
import math
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


class DynamicBadge(Gtk.DrawingArea):
    """Cairo-drawn badge serving as the seed for the elastic speech bubble."""

    def __init__(self):
        super().__init__()
        self.set_size_request(70, 60)

        # Semiotic State Defaults (Standard Blue with 4 dots)
        self.glow_color = (0.22, 0.74, 0.97, 1.0)  # #38BDF8
        self.badge_text = "...."

        # GTK4 Drawing Areas need a draw function assigned
        self.set_draw_func(self.on_draw)

        # Click detection
        self.click_gesture = Gtk.GestureClick.new()
        self.click_gesture.set_button(1)
        self.add_controller(self.click_gesture)

    def set_state(self, text: str, r: float, g: float, b: float):
        """Updates both the symbol/text payload and the electric glow color."""
        self.badge_text = text
        self.glow_color = (r, g, b, 1.0)
        self.queue_draw()

    def set_indicator_color(self, r: float, g: float, b: float):
        """Update the Cairo glow color while preserving current text."""
        self.glow_color = (r, g, b, 1.0)
        self.queue_draw()

    def on_draw(self, area, cr, width, height):
        pad = 12
        box_w = width - (pad * 2)
        box_h = height - (pad * 2) - 12  # Reserve 12px at the bottom for the tail
        r = 6.0  # Corner radius

        cr.translate(pad, pad)

        # --- CHASSIS GEOMETRY ---
        cr.move_to(r, 0)
        cr.line_to(box_w - r, 0)
        cr.arc(box_w - r, r, r, -math.pi / 2, 0)
        cr.line_to(box_w, box_h - r)
        cr.arc(box_w - r, box_h - r, r, 0, math.pi / 2)

        cr.line_to(box_w * 0.40, box_h)
        cr.line_to(-6, box_h + 12)
        cr.line_to(box_w * 0.15, box_h)

        cr.line_to(r, box_h)
        cr.arc(r, box_h - r, r, math.pi / 2, math.pi)
        cr.line_to(0, r)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

        # --- ELECTRIC SHADING & GLOW ---
        glow_r, glow_g, glow_b, _ = self.glow_color

        for i in range(4, 0, -1):
            cr.set_source_rgba(glow_r, glow_g, glow_b, 0.15)
            cr.set_line_width(i * 3.0)
            cr.stroke_preserve()

        cr.set_source_rgba(0.06, 0.09, 0.16, 0.95)
        cr.fill_preserve()

        cr.set_source_rgba(*self.glow_color)
        cr.set_line_width(1.5)
        cr.stroke()

        # --- DYNAMIC TEXT RENDERING ---
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(18)

        extents = cr.text_extents(self.badge_text)

        # Center text precisely inside the main badge box (excluding the tail)
        text_x = (box_w / 2.0) - (extents.width / 2.0) - extents.x_bearing
        text_y = (box_h / 2.0) - (extents.height / 2.0) - extents.y_bearing

        # Ambient Text Glow Pass (Matches active color)
        cr.set_source_rgba(glow_r, glow_g, glow_b, 0.6)
        cr.move_to(text_x, text_y)
        cr.show_text(self.badge_text)

        # High-Contrast Core Text Pass
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.move_to(text_x, text_y)
        cr.show_text(self.badge_text)


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
        self.avatar_overlay.set_size_request(600, 400)

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

        # The new Cairo badge aligned to START for dynamic absolute positioning
        self.badge = DynamicBadge()
        self.badge.set_halign(Gtk.Align.START)
        self.badge.set_valign(Gtk.Align.START)
        self.badge.click_gesture.connect(
            "pressed", lambda gesture, n, x, y: self._toggle_thought_bubble()
        )

        self.avatar_overlay.add_overlay(self.badge)
        self.main_box.append(self.avatar_overlay)

        self.set_child(self.main_box)
        self._apply_css()

        # Add the tick callback to dynamically anchor the badge to the eye
        self.add_tick_callback(self._sync_badge_position)

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

    def _sync_badge_position(self, widget, frame_clock):
        """Calculates the center of the eye and positions the speech bubble dynamically."""
        vis = self.avatar
        vw = vis.get_width()
        vh = vis.get_height()

        if vw == 0 or vh == 0:
            return GLib.SOURCE_CONTINUE

        # Body geometry identical to visualizer logic
        cx = vw / 2.0
        cy = vh / 2.0
        r_body = min(vw, vh) * 0.38
        r_bezel = r_body * 0.68
        max_travel = r_bezel * 0.35

        # 1. Obtain the center of Wheatley's eye (clamping travel to bezel constraints)
        dx = vis.current_dx
        dy = vis.current_dy
        dist = math.hypot(dx, dy)

        if dist > max_travel and dist > 0:
            dx = (dx / dist) * max_travel
            dy = (dy / dist) * max_travel

        eye_cx = cx + dx
        eye_cy = cy + dy

        # 2. Position the speech bubble in relation to that location
        # Push out at a 45-degree angle (top-right) from the physical eye center
        angle = -math.pi / 4.0

        # Target the outer edge of the chassis shell, stretching slightly past it
        touch_x = eye_cx + math.cos(angle) * (r_body * 1.05)
        touch_y = eye_cy + math.sin(angle) * (r_body * 1.05)

        # Apply layout offsets from the avatar_align_box container
        touch_x += self.avatar_align_box.get_margin_start()
        touch_y += self.avatar_align_box.get_margin_top()

        # 3. Align the tip of the badge's tail to this exact touch point
        badge_w = self.badge.get_width()
        badge_h = self.badge.get_height()
        if badge_w == 0: badge_w = 70
        if badge_h == 0: badge_h = 60

        # Extracting the hardcoded Cairo geometry:
        # Tail X offset = pad(12) - 6 = 6.0
        # Tail Y offset drops 12px below the box, which sits exactly at (height - 12.0)
        tail_x = 6.0
        tail_y = badge_h - 12.0

        final_x = max(0, int(touch_x - tail_x))
        final_y = max(0, int(touch_y - tail_y))

        # Push the widget using its margins to act as absolute coordinates
        self.badge.set_margin_start(final_x)
        self.badge.set_margin_top(final_y)

        return GLib.SOURCE_CONTINUE

    def _on_realize(self):
        self._restore_position_if_saved()
        GLib.idle_add(self.update_input_region)

    def update_input_region(self):
        native = self.get_native()
        if not native: return
        surface = native.get_surface()
        if not surface: return

        region = cairo.Region()
        res, avatar_rect = self.avatar_container.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(avatar_rect.origin.x), int(avatar_rect.origin.y),
                int(avatar_rect.size.width), int(avatar_rect.size.height)
            ))

        res, badge_rect = self.badge.compute_bounds(self)
        if res:
            region.union(cairo.RectangleInt(
                int(badge_rect.origin.x), int(badge_rect.origin.y),
                int(badge_rect.size.width), int(badge_rect.size.height)
            ))

        surface.set_input_region(region)

    def get_settings(self) -> OverlaySettings:
        return self.settings

    def clamp_coordinates(self, x: float, y: float) -> tuple[int, int]:
        win_w = self.get_width() if self.get_width() > 0 else 150
        win_h = self.get_height() if self.get_height() > 0 else 150
        max_x = max(0, int(self.map_width - win_w))
        max_y = max(0, int(self.map_height - win_h))
        return max(0, min(int(x), max_x)), max(0, min(int(y), max_y))

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
        if saved_x is None or saved_y is None: return
        clamped_x, clamped_y = self.clamp_coordinates(saved_x, saved_y)
        self._apply_position(clamped_x, clamped_y)

    def _toggle_thought_bubble(self):
        print("[Charon Overlay] Dynamic Badge clicked! Ready for expansion animation.")

    def set_indicator_type(self, msg_type: str, custom_symbol: str = None):
        """Binds semantic categories to explicit color values and idiomatic symbols."""
        if msg_type == "warning":
            text = custom_symbol or "!!"
            self.badge.set_state(text, 0.98, 0.75, 0.14)
        elif msg_type == "urgent":
            text = custom_symbol or "$#@!"
            self.badge.set_state(text, 0.93, 0.26, 0.26)
        elif msg_type == "inbox":
            text = custom_symbol or "@"
            self.badge.set_state(text, 0.66, 0.33, 0.97)
        else:
            text = custom_symbol or "...."
            self.badge.set_state(text, 0.22, 0.74, 0.97)

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
                    surface.begin_move(event.get_device(), 1, start_x, start_y, event.get_time())
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
        symbol = payload.get("symbol", None)

        if category in ("warning", "urgent"):
            self.avatar.set_expressive_state("alert")
        elif "text" in payload:
            self.avatar.set_expressive_state(
                state_name if state_name in EXPRESSIVE_STATES else "expressing")
        else:
            self.avatar.set_expressive_state("observing")

        self.set_indicator_type(category, custom_symbol=symbol)

        if "text" in payload:
            text = payload["text"]
            print(f"[Charon Overlay] Intercepted text for Step 2 animation payload: {text}")

    def _apply_css(self):
        css_provider = Gtk.CssProvider()
        css = """
        window {
            background-color: transparent;
            box-shadow: none;
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

        win = CharonOverlayWindow(app=app_instance, map_width=map_w, map_height=map_h)
        win.present()

    app.connect("activate", on_activate)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.run([sys.argv[0]] + residual_args)

if __name__ == "__main__":
    main()