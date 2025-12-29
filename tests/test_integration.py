#!/usr/bin/env python3
"""
End-to-End Integration Tests for MCP Audit

Tests complete workflow: event parsing → session tracking → persistence → analysis
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from token_audit.base_tracker import BaseTracker, SCHEMA_VERSION
from token_audit.claude_code_adapter import ClaudeCodeAdapter
from token_audit.codex_cli_adapter import CodexCLIAdapter
from token_audit.session_manager import SessionManager
from token_audit.normalization import normalize_tool_name, normalize_server_name


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_claude_code_events():
    """Sample Claude Code debug.log events"""
    return [
        {
            "id": "msg_001",
            "type": "assistant",
            "message": {
                "id": "msg_001",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_001",
                        "name": "mcp__zen__chat",
                        "input": {"prompt": "test query"},
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 20,
                    "cache_read_input_tokens": 500,
                },
            },
        },
        {
            "id": "msg_002",
            "type": "assistant",
            "message": {
                "id": "msg_002",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_002",
                        "name": "mcp__brave-search__web",
                        "input": {"query": "search query"},
                    }
                ],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 1000,
                },
            },
        },
    ]


@pytest.fixture
def sample_codex_cli_events():
    """Sample Codex CLI output events (actual JSONL format).

    Since task-69.8, MCP tool calls require both function_call (registers pending)
    and function_call_output (completes with estimated tokens) events.
    """
    return [
        # turn_context event for model detection
        {
            "timestamp": "2025-11-04T11:38:27.361Z",
            "type": "turn_context",
            "payload": {
                "cwd": "/test/project",
                "model": "gpt-5-codex",
            },
        },
        # token_count event for token usage
        {
            "timestamp": "2025-11-04T11:38:30.056Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 300,
                        "cached_input_tokens": 1500,
                        "output_tokens": 150,
                        "reasoning_output_tokens": 50,
                        "total_tokens": 2000,
                    },
                    "last_token_usage": {
                        "input_tokens": 300,
                        "cached_input_tokens": 1500,
                        "output_tokens": 150,
                        "reasoning_output_tokens": 50,
                        "total_tokens": 2000,
                    },
                },
            },
        },
        # MCP tool call event (zen server with -mcp suffix)
        {
            "timestamp": "2025-11-04T11:38:31.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "mcp__zen-mcp__chat",  # Codex format with -mcp suffix
                "arguments": '{"prompt": "test query"}',
                "call_id": "call_abc123",
            },
        },
        # function_call_output for zen chat (task-69.8: completes MCP tool call)
        {
            "timestamp": "2025-11-04T11:38:31.500Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_abc123",
                "output": "Response from zen chat\nWall time: 0.5 seconds",
            },
        },
        # MCP tool call event (brave-search server with -mcp suffix)
        {
            "timestamp": "2025-11-04T11:38:32.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "mcp__brave-search-mcp__web",  # Codex format with -mcp suffix
                "arguments": '{"query": "search query"}',
                "call_id": "call_def456",
            },
        },
        # function_call_output for brave search (task-69.8: completes MCP tool call)
        {
            "timestamp": "2025-11-04T11:38:32.500Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_def456",
                "output": "Search results from brave\nWall time: 1.0 seconds",
            },
        },
    ]


# ============================================================================
# Cross-Platform Normalization Tests
# ============================================================================


class TestCrossPlatformNormalization:
    """Test that different platforms normalize to same tool names"""

    def test_claude_code_vs_codex_cli_normalization(self) -> None:
        """Test Claude Code and Codex CLI produce same normalized names"""
        # Claude Code format
        claude_tool = "mcp__zen__chat"
        # Codex CLI format
        codex_tool = "mcp__zen-mcp__chat"

        # Both should normalize to same name
        assert normalize_tool_name(claude_tool) == normalize_tool_name(codex_tool)
        assert normalize_server_name(claude_tool) == normalize_server_name(codex_tool)

    def test_normalized_tools_aggregate_correctly(self) -> None:
        """Test different platform formats aggregate to same tool"""
        tools = [
            "mcp__zen__chat",  # Claude Code
            "mcp__zen-mcp__chat",  # Codex CLI
            "mcp__zen__debug",  # Claude Code
            "mcp__zen-mcp__debug",  # Codex CLI
        ]

        normalized = set(normalize_tool_name(t) for t in tools)

        # Should only have 2 unique tools
        assert len(normalized) == 2
        assert "mcp__zen__chat" in normalized
        assert "mcp__zen__debug" in normalized


# ============================================================================
# Event Parsing Tests
# ============================================================================


class TestEventParsing:
    """Test event parsing across platforms"""

    def test_claude_code_event_parsing(self, sample_claude_code_events, tmp_path) -> None:
        """Test parsing Claude Code events"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        for event in sample_claude_code_events:
            result = adapter.parse_event(json.dumps(event))

            if result:
                tool_name, usage = result
                assert tool_name.startswith("mcp__")
                assert usage["input_tokens"] > 0

    def test_codex_cli_event_parsing(self, sample_codex_cli_events) -> None:
        """Test parsing Codex CLI events.

        Since task-69.8, function_call events return None (register pending).
        MCP tool calls complete when function_call_output arrives with estimated tokens.
        """
        adapter = CodexCLIAdapter(project="test", codex_args=[])

        mcp_calls_found = 0
        token_events_found = 0

        for event in sample_codex_cli_events:
            result = adapter.parse_event(json.dumps(event))

            if result:
                tool_name, usage = result

                if tool_name == "__session__":
                    # Token count event
                    token_events_found += 1
                    assert usage["input_tokens"] > 0 or usage["cache_read_tokens"] > 0
                else:
                    # MCP tool call from function_call_output (task-69.8)
                    mcp_calls_found += 1
                    assert tool_name.startswith("mcp__")
                    # Now includes estimated tokens
                    assert usage["is_estimated"] is True
                    assert usage["estimation_method"] == "tiktoken"
                    assert usage["input_tokens"] > 0

        # Verify model was detected from turn_context
        assert adapter.detected_model == "gpt-5-codex"

        # Verify we found expected event types
        assert token_events_found >= 1, "Should find at least one token_count event"
        assert mcp_calls_found >= 1, "Should find at least one MCP tool call"

    def test_unrecognized_event_handling(self, tmp_path) -> None:
        """Test handling of unrecognized events"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Invalid JSON
        result = adapter.parse_event("{ invalid json }")
        assert result is None

        # Valid JSON but not a tool event
        result = adapter.parse_event('{"type": "other"}')
        assert result is None


# ============================================================================
# Session Tracking Tests
# ============================================================================


class TestSessionTracking:
    """Test complete session tracking workflow"""

    def test_claude_code_session_tracking(self, sample_claude_code_events, tmp_path) -> None:
        """Test complete Claude Code session tracking"""
        adapter = ClaudeCodeAdapter(project="test-project", claude_dir=tmp_path)

        # Parse events and record calls
        for event in sample_claude_code_events:
            result = adapter.parse_event(json.dumps(event))
            if result:
                tool_name, usage = result
                content_hash = adapter.compute_content_hash(usage.get("tool_params", {}))
                adapter.record_tool_call(
                    tool_name=tool_name,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_created_tokens=usage["cache_created_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                    content_hash=content_hash,
                )

        # Finalize session
        session = adapter.finalize_session()

        # Verify session data
        assert session.project == "test-project"
        assert session.platform == "claude-code"
        assert session.mcp_tool_calls.total_calls == 2
        assert session.mcp_tool_calls.unique_tools == 2
        assert session.token_usage.total_tokens > 0

    def test_codex_cli_session_tracking(self, sample_codex_cli_events) -> None:
        """Test complete Codex CLI session tracking.

        Since task-69.8, function_call events return None (register pending).
        MCP tool calls complete when function_call_output arrives with estimated tokens.
        """
        adapter = CodexCLIAdapter(project="test-project", codex_args=[])

        # Parse events and record calls using adapter's _process_tool_call
        for event in sample_codex_cli_events:
            result = adapter.parse_event(json.dumps(event))
            if result:
                tool_name, usage = result
                # Use adapter's processing (handles both session and MCP)
                adapter._process_tool_call(tool_name, usage)

        # Finalize session
        session = adapter.finalize_session()

        # Verify session data
        assert session.project == "test-project"
        assert session.platform == "codex-cli"
        assert session.mcp_tool_calls.total_calls == 2
        assert session.mcp_tool_calls.unique_tools == 2

        # Verify model was detected
        assert adapter.detected_model == "gpt-5-codex"

        # Verify token tracking from token_count events
        assert session.token_usage.input_tokens > 0
        assert session.token_usage.cache_read_tokens > 0

        # Verify tools normalized (Codex -mcp suffix stripped)
        zen_session = session.server_sessions.get("zen")
        assert zen_session is not None
        assert "mcp__zen__chat" in zen_session.tools

        # Verify token estimation metadata (task-69.8)
        chat_tool = zen_session.tools["mcp__zen__chat"]
        assert len(chat_tool.call_history) == 1
        call = chat_tool.call_history[0]
        assert call.is_estimated is True
        assert call.estimation_method == "tiktoken"


# ============================================================================
# Persistence Tests
# ============================================================================


class TestPersistence:
    """Test session persistence and recovery"""

    def test_save_and_load_session(self, tmp_path, sample_claude_code_events) -> None:
        """Test saving and loading session"""
        # Create and track session
        adapter = ClaudeCodeAdapter(project="test-project", claude_dir=tmp_path)

        for event in sample_claude_code_events:
            result = adapter.parse_event(json.dumps(event))
            if result:
                tool_name, usage = result
                adapter.record_tool_call(
                    tool_name=tool_name,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_created_tokens=usage["cache_created_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                )

        session = adapter.finalize_session()

        # Save session
        adapter.save_session(tmp_path)

        # Load session
        manager = SessionManager(base_dir=tmp_path)
        loaded_session = manager.load_session(adapter.session_dir)

        # Verify loaded data matches
        assert loaded_session is not None
        assert loaded_session.project == session.project
        assert loaded_session.platform == session.platform
        assert loaded_session.mcp_tool_calls.total_calls == session.mcp_tool_calls.total_calls

    def test_schema_version_validation(self, tmp_path) -> None:
        """Test schema version validation on load"""
        manager = SessionManager(base_dir=tmp_path)

        # Create session directory
        session_dir = tmp_path / "test-session"
        session_dir.mkdir()

        # Write session with incompatible schema version
        summary_data = {
            "schema_version": "2.0.0",  # Incompatible major version
            "project": "test",
            "platform": "test",
        }

        (session_dir / "summary.json").write_text(json.dumps(summary_data))

        # Should fail to load
        loaded_session = manager.load_session(session_dir)
        assert loaded_session is None


# ============================================================================
# Duplicate Detection Tests
# ============================================================================


class TestDuplicateDetection:
    """Test duplicate tool call detection"""

    def test_duplicate_detection(self, tmp_path) -> None:
        """Test duplicate calls are detected"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Same input = same content hash
        input_params = {"query": "test"}
        hash1 = adapter.compute_content_hash(input_params)
        hash2 = adapter.compute_content_hash(input_params)

        assert hash1 == hash2

        # Record two calls with same hash
        adapter.record_tool_call(
            tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50, content_hash=hash1
        )
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
            content_hash=hash2,  # Duplicate
        )

        session = adapter.finalize_session()

        # Should detect duplicate
        assert session.redundancy_analysis is not None
        assert session.redundancy_analysis["duplicate_calls"] == 1
        assert session.redundancy_analysis["potential_savings"] == 150


