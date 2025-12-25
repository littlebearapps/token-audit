"""
Config analyzer module for MCP configuration analysis.

Provides multi-platform MCP config discovery, parsing, and issue detection
for Claude Code, Codex CLI, and Gemini CLI.
"""

from .analyzer import ConfigIssue, analyze_config
from .credential_detector import CredentialIssue, detect_credentials
from .discovery import (
    ConfigFile,
    detect_current_platform,
    discover_config,
    discover_existing_configs,
    get_primary_config,
)
from .parsers import MCPConfig, ServerConfig, parse_config, parse_json_config, parse_toml_config
from .pinned_servers import (
    SOURCE_AUTO_DETECT_LOCAL,
    SOURCE_EXPLICIT,
    SOURCE_HIGH_USAGE,
    PinnedServer,
    PinnedServerDetector,
    detect_pinned_servers,
)

__all__ = [
    # Discovery
    "ConfigFile",
    "discover_config",
    "discover_existing_configs",
    "get_primary_config",
    "detect_current_platform",
    # Parsing
    "MCPConfig",
    "ServerConfig",
    "parse_config",
    "parse_json_config",
    "parse_toml_config",
    # Analysis
    "ConfigIssue",
    "analyze_config",
    # Credentials
    "CredentialIssue",
    "detect_credentials",
    # Pinned servers
    "PinnedServer",
    "PinnedServerDetector",
    "SOURCE_AUTO_DETECT_LOCAL",
    "SOURCE_EXPLICIT",
    "SOURCE_HIGH_USAGE",
    "detect_pinned_servers",
]
