"""
PlainDisplay - Simple print-based display for CI/logging environments.

This adapter outputs plain text that works in any terminal, including
non-TTY environments like CI pipelines or log files.
"""

import time
from datetime import datetime
from typing import Optional

from ..base_tracker import SCHEMA_VERSION
from .base import DisplayAdapter
from .snapshot import DisplaySnapshot


class PlainDisplay(DisplayAdapter):
    """Simple print-based display for CI/logging.

    Rate-limits update output to avoid log spam while still
    providing periodic progress information.
    """

    def __init__(self, print_interval: float = 5.0) -> None:
        """Initialize plain display.

        Args:
            print_interval: Minimum seconds between progress updates
        """
        self._last_print_time: float = 0
        self._print_interval = print_interval

    def start(self, snapshot: DisplaySnapshot) -> None:
        """Print header and initial state."""
        print("=" * 70)
        print(f"Token Audit - {snapshot.platform}")
        print(f"Project: {snapshot.project}")
        print("=" * 70)
        print("Tracking started. Press Ctrl+C to stop.")
        print()

    def update(self, snapshot: DisplaySnapshot) -> Optional[str]:
        """Print progress update (rate-limited). Returns None (no keyboard input)."""
        now = time.time()
        if now - self._last_print_time >= self._print_interval:
            self._last_print_time = now
            print(
                f"[{snapshot.duration_seconds:.0f}s] "
                f"Tokens: {snapshot.total_tokens:,} | "
                f"MCP calls: {snapshot.total_tool_calls} | "
                f"Cost (USD): ${snapshot.cost_estimate:.4f}"
            )
        return None

    def on_event(self, tool_name: str, tokens: int, timestamp: datetime) -> None:
        """Print each tool call."""
        time_str = timestamp.strftime("%H:%M:%S")
        print(f"  [{time_str}] {tool_name} ({tokens:,} tokens)")

    def stop(self, snapshot: DisplaySnapshot) -> None:
        """Print final summary with enhanced cost display."""
        print()
        print("=" * 70)
        print("Session Complete")
        print("=" * 70)

        # Model info (AC #6)
        if snapshot.model_name and snapshot.model_name != "Unknown Model":
            print(f"Model: {snapshot.model_name}")

        print(f"Total tokens: {snapshot.total_tokens:,}")
        print(f"MCP tool calls: {snapshot.total_tool_calls}")
        print(f"Cache efficiency: {snapshot.cache_efficiency:.0%}")

        # Enhanced cost display (AC #1, #3, #4, task-47.1)
        print(f"Cost w/ Cache (USD): ${snapshot.cost_estimate:.4f}")

        if snapshot.cost_no_cache > 0:
            print(f"Cost w/o Cache (USD): ${snapshot.cost_no_cache:.4f}")
            if snapshot.cache_savings > 0:
                print(
                    f"Cache savings: ${snapshot.cache_savings:.4f} ({snapshot.savings_percent:.1f}% saved)"
                )
            elif snapshot.cache_savings < 0:
                print(f"Net cost from caching: ${abs(snapshot.cache_savings):.4f}")
            else:
                print("Cache savings: $0.0000 (break even)")

        print(f"Schema version: {SCHEMA_VERSION}")

        # Session save location
        if snapshot.session_dir:
            print(f"\nSession saved to: {snapshot.session_dir}")