# ============================================================================
# Anomaly Detection Tests
# ============================================================================


class TestAnomalyDetection:
    """Test anomaly detection in tool usage"""

    def test_high_frequency_detection(self, tmp_path) -> None:
        """Test high frequency anomaly detection"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Record 15 calls (threshold is 10)
        for _ in range(15):
            adapter.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)

        session = adapter.finalize_session()

        # Should detect high frequency
        anomalies = [a for a in session.anomalies if a["type"] == "high_frequency"]
        assert len(anomalies) > 0
        assert anomalies[0]["tool"] == "mcp__zen__chat"
        assert anomalies[0]["calls"] == 15

    def test_high_avg_tokens_detection(self, tmp_path) -> None:
        """Test high average tokens anomaly detection"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Record call with 600K tokens (threshold is 500K - raised for Claude Code context)
        adapter.record_tool_call(
            tool_name="mcp__zen__thinkdeep", input_tokens=400000, output_tokens=200000
        )

        session = adapter.finalize_session()

        # Should detect high avg tokens
        anomalies = [a for a in session.anomalies if a["type"] == "high_avg_tokens"]
        assert len(anomalies) > 0
        assert anomalies[0]["tool"] == "mcp__zen__thinkdeep"


# ============================================================================
# Multi-Server Tracking Tests
# ============================================================================


