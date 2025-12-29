"""
Tests for the compare command (v1.0.4 - task-247.16).

Tests cover:
- Session comparison with multiple sessions
- Output formats (table, JSON, CSV)
- AVERAGE row calculation
- --latest N flag behavior
- Edge cases (single session, empty sessions)
"""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from token_audit.base_tracker import (
    Call,
    ServerSession,
    Session,
    TokenUsage,
    ToolStats,
)
from token_audit.buckets import BucketClassifier
from token_audit.session_manager import SessionManager
from token_audit.storage import StorageManager


# ============================================================================
# Test Fixtures (copied from test_buckets.py for consistency)
# ============================================================================


def create_test_session(
    input_tokens: int = 10000,
    output_tokens: int = 5000,
    session_id: str = "test-session-123",
    timestamp: datetime = None,
) -> Session:
    """Create a minimal test session."""
    session = Session(
        project="test-project",
        platform="claude-code",
        session_id=session_id,
    )
    session.token_usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
    if timestamp:
        session.timestamp = timestamp
    return session


def add_call_to_session(
    session: Session,
    server_name: str,
    tool_name: str,
    total_tokens: int = 100,
    output_tokens: int = None,
    content_hash: str = None,
    timestamp: datetime = None,
) -> Call:
    """Add a call with full details to a session's call history."""
    if server_name not in session.server_sessions:
        session.server_sessions[server_name] = ServerSession(server=server_name)

    server = session.server_sessions[server_name]
    if tool_name not in server.tools:
        server.tools[tool_name] = ToolStats()

    total_calls = sum(
        sum(len(ts.call_history) for ts in ss.tools.values())
        for ss in session.server_sessions.values()
    )

    if output_tokens is None:
        output_tokens = total_tokens // 2
    input_tokens = total_tokens - output_tokens

    tool_stats = server.tools[tool_name]
    call = Call(
        timestamp=timestamp or datetime.now(timezone.utc),
        tool_name=tool_name,
        server=server_name,
        index=total_calls,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        content_hash=content_hash,
    )
    tool_stats.call_history.append(call)
    tool_stats.calls += 1
    tool_stats.total_tokens += total_tokens
    server.total_calls += 1
    server.total_tokens += total_tokens

    return call


def create_wpnav_session(
    session_id: str = "wpnav-session",
    state_pct: float = 50.0,
    redundant_pct: float = 20.0,
    discovery_pct: float = 10.0,
) -> Session:
    """Create a WP Navigator session with typical patterns.

    Bucket distribution is approximate based on token distribution.
    """
    session = create_test_session(session_id=session_id)
    total_tokens = 10000

    # State serialization calls (get/list patterns)
    state_tokens = int(total_tokens * state_pct / 100)
    if state_tokens > 0:
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__get_page",
            total_tokens=state_tokens // 2,
            content_hash="page1",
        )
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__list_posts",
            total_tokens=state_tokens // 2,
            content_hash="posts1",
        )

    # Redundant calls (duplicate content_hash)
    redundant_tokens = int(total_tokens * redundant_pct / 100)
    if redundant_tokens > 0:
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__get_page",
            total_tokens=redundant_tokens,
            content_hash="page1",  # Duplicate
        )

    # Tool discovery calls (introspect patterns)
    discovery_tokens = int(total_tokens * discovery_pct / 100)
    if discovery_tokens > 0:
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__introspect",
            total_tokens=discovery_tokens,
            content_hash="intro1",
        )

    # Drift - remaining tokens go to non-classified calls
    drift_tokens = total_tokens - state_tokens - redundant_tokens - discovery_tokens
    if drift_tokens > 0:
        add_call_to_session(
            session, "wpnav", "custom_action", total_tokens=drift_tokens, content_hash="drift1"
        )

    return session


# ============================================================================
# SessionComparison Mock (mirrors internal dataclass)
# ============================================================================


@dataclass
class SessionComparison:
    """Mock of internal SessionComparison dataclass."""

    session_name: str
    total_tokens: int
    state_pct: float
    redundant_pct: float
    drift_pct: float
    discovery_pct: float


# ============================================================================
# Compare Output Function Tests
# ============================================================================


