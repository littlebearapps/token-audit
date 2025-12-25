#!/usr/bin/env python3
"""
Integration tests for Claude Code adapter.

Tests the ClaudeCodeAdapter's ability to:
1. Find Claude Code directories
2. Parse JSONL events
3. Track tokens from new content
4. Handle session-level events (__session__)
5. Handle MCP tool call events
"""

import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from token_audit.claude_code_adapter import ClaudeCodeAdapter
from token_audit.display import NullDisplay


@pytest.fixture
def mock_claude_dir() -> Generator[Path, None, None]:
    """Create a temporary Claude Code directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_jsonl_content() -> str:
    """Sample JSONL content with various event types."""
    events = [
        # Summary event (skipped)
        {"type": "summary", "summary": "Test session"},
        # User message (skipped - no usage)
        {
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
        },
        # Assistant message with usage (session event)
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-5-20251101",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello!"}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 500,
                },
            },
        },
        # Assistant message with MCP tool call
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-5-20251101",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "mcp__zen__chat",
                        "input": {"prompt": "test"},
                    }
                ],
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "cache_creation_input_tokens": 2000,
                    "cache_read_input_tokens": 1000,
                },
            },
        },
    ]
    return "\n".join(json.dumps(e) for e in events)


class TestClaudeCodeAdapterInitialization:
    """Test adapter initialization and directory detection."""

    def test_initialization_with_claude_dir(self, mock_claude_dir: Path) -> None:
        """Test adapter initialization with explicit claude_dir."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        assert adapter.project == "test-project"
        assert adapter.claude_dir == mock_claude_dir
        assert adapter.platform == "claude-code"

    def test_find_jsonl_files_empty_dir(self, mock_claude_dir: Path) -> None:
        """Test finding JSONL files in empty directory."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        files = adapter._find_jsonl_files()
        assert files == []

    def test_find_jsonl_files_with_files(self, mock_claude_dir: Path) -> None:
        """Test finding JSONL files in directory with files."""
        # Create test files
        (mock_claude_dir / "session1.jsonl").write_text('{"type": "test"}')
        (mock_claude_dir / "session2.jsonl").write_text('{"type": "test"}')
        (mock_claude_dir / "other.txt").write_text("not jsonl")

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        files = adapter._find_jsonl_files()

        assert len(files) == 2
        assert all(f.suffix == ".jsonl" for f in files)


class TestEventParsing:
    """Test JSONL event parsing."""

    def test_parse_summary_event(self, mock_claude_dir: Path) -> None:
        """Summary events should return None (skipped)."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        event = '{"type": "summary", "summary": "Test"}'
        result = adapter.parse_event(event)
        assert result is None

    def test_parse_user_event(self, mock_claude_dir: Path) -> None:
        """User events should return None (skipped)."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        event = '{"type": "user", "message": {"role": "user", "content": "Hi"}}'
        result = adapter.parse_event(event)
        assert result is None

    def test_parse_assistant_event_with_usage(self, mock_claude_dir: Path) -> None:
        """Assistant events with usage should return __session__ data."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello!"}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_creation_input_tokens": 1000,
                        "cache_read_input_tokens": 500,
                    },
                },
            }
        )
        result = adapter.parse_event(event)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "__session__"
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["cache_created_tokens"] == 1000
        assert usage["cache_read_tokens"] == 500

    def test_parse_assistant_event_with_mcp_tool(self, mock_claude_dir: Path) -> None:
        """Assistant events with MCP tools should return tool name and usage."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "mcp__zen__chat",
                            "input": {"prompt": "test"},
                        }
                    ],
                    "usage": {
                        "input_tokens": 200,
                        "output_tokens": 100,
                        "cache_creation_input_tokens": 2000,
                        "cache_read_input_tokens": 1000,
                    },
                },
            }
        )
        result = adapter.parse_event(event)

        assert result is not None
        tool_name, usage = result
        assert tool_name == "mcp__zen__chat"
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 100

    def test_parse_invalid_json(self, mock_claude_dir: Path) -> None:
        """Invalid JSON should return None."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        result = adapter.parse_event("not valid json")
        assert result is None


