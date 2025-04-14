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
TOKEN = os.getenv('DISCORD_TOKEN_DEV' if ENV == 'development' else 'DISCORD_TOKEN_PROD')
if not TOKEN:
    error_msg = "トークンが設定されていません。環境変数を設定してください。"
    logger.error(error_msg)
    raise ValueError(error_msg)

# 管理者チャンネルの設定
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHANNEL_ID_DEV' if ENV == 'development' else 'ADMIN_CHANNEL_ID_PROD', 0))
if not ADMIN_CHANNEL_ID:
    logger.warning("管理者チャンネルIDが設定されていません。管理者コマンドは使用できません。")

# 機能の設定
FEATURES = {
    "ramble_game": {
        "enabled": False,
        "settings": {
            "round_duration": 30
        }
    },
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
    "fortune": {
        "enabled": False,
        "settings": {
            "cooldown": 3600
        }
    },
    "comedy_game": {
        "enabled": True,
        "settings": {
            "timeout": 300,
            "min_players": 2,
            "max_cards": 3
        }
    },
    "janken": {
        "enabled": True,
        "settings": {
            "timeout": 30
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
    }
}

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