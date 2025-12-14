"""
Tests for the Smell Engine (v1.5.0 - task-103.1).

Tests cover:
- SmellThresholds configuration
- SmellDetector for each pattern:
  - HIGH_VARIANCE
  - TOP_CONSUMER
  - HIGH_MCP_SHARE
  - CHATTY
  - LOW_CACHE_HIT
- Integration with session finalization
"""

import pytest

from mcp_audit.base_tracker import (
    ServerSession,
    Session,
    Smell,
    TokenUsage,
    ToolStats,
)
from mcp_audit.smells import SmellDetector, SmellThresholds, detect_smells


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session(
    input_tokens: int = 10000,
    output_tokens: int = 5000,
    cache_read: int = 0,
    cache_created: int = 0,
) -> Session:
    """Create a minimal test session."""
    session = Session(
        project="test-project",
        platform="claude-code",
        session_id="test-session-123",
    )
    session.token_usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_created_tokens=cache_created,
        total_tokens=input_tokens + output_tokens,
    )
    return session


def add_tool_to_session(
    session: Session,
    server_name: str,
    tool_name: str,
    calls: int,
    total_tokens: int,
    cache_read: int = 0,
    cache_created: int = 0,
) -> None:
    """Add a tool with stats to a session."""
    if server_name not in session.server_sessions:
        session.server_sessions[server_name] = ServerSession(server=server_name)

    server = session.server_sessions[server_name]
    server.tools[tool_name] = ToolStats(
        calls=calls,
        total_tokens=total_tokens,
        cache_read_tokens=cache_read,
        cache_created_tokens=cache_created,
    )
    server.total_calls += calls
    server.total_tokens += total_tokens


# ============================================================================
# SmellThresholds Tests
# ============================================================================


class TestSmellThresholds:
    """Tests for SmellThresholds configuration."""

    def test_default_thresholds(self) -> None:
        """Test default threshold values."""
        thresholds = SmellThresholds()

        assert thresholds.high_variance_cv == 0.5
        assert thresholds.top_consumer_percent == 50.0
        assert thresholds.high_mcp_share_percent == 80.0
        assert thresholds.chatty_call_threshold == 20
        assert thresholds.low_cache_hit_percent == 30.0

    def test_custom_thresholds(self) -> None:
        """Test custom threshold values."""
        thresholds = SmellThresholds(
            chatty_call_threshold=10,
            top_consumer_percent=40.0,
        )

        assert thresholds.chatty_call_threshold == 10
        assert thresholds.top_consumer_percent == 40.0
        # Others should be default
        assert thresholds.high_mcp_share_percent == 80.0


# ============================================================================
# TOP_CONSUMER Pattern Tests
# ============================================================================


class TestTopConsumerDetection:
    """Tests for TOP_CONSUMER smell detection."""

    def test_detects_top_consumer(self) -> None:
        """Test detection of tool consuming >50% of MCP tokens."""
        session = create_test_session()

        # Add tools: one consuming 60%, one consuming 40%
        add_tool_to_session(session, "zen", "mcp__zen__thinkdeep", calls=5, total_tokens=6000)
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=10, total_tokens=4000)

        detector = SmellDetector()
        smells = detector.analyze(session)

        top_consumer_smells = [s for s in smells if s.pattern == "TOP_CONSUMER"]
        assert len(top_consumer_smells) == 1

        smell = top_consumer_smells[0]
        assert smell.tool == "mcp__zen__thinkdeep"
        assert smell.severity == "info"
        assert smell.evidence["percentage"] == 60.0

    def test_no_top_consumer_when_balanced(self) -> None:
        """Test no detection when tokens are balanced."""
        session = create_test_session()

        # Add balanced tools: each ~33%
        add_tool_to_session(session, "zen", "mcp__zen__thinkdeep", calls=5, total_tokens=3000)
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=5, total_tokens=3000)
        add_tool_to_session(session, "zen", "mcp__zen__debug", calls=5, total_tokens=3000)

        detector = SmellDetector()
        smells = detector.analyze(session)

        top_consumer_smells = [s for s in smells if s.pattern == "TOP_CONSUMER"]
        assert len(top_consumer_smells) == 0

    def test_ignores_small_token_counts(self) -> None:
        """Test that tiny token consumers are ignored."""
        session = create_test_session()

        # Add tool with very few tokens (under threshold)
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=2, total_tokens=500)

        detector = SmellDetector()
        smells = detector.analyze(session)

        top_consumer_smells = [s for s in smells if s.pattern == "TOP_CONSUMER"]
        assert len(top_consumer_smells) == 0


