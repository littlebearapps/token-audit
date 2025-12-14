"""ASCII mode utilities for mcp-audit TUI.

Provides ASCII alternatives for Unicode characters when running
in environments that don't support Unicode properly.
"""

import os
from typing import Dict, List, Tuple

from rich import box


def is_ascii_mode() -> bool:
    """Check if ASCII mode is enabled.

    Returns True if MCP_AUDIT_ASCII environment variable is set to a truthy value.
    """
    ascii_env = os.environ.get("MCP_AUDIT_ASCII", "").lower()
    return ascii_env in ("1", "true", "yes", "on")


def get_box_style() -> box.Box:
    """Get the appropriate box style based on ASCII mode.

    Returns:
        box.ASCII if ASCII mode enabled, otherwise box.ROUNDED
    """
    if is_ascii_mode():
        return box.ASCII
    return box.ROUNDED


# Emoji to ASCII text mapping
EMOJI_TO_ASCII: Dict[str, str] = {
    "📌": "[pin]",
    "💰": "[+$]",
    "💸": "[-$]",
    "🌿": "branch:",
    "📁": "files:",
    "↺": "(sync)",
    # Accuracy indicators (v0.7.0 - task-105.5)
    "✓": "[OK]",
    "~": "[~]",
    "?": "[?]",
    # Notification icons (v0.8.0 - task-106.9)
    "⚠": "[WARN]",
    "✗": "[ERR]",
    "ℹ": "[INFO]",
}

# Histogram block characters for token distribution (v0.7.0 - task-105.7)
HISTOGRAM_BLOCKS = " ▁▂▃▄▅▆▇█"
HISTOGRAM_ASCII = " _.-=+*#@"


def ascii_emoji(emoji: str) -> str:
    """Convert emoji to ASCII equivalent if in ASCII mode.

    Args:
        emoji: The emoji character to potentially convert

    Returns:
        ASCII equivalent if in ASCII mode, otherwise the original emoji
    """
    if is_ascii_mode():
        return EMOJI_TO_ASCII.get(emoji, emoji)
    return emoji


def format_with_emoji(emoji: str, text: str) -> str:
    """Format text with emoji prefix, respecting ASCII mode.

    Args:
        emoji: The emoji to prepend
        text: The text content

    Returns:
        Formatted string with emoji or ASCII equivalent
    """
    prefix = ascii_emoji(emoji)
    if prefix.startswith("["):
        # ASCII mode - add space after bracket notation
        return f"{prefix} {text}"
    elif prefix.endswith(":"):
        # ASCII mode - colon prefix like "branch:"
        return f"{prefix} {text}"
    else:
        # Unicode mode - emoji with space
        return f"{prefix} {text}"


def accuracy_indicator(accuracy_level: str) -> Tuple[str, str]:
    """Get accuracy icon and color style for given accuracy level.

    Args:
        accuracy_level: One of "exact", "estimated", or "calls-only"

    Returns:
        Tuple of (icon, color_style) for use with Rich styling.
        Icon will be ASCII equivalent if ASCII mode is enabled.

    v0.7.0 - task-105.5
    """
    indicators = {
        "exact": ("✓", "green"),
        "estimated": ("~", "yellow"),
        "calls-only": ("?", "dim"),
    }
    icon, color = indicators.get(accuracy_level, ("?", "dim"))
    return (ascii_emoji(icon), color)


def compute_percentile(values: List[int], percentile: float) -> int:
    """Compute percentile from a list of values.

    Args:
        values: List of numeric values
        percentile: Percentile to compute (0-100)

    Returns:
        Value at the given percentile, or 0 if list is empty

    v0.7.0 - task-105.7
    """
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * percentile / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def generate_histogram(values: List[int], buckets: int = 8) -> str:
    """Generate Unicode block histogram from token values.

    Args:
        values: List of token counts (one per call)
        buckets: Number of histogram buckets (default 8)

    Returns:
        String of histogram block characters representing distribution.
        Uses ASCII fallback if ASCII mode is enabled.

    v0.7.0 - task-105.7
    """
    if not values:
        return " " * buckets

    min_val, max_val = min(values), max(values)
    if min_val == max_val:
        # All values same - show mid-height bars
        blocks = HISTOGRAM_ASCII if is_ascii_mode() else HISTOGRAM_BLOCKS
        return blocks[4] * buckets

    # Count values per bucket
    bucket_counts = [0] * buckets
    bucket_size = (max_val - min_val) / buckets
    for v in values:
        bucket_idx = min(int((v - min_val) / bucket_size), buckets - 1)
        bucket_counts[bucket_idx] += 1

    # Normalize to block heights (0-8)
    max_count = max(bucket_counts) or 1
    blocks = HISTOGRAM_ASCII if is_ascii_mode() else HISTOGRAM_BLOCKS
    result = ""
    for count in bucket_counts:
        height = int(count / max_count * 8)
        result += blocks[height]

    return result
