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
import tempfile
import config
import utils

import csv
import urllib.request
import io
from typing import Any, Dict, Optional, Tuple
from PIL import Image

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
    
    def __init__(self, bot: commands.Bot):
        """
        誕生日管理のコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
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
            await asyncio.to_thread(save_snapshot, self, "birthday", "settings")
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
        return now.hour == target_hour and now.minute == 0

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
            if self.settings.get("last_announced_date") == today_str:
                return

            announced = await self._announce_today_birthdays(now)
            if announced:
                await self._change_settings({"last_announced_date": today_str})
        except Exception as e:
            logger.error(f"Error in birthday_task: {e}")
            logger.error(traceback.format_exc())

    async def _announce_today_birthdays(self, now: datetime.datetime) -> bool:
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
            return False

        unique: Dict[Tuple[Optional[str], int, int], list] = {}
        for record in unreported_birthdays:
            key = (record.get("character_id"), record.get("month"), record.get("day"))
            unique.setdefault(key, []).append(record)

        announced_any = False
        for grouped_records in unique.values():
            if len(grouped_records) != 1:
                continue
            birthday_record = grouped_records[0]
            await self._announce_zircon_birthday(channel, birthday_record)
            birthday_record["reported"] = True
            announced_any = True

        if announced_any:
            await self.save_birthdays_async()

        return announced_any

    async def _announce_zircon_birthday(self, channel, birthday_data):
        """Zirconキャラクターの誕生日を発表"""
        character_id = birthday_data.get("character_id", "")
        name = birthday_data.get("name", "不明")
        month = birthday_data.get("month")
        day = birthday_data.get("day")
        
        # tempfileを使用して安全な一時ファイル管理
        temp_webp_path = None
        temp_png_path = None
        
        try:
            # 画像URLを取得（config.pyで一元管理）
            url = config.get_character_image_url(character_id)
            is_webp = url.endswith('.webp')
            
            # 画像取得
            if is_webp:
                # webp形式
                # 一時ファイル作成（自動削除は無効化、手動で削除）
                fd, temp_webp_path = tempfile.mkstemp(suffix='.webp', prefix=f'birthday_{character_id}_')
                os.close(fd)  # ファイルディスクリプタを閉じる
                urllib.request.urlretrieve(url, temp_webp_path)
                img = Image.open(temp_webp_path)
                img = img.convert('RGB')
                
                fd, temp_png_path = tempfile.mkstemp(suffix='.png', prefix=f'birthday_{character_id}_')
                os.close(fd)
                img.save(temp_png_path, 'PNG')
                img.close()
            else:
                # png形式
                fd, temp_png_path = tempfile.mkstemp(suffix='.png', prefix=f'birthday_{character_id}_')
                os.close(fd)
                urllib.request.urlretrieve(url, temp_png_path)
            
            # Embed作成
            embed = discord.Embed(
                title="🎉 誕生日おめでとう！ 🎉",
                description=f"**{name}** の誕生日です！",
                color=discord.Color.blue()
            )
            embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=False)
            embed.add_field(name="キャラクター番号", value=character_id, inline=False)
            embed.set_footer(text=f"Zirconキャラクター")
            
            # 画像をアップロードしてサムネイルに設定
            with open(temp_png_path, 'rb') as f:
                file = discord.File(f, filename=f"{character_id}.png")
                embed.set_thumbnail(url=f"attachment://{character_id}.png")
                await channel.send(embed=embed, file=file)
            
        except Exception as e:
            logger.error(f"Error in _announce_zircon_birthday: {e}")
            logger.error(traceback.format_exc())
        finally:
            # 一時ファイルの確実なクリーンアップ
            for path in [temp_webp_path, temp_png_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as cleanup_error:
                        logger.warning(f"一時ファイルの削除に失敗: {path}, {cleanup_error}")

    def load_birthdays(self):
        """誕生日データを読み込みます（リスト形式）。dataフォルダがなければ作成。"""
        # 環境に依存しないパス構築
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        data_dir = os.path.abspath(data_dir)
        birthdays_path = os.path.join(data_dir, 'birthdays.json')
        
        os.makedirs(data_dir, exist_ok=True)
        try:
            if not os.path.exists(birthdays_path):
                utils.atomic_write_json(birthdays_path, [])
            with open(birthdays_path, "r", encoding="utf-8") as f:
                self.birthdays = json.load(f)
                if not isinstance(self.birthdays, list):
                    self.birthdays = []
        except Exception as e:
            logger.error(f"Error loading birthdays: {e}")
            logger.error(traceback.format_exc())
            self.birthdays = []

    def save_birthdays(self):
        """誕生日データを保存します（リスト形式）。dataフォルダがなければ作成。

        Note: 非同期コンテキストから呼び出す場合はsave_birthdays_async()を使用してください。
        """
        # 環境に依存しないパス構築
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        data_dir = os.path.abspath(data_dir)
        birthdays_path = os.path.join(data_dir, 'birthdays.json')

        os.makedirs(data_dir, exist_ok=True)
        utils.atomic_write_json(birthdays_path, self.birthdays)

    async def save_birthdays_async(self):
        """誕生日データを非同期で保存します（ロック付き）。"""
        async with self._data_lock:
            await asyncio.to_thread(self.save_birthdays)

    @app_commands.command(name="birthday", description="誕生日の確認（一覧表示または検索）")
    @app_commands.describe(id_or_name="検索したいキャラクターIDまたは名前（指定しない場合は一覧表示）")
    async def birthday(self, interaction: discord.Interaction, id_or_name: Optional[str] = None):
        """
        引数なしなら一覧表示、引数ありなら検索を行います。
        """
        try:
            # 引数がある場合は検索モード
            if id_or_name:
                await self._handle_search(interaction, id_or_name)
            else:
                # 引数がない場合は一覧表示モード
                await self._handle_list(interaction)
        except Exception as e:
            logger.error(f"Error in birthday command: {e}", exc_info=True)
            await interaction.response.send_message(
                "エラーが発生しました。", ephemeral=True
            )

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


    @app_commands.command(name="birthday_update", description="ファイルから誕生日データを一括更新します（全置換）")
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
                text_data = content.decode("utf-8-sig")
                f = io.StringIO(text_data)
                reader = csv.DictReader(f)
                # ヘッダーチェック（簡易）
                if not reader.fieldnames or "character_id" not in reader.fieldnames:
                    # ヘッダーなしとみなして位置でパースを試みるフォールバックも考えられるが、
                    # 安全のためヘッダー必須とするか、ユーザーガイドに従う。
                    # ここでは前のインポート機能に合わせて柔軟に対応する
                    f.seek(0)
                    csv_data = list(csv.reader(f))
                    # ヘッダー行判定: 最初の行の要素が数字でなければヘッダーとみなす
                    start_idx = 0
                    if csv_data and not csv_data[0][0].isdigit():
                        start_idx = 1
                    
                    for row in csv_data[start_idx:]:
                        if len(row) < 3: continue
                        # format: id, name, month, day (name is optional in old format but let's require it or fetch logic? 
                        # User wants BULK REPLACEMENT, implying full data provided.
                        # Let's assume standard format: id, name, month, day
                        # If name missing, use placeholder?
                        # Previous import used web scraping. Bulk update should ideally be fast.
                        # For now, expect: id, name, month, day.
                        # If 3 cols: id, month, day (scrape name?) -> Scraping 100s of items is slow.
                        # Let's require Name in CSV for bulk update to be strict.
                        if len(row) >= 4:
                            new_birthdays.append({
                                "character_id": row[0],
                                "name": row[1],
                                "month": int(row[2]),
                                "day": int(row[3]),
                                "reported": False
                            })
                        elif len(row) == 3:
                             # 互換性: id, month, day -> name="不明"
                             new_birthdays.append({
                                "character_id": row[0],
                                "name": "不明",
                                "month": int(row[1]),
                                "day": int(row[2]),
                                "reported": False
                            })
            else:
                await interaction.followup.send("対応していないファイル形式です (.json, .csv)", ephemeral=True)
                return

            if not new_birthdays:
                await interaction.followup.send("有効な誕生日データが見つかりませんでした。", ephemeral=True)
                return

            # バリデーションと整形
            validated = []
            for b in new_birthdays:
                try:
                    m = int(b.get("month", 0))
                    d = int(b.get("day", 0))
                    if 1 <= m <= 12 and 1 <= d <= 31:
                         validated.append({
                             "character_id": str(b.get("character_id", "")),
                             "name": str(b.get("name", "不明")),
                             "month": m,
                             "day": d,
                             "reported": False
                         })
                except:
                    continue
            
            async with self._data_lock:
                previous = self.birthdays
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot)) 