# ============================================================================
# HIGH_MCP_SHARE Pattern Tests
# ============================================================================


class TestHighMcpShareDetection:
    """Tests for HIGH_MCP_SHARE smell detection."""

    def test_detects_high_mcp_share(self) -> None:
        """Test detection of MCP tools consuming >80% of session tokens."""
        session = create_test_session(input_tokens=1000, output_tokens=500)
        # Total session = 1500

        # Add MCP tools consuming 1300 tokens (86.7% of session)
        add_tool_to_session(session, "zen", "mcp__zen__thinkdeep", calls=5, total_tokens=1300)

        detector = SmellDetector()
        smells = detector.analyze(session)

        high_mcp_smells = [s for s in smells if s.pattern == "HIGH_MCP_SHARE"]
        assert len(high_mcp_smells) == 1

        smell = high_mcp_smells[0]
        assert smell.tool is None  # Session-level smell
        assert smell.severity == "info"
        assert smell.evidence["mcp_percentage"] > 80.0

    def test_no_high_mcp_share_when_low(self) -> None:
        """Test no detection when MCP share is reasonable."""
        session = create_test_session(input_tokens=10000, output_tokens=5000)
        # Total session = 15000

        # Add MCP tools consuming 5000 tokens (33% of session)
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=10, total_tokens=5000)

        detector = SmellDetector()
        smells = detector.analyze(session)

        high_mcp_smells = [s for s in smells if s.pattern == "HIGH_MCP_SHARE"]
        assert len(high_mcp_smells) == 0


# ============================================================================
# CHATTY Pattern Tests
# ============================================================================


class TestChattyDetection:
    """Tests for CHATTY smell detection."""

    def test_detects_chatty_tool(self) -> None:
        """Test detection of tool called >20 times."""
        session = create_test_session()

        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=25, total_tokens=5000)

        detector = SmellDetector()
        smells = detector.analyze(session)

        chatty_smells = [s for s in smells if s.pattern == "CHATTY"]
        assert len(chatty_smells) == 1

        smell = chatty_smells[0]
        assert smell.tool == "mcp__zen__chat"
        assert smell.severity == "warning"
        assert smell.evidence["call_count"] == 25
        assert smell.evidence["threshold"] == 20

    def test_no_chatty_when_below_threshold(self) -> None:
        """Test no detection when calls are below threshold."""
        session = create_test_session()

        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=15, total_tokens=3000)

        detector = SmellDetector()
        smells = detector.analyze(session)

        chatty_smells = [s for s in smells if s.pattern == "CHATTY"]
        assert len(chatty_smells) == 0

    def test_custom_chatty_threshold(self) -> None:
        """Test custom chatty threshold."""
        session = create_test_session()

        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=15, total_tokens=3000)

        # Lower threshold to 10
        thresholds = SmellThresholds(chatty_call_threshold=10)
        detector = SmellDetector(thresholds=thresholds)
        smells = detector.analyze(session)

        chatty_smells = [s for s in smells if s.pattern == "CHATTY"]
        assert len(chatty_smells) == 1


# ============================================================================
# LOW_CACHE_HIT Pattern Tests
# ============================================================================


