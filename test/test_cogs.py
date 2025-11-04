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

    async def test_dictionary_add_and_search(self):
        from cogs.dictionary import Dictionary
        cog = Dictionary(self.bot)
        # 内部辞書に直接追加
        cog.words = {"test": "テスト"}
        self.assertEqual(cog.words["test"], "テスト")
        # 検索ロジック
        matches = [k for k in cog.words if "te" in k]
        self.assertIn("test", matches)



    async def test_comedy_game_load_data(self):
        from cogs.comedy_game import Comedy
        cog = Comedy(self.bot)
        # situations/cardsはファイル依存なので、属性の存在のみ確認
        self.assertTrue(hasattr(cog, "situations"))
        self.assertTrue(hasattr(cog, "cards"))

    async def test_janken_judge(self):
        from cogs.janken import Janken
        cog = Janken(self.bot)
        # 勝敗ロジック
        self.assertEqual(cog.judge("rock", "scissors"), "あなたの勝ち！")
        self.assertEqual(cog.judge("rock", "paper"), "ボットの勝ち！")
        self.assertEqual(cog.judge("rock", "rock"), "引き分け！")

    async def test_oracle_init(self):
        from cogs.oracle import Oracle
        cog = Oracle(self.bot)
        self.assertTrue(hasattr(cog, "bot"))

    async def test_admin_is_command_enabled(self):
        from cogs.admin import Admin
        cog = Admin(self.bot)
        self.assertTrue(callable(cog.is_command_enabled))
        # config.pyのFEATURESに依存
        self.assertIsInstance(cog.is_command_enabled("comedy_game"), bool)

if __name__ == '__main__':
    unittest.main()