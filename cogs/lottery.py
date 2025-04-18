"""
抽選機能を提供するCog
指定ロールから指定人数を順番に抽選し、演出付きで発表します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import logging
import traceback
import config

logger = logging.getLogger(__name__)

class Lottery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="lottery",
        description="指定したロールから指定人数を順番に抽選します"
    )
    @app_commands.describe(
        role="抽選対象のロール",
        count="抽選する人数（1以上、最大50人）"
    )
    async def lottery(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        count: int
    ):
        try:
            if not config.is_feature_enabled('lottery'):
                await interaction.response.send_message("現在抽選機能は無効化されています。", ephemeral=True)
                return

            if count < 1 or count > 50:
                await interaction.response.send_message("抽選人数は1～50人で指定してください。", ephemeral=True)
                return

            members = [m for m in role.members if not m.bot]
            if len(members) < count:
                await interaction.response.send_message(f"ロール「{role.name}」のメンバーが{count}人未満です。", ephemeral=True)
                return

            selected = random.sample(members, count)
            await interaction.response.send_message(
                f"🎉 抽選を開始します！\n対象ロール: {role.mention}\n抽選人数: {count}人\n"
                f"抽選は順番に発表されます。お楽しみに！"
            )

            await asyncio.sleep(2)
            for i, member in enumerate(selected, 1):
                await interaction.channel.send(f"【{i}人目！】")
                # 3秒カウントダウン
                for sec in range(3, 0, -1):
                    msg = await interaction.channel.send(f"…{sec}…")
                    await asyncio.sleep(1)
                    await msg.delete()
                # 抽選発表
                embed = discord.Embed(
                    title="🎊 当選者発表！",
                    description=f"✨ **{member.mention}** さん、おめでとうございます！ 🎉",
                    color=discord.Color.gold()
                )
                await interaction.channel.send(embed=embed)
                if i != count:
                    await asyncio.sleep(15)
            await interaction.channel.send("🎉 全ての抽選が終了しました！おめでとうございます！")
        except Exception as e:
            logger.error(f"抽選コマンド実行中にエラー: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Lottery(bot))