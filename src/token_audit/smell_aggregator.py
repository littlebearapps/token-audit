#!/usr/bin/env python3
"""
Smell Aggregator - Cross-session smell pattern analysis.

This module aggregates smell patterns across multiple sessions to identify
persistent efficiency issues and trends over time.

Features:
- Query smells across session history by project/platform/date range
- Calculate smell frequencies over time
- Detect trends (improving, worsening, stable)
- Generate aggregation reports
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base_tracker import Session
from .session_manager import SessionManager
from .storage import get_default_base_dir

# Threshold for determining trend direction
TREND_STABILITY_THRESHOLD = 10.0  # +-10% is considered stable


@dataclass
class AggregatedSmell:
    """Aggregated smell statistics across sessions."""

    pattern: str  # e.g., "CHATTY", "LOW_CACHE_HIT"
    total_occurrences: int = 0  # Total times detected across all sessions
    sessions_affected: int = 0  # Number of sessions with this smell
    total_sessions: int = 0  # Total sessions in query range
    frequency_percent: float = 0.0  # sessions_affected / total_sessions * 100
    trend: str = "stable"  # "improving", "worsening", "stable"
    trend_change_percent: float = 0.0  # Percentage change in occurrence rate
    severity_breakdown: Dict[str, int] = field(default_factory=dict)
    top_tools: List[Tuple[str, int]] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern": self.pattern,
            "total_occurrences": self.total_occurrences,
            "sessions_affected": self.sessions_affected,
            "total_sessions": self.total_sessions,
            "frequency_percent": round(self.frequency_percent, 1),
            "trend": self.trend,
            "trend_change_percent": round(self.trend_change_percent, 1),
            "severity_breakdown": self.severity_breakdown,
            "top_tools": self.top_tools,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


@dataclass
class SmellAggregationResult:
    """Complete aggregation result for reporting."""

    query_start: date
    query_end: date
    platform_filter: Optional[str] = None
    project_filter: Optional[str] = None
    total_sessions: int = 0
    sessions_with_smells: int = 0
    aggregated_smells: List[AggregatedSmell] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": {
                "start_date": self.query_start.isoformat(),
                "end_date": self.query_end.isoformat(),
                "platform": self.platform_filter,
                "project": self.project_filter,
            },
            "summary": {
                "total_sessions": self.total_sessions,
                "sessions_with_smells": self.sessions_with_smells,
            },
            "smells": [s.to_dict() for s in self.aggregated_smells],
            "generated_at": self.generated_at.isoformat(),
        }


class SmellAggregator:
    """Aggregates smell patterns across multiple sessions.

    Usage:
        aggregator = SmellAggregator()
        result = aggregator.aggregate(
            days=30,
            platform="claude-code",
            project=None,  # All projects
        )

        for smell in result.aggregated_smells:
            print(f"{smell.pattern}: {smell.frequency_percent:.1f}% ({smell.trend})")
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize with session storage base directory.

        Args:
            base_dir: Base directory for session data. Defaults to ~/.token-audit/sessions/
        """
        self.base_dir = base_dir or get_default_base_dir()

    def aggregate(
        self,
        days: int = 30,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        platform: Optional[str] = None,
        project: Optional[str] = None,
    ) -> SmellAggregationResult:
        """Aggregate smells across sessions in date range.

        Args:
            days: Number of days to analyze (ignored if start_date/end_date provided)
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive, defaults to today)
            platform: Filter by platform name (e.g., "claude-code")
            project: Filter by project name

        Returns:
            SmellAggregationResult with aggregated smell statistics
        """
        # Calculate date range
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=days)

        # Load sessions
        sessions = self._load_sessions(
            start_date=start_date,
            end_date=end_date,
            platform=platform,
            project=project,
        )

        if not sessions:
            return SmellAggregationResult(
                query_start=start_date,
                query_end=end_date,
                platform_filter=platform,
                project_filter=project,
            )

        # Calculate frequencies
        aggregated = self._calculate_frequencies(sessions)

        # Detect trends for each smell
        for pattern, agg_smell in aggregated.items():
            trend, change_pct = self._detect_trend(sessions, pattern)
            agg_smell.trend = trend
            agg_smell.trend_change_percent = change_pct

        # Sort by frequency (highest first)
        sorted_smells = sorted(
            aggregated.values(),
            key=lambda s: s.frequency_percent,
            reverse=True,
        )

        # Count sessions with any smells
        sessions_with_smells = sum(1 for s in sessions if s.smells)

        return SmellAggregationResult(
            query_start=start_date,
            query_end=end_date,
            platform_filter=platform,
            project_filter=project,
            total_sessions=len(sessions),
            sessions_with_smells=sessions_with_smells,
            aggregated_smells=sorted_smells,
            generated_at=datetime.now(),
        )

    def _load_sessions(
        self,
        start_date: date,
        end_date: date,
        platform: Optional[str] = None,
        project: Optional[str] = None,
    ) -> List[Session]:
        """Load sessions matching filters.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            platform: Platform filter
            project: Project filter

        Returns:
            List of Session objects with smell data
        """
        sessions: List[Session] = []

        # Iterate through platform directories
        if not self.base_dir.exists():
            return sessions

        # Handle both old base_dir (direct) and new per-platform structure
        platform_dirs = []

        # Check if base_dir contains platform subdirectories
        # Platform directories use hyphens (claude-code, codex-cli, gemini-cli)
        valid_platforms = ("claude-code", "codex-cli", "gemini-cli", "ollama-cli", "custom")
        for item in self.base_dir.iterdir():
            # If the item looks like a platform directory
            if (
                item.is_dir()
                and item.name in valid_platforms
                and (platform is None or item.name == platform)
            ):
                platform_dirs.append(item)

        if not platform_dirs:
            # Fallback: base_dir might BE a platform directory
            platform_dirs = [self.base_dir]

        # Load sessions from each platform
        for platform_dir in platform_dirs:
            manager = SessionManager(base_dir=platform_dir)

            try:
                session_paths = manager.list_sessions()
            except TypeError:
                # Handle timezone comparison issues in list_sessions
                # Fall back to directly iterating session files
                session_paths = self._find_session_files(platform_dir)

            for session_path in session_paths:
                try:
                    session = manager.load_session(session_path)
                except Exception:
                    continue

                if session is None:
                    continue

                # Apply date filter
                session_date = session.timestamp.date()
                if session_date < start_date or session_date > end_date:
                    continue

                # Apply platform filter (if not already filtered by directory)
                # Platforms use hyphens consistently (claude-code, codex-cli, gemini-cli)
                if platform and session.platform != platform:
                    continue

                # Apply project filter
                if project and session.project != project:
                    continue

                sessions.append(session)

        # Sort by timestamp (oldest first for trend detection)
        # Handle potential timezone comparison issues
        try:
            sessions.sort(key=lambda s: s.timestamp)
        except TypeError:
            # Convert all timestamps to naive for comparison
            sessions.sort(key=lambda s: s.timestamp.replace(tzinfo=None))

        return sessions

    def _find_session_files(self, platform_dir: Path) -> List[Path]:
        """Find session files directly by iterating directories.

        Fallback when SessionManager.list_sessions() fails due to
        timezone comparison issues.

        Args:
            platform_dir: Platform directory to search

        Returns:
            List of session file paths
        """
        session_files: List[Path] = []

        # Look for date directories (YYYY-MM-DD format)
        for item in platform_dir.iterdir():
            if not item.is_dir():
                continue

            # Try parsing as date directory
            try:
                datetime.strptime(item.name, "%Y-%m-%d")
            except ValueError:
                continue

            # Find .json files in date directory
            for session_file in item.glob("*.json"):
                if not session_file.name.startswith("."):
                    session_files.append(session_file)

        return session_files

    def _calculate_frequencies(
        self,
        sessions: List[Session],
    ) -> Dict[str, AggregatedSmell]:
        """Calculate smell frequencies across sessions.

        Args:
            sessions: List of sessions to analyze

        Returns:
            Dictionary mapping pattern name to AggregatedSmell
        """
        if not sessions:
            return {}

        total_sessions = len(sessions)
        aggregated: Dict[str, AggregatedSmell] = {}

        # Track which sessions have each pattern
        sessions_per_pattern: Dict[str, set[int]] = defaultdict(set)
        tool_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        severity_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        first_seen: Dict[str, datetime] = {}
        last_seen: Dict[str, datetime] = {}

        for i, session in enumerate(sessions):
            for smell in session.smells:
                pattern = smell.pattern

                # Track session occurrence
                sessions_per_pattern[pattern].add(i)

                # Track severity
                severity_counts[pattern][smell.severity] += 1

                # Track tool
                if smell.tool:
                    tool_counts[pattern][smell.tool] += 1

                # Track first/last seen
                if pattern not in first_seen:
                    first_seen[pattern] = session.timestamp
                last_seen[pattern] = session.timestamp

        # Build AggregatedSmell for each pattern
        for pattern, session_indices in sessions_per_pattern.items():
            sessions_affected = len(session_indices)
            total_occurrences = sum(severity_counts[pattern].values())

            # Get top tools
            top_tools = sorted(
                tool_counts[pattern].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]

            aggregated[pattern] = AggregatedSmell(
                pattern=pattern,
                total_occurrences=total_occurrences,
                sessions_affected=sessions_affected,
                total_sessions=total_sessions,
                frequency_percent=(sessions_affected / total_sessions) * 100,
                severity_breakdown=dict(severity_counts[pattern]),
                top_tools=top_tools,
                first_seen=first_seen.get(pattern),
                last_seen=last_seen.get(pattern),
            )

        return aggregated

    def _detect_trend(
        self,
        sessions: List[Session],
        pattern: str,
        comparison_ratio: float = 0.5,
    ) -> Tuple[str, float]:
        """Detect trend by comparing recent vs older sessions.

        Uses split-window comparison: divides sessions into old and new halves,
        calculates occurrence rate in each, and compares.

        Args:
            sessions: Sessions sorted by date (oldest first)
            pattern: Smell pattern to analyze
            comparison_ratio: Split point for old/new comparison (0.5 = 50/50)

        Returns:
            Tuple of (trend_direction, change_percent):
            - trend_direction: "improving", "worsening", "stable"
            - change_percent: Percentage change (negative = improving)
        """
        if len(sessions) < 2:
            return ("stable", 0.0)

        # Split into old and new halves
        split_idx = max(1, int(len(sessions) * comparison_ratio))
        old_sessions = sessions[:split_idx]
        new_sessions = sessions[split_idx:]

        if not old_sessions or not new_sessions:
            return ("stable", 0.0)

        def occurrence_rate(session_list: List[Session]) -> float:
            """Calculate occurrence rate for a list of sessions."""
            if not session_list:
                return 0.0
            count = sum(1 for s in session_list if any(sm.pattern == pattern for sm in s.smells))
            return count / len(session_list)

        old_rate = occurrence_rate(old_sessions)
        new_rate = occurrence_rate(new_sessions)

        # Calculate change
        if old_rate == 0:
            if new_rate == 0:
                return ("stable", 0.0)
            else:
                return ("worsening", 100.0)  # Newly appearing

        change_percent = ((new_rate - old_rate) / old_rate) * 100

        # Determine trend with stability threshold
        if change_percent > TREND_STABILITY_THRESHOLD:
            return ("worsening", change_percent)
        elif change_percent < -TREND_STABILITY_THRESHOLD:
            return ("improving", change_percent)
        else:
            return ("stable", change_percent)


def aggregate_smells(
    days: int = 30,
    platform: Optional[str] = None,
    project: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> SmellAggregationResult:
    """Convenience function to aggregate smells.

    Args:
        days: Number of days to analyze
        platform: Filter by platform
        project: Filter by project
        base_dir: Base directory for session data

    Returns:
        SmellAggregationResult with aggregated statistics
    """
    aggregator = SmellAggregator(base_dir=base_dir)
    return aggregator.aggregate(days=days, platform=platform, project=project)
