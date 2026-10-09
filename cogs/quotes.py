"""Quote management and scheduled posting cog."""

from __future__ import annotations

import asyncio
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
import utils
from quote_records import normalize, merge_records, parse_upload
from cogs.pagination import Pagination

logger = logging.getLogger(__name__)
# 環境に依存しないパス構築
_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
_DATA_DIR = os.path.abspath(_DATA_DIR)
_DEFAULT_DATA_PATH = os.path.join(config._DATA_DIR, "quotes.json")


def _now(tz: datetime.tzinfo) -> datetime.datetime:
    """Return the current time in the configured timezone."""
    return datetime.datetime.now(tz)


class Quotes(commands.Cog):
    """Manage quotes and automatically post them on a schedule."""

    def __init__(self, bot: commands.Bot, data_path: Optional[str] = None) -> None:
        self.bot = bot
        self.tz = utils.get_timezone()
        self.data_path = data_path or _DEFAULT_DATA_PATH
        self._data_lock = asyncio.Lock()
        self.quotes: List[Dict] = []
        self.settings: Dict[str, Any] = {}
        self._task_started = False
        self._has_rejected_rows = False
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
        return utils.coerce_bool(value, fallback)

    @staticmethod
    def _coerce_int(value: Any, fallback: int, *, minimum: int, maximum: Optional[int] = None) -> int:
        return utils.coerce_int(value, fallback, minimum=minimum, maximum=maximum)

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
        config.set_runtime_section("quotes", payload)

    async def _change_settings(self, values: Dict[str, Any]) -> None:
        async with self._data_lock:
            updated = {**self.settings, **values}
            await asyncio.to_thread(config.set_runtime_section, "quotes", updated)
            self.settings = updated

    def _ensure_data_dir(self) -> None:
        os.makedirs(os.path.dirname(self.data_path) or ".", exist_ok=True)

    def _load_data(self) -> None:
        """Load quotes from disk."""
        self._ensure_data_dir()

        if not os.path.exists(self.data_path):
            self._has_rejected_rows = False
            self.quotes = []
            self._save_data()
            return

        with open(self.data_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload if isinstance(payload, list) else payload.get("quotes") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("quotes.json must contain a quote list")
        valid, rejected, seen = [], [], set()
        for number, row in enumerate(rows, 1):
            try:
                quote = normalize(row)
                # Stable even when rejected rows force us to preserve the source file.
                quote["id"] = quote["id"] or str(uuid.uuid5(uuid.NAMESPACE_URL,
                    f"zft-quote:{number}:" + json.dumps(quote, ensure_ascii=False, sort_keys=True)))
                if quote["id"] in seen:
                    raise ValueError("duplicate ID")
                seen.add(quote["id"])
                valid.append(quote)
            except ValueError as exc:
                rejected.append({"row": number, "error": str(exc), "record": row})
        self.quotes = valid
        self._has_rejected_rows = bool(rejected)
        if rejected:
            utils.atomic_write_json(self.data_path + ".rejected.json", rejected)
            logger.warning("Rejected %s invalid quotes; original file preserved", len(rejected))
        elif rows != valid or isinstance(payload, list):
            self._save_data()

    def _save_data(self) -> None:
        """Persist quotes to disk."""
        if getattr(self, "_has_rejected_rows", False):
            raise ValueError("不正な名言を含むため個別更新できません。.rejected.jsonを確認し、修正したファイルで全置換してください")
        self._ensure_data_dir()
        payload = {
            "quotes": self.quotes,
        }
        utils.atomic_write_json(self.data_path, payload)

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
        """キャラクター画像URLを取得（config.pyで一元管理）"""
        cid = character_id.strip()
        if not cid:
            return ""
        return config.get_character_image_url(cid)

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
            # キャラクターページURL（config.pyで一元管理）
            embed.url = config.get_character_page_url(str(character_id))
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
            await asyncio.to_thread(self._persist_settings)

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

    def cog_unload(self):
        self.quote_posting_loop.cancel()

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

    async def _show_records(self, interaction, records, title):
        if not records:
            await interaction.response.send_message("該当する名言はありません。", ephemeral=True)
            return
        view = Pagination(records, interaction.user.id, title,
                          lambda q: (f"{q['speaker']} (ID: {q['id']})", self._format_quote_line(q)))
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def _handle_list(self, interaction, page=1):
        await self._show_records(interaction, self.quotes, "📝 名言一覧")

    async def _handle_search(self, interaction, keyword):
        keyword = keyword.strip().casefold()
        matches = [q for q in self.quotes if any(keyword in str(q.get(key) or "").casefold()
                   for key in ("speaker", "text", "id", "character_id"))]
        await self._show_records(interaction, matches, "🔍 名言検索結果")

    async def _replace_records(self, records, *, full_replace=False):
        rejected = getattr(self, "_has_rejected_rows", False)
        if rejected and not full_replace:
            raise ValueError("不正な名言を含むため個別更新できません。.rejected.jsonを確認し、修正したファイルで全置換してください")
        previous = self.quotes
        self.quotes = records
        self._has_rejected_rows = False
        try:
            await asyncio.to_thread(self._save_data)
        except BaseException:
            self.quotes = previous
            self._has_rejected_rows = rejected
            raise

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quote_update", description="ファイルから名言データを一括更新します（全置換）")
    @app_commands.describe(file="更新用ファイル（CSV/JSON）")
    async def quote_update(self, interaction: discord.Interaction, file: discord.Attachment):
        """CSV/JSONファイルから名言を一括更新（全置換）します。"""

        await interaction.response.defer(ephemeral=True)
        try:
            if isinstance(file.size, int) and file.size > 5 * 1024 * 1024:
                raise ValueError("ファイルは5MB以内で指定してください")
            rows = parse_upload(await file.read(), file.filename)
            async with self._data_lock:
                records = merge_records(rows, self.quotes, interaction.user.id, _now(self.tz).isoformat())
                await self._replace_records(records, full_replace=True)
            await interaction.followup.send(f"名言データを全置換しました ({len(records)}件)。", ephemeral=True)
        except (ValueError, UnicodeError) as exc:
            await interaction.followup.send(f"更新しませんでした: {exc}", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quote_add", description="名言を1件追加します")
    async def quote_add(self, interaction: discord.Interaction, speaker: str, text: str, character_id: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self._data_lock:
                record = merge_records([dict(speaker=speaker, text=text, character_id=character_id)], [],
                                       interaction.user.id, _now(self.tz).isoformat())[0]
                await self._replace_records([*self.quotes, record])
            await interaction.followup.send(f"名言を追加しました。ID: {record['id']}", ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quote_edit", description="IDを指定して名言を編集します")
    @app_commands.describe(clear_character="trueでキャラクターIDを解除（character_idとの併用不可）")
    async def quote_edit(self, interaction: discord.Interaction, quote_id: str, speaker: Optional[str] = None,
                         text: Optional[str] = None, character_id: Optional[str] = None, clear_character: bool = False):
        await interaction.response.defer(ephemeral=True)
        try:
            if clear_character and character_id is not None:
                raise ValueError("character_idとclear_characterは同時に指定できません")
            async with self._data_lock:
                existing = next((q for q in self.quotes if q['id'] == quote_id), None)
                if existing is None:
                    raise ValueError("指定した名言IDは見つかりません")
                changes = {key: value for key, value in dict(speaker=speaker, text=text, character_id=character_id).items() if value is not None}
                if clear_character:
                    changes['character_id'] = None
                record = merge_records([{**existing, **changes}], self.quotes, interaction.user.id, _now(self.tz).isoformat())[0]
                await self._replace_records([record if q['id'] == quote_id else q for q in self.quotes])
            await interaction.followup.send(f"名言 {quote_id} を編集しました。", ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quote_delete", description="IDを指定して名言を削除します（confirm:trueで確定）")
    async def quote_delete(self, interaction: discord.Interaction, quote_id: str, confirm: bool = False):
        await interaction.response.defer(ephemeral=True)
        async with self._data_lock:
            existing = next((q for q in self.quotes if q['id'] == quote_id), None)
            if existing is None:
                await interaction.followup.send("指定した名言IDは見つかりません。", ephemeral=True)
                return
            if not confirm:
                await interaction.followup.send(f"削除対象: {existing['speaker']} » {existing['text'][:200]}\n削除するには同じIDでconfirm:trueを指定してください。", ephemeral=True)
                return
            await self._replace_records([q for q in self.quotes if q['id'] != quote_id])
        await interaction.followup.send(f"名言 {quote_id} を削除しました。", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quote_toggle", description="名言の定期投稿をON/OFFします")
    @app_commands.describe(enabled="true で有効化、false で無効化")
    async def quote_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self._change_settings({"enabled": bool(enabled)})
        state = "有効" if enabled else "無効"
        await interaction.response.send_message(f"名言の定期投稿を{state}にしました。", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
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

        await self._change_settings({"days": days, "hour": hour, "minute": minute, "last_posted_at": None})

        await interaction.response.send_message(
            f"投稿スケジュールを {days}日おき {hour:02d}:{minute:02d} に設定しました。", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Quotes(bot))
