#!/usr/bin/env python3
"""
Test suite for gemini_cli_adapter module

Tests GeminiCLIAdapter implementation for parsing Gemini CLI session JSON files.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from token_audit.gemini_cli_adapter import (
    GeminiCLIAdapter,
    GeminiMessage,
    GeminiSession,
    MODEL_DISPLAY_NAMES,
)


# ============================================================================
# Sample Session Data
# ============================================================================


def make_sample_session(
    session_id: str = "test-session-id",
    project_hash: str = "a" * 64,
    model: str = "gemini-2.5-pro",
    include_mcp_tools: bool = True,
) -> Dict[str, Any]:
    """Create a sample Gemini CLI session JSON structure."""
    messages = [
        # User message
        {
            "id": "msg-001",
            "type": "user",
            "content": "Hello, can you help me?",
            "timestamp": "2025-11-07T05:10:42.000Z",
        },
        # Gemini response with tokens
        {
            "id": "msg-002",
            "type": "gemini",
            "content": "Of course! How can I help?",
            "model": model,
            "thoughts": [{"type": "thought", "text": "Analyzing request..."}],
            "tokens": {
                "input": 1000,
                "output": 50,
                "cached": 500,
                "thoughts": 100,
                "tool": 0,
                "total": 1650,
            },
            "timestamp": "2025-11-07T05:10:45.000Z",
        },
    ]

    # Add MCP tool call if requested
    if include_mcp_tools:
        messages.append(
            {
                "id": "msg-003",
                "type": "gemini",
                "content": "I found some results.",
                "model": model,
                "thoughts": [],
                "toolCalls": [
                    {
                        "id": "mcp-call-001",
                        "name": "mcp__zen__chat",
                        "args": {"prompt": "test"},
                        "result": ["Result"],
                        "status": "success",
                        "timestamp": "2025-11-07T05:10:50.000Z",
                    }
                ],
                "tokens": {
                    "input": 500,
                    "output": 100,
                    "cached": 200,
                    "thoughts": 50,
                    "tool": 25,
                    "total": 875,
                },
                "timestamp": "2025-11-07T05:10:55.000Z",
            }
        )

    return {
        "sessionId": session_id,
        "projectHash": project_hash,
        "startTime": "2025-11-07T05:10:41.717Z",
        "lastUpdated": "2025-11-07T05:15:00.000Z",
        "messages": messages,
    }


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_session_data() -> Dict[str, Any]:
    """Create sample session data."""
    return make_sample_session()


@pytest.fixture
def sample_session_file(tmp_path: Path, sample_session_data: Dict[str, Any]) -> Path:
    """Create a temporary session file."""
    chats_dir = tmp_path / ".gemini" / "tmp" / ("a" * 64) / "chats"
    chats_dir.mkdir(parents=True)

    session_file = chats_dir / "session-2025-11-07T05-10-test.json"
    session_file.write_text(json.dumps(sample_session_data))

    return session_file


@pytest.fixture
def adapter(tmp_path: Path, sample_session_file: Path) -> GeminiCLIAdapter:
    """Create adapter with temp directories."""
    return GeminiCLIAdapter(
        project="test-project",
        gemini_dir=tmp_path / ".gemini",
        session_file=sample_session_file,
    )


# ============================================================================
# GeminiMessage Tests
# ============================================================================


class TestGeminiMessage:
    """Tests for GeminiMessage parsing."""

    def test_from_json_user_message(self) -> None:
        """Test parsing user message."""
        data = {
            "id": "msg-001",
            "type": "user",
            "content": "Hello",
            "timestamp": "2025-11-07T05:10:42.000Z",
        }

        msg = GeminiMessage.from_json(data)

        assert msg.id == "msg-001"
        assert msg.message_type == "user"
        assert msg.content == "Hello"
        assert msg.model is None
        assert msg.tokens is None

    def test_from_json_gemini_message_with_tokens(self) -> None:
        """Test parsing gemini message with tokens."""
        data = {
            "id": "msg-002",
            "type": "gemini",
            "content": "Response",
            "model": "gemini-2.5-pro",
            "tokens": {
                "input": 1000,
                "output": 50,
                "cached": 500,
                "thoughts": 100,
                "tool": 0,
                "total": 1650,
            },
            "timestamp": "2025-11-07T05:10:45.000Z",
        }

        msg = GeminiMessage.from_json(data)

        assert msg.id == "msg-002"
        assert msg.message_type == "gemini"
        assert msg.model == "gemini-2.5-pro"
        assert msg.tokens is not None
        assert msg.tokens["input"] == 1000
        assert msg.tokens["output"] == 50
        assert msg.tokens["cached"] == 500
        assert msg.tokens["thoughts"] == 100

    def test_from_json_with_tool_calls(self) -> None:
        """Test parsing message with tool calls."""
        data = {
            "id": "msg-003",
            "type": "gemini",
            "content": "Result",
            "model": "gemini-2.5-pro",
            "toolCalls": [
                {
                    "id": "call-001",
                    "name": "mcp__zen__chat",
                    "args": {"prompt": "test"},
                    "status": "success",
                }
            ],
            "tokens": {
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 10,
                "total": 160,
            },
            "timestamp": "2025-11-07T05:10:50.000Z",
        }

        msg = GeminiMessage.from_json(data)

        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "mcp__zen__chat"
        assert msg.tool_calls[0]["status"] == "success"


# ============================================================================
# GeminiSession Tests
# ============================================================================


class TestGeminiSession:
    """Tests for GeminiSession parsing."""

    def test_from_file(self, sample_session_file: Path) -> None:
        """Test parsing session from file."""
        session = GeminiSession.from_file(sample_session_file)

        assert session.session_id == "test-session-id"
        assert session.project_hash == "a" * 64
        assert len(session.messages) == 3
        assert session.source_file == sample_session_file.name

    def test_session_timestamps(self, sample_session_file: Path) -> None:
        """Test session timestamp parsing."""
        session = GeminiSession.from_file(sample_session_file)

        assert session.start_time.year == 2025
        assert session.start_time.month == 11
        assert session.start_time.day == 7


# ============================================================================
# GeminiCLIAdapter Initialization Tests
# ============================================================================


class TestGeminiCLIAdapterInitialization:
    """Tests for GeminiCLIAdapter initialization."""

    def test_initialization(self, adapter: GeminiCLIAdapter) -> None:
        """Test adapter initializes correctly."""
        assert adapter.project == "test-project"
        assert adapter.platform == "gemini-cli"
        assert adapter.thoughts_tokens == 0

    def test_default_gemini_dir(self) -> None:
        """Test default gemini_dir is ~/.gemini."""
        adapter = GeminiCLIAdapter(project="test")
        assert adapter.gemini_dir == Path.home() / ".gemini"

    def test_custom_session_file(self, tmp_path: Path) -> None:
        """Test custom session file path."""
        custom_file = tmp_path / "custom_session.json"
        custom_file.write_text('{"sessionId": "test", "projectHash": "abc", "messages": []}')

        adapter = GeminiCLIAdapter(project="test", session_file=custom_file)

        assert adapter._session_file == custom_file


# ============================================================================
# Project Hash Detection Tests
# ============================================================================


class TestProjectHashDetection:
    """Tests for project hash detection."""

    def test_calculate_project_hash(self, adapter: GeminiCLIAdapter) -> None:
        """Test project hash calculation."""
        # Hash should be 64 hex chars (SHA256)
        adapter._project_hash = None
        calculated = adapter._calculate_project_hash()

        assert calculated is not None
        assert len(calculated) == 64
        assert all(c in "0123456789abcdef" for c in calculated)

    def test_list_available_hashes(self, adapter: GeminiCLIAdapter, tmp_path: Path) -> None:
        """Test listing available project hashes."""
        hashes = adapter.list_available_hashes()

        assert len(hashes) >= 1
        hash_val, path, mtime = hashes[0]
        assert len(hash_val) == 64

    def test_find_project_hash_ignores_empty_chats_dirs(self, tmp_path: Path) -> None:
        """Test that _find_project_hash ignores hash directories with empty chats folders.

        This is a regression test for a bug where _find_project_hash would return
        a hash directory that had a chats/ folder but no session files, causing
        get_latest_session_file() to return None.
        """
        # Create gemini directory structure
        gemini_dir = tmp_path / ".gemini"

        # Hash 1: Valid - has session file
        valid_hash = "a" * 64
        valid_chats = gemini_dir / "tmp" / valid_hash / "chats"
        valid_chats.mkdir(parents=True)
        session_file = valid_chats / "session-2025-01-01T00-00-test123.json"
        session_file.write_text(
            json.dumps(
                {
                    "sessionId": "test",
                    "projectHash": valid_hash,
                    "startTime": "2025-01-01T00:00:00Z",
                    "lastUpdated": "2025-01-01T00:00:00Z",
                    "messages": [],
                }
            )
        )

        # Hash 2: Invalid - has chats dir but NO session files (newer directory)
        empty_hash = "b" * 64
        empty_chats = gemini_dir / "tmp" / empty_hash / "chats"
        empty_chats.mkdir(parents=True)
        # Touch the directory to make it "newer"
        import time

        time.sleep(0.01)  # Ensure different mtime
        empty_chats.touch()

        # Create adapter pointing to test gemini dir
        adapter = GeminiCLIAdapter(project="test", gemini_dir=gemini_dir)

        # _find_project_hash should return the valid hash (with session files),
        # NOT the empty hash (even though it's newer)
        result = adapter._find_project_hash()
        assert result == valid_hash, (
            f"Expected {valid_hash[:16]}... (with session files), "
            f"got {result[:16] if result else None}..."
        )

    def test_check_for_newer_session_file(self, tmp_path: Path) -> None:
        """Test detection of new session files during monitoring.

        This tests the fix for dynamically detecting when a new Gemini CLI
        conversation is started (which creates a new session file).
        """
        import time

        # Create gemini directory structure
        gemini_dir = tmp_path / ".gemini"
        project_hash = "c" * 64
        chats_dir = gemini_dir / "tmp" / project_hash / "chats"
        chats_dir.mkdir(parents=True)

        # Create initial session file
        old_session = chats_dir / "session-2025-01-01T00-00-old.json"
        old_session.write_text(
            json.dumps(
                {
                    "sessionId": "old-session",
                    "projectHash": project_hash,
                    "startTime": "2025-01-01T00:00:00Z",
                    "lastUpdated": "2025-01-01T00:00:00Z",
                    "messages": [],
                }
            )
        )

        # Create adapter
        adapter = GeminiCLIAdapter(project="test", gemini_dir=gemini_dir)

        # Initially, no newer file exists
        result = adapter._check_for_newer_session_file(old_session)
        assert result is None

        # Create a newer session file (simulating new Gemini CLI conversation)
        time.sleep(0.01)  # Ensure different mtime
        new_session = chats_dir / "session-2025-01-01T01-00-new.json"
        new_session.write_text(
            json.dumps(
                {
                    "sessionId": "new-session",
                    "projectHash": project_hash,
                    "startTime": "2025-01-01T01:00:00Z",
                    "lastUpdated": "2025-01-01T01:00:00Z",
                    "messages": [],
                }
            )
        )

        # Now a newer file should be detected
        result = adapter._check_for_newer_session_file(old_session)
        assert result is not None
        assert result.name == "session-2025-01-01T01-00-new.json"

        # If we're already monitoring the newest file, no newer file returned
        result = adapter._check_for_newer_session_file(new_session)
        assert result is None


# ============================================================================
# Event Parsing Tests
# ============================================================================


class TestEventParsing:
    """Tests for message event parsing."""

    def test_parse_user_message_returns_none(self, adapter: GeminiCLIAdapter) -> None:
        """Test user messages return None (no token data)."""
        msg = GeminiMessage(
            id="msg-001",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="user",
            content="Hello",
        )

        result = adapter.parse_event(msg)
        assert result is None

    def test_parse_gemini_message_with_tokens(self, adapter: GeminiCLIAdapter) -> None:
        """Test gemini messages return session token data."""
        msg = GeminiMessage(
            id="msg-002",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Response",
            model="gemini-2.5-pro",
            tokens={
                "input": 1000,
                "output": 50,
                "cached": 500,
                "thoughts": 100,
                "tool": 0,
                "total": 1650,
            },
        )

        result = adapter.parse_event(msg)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 50  # v1.3.0: No longer includes thoughts
        assert usage["reasoning_tokens"] == 100  # v1.3.0: Tracked separately
        assert usage["cache_read_tokens"] == 500

    def test_parse_mcp_tool_call(self, adapter: GeminiCLIAdapter) -> None:
        """Test MCP tool call parsing - tool is processed in-place, session tokens returned."""
        msg = GeminiMessage(
            id="msg-003",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "mcp__zen__chat",
                    "args": {"prompt": "test"},
                    "status": "success",
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 10,
                "total": 160,
            },
        )

        result = adapter.parse_event(msg)

        # parse_event now always returns session tokens (task-72.2)
        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50

        # MCP tool was processed in-place (task-72.1)
        # server_sessions is keyed by server name (e.g., "zen"), not tool name
        assert "zen" in adapter.server_sessions
        assert "mcp__zen__chat" in adapter.server_sessions["zen"].tools

    def test_builtin_tool_tracked(self, adapter: GeminiCLIAdapter) -> None:
        """Test built-in tools are tracked and counted (task-70.2, task-72.1)."""
        msg = GeminiMessage(
            id="msg-003",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",  # Built-in tool
                    "args": {"path": "/test"},
                    "status": "success",
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 10,
                "total": 160,
            },
        )

        result = adapter.parse_event(msg)

        # parse_event now always returns session tokens (task-72.2)
        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 100

        # Built-in tool was processed in-place (task-72.1)
        assert adapter._builtin_tool_calls == 1

    def test_builtin_tool_token_estimation(self, adapter: GeminiCLIAdapter) -> None:
        """Test built-in tools get token estimation like MCP tools (task-69.24).

        Per Task 69 validated plan: "Built-in vs MCP Tools: No difference in
        accuracy approach. Both are function calls to the model and use the
        same estimation method."
        """
        msg = GeminiMessage(
            id="msg-builtin-tokens",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Search results",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "google_web_search",  # Built-in tool
                    "args": {"query": "MCP protocol documentation"},
                    "result": [
                        {
                            "functionResponse": {
                                "response": "Found 10 results for MCP protocol documentation..."
                            }
                        }
                    ],
                    "status": "success",
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 0,  # Native tool field is always 0
                "total": 150,
            },
        )

        adapter.parse_event(msg)

        # Built-in tool should have token estimation
        assert adapter._builtin_tool_calls == 1
        assert adapter._estimated_tool_calls == 1  # Built-in tools now estimated

        # Check that the tool call was recorded with estimation
        # Built-in tools use "builtin" as server name (not __builtin__)
        assert "builtin" in adapter.server_sessions
        builtin_session = adapter.server_sessions["builtin"]
        assert "builtin__google_web_search" in builtin_session.tools

        tool_stats = builtin_session.tools["builtin__google_web_search"]
        assert len(tool_stats.call_history) == 1
        call = tool_stats.call_history[0]
        assert call.input_tokens > 0  # Estimated from args
        assert call.output_tokens > 0  # Estimated from result
        # Token estimation metadata (task-69.24)
        # Method depends on available tokenizers (sentencepiece preferred, tiktoken fallback)
        assert call.is_estimated is True
        assert call.estimation_method in ("sentencepiece", "tiktoken", "character")
        assert call.estimation_encoding is not None

    def test_multiple_tool_calls_in_single_message(self, adapter: GeminiCLIAdapter) -> None:
        """Test ALL tool calls in a message are processed, not just the first (task-72.1).

        This is a regression test for a critical bug where parse_event() returned
        after processing the first tool call, causing:
        1. Only the first tool call to be processed
        2. Session tokens to be lost for messages with tool calls
        """
        msg = GeminiMessage(
            id="msg-multi-tool",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="I read the file and listed the directory",
            model="gemini-2.5-flash",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",  # Built-in tool 1
                    "args": {"path": "/test/file.txt"},
                    "status": "success",
                },
                {
                    "id": "call-002",
                    "name": "list_directory",  # Built-in tool 2
                    "args": {"path": "/test"},
                    "status": "success",
                },
            ],
            tokens={
                "input": 9637,
                "output": 105,
                "cached": 1753,
                "thoughts": 0,
                "tool": 50,
                "total": 9742,
            },
        )

        # Before fix: parse_event() would return after first tool call,
        # losing the second tool call and ALL session tokens
        result = adapter.parse_event(msg)

        # Verify session tokens are returned (task-72.2)
        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 9637
        assert usage["output_tokens"] == 105
        assert usage["cache_read_tokens"] == 1753

        # Verify BOTH tool calls were processed (task-72.1)
        assert adapter._builtin_tool_calls == 2, (
            f"Expected 2 built-in tool calls, got {adapter._builtin_tool_calls}. "
            "parse_event() may be returning after the first tool call."
        )

    def test_multiple_mcp_tools_in_single_message(self, adapter: GeminiCLIAdapter) -> None:
        """Test multiple MCP tool calls in a single message are all processed."""
        msg = GeminiMessage(
            id="msg-multi-mcp",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="I used multiple MCP tools",
            model="gemini-2.5-flash",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "mcp__zen__chat",
                    "args": {"prompt": "test1"},
                    "status": "success",
                },
                {
                    "id": "call-002",
                    "name": "mcp__brave__search",
                    "args": {"query": "test2"},
                    "status": "success",
                },
                {
                    "id": "call-003",
                    "name": "mcp__jina__read_url",
                    "args": {"url": "https://example.com"},
                    "status": "success",
                },
            ],
            tokens={
                "input": 5000,
                "output": 200,
                "cached": 1000,
                "thoughts": 50,
                "tool": 100,
                "total": 5250,
            },
        )

        result = adapter.parse_event(msg)

        # Verify session tokens are returned
        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 5000
        assert usage["output_tokens"] == 200  # v1.3.0: No longer includes thoughts
        assert usage["reasoning_tokens"] == 50  # v1.3.0: Tracked separately

        # Verify ALL 3 MCP tools were processed
        # server_sessions is keyed by server name, tools are nested
        assert "zen" in adapter.server_sessions
        assert "mcp__zen__chat" in adapter.server_sessions["zen"].tools
        assert "brave" in adapter.server_sessions
        assert "mcp__brave__search" in adapter.server_sessions["brave"].tools
        assert "jina" in adapter.server_sessions
        assert "mcp__jina__read_url" in adapter.server_sessions["jina"].tools

    def test_mixed_mcp_and_builtin_tools_in_message(self, adapter: GeminiCLIAdapter) -> None:
        """Test message with both MCP and built-in tools processes all."""
        msg = GeminiMessage(
            id="msg-mixed",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="I used both MCP and built-in tools",
            model="gemini-2.5-flash",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",  # Built-in
                    "args": {"path": "/test"},
                    "status": "success",
                },
                {
                    "id": "call-002",
                    "name": "mcp__zen__chat",  # MCP
                    "args": {"prompt": "test"},
                    "status": "success",
                },
                {
                    "id": "call-003",
                    "name": "list_directory",  # Built-in
                    "args": {"path": "/"},
                    "status": "success",
                },
            ],
            tokens={
                "input": 3000,
                "output": 100,
                "cached": 500,
                "thoughts": 0,
                "tool": 75,
                "total": 3100,
            },
        )

        result = adapter.parse_event(msg)

        # Verify session tokens returned
        assert result is not None
        assert result[0] == "__session__"

        # Verify all tools processed
        assert adapter._builtin_tool_calls == 2  # read_file + list_directory
        assert "zen" in adapter.server_sessions
        assert "mcp__zen__chat" in adapter.server_sessions["zen"].tools

    def test_unknown_tool_ignored(self, adapter: GeminiCLIAdapter) -> None:
        """Test unknown tools (not mcp__ or built-in) are ignored."""
        msg = GeminiMessage(
            id="msg-004",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "custom_unknown_tool",  # Unknown tool
                    "args": {"arg": "value"},
                    "status": "success",
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 0,
                "total": 150,
            },
        )

        result = adapter.parse_event(msg)

        # Should return session tokens, not tool call (unknown tool ignored)
        assert result is not None
        tool_name, _ = result
        assert tool_name == "__session__"


# ============================================================================
# Model Detection Tests
# ============================================================================


class TestModelDetection:
    """Tests for model detection."""

    def test_model_display_names(self) -> None:
        """Test model display name mappings."""
        assert MODEL_DISPLAY_NAMES["gemini-2.5-pro"] == "Gemini 2.5 Pro"
        assert MODEL_DISPLAY_NAMES["gemini-2.5-flash"] == "Gemini 2.5 Flash"
        assert MODEL_DISPLAY_NAMES["gemini-3-pro-preview"] == "Gemini 3 Pro Preview"

    def test_model_detected_from_message(self, adapter: GeminiCLIAdapter) -> None:
        """Test model detection from gemini message."""
        msg = GeminiMessage(
            id="msg-001",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Response",
            model="gemini-2.5-pro",
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 0,
                "total": 150,
            },
        )

        adapter.parse_event(msg)

        assert adapter.detected_model == "gemini-2.5-pro"
        assert adapter.model_name == "Gemini 2.5 Pro"
        assert adapter.session.model == "gemini-2.5-pro"


# ============================================================================
# Thoughts Token Tracking Tests
# ============================================================================


class TestThoughtsTokenTracking:
    """Tests for Gemini-specific thoughts token tracking."""

    def test_thoughts_tokens_accumulated(self, adapter: GeminiCLIAdapter) -> None:
        """Test thoughts tokens are accumulated separately."""
        msg1 = GeminiMessage(
            id="msg-001",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Response 1",
            model="gemini-2.5-pro",
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 100,
                "tool": 0,
                "total": 250,
            },
        )
        msg2 = GeminiMessage(
            id="msg-002",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Response 2",
            model="gemini-2.5-pro",
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 150,
                "tool": 0,
                "total": 300,
            },
        )

        adapter.parse_event(msg1)
        adapter.parse_event(msg2)

        assert adapter.thoughts_tokens == 250  # 100 + 150


# ============================================================================
# Batch Processing Tests
# ============================================================================


class TestBatchProcessing:
    """Tests for batch session processing."""

    def test_process_session_file_batch(
        self, adapter: GeminiCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test batch processing of session file."""
        adapter.process_session_file_batch(sample_session_file)
        session = adapter.finalize_session()

        # Verify tokens processed
        assert session.token_usage.total_tokens > 0
        assert session.token_usage.input_tokens > 0
        assert session.token_usage.output_tokens > 0

        # Verify message count
        assert session.message_count == 2  # 2 gemini messages

    def test_batch_processing_model_detection(
        self, adapter: GeminiCLIAdapter, sample_session_file: Path
    ) -> None:
        """Test model detection during batch processing."""
        adapter.process_session_file_batch(sample_session_file)

        assert adapter.detected_model == "gemini-2.5-pro"


