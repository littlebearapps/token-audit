"""
Tests for the 4-Bucket Token Classification System (v1.0.4 - task-247).

Tests cover:
- BucketThresholds configuration
- BucketResult dataclass and serialization
- Pattern matching for each bucket type
- Redundancy detection (content_hash based)
- Classification priority order
- Session aggregation
"""

from datetime import datetime, timezone

import pytest

from token_audit.base_tracker import (
    Call,
    ServerSession,
    Session,
    TokenUsage,
    ToolStats,
)
from token_audit.buckets import (
    BucketClassifier,
    BucketName,
    BucketResult,
    BucketThresholds,
    DEFAULT_BUCKET_PATTERNS,
    DEFAULT_BUCKET_THRESHOLDS,
    classify_session,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session(
    input_tokens: int = 10000,
    output_tokens: int = 5000,
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
        total_tokens=input_tokens + output_tokens,
    )
    return session


def add_call_to_session(
    session: Session,
    server_name: str,
    tool_name: str,
    total_tokens: int = 100,
    output_tokens: int = None,
    content_hash: str = None,
    timestamp: datetime = None,
) -> Call:
    """Add a call with full details to a session's call history.

    Returns the created Call for inspection in tests.
    """
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

    # Default output_tokens to half of total if not specified
    if output_tokens is None:
        output_tokens = total_tokens // 2
    input_tokens = total_tokens - output_tokens

    tool_stats = server.tools[tool_name]
    call = Call(
        timestamp=timestamp or datetime.now(timezone.utc),
        tool_name=tool_name,
        server=server_name,
        index=total_calls,
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        content_hash=content_hash,
    )
    tool_stats.call_history.append(call)
    tool_stats.calls += 1
    tool_stats.total_tokens += total_tokens
    server.total_calls += 1
    server.total_tokens += total_tokens

    return call


# ============================================================================
# BucketThresholds Tests
# ============================================================================


class TestBucketThresholds:
    """Tests for BucketThresholds configuration."""

    def test_default_thresholds(self) -> None:
        """Test default threshold values."""
        thresholds = BucketThresholds()

        assert thresholds.large_payload_threshold == 5000
        assert thresholds.redundant_min_occurrences == 2

    def test_custom_thresholds(self) -> None:
        """Test custom threshold values."""
        thresholds = BucketThresholds(
            large_payload_threshold=10000,
            redundant_min_occurrences=3,
        )

        assert thresholds.large_payload_threshold == 10000
        assert thresholds.redundant_min_occurrences == 3

    def test_default_thresholds_constant(self) -> None:
        """Test DEFAULT_BUCKET_THRESHOLDS constant."""
        assert DEFAULT_BUCKET_THRESHOLDS.large_payload_threshold == 5000
        assert DEFAULT_BUCKET_THRESHOLDS.redundant_min_occurrences == 2


# ============================================================================
# BucketResult Tests
# ============================================================================


class TestBucketResult:
    """Tests for BucketResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values for BucketResult."""
        result = BucketResult(bucket="drift")

        assert result.bucket == "drift"
        assert result.tokens == 0
        assert result.percentage == 0.0
        assert result.call_count == 0
        assert result.top_tools == []

    def test_to_dict(self) -> None:
        """Test JSON serialization."""
        result = BucketResult(
            bucket="state_serialization",
            tokens=5000,
            percentage=45.5555,
            call_count=10,
            top_tools=[("wpnav_get_page", 3000), ("wpnav_list_posts", 2000)],
        )

        data = result.to_dict()

        assert data["bucket"] == "state_serialization"
        assert data["tokens"] == 5000
        assert data["percentage"] == 45.56  # Rounded to 2 decimals
        assert data["call_count"] == 10
        assert len(data["top_tools"]) == 2
        assert data["top_tools"][0] == {"tool": "wpnav_get_page", "tokens": 3000}


# ============================================================================
# BucketName Tests
# ============================================================================


class TestBucketName:
    """Tests for BucketName constants."""

    def test_bucket_names(self) -> None:
        """Test bucket name constants."""
        assert BucketName.REDUNDANT == "redundant"
        assert BucketName.STATE_SERIALIZATION == "state_serialization"
        assert BucketName.TOOL_DISCOVERY == "tool_discovery"
        assert BucketName.DRIFT == "drift"

    def test_all_returns_priority_order(self) -> None:
        """Test BucketName.all() returns buckets in priority order."""
        all_buckets = BucketName.all()

        assert len(all_buckets) == 4
        assert all_buckets[0] == BucketName.REDUNDANT
        assert all_buckets[1] == BucketName.TOOL_DISCOVERY
        assert all_buckets[2] == BucketName.STATE_SERIALIZATION
        assert all_buckets[3] == BucketName.DRIFT


# ============================================================================
# Default Patterns Tests
# ============================================================================


class TestDefaultPatterns:
    """Tests for DEFAULT_BUCKET_PATTERNS constant."""

    def test_state_serialization_patterns_exist(self) -> None:
        """Test state_serialization patterns are defined."""
        patterns = DEFAULT_BUCKET_PATTERNS["state_serialization"]

        assert len(patterns) >= 5
        assert any("get" in p for p in patterns)
        assert any("list" in p for p in patterns)
        assert any("read" in p for p in patterns)

    def test_tool_discovery_patterns_exist(self) -> None:
        """Test tool_discovery patterns are defined."""
        patterns = DEFAULT_BUCKET_PATTERNS["tool_discovery"]

        assert len(patterns) >= 4
        assert any("introspect" in p for p in patterns)
        assert any("schema" in p for p in patterns)
        assert any("describe" in p for p in patterns)


# ============================================================================
# Pattern Matching Tests
# ============================================================================


class TestPatternMatching:
    """Tests for pattern matching logic."""

    def test_state_serialization_get_pattern(self) -> None:
        """Test *_get_* and *_get$ patterns match."""
        classifier = BucketClassifier()

        # Middle pattern: *_get_*
        assert classifier._matches_patterns("wpnav_get_page", "state_serialization")
        assert classifier._matches_patterns("mcp__wpnav__get_post", "state_serialization")
        # Ending pattern: *_get$
        assert classifier._matches_patterns("task_get", "state_serialization")
        assert classifier._matches_patterns("mcp__backlog__task_get", "state_serialization")

    def test_state_serialization_list_pattern(self) -> None:
        """Test *_list_* and *_list$ patterns match."""
        classifier = BucketClassifier()

        # Middle pattern: *_list_*
        assert classifier._matches_patterns("wpnav_list_pages", "state_serialization")
        # Ending pattern: *_list$
        assert classifier._matches_patterns("mcp__backlog__task_list", "state_serialization")
        assert classifier._matches_patterns("task_list", "state_serialization")

    def test_tool_discovery_introspect_pattern(self) -> None:
        """Test *_introspect* pattern matches."""
        classifier = BucketClassifier()

        assert classifier._matches_patterns("wpnav_introspect", "tool_discovery")
        assert classifier._matches_patterns("mcp__wpnav__introspect_schema", "tool_discovery")

    def test_tool_discovery_schema_pattern(self) -> None:
        """Test *_schema* pattern matches."""
        classifier = BucketClassifier()

        assert classifier._matches_patterns("get_schema", "tool_discovery")
        assert classifier._matches_patterns("mcp__server__schema_info", "tool_discovery")

    def test_case_insensitive_matching(self) -> None:
        """Test patterns are case-insensitive."""
        classifier = BucketClassifier()

        assert classifier._matches_patterns("WPNAV_GET_PAGE", "state_serialization")
        assert classifier._matches_patterns("Wpnav_Introspect", "tool_discovery")
        assert classifier._matches_patterns("MCP__Server__LIST_Items", "state_serialization")

    def test_no_match_returns_false(self) -> None:
        """Test non-matching patterns return False."""
        classifier = BucketClassifier()

        assert not classifier._matches_patterns("custom_tool", "state_serialization")
        assert not classifier._matches_patterns("do_something", "tool_discovery")

    def test_wpnav_patterns_match(self) -> None:
        """Test WP Navigator specific patterns match correctly."""
        classifier = BucketClassifier()

        # State serialization patterns
        assert classifier._matches_patterns("mcp__wpnav__get_page", "state_serialization")
        assert classifier._matches_patterns("mcp__wpnav__list_posts", "state_serialization")
        assert classifier._matches_patterns("mcp__wpnav__get_plugin", "state_serialization")

        # Tool discovery patterns
        assert classifier._matches_patterns("mcp__wpnav__introspect", "tool_discovery")


# ============================================================================
# Redundancy Classification Tests (Task 247.3)
# ============================================================================


class TestRedundancyClassification:
    """Tests for redundancy bucket (content_hash based)."""

    def test_first_occurrence_not_redundant(self) -> None:
        """Test first occurrence of hash is NOT marked redundant."""
        session = create_test_session()

        # Add two calls with same hash
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # First call (index 0) should NOT be redundant
        assert classifications[0].primary_bucket != BucketName.REDUNDANT
        # Second call (index 1) SHOULD be redundant
        assert classifications[1].primary_bucket == BucketName.REDUNDANT

    def test_duplicate_marked_redundant(self) -> None:
        """Test duplicate (2nd+ occurrence) is marked redundant."""
        session = create_test_session()

        # Add three calls with same hash
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # First is original, 2nd and 3rd are redundant
        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION
        assert classifications[1].primary_bucket == BucketName.REDUNDANT
        assert classifications[2].primary_bucket == BucketName.REDUNDANT

    def test_no_hash_not_redundant(self) -> None:
        """Test calls without content_hash are never redundant."""
        session = create_test_session()

        # Add calls without hash (content_hash=None)
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash=None
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash=None
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # Neither should be redundant (no hash to compare)
        assert classifications[0].primary_bucket != BucketName.REDUNDANT
        assert classifications[1].primary_bucket != BucketName.REDUNDANT

    def test_secondary_bucket_tracking(self) -> None:
        """Test redundant calls track secondary bucket."""
        session = create_test_session()

        # Add state serialization calls that are duplicates
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # Second call is redundant with state_serialization as secondary
        assert classifications[1].primary_bucket == BucketName.REDUNDANT
        assert classifications[1].secondary_bucket == BucketName.STATE_SERIALIZATION

    def test_custom_min_occurrences_threshold(self) -> None:
        """Test custom redundant_min_occurrences threshold."""
        session = create_test_session()

        # Add two calls with same hash
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )

        # With threshold=3, 2 occurrences should not trigger redundancy
        thresholds = BucketThresholds(redundant_min_occurrences=3)
        classifier = BucketClassifier(thresholds=thresholds)
        classifications = classifier.get_call_classifications(session)

        # Neither should be redundant (only 2 occurrences, need 3)
        assert classifications[0].primary_bucket != BucketName.REDUNDANT
        assert classifications[1].primary_bucket != BucketName.REDUNDANT


