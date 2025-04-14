"""
おみくじ機能を実装するCog
このモジュールは、おみくじ機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
import traceback
import json
import asyncio
from datetime import datetime
from pathlib import Path
import config

# ロギングの設定
logger = logging.getLogger(__name__)

# データファイルのパス
DATA_DIR = Path(__file__).parent.parent / "data"
FORTUNE_DATA_PATH = DATA_DIR / "fortune_data.json"
LUCKY_ITEMS_PATH = DATA_DIR / "lucky_items.json"
LUCKY_COLORS_PATH = DATA_DIR / "lucky_colors.json"

class Fortune(commands.Cog):
    """
    おみくじ機能を提供するCog
    """
    
    def __init__(self, bot: commands.Bot):
        """
        初期化処理
        
        Args:
            bot (commands.Bot): Discordボットのインスタンス
        """
        self.bot = bot
        self.load_data()
        logger.info("Fortune cog initialized")

    def load_data(self):
        """データファイルを読み込む"""
        try:
            # 運勢データの読み込み
            with open(FORTUNE_DATA_PATH, "r", encoding="utf-8") as f:
                self.fortunes = json.load(f)
            
            # ラッキーアイテムの読み込み
            with open(LUCKY_ITEMS_PATH, "r", encoding="utf-8") as f:
                self.lucky_items = json.load(f)["items"]
            
            # ラッキーカラーの読み込み
            with open(LUCKY_COLORS_PATH, "r", encoding="utf-8") as f:
                self.lucky_colors = json.load(f)["colors"]
            
            # 色のマッピング
            self.color_map = {
                "gold": discord.Color.gold(),
                "green": discord.Color.green(),
                "blue": discord.Color.blue(),
                "teal": discord.Color.teal(),
                "dark_teal": discord.Color.dark_teal(),
                "orange": discord.Color.orange(),
                "red": discord.Color.red()
            }
            
        except Exception as e:
            logger.error(f"データファイルの読み込み中にエラーが発生しました: {e}")
            raise

    async def show_animation(self, interaction: discord.Interaction):
        """
        おみくじを引く際のアニメーションを表示する
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        # 初期メッセージを送信
        embed = discord.Embed(
            title="🎋 おみくじを引いています...",
            description="🔮 運勢を占っています...",
            color=discord.Color.blue()
        )
        message = await interaction.response.send_message(embed=embed)
        
        # アニメーションのステップ
        steps = [
            ("🎋 おみくじを引いています...", "🔮 運勢を占っています...", 0),
            ("🎋 → 🎋 → 🎋", "🔮 → 🔮 → 🔮", 25),
            ("🎋 → 🎋 → 🎋 → 🎋", "🔮 → 🔮 → 🔮 → 🔮", 50),
            ("🎋 → 🎋 → 🎋 → 🎋 → 🎋", "🔮 → 🔮 → 🔮 → 🔮 → 🔮", 75),
            ("✨ 結果が出ました！", "✨ 結果が出ました！", 100)
        ]
        
        # 各ステップを表示
        for title, description, progress in steps:
            # プログレスバーを作成
            progress_bar = self.create_progress_bar(progress)
            
            # メッセージを更新
            embed = discord.Embed(
                title=title,
                description=f"{description}\n\n{progress_bar}",
                color=discord.Color.blue()
            )
            await interaction.edit_original_response(embed=embed)
            
            # 待機時間
            await asyncio.sleep(1)

    def create_progress_bar(self, progress: int) -> str:
        """
        プログレスバーを作成する
        
        Args:
            progress (int): 進捗率（0-100）
            
        Returns:
            str: プログレスバーの文字列
        """
        bar_length = 20
        filled_length = int(bar_length * progress / 100)
        bar = "=" * filled_length + " " * (bar_length - filled_length)
        return f"[{bar}] {progress}%"

    @app_commands.command(name="fortune", description="おみくじを引きます")
    async def draw_omikuji(self, interaction: discord.Interaction):
        """おみくじを引きます"""
        # アニメーションを表示
        await self.show_animation(interaction)

        # 運勢を抽選
        total = sum(f["rate"] for f in self.fortunes.values())
        r = random.uniform(0, total)
        current = 0
        selected_fortune = None

        for fortune_name, fortune in self.fortunes.items():
            current += fortune["rate"]
            if r <= current:
                selected_fortune = fortune_name
                break

        if not selected_fortune:
            selected_fortune = "凶"

        fortune = self.fortunes[selected_fortune]
        
        # ランダムな説明、アドバイス、健康運、恋愛運、仕事運を選択
        description = random.choice(fortune["descriptions"])
        advice = random.choice(fortune["advice"])
        health = random.choice(fortune["health"])
        love = random.choice(fortune["love"])
        work = random.choice(fortune["work"])

        # ラッキーアイテム、ラッキーカラー、ラッキーナンバーを抽選
        lucky_item = random.choice(self.lucky_items)
        lucky_color = random.choice(self.lucky_colors)
        lucky_number = random.randint(1, 9)

        # 埋め込みメッセージを作成
        embed = discord.Embed(
            title=f"✨ {selected_fortune} ✨",
            description=description,
            color=self.color_map[fortune["color"]]
        )
        embed.add_field(name="アドバイス", value=advice, inline=False)
        embed.add_field(name="健康運", value=health, inline=True)
        embed.add_field(name="恋愛運", value=love, inline=True)
        embed.add_field(name="仕事運", value=work, inline=True)
        embed.add_field(name="ラッキーアイテム", value=lucky_item, inline=True)
        embed.add_field(name="ラッキーカラー", value=lucky_color, inline=True)
        embed.add_field(name="ラッキーナンバー", value=str(lucky_number), inline=True)
        embed.set_footer(text=f"引いた日: {datetime.now().strftime('%Y年%m月%d日')}")

        await interaction.edit_original_response(embed=embed)

async def setup(bot: commands.Bot):
    """
    Cogをボットに追加する関数
    
    Args:
        bot (commands.Bot): Discordボットのインスタンス
    """
    try:
        await bot.add_cog(Fortune(bot))
        logger.info("Fortune cogが正常に追加されました")
    except Exception as e:
        logger.error(f"Fortune cogの追加中にエラーが発生しました: {e}\n{traceback.format_exc()}")
        raise 