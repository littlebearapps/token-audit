"""Tests for session comparison feature (v0.8.0 - task-106.7).

Tests session selection, comparison data computation, delta calculations,
smell matrix building, and AI export format.
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from token_audit.display.session_browser import (
    BrowserMode,
    BrowserState,
    ComparisonData,
    SessionBrowser,
    SessionEntry,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session_entry(
    project: str = "test-project",
    platform: str = "claude-code",
    session_date: date = None,
    total_tokens: int = 100000,
    cost_estimate: float = 0.05,
    path: Path = None,
    duration_seconds: float = 3600.0,
    tool_count: int = 5,
    smell_count: int = 0,
) -> SessionEntry:
    """Create a test SessionEntry."""
    return SessionEntry(
        path=path or Path("/tmp/test.json"),
        session_date=session_date or date(2025, 1, 1),
        platform=platform,
        project=project,
        duration_seconds=duration_seconds,
        total_tokens=total_tokens,
        cost_estimate=cost_estimate,
        tool_count=tool_count,
        smell_count=smell_count,
    )


def create_test_session_data(
    total_tokens: int = 100000,
    mcp_tokens: int = 50000,
    tool_usage: Dict[str, int] = None,
    detected_smells: list = None,
) -> Dict[str, Any]:
    """Create test session data JSON content."""
    tool_usage = tool_usage or {"zen.chat": 30000, "brave-search.web": 20000}
    detected_smells = detected_smells or []

    server_sessions = {}
    for tool_key, tokens in tool_usage.items():
        parts = tool_key.split(".")
        server = parts[0]
        tool = parts[1] if len(parts) > 1 else "default"
        if server not in server_sessions:
            server_sessions[server] = {"tools": {}}
        server_sessions[server]["tools"][tool] = {
            "calls": 10,
            "total_tokens": tokens,
        }

    return {
        "session": {
            "timestamp": "2025-01-01T12:00:00",
            "duration_seconds": 3600,
        },
        "token_usage": {
            "total_tokens": total_tokens,
            "input_tokens": total_tokens // 2,
            "output_tokens": total_tokens // 4,
            "cache_tokens": total_tokens // 4,
        },
        "mcp_summary": {
            "total_tokens": mcp_tokens,
            "total_calls": 50,
        },
        "server_sessions": server_sessions,
        "detected_smells": detected_smells,
    }


# ============================================================================
# BrowserState Selection Tests
# ============================================================================


class TestBrowserStateSelection:
    """Tests for session selection state."""

    def test_initial_selected_sessions_empty(self) -> None:
        """Test that selected_sessions is empty initially."""
        state = BrowserState()
        assert state.selected_sessions == set()

    def test_selected_sessions_is_set(self) -> None:
        """Test that selected_sessions is a set type."""
        state = BrowserState()
        assert isinstance(state.selected_sessions, set)

    def test_add_session_to_selection(self) -> None:
        """Test adding session index to selection."""
        state = BrowserState()
        state.selected_sessions.add(0)
        assert 0 in state.selected_sessions

    def test_remove_session_from_selection(self) -> None:
        """Test removing session index from selection."""
        state = BrowserState()
        state.selected_sessions.add(0)
        state.selected_sessions.remove(0)
        assert 0 not in state.selected_sessions

    def test_multiple_sessions_selected(self) -> None:
        """Test multiple session indices can be selected."""
        state = BrowserState()
        state.selected_sessions.add(0)
        state.selected_sessions.add(2)
        state.selected_sessions.add(5)
        assert len(state.selected_sessions) == 3
        assert {0, 2, 5} == state.selected_sessions


# ============================================================================
# BrowserMode Tests
# ============================================================================


class TestBrowserModeComparison:
    """Tests for COMPARISON browser mode."""

    def test_comparison_mode_exists(self) -> None:
        """Test that COMPARISON mode is defined."""
        assert hasattr(BrowserMode, "COMPARISON")
        assert BrowserMode.COMPARISON is not None

    def test_comparison_mode_is_distinct(self) -> None:
        """Test that COMPARISON mode is distinct from other modes."""
        modes = [BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.COMPARISON]
        assert len(modes) == len(set(modes))


# ============================================================================
# ComparisonData Dataclass Tests
# ============================================================================


class TestComparisonDataDataclass:
    """Tests for ComparisonData dataclass."""

    def test_create_comparison_data(self) -> None:
        """Test creating ComparisonData with all fields."""
        baseline_entry = create_test_session_entry()
        comp_entry = create_test_session_entry(session_date=date(2025, 1, 2))

        data = ComparisonData(
            baseline=baseline_entry,
            baseline_data={"token_usage": {"total_tokens": 100000}},
            comparisons=[(comp_entry, {"token_usage": {"total_tokens": 150000}})],
            token_deltas=[50000],
            mcp_share_deltas=[5.0],
            tool_changes=[("zen.chat", 10000)],
            smell_matrix={"HIGH_VARIANCE": [True, False]},
        )

        assert data.baseline == baseline_entry
        assert len(data.comparisons) == 1
        assert data.token_deltas == [50000]
        assert data.mcp_share_deltas == [5.0]
        assert len(data.tool_changes) == 1
        assert "HIGH_VARIANCE" in data.smell_matrix


# ============================================================================
# SessionBrowser Selection Tests
# ============================================================================


class TestSessionBrowserSelection:
    """Tests for session selection in SessionBrowser."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_toggle_selection_adds_session(self, mock_theme) -> None:
        """Test _toggle_session_selection adds session when not selected."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        browser.state = BrowserState()
        browser.state.sessions = [create_test_session_entry()]
        browser.state.selected_index = 0
        browser._notification = None

        browser._toggle_session_selection()

        assert 0 in browser.state.selected_sessions

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_toggle_selection_removes_session(self, mock_theme) -> None:
        """Test _toggle_session_selection removes session when already selected."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        browser.state = BrowserState()
        browser.state.sessions = [create_test_session_entry()]
        browser.state.selected_index = 0
        browser.state.selected_sessions = {0}
        browser._notification = None

        browser._toggle_session_selection()

        assert 0 not in browser.state.selected_sessions

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_toggle_selection_empty_sessions(self, mock_theme) -> None:
        """Test _toggle_session_selection does nothing with empty session list."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        browser.state = BrowserState()
        browser.state.sessions = []
        browser._notification = None

        browser._toggle_session_selection()

        assert len(browser.state.selected_sessions) == 0


# ============================================================================
# Comparison View Opening Tests
# ============================================================================


class TestOpenComparisonView:
    """Tests for opening comparison view."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_open_comparison_requires_two_sessions(self, mock_theme) -> None:
        """Test _open_comparison_view shows warning if < 2 sessions selected."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        browser.state = BrowserState()
        browser.state.sessions = [create_test_session_entry()]
        browser.state.selected_sessions = {0}  # Only 1 selected
        browser._notification = None
        browser._comparison_data = None
        browser.theme = MagicMock()

        browser._open_comparison_view()

        # Should show notification warning
        assert browser._notification is not None
        assert browser._notification.level == "warning"

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_open_comparison_changes_mode(self, mock_theme) -> None:
        """Test _open_comparison_view changes to COMPARISON mode."""
        mock_theme.return_value = MagicMock()

        # Create temp files with test data
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(json.dumps(create_test_session_data()))
            path2.write_text(json.dumps(create_test_session_data(total_tokens=150000)))

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2, session_date=date(2025, 1, 2)),
            ]
            browser.state.selected_sessions = {0, 1}
            browser._notification = None
            browser._comparison_data = None
            browser.theme = MagicMock()

            browser._open_comparison_view()

            assert browser.state.mode == BrowserMode.COMPARISON


# ============================================================================
# Comparison Data Computation Tests
# ============================================================================


class TestComputeComparisonData:
    """Tests for _compute_comparison_data method."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_compute_requires_two_sessions(self, mock_theme) -> None:
        """Test _compute_comparison_data returns None if < 2 sessions."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        browser.state = BrowserState()
        browser.state.sessions = [create_test_session_entry()]
        browser.state.selected_sessions = {0}

        result = browser._compute_comparison_data()
        assert result is None

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_compute_token_deltas(self, mock_theme) -> None:
        """Test token delta computation."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(json.dumps(create_test_session_data(total_tokens=100000)))
            path2.write_text(json.dumps(create_test_session_data(total_tokens=150000)))

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            # 150000 - 100000 = 50000
            assert result.token_deltas[0] == 50000

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_compute_mcp_share_deltas(self, mock_theme) -> None:
        """Test MCP share delta computation."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            # 50% MCP
            path1.write_text(
                json.dumps(create_test_session_data(total_tokens=100000, mcp_tokens=50000))
            )
            # 70% MCP
            path2.write_text(
                json.dumps(create_test_session_data(total_tokens=100000, mcp_tokens=70000))
            )

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            # 70% - 50% = 20%
            assert result.mcp_share_deltas[0] == pytest.approx(20.0, rel=0.01)


# ============================================================================
# Smell Matrix Tests
# ============================================================================


class TestSmellMatrix:
    """Tests for smell matrix computation."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_smell_matrix_empty_when_no_smells(self, mock_theme) -> None:
        """Test smell matrix is empty when no smells detected."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(json.dumps(create_test_session_data(detected_smells=[])))
            path2.write_text(json.dumps(create_test_session_data(detected_smells=[])))

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            assert result.smell_matrix == {}

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_smell_matrix_baseline_only(self, mock_theme) -> None:
        """Test smell matrix when only baseline has smell."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(
                json.dumps(
                    create_test_session_data(
                        detected_smells=[{"pattern": "HIGH_VARIANCE", "severity": "warning"}]
                    )
                )
            )
            path2.write_text(json.dumps(create_test_session_data(detected_smells=[])))

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            assert "HIGH_VARIANCE" in result.smell_matrix
            assert result.smell_matrix["HIGH_VARIANCE"] == [True, False]

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_smell_matrix_both_sessions(self, mock_theme) -> None:
        """Test smell matrix when both sessions have smells."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(
                json.dumps(
                    create_test_session_data(
                        detected_smells=[{"pattern": "HIGH_VARIANCE", "severity": "warning"}]
                    )
                )
            )
            path2.write_text(
                json.dumps(
                    create_test_session_data(
                        detected_smells=[
                            {"pattern": "HIGH_VARIANCE", "severity": "warning"},
                            {"pattern": "TOOL_CHURN", "severity": "info"},
                        ]
                    )
                )
            )

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            assert "HIGH_VARIANCE" in result.smell_matrix
            assert "TOOL_CHURN" in result.smell_matrix
            assert result.smell_matrix["HIGH_VARIANCE"] == [True, True]
            assert result.smell_matrix["TOOL_CHURN"] == [False, True]


# ============================================================================
# Tool Changes Tests
# ============================================================================


class TestToolChanges:
    """Tests for tool changes computation."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_tool_changes_computed(self, mock_theme) -> None:
        """Test that tool changes are computed correctly."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = Path(tmpdir) / "session1.json"
            path2 = Path(tmpdir) / "session2.json"

            path1.write_text(
                json.dumps(
                    create_test_session_data(
                        tool_usage={"zen.chat": 30000, "brave-search.web": 20000}
                    )
                )
            )
            path2.write_text(
                json.dumps(
                    create_test_session_data(
                        tool_usage={"zen.chat": 50000, "brave-search.web": 10000}
                    )
                )
            )

            browser = SessionBrowser.__new__(SessionBrowser)
            browser.state = BrowserState()
            browser.state.sessions = [
                create_test_session_entry(path=path1),
                create_test_session_entry(path=path2),
            ]
            browser.state.selected_sessions = {0, 1}

            result = browser._compute_comparison_data()

            assert result is not None
            assert len(result.tool_changes) > 0
            # Check that tool_changes is a list of (tool_name, delta) tuples
            for tool_name, delta in result.tool_changes:
                assert isinstance(tool_name, str)
                assert isinstance(delta, int)


# ============================================================================
# Load Session Data Tests
# ============================================================================


class TestLoadSessionData:
    """Tests for _load_session_data method."""

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_load_valid_json(self, mock_theme) -> None:
        """Test loading valid session JSON."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            data = create_test_session_data()
            path.write_text(json.dumps(data))

            browser = SessionBrowser.__new__(SessionBrowser)
            result = browser._load_session_data(path)

            assert result is not None
            assert "token_usage" in result

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_load_invalid_json(self, mock_theme) -> None:
        """Test loading invalid JSON returns None."""
        mock_theme.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            path.write_text("not valid json {{{")

            browser = SessionBrowser.__new__(SessionBrowser)
            result = browser._load_session_data(path)

            assert result is None

    @patch("token_audit.display.session_browser.get_active_theme")
    def test_load_missing_file(self, mock_theme) -> None:
        """Test loading missing file returns None."""
        mock_theme.return_value = MagicMock()

        browser = SessionBrowser.__new__(SessionBrowser)
        result = browser._load_session_data(Path("/nonexistent/path.json"))

        assert result is None


# ============================================================================
# Selection Indicator Tests
# ============================================================================


class TestSelectionIndicator:
    """Tests for visual selection indicator in session table."""

    def test_selected_sessions_tracked_in_state(self) -> None:
        """Test that selected sessions are tracked in BrowserState."""
        state = BrowserState()
        state.selected_sessions.add(1)
        state.selected_sessions.add(3)

        assert 1 in state.selected_sessions
        assert 3 in state.selected_sessions
        assert 2 not in state.selected_sessions

    def test_selection_survives_mode_changes(self) -> None:
        """Test that selection survives mode changes."""
        state = BrowserState()
        state.selected_sessions = {0, 2}
        state.mode = BrowserMode.DETAIL

        # Change mode
        state.mode = BrowserMode.LIST

        # Selection should persist
        assert state.selected_sessions == {0, 2}