# ============================================================================
# Platform Metadata Tests
# ============================================================================


class TestPlatformMetadata:
    """Tests for platform metadata."""

    def test_get_platform_metadata(self, adapter: GeminiCLIAdapter) -> None:
        """Test platform metadata includes correct fields."""
        adapter.detected_model = "gemini-2.5-pro"
        adapter.model_name = "Gemini 2.5 Pro"
        adapter.thoughts_tokens = 500

        metadata = adapter.get_platform_metadata()

        assert metadata["model"] == "gemini-2.5-pro"
        assert metadata["model_name"] == "Gemini 2.5 Pro"
        assert metadata["thoughts_tokens"] == 500
        assert "gemini_dir" in metadata


# ============================================================================
# Integration Tests
# ============================================================================


class TestGeminiCLIAdapterIntegration:
    """Integration tests for complete workflow."""

    def test_complete_batch_workflow(
        self, adapter: GeminiCLIAdapter, sample_session_file: Path, tmp_path: Path
    ) -> None:
        """Test complete batch processing workflow."""
        adapter.process_session_file_batch(sample_session_file)
        session = adapter.finalize_session()
        adapter.save_session(tmp_path / "output")

        # Verify session data
        assert session.project == "test-project"
        assert session.platform == "gemini-cli"
        assert session.model == "gemini-2.5-pro"

        # Verify MCP calls tracked (1 mcp__zen__chat call)
        assert session.mcp_tool_calls.total_calls == 1

        # Verify files saved
        assert adapter.session_dir is not None


