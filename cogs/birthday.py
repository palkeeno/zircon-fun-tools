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
import urllib.request
import io
from PIL import Image
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

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
            # 同じ日付の別名もまとめず、1人ずつ個別に発表
            # ただし、同じid_or_name・同じ日付が複数ある場合はスキップ
            unique = {}
            for b in unreported_birthdays:
                key = (b.get("id_or_name"), b["month"], b["day"])
                if key not in unique:
                    unique[key] = [b]
                else:
                    unique[key].append(b)
            for key, items in unique.items():
                if len(items) == 1:
                    b = items[0]
                    await self._announce_birthday(channel, b)
                    b["reported"] = True
            self.save_birthdays()
        except Exception as e:
            logger.error(f"Error in birthday_task: {e}")
            logger.error(traceback.format_exc())

    async def _announce_birthday(self, channel, birthday_data):
        """誕生日を発表する（type別処理）"""
        btype = birthday_data.get("type", 3)
        id_or_name = birthday_data.get("id_or_name", "")
        month = birthday_data.get("month")
        day = birthday_data.get("day")

        try:
            if btype == 1:
                # Discordユーザ
                await self._announce_discord_user(channel, id_or_name, month, day)
            elif btype == 2:
                # Zirconキャラクター
                await self._announce_zircon_character(channel, id_or_name, month, day)
            else:
                # その他
                await self._announce_other(channel, id_or_name, month, day)
        except Exception as e:
            logger.error(f"Error in _announce_birthday: {e}")
            logger.error(traceback.format_exc())

    async def _announce_discord_user(self, channel, id_or_name, month, day):
        """Discordユーザの誕生日を発表"""
        try:
            # id_or_nameが数字ならID、それ以外は名前として扱う
            user = None
            if id_or_name.isdigit():
                # IDで検索
                user_id = int(id_or_name)
                user = channel.guild.get_member(user_id)
            else:
                # 名前で検索
                for member in channel.guild.members:
                    if member.name == id_or_name or member.display_name == id_or_name:
                        user = member
                        break
            
            if not user:
                # サーバーメンバーで見つからない場合はアナウンスしない
                logger.info(f"Discordユーザ {id_or_name} がサーバーメンバーに見つかりませんでした。")
                return

            # Embed作成
            embed = discord.Embed(
                title="🎉 誕生日おめでとう！ 🎉",
                description=f"{user.mention} さんの誕生日です！",
                color=discord.Color.gold()
            )
            embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"素敵な一日をお過ごしください！")
            
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in _announce_discord_user: {e}")
            logger.error(traceback.format_exc())

    async def _announce_zircon_character(self, channel, number, month, day):
        """Zirconキャラクターの誕生日を発表"""
        driver = None
        try:
            # キャラ名取得（Selenium）
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(f"https://zircon.konami.net/nft/character/{number}")
            import time
            time.sleep(2)
            html = driver.page_source.encode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            name_elem = soup.select_one("#root > main > div > section.status > div > dl:nth-of-type(1) > dd > p")
            char_name = name_elem.text if name_elem else f"キャラクター #{number}"
            
            # 画像取得
            if number.isdigit() and int(number) <= 1000:
                # webp形式
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{number}.webp"
                temp_path = f"temp_{number}.webp"
                urllib.request.urlretrieve(url, temp_path)
                img = Image.open(temp_path)
                img = img.convert('RGB')
                png_path = f"temp_{number}.png"
                img.save(png_path, 'PNG')
                os.remove(temp_path)
            else:
                # png形式
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{number}.png"
                png_path = f"temp_{number}.png"
                urllib.request.urlretrieve(url, png_path)
            
            # Embed作成
            embed = discord.Embed(
                title="🎉 誕生日おめでとう！ 🎉",
                description=f"**{char_name}** の誕生日です！",
                color=discord.Color.blue()
            )
            embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=False)
            embed.add_field(name="キャラクター番号", value=number, inline=False)
            embed.set_footer(text=f"Zirconキャラクター")
            
            # 画像をアップロードしてサムネイルに設定
            with open(png_path, 'rb') as f:
                file = discord.File(f, filename=f"{number}.png")
                embed.set_thumbnail(url=f"attachment://{number}.png")
                await channel.send(embed=embed, file=file)
            
            # 一時ファイル削除
            os.remove(png_path)
            
        except Exception as e:
            logger.error(f"Error in _announce_zircon_character: {e}")
            logger.error(traceback.format_exc())
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    async def _announce_other(self, channel, name, month, day):
        """その他の誕生日を発表"""
        try:
            embed = discord.Embed(
                title="🎉 誕生日おめでとう！ 🎉",
                description=f"**{name}** さんの誕生日です！",
                color=discord.Color.pink()
            )
            embed.add_field(name="誕生日", value=f"{month}月{day}日", inline=False)
            embed.set_footer(text=f"素敵な一日をお過ごしください！")
            
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in _announce_other: {e}")
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
        description="登録されている誕生日を名前/IDで削除します"
    )
    @app_commands.describe(
        search="削除したい名前/ID"
    )
    async def remove_birthday(self, interaction: discord.Interaction, search: str):
        """
        名前/IDで誕生日を削除。複数候補時はリスト表示し、番号指定で削除。
        
        Args:
            interaction (discord.Interaction): インタラクション
            search (str): 削除したい名前/ID
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
            candidates = [b for b in self.birthdays if search in b.get("id_or_name", "")]
            if not candidates:
                await interaction.response.send_message(
                    "該当する誕生日はありません。",
                    ephemeral=True
                )
                return
                
            if len(candidates) == 1:
                self.birthdays.remove(candidates[0])
                self.save_birthdays()
                type_label = {1: "Discordユーザ", 2: "Zirconキャラクター", 3: "その他"}
                btype = candidates[0].get("type", 3)
                await interaction.response.send_message(
                    f"{candidates[0]['id_or_name']}({candidates[0]['month']}月{candidates[0]['day']}日)[{type_label[btype]}] の誕生日を削除しました。",
                    ephemeral=True
                )
                return

            # 複数候補時はリスト表示し、番号指定を待つ
            msg = "複数該当があります。削除したい番号を返信してください:\n"
            type_label = {1: "Discordユーザ", 2: "Zirconキャラクター", 3: "その他"}
            for idx, b in enumerate(candidates, 1):
                btype = b.get("type", 3)
                msg += f"{idx}. {b['id_or_name']}({b['month']}月{b['day']}日)[{type_label[btype]}]\n"
            await interaction.response.send_message(msg, ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

            try:
                reply = await self.bot.wait_for('message', check=check, timeout=30)
                num = int(reply.content)
                if 1 <= num <= len(candidates):
                    self.birthdays.remove(candidates[num-1])
                    self.save_birthdays()
                    btype = candidates[num-1].get("type", 3)
                    await interaction.followup.send(
                        f"{candidates[num-1]['id_or_name']}({candidates[num-1]['month']}月{candidates[num-1]['day']}日)[{type_label[btype]}] の誕生日を削除しました。",
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
        type="1=Discordユーザ, 2=Zirconキャラクター, 3=その他",
        id_or_name="DiscordユーザID/名前、Zircon番号、またはその他の名前",
        month="月（1-12）",
        day="日（1-31）"
    )
    async def add_birthday(self, interaction: discord.Interaction, id_or_name: str, month: int, day: int, type: int):
        """
        誕生日を登録します。
        
        Args:
            interaction (discord.Interaction): インタラクション
            id_or_name (str): ID/名前
            month (int): 月
            day (int): 日
            type (int): 1=Discord, 2=Zircon, 3=その他
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'addbirthday'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # typeのバリデーション
            if type not in [1, 2, 3]:
                await interaction.response.send_message(
                    "typeは1（Discordユーザ）, 2（Zirconキャラクター）, 3（その他）のいずれかを指定してください。",
                    ephemeral=True
                )
                return
            
            # 日付のバリデーション
            if not (1 <= month <= 12 and 1 <= day <= 31):
                await interaction.response.send_message(
                    "無効な日付です。月は1-12、日は1-31の範囲で指定してください。",
                    ephemeral=True
                )
                return

            # データ追加
            self.birthdays.append({
                "id_or_name": id_or_name,
                "month": month,
                "day": day,
                "reported": False,
                "type": type
            })
            self.save_birthdays()

            type_label = {1: "Discordユーザ", 2: "Zirconキャラクター", 3: "その他"}
            await interaction.response.send_message(
                f"誕生日を登録しました：{id_or_name} {month}月{day}日 [{type_label[type]}]",
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
        search="名前/IDで絞り込み（オプション）"
    )
    async def list_birthdays(self, interaction: discord.Interaction, search: str = None):
        """
        登録されている誕生日の一覧を表示します。引数searchでフィルタ可能。
        Args:
            interaction (discord.Interaction): インタラクション
            search (str, optional): 名前/IDで絞り込み
        """
        # 権限チェック
        if not permissions.can_run_command(interaction, 'birthdays'):
            await interaction.response.send_message(
                "このコマンドを実行する権限がありません。管理者にお問い合わせください。",
                ephemeral=True
            )
            return

        try:
            # searchでフィルタ
            if search:
                filtered = [b for b in self.birthdays if search in b.get("id_or_name", "")]
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
            type_label = {1: "Discordユーザ", 2: "Zirconキャラクター", 3: "その他"}
            for b in sorted_birthdays:
                btype = b.get("type", 3)
                embed.add_field(
                    name=f"{b['id_or_name']} [{type_label[btype]}]",
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