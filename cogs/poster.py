import discord
from discord import app_commands
from discord.ext import commands
import urllib.request
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
from PIL import Image, ImageDraw, ImageFont
import logging
import traceback
import config
import json
import os
import io

logger = logging.getLogger(__name__)

class Poster(commands.Cog):
    """
    キャラクターポスター生成コグ
    /posterコマンドでキャラクターポスターを生成します。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # config.pyからパス・フォント・チャンネルIDを取得
        self.fontA = ImageFont.truetype(config.POSTER_FONT_A, 30)
        self.fontB = ImageFont.truetype(config.POSTER_FONT_B, 40)
        self.fontC = ImageFont.truetype(config.POSTER_FONT_C, 35)
        self.fontD = ImageFont.truetype(config.POSTER_FONT_D, 115)
        self.card_path = config.POSTER_CARD_PATH
        self.mask_path = config.POSTER_MASK_PATH
        self.peaceful_path = config.POSTER_PEACEFUL_PATH
        self.brave_path = config.POSTER_BRAVE_PATH
        self.glory_path = config.POSTER_GLORY_PATH
        self.freedom_path = config.POSTER_FREEDOM_PATH
        self.dst_path = config.POSTER_DST_PATH
        self.channel_id = config.POSTER_CHANNEL_ID
        # poster_const.jsonの読み込み
        const_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'poster_const.json')
        with open(const_path, encoding='utf-8') as f:
            self.const = json.load(f)

    def _draw_poster(self, char, card, mask, peaceful, brave, glory, freedom, info):
        """
        画像合成・描画処理を分離。infoはスクレイピングで取得した情報(dict)を想定。
        """
        draw = ImageDraw.Draw(card)
        # キャラ画像合成
        char_resize_small = char.resize((round(char.width / 15), round(char.height / 15)))
        char_resize_blur = char_resize_small.resize(((2880, 2880)), resample=Image.BILINEAR)
        card.paste(char_resize_blur, (-480, -300))
        char_resize_main = char.resize((1920, 1920))
        card.paste(char_resize_main, (0, 0), mask)
        # 国旗
        flag_pos = self.const["flag_positions"].get(info['country'])
        if flag_pos:
            flag_img = {"Brave": brave, "Peaceful": peaceful, "Glory": glory, "Freedom": freedom}.get(info['country'])
            if flag_img:
                card.paste(flag_img, tuple(flag_pos))
        # 背景色
        bg_colors = self.const["background_colors"].get(info['background'], self.const["background_colors"]["default"])
        color1, color2, color3 = tuple(bg_colors[0]), tuple(bg_colors[1]), tuple(bg_colors[2])
        for rect in self.const["rectangle_areas"]:
            x1, y1, x2, y2, fill = rect
            if fill == "color1":
                fill = color1
            draw.rectangle((x1, y1, x2, y2), fill=tuple(fill))
        # 点々
        for y in self.const["dotted_lines_y"]:
            draw.text((self.const["dotted_left"]["x"], y), self.const["dotted_left"]["text"], color1, font=self.fontA)
            draw.text((self.const["dotted_right"]["x"], y), self.const["dotted_right"]["text"], color2, font=self.fontA)
        # 詳細ラベル
        for key, (x, y, label) in self.const["labels"].items():
            draw.text((x, y), label, tuple(self.const["font_colors"]["white"]), font=self.fontB)
            if key in info:
                chunk = self.const["text_chunk"].get(key)
                if chunk:
                    for i in range(0, len(info[key]), chunk):
                        draw.text((self.const["text_start_x"], y + (i * 3.5)), info[key][i:i+chunk], tuple(self.const["font_colors"]["white"]), font=self.fontB)
                else:
                    draw.text((self.const["text_start_x"], y), info[key], tuple(self.const["font_colors"]["white"]), font=self.fontB)
        # 目標
        for i in range(0, len(info['goal']), self.const["text_chunk"]["goal"]):
            draw.text((self.const["goal_text"]["x"], self.const["goal_text"]["y"] + i * self.const["goal_text"]["y_step"]), info['goal'][i:i+self.const["text_chunk"]["goal"]], tuple(self.const["font_colors"]["white"]), font=self.fontC, stroke_width=3, stroke_fill=color1)
        # 名前
        name_x = self.const["name_text"]["base_x"] - len(info['name']) * self.const["name_text"]["char_width"]
        draw.text((name_x, self.const["name_text"]["y"]), info['name'], tuple(self.const["font_colors"]["white"]), font=self.fontD, stroke_width=3, stroke_fill=color1)
        # セリフ縦書き
        lines_conf = self.const["lines_text"]
        for i in range(len(info['lines'])):
            if i <= lines_conf["block"]:
                j = 1
            elif i <= lines_conf["block"] * 2:
                j = 2
            elif i <= lines_conf["block"] * 3:
                j = 3
            elif i <= lines_conf["block"] * 4:
                j = 4
            else:
                j = 5
            x = lines_conf["base_x"] - j * lines_conf["x_step"]
            y = lines_conf["base_y"] + i * lines_conf["y_step"] - (j - 1) * lines_conf["block_y_step"] * lines_conf["block"]
            draw.text((x, y), info['lines'][i:i+1], tuple(self.const["font_colors"]["white"]), font=self.fontD, stroke_width=3, stroke_fill=color3)
        return card

    @app_commands.command(name="poster", description="キャラクターポスターを作成します")
    @app_commands.describe(number="キャラクターの番号を入力してください")
    async def poster_command(self, interaction: discord.Interaction, number: str):
        await interaction.response.send_message(
            "キャラクターカード作成中です\nカードが完成するまでコマンドを入力しないようお願いします"
        )
        driver = None
        try:
            # キャラ画像URL取得
            if len(number) <= 4:
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{number}.webp"
            else:
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{number}.png"
            try:
                urllib.request.urlretrieve(url, self.dst_path)
            except Exception as e:
                logger.error(f"画像のダウンロードに失敗: {e}")
                await interaction.followup.send("キャラクター画像の取得に失敗しました。番号が正しいかご確認ください。", ephemeral=True)
                return
            try:
                char = Image.open(self.dst_path)
                card = Image.open(self.card_path)
                mask = Image.open(self.mask_path)
                peaceful = Image.open(self.peaceful_path)
                brave = Image.open(self.brave_path)
                glory = Image.open(self.glory_path)
                freedom = Image.open(self.freedom_path)
            except Exception as e:
                logger.error(f"画像ファイルの読み込みに失敗: {e}")
                await interaction.followup.send("画像ファイルの読み込みに失敗しました。管理者に連絡してください。", ephemeral=True)
                return
            # Seleniumでキャラ情報取得
            try:
                driver = webdriver.Chrome()
                driver.get(f"https://zircon.konami.net/character/{number}")
                time.sleep(3)
                html = driver.page_source.encode("utf-8")
                soup = BeautifulSoup(html, "html.parser")
                selectors = {
                    'name': "#root > main > div > section.status > div > dl:nth-of-type(1) > dd > p",
                    'country': "#root > main > div > section.status > div > dl:nth-of-type(3) > dd > p",
                    'skill': "#root > main > div > section.status > div > dl:nth-of-type(4) > dd > p",
                    'sencetype': "#root > main > div > section.status > div > dl:nth-of-type(5) > dd > p",
                    'personality': "#root > main > div > section.status > div > dl:nth-of-type(6) > dd > p",
                    'goal': "#root > main > div > section.status > div > dl:nth-of-type(7) > dd > p",
                    'zirpower': "#root > main > div > section.status > div > dl:nth-of-type(8) > dd > p",
                    'zircongear': "#root > main > div > section.status > div > dl:nth-of-type(9) > dd > p",
                    'firstperson': "#root > main > div > section.status > div > dl:nth-of-type(10) > dd > p",
                    'nickname': "#root > main > div > section.status > div > dl:nth-of-type(11) > dd > p",
                    'lines': "#root > main > div > section.status > div > dl:nth-of-type(12) > dd > p",
                    'weakness': "#root > main > div > section.status > div > dl:nth-of-type(13) > dd > p",
                    'background': "#root > main > div > section.property > table > tbody > tr:nth-of-type(15) > td:nth-of-type(3)"
                }
                info = {}
                for key, selector in selectors.items():
                    el = soup.select_one(selector)
                    info[key] = el.text if el else ''
            except Exception as e:
                logger.error(f"Selenium/スクレイピングに失敗: {e}")
                await interaction.followup.send("キャラクター情報の取得に失敗しました。番号が正しいか、または公式サイトの仕様変更がないかご確認ください。", ephemeral=True)
                return
            try:
                poster_img = self._draw_poster(char, card, mask, peaceful, brave, glory, freedom, info)
                img_bytes = io.BytesIO()
                poster_img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
            except Exception as e:
                logger.error(f"画像合成・保存に失敗: {e}")
                await interaction.followup.send("画像の合成または保存に失敗しました。管理者に連絡してください。", ephemeral=True)
                return
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                try:
                    filename = f"poster_{number}.png"
                    await channel.send(file=discord.File(img_bytes, filename=filename))
                except Exception as e:
                    logger.error(f"Discordへの画像送信に失敗: {e}")
                    await interaction.followup.send("画像の送信に失敗しました。管理者に連絡してください。", ephemeral=True)
                    return
            else:
                await interaction.followup.send("チャンネルが見つかりませんでした。", ephemeral=True)
        except Exception as e:
            logger.error(f"予期せぬエラー: {e}")
            logger.error(traceback.format_exc())
            await interaction.followup.send("エラーが発生しました。管理者に連絡してください。", ephemeral=True)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Seleniumドライバの終了に失敗: {e}")

async def setup(bot: commands.Bot):
    try:
        await bot.add_cog(Poster(bot))
        logger.info("Poster cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load Poster cog: {e}")
        logger.error(traceback.format_exc())
        raise
