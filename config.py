"""
設定ファイル
このモジュールは、Discordボットの設定と環境変数の管理を行います。
"""

import os
from dotenv import load_dotenv
import logging
import discord

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # .envファイルを読み込む
    load_dotenv()
except Exception as e:
    logger.error(f".envファイルの読み込みに失敗しました: {e}")
    raise

# 環境に応じてトークンを設定
ENV = os.getenv('ENV', 'development')  # デフォルトは開発環境
TOKEN = os.getenv('DISCORD_TOKEN_DEV' if ENV == 'development' else 'DISCORD_TOKEN_PROD')

# トークンの検証
if not TOKEN:
    error_msg = f"{'開発' if ENV == 'development' else '本番'}環境のトークンが設定されていません。"
    logger.error(error_msg)
    raise ValueError(error_msg)

# コマンドプレフィックス（将来的な拡張用）
PREFIX = '!'

# 占い機能の設定
FORTUNE_MAX_CHOICES = 5  # 最大選択肢数

# じゃんけんの設定
JANKEN_TIMEOUT = 30  # じゃんけんの待機時間（秒）

# 大喜利ゲームの設定
COMEDY_GAME_TIMEOUT = 300  # 回答待機時間（秒）
COMEDY_GAME_MIN_PLAYERS = 2  # 最小プレイヤー数
COMEDY_GAME_MAX_CARDS = 3  # 使用できる最大カード数

# 管理者チャンネルの設定
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHANNEL_ID', 0))
if not ADMIN_CHANNEL_ID:
    logger.warning("ADMIN_CHANNEL_IDが設定されていません。管理者コマンドは使用できません。")

# 機能の状態管理
FEATURE_STATUS = {
    'janken': True,      # じゃんけん機能
    'fortune': True,     # 占い機能
    'comedy': True       # コメディゲーム機能
}

def is_admin_channel(channel_id: int) -> bool:
    """
    指定されたチャンネルが管理者チャンネルかどうかを判定します。
    
    Args:
        channel_id (int): チャンネルID
        
    Returns:
        bool: 管理者チャンネルの場合はTrue、そうでない場合はFalse
    """
    return channel_id == ADMIN_CHANNEL_ID

def set_feature_status(feature: str, status: bool) -> bool:
    """
    機能の状態を設定します。
    
    Args:
        feature (str): 機能名
        status (bool): 有効化する場合はTrue、無効化する場合はFalse
        
    Returns:
        bool: 設定に成功した場合はTrue、失敗した場合はFalse
    """
    if feature in FEATURE_STATUS:
        FEATURE_STATUS[feature] = status
        logger.info(f"機能 '{feature}' の状態を {status} に設定しました")
        return True
    logger.warning(f"無効な機能名が指定されました: {feature}")
    return False

def is_feature_enabled(feature: str) -> bool:
    """
    機能が有効かどうかを確認します。
    
    Args:
        feature (str): 機能名
        
    Returns:
        bool: 機能が有効な場合はTrue、無効な場合はFalse
    """
    return FEATURE_STATUS.get(feature, False)

# じゃんけんの設定
JANKEN_EMOJIS = {
    'rock': '✊',
    'scissors': '✌️',
    'paper': '✋'
}

# 占いの設定
FORTUNE_MAX_CHOICES = 5  # 選択肢の最大数 