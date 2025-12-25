"""Tests for LiveTracker JSONL streaming functionality."""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from token_audit.base_tracker import SCHEMA_VERSION
from token_audit.server.live_tracker import LiveSession, LiveTracker
from token_audit.storage import StreamingStorage


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage(tmp_path: Path) -> StreamingStorage:
    """Create a StreamingStorage with a temporary directory."""
    return StreamingStorage(base_dir=tmp_path)


@pytest.fixture
def tracker(temp_storage: StreamingStorage) -> LiveTracker:
    """Create a LiveTracker with temporary storage."""
    return LiveTracker(storage=temp_storage)


# =============================================================================
# LiveSession Tests
# =============================================================================


class TestLiveSession:
    """Tests for the LiveSession dataclass."""

    def test_live_session_creation(self) -> None:
        """Test creating a LiveSession with required fields."""
        now = datetime.now()
        session = LiveSession(
            session_id="test123",
            platform="claude_code",
            project="my-project",
            started_at=now,
        )

        assert session.session_id == "test123"
        assert session.platform == "claude_code"
        assert session.project == "my-project"
        assert session.started_at == now
        assert session.ended_at is None
        assert session.file_path is None

    def test_live_session_default_metrics(self) -> None:
        """Test LiveSession initializes with zero metrics."""
        session = LiveSession(
            session_id="abc",
            platform="claude_code",
            project=None,
            started_at=datetime.now(),
        )

        assert session.total_input_tokens == 0
        assert session.total_output_tokens == 0
        assert session.total_cache_read_tokens == 0
        assert session.total_cache_write_tokens == 0
        assert session.total_cost_usd == 0.0
        assert session.call_count == 0
        assert session.tool_calls == {}
        assert session.server_calls == {}
        assert session.model_usage == {}
        assert session.smells == []

    def test_live_session_to_dict(self) -> None:
        """Test LiveSession serialization to dictionary."""
        now = datetime.now()
        session = LiveSession(
            session_id="xyz789",
            platform="codex_cli",
            project="test-proj",
            started_at=now,
            file_path=Path("/tmp/test.jsonl"),
        )
        session.total_input_tokens = 100
        session.total_output_tokens = 200
        session.tool_calls = {"Read": 5}

        result = session.to_dict()

        assert result["session_id"] == "xyz789"
        assert result["platform"] == "codex_cli"
        assert result["project"] == "test-proj"
        assert result["started_at"] == now.isoformat()
        assert result["ended_at"] is None
        assert result["file_path"] == "/tmp/test.jsonl"
        assert result["total_input_tokens"] == 100
        assert result["total_output_tokens"] == 200
        assert result["tool_calls"] == {"Read": 5}

    def test_live_session_to_dict_with_ended_at(self) -> None:
        """Test serialization includes ended_at when set."""
        start = datetime.now()
        end = datetime.now()
        session = LiveSession(
            session_id="test",
            platform="claude_code",
            project=None,
            started_at=start,
            ended_at=end,
        )

        result = session.to_dict()
        assert result["ended_at"] == end.isoformat()


# =============================================================================
# LiveTracker Initialization Tests
# =============================================================================


class TestLiveTrackerInit:
    """Tests for LiveTracker initialization."""

    def test_init_with_storage(self, temp_storage: StreamingStorage) -> None:
        """Test initializing with provided storage."""
        tracker = LiveTracker(storage=temp_storage)
        assert tracker._storage is temp_storage
        assert tracker._active_session is None

    def test_init_without_storage(self) -> None:
        """Test initializing creates default storage."""
        tracker = LiveTracker()
        assert tracker._storage is not None
        assert isinstance(tracker._storage, StreamingStorage)
        assert tracker._active_session is None

    def test_has_active_session_false_initially(self, tracker: LiveTracker) -> None:
        """Test has_active_session returns False initially."""
        assert tracker.has_active_session is False

    def test_active_session_none_initially(self, tracker: LiveTracker) -> None:
        """Test active_session property returns None initially."""
        assert tracker.active_session is None


# =============================================================================
# Session Lifecycle Tests
# =============================================================================


