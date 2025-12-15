"""Lottery cog

抽選を行うスラッシュコマンドを提供します。

仕様（要約）:
 - /lottery role count
 - 指定人数分ランダムに選出。重複選出はしない。
 - 発表前に演出（何人目の告知 + カウントダウン）を表示。
 - 各当選者発表後、当選を開始した人がNextボタンを押すことで次の抽選に移る
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


class ShowResultsView(discord.ui.View):
    """キャンセル時に当選者一覧を表示するか確認するView"""

    def __init__(self, operator_id: int):
        super().__init__(timeout=60.0)  # 1分でタイムアウト
        self.operator_id = operator_id
        self.show_results: Optional[bool] = None

    @discord.ui.button(label="はい", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """はいボタンが押されたときの処理"""
        # 権限チェック: 抽選を開始したユーザーのみ
        if interaction.user.id != self.operator_id:
            await interaction.response.send_message(
                "このボタンは抽選を開始したユーザーのみ操作できます。",
                ephemeral=True
            )
            return

        self.show_results = True
        self.stop()
        await interaction.response.send_message("当選者一覧を表示します。", ephemeral=True)

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.secondary, emoji="❌")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """いいえボタンが押されたときの処理"""
        # 権限チェック: 抽選を開始したユーザーのみ
        if interaction.user.id != self.operator_id:
            await interaction.response.send_message(
                "このボタンは抽選を開始したユーザーのみ操作できます。",
                ephemeral=True
            )
            return
        self.show_results = False
        self.stop()
        # 公開メッセージで通知
        await interaction.response.send_message("一覧表示をスキップします。")


class NextLotteryView(discord.ui.View):
    """次の抽選に進むためのボタンを持つView"""

    def __init__(self, operator_id: int):
        super().__init__(timeout=900.0)  # 15分でタイムアウト
        self.operator_id = operator_id
        self.value: Optional[bool] = None

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Nextボタンが押されたときの処理"""
        # 権限チェック: 抽選を開始したユーザーのみ
        if interaction.user.id != self.operator_id:
            await interaction.response.send_message(
                "このボタンは抽選を開始したユーザーのみ操作できます。",
                ephemeral=True
            )
            return

        self.value = True
        self.stop()
        # 公開メッセージとして通知（ephemeralではない）
        await interaction.response.send_message("次の抽選を開始します！")

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """キャンセルボタンが押されたときの処理"""
        # 権限チェック: 抽選を開始したユーザーのみ
        if interaction.user.id != self.operator_id:
            await interaction.response.send_message(
                "このボタンは抽選を開始したユーザーのみ操作できます。",
                ephemeral=True
            )
            return

        self.value = False
        self.stop()
        # ここでは公開メッセージは送らず、メインフロー側で
        # 「抽選がキャンセルされました。ここまでの結果を表示しますか？」を投稿する
        await interaction.response.defer()


class Lottery(commands.Cog):
    """抽選を扱うCog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Lottery が初期化されました")

    # _is_operator removed


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

            # 次の抽選に進むためのボタンを表示（最後の当選者以外）
            if i < count:
                view = NextLotteryView(interaction.user.id)
                next_msg = await send_target("管理者が「Next」ボタンを押すと次の抽選を開始します。", view=view)
                
                # ボタンが押されるまで待機（タイムアウト: 300秒）
                await view.wait()
                
                if view.value is None:
                    # タイムアウト
                    # ビューのボタンを無効化してメッセージを更新
                    try:
                        for child in view.children:
                            child.disabled = True
                        await next_msg.edit(content="タイムアウトしました。抽選を終了します。", view=view)
                    except Exception:
                        await send_target("タイムアウトしました。抽選を終了します。")
                    break
                elif not view.value:
                    # キャンセルされた - 確認ビューへ差し替え
                    try:
                        for child in view.children:
                            child.disabled = True
                        confirm_view = ShowResultsView(interaction.user.id)
                        await next_msg.edit(content="抽選がキャンセルされました。ここまでの結果を表示しますか？", view=confirm_view)
                        confirm_msg = next_msg
                    except Exception:
                        confirm_view = ShowResultsView(interaction.user.id)
                        confirm_msg = await send_target("抽選がキャンセルされました。ここまでの結果を表示しますか？", view=confirm_view)

                    await confirm_view.wait()

                    if confirm_view.show_results:
                        # 「はい」: ボタン無効化し結果表示へ（ループ終了で後段表示）
                        try:
                            for child in confirm_view.children:
                                child.disabled = True
                            await confirm_msg.edit(content="ここまでの結果を表示します。", view=confirm_view)
                        except Exception:
                            pass
                        break
                    else:
                        # 「いいえ」またはタイムアウト: ボタン無効化し別メッセージ投稿
                        try:
                            for child in confirm_view.children:
                                child.disabled = True
                            await confirm_msg.edit(view=confirm_view)  # 内容はそのまま、ボタンだけ無効化
                        except Exception:
                            pass
                        await send_target("抽選が中断されました。")
                        already_winners.clear()  # 結果を表示しない
                        break
                # view.value が True なら次へ進む
                try:
                    for child in view.children:
                        child.disabled = True
                    await next_msg.edit(content="Nextが押されました。次の抽選に進みます…", view=view)
                except Exception:
                    pass
            else:
                # 最後の当選者なので少し余韻を持たせる
                await asyncio.sleep(3)

        # 最終当選者一覧を表示（空の場合は何も表示しない）
        if already_winners:
            desc_lines = [f"{idx+1}. {m.mention}" for idx, m in enumerate(already_winners)]
            final_embed = discord.Embed(title="🏆 抽選結果一覧", description="\n".join(desc_lines), color=discord.Color.green())
            await send_target(embed=final_embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lottery(bot))
