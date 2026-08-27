import cairo
import math
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class MessageBubble(Gtk.Overlay):
    """Dynamic comic speech/thought bubble with GPU scale animations, click gestures, and virtual Cairo buttons."""

    def __init__(self):
        super().__init__()
        self.message_type = "speech"
        self.on_action_callback = None  # Fired when a virtual button is clicked
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

        # State for virtual Cairo buttons
        self.actions = []  # List of dicts: [{"id": "fix", "label": "Fix Context"}, ...]
        self.hitboxes = {}  # Maps action_id -> (x, y, w, h) in absolute widget coordinates
        self.hovered_action = None  # Tracks the currently hovered action_id

        # Drawing Area for background shape
        self.bg_draw = Gtk.DrawingArea()
        self.bg_draw.set_size_request(320, 180)  # Increased to accommodate buttons
        self.bg_draw.set_draw_func(self._draw_background)
        self.set_child(self.bg_draw)

        # Text Label Overlay
        self.label = Gtk.Label()
        self.label.set_wrap(True)
        self.label.set_max_width_chars(28)
        self.label.set_margin_top(14)
        self.label.set_margin_bottom(28)  # Default reserve space, scales dynamically if actions exist
        self.label.set_margin_start(16)
        self.label.set_margin_end(16)
        self.label.set_valign(Gtk.Align.CENTER)
        self.label.set_halign(Gtk.Align.CENTER)
        self.add_overlay(self.label)

        # Click gesture controller
        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(1)
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_gesture.connect("pressed", self._on_bubble_clicked)
        self.add_controller(click_gesture)

        # Motion Controller for Hover States
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self._on_mouse_motion)
        motion_controller.connect("leave", self._on_mouse_leave)
        self.add_controller(motion_controller)

        # Hide initially with 0 scale
        self.set_visible(False)
        self._apply_scale_css(0.0)

    def show_message(self, text: str, msg_type: str = "speech", actions: list = None):
        """Pop in a message with an elastic animation and optional interactive actions."""
        self.is_closing = False
        self.message_type = msg_type
        self.actions = actions or []
        self.hitboxes.clear()
        self.hovered_action = None

        self.label.set_label(f"<span size='medium' weight='bold' foreground='#FFFFFF'>{text}</span>")
        self.label.set_use_markup(True)

        # Adjust layout based on whether we have buttons to draw
        self.label.set_margin_bottom(64 if self.actions else 28)

        self.set_visible(True)
        self.bg_draw.queue_draw()

        if self.tick_id != 0:
            self.remove_tick_callback(self.tick_id)

        self.start_time = 0
        self.tick_id = self.add_tick_callback(self._animate_pop_in_tick)

    def _on_mouse_motion(self, controller, x, y):
        """Hit-test for hover states and trigger redraw if state changes."""
        new_hover = None
        for action_id, (hx, hy, hw, hh) in self.hitboxes.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                new_hover = action_id
                break

        if new_hover != self.hovered_action:
            self.hovered_action = new_hover
            cursor = Gdk.Cursor.new_from_name("pointer") if new_hover else None
            self.set_cursor(cursor)
            self.bg_draw.queue_draw()

    def _on_mouse_leave(self, controller):
        if self.hovered_action is not None:
            self.hovered_action = None
            self.set_cursor(None)
            self.bg_draw.queue_draw()

    def _on_bubble_clicked(self, gesture, n_press, x, y):
        """Intercepts click, hit-tests buttons, and triggers actions."""
        if self.is_closing:
            return

        # Hit-Test Virtual Buttons
        clicked_action = None
        for action_id, (hx, hy, hw, hh) in self.hitboxes.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                clicked_action = action_id
                break

        # Dispatch payload
        if clicked_action and self.on_action_callback:
            self.on_action_callback(clicked_action)
        elif not clicked_action and self.actions:
            # Eat click if missed but buttons are mandatory
            return

        # Collapse the bubble
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

            # Small trailing thought circles
            cr.new_sub_path()
            cr.arc(box_width / 2 - 5, box_height + 6, 5, 0, 2 * math.pi)
            cr.close_path()

            cr.new_sub_path()
            cr.arc(box_width / 2 - 14, box_height + 16, 3, 0, 2 * math.pi)
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

        # --- VIRTUAL CAIRO BUTTONS ---
        if self.actions:
            self.hitboxes.clear()
            btn_count = len(self.actions)
            btn_margin = 16
            btn_height = 28
            total_btn_width = box_width - (btn_margin * 2)

            gap = 10
            btn_width = (total_btn_width - (gap * (btn_count - 1))) / btn_count

            start_x = btn_margin
            start_y = box_height - btn_height - 12

            cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(12)

            for i, action in enumerate(self.actions):
                ax = start_x + (btn_width + gap) * i
                ay = start_y

                # Map Absolute Widget Coordinates (adding pad offset)
                self.hitboxes[action["id"]] = (ax + pad, ay + pad, btn_width, btn_height)

                # Draw Button Chassis
                br = 6
                cr.new_sub_path()
                cr.arc(ax + br, ay + br, br, math.pi, 3 * math.pi / 2)
                cr.arc(ax + btn_width - br, ay + br, br, -math.pi / 2, 0)
                cr.arc(ax + btn_width - br, ay + btn_height - br, br, 0, math.pi / 2)
                cr.arc(ax + br, ay + btn_height - br, br, math.pi / 2, math.pi)
                cr.close_path()

                is_hovered = (self.hovered_action == action["id"])

                if is_hovered:
                    cr.set_source_rgba(glow_r, glow_g, glow_b, 0.3)
                    cr.fill_preserve()
                    cr.set_source_rgba(*self.glow_color)
                else:
                    cr.set_source_rgba(0.0, 0.0, 0.0, 0.4)
                    cr.fill_preserve()
                    cr.set_source_rgba(glow_r, glow_g, glow_b, 0.7)

                cr.set_line_width(1.2)
                cr.stroke()

                # Draw Button Label
                extents = cr.text_extents(action["label"])
                text_x = ax + (btn_width / 2.0) - (extents.width / 2.0) - extents.x_bearing
                text_y = ay + (btn_height / 2.0) - (extents.height / 2.0) - extents.y_bearing

                if is_hovered:
                    cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
                else:
                    cr.set_source_rgba(0.8, 0.8, 0.8, 1.0)

                cr.move_to(text_x, text_y)
                cr.show_text(action["label"])