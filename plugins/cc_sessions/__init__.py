"""Claude Code Sessions — WenZi official example plugin.

Browse and view Claude Code session history through the launcher.

Installation:
    cp -r plugins/cc_sessions/ ~/.config/WenZi/scripts/cc_sessions/

Usage in ~/.config/WenZi/scripts/init.py:
    import cc_sessions
"""

try:
    from wenzi.scripting.api import wz

    if wz is not None:
        from .init_plugin import register

        register(wz)
except ImportError:
    pass  # Not running inside WenZi
