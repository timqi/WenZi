"""Debug script: verify pynput key event capture on macOS."""

from pynput import keyboard


def on_press(key):
    vk = getattr(key, "vk", None)
    char = getattr(key, "char", None)
    print(f"PRESS   key={key!r}  type={type(key).__name__}  vk={vk}  char={char}")


def on_release(key):
    vk = getattr(key, "vk", None)
    char = getattr(key, "char", None)
    print(f"RELEASE key={key!r}  type={type(key).__name__}  vk={vk}  char={char}")
    if key == keyboard.Key.esc:
        print("\nESC pressed, exiting.")
        return False


print("Listening for key events via pynput... Press ESC to quit.")
print("Try pressing: fn, f2, a, shift, cmd, etc.\n")

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
