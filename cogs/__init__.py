"""
Discordボットのコグ（機能拡張）モジュールを管理するパッケージ。
"""

from .birthday import Birthday
from .oracle import Oracle
from .admin import Admin
from .lottery import Lottery
from .poster import Poster

__all__ = [
    'Birthday',
    'Oracle',
    'Admin',
    'Lottery',
    'Poster'
] 