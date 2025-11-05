# """
# Googleスプレッドシートをデータソースとする辞書コグ。

# スプレッドシート全体からキーワード検索を行い、シート名や行番号とともに
# 結果をEmbedで表示します。スプレッドシートの更新は外部で行い、ボット側では
# Google Sheets API経由で読み取り専用アクセスを行います。
# """

# from __future__ import annotations

# import time
# from typing import Any, Dict, List, Sequence, Tuple

# import discord
# from discord import app_commands
# from discord.ext import commands
# import logging
# import traceback

# import config

# try:
#     import gspread  # type: ignore
# except ImportError:  # pragma: no cover - optional dependency
#     gspread = None  # type: ignore

# logger = logging.getLogger(__name__)

# Entry = Dict[str, Any]


# class Dictionary(commands.Cog):
#     """Googleスプレッドシートを参照する辞書機能コグ。"""

#     CACHE_TTL_SECONDS = 300
#     MAX_LINES_PER_FIELD = 6

#     def __init__(self, bot: commands.Bot):
#         self.bot = bot
#         self._entries: List[Entry] = []
#         self._last_loaded: float = 0.0
#         self._sheet_id: str | None = config.DICTIONARY_SHEET_ID

#     # ------------------------------------------------------------------
#     # データ読み込み関連
#     # ------------------------------------------------------------------
#     def _ensure_loaded(self, force: bool = False) -> None:
#         if not config.is_feature_enabled("dictionary"):
#             self._entries = []
#             return

#         if not self._sheet_id:
#             raise RuntimeError("DICTIONARY_SHEET_ID が設定されていません。環境変数を確認してください。")

#         if not force and self._entries and (time.time() - self._last_loaded) < self.CACHE_TTL_SECONDS:
#             return

#         if gspread is None:
#             raise RuntimeError("gspread がインストールされていません。requirements.txt を確認してください。")

#         logger.info("Google Sheets から辞書データを取得します")
#         credentials = config.get_google_credentials()
#         client = gspread.authorize(credentials)

#         try:
#             spreadsheet = client.open_by_key(self._sheet_id)
#         except Exception as exc:  # pragma: no cover - ネットワーク依存
#             logger.error("スプレッドシートを開けませんでした: %s", exc)
#             raise

#         entries: List[Entry] = []
#         for worksheet in spreadsheet.worksheets():
#             try:
#                 values = worksheet.get_all_values()
#             except Exception as exc:  # pragma: no cover - ネットワーク依存
#                 logger.error("シート '%s' の取得に失敗しました: %s", worksheet.title, exc)
#                 continue

#             if not values:
#                 continue

#             headers = self._normalise_headers(values[0])
#             for row_index, row in enumerate(values[1:], start=2):
#                 entry = self._build_entry(worksheet, headers, row_index, row)
#                 if entry:
#                     entries.append(entry)

#         self._entries = entries
#         self._last_loaded = time.time()
#         logger.info("辞書データを %d 件ロードしました", len(entries))

#     @staticmethod
#     def _normalise_headers(header_row: Sequence[str]) -> List[str]:
#         headers: List[str] = []
#         for idx, value in enumerate(header_row):
#             name = value.strip()
#             if not name:
#                 name = f"Column {idx + 1}"
#             headers.append(name)
#         return headers

#     def _build_entry(
#         self,
#         worksheet: Any,
#         headers: Sequence[str],
#         row_index: int,
#         row: Sequence[str],
#     ) -> Entry | None:
#         pairs: List[Tuple[str, str]] = []
#         text_parts: List[str] = []
#         summary: str | None = None

#         for col_index, cell in enumerate(row):
#             cell_value = cell.strip()
#             if not cell_value:
#                 continue

#             header = headers[col_index] if col_index < len(headers) else f"Column {col_index + 1}"
#             header = header.strip() or f"Column {col_index + 1}"
#             pairs.append((header, cell_value))
#             text_parts.append(f"{header}: {cell_value}")

#             if not summary:
#                 summary = cell_value

#         if not pairs:
#             return None

#         if not summary:
#             summary = f"{worksheet.title} 行{row_index}"

#         return {
#             "sheet": worksheet.title,
#             "gid": getattr(worksheet, "id", None),
#             "row": row_index,
#             "summary": summary,
#             "pairs": pairs,
#             "text": "\n".join(text_parts),
#         }

#     @staticmethod
#     def _count_keyword_occurrences(keyword_lower: str, text: str) -> int:
#         return text.lower().count(keyword_lower) if keyword_lower else 0

