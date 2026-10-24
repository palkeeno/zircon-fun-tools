"""受付・抽選・ロール回収を管理する、再起動可能なイベント。"""
import asyncio
import copy
import json
import io
import os
import random
import uuid

import discord
from discord import app_commands
from discord.ext import commands

import config
import utils
from command_errors import send_error
from cogs.role_tools import validate_role


CONDITIONS = {"message": "チャンネルで発言", "keyword": "指定の言葉", "button": "参加ボタン",
              "reaction": "リアクション", "attachment": "画像・ファイル", "form": "フォーム"}
METHODS = {"random": "順次ランダム抽選", "majority": "多数派が勝利", "minority": "少数派が勝利"}


def select_winners(event):
    """0票を除外。同票の選択肢はすべて勝利。"""
    people = list(event["entries"])
    if event["method"] == "random":
        if len(people) < event["count"]:
            raise ValueError("参加人数が抽選人数に足りません。受付を継続します。")
        return random.sample(people, event["count"])
    buckets = {}
    for uid, entry in event["entries"].items():
        vote = entry.get("vote")
        if vote is not None:
            buckets.setdefault(vote, []).append(uid)
    if not buckets:
        raise ValueError("投票がありません。受付を継続します。")
    target = (max if event["method"] == "majority" else min)(map(len, buckets.values()))
    return [uid for group in buckets.values() if len(group) == target for uid in group]


class EventView(discord.ui.View):
    def __init__(self, cog, event):
        super().__init__(timeout=None)
        self.cog, self.key = cog, event["id"]
        for action, label, style in [
            ("join", "参加 / フォーム", discord.ButtonStyle.success),
            ("leave", "辞退", discord.ButtonStyle.secondary),
            ("draw", "締切して抽選 / 次を発表", discord.ButtonStyle.primary),
            ("reset", "終了・ロール回収 / 回収再試行", discord.ButtonStyle.danger),
        ]:
            if action == "join" and event["condition"] not in {"button", "form"}:
                continue
            button = discord.ui.Button(label=label, style=style, custom_id=f"event:{self.key}:{action}")
            async def callback(interaction, action=action):
                await self.dispatch(interaction, action)
            button.callback = callback
            self.add_item(button)
        if event["method"] != "random":
            select = discord.ui.Select(placeholder="投票先を選択（締切まで変更可）", custom_id=f"event:{self.key}:vote",
                                       options=[discord.SelectOption(label=s, value=str(i)) for i, s in enumerate(event["options"])])
            async def vote(interaction):
                await self.dispatch(interaction, "vote", int(select.values[0]))
            select.callback = vote
            self.add_item(select)

    async def dispatch(self, interaction, action, vote=None):
        try:
            event = self.cog.events.get(self.key)
            if not event:
                raise ValueError("このイベントは終了しました。")
            if action == "join" and event["condition"] == "form":
                await interaction.response.send_modal(EntryForm(self.cog, self.key, event["question"]))
                return
            await interaction.response.defer(ephemeral=True)
            if action in {"draw", "reset"}:
                if interaction.user.id not in [event["owner"], *event.get("controllers", [])]:
                    raise ValueError("作成者だけが進行できます。別の運営者は /event_manage を使ってください。")
                await self.cog.advance(self.key, interaction.guild, interaction.channel, reset=action == "reset")
                message = "進行しました。ロール回収の失敗があれば再試行してください。"
            elif action == "leave":
                await self.cog.leave(self.key, interaction.user)
                message = "参加を取り消しました。"
            else:
                await self.cog.join(self.key, interaction.user, vote=vote, via=action)
                message = "参加・投票を登録しました。"
            await interaction.followup.send(message, ephemeral=True)
        except Exception as error:
            await send_error(interaction, error)

    async def on_error(self, interaction, error, item):
        await send_error(interaction, error)


