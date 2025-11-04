"""
設定ファイル
このモジュールは、Discordボットの設定と環境変数の管理を行います。
"""

import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
try:
    load_dotenv()
except Exception as e:
    logger.error(f".envファイルの読み込みに失敗しました: {e}")
    raise

# 環境設定
ENV = os.getenv('ENV', 'development')  # デフォルトは開発環境

# Discordボットの設定

def get_token():
    """
    現在の環境変数に基づいてトークンを取得します。
    テスト用に関数化。
    """
    ENV = os.getenv('ENV', 'development')
    token = os.getenv('DISCORD_TOKEN_DEV' if ENV == 'development' else 'DISCORD_TOKEN_PROD')
    if not token:
        error_msg = "トークンが設定されていません。環境変数を設定してください。"
        logger.error(error_msg)
        raise ValueError(error_msg)
    return token

TOKEN = get_token()

# 管理者チャンネルの設定
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHANNEL_ID_DEV' if ENV == 'development' else 'ADMIN_CHANNEL_ID_PROD', 0))
if not ADMIN_CHANNEL_ID:
    logger.warning("管理者チャンネルIDが設定されていません。管理者コマンドは使用できません。")

# 運営ロールIDの設定
OPERATOR_ROLE_ID = int(os.getenv('OPERATOR_ROLE_ID_DEV' if ENV == 'development' else 'OPERATOR_ROLE_ID_DEV', '0'))  # 0は未設定扱い
if not OPERATOR_ROLE_ID:
    logger.warning("運営ロールが設定されていません。運営ロールが必要なコマンドは使用できません。")

# Posterコマンド用の画像・フォント・チャンネル設定
POSTER_CARD_PATH = os.getenv('POSTER_CARD_PATH', 'card.png')
POSTER_MASK_PATH = os.getenv('POSTER_MASK_PATH', 'mask.png')
POSTER_PEACEFUL_PATH = os.getenv('POSTER_PEACEFUL_PATH', 'peaceful.png')
POSTER_BRAVE_PATH = os.getenv('POSTER_BRAVE_PATH', 'brave.png')
POSTER_GLORY_PATH = os.getenv('POSTER_GLORY_PATH', 'glory.png')
POSTER_FREEDOM_PATH = os.getenv('POSTER_FREEDOM_PATH', 'freedom.png')
POSTER_DST_PATH = os.getenv('POSTER_DST_PATH', 'poster_output.png')
POSTER_FONT_A = os.getenv('POSTER_FONT_A', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_B = os.getenv('POSTER_FONT_B', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_C = os.getenv('POSTER_FONT_C', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_D = os.getenv('POSTER_FONT_D', 'ヒラギノ明朝 ProN.ttc')
POSTER_CHANNEL_ID = int(os.getenv('POSTER_CHANNEL_ID', '0'))

# 機能の設定
FEATURES = {

    "birthday": {
        "enabled": False,
        "settings": {
            "notification_time": "09:00",
            "timezone": "Asia/Tokyo"
        }
    },
    "dictionary": {
        "enabled": False,
        "settings": {
            "max_words": 1000,
            "search_limit": 10,
            "fuzzy_search": True
        }
    },



    "oracle": {
        "enabled": True,
        "settings": {
            "max_choices": 5
        }
    },
    "admin": {
        "enabled": True,
        "settings": {}
    },
    "lottery": {
        "enabled": True, 
        "settings": {}
    },
    "poster": {
        "enabled": True, 
        "settings": {}
    }
}

# FEATURESから有効/無効状態のみを抽出した辞書
FEATURE_STATE = {k: v["enabled"] for k, v in FEATURES.items()}

# じゃんけんの設定
JANKEN_EMOJIS = {
    'rock': '✊',
    'scissors': '✌️',
    'paper': '✋'
}

def is_feature_enabled(feature: str) -> bool:
    """
    指定された機能が有効かどうかを判定します。
    
    Args:
        feature (str): 機能名
        
    Returns:
        bool: 機能が有効な場合はTrue、そうでない場合はFalse
    """
    return FEATURES.get(feature, {}).get('enabled', False)

def get_feature_settings(feature: str) -> Dict[str, Any]:
    """
    指定された機能の設定を取得します。
    
    Args:
        feature (str): 機能名
        
    Returns:
        Dict[str, Any]: 機能の設定
    """
    return FEATURES.get(feature, {}).get('settings', {})