"""Quote management and scheduled posting cog."""

from __future__ import annotations

import asyncio
import csv
import datetime
import io
import json
import logging
import os
import random
import uuid
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config


try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover - fallback for environments without zoneinfo
    ZoneInfo = None  # type: ignore

logger = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "Asia/Tokyo"
# 環境に依存しないパス構築
_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
_DATA_DIR = os.path.abspath(_DATA_DIR)
_DEFAULT_DATA_PATH = os.path.join(_DATA_DIR, "quotes.json")
_ITEMS_PER_PAGE = 10


def _get_timezone() -> datetime.tzinfo:
    """Return the timezone used for scheduling."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(_DEFAULT_TIMEZONE)
        except Exception:  # pragma: no cover - ZoneInfo may raise if timezone absent
            logger.warning("ZoneInfoで %s を取得できません。UTC+09:00 を使用します", _DEFAULT_TIMEZONE)
    return datetime.timezone(datetime.timedelta(hours=9))


def _now(tz: datetime.tzinfo) -> datetime.datetime:
    """Return the current time in the configured timezone."""
    return datetime.datetime.now(tz)


class Quotes(commands.Cog):
    """Manage quotes and automatically post them on a schedule."""

    def __init__(self, bot: commands.Bot, data_path: Optional[str] = None) -> None:
        self.bot = bot
        self.tz = _get_timezone()
        self.data_path = data_path or _DEFAULT_DATA_PATH
        self._data_lock = asyncio.Lock()
        self.quotes: List[Dict] = []
        self.settings: Dict[str, Any] = {}
        self._task_started = False
        self._load_data()
        self.settings = self._load_settings()
        logger.info("Quotes が初期化されました")

    @property
    def _default_settings(self) -> Dict[str, Any]:
        """Return default settings derived from config."""
        feature_settings = config.get_feature_settings("quotes")
        return {
            "enabled": self._coerce_bool(feature_settings.get("default_enabled"), True),
            "days": self._coerce_int(feature_settings.get("default_days"), 1, minimum=1),
            "hour": self._coerce_int(feature_settings.get("default_hour"), 9, minimum=0, maximum=23),
            "minute": self._coerce_int(feature_settings.get("default_minute"), 0, minimum=0, maximum=59),
            "last_posted_at": None,
            "last_posted_quote_id": None,
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
    def _coerce_int(value: Any, fallback: int, *, minimum: int, maximum: Optional[int] = None) -> int:
        try:
            if value is None:
                raise TypeError
            number = int(value)
        except (TypeError, ValueError):
            number = fallback
        number = max(minimum, number)
        if maximum is not None:
            number = min(maximum, number)
        return number

    def _normalize_settings(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self._default_settings
        return {
            "enabled": self._coerce_bool(raw.get("enabled"), defaults["enabled"]),
            "days": self._coerce_int(raw.get("days"), defaults["days"], minimum=1),
            "hour": self._coerce_int(raw.get("hour"), defaults["hour"], minimum=0, maximum=23),
            "minute": self._coerce_int(raw.get("minute"), defaults["minute"], minimum=0, maximum=59),
            "last_posted_at": raw.get("last_posted_at") if isinstance(raw.get("last_posted_at"), str) else None,
            "last_posted_quote_id": raw.get("last_posted_quote_id") if raw.get("last_posted_quote_id") else None,
        }

    def _load_settings(self) -> Dict[str, Any]:
        stored = config.get_runtime_section("quotes")
        normalized = self._normalize_settings(stored)
        self._persist_settings(normalized)
        return normalized

    def _persist_settings(self, values: Optional[Dict[str, Any]] = None) -> None:
        payload = values if values is not None else self.settings
        try:
            config.set_runtime_section("quotes", payload)
        except Exception as exc:
            logger.error("名言設定の保存に失敗しました: %s", exc, exc_info=True)

    def _get_member(self, interaction: discord.Interaction) -> Optional[discord.Member]:
        if isinstance(interaction.user, discord.Member):
            return interaction.user
        if interaction.guild is not None:
            return interaction.guild.get_member(interaction.user.id)
        return None



    def _ensure_data_dir(self) -> None:
        os.makedirs(os.path.dirname(self.data_path) or ".", exist_ok=True)

    def _load_data(self) -> None:
        """Load quotes from disk."""
        self._ensure_data_dir()

        if not os.path.exists(self.data_path):
            self.quotes = []
            self._save_data()
            return

        try:
            with open(self.data_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            logger.error("quotes.json の読み込みに失敗しました: %s", exc)
            payload = {}
        except FileNotFoundError:
            payload = {}

        if isinstance(payload, list):
            # 旧形式との互換性維持
            self.quotes = payload
            self._save_data()
            return

        if isinstance(payload, dict):
            self.quotes = payload.get("quotes", [])
        else:
            self.quotes = []

        if not isinstance(self.quotes, list):
            self.quotes = []

        for quote in self.quotes:
            if not isinstance(quote, dict):
                continue
            quote.setdefault("speaker", "")
            quote.setdefault("text", "")
            quote.setdefault("id", "")
            quote.setdefault("character_id", None)

    def _save_data(self) -> None:
        """Persist quotes to disk."""
        self._ensure_data_dir()
        payload = {
            "quotes": self.quotes,
        }
        with open(self.data_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime.datetime]:
        if not value:
            return None
        try:
            parsed = datetime.datetime.fromisoformat(value)
        except ValueError:
            logger.warning("日時文字列の解析に失敗しました: %s", value)
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=self.tz)
        return parsed.astimezone(self.tz)

    def _compute_next_run(self, last_posted: Optional[datetime.datetime]) -> datetime.datetime:
        days = max(1, int(self.settings.get("days", 1)))
        hour = max(0, min(23, int(self.settings.get("hour", 9))))
        minute = max(0, min(59, int(self.settings.get("minute", 0))))
        now = _now(self.tz)
        scheduled_time = datetime.time(hour=hour, minute=minute, tzinfo=self.tz)

        if last_posted is None:
            candidate = datetime.datetime.combine(now.date(), scheduled_time)
            if now >= candidate:
                return now
            return candidate

        next_date = last_posted.date() + datetime.timedelta(days=days)
        next_run = datetime.datetime.combine(next_date, scheduled_time)
        if next_run <= now:
            return now
        return next_run

    def _build_thumbnail_url(self, character_id: str) -> str:
        cid = character_id.strip()
        if not cid:
            return ""
        if len(cid) <= 4:
            return f"https://storage.googleapis.com/prd-azz-image/pfp_{cid}.webp"
        return f"https://storage.googleapis.com/prd-azz-image/pfp_{cid}.png"

    def _select_quote(self) -> Optional[Dict]:
        if not self.quotes:
            return None
        last_id = self.settings.get("last_posted_quote_id")
        candidates = [q for q in self.quotes if q.get("id") != last_id]
        if not candidates:
            candidates = self.quotes
        return random.choice(candidates)

    def _build_embed(self, quote: Dict) -> discord.Embed:
        embed = discord.Embed(
            title=quote.get("speaker", "不明な発言者"),
            description=quote.get("text", ""),
            color=discord.Color.green(),
        )
        character_id = quote.get("character_id")
        quote_id = quote.get("id", "")
        if character_id:
            embed.url = f"https://zircon.konami.net/nft/character/{character_id}"
            embed.set_thumbnail(url=self._build_thumbnail_url(str(character_id)))
            footer = f"#{character_id} · quote_id:{quote_id}"
        else:
            footer = f"quote_id:{quote_id}"
        embed.set_footer(text=footer)
        embed.timestamp = _now(self.tz)
        return embed

    async def _maybe_post_quote(self) -> None:
        channel_id = config.get_quote_channel_id()
        if not channel_id:
            return
        async with self._data_lock:
            if not self.settings.get("enabled", True):
                return
            if not self.quotes:
                return
            last_posted = self._parse_datetime(self.settings.get("last_posted_at"))
            next_run = self._compute_next_run(last_posted)
        now = _now(self.tz)
        if now < next_run:
            return

        quote = self._select_quote()
        if not quote:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)  # type: ignore[assignment]
            except Exception as exc:
                logger.error("名言投稿チャンネルの取得に失敗しました: %s", exc)
                return

        embed = self._build_embed(quote)
        try:
            await channel.send(embed=embed)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error("名言の自動投稿に失敗しました: %s", exc)
            return

        async with self._data_lock:
            self.settings["last_posted_at"] = _now(self.tz).isoformat()
            self.settings["last_posted_quote_id"] = quote.get("id")
            self._persist_settings()

    @tasks.loop(minutes=1)
    async def quote_posting_loop(self) -> None:
        try:
            await self._maybe_post_quote()
        except Exception as exc:  # pragma: no cover - safety net
            logger.error("名言定期投稿ループでエラー: %s", exc, exc_info=True)

    @quote_posting_loop.before_loop
    async def before_quote_posting_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._task_started:
            self.quote_posting_loop.start()
            self._task_started = True

    # ===== Utility helpers =====

    def _format_quote_line(self, quote: Dict) -> str:
        character_id = quote.get("character_id")
        prefix = f"#{character_id} " if character_id else ""
        text = quote.get("text", "").strip().replace("\n", " ")
        if len(text) > 80:
            text = text[:77] + "..."
        return f"{quote.get('speaker', '不明')} » {prefix}{text}"

    # ===== Slash commands =====

    @app_commands.command(name="quote", description="名言の確認（一覧表示または検索）")
    @app_commands.describe(keyword="検索したいキーワード（指定しない場合は一覧表示）")
    async def quote(self, interaction: discord.Interaction, keyword: Optional[str] = None):
        """引数なしなら一覧表示、ありなら検索。"""
        if keyword:
            await self._handle_search(interaction, keyword)
        else:
            await self._handle_list(interaction)

    async def _handle_list(self, interaction: discord.Interaction, page: int = 1):
        # List logic handling
        total = len(self.quotes)
        if total == 0:
            await interaction.response.send_message("名言はまだ登録されていません。", ephemeral=True)
            return

        # Simple random 10 or latest 10? The previous implementation had pagination.
        # Let's support 10 items for now or re-implement pagination logic if crucial.
        # User asked to consolidate commands.
        # For simple consolidation, let's show first 10 items or basic pagination if we want to be fancy.
        # Given the "list" command had page arg, we can support pagination via buttons if we really wanted to,
        # but to keep it simple and within the "single command" paradigm without complex optional args for pages:
        # Just show 1-10.
        
        embed = discord.Embed(
            title="📝 名言一覧",
            description=f"登録数: {total} 件",
            color=discord.Color.blue(),
        )
        for quote in self.quotes[:_ITEMS_PER_PAGE]:
            quote_id = quote.get("id", "")
            embed.add_field(
                name=f"{quote.get('speaker', '不明')} (ID: {quote_id})",
                value=self._format_quote_line(quote),
                inline=False,
            )
        
        if total > _ITEMS_PER_PAGE:
            embed.set_footer(text=f"※ 全 {total} 件中、先頭 {_ITEMS_PER_PAGE} 件を表示しています。絞り込むにはキーワードを指定してください。")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_search(self, interaction: discord.Interaction, keyword: str):
        keyword = keyword.strip().lower()
        matches = [
            q for q in self.quotes
            if keyword in q.get("speaker", "").lower() or keyword in q.get("text", "").lower()
        ]
        if not matches:
            await interaction.response.send_message("該当する名言は見つかりませんでした。", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🔍 検索結果 ({len(matches)}件)",
            color=discord.Color.teal(),
        )
        for quote in matches[:_ITEMS_PER_PAGE]:
            quote_id = quote.get("id", "")
            embed.add_field(
                name=f"{quote.get('speaker', '不明')} (ID: {quote_id})",
                value=self._format_quote_line(quote),
                inline=False,
            )
        if len(matches) > _ITEMS_PER_PAGE:
             embed.set_footer(text=f"先頭 {_ITEMS_PER_PAGE} 件のみ表示。残り {len(matches) - _ITEMS_PER_PAGE} 件はキーワードをより詳細にしてください。")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(name="quote_update", description="ファイルから名言データを一括更新します（全置換）")
    @app_commands.describe(file="更新用ファイル（CSV/JSON）")
    async def quote_update(self, interaction: discord.Interaction, file: discord.Attachment):
        """CSVファイルから名言を一括更新（全置換）します。"""

        await interaction.response.defer(ephemeral=True)
        try:
            content = await file.read()
            filename = file.filename.lower()
            new_quotes = []

            now_iso = _now(self.tz).isoformat()
            
            if filename.endswith(".json"):
                 data = json.loads(content.decode("utf-8"))
                 if isinstance(data, list):
                     for item in data:
                        new_quotes.append({
                            "id": str(uuid.uuid4()),
                            "speaker": item.get("speaker", "不明"),
                            "text": item.get("text", ""),
                            "character_id": item.get("character_id"),
                            "created_by": interaction.user.id,
                            "created_at": now_iso,
                            "updated_at": now_iso
                        })
                 else:
                     await interaction.followup.send("JSONはリスト形式である必要があります。", ephemeral=True)
                     return

            elif filename.endswith(".csv"):
                text_data = content.decode("utf-8-sig")
                f = io.StringIO(text_data)
                reader = csv.DictReader(f)
                
                # Check headers or fallback to positional
                fieldnames = [fn.lower() for fn in (reader.fieldnames or [])]
                if "speaker" in fieldnames and "text" in fieldnames:
                    # DictReader usage
                    f.seek(0)
                    reader = csv.DictReader(f) # reset
                    for row in reader:
                        # Normalize keys
                        row_lower = {k.lower(): v for k, v in row.items()}
                        new_quotes.append({
                            "id": str(uuid.uuid4()),
                            "speaker": row_lower.get("speaker", "不明"),
                            "text": row_lower.get("text", ""),
                            "character_id": row_lower.get("character_id"),
                            "created_by": interaction.user.id,
                            "created_at": now_iso,
                            "updated_at": now_iso
                        })
                else:
                    # Positional fallback
                    f.seek(0)
                    reader_list = list(csv.reader(f))
                    for row in reader_list:
                         if not row: continue
                         if len(row) >= 2:
                             new_quotes.append({
                                "id": str(uuid.uuid4()),
                                "speaker": row[0],
                                "text": row[1],
                                "character_id": row[2] if len(row) > 2 else None,
                                "created_by": interaction.user.id,
                                "created_at": now_iso,
                                "updated_at": now_iso
                            })
            else:
                 await interaction.followup.send("対応形式: .json, .csv", ephemeral=True)
                 return
            
            if not new_quotes:
                await interaction.followup.send("データが見つかりませんでした。", ephemeral=True)
                return

            async with self._data_lock:
                self.quotes = new_quotes
                self._save_data()

            await interaction.followup.send(f"名言データを全置換しました ({len(new_quotes)}件)。", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in quote_update: {e}", exc_info=True)
            await interaction.followup.send("更新中にエラーが発生しました。", ephemeral=True)

    @app_commands.command(name="quote_toggle", description="名言の定期投稿をON/OFFします")
    @app_commands.describe(enabled="true で有効化、false で無効化")
    async def quote_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        async with self._data_lock:
            self.settings["enabled"] = bool(enabled)
            self._persist_settings()
        state = "有効" if enabled else "無効"
        await interaction.response.send_message(f"名言の定期投稿を{state}にしました。", ephemeral=True)

    @app_commands.command(name="quote_schedule", description="名言の定期投稿スケジュールを設定します")
    @app_commands.describe(
        days="何日おきに投稿するか (1以上の整数)",
        hour="投稿時刻 (0-23)",
        minute="投稿時刻 (0-59)",
    )
    async def quote_schedule(self, interaction: discord.Interaction, days: int, hour: int, minute: int) -> None:
        """名言の定期投稿スケジュールを設定するコマンド."""

        if days < 1 or not (0 <= hour <= 23) or not (0 <= minute <= 59):
            await interaction.response.send_message("入力値が不正です。日数は1以上、時刻は0-23/0-59で指定してください。", ephemeral=True)
            return

        async with self._data_lock:
            self.settings["days"] = days
            self.settings["hour"] = hour
            self.settings["minute"] = minute
            self.settings["last_posted_at"] = None
            self._persist_settings()

        await interaction.response.send_message(
            f"投稿スケジュールを {days}日おき {hour:02d}:{minute:02d} に設定しました。", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quotes(bot))
