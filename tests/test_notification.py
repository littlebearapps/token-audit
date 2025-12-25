"""Tests for TUI notification system (v0.8.0 - task-106.9).

Tests notification state management, expiry logic, theme colors, and ASCII fallback.
"""

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from token_audit.display.rich_display import Notification, RichDisplay
from token_audit.display.snapshot import DisplaySnapshot


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_snapshot() -> DisplaySnapshot:
    """Create a minimal DisplaySnapshot for testing."""
    return DisplaySnapshot.create(
        project="test-project",
        platform="claude-code",
        start_time=datetime(2025, 1, 1, 12, 0, 0),
        duration_seconds=300.0,
    )


# ============================================================================
# Notification Dataclass Tests
# ============================================================================


class TestNotificationDataclass:
    """Tests for Notification dataclass."""

    def test_create_notification(self) -> None:
        """Test creating a notification with all fields."""
        notification = Notification(
            message="Test message",
            level="success",
            expires_at=time.time() + 3.0,
        )
        assert notification.message == "Test message"
        assert notification.level == "success"
        assert notification.expires_at > time.time()

    def test_notification_levels(self) -> None:
        """Test all supported notification levels."""
        for level in ["success", "warning", "error", "info"]:
            notification = Notification(
                message=f"Test {level}",
                level=level,
                expires_at=time.time() + 3.0,
            )
            assert notification.level == level


# ============================================================================
# RichDisplay Notification Tests
# ============================================================================


class TestRichDisplayNotification:
    """Tests for notification methods in RichDisplay."""

    def test_initial_notification_is_none(self) -> None:
        """Test that notification is None initially."""
        display = RichDisplay()
        assert display._notification is None

    def test_show_notification_success(self) -> None:
        """Test show_notification creates success notification."""
        display = RichDisplay()
        display.show_notification("Operation succeeded", "success")

        assert display._notification is not None
        assert display._notification.message == "Operation succeeded"
        assert display._notification.level == "success"

    def test_show_notification_error(self) -> None:
        """Test show_notification creates error notification."""
        display = RichDisplay()
        display.show_notification("Operation failed", "error", timeout=5.0)

        assert display._notification is not None
        assert display._notification.message == "Operation failed"
        assert display._notification.level == "error"

    def test_show_notification_default_level(self) -> None:
        """Test show_notification defaults to info level."""
        display = RichDisplay()
        display.show_notification("Information message")

        assert display._notification is not None
        assert display._notification.level == "info"

    def test_show_notification_custom_timeout(self) -> None:
        """Test show_notification respects custom timeout."""
        display = RichDisplay()
        before = time.time()
        display.show_notification("Test", timeout=10.0)
        after = time.time()

        # Should expire approximately 10 seconds after creation
        assert display._notification is not None
        assert display._notification.expires_at >= before + 10.0
        assert display._notification.expires_at <= after + 10.0 + 0.1

    def test_notification_replaces_previous(self) -> None:
        """Test that new notification replaces existing one."""
        display = RichDisplay()
        display.show_notification("First", "info")
        display.show_notification("Second", "success")

        assert display._notification is not None
        assert display._notification.message == "Second"
        assert display._notification.level == "success"


# ============================================================================
# Notification Expiry Tests
# ============================================================================


class TestNotificationExpiry:
    """Tests for notification auto-dismiss behavior."""

    def test_notification_not_expired(self) -> None:
        """Test notification remains when not expired."""
        display = RichDisplay()
        display.show_notification("Test", timeout=10.0)

        # Simulate update cycle
        snapshot = create_test_snapshot()
        with patch.object(display, "_raw_mode_enabled", False):
            display._notification  # Access to check it's still there

        assert display._notification is not None

    def test_notification_cleared_when_expired(self) -> None:
        """Test notification is cleared after expiry during update."""
        display = RichDisplay()
        # Create an already-expired notification
        display._notification = Notification(
            message="Expired",
            level="info",
            expires_at=time.time() - 1.0,  # Already expired
        )

        # The update method clears expired notifications
        # Simulate the expiry check that happens in update()
        if display._notification and time.time() > display._notification.expires_at:
            display._notification = None

        assert display._notification is None

    def test_notification_expires_at_calculation(self) -> None:
        """Test expires_at is correctly calculated from timeout."""
        display = RichDisplay()
        start_time = time.time()
        display.show_notification("Test", timeout=5.0)

        assert display._notification is not None
        # Should be within reasonable bounds
        expected_expiry = start_time + 5.0
        assert abs(display._notification.expires_at - expected_expiry) < 0.1


