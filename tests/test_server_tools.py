"""Tests for MCP server tool implementations.

These tests verify the wrapper functions in tools.py that expose
LiveTracker functionality via MCP tools.
"""

import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from token_audit.server import tools
from token_audit.server.live_tracker import LiveTracker
from token_audit.server.schemas import (
    GetMetricsOutput,
    ServerPlatform,
    SeverityLevel,
    StartTrackingOutput,
)
from token_audit.storage import StreamingStorage


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage(tmp_path: Path) -> StreamingStorage:
    """Create a StreamingStorage with a temporary directory."""
    return StreamingStorage(base_dir=tmp_path)


@pytest.fixture
def temp_tracker(temp_storage: StreamingStorage) -> LiveTracker:
    """Create a LiveTracker with temporary storage."""
    return LiveTracker(storage=temp_storage)


@pytest.fixture
def mock_tracker(temp_tracker: LiveTracker):
    """
    Patch the global tracker in tools module with a temp tracker.

    Yields the tracker and restores original after test.
    """
    original_tracker = tools._tracker
    tools._tracker = temp_tracker
    yield temp_tracker
    tools._tracker = original_tracker


# =============================================================================
# start_tracking Tests
# =============================================================================


class TestStartTracking:
    """Tests for the start_tracking tool."""

    def test_start_tracking_returns_output_model(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking returns StartTrackingOutput."""
        result = tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="test-project",
        )

        assert isinstance(result, StartTrackingOutput)

    def test_start_tracking_creates_session(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking creates an active session."""
        result = tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="my-project",
        )

        assert result.status == "active"
        assert result.session_id != ""
        assert result.platform == "claude_code"
        assert result.project == "my-project"
        assert result.started_at != ""
        assert "Now tracking" in result.message

    def test_start_tracking_claude_code(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking with claude_code platform."""
        result = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        assert result.platform == "claude_code"
        assert result.status == "active"

    def test_start_tracking_codex_cli(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking with codex_cli platform."""
        result = tools.start_tracking(platform=ServerPlatform.CODEX_CLI)

        assert result.platform == "codex_cli"
        assert result.status == "active"

    def test_start_tracking_gemini_cli(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking with gemini_cli platform."""
        result = tools.start_tracking(platform=ServerPlatform.GEMINI_CLI)

        assert result.platform == "gemini_cli"
        assert result.status == "active"

    def test_start_tracking_without_project(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking without project parameter."""
        result = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        assert result.project is None
        assert result.status == "active"

    def test_start_tracking_already_active(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking when session already active."""
        # Start first session
        first = tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="first-project",
        )

        # Try to start second session
        second = tools.start_tracking(
            platform=ServerPlatform.CODEX_CLI,
            project="second-project",
        )

        # Should return existing session info, not error
        assert second.status == "active"
        assert second.session_id == first.session_id
        assert second.platform == "claude_code"  # Original platform
        assert second.project == "first-project"  # Original project
        assert "already active" in second.message

    def test_start_tracking_exception_handling(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking handles exceptions gracefully."""
        # Make start_session raise an exception
        mock_tracker.start_session = MagicMock(side_effect=RuntimeError("Storage failure"))

        result = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        assert result.status == "error"
        assert result.session_id == ""
        assert "Failed to start tracking" in result.message
        assert "Storage failure" in result.message

    def test_start_tracking_session_id_format(self, mock_tracker: LiveTracker) -> None:
        """Test session_id has expected format (8 char short UUID)."""
        result = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        assert len(result.session_id) == 8
        # Should be alphanumeric (hex chars from UUID)
        assert result.session_id.replace("-", "").isalnum()

    def test_start_tracking_started_at_is_iso(self, mock_tracker: LiveTracker) -> None:
        """Test started_at is valid ISO 8601 timestamp."""
        result = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Should parse without error
        parsed = datetime.fromisoformat(result.started_at)
        assert isinstance(parsed, datetime)


# =============================================================================
# get_metrics Tests
# =============================================================================


class TestGetMetrics:
    """Tests for the get_metrics tool."""

    def test_get_metrics_returns_output_model(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics returns GetMetricsOutput."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        result = tools.get_metrics()

        assert isinstance(result, GetMetricsOutput)

    def test_get_metrics_no_session(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics with no active session."""
        result = tools.get_metrics()

        assert result.session_id == "none"
        assert result.tokens.total == 0
        assert result.cost_usd == 0.0
        assert result.call_count == 0

    def test_get_metrics_no_session_includes_no_session_smell(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test get_metrics shows NO_SESSION smell when no session."""
        result = tools.get_metrics(include_smells=True)

        assert len(result.smells) == 1
        assert result.smells[0].pattern == "NO_SESSION"
        assert result.smells[0].severity == SeverityLevel.INFO
        assert "start_tracking" in result.smells[0].description

    def test_get_metrics_no_session_without_smells(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics with include_smells=False shows no smells."""
        result = tools.get_metrics(include_smells=False)

        assert result.smells == []

    def test_get_metrics_with_active_session(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics returns session metrics."""
        tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="test-proj",
        )

        result = tools.get_metrics()

        assert result.session_id != "none"
        assert result.tokens.input == 0  # No tool calls yet
        assert result.cost_usd == 0.0

    def test_get_metrics_after_tool_calls(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics reflects recorded tool calls."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Record some tool calls directly on tracker
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=500,
            cache_read=50,
            cache_write=25,
            cost_usd=0.01,
        )

        result = tools.get_metrics()

        assert result.tokens.input == 100
        assert result.tokens.output == 500
        assert result.tokens.cache_read == 50
        assert result.tokens.cache_write == 25
        assert result.tokens.total == 650  # input + output + cache_read
        assert result.cost_usd == pytest.approx(0.01)
        assert result.call_count == 1
        assert result.tool_count == 1

    def test_get_metrics_rates(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics calculates rate metrics."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=1000,
        )

        result = tools.get_metrics()

        assert result.rates.duration_minutes >= 0
        assert result.rates.tokens_per_min >= 0
        assert result.rates.calls_per_min >= 0

    def test_get_metrics_cache_hit_ratio(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics calculates cache hit ratio."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=100,  # 50% of total input is cached
        )

        result = tools.get_metrics()

        assert result.cache.hit_ratio == pytest.approx(0.5, abs=0.01)
        assert result.cache.savings_tokens == 100

    def test_get_metrics_cache_savings_usd_with_model(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics calculates savings_usd using per-model pricing."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        # Use a known model with pricing
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=1_000_000,  # 1M tokens to make calculation clearer
            model="claude-sonnet-4-5-20250929",  # Input: $3.00/MTok, Cache: $0.30/MTok
        )

        result = tools.get_metrics()

        # Savings = 1M tokens * ($3.00 - $0.30) / 1M = $2.70
        assert result.cache.savings_usd == pytest.approx(2.70, abs=0.01)
        # Verify model_usage now tracks cache_read
        assert "claude-sonnet-4-5-20250929" in result.model_usage
        assert result.model_usage["claude-sonnet-4-5-20250929"]["cache_read"] == 1_000_000

    def test_get_metrics_cache_savings_usd_fallback(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics uses fallback rate when model pricing unavailable."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        # No model specified - should use fallback rate
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=1_000_000,  # 1M tokens
        )

        result = tools.get_metrics()

        # Fallback rate is $2.70/MTok (Claude Sonnet)
        # Savings = 1M tokens * $2.70 / 1M = $2.70
        assert result.cache.savings_usd == pytest.approx(2.70, abs=0.01)

    def test_get_metrics_cache_savings_usd_multiple_models(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics sums savings across multiple models."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        # Claude Sonnet: $3.00 input, $0.30 cache = $2.70 savings rate
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=500_000,
            model="claude-sonnet-4-5-20250929",
        )
        # Claude Haiku: $1.00 input, $0.10 cache = $0.90 savings rate
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            cache_read=500_000,
            model="claude-haiku-4-5-20251001",
        )

        result = tools.get_metrics()

        # Sonnet: 500K * $2.70/M = $1.35
        # Haiku: 500K * $0.90/M = $0.45
        # Total: $1.80
        assert result.cache.savings_usd == pytest.approx(1.80, abs=0.01)

    def test_get_metrics_model_usage_includes_cache(self, mock_tracker: LiveTracker) -> None:
        """Test model_usage now tracks cache_read and cache_write per model."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=50,
            cache_read=200,
            cache_write=75,
            model="claude-sonnet-4-5-20250929",
        )

        result = tools.get_metrics()

        model_data = result.model_usage["claude-sonnet-4-5-20250929"]
        assert model_data["tokens_in"] == 100
        assert model_data["tokens_out"] == 50
        assert model_data["cache_read"] == 200
        assert model_data["cache_write"] == 75
        assert model_data["calls"] == 1

    def test_get_metrics_with_smells(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics includes recorded smells."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_smell(
            pattern="CHATTY",
            severity="medium",
            tool="mcp__zen__chat",
            description="Too many calls",
        )

        result = tools.get_metrics(include_smells=True)

        assert len(result.smells) == 1
        assert result.smells[0].pattern == "CHATTY"
        assert result.smells[0].severity == SeverityLevel.MEDIUM
        assert result.smells[0].tool == "mcp__zen__chat"

    def test_get_metrics_without_smells(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics excludes smells when include_smells=False."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_smell(pattern="TEST", severity="low")

        result = tools.get_metrics(include_smells=False)

        assert result.smells == []

    def test_get_metrics_model_usage(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics includes per-model usage."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
            tokens_out=200,
        )

        result = tools.get_metrics(include_breakdown=True)

        assert "claude-sonnet-4-20250514" in result.model_usage

    def test_get_metrics_without_breakdown(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics excludes model_usage when include_breakdown=False."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
        )

        result = tools.get_metrics(include_breakdown=False)

        assert result.model_usage == {}

    def test_get_metrics_by_session_id(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics with explicit session_id."""
        started = tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        result = tools.get_metrics(session_id=started.session_id)

        assert result.session_id == started.session_id

    def test_get_metrics_invalid_session_id(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics with non-existent session_id."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        result = tools.get_metrics(session_id="nonexistent")

        # Should return empty metrics, not error
        assert result.session_id == "nonexistent"
        assert result.tokens.total == 0

    def test_get_metrics_smell_severity_conversion(self, mock_tracker: LiveTracker) -> None:
        """Test smell severity strings convert to enum correctly."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Record smells with different severity strings
        for sev in ["critical", "high", "medium", "low", "info"]:
            mock_tracker.record_smell(pattern=f"TEST_{sev.upper()}", severity=sev)

        result = tools.get_metrics(include_smells=True)

        severities = [s.severity for s in result.smells]
        assert SeverityLevel.CRITICAL in severities
        assert SeverityLevel.HIGH in severities
        assert SeverityLevel.MEDIUM in severities
        assert SeverityLevel.LOW in severities
        assert SeverityLevel.INFO in severities


# =============================================================================
# get_tracker Tests
# =============================================================================


class TestGetTracker:
    """Tests for the get_tracker helper function."""

    def test_get_tracker_returns_global(self) -> None:
        """Test get_tracker returns the global tracker instance."""
        tracker = tools.get_tracker()
        assert tracker is tools._tracker

    def test_get_tracker_is_live_tracker(self) -> None:
        """Test get_tracker returns a LiveTracker instance."""
        tracker = tools.get_tracker()
        assert isinstance(tracker, LiveTracker)


# =============================================================================
# Integration Tests
# =============================================================================


class TestToolsIntegration:
    """Integration tests for tools working together."""

    def test_start_then_get_metrics(self, mock_tracker: LiveTracker) -> None:
        """Test typical flow: start_tracking -> get_metrics."""
        # Start tracking
        start_result = tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="integration-test",
        )
        assert start_result.status == "active"

        # Get metrics
        metrics = tools.get_metrics()

        assert metrics.session_id == start_result.session_id
        assert metrics.tokens.total == 0
        assert metrics.smells == []  # No smells yet

    def test_metrics_update_with_activity(self, mock_tracker: LiveTracker) -> None:
        """Test metrics update as tool calls are recorded."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Initial metrics
        m1 = tools.get_metrics()
        assert m1.call_count == 0

        # Record activity
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
        )

        # Updated metrics
        m2 = tools.get_metrics()
        assert m2.call_count == 1
        assert m2.tokens.input == 100

    def test_multiple_tool_calls_accumulate(self, mock_tracker: LiveTracker) -> None:
        """Test multiple tool calls accumulate in metrics."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        for i in range(5):
            mock_tracker.record_tool_call(
                tool=f"Tool{i}",
                server="builtin",
                tokens_in=100,
                tokens_out=200,
            )

        result = tools.get_metrics()

        assert result.call_count == 5
        assert result.tool_count == 5
        assert result.tokens.input == 500
        assert result.tokens.output == 1000


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_get_metrics_zero_duration(self, mock_tracker: LiveTracker) -> None:
        """Test get_metrics handles zero/very small duration."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Get metrics immediately (very small duration)
        result = tools.get_metrics()

        # Should not raise division by zero
        assert result.rates.tokens_per_min >= 0
        assert result.rates.calls_per_min >= 0

    def test_get_metrics_zero_input_tokens(self, mock_tracker: LiveTracker) -> None:
        """Test cache hit ratio with zero input tokens."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # No tool calls = zero input tokens
        result = tools.get_metrics()

        # Should not raise division by zero
        assert result.cache.hit_ratio == 0.0

    def test_smell_with_missing_fields(self, mock_tracker: LiveTracker) -> None:
        """Test handling smells with missing optional fields."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Record smell without tool or description
        mock_tracker.record_smell(pattern="MINIMAL", severity="low")

        result = tools.get_metrics()

        assert len(result.smells) == 1
        assert result.smells[0].pattern == "MINIMAL"
        assert result.smells[0].tool is None

    def test_empty_project_string(self, mock_tracker: LiveTracker) -> None:
        """Test start_tracking with empty string project."""
        result = tools.start_tracking(
            platform=ServerPlatform.CLAUDE_CODE,
            project="",  # Empty string, not None
        )

        assert result.status == "active"
        assert result.project == ""

    def test_model_usage_multiple_models(self, mock_tracker: LiveTracker) -> None:
        """Test model_usage with multiple different models."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
        )
        mock_tracker.record_tool_call(
            tool="Write",
            server="builtin",
            model="claude-opus-4-20250514",
            tokens_in=200,
        )

        result = tools.get_metrics()

        assert len(result.model_usage) == 2
        assert "claude-sonnet-4-20250514" in result.model_usage
        assert "claude-opus-4-20250514" in result.model_usage


# =============================================================================
# analyze_config Tests
# =============================================================================


class TestAnalyzeConfig:
    """Tests for analyze_config tool."""

    @pytest.fixture
    def mock_allowed_dirs(self, tmp_path: Path):
        """Patch ALLOWED_CONFIG_DIRS to include tmp_path/.claude for testing."""
        from token_audit.server import security

        mock_dirs = [
            tmp_path / ".claude",
            tmp_path / ".codex",
            tmp_path / ".gemini",
        ]
        # Ensure the directories exist
        for d in mock_dirs:
            d.mkdir(parents=True, exist_ok=True)

        with patch.object(security, "ALLOWED_CONFIG_DIRS", mock_dirs):
            yield tmp_path

    @pytest.fixture
    def mcp_config_file(self, mock_allowed_dirs: Path) -> Path:
        """Create a test MCP config file with servers and pinned config."""
        import json

        config = {
            "mcpServers": {
                "zen": {
                    "command": "node",
                    "args": ["/path/to/zen-server"],
                },
                "custom-local": {
                    "command": "python",
                    "args": ["/Users/test/my-custom-server.py"],
                },
                "brave-search": {
                    "command": "npx",
                    "args": ["@brave/brave-search-mcp-server"],
                },
            },
            "pinned_servers": ["zen"],
        }

        # Create in mocked .claude directory
        config_path = mock_allowed_dirs / ".claude" / ".mcp.json"
        config_path.write_text(json.dumps(config))
        return config_path

    @pytest.fixture
    def mcp_config_with_pinned_flag(self, mock_allowed_dirs: Path) -> Path:
        """Create a test MCP config with pinned: true flag on a server."""
        import json

        config = {
            "mcpServers": {
                "my-server": {
                    "command": "node",
                    "args": ["./server.js"],
                    "pinned": True,
                    "notes": "My important server",
                },
                "other-server": {
                    "command": "npx",
                    "args": ["some-package"],
                },
            },
        }

        # Create in mocked .claude directory
        config_path = mock_allowed_dirs / ".claude" / ".mcp.json"
        config_path.write_text(json.dumps(config))
        return config_path

    def test_analyze_config_returns_pinned_servers(self, mcp_config_file: Path) -> None:
        """Test analyze_config returns pinned_servers list."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_file),
        )

        # Should have pinned_servers field
        assert hasattr(result, "pinned_servers")
        assert isinstance(result.pinned_servers, list)

        # Should include zen (explicit) and custom-local (auto-detected)
        pinned_names = {p.name for p in result.pinned_servers}
        assert "zen" in pinned_names  # Explicitly pinned

    def test_analyze_config_pinned_server_info_fields(self, mcp_config_file: Path) -> None:
        """Test PinnedServerInfo has correct fields."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_file),
        )

        # Find zen in pinned servers
        zen_pinned = next((p for p in result.pinned_servers if p.name == "zen"), None)

        assert zen_pinned is not None
        assert zen_pinned.name == "zen"
        assert zen_pinned.source == "explicit_config"
        assert (
            "pinned_servers" in zen_pinned.reason.lower() or "explicit" in zen_pinned.reason.lower()
        )

    def test_analyze_config_auto_detected_pinned(self, mcp_config_file: Path) -> None:
        """Test auto-detection of custom/local servers as pinned."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_file),
        )

        # custom-local should be auto-detected (has /Users/ in path)
        custom_pinned = next((p for p in result.pinned_servers if p.name == "custom-local"), None)

        assert custom_pinned is not None
        assert custom_pinned.source == "custom_path"
        assert custom_pinned.name == "custom-local"

    def test_analyze_config_pinned_flag_detection(self, mcp_config_with_pinned_flag: Path) -> None:
        """Test detection of pinned: true flag on servers."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_with_pinned_flag),
        )

        # my-server should be detected via pinned: true flag
        my_server_pinned = next((p for p in result.pinned_servers if p.name == "my-server"), None)

        assert my_server_pinned is not None
        assert my_server_pinned.source == "explicit_flag"

    def test_analyze_config_returns_context_tax(self, mcp_config_file: Path) -> None:
        """Test analyze_config returns context_tax_estimate."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_file),
        )

        # Should have context_tax_estimate field
        assert hasattr(result, "context_tax_estimate")
        assert isinstance(result.context_tax_estimate, int)

        # With 3 servers, should have > 0 context tax
        assert result.context_tax_estimate > 0

    def test_analyze_config_context_tax_is_reasonable(self, mcp_config_file: Path) -> None:
        """Test context_tax_estimate is in reasonable range."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mcp_config_file),
        )

        # 3 servers should have between 500 and 20000 tokens
        # (based on schema_analyzer estimates)
        assert result.context_tax_estimate >= 500
        assert result.context_tax_estimate <= 20000

    def test_analyze_config_file_not_found(self, mock_allowed_dirs: Path) -> None:
        """Test analyze_config handles missing file gracefully."""
        from token_audit.server.schemas import ServerPlatform

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(mock_allowed_dirs / ".claude" / "nonexistent.json"),
        )

        assert result.server_count == 0
        assert result.pinned_servers == []
        assert result.context_tax_estimate == 0
        assert any(i.category == "file_not_found" for i in result.issues)

    def test_analyze_config_parse_error(self, mock_allowed_dirs: Path) -> None:
        """Test analyze_config handles invalid JSON gracefully."""
        from token_audit.server.schemas import ServerPlatform

        bad_config = mock_allowed_dirs / ".claude" / ".mcp.json"
        bad_config.write_text("{ invalid json }")

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(bad_config),
        )

        assert result.server_count == 0
        assert result.pinned_servers == []
        assert result.context_tax_estimate == 0
        assert any(i.category == "parse_error" for i in result.issues)

    def test_analyze_config_empty_config(self, mock_allowed_dirs: Path) -> None:
        """Test analyze_config handles empty config."""
        import json
        from token_audit.server.schemas import ServerPlatform

        empty_config = mock_allowed_dirs / ".claude" / ".mcp.json"
        empty_config.write_text(json.dumps({"mcpServers": {}}))

        result = tools.analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path=str(empty_config),
        )

        assert result.server_count == 0
        assert result.pinned_servers == []
        # Empty config may still have baseline overhead from SchemaAnalyzer
        # Just verify it returns a non-negative value
        assert result.context_tax_estimate >= 0


# ============================================================================
# Task 151: analyze_session pinned server usage tests
# ============================================================================


class TestAnalyzeSessionPinnedServers:
    """Tests for analyze_session pinned server usage functionality."""

    def test_analyze_session_has_pinned_server_usage_field(self, mock_tracker: LiveTracker) -> None:
        """Test that analyze_session returns pinned_server_usage field."""
        # Start a session
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE, project="test-151")

        result = tools.analyze_session()

        # Check that pinned_server_usage field exists and is a list
        assert hasattr(result, "pinned_server_usage")
        assert isinstance(result.pinned_server_usage, list)

    def test_analyze_session_no_session_returns_empty_pinned_usage(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test analyze_session with no session returns empty pinned_server_usage."""
        result = tools.analyze_session()

        assert result.pinned_server_usage == []

    def test_pinned_server_usage_structure(self) -> None:
        """Test PinnedServerUsage has correct field structure."""
        from token_audit.server.schemas import PinnedServerUsage

        # Create a sample PinnedServerUsage
        usage = PinnedServerUsage(
            name="test-server",
            calls=10,
            tokens=5000,
            percentage=25.5,
            is_active=True,
        )

        assert usage.name == "test-server"
        assert usage.calls == 10
        assert usage.tokens == 5000
        assert usage.percentage == 25.5
        assert usage.is_active is True

    def test_pinned_server_usage_defaults(self) -> None:
        """Test PinnedServerUsage default values."""
        from token_audit.server.schemas import PinnedServerUsage

        usage = PinnedServerUsage(name="test", calls=0)

        assert usage.tokens == 0
        assert usage.percentage == 0.0
        assert usage.is_active is True


# ============================================================================
# Task 151: get_recommendations pinned server context tests
# ============================================================================


class TestGetRecommendationsPinnedServers:
    """Tests for get_recommendations pinned server context functionality."""

    def test_recommendation_has_pinned_server_fields(self) -> None:
        """Test that Recommendation schema has pinned server fields."""
        from token_audit.server.schemas import Recommendation, SeverityLevel

        rec = Recommendation(
            id="test-1",
            severity=SeverityLevel.MEDIUM,
            category="test",
            title="Test Recommendation",
            action="Do something",
            impact="Some impact",
            confidence=0.8,
        )

        # Check default values
        assert rec.affects_pinned_server is False
        assert rec.pinned_server_name is None

    def test_recommendation_with_pinned_server(self) -> None:
        """Test Recommendation with pinned server fields populated."""
        from token_audit.server.schemas import Recommendation, SeverityLevel

        rec = Recommendation(
            id="test-2",
            severity=SeverityLevel.HIGH,
            category="test",
            title="Pinned Server Recommendation",
            action="Optimize pinned server",
            impact="Better performance",
            confidence=0.9,
            affects_pinned_server=True,
            pinned_server_name="my-pinned-server",
        )

        assert rec.affects_pinned_server is True
        assert rec.pinned_server_name == "my-pinned-server"

    def test_get_recommendations_accepts_pinned_servers_param(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test that get_recommendations accepts pinned_servers parameter."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE, project="test-151")

        # Should not raise when called with pinned_servers
        result = tools.get_recommendations(pinned_servers=["server-a", "server-b"])

        assert hasattr(result, "recommendations")
        assert isinstance(result.recommendations, list)

    def test_get_recommendations_no_session_with_pinned_servers(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test get_recommendations with no session returns empty list."""
        result = tools.get_recommendations(pinned_servers=["server-a"])

        assert result.recommendations == []
        assert result.total_potential_savings_tokens == 0


# ============================================================================
# Task 157: get_trends tests
# ============================================================================


class TestGetTrends:
    """Tests for get_trends tool functionality."""

    def test_get_trends_returns_output_model(self) -> None:
        """Test that get_trends returns GetTrendsOutput model."""
        from token_audit.server.schemas import GetTrendsOutput, TrendPeriod

        result = tools.get_trends()

        assert isinstance(result, GetTrendsOutput)
        assert hasattr(result, "period")
        assert hasattr(result, "sessions_analyzed")
        assert hasattr(result, "patterns")
        assert hasattr(result, "top_affected_tools")
        assert hasattr(result, "overall_trend")
        assert hasattr(result, "recommendations")

    def test_get_trends_period_default(self) -> None:
        """Test get_trends uses LAST_30_DAYS by default."""
        from token_audit.server.schemas import TrendPeriod

        result = tools.get_trends()

        assert result.period == TrendPeriod.LAST_30_DAYS.value

    def test_get_trends_period_mapping(self) -> None:
        """Test get_trends maps all period values correctly."""
        from token_audit.server.schemas import TrendPeriod

        for period in TrendPeriod:
            result = tools.get_trends(period=period)
            assert result.period == period.value

    def test_get_trends_platform_filter(self) -> None:
        """Test get_trends accepts platform filter."""
        from token_audit.server.schemas import TrendPeriod

        result = tools.get_trends(
            period=TrendPeriod.LAST_7_DAYS,
            platform=ServerPlatform.CLAUDE_CODE,
        )

        # Should not raise
        assert isinstance(result.sessions_analyzed, int)

    def test_get_trends_empty_sessions_returns_stable(self, tmp_path: Path) -> None:
        """Test get_trends with no sessions returns stable trend."""
        from token_audit.smell_aggregator import SmellAggregator

        # Create aggregator with empty directory
        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=0,
                aggregated_smells=[],
            )

            result = tools.get_trends()

            assert result.overall_trend == "stable"
            assert result.sessions_analyzed == 0
            assert result.patterns == []

    def test_get_trends_empty_has_recommendation(self, tmp_path: Path) -> None:
        """Test get_trends with no sessions includes helpful recommendation."""
        from token_audit.smell_aggregator import SmellAggregator

        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=0,
                aggregated_smells=[],
            )

            result = tools.get_trends()

            assert len(result.recommendations) > 0
            assert "token-audit collect" in result.recommendations[0]

    def test_get_trends_overall_trend_calculation(self) -> None:
        """Test overall trend is calculated from aggregated smells."""
        from token_audit.smell_aggregator import SmellAggregator, AggregatedSmell

        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            # Create mock result with worsening trends
            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=10,
                sessions_with_smells=8,
                aggregated_smells=[
                    AggregatedSmell(
                        pattern="CHATTY",
                        total_occurrences=5,
                        sessions_affected=4,
                        total_sessions=10,
                        frequency_percent=40.0,
                        trend="worsening",
                        trend_change_percent=25.0,
                    ),
                    AggregatedSmell(
                        pattern="LOW_CACHE_HIT",
                        total_occurrences=3,
                        sessions_affected=3,
                        total_sessions=10,
                        frequency_percent=30.0,
                        trend="stable",
                        trend_change_percent=5.0,
                    ),
                ],
            )

            result = tools.get_trends()

            # With 1 worsening and 0 improving, overall should be worsening
            assert result.overall_trend == "worsening"

    def test_get_trends_patterns_conversion(self) -> None:
        """Test AggregatedSmell is correctly converted to SmellTrend."""
        from token_audit.smell_aggregator import SmellAggregator, AggregatedSmell
        from token_audit.server.schemas import SmellTrend

        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=5,
                sessions_with_smells=3,
                aggregated_smells=[
                    AggregatedSmell(
                        pattern="TOP_CONSUMER",
                        total_occurrences=7,
                        sessions_affected=3,
                        total_sessions=5,
                        frequency_percent=60.0,
                        trend="improving",
                        trend_change_percent=-15.5,
                    ),
                ],
            )

            result = tools.get_trends()

            assert len(result.patterns) == 1
            pattern = result.patterns[0]
            assert isinstance(pattern, SmellTrend)
            assert pattern.pattern == "TOP_CONSUMER"
            assert pattern.occurrences == 7
            assert pattern.trend == "improving"
            assert pattern.change_percent == -15.5

    def test_get_trends_top_affected_tools(self) -> None:
        """Test top_affected_tools are extracted from smell patterns."""
        from token_audit.smell_aggregator import SmellAggregator, AggregatedSmell

        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=5,
                aggregated_smells=[
                    AggregatedSmell(
                        pattern="CHATTY",
                        total_occurrences=10,
                        sessions_affected=4,
                        total_sessions=5,
                        frequency_percent=80.0,
                        trend="stable",
                        top_tools=[("Read", 5), ("Grep", 3)],
                    ),
                    AggregatedSmell(
                        pattern="LOW_CACHE_HIT",
                        total_occurrences=5,
                        sessions_affected=2,
                        total_sessions=5,
                        frequency_percent=40.0,
                        trend="stable",
                        top_tools=[("Read", 2), ("Write", 1)],
                    ),
                ],
            )

            result = tools.get_trends()

            # Read should be first (5+2=7 occurrences)
            assert "Read" in result.top_affected_tools
            assert len(result.top_affected_tools) <= 5

    def test_get_trends_recommendations_for_worsening(self) -> None:
        """Test recommendations are generated for worsening patterns."""
        from token_audit.smell_aggregator import SmellAggregator, AggregatedSmell

        with patch.object(SmellAggregator, "aggregate") as mock_aggregate:
            from token_audit.smell_aggregator import SmellAggregationResult
            from datetime import date

            mock_aggregate.return_value = SmellAggregationResult(
                query_start=date.today(),
                query_end=date.today(),
                total_sessions=10,
                aggregated_smells=[
                    AggregatedSmell(
                        pattern="EXPENSIVE_FAILURES",
                        total_occurrences=15,
                        sessions_affected=6,
                        total_sessions=10,
                        frequency_percent=60.0,
                        trend="worsening",
                        trend_change_percent=50.0,
                    ),
                ],
            )

            result = tools.get_trends()

            # Should have a recommendation addressing the worsening pattern
            assert len(result.recommendations) > 0
            assert "EXPENSIVE_FAILURES" in result.recommendations[0]
            assert "worsening" in result.recommendations[0].lower()


class TestGetTrendsHelpers:
    """Tests for get_trends helper functions."""

    def test_calculate_overall_trend_empty(self) -> None:
        """Test _calculate_overall_trend with empty list returns stable."""
        result = tools._calculate_overall_trend([])
        assert result == "stable"

    def test_calculate_overall_trend_all_improving(self) -> None:
        """Test overall trend when all patterns are improving."""
        from token_audit.smell_aggregator import AggregatedSmell

        smells = [
            AggregatedSmell(pattern="A", trend="improving", trend_change_percent=-20.0),
            AggregatedSmell(pattern="B", trend="improving", trend_change_percent=-10.0),
        ]
        result = tools._calculate_overall_trend(smells)
        assert result == "improving"

    def test_calculate_overall_trend_all_worsening(self) -> None:
        """Test overall trend when all patterns are worsening."""
        from token_audit.smell_aggregator import AggregatedSmell

        smells = [
            AggregatedSmell(pattern="A", trend="worsening", trend_change_percent=30.0),
            AggregatedSmell(pattern="B", trend="worsening", trend_change_percent=20.0),
        ]
        result = tools._calculate_overall_trend(smells)
        assert result == "worsening"

    def test_calculate_overall_trend_mixed(self) -> None:
        """Test overall trend with mixed patterns."""
        from token_audit.smell_aggregator import AggregatedSmell

        # 2 worsening, 1 improving -> worsening
        smells = [
            AggregatedSmell(pattern="A", trend="worsening", trend_change_percent=20.0),
            AggregatedSmell(pattern="B", trend="worsening", trend_change_percent=10.0),
            AggregatedSmell(pattern="C", trend="improving", trend_change_percent=-15.0),
        ]
        result = tools._calculate_overall_trend(smells)
        assert result == "worsening"

    def test_calculate_overall_trend_equal_balanced(self) -> None:
        """Test overall trend when improving equals worsening returns stable."""
        from token_audit.smell_aggregator import AggregatedSmell

        smells = [
            AggregatedSmell(pattern="A", trend="worsening", trend_change_percent=20.0),
            AggregatedSmell(pattern="B", trend="improving", trend_change_percent=-20.0),
        ]
        result = tools._calculate_overall_trend(smells)
        assert result == "stable"

    def test_generate_trend_recommendations_empty(self) -> None:
        """Test _generate_trend_recommendations with no smells."""
        result = tools._generate_trend_recommendations([])
        assert len(result) > 0
        assert "Collect more session data" in result[0]

    def test_generate_trend_recommendations_stable_patterns(self) -> None:
        """Test recommendations for stable patterns only."""
        from token_audit.smell_aggregator import AggregatedSmell

        smells = [
            AggregatedSmell(
                pattern="LOW_CACHE_HIT",
                trend="stable",
                trend_change_percent=0.0,
                frequency_percent=30.0,
                total_sessions=10,
                sessions_affected=3,
            ),
        ]
        result = tools._generate_trend_recommendations(smells)
        # Should mention stable or continue current practices
        assert any("stable" in r.lower() or "continue" in r.lower() for r in result)

    def test_generate_trend_recommendations_high_frequency(self) -> None:
        """Test recommendations for high-frequency stable patterns."""
        from token_audit.smell_aggregator import AggregatedSmell

        smells = [
            AggregatedSmell(
                pattern="CHATTY",
                trend="stable",
                trend_change_percent=0.0,
                frequency_percent=75.0,  # >50% triggers monitor recommendation
                total_sessions=10,
                sessions_affected=7,
            ),
        ]
        result = tools._generate_trend_recommendations(smells)
        # Should recommend monitoring the persistent pattern
        assert any("Monitor" in r or "CHATTY" in r for r in result)

    def test_generate_trend_recommendations_max_five(self) -> None:
        """Test recommendations are capped at 5."""
        from token_audit.smell_aggregator import AggregatedSmell

        # Create many worsening patterns
        smells = [
            AggregatedSmell(
                pattern=f"PATTERN_{i}",
                trend="worsening",
                trend_change_percent=float(10 + i),
                total_sessions=10,
                sessions_affected=i + 1,
            )
            for i in range(10)
        ]
        result = tools._generate_trend_recommendations(smells)
        assert len(result) <= 5


# ============================================================================
# Task 160: analyze_session model_usage tests
# ============================================================================


class TestAnalyzeSessionModelUsage:
    """Tests for analyze_session model_usage functionality."""

    def test_analyze_session_includes_model_usage(self, mock_tracker: LiveTracker) -> None:
        """Test analyze_session returns per-model usage breakdown."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=50,
            model="claude-sonnet-4-20250514",
        )
        result = tools.analyze_session()

        assert "claude-sonnet-4-20250514" in result.model_usage
        assert result.model_usage["claude-sonnet-4-20250514"]["tokens_in"] == 100
        assert result.model_usage["claude-sonnet-4-20250514"]["tokens_out"] == 50

    def test_analyze_session_model_usage_multiple_models(self, mock_tracker: LiveTracker) -> None:
        """Test model_usage tracks multiple models correctly."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)

        # Record calls with different models
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            tokens_out=50,
            model="claude-sonnet-4-20250514",
        )
        mock_tracker.record_tool_call(
            tool="Write",
            server="builtin",
            tokens_in=200,
            tokens_out=100,
            model="claude-opus-4-20250514",
        )

        result = tools.analyze_session()

        assert len(result.model_usage) == 2
        assert "claude-sonnet-4-20250514" in result.model_usage
        assert "claude-opus-4-20250514" in result.model_usage
        assert result.model_usage["claude-sonnet-4-20250514"]["calls"] == 1
        assert result.model_usage["claude-opus-4-20250514"]["calls"] == 1

    def test_analyze_session_model_usage_excluded_when_disabled(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test model_usage is empty when include_model_usage=False."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        mock_tracker.record_tool_call(
            tool="Read",
            server="builtin",
            tokens_in=100,
            model="claude-sonnet-4-20250514",
        )

        result = tools.analyze_session(include_model_usage=False)

        assert result.model_usage == {}

    def test_analyze_session_no_session_returns_empty_model_usage(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test analyze_session with no session returns empty model_usage."""
        result = tools.analyze_session()

        assert result.model_usage == {}


# ============================================================================
# Task 161: analyze_session zombie_tools tests
# ============================================================================


class TestAnalyzeSessionZombieTools:
    """Tests for analyze_session zombie tool detection."""

    def test_analyze_session_zombie_tools_field_exists(self, mock_tracker: LiveTracker) -> None:
        """Test zombie_tools field exists in output."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        result = tools.analyze_session()

        assert hasattr(result, "zombie_tools")
        assert isinstance(result.zombie_tools, list)

    def test_analyze_session_returns_empty_zombie_list_no_config(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test zombie_tools is empty when no zombie config exists."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        result = tools.analyze_session()

        # Without a zombie config, should return empty list
        assert result.zombie_tools == []

    def test_analyze_session_no_session_returns_empty_zombie_tools(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test analyze_session with no session returns empty zombie_tools."""
        result = tools.analyze_session()

        assert result.zombie_tools == []

    def test_analyze_session_zombie_tools_excluded_when_disabled(
        self, mock_tracker: LiveTracker
    ) -> None:
        """Test zombie_tools is empty when include_zombie_tools=False."""
        tools.start_tracking(platform=ServerPlatform.CLAUDE_CODE)
        result = tools.analyze_session(include_zombie_tools=False)

        assert result.zombie_tools == []