# ============================================================================
# Task-70 Feature Tests
# ============================================================================


class TestGitMetadata:
    """Tests for git metadata collection (task-70.1)."""

    def test_git_metadata_collected_on_init(self, tmp_path: Path) -> None:
        """Test that git metadata is collected during initialization."""
        adapter = GeminiCLIAdapter(project="test", gemini_dir=tmp_path)

        # Git metadata should be a dict (may be empty if not in a git repo)
        assert hasattr(adapter, "_git_metadata")
        assert isinstance(adapter._git_metadata, dict)
        assert "branch" in adapter._git_metadata
        assert "commit_short" in adapter._git_metadata
        assert "status" in adapter._git_metadata


class TestGeminiMcpToolDetection:
    """Tests for Gemini CLI MCP tool detection (task-69.28).

    Gemini CLI uses <server>__<tool> format for MCP tools, not mcp__<server>__<tool>.
    This test class verifies the _is_gemini_mcp_tool helper method correctly
    identifies MCP tools and distinguishes them from built-in tools.
    """

    def test_is_gemini_mcp_tool_detects_mcp_tools(self, adapter: GeminiCLIAdapter) -> None:
        """Test MCP tools with <server>__<tool> format are detected."""
        # These should all be detected as MCP tools
        assert adapter._is_gemini_mcp_tool("fs__read_file") is True
        assert adapter._is_gemini_mcp_tool("fs__list_directory") is True
        assert adapter._is_gemini_mcp_tool("brave__search") is True
        assert adapter._is_gemini_mcp_tool("github__list_repos") is True
        assert adapter._is_gemini_mcp_tool("zen__chat") is True

    def test_is_gemini_mcp_tool_rejects_builtin_tools(self, adapter: GeminiCLIAdapter) -> None:
        """Test built-in tools are NOT detected as MCP tools."""
        from token_audit.gemini_cli_adapter import GEMINI_BUILTIN_TOOLS

        # All built-in tools should return False
        for tool in GEMINI_BUILTIN_TOOLS:
            assert adapter._is_gemini_mcp_tool(tool) is False, f"{tool} should not be MCP tool"

    def test_is_gemini_mcp_tool_rejects_internal_markers(self, adapter: GeminiCLIAdapter) -> None:
        """Test internal markers are NOT detected as MCP tools."""
        assert adapter._is_gemini_mcp_tool("__session__") is False
        assert adapter._is_gemini_mcp_tool("__builtin__") is False
        assert adapter._is_gemini_mcp_tool("__internal__:test") is False

    def test_is_gemini_mcp_tool_rejects_simple_names(self, adapter: GeminiCLIAdapter) -> None:
        """Test simple tool names without __ are NOT detected as MCP tools."""
        assert adapter._is_gemini_mcp_tool("search") is False
        assert adapter._is_gemini_mcp_tool("read") is False
        assert adapter._is_gemini_mcp_tool("unknown_tool") is False

    def test_mcp_tool_call_parsed_and_normalized(self, adapter: GeminiCLIAdapter) -> None:
        """Test Gemini MCP tool calls are parsed and normalized to mcp__ format (task-69.28)."""
        msg = GeminiMessage(
            id="msg-mcp",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-mcp-001",
                    "name": "fs__read_file",  # Gemini MCP format
                    "args": {"path": "/test/file.txt"},
                    "status": "success",
                    "result": [{"functionResponse": {"response": {"output": "file content"}}}],
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 10,
                "total": 160,
            },
        )

        # Process the message
        adapter.parse_event(msg)

        # Verify MCP tool was detected and normalized
        # The tool should be stored under the server name "fs" with normalized tool name
        assert "fs" in adapter.server_sessions, "MCP server 'fs' should be tracked"
        assert (
            "mcp__fs__read_file" in adapter.server_sessions["fs"].tools
        ), "Tool should be normalized to mcp__fs__read_file"

    def test_mcp_tool_token_estimation_applied(self, adapter: GeminiCLIAdapter) -> None:
        """Test token estimation is applied to Gemini MCP tools (task-69.28)."""
        msg = GeminiMessage(
            id="msg-mcp-est",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-mcp-002",
                    "name": "fs__read_file",
                    "args": {"path": "/pyproject.toml"},
                    "status": "success",
                    "result": [{"functionResponse": {"response": {"output": "test content"}}}],
                }
            ],
            tokens={
                "input": 100,
                "output": 50,
                "cached": 0,
                "thoughts": 0,
                "tool": 0,  # No native tool tokens
                "total": 150,
            },
        )

        # Process the message
        adapter.parse_event(msg)

        # Verify token estimation was applied
        assert adapter._estimated_tool_calls >= 1, "Should have at least 1 estimated tool call"


