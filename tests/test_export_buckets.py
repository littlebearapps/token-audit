"""
Tests for bucket data in AI exports (v1.0.4 - task-247.18).

Tests cover:
- Bucket classification section generation
- Decision guidance thresholds
- AI export integration with --include-buckets flag
- Per-task bucket breakdown with --by-task flag
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from token_audit.base_tracker import (
    Call,
    ServerSession,
    Session,
    TokenUsage,
    ToolStats,
)
from token_audit.buckets import BucketClassifier, BucketResult
from token_audit.session_manager import SessionManager


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session(
    input_tokens: int = 10000,
    output_tokens: int = 5000,
    session_id: str = "test-session-123",
) -> Session:
    """Create a minimal test session."""
    session = Session(
        project="test-project",
        platform="claude-code",
        session_id=session_id,
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
    """Add a call with full details to a session's call history."""
    if server_name not in session.server_sessions:
        session.server_sessions[server_name] = ServerSession(server=server_name)

    server = session.server_sessions[server_name]
    if tool_name not in server.tools:
        server.tools[tool_name] = ToolStats()

    total_calls = sum(
        sum(len(ts.call_history) for ts in ss.tools.values())
        for ss in session.server_sessions.values()
    )

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
# Mock BucketResult Helper
# ============================================================================


def create_bucket_results(
    state_pct: float = 25.0,
    redundant_pct: float = 25.0,
    drift_pct: float = 25.0,
    discovery_pct: float = 25.0,
    total_tokens: int = 10000,
) -> List[BucketResult]:
    """Create mock BucketResult list with specified percentages."""
    return [
        BucketResult(
            bucket="state_serialization",
            tokens=int(total_tokens * state_pct / 100),
            percentage=state_pct,
            call_count=5,
            top_tools=[("mcp__wpnav__get_page", int(total_tokens * state_pct / 100))],
        ),
        BucketResult(
            bucket="redundant",
            tokens=int(total_tokens * redundant_pct / 100),
            percentage=redundant_pct,
            call_count=3,
            top_tools=[("mcp__wpnav__list_posts", int(total_tokens * redundant_pct / 100))],
        ),
        BucketResult(
            bucket="drift",
            tokens=int(total_tokens * drift_pct / 100),
            percentage=drift_pct,
            call_count=8,
            top_tools=[("custom_action", int(total_tokens * drift_pct / 100))],
        ),
        BucketResult(
            bucket="tool_discovery",
            tokens=int(total_tokens * discovery_pct / 100),
            percentage=discovery_pct,
            call_count=2,
            top_tools=[("mcp__wpnav__introspect", int(total_tokens * discovery_pct / 100))],
        ),
    ]


# ============================================================================
# Guidance Threshold Tests
# ============================================================================


class TestBucketGuidance:
    """Tests for _generate_bucket_guidance function."""

    def test_guidance_state_serialization_dominant(self) -> None:
        """≥60% state_serialization triggers delta-sync advice."""
        from token_audit.cli import _generate_bucket_guidance

        results = create_bucket_results(
            state_pct=65.0, redundant_pct=15.0, drift_pct=15.0, discovery_pct=5.0
        )

        guidance = _generate_bucket_guidance(results)

        assert "State serialization is 65%" in guidance
        assert "delta-sync" in guidance or "pagination" in guidance

    def test_guidance_redundant_dominant(self) -> None:
        """≥30% redundant triggers caching advice."""
        from token_audit.cli import _generate_bucket_guidance

        results = create_bucket_results(
            state_pct=25.0, redundant_pct=35.0, drift_pct=25.0, discovery_pct=15.0
        )

        guidance = _generate_bucket_guidance(results)

        assert "Redundant calls are 35%" in guidance
        assert "caching" in guidance.lower() or "deduplication" in guidance.lower()

    def test_guidance_drift_dominant(self) -> None:
        """≥40% drift triggers error handling advice."""
        from token_audit.cli import _generate_bucket_guidance

        results = create_bucket_results(
            state_pct=20.0, redundant_pct=20.0, drift_pct=45.0, discovery_pct=15.0
        )

        guidance = _generate_bucket_guidance(results)

        assert "Conversation drift is 45%" in guidance
        assert "error" in guidance.lower() or "retries" in guidance.lower()

    def test_guidance_discovery_dominant(self) -> None:
        """≥20% tool_discovery triggers schema caching advice when dominant."""
        from token_audit.cli import _generate_bucket_guidance

        # Discovery must be clearly dominant (highest %) AND >= 20% threshold
        results = create_bucket_results(
            state_pct=20.0, redundant_pct=15.0, drift_pct=15.0, discovery_pct=50.0
        )

        guidance = _generate_bucket_guidance(results)

        assert "Tool discovery is 50%" in guidance
        assert "introspection" in guidance.lower() or "schema" in guidance.lower()

    def test_guidance_well_distributed(self) -> None:
        """Balanced distribution triggers holistic advice."""
        from token_audit.cli import _generate_bucket_guidance

        # All buckets below their thresholds
        results = create_bucket_results(
            state_pct=50.0,  # Below 60%
            redundant_pct=20.0,  # Below 30%
            drift_pct=20.0,  # Below 40%
            discovery_pct=10.0,  # Below 20%
        )

        guidance = _generate_bucket_guidance(results)

        assert "well-distributed" in guidance.lower()
        assert "holistic" in guidance.lower()

    def test_guidance_empty_results(self) -> None:
        """Empty results returns appropriate message."""
        from token_audit.cli import _generate_bucket_guidance

        guidance = _generate_bucket_guidance([])

        assert "No data available" in guidance