# ============================================================================
# State Serialization Classification Tests
# ============================================================================


class TestStateSerializationClassification:
    """Tests for state_serialization bucket."""

    def test_pattern_match_classifies_state(self) -> None:
        """Test tool name pattern match classifies as state."""
        session = create_test_session()

        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__get_page",
            total_tokens=100,  # Small payload, but pattern matches
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION

    def test_large_output_classifies_state(self) -> None:
        """Test large output_tokens classifies as state regardless of pattern."""
        session = create_test_session()

        # Tool name doesn't match patterns, but large output
        add_call_to_session(
            session,
            "custom",
            "custom_tool",
            total_tokens=6000,
            output_tokens=5500,  # > 5000 threshold
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION

    def test_small_output_no_pattern_not_state(self) -> None:
        """Test small output without pattern match is not state."""
        session = create_test_session()

        # No pattern match, small output
        add_call_to_session(session, "custom", "custom_tool", total_tokens=100, output_tokens=50)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket != BucketName.STATE_SERIALIZATION
        assert classifications[0].primary_bucket == BucketName.DRIFT

    def test_custom_large_payload_threshold(self) -> None:
        """Test custom large_payload_threshold."""
        session = create_test_session()

        add_call_to_session(session, "custom", "custom_tool", total_tokens=3000, output_tokens=2500)

        # With lower threshold, should be classified as state
        thresholds = BucketThresholds(large_payload_threshold=2000)
        classifier = BucketClassifier(thresholds=thresholds)
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION


# ============================================================================
# Tool Discovery Classification Tests
# ============================================================================


class TestToolDiscoveryClassification:
    """Tests for tool_discovery bucket."""

    def test_introspect_pattern(self) -> None:
        """Test *_introspect* pattern classifies as discovery."""
        session = create_test_session()

        add_call_to_session(session, "wpnav", "mcp__wpnav__introspect", total_tokens=500)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.TOOL_DISCOVERY

    def test_schema_pattern(self) -> None:
        """Test *_schema* pattern classifies as discovery."""
        session = create_test_session()

        add_call_to_session(session, "server", "get_schema", total_tokens=300)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.TOOL_DISCOVERY

    def test_describe_pattern(self) -> None:
        """Test *_describe* pattern classifies as discovery."""
        session = create_test_session()

        add_call_to_session(session, "server", "mcp__server__describe_tools", total_tokens=200)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.TOOL_DISCOVERY


# ============================================================================
# Drift Classification Tests
# ============================================================================


class TestDriftClassification:
    """Tests for drift bucket (default)."""

    def test_unmatched_call_is_drift(self) -> None:
        """Test unmatched tool name classifies as drift."""
        session = create_test_session()

        add_call_to_session(session, "custom", "do_something", total_tokens=100)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.DRIFT

    def test_small_custom_call_is_drift(self) -> None:
        """Test small custom call is drift."""
        session = create_test_session()

        add_call_to_session(session, "zen", "mcp__zen__chat", total_tokens=500, output_tokens=100)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.DRIFT


# ============================================================================
# Classification Priority Tests
# ============================================================================


class TestClassificationPriority:
    """Tests for classification priority order."""

    def test_redundant_beats_state(self) -> None:
        """Test redundant priority is higher than state_serialization."""
        session = create_test_session()

        # Two identical state serialization calls
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000, content_hash="hash123"
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # First is state (original), second is redundant (not state)
        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION
        assert classifications[1].primary_bucket == BucketName.REDUNDANT

    def test_redundant_beats_discovery(self) -> None:
        """Test redundant priority is higher than tool_discovery."""
        session = create_test_session()

        # Two identical introspection calls
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__introspect", total_tokens=500, content_hash="intro_hash"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__introspect", total_tokens=500, content_hash="intro_hash"
        )

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # First is discovery (original), second is redundant
        assert classifications[0].primary_bucket == BucketName.TOOL_DISCOVERY
        assert classifications[1].primary_bucket == BucketName.REDUNDANT
        assert classifications[1].secondary_bucket == BucketName.TOOL_DISCOVERY

    def test_discovery_beats_state_on_pattern(self) -> None:
        """Test tool_discovery is checked before state_serialization."""
        session = create_test_session()

        # A tool that might match both (hypothetically)
        # Using introspect pattern - should be discovery not state
        add_call_to_session(session, "server", "list_tools_introspect", total_tokens=1000)

        classifier = BucketClassifier()
        classifications = classifier.get_call_classifications(session)

        # Should be discovery (checked before state pattern matching)
        assert classifications[0].primary_bucket == BucketName.TOOL_DISCOVERY


