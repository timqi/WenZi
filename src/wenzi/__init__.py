"""WenZi (闻字) - macOS menubar speech-to-text app."""

import os
import sys

if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle — use the real version
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("wenzi")
    except PackageNotFoundError:
        __version__ = "0.0.0-dev"
else:
    # Running via uv run / python — always dev
    __version__ = "dev"


def get_version() -> str:
    """Return the current app version, honoring WENZI_DEV_VERSION env var."""
    return os.environ.get("WENZI_DEV_VERSION") or __version__
