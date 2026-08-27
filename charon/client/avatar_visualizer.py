"""
charon/client/avatar_visualizer.py

Cairo GTK4 Wheatley Personality Core Visualizer rendering logic and physics.
"""
import math
import random
import time
import cairo

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from .avatar_states import BASE_ROTATION, EXPRESSIVE_STATES


class AvatarVisualizer(Gtk.DrawingArea):
    """Wheatley Personality Core Visualizer with Overlay Control & Global Pointer Fallback."""

    def __init__(self):
        super().__init__()
        self.set_content_width(100)
        self.set_content_height(100)
        self.set_draw_func(self._draw)

        self.phase = 0.0
        self.rotation_angle = 0.0
        self.state_name = "observing"

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_mouse_motion)
        self.add_controller(motion)

        # Delta Tracking
        self.target_dx = 0.0
        self.target_dy = 0.0
        self.current_dx = 0.0
        self.current_dy = 0.0

        # Set strictly to global coordinate origin (0, 0)
        self.last_raw_mouse_x = None
        self.last_raw_mouse_y = None

        # Pendulum Head Tilt & Idle Tracking
        self.target_head_tilt = 0.0
        self.current_head_tilt = 0.0
        self.last_mouse_move_time = 0.0

        self.external_gaze_active = False
        self.blink_phase = 0.0
        self.is_blinking = False
        self.next_blink_timer = random.randint(120, 240)

        # --- Speech Viseme Tracking ---
        self.target_speech_aperture = 0.0
        self.current_speech_aperture = 0.0

        # Interpolated Parameters
        target = EXPRESSIVE_STATES["observing"]
        self.curr_pulse_speed = target["pulse_speed"]
        self.curr_rot_speed = target["rotation_speed"]
        self.curr_top_lid = target["top_lid"]
        self.curr_bottom_lid = target["bottom_lid"]
        self.curr_lid_tilt = target["lid_tilt"]
        self.curr_core_inner = list(target["core_inner"])
        self.curr_core_outer = list(target["core_outer"])
        self.curr_ring_a = list(target["ring_a"])
        self.curr_ring_b = list(target["ring_b"])

        self.add_tick_callback(self._on_tick)

    # -------------------------------------------------------------------------
    # Public API & Gaze Math
    # -------------------------------------------------------------------------

    def set_speech_viseme(self, scale: float):
        """
        Called by the synchronized audio playback thread.
        Scale should be 0.0 (silent) to 1.0 (loudest).
        """
        self.target_speech_aperture = scale

        # Auto-state management based on speech
        if scale > 0.05 and self.state_name == "observing":
            self.set_expressive_state("expressing")
        elif scale == 0.0 and self.state_name == "expressing":
            self.set_expressive_state("observing")

    def set_expressive_state(self, state_name: str):
        if state_name in EXPRESSIVE_STATES:
            self.state_name = state_name

    def set_target_gaze(self, x: float, y: float, screen_w: float = None, screen_h: float = None):
        """Standard window-relative or screen-mapped overlay controller gaze update."""
        self.external_gaze_active = True
        self._route_gaze(x, y, screen_w, screen_h)

    def set_target_gaze_relative(self, mouse_x: float, mouse_y: float, center_x: float, center_y: float,
                                 map_width: float, map_height: float):
        """Global coordinate update mapped proportionally to Mutter desktop boundaries."""
        self.external_gaze_active = True

        # Calculate absolute distance vector
        raw_dx = mouse_x - center_x
        raw_dy = mouse_y - center_y

        # Determine max possible travel to the screen edge from the window's current position
        max_x = center_x if raw_dx < 0 else (map_width - center_x)
        max_y = center_y if raw_dy < 0 else (map_height - center_y)

        # Guard against division by zero if pinned exactly to a screen edge
        max_x = max(1.0, max_x)
        max_y = max(1.0, max_y)

        # Normalize to a smooth -1.0 to 1.0 scale proportional to the desktop bounds
        norm_x = raw_dx / max_x
        norm_y = raw_dy / max_y

        # Pass the normalized delta to the gaze handler, scaling to a virtual 200px radius
        self._update_gaze(norm_x * 200.0, norm_y * 200.0, cx=0.0, cy=0.0)

    def _route_gaze(self, x: float, y: float, screen_w: float = None, screen_h: float = None):
        """Intercepts and auto-normalizes global coordinates across multi-monitor setups."""
        if (screen_w is None or screen_h is None) and (abs(x) > 300 or abs(y) > 300):
            display = Gdk.Display.get_default()
            if display:
                monitors = display.get_monitors()
                total_w, max_h = 0, 0
                for i in range(monitors.get_n_items()):
                    geom = monitors.get_item(i).get_geometry()
                    total_w += geom.width
                    max_h = max(max_h, geom.height)

                if total_w > 0:
                    screen_w = float(total_w)
                    screen_h = float(max_h)

        if screen_w and x > screen_w:
            screen_w = float(math.ceil(x / 1920.0) * 1920.0)
        if screen_h and y > screen_h:
            screen_h = float(math.ceil(y / 1080.0) * 1080.0)

        if screen_w and screen_h:
            norm_x = (x / screen_w) * 2.0 - 1.0
            norm_y = (y / screen_h) * 2.0 - 1.0
            self._update_gaze(norm_x * 200.0, norm_y * 200.0, cx=0.0, cy=0.0)
        else:
            self._update_gaze(x, y)

    def reset_gaze_to_idle(self):
        self.external_gaze_active = False
        self.target_dx = 0.0
        self.target_dy = 0.0

    def _update_gaze(self, mouse_x: float, mouse_y: float, cx: float = None, cy: float = None):
        if cx is None: cx = self.get_width() / 2.0
        if cy is None: cy = self.get_height() / 2.0

        if self.last_raw_mouse_x is None or self.last_raw_mouse_y is None:
            self.last_raw_mouse_x = mouse_x
            self.last_raw_mouse_y = mouse_y

        delta_moved = math.hypot(mouse_x - self.last_raw_mouse_x, mouse_y - self.last_raw_mouse_y)

        if delta_moved > 0.5:
            self.last_mouse_move_time = time.time()

        self.last_raw_mouse_x = mouse_x
        self.last_raw_mouse_y = mouse_y
        self.target_dx = mouse_x - cx
        self.target_dy = mouse_y - cy

    def _on_mouse_motion(self, controller, x: float, y: float):
        if not self.external_gaze_active:
            self._update_gaze(x, y)

    def _poll_global_mouse_position(self):
        if self.external_gaze_active or not self.get_mapped() or self.get_width() <= 10:
            return

        native = self.get_native()
        if not native: return
        surface = native.get_surface()
        if not surface or not surface.get_display(): return
        seat = surface.get_display().get_default_seat()
        if not seat or not seat.get_pointer(): return

        res = surface.get_device_position(seat.get_pointer())
        if res:
            is_over, surface_x, surface_y, _ = res
            if not is_over:
                self.reset_gaze_to_idle()
                return
            self._update_gaze(surface_x, surface_y)

    def _lerp(self, current: float, target: float, factor: float = 0.1) -> float:
        return current + (target - current) * factor

    def _lerp_color(self, current: list, target: tuple, factor: float = 0.1) -> list:
        return [self._lerp(c, t, factor) for c, t in zip(current, target)]

    # -------------------------------------------------------------------------
    # Tick & Pendulum Logic
    # -------------------------------------------------------------------------

    def _on_tick(self, widget, frame_clock):
        self._poll_global_mouse_position()

        # Smooth the raw audio scale (use a fast factor like 0.4 for snappy lipsync)
        self.current_speech_aperture = self._lerp(
            self.current_speech_aperture,
            self.target_speech_aperture,
            0.4
        )

        target = EXPRESSIVE_STATES.get(self.state_name, EXPRESSIVE_STATES["observing"])

        # Base lerps
        self.curr_pulse_speed = self._lerp(self.curr_pulse_speed, target["pulse_speed"])
        self.curr_rot_speed = self._lerp(self.curr_rot_speed, target["rotation_speed"])
        self.curr_top_lid = self._lerp(self.curr_top_lid, target["top_lid"])
        self.curr_bottom_lid = self._lerp(self.curr_bottom_lid, target["bottom_lid"])
        self.curr_lid_tilt = self._lerp(self.curr_lid_tilt, target["lid_tilt"])
        self.curr_core_inner = self._lerp_color(self.curr_core_inner, target["core_inner"])
        self.curr_core_outer = self._lerp_color(self.curr_core_outer, target["core_outer"])
        self.curr_ring_a = self._lerp_color(self.curr_ring_a, target["ring_a"])
        self.curr_ring_b = self._lerp_color(self.curr_ring_b, target["ring_b"])

        dx = self.target_dx
        dy = self.target_dy
        dist = math.hypot(dx, dy)
        time_since_move = time.time() - self.last_mouse_move_time

        if dist > 0 and time_since_move < 0.3:
            if dx < 0 and dy < 0: tilt_dir = -1.0
            elif dx > 0 and dy < 0: tilt_dir = 1.0
            elif dx > 0 and dy > 0: tilt_dir = -1.0
            elif dx < 0 and dy > 0: tilt_dir = 1.0
            else: tilt_dir = 0.0

            abs_angle = math.atan2(abs(dy), abs(dx))
            pendulum_magnitude = math.sin(abs_angle * 2.0)
            MAX_TILT = math.radians(25.0)
            deadzone = min(1.0, dist / 150.0)
            self.target_head_tilt = tilt_dir * MAX_TILT * pendulum_magnitude * deadzone
        else:
            self.target_head_tilt = 0.0

        if time_since_move < 3.0:
            active_dx = self.target_dx
            active_dy = self.target_dy
        else:
            active_dx = 0.0
            active_dy = 0.0

        jitter_x = random.uniform(-1.0, 1.0) if self.state_name == "thinking" else 0.0
        jitter_y = random.uniform(-1.0, 1.0) if self.state_name == "thinking" else 0.0

        self.current_dx = self._lerp(self.current_dx, active_dx + jitter_x, 0.14)
        self.current_dy = self._lerp(self.current_dy, active_dy + jitter_y, 0.14)
        self.current_head_tilt = self._lerp(self.current_head_tilt, self.target_head_tilt, 0.08)

        # Blinking
        self.next_blink_timer -= 1
        if self.next_blink_timer <= 0 and not self.is_blinking:
            self.is_blinking = True
            self.blink_phase = 0.0

        if self.is_blinking:
            self.blink_phase += 0.18
            if self.blink_phase >= 1.0:
                self.is_blinking = False
                self.blink_phase = 0.0
                self.next_blink_timer = random.randint(120, 300)

        self.phase += self.curr_pulse_speed
        self.rotation_angle += self.curr_rot_speed
        if self.phase > 2 * math.pi: self.phase -= 2 * math.pi
        if self.rotation_angle > 2 * math.pi: self.rotation_angle -= 2 * math.pi

        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    # -------------------------------------------------------------------------
    # Rendering Pipeline
    # -------------------------------------------------------------------------

    def _draw(self, area, cr: cairo.Context, width: int, height: int):
        cx, cy = width / 2.0, height / 2.0
        r_body = min(width, height) * 0.38
        r_bezel = r_body * 0.68
        r_core = r_bezel * 0.72

        # Add speech_aperture to the baseline sine wave pulse
        pulse = 1.0 + 0.06 * math.sin(self.phase * 2) + (self.current_speech_aperture * 0.15)

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        total_rotation = BASE_ROTATION + self.current_head_tilt

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(total_rotation)
        cr.translate(-cx, -cy)

        self._draw_roll_bars(cr, cx, cy, r_body)
        self._draw_core_body_shell(cr, cx, cy, r_body)

        bezel_grad = cairo.RadialGradient(cx, cy, r_bezel * 0.2, cx, cy, r_bezel)
        bezel_grad.add_color_stop_rgba(0.0, 0.08, 0.12, 0.18, 0.98)
        bezel_grad.add_color_stop_rgba(0.85, 0.03, 0.05, 0.08, 0.98)
        bezel_grad.add_color_stop_rgba(1.0, 0.25, 0.32, 0.42, 0.9)
        cr.arc(cx, cy, r_bezel, 0, 2 * math.pi)
        cr.set_source(bezel_grad)
        cr.fill()

        dx_screen = self.current_dx
        dy_screen = self.current_dy
        dist = math.hypot(dx_screen, dy_screen)
        max_travel = r_bezel * 0.35

        if dist > max_travel and dist > 0:
            dx_screen = (dx_screen / dist) * max_travel
            dy_screen = (dy_screen / dist) * max_travel

        cos_t = math.cos(-total_rotation)
        sin_t = math.sin(-total_rotation)
        dx_local = dx_screen * cos_t - dy_screen * sin_t
        dy_local = dx_screen * sin_t + dy_screen * cos_t

        eye_cx = cx + dx_local
        eye_cy = cy + dy_local

        pupil_shift_x = 0.0
        pupil_shift_y = 0.0
        if max_travel > 0:
            pupil_shift_x = (dx_local / max_travel) * (r_core * 0.45)
            pupil_shift_y = (dy_local / max_travel) * (r_core * 0.45)

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(self.rotation_angle)
        cr.set_line_width(1.3)
        cr.set_source_rgba(*self.curr_ring_a)
        self._draw_polygon(cr, 0, 0, r_bezel * 0.9 * pulse, 8)
        cr.stroke()
        cr.restore()

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(-self.rotation_angle * 1.3)
        cr.set_line_width(1.1)
        cr.set_source_rgba(*self.curr_ring_b)
        self._draw_polygon(cr, 0, 0, r_bezel * 0.78, 6)
        cr.stroke()
        cr.restore()

        pupil_grad = cairo.RadialGradient(
            eye_cx + pupil_shift_x, eye_cy + pupil_shift_y, r_core * 0.08,
            eye_cx, eye_cy, r_core * pulse
        )
        pupil_grad.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.98)
        pupil_grad.add_color_stop_rgba(0.35, *self.curr_core_inner)
        pupil_grad.add_color_stop_rgba(0.85, *self.curr_core_outer)
        pupil_grad.add_color_stop_rgba(1.0, 0.05, 0.08, 0.14, 0.95)

        cr.arc(eye_cx, eye_cy, r_core * pulse, 0, 2 * math.pi)
        cr.set_source(pupil_grad)
        cr.fill()

        self._draw_shutter_eyelids(cr, cx, cy, r_bezel)
        self._draw_chassis_leds(cr, cx, cy, r_body)

        cr.restore()

    def _draw_core_body_shell(self, cr: cairo.Context, cx: float, cy: float, R: float):
        shell_grad = cairo.RadialGradient(cx - R * 0.35, cy - R * 0.35, R * 0.1, cx, cy, R)
        shell_grad.add_color_stop_rgba(0.0, 0.94, 0.96, 0.98, 0.98)
        shell_grad.add_color_stop_rgba(0.65, 0.75, 0.8, 0.85, 0.98)
        shell_grad.add_color_stop_rgba(0.92, 0.32, 0.38, 0.46, 0.98)
        shell_grad.add_color_stop_rgba(1.0, 0.12, 0.16, 0.22, 0.98)

        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.set_source(shell_grad)
        cr.fill()

        cr.set_line_width(1.2)
        cr.set_source_rgba(0.1, 0.14, 0.2, 0.7)
        cr.arc(cx, cy, R * 0.88, math.pi * 1.15, math.pi * 1.85)
        cr.stroke()
        cr.arc(cx, cy, R * 0.88, math.pi * 0.15, math.pi * 0.85)
        cr.stroke()

        cr.set_source_rgba(0.2, 0.25, 0.35, 0.8)
        for angle in [math.pi * 0.25, math.pi * 0.75, math.pi * 1.25, math.pi * 1.75]:
            rx = cx + R * 0.86 * math.cos(angle)
            ry = cy + R * 0.86 * math.sin(angle)
            cr.arc(rx, ry, 1.2, 0, 2 * math.pi)
            cr.fill()

    def _draw_roll_bars(self, cr: cairo.Context, cx: float, cy: float, R: float):
        bar_grad = cairo.LinearGradient(cx - R * 1.2, cy, cx + R * 1.2, cy)
        bar_grad.add_color_stop_rgba(0.0, 0.2, 0.25, 0.32, 0.95)
        bar_grad.add_color_stop_rgba(0.5, 0.6, 0.65, 0.72, 0.95)
        bar_grad.add_color_stop_rgba(1.0, 0.2, 0.25, 0.32, 0.95)

        cr.set_source(bar_grad)
        cr.set_line_width(3.2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.arc(cx, cy - R * 0.15, R * 1.12, math.pi * 1.22, math.pi * 1.78)
        cr.stroke()
        cr.arc(cx, cy + R * 0.15, R * 1.12, math.pi * 0.22, math.pi * 0.78)
        cr.stroke()

    def _draw_chassis_leds(self, cr: cairo.Context, cx: float, cy: float, R: float):
        pulse_alpha = 0.6 + 0.35 * math.sin(self.phase * 3)
        for side in [-1, 1]:
            lx = cx + side * (R * 0.82)
            ly = cy
            led_glow = cairo.RadialGradient(lx, ly, 0.5, lx, ly, 4.5)
            led_glow.add_color_stop_rgba(0.0, self.curr_core_inner[0], self.curr_core_inner[1], self.curr_core_inner[2], pulse_alpha)
            led_glow.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
            cr.arc(lx, ly, 4.5, 0, 2 * math.pi)
            cr.set_source(led_glow)
            cr.fill()
            cr.arc(lx, ly, 1.5, 0, 2 * math.pi)
            cr.set_source_rgba(0.95, 0.98, 1.0, 0.95)
            cr.fill()

    def _draw_shutter_eyelids(self, cr: cairo.Context, cx: float, cy: float, R: float):
        blink_factor = math.sin(self.blink_phase * math.pi) if self.is_blinking else 0.0

        # Speech makes the eyelids open wider (max 20% wider at peak volume)
        speech_bounce = self.current_speech_aperture * 0.20

        # Ensure lids don't go below 0 (fully open)
        effective_top = max(0.1, self.curr_top_lid - speech_bounce) * (1.0 - blink_factor)
        effective_bottom = max(0.1, self.curr_bottom_lid - speech_bounce) * (1.0 - blink_factor)

        top_y = cy - (R * effective_top)
        bottom_y = cy + (R * effective_bottom)
        tilt = self.curr_lid_tilt * R

        cr.save()
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.clip()

        p1_x, p1_y = cx - R * 1.1, cy - tilt * 0.8
        p2_x, p2_y = cx + R * 1.1, cy + tilt * 0.8

        cr.save()
        cr.move_to(p1_x, p1_y)
        cr.curve_to(cx - R * 0.45, top_y - tilt * 0.4, cx + R * 0.45, top_y + tilt * 0.4, p2_x, p2_y)
        cr.line_to(cx + R * 1.1, cy - R * 1.2)
        cr.curve_to(cx + R * 0.6, cy - R * 1.35, cx - R * 0.6, cy - R * 1.35, cx - R * 1.1, cy - R * 1.2)
        cr.close_path()

        top_grad = cairo.LinearGradient(cx, cy - R, cx, top_y)
        top_grad.add_color_stop_rgba(0.0, 0.04, 0.06, 0.10, 0.98)
        top_grad.add_color_stop_rgba(0.7, 0.12, 0.16, 0.24, 0.98)
        top_grad.add_color_stop_rgba(1.0, 0.22, 0.28, 0.38, 0.98)

        cr.set_source(top_grad)
        cr.fill_preserve()
        cr.set_source_rgba(*self.curr_ring_a)
        cr.set_line_width(1.8)
        cr.stroke()

        cr.move_to(cx - R * 0.75, top_y - R * 0.22)
        cr.curve_to(cx - R * 0.25, top_y - R * 0.16, cx + R * 0.25, top_y - R * 0.16, cx + R * 0.75, top_y - R * 0.22)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.45)
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()

        cr.save()
        cr.move_to(p1_x, p1_y)
        cr.curve_to(cx - R * 0.45, bottom_y - tilt * 0.4, cx + R * 0.45, bottom_y + tilt * 0.4, p2_x, p2_y)
        cr.line_to(cx + R * 1.1, cy + R * 1.2)
        cr.curve_to(cx + R * 0.6, cy + R * 1.35, cx - R * 0.6, cy + R * 1.35, cx - R * 1.1, cy + R * 1.2)
        cr.close_path()

        bottom_grad = cairo.LinearGradient(cx, bottom_y, cx, cy + R)
        bottom_grad.add_color_stop_rgba(0.0, 0.22, 0.28, 0.38, 0.98)
        bottom_grad.add_color_stop_rgba(0.3, 0.12, 0.16, 0.24, 0.98)
        bottom_grad.add_color_stop_rgba(1.0, 0.04, 0.06, 0.10, 0.98)

        cr.set_source(bottom_grad)
        cr.fill_preserve()
        cr.set_source_rgba(*self.curr_ring_b)
        cr.set_line_width(1.8)
        cr.stroke()

        cr.move_to(cx - R * 0.75, bottom_y + R * 0.22)
        cr.curve_to(cx - R * 0.25, bottom_y + R * 0.16, cx + R * 0.25, bottom_y + R * 0.16, cx + R * 0.75, bottom_y + R * 0.22)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.45)
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()
        cr.restore()

    def _draw_polygon(self, cr: cairo.Context, cx: float, cy: float, radius: float, sides: int):
        angle_step = 2 * math.pi / sides
        for i in range(sides):
            angle = i * angle_step
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.close_path()