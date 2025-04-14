"""
誕生日管理のコグ
このモジュールは、誕生日の管理機能を提供します。
"""

import discord
from discord import app_commands
from discord.ext import commands
import json
import logging
import traceback
import config

# ロギングの設定
logger = logging.getLogger(__name__)

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
        self.birthdays = {}
        self.load_birthdays()

    def load_birthdays(self):
        """誕生日データを読み込みます"""
        try:
            with open("data/birthdays.json", "r", encoding="utf-8") as f:
                self.birthdays = json.load(f)
        except FileNotFoundError:
            self.birthdays = {}
        except Exception as e:
            logger.error(f"Error loading birthdays: {e}")
            logger.error(traceback.format_exc())
            self.birthdays = {}

    def save_birthdays(self):
        """誕生日データを保存します"""
        try:
            with open("data/birthdays.json", "w", encoding="utf-8") as f:
                json.dump(self.birthdays, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving birthdays: {e}")
            logger.error(traceback.format_exc())

    @app_commands.command(
        name="addbirthday",
        description="誕生日を登録します"
    )
    @app_commands.describe(
        month="月（1-12）",
        day="日（1-31）"
    )
    async def add_birthday(self, interaction: discord.Interaction, month: int, day: int):
        """
        誕生日を登録します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            month (int): 月
            day (int): 日
        """
        if not config.is_feature_enabled('addbirthday'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
                ephemeral=True
            )
            return

        try:
            # 日付のバリデーション
            if not (1 <= month <= 12 and 1 <= day <= 31):
                await interaction.response.send_message(
                    "無効な日付です。月は1-12、日は1-31の範囲で指定してください。",
                    ephemeral=True
                )
                return

            user_id = str(interaction.user.id)
            self.birthdays[user_id] = {
                "month": month,
                "day": day
            }
            self.save_birthdays()

            await interaction.response.send_message(
                f"誕生日を登録しました：{month}月{day}日",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in add_birthday: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="birthdays",
        description="登録されている誕生日の一覧を表示します"
    )
    async def list_birthdays(self, interaction: discord.Interaction):
        """
        登録されている誕生日の一覧を表示します。
        
        Args:
            interaction (discord.Interaction): インタラクション
        """
        if not config.is_feature_enabled('birthdays'):
            await interaction.response.send_message(
                "このコマンドは現在無効化されています。",
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

            embed = discord.Embed(
                title="🎂 誕生日一覧",
                description="登録されている誕生日の一覧です",
                color=discord.Color.pink()
            )

            # 月日でソート
            sorted_birthdays = sorted(
                self.birthdays.items(),
                key=lambda x: (x[1]["month"], x[1]["day"])
            )

            for user_id, birthday in sorted_birthdays:
                user = await self.bot.fetch_user(int(user_id))
                embed.add_field(
                    name=user.name,
                    value=f"{birthday['month']}月{birthday['day']}日",
                    inline=False
                )

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in list_birthdays: {e}")
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
        await bot.add_cog(Birthday(bot))
        logger.info("Birthday cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Birthday cog: {e}")
        logger.error(traceback.format_exc())
        raise 