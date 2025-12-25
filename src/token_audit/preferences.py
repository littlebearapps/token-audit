"""User preferences for token-audit TUI.

Manages persistent user settings like pinned sessions, sort preferences,
and theme overrides. Stored in ~/.token-audit/preferences.json.

v0.7.0 - task-105.3, task-105.4
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PREFERENCES_SCHEMA_VERSION = "1.0.0"
MAX_PINNED_SESSIONS = 50


def get_preferences_path() -> Path:
    """Get path to preferences file."""
    return Path.home() / ".token-audit" / "preferences.json"


@dataclass
class SortPreference:
    """Sort preference state."""

    key: str = "date"
    reverse: bool = True  # newest/highest first


@dataclass
class Preferences:
    """User preferences data."""

    schema_version: str = PREFERENCES_SCHEMA_VERSION
    pinned_sessions: List[str] = field(default_factory=list)
    last_sort: SortPreference = field(default_factory=SortPreference)
    last_filter_platform: Optional[str] = None
    theme_preference: str = "auto"
    pins_sort_to_top: bool = True  # Whether pinned sessions appear at top of list
    tui_launch_count: int = 0  # v1.0.0 - Track TUI launches for onboarding hints


class PreferencesManager:
    """Manages user preferences with file persistence.

    Thread-safe load/save using file locking on Unix systems.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        """Initialize preferences manager.

        Args:
            path: Override path for preferences file (for testing)
        """
        self.path = path or get_preferences_path()
        self._prefs: Optional[Preferences] = None

    def load(self) -> Preferences:
        """Load preferences from disk.

        Returns:
            Preferences object with loaded or default values.
        """
        if not self.path.exists():
            self._prefs = Preferences()
            return self._prefs

        try:
            with open(self.path) as f:
                data = json.load(f)

            # Parse with validation
            sort_data = data.get("last_sort", {})
            self._prefs = Preferences(
                schema_version=data.get("schema_version", PREFERENCES_SCHEMA_VERSION),
                pinned_sessions=data.get("pinned_sessions", [])[:MAX_PINNED_SESSIONS],
                last_sort=SortPreference(
                    key=sort_data.get("key", "date"),
                    reverse=sort_data.get("reverse", True),
                ),
                last_filter_platform=data.get("last_filter_platform"),
                theme_preference=data.get("theme_preference", "auto"),
                pins_sort_to_top=data.get("pins_sort_to_top", True),
                tui_launch_count=data.get("tui_launch_count", 0),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted file - use defaults
            self._prefs = Preferences()

        return self._prefs

    def save(self) -> None:
        """Save preferences to disk with file locking."""
        if self._prefs is None:
            return

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "schema_version": self._prefs.schema_version,
            "pinned_sessions": self._prefs.pinned_sessions[:MAX_PINNED_SESSIONS],
            "last_sort": {
                "key": self._prefs.last_sort.key,
                "reverse": self._prefs.last_sort.reverse,
            },
            "last_filter_platform": self._prefs.last_filter_platform,
            "theme_preference": self._prefs.theme_preference,
            "pins_sort_to_top": self._prefs.pins_sort_to_top,
            "tui_launch_count": self._prefs.tui_launch_count,
        }

        # Write with file locking on Unix
        with open(self.path, "w") as f:
            if sys.platform != "win32":
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            else:
                # Windows: no fcntl, just write
                json.dump(data, f, indent=2)

    @property
    def prefs(self) -> Preferences:
        """Get preferences, loading if needed."""
        if self._prefs is None:
            self.load()
        return self._prefs  # type: ignore[return-value]

    def pin_session(self, session_id: str) -> bool:
        """Pin a session.

        Args:
            session_id: Session identifier (typically file stem)

        Returns:
            True if pinned successfully, False if already at limit.
        """
        if session_id in self.prefs.pinned_sessions:
            return True  # Already pinned

        if len(self.prefs.pinned_sessions) >= MAX_PINNED_SESSIONS:
            return False  # At limit

        self.prefs.pinned_sessions.insert(0, session_id)
        self.save()
        return True

    def unpin_session(self, session_id: str) -> None:
        """Unpin a session.

        Args:
            session_id: Session identifier to unpin
        """
        if session_id in self.prefs.pinned_sessions:
            self.prefs.pinned_sessions.remove(session_id)
            self.save()

    def is_pinned(self, session_id: str) -> bool:
        """Check if a session is pinned.

        Args:
            session_id: Session identifier to check

        Returns:
            True if session is pinned.
        """
        return session_id in self.prefs.pinned_sessions

    def toggle_pin(self, session_id: str) -> bool:
        """Toggle pin state for a session.

        Args:
            session_id: Session identifier

        Returns:
            New pin state (True if now pinned, False if unpinned).
        """
        if self.is_pinned(session_id):
            self.unpin_session(session_id)
            return False
        else:
            return self.pin_session(session_id)

    def set_sort(self, key: str, reverse: bool) -> None:
        """Set sort preference.

        Args:
            key: Sort key (date, cost, tokens, duration, platform)
            reverse: True for descending order
        """
        self.prefs.last_sort.key = key
        self.prefs.last_sort.reverse = reverse
        self.save()

    def set_filter_platform(self, platform: Optional[str]) -> None:
        """Set platform filter preference.

        Args:
            platform: Platform name or None for all
        """
        self.prefs.last_filter_platform = platform
        self.save()

    def set_theme(self, theme: str) -> None:
        """Set theme preference.

        Args:
            theme: Theme name (auto, dark, light, high-contrast-dark, high-contrast-light)
        """
        self.prefs.theme_preference = theme
        self.save()

    def clear_all_pins(self) -> int:
        """Clear all pinned sessions.

        Returns:
            Number of pins that were cleared.
        """
        count = len(self.prefs.pinned_sessions)
        if count > 0:
            self.prefs.pinned_sessions.clear()
            self.save()
        return count

    def toggle_pins_sort_to_top(self) -> bool:
        """Toggle whether pinned sessions sort to top.

        Returns:
            New state (True if pins now sort to top, False otherwise).
        """
        self.prefs.pins_sort_to_top = not self.prefs.pins_sort_to_top
        self.save()
        return self.prefs.pins_sort_to_top

    def increment_launch_count(self) -> int:
        """Increment TUI launch count for onboarding tracking.

        Returns:
            New launch count after incrementing.
        """
        self.prefs.tui_launch_count += 1
        self.save()
        return self.prefs.tui_launch_count

    def is_new_user(self) -> bool:
        """Check if user is still in onboarding phase.

        Returns:
            True if launch count is 3 or less (show help hints).
        """
        return self.prefs.tui_launch_count <= 3