class TestBuiltinToolTracking:
    """Tests for built-in tool tracking (task-70.2)."""

    def test_builtin_tool_counters_initialized(self, adapter: GeminiCLIAdapter) -> None:
        """Test built-in tool counters are initialized."""
        assert adapter._builtin_tool_calls == 0
        assert adapter._builtin_tool_tokens == 0

    def test_all_gemini_builtin_tools_recognized(self, adapter: GeminiCLIAdapter) -> None:
        """Test all known Gemini CLI built-in tools are tracked.

        Tool names from official source:
        https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/tools/tool-names.ts
        """
        from token_audit.gemini_cli_adapter import GEMINI_BUILTIN_TOOLS

        # All these tools should be in the set (official names from Gemini CLI source)
        expected_tools = {
            "glob",  # File pattern matching
            "google_web_search",  # Web search
            "list_directory",  # Directory listing (ls)
            "read_file",  # Read single file
            "read_many_files",  # Read multiple files
            "replace",  # File content replacement (edit)
            "run_shell_command",  # Shell execution
            "save_memory",  # Memory/context saving
            "search_file_content",  # Grep/ripgrep search
            "web_fetch",  # Fetch web content
            "write_file",  # Write file
            "write_todos",  # Task management
        }

        for tool in expected_tools:
            assert tool in GEMINI_BUILTIN_TOOLS, f"{tool} should be in GEMINI_BUILTIN_TOOLS"

    def test_builtin_tools_all_processed(self, adapter: GeminiCLIAdapter) -> None:
        """Test all built-in tools are processed and counted (task-72.1)."""
        builtin_tools = ["read_file", "list_directory", "google_web_search", "run_shell_command"]

        for i, tool_name in enumerate(builtin_tools):
            msg = GeminiMessage(
                id=f"msg-{i:03d}",
                timestamp=datetime.now(tz=timezone.utc),
                message_type="gemini",
                content="Result",
                model="gemini-2.5-pro",
                tool_calls=[
                    {
                        "id": f"call-{i:03d}",
                        "name": tool_name,
                        "args": {},
                        "status": "success",
                    }
                ],
                tokens={
                    "input": 10,
                    "output": 5,
                    "cached": 0,
                    "thoughts": 0,
                    "tool": 5,
                    "total": 20,
                },
            )

            result = adapter.parse_event(msg)
            # Always returns session tokens
            assert result is not None
            parsed_name, _ = result
            assert parsed_name == "__session__"

        # All 4 built-in tools were processed
        assert adapter._builtin_tool_calls == 4


