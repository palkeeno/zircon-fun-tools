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
import config
from difflib import get_close_matches

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
        self.dictionary_file = "data/dictionary.json"
        self.dictionary = self.load_dictionary()

    def load_dictionary(self):
        """辞書データを読み込む"""
        try:
            if not config.is_feature_enabled('load_dictionary'):
                return {}
            
            if not os.path.exists(self.dictionary_file):
                os.makedirs(os.path.dirname(self.dictionary_file), exist_ok=True)
                with open(self.dictionary_file, 'w') as f:
                    json.dump({}, f)
                return {}
            
            with open(self.dictionary_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading dictionary: {e}")
            logger.error(traceback.format_exc())
            return {}

    def save_dictionary(self):
        """辞書データを保存"""
        try:
            if not config.is_feature_enabled('save_dictionary'):
                return
            
            with open(self.dictionary_file, 'w') as f:
                json.dump(self.dictionary, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving dictionary: {e}")
            logger.error(traceback.format_exc())

    @app_commands.command(name="addword", description="新しい単語を辞書に追加します")
    @app_commands.describe(word="追加する単語", meaning="単語の意味")
    async def add_word(self, interaction: discord.Interaction, word: str, meaning: str):
        """新しい単語を辞書に追加します"""
        if not config.is_feature_enabled('addword'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
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

    @app_commands.command(name="search", description="単語を検索します")
    @app_commands.describe(word="検索する単語")
    async def search_word(self, interaction: discord.Interaction, word: str):
        """単語を検索します"""
        if not config.is_feature_enabled('searchword'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        try:
            if word in self.dictionary:
                embed = discord.Embed(
                    title=f"🔍 {word}",
                    description=self.dictionary[word],
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed)
            else:
                # あいまい検索
                matches = get_close_matches(word, self.dictionary.keys(), n=3, cutoff=0.6)
                if matches:
                    embed = discord.Embed(
                        title="🔍 検索結果",
                        description=f"「{word}」に近い単語が見つかりました：",
                        color=discord.Color.orange()
                    )
                    for match in matches:
                        embed.add_field(
                            name=match,
                            value=self.dictionary[match],
                            inline=False
                        )
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(f"「{word}」に一致する単語が見つかりませんでした。")
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
        if not config.is_feature_enabled('deleteword'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
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
        if not config.is_feature_enabled('listwords'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
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