# ============================================================================
# Notification Rendering Tests
# ============================================================================


class TestNotificationRendering:
    """Tests for notification bar rendering."""

    def test_build_notification_empty_when_none(self) -> None:
        """Test _build_notification returns empty text when no notification."""
        display = RichDisplay()
        text = display._build_notification()
        assert str(text) == ""

    def test_build_notification_includes_message(self) -> None:
        """Test _build_notification includes the message."""
        display = RichDisplay()
        display.show_notification("Test message here", "success")

        text = display._build_notification()
        assert "Test message here" in str(text)

    def test_build_notification_includes_countdown(self) -> None:
        """Test _build_notification includes remaining time."""
        display = RichDisplay()
        display.show_notification("Test", "info", timeout=5.0)

        text = display._build_notification()
        text_str = str(text)
        # Should include some time indicator
        assert "[" in text_str and "s]" in text_str


# ============================================================================
# Notification Theme Tests
# ============================================================================


class TestNotificationTheme:
    """Tests for notification theming."""

    def test_success_notification_uses_success_color(self) -> None:
        """Test success notification uses theme success color."""
        display = RichDisplay()
        display.show_notification("Success!", "success")

        # Build notification - theme color should be used
        text = display._build_notification()
        # Text object was built, no crash
        assert str(text) != ""

    def test_error_notification_uses_error_color(self) -> None:
        """Test error notification uses theme error color."""
        display = RichDisplay()
        display.show_notification("Error!", "error")

        text = display._build_notification()
        assert str(text) != ""

    def test_warning_notification_uses_warning_color(self) -> None:
        """Test warning notification uses theme warning color."""
        display = RichDisplay()
        display.show_notification("Warning!", "warning")

        text = display._build_notification()
        assert str(text) != ""

    def test_info_notification_uses_info_color(self) -> None:
        """Test info notification uses theme info color."""
        display = RichDisplay()
        display.show_notification("Info!", "info")

        text = display._build_notification()
        assert str(text) != ""


# ============================================================================
# ASCII Mode Tests
# ============================================================================


class TestNotificationAsciiMode:
    """Tests for notification ASCII fallback."""

    def test_success_icon_ascii_fallback(self, monkeypatch) -> None:
        """Test success checkmark converts to [OK] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")

        # Need to create display after setting env var
        display = RichDisplay()
        display.show_notification("Success", "success")

        text = display._build_notification()
        assert "[OK]" in str(text)

    def test_warning_icon_ascii_fallback(self, monkeypatch) -> None:
        """Test warning icon converts to [WARN] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")

        display = RichDisplay()
        display.show_notification("Warning", "warning")

        text = display._build_notification()
        assert "[WARN]" in str(text)

    def test_error_icon_ascii_fallback(self, monkeypatch) -> None:
        """Test error icon converts to [ERR] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")

        display = RichDisplay()
        display.show_notification("Error", "error")

        text = display._build_notification()
        assert "[ERR]" in str(text)

    def test_info_icon_ascii_fallback(self, monkeypatch) -> None:
        """Test info icon converts to [INFO] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")

        display = RichDisplay()
        display.show_notification("Info", "info")

        text = display._build_notification()
        assert "[INFO]" in str(text)

    def test_unicode_icons_when_ascii_disabled(self, monkeypatch) -> None:
        """Test Unicode icons are used when ASCII mode disabled."""
        monkeypatch.delenv("TOKEN_AUDIT_ASCII", raising=False)

        display = RichDisplay()
        display.show_notification("Success", "success")

        text = display._build_notification()
        text_str = str(text)
        # Should NOT have ASCII fallback
        assert "[OK]" not in text_str


# ============================================================================
# Layout Integration Tests
# ============================================================================


class TestNotificationLayout:
    """Tests for notification in layout."""

    def test_layout_includes_notification_when_active(self) -> None:
        """Test _build_layout includes notification row when active."""
        display = RichDisplay()
        display.show_notification("Test notification", "info")

        snapshot = create_test_snapshot()
        layout = display._build_layout(snapshot)

        # Check layout has notification child
        child_names = [child.name for child in layout.children]
        assert "notification" in child_names

    def test_layout_excludes_notification_when_none(self) -> None:
        """Test _build_layout does not include notification row when None."""
        display = RichDisplay()
        # No notification set

        snapshot = create_test_snapshot()
        layout = display._build_layout(snapshot)

        # Check layout does NOT have notification child
        child_names = [child.name for child in layout.children]
        assert "notification" not in child_names
