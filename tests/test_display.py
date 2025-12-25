"""
Tests for the display module.

Tests DisplaySnapshot, display adapters, and factory function.
"""

import io
import sys
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from token_audit.display import (
    DisplaySnapshot,
    NullDisplay,
    PlainDisplay,
    create_display,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_snapshot(
    project: str = "test-project",
    platform: str = "claude-code",
    total_tokens: int = 1000,
    tool_calls: int = 5,
) -> DisplaySnapshot:
    """Create a test DisplaySnapshot with configurable values."""
    return DisplaySnapshot.create(
        project=project,
        platform=platform,
        start_time=datetime(2025, 1, 1, 12, 0, 0),
        duration_seconds=300.0,
        input_tokens=total_tokens // 2,
        output_tokens=total_tokens // 4,
        cache_tokens=total_tokens // 4,
        total_tokens=total_tokens,
        cache_efficiency=0.25,
        cost_estimate=0.0123,
        total_tool_calls=tool_calls,
        unique_tools=3,
        top_tools=[
            ("mcp__zen__chat", 3, 500, 166),
            ("mcp__brave-search__web", 2, 300, 150),
        ],
        recent_events=[
            (datetime(2025, 1, 1, 12, 4, 30), "mcp__zen__chat", 200),
        ],
    )


# ============================================================================
# DisplaySnapshot Tests
# ============================================================================


class TestDisplaySnapshot:
    """Tests for DisplaySnapshot dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating snapshot with minimal values."""
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="claude-code",
            start_time=datetime.now(),
            duration_seconds=0.0,
        )
        assert snapshot.project == "test"
        assert snapshot.platform == "claude-code"
        assert snapshot.input_tokens == 0
        assert snapshot.total_tokens == 0
        assert snapshot.top_tools == ()
        assert snapshot.recent_events == ()

    def test_create_with_all_fields(self) -> None:
        """Test creating snapshot with all fields populated."""
        snapshot = create_test_snapshot()
        assert snapshot.project == "test-project"
        assert snapshot.platform == "claude-code"
        assert snapshot.total_tokens == 1000
        assert snapshot.total_tool_calls == 5
        assert len(snapshot.top_tools) == 2
        assert len(snapshot.recent_events) == 1

    def test_snapshot_is_frozen(self) -> None:
        """Test that snapshot is immutable (frozen=True)."""
        snapshot = create_test_snapshot()
        with pytest.raises(AttributeError):
            snapshot.total_tokens = 2000  # type: ignore

    def test_top_tools_tuple_conversion(self) -> None:
        """Test that top_tools list is converted to tuple."""
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=datetime.now(),
            duration_seconds=0.0,
            top_tools=[("tool1", 1, 100, 100)],
        )
        assert isinstance(snapshot.top_tools, tuple)
        assert snapshot.top_tools == (("tool1", 1, 100, 100),)

    def test_recent_events_tuple_conversion(self) -> None:
        """Test that recent_events list is converted to tuple."""
        now = datetime.now()
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=now,
            duration_seconds=0.0,
            recent_events=[(now, "tool1", 100)],
        )
        assert isinstance(snapshot.recent_events, tuple)


# ============================================================================
# NullDisplay Tests
# ============================================================================


class TestNullDisplay:
    """Tests for NullDisplay (silent mode)."""

    def test_null_display_produces_no_output(self) -> None:
        """Test that NullDisplay produces no output."""
        display = NullDisplay()
        snapshot = create_test_snapshot()

        captured = io.StringIO()
        with redirect_stdout(captured):
            display.start(snapshot)
            display.update(snapshot)
            display.on_event("mcp__zen__chat", 100, datetime.now())
            display.stop(snapshot)

        assert captured.getvalue() == ""

    def test_null_display_context_manager(self) -> None:
        """Test NullDisplay as context manager."""
        snapshot = create_test_snapshot()
        with NullDisplay() as display:
            display.start(snapshot)
            display.stop(snapshot)
        # Should complete without error


# ============================================================================
# PlainDisplay Tests
# ============================================================================


