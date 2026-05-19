"""Tests for ChooserKeyBuffer — persistent tap + O(1) arm/disarm."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from wenzi.scripting.ui import chooser_key_buffer as ckb


@pytest.fixture
def patched_runner():
    """Replace CGEventTapRunner with a MagicMock that always 'succeeds'."""
    runner = MagicMock()
    runner.tap = 0xDEADBEEF  # non-zero → creation succeeded
    with patch.object(ckb, "CGEventTapRunner", return_value=runner):
        yield runner


@pytest.fixture
def patched_cg(monkeypatch):
    """Stub Core Graphics helpers so no real tap/events are touched."""
    monkeypatch.setattr(ckb, "CGEventCreateCopy", lambda ev: ev or 0)
    monkeypatch.setattr(ckb, "CFRelease", lambda obj: None)
    monkeypatch.setattr(ckb, "CGEventTapEnable", lambda *a, **k: None)
    # Default: no modifier flags on any event.
    monkeypatch.setattr(ckb, "CGEventGetFlags", lambda ev: 0)
    return monkeypatch


@pytest.fixture
def calllater_spy():
    """Record AppHelper.callLater invocations without actually scheduling."""
    calls = []

    def _fake_callLater(delay, fn, *args, **kwargs):
        calls.append((delay, fn, args, kwargs))

    with patch("PyObjCTools.AppHelper.callLater", side_effect=_fake_callLater):
        yield calls


@pytest.fixture
def callafter_spy():
    calls = []

    def _fake_callAfter(fn, *args, **kwargs):
        calls.append((fn, args, kwargs))

    with patch("PyObjCTools.AppHelper.callAfter", side_effect=_fake_callAfter):
        yield calls


def _installed_buffer():
    """Fresh instance with its persistent tap installed (via the mock)."""
    buf = ckb.ChooserKeyBuffer()
    buf.install()
    return buf


def _keycode_event(keycode: int) -> int:
    """Return an opaque sentinel for a CGEvent with the given keycode."""
    return 0x1000 + keycode


def _install_keycode_getter(monkeypatch, table: dict[int, int]) -> None:
    def _get(ev, field):
        return table.get(ev, 0)
    monkeypatch.setattr(ckb, "CGEventGetIntegerValueField", _get)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_install_is_idempotent(patched_runner, patched_cg):
    buf = ckb.ChooserKeyBuffer()
    buf.install()
    buf.install()
    # runner.start() should only be called on the first install
    assert patched_runner.start.call_count == 1


def test_arm_without_install_is_noop(patched_cg, calllater_spy):
    """arm() before install (or after a failed install) silently no-ops."""
    buf = ckb.ChooserKeyBuffer()
    buf.arm(lambda: True)
    assert not buf._armed
    assert calllater_spy == []


def test_not_armed_passes_through(patched_runner, patched_cg, monkeypatch):
    """Persistent tap is live but flag is False → events pass through."""
    buf = _installed_buffer()
    ev = _keycode_event(0)
    _install_keycode_getter(monkeypatch, {ev: 0})
    ret = buf._tap_callback(None, ckb.kCGEventKeyDown, ev, None)
    assert ret == ev  # passthrough
    assert buf._events == []


def test_arm_then_ready_replays_events(
    patched_runner, patched_cg, calllater_spy, monkeypatch,
):
    """Plain keys buffer; predicate True → events posted to NSApp."""
    buf = _installed_buffer()

    # Printable keycodes for 'a' (0), 's' (1), 'd' (2) — not literal
    # mappings; the test only cares they're in _BUFFERABLE_KEYCODES.
    events = [
        (_keycode_event(0), ckb.kCGEventKeyDown),
        (_keycode_event(0), ckb.kCGEventKeyUp),
        (_keycode_event(1), ckb.kCGEventKeyDown),
        (_keycode_event(1), ckb.kCGEventKeyUp),
    ]
    _install_keycode_getter(
        monkeypatch,
        {ev: code for ev, code in zip([e for e, _ in events], [0, 0, 1, 1])},
    )

    release_mock = MagicMock()
    monkeypatch.setattr(ckb, "CFRelease", release_mock)

    ready = [False]
    buf.arm(lambda: ready[0], timeout_s=10.0)

    for ev, etype in events:
        ret = buf._tap_callback(None, etype, ev, None)
        assert ret is None, "plain key events must be swallowed"

    assert len(calllater_spy) == 1
    _, poll_fn, _, _ = calllater_spy[0]
    fake_app = MagicMock()
    fake_ns_event_cls = MagicMock()
    fake_ns_event_cls.eventWithCGEvent_.side_effect = lambda ev: MagicMock(name=f"NS{ev}")
    with patch("AppKit.NSApp", return_value=fake_app), \
         patch("Cocoa.NSEvent", fake_ns_event_cls):
        poll_fn()
    assert len(calllater_spy) == 2, "second poll must be re-scheduled"
    assert release_mock.call_count == 0, "no CFRelease before replay"

    ready[0] = True
    _, poll_fn2, _, _ = calllater_spy[1]
    with patch("AppKit.NSApp", return_value=fake_app), \
         patch("Cocoa.NSEvent", fake_ns_event_cls):
        poll_fn2()

    assert fake_app.postEvent_atStart_.call_count == 4
    assert release_mock.call_count == 4, "each buffered event must be released"
    # Persistent tap — must NOT be torn down on disarm.
    patched_runner.stop.assert_not_called()


def test_modifier_event_aborts_and_drops(
    patched_runner, patched_cg, calllater_spy, callafter_spy, monkeypatch,
):
    """A cmd-bearing key triggers disarm-and-drop (tap stays alive)."""
    buf = _installed_buffer()
    _install_keycode_getter(monkeypatch, {0x42: 0})
    buf.arm(lambda: False, timeout_s=10.0)

    ret = buf._tap_callback(None, ckb.kCGEventKeyDown, 0x42, None)
    assert ret is None

    monkeypatch.setattr(ckb, "CGEventGetFlags", lambda ev: ckb.kCGEventFlagMaskCommand)
    ret = buf._tap_callback(None, ckb.kCGEventKeyDown, 0x99, None)
    assert ret == 0x99  # passthrough

    drop_fn = next(fn for fn, _, _ in callafter_spy if fn == buf._disarm_and_drop)
    drop_fn("modifier")
    patched_runner.stop.assert_not_called()
    assert not buf._armed


def test_timeout_drops_buffer(
    patched_runner, patched_cg, calllater_spy, monkeypatch,
):
    """Predicate never True → buffer dropped on timeout; tap stays alive."""
    buf = _installed_buffer()
    _install_keycode_getter(monkeypatch, {0x01: 0})
    buf.arm(lambda: False, timeout_s=0.05)
    buf._tap_callback(None, ckb.kCGEventKeyDown, 0x01, None)

    buf._armed_at = time.monotonic() - 10.0
    _, poll_fn, _, _ = calllater_spy[0]
    poll_fn()

    assert not buf._armed
    patched_runner.stop.assert_not_called()


def test_escape_aborts(
    patched_runner, patched_cg, calllater_spy, callafter_spy, monkeypatch,
):
    """Pressing Escape disarms without replay."""
    buf = _installed_buffer()
    esc_ev = _keycode_event(ckb._KC_ESCAPE)
    _install_keycode_getter(monkeypatch, {esc_ev: ckb._KC_ESCAPE})
    buf.arm(lambda: False, timeout_s=10.0)
    ret = buf._tap_callback(None, ckb.kCGEventKeyDown, esc_ev, None)
    assert ret == esc_ev  # passthrough

    drop_fn = next(fn for fn, _, _ in callafter_spy if fn == buf._disarm_and_drop)
    drop_fn("escape")
    assert not buf._armed


def test_non_bufferable_keycode_passes_through(
    patched_runner, patched_cg, calllater_spy, monkeypatch,
):
    """F-keys and the like are not buffered."""
    buf = _installed_buffer()
    f1_ev = _keycode_event(122)  # kVK_F1
    _install_keycode_getter(monkeypatch, {f1_ev: 122})
    buf.arm(lambda: False, timeout_s=10.0)
    ret = buf._tap_callback(None, ckb.kCGEventKeyDown, f1_ev, None)
    assert ret == f1_ev
    assert buf._events == []


def test_install_failure_is_silent(patched_cg, calllater_spy):
    """Accessibility denied → install() cleans up; arm() becomes a no-op."""
    bad_runner = MagicMock()
    bad_runner.tap = None  # simulate CGEventTapCreate returned NULL
    with patch.object(ckb, "CGEventTapRunner", return_value=bad_runner):
        buf = ckb.ChooserKeyBuffer()
        buf.install()
    assert buf._runner is None
    bad_runner.stop.assert_called_once()
    buf.arm(lambda: True)
    assert not buf._armed
    assert calllater_spy == []


def test_shutdown_releases_events_and_stops_runner(
    patched_runner, patched_cg, calllater_spy, monkeypatch,
):
    """shutdown() disarms, releases buffered events, and stops the tap."""
    buf = _installed_buffer()
    ev = _keycode_event(0)
    _install_keycode_getter(monkeypatch, {ev: 0})

    release_mock = MagicMock()
    monkeypatch.setattr(ckb, "CFRelease", release_mock)

    buf.arm(lambda: False, timeout_s=10.0)
    buf._tap_callback(None, ckb.kCGEventKeyDown, ev, None)
    assert len(buf._events) == 1

    buf.shutdown()

    assert not buf._armed
    assert buf._runner is None
    assert release_mock.call_count == 1
    patched_runner.stop.assert_called_once()
