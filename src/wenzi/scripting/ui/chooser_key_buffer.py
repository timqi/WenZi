"""Buffer keystrokes during chooser show() and replay when ready.

NSEvent creation is confined to the main thread — see ``wenzi/hotkey.py``
for why creating AppKit objects on the tap thread is unsafe.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from wenzi._cgeventtap import (
    CFRelease,
    CGEventCreateCopy,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapEnable,
    CGEventTapRunner,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapDisabledByTimeout,
    kCGKeyboardEventKeycode,
)

logger = logging.getLogger(__name__)

# Shift excluded so capital letters (shift+b → "B") still buffer.
_NON_SHIFT_MODIFIER_MASK = (
    kCGEventFlagMaskCommand
    | kCGEventFlagMaskControl
    | kCGEventFlagMaskAlternate
)

_KC_DELETE = 51
_KC_ESCAPE = 53
_KC_LEFT = 123
_KC_RIGHT = 124
_KC_DOWN = 125
_KC_UP = 126

_BUFFERABLE_KEYCODES = frozenset(range(0, 51)) | {
    _KC_DELETE,
    _KC_LEFT,
    _KC_RIGHT,
    _KC_DOWN,
    _KC_UP,
}

_POLL_INTERVAL_S = 0.016
_DEFAULT_TIMEOUT_S = 0.8
_TAP_READY_WAIT_S = 0.05


class ChooserKeyBuffer:
    def __init__(self) -> None:
        self._runner: CGEventTapRunner | None = None
        self._events: list[tuple[int, int]] = []
        self._armed = False
        self._lock = threading.Lock()
        self._armed_at = 0.0
        self._timeout_s = _DEFAULT_TIMEOUT_S
        self._ready_predicate: Callable[[], bool] | None = None
        self._on_ready: Callable[[], None] | None = None

    def install(self) -> None:
        """Create the persistent CGEventTap.  Idempotent.  Main-thread only.

        Must be called before any hotkey tap registers so that the hotkey
        tap sits at HEAD and sees events first (swallows the chooser
        hotkey before our buffer ever sees it).
        """
        if self._runner is not None:
            return
        runner = CGEventTapRunner()
        mask = (
            CGEventMaskBit(kCGEventKeyDown)
            | CGEventMaskBit(kCGEventKeyUp)
            | CGEventMaskBit(kCGEventFlagsChanged)
        )
        runner.start(mask, self._tap_callback)
        runner.wait_ready(_TAP_READY_WAIT_S)
        if runner.tap is None:
            logger.warning(
                "ChooserKeyBuffer: tap create failed — keystrokes may be "
                "lost during chooser show (check Accessibility permission)"
            )
            runner.stop()
            return
        self._runner = runner

    def shutdown(self) -> None:
        """Stop the tap and release any buffered events.  Main-thread only."""
        with self._lock:
            self._armed = False
            events = self._events
            self._events = []
            self._ready_predicate = None
            self._on_ready = None
        for cg_event, _ in events:
            CFRelease(cg_event)
        runner = self._runner
        self._runner = None
        if runner is not None:
            runner.stop()

    def arm(
        self,
        ready_predicate: Callable[[], bool],
        *,
        on_ready: Callable[[], None] | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        """Start buffering keystrokes.  O(1) flag flip; relies on a persistent
        tap installed by ``install()``.  Main-thread only.

        Safe to call from the hotkey tap thread as well (the lock makes
        field updates atomic and no AppKit is touched here)."""
        if self._runner is None:
            # install() never called or failed — silently no-op.
            return
        with self._lock:
            already = self._armed
            self._armed = True
            self._armed_at = time.monotonic()
            self._timeout_s = max(0.05, timeout_s)
            self._ready_predicate = ready_predicate
            self._on_ready = on_ready
            if not already:
                self._events = []
        if not already:
            self._schedule_poll()

    def disarm(self) -> None:
        self._disarm_and_drop("external")

    def _schedule_poll(self) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callLater(_POLL_INTERVAL_S, self._poll_once)

    def _poll_once(self) -> None:
        try:
            with self._lock:
                if not self._armed:
                    return
                elapsed = time.monotonic() - self._armed_at
                predicate = self._ready_predicate
                timeout = self._timeout_s
            if elapsed >= timeout:
                self._disarm_and_drop("timeout")
                return
            if predicate is not None and predicate():
                self._disarm_and_replay()
                return
        except Exception:
            logger.warning("chooser key buffer: poll error", exc_info=True)
        self._schedule_poll()

    def _tap_callback(self, proxy, event_type, event, refcon):
        try:
            if event_type == kCGEventTapDisabledByTimeout:
                runner = self._runner
                if runner is not None and runner.tap:
                    CGEventTapEnable(runner.tap, True)
                return event
            with self._lock:
                if not self._armed:
                    return event
            if event_type == kCGEventFlagsChanged:
                return event
            flags = CGEventGetFlags(event)
            if flags & _NON_SHIFT_MODIFIER_MASK:
                self._request_disarm("modifier")
                return event
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if keycode == _KC_ESCAPE:
                self._request_disarm("escape")
                return event
            if keycode not in _BUFFERABLE_KEYCODES:
                return event
            if event_type not in (kCGEventKeyDown, kCGEventKeyUp):
                return event
            copy = CGEventCreateCopy(event)
            if not copy:
                return event
            with self._lock:
                if not self._armed:
                    CFRelease(copy)
                    return event
                self._events.append((copy, event_type))
            return None
        except Exception:
            logger.warning(
                "chooser key buffer: tap callback error", exc_info=True,
            )
            return event

    def _request_disarm(self, reason: str) -> None:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(self._disarm_and_drop, reason)

    def _consume_armed_state(
        self,
    ) -> tuple[list[tuple[int, int]], Callable[[], None] | None] | None:
        """Atomically clear armed state. Returns (events, on_ready), or None
        if already disarmed (caller should bail)."""
        with self._lock:
            if not self._armed:
                return None
            self._armed = False
            events = self._events
            self._events = []
            on_ready = self._on_ready
            self._on_ready = None
            self._ready_predicate = None
        return events, on_ready

    def _disarm_and_drop(self, reason: str) -> None:
        consumed = self._consume_armed_state()
        if consumed is None:
            return
        events, _ = consumed
        if events:
            logger.info(
                "chooser key buffer: dropped %d event(s) (reason=%s)",
                len(events), reason,
            )
        for cg_event, _ in events:
            CFRelease(cg_event)

    def _disarm_and_replay(self) -> None:
        consumed = self._consume_armed_state()
        if consumed is None:
            return
        events, on_ready = consumed
        if on_ready is not None:
            try:
                on_ready()
            except Exception:
                logger.warning(
                    "chooser key buffer: on_ready raised", exc_info=True,
                )
        if events:
            logger.debug(
                "chooser key buffer: replaying %d event(s)", len(events),
            )
            self._post_events(events)

    def _post_events(self, events: list[tuple[int, int]]) -> None:
        from AppKit import NSApp
        from Cocoa import NSEvent

        app = NSApp()
        for cg_event, _event_type in events:
            try:
                ns_event = NSEvent.eventWithCGEvent_(cg_event)
                if ns_event is not None and app is not None:
                    app.postEvent_atStart_(ns_event, False)
            except Exception:
                logger.warning(
                    "chooser key buffer: postEvent failed", exc_info=True,
                )
            CFRelease(cg_event)


shared = ChooserKeyBuffer()
