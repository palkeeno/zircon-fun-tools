"""
誕生日管理のコグ
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import logging
import traceback
import datetime
import os
import config
import utils
from birthday_records import normalize, select
from cogs.pagination import Pagination

import csv
import io
from typing import Any, Dict, Optional, Tuple

# ロギングの設定
logger = logging.getLogger(__name__)

class BirthdayPaginationView(discord.ui.View):
    """誕生日一覧のページネーション用ビュー"""

    def __init__(self, birthdays: list):
        super().__init__(timeout=180)
        self.birthdays = birthdays
        self.current_page = 0
        self.items_per_page = 8
        self.max_pages = (len(birthdays) - 1) // self.items_per_page + 1

        # ボタンの初期状態を更新
        self.update_buttons()

    def update_buttons(self):
        """ボタンの有効/無効を更新"""
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1

    def create_embed(self) -> discord.Embed:
        """現在のページのEmbedを作成"""
        embed = discord.Embed(
            title="🎂 誕生日一覧",
            description="登録されているZirconキャラクターの誕生日一覧です",
            color=discord.Color.pink()
        )

        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.birthdays))
        page_items = self.birthdays[start_idx:end_idx]

        # 1つのフィールドに8行のデータを記載
        lines = []
        for b in page_items:
            char_id = b.get("character_id", "???")
            name = b.get("name", "不明")
            month = b.get("month", 0)
            day = b.get("day", 0)
            lines.append(f"{char_id}, {name} : birthday({month:02d}/{day:02d})")

        embed.add_field(
            name=f"ページ {self.current_page + 1}/{self.max_pages}",
            value="\n".join(lines),
            inline=False
        )

        embed.set_footer(text=f"全 {len(self.birthdays)} 件")
        return embed

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """前のページへ"""
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """次のページへ"""
        self.current_page = min(self.max_pages - 1, self.current_page + 1)
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class Birthday(commands.Cog):
    """誕生日管理のコグ"""

    def __init__(self, bot: commands.Bot, data_path: Optional[str] = None):
        """
        誕生日管理のコグを初期化します。

        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
        self.data_path = data_path or os.path.join(config._DATA_DIR, "birthdays.json")
        self.tz = utils.get_timezone()
        self.birthdays = []
        self.defaults: Dict[str, Any] = self._feature_defaults()
        self.settings: Dict[str, Any] = {}
        self.birthday_task_started = False
        self._data_lock = asyncio.Lock()  # JSONファイルの排他制御用ロック
        self.load_birthdays()
        self._load_settings()
        self._refresh_daily_flags(datetime.datetime.now(self.tz))
        logger.info("Birthday が初期化されました")

    def _feature_defaults(self) -> Dict[str, Any]:
        feature_settings = config.get_feature_settings("birthday")
        default_enabled = feature_settings.get("default_enabled", True)
        default_hour = feature_settings.get("default_hour", 9)
        return {
            "enabled": self._coerce_bool(default_enabled, True),
            "hour": self._clamp_int(default_hour, 0, 23, 9),
            "last_announced_date": None,
            "last_reset_date": None,
        }

    @staticmethod
    def _coerce_bool(value: Any, fallback: bool) -> bool:
        return utils.coerce_bool(value, fallback)

    @staticmethod
    def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
        return utils.clamp_int(value, minimum, maximum, fallback)

    def _load_settings(self) -> None:
        stored = config.get_runtime_section("birthday")
        normalized = {
            "enabled": self._coerce_bool(stored.get("enabled"), self.defaults["enabled"]),
            "hour": self._clamp_int(stored.get("hour"), 0, 23, self.defaults["hour"]),
            "last_announced_date": stored.get("last_announced_date") if isinstance(stored.get("last_announced_date"), str) else None,
            "last_reset_date": stored.get("last_reset_date") if isinstance(stored.get("last_reset_date"), str) else None,
        }
        self.settings = normalized
        self._persist_settings()

    def _persist_settings(self) -> None:
        config.set_runtime_section("birthday", self.settings)

    async def _change_settings(self, values: Dict[str, Any]) -> None:
        async with self._data_lock:
            updated = {**self.settings, **values}
            await asyncio.to_thread(config.set_runtime_section, "birthday", updated)
            self.settings = updated

    def _refresh_daily_flags(self, now: datetime.datetime) -> None:
        today_str = now.date().isoformat()
        if self.settings.get("last_reset_date") == today_str:
            return
        changed = False
        for record in self.birthdays:
            if record.get("reported"):
                record["reported"] = False
                changed = True
        if changed:
            self.save_birthdays()
        self.settings["last_reset_date"] = today_str
        self._persist_settings()

    def _is_scheduled_time(self, now: datetime.datetime) -> bool:
        target_hour = self._clamp_int(self.settings.get("hour"), 0, 23, self.defaults["hour"])
        return now.hour >= target_hour

    @commands.Cog.listener()
    async def on_ready(self):
        """ボットの準備が完了したときに誕生日タスクを開始します（常時）。"""
        if not self.birthday_task_started:
            self.birthday_task.start()
            self.birthday_task_started = True

    @tasks.loop(minutes=1)
    async def birthday_task(self):
        """スケジュールされた時刻に誕生日をチェックして通知するタスク"""
        try:
            now = datetime.datetime.now(self.tz)
            async with self._data_lock:
                await asyncio.to_thread(self._refresh_daily_flags, now)

            if not self.settings.get("enabled", True):
                return

            if not self._is_scheduled_time(now):
                return

            today_str = now.date().isoformat()
            pending_today = any(b["month"] == now.month and b["day"] == now.day
                                and not b.get("reported", False) for b in self.birthdays)
            if self.settings.get("last_announced_date") == today_str and not pending_today:
                return

            announced = await self._announce_today_birthdays(now)
            if announced:
                await self._change_settings({"last_announced_date": today_str})
        except Exception as e:
            logger.error(f"Error in birthday_task: {e}")
            logger.error(traceback.format_exc())

    async def _announce_today_birthdays(self, now: datetime.datetime) -> bool:
        async with self._data_lock:
            return await self._announce_today_birthdays_locked(now)

    async def _announce_today_birthdays_locked(self, now: datetime.datetime) -> bool:
        today_month = now.month
        today_day = now.day
        today_birthdays = [b for b in self.birthdays if b.get("month") == today_month and b.get("day") == today_day]
        if not today_birthdays:
            return False

        channel_id = config.get_birthday_channel_id()
        if not channel_id:
            logger.warning("誕生日チャンネルIDが設定されていません")
            return False

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)  # type: ignore[attr-defined]
            except Exception:
                logger.error(f"誕生日チャンネルが見つかりません: {channel_id}")
                return False

        unreported_birthdays = [b for b in today_birthdays if not b.get("reported", False)]
        if not unreported_birthdays:
            return True

        unique: Dict[Tuple[Optional[str], int, int], list] = {}
        for record in today_birthdays:
            key = (str(record.get("character_id", "")).strip(), record.get("month"), record.get("day"))
            unique.setdefault(key, []).append(record)

        announced_any = False
        for grouped_records in unique.values():
            if all(record.get("reported", False) for record in grouped_records):
                continue
            birthday_record = grouped_records[0]
            if any(record.get("reported", False) for record in grouped_records) or await self._announce_zircon_birthday(channel, birthday_record):
                for record in grouped_records:
                    record["reported"] = True
                announced_any = True

        if announced_any:
            await asyncio.to_thread(self.save_birthdays)

        return announced_any and all(b.get("reported", False) for b in today_birthdays)

    async def _announce_zircon_birthday(self, channel, birthday_data) -> bool:
        character_id = str(birthday_data.get("character_id", ""))
        embed = discord.Embed(title="🎉 誕生日おめでとう！ 🎉",
            description=f"**{birthday_data.get('name', '不明')}** の誕生日です！", color=discord.Color.blue())
        embed.add_field(name="誕生日", value=f"{birthday_data.get('month')}月{birthday_data.get('day')}日")
        embed.add_field(name="キャラクター番号", value=character_id)
        file = None
        try:
            path = await config.IMAGE_CACHE.get(config.get_character_image_url(character_id))
            file = discord.File(path, filename=f"{character_id}.png")
            embed.set_thumbnail(url=f"attachment://{character_id}.png")
        except Exception:
            logger.warning("画像取得に失敗したため文字だけでお祝いします: %s", character_id, exc_info=True)
        try:
            if file:
                await channel.send(embed=embed, file=file)
            else:
                await channel.send(embed=embed)
            return True
        except Exception:
            logger.exception("誕生日の送信に失敗しました: %s", character_id)
            return False
        finally:
            if file:
                file.close()

    def load_birthdays(self):
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        if not os.path.isfile(self.data_path):
            self.birthdays = []
            self.save_birthdays()
            return
        with open(self.data_path, encoding="utf-8") as handle:
            rows = json.load(handle)
        if not isinstance(rows, list):
            raise ValueError("birthdays.json must be a list")
        valid, rejected, dates_by_id = [], [], {}
        for number, row in enumerate(rows, 1):
            try:
                record = normalize(row)
                date = (record["month"], record["day"])
                if record["character_id"] in dates_by_id and dates_by_id[record["character_id"]] != date:
                    raise ValueError("同じキャラクターIDに異なる誕生日が登録されています")
                dates_by_id[record["character_id"]] = date
                valid.append(record)
            except (ValueError, TypeError) as exc:
                rejected.append({"row": number, "error": str(exc), "record": row})
        self.birthdays = valid
        if rejected:
            utils.atomic_write_json(self.data_path + ".rejected.json", rejected)
            logger.warning("Rejected %s invalid birthdays; original preserved", len(rejected))
            raise ValueError("誕生日データに不正なレコードがあります。.rejected.jsonを確認してください")

    def save_birthdays(self):
        utils.atomic_write_json(self.data_path, self.birthdays)

    def cog_unload(self):
        self.birthday_task.cancel()

    async def save_birthdays_async(self):
        """誕生日データを非同期で保存します（ロック付き）。"""
        async with self._data_lock:
            await asyncio.to_thread(self.save_birthdays)

    @app_commands.command(name="birthday", description="誕生日を一覧・検索・今日・今月・次に来る順で表示します")
    @app_commands.choices(mode=[app_commands.Choice(name="一覧", value="all"),
        app_commands.Choice(name="今日", value="today"), app_commands.Choice(name="今月", value="month"),
        app_commands.Choice(name="次に来る順", value="upcoming")])
    async def birthday(self, interaction: discord.Interaction, id_or_name: Optional[str] = None, mode: str = "all"):
        records = select(self.birthdays, mode, datetime.datetime.now(self.tz).date())
        if id_or_name:
            query = id_or_name.strip().casefold()
            records = [b for b in records if query in b['character_id'].casefold() or query in b['name'].casefold()]
        if not records:
            await interaction.response.send_message("該当する誕生日はありません。", ephemeral=True)
            return
        titles = {"all": "誕生日一覧", "today": "今日の誕生日", "month": "今月の誕生日", "upcoming": "次に来る誕生日順"}
        view = Pagination(records, interaction.user.id, titles[mode],
            lambda b: (f"{b['name']} (#{b['character_id']})", f"{b['month']}月{b['day']}日"))
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.message = await interaction.original_response()

    async def _handle_search(self, interaction: discord.Interaction, query: str):
        candidates = [b for b in self.birthdays
                     if query in b.get("character_id", "") or query.lower() in b.get("name", "").lower()]

        if not candidates:
            await interaction.response.send_message(
                f"`{query}` に一致するキャラクターの誕生日は登録されていません。",
                ephemeral=True
            )
            return

        if len(candidates) == 1:
            result = candidates[0]
            await self._show_birthday_detail(interaction, result)
        else:
            await self._show_birthday_list_embed(interaction, candidates, title=f"🔍 検索結果: {len(candidates)}件")

    async def _show_birthday_detail(self, interaction: discord.Interaction, data: dict):
        char_id = data.get("character_id", "???")
        char_name = data.get("name", "不明")
        month = data.get("month", 0)
        day = data.get("day", 0)

        embed = discord.Embed(title="🎂 誕生日情報", color=discord.Color.pink())
        embed.add_field(name="キャラクターID", value=char_id, inline=True)
        embed.add_field(name="名前", value=char_name, inline=True)
        embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=True)

        await interaction.response.send_message(embed=embed)

    async def _handle_list(self, interaction: discord.Interaction):
        if not self.birthdays:
            await interaction.response.send_message("登録されている誕生日はありません。", ephemeral=True)
            return

        sorted_birthdays = sorted(self.birthdays, key=lambda x: (x["month"], x["day"]))

        if len(sorted_birthdays) > 8:
            view = BirthdayPaginationView(sorted_birthdays)
            embed = view.create_embed()
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await self._show_birthday_list_embed(interaction, sorted_birthdays)

    async def _show_birthday_list_embed(self, interaction: discord.Interaction, data: list, title="🎂 誕生日一覧"):
        embed = discord.Embed(title=title, color=discord.Color.pink())
        lines = []
        for b in data[:10]:
            char_id = b.get("character_id", "???")
            name = b.get("name", "不明")
            month = b.get("month", 0)
            day = b.get("day", 0)
            lines.append(f"**{name}** (#{char_id}) - {month}月{day}日")

        embed.add_field(name="キャラクター", value="\n".join(lines), inline=False)
        if len(data) > 10:
            embed.set_footer(text=f"※ 表示件数制限のため先頭10件のみ表示しています。")

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)


    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="birthday_update", description="ファイルからデータを一括更新します（全置換）")
    @app_commands.describe(file="更新用ファイル（CSV/JSON）")
    async def birthday_update(self, interaction: discord.Interaction, file: discord.Attachment):
        """
        運営専用: アップロードされたファイルの内容で誕生日リストを完全に置き換えます。
        対応フォーマット:
        - JSON: list of dicts [{"character_id": "...", "name": "...", "month": 1, "day": 1}]
        - CSV: character_id, name, month, day (ヘッダーあり推奨)
        """

        await interaction.response.defer(ephemeral=True)

        try:
            content = await file.read()
            filename = file.filename.lower()
            new_birthdays = []

            if filename.endswith(".json"):
                data = json.loads(content.decode("utf-8"))
                if isinstance(data, list):
                    new_birthdays = data
                else:
                    await interaction.followup.send("JSONフォーマットエラー: ルートはリストである必要があります。", ephemeral=True)
                    return
            elif filename.endswith(".csv"):
                rows = [row for row in csv.reader(io.StringIO(content.decode("utf-8-sig"))) if any(cell.strip() for cell in row)]
                if rows:
                    headers = [cell.strip().lower() for cell in rows[0]]
                    if "character_id" in headers:
                        if not {"character_id", "month", "day"}.issubset(headers):
                            raise ValueError("CSVヘッダーにcharacter_id, month, dayが必要です")
                        for row in rows[1:]:
                            if len(row) != len(headers):
                                raise ValueError("CSV行の項目数がヘッダーと一致しません")
                            new_birthdays.append(dict(zip(headers, row)))
                    else:
                        for row in rows:
                            if len(row) == 4:
                                new_birthdays.append(dict(character_id=row[0], name=row[1], month=row[2], day=row[3]))
                            elif len(row) == 3:
                                new_birthdays.append(dict(character_id=row[0], name="不明", month=row[1], day=row[2]))
                            else:
                                raise ValueError("CSV行は3または4項目で指定してください")
            else:
                await interaction.followup.send("対応していないファイル形式です (.json, .csv)", ephemeral=True)
                return

            if not new_birthdays:
                await interaction.followup.send("有効な誕生日データが見つかりませんでした。", ephemeral=True)
                return

            validated = []
            for row in new_birthdays:
                try:
                    validated.append(normalize({**row, "reported": False}))
                except (ValueError, TypeError):
                    continue

            if not validated:
                await interaction.followup.send("検証後の有効データが0件のため更新しません。既存データは保持されます。", ephemeral=True)
                return
            keys = [b["character_id"] for b in validated]
            if len(keys) != len(set(keys)):
                await interaction.followup.send("キャラクターIDの重複があるため更新しません。", ephemeral=True)
                return
            invalid_count = len(new_birthdays) - len(validated)
            if invalid_count:
                await interaction.followup.send(f"不正なデータが{invalid_count}件あるため更新しません。ファイルを修正してください。", ephemeral=True)
                return
            async with self._data_lock:
                previous = self.birthdays
                reported = {}
                for b in previous:
                    key = (b["character_id"], b["month"], b["day"])
                    reported[key] = reported.get(key, False) or b.get("reported", False)
                for record in validated:
                    record["reported"] = reported.get((record["character_id"], record["month"], record["day"]), False)
                self.birthdays = validated
                try:
                    await asyncio.to_thread(self.save_birthdays)
                except Exception:
                    self.birthdays = previous
                    raise

            await interaction.followup.send(f"誕生日データを全置換しました。({len(self.birthdays)} 件)", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in birthday_update: {e}", exc_info=True)
            await interaction.followup.send("ファイルの読み込みまたは処理中にエラーが発生しました。", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="birthday_toggle",
        description="誕生日の自動投稿をON/OFFします"
    )
    @app_commands.describe(enabled="true で有効化、false で無効化")
    async def birthday_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        """誕生日の自動投稿機能を切り替えるコマンド."""

        updated = {"enabled": bool(enabled)}
        if enabled:
            updated["last_announced_date"] = None
        await self._change_settings(updated)
        status = "有効" if enabled else "無効"
        await interaction.response.send_message(
            f"誕生日の自動投稿を{status}にしました。",
            ephemeral=True,
        )

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="birthday_schedule",
        description="誕生日の自動投稿時刻を設定します (時のみ指定)"
    )
    @app_commands.describe(hour="自動投稿する時刻 (0-23)")
    async def birthday_schedule(self, interaction: discord.Interaction, hour: int) -> None:
        """誕生日の自動投稿時刻を設定するコマンド."""

        if hour < 0 or hour > 23:
            await interaction.response.send_message(
                "時刻は0-23の範囲で指定してください。",
                ephemeral=True,
            )
            return

        await self._change_settings({"hour": hour})
        await interaction.response.send_message(
            f"誕生日の自動投稿時刻を {hour:02d}:00 に設定しました。",
            ephemeral=True,
        )

    async def _replace_birthdays(self, records):
        validated = [normalize(record) for record in records]
        # A mutation must not introduce duplicates, but preserved legacy groups
        # elsewhere in the list must not prevent management of another character.
        prior_counts, prior_dates = {}, {}
        for record in self.birthdays:
            cid = record['character_id']
            prior_counts[cid] = prior_counts.get(cid, 0) + 1
            prior_dates.setdefault(cid, set()).add((record['month'], record['day']))
        grouped = {}
        for record in validated:
            grouped.setdefault(record['character_id'], []).append(record)
        canonical = []
        for cid, group in grouped.items():
            dates = {(b['month'], b['day']) for b in group}
            if len(group) > 1 and (len(dates) != 1 or dates != prior_dates.get(cid)
                                  or len(group) > prior_counts.get(cid, 0)):
                raise ValueError("同じキャラクターIDが既に登録されています")
            canonical.append({**group[0], 'reported': any(b['reported'] for b in group)})
        previous = self.birthdays
        self.birthdays = canonical
        try:
            await asyncio.to_thread(self.save_birthdays)
        except BaseException:
            self.birthdays = previous
            raise

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="birthday_add", description="誕生日を1件追加します")
    async def birthday_add(self, interaction: discord.Interaction, character_id: str, name: str, month: int, day: int):
        await interaction.response.defer(ephemeral=True)
        async with self._data_lock:
            record = normalize(dict(character_id=character_id, name=name, month=month, day=day, reported=False))
            if any(b['character_id'] == record['character_id'] for b in self.birthdays):
                raise ValueError("同じキャラクターIDが既に登録されています")
            await self._replace_birthdays([*self.birthdays, record])
        await interaction.followup.send("誕生日を追加しました。", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="birthday_edit", description="キャラクターIDを指定して誕生日を編集します")
    async def birthday_edit(self, interaction: discord.Interaction, character_id: str, name: Optional[str] = None,
                            month: Optional[int] = None, day: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        async with self._data_lock:
            matches = [b for b in self.birthdays if b['character_id'] == character_id.strip()]
            if not matches or len({(b['month'], b['day']) for b in matches}) != 1:
                raise ValueError("一致する誕生日が1件ではありません。一括更新で整理してください")
            changes = {key: value for key, value in dict(name=name, month=month, day=day).items() if value is not None}
            original = matches[0]
            record = normalize({**original, **changes})
            if (record['month'], record['day']) != (original['month'], original['day']):
                record['reported'] = False
            else:
                record['reported'] = any(b.get('reported', False) for b in matches)
            # Old same-day duplicates describe one character, so edit them as one record.
            await self._replace_birthdays([b for b in self.birthdays if b not in matches] + [record])
        await interaction.followup.send("誕生日を編集しました。", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="birthday_delete", description="キャラクターIDを指定して誕生日を削除します（confirm:trueで確定）")
    async def birthday_delete(self, interaction: discord.Interaction, character_id: str, confirm: bool = False):
        await interaction.response.defer(ephemeral=True)
        async with self._data_lock:
            matches = [b for b in self.birthdays if b['character_id'] == character_id.strip()]
            if not matches:
                raise ValueError("指定したキャラクターIDは見つかりません")
            if not confirm:
                await interaction.followup.send(f"削除対象: #{character_id} の{len(matches)}件。confirm:trueで確定してください。", ephemeral=True)
                return
            await self._replace_birthdays([b for b in self.birthdays if b not in matches])
        await interaction.followup.send("誕生日を削除しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
