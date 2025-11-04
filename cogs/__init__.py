"""
Discordボットのコグ（機能拡張）モジュールを管理するパッケージ。
"""

from .birthday import Birthday
from .dictionary import Dictionary
from .janken import Janken
from .oracle import Oracle
from .admin import Admin

__all__ = [
    'Birthday',
    'Dictionary',
    'Janken',
    'Oracle',
    'Admin'
] 