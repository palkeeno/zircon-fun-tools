"""
Discordボットのコグ（機能拡張）モジュールを管理するパッケージ。
"""

from .ramble_game import RambleGame
from .birthday import Birthday
from .dictionary import Dictionary
from .comedy_game import ComedyGame
from .janken import Janken
from .fortune import Fortune
from .oracle import Oracle
from .admin import Admin

__all__ = [
    'RambleGame',
    'Birthday',
    'Dictionary',
    'ComedyGame',
    'Janken',
    'Fortune',
    'Oracle',
    'Admin'
] 