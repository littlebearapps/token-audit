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

from mcp_audit.gemini_cli_adapter import (
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
        assert usage["output_tokens"] == 150  # output + thoughts
        assert usage["cache_read_tokens"] == 500

    def test_parse_mcp_tool_call(self, adapter: GeminiCLIAdapter) -> None:
        """Test MCP tool call parsing."""
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

        assert result is not None
        tool_name, usage = result
        assert tool_name == "mcp__zen__chat"
        assert usage["success"] is True

    def test_native_tool_ignored(self, adapter: GeminiCLIAdapter) -> None:
        """Test native tools (not mcp__) are ignored."""
        msg = GeminiMessage(
            id="msg-003",
            timestamp=datetime.now(tz=timezone.utc),
            message_type="gemini",
            content="Result",
            model="gemini-2.5-pro",
            tool_calls=[
                {
                    "id": "call-001",
                    "name": "read_file",  # Native tool
                    "args": {"path": "/test"},
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

        # Should return session tokens, not tool call
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
