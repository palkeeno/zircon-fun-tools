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
import platform
import math

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
        # config.pyからパスを取得
        self.mask_path = config.POSTER_MASK_PATH
        self.peaceful_path = config.POSTER_PEACEFUL_PATH
        self.brave_path = config.POSTER_BRAVE_PATH
        self.glory_path = config.POSTER_GLORY_PATH
        self.freedom_path = config.POSTER_FREEDOM_PATH
        self.dst_path = config.POSTER_DST_PATH
        
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
    def _try_load_font(self, prefer_path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """フォントを安全に読み込む。存在しない場合は自動ダウンロードまたはシステムフォントにフォールバック。

        優先順:
        1) config で指定されたパス（相対の場合はリポジトリルートや data/fonts も探索）
        2) システムの既存日本語フォント（Windows/Linux 共通）
        3) Noto Sans JP を Google Fonts からダウンロード（data/fonts/ にキャッシュ）
        4) PIL のデフォルトフォント
        """
        candidates = []
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        
        # まず指定パス
        if prefer_path:
            candidates.append(prefer_path)
            if not os.path.isabs(prefer_path):
                candidates.append(os.path.join(repo_root, prefer_path))
                candidates.append(os.path.join(repo_root, 'data', 'fonts', prefer_path))

        # システムフォント候補（環境に応じて最適化）
        is_linux = platform.system() == "Linux"
        if is_linux:
            # Linux環境のフォントパス
            system_fonts = [
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        else:
            # Windows環境のフォントパス
            system_fonts = [
                r"C:\Windows\Fonts\meiryo.ttc",
                r"C:\Windows\Fonts\msgothic.ttc",
                r"C:\Windows\Fonts\YuGothM.ttc",
            ]
        candidates.extend(system_fonts)

        # 既存候補を試す
        for path in candidates:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
            except Exception:
                continue

        # ここまで見つからなければ Noto Sans JP を自動ダウンロード
        downloaded_font = self._download_fallback_font()
        if downloaded_font and os.path.exists(downloaded_font):
            try:
                return ImageFont.truetype(downloaded_font, size)
            except Exception:
                pass

        # 最終手段: PIL デフォルト
        logger.warning("フォントを読み込めませんでした。PILのデフォルトフォントを使用します。")
        return ImageFont.load_default()

    def _download_fallback_font(self) -> str:
        """Google Fonts から Noto Sans JP をダウンロードし、data/fonts/ にキャッシュする。

        Returns:
            str: ダウンロードしたフォントファイルのパス。失敗時は空文字列。
        """
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        fonts_dir = os.path.join(repo_root, 'data', 'fonts')
        os.makedirs(fonts_dir, exist_ok=True)
        
        font_path = os.path.join(fonts_dir, 'NotoSansJP-Regular.ttf')
        
        # すでにダウンロード済みならそれを返す
        if os.path.exists(font_path):
            return font_path
        
        # Google Fonts の直リンク（Noto Sans JP Regular）
        # 注：このURLは変わる可能性があるため、本番では fonts.google.com API や CDN を利用推奨
        font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
        
        try:
            logger.info("フォントが見つからないため、Noto Sans JP をダウンロードします: %s", font_url)
            urllib.request.urlretrieve(font_url, font_path)
            logger.info("フォントをダウンロードしました: %s", font_path)
            return font_path
        except Exception as e:
            logger.error("フォントのダウンロードに失敗しました: %s", e)
            return ""

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
        font_40 = self._try_load_font(config.POSTER_FONT_A, 40)
        font_80 = self._try_load_font(config.POSTER_FONT_B, 80)
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
                        flag_img = Image.open(candidate)
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
        
        # 5. 目標（goal）を領域中央揃えで配置（850, 1500）から（1550, 2050）
        goal = info.get('goal', '')
        if goal:
            # 領域定義
            goal_x_left, goal_x_right = 850, 1550
            goal_y_top, goal_y_bottom = 1500, 2050
            goal_width = goal_x_right - goal_x_left
            goal_height = goal_y_bottom - goal_y_top
            
            # 最大120pxから順にサイズを試して、領域に収まる最大サイズを見つける
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
        
        # 9. その他の情報をテーブル形式で配置（50, 1500）から（800, 2100）
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
        
        # 8. 国旗画像の配置（900,900）を左上として横幅300pxで配置
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
                
                # 左上が(900, 900)となるように配置
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
        
        return canvas

    @app_commands.command(
        name="poster", 
        description="キャラクターポスターを作成します"
    )
    @app_commands.describe(
        character_id="キャラクターIDを入力してください"
    )
    async def poster(self, interaction: discord.Interaction, character_id: str):

        # 画像アセットの存在確認（マスクと国旗はオプション）
        # 現在は必須アセットなし（すべてオプション）
        optional_assets = [
            ('mask.png', self.mask_path),
            ('peaceful.png', self.peaceful_path),
            ('brave.png', self.brave_path),
            ('glory.png', self.glory_path),
            ('freedom.png', self.freedom_path),
        ]
        
        missing = [name for name, path in optional_assets if not os.path.exists(path)]
        
        if missing:
            logger.info(f"オプション画像が不足していますが、処理を続行します: {', '.join(missing)}")
        
        await interaction.response.send_message(
            "キャラクターカード作成中です\nカードが完成するまでコマンドを入力しないようお願いします"
        )
        driver = None
        try:
            # キャラ画像URL取得
            if len(character_id) <= 4:
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.webp"
            else:
                url = f"https://storage.googleapis.com/prd-azz-image/pfp_{character_id}.png"
            try:
                urllib.request.urlretrieve(url, self.dst_path)
            except Exception as e:
                logger.error(f"画像のダウンロードに失敗: {e}")
                await interaction.followup.send("キャラクター画像の取得に失敗しました。番号が正しいかご確認ください。", ephemeral=True)
                return
            try:
                # キャラクター画像を開く
                char = Image.open(self.dst_path)
                
                # WebP形式の場合はPNGに変換
                if char.format == 'WEBP':
                    char = char.convert('RGB')
                
                # マスク画像（オプション）
                mask = None
                if os.path.exists(self.mask_path):
                    mask = Image.open(self.mask_path)
                
                # 注: peaceful, brave, glory, freedom 画像は現在使用されていません
                # 将来の機能拡張のために読み込み処理は残していますが、_draw_poster()には渡していません
            except Exception as e:
                logger.error(f"画像ファイルの読み込みに失敗: {e}")
                await interaction.followup.send("画像ファイルの読み込みに失敗しました。管理者に連絡してください。", ephemeral=True)
                return
            # Seleniumでキャラ情報取得
            try:
                # ChromeDriverのオプションを設定（ログ抑制）
                chrome_options = Options()
                chrome_options.add_argument('--log-level=3')  # ログレベルを抑制
                chrome_options.add_argument('--disable-logging')  # ロギング無効化
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])  # DevToolsログ抑制
                
                # ヘッドレスモード（ブラウザウィンドウを開かない）
                # WindowsとLinuxの両方で同じ動作にするため
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--disable-gpu')  # GPU無効化（ヘッドレス環境で不要）
                
                # Linux環境で必要なオプション（Windowsでも動作するが、環境判定で追加）
                is_linux = platform.system() == "Linux"
                if is_linux:
                    chrome_options.add_argument('--no-sandbox')  # Linux環境で必要
                    chrome_options.add_argument('--disable-dev-shm-usage')  # 共有メモリの問題を回避
                
                driver = webdriver.Chrome(options=chrome_options)
                driver.get(f"https://zircon.konami.net/nft/character/{character_id}")
                time.sleep(3)
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
            except Exception as e:
                logger.error(f"Selenium/スクレイピングに失敗: {e}")
                await interaction.followup.send("キャラクター情報の取得に失敗しました。番号が正しいか、または公式サイトの仕様変更がないかご確認ください。", ephemeral=True)
                return
            try:
                poster_img = self._draw_poster(char, mask, info)
                img_bytes = io.BytesIO()
                poster_img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
            except Exception as e:
                logger.error(f"画像合成・保存に失敗: {e}")
                await interaction.followup.send("画像の合成または保存に失敗しました。管理者に連絡してください。", ephemeral=True)
                return
            # ポスター画像をユーザーに送信
            try:
                filename = f"poster_{character_id}.png"
                await interaction.followup.send(
                    content=f"✅ キャラクター #{character_id} のポスターが完成しました！",
                    file=discord.File(img_bytes, filename=filename)
                )
            except Exception as e:
                logger.error(f"Discordへの画像送信に失敗: {e}")
                await interaction.followup.send("画像の送信に失敗しました。管理者に連絡してください。", ephemeral=True)
                return
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
    await bot.add_cog(Poster(bot))