"""Theme detection utilities for token-audit TUI.

Attempts to detect terminal background color to select appropriate theme.
Supports explicit override via environment variable, COLORFGBG detection,
and macOS system dark mode detection.
"""

import os
import subprocess
from typing import Literal, Optional

from .themes import DEFAULT_DARK, DEFAULT_LIGHT, _ThemeType, get_theme

TerminalMode = Literal["dark", "light", "unknown"]


def detect_terminal_mode() -> TerminalMode:
    """Detect whether terminal is in dark or light mode.

    Detection methods (in order of preference):
    1. TOKEN_AUDIT_THEME environment variable (explicit override)
    2. COLORFGBG environment variable (set by some terminals)
    3. macOS AppleInterfaceStyle (system dark mode)
    4. Default to "unknown"

    Returns:
        "dark", "light", or "unknown"
    """
    # 1. Check explicit override
    env_theme = os.environ.get("TOKEN_AUDIT_THEME", "").lower()
    if env_theme in ("dark", "mocha", "catppuccin-mocha", "hc-dark", "high-contrast-dark"):
        return "dark"
    if env_theme in ("light", "latte", "catppuccin-latte", "hc-light", "high-contrast-light"):
        return "light"

    # 2. Check COLORFGBG (format: "fg;bg" where colors are 0-15)
    # Light backgrounds typically have bg >= 7
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        try:
            parts = colorfgbg.split(";")
            if len(parts) >= 2:
                bg = int(parts[-1])
                # ANSI colors 7, 15 are white/light gray (light backgrounds)
                if bg in (7, 15):
                    return "light"
                # ANSI colors 0, 8 are black/dark gray (dark backgrounds)
                if bg in (0, 8):
                    return "dark"
        except (ValueError, IndexError):
            pass

    # 3. Check macOS system dark mode
    if _is_macos():
        macos_mode = _detect_macos_mode()
        if macos_mode:
            return macos_mode

    # 4. Default to unknown
    return "unknown"


def _is_macos() -> bool:
    """Check if running on macOS."""
    import platform

    return platform.system() == "Darwin"


def _detect_macos_mode() -> Optional[TerminalMode]:
    """Detect macOS dark/light mode via AppleInterfaceStyle.

    Returns:
        "dark" or "light" if detected, None otherwise
    """
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        if result.returncode == 0 and "Dark" in result.stdout:
            return "dark"
        # No error but no "Dark" means light mode (default)
        return "light"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def get_active_theme(
    override: Optional[str] = None,
    config_theme: Optional[str] = None,
) -> _ThemeType:
    """Get the active theme based on detection and configuration.

    Priority order:
    1. Explicit override parameter (from CLI --theme flag)
    2. TOKEN_AUDIT_THEME environment variable
    3. Config file theme setting
    4. Auto-detected terminal mode
    5. Default to dark theme

    Args:
        override: Explicit theme name from CLI flag
        config_theme: Theme name from config file

    Returns:
        ThemeColors implementation
    """
    # 1. CLI override takes precedence
    if override:
        if override.lower() == "auto":
            pass  # Fall through to auto-detection
        else:
            return get_theme(override)

    # 2. Environment variable
    env_theme = os.environ.get("TOKEN_AUDIT_THEME", "").lower()
    if env_theme and env_theme != "auto":
        return get_theme(env_theme)

    # 3. Config file
    if config_theme and config_theme.lower() != "auto":
        return get_theme(config_theme)

    # 4. Auto-detect
    mode = detect_terminal_mode()
    if mode == "light":
        return get_theme(DEFAULT_LIGHT)
    elif mode == "dark":
        return get_theme(DEFAULT_DARK)

    # 5. Default to dark (most common for developers)
    return get_theme(DEFAULT_DARK)


def is_ascii_mode() -> bool:
    """Check if ASCII mode is enabled.

    Returns True if TOKEN_AUDIT_ASCII environment variable is set to a truthy value.
    """
    ascii_env = os.environ.get("TOKEN_AUDIT_ASCII", "").lower()
    return ascii_env in ("1", "true", "yes", "on")
