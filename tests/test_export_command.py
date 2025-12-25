"""
Tests for the export command (v1.5.0 - task-103.2).

Tests cover:
- AI prompt export in markdown format
- AI prompt export in JSON format
- Storage helper functions
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest


# ============================================================================
# Storage Helper Tests
# ============================================================================


class TestStorageHelpers:
    """Tests for storage helper functions."""

    def test_load_session_file_valid(self) -> None:
        """Test loading a valid session JSON file."""
        from token_audit.storage import load_session_file

        session_data = {
            "session": {"platform": "claude-code", "project": "test"},
            "token_usage": {"total_tokens": 1000},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(session_data, f)
            f.flush()
            file_path = Path(f.name)

        try:
            loaded = load_session_file(file_path)
            assert loaded is not None
            assert loaded["session"]["platform"] == "claude-code"
            assert loaded["token_usage"]["total_tokens"] == 1000
        finally:
            file_path.unlink()

    def test_load_session_file_invalid_json(self) -> None:
        """Test loading an invalid JSON file returns None."""
        from token_audit.storage import load_session_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            f.flush()
            file_path = Path(f.name)

        try:
            loaded = load_session_file(file_path)
            assert loaded is None
        finally:
            file_path.unlink()

    def test_load_session_file_missing(self) -> None:
        """Test loading a missing file returns None."""
        from token_audit.storage import load_session_file

        loaded = load_session_file(Path("/nonexistent/path.json"))
        assert loaded is None

    def test_get_latest_session_missing_dir(self) -> None:
        """Test get_latest_session with missing directory returns None."""
        from token_audit.storage import get_latest_session

        result = get_latest_session(Path("/nonexistent/directory"))
        assert result is None


# ============================================================================
# AI Prompt Generation Tests
# ============================================================================


class TestAIPromptGeneration:
    """Tests for AI prompt generation functions."""

    def test_generate_markdown_basic(self) -> None:
        """Test markdown generation with basic session data."""
        from token_audit.cli import generate_ai_prompt_markdown

        session_data = {
            "session": {
                "platform": "claude-code",
                "model": "claude-opus-4-5",
                "duration_seconds": 300,
                "project": "test-project",
            },
            "token_usage": {
                "input_tokens": 5000,
                "output_tokens": 2000,
                "cache_read_tokens": 1000,
                "cache_created_tokens": 500,
                "total_tokens": 8500,
            },
            "cost_estimate_usd": 0.15,
            "mcp_summary": {
                "total_calls": 10,
                "unique_tools": 3,
                "most_called": "mcp__zen__chat (5 calls)",
            },
            "server_sessions": {},
            "smells": [],
            "zombie_tools": {},
            "data_quality": {
                "accuracy_level": "exact",
                "token_source": "native",
                "confidence": 1.0,
            },
        }

        session_path = Path("/tmp/test-session.json")
        output = generate_ai_prompt_markdown(session_data, session_path)

        # Verify key sections exist
        assert "# MCP Session Analysis Request" in output
        assert "## Session Summary" in output
        assert "**Platform**: claude-code" in output
        assert "## Token Usage" in output
        assert "**Total Tokens**: 8,500" in output
        assert "## Cost" in output
        assert "$0.1500" in output
        assert "## MCP Tool Usage" in output
        # v0.8.0: Renamed to Context-Aware Analysis Questions (task-106.5)
        assert "## Context-Aware Analysis Questions" in output

    def test_generate_markdown_with_smells(self) -> None:
        """Test markdown generation includes smells."""
        from token_audit.cli import generate_ai_prompt_markdown

        session_data = {
            "session": {"platform": "claude-code"},
            "token_usage": {"total_tokens": 1000},
            "cost_estimate_usd": 0.01,
            "mcp_summary": {},
            "server_sessions": {},
            "smells": [
                {
                    "pattern": "CHATTY",
                    "severity": "warning",
                    "tool": "mcp__zen__chat",
                    "description": "Called 25 times",
                    "evidence": {"call_count": 25, "threshold": 20},
                }
            ],
            "zombie_tools": {},
        }

        session_path = Path("/tmp/test-session.json")
        output = generate_ai_prompt_markdown(session_data, session_path)

        assert "## Detected Efficiency Issues" in output
        assert "CHATTY" in output
        assert "Called 25 times" in output

    def test_generate_json_basic(self) -> None:
        """Test JSON generation with basic session data."""
        from token_audit.cli import generate_ai_prompt_json

        session_data = {
            "session": {
                "platform": "codex-cli",
                "model": "gpt-5.1-codex",
                "duration_seconds": 180,
                "project": "my-project",
            },
            "token_usage": {"total_tokens": 5000},
            "cost_estimate_usd": 0.05,
            "mcp_summary": {"total_calls": 5},
            "server_sessions": {},
            "smells": [],
            "zombie_tools": {},
            "data_quality": {"accuracy_level": "estimated"},
        }

        session_path = Path("/tmp/test-session.json")
        output = generate_ai_prompt_json(session_data, session_path)

        # Parse and verify
        parsed = json.loads(output)
        assert "analysis_request" in parsed
        assert "session_summary" in parsed
        assert parsed["session_summary"]["platform"] == "codex-cli"
        assert "token_usage" in parsed
        assert "smells" in parsed
        assert "top_tools" in parsed


class TestFormatDuration:
    """Tests for duration formatting."""

    def test_seconds(self) -> None:
        """Test formatting duration in seconds."""
        from token_audit.cli import _format_duration

        assert _format_duration(45) == "45s"

    def test_minutes(self) -> None:
        """Test formatting duration in minutes."""
        from token_audit.cli import _format_duration

        assert _format_duration(125) == "2m 5s"

    def test_hours(self) -> None:
        """Test formatting duration in hours."""
        from token_audit.cli import _format_duration

        assert _format_duration(3725) == "1h 2m"


class TestPinnedMCPFocusExport:
    """Tests for v0.8.0 Pinned MCP Focus export features (task-106.5)."""

    @pytest.fixture
    def session_data_with_servers(self) -> Dict[str, Any]:
        """Session data with MCP server usage."""
        return {
            "session": {
                "platform": "claude-code",
                "model": "claude-opus-4-5",
                "duration_seconds": 300,
                "project": "test-project",
            },
            "token_usage": {"total_tokens": 50000},
            "cost_estimate_usd": 0.50,
            "mcp_summary": {"total_calls": 20},
            "server_sessions": {
                "backlog": {
                    "tools": {
                        "task_create": {"calls": 5, "total_tokens": 10000},
                        "task_edit": {"calls": 3, "total_tokens": 6000},
                    }
                },
                "brave-search": {
                    "tools": {
                        "brave_web_search": {"calls": 8, "total_tokens": 24000},
                    }
                },
                "jina": {
                    "tools": {
                        "read_url": {"calls": 4, "total_tokens": 10000},
                    }
                },
            },
            "smells": [],
            "zombie_tools": {},
            "data_quality": {"accuracy_level": "exact"},
        }

    def test_markdown_with_pinned_focus(self, session_data_with_servers: Dict[str, Any]) -> None:
        """Test markdown generation with --pinned-focus flag."""
        from token_audit.cli import generate_ai_prompt_markdown

        output = generate_ai_prompt_markdown(
            session_data_with_servers,
            Path("/tmp/test.json"),
            pinned_focus=True,
            pinned_servers=["backlog"],
        )

        assert "## Pinned Server Focus: backlog" in output
        assert "### Usage Summary" in output
        assert "### Tool Breakdown" in output
        assert "task_create" in output
        assert "task_edit" in output

    def test_markdown_pinned_server_not_used(
        self, session_data_with_servers: Dict[str, Any]
    ) -> None:
        """Test markdown when pinned server wasn't used."""
        from token_audit.cli import generate_ai_prompt_markdown

        output = generate_ai_prompt_markdown(
            session_data_with_servers,
            Path("/tmp/test.json"),
            pinned_focus=True,
            pinned_servers=["unused-server"],
        )

        assert "## Pinned Server Focus: unused-server" in output
        assert "Pinned but not used" in output

    def test_markdown_with_full_mcp_breakdown(
        self, session_data_with_servers: Dict[str, Any]
    ) -> None:
        """Test markdown generation with --full-mcp-breakdown flag."""
        from token_audit.cli import generate_ai_prompt_markdown

        output = generate_ai_prompt_markdown(
            session_data_with_servers,
            Path("/tmp/test.json"),
            full_mcp_breakdown=True,
        )

        assert "## Full MCP Server Breakdown" in output
        assert "### Server: backlog" in output
        assert "### Server: brave-search" in output
        assert "### Server: jina" in output

    def test_markdown_full_breakdown_shows_pinned_badge(
        self, session_data_with_servers: Dict[str, Any]
    ) -> None:
        """Test that pinned servers are marked in full breakdown."""
        from token_audit.cli import generate_ai_prompt_markdown

        output = generate_ai_prompt_markdown(
            session_data_with_servers,
            Path("/tmp/test.json"),
            full_mcp_breakdown=True,
            pinned_servers=["backlog"],
        )

        assert "[PINNED]" in output

    def test_markdown_shows_pinned_servers_in_summary(
        self, session_data_with_servers: Dict[str, Any]
    ) -> None:
        """Test that pinned servers appear in session summary."""
        from token_audit.cli import generate_ai_prompt_markdown

        output = generate_ai_prompt_markdown(
            session_data_with_servers,
            Path("/tmp/test.json"),
            pinned_servers=["backlog", "jina"],
        )

        assert "**Pinned Servers**: backlog, jina" in output

    def test_json_with_pinned_servers(self, session_data_with_servers: Dict[str, Any]) -> None:
        """Test JSON export includes pinned servers."""
        from token_audit.cli import generate_ai_prompt_json

        output = generate_ai_prompt_json(
            session_data_with_servers,
            Path("/tmp/test.json"),
            pinned_servers=["backlog"],
        )

        parsed = json.loads(output)
        assert "pinned_servers" in parsed
        assert parsed["pinned_servers"] == ["backlog"]

    def test_json_with_pinned_focus(self, session_data_with_servers: Dict[str, Any]) -> None:
        """Test JSON export includes pinned server analysis."""
        from token_audit.cli import generate_ai_prompt_json

        output = generate_ai_prompt_json(
            session_data_with_servers,
            Path("/tmp/test.json"),
            pinned_focus=True,
            pinned_servers=["backlog"],
        )

        parsed = json.loads(output)
        assert "pinned_server_analysis" in parsed
        assert "backlog" in parsed["pinned_server_analysis"]
        assert parsed["pinned_server_analysis"]["backlog"]["is_pinned"] is True

    def test_json_with_full_breakdown(self, session_data_with_servers: Dict[str, Any]) -> None:
        """Test JSON export includes full server breakdown."""
        from token_audit.cli import generate_ai_prompt_json

        output = generate_ai_prompt_json(
            session_data_with_servers,
            Path("/tmp/test.json"),
            full_mcp_breakdown=True,
            pinned_servers=["backlog"],
        )

        parsed = json.loads(output)
        assert "full_server_breakdown" in parsed
        assert "backlog" in parsed["full_server_breakdown"]
        assert "brave-search" in parsed["full_server_breakdown"]
        assert parsed["full_server_breakdown"]["backlog"]["is_pinned"] is True
        assert parsed["full_server_breakdown"]["brave-search"]["is_pinned"] is False

    def test_json_includes_context_questions(
        self, session_data_with_servers: Dict[str, Any]
    ) -> None:
        """Test JSON export includes context-aware questions."""
        from token_audit.cli import generate_ai_prompt_json

        output = generate_ai_prompt_json(
            session_data_with_servers,
            Path("/tmp/test.json"),
        )

        parsed = json.loads(output)
        assert "context_questions" in parsed
        assert isinstance(parsed["context_questions"], list)


