"""
誕生日管理のコグ
このモジュールは、誕生日の管理機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import logging
import traceback
import datetime
import os
import config
import permissions
import csv
import urllib.request
import io
from typing import Any, Dict, Optional, Tuple
from PIL import Image
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# ロギングの設定
logger = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "Asia/Tokyo"


def _get_timezone() -> datetime.tzinfo:
    if ZoneInfo is not None:
        try:
            return ZoneInfo(_DEFAULT_TIMEZONE)
        except Exception:
            logger.warning("ZoneInfoで %s を取得できません。UTC+09:00 を使用します", _DEFAULT_TIMEZONE)
    return datetime.timezone(datetime.timedelta(hours=9))

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
    """
    誕生日管理のコグ
    誕生日の管理機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        誕生日管理のコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
        self.tz = _get_timezone()
        self.birthdays = []
        self.defaults: Dict[str, Any] = self._feature_defaults()
        self.settings: Dict[str, Any] = {}
        self.birthday_task_started = False
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
        if isinstance(value, bool):
            return value
        if value is None:
            return fallback
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
            return fallback
        try:
            return bool(value)
        except Exception:
            return fallback

    @staticmethod
    def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
        try:
            if value is None:
                return fallback
            number = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(minimum, min(maximum, number))

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
        try:
            config.set_runtime_section("birthday", self.settings)
        except Exception as exc:
            logger.error("誕生日設定の保存に失敗しました: %s", exc, exc_info=True)

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

    def _get_member(self, interaction: discord.Interaction) -> Optional[discord.Member]:
        if isinstance(interaction.user, discord.Member):
            return interaction.user
        if interaction.guild:
            return interaction.guild.get_member(interaction.user.id)
        return None

    def _is_operator(self, interaction: discord.Interaction) -> bool:
        return permissions.is_operator_member(self._get_member(interaction))

    async def _ensure_operator(self, interaction: discord.Interaction) -> bool:
        if self._is_operator(interaction):
            return True
        await interaction.response.send_message(
            "このコマンドは運営のみ実行できます。",
            ephemeral=True
        )
        return False

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
            self._refresh_daily_flags(now)

            if not self.settings.get("enabled", True):
                return

            if not self._is_scheduled_time(now):
                return

            today_str = now.date().isoformat()
            if self.settings.get("last_announced_date") == today_str:
                return

            announced = await self._announce_today_birthdays(now)
            if announced:
                self.settings["last_announced_date"] = today_str
                self._persist_settings()
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
            self.save_birthdays()

        return announced_any

    async def _announce_zircon_birthday(self, channel, birthday_data):
        """Zirconキャラクターの誕生日を発表"""
        character_id = birthday_data.get("character_id", "")
        name = birthday_data.get("name", "不明")
        month = birthday_data.get("month")
        day = birthday_data.get("day")
        
        try:
            # 画像取得
            if character_id.isdigit() and int(character_id) <= 1000:
                # webp形式
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.webp"
                temp_path = f"temp_{character_id}.webp"
                urllib.request.urlretrieve(url, temp_path)
                img = Image.open(temp_path)
                img = img.convert('RGB')
                png_path = f"temp_{character_id}.png"
                img.save(png_path, 'PNG')
                os.remove(temp_path)
            else:
                # png形式
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.png"
                png_path = f"temp_{character_id}.png"
                urllib.request.urlretrieve(url, png_path)
            
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
            with open(png_path, 'rb') as f:
                file = discord.File(f, filename=f"{character_id}.png")
                embed.set_thumbnail(url=f"attachment://{character_id}.png")
                await channel.send(embed=embed, file=file)
            
            # 一時ファイル削除
            os.remove(png_path)
            
        except Exception as e:
            logger.error(f"Error in _announce_zircon_birthday: {e}")
            logger.error(traceback.format_exc())

    def load_birthdays(self):
        """誕生日データを読み込みます（リスト形式）。dataフォルダがなければ作成。"""
        os.makedirs("data", exist_ok=True)
        try:
            if not os.path.exists("data/birthdays.json"):
                with open("data/birthdays.json", "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
            with open("data/birthdays.json", "r", encoding="utf-8") as f:
                self.birthdays = json.load(f)
                if not isinstance(self.birthdays, list):
                    self.birthdays = []
        except Exception as e:
            logger.error(f"Error loading birthdays: {e}")
            logger.error(traceback.format_exc())
            self.birthdays = []

    def save_birthdays(self):
        """誕生日データを保存します（リスト形式）。dataフォルダがなければ作成。"""
        os.makedirs("data", exist_ok=True)
        try:
            with open("data/birthdays.json", "w", encoding="utf-8") as f:
                json.dump(self.birthdays, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving birthdays: {e}")
            logger.error(traceback.format_exc())

    @app_commands.command(
        name="birthday_delete",
        description="登録されている誕生日を削除します"
    )
    @app_commands.describe(
        id="削除したいキャラクターID"
    )
    async def birthday_delete(self, interaction: discord.Interaction, id: str):
        """
        キャラクターIDで誕生日を削除します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            id (str): 削除したいキャラクターID
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthday_delete'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # 該当するキャラクターを検索
            candidates = [b for b in self.birthdays 
                         if b.get("character_id", "") == id]
            if not candidates:
                await interaction.response.send_message(
                    f"キャラクターID `{id}` の誕生日は登録されていません。",
                    ephemeral=True
                )
                return
            
            # 該当するキャラクターの誕生日を削除
            removed = candidates[0]
            self.birthdays.remove(removed)
            self.save_birthdays()
            char_id = removed.get("character_id", "???")
            name = removed.get("name", "不明")
            await interaction.response.send_message(
                f"{name} (#{char_id}) {removed['month']}月{removed['day']}日 の誕生日を削除しました。",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in birthday_delete: {e}", exc_info=True)
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="birthday_add",
        description="Zirconキャラクターの誕生日を登録します"
    )
    @app_commands.describe(
        id="Zirconキャラクター番号",
        month="月（1-12）",
        date="日（1-31）"
    )
    async def birthday_add(self, interaction: discord.Interaction, id: str, month: int, date: int):
        """
        Zirconキャラクターの誕生日を登録します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            id (str): キャラクター番号
            month (int): 月
            date (int): 日
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthday_add'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            # 日付のバリデーション
            if not (1 <= month <= 12 and 1 <= date <= 31):
                await interaction.followup.send(
                    "無効な日付です。月は1-12、日は1-31の範囲で指定してください。",
                    ephemeral=True
                )
                return

            # キャラクター名を取得
            driver = None
            try:
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--log-level=3')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
                
                driver = webdriver.Chrome(options=chrome_options)
                driver.get(f"https://zircon.konami.net/nft/character/{id}")
                import time
                time.sleep(2)
                html = driver.page_source.encode("utf-8")
                soup = BeautifulSoup(html, "html.parser")
                name_elem = soup.select_one("#root > main > div > section.status > div > dl:nth-of-type(1) > dd > p")
                
                if not name_elem or not name_elem.text.strip():
                    char_name = "<不明>"
                else:
                    char_name = name_elem.text.strip()
                
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

            # データ追加
            self.birthdays.append({
                "character_id": id,
                "name": char_name,
                "month": month,
                "day": date,
                "reported": False
            })
            
            # 誕生日順にソート
            self.birthdays.sort(key=lambda x: (x["month"], x["day"]))
            self.save_birthdays()

            await interaction.followup.send(
                f"誕生日を登録しました：{char_name} (#{id}) {month}月{date}日",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in birthday_add: {e}", exc_info=True)
            logger.error(traceback.format_exc())
            await interaction.followup.send(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="birthday_edit",
        description="登録済みの誕生日情報を編集します"
    )
    @app_commands.describe(
        id="編集したいキャラクターID",
        month="新しい月（1-12）",
        date="新しい日（1-31）",
        name="新しいキャラクター名（省略可）"
    )
    async def birthday_edit(
        self,
        interaction: discord.Interaction,
        id: str,
        month: Optional[int] = None,
        date: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        """登録済みの誕生日エントリを更新します。

        Args:
            interaction: Discordインタラクションのコンテキスト。
            id: 編集対象のキャラクターID。
            month: 新しい誕生日の月。省略時は変更しません。
            date: 新しい誕生日の日。省略時は変更しません。
            name: 新しいキャラクター名。省略時は変更しません。
        """
        if not permissions.can_run_command(interaction, 'birthday_edit'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        has_update_target = any(v is not None for v in (month, date, name))
        if not has_update_target:
            await interaction.response.send_message(
                "更新する項目を最低1つ指定してください。",
                ephemeral=True
            )
            return

        if month is not None and not (1 <= month <= 12):
            await interaction.response.send_message(
                "無効な月です。1-12の範囲で指定してください。",
                ephemeral=True
            )
            return

        if date is not None and not (1 <= date <= 31):
            await interaction.response.send_message(
                "無効な日です。1-31の範囲で指定してください。",
                ephemeral=True
            )
            return

        target = next((b for b in self.birthdays if b.get("character_id") == id), None)
        if target is None:
            await interaction.response.send_message(
                f"キャラクターID `{id}` の誕生日は登録されていません。",
                ephemeral=True
            )
            return

        changes = []
        requires_sort = False
        reset_reported = False

        if month is not None and month != target.get("month"):
            target["month"] = month
            changes.append(f"月を {month} に更新")
            requires_sort = True
            reset_reported = True

        if date is not None and date != target.get("day"):
            target["day"] = date
            changes.append(f"日を {date} に更新")
            requires_sort = True
            reset_reported = True

        if name is not None:
            trimmed_name = name.strip()
            if not trimmed_name:
                await interaction.response.send_message(
                    "名前が空白です。正しい名前を指定してください。",
                    ephemeral=True
                )
                return
            if trimmed_name != target.get("name"):
                target["name"] = trimmed_name
                changes.append("名前を更新")

        if not changes:
            await interaction.response.send_message(
                "指定された値は既存の登録内容と同じです。変更は行われませんでした。",
                ephemeral=True
            )
            return

        if reset_reported:
            target["reported"] = False

        if requires_sort:
            self.birthdays.sort(key=lambda x: (x["month"], x["day"]))

        self.save_birthdays()

        await interaction.response.send_message(
            f"{target.get('name', '不明')} (#{target.get('character_id', '???')}) の誕生日情報を更新しました：" + ", ".join(changes),
            ephemeral=True
        )

    @app_commands.command(
        name="birthday_list",
        description="登録されている誕生日の一覧を表示します"
    )
    async def birthday_list(self, interaction: discord.Interaction):
        """
        登録されている誕生日の一覧を表示します。
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthday_list'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            if not self.birthdays:
                await interaction.response.send_message(
                    "登録されている誕生日はありません。",
                    ephemeral=True
                )
                return

            # 誕生日順にソート（データは既にソート済みだが念のため）
            sorted_birthdays = sorted(
                self.birthdays,
                key=lambda x: (x["month"], x["day"])
            )

            # ページネーション用のビューを作成
            if len(sorted_birthdays) > 8:
                view = BirthdayPaginationView(sorted_birthdays)
                embed = view.create_embed()
                await interaction.response.send_message(embed=embed, view=view)
            else:
                # 8件以下の場合はページネーションなし
                embed = discord.Embed(
                    title="🎂 誕生日一覧",
                    description="登録されているZirconキャラクターの誕生日一覧です",
                    color=discord.Color.pink()
                )
                
                lines = []
                for b in sorted_birthdays:
                    char_id = b.get("character_id", "???")
                    name = b.get("name", "不明")
                    month = b.get("month", 0)
                    day = b.get("day", 0)
                    lines.append(f"{char_id}, {name} : birthday({month:02d}/{day:02d})")
                
                embed.add_field(
                    name=f"全 {len(sorted_birthdays)} 件",
                    value="\n".join(lines),
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in birthday_list: {e}", exc_info=True)
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="birthday_search",
        description="特定のキャラクターの誕生日を検索します"
    )
    @app_commands.describe(
        id_or_name="検索したいキャラクターIDまたは名前"
    )
    async def birthday_search(self, interaction: discord.Interaction, id_or_name: str):
        """
        キャラクターIDまたは名前で誕生日を検索します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            id_or_name (str): キャラクターIDまたは名前
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthday_search'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # IDまたは名前で検索（部分一致）
            candidates = [b for b in self.birthdays 
                         if id_or_name in b.get("character_id", "") or id_or_name.lower() in b.get("name", "").lower()]
            
            if not candidates:
                await interaction.response.send_message(
                    f"`{id_or_name}` に一致するキャラクターの誕生日は登録されていません。",
                    ephemeral=True
                )
                return
            
            # 1件の場合は詳細表示
            if len(candidates) == 1:
                result = candidates[0]
                char_id = result.get("character_id", "???")
                char_name = result.get("name", "不明")
                month = result.get("month", 0)
                day = result.get("day", 0)
                
                embed = discord.Embed(
                    title="🎂 誕生日情報",
                    color=discord.Color.pink()
                )
                embed.add_field(name="キャラクターID", value=char_id, inline=True)
                embed.add_field(name="名前", value=char_name, inline=True)
                embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=True)
                
                await interaction.response.send_message(embed=embed)
            else:
                # 複数件の場合は一覧表示
                embed = discord.Embed(
                    title=f"🎂 検索結果: {len(candidates)}件",
                    description=f"`{id_or_name}` で検索した結果",
                    color=discord.Color.pink()
                )
                
                lines = []
                for b in candidates[:10]:  # 最大10件まで表示
                    char_id = b.get("character_id", "???")
                    name = b.get("name", "不明")
                    month = b.get("month", 0)
                    day = b.get("day", 0)
                    lines.append(f"**{name}** (#{char_id}) - {month}月{day}日")
                
                embed.add_field(name="該当キャラクター", value="\n".join(lines), inline=False)
                
                if len(candidates) > 10:
                    embed.set_footer(text=f"※ 10件以上該当しました。さらに絞り込んでください。")
                
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in birthday_search: {e}", exc_info=True)
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="birthday_toggle",
        description="誕生日の自動投稿をON/OFFします"
    )
    @app_commands.describe(enabled="true で有効化、false で無効化")
    async def birthday_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        """誕生日の自動投稿機能を運営が切り替えるコマンド."""
        if not await self._ensure_operator(interaction):
            return

        self.settings["enabled"] = bool(enabled)
        if enabled:
            # 再有効化と同時に当日の投稿状況をリセット
            self.settings["last_announced_date"] = None
        self._persist_settings()
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
        """誕生日の自動投稿時刻を設定する運営向けコマンド."""
        if not await self._ensure_operator(interaction):
            return

        if hour < 0 or hour > 23:
            await interaction.response.send_message(
                "時刻は0-23の範囲で指定してください。",
                ephemeral=True,
            )
            return

        self.settings["hour"] = hour
        self._persist_settings()
        await interaction.response.send_message(
            f"誕生日の自動投稿時刻を {hour:02d}:00 に設定しました。",
            ephemeral=True,
        )

    @app_commands.command(
        name="birthday_import",
        description="CSVファイルから誕生日を一括登録します"
    )
    @app_commands.describe(
        file="character_id,month,day のCSVファイルを添付してください"
    )
    async def birthday_import(self, interaction: discord.Interaction, file: discord.Attachment):
        """
        CSVをインポートして誕生日を一括登録します。

        フォーマット: character_id,month,day
        - character_id: Zirconキャラクター番号
        - month: 1-12
        - day: 1-31
        既存の character_id と一致するレコードはスキップします。
        キャラクター名は自動取得されます。
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthday_import'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # ファイル読み込み
            data = await file.read()
            text = data.decode('utf-8-sig')  # BOM対策
            reader = csv.reader(io.StringIO(text))

            # 既存のid集合
            existing_ids = set()
            for b in self.birthdays:
                v = b.get('character_id')
                if isinstance(v, str):
                    existing_ids.add(v)

            added = 0
            skipped_dup = 0
            invalid = 0
            total = 0
            
            # Selenium初期化
            driver = None
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            for idx, row in enumerate(reader, start=1):
                # ヘッダ行っぽい場合はスキップ
                if idx == 1 and row and str(row[0]).strip().lower() in {"character_id", "キャラクター番号", "番号"}:
                    continue
                total += 1

                if len(row) < 3:
                    invalid += 1
                    continue

                try:
                    character_id = str(row[0]).strip()
                    month = int(str(row[1]).strip())
                    day = int(str(row[2]).strip())
                except Exception:
                    invalid += 1
                    continue

                # バリデーション
                if not character_id:
                    invalid += 1
                    continue
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    invalid += 1
                    continue

                # 重複チェック（character_id一致）
                if character_id in existing_ids:
                    skipped_dup += 1
                    continue

                # キャラクター名を取得
                try:
                    if not driver:
                        driver = webdriver.Chrome(options=chrome_options)
                    
                    driver.get(f"https://zircon.konami.net/nft/character/{character_id}")
                    import time
                    time.sleep(2)
                    html = driver.page_source.encode("utf-8")
                    soup = BeautifulSoup(html, "html.parser")
                    name_elem = soup.select_one("#root > main > div > section.status > div > dl:nth-of-type(1) > dd > p")
                    
                    if not name_elem or not name_elem.text.strip():
                        char_name = "<不明>"
                    else:
                        char_name = name_elem.text.strip()
                    
                    # 追加
                    self.birthdays.append({
                        "character_id": character_id,
                        "name": char_name,
                        "month": month,
                        "day": day,
                        "reported": False
                    })
                    existing_ids.add(character_id)
                    added += 1
                    
                except Exception as e:
                    logger.error(f"キャラクター #{character_id} の取得に失敗: {e}")
                    invalid += 1
                    continue

            # Selenium終了
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            # 誕生日順にソート＆保存
            if added > 0:
                self.birthdays.sort(key=lambda x: (x["month"], x["day"]))
                self.save_birthdays()

            await interaction.followup.send(
                f"CSVの読み込みが完了しました。\n合計行数: {total}\n追加: {added}\n重複スキップ: {skipped_dup}\n不正行: {invalid}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in import_birthdays: {e}")
            logger.error(traceback.format_exc())
            await interaction.followup.send(
                "CSVの読み込みに失敗しました。ファイル形式と内容をご確認ください。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Birthday(bot))
        logger.info("Birthday cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Birthday cog: {e}")
        logger.error(traceback.format_exc())
        raise 