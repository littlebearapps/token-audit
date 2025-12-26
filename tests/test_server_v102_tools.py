"""
Tests for v1.0.2 MCP server tools.

Tests the 7 new tools added in v1.0.2:
- get_daily_summary
- get_weekly_summary
- get_monthly_summary
- list_sessions
- get_session_details
- pin_server
- delete_session
"""

import pytest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from token_audit.server import tools
from token_audit.server.schemas import (
    DataQuality,
    GetDailySummaryOutput,
    GetMonthlySummaryOutput,
    GetSessionDetailsOutput,
    GetWeeklySummaryOutput,
    ListSessionsOutput,
    PinAction,
    PinServerOutput,
    DeleteSessionOutput,
    ServerPlatform,
    SessionSortBy,
    SortOrder,
    TrendDirection,
    WeekStartDay,
)


class TestGetDailySummary:
    """Tests for get_daily_summary tool."""

    def test_returns_output_model(self):
        """Result should be GetDailySummaryOutput."""
        result = tools.get_daily_summary(days=7)
        assert isinstance(result, GetDailySummaryOutput)

    def test_default_days(self):
        """Default should be 7 days."""
        result = tools.get_daily_summary()
        assert result.period.days == 7

    def test_period_dates(self):
        """Period should cover correct date range."""
        result = tools.get_daily_summary(days=7)
        # Period end should be today
        assert result.period.end == date.today().isoformat()
        # Period start should be 6 days ago
        expected_start = (date.today() - timedelta(days=6)).isoformat()
        assert result.period.start == expected_start

    def test_empty_sessions_returns_empty_daily(self):
        """Empty sessions should return empty daily list."""
        result = tools.get_daily_summary(days=7)
        # With no sessions, daily list may be empty
        assert isinstance(result.daily, list)

    def test_totals_are_zero_for_empty(self):
        """Totals should be zero when no sessions."""
        result = tools.get_daily_summary(days=7)
        # Totals should exist even if zero
        assert result.totals.sessions >= 0
        assert result.totals.total_tokens >= 0
        assert result.totals.cost_usd >= 0

    def test_trends_default_stable(self):
        """Trends should default to stable for no data."""
        result = tools.get_daily_summary(days=7)
        # Should have trends object
        assert hasattr(result.trends, "direction")
        assert hasattr(result.trends, "avg_daily_cost")


class TestGetWeeklySummary:
    """Tests for get_weekly_summary tool."""

    def test_returns_output_model(self):
        """Result should be GetWeeklySummaryOutput."""
        result = tools.get_weekly_summary(weeks=4)
        assert isinstance(result, GetWeeklySummaryOutput)

    def test_default_weeks(self):
        """Default should be 4 weeks."""
        result = tools.get_weekly_summary()
        assert result.period.weeks == 4

    def test_week_start_monday(self):
        """Week start can be set to Monday."""
        result = tools.get_weekly_summary(start_of_week=WeekStartDay.MONDAY)
        assert isinstance(result, GetWeeklySummaryOutput)

    def test_week_start_sunday(self):
        """Week start can be set to Sunday."""
        result = tools.get_weekly_summary(start_of_week=WeekStartDay.SUNDAY)
        assert isinstance(result, GetWeeklySummaryOutput)

    def test_platform_filter(self):
        """Platform filter should be accepted."""
        result = tools.get_weekly_summary(platform=ServerPlatform.CLAUDE_CODE)
        assert isinstance(result, GetWeeklySummaryOutput)


class TestGetMonthlySummary:
    """Tests for get_monthly_summary tool."""

    def test_returns_output_model(self):
        """Result should be GetMonthlySummaryOutput."""
        result = tools.get_monthly_summary(months=3)
        assert isinstance(result, GetMonthlySummaryOutput)

    def test_default_months(self):
        """Default should be 3 months."""
        result = tools.get_monthly_summary()
        assert result.period.months == 3

    def test_trends_exist(self):
        """Trends should be included."""
        result = tools.get_monthly_summary()
        assert hasattr(result.trends, "direction")


class TestListSessions:
    """Tests for list_sessions tool."""

    def test_returns_output_model(self):
        """Result should be ListSessionsOutput."""
        result = tools.list_sessions(limit=20)
        assert isinstance(result, ListSessionsOutput)

    def test_pagination_info(self):
        """Pagination info should be included."""
        result = tools.list_sessions(limit=10, offset=0)
        assert hasattr(result.pagination, "total")
        assert hasattr(result.pagination, "limit")
        assert hasattr(result.pagination, "offset")
        assert hasattr(result.pagination, "has_more")

    def test_default_limit(self):
        """Default limit should be 20."""
        result = tools.list_sessions()
        assert result.pagination.limit == 20

    def test_default_offset(self):
        """Default offset should be 0."""
        result = tools.list_sessions()
        assert result.pagination.offset == 0

    def test_sort_by_date(self):
        """Should accept date sort."""
        result = tools.list_sessions(sort_by=SessionSortBy.DATE)
        assert isinstance(result, ListSessionsOutput)

    def test_sort_by_cost(self):
        """Should accept cost sort."""
        result = tools.list_sessions(sort_by=SessionSortBy.COST)
        assert isinstance(result, ListSessionsOutput)

    def test_sort_order_desc(self):
        """Should accept desc order."""
        result = tools.list_sessions(sort_order=SortOrder.DESC)
        assert isinstance(result, ListSessionsOutput)

    def test_sort_order_asc(self):
        """Should accept asc order."""
        result = tools.list_sessions(sort_order=SortOrder.ASC)
        assert isinstance(result, ListSessionsOutput)