# ============================================================================
# Session Classification Tests
# ============================================================================


class TestSessionClassification:
    """Tests for classify_session aggregation."""

    def test_empty_session(self) -> None:
        """Test classifying an empty session."""
        session = create_test_session()
        # No calls added

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        # Should return 4 buckets, all empty
        assert len(results) == 4
        for result in results:
            assert result.tokens == 0
            assert result.call_count == 0

    def test_all_buckets_represented(self) -> None:
        """Test all 4 buckets appear in results."""
        session = create_test_session()

        # Add one call of each type
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=100)
        add_call_to_session(session, "wpnav", "mcp__wpnav__introspect", total_tokens=100)
        add_call_to_session(session, "custom", "custom_tool", total_tokens=100)

        # Add duplicate for redundant
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=100, content_hash="dup_hash"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=100, content_hash="dup_hash"
        )

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        bucket_names = {r.bucket for r in results}
        assert bucket_names == {
            BucketName.REDUNDANT,
            BucketName.STATE_SERIALIZATION,
            BucketName.TOOL_DISCOVERY,
            BucketName.DRIFT,
        }

    def test_percentage_calculation(self) -> None:
        """Test percentage is calculated correctly."""
        session = create_test_session()

        # 3 calls: 1000, 1000, 1000 = 3000 total
        # 2 state, 1 drift
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000)
        add_call_to_session(session, "wpnav", "mcp__wpnav__list_posts", total_tokens=1000)
        add_call_to_session(session, "custom", "custom_tool", total_tokens=1000)

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        state_result = next(r for r in results if r.bucket == BucketName.STATE_SERIALIZATION)
        drift_result = next(r for r in results if r.bucket == BucketName.DRIFT)

        # State: 2000/3000 = 66.67%
        assert abs(state_result.percentage - 66.67) < 0.1
        # Drift: 1000/3000 = 33.33%
        assert abs(drift_result.percentage - 33.33) < 0.1

    def test_top_tools_ranking(self) -> None:
        """Test top_tools is sorted by tokens descending."""
        session = create_test_session()

        # Multiple state calls with different tokens
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=3000)
        add_call_to_session(session, "wpnav", "mcp__wpnav__list_posts", total_tokens=1000)
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_user", total_tokens=2000)

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        state_result = next(r for r in results if r.bucket == BucketName.STATE_SERIALIZATION)

        # Should be sorted: get_page (3000), get_user (2000), list_posts (1000)
        assert len(state_result.top_tools) == 3
        assert state_result.top_tools[0][0] == "mcp__wpnav__get_page"
        assert state_result.top_tools[0][1] == 3000
        assert state_result.top_tools[1][0] == "mcp__wpnav__get_user"
        assert state_result.top_tools[2][0] == "mcp__wpnav__list_posts"

    def test_top_tools_limited_to_5(self) -> None:
        """Test top_tools is limited to 5 entries."""
        session = create_test_session()

        # Add 7 different state tools
        for i in range(7):
            add_call_to_session(
                session, "wpnav", f"mcp__wpnav__get_item_{i}", total_tokens=100 * (i + 1)
            )

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        state_result = next(r for r in results if r.bucket == BucketName.STATE_SERIALIZATION)

        # Should only have top 5
        assert len(state_result.top_tools) == 5
        # Highest should be item_6 (700 tokens)
        assert state_result.top_tools[0][0] == "mcp__wpnav__get_item_6"

    def test_multiple_servers(self) -> None:
        """Test classification works across multiple servers."""
        session = create_test_session()

        # Add calls from different servers
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000)
        add_call_to_session(session, "backlog", "mcp__backlog__task_list", total_tokens=500)
        add_call_to_session(session, "zen", "mcp__zen__chat", total_tokens=500)

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        # wpnav and backlog should be state, zen should be drift
        state_result = next(r for r in results if r.bucket == BucketName.STATE_SERIALIZATION)
        drift_result = next(r for r in results if r.bucket == BucketName.DRIFT)

        assert state_result.tokens == 1500  # wpnav + backlog
        assert drift_result.tokens == 500  # zen

    def test_results_sorted_by_tokens_descending(self) -> None:
        """Test results are sorted by tokens descending."""
        session = create_test_session()

        # Create scenario where drift has most tokens
        add_call_to_session(session, "zen", "mcp__zen__chat", total_tokens=5000)
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000)

        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        # First result should have highest tokens
        assert results[0].tokens >= results[1].tokens
        # Drift should be first (5000 > 1000)
        assert results[0].bucket == BucketName.DRIFT


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunction:
    """Tests for classify_session convenience function."""

    def test_classify_session_function(self) -> None:
        """Test the module-level classify_session function."""
        session = create_test_session()

        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=1000)

        results = classify_session(session)

        assert len(results) == 4
        state_result = next(r for r in results if r.bucket == BucketName.STATE_SERIALIZATION)
        assert state_result.tokens == 1000

    def test_classify_session_with_custom_thresholds(self) -> None:
        """Test convenience function with custom thresholds."""
        session = create_test_session()

        # Large output that would normally be state
        add_call_to_session(session, "custom", "custom_tool", total_tokens=6000, output_tokens=5500)

        # With higher threshold, should be drift instead
        thresholds = BucketThresholds(large_payload_threshold=10000)
        results = classify_session(session, thresholds=thresholds)

        drift_result = next(r for r in results if r.bucket == BucketName.DRIFT)
        assert drift_result.tokens == 6000


