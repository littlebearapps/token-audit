#!/usr/bin/env python3
"""Tests for task management module (task-247.6)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from token_audit.base_tracker import Call, ServerSession, Session, ToolStats
from token_audit.buckets import BucketName, BucketResult
from token_audit.tasks import TaskManager, TaskMarker, TaskSummary


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    """Create a temporary storage directory."""
    storage_dir = tmp_path / "tasks"
    storage_dir.mkdir()
    return storage_dir


@pytest.fixture
def sample_session() -> Session:
    """Create a sample session with tool calls for testing."""
    # Create calls with different timestamps and classifications
    now = datetime.now(timezone.utc)
    calls = [
        Call(
            index=0,
            timestamp=now.replace(hour=10, minute=0),
            tool_name="wpnav_introspect",
            server="wpnav",
            total_tokens=100,
            output_tokens=80,
            content_hash="hash_a",
        ),
        Call(
            index=1,
            timestamp=now.replace(hour=10, minute=5),
            tool_name="wpnav_get_page",
            server="wpnav",
            total_tokens=500,
            output_tokens=450,
            content_hash="hash_b",
        ),
        Call(
            index=2,
            timestamp=now.replace(hour=10, minute=10),
            tool_name="Read",
            server="builtin",
            total_tokens=200,
            output_tokens=150,
            content_hash="hash_c",
        ),
        Call(
            index=3,
            timestamp=now.replace(hour=10, minute=15),
            tool_name="wpnav_get_page",
            server="wpnav",
            total_tokens=500,
            output_tokens=450,
            content_hash="hash_b",  # Duplicate of call 1
        ),
    ]

    tool_stats_wpnav_introspect = ToolStats(calls=1, total_tokens=100)
    tool_stats_wpnav_introspect.call_history = [calls[0]]

    tool_stats_wpnav_get = ToolStats(calls=2, total_tokens=1000)
    tool_stats_wpnav_get.call_history = [calls[1], calls[3]]

    tool_stats_read = ToolStats(calls=1, total_tokens=200)
    tool_stats_read.call_history = [calls[2]]

    server_sessions = {
        "wpnav": ServerSession(
            server="wpnav",
            tools={
                "wpnav_introspect": tool_stats_wpnav_introspect,
                "wpnav_get_page": tool_stats_wpnav_get,
            },
            total_calls=3,
            total_tokens=1100,
        ),
        "builtin": ServerSession(
            server="builtin",
            tools={"Read": tool_stats_read},
            total_calls=1,
            total_tokens=200,
        ),
    }

    return Session(
        session_id="test-session-123",
        project="test-project",
        platform="claude-code",
        server_sessions=server_sessions,
    )


# =============================================================================
# TaskMarker Tests
# =============================================================================


class TestTaskMarker:
    """Tests for TaskMarker dataclass."""

    def test_default_values(self) -> None:
        """TaskMarker should have sensible defaults."""
        marker = TaskMarker()

        assert marker.name == ""
        assert marker.marker_type == "start"
        assert marker.session_id == ""
        assert isinstance(marker.timestamp, datetime)

    def test_create_start_marker(self) -> None:
        """Create a start marker with all fields."""
        marker = TaskMarker(
            name="Install plugin",
            marker_type="start",
            session_id="session-123",
        )

        assert marker.name == "Install plugin"
        assert marker.marker_type == "start"
        assert marker.session_id == "session-123"

    def test_create_end_marker(self) -> None:
        """Create an end marker."""
        marker = TaskMarker(
            name="Install plugin",
            marker_type="end",
            session_id="session-123",
        )

        assert marker.marker_type == "end"

    def test_to_dict(self) -> None:
        """to_dict() should return JSON-serializable dict."""
        now = datetime.now(timezone.utc)
        marker = TaskMarker(
            timestamp=now,
            name="Fix bug",
            marker_type="start",
            session_id="abc123",
        )

        result = marker.to_dict()

        assert result["name"] == "Fix bug"
        assert result["type"] == "start"
        assert result["session_id"] == "abc123"
        assert "timestamp" in result
        # Should be serializable
        json.dumps(result)

    def test_from_dict(self) -> None:
        """from_dict() should reconstruct TaskMarker."""
        data = {
            "timestamp": "2025-12-28T10:00:00+00:00",
            "name": "Deploy feature",
            "type": "end",
            "session_id": "xyz789",
        }

        marker = TaskMarker.from_dict(data)

        assert marker.name == "Deploy feature"
        assert marker.marker_type == "end"
        assert marker.session_id == "xyz789"
        assert isinstance(marker.timestamp, datetime)

    def test_from_dict_handles_missing_fields(self) -> None:
        """from_dict() should handle missing fields gracefully."""
        data = {"name": "Test task"}

        marker = TaskMarker.from_dict(data)

        assert marker.name == "Test task"
        assert marker.marker_type == "start"  # default
        assert marker.session_id == ""  # default


# =============================================================================
# TaskSummary Tests
# =============================================================================


class TestTaskSummary:
    """Tests for TaskSummary dataclass."""

    def test_default_values(self) -> None:
        """TaskSummary should have sensible defaults."""
        summary = TaskSummary(name="Test Task")

        assert summary.name == "Test Task"
        assert summary.total_tokens == 0
        assert summary.buckets == {}
        assert summary.duration_seconds == 0.0
        assert summary.call_count == 0
        assert summary.call_indices == []

    def test_create_with_buckets(self) -> None:
        """Create TaskSummary with bucket results."""
        buckets = {
            "drift": BucketResult(bucket="drift", tokens=1000, percentage=50.0, call_count=5),
            "state_serialization": BucketResult(
                bucket="state_serialization",
                tokens=1000,
                percentage=50.0,
                call_count=3,
            ),
        }

        summary = TaskSummary(
            name="Install plugin",
            total_tokens=2000,
            buckets=buckets,
            duration_seconds=120.5,
            call_count=8,
            call_indices=[0, 1, 2, 3, 4, 5, 6, 7],
        )

        assert summary.total_tokens == 2000
        assert len(summary.buckets) == 2
        assert summary.duration_seconds == 120.5
        assert len(summary.call_indices) == 8

    def test_to_dict(self) -> None:
        """to_dict() should return JSON-serializable dict."""
        now = datetime.now(timezone.utc)
        buckets = {"drift": BucketResult(bucket="drift", tokens=500, percentage=100.0)}

        summary = TaskSummary(
            name="Test",
            total_tokens=500,
            buckets=buckets,
            start_time=now,
            end_time=now,
        )

        result = summary.to_dict()

        assert result["name"] == "Test"
        assert result["total_tokens"] == 500
        assert "buckets" in result
        assert "drift" in result["buckets"]
        # Should be serializable
        json.dumps(result)


# =============================================================================
# TaskManager Tests
# =============================================================================


class TestTaskManagerInit:
    """Tests for TaskManager initialization."""

    def test_default_storage_path(self) -> None:
        """TaskManager should use default storage path."""
        manager = TaskManager()

        assert manager.storage_path == Path.home() / ".token-audit" / "tasks"

    def test_custom_storage_path(self, temp_storage: Path) -> None:
        """TaskManager should accept custom storage path."""
        manager = TaskManager(storage_path=temp_storage)

        assert manager.storage_path == temp_storage


class TestTaskManagerStartEnd:
    """Tests for TaskManager start_task and end_task."""

    def test_start_task(self, temp_storage: Path) -> None:
        """start_task() should create and return a marker."""
        manager = TaskManager(storage_path=temp_storage)

        marker = manager.start_task("Install plugin", session_id="session-123")

        assert marker.name == "Install plugin"
        assert marker.marker_type == "start"
        assert marker.session_id == "session-123"
        assert manager.current_task == "Install plugin"

    def test_end_task(self, temp_storage: Path) -> None:
        """end_task() should create an end marker."""
        manager = TaskManager(storage_path=temp_storage)
        manager.start_task("Install plugin", session_id="session-123")

        marker = manager.end_task(session_id="session-123")

        assert marker is not None
        assert marker.name == "Install plugin"
        assert marker.marker_type == "end"
        assert manager.current_task is None

    def test_end_task_without_start(self, temp_storage: Path) -> None:
        """end_task() without active task should return None."""
        manager = TaskManager(storage_path=temp_storage)

        marker = manager.end_task(session_id="session-123")

        assert marker is None

    def test_start_task_auto_ends_previous(self, temp_storage: Path) -> None:
        """Starting a new task should auto-end the previous one."""
        manager = TaskManager(storage_path=temp_storage)

        manager.start_task("Task 1", session_id="session-123")
        manager.start_task("Task 2", session_id="session-123")

        assert manager.current_task == "Task 2"
        # Should have 3 markers: start1, end1, start2
        session_markers = [m for m in manager.markers if m.session_id == "session-123"]
        assert len(session_markers) == 3


class TestTaskManagerPersistence:
    """Tests for TaskManager persistence."""

    def test_markers_persisted_to_disk(self, temp_storage: Path) -> None:
        """Markers should be saved to disk."""
        manager = TaskManager(storage_path=temp_storage)

        manager.start_task("Test task", session_id="session-456")
        manager.end_task(session_id="session-456")

        # Check file exists
        file_path = temp_storage / "session-456.json"
        assert file_path.exists()

        # Check content
        with open(file_path) as f:
            data = json.load(f)

        assert data["session_id"] == "session-456"
        assert len(data["markers"]) == 2

    def test_load_markers(self, temp_storage: Path) -> None:
        """Markers should be loadable from disk."""
        # Create markers file manually
        file_path = temp_storage / "session-789.json"
        data = {
            "session_id": "session-789",
            "markers": [
                {
                    "timestamp": "2025-12-28T10:00:00+00:00",
                    "name": "Loaded task",
                    "type": "start",
                    "session_id": "session-789",
                },
                {
                    "timestamp": "2025-12-28T10:05:00+00:00",
                    "name": "Loaded task",
                    "type": "end",
                    "session_id": "session-789",
                },
            ],
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        manager = TaskManager(storage_path=temp_storage)
        markers = manager._load_markers("session-789")

        assert len(markers) == 2
        assert markers[0].name == "Loaded task"
        assert markers[0].marker_type == "start"
        assert markers[1].marker_type == "end"

    def test_load_nonexistent_session(self, temp_storage: Path) -> None:
        """Loading nonexistent session should return empty list."""
        manager = TaskManager(storage_path=temp_storage)

        markers = manager._load_markers("nonexistent-session")

        assert markers == []


class TestTaskManagerClear:
    """Tests for TaskManager clear_markers."""

    def test_clear_specific_session(self, temp_storage: Path) -> None:
        """clear_markers() should remove markers for specific session."""
        manager = TaskManager(storage_path=temp_storage)
        manager.start_task("Task A", session_id="session-a")
        manager.end_task(session_id="session-a")
        manager.start_task("Task B", session_id="session-b")
        manager.end_task(session_id="session-b")

        manager.clear_markers(session_id="session-a")

        # session-a markers should be gone
        markers_a = manager._load_markers("session-a")
        assert len(markers_a) == 0

        # session-b markers should remain
        file_b = temp_storage / "session-b.json"
        assert file_b.exists()

    def test_clear_all(self, temp_storage: Path) -> None:
        """clear_markers() without session_id should clear memory."""
        manager = TaskManager(storage_path=temp_storage)
        manager.start_task("Task", session_id="session-1")

        manager.clear_markers()

        assert len(manager.markers) == 0
        assert manager.current_task is None


class TestTaskManagerListSessions:
    """Tests for TaskManager list_sessions_with_markers."""

    def test_list_empty(self, temp_storage: Path) -> None:
        """Empty storage should return empty list."""
        manager = TaskManager(storage_path=temp_storage)

        sessions = manager.list_sessions_with_markers()

        assert sessions == []

    def test_list_sessions(self, temp_storage: Path) -> None:
        """Should list all sessions with marker files."""
        manager = TaskManager(storage_path=temp_storage)
        manager.start_task("Task 1", session_id="session-alpha")
        manager.end_task(session_id="session-alpha")
        manager.start_task("Task 2", session_id="session-beta")
        manager.end_task(session_id="session-beta")

        sessions = manager.list_sessions_with_markers()

        assert len(sessions) == 2
        assert "session-alpha" in sessions
        assert "session-beta" in sessions


class TestTaskManagerGetTasks:
    """Tests for TaskManager.get_tasks() grouping."""

    def test_get_tasks_empty(self, temp_storage: Path, sample_session: Session) -> None:
        """get_tasks() with no markers should return empty list."""
        manager = TaskManager(storage_path=temp_storage)

        summaries = manager.get_tasks(sample_session)

        assert summaries == []

    def test_get_tasks_groups_calls(self, temp_storage: Path, sample_session: Session) -> None:
        """get_tasks() should group calls between markers."""
        # Get the call timestamps from the session
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.index)

        # Create markers that span the calls
        manager = TaskManager(storage_path=temp_storage)

        # Create marker files directly
        start_time = all_calls[0].timestamp
        end_time = all_calls[-1].timestamp
        data = {
            "session_id": sample_session.session_id,
            "markers": [
                {
                    "timestamp": start_time.isoformat(),
                    "name": "Full session task",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": end_time.isoformat(),
                    "name": "Full session task",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
            ],
        }
        file_path = temp_storage / f"{sample_session.session_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        summaries = manager.get_tasks(sample_session)

        assert len(summaries) == 1
        summary = summaries[0]
        assert summary.name == "Full session task"
        assert summary.call_count == 4
        assert summary.total_tokens > 0

    def test_get_tasks_bucket_breakdown(self, temp_storage: Path, sample_session: Session) -> None:
        """get_tasks() should include bucket breakdown per task."""
        # Get all calls for timing
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.index)

        manager = TaskManager(storage_path=temp_storage)

        # Create marker file
        start_time = all_calls[0].timestamp
        end_time = all_calls[-1].timestamp
        data = {
            "session_id": sample_session.session_id,
            "markers": [
                {
                    "timestamp": start_time.isoformat(),
                    "name": "Test task",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": end_time.isoformat(),
                    "name": "Test task",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
            ],
        }
        file_path = temp_storage / f"{sample_session.session_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        summaries = manager.get_tasks(sample_session)

        assert len(summaries) == 1
        summary = summaries[0]

        # Check buckets exist
        assert BucketName.DRIFT in summary.buckets
        assert BucketName.REDUNDANT in summary.buckets
        assert BucketName.STATE_SERIALIZATION in summary.buckets
        assert BucketName.TOOL_DISCOVERY in summary.buckets

        # Our sample session should have:
        # - wpnav_introspect -> tool_discovery
        # - wpnav_get_page (2x, one redundant) -> state_serialization + redundant
        # - Read -> drift
        total_percentage = sum(b.percentage for b in summary.buckets.values())
        assert 99.9 <= total_percentage <= 100.1  # Should sum to ~100%


class TestTaskManagerIntegration:
    """Integration tests for TaskManager workflow."""

    def test_full_workflow(self, temp_storage: Path, sample_session: Session) -> None:
        """Test complete workflow: start -> end -> get_tasks."""
        manager = TaskManager(storage_path=temp_storage)

        # Simulate marking tasks (in practice, this happens during session)
        # Get timestamps from session calls
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.index)

        # Create markers manually with call-aligned timestamps
        manager.markers = [
            TaskMarker(
                timestamp=all_calls[0].timestamp,
                name="Setup phase",
                marker_type="start",
                session_id=sample_session.session_id,
            ),
            TaskMarker(
                timestamp=all_calls[1].timestamp,
                name="Setup phase",
                marker_type="end",
                session_id=sample_session.session_id,
            ),
        ]
        manager._save_markers(sample_session.session_id)

        # Load and analyze
        summaries = manager.get_tasks(sample_session)

        assert len(summaries) == 1
        assert summaries[0].name == "Setup phase"
        assert summaries[0].total_tokens > 0


# =============================================================================
# Task Boundary Edge Cases (task-247.10)
# =============================================================================


class TestTaskBoundaryEdgeCases:
    """Edge case tests for task boundary handling (task-247.10)."""

    def test_calls_before_first_task(self, temp_storage: Path, sample_session: Session) -> None:
        """Calls before first start marker are excluded from summaries."""
        # Get all calls sorted by timestamp
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.timestamp)

        # Create marker that starts AFTER the first call
        # Call 0 is at 10:00, Call 1 is at 10:05
        # Start task at 10:05 (after call 0)
        manager = TaskManager(storage_path=temp_storage)

        data = {
            "session_id": sample_session.session_id,
            "markers": [
                {
                    "timestamp": all_calls[1].timestamp.isoformat(),  # 10:05
                    "name": "Late start task",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": all_calls[-1].timestamp.isoformat(),  # 10:15
                    "name": "Late start task",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
            ],
        }
        file_path = temp_storage / f"{sample_session.session_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        summaries = manager.get_tasks(sample_session)

        assert len(summaries) == 1
        summary = summaries[0]
        # Call 0 (10:00) should be excluded since task starts at 10:05
        assert 0 not in summary.call_indices
        # Other calls should be included
        assert summary.call_count >= 1

    def test_calls_after_last_task(self, temp_storage: Path, sample_session: Session) -> None:
        """Calls after last end marker are excluded from summaries."""
        # Get all calls sorted by timestamp
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.timestamp)

        # Create marker that ends BEFORE the last call
        # Calls are at 10:00, 10:05, 10:10, 10:15
        # End task at 10:10 (before call 3 at 10:15)
        manager = TaskManager(storage_path=temp_storage)

        data = {
            "session_id": sample_session.session_id,
            "markers": [
                {
                    "timestamp": all_calls[0].timestamp.isoformat(),  # 10:00
                    "name": "Early end task",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": all_calls[2].timestamp.isoformat(),  # 10:10
                    "name": "Early end task",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
            ],
        }
        file_path = temp_storage / f"{sample_session.session_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        summaries = manager.get_tasks(sample_session)

        assert len(summaries) == 1
        summary = summaries[0]
        # Call 3 (10:15) should be excluded since task ends at 10:10
        assert 3 not in summary.call_indices
        # Earlier calls should be included
        assert summary.call_count >= 1

    def test_overlapping_markers(self, temp_storage: Path, sample_session: Session) -> None:
        """Multiple tasks with overlapping time windows create separate summaries."""
        # Get all calls sorted by timestamp
        all_calls = []
        for server_session in sample_session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.timestamp)

        # Create two tasks that overlap in time
        # Task A: 10:00 - 10:10 (covers calls 0, 1, 2)
        # Task B: 10:05 - 10:15 (covers calls 1, 2, 3)
        manager = TaskManager(storage_path=temp_storage)

        data = {
            "session_id": sample_session.session_id,
            "markers": [
                {
                    "timestamp": all_calls[0].timestamp.isoformat(),  # 10:00
                    "name": "Task A",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": all_calls[2].timestamp.isoformat(),  # 10:10
                    "name": "Task A",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": all_calls[1].timestamp.isoformat(),  # 10:05
                    "name": "Task B",
                    "type": "start",
                    "session_id": sample_session.session_id,
                },
                {
                    "timestamp": all_calls[-1].timestamp.isoformat(),  # 10:15
                    "name": "Task B",
                    "type": "end",
                    "session_id": sample_session.session_id,
                },
            ],
        }
        file_path = temp_storage / f"{sample_session.session_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        summaries = manager.get_tasks(sample_session)

        # Should have 2 separate task summaries
        assert len(summaries) == 2

        # Find Task A and Task B
        task_a = next((s for s in summaries if s.name == "Task A"), None)
        task_b = next((s for s in summaries if s.name == "Task B"), None)

        assert task_a is not None, "Task A should exist"
        assert task_b is not None, "Task B should exist"

        # Both tasks should have calls
        assert task_a.call_count >= 1
        assert task_b.call_count >= 1

        # Verify no errors in bucket calculations
        for summary in summaries:
            total_percentage = sum(b.percentage for b in summary.buckets.values())
            assert (
                99.9 <= total_percentage <= 100.1
            ), f"Bucket percentages should sum to ~100%, got {total_percentage}"