class TestRecommendationsExport:
    """Tests for v0.8.0 Recommendations in export (task-106.2)."""

    def test_markdown_includes_recommendations_section(self) -> None:
        """Test that smells generate recommendations in markdown."""
        from token_audit.cli import generate_ai_prompt_markdown

        session_data = {
            "session": {"platform": "claude-code", "duration_seconds": 300},
            "token_usage": {"total_tokens": 50000},
            "cost_estimate_usd": 0.50,
            "mcp_summary": {},
            "server_sessions": {},
            "smells": [
                {
                    "pattern": "CHATTY",
                    "severity": "warning",
                    "tool": "mcp__backlog__task_edit",
                    "description": "Called 35 times",
                    "evidence": {
                        "call_count": 35,
                        "threshold": 20,
                        "total_tokens": 17500,
                        "avg_tokens_per_call": 500,
                    },
                }
            ],
            "zombie_tools": {},
            "data_quality": {},
        }

        output = generate_ai_prompt_markdown(session_data, Path("/tmp/test.json"))

        assert "## AI Recommendations" in output
        assert "BATCH_OPERATIONS" in output
        assert "**Confidence**:" in output
        assert "**Evidence**:" in output
        assert "**Action**:" in output
        assert "**Impact**:" in output

    def test_json_includes_recommendations(self) -> None:
        """Test that smells generate recommendations in JSON."""
        from token_audit.cli import generate_ai_prompt_json

        session_data = {
            "session": {"platform": "claude-code"},
            "token_usage": {"total_tokens": 50000},
            "cost_estimate_usd": 0.50,
            "mcp_summary": {},
            "server_sessions": {},
            "smells": [
                {
                    "pattern": "UNDERUTILIZED_SERVER",
                    "severity": "info",
                    "evidence": {
                        "server": "unused-server",
                        "utilization_percent": 0,
                        "available_tools": 10,
                        "used_tools": 0,
                    },
                }
            ],
            "zombie_tools": {},
            "data_quality": {},
        }

        output = generate_ai_prompt_json(session_data, Path("/tmp/test.json"))

        parsed = json.loads(output)
        assert "recommendations" in parsed
        assert len(parsed["recommendations"]) > 0
        assert parsed["recommendations"][0]["type"] == "REMOVE_UNUSED_SERVER"


