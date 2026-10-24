"""Interactive major-arcana readings without automatic interpretation."""

import asyncio
import logging
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from command_errors import send_error
from cogs.tarot_cards import CARDS, POSITIONS

logger = logging.getLogger(__name__)
TITLES = {"one": "ワンオラクル", "three": "過去・現在・未来", "choice": "二者択一"}
TIMEOUT = 300
MENTIONS = discord.AllowedMentions.none()


def safe_text(value: str) -> str:
    """Keep user text from changing the result's formatting or mentioning people."""
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))


def card_embed(number: int, reversed_: bool, title: str) -> discord.Embed:
    """Render the same complete set of meanings on every draw."""
    card = CARDS[number]
    embed = discord.Embed(title=title, color=discord.Color.purple())
    embed.add_field(name=f"{card.number:02d} {card.name} ― {'逆位置' if reversed_ else '正位置'}",
                    value="／".join(card.reversed if reversed_ else card.upright), inline=False)
    embed.add_field(name="カードの意味", value=card.reversed_text if reversed_ else card.upright_text,
                    inline=False)
    return embed


class TarotButton(discord.ui.Button):
    """Bind a component to the exact screen on which it appeared."""

    def __init__(self, panel, action: str, label: str, row: int, slot=None):
        super().__init__(label=label, row=row, style=discord.ButtonStyle.secondary,
                         custom_id=f"tarot:{panel.revision}:{action}:{slot}")
        self.action = action
        self.slot = slot
        self.revision = panel.revision

    async def callback(self, interaction: discord.Interaction):
        await self.view.act(interaction, self.action, self.revision, self.slot)


