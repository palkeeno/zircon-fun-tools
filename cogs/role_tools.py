"""Remove a role from all members without deleting the role itself."""
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


def validate_role(guild, actor, role):
    if not actor.guild_permissions.manage_roles:
        raise ValueError("ロール管理権限が必要です")
    if role.is_default() or role.managed:
        raise ValueError("@everyone・連携管理ロールは解除できません")
    if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
        raise ValueError("Botのロール管理権限とロール階層を確認してください")
    if actor.id != guild.owner_id and role >= actor.top_role:
        raise ValueError("自分の最上位ロール以上のロールは解除できません")


async def targets(guild, role):
    return [member async for member in guild.fetch_members(limit=None) if role in member.roles]


class RemovalConfirmation(discord.ui.View):
    def __init__(self, cog, owner_id, guild, role):
        super().__init__(timeout=60)
        self.cog, self.owner_id, self.guild, self.role = cog, owner_id, guild, role
        self.used = False
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or self.used:
            await interaction.response.send_message("この確認は実行した本人だけが一度操作できます。", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.used = True
        if self.message:
            try:
                await self.message.edit(content="確認期限が切れました。ロールは変更していません。", view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="全員から解除する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.used = True
        self.stop()
        await interaction.response.defer()
        role = self.guild.get_role(self.role.id)
        try:
            if role is None:
                raise ValueError("ロールが存在しません")
            validate_role(self.guild, interaction.user, role)
        except ValueError as exc:
            await interaction.edit_original_response(content=str(exc), view=None)
            return
        key = (self.guild.id, role.id)
        if key in self.cog.running:
            await interaction.edit_original_response(content="このロールの解除は既に処理中です。", view=None)
            return
        self.cog.running.add(key)
        try:
            members = await targets(self.guild, role)
            await interaction.edit_original_response(content=f"{len(members)}人から解除しています…", view=None)
            succeeded, failed = 0, []
            for number, member in enumerate(members, 1):
                try:
                    # atomic=True removes only this role, preserving concurrent changes to other roles.
                    await member.remove_roles(role, reason=f"/remove-role by {self.owner_id}", atomic=True)
                    succeeded += 1
                except discord.HTTPException:
                    failed.append(member.id)
                    logger.exception("Role removal failed for member %s", member.id)
                if number % 10 == 0:
                    try:
                        await interaction.edit_original_response(content=f"解除中: {number}/{len(members)}人（成功{succeeded}・失敗{len(failed)}）", view=None)
                    except discord.HTTPException:
                        logger.warning("Could not publish role removal progress")
                await asyncio.sleep(0.1)
            summary = f"解除完了: 成功{succeeded}人・失敗{len(failed)}人。ロール自体は残しています。"
            if failed:
                summary += "\n失敗したメンバーID（先頭10件）: " + ", ".join(map(str, failed[:10]))
            logger.info("Role %s removal by %s: %s succeeded, %s failed", role.id, self.owner_id, succeeded, len(failed))
            await interaction.edit_original_response(content=summary, view=None)
        finally:
            self.cog.running.discard(key)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.used = True
        self.stop()
        await interaction.response.edit_message(content="キャンセルしました。ロールは変更していません。", view=None)

    async def on_error(self, interaction, error, item):
        from command_errors import send_error
        await send_error(interaction, error)


class RoleTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = set()

    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.command(name="remove-role", description="指定ロールを全員から解除します（ロール自体は削除しません）")
    async def remove_role(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        try:
            validate_role(interaction.guild, interaction.user, role)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        members = await targets(interaction.guild, role)
        view = RemovalConfirmation(self, interaction.user.id, interaction.guild, role)
        view.message = await interaction.followup.send(
            f"「{discord.utils.escape_markdown(role.name)}」を{len(members)}人から解除します。ロールは削除しません。実行しますか？",
            view=view, ephemeral=True, wait=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(RoleTools(bot))
