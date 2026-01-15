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
                    logger.info(f"スラッシュコマンド同期完了: {len(guild_synced)}個")
                else:
                    # グローバル同期（反映まで最長1時間程度かかる）
                    synced = await self.tree.sync()
                    logger.info(f"スラッシュコマンド同期完了: {len(synced)}個（グローバル）")
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
