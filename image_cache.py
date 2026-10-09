"""誕生日とポスターで共有する、再起動後も使える画像キャッシュ。"""

import asyncio
import hashlib
import io
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.error
import urllib.request

from PIL import Image

logger = logging.getLogger(__name__)


def download_bytes(url: str, *, timeout: float = 20, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    """接続・読込待ち、総取得時間、サイズを制限する。"""
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(url, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("ダウンロードサイズが上限を超えています")
        chunks = []
        size = 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("ダウンロード時間が上限を超えています")
            chunk = response.read1(min(64 * 1024, max_bytes - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("ダウンロードサイズが上限を超えています")
            chunks.append(chunk)
        return b"".join(chunks)


class ImageCache:
    def __init__(self, directory, *, timeout=20, max_bytes=10 * 1024 * 1024):
        self.directory = Path(directory)
        self.timeout = timeout
        self.max_bytes = max_bytes
        # 同じURLへの同時リクエストは、検証・ダウンロード・保存をまとめて排他する。
        self._locks = [threading.Lock() for _ in range(64)]

    @staticmethod
    def _validate(path):
        with Image.open(path) as image:
            if image.width * image.height > 25_000_000:
                raise ValueError("画像の画素数が上限を超えています")
            image.verify()

    def get_sync(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        destination = self.directory / (digest + ".png")
        with self._locks[int(digest[:8], 16) % len(self._locks)]:
            if destination.is_file():
                try:
                    self._validate(destination)
                    return destination
                except (OSError, ValueError, Image.DecompressionBombError):
                    logger.warning("破損した画像キャッシュを再取得します: %s", destination.name)
            self.directory.mkdir(parents=True, exist_ok=True)
            content = None
            for attempt in range(2):
                try:
                    content = download_bytes(url, timeout=self.timeout, max_bytes=self.max_bytes)
                    break
                except urllib.error.HTTPError as exc:
                    if attempt or exc.code < 500:
                        raise
                except (urllib.error.URLError, TimeoutError):
                    if attempt:
                        raise
            fd, temporary = tempfile.mkstemp(prefix=".image-", suffix=".png", dir=self.directory)
            os.close(fd)
            try:
                with Image.open(io.BytesIO(content)) as image:
                    if image.width * image.height > 25_000_000:
                        raise ValueError("画像の画素数が上限を超えています")
                    with image.convert("RGBA") as converted:
                        converted.save(temporary, format="PNG")
                self._validate(temporary)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
            return destination

    async def get(self, url: str) -> Path:
        # キャンセル後もワーカースレッド側が完了・片付けるため、不完全な画像を公開しない。
        return await asyncio.to_thread(self.get_sync, url)
