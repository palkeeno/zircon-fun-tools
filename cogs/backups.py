"""Persistent snapshots of the last administrator change (separate from .bak)."""
import asyncio
import copy
import json
from pathlib import Path

import config
import utils


def snapshot_path(cog, feature, kind):
    directory = Path(getattr(cog, "data_path", Path(config._DATA_DIR) / "quotes.json")).parent if feature == "quote" else Path(config._DATA_DIR)
    return directory / "backups" / f"{feature}-{kind}.json"


def payload(cog, feature, kind):
    if kind == "settings":
        return copy.deepcopy(cog.settings)
    return copy.deepcopy(cog.birthdays if feature == "birthday" else cog.quotes)


def save_snapshot(cog, feature, kind):
    utils.atomic_write_json(snapshot_path(cog, feature, kind), payload(cog, feature, kind))


def persist_with_snapshot(cog, feature, kind, write, previous=None):
    """Keep the prior restore point if the live write fails. Caller holds the cog lock."""
    path = snapshot_path(cog, feature, kind)
    old_backup = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    had_backup = path.exists()
    before = payload(cog, feature, kind) if previous is None else previous
    utils.atomic_write_json(path, before)
    try:
        write()
    except Exception:
        if had_backup:
            utils.atomic_write_json(path, old_backup)
        else:
            path.unlink()
        raise


class SnapshotChangedError(ValueError):
    """The administrator must confirm the new restore point again."""


async def restore_snapshot(cog, feature, kind, expected=None):
    async with cog._data_lock:
        path = snapshot_path(cog, feature, kind)
        def read():
            content = path.read_bytes()
            if expected is not None and content != expected:
                raise SnapshotChangedError("Backup changed after confirmation opened")
            return json.loads(content)
        restored = await asyncio.to_thread(read)
        if kind == "settings":
            if not isinstance(restored, dict):
                raise ValueError("Invalid settings backup")
            section = "birthday" if feature == "birthday" else "quotes"
            await asyncio.to_thread(config.set_runtime_section, section, restored)
            cog.settings = restored
        else:
            if not isinstance(restored, list) or any(not isinstance(row, dict) for row in restored):
                raise ValueError("Invalid data backup")
            attribute = "birthdays" if feature == "birthday" else "quotes"
            previous = getattr(cog, attribute)
            setattr(cog, attribute, restored)
            try:
                await asyncio.to_thread(cog.save_birthdays if feature == "birthday" else cog._save_data)
            except Exception:
                setattr(cog, attribute, previous)
                raise
