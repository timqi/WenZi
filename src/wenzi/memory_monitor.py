"""Periodic memory snapshots and window lifecycle logging.

Emits greppable log lines so memory growth can be correlated with
panel open/close events from historical logs.

Log line formats:

    memory_snapshot rss=183.5M footprint=144.0M iosurface_dirty=64.2M \
      iosurface_count=42 ca_whippet_count=1 ca_whippet_total=63.3M largest=63.3M@3840x2160

    window_event event=became_key class=SettingsPanel visible=1 frame=0,0,3840,2160
    window_event event=will_close class=SettingsPanel visible=1 frame=0,0,3840,2160

    window_inventory count=3 items=NSStatusBarWindow:1:320x22;WenZiChooserPanel:0:520x49;...
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading

logger = logging.getLogger(__name__)

_SNAPSHOT_INTERVAL = 30.0
_VMMAP_TIMEOUT = 10
_PS_TIMEOUT = 5

_timer = None
_timer_target = None
_observers: list = []
_started = False


def _to_mb(s: str) -> float:
    """Parse a vmmap size like '63.3M', '512K', '1.2G' into MB."""
    s = s.strip()
    if not s:
        return 0.0
    m = re.fullmatch(r"([\d.]+)([KMGT]?)", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "K":
        return val / 1024
    if unit == "G":
        return val * 1024
    if unit == "T":
        return val * 1024 * 1024
    return val  # M or bare


def _rss_mb(pid: int) -> float:
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=_PS_TIMEOUT,
        ).stdout.strip()
        return int(out) / 1024 if out else 0.0
    except Exception:
        return 0.0


def _parse_vmmap(pid: int) -> dict:
    """Run `vmmap` and extract footprint + IOSurface + CA Whippet Drawable stats.

    `vmmap` output has per-region DETAIL lines (with hex address ranges) first,
    then a SUMMARY section at the end (started by "==== Summary"). IOSurface
    appears in BOTH: detail lines look like
        "IOSurface   113e14000-113e18000    [   16K     0K ...]"
    while the summary row is
        "IOSurface   100.9M  0K  0K  0K  0K  0K  0K  60"
    We only want the summary aggregate, so parse only after the summary marker.

    CA Whippet Drawable is a user tag, not a region type, so it only appears in
    the detail section; we scan the full output for those lines.
    """
    result = {
        "footprint_mb": 0.0,
        "iosurface_dirty_mb": 0.0,
        "iosurface_count": 0,
        "ca_whippet_count": 0,
        "ca_whippet_total_mb": 0.0,
        "ca_whippet_largest": "",
    }
    try:
        out = subprocess.run(
            ["vmmap", str(pid)],
            capture_output=True, text=True, timeout=_VMMAP_TIMEOUT,
        ).stdout
    except Exception:
        return result

    m = re.search(r"Physical footprint:\s+([\d.]+[KMGT]?)", out)
    if m:
        result["footprint_mb"] = _to_mb(m.group(1))

    # Split off just the summary section to avoid matching detail rows.
    summary_split = re.split(r"\n==== Summary\b", out, maxsplit=1)
    summary = summary_split[1] if len(summary_split) > 1 else ""

    # Summary row: "IOSurface  VIRTUAL  RESIDENT  DIRTY  SWAPPED  VOLATILE  NONVOL  EMPTY  COUNT"
    # DIRTY is the 3rd size token, region count is the last integer token.
    for line in summary.splitlines():
        if not line.startswith("IOSurface"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            result["iosurface_dirty_mb"] = _to_mb(parts[3])
            for tok in reversed(parts):
                if tok.isdigit():
                    result["iosurface_count"] = int(tok)
                    break
        except (ValueError, IndexError):
            pass
        break

    largest_mb = 0.0
    largest_dim = ""
    whippet_count = 0
    whippet_total = 0.0
    for line in out.splitlines():
        if "'CA Whippet Drawable'" not in line:
            continue
        whippet_count += 1
        m_sz = re.search(r"\[\s*([\d.]+[KMG]?)\s+([\d.]+[KMG]?)", line)
        if m_sz:
            dirty = _to_mb(m_sz.group(2))
            whippet_total += dirty
            if dirty > largest_mb:
                largest_mb = dirty
                m_dim = re.search(r"(\d+)x(\d+)\s+\(", line)
                largest_dim = f"{m_dim.group(1)}x{m_dim.group(2)}" if m_dim else "?"
    result["ca_whippet_count"] = whippet_count
    result["ca_whippet_total_mb"] = whippet_total
    if whippet_count:
        result["ca_whippet_largest"] = f"{largest_mb:.1f}M@{largest_dim}"
    return result


def _log_window_inventory() -> None:
    """Log class + visibility + frame of every NSApp.windows() entry."""
    try:
        from AppKit import NSApp

        windows = NSApp.windows()
        items = []
        for w in windows:
            try:
                cls = str(w.className())
            except Exception:
                cls = "?"
            try:
                vis = 1 if w.isVisible() else 0
            except Exception:
                vis = 0
            try:
                f = w.frame()
                size = f"{int(f.size.width)}x{int(f.size.height)}"
            except Exception:
                size = "?"
            items.append(f"{cls}:{vis}:{size}")
        logger.info(
            "window_inventory count=%d items=%s",
            len(items), ";".join(items) or "-",
        )
    except Exception:
        logger.debug("Failed to log window inventory", exc_info=True)


def _run_snapshot_on_worker() -> None:
    """Run vmmap/ps on a worker thread, then marshal inventory + log to main."""
    pid = os.getpid()
    rss = _rss_mb(pid)
    vm = _parse_vmmap(pid)

    def _emit() -> None:
        logger.info(
            "memory_snapshot rss=%.1fM footprint=%.1fM iosurface_dirty=%.1fM "
            "iosurface_count=%d ca_whippet_count=%d ca_whippet_total=%.1fM largest=%s",
            rss, vm["footprint_mb"], vm["iosurface_dirty_mb"],
            vm["iosurface_count"], vm["ca_whippet_count"],
            vm["ca_whippet_total_mb"], vm["ca_whippet_largest"] or "n/a",
        )
        _log_window_inventory()

    from PyObjCTools import AppHelper
    AppHelper.callAfter(_emit)


def _timer_fire() -> None:
    # Offload the subprocess calls off the main thread so the event loop
    # doesn't block on vmmap (~50–200 ms on a busy process).
    threading.Thread(
        target=_run_snapshot_on_worker, daemon=True, name="memory-monitor",
    ).start()


def _describe_window(note) -> tuple[str, int, str]:
    try:
        w = note.object()
        cls = str(w.className())
        vis = 1 if w.isVisible() else 0
        f = w.frame()
        frame_s = f"{int(f.origin.x)},{int(f.origin.y)},{int(f.size.width)},{int(f.size.height)}"
        return cls, vis, frame_s
    except Exception:
        return "?", 0, "?"


def _on_became_key(note) -> None:
    cls, vis, frame_s = _describe_window(note)
    logger.info("window_event event=became_key class=%s visible=%d frame=%s", cls, vis, frame_s)


def _on_will_close(note) -> None:
    cls, vis, frame_s = _describe_window(note)
    logger.info("window_event event=will_close class=%s visible=%d frame=%s", cls, vis, frame_s)


def _on_occlusion_change(note) -> None:
    cls, vis, frame_s = _describe_window(note)
    logger.info(
        "window_event event=occlusion class=%s visible=%d frame=%s",
        cls, vis, frame_s,
    )


def start() -> None:
    """Begin periodic snapshots and window event logging. Idempotent."""
    global _timer, _timer_target, _started
    if _started:
        return
    _started = True

    from AppKit import (
        NSTimer,
        NSWindowDidBecomeKeyNotification,
        NSWindowDidChangeOcclusionStateNotification,
        NSWindowWillCloseNotification,
    )
    from Foundation import NSObject

    nc_callbacks = (
        (NSWindowDidBecomeKeyNotification, _on_became_key),
        (NSWindowWillCloseNotification, _on_will_close),
        (NSWindowDidChangeOcclusionStateNotification, _on_occlusion_change),
    )
    from Foundation import NSNotificationCenter
    center = NSNotificationCenter.defaultCenter()
    for name, cb in nc_callbacks:
        obs = center.addObserverForName_object_queue_usingBlock_(name, None, None, cb)
        _observers.append(obs)

    class _MemMonitorTarget(NSObject):
        def fire_(self, _timer):  # noqa: N802
            _timer_fire()

    _timer_target = _MemMonitorTarget.alloc().init()
    _timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        _SNAPSHOT_INTERVAL, _timer_target, b"fire:", None, True,
    )
    # Fire an initial snapshot immediately so baseline is in the log.
    _timer_fire()
    logger.info("memory_monitor started interval=%.0fs", _SNAPSHOT_INTERVAL)


def stop() -> None:
    """Stop the timer and unregister observers."""
    global _timer, _started
    if not _started:
        return
    if _timer is not None:
        try:
            _timer.invalidate()
        except Exception:
            pass
        _timer = None
    from Foundation import NSNotificationCenter
    center = NSNotificationCenter.defaultCenter()
    for obs in _observers:
        try:
            center.removeObserver_(obs)
        except Exception:
            pass
    _observers.clear()
    _started = False
