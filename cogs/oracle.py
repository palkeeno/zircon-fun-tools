"""
選択肢アドバイス機能を実装するCog
このモジュールは、選択肢アドバイス機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
import traceback
import config

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
            # 機能が有効かどうかを確認
            if not config.is_feature_enabled('oracle'):
                await interaction.response.send_message(
                    "申し訳ありません。現在、選択肢アドバイス機能は無効になっています。",
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

            # ランダムな選択肢を生成
            selected = random.randint(1, choices)

            # メッセージテンプレート
            messages = [
                f"うーん...{choices}個の選択肢の中から、{selected}番目が一番良さそうですね！",
                f"私の直感では、{selected}番目の選択肢が運気が強いようです✨",
                f"あっ！{selected}番目が光って見えます！これが正解です！",
                f"ふむふむ...{choices}個の選択肢をじっくり見てみると、{selected}番目が気になりますね。",
                f"私の水晶玉が{selected}番目の選択肢を示しています🔮"
            ]

            # ランダムにメッセージを選択
            message = random.choice(messages)

            # 結果を送信
            await interaction.response.send_message(message)

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