import cairo
import math
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


class MessageBubble(Gtk.Overlay):
    """Dynamic comic speech/thought bubble with GPU scale animations and click gestures."""

    def __init__(self):
        super().__init__()
        self.message_type = "speech"
        self.on_dismissed_callback = None

        # Match the DynamicBadge electric blue glow
        self.glow_color = (0.22, 0.74, 0.97, 1.0)

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
        self.bg_draw.set_size_request(280, 140)
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
        self.label.set_valign(Gtk.Align.CENTER)
        self.label.set_halign(Gtk.Align.CENTER)
        self.add_overlay(self.label)

        # Click gesture controller
        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(1)
        # CRITICAL FIX: Intercept the event during the CAPTURE phase before children (Gtk.Label) consume it
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_gesture.connect("pressed", self._on_bubble_clicked)
        self.add_controller(click_gesture)

        # Hide initially with 0 scale
        self.set_visible(False)
        self._apply_scale_css(0.0)

    def show_message(self, text: str, msg_type: str = "speech"):
        """Pop in a message with an elastic animation."""
        self.is_closing = False
        self.message_type = msg_type

        # Switched text to bright white to contrast with the dark background
        self.label.set_label(f"<span size='medium' weight='bold' foreground='#FFFFFF'>{text}</span>")
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
            self.set_visible(False)
            if self.on_dismissed_callback:
                self.on_dismissed_callback()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _apply_scale_css(self, scale):
        css = f".message-bubble {{ transform: scale({scale}); transform-origin: bottom center; }}"
        self.css_provider.load_from_data(css.encode())

    def _draw_background(self, area, cr, width, height):
        if width <= 0 or height <= 0:
            return

        pad = 8
        tail_height = 20
        box_width = width - (pad * 2)
        box_height = height - tail_height - (pad * 2)

        cr.translate(pad, pad)

        # --- PATH GENERATION ---
        if self.message_type == "speech":
            radius = 12
            cr.move_to(radius, 0)
            cr.line_to(box_width - radius, 0)
            cr.arc(box_width - radius, radius, radius, -math.pi / 2, 0)
            cr.line_to(box_width, box_height - radius)
            cr.arc(box_width - radius, box_height - radius, radius, 0, math.pi / 2)

            # Draw tail inline with bottom edge
            cr.line_to(box_width / 2 + 10, box_height)
            cr.line_to(box_width / 2 - 5, box_height + tail_height)
            cr.line_to(box_width / 2 - 15, box_height)

            cr.line_to(radius, box_height)
            cr.arc(radius, box_height - radius, radius, math.pi / 2, math.pi)
            cr.line_to(0, radius)
            cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()

        elif self.message_type == "thought":
            radius = 20
            # Main Bubble Path
            cr.arc(box_width - radius, radius, radius, -math.pi / 2, 0)
            cr.arc(box_width - radius, box_height - radius, radius, 0, math.pi / 2)
            cr.arc(radius, box_height - radius, radius, math.pi / 2, math.pi)
            cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()

            # Small trailing thought circles (sub-paths so they get stroked/filled together)
            cr.new_sub_path()
            cr.arc(box_width / 2 - 5, box_height + 6, 5, 0, 2 * math.pi)
            cr.close_path()

            cr.new_sub_path()
            cr.arc(box_width / 2 - 14, box_height + 16, 3, 0, 2 * math.pi)
            cr.close_path()

        # --- ELECTRIC SHADING & GLOW ---
        glow_r, glow_g, glow_b, _ = self.glow_color

        # Outer Glow Passes
        for i in range(4, 0, -1):
            cr.set_source_rgba(glow_r, glow_g, glow_b, 0.15)
            cr.set_line_width(i * 3.0)
            cr.stroke_preserve()

        # Core Background (Dark Blue/Grey)
        cr.set_source_rgba(0.06, 0.09, 0.16, 0.95)
        cr.fill_preserve()

        # Solid Inner Border (Electric Blue)
        cr.set_source_rgba(*self.glow_color)
        cr.set_line_width(1.5)
        cr.stroke()


class DynamicBadge(Gtk.DrawingArea):
    """Cairo-drawn badge serving as the seed for the elastic speech bubble."""

    def __init__(self):
        super().__init__()
        self.set_size_request(70, 60)

        # Semiotic State Defaults (Standard Blue with 4 dots)
        self.glow_color = (0.22, 0.74, 0.97, 1.0)  # #38BDF8
        self.badge_text = "...."
        self.bubble_type = "thought"

        # GTK4 Drawing Areas need a draw function assigned
        self.set_draw_func(self.on_draw)

        # Click detection
        self.click_gesture = Gtk.GestureClick.new()
        self.click_gesture.set_button(1)
        # CRITICAL FIX: Ensure the badge captures click events reliably anywhere on its surface
        self.click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.add_controller(self.click_gesture)

    def set_state(self, text: str, r: float, g: float, b: float, bubble_type: str = "thought"):
        """Updates symbol, color, and visual bubble geometry."""
        self.badge_text = text
        self.glow_color = (r, g, b, 1.0)
        self.bubble_type = bubble_type
        self.queue_draw()

    def set_indicator_color(self, r: float, g: float, b: float):
        """Update the Cairo glow color while preserving current text."""
        self.glow_color = (r, g, b, 1.0)
        self.queue_draw()

    def on_draw(self, area, cr, width, height):
        if width <= 0 or height <= 0:
            return

        pad = 12
        box_w = width - (pad * 2)
        box_h = height - (pad * 2) - 12  # Reserve 12px at the bottom for the tail
        r = 6.0  # Corner radius

        cr.translate(pad, pad)

        # --- CHASSIS GEOMETRY ---
        if self.bubble_type == "speech":
            cr.move_to(r, 0)
            cr.line_to(box_w - r, 0)
            cr.arc(box_w - r, r, r, -math.pi / 2, 0)
            cr.line_to(box_w, box_h - r)
            cr.arc(box_w - r, box_h - r, r, 0, math.pi / 2)

            # Sharp connected tail
            cr.line_to(box_w * 0.40, box_h)
            cr.line_to(-6, box_h + 12)
            cr.line_to(box_w * 0.15, box_h)

            cr.line_to(r, box_h)
            cr.arc(r, box_h - r, r, math.pi / 2, math.pi)
            cr.line_to(0, r)
            cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()
        else:
            # "thought" bubble base geometry without attached tail
            cr.move_to(r, 0)
            cr.line_to(box_w - r, 0)
            cr.arc(box_w - r, r, r, -math.pi / 2, 0)
            cr.line_to(box_w, box_h - r)
            cr.arc(box_w - r, box_h - r, r, 0, math.pi / 2)
            cr.line_to(r, box_h)
            cr.arc(r, box_h - r, r, math.pi / 2, math.pi)
            cr.line_to(0, r)
            cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()

            # Small disconnected trailing dots dropped into the reserved tail margin
            cr.new_sub_path()
            cr.arc(12, box_h + 5, 3, 0, 2 * math.pi)
            cr.close_path()

            cr.new_sub_path()
            cr.arc(4, box_h + 10, 1.5, 0, 2 * math.pi)
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