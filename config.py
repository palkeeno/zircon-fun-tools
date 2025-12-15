"""
設定ファイル
このモジュールは、Discordボットの設定と環境変数の管理を行います。
"""

import os
import json
import logging
from typing import Dict, Any, Optional
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

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
_RUNTIME_CONFIG_PATH = os.path.join(_DATA_DIR, 'config.json')


def _safe_int(value: Optional[str], default: int) -> int:
    """環境変数を整数として解釈し、失敗時はデフォルト値を返す。"""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        logger.warning("環境変数の整数変換に失敗しました。value=%s, default=%s", value, default)
        return default


def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _load_runtime_config() -> Dict[str, Any]:
    _ensure_data_dir()
    if not os.path.exists(_RUNTIME_CONFIG_PATH):
        return {}
    try:
        with open(_RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        logger.warning("runtime config の読み込みに失敗しました: %s", exc)
        return {}
    except OSError as exc:
        logger.error("runtime config のアクセス時にエラーが発生しました: %s", exc)
        return {}
    if isinstance(payload, dict):
        return payload
    logger.warning("runtime config の形式が不正です。空の設定として扱います。")
    return {}


def _save_runtime_config(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(_RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def get_runtime_section(section: str) -> Dict[str, Any]:
    """設定ファイル (data/config.json) から指定セクションを取得します。"""
    payload = _load_runtime_config()
    value = payload.get(section)
    return dict(value) if isinstance(value, dict) else {}


def set_runtime_section(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """設定ファイル (data/config.json) に指定セクションを書き込みます。"""
    if not isinstance(values, dict):
        raise ValueError("values must be a dict")
    payload = _load_runtime_config()
    payload[section] = dict(values)
    _save_runtime_config(payload)
    return dict(values)

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

# 即時ギルド同期用のGuild ID（開発/本番で切替可能）
# 設定すると、そのギルドに対してスラッシュコマンドを即時同期します（数秒で反映）。
# 未設定(0)の場合はグローバル同期のみとなり、反映まで最大1時間かかることがあります。
GUILD_ID = int(os.getenv('GUILD_ID_DEV' if ENV == 'development' else 'GUILD_ID_PROD', '0'))

# Birthday機能の設定
BIRTHDAY_CHANNEL_ID = int(os.getenv('BIRTHDAY_CHANNEL_ID_DEV' if ENV == 'development' else 'BIRTHDAY_CHANNEL_ID_PROD', '0'))

# Posterコマンド用の画像・フォント・チャンネル設定
# アセットディレクトリのベースパス
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'assets')
POSTER_MASK_PATH = os.getenv('POSTER_MASK_PATH', os.path.join(_ASSETS_DIR, 'mask.png'))
POSTER_PEACEFUL_PATH = os.getenv('POSTER_PEACEFUL_PATH', os.path.join(_ASSETS_DIR, 'peaceful.png'))
POSTER_BRAVE_PATH = os.getenv('POSTER_BRAVE_PATH', os.path.join(_ASSETS_DIR, 'brave.png'))
POSTER_GLORY_PATH = os.getenv('POSTER_GLORY_PATH', os.path.join(_ASSETS_DIR, 'glory.png'))
POSTER_FREEDOM_PATH = os.getenv('POSTER_FREEDOM_PATH', os.path.join(_ASSETS_DIR, 'freedom.png'))
POSTER_DST_PATH = os.getenv('POSTER_DST_PATH', 'poster_output.png')
POSTER_FONT_A = os.getenv('POSTER_FONT_A', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_B = os.getenv('POSTER_FONT_B', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_C = os.getenv('POSTER_FONT_C', 'ヒラギノ明朝 ProN.ttc')
POSTER_FONT_D = os.getenv('POSTER_FONT_D', 'ヒラギノ明朝 ProN.ttc')
POSTER_CHANNEL_ID = int(os.getenv('POSTER_CHANNEL_ID', '0'))

# Quotes 機能の設定
QUOTE_CHANNEL_ID = _safe_int(os.getenv('QUOTE_CHANNEL_ID_DEV' if ENV == 'development' else 'QUOTE_CHANNEL_ID_PROD', '0'), 0)

# 機能の設定
FEATURES = {
    "birthday": {
        "settings": {
            "timezone": "Asia/Tokyo",
            "default_enabled": True,
            "default_hour": 9
        }
    },
    "quotes": {
        "settings": {
            "default_enabled": True,
            "default_days": 1,
            "default_hour": 9,
            "default_minute": 0,
            "timezone": "Asia/Tokyo"
        }
    }
}



def get_feature_settings(feature: str) -> Dict[str, Any]:
    """
    指定された機能の設定を取得します。
    
    Args:
        feature (str): 機能名
        
    Returns:
        Dict[str, Any]: 機能の設定
    """
    return FEATURES.get(feature, {}).get('settings', {})

def get_birthday_channel_id() -> int:
    """
    誕生日通知チャンネルのIDを取得します。
    
    Returns:
        int: 誕生日通知チャンネルのID
    """
    return BIRTHDAY_CHANNEL_ID


def get_quote_channel_id() -> int:
    """
    名言投稿チャンネルのIDを取得します。

    Returns:
        int: 名言投稿チャンネルのID
    """
    return QUOTE_CHANNEL_ID