class TestBuiltinToolsPersistence:
    """Tests for built-in tool persistence to session file (task-72.3)."""

    def test_builtin_tools_saved_to_session_file(
        self, adapter: GeminiCLIAdapter, tmp_path: Path
    ) -> None:
        """Test that built-in tools are saved to session file, not just displayed."""
        msg = GeminiMessage(
            id="msg-builtin-persist",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="I used built-in tools",
            model="gemini-2.5-flash",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",
                    "args": {"path": "/test/file.txt"},
                    "status": "success",
                },
                {
                    "id": "call-002",
                    "name": "list_directory",
                    "args": {"path": "/test"},
                    "status": "success",
                },
            ],
            tokens={
                "input": 1000,
                "output": 50,
                "cached": 200,
                "thoughts": 0,
                "tool": 25,
                "total": 1275,
            },
        )

        # Process the message
        result = adapter.parse_event(msg)
        assert result is not None

        # Finalize and save session
        adapter.finalize_session()
        output_dir = tmp_path / "sessions"
        adapter.save_session(output_dir)

        # Read saved session file
        assert adapter.session_path is not None
        with open(adapter.session_path) as f:
            saved_data = json.load(f)

        # Verify built-in tools are in tool_calls array
        tool_calls = saved_data.get("tool_calls", [])
        assert len(tool_calls) == 2, (
            f"Expected 2 built-in tool calls in session file, got {len(tool_calls)}. "
            "Built-in tools may not be saved to session file."
        )

        # Verify tool names are properly formatted
        tool_names = [call["tool"] for call in tool_calls]
        assert "builtin__read_file" in tool_names
        assert "builtin__list_directory" in tool_names

        # Verify server is set to "builtin"
        for call in tool_calls:
            assert call["server"] == "builtin"

    def test_mixed_tools_all_saved_to_session(
        self, adapter: GeminiCLIAdapter, tmp_path: Path
    ) -> None:
        """Test that both MCP and built-in tools are saved to session file."""
        msg = GeminiMessage(
            id="msg-mixed-persist",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="I used both MCP and built-in tools",
            model="gemini-2.5-flash",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",  # Built-in
                    "args": {"path": "/test"},
                    "status": "success",
                },
                {
                    "id": "call-002",
                    "name": "mcp__zen__chat",  # MCP
                    "args": {"prompt": "test"},
                    "status": "success",
                },
            ],
            tokens={
                "input": 500,
                "output": 25,
                "cached": 100,
                "thoughts": 0,
                "tool": 10,
                "total": 635,
            },
        )

        result = adapter.parse_event(msg)
        assert result is not None

        adapter.finalize_session()
        output_dir = tmp_path / "sessions"
        adapter.save_session(output_dir)

        assert adapter.session_path is not None
        with open(adapter.session_path) as f:
            saved_data = json.load(f)

        tool_calls = saved_data.get("tool_calls", [])
        assert len(tool_calls) == 2

        tool_names = [call["tool"] for call in tool_calls]
        assert "builtin__read_file" in tool_names
        assert "mcp__zen__chat" in tool_names