class TestMultiServerTracking:
    """Test tracking multiple MCP servers"""

    def test_multiple_servers_tracked(self, tmp_path) -> None:
        """Test multiple MCP servers tracked separately"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Record calls to different servers
        adapter.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)
        adapter.record_tool_call(
            tool_name="mcp__brave-search__web", input_tokens=200, output_tokens=100
        )
        adapter.record_tool_call(
            tool_name="mcp__context7__search", input_tokens=150, output_tokens=75
        )

        session = adapter.finalize_session()

        # Should have 3 server sessions
        assert len(session.server_sessions) == 3
        assert "zen" in session.server_sessions
        assert "brave-search" in session.server_sessions
        assert "context7" in session.server_sessions

    def test_server_session_files_created(self, tmp_path) -> None:
        """Test session file created with server data (v1.0.4: single file)"""
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)

        # Record calls to multiple servers
        adapter.record_tool_call(tool_name="mcp__zen__chat", input_tokens=100, output_tokens=50)
        adapter.record_tool_call(
            tool_name="mcp__brave-search__web", input_tokens=200, output_tokens=100
        )

        adapter.finalize_session()
        adapter.save_session(tmp_path)

        # Verify single session file created (v1.0.4 format)
        assert adapter.session_dir is not None
        session_files = list(adapter.session_dir.glob("*.json"))
        assert len(session_files) == 1
        assert session_files[0].name.startswith("test-")

        # Verify file contains both server data
        with open(session_files[0]) as f:
            data = json.load(f)
        assert "_file" in data
        mcp_summary = data.get("mcp_summary", {})
        servers_used = mcp_summary.get("servers_used", [])
        assert "zen" in servers_used
        assert "brave-search" in servers_used


# ============================================================================
# End-to-End Workflow Tests
# ============================================================================


class TestEndToEndWorkflow:
    """Complete end-to-end workflow tests"""

    def test_complete_claude_code_workflow(self, tmp_path, sample_claude_code_events) -> None:
        """Test complete workflow: events → tracking → persistence → loading"""
        # 1. Create adapter
        adapter = ClaudeCodeAdapter(project="e2e-test", claude_dir=tmp_path)

        # 2. Parse events and track
        for event in sample_claude_code_events:
            result = adapter.parse_event(json.dumps(event))
            if result:
                tool_name, usage = result
                adapter.record_tool_call(
                    tool_name=tool_name,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_created_tokens=usage["cache_created_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                )

        # 3. Finalize session
        session = adapter.finalize_session()

        # 4. Save to disk
        adapter.save_session(tmp_path)

        # 5. Load from disk
        manager = SessionManager(base_dir=tmp_path)
        loaded_session = manager.load_session(adapter.session_dir)

        # 6. Verify complete workflow
        assert loaded_session is not None
        assert loaded_session.schema_version == SCHEMA_VERSION
        assert loaded_session.project == "e2e-test"
        assert loaded_session.platform == "claude-code"
        assert loaded_session.mcp_tool_calls.total_calls == 2
        assert loaded_session.mcp_tool_calls.unique_tools == 2
        assert loaded_session.token_usage.total_tokens > 0
        assert "zen" in loaded_session.server_sessions
        assert "brave-search" in loaded_session.server_sessions

    def test_complete_codex_cli_workflow(self, tmp_path, sample_codex_cli_events) -> None:
        """Test complete Codex CLI workflow with normalization.

        Since task-69.8, function_call events return None (register pending).
        MCP tool calls complete when function_call_output arrives with estimated tokens.
        """
        # 1. Create adapter
        adapter = CodexCLIAdapter(project="codex-e2e-test", codex_args=[])

        # 2. Parse events and track using adapter's _process_tool_call
        for event in sample_codex_cli_events:
            result = adapter.parse_event(json.dumps(event))
            if result:
                tool_name, usage = result
                # Use adapter's processing (handles both session and MCP)
                adapter._process_tool_call(tool_name, usage)

        # 3. Finalize and save
        session = adapter.finalize_session()
        adapter.save_session(tmp_path)

        # 4. Load from disk
        manager = SessionManager(base_dir=tmp_path)
        loaded_session = manager.load_session(adapter.session_dir)

        # 5. Verify Codex tools normalized
        assert loaded_session is not None
        zen_session = loaded_session.server_sessions.get("zen")
        assert zen_session is not None
        # Should be normalized (no -mcp suffix)
        assert "mcp__zen__chat" in zen_session.tools

        # 6. Verify model and tokens persisted
        assert loaded_session.model == "gpt-5-codex"
        assert loaded_session.token_usage.input_tokens > 0

        # 7. Verify token estimation was recorded
        # (Note: call_history may be empty after load depending on persistence settings)
        chat_tool = zen_session.tools["mcp__zen__chat"]
        assert chat_tool.calls == 1
        assert chat_tool.total_tokens > 0  # Estimated tokens recorded

    def test_cross_session_analysis(self, tmp_path, sample_claude_code_events) -> None:
        """Test analyzing multiple sessions"""
        # SessionManager expects sessions in date subdirs directly.
        # ClaudeCodeAdapter.save_session() creates platform/date structure,
        # so point SessionManager at the platform directory.
        manager = SessionManager(base_dir=tmp_path / "claude-code")

        # Create 3 sessions
        for i in range(3):
            adapter = ClaudeCodeAdapter(project=f"session-{i}", claude_dir=tmp_path)

            for event in sample_claude_code_events:
                result = adapter.parse_event(json.dumps(event))
                if result:
                    tool_name, usage = result
                    adapter.record_tool_call(
                        tool_name=tool_name,
                        input_tokens=usage["input_tokens"],
                        output_tokens=usage["output_tokens"],
                        cache_created_tokens=usage["cache_created_tokens"],
                        cache_read_tokens=usage["cache_read_tokens"],
                    )

            adapter.finalize_session()
            adapter.save_session(tmp_path)

        # List all sessions
        sessions = manager.list_sessions()
        assert len(sessions) == 3

        # Load all sessions
        loaded_sessions = []
        for session_dir in sessions:
            session = manager.load_session(session_dir)
            if session:
                loaded_sessions.append(session)

        assert len(loaded_sessions) == 3

        # Aggregate statistics
        total_calls = sum(s.mcp_tool_calls.total_calls for s in loaded_sessions)
        total_tokens = sum(s.token_usage.total_tokens for s in loaded_sessions)

        assert total_calls == 6  # 2 calls per session × 3 sessions
        assert total_tokens > 0


# ============================================================================
# TUI Summary Display Tests (task-42.1)
# ============================================================================


class TestTUISummaryDisplay:
    """Test TUI summary display with enhanced fields"""

    def test_build_snapshot_from_session_includes_model(self, tmp_path) -> None:
        """Test that snapshot includes model information from session"""
        from token_audit.cli import _build_snapshot_from_session

        # Create session with model
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)
        adapter.detected_model = "claude-opus-4-5-20251101"
        adapter.session.model = "claude-opus-4-5-20251101"
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=5000,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify model fields
        assert snapshot.model_id == "claude-opus-4-5-20251101"
        assert snapshot.model_name == "Claude Opus 4.5"

    def test_build_snapshot_from_session_includes_cost_fields(self, tmp_path) -> None:
        """Test that snapshot includes enhanced cost fields"""
        from token_audit.cli import _build_snapshot_from_session

        # Create session with tokens
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)
        adapter.detected_model = "claude-sonnet-4-5-20250929"
        adapter.session.model = "claude-sonnet-4-5-20250929"
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=10000,
            output_tokens=5000,
            cache_read_tokens=100000,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify cost fields are populated
        assert snapshot.cost_no_cache > 0.0
        assert snapshot.cache_savings >= 0.0
        assert snapshot.savings_percent >= 0.0

    def test_build_snapshot_from_session_includes_server_hierarchy(self, tmp_path) -> None:
        """Test that snapshot includes server hierarchy"""
        from token_audit.cli import _build_snapshot_from_session

        # Create session with multiple servers
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
        )
        adapter.record_tool_call(
            tool_name="mcp__brave-search__web",
            input_tokens=2000,
            output_tokens=1000,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify server hierarchy
        assert len(snapshot.server_hierarchy) == 2
        server_names = [s[0] for s in snapshot.server_hierarchy]
        assert "zen" in server_names
        assert "brave-search" in server_names

    def test_build_snapshot_from_session_handles_empty_model(self, tmp_path) -> None:
        """Test that snapshot handles missing model gracefully"""
        from token_audit.cli import _build_snapshot_from_session

        # Create session without model
        adapter = ClaudeCodeAdapter(project="test", claude_dir=tmp_path)
        # Don't set detected_model
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=1000,
            output_tokens=500,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify graceful handling
        assert snapshot.model_id == ""
        assert snapshot.model_name == "Unknown Model"
        # Cost should still be calculated with default pricing
        assert snapshot.cost_no_cache > 0.0

    def test_build_snapshot_from_session_codex_cli(self) -> None:
        """Test that snapshot works with Codex CLI sessions (task-42.3)"""
        from token_audit.cli import _build_snapshot_from_session

        # Create Codex CLI session
        adapter = CodexCLIAdapter(project="test", codex_args=[])
        adapter.detected_model = "gpt-5.1"
        adapter.session.model = "gpt-5.1"
        adapter.record_tool_call(
            tool_name="mcp__zen-mcp__chat",  # Codex format
            input_tokens=10000,
            output_tokens=5000,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify model fields work for OpenAI models
        assert snapshot.model_id == "gpt-5.1"
        assert snapshot.model_name == "gpt-5.1"  # Falls through to model_id if not in mapping

        # Note: cost_estimate comes from session.cost_estimate which Codex CLI adapter
        # doesn't set during tracking (pre-existing behavior). cost_no_cache is calculated
        # in _build_snapshot_from_session() and works correctly.
        assert snapshot.cost_no_cache > 0.0

        # Verify server hierarchy works with normalized tool names
        assert len(snapshot.server_hierarchy) == 1
        server_name = snapshot.server_hierarchy[0][0]
        assert server_name == "zen"  # Normalized from zen-mcp

    def test_build_snapshot_from_session_gemini_cli(self, tmp_path) -> None:
        """Test that snapshot works with Gemini CLI sessions (task-42.4)"""
        from token_audit.cli import _build_snapshot_from_session
        from token_audit.gemini_cli_adapter import GeminiCLIAdapter

        # Create Gemini CLI session
        adapter = GeminiCLIAdapter(project="test", gemini_dir=tmp_path)
        adapter.detected_model = "gemini-2.5-pro"
        adapter.session.model = "gemini-2.5-pro"
        adapter.record_tool_call(
            tool_name="mcp__zen__chat",  # Gemini uses Claude Code format
            input_tokens=10000,
            output_tokens=5000,
            cache_read_tokens=2000,
        )
        session = adapter.finalize_session()

        # Build snapshot
        snapshot = _build_snapshot_from_session(session, datetime.now())

        # Verify model fields work for Gemini models (AC #1, #5)
        assert snapshot.model_id == "gemini-2.5-pro"
        # Check CLI's MODEL_DISPLAY_NAMES
        assert snapshot.model_name in ["Gemini 2.5 Pro", "gemini-2.5-pro"]

        # Note: cost_estimate comes from session (Gemini adapter doesn't set it - pre-existing)
        # cost_no_cache is calculated in _build_snapshot_from_session() (AC #3, #6)
        assert snapshot.cost_no_cache > 0.0

        # Verify server hierarchy works
        assert len(snapshot.server_hierarchy) == 1
        server_name = snapshot.server_hierarchy[0][0]
        assert server_name == "zen"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
