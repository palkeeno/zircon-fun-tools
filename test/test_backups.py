import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config
import utils
from cogs.backups import save_snapshot, restore_snapshot, snapshot_path
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