# ============================================================================
# Custom Patterns Tests
# ============================================================================


class TestCustomPatterns:
    """Tests for custom pattern configuration."""

    def test_custom_patterns(self) -> None:
        """Test using custom patterns."""
        custom_patterns = {
            "state_serialization": [r".*_fetch_.*"],
            "tool_discovery": [r".*_discover_.*"],
        }

        session = create_test_session()

        add_call_to_session(session, "custom", "my_fetch_data", total_tokens=1000)
        add_call_to_session(session, "custom", "my_discover_tools", total_tokens=500)

        classifier = BucketClassifier(patterns=custom_patterns)
        classifications = classifier.get_call_classifications(session)

        assert classifications[0].primary_bucket == BucketName.STATE_SERIALIZATION
        assert classifications[1].primary_bucket == BucketName.TOOL_DISCOVERY

    def test_empty_patterns_defaults_to_drift(self) -> None:
        """Test empty patterns result in drift classification."""
        empty_patterns: dict = {
            "state_serialization": [],
            "tool_discovery": [],
        }

        session = create_test_session()
        add_call_to_session(session, "wpnav", "mcp__wpnav__get_page", total_tokens=100)

        classifier = BucketClassifier(patterns=empty_patterns)
        classifications = classifier.get_call_classifications(session)

        # Without patterns, should fall through to drift
        assert classifications[0].primary_bucket == BucketName.DRIFT
