"""Tests for wenzi.screenshot.annotation.

Pure-logic helpers are tested directly. PyObjC-dependent code is tested
via mocks — the module defers all AppKit/WebKit imports to call time.
"""

from __future__ import annotations

import base64
import struct


# ---------------------------------------------------------------------------
# decode_data_url tests
# ---------------------------------------------------------------------------


class TestDecodeDataUrl:
    def test_valid_png_data_url(self):
        from wenzi.screenshot.annotation import decode_data_url

        raw = b"\x89PNG\r\n\x1a\nfake"
        url = "data:image/png;base64," + base64.b64encode(raw).decode()
        assert decode_data_url(url) == raw

    def test_empty_payload(self):
        from wenzi.screenshot.annotation import decode_data_url

        result = decode_data_url("data:image/png;base64,")
        assert result == b""

    def test_wrong_prefix_returns_none(self):
        from wenzi.screenshot.annotation import decode_data_url

        assert decode_data_url("data:image/jpeg;base64,abc") is None

    def test_invalid_base64_returns_none(self):
        from wenzi.screenshot.annotation import decode_data_url

        assert decode_data_url("data:image/png;base64,!!!invalid!!!") is None


# ---------------------------------------------------------------------------
# get_image_dimensions tests
# ---------------------------------------------------------------------------


def _make_minimal_png(width: int, height: int) -> bytes:
    """Build a minimal valid PNG header (signature + IHDR)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_crc = b"\x00" * 4
    ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    return sig + ihdr_chunk


class TestGetImageDimensions:
    def test_valid_png(self, tmp_path):
        from wenzi.screenshot.annotation import get_image_dimensions

        png_path = tmp_path / "test.png"
        png_path.write_bytes(_make_minimal_png(1024, 768))

        w, h = get_image_dimensions(str(png_path))
        assert w == 1024
        assert h == 768

    def test_small_image(self, tmp_path):
        from wenzi.screenshot.annotation import get_image_dimensions

        png_path = tmp_path / "small.png"
        png_path.write_bytes(_make_minimal_png(50, 30))

        w, h = get_image_dimensions(str(png_path))
        assert w == 50
        assert h == 30

    def test_non_png_returns_fallback(self, tmp_path):
        from wenzi.screenshot.annotation import get_image_dimensions

        txt = tmp_path / "not_a_png.txt"
        txt.write_text("hello")
        assert get_image_dimensions(str(txt)) == (800, 600)

    def test_missing_file_returns_fallback(self):
        from wenzi.screenshot.annotation import get_image_dimensions

        assert get_image_dimensions("/nonexistent/path.png") == (800, 600)


# ---------------------------------------------------------------------------
# AnnotationLayer unit tests (no PyObjC)
# ---------------------------------------------------------------------------


class TestAnnotationLayerInit:
    def test_initial_state(self):
        from wenzi.screenshot.annotation import AnnotationLayer

        layer = AnnotationLayer()
        assert layer._open is False
        assert layer._panel is None
        assert layer._image_path is None

    def test_show_missing_image_calls_cancel(self, tmp_path):
        from wenzi.screenshot.annotation import AnnotationLayer

        layer = AnnotationLayer()
        cancelled = []
        layer.show(
            image_path=str(tmp_path / "missing.png"),
            on_done=lambda: None,
            on_cancel=lambda: cancelled.append(True),
        )
        assert cancelled == [True]
        assert layer._open is False


# ---------------------------------------------------------------------------
# Event handling tests
# ---------------------------------------------------------------------------


class TestEventHandling:
    def _make_layer(self):
        from wenzi.screenshot.annotation import AnnotationLayer

        layer = AnnotationLayer()
        layer._open = True
        return layer

    def test_confirm_triggers_export(self):
        layer = self._make_layer()
        sent_events = []
        layer._send_event = lambda ev, data=None: sent_events.append(ev)

        layer._handle_event("confirm", None)
        assert layer._pending_action == "clipboard"
        assert "export" in sent_events

    def test_save_triggers_export(self):
        layer = self._make_layer()
        sent_events = []
        layer._send_event = lambda ev, data=None: sent_events.append(ev)

        layer._handle_event("save", None)
        assert layer._pending_action == "save"
        assert "export" in sent_events

    def test_cancel_calls_callback(self):
        layer = self._make_layer()
        cancelled = []
        layer._on_cancel = lambda: cancelled.append(True)

        layer._handle_event("cancel", None)
        assert cancelled == [True]

    def test_exported_clipboard_action(self):
        layer = self._make_layer()
        layer._pending_action = "clipboard"
        done = []
        layer._on_done = lambda: done.append(True)
        layer._copy_to_clipboard = lambda png: None
        layer._play_sound = lambda: None

        raw = b"\x89PNG"
        data_url = "data:image/png;base64," + base64.b64encode(raw).decode()
        layer._handle_exported({"dataUrl": data_url})

        assert done == [True]

    def test_exported_no_pending_action_ignored(self):
        layer = self._make_layer()
        layer._pending_action = None

        raw = b"\x89PNG"
        data_url = "data:image/png;base64," + base64.b64encode(raw).decode()
        layer._handle_exported({"dataUrl": data_url})

    def test_exported_none_data_ignored(self):
        layer = self._make_layer()
        layer._pending_action = "clipboard"
        layer._handle_exported(None)

    def test_js_message_routes_event(self):
        layer = self._make_layer()
        events = []
        layer._handle_event = lambda name, data: events.append(name)

        layer._handle_js_message({"type": "event", "name": "confirm", "data": None})
        assert events == ["confirm"]

    def test_js_message_routes_console(self):
        layer = self._make_layer()
        layer._handle_js_message({"type": "console", "level": "info", "message": "test"})

    def test_close_idempotent(self):
        from wenzi.screenshot.annotation import AnnotationLayer

        layer = AnnotationLayer()
        layer.close()  # not open, should not raise
        layer.close()  # still fine
