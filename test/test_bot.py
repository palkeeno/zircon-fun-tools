"""
ボットの基本機能のテスト
このモジュールは、FunToolsBotクラスの基本機能をテストします。
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import discord
from discord.ext import commands
import config
from main import FunToolsBot
import asyncio
import logging

class TestFunToolsBot(unittest.IsolatedAsyncioTestCase):
    """ボットの基本機能のテストクラス"""

    async def asyncSetUp(self):
        """テストの前準備"""
        self.bot = FunToolsBot()
        # ユーザー属性をモック化
        self.bot._connection = MagicMock()
        self.bot._connection.user = MagicMock()
        self.bot._connection.user.id = 123456789
        self.bot._connection.user.name = "TestBot"
        # ロガーをモック化
        self.bot.logger = MagicMock()

    @patch('discord.Client.login')
    async def test_bot_initialization(self, mock_login):
        """ボットの初期化テスト"""
        self.assertIsInstance(self.bot, commands.Bot)
        self.assertTrue(callable(self.bot.command_prefix))
        self.assertTrue(self.bot.intents.message_content)
        self.assertTrue(self.bot.intents.members)

    @patch('discord.ext.commands.Bot.load_extension')
    async def test_setup_hook(self, mock_load_extension):
        """setup_hookのテスト"""
        # モックの設定
        self.bot.tree.sync = AsyncMock()
        mock_load_extension.return_value = None

        # テスト実行
        await self.bot.setup_hook()

        # 検証
        self.assertEqual(mock_load_extension.call_count, len(self.bot.enabled_extensions))
        self.assertTrue(self.bot.tree.sync.called)

    @patch('discord.Client.change_presence')
    async def test_on_ready(self, mock_change_presence):
        """on_readyイベントのテスト"""
        mock_change_presence.return_value = None

        # logger.infoはグローバルloggerなのでpatch
        with patch('main.logger.info') as mock_logger_info:
            await self.bot.on_ready()

            # 検証
            mock_change_presence.assert_called_once_with(
                activity=discord.Game(name="/help でコマンド一覧")
            )
            self.assertTrue(mock_logger_info.called)

    @patch('logging.Logger.error')
    async def test_on_error(self, mock_logger_error):
        """on_errorイベントのテスト"""
        # モックの設定
        event_method = "test_event"
        error = Exception("Test error")

        # テスト実行
        await self.bot.on_error(event_method, error)

        # 検証
        mock_logger_error.assert_called()
        self.assertTrue(mock_logger_error.call_count >= 2)  # エラーメッセージとトレースバー

    @patch('logging.Logger.error')
    async def test_on_command_error(self, mock_logger_error):
        """on_command_errorイベントのテスト"""
        # モックの設定
        ctx = MagicMock()
        ctx.send = AsyncMock()

        # CommandNotFoundエラーのテスト
        error = commands.CommandNotFound()
        await self.bot.on_command_error(ctx, error)
        self.assertFalse(mock_logger_error.called)  # CommandNotFoundはログに記録しない

        # その他のエラーのテスト
        error = Exception("Test error")
        await self.bot.on_command_error(ctx, error)
        mock_logger_error.assert_called()
        self.assertTrue(mock_logger_error.call_count >= 2)  # エラーメッセージとトレースバー

if __name__ == '__main__':
    unittest.main()