class EntryForm(discord.ui.Modal):
    def __init__(self, cog, key, question):
        super().__init__(title="イベント参加フォーム")
        self.cog, self.key = cog, key
        self.answer = discord.ui.TextInput(label=question, max_length=500, style=discord.TextStyle.paragraph)
        self.add_item(self.answer)

    async def on_submit(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await self.cog.join(self.key, interaction.user, via="form", answer=str(self.answer))
            await interaction.followup.send("応募しました。投票型の場合は続けて投票先を選んでください。", ephemeral=True)
        except Exception as error:
            await send_error(interaction, error)

    async def on_error(self, interaction, error):
        await send_error(interaction, error)


class Events(commands.Cog):
    def __init__(self, bot, path=None):
        self.bot = bot
        self.path = path or os.path.join(config._DATA_DIR, "events.json")
        self.events = {}
        self.lock = asyncio.Lock()
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as handle:
                self.events = json.load(handle)
            if not isinstance(self.events, dict):
                raise ValueError("events.json が不正です。元ファイルを保護して起動を中止します。")

    async def cog_load(self):
        for event in self.events.values():
            self.bot.add_view(EventView(self, event))

    def save(self):
        utils.atomic_write_json(self.path, self.events)

    def change(self, key, event):
        before = copy.deepcopy(self.events)
        if event is None:
            self.events.pop(key, None)
        else:
            self.events[key] = event
        try:
            self.save()
        except Exception:
            self.events = before
            raise

    def eligible(self, event, member):
        if member.guild.id != event["guild"] or member.bot or member.id == event["owner"]:
            raise ValueError("Botとイベント作成者は参加対象外です。")
        if event["required"] and event["required"] not in [r.id for r in member.roles]:
            raise ValueError("参加に必要なロールがありません。")

    async def join(self, key, member, *, via, vote=None, answer=None):
        async with self.lock:
            event = copy.deepcopy(self.events[key])
            if event["state"] != "open":
                raise ValueError("受付は終了しています。")
            self.eligible(event, member)
            uid = str(member.id)
            if via == "vote" and uid not in event["entries"] and event["condition"] != "button":
                raise ValueError("先に指定された条件で参加登録してください。")
            if via != "vote" and via != event["condition"] and not (via == "join" and event["condition"] == "button"):
                raise ValueError("このイベントの参加条件を満たしていません。")
            if uid not in event["entries"] and len(event["entries"]) >= 1000:
                raise ValueError("参加上限1000人に達しました。")
            entry = event["entries"].setdefault(uid, {})
            if vote is not None:
                if not 0 <= vote < len(event["options"]):
                    raise ValueError("投票先が不正です。")
                entry["vote"] = vote
            if answer is not None:
                entry["answer"] = answer
            # 先に保存し、API成功直後の再起動でも回収対象を失わない。
            self.change(key, event)
            role = member.guild.get_role(event["role"])
            if event["role"] and role is None:
                raise ValueError("参加者ロールが削除されています。運営者へ連絡してください。")
            if role:
                await member.add_roles(role, atomic=True, reason="イベント参加")

    async def leave(self, key, member):
        async with self.lock:
            event = copy.deepcopy(self.events[key])
            if event["state"] != "open":
                raise ValueError("締切後は辞退できません。運営者へ連絡してください。")
            uid = str(member.id)
            if uid not in event["entries"]:
                return
            role = member.guild.get_role(event["role"])
            if role:
                await member.remove_roles(role, atomic=True, reason="イベント辞退")
            del event["entries"][uid]
            self.change(key, event)

    async def advance(self, key, guild, channel, *, reset=False):
        async with self.lock:
            event = copy.deepcopy(self.events[key])
            if guild.id != event["guild"]:
                raise ValueError("別サーバーのイベントです。")
            if reset:
                event["state"] = "cleanup"
                self.change(key, event)
            if event["state"] == "open":
                # 締切と選出を同じ保存で確定。以後のクリックで引き直さない。
                event["winners"] = select_winners(event)
                event["index"] = 0
                event["state"] = "drawing"
                self.change(key, event)
            if event["state"] == "drawing":
                i = event["index"]
                if i < len(event["winners"]):
                    uid = event["winners"][i]
                    if event["method"] != "random":
                        # 投票型は結果をまとめて発表。送信済みの範囲を保存する。
                        while event["index"] < len(event["winners"]):
                            start = event["index"]
                            group = event["winners"][start:start + 30]
                            await channel.send("🏆 " + METHODS[event["method"]] + "・当選者：\n" + " ".join(f"<@{u}>" for u in group),
                                               allowed_mentions=discord.AllowedMentions.none())
                            event["index"] += len(group)
                            self.change(key, event)
                    else:
                        await self.announce_random(key, event, channel, uid, i)
                if event["index"] < len(event["winners"]):
                    return
                event["state"] = "cleanup"
                self.change(key, event)
            if event["state"] == "cleanup":
                await self.cleanup(key, event, guild, channel)

    async def announce_random(self, key, event, channel, uid, i):
        await channel.send(f"🎲 {i + 1}人目の発表まで…")
        await asyncio.sleep(event.get("interval", 5))
        await channel.send(f"🎊 {i + 1}人目の当選者：<@{uid}>",
                           allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        event["index"] += 1
        self.change(key, event)

    async def cleanup(self, key, event, guild, channel):
        failed = []
        role = guild.get_role(event["role"])
        for uid in list(event["entries"]):
            try:
                member = await guild.fetch_member(int(uid))
                if role:
                    await member.remove_roles(role, atomic=True, reason="イベント終了")
            except discord.NotFound:
                pass  # 脱退済み
            except discord.HTTPException:
                failed.append(uid)
                continue
            del event["entries"][uid]
            self.change(key, event)
        if not failed:
            self.change(key, None)
        await channel.send(f"受付終了・ロール回収：残り{len(failed)}人。" + ("回収再試行ボタンを押してください。" if failed else "イベントを終了しました。"),
                           allowed_mentions=discord.AllowedMentions.none())

    async def create(self, interaction, *, title, role, required, channels, condition, method,
                     count, interval=5, keyword="", contains=False, message_id=0, emoji="✅", options="", question="参加名・希望枠"):
        if role:
            validate_role(interaction.guild, interaction.user, role)
        if required and role and required.id == role.id:
            raise ValueError("参加者ロールと必須ロールは別にしてください。")
        ids = [int(s.strip().strip("<#>")) for s in channels.split(",") if s.strip()]
        if not ids or len(ids) > 10 or any(not isinstance(interaction.guild.get_channel(i), discord.TextChannel) for i in ids):
            raise ValueError("対象チャンネルは同じサーバーのテキストチャンネルを1〜10件指定してください。")
        choices = [s.strip() for s in options.split("|") if s.strip()]
        if method != "random" and (not 2 <= len(choices) <= 25 or len(set(choices)) != len(choices) or any(len(s) > 100 for s in choices)):
            raise ValueError("投票の選択肢は | 区切りで重複なしの2〜25件、各100文字以内です。")
        if condition == "keyword" and not keyword.strip():
            raise ValueError("指定の言葉を入力してください。")
        if condition == "reaction":
            await interaction.guild.get_channel(ids[0]).fetch_message(message_id)
        async with self.lock:
            if len(self.events) >= 20:
                raise ValueError("進行中イベントは20件までです。終了・回収してから作成してください。")
            if role and any(e["role"] == role.id for e in self.events.values()):
                raise ValueError("その参加者ロールは進行中イベントで使用中です。")
            # 前回分の印が残る状態で受付しない。
            if role:
                async for member in interaction.guild.fetch_members(limit=None):
                    if role in member.roles:
                        raise ValueError("参加者ロールが残っています。先に /remove-role でリセットしてください。")
            key = uuid.uuid4().hex[:12]
            event = dict(id=key, title=title, guild=interaction.guild.id, owner=interaction.user.id,
                         role=role.id if role else 0, required=required.id if required else 0,
                         channels=ids, condition=condition, method=method, count=count, interval=interval, keyword=keyword,
                         contains=contains, message_id=message_id, emoji=emoji, options=choices,
                         question=question, state="open", entries={})
            self.change(key, event)
        await interaction.followup.send(f"受付開始：{title}\nイベントID：`{key}`\n条件：{CONDITIONS[condition]} / {METHODS[method]}\n対象：" + " ".join(f"<#{i}>" for i in ids),
                                        view=EventView(self, event), allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="lottery", description="通常抽選の受付開始。発言で参加ロール付与、抽選時締切、終了時自動回収")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    async def lottery(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel,
                      count: app_commands.Range[int, 1, 100], required_role: discord.Role = None, interval: app_commands.Range[int, 5, 60] = 5):
        await interaction.response.defer()
        # 公開パネルは別送信（進行者のみ操作可能）。
        await self.create(interaction, title="通常抽選", role=role, required=required_role, channels=str(channel.id),
                          condition="message", method="random", count=count, interval=interval)

    @app_commands.command(name="event_create", description="参加条件と選出方式を選んでイベントの受付を開始")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.choices(condition=[app_commands.Choice(name=n, value=v) for v, n in CONDITIONS.items()],
                          method=[app_commands.Choice(name=n, value=v) for v, n in METHODS.items()])
    @app_commands.describe(channels="対象チャンネルのIDまたはメンション。複数はカンマ区切り（最大10件）",
                           role="参加の目印・告知用の専用ロール（任意）", required_role="参加資格に必要なロール（任意）",
                           options="投票型の選択肢を | 区切りで指定。同票は全該当選択肢が勝利、0票は除外",
                           message_id="リアクション対象メッセージID（最初の対象チャンネル内）",
                           keyword="言葉条件で使う文字列", contains="言葉の部分一致。Falseなら完全一致",
                           question="フォームの質問（1項目）", count="ランダム型の当選人数。投票型は該当者全員が当選")
    async def event_create(self, interaction: discord.Interaction, title: app_commands.Range[str, 1, 80],
                           channels: str, condition: str, method: str, role: discord.Role = None,
                           required_role: discord.Role = None, count: app_commands.Range[int, 1, 100] = 1,
                           keyword: str = "", contains: bool = False, message_id: str = "0", emoji: str = "✅",
                           options: str = "", question: app_commands.Range[str, 1, 45] = "参加名・希望枠"):
        await interaction.response.defer()
        await self.create(interaction, title=title, role=role, required=required_role, channels=channels,
                          condition=condition, method=method, count=count, keyword=keyword, contains=contains,
                          message_id=int(message_id), emoji=emoji, options=options, question=question)

    @app_commands.command(name="event_manage", description="イベント状態確認・操作パネル再表示（再起動後も利用可）")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    async def event_manage(self, interaction: discord.Interaction, event_id: str = ""):
        if not event_id:
            lines = [f"`{e['id']}` {e['title']} / {e['state']} / {len(e['entries'])}人"
                     for e in self.events.values() if e["guild"] == interaction.guild_id]
            await interaction.response.send_message("\n".join(lines[:10]) or "進行中のイベントはありません。", ephemeral=True)
            if len(lines) > 10:
                await interaction.followup.send("\n".join(lines[10:]), ephemeral=True)
            return
        async with self.lock:
            event = copy.deepcopy(self.events.get(event_id))
            if not event or event["guild"] != interaction.guild_id:
                raise ValueError("進行中のイベントが見つかりません。")
            event.setdefault("controllers", []).append(interaction.user.id)
            self.change(event_id, event)
        await interaction.response.send_message(f"{event['title']} / {event['state']} / 参加{len(event['entries'])}人", view=EventView(self, event), ephemeral=True,
                                                file=discord.File(io.BytesIO(json.dumps(event["entries"], ensure_ascii=False, indent=2).encode("utf-8")), filename="participants.json"))

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.guild.id != config.GUILD_ID or message.author.bot:
            return
        for key, event in list(self.events.items()):
            if event["state"] != "open" or message.channel.id not in event["channels"]:
                continue
            condition = event["condition"]
            matches = condition == "message" or (condition == "attachment" and bool(message.attachments))
            if condition == "keyword":
                matches = event["keyword"] in message.content if event["contains"] else event["keyword"] == message.content.strip()
            if matches:
                try:
                    await self.join(key, message.author, via=condition)
                except (ValueError, discord.HTTPException):
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.reaction(payload, False)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.reaction(payload, True)

    async def reaction(self, payload, remove):
        if payload.guild_id != config.GUILD_ID:
            return
        for key, event in list(self.events.items()):
            if (event["state"] != "open" or event["condition"] != "reaction" or payload.channel_id != event["channels"][0]
                    or payload.message_id != event["message_id"] or str(payload.emoji) != event["emoji"]):
                continue
            try:
                guild = self.bot.get_guild(payload.guild_id)
                member = await guild.fetch_member(payload.user_id)
                if remove:
                    await self.leave(key, member)
                else:
                    await self.join(key, member, via="reaction")
            except (ValueError, discord.HTTPException):
                pass


async def setup(bot):
    await bot.add_cog(Events(bot))
