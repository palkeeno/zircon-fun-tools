"""Bounded, expiring disk caches for character metadata and rendered posters."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import threading
from PIL import Image
import utils


class PosterCache:
    def __init__(self, directory, ttl=86400, max_entries=200):
        self.directory = Path(directory)
        self.ttl, self.max_entries = ttl, max_entries
        self._lock = threading.RLock()

    def path(self, kind, key):
        return self.directory / (hashlib.sha256(f"{kind}:{key}".encode()).hexdigest() + (".json" if kind == "info" else ".png"))

    def get(self, kind, key):
        with self._lock:
            return self._get(kind, key)

    def _get(self, kind, key):
        path = self.path(kind, key)
        try:
            if time.time() - path.stat().st_mtime > self.ttl:
                return None
            if kind == "info":
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or not value.get("name") or any(not isinstance(v, str) for v in value.values()):
                    return None
                return value
            content = path.read_bytes()
            with Image.open(io.BytesIO(content)) as image:
                if image.format != "PNG" or image.size != (1600, 2100):
                    return None
                image.verify()
            return content
        except (OSError, ValueError, TypeError):
            return None

    def put(self, kind, key, value):
        with self._lock:
            self._put(kind, key, value)

    def _put(self, kind, key, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(kind, key)
        if kind == "info":
            utils.atomic_write_json(path, value)
        else:
            fd, temporary = tempfile.mkstemp(prefix=".poster-", dir=self.directory)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(value)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        # Bound disk growth, including backups produced by the common JSON writer.
        entries = sorted(self.directory.glob("*"), key=lambda entry: entry.stat().st_mtime, reverse=True)
        for old in entries[self.max_entries:]:
            if old.is_file() and not old.name.startswith("."):
                old.unlink(missing_ok=True)
