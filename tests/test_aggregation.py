"""
Tests for the Aggregation module (v1.0.0 - tasks 225.1-225.8).

Tests cover:
- AggregateModelUsage dataclass
- ProjectAggregate dataclass
- DailyAggregate dataclass
- WeeklyAggregate dataclass
- MonthlyAggregate dataclass
- StorageManager.list_sessions_in_range()
- StorageManager.get_date_range()
- aggregate_daily() function
- aggregate_weekly() function
- aggregate_monthly() function
"""

import json
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from token_audit.aggregation import (
    AggregateModelUsage,
    DailyAggregate,
    MonthlyAggregate,
    ProjectAggregate,
    WeeklyAggregate,
    aggregate_daily,
    aggregate_monthly,
    aggregate_weekly,
)
from token_audit.storage import StorageManager

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def storage(temp_storage_dir):
    """Create a StorageManager with temporary storage."""
    return StorageManager(base_dir=temp_storage_dir)


def create_test_session_file(
    storage_dir: Path,
    platform: str,
    session_date: date,
    session_id: str,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cost_estimate: float = 0.01,
    working_directory: str = "/test/project",
    model: str = "claude-sonnet-4",
) -> Path:
    """Create a test session file in storage."""
    date_str = session_date.strftime("%Y-%m-%d")
    # Convert underscore to hyphen for directory name (e.g., claude_code -> claude-code)
    # to match StorageManager.get_platform_dir() behavior
    platform_dir_name = platform.replace("_", "-")
    date_dir = storage_dir / platform_dir_name / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    session_file = date_dir / f"session-{session_id}.json"

    session_data = {
        "_file": {
            "schema_version": "1.7.0",
            "session_id": session_id,
            "started_at": f"{date_str}T10:00:00Z",
            "ended_at": f"{date_str}T11:00:00Z",
            "project": "test-project",
            "total_tokens": input_tokens + output_tokens,
            "total_cost": cost_estimate,
            "tool_count": 5,
            "server_count": 2,
        },
        "session": {
            "id": session_id,
            "project": "test-project",
            "platform": platform,
            "model": model,
            "working_directory": working_directory,
            "started_at": f"{date_str}T10:00:00Z",
            "ended_at": f"{date_str}T11:00:00Z",
            "duration_seconds": 3600,
            "source_files": [],
            "message_count": 10,
            "models_used": [model],
        },
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_created_tokens": 100,
            "cache_read_tokens": 200,
            "reasoning_tokens": 0,
            "total_tokens": input_tokens + output_tokens + 300,
            "cache_efficiency": 0.2,
        },
        "cost_estimate": cost_estimate,  # Key name expected by session_manager
        "cost_no_cache_usd": cost_estimate * 1.5,
        "cache_savings_usd": cost_estimate * 0.5,
        "mcp_summary": {
            "total_calls": 10,
            "unique_tools": 5,
            "unique_servers": 2,
            "servers_used": [],
            "top_by_tokens": [],
            "top_by_calls": [],
        },
        "builtin_tool_summary": {"total_calls": 5, "total_tokens": 500, "tools": []},
        "cache_analysis": {
            "status": "efficient",
            "summary": "Good cache usage",
            "creation_tokens": 100,
            "read_tokens": 200,
            "ratio": 2.0,
            "net_savings_usd": 0.005,
            "top_cache_creators": [],
            "top_cache_readers": [],
            "recommendation": "",
        },
        "tool_calls": [],
        "smells": [],
        "recommendations": [],
        "zombie_tools": {},
        "analysis": {"redundancy": None, "anomalies": []},
        "model_usage": {
            model: {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_created_tokens": 100,
                "cache_read_tokens": 200,
                "total_tokens": input_tokens + output_tokens + 300,
                "cost_usd": cost_estimate,
                "call_count": 10,
            }
        },
        "tool_sequence": [],
        "server_sessions": {},
        "data_quality": None,
    }

    with open(session_file, "w") as f:
        json.dump(session_data, f)

    return session_file


# ============================================================================
# AggregateModelUsage Tests (Task 225.1)
# ============================================================================


