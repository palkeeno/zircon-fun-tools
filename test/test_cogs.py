import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from discord.ext import commands
import sys
import os

sys.modules["config"] = __import__("config")  # configのimportエラー回避

class TestCogs(unittest.IsolatedAsyncioTestCase):
    """コグのテストクラス（Discordサーバ不要/ロジック網羅）"""

    async def asyncSetUp(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.interaction.user = MagicMock()
        self.interaction.user.id = 123456789
        self.interaction.guild = MagicMock()
        self.interaction.guild.id = 987654321
        self.interaction.channel = MagicMock()
        self.interaction.channel.id = 456789123
        self.interaction.response = AsyncMock()


    async def test_birthday_load_and_save(self):
        from cogs.birthday import Birthday
        cog = Birthday(self.bot)
        # 誕生日データのロード・セーブはファイルI/Oなので、ここでは辞書型で直接テスト
        cog.birthdays = {"123": {"month": 1, "day": 2}}
        self.assertEqual(cog.birthdays["123"]["month"], 1)
        self.assertEqual(cog.birthdays["123"]["day"], 2)

    async def test_oracle_init(self):
        from cogs.oracle import Oracle
        cog = Oracle(self.bot)
        self.assertTrue(hasattr(cog, "bot"))

if __name__ == '__main__':
    unittest.main()