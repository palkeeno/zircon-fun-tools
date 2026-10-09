"""Shared private controls for birthday and quote management."""

import logging
import asyncio
import io
import json

from cogs.backups import payload, snapshot_path, restore_snapshot, SnapshotChangedError

import discord

logger = logging.getLogger(__name__)


async def report_error(interaction):
    message = "処理に失敗しました。設定・データを確認して再実行してください。"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class AdminPanel(discord.ui.View):
    def __init__(self, cog, feature, owner_id, file=None):
        super().__init__(timeout=180)
        self.cog = cog
        self.feature = feature
        self.owner_id = owner_id
        self.file = file
        self.busy = False
        self.replace_data.disabled = file is None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("この操作パネルは実行した本人のみ操作できます。", ephemeral=True)
            return False
        if self.busy:
            await interaction.response.send_message("処理中です。しばらくお待ちください。", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction, error, item):
        logger.error("管理パネルの操作に失敗しました", exc_info=error)
        await report_error(interaction)

    def embed(self):
        birthday = self.feature == "birthday"
        settings = self.cog.settings
        name = "誕生日" if birthday else "名言"
        count = len(self.cog.birthdays if birthday else self.cog.quotes)
        embed = discord.Embed(title=f"{name}の管理", color=discord.Color.blue())
        embed.add_field(name="自動投稿", value="ON" if settings.get("enabled", True) else "OFF")
        schedule = f"毎日 {settings['hour']:02d}:00" if birthday else f"{settings['days']}日おき {settings['hour']:02d}:{settings['minute']:02d}"
        embed.add_field(name="投稿スケジュール", value=f"{schedule}（{self.cog.tz}）")
        embed.add_field(name="登録件数", value=f"{count}件")
        embed.description = "データ更新は、コマンドの file にCSV/JSONを添付してください。"
        if self.file:
            embed.description = f"添付ファイル: {discord.utils.escape_markdown(self.file.filename)}\n「データを更新」で全置換の確認を表示します。"
        self.toggle.label = "自動投稿をOFFにする" if settings.get("enabled", True) else "自動投稿をONにする"
        return embed

    @discord.ui.button(label="自動投稿を切り替え", style=discord.ButtonStyle.primary)
    async def toggle(self, interaction, button):
        self.busy = True
        try:
            await interaction.response.defer()
            enabled = not self.cog.settings.get("enabled", True)
            values = {"enabled": enabled}
            if self.feature == "birthday" and enabled:
                values["last_announced_date"] = None
            await self.cog._change_settings(values)
            await interaction.edit_original_response(embed=self.embed(), view=self)
        finally:
            self.busy = False

    @discord.ui.button(label="投稿スケジュール", style=discord.ButtonStyle.secondary)
    async def schedule(self, interaction, button):
        await interaction.response.send_modal(ScheduleModal(self))

    @discord.ui.button(label="データを更新", style=discord.ButtonStyle.danger)
    async def replace_data(self, interaction, button):
        if self.replace_data.disabled:
            await interaction.response.send_message("ファイルを添付してコマンドを再実行してください。", ephemeral=True)
            return
        await interaction.response.send_message(
            "添付ファイルの内容で登録データをすべて置き換えます。更新しますか？",
            view=ReplaceConfirmation(self), ephemeral=True,
        )


    async def download(self, interaction, kind):
        await interaction.response.defer(ephemeral=True)
        async with self.cog._data_lock:
            data = payload(self.cog, self.feature, kind)
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        await interaction.followup.send(
            "現在のデータです。設定ファイルにはBotトークンや環境変数を含みません。",
            file=discord.File(io.BytesIO(content), filename=f"{self.feature}-{kind}.json"),
            ephemeral=True,
        )

    @discord.ui.button(label="データをダウンロード", style=discord.ButtonStyle.secondary, row=1)
    async def export_data(self, interaction, button):
        await self.download(interaction, "data")

    @discord.ui.button(label="設定をダウンロード", style=discord.ButtonStyle.secondary, row=1)
    async def export_settings(self, interaction, button):
        await self.download(interaction, "settings")

    async def ask_restore(self, interaction, kind):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with self.cog._data_lock:
                expected = await asyncio.to_thread(snapshot_path(self.cog, self.feature, kind).read_bytes)
        except FileNotFoundError:
            await interaction.followup.send("復元できるバックアップがありません。次回の管理操作から自動保存されます。", ephemeral=True)
            return
        label = "データ更新" if kind == "data" else "設定変更"
        await interaction.followup.send(
            f"直前の{label}前の状態に戻します。復元しますか？",
            view=RestoreConfirmation(self, kind, expected), ephemeral=True,
        )

    @discord.ui.button(label="データを復元", style=discord.ButtonStyle.danger, row=2)
    async def rollback_data(self, interaction, button):
        await self.ask_restore(interaction, "data")

    @discord.ui.button(label="設定を復元", style=discord.ButtonStyle.danger, row=2)
    async def rollback_settings(self, interaction, button):
        await self.ask_restore(interaction, "settings")


