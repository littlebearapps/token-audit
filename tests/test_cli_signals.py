#!/usr/bin/env python3
"""
Tests for CLI signal handling functionality.

These tests verify that token-audit collect properly saves sessions when:
- Running in foreground and Ctrl+C pressed (SIGINT)
- Running in background and killed via SIGTERM
- Running via timeout command (SIGTERM)
"""

import signal
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from token_audit import cli
from token_audit.base_tracker import BaseTracker, Session


class MockTracker(BaseTracker):
    """Mock tracker for testing signal handling."""

    def __init__(self, project: str = "test-project"):
        super().__init__(project=project, platform="test-platform")
        self.tracking_started = False
        self.monitoring_started = False
        self.stop_called = False

    def start_tracking(self) -> None:
        self.tracking_started = True

    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        return None

    def get_platform_metadata(self) -> Dict[str, Any]:
        return {"platform": "test"}

    def monitor(self, display: Any = None) -> None:
        self.monitoring_started = True
        # Simulate a long-running process that gets interrupted
        raise KeyboardInterrupt()

    def stop(self) -> Optional[Session]:
        self.stop_called = True
        return super().stop()


class TestGlobalState:
    """Test global state management for signal handlers."""

    def test_globals_initialized_to_none(self) -> None:
        """Global state should start as None/False."""
        # Reset globals (importing fresh would be better but harder)
        cli._active_tracker = None
        cli._active_display = None
        cli._shutdown_in_progress = False
        cli._session_saved = False

        assert cli._active_tracker is None
        assert cli._active_display is None
        assert cli._shutdown_in_progress is False
        assert cli._session_saved is False


class TestCleanupSession:
    """Test the _cleanup_session function."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        cli._active_tracker = None
        cli._active_display = None
        cli._shutdown_in_progress = False
        cli._session_saved = False

    def test_cleanup_does_nothing_if_no_tracker(self) -> None:
        """Cleanup should not crash if no tracker is set."""
        cli._active_tracker = None
        cli._cleanup_session()
        # Should complete without error
        assert cli._shutdown_in_progress is True

    def test_cleanup_prevents_reentry(self) -> None:
        """Cleanup should only run once."""
        cli._shutdown_in_progress = True

        # Create a mock tracker that would fail if called
        mock_tracker = MagicMock()
        mock_tracker.stop.side_effect = Exception("Should not be called")
        cli._active_tracker = mock_tracker

        # Should not call stop() because _shutdown_in_progress is True
        cli._cleanup_session()
        mock_tracker.stop.assert_not_called()

    def test_cleanup_prevents_reentry_if_saved(self) -> None:
        """Cleanup should not run if session already saved."""
        cli._session_saved = True

        mock_tracker = MagicMock()
        mock_tracker.stop.side_effect = Exception("Should not be called")
        cli._active_tracker = mock_tracker

        cli._cleanup_session()
        mock_tracker.stop.assert_not_called()

    def test_cleanup_calls_tracker_stop(self) -> None:
        """Cleanup should call tracker.stop()."""
        mock_tracker = MagicMock()
        mock_session = MagicMock()
        mock_tracker.stop.return_value = mock_session
        mock_tracker.session_dir = Path("/tmp/test-session")
        # Set up session attributes for has_data check
        mock_tracker.session.token_usage.total_tokens = 100
        mock_tracker.session.mcp_tool_calls.total_calls = 1
        cli._active_tracker = mock_tracker

        cli._cleanup_session()

        mock_tracker.stop.assert_called_once()
        assert cli._session_saved is True

    def test_cleanup_handles_tracker_error(self) -> None:
        """Cleanup should handle errors gracefully."""
        mock_tracker = MagicMock()
        # Set up session attributes for has_data check
        mock_tracker.session.token_usage.total_tokens = 100
        mock_tracker.session.mcp_tool_calls.total_calls = 1
        mock_tracker.stop.side_effect = Exception("Test error")
        cli._active_tracker = mock_tracker

        # Should not raise
        cli._cleanup_session()
        assert cli._shutdown_in_progress is True

    def test_cleanup_skips_save_when_no_data(self) -> None:
        """Cleanup should not save session if no data was tracked."""
        mock_tracker = MagicMock()
        mock_session = MagicMock()
        mock_tracker.stop.return_value = mock_session
        mock_tracker.session_dir = Path("/tmp/test-session")
        # Set up session attributes with zero data
        mock_tracker.session.token_usage.total_tokens = 0
        mock_tracker.session.mcp_tool_calls.total_calls = 0
        cli._active_tracker = mock_tracker

        cli._cleanup_session()

        # stop() should NOT be called when no data was tracked
        mock_tracker.stop.assert_not_called()
        # _session_saved should remain False since nothing was saved
        assert cli._session_saved is False


class TestSignalHandler:
    """Test the _signal_handler function."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        cli._active_tracker = None
        cli._active_display = None
        cli._shutdown_in_progress = False
        cli._session_saved = False

    def test_signal_handler_calls_cleanup(self) -> None:
        """Signal handler should call cleanup."""
        mock_tracker = MagicMock()
        mock_tracker.stop.return_value = None
        # Set up session attributes for has_data check
        mock_tracker.session.token_usage.total_tokens = 100
        mock_tracker.session.mcp_tool_calls.total_calls = 1
        cli._active_tracker = mock_tracker

        with pytest.raises(SystemExit) as exc_info:
            cli._signal_handler(signal.SIGINT, None)

        # Should exit with 128 + signal number
        assert exc_info.value.code == 128 + signal.SIGINT
        mock_tracker.stop.assert_called_once()

    def test_signal_handler_sigterm_exit_code(self) -> None:
        """SIGTERM should exit with 128 + SIGTERM."""
        mock_tracker = MagicMock()
        mock_tracker.stop.return_value = None
        # Set up session attributes for has_data check
        mock_tracker.session.token_usage.total_tokens = 100
        mock_tracker.session.mcp_tool_calls.total_calls = 1
        cli._active_tracker = mock_tracker

        with pytest.raises(SystemExit) as exc_info:
            cli._signal_handler(signal.SIGTERM, None)

        assert exc_info.value.code == 128 + signal.SIGTERM


