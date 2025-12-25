"""Aggregation data structures and functions for historical token usage reporting.

This module provides the core aggregation engine for token-audit, enabling:
- Daily, weekly, and monthly token/cost aggregations
- Model-level breakdowns per time period
- Project-level grouping for multi-project analysis

All cost values use microdollars (int) to avoid float precision issues:
    1 microdollar = 1/1,000,000 USD

Example:
    >>> from token_audit.aggregation import aggregate_daily
    >>> results = aggregate_daily(platform="claude_code", start_date=date(2025, 1, 1))
    >>> for day in results:
    ...     print(f"{day.date}: {day.cost_usd:.4f} USD")
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from token_audit.session_manager import SessionManager
    from token_audit.storage import Platform, StorageManager

__all__ = [
    "AggregateModelUsage",
    "ProjectAggregate",
    "DailyAggregate",
    "WeeklyAggregate",
    "MonthlyAggregate",
    "aggregate_daily",
    "aggregate_weekly",
    "aggregate_monthly",
]


# Microdollar conversion constant
MICROS_PER_DOLLAR = Decimal(1_000_000)


@dataclass
class AggregateModelUsage:
    """Per-model token and cost breakdown within an aggregate.

    Named differently from base_tracker.ModelUsage to avoid confusion.
    Uses cost_micros (int) instead of cost_usd (float) for precision.

    Attributes:
        model: Model identifier (e.g., "claude-sonnet-4-20250514")
        input_tokens: Total input tokens for this model
        output_tokens: Total output tokens for this model
        cache_created_tokens: Cache creation tokens for this model
        cache_read_tokens: Cache read tokens for this model
        total_tokens: Sum of all token types for this model
        cost_micros: Cost in microdollars (1/1,000,000 USD) for precision
        call_count: Number of tool calls using this model
    """

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_micros: int = 0  # Microdollars for precision
    call_count: int = 0

    @property
    def cost_usd(self) -> Decimal:
        """Return cost in USD as Decimal for display."""
        return Decimal(self.cost_micros) / MICROS_PER_DOLLAR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_micros": self.cost_micros,
            "cost_usd": float(self.cost_usd),  # For human readability
            "call_count": self.call_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AggregateModelUsage":
        """Create from dict (e.g., JSON deserialization)."""
        return cls(
            model=data.get("model", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_created_tokens=data.get("cache_created_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost_micros=data.get("cost_micros", 0),
            call_count=data.get("call_count", 0),
        )


@dataclass
class ProjectAggregate:
    """Per-project token and cost breakdown within an aggregate.

    Attributes:
        project_path: Project directory path (git root or cwd)
        input_tokens: Total input tokens for this project
        output_tokens: Total output tokens for this project
        cache_created_tokens: Cache creation tokens for this project
        cache_read_tokens: Cache read tokens for this project
        total_tokens: Sum of all token types for this project
        cost_micros: Cost in microdollars (1/1,000,000 USD)
        session_count: Number of sessions in this project
    """

    project_path: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_micros: int = 0
    session_count: int = 0

    @property
    def cost_usd(self) -> Decimal:
        """Return cost in USD as Decimal for display."""
        return Decimal(self.cost_micros) / MICROS_PER_DOLLAR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "project_path": self.project_path,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_micros": self.cost_micros,
            "cost_usd": float(self.cost_usd),
            "session_count": self.session_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectAggregate":
        """Create from dict (e.g., JSON deserialization)."""
        return cls(
            project_path=data.get("project_path", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_created_tokens=data.get("cache_created_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost_micros=data.get("cost_micros", 0),
            session_count=data.get("session_count", 0),
        )


@dataclass
class DailyAggregate:
    """Single day token usage and cost metrics.

    Attributes:
        date: Date string in YYYY-MM-DD format
        platform: Platform identifier (e.g., "claude_code", "codex_cli")
        input_tokens: Total input tokens for the day
        output_tokens: Total output tokens for the day
        cache_created_tokens: Cache creation tokens for the day
        cache_read_tokens: Cache read tokens for the day
        total_tokens: Sum of all token types for the day
        cost_micros: Cost in microdollars (1/1,000,000 USD)
        session_count: Number of sessions for the day
        model_breakdowns: Per-model breakdown (model -> AggregateModelUsage)
        project_breakdowns: Per-project breakdown if group_by_project=True
    """

    date: str = ""  # YYYY-MM-DD format
    platform: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_micros: int = 0
    session_count: int = 0
    model_breakdowns: Dict[str, AggregateModelUsage] = field(default_factory=dict)
    project_breakdowns: Optional[Dict[str, ProjectAggregate]] = None

    @property
    def cost_usd(self) -> Decimal:
        """Return cost in USD as Decimal for display."""
        return Decimal(self.cost_micros) / MICROS_PER_DOLLAR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: Dict[str, Any] = {
            "date": self.date,
            "platform": self.platform,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_micros": self.cost_micros,
            "cost_usd": float(self.cost_usd),
            "session_count": self.session_count,
            "model_breakdowns": {k: v.to_dict() for k, v in self.model_breakdowns.items()},
        }
        if self.project_breakdowns is not None:
            result["project_breakdowns"] = {
                k: v.to_dict() for k, v in self.project_breakdowns.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyAggregate":
        """Create from dict (e.g., JSON deserialization)."""
        model_breakdowns = {
            k: AggregateModelUsage.from_dict(v) for k, v in data.get("model_breakdowns", {}).items()
        }
        project_breakdowns = None
        if "project_breakdowns" in data and data["project_breakdowns"] is not None:
            project_breakdowns = {
                k: ProjectAggregate.from_dict(v) for k, v in data["project_breakdowns"].items()
            }
        return cls(
            date=data.get("date", ""),
            platform=data.get("platform", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_created_tokens=data.get("cache_created_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost_micros=data.get("cost_micros", 0),
            session_count=data.get("session_count", 0),
            model_breakdowns=model_breakdowns,
            project_breakdowns=project_breakdowns,
        )


@dataclass
class WeeklyAggregate:
    """Single week token usage and cost metrics.

    Weeks are defined by ISO week numbers (Monday-Sunday) by default,
    but can be configured to start on different days.

    Attributes:
        week_start: Start date of the week (YYYY-MM-DD)
        week_end: End date of the week (YYYY-MM-DD)
        platform: Platform identifier
        input_tokens: Total input tokens for the week
        output_tokens: Total output tokens for the week
        cache_created_tokens: Cache creation tokens for the week
        cache_read_tokens: Cache read tokens for the week
        total_tokens: Sum of all token types for the week
        cost_micros: Cost in microdollars (1/1,000,000 USD)
        session_count: Number of sessions for the week
        model_breakdowns: Per-model breakdown
        project_breakdowns: Per-project breakdown if enabled
    """

    week_start: str = ""  # YYYY-MM-DD format
    week_end: str = ""  # YYYY-MM-DD format
    platform: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_micros: int = 0
    session_count: int = 0
    model_breakdowns: Dict[str, AggregateModelUsage] = field(default_factory=dict)
    project_breakdowns: Optional[Dict[str, ProjectAggregate]] = None

    @property
    def cost_usd(self) -> Decimal:
        """Return cost in USD as Decimal for display."""
        return Decimal(self.cost_micros) / MICROS_PER_DOLLAR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: Dict[str, Any] = {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "platform": self.platform,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_micros": self.cost_micros,
            "cost_usd": float(self.cost_usd),
            "session_count": self.session_count,
            "model_breakdowns": {k: v.to_dict() for k, v in self.model_breakdowns.items()},
        }
        if self.project_breakdowns is not None:
            result["project_breakdowns"] = {
                k: v.to_dict() for k, v in self.project_breakdowns.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeeklyAggregate":
        """Create from dict (e.g., JSON deserialization)."""
        model_breakdowns = {
            k: AggregateModelUsage.from_dict(v) for k, v in data.get("model_breakdowns", {}).items()
        }
        project_breakdowns = None
        if "project_breakdowns" in data and data["project_breakdowns"] is not None:
            project_breakdowns = {
                k: ProjectAggregate.from_dict(v) for k, v in data["project_breakdowns"].items()
            }
        return cls(
            week_start=data.get("week_start", ""),
            week_end=data.get("week_end", ""),
            platform=data.get("platform", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_created_tokens=data.get("cache_created_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost_micros=data.get("cost_micros", 0),
            session_count=data.get("session_count", 0),
            model_breakdowns=model_breakdowns,
            project_breakdowns=project_breakdowns,
        )


@dataclass
class MonthlyAggregate:
    """Single month token usage and cost metrics.

    Attributes:
        year: Year (e.g., 2025)
        month: Month (1-12)
        platform: Platform identifier
        input_tokens: Total input tokens for the month
        output_tokens: Total output tokens for the month
        cache_created_tokens: Cache creation tokens for the month
        cache_read_tokens: Cache read tokens for the month
        total_tokens: Sum of all token types for the month
        cost_micros: Cost in microdollars (1/1,000,000 USD)
        session_count: Number of sessions for the month
        model_breakdowns: Per-model breakdown
        project_breakdowns: Per-project breakdown if enabled
    """

    year: int = 0
    month: int = 0
    platform: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_micros: int = 0
    session_count: int = 0
    model_breakdowns: Dict[str, AggregateModelUsage] = field(default_factory=dict)
    project_breakdowns: Optional[Dict[str, ProjectAggregate]] = None

    @property
    def cost_usd(self) -> Decimal:
        """Return cost in USD as Decimal for display."""
        return Decimal(self.cost_micros) / MICROS_PER_DOLLAR

    @property
    def month_str(self) -> str:
        """Return YYYY-MM format string."""
        return f"{self.year}-{self.month:02d}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result: Dict[str, Any] = {
            "year": self.year,
            "month": self.month,
            "month_str": self.month_str,
            "platform": self.platform,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_micros": self.cost_micros,
            "cost_usd": float(self.cost_usd),
            "session_count": self.session_count,
            "model_breakdowns": {k: v.to_dict() for k, v in self.model_breakdowns.items()},
        }
        if self.project_breakdowns is not None:
            result["project_breakdowns"] = {
                k: v.to_dict() for k, v in self.project_breakdowns.items()
            }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonthlyAggregate":
        """Create from dict (e.g., JSON deserialization)."""
        model_breakdowns = {
            k: AggregateModelUsage.from_dict(v) for k, v in data.get("model_breakdowns", {}).items()
        }
        project_breakdowns = None
        if "project_breakdowns" in data and data["project_breakdowns"] is not None:
            project_breakdowns = {
                k: ProjectAggregate.from_dict(v) for k, v in data["project_breakdowns"].items()
            }
        return cls(
            year=data.get("year", 0),
            month=data.get("month", 0),
            platform=data.get("platform", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_created_tokens=data.get("cache_created_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost_micros=data.get("cost_micros", 0),
            session_count=data.get("session_count", 0),
            model_breakdowns=model_breakdowns,
            project_breakdowns=project_breakdowns,
        )


# =============================================================================
# Aggregation Functions (Task 225.3+)
# =============================================================================


def aggregate_daily(
    platform: Optional["Platform"] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by_project: bool = False,
    storage: Optional["StorageManager"] = None,
) -> List[DailyAggregate]:
    """Aggregate sessions by day.

    Aggregates session data across time periods with accurate token/cost totals,
    model breakdowns, and optional project grouping.

    Args:
        platform: Filter by platform (None = all platforms)
        start_date: Start of date range (None = earliest session)
        end_date: End of date range (None = today)
        group_by_project: Include project_breakdowns in results
        storage: StorageManager instance (None = create default)

    Returns:
        List of DailyAggregate sorted by date ascending.
        Empty list if no sessions in range.

    Example:
        >>> results = aggregate_daily(platform="claude_code", start_date=date(2025, 1, 1))
        >>> for day in results:
        ...     print(f"{day.date}: {day.total_tokens} tokens, ${day.cost_usd:.4f}")
    """
    from token_audit.session_manager import SessionManager
    from token_audit.storage import StorageManager as SM

    # Initialize storage manager
    storage_mgr: SM = storage if storage is not None else SM()

    session_manager = SessionManager()

    # Determine platforms to query
    platforms_to_query = [platform] if platform else storage_mgr.list_platforms()

    if not platforms_to_query:
        return []

    # Determine date range
    actual_end_date = end_date or date.today()
    actual_start_date = start_date

    if actual_start_date is None:
        # Get earliest date across requested platforms
        first_date, _ = storage_mgr.get_date_range(platform)
        if first_date is None:
            return []  # No sessions at all
        actual_start_date = first_date

    # Collect sessions grouped by (date, platform)
    # Key: (date_str, platform) -> List of session paths
    sessions_by_day: Dict[tuple[str, str], List[Path]] = {}

    for p in platforms_to_query:
        session_indexes = storage_mgr.list_sessions_in_range(p, actual_start_date, actual_end_date)
        for idx in session_indexes:
            key = (idx.date, p)
            if key not in sessions_by_day:
                sessions_by_day[key] = []
            # Construct full path from relative path
            session_path = storage_mgr.base_dir / idx.file_path
            sessions_by_day[key].append(session_path)

    if not sessions_by_day:
        return []

    # Build aggregates
    results: List[DailyAggregate] = []

    for (date_str, plat), session_paths in sessions_by_day.items():
        aggregate = _build_daily_aggregate(
            date_str=date_str,
            platform=plat,
            session_paths=session_paths,
            session_manager=session_manager,
            group_by_project=group_by_project,
        )
        if aggregate:
            results.append(aggregate)

    # Sort by date ascending
    results.sort(key=lambda x: x.date)

    return results


def _build_daily_aggregate(
    date_str: str,
    platform: str,
    session_paths: List[Path],
    session_manager: "SessionManager",
    group_by_project: bool,
) -> Optional[DailyAggregate]:
    """Build a DailyAggregate from a list of session paths.

    Args:
        date_str: Date string (YYYY-MM-DD)
        platform: Platform identifier
        session_paths: List of session file paths
        session_manager: SessionManager for loading sessions
        group_by_project: Whether to include project breakdowns

    Returns:
        DailyAggregate with aggregated metrics, or None if no valid sessions
    """
    # Initialize accumulators
    total_input = 0
    total_output = 0
    total_cache_created = 0
    total_cache_read = 0
    total_tokens = 0
    total_cost_micros = 0
    session_count = 0
    model_breakdowns: Dict[str, AggregateModelUsage] = {}
    project_breakdowns: Optional[Dict[str, ProjectAggregate]] = {} if group_by_project else None

    for session_path in session_paths:
        if not session_path.exists():
            continue

        session = session_manager.load_session(session_path)
        if session is None:
            continue

        session_count += 1

        # Aggregate token usage
        if session.token_usage:
            total_input += session.token_usage.input_tokens
            total_output += session.token_usage.output_tokens
            total_cache_created += session.token_usage.cache_created_tokens
            total_cache_read += session.token_usage.cache_read_tokens
            total_tokens += session.token_usage.total_tokens

        # Convert cost to microdollars
        cost_micros = int(session.cost_estimate * 1_000_000)
        total_cost_micros += cost_micros

        # Aggregate model usage
        for model_name, model_usage in session.model_usage.items():
            if model_name not in model_breakdowns:
                model_breakdowns[model_name] = AggregateModelUsage(model=model_name)

            breakdown = model_breakdowns[model_name]
            breakdown.input_tokens += model_usage.input_tokens
            breakdown.output_tokens += model_usage.output_tokens
            breakdown.cache_created_tokens += model_usage.cache_created_tokens
            breakdown.cache_read_tokens += model_usage.cache_read_tokens
            breakdown.total_tokens += model_usage.total_tokens
            breakdown.cost_micros += int(model_usage.cost_usd * 1_000_000)
            breakdown.call_count += model_usage.call_count

        # Aggregate project usage (if enabled)
        if group_by_project and project_breakdowns is not None:
            project_path = session.working_directory or "unknown"
            if project_path not in project_breakdowns:
                project_breakdowns[project_path] = ProjectAggregate(project_path=project_path)

            proj = project_breakdowns[project_path]
            proj.session_count += 1
            if session.token_usage:
                proj.input_tokens += session.token_usage.input_tokens
                proj.output_tokens += session.token_usage.output_tokens
                proj.cache_created_tokens += session.token_usage.cache_created_tokens
                proj.cache_read_tokens += session.token_usage.cache_read_tokens
                proj.total_tokens += session.token_usage.total_tokens
            proj.cost_micros += cost_micros

    if session_count == 0:
        return None

    return DailyAggregate(
        date=date_str,
        platform=platform,
        input_tokens=total_input,
        output_tokens=total_output,
        cache_created_tokens=total_cache_created,
        cache_read_tokens=total_cache_read,
        total_tokens=total_tokens,
        cost_micros=total_cost_micros,
        session_count=session_count,
        model_breakdowns=model_breakdowns,
        project_breakdowns=project_breakdowns,
    )


# =============================================================================
# Helper Functions for Weekly/Monthly Aggregation
# =============================================================================


def _get_week_start(d: date, start_of_week: int = 0) -> date:
    """Get the start of the week containing the given date.

    Args:
        d: The date to find the week start for
        start_of_week: Day of week to use as start (0=Monday, 6=Sunday)

    Returns:
        Date of the start of the week
    """
    # Python weekday(): Monday=0, Sunday=6 (ISO 8601)
    days_since_start = (d.weekday() - start_of_week) % 7
    return d - timedelta(days=days_since_start)


def _merge_model_breakdowns(
    breakdowns: List[Dict[str, AggregateModelUsage]],
) -> Dict[str, AggregateModelUsage]:
    """Merge multiple model breakdown dicts into one.

    Args:
        breakdowns: List of model_breakdowns dicts to merge

    Returns:
        Merged dict with summed values for each model
    """
    merged: Dict[str, AggregateModelUsage] = {}
    for bd in breakdowns:
        for model, usage in bd.items():
            if model in merged:
                # Add to existing
                merged[model] = AggregateModelUsage(
                    model=model,
                    input_tokens=merged[model].input_tokens + usage.input_tokens,
                    output_tokens=merged[model].output_tokens + usage.output_tokens,
                    cache_created_tokens=merged[model].cache_created_tokens
                    + usage.cache_created_tokens,
                    cache_read_tokens=merged[model].cache_read_tokens + usage.cache_read_tokens,
                    total_tokens=merged[model].total_tokens + usage.total_tokens,
                    cost_micros=merged[model].cost_micros + usage.cost_micros,
                    call_count=merged[model].call_count + usage.call_count,
                )
            else:
                # Create new (copy)
                merged[model] = AggregateModelUsage(
                    model=model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_created_tokens=usage.cache_created_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    total_tokens=usage.total_tokens,
                    cost_micros=usage.cost_micros,
                    call_count=usage.call_count,
                )
    return merged


def _merge_project_breakdowns(
    breakdowns: List[Optional[Dict[str, ProjectAggregate]]],
) -> Optional[Dict[str, ProjectAggregate]]:
    """Merge multiple project breakdown dicts into one.

    Args:
        breakdowns: List of project_breakdowns dicts to merge (may contain None)

    Returns:
        Merged dict with summed values for each project, or None if all inputs are None
    """
    # Check if any breakdowns are not None
    non_none = [bd for bd in breakdowns if bd is not None]
    if not non_none:
        return None

    merged: Dict[str, ProjectAggregate] = {}
    for bd in non_none:
        for project_path, proj in bd.items():
            if project_path in merged:
                # Add to existing
                merged[project_path] = ProjectAggregate(
                    project_path=project_path,
                    input_tokens=merged[project_path].input_tokens + proj.input_tokens,
                    output_tokens=merged[project_path].output_tokens + proj.output_tokens,
                    cache_created_tokens=merged[project_path].cache_created_tokens
                    + proj.cache_created_tokens,
                    cache_read_tokens=merged[project_path].cache_read_tokens
                    + proj.cache_read_tokens,
                    total_tokens=merged[project_path].total_tokens + proj.total_tokens,
                    cost_micros=merged[project_path].cost_micros + proj.cost_micros,
                    session_count=merged[project_path].session_count + proj.session_count,
                )
            else:
                # Create new (copy)
                merged[project_path] = ProjectAggregate(
                    project_path=project_path,
                    input_tokens=proj.input_tokens,
                    output_tokens=proj.output_tokens,
                    cache_created_tokens=proj.cache_created_tokens,
                    cache_read_tokens=proj.cache_read_tokens,
                    total_tokens=proj.total_tokens,
                    cost_micros=proj.cost_micros,
                    session_count=proj.session_count,
                )
    return merged


# =============================================================================
# Weekly and Monthly Aggregation Functions (Tasks 225.4, 225.5)
# =============================================================================


def aggregate_weekly(
    platform: Optional["Platform"] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    start_of_week: int = 0,
    group_by_project: bool = False,
    storage: Optional["StorageManager"] = None,
) -> List[WeeklyAggregate]:
    """Aggregate sessions by week.

    Builds on aggregate_daily() by grouping daily results into weeks.

    Args:
        platform: Filter by platform (None = all platforms)
        start_date: Start of date range (None = earliest session)
        end_date: End of date range (None = today)
        start_of_week: Day to use as week start (0=Monday/ISO 8601, 6=Sunday)
        group_by_project: Include project_breakdowns in results
        storage: StorageManager instance (None = create default)

    Returns:
        List of WeeklyAggregate sorted by week_start ascending.
        Empty list if no sessions in range.

    Example:
        >>> results = aggregate_weekly(platform="claude_code", start_of_week=0)
        >>> for week in results:
        ...     print(f"{week.week_start} to {week.week_end}: ${week.cost_usd:.4f}")
    """
    # Get daily aggregates first
    daily_results = aggregate_daily(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        group_by_project=group_by_project,
        storage=storage,
    )

    if not daily_results:
        return []

    # Group by week start date
    # Key: (week_start_str, platform) -> List[DailyAggregate]
    weeks: Dict[tuple[str, str], List[DailyAggregate]] = {}

    for day in daily_results:
        day_date = date.fromisoformat(day.date)
        week_start = _get_week_start(day_date, start_of_week)
        week_start_str = week_start.isoformat()
        key = (week_start_str, day.platform)

        if key not in weeks:
            weeks[key] = []
        weeks[key].append(day)

    # Build weekly aggregates
    results: List[WeeklyAggregate] = []

    for (week_start_str, plat), days in weeks.items():
        # Calculate week_end (6 days after week_start)
        week_start = date.fromisoformat(week_start_str)
        week_end = week_start + timedelta(days=6)

        # Sum all days
        total_input = sum(d.input_tokens for d in days)
        total_output = sum(d.output_tokens for d in days)
        total_cache_created = sum(d.cache_created_tokens for d in days)
        total_cache_read = sum(d.cache_read_tokens for d in days)
        total_tokens = sum(d.total_tokens for d in days)
        total_cost_micros = sum(d.cost_micros for d in days)
        session_count = sum(d.session_count for d in days)

        # Merge breakdowns
        model_breakdowns = _merge_model_breakdowns([d.model_breakdowns for d in days])
        project_breakdowns = _merge_project_breakdowns([d.project_breakdowns for d in days])

        results.append(
            WeeklyAggregate(
                week_start=week_start_str,
                week_end=week_end.isoformat(),
                platform=plat,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_created_tokens=total_cache_created,
                cache_read_tokens=total_cache_read,
                total_tokens=total_tokens,
                cost_micros=total_cost_micros,
                session_count=session_count,
                model_breakdowns=model_breakdowns,
                project_breakdowns=project_breakdowns,
            )
        )

    # Sort by week_start ascending
    results.sort(key=lambda x: x.week_start)

    return results


def aggregate_monthly(
    platform: Optional["Platform"] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by_project: bool = False,
    storage: Optional["StorageManager"] = None,
) -> List[MonthlyAggregate]:
    """Aggregate sessions by month.

    Builds on aggregate_daily() by grouping daily results into calendar months.

    Args:
        platform: Filter by platform (None = all platforms)
        start_date: Start of date range (None = earliest session)
        end_date: End of date range (None = today)
        group_by_project: Include project_breakdowns in results
        storage: StorageManager instance (None = create default)

    Returns:
        List of MonthlyAggregate sorted by (year, month) ascending.
        Empty list if no sessions in range.

    Example:
        >>> results = aggregate_monthly(platform="claude_code")
        >>> for month in results:
        ...     print(f"{month.month_str}: {month.total_tokens} tokens, ${month.cost_usd:.4f}")
    """
    # Get daily aggregates first
    daily_results = aggregate_daily(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        group_by_project=group_by_project,
        storage=storage,
    )

    if not daily_results:
        return []

    # Group by (year, month, platform)
    # Key: (year, month, platform) -> List[DailyAggregate]
    months: Dict[tuple[int, int, str], List[DailyAggregate]] = {}

    for day in daily_results:
        day_date = date.fromisoformat(day.date)
        key = (day_date.year, day_date.month, day.platform)

        if key not in months:
            months[key] = []
        months[key].append(day)

    # Build monthly aggregates
    results: List[MonthlyAggregate] = []

    for (year, month, plat), days in months.items():
        # Sum all days
        total_input = sum(d.input_tokens for d in days)
        total_output = sum(d.output_tokens for d in days)
        total_cache_created = sum(d.cache_created_tokens for d in days)
        total_cache_read = sum(d.cache_read_tokens for d in days)
        total_tokens = sum(d.total_tokens for d in days)
        total_cost_micros = sum(d.cost_micros for d in days)
        session_count = sum(d.session_count for d in days)

        # Merge breakdowns
        model_breakdowns = _merge_model_breakdowns([d.model_breakdowns for d in days])
        project_breakdowns = _merge_project_breakdowns([d.project_breakdowns for d in days])

        results.append(
            MonthlyAggregate(
                year=year,
                month=month,
                platform=plat,
                input_tokens=total_input,
                output_tokens=total_output,
                cache_created_tokens=total_cache_created,
                cache_read_tokens=total_cache_read,
                total_tokens=total_tokens,
                cost_micros=total_cost_micros,
                session_count=session_count,
                model_breakdowns=model_breakdowns,
                project_breakdowns=project_breakdowns,
            )
        )

    # Sort by (year, month) ascending
    results.sort(key=lambda x: (x.year, x.month))

    return results
