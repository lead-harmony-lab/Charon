import cairo
import math
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


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

        # Ambient Text Glow Pass
        cr.set_source_rgba(glow_r, glow_g, glow_b, 0.6)
        cr.move_to(text_x, text_y)
        cr.show_text(self.badge_text)

        # High-Contrast Core Text Pass
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.move_to(text_x, text_y)
        cr.show_text(self.badge_text)