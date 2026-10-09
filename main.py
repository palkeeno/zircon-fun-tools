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
from command_errors import send_error

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FunToolsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or('!'), intents=intents)
        self.tree.on_error = self.on_tree_error
        self.tree.interaction_check = self.check_target_guild
        self.initial_extensions = [
            'cogs.birthday',
            'cogs.oracle',
            'cogs.lottery',
            'cogs.poster',
            'cogs.quotes',
            'cogs.help',
            'cogs.role_tools'
        ]

    async def setup_hook(self):
        if config.GUILD_ID <= 0:
            raise ValueError("単一サーバー用Botです。GUILD_ID_DEV / GUILD_ID_PROD に対象サーバーIDを設定してください")
        # ロード失敗時に不完全なコマンド一覧をDiscordへ同期しない。
        for extension in self.initial_extensions:
            await self.load_extension(extension)
            logger.info("%s をロードしました", extension)
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        # 旧グローバル登録は対象ギルドへの同期成功後に削除する。
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        self.enabled_extensions = list(self.initial_extensions)
        logger.info("単一サーバー %s への同期完了: %s個", config.GUILD_ID, len(synced))

    async def check_target_guild(self, interaction):
        if interaction.guild_id == config.GUILD_ID:
            return True
        await interaction.response.send_message("このBotは指定されたサーバー内で利用してください。", ephemeral=True)
        return False

    async def on_tree_error(self, interaction, error):
        await send_error(interaction, error)

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

async def main():
    # Importing main/config must not validate secrets, install fonts or create a Bot.
    token = config.get_token()
    async with FunToolsBot() as bot:
        await bot.start(token)


def run():
    try:
        asyncio.run(main())
        return 0
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        return 0
    except Exception:
        logger.exception("Bot terminated; systemd supervises production restarts")
        return 1


if __name__ == '__main__':
    sys.exit(run())
