"""Lottery cog

抽選を行うスラッシュコマンドを提供します。

仕様（要約）:
 - /lottery role count
 - 運営ロールのみ実行可能（`config.OPERATOR_ROLE_ID`）
 - `config.is_feature_enabled('lottery')` が True の時のみ実行可能
 - 指定人数分ランダムに選出。重複選出はしない。
 - 発表前に演出（何人目の告知 + カウントダウン）を表示。
 - 各当選者発表後、少し間を置いて次を行う。
 - 最後に当選者一覧を表示する。
"""

from __future__ import annotations

import random
import asyncio
import logging
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

import config

logger = logging.getLogger(__name__)


class Lottery(commands.Cog):
    """抽選を扱うCog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_operator(self, interaction: discord.Interaction) -> bool:
        operator_role_id = getattr(config, "OPERATOR_ROLE_ID", 0)
        if not operator_role_id:
            return False

        member: Optional[discord.Member] = None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        elif interaction.guild is not None:
            member = interaction.guild.get_member(interaction.user.id)

        if not member:
            return False

        return any(r.id == operator_role_id for r in member.roles)

    @app_commands.command(name="lottery", description="指定ロールから人数分を抽選して順に発表します")
    @app_commands.describe(
        role="抽選対象のロール",
        count="抽選する人数（1以上）",
    )
    async def lottery(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        count: int,
    ):
        # 初期バリデーション
        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        if not config.is_feature_enabled('lottery'):
            await interaction.response.send_message("現在抽選機能は無効化されています。", ephemeral=True)
            return

        if count < 1:
            await interaction.response.send_message("抽選人数は1以上で指定してください。", ephemeral=True)
            return

        # 集合作成（ボット除外）。指定ロールを持つ全員が対象。
        members = [m for m in role.members if not m.bot]
        if len(members) < count:
            await interaction.response.send_message(f"ロール「{role.name}」の対象人数が不足しています（{len(members)}人）。", ephemeral=True)
            return

        # 最初の応答
        await interaction.response.send_message(
            f"🎉 抽選を開始します！対象ロール: {role.mention}、抽選人数: {count}人。発表は順次行います。",
            ephemeral=False,
        )

        channel = interaction.channel

        # unified send_target wrapper: always returns a Message when possible
        if channel is None:
            async def send_target(*args, **kwargs):
                # when using followup, request the message object with wait=True
                return await interaction.followup.send(*args, wait=True, **kwargs)
        else:
            async def send_target(*args, **kwargs):
                return await channel.send(*args, **kwargs)

        already_winners: List[discord.Member] = []

        # 少し待って盛り上げ
        await asyncio.sleep(1.5)

        for i in range(1, count + 1):
            # 候補を更新
            candidates = [m for m in members if m not in already_winners]
            if not candidates:
                await send_target("抽選可能なメンバーがいなくなりました。抽選を終了します。")
                break

            winner = random.choice(candidates)
            already_winners.append(winner)

            # 発表前の煽りメッセージ
            header = f"# 【{i}人目の当選者を発表します！】"
            await send_target(header)

            # カウントダウン（編集で見せるのがスマートだが、単純送信でもOK）
            await send_target("カウントダウン... 3")
            await asyncio.sleep(1)
            for sec in range(2, 0, -1):
                await send_target(f"カウントダウン... {sec}")
                await asyncio.sleep(1)

            # 当選発表（Embed）
            embed = discord.Embed(
                title=f"🎊 当選者発表 — {i}人目 🎊",
                description=f"✨ **{winner.display_name}** さん、当選です！\n{winner.mention}",
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=winner.display_avatar.url if hasattr(winner, 'display_avatar') else discord.Embed.Empty)
            await send_target(embed=embed)

            # 少し余韻を持たせる
            await asyncio.sleep(15)

        # 最終当選者一覧を表示
        if already_winners:
            # 当選者をメンションして見やすく表示
            desc_lines = [f"{idx+1}. {m.mention}" for idx, m in enumerate(already_winners)]
            final_embed = discord.Embed(title="🏆 抽選結果一覧", description="\n".join(desc_lines), color=discord.Color.green())
            await send_target(embed=final_embed)
        else:
            await send_target("当選者はいませんでした。")


async def setup(bot: commands.Bot):
    await bot.add_cog(Lottery(bot))