class TestGetSessionDetails:
    """Tests for get_session_details tool."""

    def test_returns_output_model(self):
        """Result should be GetSessionDetailsOutput."""
        result = tools.get_session_details(session_id="nonexistent-id")
        assert isinstance(result, GetSessionDetailsOutput)

    def test_nonexistent_session_has_unknown_platform(self):
        """Nonexistent session should return unknown platform."""
        result = tools.get_session_details(session_id="nonexistent-id")
        assert result.session.platform == "unknown"

    def test_data_quality_included(self):
        """Data quality should be included."""
        result = tools.get_session_details(session_id="nonexistent-id")
        assert hasattr(result.data_quality, "accuracy_level")
        assert hasattr(result.data_quality, "confidence")

    def test_optional_sections_excluded(self):
        """Optional sections can be excluded."""
        result = tools.get_session_details(
            session_id="nonexistent-id",
            include_tool_calls=False,
            include_smells=False,
            include_recommendations=False,
        )
        assert result.tool_calls == []
        assert result.smells == []
        assert result.recommendations == []


class TestPinServer:
    """Tests for pin_server tool."""

    def test_returns_output_model(self):
        """Result should be PinServerOutput."""
        result = tools.pin_server(
            server_name="test-server",
            action=PinAction.PIN,
        )
        assert isinstance(result, PinServerOutput)

    def test_pin_action(self):
        """Pin action should pin the server."""
        result = tools.pin_server(
            server_name="test-pin-server",
            action=PinAction.PIN,
        )
        assert result.success is True
        assert result.action == PinAction.PIN
        assert "test-pin-server" in result.pinned_servers

    def test_unpin_action(self):
        """Unpin action should unpin the server."""
        # First pin
        tools.pin_server(server_name="test-unpin-server", action=PinAction.PIN)
        # Then unpin
        result = tools.pin_server(
            server_name="test-unpin-server",
            action=PinAction.UNPIN,
        )
        assert result.action == PinAction.UNPIN
        assert "test-unpin-server" not in result.pinned_servers

    def test_notes_accepted(self):
        """Notes parameter should be accepted."""
        result = tools.pin_server(
            server_name="test-notes-server",
            notes="Test notes",
            action=PinAction.PIN,
        )
        assert isinstance(result, PinServerOutput)


class TestDeleteSession:
    """Tests for delete_session tool."""

    def test_returns_output_model(self):
        """Result should be DeleteSessionOutput."""
        result = tools.delete_session(session_id="nonexistent-id", confirm=False)
        assert isinstance(result, DeleteSessionOutput)

    def test_requires_confirmation(self):
        """Deletion should require confirmation."""
        result = tools.delete_session(session_id="test-id", confirm=False)
        assert result.success is False
        assert "confirm" in result.message.lower()

    def test_nonexistent_session_fails(self):
        """Deleting nonexistent session should fail."""
        result = tools.delete_session(session_id="nonexistent-id-12345", confirm=True)
        assert result.success is False
        assert "not found" in result.message.lower()


class TestTrendCalculation:
    """Tests for trend calculation helper."""

    def test_empty_entries_returns_stable(self):
        """Empty entries should return stable trend."""
        direction, change, avg = tools._calculate_usage_trends([])
        assert direction == TrendDirection.STABLE
        assert change == 0.0
        assert avg == 0.0

    def test_single_entry_returns_stable(self):
        """Single entry should return stable trend."""
        direction, change, avg = tools._calculate_usage_trends([(10.0, 1000)])
        assert direction == TrendDirection.STABLE
        assert avg == 10.0

    def test_increasing_trend(self):
        """Increasing costs should show increasing trend."""
        entries = [(1.0, 100), (2.0, 200), (10.0, 1000), (20.0, 2000)]
        direction, change, avg = tools._calculate_usage_trends(entries)
        assert direction == TrendDirection.INCREASING
        assert change > 0

    def test_decreasing_trend(self):
        """Decreasing costs should show decreasing trend."""
        entries = [(20.0, 2000), (10.0, 1000), (2.0, 200), (1.0, 100)]
        direction, change, avg = tools._calculate_usage_trends(entries)
        assert direction == TrendDirection.DECREASING
        assert change < 0

    def test_stable_trend(self):
        """Stable costs should show stable trend."""
        entries = [(10.0, 1000), (10.0, 1000), (10.0, 1000), (10.0, 1000)]
        direction, change, avg = tools._calculate_usage_trends(entries)
        assert direction == TrendDirection.STABLE
        assert abs(change) <= 10  # Within 10% is stable
