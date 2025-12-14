"""
Discordボットのコグ（機能拡張）モジュールを管理するパッケージ。
"""

from .birthday import Birthday
from .oracle import Oracle
from .lottery import Lottery
from .poster import Poster
from .quotes import Quotes

__all__ = [
    'Birthday',
    'Oracle',
    'Lottery',
    'Poster',
    'Quotes'
] 