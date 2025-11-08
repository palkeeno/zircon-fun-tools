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
        self.birthdays = []
        self.birthday_task_started = False
        self.reported_flag_reset_task_started = False
        self.load_birthdays()

    @commands.Cog.listener()
    async def on_ready(self):
        """ボットの準備が完了したときに誕生日タスクを開始します（常時）。"""
        if not self.birthday_task_started:
            self.birthday_task.start()
            self.birthday_task_started = True
        if not self.reported_flag_reset_task_started:
            self.reported_flag_reset_task.start()
            self.reported_flag_reset_task_started = True

    @tasks.loop(hours=24)
    async def birthday_task(self):
        """毎日誕生日をチェックして通知するタスク"""
        now = datetime.datetime.now()
        today_month = now.month
        today_day = now.day
        
        # 今日誕生日の人を抽出
        today_birthdays = [b for b in self.birthdays if b["month"] == today_month and b["day"] == today_day]
        if not today_birthdays:
            return
        try:
            channel_id = config.get_birthday_channel_id()
            if not channel_id:
                logger.warning("誕生日チャンネルIDが設定されていません")
                return
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                logger.error(f"誕生日チャンネルが見つかりません: {channel_id}")
                return
            # 報告済みでない人のみアナウンス
            unreported_birthdays = [b for b in today_birthdays if not b.get("reported", False)]
            if not unreported_birthdays:
                return
            # 重複（同じ名前・同じ日付）があるユーザは除外
            unique = {}
            for b in unreported_birthdays:
                key = (b["name"], b["month"], b["day"])
                if key not in unique:
                    unique[key] = [b]
                else:
                    unique[key].append(b)
            announce_names = []
            announce_birthdays = []
            for key, items in unique.items():
                if len(items) == 1:
                    announce_names.append(items[0]["name"])
                    announce_birthdays.append(items[0])
            if not announce_names:
                return
            names = ', '.join(announce_names)
            msg = f"🎉 今日は {names} さんの誕生日です！おめでとうございます！ 🎉"
            await channel.send(msg)
            # 報告済みフラグをセット
            for b in announce_birthdays:
                b["reported"] = True
            self.save_birthdays()
        except Exception as e:
            logger.error(f"Error in birthday_task: {e}")
            logger.error(traceback.format_exc())

    @tasks.loop(hours=24)
    async def reported_flag_reset_task(self):
        """毎日9時に報告済みフラグをリセットするタスク"""
        now = datetime.datetime.now()
        # 9時以降のみ実行
        if now.hour < 9:
            return
        today_month = now.month
        today_day = now.day
        changed = False
        for b in self.birthdays:
            # 今日以外の誕生日はフラグを外す
            if b.get("reported", False) and not (b["month"] == today_month and b["day"] == today_day):
                b["reported"] = False
                changed = True
        if changed:
            self.save_birthdays()

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
                # reportedフラグがない場合はFalseで初期化
                for b in self.birthdays:
                    if "reported" not in b:
                        b["reported"] = False
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
        name="removebirthday",
        description="登録されている誕生日を名前で削除します"
    )
    @app_commands.describe(
        name="削除したい名前"
    )
    async def remove_birthday(self, interaction: discord.Interaction, name: str):
        """
        名前で誕生日を削除。複数候補時はリスト表示し、番号指定で削除。
        
        Args:
            interaction (discord.Interaction): インタラクション
            name (str): 削除したい名前
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'removebirthday'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # 候補抽出
            candidates = [b for b in self.birthdays if name in b["name"]]
            if not candidates:
                await interaction.response.send_message(
                    "該当する誕生日はありません。",
                    ephemeral=True
                )
                return
                
            if len(candidates) == 1:
                self.birthdays.remove(candidates[0])
                self.save_birthdays()
                await interaction.response.send_message(
                    f"{candidates[0]['name']}({candidates[0]['month']}月{candidates[0]['day']}日) の誕生日を削除しました。",
                    ephemeral=True
                )
                return

            # 複数候補時はリスト表示し、番号指定を待つ
            msg = "複数該当があります。削除したい番号を返信してください:\n"
            for idx, b in enumerate(candidates, 1):
                msg += f"{idx}. {b['name']}({b['month']}月{b['day']}日)\n"
            await interaction.response.send_message(msg, ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

            try:
                reply = await self.bot.wait_for('message', check=check, timeout=30)
                num = int(reply.content)
                if 1 <= num <= len(candidates):
                    self.birthdays.remove(candidates[num-1])
                    self.save_birthdays()
                    await interaction.followup.send(
                        f"{candidates[num-1]['name']}({candidates[num-1]['month']}月{candidates[num-1]['day']}日) の誕生日を削除しました。",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send("無効な番号です。削除を中止しました。", ephemeral=True)
            except Exception:
                await interaction.followup.send("番号の返信がなかったため削除を中止しました。", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in remove_birthday: {e}")
            logger.error(traceback.format_exc())
            await interaction.response.send_message(
                "エラーが発生しました。もう一度お試しください。",
                ephemeral=True
            )

    @app_commands.command(
        name="addbirthday",
        description="誕生日を登録します"
    )
    @app_commands.describe(
        name="登録する名前",
        month="月（1-12）",
        day="日（1-31）"
    )
    async def add_birthday(self, interaction: discord.Interaction, name: str, month: int, day: int):
        """
        誕生日を登録します。名前＋月日で保存。
        
        Args:
            interaction (discord.Interaction): インタラクション
            name (str): 名前
            month (int): 月
            day (int): 日
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'addbirthday'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
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

            # データ追加
            self.birthdays.append({
                "name": name,
                "month": month,
                "day": day,
                "reported": False
            })
            self.save_birthdays()

            await interaction.response.send_message(
                f"誕生日を登録しました：{name} {month}月{day}日",
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
    @app_commands.describe(
        name="名前で絞り込み（オプション）"
    )
    async def list_birthdays(self, interaction: discord.Interaction, name: str = None):
        """
        登録されている誕生日の一覧を表示します。引数nameでフィルタ可能。
        Args:
            interaction (discord.Interaction): インタラクション
            name (str, optional): 名前で絞り込み
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthdays'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # nameでフィルタ
            if name:
                filtered = [b for b in self.birthdays if name in b["name"]]
            else:
                filtered = self.birthdays

            if not filtered:
                await interaction.response.send_message(
                    "該当する誕生日はありません。",
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
                filtered,
                key=lambda x: (x["month"], x["day"])
            )
            for b in sorted_birthdays:
                embed.add_field(
                    name=b["name"],
                    value=f"{b['month']}月{b['day']}日",
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