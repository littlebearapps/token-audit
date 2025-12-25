"""
Tests for the Smell Aggregator (v0.8.0 - task-106.3).

Tests cover:
- AggregatedSmell dataclass
- SmellAggregationResult dataclass
- SmellAggregator frequency calculation
- SmellAggregator trend detection
- CLI integration
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from token_audit.base_tracker import (
    Session,
    Smell,
    TokenUsage,
)
from token_audit.smell_aggregator import (
    TREND_STABILITY_THRESHOLD,
    AggregatedSmell,
    SmellAggregationResult,
    SmellAggregator,
)

# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session(
    project: str = "test-project",
    platform: str = "claude-code",
    days_ago: int = 0,
    smells: list[Smell] | None = None,
) -> Session:
    """Create a test session with optional smells."""
    session = Session(
        project=project,
        platform=platform,
        session_id=f"test-session-{days_ago}",
    )
    session.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    session.token_usage = TokenUsage(
        input_tokens=10000,
        output_tokens=5000,
        total_tokens=15000,
    )
    session.smells = smells or []
    return session


def create_smell(
    pattern: str,
    severity: str = "warning",
    tool: str | None = None,
) -> Smell:
    """Create a test smell."""
    return Smell(
        pattern=pattern,
        severity=severity,
        tool=tool,
        description=f"Test {pattern} smell",
        evidence={"test": True},
    )


# ============================================================================
# AggregatedSmell Tests
# ============================================================================


class TestAggregatedSmell:
    """Tests for AggregatedSmell dataclass."""

    def test_default_values(self) -> None:
        """Test default values for AggregatedSmell."""
        agg = AggregatedSmell(pattern="CHATTY")

        assert agg.pattern == "CHATTY"
        assert agg.total_occurrences == 0
        assert agg.sessions_affected == 0
        assert agg.total_sessions == 0
        assert agg.frequency_percent == 0.0
        assert agg.trend == "stable"
        assert agg.trend_change_percent == 0.0
        assert agg.severity_breakdown == {}
        assert agg.top_tools == []
        assert agg.first_seen is None
        assert agg.last_seen is None

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        now = datetime.now(timezone.utc)
        agg = AggregatedSmell(
            pattern="CHATTY",
            total_occurrences=10,
            sessions_affected=5,
            total_sessions=10,
            frequency_percent=50.0,
            trend="worsening",
            trend_change_percent=25.5,
            severity_breakdown={"warning": 8, "info": 2},
            top_tools=[("tool1", 5), ("tool2", 3)],
            first_seen=now - timedelta(days=5),
            last_seen=now,
        )

        data = agg.to_dict()

        assert data["pattern"] == "CHATTY"
        assert data["total_occurrences"] == 10
        assert data["sessions_affected"] == 5
        assert data["frequency_percent"] == 50.0
        assert data["trend"] == "worsening"
        assert data["trend_change_percent"] == 25.5
        assert data["severity_breakdown"] == {"warning": 8, "info": 2}
        assert data["top_tools"] == [("tool1", 5), ("tool2", 3)]
        assert data["first_seen"] is not None
        assert data["last_seen"] is not None


# ============================================================================
# SmellAggregationResult Tests
# ============================================================================


class TestSmellAggregationResult:
    """Tests for SmellAggregationResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values for SmellAggregationResult."""
        result = SmellAggregationResult(
            query_start=date(2025, 1, 1),
            query_end=date(2025, 1, 31),
        )

        assert result.query_start == date(2025, 1, 1)
        assert result.query_end == date(2025, 1, 31)
        assert result.platform_filter is None
        assert result.project_filter is None
        assert result.total_sessions == 0
        assert result.sessions_with_smells == 0
        assert result.aggregated_smells == []

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        result = SmellAggregationResult(
            query_start=date(2025, 1, 1),
            query_end=date(2025, 1, 31),
            platform_filter="claude-code",
            total_sessions=10,
            sessions_with_smells=5,
            aggregated_smells=[
                AggregatedSmell(pattern="CHATTY", frequency_percent=50.0),
            ],
        )

        data = result.to_dict()

        assert data["query"]["start_date"] == "2025-01-01"
        assert data["query"]["end_date"] == "2025-01-31"
        assert data["query"]["platform"] == "claude-code"
        assert data["summary"]["total_sessions"] == 10
        assert data["summary"]["sessions_with_smells"] == 5
        assert len(data["smells"]) == 1
        assert data["smells"][0]["pattern"] == "CHATTY"


# ============================================================================
# SmellAggregator Frequency Tests
# ============================================================================


class TestSmellAggregatorFrequency:
    """Tests for SmellAggregator frequency calculation."""

    def test_empty_sessions(self) -> None:
        """Test with no sessions."""
        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies([])

        assert result == {}

    def test_no_smells(self) -> None:
        """Test sessions with no smells."""
        sessions = [create_test_session(days_ago=i) for i in range(5)]

        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies(sessions)

        assert result == {}

    def test_single_smell_all_sessions(self) -> None:
        """Test single smell pattern in all sessions."""
        sessions = [
            create_test_session(
                days_ago=i,
                smells=[create_smell("CHATTY", tool="mcp__zen__chat")],
            )
            for i in range(5)
        ]

        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies(sessions)

        assert "CHATTY" in result
        chatty = result["CHATTY"]
        assert chatty.sessions_affected == 5
        assert chatty.total_sessions == 5
        assert chatty.frequency_percent == 100.0
        assert chatty.total_occurrences == 5
        assert chatty.top_tools == [("mcp__zen__chat", 5)]

    def test_smell_in_some_sessions(self) -> None:
        """Test smell pattern in only some sessions."""
        sessions = [
            create_test_session(days_ago=0, smells=[create_smell("CHATTY")]),
            create_test_session(days_ago=1, smells=[]),
            create_test_session(days_ago=2, smells=[create_smell("CHATTY")]),
            create_test_session(days_ago=3, smells=[]),
            create_test_session(days_ago=4, smells=[]),
        ]

        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies(sessions)

        assert "CHATTY" in result
        chatty = result["CHATTY"]
        assert chatty.sessions_affected == 2
        assert chatty.total_sessions == 5
        assert chatty.frequency_percent == 40.0

    def test_multiple_smell_patterns(self) -> None:
        """Test multiple different smell patterns."""
        sessions = [
            create_test_session(
                days_ago=0,
                smells=[
                    create_smell("CHATTY"),
                    create_smell("LOW_CACHE_HIT"),
                ],
            ),
            create_test_session(
                days_ago=1,
                smells=[create_smell("CHATTY")],
            ),
        ]

        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies(sessions)

        assert len(result) == 2
        assert "CHATTY" in result
        assert "LOW_CACHE_HIT" in result
        assert result["CHATTY"].sessions_affected == 2
        assert result["LOW_CACHE_HIT"].sessions_affected == 1

    def test_severity_breakdown(self) -> None:
        """Test severity breakdown tracking."""
        sessions = [
            create_test_session(
                days_ago=i,
                smells=[create_smell("CHATTY", severity=sev)],
            )
            for i, sev in enumerate(["warning", "warning", "info", "high"])
        ]

        aggregator = SmellAggregator()
        result = aggregator._calculate_frequencies(sessions)

        chatty = result["CHATTY"]
        assert chatty.severity_breakdown == {"warning": 2, "info": 1, "high": 1}


# ============================================================================
# SmellAggregator Trend Detection Tests
# ============================================================================


class TestSmellAggregatorTrend:
    """Tests for SmellAggregator trend detection."""

    def test_stable_trend(self) -> None:
        """Test stable trend (no significant change)."""
        # 50% occurrence in both halves
        sessions = [
            create_test_session(days_ago=0, smells=[create_smell("CHATTY")]),
            create_test_session(days_ago=1, smells=[]),
            create_test_session(days_ago=2, smells=[create_smell("CHATTY")]),
            create_test_session(days_ago=3, smells=[]),
        ]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "CHATTY")

        assert trend == "stable"
        assert abs(change) <= TREND_STABILITY_THRESHOLD

    def test_worsening_trend(self) -> None:
        """Test worsening trend (more recent occurrences)."""
        # Old: 0% occurrence, New: 100% occurrence
        sessions = [
            create_test_session(days_ago=4, smells=[]),  # Old
            create_test_session(days_ago=3, smells=[]),  # Old
            create_test_session(days_ago=1, smells=[create_smell("CHATTY")]),  # New
            create_test_session(days_ago=0, smells=[create_smell("CHATTY")]),  # New
        ]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "CHATTY")

        assert trend == "worsening"
        assert change > TREND_STABILITY_THRESHOLD

    def test_improving_trend(self) -> None:
        """Test improving trend (fewer recent occurrences)."""
        # Old: 100% occurrence, New: 0% occurrence
        sessions = [
            create_test_session(days_ago=4, smells=[create_smell("CHATTY")]),  # Old
            create_test_session(days_ago=3, smells=[create_smell("CHATTY")]),  # Old
            create_test_session(days_ago=1, smells=[]),  # New
            create_test_session(days_ago=0, smells=[]),  # New
        ]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "CHATTY")

        assert trend == "improving"
        assert change < -TREND_STABILITY_THRESHOLD

    def test_new_smell_worsening(self) -> None:
        """Test newly appearing smell is classified as worsening."""
        # Old: 0%, New: 100%
        sessions = [
            create_test_session(days_ago=4, smells=[]),
            create_test_session(days_ago=3, smells=[]),
            create_test_session(days_ago=1, smells=[create_smell("CHATTY")]),
            create_test_session(days_ago=0, smells=[create_smell("CHATTY")]),
        ]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "CHATTY")

        assert trend == "worsening"

    def test_single_session(self) -> None:
        """Test with single session returns stable."""
        sessions = [create_test_session(days_ago=0, smells=[create_smell("CHATTY")])]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "CHATTY")

        assert trend == "stable"
        assert change == 0.0

    def test_pattern_not_present(self) -> None:
        """Test trend for pattern not in any session."""
        sessions = [
            create_test_session(days_ago=0, smells=[]),
            create_test_session(days_ago=1, smells=[]),
        ]

        aggregator = SmellAggregator()
        trend, change = aggregator._detect_trend(sessions, "NONEXISTENT")

        assert trend == "stable"
        assert change == 0.0


# ============================================================================
# Integration Tests
# ============================================================================


class TestSmellAggregatorIntegration:
    """Integration tests for SmellAggregator."""

    def test_aggregate_empty_base_dir(self, tmp_path: Path) -> None:
        """Test aggregation with non-existent base directory."""
        aggregator = SmellAggregator(base_dir=tmp_path / "nonexistent")
        result = aggregator.aggregate(days=7)

        assert result.total_sessions == 0
        assert result.aggregated_smells == []

    def test_aggregate_date_range(self) -> None:
        """Test date range calculation."""
        aggregator = SmellAggregator()
        result = aggregator.aggregate(days=7)

        assert result.query_end == date.today()
        assert result.query_start == date.today() - timedelta(days=7)

    def test_aggregate_custom_date_range(self) -> None:
        """Test custom date range."""
        aggregator = SmellAggregator()
        result = aggregator.aggregate(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 15),
        )

        assert result.query_start == date(2025, 1, 1)
        assert result.query_end == date(2025, 1, 15)

    def test_aggregate_platform_filter(self) -> None:
        """Test platform filter is passed through."""
        aggregator = SmellAggregator()
        result = aggregator.aggregate(days=7, platform="claude-code")

        assert result.platform_filter == "claude-code"

    def test_aggregate_project_filter(self) -> None:
        """Test project filter is passed through."""
        aggregator = SmellAggregator()
        result = aggregator.aggregate(days=7, project="my-project")

        assert result.project_filter == "my-project"