class TestDisplayEventNotification:
    """Tests for display event notification (task-70.3)."""

    def test_process_parsed_event_notifies_display(self, adapter: GeminiCLIAdapter) -> None:
        """Test that _process_parsed_event calls display.on_event."""
        from unittest.mock import Mock

        # Set up mock display
        mock_display = Mock()
        adapter._display = mock_display

        # Process an MCP event
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "success": True,
        }
        adapter._process_parsed_event("mcp__test__tool", usage)

        # Verify on_event was called
        mock_display.on_event.assert_called_once()
        call_args = mock_display.on_event.call_args
        assert call_args[0][0] == "mcp__test__tool"  # tool_name
        assert call_args[0][1] == 150  # total_tokens

    def test_builtin_tool_notifies_display(self, adapter: GeminiCLIAdapter) -> None:
        """Test that built-in tools notify display with [built-in] prefix."""
        from unittest.mock import Mock

        mock_display = Mock()
        adapter._display = mock_display

        usage = {
            "input_tokens": 0,
            "output_tokens": 50,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "success": True,
        }
        adapter._process_parsed_event("__builtin__:read_file", usage)

        mock_display.on_event.assert_called_once()
        call_args = mock_display.on_event.call_args
        assert call_args[0][0] == "[built-in] read_file"


