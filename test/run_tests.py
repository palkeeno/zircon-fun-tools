"""実データ・認証情報に触れず、一時コピー上でテストを実行する。"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run_tests():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="zft-tests-") as directory:
        destination = Path(directory)
        for name in ["main.py", "config.py", "utils.py", "image_cache.py", "poster_cache.py", "quote_records.py", "birthday_records.py", "command_errors.py", "setup_fonts.py", "cogs", "test", "scripts"]:
            source = root / name
            if not source.exists():
                continue
            if source.is_dir():
                shutil.copytree(source, destination / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, destination / name)
        environment = os.environ.copy()
        for key in list(environment):
            if key in {"ENV", "ZFT_ENV", "ZFT_ENV_FILE", "ZFT_DATA_DIR", "ZIRCON_IMAGE_BASE_URL", "ZIRCON_CHARACTER_PAGE_URL"} or key.startswith(("DISCORD_TOKEN_", "GUILD_ID_", "BIRTHDAY_CHANNEL_ID_", "QUOTE_CHANNEL_ID_", "POSTER_")):
                environment.pop(key)
        environment.update(PYTHONIOENCODING="utf-8", ENV="development", DISCORD_TOKEN_DEV="test_dummy_token", GUILD_ID_DEV="123", BIRTHDAY_CHANNEL_ID_DEV="0", QUOTE_CHANNEL_ID_DEV="0", POSTER_CHANNEL_ID="0")
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "test", "-v"], cwd=destination, env=environment)
        return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