class TestAggregateModelUsage:
    """Tests for AggregateModelUsage dataclass."""

    def test_default_values(self) -> None:
        """Test default values for AggregateModelUsage."""
        usage = AggregateModelUsage()

        assert usage.model == ""
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_created_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.total_tokens == 0
        assert usage.cost_micros == 0
        assert usage.call_count == 0

    def test_cost_usd_property(self) -> None:
        """Test cost_usd property returns correct Decimal."""
        usage = AggregateModelUsage(cost_micros=1_500_000)  # $1.50

        assert usage.cost_usd == Decimal("1.5")
        assert isinstance(usage.cost_usd, Decimal)

    def test_cost_usd_zero(self) -> None:
        """Test cost_usd property with zero value."""
        usage = AggregateModelUsage(cost_micros=0)
        assert usage.cost_usd == Decimal("0")

    def test_cost_usd_fractional(self) -> None:
        """Test cost_usd property with fractional value."""
        usage = AggregateModelUsage(cost_micros=123)  # $0.000123
        assert usage.cost_usd == Decimal("0.000123")

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        usage = AggregateModelUsage(
            model="claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
            cache_created_tokens=100,
            cache_read_tokens=200,
            total_tokens=1800,
            cost_micros=50000,  # $0.05
            call_count=10,
        )

        result = usage.to_dict()

        assert result["model"] == "claude-sonnet-4"
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["cost_micros"] == 50000
        assert result["cost_usd"] == 0.05
        assert result["call_count"] == 10

    def test_from_dict(self) -> None:
        """Test from_dict deserialization."""
        data = {
            "model": "claude-opus-4",
            "input_tokens": 2000,
            "output_tokens": 1000,
            "cache_created_tokens": 200,
            "cache_read_tokens": 400,
            "total_tokens": 3600,
            "cost_micros": 100000,
            "call_count": 20,
        }

        usage = AggregateModelUsage.from_dict(data)

        assert usage.model == "claude-opus-4"
        assert usage.input_tokens == 2000
        assert usage.cost_micros == 100000
        assert usage.call_count == 20

    def test_roundtrip(self) -> None:
        """Test to_dict/from_dict roundtrip preserves data."""
        original = AggregateModelUsage(
            model="test-model",
            input_tokens=1234,
            output_tokens=567,
            cache_created_tokens=89,
            cache_read_tokens=12,
            total_tokens=1902,
            cost_micros=34567,
            call_count=99,
        )

        roundtrip = AggregateModelUsage.from_dict(original.to_dict())

        assert roundtrip.model == original.model
        assert roundtrip.input_tokens == original.input_tokens
        assert roundtrip.cost_micros == original.cost_micros


# ============================================================================
# ProjectAggregate Tests (Task 225.1)
# ============================================================================


class TestProjectAggregate:
    """Tests for ProjectAggregate dataclass."""

    def test_default_values(self) -> None:
        """Test default values for ProjectAggregate."""
        proj = ProjectAggregate()

        assert proj.project_path == ""
        assert proj.input_tokens == 0
        assert proj.session_count == 0
        assert proj.cost_micros == 0

    def test_cost_usd_property(self) -> None:
        """Test cost_usd property returns correct Decimal."""
        proj = ProjectAggregate(cost_micros=2_000_000)  # $2.00

        assert proj.cost_usd == Decimal("2")
        assert isinstance(proj.cost_usd, Decimal)

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        proj = ProjectAggregate(
            project_path="/home/user/project",
            input_tokens=5000,
            output_tokens=2500,
            total_tokens=7500,
            cost_micros=75000,
            session_count=5,
        )

        result = proj.to_dict()

        assert result["project_path"] == "/home/user/project"
        assert result["session_count"] == 5
        assert result["cost_usd"] == 0.075

    def test_roundtrip(self) -> None:
        """Test to_dict/from_dict roundtrip preserves data."""
        original = ProjectAggregate(
            project_path="/test/path",
            input_tokens=1000,
            cost_micros=10000,
            session_count=3,
        )

        roundtrip = ProjectAggregate.from_dict(original.to_dict())

        assert roundtrip.project_path == original.project_path
        assert roundtrip.session_count == original.session_count


