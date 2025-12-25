#!/usr/bin/env python3
"""MCP Schema Analyzer for context tax calculation (v0.6.0 - task-114.1)

Analyzes MCP server schemas to calculate the "context tax" - the token
overhead incurred by including tool definitions in every LLM request.

Token estimates are based on empirical analysis documented in:
docs/platforms/schema-capture-research.md
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from token_audit.base_tracker import StaticCost

logger = logging.getLogger(__name__)


@dataclass
class ServerSchema:
    """Per-server schema data for context tax calculation.

    Attributes:
        server: Server name/identifier
        tool_count: Number of tools exposed by server
        estimated_tokens: Estimated token count for schema
        source: How the estimate was obtained ("known_db", "estimate", "config")
    """

    server: str
    tool_count: int
    estimated_tokens: int
    source: str  # "known_db", "estimate", "config"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "server": self.server,
            "tool_count": self.tool_count,
            "estimated_tokens": self.estimated_tokens,
            "source": self.source,
        }


class SchemaAnalyzer:
    """Analyzes MCP server schemas for context tax calculation.

    Uses a database of known servers with empirically measured token counts,
    falling back to estimation for unknown servers.

    Token estimates based on research (docs/platforms/schema-capture-research.md):
    - Average: ~100-250 tokens per tool depending on schema complexity
    - Conservative default: 175 tokens per tool
    """

    # Known server token counts (from empirical analysis)
    # Format: "server_name": {"tools": count, "tokens": total_tokens}
    KNOWN_SERVERS: Dict[str, Dict[str, int]] = {
        # Common MCP servers with measured token counts
        "backlog": {"tools": 15, "tokens": 2250},
        "brave-search": {"tools": 6, "tokens": 1200},
        "jina": {"tools": 20, "tokens": 3600},
        "zen": {"tools": 12, "tokens": 3000},
        "context7": {"tools": 5, "tokens": 750},
        "mult-fetch": {"tools": 3, "tokens": 450},
        "filesystem": {"tools": 5, "tokens": 600},
        "git": {"tools": 8, "tokens": 1200},
        "linear-server": {"tools": 10, "tokens": 1500},
        "cloudflare": {"tools": 6, "tokens": 900},
        # Aliases for common naming patterns
        "@brave/brave-search-mcp-server": {"tools": 6, "tokens": 1200},
        "@modelcontextprotocol/server-filesystem": {"tools": 5, "tokens": 600},
        "zen-mcp-server": {"tools": 12, "tokens": 3000},
        "mcp-keychain": {"tools": 4, "tokens": 600},
    }

    # Default tokens per tool when server is unknown
    TOKENS_PER_TOOL_ESTIMATE: int = 175

    # Default tools per server when tool count unknown
    DEFAULT_TOOLS_PER_SERVER: int = 10

    def __init__(
        self,
        tokens_per_tool: int = TOKENS_PER_TOOL_ESTIMATE,
        known_servers: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> None:
        """Initialize the schema analyzer.

        Args:
            tokens_per_tool: Override default tokens per tool estimate
            known_servers: Override/extend the known servers database
        """
        self.tokens_per_tool = tokens_per_tool
        self.known_servers = dict(self.KNOWN_SERVERS)
        if known_servers:
            self.known_servers.update(known_servers)

    def analyze_from_config(self, mcp_config: Dict[str, Any]) -> List[ServerSchema]:
        """Analyze servers from MCP configuration.

        Supports Claude Code (.mcp.json) format:
        {
            "mcpServers": {
                "server-name": {"command": "...", "args": [...]}
            }
        }

        Args:
            mcp_config: Parsed MCP configuration dict

        Returns:
            List of ServerSchema objects with token estimates
        """
        servers: List[ServerSchema] = []

        # Handle Claude Code / Gemini CLI format
        mcp_servers = mcp_config.get("mcpServers", {})
        if not mcp_servers:
            # Try Codex CLI format (flat dict of server configs)
            mcp_servers = mcp_config

        for server_name, server_config in mcp_servers.items():
            # Skip non-dict entries (might be metadata)
            if not isinstance(server_config, dict):
                continue

            # Check if server is in known database
            schema = self._get_server_schema(server_name, server_config)
            servers.append(schema)

        return servers

    def analyze_from_file(self, config_path: Path) -> List[ServerSchema]:
        """Analyze servers from an MCP configuration file.

        Supports both JSON (.mcp.json, settings.json) and TOML (config.toml) formats.

        Args:
            config_path: Path to MCP config file (.mcp.json, settings.json, config.toml)

        Returns:
            List of ServerSchema objects with token estimates

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If JSON config file is invalid
            ValueError: If TOML parsing fails and tomllib not available
        """
        if not config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {config_path}")

        suffix = config_path.suffix.lower()

        if suffix == ".toml":
            # Parse TOML format (Codex CLI)
            mcp_config = self._parse_toml_config(config_path)
        else:
            # Parse JSON format (Claude Code, Gemini CLI)
            with open(config_path) as f:
                mcp_config = json.load(f)

        return self.analyze_from_config(mcp_config)

    def _parse_toml_config(self, config_path: Path) -> Dict[str, Any]:
        """Parse TOML config file (Codex CLI format).

        Codex CLI config format:
        [mcp_servers.server-name]
        command = "..."
        args = [...]

        Args:
            config_path: Path to config.toml file

        Returns:
            Dict with mcpServers key for compatibility
        """
        try:
            import tomllib
        except ImportError:
            # Python < 3.11, try tomli as fallback
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                raise ValueError(
                    "TOML support requires Python 3.11+ or 'tomli' package. "
                    "Install with: pip install tomli"
                ) from None

        with open(config_path, "rb") as f:
            toml_config = tomllib.load(f)

        # Convert Codex CLI format to standard format
        # [mcp_servers.name] -> {"mcpServers": {"name": {...}}}
        mcp_servers = toml_config.get("mcp_servers", {})

        return {"mcpServers": mcp_servers}

    def _get_server_schema(self, server_name: str, server_config: Dict[str, Any]) -> ServerSchema:
        """Get schema info for a single server.

        Checks known database first, then falls back to estimation.

        Args:
            server_name: Name of the MCP server
            server_config: Server configuration dict

        Returns:
            ServerSchema with token estimates
        """
        # Check for exact match in known servers
        if server_name in self.known_servers:
            known = self.known_servers[server_name]
            return ServerSchema(
                server=server_name,
                tool_count=known["tools"],
                estimated_tokens=known["tokens"],
                source="known_db",
            )

        # Check for partial matches (e.g., "zen" in "mcp__zen__*")
        for known_name, known_data in self.known_servers.items():
            if known_name in server_name or server_name in known_name:
                return ServerSchema(
                    server=server_name,
                    tool_count=known_data["tools"],
                    estimated_tokens=known_data["tokens"],
                    source="known_db",
                )

        # Check command for known package patterns
        command = server_config.get("command", "")
        args = server_config.get("args", [])
        full_command = f"{command} {' '.join(str(a) for a in args)}"

        for known_name, known_data in self.known_servers.items():
            if known_name in full_command:
                return ServerSchema(
                    server=server_name,
                    tool_count=known_data["tools"],
                    estimated_tokens=known_data["tokens"],
                    source="known_db",
                )

        # Fall back to estimation
        estimated_tools = self.DEFAULT_TOOLS_PER_SERVER
        estimated_tokens = estimated_tools * self.tokens_per_tool

        logger.debug(
            f"Unknown server '{server_name}', estimating {estimated_tools} tools, "
            f"{estimated_tokens} tokens"
        )

        return ServerSchema(
            server=server_name,
            tool_count=estimated_tools,
            estimated_tokens=estimated_tokens,
            source="estimate",
        )

    def calculate_static_cost(self, servers: List[ServerSchema]) -> StaticCost:
        """Calculate total static cost from server schemas.

        Args:
            servers: List of ServerSchema objects from analyze_*

        Returns:
            StaticCost with aggregated token counts and metadata
        """
        if not servers:
            return StaticCost(
                total_tokens=0,
                source="estimate",
                by_server={},
                confidence=0.0,
            )

        total_tokens = 0
        by_server: Dict[str, int] = {}
        known_count = 0
        estimated_count = 0

        for server in servers:
            total_tokens += server.estimated_tokens
            by_server[server.server] = server.estimated_tokens

            if server.source == "known_db":
                known_count += 1
            else:
                estimated_count += 1

        # Calculate confidence based on ratio of known vs estimated
        total_servers = known_count + estimated_count
        if total_servers > 0:
            # Known servers: 0.9 confidence each
            # Estimated servers: 0.7 confidence each
            confidence = (known_count * 0.9 + estimated_count * 0.7) / total_servers
        else:
            confidence = 0.0

        # Determine source label
        if estimated_count == 0:
            source = "known_db"
        elif known_count == 0:
            source = "estimate"
        else:
            source = "mixed"

        return StaticCost(
            total_tokens=total_tokens,
            source=source,
            by_server=by_server,
            confidence=round(confidence, 2),
        )

    def get_zombie_context_tax(
        self,
        zombie_tools: Dict[str, List[str]],
        servers: List[ServerSchema],
    ) -> int:
        """Calculate tokens wasted on unused zombie tools.

        Estimates the portion of context tax attributed to tools that
        were never called during the session.

        Args:
            zombie_tools: Dict of server -> list of unused tool names
            servers: List of ServerSchema from analyze_*

        Returns:
            Estimated token count wasted on zombie tools
        """
        if not zombie_tools or not servers:
            return 0

        zombie_tokens = 0

        # Create lookup for server schemas
        server_lookup = {s.server: s for s in servers}

        for server_name, unused_tools in zombie_tools.items():
            if not unused_tools:
                continue

            # Get server schema if available
            schema = server_lookup.get(server_name)
            if schema and schema.tool_count > 0:
                # Calculate per-tool token estimate for this server
                tokens_per_tool = schema.estimated_tokens / schema.tool_count
                zombie_tokens += int(len(unused_tools) * tokens_per_tool)
            else:
                # Fall back to default estimate
                zombie_tokens += len(unused_tools) * self.tokens_per_tool

        return zombie_tokens


def discover_mcp_config(working_dir: Optional[Path] = None) -> Optional[Path]:
    """Discover MCP configuration file for the current project.

    Searches in order:
    1. .mcp.json in working directory
    2. .mcp.json in parent directories (up to home)
    3. ~/.claude/settings.json (global Claude Code config)

    Args:
        working_dir: Starting directory (defaults to cwd)

    Returns:
        Path to config file if found, None otherwise
    """
    if working_dir is None:
        working_dir = Path.cwd()

    # Search for .mcp.json in directory hierarchy
    current = working_dir
    home = Path.home()

    while current >= home:
        mcp_json = current / ".mcp.json"
        if mcp_json.exists():
            return mcp_json
        if current == home:
            break
        current = current.parent

    # Fall back to global Claude Code config
    global_config = home / ".claude" / "settings.json"
    if global_config.exists():
        return global_config

    return None


def calculate_context_tax(
    working_dir: Optional[Path] = None,
    config_path: Optional[Path] = None,
) -> StaticCost:
    """Convenience function to calculate context tax for current project.

    Args:
        working_dir: Working directory to search for config
        config_path: Explicit config path (skips discovery if provided)

    Returns:
        StaticCost with context tax estimate
    """
    analyzer = SchemaAnalyzer()

    if config_path is None:
        config_path = discover_mcp_config(working_dir)

    if config_path is None:
        logger.debug("No MCP config found, returning zero context tax")
        return StaticCost(
            total_tokens=0,
            source="none",
            by_server={},
            confidence=0.0,
        )

    try:
        servers = analyzer.analyze_from_file(config_path)
        return analyzer.calculate_static_cost(servers)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to analyze MCP config: {e}")
        return StaticCost(
            total_tokens=0,
            source="error",
            by_server={},
            confidence=0.0,
        )
