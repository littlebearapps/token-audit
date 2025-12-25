"""
Keyboard input handler for non-blocking terminal input.

Provides cross-platform keyboard input for the session browser TUI.
Works on macOS/Linux using termios/tty. Windows fallback uses msvcrt.

v0.7.0 - task-105.1
"""

import sys
from typing import Any, Optional

# Store original terminal settings for restoration
_original_settings: Optional[Any] = None


def enable_raw_mode() -> bool:
    """Enable raw terminal mode for single-key input.

    Returns:
        True if raw mode was enabled, False otherwise.
    """
    global _original_settings

    if sys.platform == "win32":
        # Windows: msvcrt handles this automatically
        return True

    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        _original_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        return True
    except Exception:
        return False


def disable_raw_mode() -> None:
    """Restore terminal to normal mode."""
    global _original_settings

    if sys.platform == "win32":
        return

    if _original_settings is None:
        return

    try:
        import termios

        fd = sys.stdin.fileno()
        termios.tcsetattr(fd, termios.TCSADRAIN, _original_settings)
        _original_settings = None
    except Exception:
        pass


def check_keypress(timeout: float = 0.0) -> Optional[str]:
    """Non-blocking check for keyboard input.

    Args:
        timeout: Seconds to wait (0 = non-blocking)

    Returns:
        Key string if available, None otherwise.
        For special keys, returns escape sequences (e.g., '\\x1b[A' for up arrow).
    """
    if sys.platform == "win32":
        return _check_keypress_windows()
    else:
        return _check_keypress_unix(timeout)


def _check_keypress_windows() -> Optional[str]:
    """Windows-specific keyboard check using msvcrt."""
    try:
        import msvcrt

        if msvcrt.kbhit():  # type: ignore[attr-defined]
            ch = msvcrt.getch()  # type: ignore[attr-defined]
            # Handle extended keys (arrows, etc.)
            if ch in (b"\x00", b"\xe0"):
                ext = msvcrt.getch()  # type: ignore[attr-defined]
                # Convert Windows extended codes to ANSI escape sequences
                key_map: dict[bytes, str] = {
                    b"H": "\x1b[A",  # Up
                    b"P": "\x1b[B",  # Down
                    b"K": "\x1b[D",  # Left
                    b"M": "\x1b[C",  # Right
                }
                return key_map.get(ext)
            result: str = ch.decode("utf-8", errors="ignore")
            return result
    except Exception:
        pass
    return None


def _check_keypress_unix(timeout: float) -> Optional[str]:
    """Unix-specific keyboard check using select."""
    import select

    try:
        readable, _, _ = select.select([sys.stdin], [], [], timeout)
        if sys.stdin in readable:
            ch = sys.stdin.read(1)
            # Check for escape sequence (arrow keys, etc.)
            if ch == "\x1b":
                # Read additional chars for escape sequence with longer timeout
                # to avoid race conditions where arrow key bytes arrive separately
                readable2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if sys.stdin in readable2:
                    # Read escape sequence chars one at a time
                    next_ch = sys.stdin.read(1)
                    ch += next_ch
                    # If we got '[', expect one more char (A/B/C/D for arrows)
                    if next_ch == "[":
                        readable3, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if sys.stdin in readable3:
                            ch += sys.stdin.read(1)
            return ch
    except Exception:
        pass
    return None


def read_key(timeout: float = 0.1) -> Optional[str]:
    """Read a single key with optional timeout.

    Convenience function that handles both regular keys and special keys.

    Args:
        timeout: Seconds to wait for input.

    Returns:
        Key string, or None if no input.
    """
    return check_keypress(timeout)


# Key constants for easier matching
KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"
KEY_RIGHT = "\x1b[C"
KEY_LEFT = "\x1b[D"
KEY_ENTER = "\r"
KEY_ESC = "\x1b"
KEY_BACKSPACE = "\x7f"
KEY_TAB = "\t"
KEY_SHIFT_TAB = "\x1b[Z"  # Standard terminal escape for Shift+Tab