# ============================================================================
# DailyAggregate Tests (Task 225.1)
# ============================================================================


class TestDailyAggregate:
    """Tests for DailyAggregate dataclass."""

    def test_default_values(self) -> None:
        """Test default values for DailyAggregate."""
        agg = DailyAggregate()

        assert agg.date == ""
        assert agg.platform == ""
        assert agg.input_tokens == 0
        assert agg.cost_micros == 0
        assert agg.session_count == 0
        assert agg.model_breakdowns == {}
        assert agg.project_breakdowns is None

    def test_cost_usd_property(self) -> None:
        """Test cost_usd property returns correct Decimal."""
        agg = DailyAggregate(cost_micros=3_500_000)  # $3.50

        assert agg.cost_usd == Decimal("3.5")

    def test_to_dict_without_project_breakdowns(self) -> None:
        """Test to_dict without project breakdowns."""
        agg = DailyAggregate(
            date="2025-01-15",
            platform="claude_code",
            input_tokens=10000,
            output_tokens=5000,
            total_tokens=15000,
            cost_micros=150000,
            session_count=3,
            model_breakdowns={
                "claude-sonnet-4": AggregateModelUsage(
                    model="claude-sonnet-4",
                    input_tokens=10000,
                    cost_micros=150000,
                )
            },
        )

        result = agg.to_dict()

        assert result["date"] == "2025-01-15"
        assert result["platform"] == "claude_code"
        assert result["session_count"] == 3
        assert "project_breakdowns" not in result
        assert "claude-sonnet-4" in result["model_breakdowns"]

    def test_to_dict_with_project_breakdowns(self) -> None:
        """Test to_dict with project breakdowns."""
        agg = DailyAggregate(
            date="2025-01-15",
            platform="claude_code",
            session_count=2,
            cost_micros=100000,
            project_breakdowns={
                "/project1": ProjectAggregate(project_path="/project1", session_count=1),
                "/project2": ProjectAggregate(project_path="/project2", session_count=1),
            },
        )

        result = agg.to_dict()

        assert "project_breakdowns" in result
        assert "/project1" in result["project_breakdowns"]
        assert "/project2" in result["project_breakdowns"]

    def test_roundtrip(self) -> None:
        """Test to_dict/from_dict roundtrip preserves data."""
        original = DailyAggregate(
            date="2025-01-15",
            platform="claude_code",
            input_tokens=1000,
            cost_micros=10000,
            session_count=2,
            model_breakdowns={
                "model-a": AggregateModelUsage(model="model-a", cost_micros=5000),
            },
        )

        roundtrip = DailyAggregate.from_dict(original.to_dict())

        assert roundtrip.date == original.date
        assert roundtrip.platform == original.platform
        assert roundtrip.cost_micros == original.cost_micros


# ============================================================================
# WeeklyAggregate Tests (Task 225.1)
# ============================================================================


class TestWeeklyAggregate:
    """Tests for WeeklyAggregate dataclass."""

    def test_default_values(self) -> None:
        """Test default values for WeeklyAggregate."""
        agg = WeeklyAggregate()

        assert agg.week_start == ""
        assert agg.week_end == ""
        assert agg.platform == ""
        assert agg.cost_micros == 0

    def test_cost_usd_property(self) -> None:
        """Test cost_usd property returns correct Decimal."""
        agg = WeeklyAggregate(cost_micros=10_000_000)  # $10.00

        assert agg.cost_usd == Decimal("10")

    def test_roundtrip(self) -> None:
        """Test to_dict/from_dict roundtrip preserves data."""
        original = WeeklyAggregate(
            week_start="2025-01-13",
            week_end="2025-01-19",
            platform="claude_code",
            cost_micros=500000,
            session_count=10,
        )

        roundtrip = WeeklyAggregate.from_dict(original.to_dict())

        assert roundtrip.week_start == original.week_start
        assert roundtrip.week_end == original.week_end


# ============================================================================
# MonthlyAggregate Tests (Task 225.1)
# ============================================================================