class TarotView(discord.ui.View):
    """One in-memory reading; no questions or readings are persisted."""

    def __init__(self, owner_id: int, spread: str, mode: str = "single",
                 reversed_: bool = True, private: bool = False):
        super().__init__(timeout=TIMEOUT)
        self.owner_id = owner_id
        self.spread = spread
        self.mode = mode
        self.private = private
        self.phase = "input" if spread == "choice" else "reading"
        deck = list(range(len(CARDS)))
        random.shuffle(deck)
        self.deck = tuple((number, bool(random.getrandbits(1)) if reversed_ else False)
                          for number in deck)
        self.selected: list[int] = []
        self.question = ""
        self.a = ""
        self.b = ""
        self.revision = 0
        self.message = None
        self.lock = asyncio.Lock()
        self.deadline = time.monotonic() + TIMEOUT
        self.refresh()

    @property
    def count(self) -> int:
        return len(POSITIONS[self.spread])

    def touch(self):
        self.deadline = time.monotonic() + TIMEOUT

    def refresh(self):
        """Rebuild controls; stale components cannot advance a newer screen."""
        self.clear_items()
        if self.phase in {"done", "expired", "cancelled"}:
            return
        if self.phase in {"input", "confirm"}:
            self.add_item(TarotButton(self, "input", "選択肢を入力する" if self.phase == "input"
                                      else "入力し直す", 0))
            if self.phase == "confirm":
                self.add_item(TarotButton(self, "start", "引き始める", 0))
            self.add_item(TarotButton(self, "cancel", "キャンセル", 0))
        elif self.spread == "choice":
            label = POSITIONS[self.spread][len(self.selected)][0]
            self.add_item(TarotButton(self, "next", f"{len(self.selected) + 1}枚目を引く：{label}", 0))
            self.add_item(TarotButton(self, "all", "残りをまとめて引く", 0))
        else:
            for slot in range(len(CARDS)):
                chosen = slot in self.selected
                label = f"選択{self.selected.index(slot) + 1}" if chosen else f"伏せ札 {slot + 1:02d}"
                button = TarotButton(self, "pick", label, slot // 5, slot)
                button.disabled = chosen
                self.add_item(button)
            self.add_item(TarotButton(self, "cancel", "終了する", 4))

    def embeds(self) -> list[discord.Embed]:
        """Render only revealed cards, keeping all earlier results visible."""
        header = discord.Embed(title=f"タロット：{TITLES[self.spread]}", color=discord.Color.purple())
        lines = ["大アルカナ22枚。同じカードは重複しません。解釈はあなた自身でどうぞ。"]
        if self.spread == "choice":
            if self.phase in {"input", "confirm"}:
                lines.append("A・Bの2つの選択肢を入力してください。Botはどちらがよいかを判定しません。")
                lines.append("入力内容と結果は自分だけに表示されます。" if self.private
                             else "入力した問い・A・Bと結果は、このチャンネルに公開されます。")
            lines.append("配置：1 現在 → 2 Aの経過 → 3 Bの経過 → 4 Aの結果 → 5 Bの結果")
            if self.a:
                lines.extend((f"A：{safe_text(self.a)}", f"B：{safe_text(self.b)}"))
            if self.question:
                lines.append(f"問い：{safe_text(self.question)}")
        elif self.phase == "reading":
            position = POSITIONS[self.spread][len(self.selected)][0]
            lines.append(f"伏せ札から{len(self.selected) + 1}枚目「{position}」を選んでください。")
            if self.mode == "all" and self.count > 1:
                lines.append("3枚を選び終えたら、まとめて結果を公開します。")
        if self.phase == "expired":
            lines.append("操作期限が切れました。新しく /tarot を実行してください。")
        elif self.phase == "cancelled":
            lines.append("終了しました。")
        elif self.phase == "done":
            lines.append("すべてのカードを公開しました。位置とカードの意味を照らし合わせてみてください。")
        header.description = "\n".join(lines)
        header.set_footer(text=f"{'非公開' if self.private else '公開'} · {len(self.selected)}/{self.count}枚選択 · 操作期限5分")
        result = [header]
        # In all mode, an interrupted reading must not reveal partial selections.
        if self.mode == "all" and len(self.selected) < self.count:
            return result
        for index, slot in enumerate(self.selected):
            position, description = POSITIONS[self.spread][index]
            embed = card_embed(*self.deck[slot], f"{index + 1}枚目：{position}")
            if self.spread == "choice" and index:
                option = self.a if index in {1, 3} else self.b
                description += f"\n選択肢：{safe_text(option)}"
            embed.add_field(name="位置の意味", value=description, inline=False)
            embed.set_footer(text=f"選んだ伏せ札：{slot + 1:02d}")
            result.append(embed)
        return result

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("この占いは実行した本人だけが操作できます。", ephemeral=True)
            return False
        return True

    async def valid(self, interaction: discord.Interaction, revision: int) -> bool:
        """Also guard modal submissions, which bypass the View's dispatch checks."""
        if not await self.interaction_check(interaction):
            return False
        if self.phase in {"done", "expired", "cancelled"} or time.monotonic() >= self.deadline:
            await interaction.response.send_message("この占いの操作は終了しています。", ephemeral=True)
            return False
        if revision != self.revision:
            await interaction.response.send_message("画面が更新されています。最新のボタンで操作してください。", ephemeral=True)
            return False
        return True

    async def update(self, interaction: discord.Interaction):
        self.revision += 1
        self.touch()
        self.refresh()
        await interaction.response.edit_message(embeds=self.embeds(), view=self, allowed_mentions=MENTIONS)
        if self.phase in {"done", "cancelled"}:
            self.stop()

    async def act(self, interaction: discord.Interaction, action: str, revision: int, slot=None):
        """Serialize actions, including clicks delivered before a screen update."""
        async with self.lock:
            if not await self.valid(interaction, revision):
                return
            if action == "input" and self.phase in {"input", "confirm"}:
                self.touch()
                await interaction.response.send_modal(ChoiceModal(self))
                return
            if action == "cancel":
                self.phase = "cancelled"
            elif action == "start" and self.phase == "confirm":
                self.phase = "reading"
                if self.mode == "all":
                    self.selected = list(range(self.count))
            elif self.phase == "reading":
                if action == "pick" and self.spread != "choice" and slot not in self.selected and slot in range(22):
                    self.selected.append(slot)
                elif action == "next" and self.spread == "choice":
                    self.selected.append(len(self.selected))
                elif action == "all" and self.spread == "choice":
                    self.selected = list(range(self.count))
                else:
                    await interaction.response.send_message("最新の画面からカードを選んでください。", ephemeral=True)
                    return
            else:
                return
            if len(self.selected) == self.count:
                self.phase = "done"
            await self.update(interaction)

    async def on_timeout(self):
        async with self.lock:
            if self.phase in {"done", "cancelled"}:
                return
            self.phase = "expired"
            self.revision += 1
            self.refresh()
            if self.message:
                try:
                    await self.message.edit(embeds=self.embeds(), view=self, allowed_mentions=MENTIONS)
                except discord.HTTPException:
                    logger.warning("Could not expire tarot controls", exc_info=True)

    async def on_error(self, interaction, error, item):
        await send_error(interaction, error)


class ChoiceModal(discord.ui.Modal):
    """Ask for choices after the command, with examples for first-time users."""

    def __init__(self, panel: TarotView):
        super().__init__(title="二者択一：2つの選択肢", timeout=TIMEOUT)
        self.panel = panel
        self.revision = panel.revision
        self.question = discord.ui.TextInput(label="占いたいこと（任意）", placeholder="例：休日をどう過ごそう？",
                                             required=False, max_length=200, default=panel.question)
        self.a = discord.ui.TextInput(label="選択肢A", placeholder="例：外に遊びに行く", max_length=80, default=panel.a)
        self.b = discord.ui.TextInput(label="選択肢B", placeholder="例：家でゆっくり過ごす", max_length=80, default=panel.b)
        for field in (self.question, self.a, self.b):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        async with self.panel.lock:
            if not await self.panel.valid(interaction, self.revision):
                return
            a, b = self.a.value.strip(), self.b.value.strip()
            if not a or not b:
                raise ValueError("選択肢A・Bは空白だけにせず入力してください。入力ボタンからやり直せます。")
            if a == b:
                raise ValueError("選択肢A・Bには異なる内容を入力してください。入力ボタンからやり直せます。")
            self.panel.question = self.question.value.strip()
            self.panel.a, self.panel.b = a, b
            self.panel.phase = "confirm"
            await self.panel.update(interaction)

    async def on_error(self, interaction, error):
        await send_error(interaction, error)


class Tarot(commands.GroupCog, group_name="tarot", group_description="大アルカナの占い・カード図鑑"):
    """Register readings as clearly described slash subcommands."""

    async def send_reading(self, interaction, spread, mode, reversed_, private):
        panel = TarotView(interaction.user.id, spread, mode, reversed_, private)
        await interaction.response.send_message(embeds=panel.embeds(), view=panel, ephemeral=private,
                                                allowed_mentions=MENTIONS)
        panel.message = await interaction.original_response()

    @app_commands.command(name="one", description="伏せ札から1枚選んで占います")
    @app_commands.describe(private="自分だけに表示（省略時は公開）", reversed="逆位置を含める（省略時は含める）")
    async def one(self, interaction: discord.Interaction, private: bool = False, reversed: bool = True):
        await self.send_reading(interaction, "one", "single", reversed, private)

    @app_commands.command(name="three", description="伏せ札から過去・現在・未来の3枚を選びます")
    @app_commands.describe(private="自分だけに表示（省略時は公開）", reversed="逆位置を含める（省略時は含める）",
                           mode="single：1枚ずつ公開／all：3枚選んでから一括公開")
    @app_commands.choices(mode=[app_commands.Choice(name="1枚ずつ公開", value="single"),
                               app_commands.Choice(name="3枚選んでから一括公開", value="all")])
    async def three(self, interaction: discord.Interaction, mode: str = "single",
                    private: bool = False, reversed: bool = True):
        await self.send_reading(interaction, "three", mode, reversed, private)

    @app_commands.command(name="choice", description="A・Bを入力し、経過と結果を5枚で見る二者択一です")
    @app_commands.describe(private="入力内容と結果を自分だけに表示（省略時は公開）",
                           reversed="逆位置を含める（省略時は含める）",
                           mode="single：ボタンで1枚ずつ引く／all：5枚を一括表示")
    @app_commands.choices(mode=[app_commands.Choice(name="1枚ずつ引く", value="single"),
                               app_commands.Choice(name="5枚をまとめて引く", value="all")])
    async def choice(self, interaction: discord.Interaction, mode: str = "single",
                     private: bool = False, reversed: bool = True):
        await self.send_reading(interaction, "choice", mode, reversed, private)

    @app_commands.command(name="card", description="大アルカナの正位置・逆位置の意味を調べます")
    @app_commands.describe(name="調べるカード", private="自分だけに表示（省略時は公開）")
    @app_commands.choices(name=[app_commands.Choice(name=f"{card.number:02d} {card.name}", value=card.number)
                               for card in CARDS])
    async def card(self, interaction: discord.Interaction, name: app_commands.Range[int, 0, 21],
                   private: bool = False):
        card = CARDS[name]
        embed = discord.Embed(title=f"カード図鑑：{card.number:02d} {card.name}", description=card.theme,
                              color=discord.Color.purple())
        for reverse in (False, True):
            embed.add_field(name="逆位置" if reverse else "正位置",
                            value="／".join(card.reversed if reverse else card.upright) + "\n"
                            + (card.reversed_text if reverse else card.upright_text), inline=False)
        embed.set_footer(text="大アルカナ22枚 · 力 VIII／正義 XI · 解釈の手がかりとしてお使いください")
        await interaction.response.send_message(embed=embed, ephemeral=private, allowed_mentions=MENTIONS)


async def setup(bot: commands.Bot):
    """Load the tarot slash command group."""
    await bot.add_cog(Tarot())
