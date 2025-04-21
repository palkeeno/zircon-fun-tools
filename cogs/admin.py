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

    @app_commands.command(
        name="feature",
        description="特定の機能を有効化/無効化します"
    )
    @app_commands.describe(
        feature="機能名",
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
            if feature in config.FEATURE_STATE:
                config.FEATURE_STATE[feature] = status
                await interaction.response.send_message(
                    f"機能 '{feature}' を {'有効化' if status else '無効化'} しました。",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"無効な機能名です。使用可能な機能: {', '.join(config.FEATURE_STATE.keys())}",
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
                for feature, enabled in config.FEATURE_STATE.items()
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

    @app_commands.command(name="enable_command", description="スラッシュコマンドを有効化します")
    @app_commands.describe(command="有効化するコマンド名")
    async def enable_command(self, interaction: discord.Interaction, command: str):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if command not in config.FEATURE_STATE:
            await interaction.response.send_message(f"無効なコマンド名です: {command}", ephemeral=True)
            return

        config.FEATURE_STATE[command] = True
        await interaction.response.send_message(f"コマンド '{command}' を有効化しました。", ephemeral=True)
        logger.info(f"コマンド '{command}' が有効化されました。")

    @app_commands.command(name="disable_command", description="スラッシュコマンドを無効化します")
    @app_commands.describe(command="無効化するコマンド名")
    async def disable_command(self, interaction: discord.Interaction, command: str):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if command not in config.FEATURE_STATE:
            await interaction.response.send_message(f"無効なコマンド名です: {command}", ephemeral=True)
            return

        config.FEATURE_STATE[command] = False
        await interaction.response.send_message(f"コマンド '{command}' を無効化しました。", ephemeral=True)
        logger.info(f"コマンド '{command}' が無効化されました。")

    @app_commands.command(name="list_commands", description="スラッシュコマンドの状態を一覧表示します")
    async def list_commands(self, interaction: discord.Interaction):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        embed = discord.Embed(title="スラッシュコマンドの状態", color=discord.Color.blue())
        
        # 既存の機能
        embed.add_field(
            name="既存の機能",
            value="\n".join([f"{cmd}: {'有効' if state else '無効'}" 
                            for cmd, state in config.FEATURE_STATE.items() 
                            if cmd in ['comedy', 'janken', 'fortune']]),
            inline=False
        )
        
        # 新規追加機能
        embed.add_field(
            name="新規追加機能",
            value="\n".join([f"{cmd}: {'有効' if state else '無効'}" 
                            for cmd, state in config.FEATURE_STATE.items() 
                            if cmd not in ['comedy', 'janken', 'fortune']]),
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _is_operator(self, interaction: discord.Interaction) -> bool:
        """
        運営ロールIDで判定します。
        """
        operator_role_id = getattr(config, "OPERATOR_ROLE_ID", 0)
        if not operator_role_id or not hasattr(interaction.user, "roles"):
            return False
        return any(role.id == operator_role_id for role in interaction.user.roles)

    def is_command_enabled(self, command_name: str) -> bool:
        return config.is_feature_enabled(command_name)

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