class TestMonthlyAggregate:
    """Tests for MonthlyAggregate dataclass."""

    def test_default_values(self) -> None:
        """Test default values for MonthlyAggregate."""
        agg = MonthlyAggregate()

        assert agg.year == 0
        assert agg.month == 0
        assert agg.platform == ""
        assert agg.cost_micros == 0

    def test_month_str_property(self) -> None:
        """Test month_str property returns correct format."""
        agg = MonthlyAggregate(year=2025, month=1)
        assert agg.month_str == "2025-01"

        agg = MonthlyAggregate(year=2025, month=12)
        assert agg.month_str == "2025-12"

    def test_cost_usd_property(self) -> None:
        """Test cost_usd property returns correct Decimal."""
        agg = MonthlyAggregate(cost_micros=100_000_000)  # $100.00

        assert agg.cost_usd == Decimal("100")

    def test_roundtrip(self) -> None:
        """Test to_dict/from_dict roundtrip preserves data."""
        original = MonthlyAggregate(
            year=2025,
            month=1,
            platform="claude_code",
            cost_micros=1000000,
            session_count=50,
        )

        roundtrip = MonthlyAggregate.from_dict(original.to_dict())

        assert roundtrip.year == original.year
        assert roundtrip.month == original.month


# ============================================================================
# StorageManager Date Range Tests (Task 225.2)
# ============================================================================