class TestSessionLifecycle:
    """Tests for session start/stop lifecycle."""

    def test_start_session_creates_session(self, tracker: LiveTracker) -> None:
        """Test start_session creates an active session."""
        session = tracker.start_session(platform="claude_code", project="test")

        assert session is not None
        assert session.session_id is not None
        assert len(session.session_id) == 8  # Short UUID
        assert session.platform == "claude_code"
        assert session.project == "test"
        assert session.started_at is not None
        assert session.file_path is not None

    def test_start_session_writes_start_event(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test start_session writes session_start event to JSONL."""
        session = tracker.start_session(platform="codex_cli")

        events = list(temp_storage.read_events(session.session_id))
        assert len(events) == 1

        start_event = events[0]
        assert start_event["type"] == "session_start"
        assert start_event["session_id"] == session.session_id
        assert start_event["platform"] == "codex_cli"
        assert "timestamp" in start_event

    def test_start_session_marks_active(self, tracker: LiveTracker) -> None:
        """Test start_session sets active session."""
        session = tracker.start_session(platform="claude_code")

        assert tracker.has_active_session is True
        assert tracker.active_session is session

    def test_start_session_fails_if_active(self, tracker: LiveTracker) -> None:
        """Test start_session raises error if session already active."""
        tracker.start_session(platform="claude_code")

        with pytest.raises(RuntimeError, match="Session already active"):
            tracker.start_session(platform="codex_cli")

    def test_stop_session_returns_session(self, tracker: LiveTracker) -> None:
        """Test stop_session returns the stopped session."""
        tracker.start_session(platform="claude_code", project="myproj")

        session = tracker.stop_session()

        assert session is not None
        assert session.platform == "claude_code"
        assert session.project == "myproj"
        assert session.ended_at is not None

    def test_stop_session_clears_active(self, tracker: LiveTracker) -> None:
        """Test stop_session clears active session."""
        tracker.start_session(platform="claude_code")
        tracker.stop_session()

        assert tracker.has_active_session is False
        assert tracker.active_session is None

    def test_stop_session_when_none_returns_none(self, tracker: LiveTracker) -> None:
        """Test stop_session returns None when no session active."""
        result = tracker.stop_session()
        assert result is None

    def test_stop_session_creates_json_file(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test stop_session converts JSONL to JSON and moves file."""
        session = tracker.start_session(platform="claude_code")
        session_id = session.session_id

        # Verify JSONL exists in active directory
        assert temp_storage.has_active_session(session_id)

        stopped = tracker.stop_session()

        # JSONL should be cleaned up
        assert not temp_storage.has_active_session(session_id)

        # JSON file should exist in completed directory
        assert stopped.file_path is not None
        assert stopped.file_path.exists()
        assert stopped.file_path.suffix == ".json"

        # Verify JSON content
        with open(stopped.file_path) as f:
            data = json.load(f)

        assert data["session_id"] == session_id
        assert data["platform"] == "claude_code"
        assert "events" in data
        assert len(data["events"]) >= 2  # session_start + session_end


# =============================================================================
# Event Recording Tests
# =============================================================================


class TestRecordToolCall:
    """Tests for record_tool_call method."""

    def test_record_tool_call_basic(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test recording a basic tool call."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=50,
            tokens_out=200,
        )

        events = list(temp_storage.read_events(session.session_id))
        tool_event = [e for e in events if e["type"] == "tool_call"][0]

        assert tool_event["tool"] == "Read"
        assert tool_event["server"] == "builtin"
        assert tool_event["tokens_in"] == 50
        assert tool_event["tokens_out"] == 200

    def test_record_tool_call_updates_metrics(self, tracker: LiveTracker) -> None:
        """Test tool call updates in-memory metrics."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=500,
            cache_read=50,
            cache_write=30,
            cost_usd=0.01,
        )

        assert session.total_input_tokens == 100
        assert session.total_output_tokens == 500
        assert session.total_cache_read_tokens == 50
        assert session.total_cache_write_tokens == 30
        assert session.total_cost_usd == 0.01
        assert session.call_count == 1

    def test_record_tool_call_tracks_per_tool(self, tracker: LiveTracker) -> None:
        """Test tool calls are tracked per-tool."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(tool="Read", server="builtin")
        tracker.record_tool_call(tool="Read", server="builtin")
        tracker.record_tool_call(tool="Write", server="builtin")

        assert session.tool_calls == {"Read": 2, "Write": 1}

    def test_record_tool_call_tracks_per_server(self, tracker: LiveTracker) -> None:
        """Test tool calls are tracked per-server."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(tool="Read", server="builtin")
        tracker.record_tool_call(tool="mcp__zen__chat", server="zen")
        tracker.record_tool_call(tool="mcp__zen__debug", server="zen")

        assert session.server_calls == {"builtin": 1, "zen": 2}

    def test_record_tool_call_tracks_model_usage(self, tracker: LiveTracker) -> None:
        """Test tool calls track per-model usage."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=200,
            model="claude-sonnet-4-20250514",
            cost_usd=0.005,
        )
        tracker.record_tool_call(
            tool="Write",
            server="builtin",
            tokens_in=50,
            tokens_out=100,
            model="claude-sonnet-4-20250514",
            cost_usd=0.003,
        )

        assert "claude-sonnet-4-20250514" in session.model_usage
        model_stats = session.model_usage["claude-sonnet-4-20250514"]
        assert model_stats["tokens_in"] == 150
        assert model_stats["tokens_out"] == 300
        assert model_stats["calls"] == 2
        assert model_stats["cost_usd"] == pytest.approx(0.008)

    def test_record_tool_call_without_active_session(self, tracker: LiveTracker) -> None:
        """Test record_tool_call raises error without active session."""
        with pytest.raises(RuntimeError, match="No active session"):
            tracker.record_tool_call(tool="Read", server="builtin")

    def test_record_tool_call_with_extra_kwargs(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test extra kwargs are included in event."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            file_path="/test/file.py",
            custom_field="value",
        )

        events = list(temp_storage.read_events(session.session_id))
        tool_event = [e for e in events if e["type"] == "tool_call"][0]

        assert tool_event["file_path"] == "/test/file.py"
        assert tool_event["custom_field"] == "value"