#     def _calculate_relevance_score(self, keyword: str, entry: Entry, allow_fuzzy: bool) -> Tuple[float, int]:
#         keyword_lower = keyword.lower()
#         summary = entry["summary"]
#         body_text = entry["text"]
#         combined = f"{summary}\n{body_text}".lower()
#         count = self._count_keyword_occurrences(keyword_lower, combined)

#         if not keyword_lower:
#             return (0.0, count)

#         summary_lower = summary.lower()
#         body_lower = body_text.lower()

#         if summary_lower == keyword_lower:
#             return (100.0, count)
#         if keyword_lower in summary_lower:
#             return (80.0, count)
#         if keyword_lower in body_lower:
#             return (60.0, count)

#         if allow_fuzzy:
#             longest = max(
#                 (i for i in range(len(keyword_lower), 0, -1) if keyword_lower[:i] in summary_lower),
#                 default=0,
#             )
#             if longest:
#                 score = float(longest) / len(keyword_lower) * 40.0
#                 return (score, count)

#         return (0.0, count)

#     def _format_entry_lines(self, entry: Entry) -> str:
#         lines: List[str] = []
#         for header, value in entry["pairs"][: self.MAX_LINES_PER_FIELD]:
#             truncated = value if len(value) <= 200 else value[:197] + "..."
#             lines.append(f"**{header}**: {truncated}")
#         if len(entry["pairs"]) > self.MAX_LINES_PER_FIELD:
#             lines.append("…")
#         return "\n".join(lines)

#     # ------------------------------------------------------------------
#     # Discord ユーティリティ
#     # ------------------------------------------------------------------
#     async def _is_operator(self, interaction: discord.Interaction) -> bool:
#         operator_role_id = getattr(config, "OPERATOR_ROLE_ID", 0)
#         if not operator_role_id:
#             return False

#         user = interaction.user
#         if isinstance(user, discord.Member):
#             roles = user.roles
#         elif interaction.guild:
#             member = interaction.guild.get_member(user.id)
#             roles = getattr(member, "roles", []) if member else []
#         else:
#             roles = []

#         return any(role.id == operator_role_id for role in roles)

#     class DictionaryPaginator(discord.ui.View):
#         def __init__(self, keyword: str, search_results: Sequence[Entry], items_per_page: int = 3, timeout: float = 180):
#             super().__init__(timeout=timeout)
#             self.keyword = keyword
#             self.search_results = list(search_results)
#             self.items_per_page = max(1, items_per_page)
#             self.current_page = 0
#             self.total_pages = max(1, (len(self.search_results) + self.items_per_page - 1) // self.items_per_page)
#             self.update_button_states()

#         def update_button_states(self) -> None:
#             disabled = self.total_pages <= 1
#             self.prev_page.disabled = disabled or self.current_page <= 0
#             self.next_page.disabled = disabled or self.current_page >= self.total_pages - 1

#         def _items_for_page(self, page: int) -> Sequence[Entry]:
#             start_idx = page * self.items_per_page
#             end_idx = start_idx + self.items_per_page
#             return self.search_results[start_idx:end_idx]

#         def get_current_page_embed(self) -> discord.Embed:
#             start_idx = self.current_page * self.items_per_page
#             end_idx = start_idx + self.items_per_page
#             embed = discord.Embed(
#                 title=f"🔍 「{self.keyword}」の検索結果",
#                 description=f"全{len(self.search_results)}件中 {start_idx + 1}～{min(end_idx, len(self.search_results))}件を表示",
#                 color=discord.Color.blue(),
#             )

#             for entry in self._items_for_page(self.current_page):
#                 sheet = entry["sheet"]
#                 row = entry["row"]
#                 summary = entry["summary"]
#                 field_name = f"📚 {summary}｜{sheet} 行{row}"
#                 embed.add_field(name=field_name, value=entry["rendered"], inline=False)

#             if self.total_pages > 1:
#                 embed.set_footer(text=f"ページ {self.current_page + 1}/{self.total_pages}")

#             return embed

#         @discord.ui.button(label="前へ", style=discord.ButtonStyle.primary, emoji="◀️")
#         async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
#             if self.current_page <= 0:
#                 return
#             self.current_page -= 1
#             self.update_button_states()
#             await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)

#         @discord.ui.button(label="次へ", style=discord.ButtonStyle.primary, emoji="▶️")
#         async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
#             if self.current_page >= self.total_pages - 1:
#                 return
#             self.current_page += 1
#             self.update_button_states()
#             await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)

#     # ------------------------------------------------------------------
#     # スラッシュコマンド
#     # ------------------------------------------------------------------
#     @app_commands.command(name="search", description="辞書スプレッドシートから情報を検索します")
#     @app_commands.describe(
#         word="検索するキーワード",
#         fuzzy="あいまい検索を行うかどうか（デフォルト: True）",
#     )
#     async def search_word(self, interaction: discord.Interaction, word: str, fuzzy: bool = True) -> None:
#         if not config.is_feature_enabled("dictionary"):
#             await interaction.response.send_message("このコマンドは現在無効化されています。", ephemeral=True)
#             return