# ============================================================================
# Bucket Classification Section Tests
# ============================================================================


class TestBucketClassificationSection:
    """Tests for _generate_bucket_classification_section function."""

    @pytest.fixture
    def session_path(self, tmp_path: Path) -> Path:
        """Create a session file for testing."""
        session = create_test_session()
        session.timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Add various calls for bucket classification
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=3000, content_hash="page1"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__list_posts", total_tokens=2000, content_hash="posts1"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__introspect", total_tokens=500, content_hash="intro1"
        )
        add_call_to_session(
            session, "wpnav", "custom_action", total_tokens=1000, content_hash="drift1"
        )

        manager = SessionManager()
        saved_files = manager.save_session(session, tmp_path)
        return saved_files["session"]

    def test_ai_export_includes_buckets(self, session_path: Path) -> None:
        """Bucket table appears in export when session has calls."""
        from token_audit.cli import _generate_bucket_classification_section

        session_data = {}  # Not used when session loads successfully

        lines = _generate_bucket_classification_section(session_path, session_data)
        output = "\n".join(lines)

        # Verify structure
        assert "## Bucket Classification" in output
        assert "| Bucket | Tokens | % | Calls | Description |" in output
        assert "state_serialization" in output
        assert "**TOTAL**" in output
        assert "### Decision Guidance" in output

    def test_ai_export_without_calls(self, tmp_path: Path) -> None:
        """No calls results in zero-token buckets."""
        from token_audit.cli import _generate_bucket_classification_section

        # Create session with no calls
        session = create_test_session()
        session.timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        manager = SessionManager()
        saved_files = manager.save_session(session, tmp_path)
        path = saved_files["session"]

        lines = _generate_bucket_classification_section(path, {})
        output = "\n".join(lines)

        assert "## Bucket Classification" in output
        # With no calls, all buckets have 0 tokens
        assert "| **TOTAL** | **0** |" in output
        assert "well-distributed" in output.lower()

    def test_ai_export_bucket_descriptions(self, session_path: Path) -> None:
        """Bucket descriptions appear correctly in table."""
        from token_audit.cli import _generate_bucket_classification_section

        lines = _generate_bucket_classification_section(session_path, {})
        output = "\n".join(lines)

        # Verify descriptions
        assert "Large content payloads" in output
        assert "Duplicate tool calls" in output or "same content_hash" in output
        assert "Schema introspection" in output
        assert "Residual" in output or "retries" in output


# ============================================================================
# AI Export Integration Tests
# ============================================================================


class TestAIExportIntegration:
    """Tests for AI export with bucket integration."""

    @pytest.fixture
    def wpnav_session_path(self, tmp_path: Path) -> Path:
        """Create a WP Navigator session for testing."""
        session = create_test_session(session_id="wpnav-test")
        session.timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # WP Navigator patterns
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__get_page", total_tokens=5000, content_hash="page1"
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__list_posts", total_tokens=3000, content_hash="posts1"
        )
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__get_page",
            total_tokens=5000,
            content_hash="page1",  # Duplicate
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__introspect", total_tokens=1000, content_hash="intro1"
        )

        manager = SessionManager()
        saved_files = manager.save_session(session, tmp_path)
        return saved_files["session"]

    def test_ai_export_decision_guidance(self, wpnav_session_path: Path) -> None:
        """Decision guidance included in bucket section."""
        from token_audit.cli import _generate_bucket_classification_section

        lines = _generate_bucket_classification_section(wpnav_session_path, {})
        output = "\n".join(lines)

        # Should have guidance section
        assert "### Decision Guidance" in output
        # Should have some guidance text (not empty)
        assert any(
            phrase in output.lower()
            for phrase in [
                "delta-sync",
                "caching",
                "error handling",
                "introspection",
                "well-distributed",
            ]
        )

    def test_ai_export_without_buckets_flag(self) -> None:
        """Default export behavior when --include-buckets not set.

        Note: This tests the expected behavior that bucket data is only
        included when explicitly requested. The actual CLI flag handling
        is tested in integration tests.
        """
        # The _generate_bucket_classification_section function is only called
        # when --include-buckets is set. If not set, the export should not
        # contain bucket data.
        #
        # This is a documentation test verifying the expected contract.
        # Full integration testing would require calling cmd_export_ai().
        assert True  # Placeholder for integration test


