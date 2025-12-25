"""
Display module for Token Audit.

Provides display adapters for different output modes:
- RichDisplay: Beautiful TUI with in-place updating (default)
- PlainDisplay: Simple print-based output for CI/logs
- NullDisplay: Silent mode for scripting

Use create_display() factory function for automatic mode selection.
"""

import sys
from typing import Any, List, Literal, Optional

from .base import DisplayAdapter
from .null_display import NullDisplay
from .plain_display import PlainDisplay
from .snapshot import DisplaySnapshot

DisplayMode = Literal["auto", "tui", "plain", "quiet"]


def create_display(
    mode: DisplayMode = "auto",
    refresh_rate: float = 0.5,
    pinned_servers: Optional[List[str]] = None,
    theme: Optional[str] = None,
) -> DisplayAdapter:
    """Factory function to create appropriate display adapter.

    Args:
        mode: Display mode
            - "auto": Use TUI if TTY, else plain (default)
            - "tui": Force TUI mode (errors if not TTY)
            - "plain": Force plain text output
            - "quiet": Silent mode (no output)
        refresh_rate: TUI refresh rate in seconds (default 0.5)
        pinned_servers: List of server names to pin at top of MCP section
        theme: Theme name override for TUI (e.g., "dark", "light", "hc-dark")
               If None, auto-detects from TOKEN_AUDIT_THEME env var or system.

    Returns:
        DisplayAdapter instance

    Raises:
        ImportError: If TUI mode requested but Rich not installed
        ValueError: If unknown mode specified
    """
    if mode == "quiet":
        return NullDisplay()

    if mode == "plain":
        return PlainDisplay()

    if mode in ("tui", "auto"):
        # Check if stdout is a TTY
        if not sys.stdout.isatty():
            if mode == "tui":
                print(
                    "Warning: --tui requested but stdout is not a TTY. "
                    "Falling back to plain mode.",
                    file=sys.stderr,
                )
            return PlainDisplay()

        # Try to import Rich
        try:
            from .rich_display import RichDisplay

            return RichDisplay(
                refresh_rate=refresh_rate,
                pinned_servers=pinned_servers,
                theme=theme,
            )
        except ImportError:
            if mode == "tui":
                raise ImportError(
                    "Rich TUI mode requires the 'rich' package. "
                    "Install with: pip install token-audit or pip install rich"
                ) from None
            return PlainDisplay()

    raise ValueError(f"Unknown display mode: {mode}")


__all__ = [
    # Core classes
    "DisplayAdapter",
    "DisplaySnapshot",
    # Implementations
    "PlainDisplay",
    "NullDisplay",
    # Factory (lazy import for RichDisplay)
    "create_display",
    # Type
    "DisplayMode",
    # Session browser (v0.7.0 - task-105.1, lazy import)
    "SessionBrowser",
]


def __getattr__(name: str) -> Any:
    """Lazy import for optional dependencies."""
    if name == "SessionBrowser":
        from .session_browser import SessionBrowser

        return SessionBrowser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