class TestStorageManagerDateRange:
    """Tests for StorageManager date range query methods."""

    def test_get_date_range_empty(self, storage: StorageManager) -> None:
        """Test get_date_range returns (None, None) for empty storage."""
        first, last = storage.get_date_range("claude_code")

        assert first is None
        assert last is None

    def test_get_date_range_single_platform(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test get_date_range returns correct bounds for single platform."""
        # Create sessions on different dates
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 10), "session1")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session2")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 20), "session3")

        first, last = storage.get_date_range("claude_code")

        assert first == date(2025, 1, 10)
        assert last == date(2025, 1, 20)

    def test_get_date_range_all_platforms(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test get_date_range across all platforms."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 5), "session1")
        create_test_session_file(temp_storage_dir, "codex_cli", date(2025, 1, 25), "session2")

        first, last = storage.get_date_range(None)

        assert first == date(2025, 1, 5)
        assert last == date(2025, 1, 25)

    def test_list_sessions_in_range_empty(self, storage: StorageManager) -> None:
        """Test list_sessions_in_range returns empty list for empty storage."""
        result = storage.list_sessions_in_range("claude_code", date(2025, 1, 1), date(2025, 1, 31))

        assert result == []

    def test_list_sessions_in_range_inclusive(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test list_sessions_in_range is inclusive of start and end dates."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 10), "session1")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session2")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 20), "session3")

        # Query exactly the boundary dates
        result = storage.list_sessions_in_range("claude_code", date(2025, 1, 10), date(2025, 1, 20))

        assert len(result) == 3

    def test_list_sessions_in_range_partial(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test list_sessions_in_range filters correctly."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 10), "session1")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session2")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 20), "session3")

        # Query subset
        result = storage.list_sessions_in_range("claude_code", date(2025, 1, 12), date(2025, 1, 18))

        assert len(result) == 1  # Only session2 on 1/15


# ============================================================================
# aggregate_daily() Tests (Task 225.3)
# ============================================================================


class TestAggregateDaily:
    """Tests for aggregate_daily() function."""

    def test_empty_storage_returns_empty_list(self, storage: StorageManager) -> None:
        """Test aggregate_daily returns [] for empty storage."""
        result = aggregate_daily(platform="claude_code", storage=storage)

        assert result == []

    def test_single_session_single_day(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_daily with single session."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            input_tokens=1000,
            output_tokens=500,
            cost_estimate=0.01,
        )

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert result[0].date == "2025-01-15"
        assert result[0].platform == "claude_code"
        assert result[0].session_count == 1
        assert result[0].input_tokens == 1000
        assert result[0].output_tokens == 500
        # Cost should be in microdollars
        assert result[0].cost_micros == 10000  # $0.01 = 10000 microdollars

    def test_multiple_sessions_same_day(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_daily correctly sums multiple sessions on same day."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
            input_tokens=2000,
            cost_estimate=0.02,
        )

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert result[0].session_count == 2
        assert result[0].input_tokens == 3000
        assert result[0].cost_micros == 30000  # $0.03

    def test_multiple_days_sorted_ascending(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_daily returns results sorted by date ascending."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 20), "session3")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 10), "session1")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session2")

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 3
        assert result[0].date == "2025-01-10"
        assert result[1].date == "2025-01-15"
        assert result[2].date == "2025-01-20"

    def test_date_range_filter(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_daily respects date range filter."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 5), "session1")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session2")
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 25), "session3")

        result = aggregate_daily(
            platform="claude_code",
            start_date=date(2025, 1, 10),
            end_date=date(2025, 1, 20),
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].date == "2025-01-15"

    def test_platform_filter(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_daily respects platform filter."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session1")
        create_test_session_file(temp_storage_dir, "codex_cli", date(2025, 1, 15), "session2")

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert result[0].platform == "claude_code"

    def test_all_platforms(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_daily with platform=None includes all platforms."""
        create_test_session_file(temp_storage_dir, "claude_code", date(2025, 1, 15), "session1")
        create_test_session_file(temp_storage_dir, "codex_cli", date(2025, 1, 15), "session2")

        result = aggregate_daily(platform=None, storage=storage)

        assert len(result) == 2
        platforms = {r.platform for r in result}
        assert platforms == {"claude_code", "codex_cli"}

    def test_model_breakdowns(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_daily includes model breakdowns."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            model="claude-sonnet-4",
            input_tokens=1000,
            cost_estimate=0.01,
        )

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert "claude-sonnet-4" in result[0].model_breakdowns
        model_usage = result[0].model_breakdowns["claude-sonnet-4"]
        assert model_usage.model == "claude-sonnet-4"
        assert model_usage.input_tokens == 1000

    def test_group_by_project(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_daily with group_by_project=True."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            working_directory="/project/a",
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
            working_directory="/project/b",
            cost_estimate=0.02,
        )

        result = aggregate_daily(
            platform="claude_code",
            group_by_project=True,
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].project_breakdowns is not None
        assert "/project/a" in result[0].project_breakdowns
        assert "/project/b" in result[0].project_breakdowns
        assert result[0].project_breakdowns["/project/a"].session_count == 1
        assert result[0].project_breakdowns["/project/b"].session_count == 1

    def test_without_group_by_project(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_daily with group_by_project=False."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            working_directory="/project/a",
        )

        result = aggregate_daily(
            platform="claude_code",
            group_by_project=False,
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].project_breakdowns is None

    def test_cost_microdollars_precision(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test that cost is stored as microdollars without float precision loss."""
        # Create session with $0.000001 cost (1 microdollar)
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
            cost_estimate=0.000001,
        )

        result = aggregate_daily(platform="claude_code", storage=storage)

        assert len(result) == 1
        # 0.000001 * 1,000,000 = 1 microdollar
        assert result[0].cost_micros == 1
        assert result[0].cost_usd == Decimal("0.000001")


# ============================================================================
# aggregate_weekly() Tests (Task 225.4, 225.8)
# ============================================================================


class TestAggregateWeekly:
    """Tests for aggregate_weekly() function."""

    def test_empty_storage_returns_empty_list(self, storage: StorageManager) -> None:
        """Test aggregate_weekly returns [] for empty storage."""
        result = aggregate_weekly(platform="claude_code", storage=storage)

        assert result == []

    def test_single_week_monday_start(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_weekly with Monday week start (ISO 8601)."""
        # Create sessions within one week (Mon 2025-01-13 to Sun 2025-01-19)
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 13),  # Monday
            "session1",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),  # Wednesday
            "session2",
            input_tokens=2000,
            cost_estimate=0.02,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 19),  # Sunday
            "session3",
            input_tokens=500,
            cost_estimate=0.005,
        )

        result = aggregate_weekly(platform="claude_code", start_of_week=0, storage=storage)

        assert len(result) == 1
        assert result[0].week_start == "2025-01-13"
        assert result[0].week_end == "2025-01-19"
        assert result[0].session_count == 3
        assert result[0].input_tokens == 3500
        assert result[0].cost_micros == 35000  # $0.035

    def test_single_week_sunday_start(
        self, storage: StorageManager, temp_storage_dir: Path
    ) -> None:
        """Test aggregate_weekly with Sunday week start (US convention)."""
        # Create sessions within one week (Sun 2025-01-12 to Sat 2025-01-18)
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 12),  # Sunday
            "session1",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),  # Wednesday
            "session2",
            input_tokens=2000,
            cost_estimate=0.02,
        )

        result = aggregate_weekly(platform="claude_code", start_of_week=6, storage=storage)

        assert len(result) == 1
        assert result[0].week_start == "2025-01-12"  # Sunday
        assert result[0].week_end == "2025-01-18"  # Saturday
        assert result[0].session_count == 2
        assert result[0].input_tokens == 3000

    def test_multiple_weeks_sorted(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_weekly returns results sorted by week_start ascending."""
        # Create sessions across three weeks
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 27),  # Week 3 (Jan 27-Feb 2)
            "session3",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 13),  # Week 1 (Jan 13-19)
            "session1",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 20),  # Week 2 (Jan 20-26)
            "session2",
        )

        result = aggregate_weekly(platform="claude_code", start_of_week=0, storage=storage)

        assert len(result) == 3
        assert result[0].week_start == "2025-01-13"
        assert result[1].week_start == "2025-01-20"
        assert result[2].week_start == "2025-01-27"

    def test_partial_week_at_start(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_weekly handles partial week at range start."""
        # Session on Wednesday, but full week is Mon-Sun
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),  # Wednesday
            "session1",
            input_tokens=1000,
        )

        result = aggregate_weekly(
            platform="claude_code",
            start_date=date(2025, 1, 15),  # Start mid-week
            end_date=date(2025, 1, 19),
            start_of_week=0,
            storage=storage,
        )

        assert len(result) == 1
        # Week still starts on Monday even though data starts Wednesday
        assert result[0].week_start == "2025-01-13"
        assert result[0].week_end == "2025-01-19"

    def test_totals_match_daily(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test that weekly totals are sums of constituent daily aggregates."""
        # Create multiple sessions across a week
        for day_offset in range(5):
            create_test_session_file(
                temp_storage_dir,
                "claude_code",
                date(2025, 1, 13) + timedelta(days=day_offset),
                f"session{day_offset}",
                input_tokens=1000,
                cost_estimate=0.01,
            )

        daily_results = aggregate_daily(platform="claude_code", storage=storage)
        weekly_results = aggregate_weekly(platform="claude_code", start_of_week=0, storage=storage)

        # Sum daily results
        daily_total_input = sum(d.input_tokens for d in daily_results)
        daily_total_cost = sum(d.cost_micros for d in daily_results)
        daily_total_sessions = sum(d.session_count for d in daily_results)

        # Weekly should match
        assert len(weekly_results) == 1
        assert weekly_results[0].input_tokens == daily_total_input
        assert weekly_results[0].cost_micros == daily_total_cost
        assert weekly_results[0].session_count == daily_total_sessions

    def test_model_breakdowns_merged(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test that model breakdowns are correctly merged across week."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 13),
            "session1",
            model="claude-sonnet-4",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
            model="claude-sonnet-4",
            input_tokens=2000,
            cost_estimate=0.02,
        )

        result = aggregate_weekly(platform="claude_code", start_of_week=0, storage=storage)

        assert len(result) == 1
        assert "claude-sonnet-4" in result[0].model_breakdowns
        model_usage = result[0].model_breakdowns["claude-sonnet-4"]
        assert model_usage.input_tokens == 3000

    def test_project_grouping(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_weekly with group_by_project=True."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 13),
            "session1",
            working_directory="/project/a",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
            working_directory="/project/b",
        )

        result = aggregate_weekly(
            platform="claude_code",
            start_of_week=0,
            group_by_project=True,
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].project_breakdowns is not None
        assert "/project/a" in result[0].project_breakdowns
        assert "/project/b" in result[0].project_breakdowns


# ============================================================================
# aggregate_monthly() Tests (Task 225.5, 225.8)
# ============================================================================


class TestAggregateMonthly:
    """Tests for aggregate_monthly() function."""

    def test_empty_storage_returns_empty_list(self, storage: StorageManager) -> None:
        """Test aggregate_monthly returns [] for empty storage."""
        result = aggregate_monthly(platform="claude_code", storage=storage)

        assert result == []

    def test_single_month(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_monthly with single month data."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 5),
            "session1",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
            input_tokens=2000,
            cost_estimate=0.02,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 25),
            "session3",
            input_tokens=500,
            cost_estimate=0.005,
        )

        result = aggregate_monthly(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert result[0].year == 2025
        assert result[0].month == 1
        assert result[0].month_str == "2025-01"
        assert result[0].session_count == 3
        assert result[0].input_tokens == 3500
        assert result[0].cost_micros == 35000  # $0.035

    def test_multiple_months_sorted(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_monthly returns results sorted by (year, month) ascending."""
        # Create sessions across three months (out of order)
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 3, 15),
            "session3",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session1",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 2, 15),
            "session2",
        )

        result = aggregate_monthly(platform="claude_code", storage=storage)

        assert len(result) == 3
        assert result[0].month_str == "2025-01"
        assert result[1].month_str == "2025-02"
        assert result[2].month_str == "2025-03"

    def test_year_transition(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_monthly handles December to January transition."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2024, 12, 15),
            "session1",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 15),
            "session2",
        )

        result = aggregate_monthly(platform="claude_code", storage=storage)

        assert len(result) == 2
        assert result[0].year == 2024
        assert result[0].month == 12
        assert result[1].year == 2025
        assert result[1].month == 1

    def test_partial_month(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_monthly handles partial month at range boundaries."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 10),
            "session1",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 20),
            "session2",
        )

        result = aggregate_monthly(
            platform="claude_code",
            start_date=date(2025, 1, 15),  # Start mid-month
            end_date=date(2025, 1, 25),  # End before month end
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].month_str == "2025-01"
        assert result[0].session_count == 1  # Only session2 in range

    def test_totals_match_daily(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test that monthly totals are sums of constituent daily aggregates."""
        # Create multiple sessions across a month
        for day in [5, 10, 15, 20, 25]:
            create_test_session_file(
                temp_storage_dir,
                "claude_code",
                date(2025, 1, day),
                f"session{day}",
                input_tokens=1000,
                cost_estimate=0.01,
            )

        daily_results = aggregate_daily(platform="claude_code", storage=storage)
        monthly_results = aggregate_monthly(platform="claude_code", storage=storage)

        # Sum daily results
        daily_total_input = sum(d.input_tokens for d in daily_results)
        daily_total_cost = sum(d.cost_micros for d in daily_results)
        daily_total_sessions = sum(d.session_count for d in daily_results)

        # Monthly should match
        assert len(monthly_results) == 1
        assert monthly_results[0].input_tokens == daily_total_input
        assert monthly_results[0].cost_micros == daily_total_cost
        assert monthly_results[0].session_count == daily_total_sessions

    def test_model_breakdowns_merged(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test that model breakdowns are correctly merged across month."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 5),
            "session1",
            model="claude-sonnet-4",
            input_tokens=1000,
            cost_estimate=0.01,
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 25),
            "session2",
            model="claude-sonnet-4",
            input_tokens=2000,
            cost_estimate=0.02,
        )

        result = aggregate_monthly(platform="claude_code", storage=storage)

        assert len(result) == 1
        assert "claude-sonnet-4" in result[0].model_breakdowns
        model_usage = result[0].model_breakdowns["claude-sonnet-4"]
        assert model_usage.input_tokens == 3000

    def test_project_grouping(self, storage: StorageManager, temp_storage_dir: Path) -> None:
        """Test aggregate_monthly with group_by_project=True."""
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 5),
            "session1",
            working_directory="/project/a",
        )
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            date(2025, 1, 25),
            "session2",
            working_directory="/project/b",
        )

        result = aggregate_monthly(
            platform="claude_code",
            group_by_project=True,
            storage=storage,
        )

        assert len(result) == 1
        assert result[0].project_breakdowns is not None
        assert "/project/a" in result[0].project_breakdowns
        assert "/project/b" in result[0].project_breakdowns
