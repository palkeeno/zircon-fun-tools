"""Test bootstrap: every unittest entry point uses disposable settings and storage."""
import atexit
import os
from pathlib import Path
import tempfile

_storage = tempfile.TemporaryDirectory(prefix="zft-unit-")
atexit.register(_storage.cleanup)
for _key in list(os.environ):
    if _key in {"ENV", "ZFT_ENV", "ZFT_DATA_DIR", "ZFT_ENV_FILE", "ZIRCON_IMAGE_BASE_URL", "ZIRCON_CHARACTER_PAGE_URL"} or _key.startswith(("DISCORD_TOKEN_", "GUILD_ID_", "BIRTHDAY_CHANNEL_ID_", "QUOTE_CHANNEL_ID_", "POSTER_")):
        os.environ.pop(_key)
os.environ.update(ENV="development", DISCORD_TOKEN_DEV="test_dummy_token", GUILD_ID_DEV="123",
                  BIRTHDAY_CHANNEL_ID_DEV="0", QUOTE_CHANNEL_ID_DEV="0", POSTER_CHANNEL_ID="0",
                  ZFT_DATA_DIR=_storage.name, ZFT_ENV_FILE=str(Path(_storage.name) / "absent.env"))
