"""In-Discord guide generated from loaded slash commands."""
import discord
from discord import app_commands
from discord.ext import commands
from cogs.pagination import Pagination


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="コマンド一覧と使い方を表示します")
    async def help_command(self, interaction: discord.Interaction):
        guild = discord.Object(id=interaction.guild_id) if interaction.guild_id else None
        roots = self.bot.tree.get_commands(guild=guild) or self.bot.tree.get_commands()
        entries = []
        for command in roots:
            if isinstance(command, app_commands.Group):
                entries.extend(child for child in command.walk_commands()
                               if isinstance(child, app_commands.Command))
            else:
                entries.append(command)
        entries.sort(key=lambda c: c.qualified_name)
        def render(command):
            args = " ".join(f"{p.name}:<{p.description if p.description != '…' else p.name}>" for p in command.parameters)
            permissions = ""
            if command.default_permissions:
                permissions = "\n必要な既定権限: " + ", ".join(name for name, enabled in command.default_permissions if enabled)
            return f"/{command.qualified_name}", f"{command.description}\n`/{command.qualified_name} {args}`"[:800] + permissions
        view = Pagination(entries, interaction.user.id, "Zircon Fun Tools · コマンド一覧", render)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(Help(bot))
