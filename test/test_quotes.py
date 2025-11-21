import datetime
import os
import tempfile
import unittest
from unittest.mock import patch

import discord
from discord.ext import commands

# Ensure token exists so config import succeeds during tests
os.environ.setdefault("ENV", "development")
os.environ.setdefault("DISCORD_TOKEN_DEV", "test_token")

from cogs.quotes import Quotes  # noqa: E402


class TestQuotesCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = os.path.join(self.temp_dir.name, "quotes.json")
        self.cog = Quotes(self.bot, data_path=self.data_path)

    async def asyncTearDown(self) -> None:
        await self.bot.close()
        self.temp_dir.cleanup()

    async def test_load_creates_default_file(self):
        self.assertTrue(os.path.exists(self.data_path))
        self.assertEqual(self.cog.quotes, [])
        self.assertIn("enabled", self.cog.settings)
        self.assertIn("days", self.cog.settings)

    async def test_select_quote_avoids_last(self):
        self.cog.quotes = [
            {"id": "a", "speaker": "A", "text": "alpha"},
            {"id": "b", "speaker": "B", "text": "beta"},
        ]
        self.cog.settings["last_posted_quote_id"] = "a"
        for _ in range(5):
            selected = self.cog._select_quote()
            self.assertIsNotNone(selected)
            if len(self.cog.quotes) > 1:
                self.assertNotEqual(selected["id"], "a")

    async def test_compute_next_run_first_post_future(self):
        target_now = datetime.datetime(2025, 11, 21, 8, 0, tzinfo=self.cog.tz)
        self.cog.settings.update({"days": 1, "hour": 9, "minute": 0})
        with patch("cogs.quotes._now", return_value=target_now):
            result = self.cog._compute_next_run(last_posted=None)
        expected = datetime.datetime.combine(target_now.date(), datetime.time(9, 0, tzinfo=self.cog.tz))
        self.assertEqual(result, expected)

    async def test_compute_next_run_catch_up(self):
        now_value = datetime.datetime(2025, 11, 21, 10, 0, tzinfo=self.cog.tz)
        last_posted = datetime.datetime(2025, 11, 20, 9, 0, tzinfo=self.cog.tz)
        self.cog.settings.update({"days": 1, "hour": 9, "minute": 0})
        with patch("cogs.quotes._now", return_value=now_value):
            result = self.cog._compute_next_run(last_posted=last_posted)
        self.assertEqual(result, now_value)

    async def test_build_thumbnail_url(self):
        self.assertTrue(self.cog._build_thumbnail_url("9").endswith(".webp"))
        self.assertTrue(self.cog._build_thumbnail_url("10004").endswith(".png"))


if __name__ == "__main__":
    unittest.main()
