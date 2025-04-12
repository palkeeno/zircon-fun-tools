"""
管理者コマンドのコグ
このモジュールは、ボットの機能を制御する管理者向けコマンドを提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import traceback
import config

# ロギングの設定
logger = logging.getLogger(__name__)

class Admin(commands.Cog):
    """
    管理者コマンドのコグ
    ボットの機能を制御するコマンドを提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        管理者コマンドのコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        """
        コマンド実行前のチェックを行います。
        管理者チャンネルでのみ実行可能です。
        
        Args:
            ctx (commands.Context): コマンドのコンテキスト
            
        Returns:
            bool: コマンドを実行可能な場合はTrue、そうでない場合はFalse
        """
        if not config.is_admin_channel(ctx.channel.id):
            await ctx.send("このコマンドは管理者チャンネルでのみ実行可能です。", ephemeral=True)
            return False
        return True

    @app_commands.command(
        name="feature",
        description="特定の機能を有効化/無効化します"
    )
    @app_commands.describe(
        feature="機能名 (janken/fortune/comedy)",
        status="有効化する場合はTrue、無効化する場合はFalse"
    )
    async def feature(self, interaction: discord.Interaction, feature: str, status: bool):
        """
        特定の機能を有効化/無効化します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            feature (str): 機能名
            status (bool): 有効化する場合はTrue、無効化する場合はFalse
        """
        try:
            if config.set_feature_status(feature, status):
                await interaction.response.send_message(
                    f"機能 '{feature}' を {'有効化' if status else '無効化'} しました。",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"無効な機能名です。使用可能な機能: {', '.join(config.FEATURE_STATUS.keys())}",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in feature command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="status",
        description="各機能の現在の状態を表示します"
    )
    async def status(self, interaction: discord.Interaction):
        """
        各機能の現在の状態を表示します。
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        try:
            status_text = "\n".join([
                f"- {feature}: {'有効' if enabled else '無効'}"
                for feature, enabled in config.FEATURE_STATUS.items()
            ])
            
            embed = discord.Embed(
                title="機能の状態",
                description=status_text,
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Admin(bot))
        logger.info("Admin cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Admin cog: {e}")
        logger.error(traceback.format_exc())
        raise 