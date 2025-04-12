"""
占い機能のコグ
このモジュールは、Discord上で占い機能を実装します。
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

class Fortune(commands.Cog):
    """
    占い機能のコグ
    占いのコマンドと機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        占い機能のコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot

    @app_commands.command(
        name="fortune",
        description="選択肢からランダムに1つを選びます"
    )
    @app_commands.describe(
        choices="選択肢をカンマ区切りで入力してください（最大5つまで）"
    )
    async def fortune(self, interaction: discord.Interaction, choices: str):
        """
        選択肢からランダムに1つを選びます。
        
        Args:
            interaction (discord.Interaction): インタラクション
            choices (str): カンマ区切りの選択肢
        """
        try:
            if not config.is_feature_enabled('fortune'):
                await interaction.response.send_message("現在占い機能は無効化されています。", ephemeral=True)
                return
                
            # 選択肢を分割
            choice_list = [choice.strip() for choice in choices.split(",")]
            
            # 選択肢の数をチェック
            if len(choice_list) > config.FORTUNE_MAX_CHOICES:
                await interaction.response.send_message(
                    f"選択肢は最大{config.FORTUNE_MAX_CHOICES}つまでです。",
                    ephemeral=True
                )
                return
            
            # ランダムに1つを選ぶ
            result = random.choice(choice_list)
            
            # 結果を表示
            embed = discord.Embed(
                title="🔮 占いの結果",
                description=f"**選択肢:**\n{', '.join(choice_list)}\n\n"
                          f"**結果:** {result}",
                color=discord.Color.purple()
            )
            embed.set_footer(text="※ この結果は参考程度にお楽しみください")
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in fortune command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message("エラーが発生しました。もう一度お試しください。", ephemeral=True)

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Fortune(bot))
        logger.info("Fortune cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Fortune cog: {e}")
        logger.error(traceback.format_exc())
        raise 