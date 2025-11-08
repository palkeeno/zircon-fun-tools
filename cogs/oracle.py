"""
選択肢アドバイス機能を実装するCog
このモジュールは、選択肢アドバイス機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import logging
import traceback
import permissions

# ロギングの設定
logger = logging.getLogger(__name__)

class Oracle(commands.Cog):
    """
    選択肢アドバイス機能を提供するCog
    """
    
    def __init__(self, bot: commands.Bot):
        """
        初期化処理
        
        Args:
            bot (commands.Bot): Discordボットのインスタンス
        """
        self.bot = bot
        logger.info("Oracle cogが初期化されました")

    @app_commands.command(name="oracle", description="選択肢のアドバイスをします")
    async def oracle(self, interaction: discord.Interaction, choices: int):
        """
        選択肢のアドバイスを提供します
        
        Args:
            interaction (discord.Interaction): インタラクション
            choices (int): 選択肢の数
        """
        try:
            # 権限チェック: 管理者は常にOK、非管理者は限定解除されたロールのみ
            if not permissions.can_run_command(interaction, 'oracle'):
                await interaction.response.send_message(
                    "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                    ephemeral=True
                )
                return

            # 選択肢の数のバリデーション
            if choices < 1:
                await interaction.response.send_message(
                    "選択肢の数は1以上を指定してください。",
                    ephemeral=True
                )
                return

            # 最初の案内メッセージを送信

            await interaction.response.send_message(
                f"{choices}個の選択肢から占います...",
                ephemeral=False
            )

            # 3秒待つ
            await asyncio.sleep(3)

            # ランダムな選択肢を生成
            selected = random.randint(1, choices)

            # メッセージテンプレート
            messages = [
                f"うーん...{choices}個の選択肢の中から、{selected}番目が一番良さそうですね！",
                f"私の直感では、{selected}番目の選択肢が運気が強いようです✨",
                f"あっ！{selected}番目が光って見えます！これが正解です！",
                f"ふむふむ...{choices}個の選択肢をじっくり見てみると、{selected}番目が気になりますね。",
                f"私の水晶玉が{selected}番目の選択肢を示しています🔮",
                f"{selected}番目の選択肢が、今日のラッキーアイテムです！",
                f"占いの結果...{selected}番目があなたにぴったりです！",
                f"迷ったときは、{selected}番目を選ぶのが吉！",
                f"{selected}番目の選択肢が未来を切り開きます！",
                f"星の導きによると、{selected}番目が最良です⭐",
                f"{selected}番目の選択肢が幸運を呼びます！",
                f"{choices}個の中で、{selected}番目が一番輝いています！",
                f"{selected}番目の選択肢が運命の扉を開きます！",
                f"{selected}番目...それが答えです！",
                f"{selected}番目の選択肢があなたの運命を変えるかも？"
            ]

            # ランダムにメッセージを選択
            message = random.choice(messages)

            # 結果を新規メッセージで送信
            await interaction.followup.send(message)

        except Exception as e:
            logger.error(f"選択肢アドバイスコマンド実行中にエラーが発生しました: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message(
                "申し訳ありません。エラーが発生しました。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """
    Cogをボットに追加する関数
    
    Args:
        bot (commands.Bot): Discordボットのインスタンス
    """
    try:
        await bot.add_cog(Oracle(bot))
        logger.info("Oracle cogが正常に追加されました")
    except Exception as e:
        logger.error(f"Oracle cogの追加中にエラーが発生しました: {e}\n{traceback.format_exc()}")
        raise 