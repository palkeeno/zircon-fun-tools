"""
Graceful startup/shutdown entry point for the Discord bot.
Use this instead of main.py if you want clean Ctrl+C handling without noisy CancelledError traceback.
"""
import discord
from discord.ext import commands
import config
import logging
import traceback
import sys
import asyncio
import setup_fonts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Font setup (Linux only)
setup_fonts.setup_fonts_if_needed()

class FunToolsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents)
        self.initial_extensions = [
            'cogs.birthday',
            'cogs.oracle',
            # 'cogs.admin',
            'cogs.lottery',
            'cogs.poster',
            'cogs.quotes'
        ]

    async def setup_hook(self):
        try:
            loaded_extensions = []
            for extension in self.initial_extensions:
                try:
                    await self.load_extension(extension)
                    loaded_extensions.append(extension)
                    logger.info(f'{extension} をロードしました')
                except Exception as e:
                    logger.error(f'{extension} のロードに失敗しました: {e}')
                    logger.error(traceback.format_exc())
            # Slash command sync
            try:
                if getattr(config, 'GUILD_ID', 0):
                    guild = discord.Object(id=config.GUILD_ID)
                    # 1) ギルド側のコマンドを一旦クリア（重複防止）
                    self.tree.clear_commands(guild=guild)
                    # 2) 現在のグローバル定義をギルドへコピー
                    self.tree.copy_global_to(guild=guild)
                    # 3) ギルドへ即時同期
                    guild_synced = await self.tree.sync(guild=guild)
                    # 4) グローバルコマンドをクリアして、サーバー設定画面での二重登録を解消
                    self.tree.clear_commands(guild=None)
                    await self.tree.sync()  # グローバル側を削除反映
                    logger.info(f"ギルド {config.GUILD_ID} に {len(guild_synced)} 個のスラッシュコマンドを同期（ギルド限定化）し、グローバル定義を削除しました")
                else:
                    # グローバル同期（反映まで最長1時間程度かかる）
                    synced = await self.tree.sync()
                    logger.info(f"グローバルに {len(synced)} 個のスラッシュコマンドを同期しました（反映には時間がかかる場合があります）")
            except Exception as e:
                logger.error(f"スラッシュコマンドの同期に失敗しました: {e}")
                logger.error(traceback.format_exc())
            self.enabled_extensions = loaded_extensions
        except Exception as e:
            logger.error(f'Error in setup_hook: {e}')
            logger.error(traceback.format_exc())
            raise

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')
        await self.change_presence(activity=discord.Game(name="/help でコマンド一覧"))

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f'Error in {event_method}:')
        logger.error(traceback.format_exc())

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f'コマンドエラー: {error}')
        logger.error(traceback.format_exc())

try:
    bot = FunToolsBot()
except Exception as e:
    logger.error(f'Failed to initialize bot: {e}')
    logger.error(traceback.format_exc())
    sys.exit(1)

async def main():
    try:
        async with bot:
            await bot.start(config.TOKEN)
    except asyncio.CancelledError:
        # Silent cancellation (Ctrl+C)
        logger.info('シャットダウン要求を受け取りました (Cancelled).')
    except KeyboardInterrupt:
        logger.info('停止要求を受信しました (Ctrl+C). 終了します。')
    finally:
        # Place any cleanup here if needed
        pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except discord.LoginFailure:
        logger.error('Invalid token provided. Please check your token in the .env file.')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('停止しました。')
        sys.exit(0)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        logger.error(traceback.format_exc())
        sys.exit(1)
