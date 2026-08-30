# charon/client/overlay.py
# System Version: v3.9.0 | File Revision: 3.9.26

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

from charon.client.avatar_widget import AvatarVisualizer, AvatarWidget
from charon.client.ws_listener import OverlayWSListener, SpeechStreamPlayer
from charon.client.avatar_states import EXPRESSIVE_STATES
from charon.config import CHARON_API_KEY
from charon.client.dynamic_badge import DynamicBadge
from charon.client.message_bubble import MessageBubble
from charon.client.context_menu import AvatarContextMenu


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


class CharonOverlayWindow(Gtk.ApplicationWindow):
    """HUD Overlay Window featuring Wheatley Core Visualizer and Cursor Gaze Tracking."""

    def __init__(self, app: Gtk.Application, map_width: float = 1920.0, map_height: float = 1080.0):
        super().__init__(application=app)

        self.settings = OverlaySettings()
        self.map_width = map_width
        self.map_height = map_height

        self._pending_telemetry = None
        self._telemetry_idle_queued = False
        self._latest_message_text = "..."
        self._last_active_pos = (-1, -1)
        self._bubble_timeout_id = None

        self._current_window_x = None
        self._current_window_y = None

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
        self.connect("map", lambda win: self._start_websocket())

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # --- AVATAR CONTAINER LAYOUT ---
        self.avatar_overlay = Gtk.Overlay()
        self.avatar_overlay.set_size_request(600, 400)

        self.avatar_container = AvatarWidget()
        self.avatar = self.avatar_container.visualizer
        self.avatar_container.set_cursor_from_name("grab")
        self._setup_avatar_drag_feedback()

        self.context_menu_manager = AvatarContextMenu(self, self.avatar_container)

        self.avatar_align_box = Gtk.Box()
        self.avatar_align_box.set_halign(Gtk.Align.CENTER)
        self.avatar_align_box.set_valign(Gtk.Align.END)
        self.avatar_align_box.set_margin_bottom(20)
        self.avatar_align_box.append(self.avatar_container)

        self.avatar_overlay.set_child(self.avatar_align_box)

        self.speech_player = SpeechStreamPlayer(visualizer=self.avatar)

        # --- DYNAMIC BADGE ---
        self.badge = DynamicBadge()
        self.badge.set_halign(Gtk.Align.START)
        self.badge.set_valign(Gtk.Align.START)
        self.badge.bubble_type = "idle" # Initialize as idle
        self.badge.click_gesture.connect(
            "pressed", lambda gesture, n, x, y: self._toggle_thought_bubble()
        )
        self.avatar_overlay.add_overlay(self.badge)

        # --- MESSAGE BUBBLE ---
        self.bubble = MessageBubble()
        self.bubble.set_halign(Gtk.Align.START)
        self.bubble.set_valign(Gtk.Align.START)
        self.bubble.set_visible(False)
        self.bubble.on_dismissed_callback = self._on_bubble_dismissed
        self.avatar_overlay.add_overlay(self.bubble)

        self.main_box.append(self.avatar_overlay)
        self.set_child(self.main_box)
        self._apply_css()

        self.add_tick_callback(self._sync_badge_position)


    def _start_websocket(self):
        ws_uri = "ws://localhost:8000/v1/concierge/stream?client_id=gtk4_avatar"
        if CHARON_API_KEY:
            ws_uri += f"&api_key={CHARON_API_KEY}"

        self.ws_thread = OverlayWSListener(
            uri=ws_uri,
            api_key=CHARON_API_KEY,
            on_event_callback=self.handle_stream_event,
            client_id="gtk4_avatar"
        )
        self.ws_thread.start()


    def _sync_badge_position(self, widget, frame_clock):
        vis = self.avatar
        vw = vis.get_width()
        vh = vis.get_height()

        if vw == 0 or vh == 0:
            return GLib.SOURCE_CONTINUE

        cx = vw / 2.0
        cy = vh / 2.0
        r_body = min(vw, vh) * 0.38
        r_bezel = r_body * 0.68
        max_travel = r_bezel * 0.35

        dx = vis.current_dx
        dy = vis.current_dy
        dist = math.hypot(dx, dy)

        if dist > max_travel and dist > 0:
            dx = (dx / dist) * max_travel
            dy = (dy / dist) * max_travel

        eye_cx = cx + dx
        eye_cy = cy + dy

        angle = -math.pi / 4.0

        touch_x = eye_cx + math.cos(angle) * (r_body * 1.05)
        touch_y = eye_cy + math.sin(angle) * (r_body * 1.05)

        res, avatar_rect = self.avatar.compute_bounds(self.avatar_overlay)
        if res:
            touch_x += avatar_rect.origin.x
            touch_y += avatar_rect.origin.y

        pos_changed = False

        if self.badge.get_visible():
            badge_w = self.badge.get_width() or 70
            badge_h = self.badge.get_height() or 60

            tail_x = 6.0
            tail_y = badge_h - 12.0

            final_x = max(0, int(touch_x - tail_x))
            final_y = max(0, int(touch_y - tail_y))

            if (final_x, final_y) != self._last_active_pos:
                self.badge.set_margin_start(final_x)
                self.badge.set_margin_top(final_y)
                self._last_active_pos = (final_x, final_y)
                pos_changed = True

        elif self.bubble.get_visible():
            bubble_w = self.bubble.get_width() or 280
            bubble_h = self.bubble.get_height() or 140

            b_tail_x = bubble_w / 2.0
            b_tail_y = bubble_h - 8.0

            b_final_x = max(0, int(touch_x - b_tail_x))
            b_final_y = max(0, int(touch_y - b_tail_y))

            if (b_final_x, b_final_y) != self._last_active_pos:
                self.bubble.set_margin_start(b_final_x)
                self.bubble.set_margin_top(b_final_y)
                self._last_active_pos = (b_final_x, b_final_y)
                pos_changed = True

        if pos_changed:
            self.update_input_region()

        return GLib.SOURCE_CONTINUE

    def _on_realize(self):
        self._restore_position_if_saved()
        GLib.idle_add(self.update_input_region)
        GLib.timeout_add(100, self._force_input_region_sync)
        GLib.timeout_add(500, self._force_input_region_sync)

    def _force_input_region_sync(self):
        self._last_active_pos = (-1, -1)
        self.update_input_region()
        return False

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

        if self.badge.get_visible():
            res, badge_rect = self.badge.compute_bounds(self)
            if res:
                region.union(cairo.RectangleInt(
                    int(badge_rect.origin.x), int(badge_rect.origin.y),
                    int(badge_rect.size.width), int(badge_rect.size.height)
                ))

        if self.bubble.get_visible():
            res, bubble_rect = self.bubble.compute_bounds(self)
            if res:
                region.union(cairo.RectangleInt(
                    int(bubble_rect.origin.x), int(bubble_rect.origin.y),
                    int(bubble_rect.size.width), int(bubble_rect.size.height)
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

    def _auto_close_bubble(self):
        self._bubble_timeout_id = None
        if self.bubble.get_visible():
            self._on_bubble_dismissed()
        return GLib.SOURCE_REMOVE

    def _toggle_thought_bubble(self):
        self._last_active_pos = (-1, -1)
        self.badge.set_visible(False)
        self.bubble.set_visible(True)

        bubble_style = getattr(self.badge, "bubble_type", "thought")
        if bubble_style == "idle":
            bubble_style = "thought" # Fallback if clicked while idle

        self.bubble.show_message(self._latest_message_text, msg_type=bubble_style)

        GLib.idle_add(self.update_input_region)

        if self._bubble_timeout_id is not None:
            GLib.source_remove(self._bubble_timeout_id)

        word_count = len(self._latest_message_text.split())
        display_ms = 3000 + (word_count * 250)

        self._bubble_timeout_id = GLib.timeout_add(display_ms, self._auto_close_bubble)

    def _on_bubble_dismissed(self):
        """Reverts back to an observing/idle state once the bubble times out or is closed."""
        if self._bubble_timeout_id is not None:
            GLib.source_remove(self._bubble_timeout_id)
            self._bubble_timeout_id = None

        self._last_active_pos = (-1, -1)
        self.bubble.set_visible(False)

        # Preserve the active modality (e.g., "speech") so the badge tail remains correct
        current_style = getattr(self.badge, "bubble_type", "thought")
        if current_style == "idle":
            current_style = "thought"

        # Explicitly pass bubble_type to override the "thought" default in set_state
        self.badge.set_state("...", 0.22, 0.74, 0.97, bubble_type=current_style)
        self.badge.set_visible(True)

        self.avatar.set_expressive_state("observing")
        GLib.idle_add(self.update_input_region)

    def set_indicator_type(self, msg_type: str, custom_symbol: str = None):
        """Legacy helper for setting color values and symbols."""
        if msg_type == "warning":
            text = custom_symbol or "!!"
            self.badge.set_state(text, 0.98, 0.75, 0.14, bubble_type="thought")
            if hasattr(self.bubble, "glow_color"): self.bubble.glow_color = (0.98, 0.75, 0.14, 1.0)
        elif msg_type == "urgent":
            text = custom_symbol or "$#@!"
            self.badge.set_state(text, 0.93, 0.26, 0.26, bubble_type="thought")
            if hasattr(self.bubble, "glow_color"): self.bubble.glow_color = (0.93, 0.26, 0.26, 1.0)
        elif msg_type == "inbox":
            text = custom_symbol or "@"
            self.badge.set_state(text, 0.66, 0.33, 0.97, bubble_type="thought")
            if hasattr(self.bubble, "glow_color"): self.bubble.glow_color = (0.66, 0.33, 0.97, 1.0)
        else:
            text = custom_symbol or "...."
            self.badge.set_state(text, 0.22, 0.74, 0.97, bubble_type="thought")
            if hasattr(self.bubble, "glow_color"): self.bubble.glow_color = (0.22, 0.74, 0.97, 1.0)

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
            if self._current_window_x is not None and self._current_window_y is not None:
                self.settings.update(
                    x=self._current_window_x,
                    y=self._current_window_y
                )

        drag_gesture.connect("drag-begin", on_drag_begin)
        drag_gesture.connect("drag-end", on_drag_end)
        self.avatar_container.add_controller(drag_gesture)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(1)

        def on_click_pressed(g, n, x, y):
            self.avatar_container.set_cursor_from_name("grabbing")

        def on_click_released(g, n, x, y):
            self.avatar_container.set_cursor_from_name("grab")

        click_gesture.connect("pressed", on_click_pressed)
        click_gesture.connect("released", on_click_released)
        self.avatar_container.add_controller(click_gesture)

    def handle_stream_event(self, event: dict):
        event_type = event.get("type") or event.get("event_type")

        if event_type == "pointer_telemetry":
            if event.get("data", {}).get("action"):
                GLib.idle_add(self._process_stream_event_ui, event)
                return

            self._pending_telemetry = event
            if not self._telemetry_idle_queued:
                self._telemetry_idle_queued = True
                GLib.idle_add(self._flush_telemetry)

        elif event_type == "window_moved":
            data = event.get("data", {})
            if "x" in data and "y" in data:
                self._current_window_x = data["x"]
                self._current_window_y = data["y"]
                GLib.idle_add(self.update_input_region)
            return

        else:
            GLib.idle_add(self._process_stream_event_ui, event)

    def _flush_telemetry(self):
        self._telemetry_idle_queued = False
        if self._pending_telemetry:
            self._process_stream_event_ui(self._pending_telemetry)
            self._pending_telemetry = None
        return False

    def _process_stream_event_ui(self, event: dict):
        event_type = event.get("type") or event.get("event_type")
        modality = event.get("modality")

        # --- 1. MULTIMODAL SIGNAL ROUTING (NEW) ---
        if modality:
            content = event.get("content", "")

            if modality == "dialogue":
                self.badge.set_state("...", 0.22, 0.74, 0.97, bubble_type="speech")
                self.badge.set_visible(True)
                self._latest_message_text = content
                self.avatar.set_expressive_state("expressing")
                self._toggle_thought_bubble()

            elif modality == "thought":
                self.badge.set_state("...", 0.22, 0.74, 0.97, bubble_type="thought")
                self.badge.set_visible(True)
                self._latest_message_text = content
                self.avatar.set_expressive_state("thinking")
                self._toggle_thought_bubble()

            elif modality == "process":
                # Background processes should not trigger bubbles; fall back to observing/idle
                self.badge.set_state("...", 0.22, 0.74, 0.97, bubble_type="idle")
                self.bubble.set_visible(False)
                self.avatar.set_expressive_state("observing")
                GLib.idle_add(self.update_input_region)
            return

        # --- 2. POINTER TELEMETRY ---
        if event_type == "pointer_telemetry":
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

                self._current_window_x = win_top_left_x
                self._current_window_y = win_top_left_y

                res, avatar_rect = self.avatar_container.compute_bounds(self)
                if res:
                    eye_center_x = win_top_left_x + avatar_rect.origin.x + (avatar_rect.size.width / 2.0)
                    eye_center_y = win_top_left_y + avatar_rect.origin.y + (avatar_rect.size.height / 2.0)
                else:
                    eye_center_x = win_top_left_x + (avatar_w / 2.0)
                    eye_center_y = win_top_left_y + (avatar_h / 2.0)

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

        # --- 3. SPEECH CHUNKS (SYNCHRONIZED AUDIO) ---
        if event_type == "speech_chunk":
            text_segment = payload.get("text_segment", "") or payload.get("text", "")
            audio_b64 = payload.get("audio_b64", "")
            visemes = payload.get("visemes", [])
            sample_rate = payload.get("sample_rate", 24000)

            if text_segment:
                self.badge.set_state("...", 0.22, 0.74, 0.97, bubble_type="speech")
                self._latest_message_text = text_segment

            if audio_b64:
                self.speech_player.play_chunk(
                    audio_b64=audio_b64,
                    sample_rate=sample_rate,
                    visemes=visemes
                )

            self.avatar.set_expressive_state("expressing")
            return

        # --- 4. GENERAL NOTIFICATIONS & STATES (Legacy Fallback) ---
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
            self._latest_message_text = payload["text"]
            self._toggle_thought_bubble()

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