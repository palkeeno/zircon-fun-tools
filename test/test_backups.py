import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config
import utils
from cogs.backups import save_snapshot, restore_snapshot, snapshot_path, persist_with_snapshot, SnapshotChangedError
from cogs.admin_panel import AdminPanel, RestoreConfirmation
from unittest.mock import MagicMock, AsyncMock


class BackupTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_restore_and_failed_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'quotes.json'
            cog = SimpleNamespace(data_path=str(path), quotes=[{'text': '以前の名言'}], settings={'hour': 9}, _data_lock=asyncio.Lock())
            cog._save_data = lambda: utils.atomic_write_json(path, {'quotes': cog.quotes})
            save_snapshot(cog, 'quote', 'data')
            cog.quotes = [{'text': '更新後'}]
            cog._save_data()
            # A normal scheduled write must not overwrite the administrator snapshot.
            cog._save_data()
            restored = SimpleNamespace(**vars(cog))
            restored._save_data = lambda: utils.atomic_write_json(path, {'quotes': restored.quotes})
            await restore_snapshot(restored, 'quote', 'data')
            self.assertEqual(restored.quotes, [{'text': '以前の名言'}])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['quotes'], restored.quotes)
            restored.quotes = [{'text': '現在'}]
            with patch.object(restored, '_save_data', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    await restore_snapshot(restored, 'quote', 'data')
            self.assertEqual(restored.quotes, [{'text': '現在'}])

    async def test_settings_restore_keeps_other_feature(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(config, '_DATA_DIR', directory), patch.object(config, '_RUNTIME_CONFIG_PATH', str(Path(directory) / 'config.json')):
            config.set_runtime_section('quotes', {'hour': 18})
            cog = SimpleNamespace(settings={'hour': 9, 'enabled': True}, _data_lock=asyncio.Lock())
            save_snapshot(cog, 'birthday', 'settings')
            cog.settings = {'hour': 12, 'enabled': False}
            await restore_snapshot(cog, 'birthday', 'settings')
            self.assertEqual(cog.settings['hour'], 9)
            self.assertEqual(config.get_runtime_section('quotes'), {'hour': 18})
            self.assertEqual(config.get_runtime_section('birthday'), cog.settings)

    async def test_export_json_and_confirmation_owner(self):
        cog = MagicMock()
        cog._data_lock = asyncio.Lock()
        cog.quotes = [{'speaker': '話者', 'text': '名言'}]
        cog.settings = {'hour': 9}
        panel = AdminPanel(cog, 'quote', 123)
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup.send = AsyncMock()
        await panel.export_data.callback(interaction)
        call = interaction.followup.send.call_args.kwargs
        self.assertTrue(call['ephemeral'])
        self.assertEqual(json.load(call['file'].fp), cog.quotes)
        confirmation = RestoreConfirmation(panel, 'data')
        interaction.user.id = 456
        self.assertFalse(await confirmation.interaction_check(interaction))
        interaction.user.id = 123
        panel.stop()
        self.assertFalse(await confirmation.interaction_check(interaction))


    async def test_failed_change_preserves_restore_point(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = SimpleNamespace(data_path=str(Path(directory) / "quotes.json"), quotes=[{"text": "original"}])
            save_snapshot(cog, "quote", "data")
            path = snapshot_path(cog, "quote", "data")
            original = path.read_bytes()
            cog.quotes = [{"text": "current"}]
            def fail():
                raise OSError("disk failure")
            with self.assertRaises(OSError):
                persist_with_snapshot(cog, "quote", "data", fail)
            self.assertEqual(path.read_bytes(), original)
            path.unlink()
            with self.assertRaises(OSError):
                persist_with_snapshot(cog, "quote", "data", fail)
            self.assertFalse(path.exists())

    async def test_stale_confirmation_does_not_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            cog = SimpleNamespace(data_path=str(Path(directory) / "quotes.json"), quotes=[{"text": "original"}], _data_lock=asyncio.Lock())
            cog._save_data = MagicMock()
            save_snapshot(cog, "quote", "data")
            expected = snapshot_path(cog, "quote", "data").read_bytes()
            cog.quotes = [{"text": "new"}]
            save_snapshot(cog, "quote", "data")
            with self.assertRaises(SnapshotChangedError):
                await restore_snapshot(cog, "quote", "data", expected)
            cog._save_data.assert_not_called()
            self.assertEqual(cog.quotes, [{"text": "new"}])

    async def test_automatic_birthday_settings_leave_snapshot_unchanged(self):
        from cogs.birthday import Birthday
        with tempfile.TemporaryDirectory() as directory, patch.object(config, "_DATA_DIR", directory), patch.object(config, "_RUNTIME_CONFIG_PATH", str(Path(directory) / "config.json")):
            cog = Birthday.__new__(Birthday)
            cog._data_lock = asyncio.Lock()
            cog.settings = {"hour": 9, "enabled": True}
            await cog._change_settings({"hour": 12})
            path = snapshot_path(cog, "birthday", "settings")
            original = path.read_bytes()
            await cog._change_settings({"last_announced_date": "2026-10-09"}, backup=False)
            self.assertEqual(path.read_bytes(), original)
            await restore_snapshot(cog, "birthday", "settings")
            self.assertEqual(cog.settings["hour"], 9)

    async def test_data_change_records_old_memory_and_round_trips(self):
        from cogs.quotes import Quotes
        with tempfile.TemporaryDirectory() as directory:
            cog = Quotes.__new__(Quotes)
            cog.data_path = str(Path(directory) / "quotes.json")
            cog._data_lock = asyncio.Lock()
            cog.tz = utils.get_timezone()
            cog.quotes = [{"speaker": "old", "text": "old", "id": "retained"}]
            old = list(cog.quotes)
            interaction = MagicMock()
            interaction.user.id = 123
            interaction.response = AsyncMock()
            interaction.followup = AsyncMock()
            file = MagicMock(filename="quote-data.json")
            file.read = AsyncMock(return_value=b'[{"speaker":"new","text":"new"}]')
            await cog._quote_update(interaction, file)
            self.assertEqual(cog.quotes[0]["text"], "new")
            await restore_snapshot(cog, "quote", "data")
            self.assertEqual(cog.quotes, old)
            self.assertEqual(json.loads(Path(cog.data_path).read_text())["quotes"], old)