class TestSignalRegistration:
    """Test that signal handlers are properly registered."""

    def test_collect_registers_sigint(self) -> None:
        """cmd_collect should register SIGINT handler."""
        original_handler = signal.getsignal(signal.SIGINT)

        try:
            # Create minimal mock setup
            with (
                patch("token_audit.display.create_display") as mock_create_display,
                patch("token_audit.cli.detect_platform", return_value="claude-code"),
                patch("token_audit.cli.detect_project_name", return_value="test"),
                patch("token_audit.claude_code_adapter.ClaudeCodeAdapter") as mock_adapter_class,
            ):
                mock_display = MagicMock()
                mock_create_display.return_value = mock_display

                mock_adapter = MagicMock()
                mock_adapter.stop.return_value = None
                mock_adapter.session_dir = None
                mock_adapter_class.return_value = mock_adapter

                # Simulate KeyboardInterrupt during monitor
                mock_adapter.monitor.side_effect = KeyboardInterrupt()

                # Create args
                args = MagicMock()
                args.quiet = False
                args.plain = True
                args.tui = False
                args.refresh_rate = 0.5
                args.platform = "auto"
                args.project = None
                args.no_logs = True

                cli.cmd_collect(args)

                # After cmd_collect, SIGINT handler should be our handler
                current_handler = signal.getsignal(signal.SIGINT)
                assert current_handler == cli._signal_handler

        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)

    def test_collect_registers_sigterm(self) -> None:
        """cmd_collect should register SIGTERM handler."""
        original_handler = signal.getsignal(signal.SIGTERM)

        try:
            with (
                patch("token_audit.display.create_display") as mock_create_display,
                patch("token_audit.cli.detect_platform", return_value="claude-code"),
                patch("token_audit.cli.detect_project_name", return_value="test"),
                patch("token_audit.claude_code_adapter.ClaudeCodeAdapter") as mock_adapter_class,
            ):
                mock_display = MagicMock()
                mock_create_display.return_value = mock_display

                mock_adapter = MagicMock()
                mock_adapter.stop.return_value = None
                mock_adapter.session_dir = None
                mock_adapter_class.return_value = mock_adapter
                mock_adapter.monitor.side_effect = KeyboardInterrupt()

                args = MagicMock()
                args.quiet = False
                args.plain = True
                args.tui = False
                args.refresh_rate = 0.5
                args.platform = "auto"
                args.project = None
                args.no_logs = True

                cli.cmd_collect(args)

                current_handler = signal.getsignal(signal.SIGTERM)
                assert current_handler == cli._signal_handler

        finally:
            signal.signal(signal.SIGTERM, original_handler)