class TestLowCacheHitDetection:
    """Tests for LOW_CACHE_HIT smell detection."""

    def test_detects_low_cache_hit(self) -> None:
        """Test detection of low cache hit rate (<30%)."""
        session = create_test_session(
            input_tokens=10000,
            output_tokens=5000,
            cache_read=1000,  # Only 9% hit rate (1000 / (1000 + 10000))
            cache_created=5000,
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        low_cache_smells = [s for s in smells if s.pattern == "LOW_CACHE_HIT"]
        assert len(low_cache_smells) == 1

        smell = low_cache_smells[0]
        assert smell.tool is None  # Session-level smell
        assert smell.evidence["hit_rate_percent"] < 30.0

    def test_no_low_cache_when_good_hit_rate(self) -> None:
        """Test no detection when cache hit rate is good."""
        session = create_test_session(
            input_tokens=5000,
            output_tokens=3000,
            cache_read=10000,  # 67% hit rate (10000 / (10000 + 5000))
            cache_created=2000,
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        low_cache_smells = [s for s in smells if s.pattern == "LOW_CACHE_HIT"]
        assert len(low_cache_smells) == 0

    def test_no_low_cache_when_no_cache_activity(self) -> None:
        """Test no detection when there's no cache activity."""
        session = create_test_session(
            input_tokens=10000,
            output_tokens=5000,
            cache_read=0,
            cache_created=0,
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        low_cache_smells = [s for s in smells if s.pattern == "LOW_CACHE_HIT"]
        assert len(low_cache_smells) == 0

    def test_low_cache_severity_levels(self) -> None:
        """Test severity levels based on how low the hit rate is."""
        # Very low hit rate (<10%) should be warning
        session = create_test_session(
            input_tokens=10000,
            output_tokens=5000,
            cache_read=500,  # 4.7% hit rate
            cache_created=5000,
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        low_cache_smells = [s for s in smells if s.pattern == "LOW_CACHE_HIT"]
        assert len(low_cache_smells) == 1
        assert low_cache_smells[0].severity == "warning"


# ============================================================================
# Integration Tests
# ============================================================================


class TestSmellDetectorIntegration:
    """Integration tests for SmellDetector."""

    def test_detect_smells_convenience_function(self) -> None:
        """Test the detect_smells convenience function."""
        session = create_test_session()
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=25, total_tokens=5000)

        smells = detect_smells(session)

        assert isinstance(smells, list)
        chatty_smells = [s for s in smells if s.pattern == "CHATTY"]
        assert len(chatty_smells) == 1

    def test_detect_smells_with_custom_thresholds(self) -> None:
        """Test detect_smells with custom thresholds."""
        session = create_test_session()
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=15, total_tokens=3000)

        # Default threshold won't catch 15 calls
        smells_default = detect_smells(session)
        chatty_default = [s for s in smells_default if s.pattern == "CHATTY"]
        assert len(chatty_default) == 0

        # Custom threshold will
        custom = SmellThresholds(chatty_call_threshold=10)
        smells_custom = detect_smells(session, thresholds=custom)
        chatty_custom = [s for s in smells_custom if s.pattern == "CHATTY"]
        assert len(chatty_custom) == 1

    def test_multiple_smells_detected(self) -> None:
        """Test detection of multiple smells in one session."""
        session = create_test_session(
            input_tokens=1000,
            output_tokens=500,
            cache_read=100,
            cache_created=500,
        )
        # Session total = 1500, low cache hit

        # Add chatty tool that's also top consumer
        add_tool_to_session(session, "zen", "mcp__zen__chat", calls=25, total_tokens=1400)
        # This tool: 25 calls (CHATTY), 93% of MCP tokens (TOP_CONSUMER),
        # 93% of session (HIGH_MCP_SHARE)

        detector = SmellDetector()
        smells = detector.analyze(session)

        patterns = {s.pattern for s in smells}
        assert "CHATTY" in patterns
        assert "TOP_CONSUMER" in patterns
        assert "HIGH_MCP_SHARE" in patterns
        assert "LOW_CACHE_HIT" in patterns

    def test_empty_session_no_smells(self) -> None:
        """Test that an empty session produces no smells."""
        session = create_test_session()

        detector = SmellDetector()
        smells = detector.analyze(session)

        # May have LOW_CACHE_HIT if no cache activity, but check others
        non_cache_smells = [s for s in smells if s.pattern != "LOW_CACHE_HIT"]
        assert len(non_cache_smells) == 0


class TestSessionFinalizationIntegration:
    """Test smell detection during session finalization."""

    def test_finalize_session_populates_smells(self) -> None:
        """Test that finalize_session runs smell detection."""
        from mcp_audit.base_tracker import BaseTracker

        # Create a concrete test tracker
        class TestTracker(BaseTracker):
            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

            def start_tracking(self) -> None:
                pass

            def get_platform_metadata(self):
                return {}

            def _build_display_snapshot(self):
                pass

            def parse_event(self, event_data):
                return None

        tracker = TestTracker(project="test", platform="test-platform")

        # Add a chatty tool
        for _ in range(25):
            tracker.record_tool_call(
                tool_name="mcp__zen__chat",
                input_tokens=100,
                output_tokens=50,
            )

        session = tracker.finalize_session()

        # Smells should be populated
        assert hasattr(session, "smells")
        assert isinstance(session.smells, list)

        chatty_smells = [s for s in session.smells if s.pattern == "CHATTY"]
        assert len(chatty_smells) == 1


# ============================================================================
# v1.7.0 Pattern Tests (task-106.1)
# ============================================================================


def add_call_to_session(
    session: Session,
    server_name: str,
    tool_name: str,
    total_tokens: int = 100,
    content_hash: str = None,
    platform_data: dict = None,
    cache_read_tokens: int = 0,
    timestamp: "datetime" = None,
) -> None:
    """Add a call with full details to a session's call history."""
    from datetime import datetime, timezone
    from mcp_audit.base_tracker import Call

    if server_name not in session.server_sessions:
        session.server_sessions[server_name] = ServerSession(server=server_name)

    server = session.server_sessions[server_name]
    if tool_name not in server.tools:
        server.tools[tool_name] = ToolStats()

    # Calculate session-level index (across all tools)
    total_calls = sum(
        sum(len(ts.call_history) for ts in ss.tools.values())
        for ss in session.server_sessions.values()
    )

    tool_stats = server.tools[tool_name]
    call = Call(
        timestamp=timestamp or datetime.now(timezone.utc),
        tool_name=tool_name,
        server=server_name,
        index=total_calls,  # Session-level index
        total_tokens=total_tokens,
        input_tokens=total_tokens // 2,
        output_tokens=total_tokens // 2,
        content_hash=content_hash,
        platform_data=platform_data,
        cache_read_tokens=cache_read_tokens,
    )
    tool_stats.call_history.append(call)
    tool_stats.calls += 1
    tool_stats.total_tokens += total_tokens
    server.total_calls += 1
    server.total_tokens += total_tokens


class TestRedundantCallsDetection:
    """Tests for REDUNDANT_CALLS smell detection."""

    def test_detects_redundant_calls(self) -> None:
        """Test detection of calls with identical content_hash."""
        session = create_test_session()

        # Add calls with same content_hash
        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=500, content_hash="abc123def456"
        )
        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=500, content_hash="abc123def456"
        )
        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=500, content_hash="different_hash"
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        redundant_smells = [s for s in smells if s.pattern == "REDUNDANT_CALLS"]
        assert len(redundant_smells) == 1
        assert redundant_smells[0].evidence["duplicate_count"] == 2

    def test_no_redundant_when_unique(self) -> None:
        """Test no detection when all calls have unique hashes."""
        session = create_test_session()

        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=500, content_hash="hash1"
        )
        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=500, content_hash="hash2"
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        redundant_smells = [s for s in smells if s.pattern == "REDUNDANT_CALLS"]
        assert len(redundant_smells) == 0

    def test_no_redundant_when_no_hash(self) -> None:
        """Test no detection when calls have no content_hash."""
        session = create_test_session()

        add_call_to_session(session, "zen", "mcp__zen__chat", total_tokens=500, content_hash=None)
        add_call_to_session(session, "zen", "mcp__zen__chat", total_tokens=500, content_hash=None)

        detector = SmellDetector()
        smells = detector.analyze(session)

        redundant_smells = [s for s in smells if s.pattern == "REDUNDANT_CALLS"]
        assert len(redundant_smells) == 0


class TestExpensiveFailuresDetection:
    """Tests for EXPENSIVE_FAILURES smell detection."""

    def test_detects_expensive_failure(self) -> None:
        """Test detection of high-token failed calls."""
        session = create_test_session()

        add_call_to_session(
            session,
            "zen",
            "mcp__zen__thinkdeep",
            total_tokens=6000,
            platform_data={"error": "Connection timeout", "is_error": True},
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        failure_smells = [s for s in smells if s.pattern == "EXPENSIVE_FAILURES"]
        assert len(failure_smells) == 1
        assert failure_smells[0].severity == "high"
        assert failure_smells[0].evidence["tokens"] == 6000

    def test_no_expensive_failure_when_small(self) -> None:
        """Test no detection when failed call is below threshold."""
        session = create_test_session()

        add_call_to_session(
            session,
            "zen",
            "mcp__zen__chat",
            total_tokens=1000,  # Below 5000 threshold
            platform_data={"error": "Some error"},
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        failure_smells = [s for s in smells if s.pattern == "EXPENSIVE_FAILURES"]
        assert len(failure_smells) == 0

    def test_no_expensive_failure_when_success(self) -> None:
        """Test no detection when call succeeded."""
        session = create_test_session()

        add_call_to_session(
            session,
            "zen",
            "mcp__zen__thinkdeep",
            total_tokens=10000,
            platform_data={"status": "success"},
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        failure_smells = [s for s in smells if s.pattern == "EXPENSIVE_FAILURES"]
        assert len(failure_smells) == 0


class TestUnderutilizedServerDetection:
    """Tests for UNDERUTILIZED_SERVER smell detection."""

    def test_detects_underutilized_server(self) -> None:
        """Test detection of server with low tool utilization."""
        session = create_test_session()

        # Add one tool being used
        add_tool_to_session(
            session, "backlog", "mcp__backlog__task_view", calls=5, total_tokens=1000
        )

        # Add zombie tools (available but unused)
        session.zombie_tools["backlog"] = [
            "mcp__backlog__task_create",
            "mcp__backlog__task_edit",
            "mcp__backlog__task_delete",
            "mcp__backlog__task_list",
            "mcp__backlog__task_search",
            "mcp__backlog__document_view",
            "mcp__backlog__document_create",
            "mcp__backlog__document_edit",
            "mcp__backlog__document_list",
        ]  # 1 used out of 10 = 10% - at threshold

        detector = SmellDetector()
        smells = detector.analyze(session)

        underutilized_smells = [s for s in smells if s.pattern == "UNDERUTILIZED_SERVER"]
        # 10% is at threshold, should trigger if <10%
        # Let's add more zombie tools to go below 10%
        session.zombie_tools["backlog"].append("mcp__backlog__extra_tool")  # 1/11 = 9%

        smells = detector.analyze(session)
        underutilized_smells = [s for s in smells if s.pattern == "UNDERUTILIZED_SERVER"]
        assert len(underutilized_smells) == 1
        assert "backlog" in underutilized_smells[0].description

    def test_detects_zero_usage_server(self) -> None:
        """Test detection of server with zero usage."""
        session = create_test_session()

        # Server with tools but no usage
        session.zombie_tools["unused-server"] = ["tool1", "tool2", "tool3"]

        detector = SmellDetector()
        smells = detector.analyze(session)

        underutilized_smells = [s for s in smells if s.pattern == "UNDERUTILIZED_SERVER"]
        assert len(underutilized_smells) == 1
        assert underutilized_smells[0].evidence["used_tools"] == 0


class TestBurstPatternDetection:
    """Tests for BURST_PATTERN smell detection."""

    def test_detects_burst_pattern(self) -> None:
        """Test detection of rapid tool calls."""
        from datetime import datetime, timezone, timedelta

        session = create_test_session()

        # Add 6 calls within 500ms (under 1 second threshold)
        base_time = datetime.now(timezone.utc)
        for i in range(6):
            add_call_to_session(
                session,
                "zen",
                "mcp__zen__chat",
                total_tokens=100,
                timestamp=base_time
                + timedelta(milliseconds=i * 100),  # 0, 100, 200, 300, 400, 500ms
            )

        detector = SmellDetector()
        smells = detector.analyze(session)

        burst_smells = [s for s in smells if s.pattern == "BURST_PATTERN"]
        assert len(burst_smells) == 1
        assert burst_smells[0].evidence["call_count"] == 6

    def test_no_burst_when_spread_out(self) -> None:
        """Test no detection when calls are spread over time."""
        from datetime import datetime, timezone, timedelta

        session = create_test_session()

        # Add 6 calls spread over 6 seconds
        base_time = datetime.now(timezone.utc)
        for i in range(6):
            add_call_to_session(
                session,
                "zen",
                "mcp__zen__chat",
                total_tokens=100,
                timestamp=base_time + timedelta(seconds=i),  # 1 second apart
            )

        detector = SmellDetector()
        smells = detector.analyze(session)

        burst_smells = [s for s in smells if s.pattern == "BURST_PATTERN"]
        assert len(burst_smells) == 0


class TestLargePayloadDetection:
    """Tests for LARGE_PAYLOAD smell detection."""

    def test_detects_large_payload(self) -> None:
        """Test detection of large token calls."""
        session = create_test_session()

        add_call_to_session(
            session, "zen", "mcp__zen__thinkdeep", total_tokens=15000  # Above 10K threshold
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        large_smells = [s for s in smells if s.pattern == "LARGE_PAYLOAD"]
        assert len(large_smells) == 1
        assert large_smells[0].evidence["tokens"] == 15000

    def test_no_large_payload_when_small(self) -> None:
        """Test no detection when calls are below threshold."""
        session = create_test_session()

        add_call_to_session(
            session, "zen", "mcp__zen__chat", total_tokens=5000  # Below 10K threshold
        )

        detector = SmellDetector()
        smells = detector.analyze(session)

        large_smells = [s for s in smells if s.pattern == "LARGE_PAYLOAD"]
        assert len(large_smells) == 0


class TestSequentialReadsDetection:
    """Tests for SEQUENTIAL_READS smell detection."""

    def test_detects_sequential_reads(self) -> None:
        """Test detection of consecutive read operations."""
        from datetime import datetime, timezone

        session = create_test_session()

        # Add 4 consecutive Read calls
        for i in range(4):
            add_call_to_session(
                session, "builtin", "Read", total_tokens=500, timestamp=datetime.now(timezone.utc)
            )

        detector = SmellDetector()
        smells = detector.analyze(session)

        sequential_smells = [s for s in smells if s.pattern == "SEQUENTIAL_READS"]
        assert len(sequential_smells) == 1
        assert sequential_smells[0].evidence["read_count"] == 4

    def test_no_sequential_reads_when_interrupted(self) -> None:
        """Test no detection when reads are interrupted by other calls."""
        from datetime import datetime, timezone

        session = create_test_session()

        # Add 2 reads, then a write, then 2 more reads
        add_call_to_session(session, "builtin", "Read", total_tokens=500)
        add_call_to_session(session, "builtin", "Read", total_tokens=500)
        add_call_to_session(session, "builtin", "Write", total_tokens=500)  # Interrupts
        add_call_to_session(session, "builtin", "Read", total_tokens=500)
        add_call_to_session(session, "builtin", "Read", total_tokens=500)

        detector = SmellDetector()
        smells = detector.analyze(session)

        sequential_smells = [s for s in smells if s.pattern == "SEQUENTIAL_READS"]
        assert len(sequential_smells) == 0  # No sequence of 3+


class TestCacheMissStreakDetection:
    """Tests for CACHE_MISS_STREAK smell detection."""

    def test_detects_cache_miss_streak(self) -> None:
        """Test detection of consecutive cache misses."""
        session = create_test_session()

        # Add 6 calls with no cache hits
        for i in range(6):
            add_call_to_session(
                session,
                "zen",
                "mcp__zen__chat",
                total_tokens=500,
                cache_read_tokens=0,  # No cache hit
            )

        detector = SmellDetector()
        smells = detector.analyze(session)

        miss_smells = [s for s in smells if s.pattern == "CACHE_MISS_STREAK"]
        assert len(miss_smells) == 1
        assert miss_smells[0].evidence["miss_count"] == 6

    def test_no_miss_streak_when_cache_hits(self) -> None:
        """Test no detection when there are cache hits."""
        session = create_test_session()

        # Add calls with cache hits interspersed
        for i in range(6):
            add_call_to_session(
                session,
                "zen",
                "mcp__zen__chat",
                total_tokens=500,
                cache_read_tokens=100 if i % 2 == 0 else 0,  # Every other has cache hit
            )

        detector = SmellDetector()
        smells = detector.analyze(session)

        miss_smells = [s for s in smells if s.pattern == "CACHE_MISS_STREAK"]
        assert len(miss_smells) == 0


class TestNewThresholdsConfiguration:
    """Tests for v1.7.0 threshold configuration."""

    def test_new_default_thresholds(self) -> None:
        """Test default values for new thresholds."""
        thresholds = SmellThresholds()

        assert thresholds.redundant_call_min_duplicates == 2
        assert thresholds.expensive_failure_token_threshold == 5000
        assert thresholds.underutilized_server_percent == 10.0
        assert thresholds.burst_pattern_calls == 5
        assert thresholds.burst_pattern_window_ms == 1000
        assert thresholds.large_payload_tokens == 10000
        assert thresholds.sequential_read_threshold == 3
        assert thresholds.cache_miss_streak_threshold == 5

    def test_custom_new_thresholds(self) -> None:
        """Test custom values for new thresholds."""
        thresholds = SmellThresholds(
            large_payload_tokens=5000,
            burst_pattern_calls=3,
        )

        assert thresholds.large_payload_tokens == 5000
        assert thresholds.burst_pattern_calls == 3
        # Others should be default
        assert thresholds.redundant_call_min_duplicates == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
