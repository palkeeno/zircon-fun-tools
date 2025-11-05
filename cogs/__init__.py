"""
Discordボットのコグ（機能拡張）モジュールを管理するパッケージ。
"""

from .birthday import Birthday
from .oracle import Oracle
from .admin import Admin

__all__ = [
    'Birthday',
    'Oracle',
    'Admin'
] 