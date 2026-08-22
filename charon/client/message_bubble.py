"""
charon/client/message_bubble.py
System Version: v3.9.4

Module: Comic-book style message bubble for the Charon Concierge.
Features elastic pop-in, cubic shrink-out, and click-to-dismiss gestures.
"""

import math
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class MessageBubble(Gtk.Box):
    """Speech Bubble with GPU-accelerated animations and click dismiss."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("comic-speech-bubble")
        self.set_valign(Gtk.Align.CENTER)

        # Animation state
        self.anim_duration_ms = 600
        self.shrink_duration_ms = 220
        self.start_time = 0
        self.tick_id = 0
        self.is_closing = False

        # --- Layout Setup ---
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.title_label = Gtk.Label(label="Charon Concierge")
        self.title_label.set_halign(Gtk.Align.START)
        self.title_label.add_css_class("bubble-title")
        self.title_label.set_hexpand(True)

        collapse_btn = Gtk.Button.new_from_icon_name("window-minimize-symbolic")
        collapse_btn.add_css_class("collapse-btn")
        collapse_btn.connect("clicked", self._on_collapse_clicked)

        header_box.append(self.title_label)
        header_box.append(collapse_btn)

        self.content_label = Gtk.Label(label="")
        self.content_label.set_halign(Gtk.Align.START)
        self.content_label.set_wrap(True)
        self.content_label.set_max_width_chars(32)
        self.content_label.add_css_class("bubble-text")

        self.append(header_box)
        self.append(self.content_label)

        # --- Click Gesture ---
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self._on_bubble_clicked)
        self.add_controller(click_gesture)

        # --- CSS Providers ---
        self.static_css_provider = Gtk.CssProvider()
        self.dynamic_css_provider = Gtk.CssProvider()

        self._apply_static_css()
        self.get_style_context().add_provider(
            self.dynamic_css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )

        self._apply_scale_css(0.0)

    def show_message(self, text: str):
        self.is_closing = False
        self.content_label.set_text(text)
        self.set_visible(True)

        if self.tick_id != 0:
            self.remove_tick_callback(self.tick_id)

        self.start_time = 0
        self.tick_id = self.add_tick_callback(self._animate_pop_in_tick)

    def _on_bubble_clicked(self, gesture, n_press, x, y):
        """Intercepts click and begins shrink animation."""
        if self.is_closing:
            return

        self.is_closing = True
        if self.tick_id != 0:
            self.remove_tick_callback(self.tick_id)

        self.start_time = 0
        self.tick_id = self.add_tick_callback(self._animate_shrink_tick)

    def _on_collapse_clicked(self, button):
        self.set_visible(False)
        self._apply_scale_css(0.0)
        if self.tick_id != 0:
            self.remove_tick_callback(self.tick_id)
            self.tick_id = 0

    def _animate_pop_in_tick(self, widget, frame_clock):
        current_time = frame_clock.get_frame_time()
        if self.start_time == 0:
            self.start_time = current_time
            return GLib.SOURCE_CONTINUE

        elapsed_ms = (current_time - self.start_time) / 1000.0
        t = min(elapsed_ms / self.anim_duration_ms, 1.0)

        if t == 0.0:
            scale = 0.0
        elif t == 1.0:
            scale = 1.0
        else:
            p = 0.3
            scale = math.pow(2, -10 * t) * math.sin((t - p / 4.0) * (2 * math.pi) / p) + 1.0

        self._apply_scale_css(scale)

        if t >= 1.0:
            self.tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _animate_shrink_tick(self, widget, frame_clock):
        current_time = frame_clock.get_frame_time()
        if self.start_time == 0:
            self.start_time = current_time
            return GLib.SOURCE_CONTINUE

        elapsed_ms = (current_time - self.start_time) / 1000.0
        t = min(elapsed_ms / self.shrink_duration_ms, 1.0)

        # Ease-In Cubic Math
        scale = 1.0 - math.pow(t, 3)
        self._apply_scale_css(max(scale, 0.0))

        if t >= 1.0:
            self.tick_id = 0
            self.is_closing = False
            self.set_visible(False) # This automatically triggers Wayland hit region update!
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _apply_scale_css(self, scale):
        css = f".comic-speech-bubble {{ transform: scale({scale}); transform-origin: bottom center; }}"
        self.dynamic_css_provider.load_from_data(css.encode("utf-8"))

    def _apply_static_css(self):
        css = """
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
        self.static_css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.static_css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )