#!/usr/bin/env python3
"""
Test suite for base_tracker module

Tests BaseTracker abstract class and shared functionality.
"""

import pytest
from datetime import datetime
from pathlib import Path
from token_audit.base_tracker import (
    BaseTracker,
    Session,
    ServerSession,
    ToolStats,
    Call,
    TokenUsage,
    MCPToolCalls,
    SCHEMA_VERSION,
    # v1.5.0: Insight Layer
    Smell,
    DataQuality,
)


# ============================================================================
# Concrete Test Implementation of BaseTracker
# ============================================================================


class ConcreteTestTracker(BaseTracker):
    """Concrete implementation of BaseTracker for testing"""

    def __init__(self, project: str = "test-project", platform: str = "test-platform"):
        super().__init__(project, platform)
        self.events = []

    def start_tracking(self) -> None:
        """Test implementation - does nothing"""
        pass

    def parse_event(self, event_data):
        """Test implementation - returns None"""
        return None

    def get_platform_metadata(self):
        """Test implementation - returns test metadata"""
        return {"test_key": "test_value"}


# ============================================================================
# Data Structure Tests
# ============================================================================


class TestDataStructures:
    """Tests for core data structures (v1.0.4 schema)"""

    def test_call_creation(self) -> None:
        """Test Call dataclass creation (v1.0.4 - no schema_version on Call)"""
        call = Call(
            tool_name="mcp__zen__chat",
            server="zen",
            index=1,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        assert call.tool_name == "mcp__zen__chat"
        assert call.server == "zen"  # v1.0.4: server name on Call
        assert call.index == 1  # v1.0.4: sequential index
        assert call.input_tokens == 100
        assert call.output_tokens == 50
        assert call.total_tokens == 150
        # v1.0.4: schema_version removed from Call (only at session level)

    def test_call_to_dict(self) -> None:
        """Test Call to_dict conversion (v1.0.4 format)"""
        from datetime import timezone

        timestamp = datetime(2025, 11, 24, 10, 30, 0, tzinfo=timezone.utc)
        call = Call(
            tool_name="mcp__zen__chat",
            server="zen",
            index=1,
            timestamp=timestamp,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        data = call.to_dict()

        # v1.0.4: uses "tool" instead of "tool_name"
        assert data["tool"] == "mcp__zen__chat"
        assert data["server"] == "zen"
        assert data["index"] == 1
        assert data["input_tokens"] == 100
        # v1.0.4: ISO 8601 with timezone offset
        assert "2025-11-24T10:30:00" in data["timestamp"]

    def test_call_to_dict_v1_0(self) -> None:
        """Test Call to_dict_v1_0 for backward compatibility"""
        timestamp = datetime(2025, 11, 24, 10, 30, 0)
        call = Call(
            tool_name="mcp__zen__chat",
            timestamp=timestamp,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        data = call.to_dict_v1_0()

        # v1.0.0 format includes schema_version and tool_name
        assert data["schema_version"] == "1.0.0"
        assert data["tool_name"] == "mcp__zen__chat"
        assert data["input_tokens"] == 100

    def test_tool_stats_creation(self) -> None:
        """Test ToolStats dataclass creation (v1.0.4 - no schema_version)"""
        stats = ToolStats(calls=5, total_tokens=1000, avg_tokens=200.0)

        assert stats.calls == 5
        assert stats.total_tokens == 1000
        assert stats.avg_tokens == 200.0
        # v1.0.4: schema_version removed from ToolStats

    def test_tool_stats_to_dict(self) -> None:
        """Test ToolStats to_dict with call history (v1.0.4)"""
        call = Call(tool_name="test", server="test-server", index=1, total_tokens=100)
        stats = ToolStats(calls=1, call_history=[call])

        data = stats.to_dict()

        assert data["calls"] == 1
        assert len(data["call_history"]) == 1
        # v1.0.4: uses "tool" instead of "tool_name"
        assert data["call_history"][0]["tool"] == "test"
        assert data["call_history"][0]["server"] == "test-server"

    def test_tool_stats_to_dict_v1_0(self) -> None:
        """Test ToolStats to_dict_v1_0 for backward compatibility"""
        call = Call(tool_name="test", total_tokens=100)
        stats = ToolStats(calls=1, call_history=[call])

        data = stats.to_dict_v1_0()

        # v1.0.0 format includes schema_version
        assert data["schema_version"] == "1.0.0"
        assert data["calls"] == 1
        assert data["call_history"][0]["tool_name"] == "test"

    def test_server_session_creation(self) -> None:
        """Test ServerSession dataclass creation"""
        session = ServerSession(server="zen", total_calls=10, total_tokens=5000)

        assert session.server == "zen"
        assert session.total_calls == 10
        assert session.total_tokens == 5000

    def test_session_creation(self) -> None:
        """Test Session dataclass creation"""
        session = Session(project="test-project", platform="test-platform", session_id="test-123")

        assert session.project == "test-project"
        assert session.platform == "test-platform"
        assert session.session_id == "test-123"
        assert session.schema_version == SCHEMA_VERSION


# ============================================================================
# BaseTracker Initialization Tests
# ============================================================================


class TestBaseTrackerInitialization:
    """Tests for BaseTracker initialization"""

    def test_initialization(self) -> None:
        """Test BaseTracker initialization"""
        tracker = ConcreteTestTracker(project="my-project", platform="my-platform")

        assert tracker.project == "my-project"
        assert tracker.platform == "my-platform"
        assert tracker.session.project == "my-project"
        assert tracker.session.platform == "my-platform"

    def test_session_id_generation(self) -> None:
        """Test session ID generation"""
        tracker = ConcreteTestTracker()

        session_id = tracker.session_id

        # Should be in format: project-YYYY-MM-DDTHH-MM-SS
        assert session_id.startswith("test-project-")
        assert "T" in session_id

    def test_server_sessions_initialized(self) -> None:
        """Test server sessions dictionary initialized"""
        tracker = ConcreteTestTracker()

        assert isinstance(tracker.server_sessions, dict)
        assert len(tracker.server_sessions) == 0

    def test_content_hashes_initialized(self) -> None:
        """Test content hashes dictionary initialized"""
        tracker = ConcreteTestTracker()

        assert isinstance(tracker.content_hashes, dict)


# ============================================================================
# Normalization Tests
# ============================================================================


class TestNormalization:
    """Tests for tool name normalization"""

    def test_normalize_server_name_claude_code(self) -> None:
        """Test server name extraction (Claude Code format)"""
        tracker = ConcreteTestTracker()

        server = tracker.normalize_server_name("mcp__zen__chat")

        assert server == "zen"

    def test_normalize_server_name_codex_cli(self) -> None:
        """Test server name extraction (Codex CLI format with -mcp)"""
        tracker = ConcreteTestTracker()

        server = tracker.normalize_server_name("mcp__zen-mcp__chat")

        assert server == "zen"

    def test_normalize_server_name_hyphenated(self) -> None:
        """Test server name with hyphens"""
        tracker = ConcreteTestTracker()

        server = tracker.normalize_server_name("mcp__brave-search__web")

        assert server == "brave-search"

    def test_normalize_tool_name_passthrough(self) -> None:
        """Test tool name normalization (Claude Code format)"""
        tracker = ConcreteTestTracker()

        normalized = tracker.normalize_tool_name("mcp__zen__chat")

        assert normalized == "mcp__zen__chat"

    def test_normalize_tool_name_codex_cli(self) -> None:
        """Test tool name normalization (Codex CLI -mcp suffix)"""
        tracker = ConcreteTestTracker()

        normalized = tracker.normalize_tool_name("mcp__zen-mcp__chat")

        assert normalized == "mcp__zen__chat"

    def test_normalize_invalid_tool_name(self) -> None:
        """Test normalization warns on invalid tool name"""
        tracker = ConcreteTestTracker()

        with pytest.warns(UserWarning):
            server = tracker.normalize_server_name("Read")

        assert server == "unknown"


# ============================================================================
# Tool Call Recording Tests
# ============================================================================


class TestToolCallRecording:
    """Tests for recording tool calls"""

    def test_record_tool_call_basic(self) -> None:
        """Test recording a basic tool call"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=20,
            cache_read_tokens=500,
        )

        # Check session token usage
        assert tracker.session.token_usage.input_tokens == 100
        assert tracker.session.token_usage.output_tokens == 50
        assert tracker.session.token_usage.cache_created_tokens == 20
        assert tracker.session.token_usage.cache_read_tokens == 500
        assert tracker.session.token_usage.total_tokens == 670

    def test_record_tool_call_creates_server_session(self) -> None:
        """Test tool call creates server session"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        assert "zen" in tracker.server_sessions
        assert tracker.server_sessions["zen"].server == "zen"

    def test_record_tool_call_creates_tool_stats(self) -> None:
        """Test tool call creates tool stats"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        zen_session = tracker.server_sessions["zen"]
        assert "mcp__zen__chat" in zen_session.tools
        tool_stats = zen_session.tools["mcp__zen__chat"]
        assert tool_stats.calls == 1
        assert tool_stats.total_tokens == 150

    def test_record_multiple_tool_calls(self) -> None:
        """Test recording multiple tool calls"""
        tracker = ConcreteTestTracker()

        # First call
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        # Second call
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=200, output_tokens=100)

        tool_stats = tracker.server_sessions["zen"].tools["mcp__zen__chat"]
        assert tool_stats.calls == 2
        assert tool_stats.total_tokens == 450  # 150 + 300
        assert tool_stats.avg_tokens == 225.0  # 450 / 2

    def test_record_tool_call_normalizes_codex_name(self) -> None:
        """Test Codex CLI tool names are normalized"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen-mcp__chat", input_tokens=100, output_tokens=50  # Codex format
        )

        # Should be normalized to Claude Code format
        zen_session = tracker.server_sessions["zen"]
        assert "mcp__zen__chat" in zen_session.tools

    def test_record_tool_call_with_duration(self) -> None:
        """Test recording tool call with duration"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, duration_ms=1500
        )

        tool_stats = tracker.server_sessions["zen"].tools["mcp__zen__chat"]
        assert tool_stats.total_duration_ms == 1500
        assert tool_stats.avg_duration_ms == 1500.0
        assert tool_stats.max_duration_ms == 1500
        assert tool_stats.min_duration_ms == 1500

    def test_record_tool_call_duration_stats(self) -> None:
        """Test duration statistics across multiple calls"""
        tracker = ConcreteTestTracker()

        # Three calls with different durations
        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, duration_ms=1000
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, duration_ms=2000
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, duration_ms=1500
        )

        tool_stats = tracker.server_sessions["zen"].tools["mcp__zen__chat"]
        assert tool_stats.total_duration_ms == 4500
        assert tool_stats.avg_duration_ms == 1500.0
        assert tool_stats.max_duration_ms == 2000
        assert tool_stats.min_duration_ms == 1000

    def test_record_tool_call_with_content_hash(self) -> None:
        """Test recording tool call with content hash (duplicate detection)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, content_hash="abc123"
        )

        assert "abc123" in tracker.content_hashes
        assert len(tracker.content_hashes["abc123"]) == 1

    def test_cache_efficiency_calculation(self) -> None:
        """Test cache efficiency calculation"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=20,
            cache_read_tokens=500,
        )

        # cache_efficiency = cache_read / total_input
        # total_input = input_tokens + cache_created + cache_read = 100 + 20 + 500 = 620
        # 500 / 620 = 0.8064...
        assert tracker.session.token_usage.cache_efficiency > 0.80
        assert tracker.session.token_usage.cache_efficiency < 0.81


# ============================================================================
# Session Finalization Tests
# ============================================================================


class TestSessionFinalization:
    """Tests for session finalization"""

    def test_finalize_session_basic(self) -> None:
        """Test basic session finalization"""
        tracker = ConcreteTestTracker()

        # Record some calls
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        session = tracker.finalize_session()

        assert session.end_timestamp is not None
        assert session.duration_seconds is not None
        assert session.duration_seconds >= 0

    def test_finalize_session_mcp_summary(self) -> None:
        """Test MCP tool calls summary"""
        tracker = ConcreteTestTracker()

        # Record multiple calls
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)
        tracker.record_tool_call(tool_name="mcp__zen__debug", input_tokens=200, output_tokens=100)

        session = tracker.finalize_session()

        assert session.mcp_tool_calls.total_calls == 3
        assert session.mcp_tool_calls.unique_tools == 2
        assert "mcp__zen__chat (2 calls)" in session.mcp_tool_calls.most_called

    def test_finalize_session_server_sessions(self) -> None:
        """Test server sessions added to session"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        session = tracker.finalize_session()

        assert "zen" in session.server_sessions
        assert session.server_sessions["zen"].server == "zen"

    def test_analyze_redundancy(self) -> None:
        """Test redundancy analysis (duplicate detection)"""
        tracker = ConcreteTestTracker()

        # Same content hash = duplicate
        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, content_hash="abc123"
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            content_hash="abc123",  # Duplicate
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            content_hash="def456",  # Different
        )

        session = tracker.finalize_session()

        assert session.redundancy_analysis is not None
        assert session.redundancy_analysis["duplicate_calls"] == 1
        assert session.redundancy_analysis["potential_savings"] == 150

    def test_detect_anomalies_high_frequency(self) -> None:
        """Test anomaly detection for high frequency"""
        tracker = ConcreteTestTracker()

        # 15 calls (threshold is 10)
        for _ in range(15):
            tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        session = tracker.finalize_session()

        # Should detect high frequency anomaly
        assert len(session.anomalies) > 0
        anomaly = session.anomalies[0]
        assert anomaly["type"] == "high_frequency"
        assert anomaly["tool"] == "mcp__zen__chat"
        assert anomaly["calls"] == 15

    def test_detect_anomalies_high_avg_tokens(self) -> None:
        """Test anomaly detection for high average tokens"""
        tracker = ConcreteTestTracker()

        # 600K tokens (threshold is 500K - raised for Claude Code context accumulation)
        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep", input_tokens=400000, output_tokens=200000
        )

        session = tracker.finalize_session()

        # Should detect high avg tokens anomaly
        assert len(session.anomalies) > 0
        anomaly = session.anomalies[0]
        assert anomaly["type"] == "high_avg_tokens"
        assert anomaly["tool"] == "mcp__zen__thinkdeep"
        assert anomaly["avg_tokens"] == 600000


# ============================================================================
# Persistence Tests
# ============================================================================


class TestPersistence:
    """Tests for session persistence (v1.0.4 single-file format)"""

    def test_save_session(self, tmp_path) -> None:
        """Test saving session to disk (v1.0.4 format)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        tracker.finalize_session()
        tracker.save_session(tmp_path)

        # v1.0.4: session_dir points to date subdirectory
        assert tracker.session_dir is not None
        assert tracker.session_dir.exists()

        # v1.0.4: single file per session, named <project>-<timestamp>.json
        # File is in date subdirectory (session_dir)
        session_files = list(tracker.session_dir.glob("*.json"))
        assert len(session_files) == 1

        # v1.0.4: no more separate mcp-*.json files
        mcp_files = list(tracker.session_dir.glob("mcp-*.json"))
        assert len(mcp_files) == 0

        # Verify file contents
        import json

        with open(session_files[0]) as f:
            data = json.load(f)

        # v1.0.4: has _file header
        assert "_file" in data
        assert data["_file"]["schema_version"] == SCHEMA_VERSION
        assert data["_file"]["type"] == "token_audit_session"

        # v1.0.4: has session block
        assert "session" in data
        assert data["session"]["project"] == "test-project"
        assert data["session"]["platform"] == "test-platform"

        # v1.0.4: has flat tool_calls array
        assert "tool_calls" in data
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["tool"] == "mcp__zen__chat"


# ============================================================================
# Utility Methods Tests
# ============================================================================


class TestUtilityMethods:
    """Tests for utility methods"""

    def test_compute_content_hash(self) -> None:
        """Test content hash computation"""
        input_data = {"query": "test", "options": {"verbose": True}}

        hash1 = BaseTracker.compute_content_hash(input_data)
        hash2 = BaseTracker.compute_content_hash(input_data)

        # Same input = same hash
        assert hash1 == hash2

        # Different input = different hash
        input_data2 = {"query": "different"}
        hash3 = BaseTracker.compute_content_hash(input_data2)
        assert hash3 != hash1

    def test_handle_unrecognized_line(self) -> None:
        """Test unrecognized line handling"""
        tracker = ConcreteTestTracker()

        # Should not crash, just warn
        with pytest.warns(UserWarning):
            tracker.handle_unrecognized_line("invalid line format")


# ============================================================================
# Integration Tests
# ============================================================================


class TestBaseTrackerIntegration:
    """Integration tests for complete tracker workflow (v1.0.4)"""

    def test_complete_workflow(self, tmp_path) -> None:
        """Test complete tracking workflow (v1.0.4 format)"""
        import json

        tracker = ConcreteTestTracker()

        # Record multiple tools across multiple servers
        tracker.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, duration_ms=1000
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__debug", input_tokens=200, output_tokens=100, duration_ms=2000
        )
        tracker.record_tool_call(
            tool_name="mcp__brave-search__web", input_tokens=150, output_tokens=75, duration_ms=500
        )

        # Finalize and save
        session = tracker.finalize_session()
        tracker.save_session(tmp_path)

        # Verify session data
        assert session.mcp_tool_calls.total_calls == 3
        assert session.mcp_tool_calls.unique_tools == 3
        assert len(tracker.server_sessions) == 2  # zen + brave-search

        # v1.0.4: single session file in date subdirectory
        session_files = list(tracker.session_dir.glob("*.json"))
        assert len(session_files) == 1

        # Load and verify the session file
        with open(session_files[0]) as f:
            data = json.load(f)

        # v1.0.4: verify _file header
        assert data["_file"]["schema_version"] == SCHEMA_VERSION

        # v1.0.4: verify flat tool_calls array has all 3 calls
        assert len(data["tool_calls"]) == 3

        # Verify sequential indices
        indices = [c["index"] for c in data["tool_calls"]]
        assert indices == [1, 2, 3]

        # Verify all servers captured in tool_calls
        servers = {c["server"] for c in data["tool_calls"]}
        assert servers == {"zen", "brave-search"}

        # v1.0.4: verify mcp_summary
        assert data["mcp_summary"]["total_calls"] == 3
        assert data["mcp_summary"]["unique_tools"] == 3
        assert data["mcp_summary"]["unique_servers"] == 2
        assert set(data["mcp_summary"]["servers_used"]) == {"zen", "brave-search"}


# ============================================================================
# Cache Analysis Tests (task-47)
# ============================================================================


class TestCacheAnalysis:
    """Tests for cache analysis functionality (task-47.3, task-47.4)"""

    def test_tool_stats_cache_tracking(self) -> None:
        """Test per-tool cache token tracking (task-47.4)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=50000,
            cache_read_tokens=10000,
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=50,
            output_tokens=25,
            cache_created_tokens=5000,
            cache_read_tokens=100000,
        )

        # Check per-tool cache tracking
        thinkdeep_stats = tracker.server_sessions["zen"].tools["mcp__zen__thinkdeep"]
        assert thinkdeep_stats.cache_created_tokens == 50000
        assert thinkdeep_stats.cache_read_tokens == 10000

        chat_stats = tracker.server_sessions["zen"].tools["mcp__zen__chat"]
        assert chat_stats.cache_created_tokens == 5000
        assert chat_stats.cache_read_tokens == 100000

    def test_tool_stats_cache_aggregation(self) -> None:
        """Test cache tokens aggregate across multiple calls"""
        tracker = ConcreteTestTracker()

        # Multiple calls to same tool
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=50,
            output_tokens=25,
            cache_created_tokens=10000,
            cache_read_tokens=5000,
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=50,
            output_tokens=25,
            cache_created_tokens=15000,
            cache_read_tokens=8000,
        )

        tool_stats = tracker.server_sessions["zen"].tools["mcp__zen__chat"]
        assert tool_stats.cache_created_tokens == 25000  # 10000 + 15000
        assert tool_stats.cache_read_tokens == 13000  # 5000 + 8000

    def test_cache_analysis_efficient(self) -> None:
        """Test cache analysis with efficient caching (positive savings)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=10000,
            cache_read_tokens=200000,  # High cache read = efficient
        )

        # Set cache savings (positive = efficient)
        tracker.session.cache_savings_usd = 0.50

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(0.50)

        assert cache_analysis.status == "efficient"
        assert cache_analysis.creation_tokens == 10000
        assert cache_analysis.read_tokens == 200000
        assert cache_analysis.ratio == 20.0  # 200000 / 10000
        assert cache_analysis.net_savings_usd == 0.50
        assert "Cache saved" in cache_analysis.summary
        assert "efficiently" in cache_analysis.recommendation.lower()

    def test_cache_analysis_inefficient_no_reuse(self) -> None:
        """Test cache analysis with no reuse (high creation, zero read)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=100000,
            cache_read_tokens=0,  # No cache reuse
        )

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(-0.25)

        assert cache_analysis.status == "inefficient"
        assert cache_analysis.read_tokens == 0
        assert "no reuse" in cache_analysis.summary.lower()
        assert "batching" in cache_analysis.recommendation.lower()

    def test_cache_analysis_inefficient_low_reuse(self) -> None:
        """Test cache analysis with low reuse (ratio < 0.1)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=100000,
            cache_read_tokens=5000,  # Low reuse: 5000/100000 = 0.05
        )

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(-0.15)

        assert cache_analysis.status == "inefficient"
        assert cache_analysis.ratio < 0.1
        assert "low reuse" in cache_analysis.summary.lower()

    def test_cache_analysis_neutral(self) -> None:
        """Test cache analysis with no cache activity"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=0,
            cache_read_tokens=0,
        )

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(0.0)

        assert cache_analysis.status == "neutral"
        assert "No cache activity" in cache_analysis.summary
        assert cache_analysis.recommendation == ""

    def test_cache_analysis_top_creators(self) -> None:
        """Test cache analysis identifies top cache creators"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=80000,
            cache_read_tokens=10000,
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=50,
            output_tokens=25,
            cache_created_tokens=20000,
            cache_read_tokens=50000,
        )

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(-0.10)

        assert len(cache_analysis.top_cache_creators) == 2
        # thinkdeep should be first (80000 > 20000)
        assert cache_analysis.top_cache_creators[0]["tool"] == "mcp__zen__thinkdeep"
        assert cache_analysis.top_cache_creators[0]["tokens"] == 80000
        assert cache_analysis.top_cache_creators[0]["pct"] == 80.0

    def test_cache_analysis_top_readers(self) -> None:
        """Test cache analysis identifies top cache readers"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=50000,
            cache_read_tokens=10000,
        )
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=50,
            output_tokens=25,
            cache_created_tokens=5000,
            cache_read_tokens=90000,
        )

        session = tracker.finalize_session()
        cache_analysis = session._build_cache_analysis(0.20)

        assert len(cache_analysis.top_cache_readers) == 2
        # chat should be first (90000 > 10000)
        assert cache_analysis.top_cache_readers[0]["tool"] == "mcp__zen__chat"
        assert cache_analysis.top_cache_readers[0]["tokens"] == 90000
        assert cache_analysis.top_cache_readers[0]["pct"] == 90.0

    def test_cache_analysis_in_session_dict(self) -> None:
        """Test cache_analysis is included in session.to_dict() (task-47.3)"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            cache_created_tokens=10000,
            cache_read_tokens=50000,
        )

        tracker.session.cache_savings_usd = 0.15
        session = tracker.finalize_session()
        data = session.to_dict()

        # Verify cache_analysis section exists
        assert "cache_analysis" in data
        assert data["cache_analysis"]["status"] in ["efficient", "inefficient", "neutral"]
        assert "summary" in data["cache_analysis"]
        assert "creation_tokens" in data["cache_analysis"]
        assert "read_tokens" in data["cache_analysis"]
        assert "ratio" in data["cache_analysis"]
        assert "net_savings_usd" in data["cache_analysis"]
        assert "top_cache_creators" in data["cache_analysis"]
        assert "top_cache_readers" in data["cache_analysis"]
        assert "recommendation" in data["cache_analysis"]

    def test_session_cost_fields(self) -> None:
        """Test session has cost_no_cache and cache_savings_usd fields"""
        session = Session(project="test", platform="test", session_id="test-123")

        # Should have default values
        assert session.cost_no_cache == 0.0
        assert session.cache_savings_usd == 0.0

        # Should be settable
        session.cost_no_cache = 1.50
        session.cache_savings_usd = 0.25
        assert session.cost_no_cache == 1.50
        assert session.cache_savings_usd == 0.25

    def test_session_to_dict_includes_cost_fields(self) -> None:
        """Test session.to_dict() includes cost_no_cache_usd and cache_savings_usd"""
        tracker = ConcreteTestTracker()

        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
        )

        tracker.session.cost_estimate = 1.00
        tracker.session.cost_no_cache = 1.25
        tracker.session.cache_savings_usd = 0.25

        session = tracker.finalize_session()
        data = session.to_dict()

        assert data["cost_estimate_usd"] == 1.00
        assert data["cost_no_cache_usd"] == 1.25
        assert data["cache_savings_usd"] == 0.25


# ============================================================================
# Schema v1.5.0 Tests (Insight Layer)
# ============================================================================


class TestSmellDataStructure:
    """Tests for Smell dataclass (v1.5.0 - task-103.3)"""

    def test_smell_creation_basic(self) -> None:
        """Test basic Smell creation"""
        smell = Smell(
            pattern="HIGH_VARIANCE",
            severity="warning",
            tool="mcp__zen__thinkdeep",
            description="Token counts vary significantly",
            evidence={"std_dev": 45000, "min_tokens": 10000, "max_tokens": 150000},
        )

        assert smell.pattern == "HIGH_VARIANCE"
        assert smell.severity == "warning"
        assert smell.tool == "mcp__zen__thinkdeep"
        assert smell.description == "Token counts vary significantly"
        assert smell.evidence["std_dev"] == 45000

    def test_smell_to_dict_with_tool(self) -> None:
        """Test Smell.to_dict() includes tool when set"""
        smell = Smell(
            pattern="CHATTY",
            severity="warning",
            tool="mcp__zen__chat",
            description="Called 25 times",
            evidence={"call_count": 25, "threshold": 20},
        )

        data = smell.to_dict()

        assert data["pattern"] == "CHATTY"
        assert data["severity"] == "warning"
        assert data["tool"] == "mcp__zen__chat"
        assert data["description"] == "Called 25 times"
        assert data["evidence"]["call_count"] == 25

    def test_smell_to_dict_without_tool(self) -> None:
        """Test Smell.to_dict() omits tool when None (session-level smells)"""
        smell = Smell(
            pattern="HIGH_MCP_SHARE",
            severity="info",
            description="MCP tools consuming 85% of session tokens",
            evidence={"mcp_percentage": 85.0},
        )

        data = smell.to_dict()

        assert data["pattern"] == "HIGH_MCP_SHARE"
        assert "tool" not in data
        assert data["evidence"]["mcp_percentage"] == 85.0

    def test_smell_default_values(self) -> None:
        """Test Smell default values"""
        smell = Smell(pattern="TOP_CONSUMER")

        assert smell.severity == "info"
        assert smell.tool is None
        assert smell.description == ""
        assert smell.evidence == {}


class TestDataQualityDataStructure:
    """Tests for DataQuality dataclass (v1.5.0 - task-103.3)"""

    def test_data_quality_creation_exact(self) -> None:
        """Test DataQuality for Claude Code (exact tokens)"""
        dq = DataQuality(
            accuracy_level="exact",
            token_source="native",
            confidence=1.0,
            notes="Native Claude Code token attribution",
        )

        assert dq.accuracy_level == "exact"
        assert dq.token_source == "native"
        assert dq.token_encoding is None
        assert dq.confidence == 1.0

    def test_data_quality_creation_estimated(self) -> None:
        """Test DataQuality for Codex CLI (estimated tokens)"""
        dq = DataQuality(
            accuracy_level="estimated",
            token_source="tiktoken",
            token_encoding="o200k_base",
            confidence=0.99,
            notes="Tokens estimated using tiktoken o200k_base",
        )

        assert dq.accuracy_level == "estimated"
        assert dq.token_source == "tiktoken"
        assert dq.token_encoding == "o200k_base"
        assert dq.confidence == 0.99

    def test_data_quality_to_dict_with_encoding(self) -> None:
        """Test DataQuality.to_dict() includes encoding when set"""
        dq = DataQuality(
            accuracy_level="estimated",
            token_source="sentencepiece",
            token_encoding="gemma",
            confidence=1.0,
            notes="Using Gemma tokenizer",
        )

        data = dq.to_dict()

        assert data["accuracy_level"] == "estimated"
        assert data["token_source"] == "sentencepiece"
        assert data["token_encoding"] == "gemma"
        assert data["confidence"] == 1.0
        assert data["notes"] == "Using Gemma tokenizer"

    def test_data_quality_to_dict_without_encoding(self) -> None:
        """Test DataQuality.to_dict() omits encoding when None"""
        dq = DataQuality(
            accuracy_level="exact",
            token_source="native",
            confidence=1.0,
        )

        data = dq.to_dict()

        assert "token_encoding" not in data
        assert "notes" not in data

    def test_data_quality_default_values(self) -> None:
        """Test DataQuality default values"""
        dq = DataQuality()

        assert dq.accuracy_level == "exact"
        assert dq.token_source == "native"
        assert dq.token_encoding is None
        assert dq.confidence == 1.0
        assert dq.notes == ""


class TestSessionV150Fields:
    """Tests for Session v1.5.0 fields (task-103.3)"""

    def test_session_has_smells_field(self) -> None:
        """Test Session has smells list field"""
        session = Session(project="test", platform="test", session_id="test-123")

        assert hasattr(session, "smells")
        assert session.smells == []

    def test_session_has_data_quality_field(self) -> None:
        """Test Session has data_quality field"""
        session = Session(project="test", platform="test", session_id="test-123")

        assert hasattr(session, "data_quality")
        assert session.data_quality is None

    def test_session_has_zombie_tools_field(self) -> None:
        """Test Session has zombie_tools field"""
        session = Session(project="test", platform="test", session_id="test-123")

        assert hasattr(session, "zombie_tools")
        assert session.zombie_tools == {}

    def test_session_to_dict_includes_smells(self) -> None:
        """Test Session.to_dict() includes smells block"""
        session = Session(project="test", platform="claude-code", session_id="test-123")
        session.smells = [
            Smell(
                pattern="CHATTY",
                severity="warning",
                tool="mcp__zen__chat",
                description="Called 25 times",
                evidence={"call_count": 25},
            ),
            Smell(
                pattern="TOP_CONSUMER",
                severity="info",
                tool="mcp__zen__thinkdeep",
                description="60% of tokens",
                evidence={"percentage": 60.0},
            ),
        ]

        data = session.to_dict()

        assert "smells" in data
        assert len(data["smells"]) == 2
        assert data["smells"][0]["pattern"] == "CHATTY"
        assert data["smells"][1]["pattern"] == "TOP_CONSUMER"

    def test_session_to_dict_includes_data_quality(self) -> None:
        """Test Session.to_dict() includes data_quality when set"""
        session = Session(project="test", platform="codex-cli", session_id="test-123")
        session.data_quality = DataQuality(
            accuracy_level="estimated",
            token_source="tiktoken",
            token_encoding="o200k_base",
            confidence=0.99,
        )

        data = session.to_dict()

        assert "data_quality" in data
        assert data["data_quality"]["accuracy_level"] == "estimated"
        assert data["data_quality"]["token_encoding"] == "o200k_base"

    def test_session_to_dict_omits_data_quality_when_none(self) -> None:
        """Test Session.to_dict() omits data_quality when not set"""
        session = Session(project="test", platform="claude-code", session_id="test-123")
        # data_quality is None by default

        data = session.to_dict()

        assert "data_quality" not in data

    def test_session_to_dict_includes_zombie_tools(self) -> None:
        """Test Session.to_dict() includes zombie_tools block"""
        session = Session(project="test", platform="claude-code", session_id="test-123")
        session.zombie_tools = {
            "zen": ["mcp__zen__refactor", "mcp__zen__precommit"],
            "backlog": ["mcp__backlog__task_archive"],
        }

        data = session.to_dict()

        assert "zombie_tools" in data
        assert data["zombie_tools"]["zen"] == ["mcp__zen__refactor", "mcp__zen__precommit"]
        assert data["zombie_tools"]["backlog"] == ["mcp__backlog__task_archive"]

    def test_session_to_dict_empty_zombie_tools(self) -> None:
        """Test Session.to_dict() includes empty zombie_tools when none detected"""
        session = Session(project="test", platform="claude-code", session_id="test-123")

        data = session.to_dict()

        assert "zombie_tools" in data
        assert data["zombie_tools"] == {}


class TestSchemaVersion170:
    """Tests for schema version 1.7.0 (task-106.5)"""

    def test_schema_version_is_1_7_0(self) -> None:
        """Test SCHEMA_VERSION constant is 1.7.0"""
        assert SCHEMA_VERSION == "1.7.0"

    def test_session_uses_schema_version_1_7_0(self) -> None:
        """Test new Session objects use schema v1.7.0"""
        session = Session(project="test", platform="test", session_id="test-123")

        assert session.schema_version == "1.7.0"

    def test_tracker_saves_with_schema_1_7_0(self, tmp_path) -> None:
        """Test saved session files have schema v1.7.0 in _file header"""
        import json

        tracker = ConcreteTestTracker()
        tracker.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)
        tracker.finalize_session()
        tracker.save_session(tmp_path)

        # Load the saved session file
        session_files = list(tracker.session_dir.glob("*.json"))
        assert len(session_files) == 1

        with open(session_files[0]) as f:
            data = json.load(f)

        assert data["_file"]["schema_version"] == "1.7.0"


class TestPinnedMCPFocus:
    """Tests for v1.7.0 Pinned MCP Focus features (task-106.5)"""

    def test_session_has_pinned_servers_field(self) -> None:
        """Test Session has pinned_servers field."""
        session = Session(project="test", platform="test", session_id="test-123")
        assert hasattr(session, "pinned_servers")
        assert session.pinned_servers == []

    def test_session_pinned_servers_can_be_set(self) -> None:
        """Test pinned_servers can be set."""
        session = Session(
            project="test",
            platform="test",
            session_id="test-123",
            pinned_servers=["backlog", "brave-search"],
        )
        assert session.pinned_servers == ["backlog", "brave-search"]

    def test_session_to_dict_includes_pinned_servers(self) -> None:
        """Test to_dict includes pinned_servers when set."""
        session = Session(
            project="test", platform="test", session_id="test-123", pinned_servers=["backlog"]
        )
        data = session.to_dict()
        assert "pinned_servers" in data
        assert data["pinned_servers"] == ["backlog"]

    def test_session_to_dict_excludes_pinned_servers_when_empty(self) -> None:
        """Test to_dict excludes pinned_servers when empty."""
        session = Session(project="test", platform="test", session_id="test-123")
        data = session.to_dict()
        assert "pinned_servers" not in data

    def test_session_to_dict_includes_mcp_servers_hierarchy(self) -> None:
        """Test to_dict includes mcp_servers hierarchy."""
        session = Session(project="test", platform="test", session_id="test-123")
        # Add some server data
        session.server_sessions["backlog"] = ServerSession(
            server="backlog",
            total_calls=5,
            total_tokens=2500,
        )
        session.server_sessions["backlog"].tools["task_view"] = ToolStats(
            calls=5, total_tokens=2500, avg_tokens=500.0
        )

        data = session.to_dict()
        assert "mcp_servers" in data
        assert "backlog" in data["mcp_servers"]
        assert data["mcp_servers"]["backlog"]["calls"] == 5
        assert data["mcp_servers"]["backlog"]["tokens"] == 2500
        assert data["mcp_servers"]["backlog"]["is_pinned"] is False
        assert "task_view" in data["mcp_servers"]["backlog"]["tools"]

    def test_session_to_dict_mcp_servers_pinned_flag(self) -> None:
        """Test mcp_servers hierarchy includes correct is_pinned flag."""
        session = Session(
            project="test", platform="test", session_id="test-123", pinned_servers=["backlog"]
        )
        session.server_sessions["backlog"] = ServerSession(
            server="backlog", total_calls=3, total_tokens=1500
        )
        session.server_sessions["brave-search"] = ServerSession(
            server="brave-search", total_calls=2, total_tokens=1000
        )

        data = session.to_dict()
        assert data["mcp_servers"]["backlog"]["is_pinned"] is True
        assert data["mcp_servers"]["brave-search"]["is_pinned"] is False

    def test_session_to_dict_includes_tool_sequence(self) -> None:
        """Test to_dict includes tool_sequence."""
        session = Session(project="test", platform="test", session_id="test-123")
        data = session.to_dict()
        assert "tool_sequence" in data
        assert isinstance(data["tool_sequence"], list)

    def test_session_to_dict_includes_pinned_server_usage(self) -> None:
        """Test to_dict includes pinned_server_usage when pinned servers set."""
        session = Session(
            project="test", platform="test", session_id="test-123", pinned_servers=["backlog"]
        )
        session.server_sessions["backlog"] = ServerSession(
            server="backlog", total_calls=5, total_tokens=2500
        )
        session.server_sessions["brave-search"] = ServerSession(
            server="brave-search", total_calls=3, total_tokens=1500
        )

        data = session.to_dict()
        assert "pinned_server_usage" in data
        assert data["pinned_server_usage"]["pinned_calls"] == 5
        assert data["pinned_server_usage"]["pinned_tokens"] == 2500
        assert data["pinned_server_usage"]["non_pinned_calls"] == 3
        assert data["pinned_server_usage"]["non_pinned_tokens"] == 1500

    def test_session_to_dict_includes_pinned_coverage(self) -> None:
        """Test to_dict includes pinned_coverage percentage."""
        session = Session(
            project="test", platform="test", session_id="test-123", pinned_servers=["backlog"]
        )
        session.server_sessions["backlog"] = ServerSession(
            server="backlog", total_calls=3, total_tokens=1500
        )
        session.server_sessions["brave-search"] = ServerSession(
            server="brave-search", total_calls=1, total_tokens=500
        )

        data = session.to_dict()
        assert "pinned_coverage" in data
        # 3 pinned calls out of 4 total = 0.75
        assert data["pinned_coverage"] == 0.75


class TestDataQualityPerPlatform:
    """Tests for data_quality initialization per platform (v1.5.0 - task-103.5)"""

    def test_claude_code_data_quality_exact(self, tmp_path) -> None:
        """Test Claude Code adapter sets data_quality to exact/native"""
        from token_audit.claude_code_adapter import ClaudeCodeAdapter

        # Create mock Claude directory structure for CI
        mock_claude_dir = tmp_path / "claude"
        mock_claude_dir.mkdir(parents=True)

        adapter = ClaudeCodeAdapter(project="test", claude_dir=mock_claude_dir)

        assert adapter.session.data_quality is not None
        assert adapter.session.data_quality.accuracy_level == "exact"
        assert adapter.session.data_quality.token_source == "native"
        assert adapter.session.data_quality.confidence == 1.0
        assert "Native token counts" in adapter.session.data_quality.notes

    def test_codex_cli_data_quality_estimated(self, tmp_path, monkeypatch) -> None:
        """Test Codex CLI adapter sets data_quality to estimated/tiktoken"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        # Create mock Codex directory structure for CI
        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")

        assert adapter.session.data_quality is not None
        assert adapter.session.data_quality.accuracy_level == "estimated"
        assert adapter.session.data_quality.token_source == "tiktoken"
        assert adapter.session.data_quality.token_encoding == "o200k_base"
        assert adapter.session.data_quality.confidence == 0.99
        assert "tiktoken" in adapter.session.data_quality.notes

    def test_gemini_cli_data_quality(self, tmp_path, monkeypatch) -> None:
        """Test Gemini CLI adapter sets data_quality appropriately.

        With sentencepiece installed (which is a core dependency), the Gemma
        tokenizer is available and returns 'exact' accuracy. Without the
        tokenizer file, it falls back to 'estimated'.
        """
        from token_audit.gemini_cli_adapter import GeminiCLIAdapter

        # Create mock Gemini directory structure for CI
        mock_gemini_dir = tmp_path / ".gemini"
        mock_gemini_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = GeminiCLIAdapter(project="test")

        assert adapter.session.data_quality is not None
        # Accuracy level depends on whether Gemma tokenizer is available
        # With sentencepiece installed, it's 'exact'; without, it's 'estimated'
        assert adapter.session.data_quality.accuracy_level in ["exact", "estimated"]
        # Token source depends on whether Gemma tokenizer is available
        assert adapter.session.data_quality.token_source in ["sentencepiece", "tiktoken"]
        # Confidence is 1.0 for Gemma, 0.95 for tiktoken fallback
        assert adapter.session.data_quality.confidence in [1.0, 0.95]

    def test_data_quality_serializes_to_session_file(self, tmp_path, monkeypatch) -> None:
        """Test data_quality block appears in saved session JSON"""
        import json

        from token_audit.codex_cli_adapter import CodexCLIAdapter

        # Create mock Codex directory structure for CI
        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.finalize_session()
        adapter.save_session(tmp_path)

        # Load the saved session file
        session_files = list(adapter.session_dir.glob("*.json"))
        assert len(session_files) == 1

        with open(session_files[0]) as f:
            data = json.load(f)

        assert "data_quality" in data
        assert data["data_quality"]["accuracy_level"] == "estimated"
        assert data["data_quality"]["token_source"] == "tiktoken"


class TestDataQualityPricingFields:
    """Tests for v1.6.0 pricing fields in DataQuality (task-108.3.4)"""

    def test_data_quality_has_pricing_fields(self) -> None:
        """Test DataQuality has pricing_source and pricing_freshness fields"""
        from token_audit.base_tracker import DataQuality

        dq = DataQuality()
        assert hasattr(dq, "pricing_source")
        assert hasattr(dq, "pricing_freshness")
        assert dq.pricing_source == "defaults"
        assert dq.pricing_freshness == "unknown"

    def test_data_quality_pricing_to_dict(self) -> None:
        """Test pricing fields are included in to_dict()"""
        from token_audit.base_tracker import DataQuality

        dq = DataQuality(
            accuracy_level="exact",
            token_source="native",
            pricing_source="api",
            pricing_freshness="fresh",
        )

        result = dq.to_dict()
        assert result["pricing_source"] == "api"
        assert result["pricing_freshness"] == "fresh"

    def test_finalize_session_sets_pricing_from_config(self, tmp_path, monkeypatch) -> None:
        """Test finalize_session() populates pricing fields from pricing_config"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        # Create mock Codex directory structure for CI
        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")

        # Adapter has _pricing_config and data_quality should exist
        assert hasattr(adapter, "_pricing_config")
        assert adapter.session.data_quality is not None

        # Finalize session - this should set pricing fields
        session = adapter.finalize_session()

        # Check pricing fields were set (values depend on pricing_config state)
        assert session.data_quality.pricing_source in ["api", "cache", "file", "defaults"]
        assert session.data_quality.pricing_freshness in ["fresh", "cached", "stale", "unknown"]

    def test_data_quality_pricing_serializes_to_json(self, tmp_path, monkeypatch) -> None:
        """Test pricing fields appear in saved session JSON"""
        import json

        from token_audit.codex_cli_adapter import CodexCLIAdapter

        # Create mock Codex directory structure for CI
        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.finalize_session()
        adapter.save_session(tmp_path)

        # Load the saved session file
        session_files = list(adapter.session_dir.glob("*.json"))
        assert len(session_files) == 1

        with open(session_files[0]) as f:
            data = json.load(f)

        # Check pricing fields in serialized data_quality
        assert "data_quality" in data
        assert "pricing_source" in data["data_quality"]
        assert "pricing_freshness" in data["data_quality"]


class TestMultiModelDataStructures:
    """Tests for v1.6.0 multi-model tracking data structures (task-108.2.2)"""

    def test_call_has_model_field(self) -> None:
        """Test Call dataclass has model field"""
        from token_audit.base_tracker import Call

        call = Call()
        assert hasattr(call, "model")
        assert call.model is None  # Default is None

    def test_call_model_can_be_set(self) -> None:
        """Test Call.model can be set"""
        from token_audit.base_tracker import Call

        call = Call(model="claude-sonnet-4-20250514")
        assert call.model == "claude-sonnet-4-20250514"

    def test_call_to_dict_includes_model_when_set(self) -> None:
        """Test Call.to_dict() includes model when present"""
        from token_audit.base_tracker import Call

        call = Call(
            index=1,
            tool_name="mcp__zen__chat",
            server="zen",
            model="claude-opus-4-5-20251101",
        )
        result = call.to_dict()
        assert result["model"] == "claude-opus-4-5-20251101"

    def test_call_to_dict_excludes_model_when_none(self) -> None:
        """Test Call.to_dict() excludes model when None (file size optimization)"""
        from token_audit.base_tracker import Call

        call = Call(
            index=1,
            tool_name="mcp__zen__chat",
            server="zen",
            model=None,
        )
        result = call.to_dict()
        assert "model" not in result

    def test_session_has_models_used_field(self) -> None:
        """Test Session has models_used field"""
        from token_audit.base_tracker import Session

        session = Session()
        assert hasattr(session, "models_used")
        assert session.models_used == []

    def test_session_has_model_usage_field(self) -> None:
        """Test Session has model_usage field"""
        from token_audit.base_tracker import Session

        session = Session()
        assert hasattr(session, "model_usage")
        assert session.model_usage == {}

    def test_model_usage_dataclass(self) -> None:
        """Test ModelUsage dataclass exists and has expected fields"""
        from token_audit.base_tracker import ModelUsage

        usage = ModelUsage(
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=5000,
            cache_created_tokens=1000,
            cache_read_tokens=500,
            total_tokens=16500,
            cost_usd=0.05,
            call_count=3,
        )
        assert usage.model == "claude-sonnet-4-20250514"
        assert usage.input_tokens == 10000
        assert usage.output_tokens == 5000
        assert usage.cache_created_tokens == 1000
        assert usage.cache_read_tokens == 500
        assert usage.total_tokens == 16500
        assert usage.cost_usd == 0.05
        assert usage.call_count == 3

    def test_model_usage_to_dict(self) -> None:
        """Test ModelUsage.to_dict() returns expected format"""
        from token_audit.base_tracker import ModelUsage

        usage = ModelUsage(
            model="claude-sonnet-4-20250514",
            input_tokens=10000,
            output_tokens=5000,
            cost_usd=0.05,
            call_count=3,
        )
        result = usage.to_dict()
        assert result == {
            "input_tokens": 10000,
            "output_tokens": 5000,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.05,
            "call_count": 3,
        }
        # Note: model is NOT in to_dict() - it's used as dict key in Session.model_usage

    def test_session_to_dict_includes_models_used(self) -> None:
        """Test Session.to_dict() includes models_used in session block"""
        from token_audit.base_tracker import Session

        session = Session()
        session.models_used = ["claude-sonnet-4-20250514", "claude-opus-4-5-20251101"]
        result = session.to_dict()
        assert result["session"]["models_used"] == [
            "claude-sonnet-4-20250514",
            "claude-opus-4-5-20251101",
        ]

    def test_session_to_dict_includes_model_usage(self) -> None:
        """Test Session.to_dict() includes model_usage block when populated"""
        from token_audit.base_tracker import ModelUsage, Session

        session = Session()
        session.model_usage = {
            "claude-sonnet-4-20250514": ModelUsage(
                model="claude-sonnet-4-20250514",
                input_tokens=10000,
                output_tokens=5000,
                cost_usd=0.05,
                call_count=3,
            ),
            "claude-opus-4-5-20251101": ModelUsage(
                model="claude-opus-4-5-20251101",
                input_tokens=5000,
                output_tokens=2000,
                cost_usd=0.15,
                call_count=1,
            ),
        }
        result = session.to_dict()
        assert "model_usage" in result
        assert "claude-sonnet-4-20250514" in result["model_usage"]
        assert result["model_usage"]["claude-sonnet-4-20250514"]["call_count"] == 3
        assert result["model_usage"]["claude-opus-4-5-20251101"]["cost_usd"] == 0.15

    def test_session_to_dict_excludes_model_usage_when_empty(self) -> None:
        """Test Session.to_dict() excludes model_usage when empty"""
        from token_audit.base_tracker import Session

        session = Session()
        session.model_usage = {}  # Empty
        result = session.to_dict()
        assert "model_usage" not in result

    def test_session_to_dict_models_used_empty_list(self) -> None:
        """Test Session.to_dict() includes empty models_used when not populated"""
        from token_audit.base_tracker import Session

        session = Session()
        result = session.to_dict()
        assert result["session"]["models_used"] == []


class TestMultiModelAggregation:
    """Tests for v1.6.0 multi-model aggregation in finalize_session() (task-108.2.3)"""

    def test_record_tool_call_accepts_model_param(self, tmp_path, monkeypatch) -> None:
        """Test record_tool_call accepts model parameter"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-5.1",
        )
        # Verify call was recorded with model
        server_session = adapter.server_sessions.get("zen")
        assert server_session is not None
        tool_stats = server_session.tools.get("mcp__zen__chat")
        assert tool_stats is not None
        assert tool_stats.call_history[0].model == "gpt-5.1"

    def test_finalize_session_aggregates_by_model(self, tmp_path, monkeypatch) -> None:
        """Test finalize_session aggregates tokens by model"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        # Record calls with different models
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-5.1",
        )
        adapter.record_tool_call(
            tool_name="mcp__zen__thinkdeep",
            input_tokens=2000,
            output_tokens=1000,
            model="gpt-5.1",
        )
        adapter.record_tool_call(
            tool_name="mcp__brave-search__web",
            input_tokens=500,
            output_tokens=200,
            model="claude-sonnet-4",
        )

        session = adapter.finalize_session()

        # Should have 2 models
        assert len(session.models_used) == 2
        assert "gpt-5.1" in session.models_used
        assert "claude-sonnet-4" in session.models_used

        # Check aggregation for gpt-5.1
        assert "gpt-5.1" in session.model_usage
        gpt_usage = session.model_usage["gpt-5.1"]
        assert gpt_usage.input_tokens == 3000  # 1000 + 2000
        assert gpt_usage.output_tokens == 1500  # 500 + 1000
        assert gpt_usage.call_count == 2

        # Check aggregation for claude-sonnet-4
        assert "claude-sonnet-4" in session.model_usage
        claude_usage = session.model_usage["claude-sonnet-4"]
        assert claude_usage.input_tokens == 500
        assert claude_usage.output_tokens == 200
        assert claude_usage.call_count == 1

    def test_finalize_session_fallback_to_session_model(self, tmp_path, monkeypatch) -> None:
        """Test finalize_session uses session model when call model is None"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.session.model = "default-model"
        # Record call without explicit model
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            # model=None (default)
        )

        session = adapter.finalize_session()

        # Should use session model as fallback
        assert "default-model" in session.models_used
        assert "default-model" in session.model_usage
        assert session.model_usage["default-model"].call_count == 1

    def test_finalize_session_fallback_to_unknown(self, tmp_path, monkeypatch) -> None:
        """Test finalize_session uses 'unknown' when no model info available"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.session.model = ""  # Empty session model
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            # model=None (default)
        )

        session = adapter.finalize_session()

        # Should use "unknown" as fallback
        assert "unknown" in session.models_used
        assert "unknown" in session.model_usage

    def test_models_used_includes_session_model_no_tool_calls(self, tmp_path, monkeypatch) -> None:
        """Test models_used includes session model even with no MCP tool calls (task-123)"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.session.model = "gpt-5.1"

        # Finalize WITHOUT recording any tool calls
        session = adapter.finalize_session()

        # models_used should contain the session model, even with no MCP calls
        assert len(session.models_used) == 1
        assert "gpt-5.1" in session.models_used
        # model_usage will be empty since no actual calls tracked tokens
        assert session.model_usage == {}

    def test_models_used_includes_session_model_and_tool_models(
        self, tmp_path, monkeypatch
    ) -> None:
        """Test models_used includes both session model and tool call models (task-123)"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.session.model = "session-default-model"

        # Record a call with a DIFFERENT model
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="tool-specific-model",
        )

        session = adapter.finalize_session()

        # models_used should contain BOTH the session model and the tool call model
        assert len(session.models_used) == 2
        assert "session-default-model" in session.models_used
        assert "tool-specific-model" in session.models_used

    def test_single_model_session_backward_compatible(self, tmp_path, monkeypatch) -> None:
        """Test single-model sessions work correctly (backward compatibility)"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        # Create mock Codex directory for CI
        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.detected_model = "claude-opus-4-5-20251101"
        adapter.session.model = adapter.detected_model

        # Record multiple calls, all same model
        for i in range(5):
            adapter.record_tool_call(
                tool_name=f"mcp__zen__tool{i}",
                input_tokens=100 * (i + 1),
                output_tokens=50 * (i + 1),
                model=adapter.detected_model,
            )

        session = adapter.finalize_session()

        # Should have only 1 model
        assert len(session.models_used) == 1
        assert session.models_used[0] == "claude-opus-4-5-20251101"

        # Total should match
        usage = session.model_usage["claude-opus-4-5-20251101"]
        assert usage.call_count == 5
        assert usage.input_tokens == 100 + 200 + 300 + 400 + 500  # 1500
        assert usage.output_tokens == 50 + 100 + 150 + 200 + 250  # 750

    def test_model_usage_appears_in_json_output(self, tmp_path, monkeypatch) -> None:
        """Test model_usage is correctly serialized in session JSON"""
        import json

        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-5.1",
        )
        adapter.record_tool_call(
            tool_name="mcp__zen__debug",
            input_tokens=2000,
            output_tokens=1000,
            model="claude-sonnet-4",
        )

        adapter.finalize_session()
        adapter.save_session(tmp_path)

        # Load and verify JSON
        session_files = list(adapter.session_dir.glob("*.json"))
        assert len(session_files) == 1

        with open(session_files[0]) as f:
            data = json.load(f)

        # Check models_used in session block
        assert "models_used" in data["session"]
        assert len(data["session"]["models_used"]) == 2

        # Check model_usage block
        assert "model_usage" in data
        assert "gpt-5.1" in data["model_usage"]
        assert "claude-sonnet-4" in data["model_usage"]
        assert data["model_usage"]["gpt-5.1"]["call_count"] == 1
        assert data["model_usage"]["gpt-5.1"]["input_tokens"] == 1000


class TestMultiModelTUIDisplay:
    """Tests for v1.6.0 multi-model TUI display (task-108.2.4)"""

    def test_convert_model_usage_for_snapshot_empty(self, tmp_path, monkeypatch) -> None:
        """Test _convert_model_usage_for_snapshot returns None for empty model_usage"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        # No tool calls, so model_usage is empty
        result = adapter._convert_model_usage_for_snapshot()
        assert result is None

    def test_convert_model_usage_for_snapshot_single_model(self, tmp_path, monkeypatch) -> None:
        """Test _convert_model_usage_for_snapshot with single model"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-5.1",
        )
        adapter.finalize_session()

        result = adapter._convert_model_usage_for_snapshot()
        assert result is not None
        assert len(result) == 1
        # Tuple format: (model, input, output, total, cache_read, cost, calls)
        model, inp, out, total, cache_read, cost, calls = result[0]
        assert model == "gpt-5.1"
        assert inp == 1000
        assert out == 500
        assert total == 1500
        assert calls == 1

    def test_convert_model_usage_for_snapshot_multi_model(self, tmp_path, monkeypatch) -> None:
        """Test _convert_model_usage_for_snapshot with multiple models"""
        from token_audit.codex_cli_adapter import CodexCLIAdapter

        mock_codex_dir = tmp_path / ".codex"
        mock_codex_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        adapter = CodexCLIAdapter(project="test")
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            model="gpt-5.1",
        )
        adapter.record_tool_call(
            tool_name="mcp__zen__debug",
            input_tokens=2000,
            output_tokens=1000,
            model="claude-sonnet-4",
        )
        adapter.finalize_session()

        result = adapter._convert_model_usage_for_snapshot()
        assert result is not None
        assert len(result) == 2

        # Convert to dict for easier assertion
        model_dict = {r[0]: r for r in result}
        assert "gpt-5.1" in model_dict
        assert "claude-sonnet-4" in model_dict

        gpt = model_dict["gpt-5.1"]
        assert gpt[1] == 1000  # input
        assert gpt[2] == 500  # output
        assert gpt[3] == 1500  # total

        claude = model_dict["claude-sonnet-4"]
        assert claude[1] == 2000  # input
        assert claude[2] == 1000  # output
        assert claude[3] == 3000  # total

    def test_display_snapshot_multi_model_fields(self) -> None:
        """Test DisplaySnapshot has multi-model fields"""
        from token_audit.display.snapshot import DisplaySnapshot

        # Create snapshot with multi-model data
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=datetime.now(),
            duration_seconds=60.0,
            models_used=["model-a", "model-b"],
            model_usage=[
                ("model-a", 1000, 500, 1500, 0, 0.01, 5),
                ("model-b", 2000, 1000, 3000, 0, 0.02, 3),
            ],
            is_multi_model=True,
        )

        assert snapshot.is_multi_model is True
        assert len(snapshot.models_used) == 2
        assert "model-a" in snapshot.models_used
        assert "model-b" in snapshot.models_used
        assert len(snapshot.model_usage) == 2

    def test_display_snapshot_single_model_defaults(self) -> None:
        """Test DisplaySnapshot defaults for single model (backward compatible)"""
        from token_audit.display.snapshot import DisplaySnapshot

        # Create snapshot without multi-model data
        snapshot = DisplaySnapshot.create(
            project="test",
            platform="test",
            start_time=datetime.now(),
            duration_seconds=60.0,
            model_id="model-a",
            model_name="Model A",
        )

        assert snapshot.is_multi_model is False
        assert len(snapshot.models_used) == 0
        assert len(snapshot.model_usage) == 0


