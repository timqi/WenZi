"""Screen capture using ScreenCaptureKit and CGWindowList.

Provides :func:`capture_screen`, which captures a screenshot of every connected
display and collects window metadata for the annotation overlay.

Requires macOS 13 (Ventura) or later — ScreenCaptureKit is used for actual
pixel capture.  ``CGWindowListCopyWindowInfo`` is used for window metadata
because it is synchronous and reliable.

Temp images are written to ``~/.cache/WenZi/screenshot_tmp/`` and should be
cleaned up by the caller after the annotation session ends.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum window dimensions to be considered visible.
_MIN_WIN_SIZE = 10

# Directory for temporary screenshot files (relative to DEFAULT_CACHE_DIR).
_SCREENSHOT_TMP_SUBDIR = "screenshot_tmp"


def _get_screenshot_tmp_dir() -> str:
    """Return the path to the temp screenshot directory (not yet created)."""
    from wenzi.config import DEFAULT_CACHE_DIR
    return os.path.join(os.path.expanduser(DEFAULT_CACHE_DIR), _SCREENSHOT_TMP_SUBDIR)


# ---------------------------------------------------------------------------
# Window metadata
# ---------------------------------------------------------------------------

def _collect_window_metadata() -> List[Dict[str, Any]]:
    """Return filtered, sorted window metadata via CGWindowList.

    Each dict contains:
    - ``bounds``: ``{"x": float, "y": float, "width": float, "height": float}``
    - ``title``: window title (may be empty string)
    - ``app``: owning application name (may be empty string)
    - ``layer``: window layer (z-order); higher = more on top
    - ``window_id``: CoreGraphics window ID

    Filtering rules (invisible windows are excluded):
    - ``layer < 0``  — background/desktop layers
    - width < 10 or height < 10  — too small to interact with
    - both ``title`` and ``app`` are empty — unidentifiable system elements
    """
    import Quartz

    options = Quartz.kCGWindowListOptionAll
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    if not window_list:
        return []

    windows: List[Dict[str, Any]] = []
    for info in window_list:
        layer = info.get("kCGWindowLayer", 0)
        if layer < 0:
            continue

        bounds_raw = info.get("kCGWindowBounds", {})
        width = float(bounds_raw.get("Width", 0))
        height = float(bounds_raw.get("Height", 0))
        if width < _MIN_WIN_SIZE or height < _MIN_WIN_SIZE:
            continue

        title = info.get("kCGWindowName", "") or ""
        app = info.get("kCGWindowOwnerName", "") or ""
        if not title and not app:
            continue

        bounds = {
            "x": float(bounds_raw.get("X", 0)),
            "y": float(bounds_raw.get("Y", 0)),
            "width": width,
            "height": height,
        }
        windows.append(
            {
                "bounds": bounds,
                "title": title,
                "app": app,
                "layer": layer,
                "window_id": info.get("kCGWindowNumber", 0),
            }
        )

    # Sort: higher layer first; within same layer, smaller area first
    # (so the "smallest containing window" is found first during hit-testing).
    windows.sort(key=lambda w: (-w["layer"], w["bounds"]["width"] * w["bounds"]["height"]))
    return windows


# ---------------------------------------------------------------------------
# Screen capture via ScreenCaptureKit
# ---------------------------------------------------------------------------

def _capture_displays_sync() -> Dict[int, Any]:
    """Capture every display using ScreenCaptureKit.

    Returns ``{display_id: CGImage}`` for each online display.

    Blocks the calling thread until all captures complete (uses a
    threading.Event to bridge the async completion handler).
    """
    import ScreenCaptureKit as SCK  # type: ignore[import]

    result: Dict[int, Any] = {}
    error_holder: List[Optional[Exception]] = [None]

    ready = threading.Event()

    def _on_shareable_content(content, error):
        if error:
            error_holder[0] = RuntimeError(f"SCShareableContent error: {error}")
            ready.set()
            return

        displays = content.displays()
        if not displays:
            ready.set()
            return

        remaining = [len(displays)]
        lock = threading.Lock()

        for display in displays:
            display_id = int(display.displayID())

            filter_ = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(
                display, []
            )
            config = SCK.SCScreenshotManager.defaultScreenshotConfiguration()

            def _on_image(image, _display_id=display_id, error=None):  # noqa: B023
                if image is not None:
                    with lock:
                        result[_display_id] = image
                with lock:
                    remaining[0] -= 1
                    if remaining[0] == 0:
                        ready.set()

            SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                filter_, config, _on_image
            )

    SCK.SCShareableContent.getWithCompletionHandler_(_on_shareable_content)

    ready.wait(timeout=10.0)

    if error_holder[0]:
        raise error_holder[0]

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture_screen() -> Dict[str, Any]:
    """Capture screenshots of all displays and collect window metadata.

    Returns a dict::

        {
            "displays": {
                <display_id: int>: <CGImage>,
                ...
            },
            "windows": [
                {
                    "bounds": {"x": float, "y": float, "width": float, "height": float},
                    "title": str,
                    "app": str,
                    "layer": int,
                    "window_id": int,
                },
                ...
            ],
        }

    ``displays`` contains one entry per connected display.
    ``windows`` is sorted: higher layer first, smaller area first within a layer.

    The caller is responsible for cleaning up any temp files written to
    ``~/.cache/WenZi/screenshot_tmp/``.

    Raises ``RuntimeError`` on capture failure.
    """
    tmp_dir = _get_screenshot_tmp_dir()
    os.makedirs(tmp_dir, exist_ok=True)

    logger.debug("Collecting window metadata via CGWindowList")
    windows = _collect_window_metadata()
    logger.debug("Found %d visible windows", len(windows))

    logger.debug("Capturing display screenshots via ScreenCaptureKit")
    displays = _capture_displays_sync()
    logger.debug("Captured %d display(s)", len(displays))

    return {
        "displays": displays,
        "windows": windows,
    }
