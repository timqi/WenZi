"""Integration tests for screenshot wiring in config.py and app.py.

These tests verify:
- DEFAULT_CONFIG contains the screenshot section with expected defaults
- _show_annotation_ui creates AnnotationLayer and calls show
- _on_screenshot_done / _on_screenshot_cancel clean up properly
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_default_config_has_screenshot_section():
    from wenzi.config import DEFAULT_CONFIG

    assert "screenshot" in DEFAULT_CONFIG


def test_default_config_screenshot_hotkey():
    from wenzi.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["screenshot"]["hotkey"] == "cmd+shift+a"


def test_default_config_screenshot_save_directory():
    from wenzi.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["screenshot"]["save_directory"] == "~/Desktop"


def test_default_config_screenshot_sound_enabled():
    from wenzi.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["screenshot"]["sound_enabled"] is True


# ---------------------------------------------------------------------------
# App method tests
# ---------------------------------------------------------------------------


class _FakeApp:
    """Minimal stand-in for WenZiApp that only has the screenshot methods."""

    def __init__(self):
        self._screenshot_annotation = None


def _attach_methods(obj):
    """Bind the real screenshot methods from WenZiApp onto a fake instance."""
    import types
    from wenzi import app as app_module

    for name in ("_on_screenshot", "_show_annotation_ui",
                 "_on_screenshot_done", "_on_screenshot_cancel"):
        method = getattr(app_module.WenZiApp, name)
        setattr(obj, name, types.MethodType(method, obj))


@pytest.fixture()
def fake_app():
    """Return a _FakeApp with screenshot methods bound to it."""
    obj = _FakeApp()
    _attach_methods(obj)
    return obj


@pytest.fixture()
def mock_screenshot_module():
    """Patch wenzi.screenshot so no real AppKit code runs."""
    mock_annotation = MagicMock()

    mock_module = MagicMock()
    mock_module.AnnotationLayer.return_value = mock_annotation

    with patch.dict(sys.modules, {"wenzi.screenshot": mock_module}):
        yield {
            "module": mock_module,
            "annotation": mock_annotation,
        }


def test_show_annotation_ui_creates_annotation(fake_app, mock_screenshot_module):
    """_show_annotation_ui should create AnnotationLayer and call show()."""
    mocks = mock_screenshot_module
    mod = mocks["module"]

    fake_app._show_annotation_ui("/tmp/test.png")

    mod.AnnotationLayer.assert_called_once()
    mocks["annotation"].show.assert_called_once()
    call_kwargs = mocks["annotation"].show.call_args
    assert call_kwargs[1]["image_path"] == "/tmp/test.png"


def test_show_annotation_ui_stores_instance(fake_app, mock_screenshot_module):
    """After _show_annotation_ui, the annotation is stored on the app."""
    mocks = mock_screenshot_module

    fake_app._show_annotation_ui("/tmp/test.png")

    assert fake_app._screenshot_annotation is mocks["annotation"]


def test_on_screenshot_done_clears_annotation(fake_app):
    mock_ann = MagicMock()
    fake_app._screenshot_annotation = mock_ann

    fake_app._on_screenshot_done()

    mock_ann.close.assert_called_once()
    assert fake_app._screenshot_annotation is None


def test_on_screenshot_done_no_annotation_is_safe(fake_app):
    fake_app._screenshot_annotation = None
    fake_app._on_screenshot_done()  # must not raise


def test_on_screenshot_cancel_closes_annotation(fake_app):
    mock_ann = MagicMock()
    fake_app._screenshot_annotation = mock_ann

    fake_app._on_screenshot_cancel()

    mock_ann.close.assert_called_once()
    assert fake_app._screenshot_annotation is None


def test_on_screenshot_cancel_no_objects_is_safe(fake_app):
    fake_app._screenshot_annotation = None
    fake_app._on_screenshot_cancel()  # must not raise
