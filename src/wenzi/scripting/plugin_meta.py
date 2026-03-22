"""Plugin metadata — parse plugin.toml from a plugin directory."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PLUGIN_TOML = "plugin.toml"


@dataclass
class PluginMeta:
    """Metadata for a WenZi plugin, read from plugin.toml."""

    name: str
    id: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    url: str = ""
    icon: str = ""
    min_wenzi_version: str = ""
    files: list[str] = field(default_factory=list)


def load_plugin_meta(plugin_dir: str) -> PluginMeta:
    """Load plugin metadata from *plugin_dir*/plugin.toml.

    Returns a :class:`PluginMeta` with all available fields populated.
    If the file is missing, malformed, or lacks a ``[plugin]`` section,
    falls back to using the directory name as the plugin name.
    """
    dir_name = os.path.basename(os.path.normpath(plugin_dir))
    toml_path = os.path.join(plugin_dir, PLUGIN_TOML)

    if not os.path.isfile(toml_path):
        return PluginMeta(name=dir_name)

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse %s, using defaults", toml_path, exc_info=True)
        return PluginMeta(name=dir_name)

    section = data.get("plugin")
    if not isinstance(section, dict):
        logger.warning("No [plugin] section in %s, using defaults", toml_path)
        return PluginMeta(name=dir_name)

    # Parse files — must be a list of strings
    raw_files = section.get("files", [])
    if isinstance(raw_files, str):
        raw_files = [raw_files]
    files = [str(f) for f in raw_files] if isinstance(raw_files, list) else []

    return PluginMeta(
        name=str(section.get("name", dir_name)),
        id=str(section.get("id", "")),
        description=str(section.get("description", "")),
        version=str(section.get("version", "")),
        author=str(section.get("author", "")),
        url=str(section.get("url", "")),
        icon=str(section.get("icon", "")),
        min_wenzi_version=str(section.get("min_wenzi_version", "")),
        files=files,
    )


INSTALL_TOML = "install.toml"
REQUEST_TIMEOUT = 30


def read_source(source: str) -> bytes:
    """Read from a local path or remote URL. Returns raw bytes."""
    from urllib.request import Request, urlopen

    if source.startswith(("http://", "https://")):
        req = Request(source, headers={"User-Agent": "WenZi-PluginManager"})
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    else:
        with open(source, "rb") as f:
            return f.read()


def find_plugin_dir(plugins_dir: str, plugin_id: str) -> str | None:
    """Find local plugin directory by scanning for matching bundle id."""
    if not os.path.isdir(plugins_dir):
        return None
    for entry in os.listdir(plugins_dir):
        entry_path = os.path.join(plugins_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        meta = load_plugin_meta(entry_path)
        if meta.id == plugin_id:
            return entry_path
    return None
