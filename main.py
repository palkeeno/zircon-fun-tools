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

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# インテントの設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class FunToolsBot(commands.Bot):
    """
    Discordボットのメインクラス
    このクラスは、ボットの初期化とコグの読み込みを行います。
    """
    
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        """
        ボットの起動時に実行されるフック
        Cogsの読み込みと同期を行います。
        """
        try:
            # Cogsの読み込み
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    try:
                        await self.load_extension(f'cogs.{filename[:-3]}')
                        logger.info(f'Loaded extension: {filename}')
                    except Exception as e:
                        logger.error(f'Failed to load extension {filename}: {e}')
                        logger.error(traceback.format_exc())

            # コマンドの同期
            try:
                synced = await self.tree.sync()
                logger.info(f'Synced {len(synced)} command(s)')
            except Exception as e:
                logger.error(f'Failed to sync commands: {e}')
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

    async def on_error(self, event_method, *args, **kwargs):
        """
        イベントハンドラでエラーが発生したときに実行されるイベント
        """
        logger.error(f'Error in {event_method}:')
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
        bot.run(config.TOKEN)
    except discord.LoginFailure:
        logger.error('Invalid token provided. Please check your token in the .env file.')
        sys.exit(1)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        logger.error(traceback.format_exc())
        sys.exit(1) 