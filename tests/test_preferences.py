"""Tests for token_audit.preferences module.

v0.7.0 - task-105.3, task-105.4
"""

import json
from pathlib import Path

import pytest

from token_audit.preferences import (
    MAX_PINNED_SESSIONS,
    PREFERENCES_SCHEMA_VERSION,
    Preferences,
    PreferencesManager,
    SortPreference,
)


class TestPreferencesManager:
    """Tests for PreferencesManager class."""

    def test_load_creates_defaults_when_missing(self, tmp_path: Path) -> None:
        """Test that loading from non-existent file creates defaults."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)

        prefs = manager.load()

        assert prefs.schema_version == PREFERENCES_SCHEMA_VERSION
        assert prefs.pinned_sessions == []
        assert prefs.last_sort.key == "date"
        assert prefs.last_sort.reverse is True
        assert prefs.last_filter_platform is None
        assert prefs.theme_preference == "auto"

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test that preferences survive save/load cycle."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)

        # Modify preferences
        manager.load()
        manager.prefs.pinned_sessions = ["session-1", "session-2"]
        manager.prefs.last_sort = SortPreference(key="cost", reverse=False)
        manager.prefs.last_filter_platform = "claude-code"
        manager.prefs.theme_preference = "dark"
        manager.save()

        # Load in new manager instance
        manager2 = PreferencesManager(path=prefs_path)
        prefs2 = manager2.load()

        assert prefs2.pinned_sessions == ["session-1", "session-2"]
        assert prefs2.last_sort.key == "cost"
        assert prefs2.last_sort.reverse is False
        assert prefs2.last_filter_platform == "claude-code"
        assert prefs2.theme_preference == "dark"

    def test_pin_session_adds_to_list(self, tmp_path: Path) -> None:
        """Test that pinning a session adds it to the list."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        result = manager.pin_session("new-session")

        assert result is True
        assert "new-session" in manager.prefs.pinned_sessions
        assert manager.prefs.pinned_sessions[0] == "new-session"  # Added at front

    def test_pin_session_already_pinned(self, tmp_path: Path) -> None:
        """Test that pinning already-pinned session returns True."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()
        manager.pin_session("existing-session")

        result = manager.pin_session("existing-session")

        assert result is True
        # Should not duplicate
        assert manager.prefs.pinned_sessions.count("existing-session") == 1

    def test_unpin_session_removes_from_list(self, tmp_path: Path) -> None:
        """Test that unpinning a session removes it from the list."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()
        manager.pin_session("session-to-remove")

        manager.unpin_session("session-to-remove")

        assert "session-to-remove" not in manager.prefs.pinned_sessions

    def test_unpin_nonexistent_session(self, tmp_path: Path) -> None:
        """Test that unpinning non-existent session doesn't error."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        # Should not raise
        manager.unpin_session("nonexistent")

    def test_toggle_pin_returns_new_state(self, tmp_path: Path) -> None:
        """Test that toggle_pin returns the new pin state."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        # Pin
        result1 = manager.toggle_pin("toggle-session")
        assert result1 is True
        assert manager.is_pinned("toggle-session")

        # Unpin
        result2 = manager.toggle_pin("toggle-session")
        assert result2 is False
        assert not manager.is_pinned("toggle-session")

    def test_max_pins_enforced(self, tmp_path: Path) -> None:
        """Test that maximum pin limit is enforced."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        # Pin up to limit
        for i in range(MAX_PINNED_SESSIONS):
            result = manager.pin_session(f"session-{i}")
            assert result is True

        # Try to pin one more
        result = manager.pin_session("one-too-many")
        assert result is False
        assert "one-too-many" not in manager.prefs.pinned_sessions

    def test_is_pinned_returns_correct_state(self, tmp_path: Path) -> None:
        """Test that is_pinned returns correct state."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        assert manager.is_pinned("not-pinned") is False

        manager.pin_session("is-pinned")
        assert manager.is_pinned("is-pinned") is True

    def test_load_handles_corrupted_json(self, tmp_path: Path) -> None:
        """Test that loading corrupted JSON falls back to defaults."""
        prefs_path = tmp_path / "preferences.json"
        prefs_path.write_text("{ invalid json }")

        manager = PreferencesManager(path=prefs_path)
        prefs = manager.load()

        # Should have defaults
        assert prefs.pinned_sessions == []
        assert prefs.last_sort.key == "date"

    def test_load_handles_missing_fields(self, tmp_path: Path) -> None:
        """Test that loading JSON with missing fields uses defaults."""
        prefs_path = tmp_path / "preferences.json"
        prefs_path.write_text('{"schema_version": "1.0.0"}')

        manager = PreferencesManager(path=prefs_path)
        prefs = manager.load()

        assert prefs.pinned_sessions == []
        assert prefs.last_sort.key == "date"
        assert prefs.theme_preference == "auto"

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that save creates parent directories if needed."""
        prefs_path = tmp_path / "subdir" / "nested" / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()
        manager.pin_session("test-session")

        manager.save()

        assert prefs_path.exists()
        data = json.loads(prefs_path.read_text())
        assert "test-session" in data["pinned_sessions"]

    def test_set_sort(self, tmp_path: Path) -> None:
        """Test that set_sort updates and saves preferences."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        manager.set_sort("cost", False)

        assert manager.prefs.last_sort.key == "cost"
        assert manager.prefs.last_sort.reverse is False

        # Verify saved
        manager2 = PreferencesManager(path=prefs_path)
        prefs2 = manager2.load()
        assert prefs2.last_sort.key == "cost"
        assert prefs2.last_sort.reverse is False

    def test_set_filter_platform(self, tmp_path: Path) -> None:
        """Test that set_filter_platform updates and saves preferences."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        manager.set_filter_platform("gemini-cli")

        assert manager.prefs.last_filter_platform == "gemini-cli"

        # Verify saved
        manager2 = PreferencesManager(path=prefs_path)
        prefs2 = manager2.load()
        assert prefs2.last_filter_platform == "gemini-cli"

    def test_set_theme(self, tmp_path: Path) -> None:
        """Test that set_theme updates and saves preferences."""
        prefs_path = tmp_path / "preferences.json"
        manager = PreferencesManager(path=prefs_path)
        manager.load()

        manager.set_theme("high-contrast-dark")

        assert manager.prefs.theme_preference == "high-contrast-dark"

        # Verify saved
        manager2 = PreferencesManager(path=prefs_path)
        prefs2 = manager2.load()
        assert prefs2.theme_preference == "high-contrast-dark"


class TestSortPreference:
    """Tests for SortPreference dataclass."""

    def test_default_values(self) -> None:
        """Test default SortPreference values."""
        pref = SortPreference()
        assert pref.key == "date"
        assert pref.reverse is True

    def test_custom_values(self) -> None:
        """Test SortPreference with custom values."""
        pref = SortPreference(key="tokens", reverse=False)
        assert pref.key == "tokens"
        assert pref.reverse is False


class TestPreferences:
    """Tests for Preferences dataclass."""

    def test_default_values(self) -> None:
        """Test default Preferences values."""
        prefs = Preferences()
        assert prefs.schema_version == PREFERENCES_SCHEMA_VERSION
        assert prefs.pinned_sessions == []
        assert prefs.last_sort.key == "date"
        assert prefs.last_filter_platform is None
        assert prefs.theme_preference == "auto"
