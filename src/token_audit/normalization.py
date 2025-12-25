#!/usr/bin/env python3
"""
Normalization Module - Cross-platform MCP tool name normalization

Provides utilities for normalizing MCP tool and server names across different
AI CLI platforms (Claude Code, Codex CLI, Gemini CLI, Ollama CLI).
"""

import warnings
from typing import Tuple


def normalize_server_name(tool_name: str) -> str:
    """
    Extract and normalize server name from MCP tool name.

    Handles platform-specific formats:
    - Claude Code: "mcp__zen__chat" → "zen"
    - Codex CLI: "mcp__zen-mcp__chat" → "zen"
    - Gemini CLI: "mcp__brave-search__web" → "brave-search"

    Args:
        tool_name: Full MCP tool name

    Returns:
        Normalized server name (without platform-specific suffixes)

    Examples:
        >>> normalize_server_name("mcp__zen__chat")
        'zen'
        >>> normalize_server_name("mcp__zen-mcp__chat")
        'zen'
        >>> normalize_server_name("mcp__brave-search__web_search")
        'brave-search'
    """
    if not tool_name.startswith("mcp__"):
        warnings.warn(f"Tool name doesn't start with 'mcp__': {tool_name}", stacklevel=2)
        return "unknown"

    # Remove mcp__ prefix
    name_parts = tool_name[5:].split("__")

    # Handle Codex CLI format: mcp__zen-mcp__chat
    server_name = name_parts[0]
    if server_name.endswith("-mcp"):
        server_name = server_name[:-4]  # Remove -mcp suffix

    return server_name


def normalize_tool_name(tool_name: str) -> str:
    """
    Normalize MCP tool name to consistent format (Claude Code style).

    Converts platform-specific formats to a unified format:
    - Codex CLI: "mcp__zen-mcp__chat" → "mcp__zen__chat"
    - Claude Code: "mcp__zen__chat" → "mcp__zen__chat" (unchanged)
    - Gemini CLI: "mcp__brave-search__web" → "mcp__brave-search__web" (unchanged)

    Args:
        tool_name: Raw tool name from platform

    Returns:
        Normalized tool name (Claude Code format)

    Examples:
        >>> normalize_tool_name("mcp__zen-mcp__chat")
        'mcp__zen__chat'
        >>> normalize_tool_name("mcp__zen__chat")
        'mcp__zen__chat'
        >>> normalize_tool_name("mcp__brave-search__web_search")
        'mcp__brave-search__web_search'
    """
    # Handle Codex CLI format with -mcp suffix
    if "-mcp__" in tool_name:
        parts = tool_name.split("__")
        if len(parts) >= 2 and parts[0] == "mcp":
            server_name = parts[1].replace("-mcp", "")
            tool_suffix = "__".join(parts[2:])
            return f"mcp__{server_name}__{tool_suffix}"

    return tool_name


def extract_server_and_tool(tool_name: str) -> Tuple[str, str]:
    """
    Extract both server name and tool name in one call.

    Args:
        tool_name: Full MCP tool name

    Returns:
        Tuple of (normalized_server_name, normalized_tool_name)

    Examples:
        >>> extract_server_and_tool("mcp__zen-mcp__chat")
        ('zen', 'mcp__zen__chat')
        >>> extract_server_and_tool("mcp__brave-search__web_search")
        ('brave-search', 'mcp__brave-search__web_search')
    """
    normalized_tool = normalize_tool_name(tool_name)
    server_name = normalize_server_name(normalized_tool)
    return (server_name, normalized_tool)


def is_mcp_tool(tool_name: str) -> bool:
    """
    Check if a tool name is an MCP tool.

    Args:
        tool_name: Tool name to check

    Returns:
        True if MCP tool, False if built-in tool

    Examples:
        >>> is_mcp_tool("mcp__zen__chat")
        True
        >>> is_mcp_tool("Read")
        False
        >>> is_mcp_tool("execute_zsh")
        False
    """
    return tool_name.startswith("mcp__")


def is_builtin_tool(tool_name: str) -> bool:
    """
    Check if a tool name is a built-in (non-MCP) tool.

    Args:
        tool_name: Tool name to check

    Returns:
        True if built-in tool, False if MCP tool

    Examples:
        >>> is_builtin_tool("Read")
        True
        >>> is_builtin_tool("mcp__zen__chat")
        False
    """
    return not is_mcp_tool(tool_name)


# ============================================================================
# Platform-Specific Utilities
# ============================================================================


def normalize_claude_code_tool(tool_name: str) -> str:
    """
    Normalize Claude Code tool name (pass-through, already in correct format).

    Args:
        tool_name: Claude Code tool name

    Returns:
        Unchanged tool name

    Examples:
        >>> normalize_claude_code_tool("mcp__zen__chat")
        'mcp__zen__chat'
    """
    return tool_name


def normalize_codex_cli_tool(tool_name: str) -> str:
    """
    Normalize Codex CLI tool name (strip -mcp suffix).

    Args:
        tool_name: Codex CLI tool name

    Returns:
        Normalized tool name

    Examples:
        >>> normalize_codex_cli_tool("mcp__zen-mcp__chat")
        'mcp__zen__chat'
    """
    return normalize_tool_name(tool_name)


def normalize_gemini_cli_tool(tool_name: str) -> str:
    """
    Normalize Gemini CLI tool name (pass-through, same as Claude Code).

    Args:
        tool_name: Gemini CLI tool name

    Returns:
        Unchanged tool name

    Examples:
        >>> normalize_gemini_cli_tool("mcp__brave-search__web")
        'mcp__brave-search__web'
    """
    return tool_name


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    import doctest

    doctest.testmod()

    # Manual tests
    print("Normalization Module Tests")
    print("=" * 60)

    test_cases = [
        "mcp__zen__chat",
        "mcp__zen-mcp__chat",
        "mcp__brave-search__brave_web_search",
        "mcp__brave-search-mcp__brave_web_search",
        "Read",
        "execute_zsh",
    ]

    for tool_name in test_cases:
        server_name = normalize_server_name(tool_name) if is_mcp_tool(tool_name) else "N/A"
        normalized = normalize_tool_name(tool_name) if is_mcp_tool(tool_name) else tool_name
        is_mcp = "MCP" if is_mcp_tool(tool_name) else "Built-in"

        print(f"\nOriginal:    {tool_name}")
        print(f"Server:      {server_name}")
        print(f"Normalized:  {normalized}")
        print(f"Type:        {is_mcp}")
