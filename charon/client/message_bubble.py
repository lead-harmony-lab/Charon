import math
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib


class MessageBubble(Gtk.Overlay):
    """Unified comic bubble that acts as both a notification badge and a text container."""

    URGENCY_COLORS = {
        "thought": (0.22, 0.74, 0.97, 1.0),  # #38BDF8 (Blue)
        "warning": (0.98, 0.80, 0.08, 1.0),  # #FACC15 (Yellow)
        "urgent": (0.97, 0.44, 0.44, 1.0),  # #F87171 (Red)
    }

    def __init__(self):
        super().__init__()
        self.message_type = "speech"
        self.urgency = "thought"
        self.is_expanded = False
        self.has_unread = False

        # Animation state
        self.anim_duration_ms = 400
        self.start_time = 0
        self.tick_id = 0
        self.current_scale = 0.0
        self.target_scale = 0.0

        self.add_css_class("message-bubble")
        self.css_provider = Gtk.CssProvider()
        self.get_style_context().add_provider(
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Draw layer for the dynamic shape and halo
        self.bg_draw = Gtk.DrawingArea()
        # Force the drawing area to stretch and fill the overlay
        self.bg_draw.set_hexpand(True)
        self.bg_draw.set_vexpand(True)
        self.bg_draw.set_draw_func(self._draw_background)
        self.set_child(self.bg_draw)

        # Text layer (hidden when collapsed)
        self.label = Gtk.Label()
        self.label.set_wrap(True)
        self.label.set_max_width_chars(28)
        self.label.set_margin_top(14)
        self.label.set_margin_bottom(28)
        self.label.set_margin_start(16)
        self.label.set_margin_end(16)
        self.label.set_opacity(0.0)  # Start hidden

        self.add_overlay(self.label)

        # Force the Overlay to calculate its size based on the text!
        self.set_measure_overlay(self.label, True)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self._on_clicked)
        self.add_controller(click_gesture)

        # Initialize hidden
        self._apply_scale_css(0.0)

    def set_payload(self, text: str, msg_type: str = "speech", urgency: str = "thought"):
        """Called when a new message arrives. Pops open to full size immediately."""
        self.message_type = msg_type
        self.urgency = urgency if urgency in self.URGENCY_COLORS else "thought"
        self.has_unread = True

        # Start fully expanded so we don't get the 'thumbtack' effect
        self.is_expanded = True

        self.label.set_label(f"<span size='medium' weight='bold' foreground='#111111'>{text}</span>")
        self.label.set_use_markup(True)
        self.bg_draw.queue_draw()

        # Animate directly to 100% scale instead of 25% scale
        self._start_animation(target_scale=1.0)

    def _on_clicked(self, gesture, n_press, x, y):
        if self.current_scale == 0.0: return

        self.is_expanded = not self.is_expanded
        self.has_unread = False if self.is_expanded else self.has_unread
        self.bg_draw.queue_draw()  # Redraw to remove unread pulse if needed

        target = 1.0 if self.is_expanded else 0.25
        self._start_animation(target_scale=target)

    def _start_animation(self, target_scale: float):
        self.target_scale = target_scale
        if self.tick_id != 0:
            self.remove_tick_callback(self.tick_id)
        self.start_time = 0
        self.tick_id = self.add_tick_callback(self._animate_tick)

    def _animate_tick(self, widget, frame_clock):
        current_time = frame_clock.get_frame_time()
        if self.start_time == 0:
            self.start_time = current_time
            self.start_scale = self.current_scale
            return GLib.SOURCE_CONTINUE

        elapsed_ms = (current_time - self.start_time) / 1000.0
        t = min(elapsed_ms / self.anim_duration_ms, 1.0)

        # Smooth ease-in-out
        ease = t * t * (3.0 - 2.0 * t)
        self.current_scale = self.start_scale + (self.target_scale - self.start_scale) * ease

        self._apply_scale_css(self.current_scale)

        # Fade text in/out based on expansion
        text_opacity = max(0.0, (self.current_scale - 0.5) * 2.0) if self.is_expanded else 0.0
        self.label.set_opacity(text_opacity)

        if t >= 1.0:
            self.tick_id = 0
            if self.target_scale == 0.0:
                self.set_visible(False)
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE

    def _apply_scale_css(self, scale):
        # Origin ensures it grows out from the side closest to the avatar
        css = f".message-bubble {{ transform: scale({scale}); transform-origin: center left; }}"
        self.css_provider.load_from_data(css.encode())

    def _draw_background(self, area, cr, width, height):
        tail_height = 20
        box_height = height - tail_height
        radius = 16

        # Draw base shape
        cr.set_source_rgba(0.98, 0.98, 0.98, 0.95)

        if self.message_type == "speech" or self.message_type not in ["thought"]:
            # Speech Rectangle
            cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
            cr.arc(width - radius, box_height - radius, radius, 0, math.pi / 2)
            cr.arc(radius, box_height - radius, radius, math.pi / 2, math.pi)
            cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)

            # Tail pointing left (towards avatar)
            cr.move_to(20, box_height)
            cr.line_to(5, height)
            cr.line_to(35, box_height)
            cr.fill_preserve()

        elif self.message_type == "thought":
            # Thought Cloud (simplified rounded rect for now, plus circles)
            cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
            cr.arc(width - radius, box_height - radius, radius, 0, math.pi / 2)
            cr.arc(radius, box_height - radius, radius, math.pi / 2, math.pi)
            cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
            cr.fill_preserve()

            # Trail leading left
            cr.arc(35, box_height + 8, 6, 0, 2 * math.pi)
            cr.fill()
            cr.arc(15, box_height + 18, 4, 0, 2 * math.pi)
            cr.fill()

        # Draw the Urgency Halo (Stroke)
        r, g, b, a = self.URGENCY_COLORS.get(self.urgency, (0.5, 0.5, 0.5, 1.0))
        cr.set_source_rgba(r, g, b, a)
        # Thicker stroke if unread to make it pop
        cr.set_line_width(4 if self.has_unread and not self.is_expanded else 2)
        cr.stroke()