"""cogs.admin
管理者向けのスラッシュコマンドを提供します。

このモジュールは以下のスラッシュコマンドを提供します:
 - /admin list_commands: 各コマンドの有効/無効状態を一覧表示
 - /admin enable_command <name>: 指定したコマンドを有効化
 - /admin disable_command <name>: 指定したコマンドを無効化

使用は運営ロール（`config.OPERATOR_ROLE_ID`）に制限されます。
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    """管理者コマンドコグ。運営ロールのみ使用可能なコマンドを提供します。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_operator(self, interaction: discord.Interaction) -> bool:
        """運営ロールIDで判定します。interaction がギルド内で発行されたことが前提です。"""
        operator_role_id = getattr(config, "OPERATOR_ROLE_ID", 0)
        if not operator_role_id:
            return False

        # interaction.user is Member in guild contexts
        member: Optional[discord.Member] = None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        elif interaction.guild is not None:
            try:
                member = interaction.guild.get_member(interaction.user.id)
            except Exception:
                member = None

        if not member:
            return False

        return any(r.id == operator_role_id for r in member.roles)

    @app_commands.command(name="list_commands", description="各コマンドの有効・無効状況を表示します")
    async def list_commands(self, interaction: discord.Interaction):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        # Use FEATURE_STATE if present, otherwise use FEATURES
        state = getattr(config, "FEATURE_STATE", None)
        if state is None:
            features = getattr(config, "FEATURES", {})
            state = {k: v.get("enabled", False) for k, v in features.items()}

        lines = [f"{name}: {'有効' if enabled else '無効'}" for name, enabled in sorted(state.items())]
        description = "\n".join(lines) if lines else "(登録されたコマンドがありません)"

        embed = discord.Embed(title="スラッシュコマンドの状態", description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="enable_command", description="指定したコマンドを有効化します")
    @app_commands.describe(command_name="有効化するコマンド名（FEATURES のキー）")
    async def enable_command(self, interaction: discord.Interaction, command_name: str):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if command_name not in getattr(config, "FEATURE_STATE", {}):
            await interaction.response.send_message(f"無効なコマンド名です: {command_name}", ephemeral=True)
            return

        # update both FEATURE_STATE and FEATURES (if present)
        config.FEATURE_STATE[command_name] = True
        if command_name in getattr(config, "FEATURES", {}):
            config.FEATURES[command_name]["enabled"] = True

        logger.info("Enabled command: %s", command_name)
        await interaction.response.send_message(f"コマンド '{command_name}' を有効化しました。", ephemeral=True)

    @app_commands.command(name="disable_command", description="指定したコマンドを無効化します")
    @app_commands.describe(command_name="無効化するコマンド名（FEATURES のキー）")
    async def disable_command(self, interaction: discord.Interaction, command_name: str):
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if command_name not in getattr(config, "FEATURE_STATE", {}):
            await interaction.response.send_message(f"無効なコマンド名です: {command_name}", ephemeral=True)
            return

        config.FEATURE_STATE[command_name] = False
        if command_name in getattr(config, "FEATURES", {}):
            config.FEATURES[command_name]["enabled"] = False

        logger.info("Disabled command: %s", command_name)
        await interaction.response.send_message(f"コマンド '{command_name}' を無効化しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    """Cog を bot に追加します。"""
    await bot.add_cog(Admin(bot))
