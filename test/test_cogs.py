"""
コグのテスト
このモジュールは、各コグの機能をテストします。
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from discord.ext import commands
from discord import app_commands
import config
import asyncio

class TestCogs(unittest.IsolatedAsyncioTestCase):
    """コグのテストクラス"""

    async def asyncSetUp(self):
        """テストの前準備"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Interactionのモックを作成
        self.interaction = AsyncMock(spec=discord.Interaction)
        self.interaction.user = MagicMock()
        self.interaction.user.id = 123456789
        self.interaction.guild = MagicMock()
        self.interaction.guild.id = 987654321
        self.interaction.channel = MagicMock()
        self.interaction.channel.id = 456789123
        self.interaction.response = AsyncMock()

    @patch('cogs.ramble_game.RambleGame.start_ramble_game')
    async def test_ramble_game_cog(self, mock_ramble):
        """ランブルゲームコグのテスト"""
        from cogs.ramble_game import RambleGame
        cog = RambleGame(self.bot)
        
        # ゲーム開始のテスト
        mock_ramble.return_value = None
        await cog.start_ramble_game(self.interaction)

    @patch('cogs.birthday.Birthday.add_birthday')
    async def test_birthday_cog(self, mock_birthday):
        """誕生日コグのテスト"""
        from cogs.birthday import Birthday
        cog = Birthday(self.bot)
        
        # 誕生日登録のテスト
        mock_birthday.return_value = None
        await cog.add_birthday(self.interaction, 1, 1)

    @patch('cogs.dictionary.Dictionary.add_word')
    async def test_dictionary_cog(self, mock_dictionary):
        """辞書コグのテスト"""
        from cogs.dictionary import Dictionary
        cog = Dictionary(self.bot)
        
        # 単語追加のテスト
        mock_dictionary.return_value = None
        await cog.add_word(self.interaction, "test", "テスト")

    @patch('cogs.fortune.Fortune.draw_omikuji')
    async def test_fortune_cog(self, mock_fortune):
        """おみくじコグのテスト"""
        from cogs.fortune import Fortune
        cog = Fortune(self.bot)
        
        # おみくじを引くテスト
        mock_fortune.return_value = None
        await cog.draw_omikuji(self.interaction)

    @patch('cogs.comedy_game.ComedyGame.comedy')
    async def test_comedy_game_cog(self, mock_comedy):
        """大喜利ゲームコグのテスト"""
        from cogs.comedy_game import ComedyGame
        cog = ComedyGame(self.bot)
        
        # ゲーム開始のテスト
        mock_comedy.return_value = None
        await cog.comedy(self.interaction)

    @patch('cogs.janken.Janken.janken')
    async def test_janken_cog(self, mock_janken):
        """じゃんけんコグのテスト"""
        from cogs.janken import Janken
        cog = Janken(self.bot)
        
        # じゃんけん開始のテスト
        mock_janken.return_value = None
        await cog.janken(self.interaction)

    @patch('cogs.oracle.Oracle.oracle')
    async def test_oracle_cog(self, mock_oracle):
        """オラクルコグのテスト"""
        from cogs.oracle import Oracle
        cog = Oracle(self.bot)
        
        # オラクルのテスト
        mock_oracle.return_value = None
        await cog.oracle(self.interaction, 3)

    @patch('cogs.admin.Admin.feature')
    async def test_admin_cog(self, mock_admin):
        """管理者コグのテスト"""
        from cogs.admin import Admin
        cog = Admin(self.bot)
        
        # 機能の有効/無効化のテスト
        mock_admin.return_value = None
        await cog.feature(self.interaction, "test_feature", True)

if __name__ == '__main__':
    unittest.main() 