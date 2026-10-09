import discord
from discord import app_commands
from discord.ext import commands
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from PIL import Image, ImageDraw, ImageFont
import logging
import traceback
import config
import platform
import math
import asyncio
import hashlib
from pathlib import Path
from functools import lru_cache
from poster_cache import PosterCache
import setup_fonts

import os
import io
from contextlib import ExitStack
import tempfile
from image_cache import download_bytes

logger = logging.getLogger(__name__)

class Poster(commands.Cog):
    """
    キャラクターポスター生成コグ
    /posterコマンドでキャラクターポスターを生成します。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # config.pyからパスを取得
        self.mask_path = config.POSTER_MASK_PATH
        self.peaceful_path = config.POSTER_PEACEFUL_PATH
        self.brave_path = config.POSTER_BRAVE_PATH
        self.glory_path = config.POSTER_GLORY_PATH
        self.freedom_path = config.POSTER_FREEDOM_PATH
        self._queue = asyncio.Queue(maxsize=config.POSTER_QUEUE_LIMIT)
        self._workers = []
        self._inflight = {}
        self._cache = PosterCache(Path(config._DATA_DIR) / "cache" / "posters", config.POSTER_CACHE_TTL)
        import threading
        self._render_locks = [threading.Lock() for _ in range(32)]
        
        # 画像アセットの存在確認
        self._check_assets()
        logger.info("Poster が初期化されました")
    
    def _check_assets(self):
        """オプション画像アセットの存在を確認し、情報を出力する"""
        optional_assets = {
            'mask.png': self.mask_path,
            'peaceful.png': self.peaceful_path,
            'brave.png': self.brave_path,
            'glory.png': self.glory_path,
            'freedom.png': self.freedom_path,
        }
        
        missing = []
        for name, path in optional_assets.items():
            if not os.path.exists(path):
                missing.append(name)
        
        if missing:
            logger.info("ℹ️ 以下のオプション画像アセットが見つかりません（処理は続行されます）:")
            for item in missing:
                logger.info(f"  - {item}")
            logger.info("必要に応じて data/assets/ ディレクトリに画像ファイルを配置してください。")
    @lru_cache(maxsize=128)
    def _try_load_font(self, prefer_path: str, size: int):
        path = setup_fonts.find_japanese_font(prefer_path)
        if not path:
            raise ValueError("日本語フォントがありません。事前にpython setup_fonts.py --prepareを実行してください")
        return ImageFont.truetype(path, size)

    def _draw_text_with_glow(self, draw: ImageDraw.Draw, text: str, x: int, y: int, 
                             font: ImageFont.FreeTypeFont, glow_layers: list, 
                             main_color: tuple = (255, 255, 255)) -> None:
        """
        グロー（光彩）効果付きでテキストを描画する
        
        Args:
            draw: ImageDrawオブジェクト
            text: 描画するテキスト
            x: X座標
            y: Y座標
            font: フォント
            glow_layers: グロー効果のレイヤー設定 [(radius, (r, g, b, a)), ...]
            main_color: メインテキストの色 (デフォルト: 白)
        """
        # グロー効果を描画
        for radius, color in glow_layers:
            for angle in range(0, 360, 30):  # 12方向
                dx = int(radius * math.cos(math.radians(angle)))
                dy = int(radius * math.sin(math.radians(angle)))
                draw.text((x + dx, y + dy), text, fill=color, font=font)
        
        # 本体を描画
        draw.text((x, y), text, fill=main_color, font=font)

    def _draw_poster(self, char, mask, info):
        """
        新仕様：1600×2100pxのポスター画像を生成
        """
        
        # 1. 1600×2100pxのキャンバスを生成
        canvas = Image.new('RGB', (1600, 2100), color=(255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        # 2. キャラクター画像を上揃えで配置（1600×1600にリサイズ）
        char_resized = char.resize((1600, 1600))
        canvas.paste(char_resized, (0, 0))
        
        # 3. マスク画像の適用（存在する場合）
        # 仕様: キャラクター画像と文字（および後続の描画）との間に重ねる
        # マスクはキャンバス全体(1600x2100)にフィット
        if mask and os.path.exists(self.mask_path):
            try:
                mask_resized = mask.resize((1640, 2140))
                # 透明PNGをそのままオーバーレイ
                canvas.paste(mask_resized, (-20, -20), mask_resized)
            except Exception as e:
                logger.warning(f"マスク適用に失敗: {e}")
        
        # フォント読み込み
        font_name = self._try_load_font(config.POSTER_FONT_C, 80)
        
        # 国旗画像の読み込み（描画はテキストの直前に行う）
        country_raw = info.get('country', '') or ''
        country_clean = country_raw.strip()
        flag_img = None
        if country_clean:
            # 探索候補: 元文字列, lower, title, capitalize
            variants = []
            seen = set()
            for v in [country_clean, country_clean.lower(), country_clean.title(), country_clean.capitalize()]:
                if v and v not in seen:
                    variants.append(v)
                    seen.add(v)
            assets_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'assets')
            for base in variants:
                candidate = os.path.join(assets_dir, f"{base}.png")
                if os.path.exists(candidate):
                    try:
                        with Image.open(candidate) as flag_source:
                            flag_img = flag_source.copy()
                        logger.info(f"国旗画像を読み込みました: {candidate}")
                        break
                    except Exception as e:
                        logger.warning(f"国旗画像の読み込みに失敗 ({candidate}): {e}")
        
        # 6. セリフ（lines）を縦書きで右揃え（50, 100）から（350, 1400）に列折り返し表示
        lines_text = info.get('lines', '')
        if lines_text:
            # lines用のフォントサイズを文字数に応じて調整
            lines_length = len(lines_text)
            if lines_length <= 8:
                font_lines = self._try_load_font(config.POSTER_FONT_D, 120)
            elif lines_length <= 12:
                font_lines = self._try_load_font(config.POSTER_FONT_D, 100)
            else:
                font_lines = self._try_load_font(config.POSTER_FONT_D, 80)
            
            # 表示領域
            x_left, x_right = 50, 350
            y_top, y_bottom = 100, 1400
            column_gap = 10

            # フィットするまでフォントサイズを下げて試す（最大120 → 最小40）
            chosen = None
            for size in [120, 110, 100, 90, 80, 70, 60, 50, 40]:
                f = self._try_load_font(config.POSTER_FONT_D, size)
                # 代表文字でサイズ計測（縦書き用の概算）
                sample_bbox = draw.textbbox((0, 0), '漢', font=f)
                char_w = sample_bbox[2] - sample_bbox[0]
                char_h = sample_bbox[3] - sample_bbox[1]
                char_spacing = int(char_h * 1.05)

                # 1列に入る行数と必要列数
                rows_per_col = max(1, (y_bottom - y_top) // char_spacing)
                needed_cols = (len(lines_text) + rows_per_col - 1) // rows_per_col
                max_cols = max(1, (x_right - x_left) // (char_w + column_gap))

                if needed_cols <= max_cols:
                    chosen = (f, char_w, char_h, char_spacing, rows_per_col)
                    break

            # それでも入らなければ、最小サイズで詰め込み（はみ出しは許容せず省略しないよう列幅計算を緩める）
            if not chosen:
                f = self._try_load_font(config.POSTER_FONT_D, 40)
                sample_bbox = draw.textbbox((0, 0), '漢', font=f)
                char_w = sample_bbox[2] - sample_bbox[0]
                char_h = sample_bbox[3] - sample_bbox[1]
                char_spacing = int(char_h * 0.95)
                rows_per_col = max(1, (y_bottom - y_top) // char_spacing)
                chosen = (f, char_w, char_h, char_spacing, rows_per_col)

            font_lines, char_w, char_h, char_spacing, rows_per_col = chosen

            # 右端から左方向へ列を積む
            col = 0
            x_col_right = x_right - col * (char_w + column_gap)
            y_cursor = y_top
            for idx, ch in enumerate(lines_text):
                # 改行判定（列折り返し）
                if (idx > 0) and (idx % rows_per_col == 0):
                    col += 1
                    x_col_right = x_right - col * (char_w + column_gap)
                    y_cursor = y_top

                # 列が領域外に出たら終了（理論上、フォント調整で入る想定）
                if x_col_right - char_w < x_left:
                    break

                # 各文字の実幅で右揃えオフセット調整
                cb = draw.textbbox((0, 0), ch, font=font_lines)
                cw = cb[2] - cb[0]
                x_draw = x_col_right - cw
                y_draw = y_cursor

                # グロー（光彩）効果付きで描画
                glow_layers = [
                    (8, (80, 80, 80, 255)),    # 最外層
                    (6, (95, 95, 95, 255)),    # 外層
                    (4, (110, 110, 110, 255)), # 中層
                    (2, (130, 130, 130, 255)), # 内層
                ]
                self._draw_text_with_glow(draw, ch, x_draw, y_draw, font_lines, glow_layers)

                y_cursor += char_spacing
        
        # 7. 名前を中央揃え（100, 1400）から（1500, 1500）
        name = info.get('name', '')
        if name:
            # テキストサイズを取得して中央揃え
            bbox = draw.textbbox((0, 0), name, font=font_name)
            text_width = bbox[2] - bbox[0]
            x_center = 100 + (1400 - text_width) // 2
            y_pos = 1420

            # グロー（光彩）効果付きで描画
            glow_layers = [
                (8, (80, 80, 80, 255)),    # 最外層
                (6, (95, 95, 95, 255)),    # 外層
                (4, (110, 110, 110, 255)), # 中層
                (2, (130, 130, 130, 255)), # 内層
            ]
            self._draw_text_with_glow(draw, name, x_center, y_pos, font_name, glow_layers)
        
        # 目標（goal）を領域中央揃えで配置（850, 1500）から（1550, 2050）
        goal = info.get('goal', '')
        if goal:
            # 領域定義
            goal_x_left, goal_x_right = 850, 1550
            goal_y_top, goal_y_bottom = 1500, 2050
            goal_width = goal_x_right - goal_x_left
            goal_height = goal_y_bottom - goal_y_top
            
            # 最大80pxから順にサイズを試して、領域に収まる最大サイズを見つける
            best_font = None
            best_lines = []
            best_total_height = 0

            for font_size in range(80, 19, -5):  # 80→75→70...→20
                test_font = self._try_load_font(config.POSTER_FONT_A, font_size)
                line_height = int(font_size * 1.3)
                
                # テキストを行に分割
                lines = []
                current_line = ""
                
                for ch in goal:
                    test_line = current_line + ch
                    bbox = draw.textbbox((0, 0), test_line, font=test_font)
                    line_width = bbox[2] - bbox[0]
                    
                    if line_width > goal_width:
                        if current_line:
                            lines.append(current_line)
                            current_line = ch
                        else:
                            # 1文字でも幅を超える場合はそのまま追加
                            lines.append(ch)
                            current_line = ""
                    else:
                        current_line = test_line
                
                if current_line:
                    lines.append(current_line)
                
                # 総高さチェック
                total_height = len(lines) * line_height
                
                if total_height <= goal_height:
                    best_font = test_font
                    best_lines = lines
                    best_total_height = total_height
                    best_line_height = line_height
                    break
            
            # フォントが見つからない場合は最小サイズで強制的に描画
            if not best_font:
                best_font = self._try_load_font(config.POSTER_FONT_A, 20)
                best_line_height = 26
                best_lines = []
                current_line = ""
                
                for ch in goal:
                    test_line = current_line + ch
                    bbox = draw.textbbox((0, 0), test_line, font=best_font)
                    line_width = bbox[2] - bbox[0]
                    
                    if line_width > goal_width:
                        if current_line:
                            best_lines.append(current_line)
                            current_line = ch
                        else:
                            best_lines.append(ch)
                            current_line = ""
                    else:
                        current_line = test_line
                
                if current_line:
                    best_lines.append(current_line)
                
                best_total_height = len(best_lines) * best_line_height
            
            # 垂直方向の中央揃え
            y_offset = (goal_height - best_total_height) // 2
            y_current = goal_y_top + y_offset
            
            # 各行を描画（水平方向も中央揃え）
            for line in best_lines:
                bbox = draw.textbbox((0, 0), line, font=best_font)
                line_width = bbox[2] - bbox[0]
                x_centered = goal_x_left + (goal_width - line_width) // 2

                # グロー（光彩）効果付きで描画（青み系）
                glow_layers = [
                    (8, (100, 100, 150, 255)),  # 最外層（薄い青み）
                    (6, (120, 120, 170, 255)),  # 外層
                    (4, (140, 140, 190, 255)),  # 中層
                    (2, (160, 160, 210, 255)),  # 内層
                ]
                self._draw_text_with_glow(draw, line, x_centered, y_current, best_font, glow_layers)

                y_current += best_line_height
        
        # その他の情報をテーブル形式で配置（50, 1500）から（800, 2100）
        info_items = [
            ('スキル', info.get('skill', '')),
            ('センスタイプ', info.get('sencetype', '')),
            ('性格', info.get('personality', '')),
            ('ジルパワー', info.get('zirpower', '')),
            ('ジルコンギア', info.get('zircongear', '')),
            ('一人称', info.get('firstperson', '')),
            ('愛称/ニックネーム', info.get('nickname', '')),
            ('弱み', info.get('weakness', ''))
        ]
        
        x_start = 50
        y_start = 1520
        row_height = 65
        label_width = 250
        value_width = 500
        font_table = self._try_load_font(config.POSTER_FONT_A, 24)
        
        for i, (label, value) in enumerate(info_items):
            y_pos = y_start + i * row_height
            if y_pos + row_height > 2080:
                break
            
            # ラベル部分（背景黒）
            draw.rectangle([(x_start, y_pos), (x_start + label_width, y_pos + row_height - 5)],
                          fill=(30, 30, 30))
            draw.text((x_start + 10, y_pos + 15), label, fill=(255, 255, 255), font=font_table)
            
            # 値部分（背景グレー）
            draw.rectangle([(x_start + label_width, y_pos), 
                          (x_start + label_width + value_width, y_pos + row_height - 5)],
                          fill=(120, 120, 120))
            
            # 値を折り返して表示（2行まで、省略せず全表示）
            pad_x = 10
            avail_w = value_width - pad_x * 2
            max_font, min_font = 24, 12

            def wrap_text_two_lines(txt: str, font: ImageFont.FreeTypeFont, max_width: int):
                lines = []
                current = ""
                for ch in txt:
                    test = current + ch
                    bbox = draw.textbbox((0, 0), test, font=font)
                    w = bbox[2] - bbox[0]
                    if w > max_width and current:
                        lines.append(current)
                        current = ch
                        if len(lines) >= 2:
                            # 2行を超えそうなら即終了して多いことを示す
                            # 呼び出し側でフォントサイズを下げる
                            # ここでは3行目に入れず返す
                            # currentは次の判定へ
                            pass
                    else:
                        current = test
                if current:
                    lines.append(current)
                return lines

            chosen_font = None
            chosen_lines = None
            chosen_line_h = None

            for size in range(max_font, min_font - 1, -2):
                f = self._try_load_font(config.POSTER_FONT_A, size)
                line_h = int(size * 1.2)
                lines = wrap_text_two_lines(value, f, avail_w)
                if len(lines) <= 2 and (len(lines) * line_h) <= (row_height - 10):
                    chosen_font = f
                    chosen_lines = lines
                    chosen_line_h = line_h
                    break

            # まだ2行に収まらない場合は最小サイズで2行に均等分割
            if chosen_font is None:
                size = min_font
                chosen_font = self._try_load_font(config.POSTER_FONT_A, size)
                chosen_line_h = int(size * 1.2)
                # 幅を見ながら、だいたい半分で分割して2行に
                mid = len(value) // 2
                # 左右の幅が近くなる位置を探索
                best_split = mid
                best_diff = 10**9
                for i in range(max(1, mid - 10), min(len(value) - 1, mid + 10)):
                    left = value[:i]
                    right = value[i:]
                    w1 = draw.textbbox((0, 0), left, font=chosen_font)[2]
                    w2 = draw.textbbox((0, 0), right, font=chosen_font)[2]
                    if w1 <= avail_w and w2 <= avail_w:
                        diff = abs(w1 - w2)
                        if diff < best_diff:
                            best_diff = diff
                            best_split = i
                chosen_lines = [value[:best_split], value[best_split:]]

            # 垂直方向センタリング
            total_h = len(chosen_lines) * chosen_line_h
            y_text = y_pos + (row_height - total_h) // 2

            for line in chosen_lines:
                # 水平センタリングではなく左寄せ（表っぽさ維持）
                x_text = x_start + label_width + pad_x
                draw.text((x_text, y_text), line, fill=(255, 255, 255), font=chosen_font)
                y_text += chosen_line_h
            
            # 縦罫線
            draw.line([(x_start + label_width, y_pos), 
                      (x_start + label_width, y_pos + row_height - 5)],
                     fill=(255, 255, 255), width=2)
        
        # 国旗画像の配置（1200, 1200）を左上として横幅300pxで配置
        # 最終レイヤー: すべての要素の上に重ねる
        if flag_img:
            try:
                flag_width, flag_height = flag_img.size
                # 横幅300pxに固定、アスペクト比維持
                target_width = 300
                ratio = target_width / flag_width
                new_height = int(flag_height * ratio)
                new_size = (target_width, new_height)
                flag_resized = flag_img.resize(new_size, Image.Resampling.LANCZOS)
                
                # 左上が(1200, 1200)となるように配置
                flag_x = 1200
                flag_y = 1200
                
                # アルファチャンネルがあればそれを使って合成、なければそのまま貼り付け
                if flag_resized.mode == 'RGBA':
                    canvas.paste(flag_resized, (flag_x, flag_y), flag_resized)
                else:
                    canvas.paste(flag_resized, (flag_x, flag_y))
                    
                logger.info(f"国旗画像を配置しました: 位置=({flag_x}, {flag_y}), サイズ={new_size}")
            except Exception as e:
                logger.warning(f"国旗画像の配置に失敗: {e}")
                import traceback
                logger.warning(traceback.format_exc())
        else:
            logger.info(f"国旗画像が見つかりませんでした。country={country_clean}")
        
        char_resized.close()
        if flag_img is not None:
            flag_img.close()
        return canvas

    def _scrape_character_info(self, character_id: str) -> dict:
        """Seleniumでキャラクター情報をスクレイピングする（同期メソッド、別スレッドで呼び出す）

        Args:
            character_id: キャラクターID

        Returns:
            キャラクター情報の辞書

        Raises:
            Exception: スクレイピングに失敗した場合
        """
        driver = None
        try:
            # ChromeDriverのオプションを設定（ログ抑制）
            chrome_options = Options()
            chrome_options.add_argument('--disable-logging')  # ロギング無効化
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])  # DevToolsログ抑制

            # ヘッドレスモード（ブラウザウィンドウを開かない）
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')  # GPU無効化（ヘッドレス環境で不要）

            # サンドボックス・共有メモリ設定（全環境で有効化 — EC2等で必須）
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')

            # メモリ管理オプション（EC2等の小規模インスタンス向け）
            chrome_options.add_argument('--disable-extensions')  # 拡張機能無効化
            chrome_options.add_argument('--disable-plugins')  # プラグイン無効化
            chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # 画像読み込み無効化（高速化）
            chrome_options.add_argument('--disable-software-rasterizer')  # ソフトウェアラスタライザ無効化

            # 追加の安定化オプション（リソース制約環境向け）
            chrome_options.add_argument('--disable-background-networking')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--window-size=1280,720')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')

            logger.info(f"Chromeドライバを起動します: character_id={character_id}")
            driver = webdriver.Chrome(options=chrome_options)

            # タイムアウト設定（リソース枯渇防止）
            driver.set_page_load_timeout(30)  # ページ読み込みタイムアウト
            driver.set_script_timeout(30)  # スクリプト実行タイムアウト
            driver.implicitly_wait(5)  # 暗黙的待機

            # キャラクターページURL（config.pyで一元管理）
            character_page_url = config.get_character_page_url(character_id)
            driver.get(character_page_url)

            # WebDriverWaitで要素の読み込みを待機（time.sleepより効率的）
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#root > main > div > section.status"))
                )
            except TimeoutException:
                logger.warning(f"ページ読み込みタイムアウト: character_id={character_id}")
                # タイムアウトでも続行を試みる

            html = driver.page_source.encode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            selectors = {
                'name': "#root > main > div > section.status > div > dl:nth-of-type(1) > dd > p",
                'country': "#root > main > div > section.status > div > dl:nth-of-type(4) > dd > p",
                'skill': "#root > main > div > section.status > div > dl:nth-of-type(5) > dd > p",
                'sencetype': "#root > main > div > section.status > div > dl:nth-of-type(6) > dd > p",
                'personality': "#root > main > div > section.status > div > dl:nth-of-type(7) > dd > p",
                'goal': "#root > main > div > section.status > div > dl:nth-of-type(8) > dd > p",
                'zirpower': "#root > main > div > section.status > div > dl:nth-of-type(9) > dd > p",
                'zircongear': "#root > main > div > section.status > div > dl:nth-of-type(10) > dd > p",
                'firstperson': "#root > main > div > section.status > div > dl:nth-of-type(11) > dd > p",
                'nickname': "#root > main > div > section.status > div > dl:nth-of-type(12) > dd > p",
                'lines': "#root > main > div > section.status > div > dl:nth-of-type(13) > dd > p",
                'weakness': "#root > main > div > section.status > div > dl:nth-of-type(14) > dd > p"
            }
            info = {}
            for key, selector in selectors.items():
                el = soup.select_one(selector)
                info[key] = el.text if el else ''

            logger.info(f"キャラクター情報のスクレイピングが完了しました: character_id={character_id}")
            return info
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("Chromeドライバを正常に終了しました")
                except Exception as e:
                    logger.error(f"Seleniumドライバの終了に失敗: {e}")

    def _cache_key(self, character_id):
        # Source/layout, configured fonts and asset contents invalidate completed images.
        pieces = [character_id, config.get_character_page_url(character_id),
                  config.get_character_image_url(character_id), Path(__file__).read_bytes().hex()]
        for path in [self.mask_path, self.peaceful_path, self.brave_path, self.glory_path, self.freedom_path]:
            pieces.append(Path(path).read_bytes().hex() if os.path.isfile(path) else "missing")
        for preferred in [config.POSTER_FONT_A, config.POSTER_FONT_B, config.POSTER_FONT_C, config.POSTER_FONT_D]:
            font = setup_fonts.find_japanese_font(preferred)
            pieces.append(preferred)
            if font:
                pieces.append(f"{font}:{Path(font).stat().st_mtime_ns}:{Path(font).stat().st_size}")
        return hashlib.sha256("|".join(pieces).encode()).hexdigest()

    def _render_poster(self, character_id: str) -> bytes:
        key = self._cache_key(character_id)
        with self._render_locks[int(key[:8], 16) % len(self._render_locks)]:
            content = self._cache.get("poster", key)
            if content is not None:
                return content
            info_key = config.get_character_page_url(character_id)
            info = self._cache.get("info", info_key)
            if info is None:
                info = self._scrape_character_info(character_id)
                if not info.get("name"):
                    raise ValueError("キャラクター名を取得できませんでした")
                self._cache.put("info", info_key, info)
            path = config.IMAGE_CACHE.get_sync(config.get_character_image_url(character_id))
            with ExitStack() as stack:
                source = stack.enter_context(Image.open(path))
                char = stack.enter_context(source.convert("RGB"))
                mask = stack.enter_context(Image.open(self.mask_path)) if os.path.exists(self.mask_path) else None
                poster = stack.enter_context(self._draw_poster(char, mask, info))
                with io.BytesIO() as output:
                    poster.save(output, format="PNG")
                    content = output.getvalue()
            self._cache.put("poster", key, content)
            return content

    def _start_workers(self):
        self._workers = [worker for worker in self._workers if not worker.done()]
        while len(self._workers) < config.POSTER_CONCURRENCY:
            self._workers.append(asyncio.create_task(self._work()))

    async def _work(self):
        while True:
            character_id, future = await self._queue.get()
            try:
                if future.cancelled():
                    continue
                worker = asyncio.create_task(asyncio.to_thread(self._render_poster, character_id))
                try:
                    content = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # A thread cannot be stopped. Retain the slot until it finishes.
                    try:
                        await worker
                    finally:
                        if not future.done():
                            future.cancel()
                    raise
                if not future.done():
                    future.set_result(content)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self._inflight.pop(character_id, None)
                self._queue.task_done()

    async def cog_unload(self):
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        while not self._queue.empty():
            character_id, future = self._queue.get_nowait()
            future.cancel()
            self._queue.task_done()
        self._inflight.clear()

    @app_commands.guild_only()
    @app_commands.command(name="poster", description="キャラクターポスターを作成します")
    @app_commands.describe(character_id="キャラクターIDを入力してください")
    async def poster(self, interaction: discord.Interaction, character_id: str):
        character_id = character_id.strip()
        if not character_id.isascii() or not character_id.isdigit():
            await interaction.response.send_message("キャラクターIDは半角数字で入力してください。", ephemeral=True)
            return
        if len(character_id) > 20:
            await interaction.response.send_message("キャラクターIDは20桁以内で指定してください。", ephemeral=True)
            return
        future = self._inflight.get(character_id)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            try:
                self._queue.put_nowait((character_id, future))
            except asyncio.QueueFull:
                await interaction.response.send_message("生成待ちが上限に達しました。しばらくしてから実行してください。", ephemeral=True)
                return
            self._inflight[character_id] = future
            # Consume errors even if all callers disconnect or time out.
            future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        self._start_workers()
        await interaction.response.defer(thinking=True)
        await interaction.edit_original_response(content=f"生成を受け付けました。待ち件数: {self._queue.qsize()}件")
        try:
            content = await asyncio.wait_for(asyncio.shield(future), timeout=600)
            with io.BytesIO(content) as output:
                file = discord.File(output, filename=f"poster_{character_id}.png")
                try:
                    await interaction.followup.send(content=f"✅ キャラクター #{character_id} のポスターが完成しました！", file=file)
                finally:
                    file.close()
        except asyncio.TimeoutError:
            await interaction.followup.send("生成待ちが10分を超えました。後ほど再実行してください。", ephemeral=True)
        except Exception as exc:
            from command_errors import send_error
            await send_error(interaction, exc)

async def setup(bot: commands.Bot):
    await bot.add_cog(Poster(bot))