class TestTokenAccumulation:
    """Test token accumulation via _process_tool_call."""

    def test_process_session_event(self, mock_claude_dir: Path) -> None:
        """Session events should accumulate tokens."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_created_tokens": 1000,
            "cache_read_tokens": 500,
        }
        adapter._process_tool_call("__session__", usage)

        assert adapter.session.token_usage.input_tokens == 100
        assert adapter.session.token_usage.output_tokens == 50
        assert adapter.session.token_usage.cache_created_tokens == 1000
        assert adapter.session.token_usage.cache_read_tokens == 500
        assert adapter.session.token_usage.total_tokens == 1650

    def test_process_mcp_tool_call(self, mock_claude_dir: Path) -> None:
        """MCP tool calls should be recorded and tokens accumulated."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        usage = {
            "input_tokens": 200,
            "output_tokens": 100,
            "cache_created_tokens": 2000,
            "cache_read_tokens": 1000,
        }
        adapter._process_tool_call("mcp__zen__chat", usage)

        # Check tokens accumulated
        assert adapter.session.token_usage.total_tokens == 3300

        # Check server session created
        assert "zen" in adapter.server_sessions
        assert adapter.server_sessions["zen"].total_calls == 1

    def test_multiple_tool_calls(self, mock_claude_dir: Path) -> None:
        """Multiple tool calls should accumulate correctly."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # First call
        adapter._process_tool_call(
            "__session__",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 0,
                "cache_read_tokens": 0,
            },
        )

        # Second call (MCP)
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_created_tokens": 0,
                "cache_read_tokens": 0,
            },
        )

        # Third call (MCP)
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 300,
                "output_tokens": 150,
                "cache_created_tokens": 0,
                "cache_read_tokens": 0,
            },
        )

        assert adapter.session.token_usage.total_tokens == 900
        assert adapter.server_sessions["zen"].total_calls == 2


class TestFileMonitoring:
    """Test file monitoring functionality."""

    def test_monitor_detects_new_content(
        self,
        mock_claude_dir: Path,
        sample_jsonl_content: str,
    ) -> None:
        """Monitor should detect and process new content written to files."""
        # Create initial file
        test_file = mock_claude_dir / "session.jsonl"
        test_file.write_text("")

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Initialize monitoring state
        adapter._tracking_start_time = time.time()
        adapter._start_time = __import__("datetime").datetime.now()
        adapter._last_display_update = 0.0
        adapter._display = NullDisplay()

        # Initialize file positions
        files = adapter._find_jsonl_files()
        for file_path in files:
            adapter.file_positions[file_path] = file_path.stat().st_size

        # Write new content
        test_file.write_text(sample_jsonl_content)

        # Run one iteration of monitoring
        files = adapter._find_jsonl_files()
        for file_path in files:
            if file_path in adapter.file_positions:
                with open(file_path) as f:
                    f.seek(adapter.file_positions[file_path])
                    new_content = f.read()
                    if new_content:
                        for line in new_content.split("\n"):
                            if line.strip():
                                result = adapter.parse_event(line)
                                if result:
                                    tool_name, usage = result
                                    adapter._process_tool_call(tool_name, usage)
                    adapter.file_positions[file_path] = f.tell()

        # Verify tokens were accumulated
        # From sample content: 2 assistant messages
        # Session event: 100+50+1000+500 = 1650
        # MCP event: 200+100+2000+1000 = 3300
        # Total: 4950
        assert adapter.session.token_usage.total_tokens == 4950

    def test_monitor_handles_new_files(self, mock_claude_dir: Path) -> None:
        """Monitor should detect and handle new files created during monitoring."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Initialize with empty directory
        adapter._tracking_start_time = time.time()
        files = adapter._find_jsonl_files()
        assert len(files) == 0

        # Create new file after tracking starts
        time.sleep(0.1)  # Ensure creation time is after tracking start
        new_file = mock_claude_dir / "new_session.jsonl"
        new_file.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-4-5-20251101",
                        "role": "assistant",
                        "content": [],
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                        },
                    },
                }
            )
        )

        # Find new files
        files = adapter._find_jsonl_files()
        assert len(files) == 1

        # New file should be read from beginning
        for file_path in files:
            if file_path not in adapter.file_positions:
                creation_time = adapter._get_file_creation_time(file_path)
                if creation_time >= adapter._tracking_start_time:
                    adapter.file_positions[file_path] = 0
                else:
                    adapter.file_positions[file_path] = file_path.stat().st_size

        assert adapter.file_positions[new_file] == 0


class TestDisplaySnapshot:
    """Test display snapshot building."""

    def test_build_display_snapshot(self, mock_claude_dir: Path) -> None:
        """Display snapshot should reflect current session state."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        adapter._start_time = __import__("datetime").datetime.now()

        # Add some data
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 1000,
                "cache_read_tokens": 500,
            },
        )

        snapshot = adapter._build_display_snapshot()

        assert snapshot.project == "test-project"
        assert snapshot.platform == "claude-code"
        assert snapshot.total_tokens == 1650
        assert snapshot.total_tool_calls == 1
        assert snapshot.unique_tools == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_file(self, mock_claude_dir: Path) -> None:
        """Empty files should be handled gracefully."""
        (mock_claude_dir / "empty.jsonl").write_text("")

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        files = adapter._find_jsonl_files()
        assert len(files) == 1  # Empty files should be included

    def test_malformed_json_line(self, mock_claude_dir: Path) -> None:
        """Malformed JSON lines should be handled gracefully."""
        test_file = mock_claude_dir / "test.jsonl"
        test_file.write_text("not json\n{invalid\n")

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Should not raise
        for line in test_file.read_text().split("\n"):
            result = adapter.parse_event(line)
            assert result is None

    def test_missing_usage_field(self, mock_claude_dir: Path) -> None:
        """Assistant messages without usage should return None."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [],
                    # No usage field
                },
            }
        )
        result = adapter.parse_event(event)
        assert result is None