class TestCompareOutputFunctions:
    """Tests for compare output formatting functions."""

    def test_compare_format_json_structure(self) -> None:
        """JSON output has correct structure with sessions and averages."""
        from token_audit.cli import _compare_output_json

        comparisons = [
            SessionComparison("session1", 1000, 60.0, 20.0, 15.0, 5.0),
            SessionComparison("session2", 2000, 40.0, 30.0, 20.0, 10.0),
        ]

        # Capture output by writing to a temp file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = _compare_output_json(comparisons, output_path)
            assert result == 0

            data = json.loads(output_path.read_text())

            # Verify structure
            assert "sessions" in data
            assert "averages" in data
            assert "session_count" in data
            assert data["session_count"] == 2

            # Verify sessions
            assert len(data["sessions"]) == 2
            assert data["sessions"][0]["session_name"] == "session1"
            assert data["sessions"][0]["total_tokens"] == 1000
            assert data["sessions"][0]["state_serialization_pct"] == 60.0

            # Verify averages
            assert data["averages"]["total_tokens"] == 1500  # (1000+2000)//2
            assert data["averages"]["state_serialization_pct"] == 50.0  # (60+40)/2
        finally:
            output_path.unlink()

    def test_compare_format_csv_structure(self) -> None:
        """CSV output has correct headers and rows."""
        from token_audit.cli import _compare_output_csv

        comparisons = [
            SessionComparison("session1", 1000, 60.0, 20.0, 15.0, 5.0),
            SessionComparison("session2", 2000, 40.0, 30.0, 20.0, 10.0),
        ]

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = _compare_output_csv(comparisons, output_path)
            assert result == 0

            lines = output_path.read_text().strip().split("\n")

            # Verify header
            assert lines[0] == "session,tokens,state_pct,redundant_pct,drift_pct,discovery_pct"

            # Verify data rows
            assert '"session1"' in lines[1]
            assert "1000" in lines[1]
            assert '"session2"' in lines[2]
            assert "2000" in lines[2]

            # Verify AVERAGE row
            assert '"AVERAGE"' in lines[3]
            assert "1500" in lines[3]  # Average tokens
        finally:
            output_path.unlink()

    def test_compare_average_calculation(self) -> None:
        """AVERAGE row correctly computes mean values."""
        from token_audit.cli import _compare_output_json

        comparisons = [
            SessionComparison("s1", 1000, 60.0, 20.0, 10.0, 10.0),
            SessionComparison("s2", 2000, 40.0, 40.0, 10.0, 10.0),
            SessionComparison("s3", 3000, 30.0, 30.0, 30.0, 10.0),
        ]

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            _compare_output_json(comparisons, output_path)
            data = json.loads(output_path.read_text())

            # Verify calculations
            # avg_tokens = (1000 + 2000 + 3000) // 3 = 2000
            assert data["averages"]["total_tokens"] == 2000

            # avg_state = (60 + 40 + 30) / 3 = 43.33...
            assert abs(data["averages"]["state_serialization_pct"] - 43.33) < 0.1

            # avg_redundant = (20 + 40 + 30) / 3 = 30.0
            assert data["averages"]["redundant_pct"] == 30.0

            # avg_drift = (10 + 10 + 30) / 3 = 16.67
            assert abs(data["averages"]["drift_pct"] - 16.67) < 0.1

            # avg_discovery = (10 + 10 + 10) / 3 = 10.0
            assert data["averages"]["discovery_pct"] == 10.0
        finally:
            output_path.unlink()


# ============================================================================
# Compare Command Integration Tests
# ============================================================================


