#!/usr/bin/env python3
"""Task Marker and Manager for per-task bucket analysis (v1.0.4 - task-247.6).

Provides infrastructure to mark logical task boundaries within a session
and compute bucket classification per task.

Usage:
    from token_audit.tasks import TaskManager

    manager = TaskManager()
    manager.start_task("Install plugin", session_id="abc123")
    # ... work happens ...
    manager.end_task(session_id="abc123")

    # Later, analyze tasks
    summaries = manager.get_tasks(session)
    for summary in summaries:
        print(f"{summary.name}: {summary.total_tokens} tokens")
        for bucket, result in summary.buckets.items():
            print(f"  {bucket}: {result.tokens} ({result.percentage:.1f}%)")
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .buckets import BucketClassifier, BucketResult, CallClassification

if TYPE_CHECKING:
    from .base_tracker import Call, Session


def _now_with_timezone() -> datetime:
    """Get current datetime with local timezone offset."""
    return datetime.now(timezone.utc).astimezone()


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 with timezone offset."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now(timezone.utc).astimezone().tzinfo)
    return dt.isoformat(timespec="seconds")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TaskMarker:
    """Marks start or end of a logical task in a session.

    Attributes:
        timestamp: When the marker was created
        name: Human-readable task name (e.g., "Install plugin", "Fix bug")
        marker_type: Either "start" or "end"
        session_id: ID of the session this marker belongs to
    """

    timestamp: datetime = field(default_factory=_now_with_timezone)
    name: str = ""
    marker_type: str = "start"  # "start" or "end"
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "timestamp": _format_timestamp(self.timestamp),
            "name": self.name,
            "type": self.marker_type,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskMarker:
        """Create TaskMarker from dict."""
        timestamp_str = data.get("timestamp", "")
        timestamp = _now_with_timezone()
        if timestamp_str:
            with contextlib.suppress(ValueError, TypeError):
                timestamp = datetime.fromisoformat(timestamp_str)

        return cls(
            timestamp=timestamp,
            name=data.get("name", ""),
            marker_type=data.get("type", "start"),
            session_id=data.get("session_id", ""),
        )


@dataclass
class TaskSummary:
    """Aggregated statistics for a single task.

    Attributes:
        name: Task name
        total_tokens: Total tokens consumed by this task
        buckets: Bucket breakdown for this task (bucket_name -> BucketResult)
        duration_seconds: Task duration in seconds
        call_count: Number of tool calls in this task
        start_time: When the task started
        end_time: When the task ended
        call_indices: List of call indices belonging to this task
    """

    name: str
    total_tokens: int = 0
    buckets: dict[str, BucketResult] = field(default_factory=dict)
    duration_seconds: float = 0.0
    call_count: int = 0
    start_time: datetime = field(default_factory=_now_with_timezone)
    end_time: datetime = field(default_factory=_now_with_timezone)
    call_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "name": self.name,
            "total_tokens": self.total_tokens,
            "buckets": {name: result.to_dict() for name, result in self.buckets.items()},
            "duration_seconds": round(self.duration_seconds, 2),
            "call_count": self.call_count,
            "start_time": _format_timestamp(self.start_time),
            "end_time": _format_timestamp(self.end_time),
            "call_indices": self.call_indices,
        }


# =============================================================================
# TaskManager
# =============================================================================


class TaskManager:
    """Manages task markers and their persistence.

    Task markers are stored in ~/.token-audit/tasks/<session-id>.json
    and can be used to group tool calls into logical tasks for analysis.

    Usage:
        manager = TaskManager()

        # During session
        manager.start_task("Install plugin", session_id="abc123")
        # ... work ...
        manager.end_task(session_id="abc123")

        # Analysis
        session = load_session(...)
        summaries = manager.get_tasks(session)
    """

    DEFAULT_STORAGE_PATH = Path.home() / ".token-audit" / "tasks"

    def __init__(self, storage_path: Path | None = None):
        """Initialize TaskManager.

        Args:
            storage_path: Directory for marker storage.
                         Defaults to ~/.token-audit/tasks/
        """
        self.storage_path = storage_path or self.DEFAULT_STORAGE_PATH
        self.markers: list[TaskMarker] = []
        self._current_task: str | None = None
        self._current_session_id: str | None = None

    def start_task(self, name: str, session_id: str) -> TaskMarker:
        """Create and persist a start marker.

        Args:
            name: Human-readable task name
            session_id: Session ID to associate with this task

        Returns:
            The created TaskMarker
        """
        # End any current task first
        if self._current_task is not None:
            self.end_task(self._current_session_id or session_id)

        marker = TaskMarker(
            timestamp=_now_with_timezone(),
            name=name,
            marker_type="start",
            session_id=session_id,
        )
        self.markers.append(marker)
        self._current_task = name
        self._current_session_id = session_id
        self._save_markers(session_id)
        return marker

    def end_task(self, session_id: str) -> TaskMarker | None:
        """Create and persist an end marker for current task.

        Args:
            session_id: Session ID (should match the start marker)

        Returns:
            The created TaskMarker, or None if no task was active
        """
        if self._current_task is None:
            return None

        marker = TaskMarker(
            timestamp=_now_with_timezone(),
            name=self._current_task,
            marker_type="end",
            session_id=session_id,
        )
        self.markers.append(marker)
        self._current_task = None
        self._current_session_id = None
        self._save_markers(session_id)
        return marker

    def is_task_active(self, session_id: str) -> tuple[bool, str | None]:
        """Check if there's an unclosed task for a session.

        Args:
            session_id: Session ID to check

        Returns:
            Tuple of (is_active, task_name or None)
        """
        markers = self._load_markers(session_id)

        for marker in reversed(markers):
            if marker.marker_type == "start":
                # Check if this start has a matching end
                has_end = any(
                    m.marker_type == "end"
                    and m.name == marker.name
                    and m.timestamp > marker.timestamp
                    for m in markers
                )
                if not has_end:
                    return True, marker.name

        return False, None

    def get_tasks(self, session: Session) -> list[TaskSummary]:
        """Group session calls by task markers and compute summaries.

        Args:
            session: Complete session with server_sessions populated

        Returns:
            List of TaskSummary, one per completed task
        """
        # Load markers for this session
        session_id = session.session_id
        markers = self._load_markers(session_id)

        if not markers:
            return []

        # Build classifier for bucket analysis
        classifier = BucketClassifier()
        hash_counts, hash_first_seen = classifier._build_hash_index(session)

        # Collect all calls with their classifications
        all_calls = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    classification = classifier.classify_call(call, hash_counts, hash_first_seen)
                    all_calls.append((call, classification))

        # Sort calls by index to ensure temporal order
        all_calls.sort(key=lambda x: x[0].index)

        # Group calls by task (between start/end markers)
        summaries = []
        current_task_name: str | None = None
        current_start_time: datetime | None = None
        current_calls: list[tuple[Call, CallClassification]] = []

        for marker in markers:
            if marker.marker_type == "start":
                # If there was a previous task, finalize it
                if current_task_name is not None and current_calls:
                    summary = self._create_summary(
                        current_task_name,
                        current_start_time,
                        marker.timestamp,
                        current_calls,
                    )
                    summaries.append(summary)

                # Start new task
                current_task_name = marker.name
                current_start_time = marker.timestamp
                current_calls = []

            elif marker.marker_type == "end" and current_task_name == marker.name:
                # Collect calls that fall within this task's time range
                for call, classification in all_calls:
                    if (
                        current_start_time
                        and current_start_time <= call.timestamp <= marker.timestamp
                    ):
                        current_calls.append((call, classification))

                # Create summary for this task
                summary = self._create_summary(
                    current_task_name,
                    current_start_time,
                    marker.timestamp,
                    current_calls,
                )
                summaries.append(summary)

                # Reset
                current_task_name = None
                current_start_time = None
                current_calls = []

        return summaries

    def _create_summary(
        self,
        name: str,
        start_time: datetime | None,
        end_time: datetime,
        calls_with_classifications: list[tuple[Call, CallClassification]],
    ) -> TaskSummary:
        """Create a TaskSummary from classified calls.

        Args:
            name: Task name
            start_time: Task start time
            end_time: Task end time
            calls_with_classifications: List of (Call, CallClassification) tuples

        Returns:
            TaskSummary with aggregated statistics
        """
        from .buckets import BucketName

        if not start_time:
            start_time = end_time

        # Calculate duration
        duration = (end_time - start_time).total_seconds()

        # Aggregate by bucket
        bucket_data: dict[str, dict[str, Any]] = {
            bucket: {"tokens": 0, "call_count": 0, "tools": {}} for bucket in BucketName.all()
        }

        call_indices = []
        total_tokens = 0

        for call, classification in calls_with_classifications:
            bucket = classification.primary_bucket
            bucket_data[bucket]["tokens"] += classification.tokens
            bucket_data[bucket]["call_count"] += 1

            tool_name = classification.tool_name
            if tool_name not in bucket_data[bucket]["tools"]:
                bucket_data[bucket]["tools"][tool_name] = 0
            bucket_data[bucket]["tools"][tool_name] += classification.tokens

            call_indices.append(call.index)
            total_tokens += classification.tokens

        # Build bucket results
        buckets: dict[str, BucketResult] = {}
        for bucket_name, data in bucket_data.items():
            percentage = (data["tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0
            top_tools = sorted(data["tools"].items(), key=lambda x: x[1], reverse=True)[:5]
            buckets[bucket_name] = BucketResult(
                bucket=bucket_name,
                tokens=data["tokens"],
                percentage=percentage,
                call_count=data["call_count"],
                top_tools=top_tools,
            )

        return TaskSummary(
            name=name,
            total_tokens=total_tokens,
            buckets=buckets,
            duration_seconds=duration,
            call_count=len(calls_with_classifications),
            start_time=start_time,
            end_time=end_time,
            call_indices=call_indices,
        )

    def _save_markers(self, session_id: str) -> None:
        """Persist markers to ~/.token-audit/tasks/<session-id>.json.

        Loads existing markers from disk first, merges with new markers,
        then writes the complete set. This prevents data loss across
        separate CLI invocations.

        Args:
            session_id: Session ID for filename
        """
        self.storage_path.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_path / f"{session_id}.json"

        # Load existing markers from disk first to prevent data loss
        existing_markers = self._load_markers(session_id)

        # Get new markers for this session
        new_markers = [m for m in self.markers if m.session_id == session_id]

        # Merge: deduplicate by (timestamp, name, marker_type)
        # Use _format_timestamp() for consistent seconds-precision comparison
        # (in-memory markers have microseconds, loaded markers are truncated to seconds)
        existing_keys = {
            (_format_timestamp(m.timestamp), m.name, m.marker_type) for m in existing_markers
        }
        for marker in new_markers:
            key = (_format_timestamp(marker.timestamp), marker.name, marker.marker_type)
            if key not in existing_keys:
                existing_markers.append(marker)

        data = {
            "session_id": session_id,
            "markers": [m.to_dict() for m in existing_markers],
        }

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_markers(self, session_id: str) -> list[TaskMarker]:
        """Load markers from disk.

        Args:
            session_id: Session ID to load markers for

        Returns:
            List of TaskMarker objects
        """
        file_path = self.storage_path / f"{session_id}.json"

        if not file_path.exists():
            return []

        try:
            with open(file_path) as f:
                data = json.load(f)

            markers = []
            for marker_data in data.get("markers", []):
                markers.append(TaskMarker.from_dict(marker_data))

            return markers

        except (json.JSONDecodeError, OSError):
            return []

    def clear_markers(self, session_id: str | None = None) -> None:
        """Clear markers from memory and optionally disk.

        Args:
            session_id: If provided, only clear markers for this session
                       and delete the marker file. If None, clear all.
        """
        if session_id:
            self.markers = [m for m in self.markers if m.session_id != session_id]
            file_path = self.storage_path / f"{session_id}.json"
            if file_path.exists():
                file_path.unlink()
        else:
            self.markers = []
            # Don't delete all files - just clear memory

        self._current_task = None
        self._current_session_id = None

    @property
    def current_task(self) -> str | None:
        """Get the name of the currently active task, if any."""
        return self._current_task

    def list_sessions_with_markers(self) -> list[str]:
        """List all session IDs that have marker files.

        Returns:
            List of session IDs with persisted markers
        """
        if not self.storage_path.exists():
            return []

        sessions = []
        for file_path in self.storage_path.glob("*.json"):
            sessions.append(file_path.stem)

        return sorted(sessions)
