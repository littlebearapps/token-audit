"""
Zombie Tool Detector - Identifies MCP tools defined but never called.

A "zombie tool" is an MCP tool that:
- Appears in the server's tool schema
- Was never called during the session
- Contributes to context overhead without providing value

This module provides detection based on:
1. User-configured known tools in token-audit.toml
2. Tools discovered from previous sessions (future enhancement)

v1.5.0 - task-103.4
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

from .base_tracker import Session


@dataclass
class ZombieToolConfig:
    """Configuration for zombie tool detection per server."""

    # Map of server name -> set of known tool names
    known_tools: Dict[str, Set[str]] = field(default_factory=dict)


def load_zombie_config(config_path: Optional[Path] = None) -> ZombieToolConfig:
    """Load zombie tool configuration from token-audit.toml.

    Args:
        config_path: Path to config file (default: token-audit.toml in cwd)

    Returns:
        ZombieToolConfig with known tools per server

    Configuration format in token-audit.toml:
    ```toml
    [zombie_tools.zen]
    tools = [
        "mcp__zen__thinkdeep",
        "mcp__zen__debug",
        "mcp__zen__refactor",
        ...
    ]

    [zombie_tools.backlog]
    tools = [
        "mcp__backlog__task_create",
        "mcp__backlog__task_list",
        ...
    ]
    ```
    """
    config = ZombieToolConfig()

    if config_path is None:
        config_path = Path.cwd() / "token-audit.toml"

    if not config_path.exists():
        return config

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        zombie_section = data.get("zombie_tools", {})
        for server_name, server_config in zombie_section.items():
            if isinstance(server_config, dict):
                tools = server_config.get("tools", [])
                if isinstance(tools, list):
                    config.known_tools[server_name] = set(tools)
    except Exception:
        # If config is malformed, return empty config
        pass

    return config


def detect_zombie_tools(
    session: Session,
    config: Optional[ZombieToolConfig] = None,
) -> Dict[str, List[str]]:
    """Detect zombie tools in a session.

    Compares configured known tools against actually called tools.
    Only reports zombies for servers that:
    1. Have known tools configured
    2. Had at least one tool called (indicating the server was active)

    Args:
        session: Finalized session with server_sessions populated
        config: Zombie tool configuration (loads from file if not provided)

    Returns:
        Dict mapping server name to list of zombie tool names
    """
    if config is None:
        config = load_zombie_config()

    zombie_tools: Dict[str, List[str]] = {}

    for server_name, server_session in session.server_sessions.items():
        # Skip builtin pseudo-server
        if server_name == "builtin":
            continue

        # Get known tools for this server
        known = config.known_tools.get(server_name, set())
        if not known:
            # No known tools configured for this server - skip
            continue

        # Get actually called tools
        called_tools = set(server_session.tools.keys())

        # Find zombies: known but not called
        zombies = known - called_tools

        if zombies:
            # Sort for consistent output
            zombie_tools[server_name] = sorted(zombies)

    return zombie_tools


def detect_zombie_tools_auto(session: Session) -> Dict[str, List[str]]:  # noqa: ARG001
    """Detect zombie tools using automatic discovery (future enhancement).

    This function is a placeholder for automatic zombie detection that doesn't
    require pre-configuration. Future implementations could:
    - Track list_tools responses during session
    - Compare against historical session data
    - Use MCP server metadata if available

    For now, returns empty dict - use detect_zombie_tools() with config.

    Args:
        session: Finalized session

    Returns:
        Empty dict (automatic detection not yet implemented)
    """
    # Future: implement automatic detection
    # For now, require explicit configuration
    return {}
