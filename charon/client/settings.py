"""
charon/client/settings.py
System Version: v3.9.0

Module: Manages JSON configuration and window bounds state stored alongside the application.
"""

import json
import os
from pathlib import Path


class OverlaySettings:
    """Manages JSON configuration and window bounds state."""

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