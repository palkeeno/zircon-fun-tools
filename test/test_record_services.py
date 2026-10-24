"""Storage normalization invariants shared by loading and backup restoration."""
import test
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from cogs.backups import restore_snapshot, save_snapshot
from cogs.quotes import Quotes
from quote_records import normalize_records


class QuoteRecordServices(unittest.IsolatedAsyncioTestCase):
    def test_legacy_id_and_order_survive_rejected_and_duplicate_rows(self):
        row = {"speaker": " A ", "text": " hello "}
        # Fixed legacy fixtures catch changes to the UUID namespace or identity encoding.
        first_id = "1c0a5f5d-95ed-5ed6-8d60-9b4f346e2f8c"
        rows = [row, {**row, "id": first_id}, {"text": "invalid"}, row]
        before = copy.deepcopy(rows)
        valid, rejected = normalize_records(rows, strict=False)
        self.assertEqual([q["id"] for q in valid],
                         [first_id, "28e70332-09a1-5664-a5d2-949cb5a78619"])
        self.assertEqual([r["row"] for r in rejected], [2, 3])
        self.assertEqual(rows, before)
        self.assertEqual(normalize_records(valid), (valid, []))

    async def test_load_and_restore_produce_identical_records(self):
        rows = [{"speaker": "A", "text": "same"}, {"speaker": "A", "text": "same"},
                {"speaker": "B", "text": "other", "id": "explicit"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            cog = Quotes(MagicMock(), str(path))
            loaded = copy.deepcopy(cog.quotes)
            cog.quotes = rows
            save_snapshot(cog, "quote", "data")
            cog.quotes = []
            await restore_snapshot(cog, "quote", "data")
            self.assertEqual(cog.quotes, loaded)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["quotes"], loaded)

    async def test_invalid_restore_leaves_memory_and_file_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quotes.json"
            cog = Quotes(MagicMock(), str(path))
            for bad in ({"text": "missing speaker"},
                        {"speaker": "B", "text": "duplicate", "id": "same"}):
                cog.quotes = [{"speaker": "A", "text": "valid", "id": "same"}, bad]
                save_snapshot(cog, "quote", "data")
                cog.quotes = [{"speaker": "current", "text": "keep", "id": "current"}]
                cog._save_data()
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    await restore_snapshot(cog, "quote", "data")
                self.assertEqual(cog.quotes[0]["id"], "current")
                self.assertEqual(path.read_bytes(), before)