class TestModelPriority:
    """Test model detection priority (opus > sonnet > haiku)."""

    def test_model_priority_prefers_opus_over_haiku(self, mock_claude_dir: Path) -> None:
        """When Haiku appears before Opus, Opus should be preferred."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # First, process a Haiku message (lower priority)
        haiku_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-haiku-4-5-20251001",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        adapter.parse_event(haiku_event)

        # Model should be set to Haiku initially
        assert adapter.detected_model == "claude-haiku-4-5-20251001"
        assert adapter.model_name == "Claude Haiku 4.5"

        # Now process an Opus message (higher priority)
        opus_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            }
        )
        adapter.parse_event(opus_event)

        # Model should be updated to Opus (higher priority)
        assert adapter.detected_model == "claude-opus-4-5-20251101"
        assert adapter.model_name == "Claude Opus 4.5"
        assert adapter.session.model == "claude-opus-4-5-20251101"

    def test_model_priority_keeps_opus_when_haiku_follows(self, mock_claude_dir: Path) -> None:
        """When Opus appears before Haiku, Opus should be kept."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # First, process an Opus message
        opus_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-5-20251101",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            }
        )
        adapter.parse_event(opus_event)

        assert adapter.detected_model == "claude-opus-4-5-20251101"

        # Now process a Haiku message (should NOT override)
        haiku_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-haiku-4-5-20251001",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        adapter.parse_event(haiku_event)

        # Model should remain Opus
        assert adapter.detected_model == "claude-opus-4-5-20251101"
        assert adapter.model_name == "Claude Opus 4.5"

    def test_model_priority_sonnet_between_opus_and_haiku(self, mock_claude_dir: Path) -> None:
        """Sonnet should upgrade from Haiku but not from Opus."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Start with Haiku
        haiku_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-haiku-4-5-20251001",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        adapter.parse_event(haiku_event)
        assert "haiku" in adapter.detected_model.lower()

        # Upgrade to Sonnet
        sonnet_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "role": "assistant",
                    "content": [],
                    "usage": {"input_tokens": 50, "output_tokens": 25},
                },
            }
        )
        adapter.parse_event(sonnet_event)
        assert adapter.detected_model == "claude-sonnet-4-5-20250929"
        assert adapter.model_name == "Claude Sonnet 4.5"

        # Haiku should NOT downgrade
        adapter.parse_event(haiku_event)
        assert adapter.detected_model == "claude-sonnet-4-5-20250929"


class TestClaudeCodeCacheAnalysis:
    """Test cache_analysis for Claude Code platform (task-47.5)"""

    def test_cache_analysis_efficient(self, mock_claude_dir: Path) -> None:
        """Test cache analysis shows efficient when read > creation"""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        # High cache read, low creation = efficient
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 1000,  # Claude Code has cache creation
                "cache_read_tokens": 10000,  # 10x read ratio = efficient
            },
        )

        session = adapter.finalize_session()
        analysis = session._build_cache_analysis()

        assert analysis.status == "efficient"
        assert analysis.creation_tokens == 1000
        assert analysis.read_tokens == 10000
        assert analysis.ratio == 10.0

    def test_cache_analysis_inefficient(self, mock_claude_dir: Path) -> None:
        """Test cache analysis shows inefficient when creation > read"""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        # High creation, low read = inefficient
        adapter._process_tool_call(
            "mcp__zen__thinkdeep",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 50000,  # High creation
                "cache_read_tokens": 0,  # No reuse
            },
        )

        session = adapter.finalize_session()
        analysis = session._build_cache_analysis()

        assert analysis.status == "inefficient"
        assert analysis.creation_tokens == 50000
        assert analysis.read_tokens == 0

    def test_cache_analysis_in_session_dict(self, mock_claude_dir: Path) -> None:
        """Test cache_analysis included in session.to_dict() for Claude Code"""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 5000,
                "cache_read_tokens": 20000,
            },
        )

        session = adapter.finalize_session()
        session_dict = session.to_dict()

        assert "cache_analysis" in session_dict
        cache_analysis = session_dict["cache_analysis"]
        assert "status" in cache_analysis
        assert "summary" in cache_analysis
        assert "top_cache_creators" in cache_analysis
        assert "top_cache_readers" in cache_analysis

    def test_per_tool_cache_tracking_claude_code(self, mock_claude_dir: Path) -> None:
        """Test per-tool cache tracking works for Claude Code"""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        # Tool that creates cache
        adapter._process_tool_call(
            "mcp__zen__thinkdeep",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 50000,
                "cache_read_tokens": 0,
            },
        )
        # Tool that reads cache
        adapter._process_tool_call(
            "mcp__zen__chat",
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_created_tokens": 0,
                "cache_read_tokens": 40000,
            },
        )

        session = adapter.finalize_session()

        # Verify per-tool cache tracking
        thinkdeep_stats = adapter.server_sessions["zen"].tools["mcp__zen__thinkdeep"]
        assert thinkdeep_stats.cache_created_tokens == 50000
        assert thinkdeep_stats.cache_read_tokens == 0

        chat_stats = adapter.server_sessions["zen"].tools["mcp__zen__chat"]
        assert chat_stats.cache_created_tokens == 0
        assert chat_stats.cache_read_tokens == 40000

        # Verify top creators/readers in analysis
        analysis = session._build_cache_analysis()
        assert len(analysis.top_cache_creators) > 0
        assert analysis.top_cache_creators[0]["tool"] == "mcp__zen__thinkdeep"
        assert len(analysis.top_cache_readers) > 0
        assert analysis.top_cache_readers[0]["tool"] == "mcp__zen__chat"


class TestSourceFilesTracking:
    """Test source_files population for Claude Code adapter (task-50)"""

    def test_active_source_files_initialized(self, mock_claude_dir: Path) -> None:
        """Test _active_source_files set initialized as empty."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        assert hasattr(adapter, "_active_source_files")
        assert isinstance(adapter._active_source_files, set)
        assert len(adapter._active_source_files) == 0

    def test_source_files_empty_initially(self, mock_claude_dir: Path) -> None:
        """Test session.source_files is empty list by default."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )
        assert adapter.session.source_files == []

    def test_source_files_populated_after_events(
        self, mock_claude_dir: Path, sample_jsonl_content: str
    ) -> None:
        """Test source_files populated with filenames after processing events."""
        # Create JSONL file
        jsonl_file = mock_claude_dir / "test-session.jsonl"
        jsonl_file.write_text(sample_jsonl_content)

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Simulate processing events from the file
        for line in sample_jsonl_content.split("\n"):
            if line.strip():
                result = adapter.parse_event(line)
                if result:
                    adapter._active_source_files.add(jsonl_file.name)
                    tool_name, usage = result
                    adapter._process_tool_call(tool_name, usage)

        # Populate source_files (simulating what happens on Ctrl+C)
        adapter.session.source_files = sorted(adapter._active_source_files)

        assert len(adapter.session.source_files) == 1
        assert adapter.session.source_files[0] == "test-session.jsonl"

    def test_source_files_only_filenames_not_paths(
        self, mock_claude_dir: Path, sample_jsonl_content: str
    ) -> None:
        """Test only filenames stored, not full paths (privacy)."""
        jsonl_file = mock_claude_dir / "session-abc123.jsonl"
        jsonl_file.write_text(sample_jsonl_content)

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Add file name (not full path)
        adapter._active_source_files.add(jsonl_file.name)
        adapter.session.source_files = sorted(adapter._active_source_files)

        # Verify only filename, no path components
        for filename in adapter.session.source_files:
            assert "/" not in filename
            assert "\\" not in filename

    def test_source_files_sorted_alphabetically(self, mock_claude_dir: Path) -> None:
        """Test source_files are sorted alphabetically."""
        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        # Add files in unsorted order
        adapter._active_source_files.add("z-session.jsonl")
        adapter._active_source_files.add("a-session.jsonl")
        adapter._active_source_files.add("m-session.jsonl")

        adapter.session.source_files = sorted(adapter._active_source_files)

        assert adapter.session.source_files == [
            "a-session.jsonl",
            "m-session.jsonl",
            "z-session.jsonl",
        ]

    def test_source_files_in_session_dict(
        self, mock_claude_dir: Path, sample_jsonl_content: str
    ) -> None:
        """Test source_files included in session.to_dict() output."""
        jsonl_file = mock_claude_dir / "test-session.jsonl"
        jsonl_file.write_text(sample_jsonl_content)

        adapter = ClaudeCodeAdapter(
            project="test-project",
            claude_dir=mock_claude_dir,
        )

        adapter._active_source_files.add(jsonl_file.name)
        adapter.session.source_files = sorted(adapter._active_source_files)

        session = adapter.finalize_session()
        session_dict = session.to_dict()

        assert "session" in session_dict
        assert "source_files" in session_dict["session"]
        assert session_dict["session"]["source_files"] == ["test-session.jsonl"]
