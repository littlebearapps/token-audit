"""
Config file parsers with normalization.

Parses JSON and TOML configuration files and normalizes them
to a common MCP server configuration structure.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


@dataclass
class ServerConfig:
    """Normalized MCP server configuration."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    disabled: bool = False
    # Additional metadata
    raw_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "disabled": self.disabled,
        }


@dataclass
class MCPConfig:
    """Normalized MCP configuration."""

    platform: str
    path: Path
    servers: Dict[str, ServerConfig] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    parse_error: Optional[str] = None

    @property
    def server_count(self) -> int:
        """Number of configured servers."""
        return len(self.servers)

    @property
    def enabled_server_count(self) -> int:
        """Number of enabled (not disabled) servers."""
        return sum(1 for s in self.servers.values() if not s.disabled)


def parse_json_config(path: Path, platform: str) -> MCPConfig:
    """Parse JSON config file (Claude Code, Gemini CLI).

    Args:
        path: Path to JSON config file
        platform: Platform identifier

    Returns:
        MCPConfig with parsed servers
    """
    config = MCPConfig(platform=platform, path=path)

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        config.raw_data = data
    except json.JSONDecodeError as e:
        config.parse_error = f"JSON parse error: {e}"
        return config
    except FileNotFoundError:
        config.parse_error = f"File not found: {path}"
        return config
    except Exception as e:
        config.parse_error = f"Error reading file: {e}"
        return config

    # Normalize to common structure
    config.servers = _normalize_json_servers(data, platform)
    return config


def parse_toml_config(path: Path, platform: str) -> MCPConfig:
    """Parse TOML config file (Codex CLI).

    Args:
        path: Path to TOML config file
        platform: Platform identifier

    Returns:
        MCPConfig with parsed servers
    """
    config = MCPConfig(platform=platform, path=path)

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        config.raw_data = data
    except Exception as e:
        config.parse_error = f"TOML parse error: {e}"
        return config

    # Normalize to common structure
    config.servers = _normalize_toml_servers(data)
    return config


def _normalize_json_servers(data: Dict[str, Any], platform: str) -> Dict[str, ServerConfig]:
    """Normalize JSON config to ServerConfig dict.

    Handles different JSON structures used by Claude Code and Gemini CLI.

    Args:
        data: Parsed JSON data
        platform: Platform for format detection

    Returns:
        Dict mapping server names to ServerConfig
    """
    servers: Dict[str, ServerConfig] = {}

    # Claude Code uses "mcpServers" key
    # Settings.json may have nested structure
    mcp_servers = data.get("mcpServers", {})

    # Handle Claude Code settings.json structure
    if not mcp_servers and "projects" in data:
        # Global settings may have projects with their own mcpServers
        pass  # Skip project-specific for now

    for name, server_data in mcp_servers.items():
        if not isinstance(server_data, dict):
            continue

        servers[name] = ServerConfig(
            name=name,
            command=server_data.get("command", ""),
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
            disabled=server_data.get("disabled", False),
            raw_config=server_data,
        )

    return servers


def _normalize_toml_servers(data: Dict[str, Any]) -> Dict[str, ServerConfig]:
    """Normalize TOML config to ServerConfig dict.

    Handles Codex CLI TOML structure.

    Args:
        data: Parsed TOML data

    Returns:
        Dict mapping server names to ServerConfig
    """
    servers: Dict[str, ServerConfig] = {}

    # Codex uses [mcp_servers.name] sections
    mcp_servers = data.get("mcp_servers", {})

    for name, server_data in mcp_servers.items():
        if not isinstance(server_data, dict):
            continue

        # Codex uses slightly different keys
        command = server_data.get("command") or server_data.get("cmd") or ""
        args = server_data.get("args") or server_data.get("arguments") or []
        env = server_data.get("env") or server_data.get("environment") or {}
        servers[name] = ServerConfig(
            name=name,
            command=command,
            args=args,
            env=env,
            disabled=server_data.get("disabled", server_data.get("enabled") is False),
            raw_config=server_data,
        )

    return servers


def parse_config(path: Path, platform: str) -> MCPConfig:
    """Parse config file based on extension.

    Args:
        path: Path to config file
        platform: Platform identifier

    Returns:
        Parsed MCPConfig
    """
    suffix = path.suffix.lower()

    if suffix == ".toml":
        return parse_toml_config(path, platform)
    elif suffix == ".json":
        return parse_json_config(path, platform)
    else:
        return MCPConfig(
            platform=platform,
            path=path,
            parse_error=f"Unsupported config format: {suffix}",
        )
