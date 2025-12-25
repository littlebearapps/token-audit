#!/usr/bin/env python3
"""
Test suite for normalization module

Tests cross-platform MCP tool name normalization.
"""

import pytest
from token_audit.normalization import (
    normalize_server_name,
    normalize_tool_name,
    extract_server_and_tool,
    is_mcp_tool,
    is_builtin_tool,
    normalize_claude_code_tool,
    normalize_codex_cli_tool,
    normalize_gemini_cli_tool,
)


class TestServerNameNormalization:
    """Tests for normalize_server_name function"""

    def test_claude_code_format(self) -> None:
        """Test Claude Code format: mcp__zen__chat"""
        assert normalize_server_name("mcp__zen__chat") == "zen"
        assert normalize_server_name("mcp__brave-search__web") == "brave-search"

    def test_codex_cli_format(self) -> None:
        """Test Codex CLI format with -mcp suffix: mcp__zen-mcp__chat"""
        assert normalize_server_name("mcp__zen-mcp__chat") == "zen"
        assert normalize_server_name("mcp__brave-search-mcp__web") == "brave-search"

    def test_gemini_cli_format(self) -> None:
        """Test Gemini CLI format (same as Claude Code)"""
        assert normalize_server_name("mcp__zen__chat") == "zen"
        assert normalize_server_name("mcp__brave-search__web_search") == "brave-search"

    def test_invalid_format_warning(self) -> None:
        """Test that invalid format generates warning"""
        with pytest.warns(UserWarning):
            result = normalize_server_name("Read")
        assert result == "unknown"

    def test_empty_string(self) -> None:
        """Test empty string handling"""
        with pytest.warns(UserWarning):
            result = normalize_server_name("")
        assert result == "unknown"


class TestToolNameNormalization:
    """Tests for normalize_tool_name function"""

    def test_claude_code_passthrough(self) -> None:
        """Test Claude Code format passes through unchanged"""
        assert normalize_tool_name("mcp__zen__chat") == "mcp__zen__chat"
        assert normalize_tool_name("mcp__brave-search__web") == "mcp__brave-search__web"

    def test_codex_cli_normalization(self) -> None:
        """Test Codex CLI format gets normalized"""
        assert normalize_tool_name("mcp__zen-mcp__chat") == "mcp__zen__chat"
        assert normalize_tool_name("mcp__brave-search-mcp__web") == "mcp__brave-search__web"

    def test_gemini_cli_passthrough(self) -> None:
        """Test Gemini CLI format passes through unchanged"""
        assert normalize_tool_name("mcp__zen__chat") == "mcp__zen__chat"

    def test_complex_tool_names(self) -> None:
        """Test complex tool names with multiple underscores"""
        assert normalize_tool_name("mcp__zen-mcp__think_deep") == "mcp__zen__think_deep"
        assert (
            normalize_tool_name("mcp__brave-search__brave_web_search")
            == "mcp__brave-search__brave_web_search"
        )


class TestExtractServerAndTool:
    """Tests for extract_server_and_tool function"""

    def test_claude_code_extraction(self) -> None:
        """Test extracting from Claude Code format"""
        server, tool = extract_server_and_tool("mcp__zen__chat")
        assert server == "zen"
        assert tool == "mcp__zen__chat"

    def test_codex_cli_extraction(self) -> None:
        """Test extracting from Codex CLI format"""
        server, tool = extract_server_and_tool("mcp__zen-mcp__chat")
        assert server == "zen"
        assert tool == "mcp__zen__chat"

    def test_complex_extraction(self) -> None:
        """Test extracting from complex names"""
        server, tool = extract_server_and_tool("mcp__brave-search-mcp__brave_web_search")
        assert server == "brave-search"
        assert tool == "mcp__brave-search__brave_web_search"


class TestToolTypeDetection:
    """Tests for MCP vs built-in tool detection"""

    def test_is_mcp_tool(self) -> None:
        """Test MCP tool detection"""
        assert is_mcp_tool("mcp__zen__chat") == True
        assert is_mcp_tool("mcp__brave-search__web") == True
        assert is_mcp_tool("Read") == False
        assert is_mcp_tool("execute_zsh") == False

    def test_is_builtin_tool(self) -> None:
        """Test built-in tool detection"""
        assert is_builtin_tool("Read") == True
        assert is_builtin_tool("Write") == True
        assert is_builtin_tool("Bash") == True
        assert is_builtin_tool("mcp__zen__chat") == False

    def test_edge_cases(self) -> None:
        """Test edge cases"""
        assert is_mcp_tool("") == False
        assert is_builtin_tool("") == True