class RestoreConfirmation(discord.ui.View):
    def __init__(self, panel, kind, expected=None):
        super().__init__(timeout=60)
        self.panel = panel
        self.kind = kind
        self.expected = expected
        self.used = False

    async def interaction_check(self, interaction):
        if self.used or self.panel.is_finished():
            await interaction.response.send_message("この確認は終了しました。コマンドを再実行してください。", ephemeral=True)
            return False
        return await self.panel.interaction_check(interaction)

    async def on_error(self, interaction, error, item):
        logger.error("復元に失敗しました", exc_info=error)
        await report_error(interaction)

    @discord.ui.button(label="復元を実行", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.used = True
        self.panel.busy = True
        self.stop()
        try:
            await interaction.response.defer(ephemeral=True)
            try:
                await restore_snapshot(self.panel.cog, self.panel.feature, self.kind, self.expected)
            except SnapshotChangedError:
                await interaction.edit_original_response(content="別の管理操作でバックアップが変わりました。管理パネルから復元を選び直してください。", view=None)
                return
            await interaction.edit_original_response(content="更新前の状態へ復元しました。管理パネルを開き直すと最新の状態を確認できます。", view=None)
        finally:
            self.panel.busy = False

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.used = True
        self.stop()
        await interaction.response.edit_message(content="復元をキャンセルしました。", view=None)


class ScheduleModal(discord.ui.Modal):
    def __init__(self, panel):
        super().__init__(title="投稿スケジュールの設定", timeout=180)
        self.panel = panel
        settings = panel.cog.settings
        self.hour = discord.ui.TextInput(label="投稿時刻・時（0〜23）", default=str(settings["hour"]), max_length=2)
        self.add_item(self.hour)
        if panel.feature == "quote":
            self.days = discord.ui.TextInput(label="投稿間隔・日数（1以上）", default=str(settings["days"]), max_length=9)
            self.minute = discord.ui.TextInput(label="投稿時刻・分（0〜59）", default=str(settings["minute"]), max_length=2)
            self.add_item(self.days)
            self.add_item(self.minute)

    async def on_submit(self, interaction):
        if self.panel.is_finished():
            await interaction.response.send_message("操作パネルの有効期限が切れました。コマンドを再実行してください。", ephemeral=True)
            return
        if not await self.panel.interaction_check(interaction):
            return
        try:
            hour = int(self.hour.value)
            if not 0 <= hour <= 23:
                raise ValueError
            values = {"hour": hour}
            if self.panel.feature == "quote":
                days, minute = int(self.days.value), int(self.minute.value)
                if days < 1 or not 0 <= minute <= 59:
                    raise ValueError
                values.update(days=days, minute=minute, last_posted_at=None)
        except ValueError:
            await interaction.response.send_message("時は0〜23、分は0〜59、日数は1以上の整数で指定してください。", ephemeral=True)
            return
        self.panel.busy = True
        try:
            await interaction.response.defer()
            await self.panel.cog._change_settings(values)
            await interaction.edit_original_response(embed=self.panel.embed(), view=self.panel)
        finally:
            self.panel.busy = False

    async def on_error(self, interaction, error):
        logger.error("スケジュールの変更に失敗しました", exc_info=error)
        await report_error(interaction)


class ReplaceConfirmation(discord.ui.View):
    def __init__(self, panel):
        super().__init__(timeout=60)
        self.panel = panel
        self.used = False

    async def interaction_check(self, interaction):
        if self.used or self.panel.is_finished() or self.panel.replace_data.disabled:
            await interaction.response.send_message("この確認は終了しました。コマンドを再実行してください。", ephemeral=True)
            return False
        return await self.panel.interaction_check(interaction)

    async def on_error(self, interaction, error, item):
        logger.error("データ更新に失敗しました", exc_info=error)
        await report_error(interaction)

    @discord.ui.button(label="全置換を実行", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self.used = True
        self.panel.busy = True
        self.panel.replace_data.disabled = True
        self.stop()
        try:
            update = getattr(self.panel.cog, f"_{self.panel.feature}_update")
            await update(interaction, self.panel.file)
            await interaction.message.edit(content="確認済みです。更新結果のメッセージをご確認ください。", view=None)
        finally:
            self.panel.busy = False

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.used = True
        self.stop()
        await interaction.response.edit_message(content="更新をキャンセルしました。", view=None)