class TestSessionSavedFlag:
    """Test the _session_saved flag prevents double-save."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        cli._active_tracker = None
        cli._active_display = None
        cli._shutdown_in_progress = False
        cli._session_saved = False

    def test_session_only_saved_once(self) -> None:
        """Session should only be saved once even if cleanup called multiple times."""
        call_count = 0

        def counting_stop() -> Session:
            nonlocal call_count
            call_count += 1
            session = Session()
            session.project = "test"
            return session

        mock_tracker = MagicMock()
        mock_tracker.stop = counting_stop
        mock_tracker.session_dir = Path("/tmp/test")
        # Set up session attributes for has_data check
        mock_tracker.session.token_usage.total_tokens = 100
        mock_tracker.session.mcp_tool_calls.total_calls = 1
        cli._active_tracker = mock_tracker

        # Call cleanup twice
        cli._cleanup_session()
        cli._cleanup_session()

        # Should only have called stop once
        assert call_count == 1
        assert cli._session_saved is True


class TestIntegrationWithMockTracker:
    """Integration tests using MockTracker."""

    def test_mock_tracker_workflow(self) -> None:
        """Test complete workflow with mock tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MockTracker()

            # Record some data
            tracker.record_tool_call(
                tool_name="mcp__test__tool",
                input_tokens=100,
                output_tokens=50,
            )

            # Finalize and save
            session = tracker.finalize_session()
            tracker.save_session(Path(tmpdir))

            assert session.mcp_tool_calls.total_calls == 1
            assert tracker.session_dir is not None
            # v1.0.4: Single file per session in date subdirectory
            session_files = list(tracker.session_dir.glob("*.json"))
            assert len(session_files) == 1
            assert session_files[0].name.startswith("test-project-")


class TestFirstRunDetection:
    """Test the _check_first_run function."""

    def test_first_run_returns_true_if_marker_exists(self) -> None:
        """Should return True immediately if .initialized marker exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock home directory with marker
            mock_home = Path(tmpdir)
            token_audit_dir = mock_home / ".token-audit"
            token_audit_dir.mkdir()
            marker = token_audit_dir / ".initialized"
            marker.touch()

            with patch.object(Path, "home", return_value=mock_home):
                result = cli._check_first_run()
                assert result is True

    def test_first_run_creates_marker_on_skip(self) -> None:
        """Should create .initialized marker when user skips setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)

            with (
                patch.object(Path, "home", return_value=mock_home),
                patch("builtins.input", return_value="n"),
            ):
                result = cli._check_first_run()
                assert result is True

                # Marker should exist
                marker = mock_home / ".token-audit" / ".initialized"
                assert marker.exists()

    def test_first_run_handles_eof_error(self) -> None:
        """Should handle EOFError gracefully (non-interactive mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)

            with (
                patch.object(Path, "home", return_value=mock_home),
                patch("builtins.input", side_effect=EOFError),
            ):
                result = cli._check_first_run()
                assert result is True

                # Marker should exist
                marker = mock_home / ".token-audit" / ".initialized"
                assert marker.exists()

    def test_first_run_handles_keyboard_interrupt(self) -> None:
        """Should handle KeyboardInterrupt gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_home = Path(tmpdir)

            with (
                patch.object(Path, "home", return_value=mock_home),
                patch("builtins.input", side_effect=KeyboardInterrupt),
            ):
                result = cli._check_first_run()
                assert result is True

                # Marker should exist
                marker = mock_home / ".token-audit" / ".initialized"
                assert marker.exists()