#         if not await self._is_operator(interaction):
#             await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
#             return

#         try:
#             self._ensure_loaded()
#         except Exception as exc:
#             logger.error("辞書データのロードに失敗しました: %s", exc)
#             await interaction.response.send_message("辞書データの読み込みに失敗しました。設定を確認してください。", ephemeral=True)
#             return

#         keyword = word.strip()
#         results: List[Entry] = []
#         for entry in self._entries:
#             score, count = self._calculate_relevance_score(keyword, entry, fuzzy)
#             if score <= 0:
#                 continue
#             enriched = dict(entry)
#             enriched["score"] = score
#             enriched["count"] = count
#             enriched["rendered"] = self._format_entry_lines(entry)
#             if self._sheet_id and entry.get("gid") is not None:
#                 gid = entry["gid"]
#                 url = f"https://docs.google.com/spreadsheets/d/{self._sheet_id}/edit#gid={gid}&range={entry['row']}"
#                 enriched["rendered"] += f"\n[シートを開く]({url})"
#             results.append(enriched)

#         if not results:
#             await interaction.response.send_message(f"「{keyword}」に該当する結果は見つかりませんでした。", ephemeral=True)
#             return

#         results.sort(key=lambda item: (-item["score"], -item["count"]))

#         view = self.DictionaryPaginator(keyword=keyword, search_results=results)
#         await interaction.response.send_message(embed=view.get_current_page_embed(), view=view)

#     @app_commands.command(name="reloaddictionary", description="Googleスプレッドシートから辞書データを再読込します")
#     async def reload_dictionary(self, interaction: discord.Interaction) -> None:
#         if not await self._is_operator(interaction):
#             await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
#             return

#         try:
#             self._ensure_loaded(force=True)
#         except Exception as exc:
#             logger.error("辞書データの再読込に失敗しました: %s", exc)
#             await interaction.response.send_message("辞書データの再読込に失敗しました。設定を確認してください。", ephemeral=True)
#             return

#         await interaction.response.send_message("辞書データを再読込しました。", ephemeral=True)

#     @app_commands.command(name="listwords", description="シートごとの登録件数を表示します")
#     async def list_words(self, interaction: discord.Interaction) -> None:
#         if not config.is_feature_enabled("dictionary"):
#             await interaction.response.send_message("この機能は現在無効化されています。", ephemeral=True)
#             return

#         if not await self._is_operator(interaction):
#             await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
#             return

#         try:
#             self._ensure_loaded()
#         except Exception as exc:
#             logger.error("辞書データのロードに失敗しました: %s", exc)
#             await interaction.response.send_message("辞書データの取得に失敗しました。", ephemeral=True)
#             return

#         if not self._entries:
#             await interaction.response.send_message("辞書データが読み込まれていません。", ephemeral=True)
#             return

#         counts: Dict[str, int] = {}
#         for entry in self._entries:
#             counts[entry["sheet"]] = counts.get(entry["sheet"], 0) + 1

#         description_lines = [f"{sheet}: {count} 件" for sheet, count in sorted(counts.items())]
#         embed = discord.Embed(title="📚 登録件数", description="\n".join(description_lines), color=discord.Color.green())
#         await interaction.response.send_message(embed=embed, ephemeral=True)

#     @app_commands.command(name="addword", description="辞書に単語を追加します（スプレッドシートで編集してください）")
#     async def add_word(self, interaction: discord.Interaction, word: str, meaning: str) -> None:  # noqa: D401
#         await interaction.response.send_message(
#             "このボットはスプレッドシートを参照します。単語の追加・編集はGoogleスプレッドシートで行ってください。",
#             ephemeral=True,
#         )

#     @app_commands.command(name="deleteword", description="辞書から単語を削除します（スプレッドシートで編集してください）")
#     async def delete_word(self, interaction: discord.Interaction, word: str) -> None:  # noqa: D401
#         await interaction.response.send_message(
#             "このボットはスプレッドシートを参照します。単語の削除はGoogleスプレッドシートで行ってください。",
#             ephemeral=True,
#         )


# async def setup(bot: commands.Bot) -> None:
#     try:
#         await bot.add_cog(Dictionary(bot))
#         logger.info("Dictionary cog loaded successfully")
#     except Exception as exc:
#         logger.error("Failed to load Dictionary cog: %s", exc)
#         logger.error(traceback.format_exc())
#         raise