class TestContextAwareQuestions:
    """Tests for v0.8.0 Context-Aware Questions (task-106.5)."""

    def test_top_consumer_question(self) -> None:
        """Test question generated for dominant tool."""
        from token_audit.cli import generate_ai_prompt_markdown

        session_data = {
            "session": {"platform": "claude-code", "duration_seconds": 300},
            "token_usage": {"total_tokens": 100000},
            "cost_estimate_usd": 1.00,
            "mcp_summary": {},
            "server_sessions": {
                "jina": {
                    "tools": {
                        "read_url": {"calls": 10, "total_tokens": 80000},  # 80% of tokens
                    }
                },
                "backlog": {
                    "tools": {
                        "task_view": {"calls": 5, "total_tokens": 20000},
                    }
                },
            },
            "smells": [],
            "zombie_tools": {},
            "data_quality": {},
        }

        output = generate_ai_prompt_markdown(session_data, Path("/tmp/test.json"))

        # Should ask about dominant tool
        assert "read_url" in output
        assert "80%" in output

    def test_unused_pinned_server_question(self) -> None:
        """Test question when pinned server not used."""
        from token_audit.cli import generate_ai_prompt_markdown

        session_data = {
            "session": {"platform": "claude-code", "duration_seconds": 300},
            "token_usage": {"total_tokens": 10000},
            "cost_estimate_usd": 0.10,
            "mcp_summary": {},
            "server_sessions": {
                "backlog": {"tools": {"task_view": {"calls": 5, "total_tokens": 10000}}}
            },
            "smells": [],
            "zombie_tools": {},
            "data_quality": {},
        }

        output = generate_ai_prompt_markdown(
            session_data,
            Path("/tmp/test.json"),
            pinned_servers=["brave-search"],  # Not in server_sessions
        )

        assert "brave-search" in output
        assert "unpinned" in output.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