class TestDisplaySnapshot:
    """Tests for DisplaySnapshot creation (task-70.1, 70.5)."""

    def test_display_snapshot_includes_git_metadata(self, adapter: GeminiCLIAdapter) -> None:
        """Test DisplaySnapshot includes git metadata."""
        adapter._start_time = datetime.now()
        adapter._git_metadata = {
            "branch": "main",
            "commit_short": "abc1234",
            "status": "clean",
        }

        snapshot = adapter._build_display_snapshot()

        assert snapshot.git_branch == "main"
        assert snapshot.git_commit_short == "abc1234"
        assert snapshot.git_status == "clean"

    def test_display_snapshot_includes_builtin_tool_counts(self, adapter: GeminiCLIAdapter) -> None:
        """Test DisplaySnapshot includes built-in tool counts."""
        adapter._start_time = datetime.now()
        adapter._builtin_tool_calls = 5
        adapter._builtin_tool_tokens = 500

        snapshot = adapter._build_display_snapshot()

        assert snapshot.builtin_tool_calls == 5
        assert snapshot.builtin_tool_tokens == 500

    def test_display_snapshot_includes_health_status(self, adapter: GeminiCLIAdapter) -> None:
        """Test DisplaySnapshot includes warnings and health status."""
        adapter._start_time = datetime.now()
        adapter._warnings = []

        snapshot = adapter._build_display_snapshot()

        assert snapshot.warnings_count == 0
        assert snapshot.health_status == "healthy"


# ============================================================================
# Source Files Tracking Tests (Task-50.3)
# ============================================================================


class TestSourceFilesTracking:
    """Tests for tracking source files from tool calls."""

    def test_source_files_populated_from_tool_calls(self, tmp_path: Path) -> None:
        """Test that source_files are correctly populated from tool call parameters."""
        test_file_path = "path/to/test_file.txt"
        session_data = make_sample_session(include_mcp_tools=False)  # Start with no MCP tools

        # Add a gemini message with a built-in read_file tool call
        session_data["messages"].append(
            {
                "id": "msg-004",
                "type": "gemini",
                "content": "Reading a file.",
                "model": "gemini-2.5-pro",
                "toolCalls": [
                    {
                        "id": "call-001",
                        "name": "read_file",
                        "args": {"file_path": test_file_path},
                        "status": "success",
                    }
                ],
                "tokens": {
                    "input": 10,
                    "output": 5,
                    "cached": 0,
                    "thoughts": 0,
                    "tool": 5,
                    "total": 20,
                },
                "timestamp": "2025-11-07T05:11:00.000Z",
            }
        )

        chats_dir = tmp_path / ".gemini" / "tmp" / ("a" * 64) / "chats"
        chats_dir.mkdir(parents=True)
        session_file = chats_dir / "session-2025-11-07T05-10-test.json"
        session_file.write_text(json.dumps(session_data))

        adapter = GeminiCLIAdapter(
            project="test-project",
            gemini_dir=tmp_path / ".gemini",
            session_file=session_file,
            from_start=True,
        )

        # Use process_session_file_batch for batch testing (not start_tracking which is infinite loop)
        adapter.process_session_file_batch(session_file)
        session = adapter.finalize_session()

        # The initial session file name and the file from the tool call should be present
        expected_source_files = sorted([session_file.name, test_file_path])
        assert session.source_files == expected_source_files
        assert test_file_path in session.source_files

    def test_source_files_populated_from_multiple_tool_calls(self, tmp_path: Path) -> None:
        """Test that source_files are correctly populated from multiple tool calls."""
        file_path_1 = "path/to/file1.txt"
        file_path_2 = "another/path/file2.json"
        dir_path_1 = "dir/path"

        session_data = make_sample_session(include_mcp_tools=False)

        session_data["messages"].append(
            {
                "id": "msg-004",
                "type": "gemini",
                "content": "Multiple file operations.",
                "model": "gemini-2.5-pro",
                "toolCalls": [
                    {
                        "id": "call-001",
                        "name": "read_file",
                        "args": {"file_path": file_path_1},
                        "status": "success",
                    },
                    {
                        "id": "call-002",
                        "name": "write_file",
                        "args": {"file_path": file_path_2, "content": "data"},
                        "status": "success",
                    },
                    {
                        "id": "call-003",
                        "name": "list_directory",
                        "args": {"dir_path": dir_path_1},
                        "status": "success",
                    },
                ],
                "tokens": {
                    "input": 30,
                    "output": 15,
                    "cached": 0,
                    "thoughts": 0,
                    "tool": 15,
                    "total": 60,
                },
                "timestamp": "2025-11-07T05:11:00.000Z",
            }
        )

        chats_dir = tmp_path / ".gemini" / "tmp" / ("a" * 64) / "chats"
        chats_dir.mkdir(parents=True)
        session_file = chats_dir / "session-2025-11-07T05-10-test.json"
        session_file.write_text(json.dumps(session_data))

        adapter = GeminiCLIAdapter(
            project="test-project",
            gemini_dir=tmp_path / ".gemini",
            session_file=session_file,
            from_start=True,
        )

        # Use process_session_file_batch for batch testing (not start_tracking which is infinite loop)
        adapter.process_session_file_batch(session_file)
        session = adapter.finalize_session()

        expected_source_files = sorted([session_file.name, file_path_1, file_path_2, dir_path_1])
        assert session.source_files == expected_source_files