class TestPlatformSpecificUtilities:
    """Tests for platform-specific normalization utilities"""

    def test_claude_code_tool_normalization(self) -> None:
        """Test Claude Code specific normalization"""
        assert normalize_claude_code_tool("mcp__zen__chat") == "mcp__zen__chat"

    def test_codex_cli_tool_normalization(self) -> None:
        """Test Codex CLI specific normalization"""
        assert normalize_codex_cli_tool("mcp__zen-mcp__chat") == "mcp__zen__chat"
        assert normalize_codex_cli_tool("mcp__zen__chat") == "mcp__zen__chat"

    def test_gemini_cli_tool_normalization(self) -> None:
        """Test Gemini CLI specific normalization"""
        assert normalize_gemini_cli_tool("mcp__zen__chat") == "mcp__zen__chat"


class TestCrossPlatformCompatibility:
    """Tests for cross-platform compatibility"""

    def test_unified_output(self) -> None:
        """Test that all platforms produce unified output"""
        # Same tool name from different platforms
        claude_tool = "mcp__zen__chat"
        codex_tool = "mcp__zen-mcp__chat"
        gemini_tool = "mcp__zen__chat"

        # All should normalize to same result
        assert normalize_tool_name(claude_tool) == "mcp__zen__chat"
        assert normalize_tool_name(codex_tool) == "mcp__zen__chat"
        assert normalize_tool_name(gemini_tool) == "mcp__zen__chat"

    def test_server_extraction_consistency(self) -> None:
        """Test server extraction is consistent across platforms"""
        tools = ["mcp__zen__chat", "mcp__zen-mcp__chat", "mcp__zen__debug", "mcp__zen-mcp__debug"]

        servers = [normalize_server_name(tool) for tool in tools]
        assert all(server == "zen" for server in servers)


# ============================================================================
# Parametrized Tests
# ============================================================================


@pytest.mark.parametrize(
    "tool_name,expected_server",
    [
        ("mcp__zen__chat", "zen"),
        ("mcp__zen-mcp__chat", "zen"),
        ("mcp__brave-search__web", "brave-search"),
        ("mcp__brave-search-mcp__web", "brave-search"),
        ("mcp__context7__search", "context7"),
        ("mcp__mult-fetch__fetch", "mult-fetch"),
    ],
)
def test_server_extraction_parametrized(tool_name, expected_server) -> None:
    """Parametrized test for server extraction"""
    assert normalize_server_name(tool_name) == expected_server


@pytest.mark.parametrize(
    "codex_tool,expected_normalized",
    [
        ("mcp__zen-mcp__chat", "mcp__zen__chat"),
        ("mcp__brave-search-mcp__web", "mcp__brave-search__web"),
        ("mcp__zen__chat", "mcp__zen__chat"),  # Already normalized
    ],
)
def test_codex_normalization_parametrized(codex_tool, expected_normalized) -> None:
    """Parametrized test for Codex normalization"""
    assert normalize_tool_name(codex_tool) == expected_normalized


# ============================================================================
# Integration Tests
# ============================================================================


class TestNormalizationIntegration:
    """Integration tests for complete normalization workflow"""

    def test_complete_workflow(self) -> None:
        """Test complete normalization workflow"""
        # Simulate receiving tool names from different platforms
        tools_from_platforms = {
            "claude_code": ["mcp__zen__chat", "mcp__brave-search__web"],
            "codex_cli": ["mcp__zen-mcp__chat", "mcp__brave-search-mcp__web"],
            "gemini_cli": ["mcp__zen__chat", "mcp__brave-search__web"],
        }

        # Normalize all tools
        normalized_tools = set()
        for platform, tools in tools_from_platforms.items():
            for tool in tools:
                normalized_tools.add(normalize_tool_name(tool))

        # Should have only 2 unique normalized tools
        assert len(normalized_tools) == 2
        assert "mcp__zen__chat" in normalized_tools
        assert "mcp__brave-search__web" in normalized_tools

    def test_session_aggregation(self) -> None:
        """Test that tools from different platforms aggregate correctly"""
        # Simulate tool calls from different platforms
        calls = [
            ("claude_code", "mcp__zen__chat"),
            ("codex_cli", "mcp__zen-mcp__chat"),
            ("claude_code", "mcp__zen__debug"),
            ("codex_cli", "mcp__zen-mcp__debug"),
        ]

        # Group by normalized tool name
        tool_counts = {}
        for platform, tool in calls:
            normalized = normalize_tool_name(tool)
            tool_counts[normalized] = tool_counts.get(normalized, 0) + 1

        # Should have 2 tools with 2 calls each
        assert len(tool_counts) == 2
        assert tool_counts["mcp__zen__chat"] == 2
        assert tool_counts["mcp__zen__debug"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
