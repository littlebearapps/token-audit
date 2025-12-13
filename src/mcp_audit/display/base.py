"""
DisplayAdapter - Abstract base class for display implementations.

The Display Adapter Pattern separates rendering from tracking logic,
enabling multiple display backends (Rich TUI, plain text, silent mode).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .snapshot import DisplaySnapshot


class DisplayAdapter(ABC):
    """Abstract base class for display implementations.

    Display adapters receive immutable snapshots and render them
    to the terminal. The tracking logic remains completely separate.

    Lifecycle:
        1. start() - Called once when tracking begins
        2. update() - Called periodically with new snapshots
        3. on_event() - Called for each tool call (for activity feed)
        4. stop() - Called once when tracking ends
    """

    @abstractmethod
    def start(self, snapshot: "DisplaySnapshot") -> None:
        """Initialize display with initial state.

        Args:
            snapshot: Initial snapshot with project/platform info
        """
        pass

    @abstractmethod
    def update(self, snapshot: "DisplaySnapshot") -> Optional[str]:
        """Update display with new snapshot.

        Args:
            snapshot: Updated snapshot with current metrics

        Returns:
            Optional action string if user interaction occurred:
            - "ai_export": User requested AI export
            - "quit": User requested quit
            - None: No action (default)

        Note:
            Implementations that don't support keyboard input should return None.
        """
        pass

    @abstractmethod
    def on_event(self, tool_name: str, tokens: int, timestamp: datetime) -> None:
        """Handle individual event for recent activity feed.

        Args:
            tool_name: Name of the MCP tool called
            tokens: Token count for this call
            timestamp: When the call occurred
        """
        pass

    @abstractmethod
    def stop(self, snapshot: "DisplaySnapshot") -> None:
        """Finalize display and show summary.

        Args:
            snapshot: Final snapshot with complete session metrics
        """
        pass

    def __enter__(self) -> "DisplayAdapter":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> Literal[False]:
        """Context manager exit - does not suppress exceptions."""
        return False