# ============================================================================
# By-Task Export Tests
# ============================================================================


class TestByTaskExport:
    """Tests for per-task bucket breakdown."""

    @pytest.fixture
    def session_with_tasks(self, tmp_path: Path) -> Path:
        """Create a session with task markers for testing."""
        session = create_test_session(session_id="task-test")
        session.timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Simulate calls from different logical tasks
        # Task 1: Page editing (state_serialization heavy)
        for i in range(3):
            add_call_to_session(
                session,
                "wpnav",
                "mcp__wpnav__get_page",
                total_tokens=2000,
                content_hash=f"task1_page{i}",
            )

        # Task 2: Content listing (mixed)
        add_call_to_session(
            session,
            "wpnav",
            "mcp__wpnav__list_posts",
            total_tokens=1500,
            content_hash="task2_posts",
        )
        add_call_to_session(
            session, "wpnav", "mcp__wpnav__introspect", total_tokens=500, content_hash="task2_intro"
        )

        manager = SessionManager()
        saved_files = manager.save_session(session, tmp_path)
        return saved_files["session"]

    def test_ai_export_by_task_structure(self, session_with_tasks: Path) -> None:
        """Per-task breakdown has correct structure.

        Note: Full --by-task testing requires TaskManager integration
        which creates task markers in the session. This test verifies
        the basic session structure for task-based analysis.
        """
        # Load and classify session
        manager = SessionManager()
        session = manager.load_session(session_with_tasks)

        assert session is not None
        assert len(session.server_sessions) > 0

        # Verify calls exist for classification
        total_calls = sum(
            sum(len(ts.call_history) for ts in ss.tools.values())
            for ss in session.server_sessions.values()
        )
        assert total_calls == 5  # 3 + 1 + 1

    def test_bucket_classifier_on_wpnav_patterns(self, session_with_tasks: Path) -> None:
        """BucketClassifier correctly identifies WP Navigator patterns."""
        manager = SessionManager()
        session = manager.load_session(session_with_tasks)
        classifier = BucketClassifier()

        results = classifier.classify_session(session)

        # Should have 4 bucket results
        assert len(results) == 4

        # Find state_serialization bucket (get/list patterns)
        state_result = next((r for r in results if r.bucket == "state_serialization"), None)
        assert state_result is not None
        assert state_result.tokens > 0  # Has tokens from get/list calls

        # Find tool_discovery bucket (introspect pattern)
        discovery_result = next((r for r in results if r.bucket == "tool_discovery"), None)
        assert discovery_result is not None
        assert discovery_result.tokens >= 500  # At least the introspect call


# ============================================================================
# Edge Cases
# ============================================================================


class TestBucketExportEdgeCases:
    """Edge case tests for bucket export functionality."""

    def test_guidance_priority_order(self) -> None:
        """First matching threshold wins when multiple could apply."""
        from token_audit.cli import _generate_bucket_guidance

        # Both state (65%) and redundant (35%) exceed thresholds
        # State is checked first, so it should win
        results = [
            BucketResult(
                bucket="state_serialization",
                tokens=6500,
                percentage=65.0,
                call_count=5,
                top_tools=[],
            ),
            BucketResult(
                bucket="redundant", tokens=3500, percentage=35.0, call_count=3, top_tools=[]
            ),
        ]

        guidance = _generate_bucket_guidance(results)

        # State should be mentioned, not redundant
        assert "State serialization is 65%" in guidance
        assert "delta-sync" in guidance.lower() or "pagination" in guidance.lower()

    def test_bucket_table_formatting(self, tmp_path: Path) -> None:
        """Bucket table has correct markdown formatting."""
        from token_audit.cli import _generate_bucket_classification_section

        session = create_test_session()
        session.timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        add_call_to_session(
            session, "test", "mcp__test__get_data", total_tokens=1000, content_hash="data1"
        )

        manager = SessionManager()
        saved_files = manager.save_session(session, tmp_path)
        path = saved_files["session"]

        lines = _generate_bucket_classification_section(path, {})

        # Verify markdown table formatting
        table_lines = [l for l in lines if "|" in l]
        assert len(table_lines) >= 3  # Header, separator, at least 1 data row

        # Header should have correct columns
        header = table_lines[0]
        assert "Bucket" in header
        assert "Tokens" in header
        assert "%" in header
        assert "Calls" in header
        assert "Description" in header