# ============================================================================
# Cost Calculation Tests (Task 97)
# ============================================================================


class TestCostCalculation:
    """Tests for cost calculation - verifying cache_read is subset of input_tokens."""

    def test_cost_calculation_cache_as_subset(self, tmp_path: Path) -> None:
        """
        Test that cost calculation treats cache_read as SUBSET of input_tokens.

        In Gemini CLI:
        - input_tokens = total input/prompt tokens
        - cache_read = portion of input_tokens served from cache (NOT additive)
        - fresh_input = input_tokens - cache_read

        Cost formula should be:
        - cost_with_cache = (fresh_input * input_rate) + (cache_read * cache_rate) + (output * output_rate)
        - cost_no_cache = (input_tokens * input_rate) + (output * output_rate)
        """
        # Create session with known token values
        session_data = {
            "sessionId": "cost-test-session",
            "projectHash": "a" * 64,
            "startTime": "2025-12-08T01:00:00.000Z",
            "lastUpdated": "2025-12-08T01:10:00.000Z",
            "messages": [
                {
                    "id": "msg-001",
                    "type": "user",
                    "content": "Test",
                    "timestamp": "2025-12-08T01:00:00.000Z",
                },
                {
                    "id": "msg-002",
                    "type": "gemini",
                    "content": "Response",
                    "model": "gemini-2.5-pro",  # $1.25/M input, $10/M output, $0.125/M cache
                    "tokens": {
                        "input": 1_000_000,  # 1M total input tokens
                        "output": 100_000,  # 100K output tokens
                        "cached": 800_000,  # 800K of the 1M came from cache
                        "thoughts": 0,
                        "tool": 0,
                        "total": 1_100_000,
                    },
                    "timestamp": "2025-12-08T01:05:00.000Z",
                },
            ],
        }

        chats_dir = tmp_path / ".gemini" / "tmp" / ("a" * 64) / "chats"
        chats_dir.mkdir(parents=True)
        session_file = chats_dir / "session-2025-12-08T01-00-test.json"
        session_file.write_text(json.dumps(session_data))

        adapter = GeminiCLIAdapter(
            project="cost-test",
            gemini_dir=tmp_path / ".gemini",
            session_file=session_file,
            from_start=True,
        )

        adapter.process_session_file_batch(session_file)
        # _build_display_snapshot calculates and stores costs in session
        adapter._start_time = datetime.now()  # Set for snapshot (naive)
        adapter._build_display_snapshot()
        session = adapter.finalize_session()

        # Expected costs with gemini-2.5-pro pricing:
        # input: $1.25/M, output: $10.0/M, cache_read: $0.125/M
        #
        # fresh_input = 1,000,000 - 800,000 = 200,000
        # cost_with_cache = (200K * $1.25/M) + (800K * $0.125/M) + (100K * $10/M)
        #                 = $0.25 + $0.10 + $1.00 = $1.35
        #
        # cost_no_cache = (1M * $1.25/M) + (100K * $10/M)
        #               = $1.25 + $1.00 = $2.25
        #
        # savings = $2.25 - $1.35 = $0.90

        expected_cost_with_cache = 1.35
        expected_cost_no_cache = 2.25
        expected_savings = 0.90

        assert abs(session.cost_estimate - expected_cost_with_cache) < 0.01, (
            f"cost_estimate should be ~${expected_cost_with_cache:.2f}, "
            f"got ${session.cost_estimate:.2f}"
        )
        assert abs(session.cost_no_cache - expected_cost_no_cache) < 0.01, (
            f"cost_no_cache should be ~${expected_cost_no_cache:.2f}, "
            f"got ${session.cost_no_cache:.2f}"
        )
        assert abs(session.cache_savings_usd - expected_savings) < 0.01, (
            f"cache_savings should be ~${expected_savings:.2f}, "
            f"got ${session.cache_savings_usd:.2f}"
        )

    def test_cost_calculation_no_cache(self, tmp_path: Path) -> None:
        """Test cost calculation when there's no caching (cache_read = 0)."""
        session_data = {
            "sessionId": "no-cache-test",
            "projectHash": "b" * 64,
            "startTime": "2025-12-08T02:00:00.000Z",
            "lastUpdated": "2025-12-08T02:10:00.000Z",
            "messages": [
                {
                    "id": "msg-001",
                    "type": "user",
                    "content": "Test",
                    "timestamp": "2025-12-08T02:00:00.000Z",
                },
                {
                    "id": "msg-002",
                    "type": "gemini",
                    "content": "Response",
                    "model": "gemini-2.5-pro",
                    "tokens": {
                        "input": 500_000,
                        "output": 50_000,
                        "cached": 0,  # No caching
                        "thoughts": 0,
                        "tool": 0,
                        "total": 550_000,
                    },
                    "timestamp": "2025-12-08T02:05:00.000Z",
                },
            ],
        }

        chats_dir = tmp_path / ".gemini" / "tmp" / ("b" * 64) / "chats"
        chats_dir.mkdir(parents=True)
        session_file = chats_dir / "session-2025-12-08T02-00-test.json"
        session_file.write_text(json.dumps(session_data))

        adapter = GeminiCLIAdapter(
            project="no-cache-test",
            gemini_dir=tmp_path / ".gemini",
            session_file=session_file,
            from_start=True,
        )

        adapter.process_session_file_batch(session_file)
        # _build_display_snapshot calculates and stores costs in session
        adapter._start_time = datetime.now()  # Set for snapshot (naive)
        adapter._build_display_snapshot()
        session = adapter.finalize_session()

        # With no caching:
        # cost = (500K * $1.25/M) + (50K * $10/M) = $0.625 + $0.50 = $1.125
        # cost_no_cache should equal cost_with_cache
        # savings = 0

        expected_cost = 1.125

        assert abs(session.cost_estimate - expected_cost) < 0.01
        assert abs(session.cost_no_cache - expected_cost) < 0.01
        assert abs(session.cache_savings_usd) < 0.01  # No savings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
