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
        count="抽選する人数（1以上、最大50人）",
        exclude_role="抽選対象外とするロール（このロールを持つ人は除外）"
    )
    async def lottery(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        count: int,
        exclude_role: discord.Role = None
    ):
        try:
            if not config.is_feature_enabled('lottery'):
                await interaction.response.send_message("現在抽選機能は無効化されています。", ephemeral=True)
                return

            if count < 1 or count > 50:
                await interaction.response.send_message("抽選人数は1～50人で指定してください。", ephemeral=True)
                return

            # 除外ロールを持つ人を除外
            members = [m for m in role.members if not m.bot and (exclude_role is None or exclude_role not in m.roles)]
            if len(members) < count:
                await interaction.response.send_message(f"ロール「{role.name}」のメンバーが{count}人未満です。", ephemeral=True)
                return

            already_winners = set()
            await interaction.response.send_message(
                f"🎉 抽選を開始します！\n対象ロール: {role.mention}\n抽選人数: {count}人\n"
                f"抽選は順番に発表されます。お楽しみに！"
            )

            await asyncio.sleep(2)
            for i in range(1, count + 1):
                # 抽選対象から既当選者を除外
                candidates = [m for m in members if m not in already_winners]
                if not candidates:
                    await interaction.channel.send("抽選可能なメンバーがいなくなりました。")
                    break
                winner = random.choice(candidates)
                already_winners.add(winner)
                await interaction.channel.send(f"# 【{i}人目！】")
                # 3秒カウントダウン
                for sec in range(3, 0, -1):
                    msg = await interaction.channel.send(f"## …{sec}…")
                    await asyncio.sleep(1)
                # 抽選発表
                embed = discord.Embed(
                    title=f"🎊 当選者発表！ : {i}人目",
                    description=f"# ✨ **{winner.mention}** さん、おめでとうございます！ 🎉",
                    color=discord.Color.gold()
                )
                await interaction.channel.send(embed=embed)
                if i != count:
                    await interaction.channel.send(f"抽選を進めるには、{interaction.user.mention} が『次行くぞ！』と発言してください。")
                    def check(m):
                        return (
                            m.channel == interaction.channel and
                            m.author == interaction.user and
                            m.content.strip() == "次行くぞ！"
                        )
                    try:
                        await self.bot.wait_for("message", check=check, timeout=300)  # 5分待機
                    except asyncio.TimeoutError:
                        await interaction.channel.send(f"時間切れのため抽選を終了します。")
                        return
            await interaction.channel.send("🎉 全ての抽選が終了しました！おめでとうございます！")
        except Exception as e:
            logger.error(f"抽選コマンド実行中にエラー: {e}\n{traceback.format_exc()}")
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Lottery(bot))