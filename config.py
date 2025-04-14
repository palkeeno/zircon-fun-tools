"""
設定ファイル
このモジュールは、Discordボットの設定と環境変数の管理を行います。
"""

import os
import json
from dotenv import load_dotenv
import logging
from typing import Dict, Any

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定ファイルのパス
SETTINGS_FILE_PATH = os.getenv('SETTINGS_FILE_PATH', 'data/settings.json')

def load_settings() -> Dict[str, Any]:
    """
    設定ファイルを読み込みます。
    
    Returns:
        Dict[str, Any]: 設定データ
    """
    try:
        with open(SETTINGS_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"{SETTINGS_FILE_PATH}が見つかりません。デフォルト設定を使用します。")
        return get_default_settings()

def get_default_settings() -> Dict[str, Any]:
    """
    デフォルトの設定を返します。
    
    Returns:
        Dict[str, Any]: デフォルト設定
    """
    ENV = os.getenv('ENV', 'development')
    token_key = 'DISCORD_TOKEN_DEV' if ENV == 'development' else 'DISCORD_TOKEN_PROD'
    token = os.getenv(token_key)

    return {
        "bot": {
            "token": token,
            "prefix": "!",
            "admin_ids": [],
            "log_channel_id": None
        },
        "features": {
            "ramble_game": {
                "enabled": True,
                "settings": {
                    "min_players": 2,
                    "max_players": 10,
                    "round_duration": 60,
                    "notification_channel": None
                }
            },
            "birthday": {
                "enabled": False,
                "settings": {
                    "notification_channel": None,
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
            "omikuji": {
                "enabled": False,
                "settings": {
                    "cooldown": 3600,
                    "max_draws_per_day": 3
                }
            }
        }
    }

try:
    # .envファイルを読み込む
    load_dotenv()
except Exception as e:
    logger.error(f".envファイルの読み込みに失敗しました: {e}")
    raise

# 環境に応じてトークンを設定
ENV = os.getenv('ENV', 'development')  # デフォルトは開発環境
token_key = 'DISCORD_TOKEN_DEV' if ENV == 'development' else 'DISCORD_TOKEN_PROD'
_token = os.getenv(token_key)

# トークンの検証
if not _token:
    error_msg = f"{'開発' if ENV == 'development' else '本番'}環境のトークンが設定されていません。環境変数 {token_key} を設定してください。"
    logger.error(error_msg)
    raise ValueError(error_msg)

TOKEN = _token

# じゃんけんの設定
JANKEN_TIMEOUT = 30  # じゃんけんの待機時間（秒）

# 大喜利ゲームの設定
COMEDY_GAME_TIMEOUT = 300  # 回答待機時間（秒）
COMEDY_GAME_MIN_PLAYERS = 2  # 最小プレイヤー数
COMEDY_GAME_MAX_CARDS = 3  # 使用できる最大カード数

# 管理者チャンネルの設定
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHANNEL_ID_DEV' if ENV == 'development' else 'ADMIN_CHANNEL_ID_PROD', 0))
if not ADMIN_CHANNEL_ID:
    logger.warning(f"{'開発' if ENV == 'development' else '本番'}環境の管理者チャンネルIDが設定されていません。管理者コマンドは使用できません。")

# 設定の読み込み
SETTINGS = load_settings()

def is_feature_enabled(feature: str) -> bool:
    """
    指定された機能が有効かどうかを判定します。
    
    Args:
        feature (str): 機能名
        
    Returns:
        bool: 機能が有効な場合はTrue、そうでない場合はFalse
    """
    return SETTINGS['features'].get(feature, {}).get('enabled', False)

# じゃんけんの設定
JANKEN_EMOJIS = {
    'rock': '✊',
    'scissors': '✌️',
    'paper': '✋'
}

# 占いの設定
FORTUNE_MAX_CHOICES = 5  # 選択肢の最大数 