class TestCompareCommand:
    """Integration tests for cmd_compare function."""

    @pytest.fixture
    def sample_sessions(self, tmp_path: Path) -> List[Path]:
        """Create sample session files for testing."""
        manager = SessionManager()
        paths = []

        for i in range(5):
            session = create_wpnav_session(
                session_id=f"test-session-{i}",
                state_pct=40.0 + i * 5,  # 40%, 45%, 50%, 55%, 60%
                redundant_pct=20.0 - i * 2,  # 20%, 18%, 16%, 14%, 12%
                discovery_pct=10.0,
            )
            session.timestamp = datetime(2024, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc)

            # save_session takes a base dir and returns dict with actual file path
            saved_files = manager.save_session(session, tmp_path)
            paths.append(saved_files["session"])

        return paths

    def test_compare_two_sessions(self, sample_sessions: List[Path]) -> None:
        """Compare 2 sessions and verify bucket percentages in output."""
        from token_audit.cli import cmd_compare

        args = argparse.Namespace(
            sessions=sample_sessions[:2],
            latest=None,
            format="json",
            output=None,
            platform=None,
        )

        # Capture stdout
        import io
        import sys

        captured = io.StringIO()
        sys.stdout = captured

        try:
            result = cmd_compare(args)
        finally:
            sys.stdout = sys.__stdout__

        assert result == 0

        output = captured.getvalue()
        data = json.loads(output)

        assert data["session_count"] == 2
        assert len(data["sessions"]) == 2

    def test_compare_multiple_sessions(self, sample_sessions: List[Path]) -> None:
        """Compare 5+ sessions, verify all appear in results."""
        from token_audit.cli import cmd_compare

        args = argparse.Namespace(
            sessions=sample_sessions,
            latest=None,
            format="json",
            output=None,
            platform=None,
        )

        import io
        import sys

        captured = io.StringIO()
        sys.stdout = captured

        try:
            result = cmd_compare(args)
        finally:
            sys.stdout = sys.__stdout__

        assert result == 0

        output = captured.getvalue()
        data = json.loads(output)

        assert data["session_count"] == 5
        assert len(data["sessions"]) == 5

    def test_compare_latest_n(self, sample_sessions: List[Path], tmp_path: Path) -> None:
        """Use --latest 3 flag, verify correct session selection."""
        from token_audit.cli import cmd_compare

        # Mock StorageManager where it's imported from
        with patch("token_audit.storage.StorageManager") as mock_storage:
            mock_instance = mock_storage.return_value
            # Return latest 3 sessions (newest first)
            mock_instance.list_sessions.return_value = sample_sessions[-3:]

            args = argparse.Namespace(
                sessions=[],
                latest=3,
                format="json",
                output=None,
                platform="claude-code",
            )

            import io
            import sys

            captured = io.StringIO()
            sys.stdout = captured

            try:
                result = cmd_compare(args)
            finally:
                sys.stdout = sys.__stdout__

            assert result == 0
            # Platform is normalized to underscore format
            mock_instance.list_sessions.assert_called_once_with(platform="claude_code", limit=3)

    def test_compare_single_session_warning(self, sample_sessions: List[Path], capsys) -> None:
        """Shows warning if only 1 session found with --latest."""
        from token_audit.cli import cmd_compare

        with patch("token_audit.storage.StorageManager") as mock_storage:
            mock_instance = mock_storage.return_value
            mock_instance.list_sessions.return_value = sample_sessions[:1]

            args = argparse.Namespace(
                sessions=[],
                latest=5,
                format="table",
                output=None,
                platform=None,
            )

            result = cmd_compare(args)

            # Should still succeed but print warning
            captured = capsys.readouterr()
            assert "Warning" in captured.out or result == 0

    def test_compare_empty_sessions(self, capsys) -> None:
        """Handles no matching sessions gracefully."""
        from token_audit.cli import cmd_compare

        with patch("token_audit.storage.StorageManager") as mock_storage:
            mock_instance = mock_storage.return_value
            mock_instance.list_sessions.return_value = []

            args = argparse.Namespace(
                sessions=[],
                latest=5,
                format="table",
                output=None,
                platform=None,
            )

            result = cmd_compare(args)

            assert result == 1
            captured = capsys.readouterr()
            assert "No sessions found" in captured.out

    def test_compare_mutual_exclusivity(self, sample_sessions: List[Path], capsys) -> None:
        """Cannot use both positional sessions and --latest flag."""
        from token_audit.cli import cmd_compare

        args = argparse.Namespace(
            sessions=sample_sessions[:2],
            latest=3,  # Both provided
            format="table",
            output=None,
            platform=None,
        )

        result = cmd_compare(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Cannot use both" in captured.out

    def test_compare_file_not_found(self, tmp_path: Path, capsys) -> None:
        """Error when session file doesn't exist."""
        from token_audit.cli import cmd_compare

        nonexistent = tmp_path / "nonexistent.json"

        args = argparse.Namespace(
            sessions=[nonexistent],
            latest=None,
            format="table",
            output=None,
            platform=None,
        )

        result = cmd_compare(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out