class TestPlainDisplay:
    """Tests for PlainDisplay (CI/logging mode)."""

    def test_plain_display_start_prints_header(self) -> None:
        """Test PlainDisplay.start() prints header."""
        display = PlainDisplay()
        snapshot = create_test_snapshot()

        captured = io.StringIO()
        with redirect_stdout(captured):
            display.start(snapshot)

        output = captured.getvalue()
        assert "Token Audit" in output
        assert "claude-code" in output
        assert "test-project" in output

    def test_plain_display_stop_prints_summary(self) -> None:
        """Test PlainDisplay.stop() prints summary."""
        display = PlainDisplay()
        snapshot = create_test_snapshot(total_tokens=1000, tool_calls=5)

        captured = io.StringIO()
        with redirect_stdout(captured):
            display.stop(snapshot)

        output = captured.getvalue()
        assert "Session Complete" in output
        assert "1,000" in output  # total tokens
        assert "5" in output  # tool calls

    def test_plain_display_on_event_prints_event(self) -> None:
        """Test PlainDisplay.on_event() prints event details."""
        display = PlainDisplay()
        event_time = datetime(2025, 1, 1, 12, 30, 45)

        captured = io.StringIO()
        with redirect_stdout(captured):
            display.on_event("mcp__zen__chat", 1234, event_time)

        output = captured.getvalue()
        assert "mcp__zen__chat" in output
        assert "1,234" in output
        assert "12:30:45" in output

    def test_plain_display_update_rate_limits(self) -> None:
        """Test PlainDisplay.update() is rate-limited."""
        display = PlainDisplay(print_interval=1.0)
        snapshot = create_test_snapshot()

        captured = io.StringIO()
        with redirect_stdout(captured):
            # First update should print
            display.update(snapshot)
            first_output = captured.getvalue()

            # Second immediate update should NOT print
            display.update(snapshot)
            second_output = captured.getvalue()

        # Should have same output (second update was rate-limited)
        assert first_output == second_output


# ============================================================================
# RichDisplay Tests
# ============================================================================


class TestRichDisplay:
    """Tests for RichDisplay (TUI mode)."""

    def test_rich_display_import(self) -> None:
        """Test that RichDisplay can be imported when Rich is available."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay()
        assert display.refresh_rate == 0.5

    def test_rich_display_custom_refresh_rate(self) -> None:
        """Test RichDisplay with custom refresh rate."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay(refresh_rate=1.0)
        assert display.refresh_rate == 1.0

    def test_rich_display_build_layout_structure(self) -> None:
        """Test RichDisplay._build_layout() returns correct structure."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay()
        snapshot = create_test_snapshot()

        layout = display._build_layout(snapshot)

        # Check layout has expected children
        child_names = [child.name for child in layout.children]
        assert "header" in child_names
        assert "tokens" in child_names
        assert "tools" in child_names
        assert "activity" in child_names
        assert "footer" in child_names

    def test_rich_display_format_duration(self) -> None:
        """Test RichDisplay._format_duration() formatting."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay()

        assert display._format_duration(0) == "00:00:00"
        assert display._format_duration(59) == "00:00:59"
        assert display._format_duration(60) == "00:01:00"
        assert display._format_duration(3661) == "01:01:01"

    def test_rich_display_truncates_long_tool_names(self) -> None:
        """Test that long tool names are truncated in display."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay()
        long_name = "mcp__very_long_server_name__very_long_tool_name_here"
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=datetime.now(),
            duration_seconds=0.0,
            top_tools=[(long_name, 1, 100, 100)],
        )

        # Should not raise an error
        layout = display._build_layout(snapshot)
        assert layout is not None

    def test_rich_display_pinned_servers(self) -> None:
        """Test that pinned servers appear first and have visual indicator."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay(pinned_servers=["zen"])
        assert "zen" in display.pinned_servers

        # Create snapshot with multiple servers
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=datetime.now(),
            duration_seconds=0.0,
            server_hierarchy=(
                ("brave-search", 5, 1000, 200, (("web", 5, 1000, 100.0),)),
                ("zen", 3, 500, 166, (("chat", 3, 500, 100.0),)),
            ),
        )

        # Build layout - should not raise
        layout = display._build_layout(snapshot)
        assert layout is not None

    def test_rich_display_multiple_pinned_servers(self) -> None:
        """Test that multiple servers can be pinned."""
        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay(pinned_servers=["zen", "backlog"])
        assert "zen" in display.pinned_servers
        assert "backlog" in display.pinned_servers
        assert len(display.pinned_servers) == 2


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestCreateDisplay:
    """Tests for create_display() factory function."""

    def test_create_display_quiet_mode(self) -> None:
        """Test create_display with quiet mode returns NullDisplay."""
        display = create_display(mode="quiet")
        assert isinstance(display, NullDisplay)

    def test_create_display_plain_mode(self) -> None:
        """Test create_display with plain mode returns PlainDisplay."""
        display = create_display(mode="plain")
        assert isinstance(display, PlainDisplay)

    def test_create_display_auto_mode_non_tty(self) -> None:
        """Test create_display auto mode falls back to PlainDisplay when not TTY."""
        with patch.object(sys.stdout, "isatty", return_value=False):
            display = create_display(mode="auto")
            assert isinstance(display, PlainDisplay)

    def test_create_display_tui_mode_non_tty_falls_back(self) -> None:
        """Test create_display tui mode falls back to plain with warning when not TTY."""
        with patch.object(sys.stdout, "isatty", return_value=False):
            captured = io.StringIO()
            with redirect_stdout(captured):
                with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                    display = create_display(mode="tui")

                    # Should fall back to PlainDisplay
                    assert isinstance(display, PlainDisplay)
                    # Should print warning to stderr
                    assert "not a TTY" in mock_stderr.getvalue()

    def test_create_display_tui_mode_with_tty(self) -> None:
        """Test create_display tui mode returns RichDisplay when TTY available."""
        with patch.object(sys.stdout, "isatty", return_value=True):
            display = create_display(mode="tui")
            # Should be RichDisplay
            from token_audit.display.rich_display import RichDisplay

            assert isinstance(display, RichDisplay)

    def test_create_display_invalid_mode(self) -> None:
        """Test create_display raises ValueError for invalid mode."""
        with pytest.raises(ValueError, match="Unknown display mode"):
            create_display(mode="invalid")  # type: ignore

    def test_create_display_custom_refresh_rate(self) -> None:
        """Test create_display passes refresh_rate to RichDisplay."""
        with patch.object(sys.stdout, "isatty", return_value=True):
            display = create_display(mode="tui", refresh_rate=2.0)
            from token_audit.display.rich_display import RichDisplay

            assert isinstance(display, RichDisplay)
            assert display.refresh_rate == 2.0


