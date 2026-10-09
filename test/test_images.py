import asyncio
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import config
import utils
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from PIL import Image, ImageFont
from image_cache import ImageCache, download_bytes
from cogs.birthday import Birthday
from cogs.poster import Poster
class CacheTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        output = io.BytesIO()
        with Image.new('RGB', (8, 8), 'red') as image:
            image.save(output, format='WEBP', lossless=True)
        cls.content = output.getvalue()
        cls.requests = 0

        class Handler(BaseHTTPRequestHandler):

            def do_GET(self):
                cls.requests += 1
                self.send_response(200)
                self.send_header('Content-Length', str(len(cls.content)))
                self.end_headers()
                try:
                    if self.path == '/slow':
                        for value in cls.content:
                            self.wfile.write(bytes([value]))
                            self.wfile.flush()
                            time.sleep(0.01)
                    else:
                        self.wfile.write(cls.content)
                except OSError:
                    pass

            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:%s/image.webp' % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_parallel_and_restart_reuse_one_download(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(directory)
            before = self.requests
            with ThreadPoolExecutor(max_workers=8) as pool:
                paths = list(pool.map(cache.get_sync, [self.url] * 8))
            self.assertEqual(self.requests - before, 1)
            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(ImageCache(directory).get_sync(self.url), paths[0])
            self.assertEqual(self.requests - before, 1)
            with Image.open(paths[0]) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.getpixel((0, 0)), (255, 0, 0, 255))

    def test_corrupted_cache_downloaded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ImageCache(directory)
            path = cache.get_sync(self.url)
            path.write_bytes(b'broken')
            before = self.requests
            self.assertEqual(cache.get_sync(self.url), path)
            self.assertEqual(self.requests - before, 1)

    def test_download_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                ImageCache(directory, max_bytes=1).get_sync(self.url)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_response_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('image_cache.download_bytes', return_value=b'html instead of image'):
                with self.assertRaises(OSError):
                    ImageCache(directory).get_sync(self.url)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_timeout_is_passed_and_retries_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('image_cache.urllib.request.urlopen', side_effect=TimeoutError) as request:
                with self.assertRaises(TimeoutError):
                    ImageCache(directory, timeout=0.5).get_sync(self.url)
                self.assertEqual(request.call_count, 2)
                request.assert_called_with(self.url, timeout=0.5)

    def test_slow_stream_has_total_time_limit(self):
        with self.assertRaises(TimeoutError):
            download_bytes(self.url.rsplit('/', 1)[0] + '/slow', timeout=0.03)

    def test_size_limit_without_content_length(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers.get.return_value = None
        response.read1.return_value = b'oversized'
        with patch('image_cache.urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                download_bytes(self.url, max_bytes=2)

class BirthdayTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.cog = Birthday.__new__(Birthday)
        self.cog.bot = MagicMock()
        self.cog._data_lock = asyncio.Lock()
        self.cog.save_birthdays = MagicMock()
        self.cog.birthdays = [dict(character_id='1', name='A', month=10, day=9, reported=False)]
        self.interaction = MagicMock()
        self.interaction.response = AsyncMock()
        self.interaction.followup = AsyncMock()

    async def test_send_failure_preserves_cache_and_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.png'
            with Image.new('RGB', (8, 8)) as image:
                image.save(path)
            channel = MagicMock()
            channel.send = AsyncMock(side_effect=[RuntimeError('send failed'), None])
            with patch.object(config.IMAGE_CACHE, 'get', new=AsyncMock(return_value=path)):
                self.assertFalse(await self.cog._announce_zircon_birthday(channel, self.cog.birthdays[0]))
                self.assertTrue(await self.cog._announce_zircon_birthday(channel, self.cog.birthdays[0]))
            self.assertTrue(path.exists())
            self.assertEqual(channel.send.await_count, 2)

class PosterTests(unittest.IsolatedAsyncioTestCase):

    async def test_actual_composition_uses_cached_image(self):
        cog = Poster(MagicMock())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'character.png'
            with Image.new('RGB', (20, 20), 'red') as image:
                image.save(path)
            cog.mask_path = str(Path(directory) / 'no-mask.png')
            with patch.object(config.IMAGE_CACHE, 'get_sync', return_value=path), patch.object(cog, '_scrape_character_info', return_value={'name': 'Test'}), patch.object(cog, '_try_load_font', return_value=ImageFont.load_default()):
                result = await asyncio.to_thread(cog._render_poster, '1')
            with Image.open(io.BytesIO(result)) as image:
                self.assertEqual(image.size, (1600, 2100))
                self.assertEqual(image.format, 'PNG')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    async def test_concurrent_posters_do_not_mix_and_leave_loop_responsive(self):
        cog = Poster(MagicMock())
        active = 0
        peak = 0
        entered = threading.Event()
        release = threading.Event()

        def render(character_id):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            entered.set()
            release.wait(timeout=2)
            active -= 1
            return character_id.encode()
        interactions = [MagicMock(), MagicMock()]
        received = []
        for interaction in interactions:
            interaction.response = AsyncMock()
            interaction.followup = AsyncMock()

            async def capture(**kwargs):
                received.append((kwargs['file'].filename, kwargs['file'].fp.read()))
            interaction.followup.send.side_effect = capture
        with patch.object(cog, '_render_poster', side_effect=render):
            tasks = [asyncio.create_task(Poster.poster.callback(cog, item, str(i))) for i, item in enumerate(interactions, 1)]
            while not entered.is_set():
                await asyncio.sleep(0.001)
            release.set()
            await asyncio.gather(*tasks)
        self.assertEqual(peak, 1)
        self.assertEqual(sorted(received), [('poster_1.png', b'1'), ('poster_2.png', b'2')])

