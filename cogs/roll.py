"""Optional, independent dice rolling options."""

import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
MAX_SIDES = 2**53 - 1
MAX_COUNT = 100


class Roll(commands.Cog):
    """Roll integers and optionally sort the results."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="roll", description="ダイスを振って1から指定した範囲の数字を出します")
    @app_commands.describe(
        n="範囲の上限（省略すると6、1以上の整数）",
        m="振る回数（省略すると1、1〜100回）",
        sort="小さい順に並べる（省略すると出た順）",
    )
    async def roll(
        self,
        interaction: discord.Interaction,
        n: app_commands.Range[int, 1, MAX_SIDES] = 6,
        m: app_commands.Range[int, 1, MAX_COUNT] = 1,
        sort: bool = False,
    ):
        """Respond with comma-separated rolls, preserving duplicates."""
        if not 1 <= n <= MAX_SIDES or not 1 <= m <= MAX_COUNT:
            await interaction.response.send_message(
                f"範囲は1〜{MAX_SIDES}、回数は1〜{MAX_COUNT}の整数で指定してください。",
                ephemeral=True,
            )
            return
        try:
            results = [random.randint(1, n) for _ in range(m)]
            if sort:
                results.sort()
            await interaction.response.send_message(
                ", ".join(str(result) for result in results)
            )
        except Exception:
            logger.exception("ダイスロールに失敗しました")
            if interaction.response.is_done():
                await interaction.followup.send("ダイスロールに失敗しました。", ephemeral=True)
            else:
                await interaction.response.send_message("ダイスロールに失敗しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    """Register the dice rolling cog."""
    await bot.add_cog(Roll(bot))
