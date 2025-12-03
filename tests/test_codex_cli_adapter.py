#!/usr/bin/env python3
"""
Test suite for codex_cli_adapter module

Tests CodexCLIAdapter implementation for parsing Codex CLI session JSONL files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from mcp_audit.codex_cli_adapter import CodexCLIAdapter, MODEL_DISPLAY_NAMES


# ============================================================================
# Sample Event Data
# ============================================================================


def make_session_meta_event(
    session_id: str = "test-session-id",
    cwd: str = "/test/project",
    cli_version: str = "0.63.0",
) -> Dict[str, Any]:
    """Create a session_meta event."""
    return {
        "timestamp": "2025-11-04T11:38:25.072Z",
        "type": "session_meta",
        "payload": {
            "id": session_id,
            "cwd": cwd,
            "cli_version": cli_version,
            "git": {
                "commit_hash": "abc123",
                "branch": "main",
                "repository_url": "https://github.com/test/repo.git",
            },
        },
    }


def make_turn_context_event(model: str = "gpt-5.1") -> Dict[str, Any]:
    """Create a turn_context event."""
    return {
        "timestamp": "2025-11-04T11:38:27.361Z",
        "type": "turn_context",
        "payload": {
            "cwd": "/test/project",
            "model": model,
        },
    }


def make_token_count_event(
    input_tokens: int = 300,
    cached_input_tokens: int = 1500,
    output_tokens: int = 150,
    reasoning_tokens: int = 50,
) -> Dict[str, Any]:
    """Create a token_count event."""
    return {
        "timestamp": "2025-11-04T11:38:30.056Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_tokens,
                    "total_tokens": input_tokens
                    + cached_input_tokens
                    + output_tokens
                    + reasoning_tokens,
                },
            },
        },
    }


def make_mcp_tool_call_event(
    tool_name: str = "mcp__zen__chat",
    arguments: Dict[str, Any] | None = None,
    call_id: str = "call_abc123",
) -> Dict[str, Any]:
    """Create an MCP tool call event."""
    return {
        "timestamp": "2025-11-04T11:38:31.000Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": tool_name,
            "arguments": json.dumps(arguments or {"prompt": "test"}),
            "call_id": call_id,
        },
    }


def make_native_tool_call_event(
    tool_name: str = "read_file",
    arguments: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Create a native (non-MCP) tool call event."""
    return {
        "timestamp": "2025-11-04T11:38:32.000Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": tool_name,
            "arguments": json.dumps(arguments or {"path": "/test/file.py"}),
            "call_id": "call_native123",
        },
    }


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_events() -> List[Dict[str, Any]]:
    """Create a list of sample Codex CLI events."""
    return [
        make_session_meta_event(),
        make_turn_context_event(),
        make_token_count_event(),
        make_mcp_tool_call_event(),
    ]


@pytest.fixture
def sample_session_file(tmp_path: Path, sample_events: List[Dict[str, Any]]) -> Path:
    """Create a temporary session JSONL file."""
    sessions_dir = tmp_path / ".codex" / "sessions" / "2025" / "11" / "04"
    sessions_dir.mkdir(parents=True)

    session_file = sessions_dir / "test-session.jsonl"
    with open(session_file, "w") as f:
        for event in sample_events:
            f.write(json.dumps(event) + "\n")

    return session_file


@pytest.fixture
def adapter(tmp_path: Path, sample_session_file: Path) -> CodexCLIAdapter:
    """Create adapter with temp directories."""
    return CodexCLIAdapter(
        project="test-project",
        codex_dir=tmp_path / ".codex",
        session_file=sample_session_file,
    )


# ============================================================================
# Initialization Tests
# ============================================================================


class TestCodexCLIAdapterInitialization:
    """Tests for CodexCLIAdapter initialization."""

    def test_initialization(self) -> None:
        """Test adapter initializes correctly."""
        adapter = CodexCLIAdapter(project="test-project")

        assert adapter.project == "test-project"
        assert adapter.platform == "codex-cli"
        assert adapter.detected_model is None
        assert adapter.model_name == "Unknown Model"
        assert adapter.subprocess_mode is False

    def test_initialization_with_subprocess_mode(self) -> None:
        """Test adapter initializes with subprocess mode."""
        adapter = CodexCLIAdapter(
            project="test-project",
            subprocess_mode=True,
            codex_args=["--model", "gpt-5.1"],
        )

        assert adapter.subprocess_mode is True
        assert adapter.codex_args == ["--model", "gpt-5.1"]

    def test_default_codex_dir(self) -> None:
        """Test default codex_dir is ~/.codex."""
        adapter = CodexCLIAdapter(project="test")
        assert adapter.codex_dir == Path.home() / ".codex"


# ============================================================================
# Session Discovery Tests
# ============================================================================


