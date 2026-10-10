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
import time
import setup_fonts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 再接続設定
MAX_RETRIES = 5  # 最大再試行回数
RETRY_DELAY_BASE = 30  # 基本待機時間（秒）
RETRY_DELAY_MAX = 300  # 最大待機時間（秒）

# import 時にフォントのインストールを実行しない。
if __name__ == '__main__':
    if config.GUILD_ID <= 0:
        logger.error("GUILD_ID_DEV / GUILD_ID_PROD に対象サーバーIDを設定してください")
        sys.exit(1)
    setup_fonts.setup_fonts_if_needed()

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
            'cogs.roll',
            'cogs.poster',
            'cogs.quotes'
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
        if isinstance(error, discord.app_commands.MissingPermissions):
            message = "このコマンドはサーバー管理者のみ実行できます。"
        elif isinstance(error, discord.app_commands.NoPrivateMessage):
            message = "このコマンドはサーバー内で実行してください。"
        else:
            logger.error("スラッシュコマンドエラー", exc_info=error)
            message = "処理中にエラーが発生しました。管理者にお問い合わせください。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

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
        pass

if __name__ == '__main__':
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            # Botインスタンスを再作成（再試行時）
            if retry_count > 0:
                logger.info(f"Botインスタンスを再作成します (試行 {retry_count + 1}/{MAX_RETRIES})")
                bot = FunToolsBot()
            
            asyncio.run(main())
            break  # 正常終了した場合はループを抜ける
            
        except discord.LoginFailure:
            logger.error('無効なトークンです。.envファイルを確認してください。')
            sys.exit(1)  # トークンエラーは再試行しない
            
        except KeyboardInterrupt:
            logger.info('停止しました。')
            sys.exit(0)
            
        except (discord.ConnectionClosed, discord.GatewayNotFound, 
                discord.HTTPException, OSError) as e:
            # ネットワーク関連エラーは再試行
            retry_count += 1
            delay = min(RETRY_DELAY_BASE * retry_count, RETRY_DELAY_MAX)
            
            logger.warning(f'接続エラーが発生しました: {e}')
            
            if retry_count < MAX_RETRIES:
                logger.info(f'{delay}秒後に再接続を試みます (試行 {retry_count}/{MAX_RETRIES})')
                time.sleep(delay)
            else:
                logger.error(f'最大再試行回数 ({MAX_RETRIES}) に達しました。終了します。')
                sys.exit(1)
                
        except Exception as e:
            retry_count += 1
            delay = min(RETRY_DELAY_BASE * retry_count, RETRY_DELAY_MAX)
            
            logger.error(f'予期しないエラー: {e}')
            logger.error(traceback.format_exc())
            
            if retry_count < MAX_RETRIES:
                logger.info(f'{delay}秒後に再起動を試みます (試行 {retry_count}/{MAX_RETRIES})')
                time.sleep(delay)
            else:
                logger.error(f'最大再試行回数 ({MAX_RETRIES}) に達しました。終了します。')
                sys.exit(1)
