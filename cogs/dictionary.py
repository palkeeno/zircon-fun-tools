"""
辞書機能のコグ
このモジュールは、カスタム辞書の機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import logging
import traceback
import os
import config

# ロギングの設定
logger = logging.getLogger(__name__)

class Dictionary(commands.Cog):
    """
    辞書機能のコグ
    カスタム辞書の機能を提供します。
    """
    
    def __init__(self, bot: commands.Bot):
        """
        辞書機能のコグを初期化します。
        
        Args:
            bot (commands.Bot): ボットのインスタンス
        """
        self.bot = bot
        self.dictionary_file = os.path.join("data", "dictionary.json")
        self.dictionary = self.load_dictionary()

    def load_dictionary(self):
        """辞書データを読み込む"""
        try:
            if not config.is_feature_enabled('dictionary'):
                return {}
            
            if not os.path.exists(self.dictionary_file):
                os.makedirs(os.path.dirname(self.dictionary_file), exist_ok=True)
                with open(self.dictionary_file, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=4)
                return {}
            
            with open(self.dictionary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading dictionary: {e}")
            logger.error(traceback.format_exc())
            return {}

    def save_dictionary(self):
        """辞書データを保存"""
        try:
            if not config.is_feature_enabled('dictionary'):
                return
            
            with open(self.dictionary_file, 'w', encoding='utf-8') as f:
                json.dump(self.dictionary, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving dictionary: {e}")
            logger.error(traceback.format_exc())

    async def _is_operator(self, interaction: discord.Interaction) -> bool:
        """
        運営ロールIDで判定します。
        """
        from config import OPERATOR_ROLE_ID
        if not OPERATOR_ROLE_ID or not hasattr(interaction.user, "roles"):
            return False
        return any(role.id == OPERATOR_ROLE_ID for role in interaction.user.roles)

    @app_commands.command(name="addword", description="新しい単語を辞書に追加します")
    @app_commands.describe(word="追加する単語", meaning="単語の意味")
    async def add_word(self, interaction: discord.Interaction, word: str, meaning: str):
        """新しい単語を辞書に追加します"""
        if not config.is_feature_enabled('dictionary'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        try:
            self.dictionary[word] = meaning
            self.save_dictionary()
            await interaction.response.send_message(f"単語「{word}」を辞書に追加しました！")
        except Exception as e:
            logger.error(f"Error in add_word: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    def _calculate_relevance_score(self, word: str, title: str, description: str) -> tuple[float, int]:
        """
        検索結果の関連性スコアを計算します。

        Args:
            word (str): 検索キーワード
            title (str): 見出し語
            description (str): 説明文

        Returns:
            tuple[float, int]: (スコア, キーワード出現回数)
        """
        keyword_lower = word.lower()
        title_lower = title.lower()
        description_lower = description.lower()

        # 見出し語完全一致は最高優先度
        if title_lower == keyword_lower:
            return (100.0, title.count(word) + description.count(word))

        # 見出し語に含まれる場合は次に高い優先度
        if keyword_lower in title_lower:
            return (80.0, title.count(word) + description.count(word))

        # 説明文に含まれる場合
        if keyword_lower in description_lower:
            return (60.0, description.count(word))

        # あいまい検索の場合（見出し語のみ）
        if len(keyword_lower) > 0:
            title_similarity = max((i for i in range(len(keyword_lower) + 1) 
                                  if keyword_lower[:i] in title_lower), default=0)
            return (float(title_similarity) / len(keyword_lower) * 40.0, 0)
        
        return (0.0, 0)

    class DictionaryPaginator(discord.ui.View):
        def __init__(self, search_results: list, items_per_page: int = 5, timeout: float = 180):
            super().__init__(timeout=timeout)
            self.search_results = search_results
            self.items_per_page = items_per_page
            self.current_page = 0
            self.total_pages = (len(search_results) + items_per_page - 1) // items_per_page
            self.update_button_states()

        def update_button_states(self):
            """ページに応じてボタンの有効/無効を設定"""
            self.prev_page.disabled = self.current_page <= 0
            self.next_page.disabled = self.current_page >= self.total_pages - 1

        def get_current_page_embed(self, word: str) -> discord.Embed:
            """現在のページのembedを生成"""
            start_idx = self.current_page * self.items_per_page
            end_idx = start_idx + self.items_per_page
            current_items = self.search_results[start_idx:end_idx]

            embed = discord.Embed(
                title=f"🔍 「{word}」の検索結果",
                description=f"全{len(self.search_results)}件中 {start_idx + 1}～{min(end_idx, len(self.search_results))}件目を表示",
                color=discord.Color.blue()
            )

            for title, description, score, count in current_items:
                embed.add_field(
                    name=f"📚 {title}",
                    value=description[:200] + ("..." if len(description) > 200 else ""),
                    inline=False
                )

            if self.total_pages > 1:
                embed.set_footer(text=f"ページ {self.current_page + 1}/{self.total_pages}")

            return embed

        @discord.ui.button(label="前へ", style=discord.ButtonStyle.primary, emoji="◀️")
        async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current_page = max(0, self.current_page - 1)
            self.update_button_states()
            await interaction.response.edit_message(
                embed=self.get_current_page_embed(interaction.message.embeds[0].title.split("「")[1].split("」")[0]),
                view=self
            )

        @discord.ui.button(label="次へ", style=discord.ButtonStyle.primary, emoji="▶️")
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.current_page = min(self.total_pages - 1, self.current_page + 1)
            self.update_button_states()
            await interaction.response.edit_message(
                embed=self.get_current_page_embed(interaction.message.embeds[0].title.split("「")[1].split("」")[0]),
                view=self
            )

    @app_commands.command(name="search", description="辞書から情報を検索します")
    @app_commands.describe(
        word="検索するキーワード",
        fuzzy="あいまい検索を行うかどうか（デフォルト: True）"
    )
    async def search_word(
        self,
        interaction: discord.Interaction,
        word: str,
        fuzzy: bool = True
    ):
        """辞書から情報を検索します"""
        if not config.is_feature_enabled('dictionary'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        try:
            # 検索結果を収集
            search_results = []
            for title, description in self.dictionary.items():
                # 完全一致または部分一致
                if (word.lower() in title.lower() or
                    word.lower() in description.lower()):
                    score, count = self._calculate_relevance_score(word, title, description)
                    search_results.append((title, description, score, count))
                # あいまい検索が有効な場合
                elif fuzzy:
                    score, count = self._calculate_relevance_score(word, title, description)
                    if score > 0:
                        search_results.append((title, description, score, count))

            # 検索結果がない場合
            if not search_results:
                await interaction.response.send_message(
                    f"「{word}」に関する情報は見つかりませんでした。",
                    ephemeral=True
                )
                return

            # スコアと出現回数で並び替え
            search_results.sort(key=lambda x: (-x[2], -x[3]))

            # ページネーターを作成
            view = self.DictionaryPaginator(search_results)
            
            # 最初のページを表示
            await interaction.response.send_message(
                embed=view.get_current_page_embed(word),
                view=view
            )

        except Exception as e:
            logger.error(f"Error in search_word: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(name="deleteword", description="単語を辞書から削除します")
    @app_commands.describe(word="削除する単語")
    async def delete_word(self, interaction: discord.Interaction, word: str):
        """単語を辞書から削除します"""
        if not config.is_feature_enabled('dictionary'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        try:
            if word in self.dictionary:
                del self.dictionary[word]
                self.save_dictionary()
                await interaction.response.send_message(f"単語「{word}」を辞書から削除しました。")
            else:
                await interaction.response.send_message(f"「{word}」は辞書に存在しません。")
        except Exception as e:
            logger.error(f"Error in delete_word: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(name="listwords", description="辞書に登録されている単語の一覧を表示します")
    async def list_words(self, interaction: discord.Interaction):
        """辞書に登録されている単語の一覧を表示"""
        if not config.is_feature_enabled('dictionary'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        if not await self._is_operator(interaction):
            await interaction.response.send_message("このコマンドは運営ロールのみ使用できます。", ephemeral=True)
            return

        try:
            if not self.dictionary:
                await interaction.response.send_message("辞書に登録されている単語はありません。")
                return

            embed = discord.Embed(
                title="📚 辞書一覧",
                description="登録されている単語の一覧です",
                color=discord.Color.green()
            )

            # 単語を50音順にソート
            sorted_words = sorted(self.dictionary.items(), key=lambda x: x[0])
            
            # 単語をグループ化して表示（1ページあたり10単語）
            words_per_page = 10
            total_pages = (len(sorted_words) + words_per_page - 1) // words_per_page

            for i in range(0, len(sorted_words), words_per_page):
                page_words = sorted_words[i:i + words_per_page]
                word_list = "\n".join(f"• {word}" for word, _ in page_words)
                embed.add_field(
                    name=f"ページ {i//words_per_page + 1}/{total_pages}",
                    value=word_list,
                    inline=False
                )

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in list_words: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """
    コグをボットに追加します。
    
    Args:
        bot (commands.Bot): ボットのインスタンス
    """
    try:
        await bot.add_cog(Dictionary(bot))
        logger.info("Dictionary cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Dictionary cog: {e}")
        logger.error(traceback.format_exc())
        raise