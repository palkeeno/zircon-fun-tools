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
class EnvironmentTests(unittest.TestCase):

    def test_env_and_legacy_selection(self):
        for values, expected in [({}, 'development'), ({'ENV': 'production'}, 'production'), ({'ZFT_ENV': 'production'}, 'production'), ({'ENV': 'development', 'ZFT_ENV': 'production'}, 'production')]:
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                self.assertEqual(config.get_environment(), expected)

    def test_local_file_selection_ignores_other_app(self):
        for filename in ['.env', 'ENV', 'ZFT_ENV']:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                app = root / 'bot'
                other = root / 'other-app'
                app.mkdir()
                other.mkdir()
                for source in ['config.py', 'utils.py', 'image_cache.py']:
                    source_path = Path(config.__file__).parent / source
                    if source_path.exists():
                        shutil.copy2(source_path, app / source)
                (other / '.env').write_text('ENV=development\nDISCORD_TOKEN_DEV=other_app\n', encoding='utf-8')
                (root / '.env').write_text('ENV=development\nDISCORD_TOKEN_DEV=parent_app\n', encoding='utf-8')
                (app / filename).write_text('ENV=production\nDISCORD_TOKEN_PROD=local_dummy\nGUILD_ID_PROD=123\nBIRTHDAY_CHANNEL_ID_PROD=456\nQUOTE_CHANNEL_ID_PROD=789\n', encoding='utf-8')
                env = os.environ.copy()
                for key in list(env):
                    if key in {'ENV', 'ZFT_ENV'} or key.startswith(('DISCORD_TOKEN_', 'GUILD_ID_', 'BIRTHDAY_CHANNEL_ID_', 'QUOTE_CHANNEL_ID_')):
                        env.pop(key)
                script = "import sys; sys.path.insert(0, sys.argv[1]); import config; assert config.ENV == 'production'; assert config.TOKEN == 'local_dummy'; assert (config.GUILD_ID, config.BIRTHDAY_CHANNEL_ID, config.QUOTE_CHANNEL_ID) == (123,456,789)"
                result = subprocess.run([sys.executable, '-c', script, str(app)], cwd=other, env=env, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_invalid_environment_rejected(self):
        for value in ['', 'prod', 'staging']:
            with patch.dict(os.environ, {'ENV': value}, clear=True):
                with self.assertRaises(ValueError):
                    config.get_environment()


class ProcessEnvironmentPrecedenceTests(unittest.TestCase):
    def test_process_selector_beats_file_alias(self):
        for process_key, file_key in [("ENV", "ZFT_ENV"), ("ZFT_ENV", "ENV")]:
            with self.subTest(process_key=process_key), tempfile.TemporaryDirectory() as directory:
                app = Path(directory)
                for name in ["config.py", "utils.py", "image_cache.py"]:
                    source = Path(config.__file__).parent / name
                    if source.exists():
                        shutil.copy2(source, app / name)
                (app / ".env").write_text(f"{file_key}=development\nDISCORD_TOKEN_DEV=file_dummy\n", encoding="utf-8")
                environment = os.environ.copy()
                for key in ["ENV", "ZFT_ENV"]:
                    environment.pop(key, None)
                environment.update({process_key: "production", "DISCORD_TOKEN_PROD": "process_dummy"})
                result = subprocess.run([sys.executable, "-c", "import config; assert config.ENV == 'production'; assert config.TOKEN == 'process_dummy'"], cwd=app, env=environment, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
