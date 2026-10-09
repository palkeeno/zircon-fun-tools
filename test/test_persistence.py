import test  # isolate credentials and storage before importing application code
import asyncio
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import config
import utils
class EnvironmentTests(unittest.TestCase):

    def test_atomic_save_failure_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            path.write_text('["old"]', encoding='utf-8')
            with patch('os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    utils.atomic_write_json(path, ['new'])
            self.assertEqual(json.loads(path.read_text()), ['old'])
            self.assertEqual(list(Path(directory).iterdir()), [path])

class CacheTests(unittest.TestCase):

    def test_backup_contains_previous_successful_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            utils.atomic_write_json(path, ['old'])
            utils.atomic_write_json(path, ['new'])
            self.assertEqual(json.loads(path.read_text()), ['new'])
            self.assertEqual(json.loads(Path(str(path) + '.bak').read_text()), ['old'])

    def test_destination_failure_keeps_old_data_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            utils.atomic_write_json(path, ['old'])
            replace = os.replace

            def fail_destination(source, destination):
                if str(destination) == str(path):
                    raise OSError('disk failure')
                replace(source, destination)
            with patch('os.replace', side_effect=fail_destination):
                with self.assertRaises(OSError):
                    utils.atomic_write_json(path, ['new'])
            self.assertEqual(json.loads(path.read_text()), ['old'])
            self.assertEqual(json.loads(Path(str(path) + '.bak').read_text()), ['old'])


from concurrent.futures import ThreadPoolExecutor
from cogs.birthday import Birthday
from cogs.quotes import Quotes

class RuntimePersistenceTests(unittest.TestCase):
    def test_corrupted_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("broken", encoding="utf-8")
            with patch.object(config, "_RUNTIME_CONFIG_PATH", str(path)), patch.object(config, "_DATA_DIR", directory):
                with self.assertRaises(json.JSONDecodeError):
                    config.set_runtime_section("birthday", {"enabled": True})
            self.assertEqual(path.read_text(), "broken")

    def test_concurrent_sections_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch.object(config, "_RUNTIME_CONFIG_PATH", str(path)), patch.object(config, "_DATA_DIR", directory):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(config.set_runtime_section, section, {"enabled": True}) for section in ["birthday", "quotes"]]
                    for future in futures:
                        future.result()
            self.assertEqual(set(json.loads(path.read_text())), {"birthday", "quotes"})

class SettingsPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_save_does_not_change_effective_settings(self):
        for cog_class in [Birthday, Quotes]:
            cog = cog_class.__new__(cog_class)
            cog._data_lock = asyncio.Lock()
            cog.settings = {"enabled": True}
            with patch("config.set_runtime_section", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    await cog._change_settings({"enabled": False})
            self.assertTrue(cog.settings["enabled"])

    async def test_quote_import_save_failure_rolls_back(self):
        cog = Quotes.__new__(Quotes)
        cog._data_lock = asyncio.Lock()
        cog.tz = utils.get_timezone()
        cog.quotes = [{"speaker": "old", "text": "old"}]
        original = cog.quotes
        cog._save_data = MagicMock(side_effect=OSError("disk failure"))
        interaction = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        file = MagicMock(filename="data.json")
        file.read = AsyncMock(return_value=b'[{"speaker":"new","text":"new"}]')
        with self.assertRaises(OSError):
            await Quotes.quote_update.callback(cog, interaction, file)
        self.assertIs(cog.quotes, original)
        interaction.followup.send.assert_not_called()
