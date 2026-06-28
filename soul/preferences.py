"""Kullanıcı tercihleri - oturumdan oturuma kalıcı."""

import json
from pathlib import Path

PREFS_FILE = Path("data/preferences.json")


class Preferences:
    """Kullanıcı tercihlerini yönetir."""

    def __init__(self):
        self.data: dict = {}
        self._load()

    def _load(self):
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if PREFS_FILE.exists():
            with open(PREFS_FILE) as f:
                self.data = json.load(f)
        else:
            self.data = {
                "language": "tr",
                "theme": "dark",
                "status_bar": True,
                "verbose": False,
                "max_turns": 50,
            }
            self._save()

    def _save(self):
        with open(PREFS_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        self._save()

    def update(self, **kwargs):
        self.data.update(kwargs)
        self._save()


prefs = Preferences()
