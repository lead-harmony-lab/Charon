"""
charon/client/avatar_states.py

Configuration and personality profiles for the Wheatley Personality Core.
"""
import math

# Neutral base orientation
BASE_ROTATION = math.radians(-180.0)

EXPRESSIVE_STATES = {
    "observing": {
        "pulse_speed": 0.02,
        "rotation_speed": 0.012,
        "top_lid": 0.55,
        "bottom_lid": 0.65,
        "lid_tilt": 0.0,
        "core_inner": (0.0, 0.95, 1.0, 0.95),
        "core_outer": (0.0, 0.5, 0.9, 0.8),
        "ring_a": (0.0, 0.95, 1.0, 0.7),
        "ring_b": (0.5, 0.0, 0.8, 0.5),
    },
    "thinking": {
        "pulse_speed": 0.065,
        "rotation_speed": 0.05,
        "top_lid": 0.22,
        "bottom_lid": 0.35,
        "lid_tilt": 0.18,
        "core_inner": (1.0, 0.0, 0.5, 0.95),
        "core_outer": (1.0, 0.84, 0.0, 0.85),
        "ring_a": (1.0, 0.0, 0.5, 0.8),
        "ring_b": (1.0, 0.84, 0.0, 0.7),
    },
    "expressing": {
        "pulse_speed": 0.045,
        "rotation_speed": 0.03,
        "top_lid": 0.68,
        "bottom_lid": 0.72,
        "lid_tilt": 0.05,
        "core_inner": (0.0, 0.95, 1.0, 0.95),
        "core_outer": (0.54, 0.17, 0.89, 0.85),
        "ring_a": (0.0, 0.95, 1.0, 0.85),
        "ring_b": (0.9, 0.1, 0.6, 0.75),
    },
    "alert": {
        "pulse_speed": 0.11,
        "rotation_speed": 0.085,
        "top_lid": 0.95,
        "bottom_lid": 0.95,
        "lid_tilt": 0.0,
        "core_inner": (1.0, 0.0, 0.2, 0.98),
        "core_outer": (1.0, 0.5, 0.0, 0.9),
        "ring_a": (1.0, 0.1, 0.1, 0.95),
        "ring_b": (1.0, 0.6, 0.0, 0.85),
    },
}