"""Persistent snapshots of the last administrator change (separate from .bak)."""
import asyncio
import copy
import json
from pathlib import Path

import config
import utils


def snapshot_path(cog, feature, kind):
    data_path = getattr(cog, "data_path", None)
    directory = Path(data_path).parent if isinstance(data_path, (str, Path)) else Path(config._DATA_DIR)
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
            if feature == "birthday":
                from birthday_records import normalize
                restored = [normalize(row) for row in restored]
                dates = {}
                for row in restored:
                    cid, date = row["character_id"], (row["month"], row["day"])
                    if cid in dates and dates[cid] != date:
                        raise ValueError("バックアップのキャラクターIDに異なる誕生日があります")
                    dates[cid] = date
            else:
                from quote_records import normalize_records
                restored, _ = normalize_records(restored)
            attribute = "birthdays" if feature == "birthday" else "quotes"
            previous = getattr(cog, attribute)
            rejected = getattr(cog, "_has_rejected_rows", False)
            setattr(cog, attribute, restored)
            if feature == "quote":
                cog._has_rejected_rows = False
            try:
                await asyncio.to_thread(cog.save_birthdays if feature == "birthday" else cog._save_data)
            except Exception:
                setattr(cog, attribute, previous)
                if feature == "quote":
                    cog._has_rejected_rows = rejected
                raise
