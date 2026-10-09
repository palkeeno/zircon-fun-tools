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
from main import FunToolsBot
class GuildSyncTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = FunToolsBot()
        self.bot.load_extension = AsyncMock()
        self.bot.tree.sync = AsyncMock(return_value=[])

    async def asyncTearDown(self):
        await self.bot.close()

    async def test_missing_guild_refuses_global_sync(self):
        with patch.object(config, 'GUILD_ID', 0):
            with self.assertRaises(ValueError):
                await self.bot.setup_hook()
        self.bot.tree.sync.assert_not_called()

    async def test_partial_load_does_not_sync(self):
        self.bot.load_extension.side_effect = [None, RuntimeError('load failure')]
        with patch.object(config, 'GUILD_ID', 123):
            with self.assertRaises(RuntimeError):
                await self.bot.setup_hook()
        self.bot.tree.sync.assert_not_called()

    async def test_failed_guild_sync_does_not_clear_global(self):
        self.bot.tree.sync.side_effect = RuntimeError('sync failure')
        with patch.object(config, 'GUILD_ID', 123), patch.object(self.bot.tree, 'clear_commands') as clear:
            with self.assertRaises(RuntimeError):
                await self.bot.setup_hook()
            clear.assert_not_called()
        self.assertEqual(self.bot.tree.sync.await_count, 1)

    async def test_other_server_denied(self):
        interaction = MagicMock(guild_id=456)
        interaction.response = AsyncMock()
        with patch.object(config, 'GUILD_ID', 123):
            self.assertFalse(await self.bot.tree.interaction_check(interaction))
        interaction.response.send_message.assert_awaited_once()

    def test_actual_extensions_register_only_in_target_guild(self):
        script = '\nimport asyncio\nfrom unittest.mock import AsyncMock\nimport discord\nimport config\nfrom main import FunToolsBot\nasync def check():\n    config.GUILD_ID = 123\n    bot = FunToolsBot()\n    bot.tree.sync = AsyncMock(return_value=[])\n    try:\n        await bot.setup_hook()\n        assert set(bot.extensions) == set(bot.initial_extensions)\n        commands = bot.tree.get_commands(guild=discord.Object(id=123))\n        names = {command.name for command in commands}\n        assert {"poster", "birthday", "quote", "birthday_update", "quote_update"} <= names\n        assert bot.tree.get_commands() == []\n        for command in commands:\n            if command.name.endswith(("_update", "_toggle", "_schedule")):\n                assert command.default_permissions.administrator\n                assert command.checks == []\n    finally:\n        await bot.close()\nasyncio.run(check())\n'
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
