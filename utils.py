"""
共通ユーティリティ関数
複数のcogで使用される共通機能を提供します。
"""

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "Asia/Tokyo"

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def get_timezone() -> datetime.tzinfo:
    """
    デフォルトタイムゾーン（Asia/Tokyo）を取得します。
    
    Returns:
        datetime.tzinfo: タイムゾーンオブジェクト
    """
    if ZoneInfo is not None:
        try:
            return ZoneInfo(_DEFAULT_TIMEZONE)
        except Exception:
            logger.warning("ZoneInfoで %s を取得できません。UTC+09:00 を使用します", _DEFAULT_TIMEZONE)
    return datetime.timezone(datetime.timedelta(hours=9))


def coerce_bool(value: Any, fallback: bool) -> bool:
    """
    値をブール値に変換します。
    
    Args:
        value: 変換する値
        fallback: 変換に失敗した場合のデフォルト値
        
    Returns:
        bool: 変換されたブール値
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return fallback
    try:
        return bool(value)
    except Exception:
        return fallback


def coerce_int(value: Any, fallback: int, *, minimum: int = None, maximum: int = None) -> int:
    """
    値を整数に変換し、範囲内に制限します。
    
    Args:
        value: 変換する値
        fallback: 変換に失敗した場合のデフォルト値
        minimum: 最小値（Noneの場合は制限なし）
        maximum: 最大値（Noneの場合は制限なし）
        
    Returns:
        int: 変換・制限された整数値
    """
    try:
        if value is None:
            raise TypeError
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    
    return number


def clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    """
    値を整数に変換し、指定範囲内に制限します（coerce_intのエイリアス）。
    
    Args:
        value: 変換する値
        minimum: 最小値
        maximum: 最大値
        fallback: 変換に失敗した場合のデフォルト値
        
    Returns:
        int: 変換・制限された整数値
    """
    return coerce_int(value, fallback, minimum=minimum, maximum=maximum)