class TestStaticCostDataStructure:
    """Tests for v1.6.0 StaticCost dataclass (task-108.4)"""

    def test_static_cost_creation_default(self) -> None:
        """Test StaticCost can be created with defaults"""
        from token_audit.base_tracker import StaticCost

        static_cost = StaticCost()

        assert static_cost.total_tokens == 0
        assert static_cost.source == "estimate"
        assert static_cost.by_server == {}
        assert static_cost.confidence == 0.7

    def test_static_cost_creation_with_values(self) -> None:
        """Test StaticCost can be created with custom values"""
        from token_audit.base_tracker import StaticCost

        static_cost = StaticCost(
            total_tokens=5000,
            source="live",
            by_server={"zen": 2500, "backlog": 1500, "brave-search": 1000},
            confidence=0.95,
        )

        assert static_cost.total_tokens == 5000
        assert static_cost.source == "live"
        assert len(static_cost.by_server) == 3
        assert static_cost.by_server["zen"] == 2500
        assert static_cost.confidence == 0.95

    def test_static_cost_to_dict(self) -> None:
        """Test StaticCost.to_dict() produces correct output"""
        from token_audit.base_tracker import StaticCost

        static_cost = StaticCost(
            total_tokens=3000,
            source="cache",
            by_server={"server-a": 2000, "server-b": 1000},
            confidence=0.8,
        )

        result = static_cost.to_dict()

        assert result["total_tokens"] == 3000
        assert result["source"] == "cache"
        assert result["by_server"] == {"server-a": 2000, "server-b": 1000}
        assert result["confidence"] == 0.8

    def test_session_has_static_cost_field(self) -> None:
        """Test Session has optional static_cost field"""
        from token_audit.base_tracker import Session, StaticCost

        session = Session()

        # Default is None
        assert session.static_cost is None

        # Can be set
        session.static_cost = StaticCost(total_tokens=5000)
        assert session.static_cost is not None
        assert session.static_cost.total_tokens == 5000

    def test_session_to_dict_includes_static_cost_when_set(self) -> None:
        """Test Session.to_dict() includes static_cost when set"""
        from token_audit.base_tracker import Session, StaticCost

        session = Session()
        session.static_cost = StaticCost(
            total_tokens=4000,
            source="estimate",
            by_server={"zen": 4000},
        )

        result = session.to_dict()

        assert "static_cost" in result
        assert result["static_cost"]["total_tokens"] == 4000
        assert result["static_cost"]["source"] == "estimate"
        assert result["static_cost"]["by_server"] == {"zen": 4000}

    def test_session_to_dict_excludes_static_cost_when_none(self) -> None:
        """Test Session.to_dict() excludes static_cost when None"""
        from token_audit.base_tracker import Session

        session = Session()
        session.static_cost = None

        result = session.to_dict()

        assert "static_cost" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