class TestRecordSmell:
    """Tests for record_smell method."""

    def test_record_smell_basic(self, tracker: LiveTracker, temp_storage: StreamingStorage) -> None:
        """Test recording a basic smell."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_smell(
            pattern="CHATTY",
            severity="medium",
            tool="mcp__zen__chat",
            description="5 calls in 30 seconds",
        )

        events = list(temp_storage.read_events(session.session_id))
        smell_event = [e for e in events if e["type"] == "smell_detected"][0]

        assert smell_event["pattern"] == "CHATTY"
        assert smell_event["severity"] == "medium"
        assert smell_event["tool"] == "mcp__zen__chat"
        assert smell_event["description"] == "5 calls in 30 seconds"

    def test_record_smell_updates_in_memory(self, tracker: LiveTracker) -> None:
        """Test smell recording updates in-memory list."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_smell(
            pattern="LOW_CACHE_HIT",
            severity="high",
            description="Cache hit ratio below 0.5",
        )

        assert len(session.smells) == 1
        smell = session.smells[0]
        assert smell["pattern"] == "LOW_CACHE_HIT"
        assert smell["severity"] == "high"

    def test_record_smell_with_evidence(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test smell with evidence kwargs."""
        session = tracker.start_session(platform="claude_code")

        tracker.record_smell(
            pattern="CHATTY",
            severity="medium",
            call_count=10,
            window_seconds=60,
        )

        events = list(temp_storage.read_events(session.session_id))
        smell_event = [e for e in events if e["type"] == "smell_detected"][0]

        assert smell_event["evidence"]["call_count"] == 10
        assert smell_event["evidence"]["window_seconds"] == 60

    def test_record_smell_without_active_session(self, tracker: LiveTracker) -> None:
        """Test record_smell raises error without active session."""
        with pytest.raises(RuntimeError, match="No active session"):
            tracker.record_smell(pattern="TEST", severity="low")


class TestAppendEvent:
    """Tests for the low-level append_event method."""

    def test_append_event_adds_timestamp(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test append_event adds timestamp if missing."""
        session = tracker.start_session(platform="claude_code")

        tracker.append_event({"type": "custom", "data": "test"})

        events = list(temp_storage.read_events(session.session_id))
        custom_event = [e for e in events if e["type"] == "custom"][0]

        assert "timestamp" in custom_event

    def test_append_event_preserves_existing_timestamp(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test append_event preserves existing timestamp."""
        session = tracker.start_session(platform="claude_code")

        tracker.append_event(
            {
                "type": "custom",
                "timestamp": "2025-01-01T00:00:00",
            }
        )

        events = list(temp_storage.read_events(session.session_id))
        custom_event = [e for e in events if e["type"] == "custom"][0]

        assert custom_event["timestamp"] == "2025-01-01T00:00:00"

    def test_append_event_without_active_session(self, tracker: LiveTracker) -> None:
        """Test append_event raises error without active session."""
        with pytest.raises(RuntimeError, match="No active session"):
            tracker.append_event({"type": "test"})


# =============================================================================
# Get Metrics Tests
# =============================================================================


class TestGetMetrics:
    """Tests for get_metrics method."""

    def test_get_metrics_basic(self, tracker: LiveTracker) -> None:
        """Test get_metrics returns expected structure."""
        tracker.start_session(platform="claude_code", project="test-proj")

        metrics = tracker.get_metrics()

        assert "session_id" in metrics
        assert metrics["platform"] == "claude_code"
        assert metrics["project"] == "test-proj"
        assert "started_at" in metrics
        assert "duration_minutes" in metrics
        assert "tokens" in metrics
        assert "cost_usd" in metrics
        assert "rates" in metrics
        assert "cache" in metrics
        assert "call_count" in metrics
        assert "tool_count" in metrics

    def test_get_metrics_token_breakdown(self, tracker: LiveTracker) -> None:
        """Test get_metrics includes token breakdown."""
        tracker.start_session(platform="claude_code")
        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=200,
            cache_read=50,
            cache_write=25,
        )

        metrics = tracker.get_metrics()

        assert metrics["tokens"]["input"] == 100
        assert metrics["tokens"]["output"] == 200
        assert metrics["tokens"]["cache_read"] == 50
        assert metrics["tokens"]["cache_write"] == 25
        assert metrics["tokens"]["total"] == 350  # in + out + cache_read

    def test_get_metrics_rates(self, tracker: LiveTracker) -> None:
        """Test get_metrics calculates rates."""
        tracker.start_session(platform="claude_code")
        tracker.record_tool_call(tool="Read", server="builtin", tokens_in=1000)

        metrics = tracker.get_metrics()

        assert "tokens_per_min" in metrics["rates"]
        assert "calls_per_min" in metrics["rates"]
        assert "duration_minutes" in metrics  # Top level, not in rates
        # Duration should be >= 0 (might be 0 if test runs very fast)
        assert metrics["duration_minutes"] >= 0

    def test_get_metrics_cache_ratio(self, tracker: LiveTracker) -> None:
        """Test get_metrics calculates cache hit ratio."""
        tracker.start_session(platform="claude_code")
        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=100,  # 50% cache hit
        )

        metrics = tracker.get_metrics()

        assert metrics["cache"]["hit_ratio"] == 0.5
        assert metrics["cache"]["savings_tokens"] == 100

    def test_get_metrics_includes_smells(self, tracker: LiveTracker) -> None:
        """Test get_metrics includes detected smells."""
        tracker.start_session(platform="claude_code")
        tracker.record_smell(pattern="CHATTY", severity="medium")
        tracker.record_smell(pattern="LOW_CACHE", severity="high")

        metrics = tracker.get_metrics()

        assert len(metrics["smells"]) == 2

    def test_get_metrics_includes_tool_breakdown(self, tracker: LiveTracker) -> None:
        """Test get_metrics includes per-tool breakdown."""
        tracker.start_session(platform="claude_code")
        tracker.record_tool_call(tool="Read", server="builtin")
        tracker.record_tool_call(tool="Read", server="builtin")
        tracker.record_tool_call(tool="Write", server="builtin")

        metrics = tracker.get_metrics()

        assert metrics["tool_calls"] == {"Read": 2, "Write": 1}
        assert metrics["tool_count"] == 2

    def test_get_metrics_includes_model_usage(self, tracker: LiveTracker) -> None:
        """Test get_metrics includes per-model breakdown."""
        tracker.start_session(platform="claude_code")
        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
        )

        metrics = tracker.get_metrics()

        assert "claude-sonnet-4-20250514" in metrics["model_usage"]

    def test_get_metrics_without_active_session(self, tracker: LiveTracker) -> None:
        """Test get_metrics raises error without active session."""
        with pytest.raises(RuntimeError, match="No active session"):
            tracker.get_metrics()


# =============================================================================
# Get Session Tests
# =============================================================================


class TestGetSession:
    """Tests for get_session method."""

    def test_get_session_returns_active(self, tracker: LiveTracker) -> None:
        """Test get_session returns active session when no ID provided."""
        session = tracker.start_session(platform="claude_code")

        result = tracker.get_session()
        assert result is session

    def test_get_session_by_id_returns_active(self, tracker: LiveTracker) -> None:
        """Test get_session with ID returns matching active session."""
        session = tracker.start_session(platform="claude_code")

        result = tracker.get_session(session.session_id)
        assert result is session

    def test_get_session_wrong_id_returns_none(self, tracker: LiveTracker) -> None:
        """Test get_session with wrong ID returns None."""
        tracker.start_session(platform="claude_code")

        result = tracker.get_session("nonexistent-id")
        assert result is None

    def test_get_session_no_active_returns_none(self, tracker: LiveTracker) -> None:
        """Test get_session returns None when no session active."""
        result = tracker.get_session()
        assert result is None


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_removes_session(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test cleanup removes active session."""
        session = tracker.start_session(platform="claude_code")
        session_id = session.session_id

        tracker.cleanup()

        assert tracker.has_active_session is False
        assert not temp_storage.has_active_session(session_id)

    def test_cleanup_when_no_session(self, tracker: LiveTracker) -> None:
        """Test cleanup is safe when no session active."""
        tracker.cleanup()  # Should not raise
        assert tracker.has_active_session is False


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety of LiveTracker."""

    def test_concurrent_tool_calls(self, tracker: LiveTracker) -> None:
        """Test concurrent tool call recording is thread-safe."""
        session = tracker.start_session(platform="claude_code")
        errors: list = []

        def record_calls() -> None:
            try:
                for i in range(10):
                    tracker.record_tool_call(
                        tool=f"Tool{i}",
                        server="builtin",
                        tokens_in=10,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert session.call_count == 50  # 5 threads * 10 calls
        assert session.total_input_tokens == 500

    def test_concurrent_smell_recording(self, tracker: LiveTracker) -> None:
        """Test concurrent smell recording is thread-safe."""
        session = tracker.start_session(platform="claude_code")
        errors: list = []

        def record_smells() -> None:
            try:
                for i in range(10):
                    tracker.record_smell(
                        pattern=f"PATTERN{i}",
                        severity="medium",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_smells) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(session.smells) == 50


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full session lifecycle."""

    def test_full_session_lifecycle(
        self, tracker: LiveTracker, temp_storage: StreamingStorage
    ) -> None:
        """Test complete session lifecycle with all event types."""
        # Start session
        session = tracker.start_session(platform="claude_code", project="integration-test")

        # Record some tool calls
        tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=50,
            tokens_out=500,
            model="claude-sonnet-4-20250514",
        )
        tracker.record_tool_call(
            tool="mcp__zen__chat",
            server="zen",
            tokens_in=200,
            tokens_out=1000,
            cache_read=100,
        )

        # Record a smell
        tracker.record_smell(
            pattern="HIGH_TOKEN_RATE",
            severity="high",
            tool="mcp__zen__chat",
            description="Token consumption exceeds threshold",
        )

        # Get metrics mid-session
        metrics = tracker.get_metrics()
        assert metrics["call_count"] == 2
        assert metrics["tokens"]["input"] == 250
        assert len(metrics["smells"]) == 1

        # Stop session
        stopped = tracker.stop_session()

        # Verify final JSON
        assert stopped.file_path.exists()
        with open(stopped.file_path) as f:
            data = json.load(f)

        assert data["session_id"] == session.session_id
        assert data["platform"] == "claude_code"
        assert data["project"] == "integration-test"
        assert data["token_usage"]["input_tokens"] == 250
        assert data["token_usage"]["output_tokens"] == 1500
        assert len(data["smells"]) == 1
        assert len(data["events"]) == 5  # start + 2 tools + 1 smell + end

    def test_session_persists_after_stop(self, tracker: LiveTracker, tmp_path: Path) -> None:
        """Test session data is fully persisted after stop."""
        session = tracker.start_session(platform="codex_cli")
        tracker.record_tool_call(tool="shell", server="builtin", tokens_in=100)

        stopped = tracker.stop_session()

        # Verify file exists and can be loaded
        assert stopped.file_path.exists()
        with open(stopped.file_path) as f:
            data = json.load(f)

        # Verify schema version
        assert data["_file"]["schema_version"] == SCHEMA_VERSION
        assert data["_file"]["source"] == "token-audit-server"
