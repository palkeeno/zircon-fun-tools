"""cogs.admin
管理者向けのスラッシュコマンドを提供します。

このモジュールは以下のスラッシュコマンドを提供します:
 - /permit <command> <role>: 指定コマンドを指定ロールに限定解除（管理者以外も実行可）
 - /permit_revoke <command> <role>: 上記限定解除を取り消す
 - /permit_list: 現在の限定解除状況を一覧表示

使用は運営ロール（`config.OPERATOR_ROLE_ID`）に制限されます。
"""

from __future__ import annotations

import logging
from typing import Optional, Set

import discord
from discord import app_commands
from discord.ext import commands

import config
import permissions

logger = logging.getLogger(__name__)


class Admin(commands.Cog):
    """管理者コマンドコグ。運営ロールのみ使用可能なコマンドを提供します。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _defer_ephemeral(self, interaction: discord.Interaction) -> None:
        """Respond early to avoid 'Unknown interaction' by deferring ephemerally.

        Discord requires an initial acknowledgement within ~3 seconds. By deferring
        immediately, we ensure the token remains valid and we can safely edit the
        original response later.
        """
        try:
            if not interaction.response.is_done():
                # thinking=True shows the loading state; keep responses ephemeral
                await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            # If deferring fails, we'll try to continue and handle errors on send.
            logger.debug("Failed to defer interaction response", exc_info=True)

    # --- Backward-compatibility helper for tests ---
    def is_command_enabled(self, name: str) -> bool:
        """Feature flags are deprecated; return True by default.
        Kept to satisfy existing tests expecting this callable.
        """
        try:
            return bool(config.FEATURES.get(name, {}).get("enabled", True))
        except Exception:
            return True

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

    # ----------------------
    # New permit management
    # ----------------------
    def _valid_command_names(self) -> Set[str]:
        try:
            return {cmd.name for cmd in self.bot.tree.get_commands()}
        except Exception:
            return set()

    @app_commands.command(name="permit", description="指定コマンドを指定ロールに限定解除します（そのロール保持者が実行可能に）")
    @app_commands.describe(command_name="スラッシュコマンド名", role="限定解除する対象ロール")
    async def permit(self, interaction: discord.Interaction, command_name: str, role: discord.Role):
        await self._defer_ephemeral(interaction)
        if not await self._is_operator(interaction):
            await interaction.edit_original_response(content="このコマンドは運営ロールのみ使用できます。")
            return
        valid = self._valid_command_names()
        if command_name not in valid:
            await interaction.edit_original_response(content=f"不明なコマンド名です: {command_name}")
            return
        if interaction.guild is None:
            await interaction.edit_original_response(content="サーバー内で実行してください。")
            return
        permissions.grant_permission(interaction.guild.id, command_name, role.id)
        await interaction.edit_original_response(
            content=f"コマンド '{command_name}' をロール {role.mention} に限定解除しました。",
        )

    @app_commands.command(name="permit_revoke", description="限定解除を取り消します")
    @app_commands.describe(command_name="スラッシュコマンド名", role="取り消す対象ロール")
    async def permit_revoke(self, interaction: discord.Interaction, command_name: str, role: discord.Role):
        await self._defer_ephemeral(interaction)
        if not await self._is_operator(interaction):
            await interaction.edit_original_response(content="このコマンドは運営ロールのみ使用できます。")
            return
        valid = self._valid_command_names()
        if command_name not in valid:
            await interaction.edit_original_response(content=f"不明なコマンド名です: {command_name}")
            return
        if interaction.guild is None:
            await interaction.edit_original_response(content="サーバー内で実行してください。")
            return
        permissions.revoke_permission(interaction.guild.id, command_name, role.id)
        await interaction.edit_original_response(
            content=f"コマンド '{command_name}' のロール {role.mention} への限定解除を取り消しました。",
        )

    @app_commands.command(name="permit_list", description="このサーバーの限定解除状況を一覧表示します")
    async def permit_list(self, interaction: discord.Interaction):
        await self._defer_ephemeral(interaction)
        if not await self._is_operator(interaction):
            await interaction.edit_original_response(content="このコマンドは運営ロールのみ使用できます。")
            return
        if interaction.guild is None:
            await interaction.edit_original_response(content="サーバー内で実行してください。")
            return
        data = permissions.list_all_permissions(interaction.guild.id)
        if not data:
            await interaction.edit_original_response(content="現在、限定解除は設定されていません。")
            return
        # Build description lines with role mentions
        lines = []
        for cmd_name, role_ids in sorted(data.items()):
            mentions = []
            for rid in role_ids:
                role = interaction.guild.get_role(int(rid))
                mentions.append(role.mention if role else f"@&{rid}")
            lines.append(f"/{cmd_name}: {', '.join(mentions) if mentions else '(なし)'}")
        embed = discord.Embed(title="限定解除状況", description="\n".join(lines), color=discord.Color.blue())
        await interaction.edit_original_response(embed=embed, content=None)


async def setup(bot: commands.Bot):
    """Cog を bot に追加します。"""
    await bot.add_cog(Admin(bot))
