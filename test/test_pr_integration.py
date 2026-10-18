"""Regression coverage for the independently developed open PRs together."""
import test
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
import utils
from cogs.backups import restore_snapshot, snapshot_path
from cogs.birthday import Birthday
from cogs.quotes import Quotes


class IntegratedRestoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.addCleanup(patch.stopall)
        patch.object(config, "_DATA_DIR", str(self.root / "config")).start()
        patch.object(config, "_RUNTIME_CONFIG_PATH", str(self.root / "config" / "config.json")).start()
        self.item = MagicMock()
        self.item.user.id = 123
        self.item.response = AsyncMock()
        self.item.followup = AsyncMock()
        self.path = self.root / "records" / "data.json"

    async def test_birthday_individual_changes_keep_correct_local_restore_point(self):
        cog = Birthday(MagicMock(), str(self.path))
        await Birthday.birthday_add.callback(cog, self.item, "1", "Before", 2, 28)
        backup = snapshot_path(cog, "birthday", "data")
        self.assertEqual(backup.parent, self.path.parent / "backups")
        self.assertEqual(json.loads(backup.read_text()), [])
        original = copy.deepcopy(cog.birthdays)
        await Birthday.birthday_edit.callback(cog, self.item, "1", name="After")
        self.assertEqual(json.loads(backup.read_text()), original)
        await restore_snapshot(cog, "birthday", "data", backup.read_bytes())
        self.assertEqual(cog.birthdays, original)
        await Birthday.birthday_delete.callback(cog, self.item, "1", confirm=True)
        self.assertEqual(cog.birthdays, [])
        await restore_snapshot(cog, "birthday", "data")
        self.assertEqual(cog.birthdays, original)
        self.assertEqual(json.loads(self.path.read_text()), original)

    async def test_quote_individual_changes_restore_identity_and_creation_history(self):
        cog = Quotes(MagicMock(), str(self.path))
        await Quotes.quote_add.callback(cog, self.item, "Speaker", "Before", "1")
        original = copy.deepcopy(cog.quotes)
        identity = original[0]["id"]
        await Quotes.quote_edit.callback(cog, self.item, identity, text="After")
        backup = snapshot_path(cog, "quote", "data")
        self.assertEqual(json.loads(backup.read_text()), original)
        await restore_snapshot(cog, "quote", "data")
        self.assertEqual(cog.quotes, original)
        await Quotes.quote_delete.callback(cog, self.item, identity, confirm=True)
        self.assertEqual(cog.quotes, [])
        await restore_snapshot(cog, "quote", "data")
        self.assertEqual(cog.quotes, original)

    async def test_leap_day_rejected_by_crud_and_year_omitted_from_bulk(self):
        cog = Birthday(MagicMock(), str(self.path))
        with self.assertRaises(ValueError):
            await Birthday.birthday_add.callback(cog, self.item, "1", "A", 2, 29)
        self.assertEqual(cog.birthdays, [])
        upload = MagicMock(filename="birthdays.json")
        upload.read = AsyncMock(return_value=b'[{"character_id":"1","name":"A","month":2,"day":28,"year":1999}]')
        await cog._birthday_update(self.item, upload)
        self.assertEqual(cog.birthdays[0]["day"], 28)
        self.assertNotIn("year", json.loads(self.path.read_text())[0])

    async def test_invalid_quote_restore_does_not_bypass_validation(self):
        cog = Quotes(MagicMock(), str(self.path))
        await Quotes.quote_add.callback(cog, self.item, "A", "Original")
        original = cog.quotes
        content = self.path.read_bytes()
        backup = snapshot_path(cog, "quote", "data")
        for rows in [[{"speaker": "A", "text": " "}],
                     [{"speaker": "A", "text": "one", "id": "same"}, {"speaker": "B", "text": "two", "id": "same"}]]:
            utils.atomic_write_json(backup, rows)
            with self.assertRaises(ValueError):
                await restore_snapshot(cog, "quote", "data")
            self.assertIs(cog.quotes, original)
            self.assertEqual(self.path.read_bytes(), content)

    async def test_valid_restore_repairs_rejected_rows_but_failed_save_retains_guard(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('[{"speaker":"A","text":"Original","id":"current"},null]')
        cog = Quotes(MagicMock(), str(self.path))
        self.assertTrue(cog._has_rejected_rows)
        original = cog.quotes
        backup = snapshot_path(cog, "quote", "data")
        rows = [{"speaker": "A", "text": "Healthy", "id": "healthy", "character_id": None}]
        utils.atomic_write_json(backup, rows)
        with patch.object(cog, "_save_data", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                await restore_snapshot(cog, "quote", "data")
        self.assertIs(cog.quotes, original)
        self.assertTrue(cog._has_rejected_rows)
        await restore_snapshot(cog, "quote", "data")
        self.assertFalse(cog._has_rejected_rows)
        self.assertEqual(cog.quotes, rows)
        self.assertIn(None, json.loads(Path(str(self.path) + ".bak").read_text()))

    async def test_legacy_restored_quote_ids_match_the_loader_and_stay_stable(self):
        cog = Quotes(MagicMock(), str(self.path))
        rows = [{"speaker": "A", "text": "Legacy"}, {"speaker": "A", "text": "Legacy"}]
        backup = snapshot_path(cog, "quote", "data")
        utils.atomic_write_json(backup, rows)
        await restore_snapshot(cog, "quote", "data")
        identities = [row["id"] for row in cog.quotes]
        self.assertEqual(len(set(identities)), 2)
        await restore_snapshot(cog, "quote", "data")
        self.assertEqual([row["id"] for row in cog.quotes], identities)
        reloaded = Quotes(MagicMock(), str(self.path))
        self.assertEqual([row["id"] for row in reloaded.quotes], identities)
