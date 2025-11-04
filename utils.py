"""Project-wide utility helpers.

Helpers that are used across multiple modules should live at the project
root so they can be imported as `import utils` from cogs and other modules.
Keep this file minimal and dependency-free.
"""

from typing import Iterable


def make_big_text(s: str) -> str:
    """Convert ASCII characters to their fullwidth counterparts.

    Useful for emphasising text in Discord embeds where font size can't be
    changed. Non-ASCII characters are returned unchanged.
    """
    out = []
    for ch in s:
        o = ord(ch)
        # map visible ASCII range 33..126 to fullwidth FF01..FF5E
        if 33 <= o <= 126:
            out.append(chr(0xFF01 + (o - 33)))
        else:
            out.append(ch)
    return ''.join(out)


def join_lines(lines: Iterable[str]) -> str:
    """Join lines with newlines, skipping empty entries."""
    return "\n".join([l for l in lines if l])
