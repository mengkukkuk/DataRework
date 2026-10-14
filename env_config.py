"""Environment loading shared by the GUI and the sync service entry points.

Precedence, highest first: real OS environment > external .env next to the exe
> .env embedded in the exe. The embedded copy supplies every key, so a partial
external file only needs the values being changed. Edit the external file and
relaunch (restart the sync service) instead of rebuilding.

Call load_env() before importing db / main_window: they read os.environ at
import time.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import envcrypt

SECRET_VARS = ("DB_PASSWORD",)


def load_env():
    bundled = Path(__file__).resolve().parent / ".env"  # source tree, or _MEIPASS when frozen
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).resolve().parent / ".env"
    else:
        external = bundled
    # load_dotenv does not override existing values, so loading the external
    # file first lets it win over the embedded one.
    load_dotenv(external)
    load_dotenv(bundled)
    for name in SECRET_VARS:
        value = os.environ.get(name)
        if envcrypt.is_encrypted(value):
            try:
                os.environ[name] = envcrypt.decrypt(value)
            except ValueError as exc:
                raise RuntimeError(f"{name} in .env could not be decrypted: {exc}") from exc
