"""
Discordボットのメインファイル
このモジュールは、Discordボットの初期化と起動を行います。
"""

import discord
from discord import app_commands
from discord.ext import commands
import config
import logging
import os
import sys
import traceback
from dotenv import load_dotenv

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FunToolsBot(commands.Bot):
    """
    Discordボットのメインクラス
    このクラスは、ボットの初期化とコグの読み込みを行います。
    """
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents)
        self.settings = config.SETTINGS
        self.initial_extensions = [
            'cogs.ramble_game',
            'cogs.birthday',
            'cogs.dictionary',
            'cogs.omikuji',
            'cogs.comedy_game',
            'cogs.janken',
            'cogs.fortune',
            'cogs.oracle',
            'cogs.admin'
        ]

    async def setup_hook(self):
        """
        ボットの起動時に実行されるフック
        Cogsの読み込みと同期を行います。
        """
        try:
            # 設定に基づいて機能を有効/無効化
            for extension in self.initial_extensions:
                try:
                    cog_name = extension.split('.')[-1]
                    if config.is_feature_enabled(cog_name):
                        await self.load_extension(extension)
                        logger.info(f'{extension} をロードしました')
                    else:
                        logger.info(f'{extension} は無効化されています')
                except Exception as e:
                    logger.error(f'{extension} のロードに失敗しました: {e}')
                    logger.error(traceback.format_exc())

            # スラッシュコマンドの同期
            try:
                synced = await self.tree.sync()
                logger.info(f"{len(synced)}個のスラッシュコマンドを同期しました")
            except Exception as e:
                logger.error(f"スラッシュコマンドの同期に失敗しました: {e}")
                logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f'Error in setup_hook: {e}')
            logger.error(traceback.format_exc())
            raise

    async def on_ready(self):
        """
        ボットの準備が完了したときに実行されるイベント
        """
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')
        await self.change_presence(activity=discord.Game(name="/help でコマンド一覧"))
        
        # 機能の状態をログに出力
        for feature, config in self.settings['features'].items():
            status = "有効" if config['enabled'] else "無効"
            logger.info(f"{feature}: {status}")

    async def on_error(self, event_method, *args, **kwargs):
        """
        イベントハンドラでエラーが発生したときに実行されるイベント
        """
        logger.error(f'Error in {event_method}:')
        logger.error(traceback.format_exc())

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f'コマンドエラー: {error}')
        logger.error(traceback.format_exc())

# ボットの初期化
try:
    bot = FunToolsBot()
except Exception as e:
    logger.error(f'Failed to initialize bot: {e}')
    logger.error(traceback.format_exc())
    sys.exit(1)

# ボットの起動
if __name__ == '__main__':
    try:
        async def main():
            async with bot:
                await bot.start(config.TOKEN)

        import asyncio
        asyncio.run(main())
    except discord.LoginFailure:
        logger.error('Invalid token provided. Please check your token in the .env file.')
        sys.exit(1)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        logger.error(traceback.format_exc())
        sys.exit(1) 