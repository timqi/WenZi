"""Debug script: print all key events received by pynput."""

from pynput import keyboard


def on_press(key):
    try:
        vk = getattr(key, "vk", None)
        print(f"PRESS   key={key!r}  type={type(key).__name__}  vk={vk}")
    except Exception as e:
        print(f"PRESS   error: {e}")


def on_release(key):
    try:
        vk = getattr(key, "vk", None)
        print(f"RELEASE key={key!r}  type={type(key).__name__}  vk={vk}")
    except Exception as e:
        print(f"RELEASE error: {e}")
    if key == keyboard.Key.esc:
        print("ESC pressed, exiting")
        return False


print("Listening for key events... Press ESC to quit.")
print("Try pressing fn, f2, and other keys to see what events are captured.\n")

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