class TestSessionDiscovery:
    """Tests for session file discovery."""

    def test_get_session_files(self, adapter: CodexCLIAdapter) -> None:
        """Test getting session files."""
        files = adapter.get_session_files()
        assert len(files) == 1

    def test_get_latest_session_file(
        self, adapter: CodexCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test getting latest session file."""
        latest = adapter.get_latest_session_file()
        assert latest == sample_session_file

    def test_list_sessions(self, adapter: CodexCLIAdapter) -> None:
        """Test listing sessions with metadata."""
        sessions = adapter.list_sessions(limit=10)

        assert len(sessions) == 1
        path, mtime, session_id = sessions[0]
        assert session_id == "test-session-id"

    def test_session_discovery_with_date_filter(self, adapter: CodexCLIAdapter) -> None:
        """Test session discovery with date filtering."""
        # Session is in 2025-11-04
        since = datetime(2025, 11, 1)
        until = datetime(2025, 11, 30)

        files = adapter.get_session_files(since=since, until=until)
        assert len(files) == 1

        # Filter that excludes the session
        since_late = datetime(2025, 12, 1)
        files = adapter.get_session_files(since=since_late)
        assert len(files) == 0


# ============================================================================
# Event Parsing Tests
# ============================================================================


class TestEventParsing:
    """Tests for JSONL event parsing."""

    def test_parse_session_meta_event(self, adapter: CodexCLIAdapter) -> None:
        """Test parsing session_meta event."""
        event = make_session_meta_event(cwd="/my/project", cli_version="0.63.0")

        result = adapter.parse_event(event)

        assert result is None  # session_meta doesn't return data
        assert adapter.session_cwd == "/my/project"
        assert adapter.cli_version == "0.63.0"
        assert adapter.git_info is not None

    def test_parse_turn_context_event(self, adapter: CodexCLIAdapter) -> None:
        """Test parsing turn_context event sets model."""
        event = make_turn_context_event(model="gpt-5.1")

        result = adapter.parse_event(event)

        assert result is None  # turn_context doesn't return data
        assert adapter.detected_model == "gpt-5.1"
        assert adapter.model_name == "GPT-5.1"
        assert adapter.session.model == "gpt-5.1"

    def test_parse_turn_context_only_sets_model_once(self, adapter: CodexCLIAdapter) -> None:
        """Test turn_context only sets model on first occurrence."""
        adapter.parse_event(make_turn_context_event(model="gpt-5.1"))
        adapter.parse_event(make_turn_context_event(model="gpt-4.1"))

        assert adapter.detected_model == "gpt-5.1"  # Unchanged

    def test_parse_token_count_event(self, adapter: CodexCLIAdapter) -> None:
        """Test parsing token_count event."""
        event = make_token_count_event(
            input_tokens=300,
            cached_input_tokens=1500,
            output_tokens=150,
            reasoning_tokens=50,
        )

        result = adapter.parse_event(event)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 300
        assert usage["output_tokens"] == 200  # 150 + 50 reasoning
        assert usage["cache_read_tokens"] == 1500
        assert usage["cache_created_tokens"] == 0

    def test_parse_mcp_tool_call_event(self, adapter: CodexCLIAdapter) -> None:
        """Test parsing MCP tool call event."""
        event = make_mcp_tool_call_event(
            tool_name="mcp__zen__chat",
            arguments={"prompt": "test query"},
        )

        result = adapter.parse_event(event)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "mcp__zen__chat"
        assert usage["tool_params"] == {"prompt": "test query"}
        assert usage["call_id"] == "call_abc123"

    def test_parse_native_tool_ignored(self, adapter: CodexCLIAdapter) -> None:
        """Test native tools are ignored."""
        event = make_native_tool_call_event()

        result = adapter.parse_event(event)
        assert result is None

    def test_parse_invalid_json(self, adapter: CodexCLIAdapter) -> None:
        """Test invalid JSON returns None."""
        result = adapter.parse_event("not valid json")
        assert result is None

    def test_parse_empty_line(self, adapter: CodexCLIAdapter) -> None:
        """Test empty lines return None."""
        assert adapter.parse_event("") is None
        assert adapter.parse_event("  ") is None

    def test_parse_unknown_event_type(self, adapter: CodexCLIAdapter) -> None:
        """Test unknown event types return None."""
        event = {"type": "unknown_type", "payload": {}}
        result = adapter.parse_event(event)
        assert result is None


# ============================================================================
# Model Detection Tests
# ============================================================================


class TestModelDetection:
    """Tests for model detection."""

    def test_model_display_names(self) -> None:
        """Test all model display name mappings."""
        # GPT-5 series
        assert MODEL_DISPLAY_NAMES["gpt-5.1"] == "GPT-5.1"
        assert MODEL_DISPLAY_NAMES["gpt-5-mini"] == "GPT-5 Mini"
        assert MODEL_DISPLAY_NAMES["gpt-5-codex"] == "GPT-5 Codex"
        assert MODEL_DISPLAY_NAMES["gpt-5.1-codex-max"] == "GPT-5.1 Codex Max"

        # GPT-4.1 series
        assert MODEL_DISPLAY_NAMES["gpt-4.1"] == "GPT-4.1"
        assert MODEL_DISPLAY_NAMES["gpt-4.1-mini"] == "GPT-4.1 Mini"

        # O-series
        assert MODEL_DISPLAY_NAMES["o4-mini"] == "O4 Mini"

    def test_unknown_model_uses_id(self, adapter: CodexCLIAdapter) -> None:
        """Test unknown models use raw ID as display name."""
        adapter.parse_event(make_turn_context_event(model="gpt-99-turbo"))

        assert adapter.detected_model == "gpt-99-turbo"
        assert adapter.model_name == "gpt-99-turbo"


# ============================================================================
# Token Accumulation Tests
# ============================================================================


class TestTokenAccumulation:
    """Tests for token accumulation."""

    def test_process_session_event(self, adapter: CodexCLIAdapter) -> None:
        """Test session events accumulate tokens."""
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_created_tokens": 0,
            "cache_read_tokens": 500,
        }
        adapter._process_tool_call("__session__", usage)

        assert adapter.session.token_usage.input_tokens == 100
        assert adapter.session.token_usage.output_tokens == 50
        assert adapter.session.token_usage.cache_read_tokens == 500
        assert adapter.session.token_usage.total_tokens == 650

    def test_process_mcp_tool_call(self, adapter: CodexCLIAdapter) -> None:
        """Test MCP tool calls are recorded."""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "tool_params": {"prompt": "test"},
        }
        adapter._process_tool_call("mcp__zen__chat", usage)

        # Server session created
        assert "zen" in adapter.server_sessions
        assert adapter.server_sessions["zen"].total_calls == 1


# ============================================================================
# Batch Processing Tests
# ============================================================================


class TestBatchProcessing:
    """Tests for batch session processing."""

    def test_process_session_file_batch(
        self, adapter: CodexCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test batch processing of session file."""
        adapter.process_session_file_batch(sample_session_file)
        session = adapter.finalize_session()

        # Verify tokens processed
        assert session.token_usage.total_tokens > 0
        assert session.token_usage.input_tokens == 300
        assert session.token_usage.output_tokens == 200  # 150 + 50 reasoning

    def test_batch_processing_model_detection(
        self, adapter: CodexCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test model detection during batch processing."""
        adapter.process_session_file_batch(sample_session_file)

        assert adapter.detected_model == "gpt-5.1"
        assert adapter.cli_version == "0.63.0"

    def test_batch_processing_mcp_calls(
        self, adapter: CodexCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test MCP call tracking during batch processing."""
        adapter.process_session_file_batch(sample_session_file)
        session = adapter.finalize_session()

        assert session.mcp_tool_calls.total_calls == 1
        assert "zen" in adapter.server_sessions


# ============================================================================
# Platform Metadata Tests
# ============================================================================


class TestPlatformMetadata:
    """Tests for platform metadata."""

    def test_get_platform_metadata(self, adapter: CodexCLIAdapter) -> None:
        """Test platform metadata includes correct fields."""
        adapter.detected_model = "gpt-5.1"
        adapter.model_name = "GPT-5.1"
        adapter.cli_version = "0.63.0"
        adapter.session_cwd = "/test/project"

        metadata = adapter.get_platform_metadata()

        assert metadata["model"] == "gpt-5.1"
        assert metadata["model_name"] == "GPT-5.1"
        assert metadata["cli_version"] == "0.63.0"
        assert metadata["session_cwd"] == "/test/project"
        assert "codex_dir" in metadata


# ============================================================================
# Edge Cases Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_token_count_with_zero_tokens(self, adapter: CodexCLIAdapter) -> None:
        """Test token count with all zeros returns None."""
        event = {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 0,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_output_tokens": 0,
                    },
                },
            },
        }
        result = adapter.parse_event(event)
        assert result is None

    def test_token_count_missing_info(self, adapter: CodexCLIAdapter) -> None:
        """Test token count without info returns None."""
        event = {
            "type": "event_msg",
            "payload": {"type": "token_count"},
        }
        result = adapter.parse_event(event)
        assert result is None

    def test_function_call_invalid_arguments(self, adapter: CodexCLIAdapter) -> None:
        """Test function call with invalid JSON arguments."""
        event = {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "mcp__zen__chat",
                "arguments": "not valid json",
                "call_id": "call_123",
            },
        }
        result = adapter.parse_event(event)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "mcp__zen__chat"
        assert usage["tool_params"] == {}  # Empty on parse failure


# ============================================================================
# Integration Tests
# ============================================================================


class TestCompleteWorkflow:
    """Integration tests for complete workflow."""

    def test_complete_batch_workflow(
        self, adapter: CodexCLIAdapter, sample_session_file: Path, tmp_path: Path
    ) -> None:
        """Test complete batch processing workflow."""
        adapter.process_session_file_batch(sample_session_file)
        session = adapter.finalize_session()
        adapter.save_session(tmp_path / "output")

        # Verify session data
        assert session.project == "test-project"
        assert session.platform == "codex-cli"
        assert session.model == "gpt-5.1"

        # Verify tokens
        assert session.token_usage.input_tokens == 300
        assert session.token_usage.output_tokens == 200
        assert session.token_usage.cache_read_tokens == 1500

        # Verify MCP calls
        assert session.mcp_tool_calls.total_calls == 1
        assert "zen" in session.server_sessions

        # Verify files saved
        assert adapter.session_dir is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
