"""
コグのテスト
このモジュールは、各コグの機能をテストします。
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from discord.ext import commands
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
        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = 123456789
        self.ctx.guild = MagicMock()
        self.ctx.guild.id = 987654321
        self.ctx.channel = MagicMock()
        self.ctx.channel.id = 456789123
        self.ctx.send = AsyncMock()

    @patch('cogs.ramble_game.RambleGame.ramble')
    async def test_ramble_game_cog(self, mock_ramble):
        """ランブルゲームコグのテスト"""
        from cogs.ramble_game import RambleGame
        cog = RambleGame(self.bot)
        
        # ゲーム開始のテスト
        self.ctx.invoked_with = "start"
        mock_ramble.return_value = None
        await cog.ramble.callback(cog, self.ctx)
        
        # ゲーム参加のテスト
        self.ctx.invoked_with = "join"
        await cog.ramble.callback(cog, self.ctx)

    @patch('cogs.birthday.Birthday.birthday_command')
    async def test_birthday_cog(self, mock_birthday):
        """誕生日コグのテスト"""
        from cogs.birthday import Birthday
        cog = Birthday(self.bot)
        
        # 誕生日登録のテスト
        self.ctx.invoked_with = "add"
        mock_birthday.return_value = None
        await cog.birthday_command.callback(cog, self.ctx, "2000-01-01")
        
        # 誕生日一覧のテスト
        self.ctx.invoked_with = "list"
        await cog.birthday_command.callback(cog, self.ctx)

    @patch('cogs.dictionary.Dictionary.dictionary_command')
    async def test_dictionary_cog(self, mock_dictionary):
        """辞書コグのテスト"""
        from cogs.dictionary import Dictionary
        cog = Dictionary(self.bot)
        
        # 単語追加のテスト
        self.ctx.invoked_with = "add"
        mock_dictionary.return_value = None
        await cog.dictionary_command.callback(cog, self.ctx, "test", "テスト")
        
        # 単語検索のテスト
        self.ctx.invoked_with = "search"
        await cog.dictionary_command.callback(cog, self.ctx, "test")

    @patch('cogs.omikuji.Omikuji.omikuji_command')
    async def test_omikuji_cog(self, mock_omikuji):
        """おみくじコグのテスト"""
        from cogs.omikuji import Omikuji
        cog = Omikuji(self.bot)
        
        # おみくじを引くテスト
        mock_omikuji.return_value = None
        await cog.omikuji_command.callback(cog, self.ctx)

    @patch('cogs.comedy_game.ComedyGame.comedy')
    async def test_comedy_game_cog(self, mock_comedy):
        """大喜利ゲームコグのテスト"""
        from cogs.comedy_game import ComedyGame
        cog = ComedyGame(self.bot)
        
        # ゲーム開始のテスト
        self.ctx.invoked_with = "start"
        mock_comedy.return_value = None
        await cog.comedy.callback(cog, self.ctx)
        
        # 回答のテスト
        self.ctx.invoked_with = "answer"
        await cog.comedy.callback(cog, self.ctx, "テスト回答")

    @patch('cogs.janken.Janken.janken_command')
    async def test_janken_cog(self, mock_janken):
        """じゃんけんコグのテスト"""
        from cogs.janken import Janken
        cog = Janken(self.bot)
        
        # じゃんけん開始のテスト
        self.ctx.invoked_with = "start"
        mock_janken.return_value = None
        await cog.janken_command.callback(cog, self.ctx)
        
        # 手を出すテスト
        self.ctx.invoked_with = "rock"
        await cog.janken_command.callback(cog, self.ctx)

    @patch('cogs.fortune.Fortune.fortune_command')
    async def test_fortune_cog(self, mock_fortune):
        """占いコグのテスト"""
        from cogs.fortune import Fortune
        cog = Fortune(self.bot)
        
        # 占いのテスト
        mock_fortune.return_value = None
        await cog.fortune_command.callback(cog, self.ctx)

    @patch('cogs.oracle.Oracle.oracle_command')
    async def test_oracle_cog(self, mock_oracle):
        """オラクルコグのテスト"""
        from cogs.oracle import Oracle
        cog = Oracle(self.bot)
        
        # オラクルのテスト
        mock_oracle.return_value = None
        await cog.oracle_command.callback(cog, self.ctx, "テスト質問")

    @patch('cogs.admin.Admin.admin_command')
    async def test_admin_cog(self, mock_admin):
        """管理者コグのテスト"""
        from cogs.admin import Admin
        cog = Admin(self.bot)
        
        # 機能の有効/無効化のテスト
        self.ctx.invoked_with = "enable"
        mock_admin.return_value = None
        await cog.admin_command.callback(cog, self.ctx, "test_feature")
        
        # 機能の状態確認のテスト
        self.ctx.invoked_with = "status"
        await cog.admin_command.callback(cog, self.ctx)

if __name__ == '__main__':
    unittest.main() 