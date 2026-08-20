"""
charon/client/avatar_widget.py

Container mapping the AvatarVisualizer and managing interaction overlays.
"""
import math

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk

from .avatar_visualizer import AvatarVisualizer
from .avatar_states import BASE_ROTATION


class AvatarWidget(Gtk.Overlay):
    """Container wrapping AvatarVisualizer with integrated Always-On-Top pin indicator."""

    def __init__(self):
        super().__init__()
        self.visualizer = AvatarVisualizer()
        self.set_child(self.visualizer)

        self.pin_button = Gtk.ToggleButton()
        self.pin_button.set_icon_name("pin-symbolic")
        self.pin_button.set_tooltip_text("Pin Window Always-On-Top")
        self.pin_button.add_css_class("flat")
        self.pin_button.add_css_class("circular")
        self.pin_button.set_halign(Gtk.Align.END)
        self.pin_button.set_valign(Gtk.Align.START)
        self.pin_button.set_margin_top(4)
        self.pin_button.set_margin_end(4)
        self.pin_button.connect("toggled", self._on_pin_toggled)

        self.add_overlay(self.pin_button)

    def _on_pin_toggled(self, button: Gtk.ToggleButton):
        root = self.get_root()
        if isinstance(root, Gtk.Window):
            is_pinned = button.get_active()
            if hasattr(root, "set_keep_above"):
                root.set_keep_above(is_pinned)

    def do_contains(self, x: float, y: float) -> bool:
        """
        Determines if a pointer event falls within the drawn avatar shape.
        Returning False allows the click to pass through to the desktop below.
        Valid clicks will naturally bubble up to Gtk.WindowHandle for dragging.
        """
        width = self.get_width()
        height = self.get_height()

        if width == 0 or height == 0:
            return False

        cx, cy = width / 2.0, height / 2.0
        r_body = min(width, height) * 0.38

        # 1. Apply Inverse Rotation to the coordinates
        total_rotation = BASE_ROTATION + self.visualizer.current_head_tilt

        dx = x - cx
        dy = y - cy

        cos_t = math.cos(-total_rotation)
        sin_t = math.sin(-total_rotation)

        local_x = cx + (dx * cos_t - dy * sin_t)
        local_y = cy + (dx * sin_t + dy * cos_t)

        # 2. Hit-Test the Main Body Shell
        dist_to_center = math.hypot(local_x - cx, local_y - cy)
        if dist_to_center <= r_body:
            return True

        # 3. Hit-Test the Roll Bars
        stroke_buffer = 6.0
        arc_radius = r_body * 1.12

        # Top Roll Bar Center
        top_cy = cy - r_body * 0.15
        dist_to_top_arc = math.hypot(local_x - cx, local_y - top_cy)

        if abs(dist_to_top_arc - arc_radius) <= stroke_buffer:
            angle = math.atan2(local_y - top_cy, local_x - cx)
            if angle < 0:
                angle += 2 * math.pi
            if math.pi * 1.20 <= angle <= math.pi * 1.80:
                return True

        # Bottom Roll Bar Center
        bottom_cy = cy + r_body * 0.15
        dist_to_bottom_arc = math.hypot(local_x - cx, local_y - bottom_cy)

        if abs(dist_to_bottom_arc - arc_radius) <= stroke_buffer:
            angle = math.atan2(local_y - bottom_cy, local_x - cx)
            if math.pi * 0.20 <= angle <= math.pi * 0.80:
                return True

        return False