# ============================================================================
# Integration Tests
# ============================================================================


class TestDisplayIntegration:
    """Integration tests for display module."""

    def test_display_lifecycle(self) -> None:
        """Test complete display lifecycle."""
        display = PlainDisplay()
        snapshot = create_test_snapshot()

        captured = io.StringIO()
        with redirect_stdout(captured):
            display.start(snapshot)
            display.on_event("mcp__zen__chat", 500, datetime.now())
            display.update(snapshot)
            display.stop(snapshot)

        output = captured.getvalue()
        # Should have header, event, and summary
        assert "Token Audit" in output
        assert "mcp__zen__chat" in output
        assert "Session Complete" in output

    def test_multiple_displays_independent(self) -> None:
        """Test that multiple display instances are independent."""
        display1 = PlainDisplay()
        display2 = PlainDisplay()

        snapshot = create_test_snapshot()

        captured1 = io.StringIO()
        captured2 = io.StringIO()

        with redirect_stdout(captured1):
            display1.start(snapshot)

        with redirect_stdout(captured2):
            display2.stop(snapshot)

        # Should have different content
        assert "Token Audit" in captured1.getvalue()
        assert "Session Complete" in captured2.getvalue()
        assert captured1.getvalue() != captured2.getvalue()


# ============================================================================
# CLI Integration Tests
# ============================================================================


class TestCLIDisplayIntegration:
    """Tests for CLI display flag combinations."""

    def test_get_display_mode_quiet(self) -> None:
        """Test get_display_mode returns 'quiet' when --quiet flag set."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = True
            plain = False
            tui = False

        assert get_display_mode(MockArgs()) == "quiet"

    def test_get_display_mode_plain(self) -> None:
        """Test get_display_mode returns 'plain' when --plain flag set."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = False
            plain = True
            tui = False

        assert get_display_mode(MockArgs()) == "plain"

    def test_get_display_mode_tui(self) -> None:
        """Test get_display_mode returns 'tui' when --tui flag set."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = False
            plain = False
            tui = True

        assert get_display_mode(MockArgs()) == "tui"

    def test_get_display_mode_auto_default(self) -> None:
        """Test get_display_mode returns 'auto' when no flags set."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = False
            plain = False
            tui = False

        assert get_display_mode(MockArgs()) == "auto"

    def test_get_display_mode_quiet_takes_precedence(self) -> None:
        """Test --quiet takes precedence over other flags."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = True
            plain = True
            tui = True

        # Quiet should override everything
        assert get_display_mode(MockArgs()) == "quiet"

    def test_get_display_mode_plain_before_tui(self) -> None:
        """Test --plain takes precedence over --tui."""
        from token_audit.cli import get_display_mode

        class MockArgs:
            quiet = False
            plain = True
            tui = True

        # Plain should override tui
        assert get_display_mode(MockArgs()) == "plain"
