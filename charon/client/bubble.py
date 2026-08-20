import math
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, cairo

class MessageBubble(Gtk.Overlay):
    """Dynamic comic speech/thought bubble with GPU scale animations and click gestures."""
    def __init__(self):
        super().__init__()
        self.message_type = "speech"
        self.on_dismissed_callback = None

        # Give widget CSS class for transform scaling
        self.add_css_class("message-bubble")
        self.css_provider = Gtk.CssProvider()
        self.get_style_context().add_provider(
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Animation states
        self.anim_duration_ms = 600
        self.shrink_duration_ms = 220
        self.start_time = 0
        self.tick_id = 0
        self.is_closing = False

        # Drawing Area for background shape
        self.bg_draw = Gtk.DrawingArea()
        self.bg_draw.set_draw_func(self._draw_background)
        self.set_child(self.bg_draw)

        # Text Label Overlay
        self.label = Gtk.Label()
        self.label.set_wrap(True)
        self.label.set_max_width_chars(28)
        self.label.set_margin_top(14)
        self.label.set_margin_bottom(28)  # Reserve space for the bottom tail
        self.label.set_margin_start(16)
        self.label.set_margin_end(16)
        self.add_overlay(self.label)

        # Click gesture controller
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self._on_bubble_clicked)
        self.add_controller(click_gesture)

    def show_message(self, text: str, msg_type: str = "speech"):
        """Pop in a message with an elastic animation."""
        self.is_closing = False
        self.message_type = msg_type
        self.label.set_label(f"<span size='medium' weight='bold' foreground='#111111'>{text}</span>")
        self.label.set_use_markup(True)
        self.set_visible(True)
        self.bg_draw.queue_draw()

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

    def _animate_pop_in_tick(self, widget, frame_clock):
        current_time = frame_clock.get_frame_time()
        if self.start_time == 0:
            self.start_time = current_time
            return GLib.SOURCE_CONTINUE

        elapsed_ms = (current_time - self.start_time) / 1000.0
        t = min(elapsed_ms / self.anim_duration_ms, 1.0)

        # Elastic Out Math
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
            self.set_visible(False)  # Triggers allocation update and window shrink
            if self.on_dismissed_callback:
                self.on_dismissed_callback()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _apply_scale_css(self, scale):
        css = f".message-bubble {{ transform: scale({scale}); transform-origin: bottom center; }}"
        self.css_provider.load_from_data(css.encode())

    def _draw_background(self, area, cr, width, height):
        tail_height = 20
        box_height = height - tail_height

        cr.set_source_rgba(0.98, 0.98, 0.98, 0.95)

        if self.message_type == "speech":
            radius = 12
            cr.arc(width - radius, radius, radius, -math.pi/2, 0)
            cr.arc(width - radius, box_height - radius, radius, 0, math.pi/2)
            cr.arc(radius, box_height - radius, radius, math.pi/2, math.pi)
            cr.arc(radius, radius, radius, math.pi, 3*math.pi/2)

            # Tail pointing down
            cr.move_to(width / 2 + 10, box_height)
            cr.line_to(width / 2 - 5, height)
            cr.line_to(width / 2 - 15, box_height)
            cr.fill()

        elif self.message_type == "thought":
            radius = 20
            cr.arc(width - radius, radius, radius, -math.pi/2, 0)
            cr.arc(width - radius, box_height - radius, radius, 0, math.pi/2)
            cr.arc(radius, box_height - radius, radius, math.pi/2, math.pi)
            cr.arc(radius, radius, radius, math.pi, 3*math.pi/2)
            cr.fill()

            # Thought circles
            cr.arc(width / 2 - 5, box_height + 5, 5, 0, 2*math.pi)
            cr.fill()
            cr.arc(width / 2 - 12, box_height + 14, 3, 0, 2*math.pi)
            cr.fill()

        # Border
        cr.set_source_rgba(0.1, 0.1, 0.1, 1.0)
        cr.set_line_width(2)
        cr.stroke()