"""Debug script: use Quartz event tap to capture all key events including fn."""

import Quartz
from AppKit import NSEvent


def callback(proxy, event_type, event, refcon):
    ns_event = NSEvent.eventWithCGEvent_(event)
    if ns_event is None:
        return event

    type_name = {
        10: "keyDown",
        11: "keyUp",
        12: "flagsChanged",
    }.get(event_type, f"type({event_type})")

    keycode = ns_event.keyCode()
    flags = ns_event.modifierFlags()
    chars = ""
    if event_type in (10, 11):
        try:
            chars = ns_event.characters()
        except Exception:
            pass

    print(
        f"{type_name:15s}  keyCode={keycode:<4d}  "
        f"flags=0x{flags:08x}  chars={chars!r}"
    )

    # fn key is keyCode 63
    if keycode == 63:
        fn_down = bool(flags & 0x800000)  # NSEventModifierFlagFunction
        print(f"  >>> fn key detected! fn_down={fn_down}")

    return event


print("Listening for ALL key events via Quartz... Press Ctrl+C to quit.")
print("Try pressing fn, f2, and other keys.\n")

mask = (
    Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
    | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
)

tap = Quartz.CGEventTapCreate(
    Quartz.kCGSessionEventTap,
    Quartz.kCGHeadInsertEventTap,
    Quartz.kCGEventTapOptionListenOnly,
    mask,
    callback,
    None,
)

if tap is None:
    print("ERROR: Failed to create event tap. Check accessibility permissions.")
    exit(1)

source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
loop = Quartz.CFRunLoopGetCurrent()
Quartz.CFRunLoopAddSource(loop, source, Quartz.kCFRunLoopDefaultMode)
Quartz.CGEventTapEnable(tap, True)

try:
    Quartz.CFRunLoopRun()
except KeyboardInterrupt:
    print("\nDone.")
