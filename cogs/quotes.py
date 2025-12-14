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
_DATA_DIR = "data"
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

    @app_commands.command(name="quote_list", description="登録されている名言を一覧表示します")
    @app_commands.describe(page="表示したいページ番号 (1ページ10件)")
    async def quote_list(self, interaction: discord.Interaction, page: Optional[int] = 1) -> None:
        if page is None or page < 1:
            page = 1
        total = len(self.quotes)
        if total == 0:
            await interaction.response.send_message("名言はまだ登録されていません。", ephemeral=True)
            return

        max_page = (total - 1) // _ITEMS_PER_PAGE + 1
        if page > max_page:
            page = max_page
        start = (page - 1) * _ITEMS_PER_PAGE
        end = min(start + _ITEMS_PER_PAGE, total)
        embed = discord.Embed(
            title="📝 名言一覧",
            description=f"登録数: {total} 件",
            color=discord.Color.blue(),
        )
        for quote in self.quotes[start:end]:
            quote_id = quote.get("id", "")
            embed.add_field(
                name=f"{quote.get('speaker', '不明')} (ID: {quote_id})",
                value=self._format_quote_line(quote),
                inline=False,
            )
        embed.set_footer(text=f"ページ {page}/{max_page}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="quote_search", description="名言をキーワードで検索します")
    @app_commands.describe(keyword="発言者名または名言本文から検索するキーワード")
    async def quote_search(self, interaction: discord.Interaction, keyword: str) -> None:
        keyword = keyword.strip()
        if not keyword:
            await interaction.response.send_message("検索キーワードを入力してください。", ephemeral=True)
            return

        keyword_lower = keyword.lower()
        matches = [
            quote for quote in self.quotes
            if keyword_lower in quote.get("speaker", "").lower() or keyword_lower in quote.get("text", "").lower()
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
            embed.set_footer(text=f"先頭 {_ITEMS_PER_PAGE} 件のみ表示。残り {len(matches) - _ITEMS_PER_PAGE} 件はコマンドで絞り込んでください。")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="quote_add", description="名言を1件登録します")
    @app_commands.describe(
        speaker="発言者名",
        text="名言の本文",
        character_id="関連するキャラクターID (任意)",
    )
    async def quote_add(self, interaction: discord.Interaction, speaker: str, text: str, character_id: Optional[str] = None) -> None:


        speaker = speaker.strip()
        text = text.strip()
        character_id = character_id.strip() if character_id else None

        if not speaker or not text:
            await interaction.response.send_message("発言者と本文はいずれも必須です。", ephemeral=True)
            return

        quote_id = str(uuid.uuid4())
        now_iso = _now(self.tz).isoformat()
        record = {
            "id": quote_id,
            "speaker": speaker,
            "text": text,
            "character_id": character_id or None,
            "created_by": interaction.user.id,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        async with self._data_lock:
            self.quotes.append(record)
            self._save_data()

        await interaction.response.send_message(
            f"名言を登録しました。ID: `{quote_id}`", ephemeral=True
        )

    @app_commands.command(name="quote_edit", description="登録済みの名言を編集します")
    @app_commands.describe(
        quote_id="編集する名言ID",
        speaker="変更後の発言者名 (任意)",
        text="変更後の本文 (任意)",
        character_id="変更後のキャラクターID (未指定で変更なし、空文字で解除)",
    )
    async def quote_edit(
        self,
        interaction: discord.Interaction,
        quote_id: str,
        speaker: Optional[str] = None,
        text: Optional[str] = None,
        character_id: Optional[str] = None,
    ) -> None:


        if speaker is None and text is None and character_id is None:
            await interaction.response.send_message("更新する項目を少なくとも1つ指定してください。", ephemeral=True)
            return

        async with self._data_lock:
            target = next((q for q in self.quotes if q.get("id") == quote_id), None)
            if not target:
                await interaction.response.send_message("指定された名言IDが見つかりません。", ephemeral=True)
                return

            if speaker is not None:
                speaker = speaker.strip()
                if speaker:
                    target["speaker"] = speaker
            if text is not None:
                text = text.strip()
                if text:
                    target["text"] = text
            if character_id is not None:
                cleaned = character_id.strip()
                target["character_id"] = cleaned or None
            target["updated_at"] = _now(self.tz).isoformat()
            self._save_data()

        await interaction.response.send_message("名言を更新しました。", ephemeral=True)

    @app_commands.command(name="quote_delete", description="名言を削除します")
    @app_commands.describe(quote_id="削除する名言ID")
    async def quote_delete(self, interaction: discord.Interaction, quote_id: str) -> None:


        async with self._data_lock:
            index = next((i for i, q in enumerate(self.quotes) if q.get("id") == quote_id), None)
            if index is None:
                await interaction.response.send_message("指定された名言IDが見つかりません。", ephemeral=True)
                return
            removed = self.quotes.pop(index)
            self._save_data()

        speaker = removed.get("speaker", "不明")
        truncated_text = removed.get("text", "").replace("\n", " ")
        if len(truncated_text) > 100:
            truncated_text = truncated_text[:97] + "..."
        message = (
            f"🗑️ {interaction.user.mention} が名言を削除しました\n"
            f"ID: `{quote_id}` / 発言者: {speaker}\n"
            f"本文: {truncated_text}"
        )
        await interaction.response.send_message(
            message,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    @app_commands.command(name="quote_import", description="CSVから名言を一括登録します")
    @app_commands.describe(file="speaker,text[,character_id] の形式のCSVファイル")
    async def quote_import(self, interaction: discord.Interaction, file: discord.Attachment) -> None:


        await interaction.response.defer(ephemeral=True)

        try:
            raw = await file.read()
            text_data = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            await interaction.followup.send("CSVファイルはUTF-8で保存してください。", ephemeral=True)
            return
        except Exception as exc:
            logger.error("CSVの読み込みに失敗しました: %s", exc)
            await interaction.followup.send("ファイルの読み込みに失敗しました。", ephemeral=True)
            return

        stream = io.StringIO(text_data)
        reader = csv.DictReader(stream)
        rows: List[Dict[str, Optional[str]]] = []
        if reader.fieldnames and "speaker" in [f.lower() for f in reader.fieldnames] and "text" in [f.lower() for f in reader.fieldnames]:
            normalized_fields = [f.lower() for f in reader.fieldnames]
            for row in reader:
                rows.append({
                    "speaker": row.get(reader.fieldnames[normalized_fields.index("speaker")], ""),
                    "text": row.get(reader.fieldnames[normalized_fields.index("text")], ""),
                    "character_id": row.get(reader.fieldnames[normalized_fields.index("character_id")], "") if "character_id" in normalized_fields else None,
                })
        else:
            stream.seek(0)
            plain_reader = csv.reader(stream)
            for row in plain_reader:
                if not row:
                    continue
                speaker = row[0] if len(row) > 0 else ""
                text_val = row[1] if len(row) > 1 else ""
                character_id = row[2] if len(row) > 2 else None
                rows.append({"speaker": speaker, "text": text_val, "character_id": character_id})

        if not rows:
            await interaction.followup.send("CSVに有効な行が見つかりませんでした。", ephemeral=True)
            return

        added = 0
        skipped = 0
        new_records: List[Dict] = []
        for row in rows:
            speaker_val = (row.get("speaker") or "").strip()
            text_val = (row.get("text") or "").strip()
            character_id_val = (row.get("character_id") or "").strip()
            if not speaker_val or not text_val:
                skipped += 1
                continue
            now_iso = _now(self.tz).isoformat()
            new_records.append({
                "id": str(uuid.uuid4()),
                "speaker": speaker_val,
                "text": text_val,
                "character_id": character_id_val or None,
                "created_by": interaction.user.id,
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            added += 1

        if added == 0:
            await interaction.followup.send("CSVに有効な名言がありませんでした。", ephemeral=True)
            return

        async with self._data_lock:
            self.quotes.extend(new_records)
            self._save_data()

        await interaction.followup.send(
            f"{added} 件の名言を登録しました。スキップ: {skipped} 件", ephemeral=True
        )

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
