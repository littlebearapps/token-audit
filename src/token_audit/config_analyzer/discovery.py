"""
Multi-platform MCP config discovery.

Discovers MCP configuration files across Claude Code, Codex CLI, and Gemini CLI
platforms, supporting both project-level and global configurations.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ConfigFile:
    """Represents a discovered config file."""

    platform: str  # claude_code, codex_cli, gemini_cli
    path: Path
    scope: str  # "project" or "global"
    exists: bool = True

    def __post_init__(self) -> None:
        self.exists = self.path.exists()


# Platform-specific config file locations
# Order matters: project configs are checked before global
PLATFORM_CONFIG_PATHS: Dict[str, List[Tuple[Path, str]]] = {
    "claude_code": [
        (Path(".mcp.json"), "project"),  # Project-level
        (Path.home() / ".claude" / "settings.json", "global"),  # Global
    ],
    "codex_cli": [
        (Path.home() / ".codex" / "config.toml", "global"),  # Codex uses global only
    ],
    "gemini_cli": [
        (Path.home() / ".gemini" / "settings.json", "global"),  # Gemini uses global only
    ],
}


def detect_current_platform() -> Optional[str]:
    """Auto-detect current platform from environment.

    Checks environment variables and process indicators to determine
    which AI coding platform is currently running.

    Returns:
        Platform identifier or None if not detected
    """
    # Check for Claude Code
    if os.environ.get("CLAUDE_CODE_SESSION"):
        return "claude_code"

    # Check for Codex CLI
    if os.environ.get("CODEX_SESSION"):
        return "codex_cli"

    # Check for Gemini CLI
    if os.environ.get("GEMINI_CLI_SESSION"):
        return "gemini_cli"

    # Check for common indicators in PATH or other env vars
    path = os.environ.get("PATH", "")
    if ".claude" in path:
        return "claude_code"

    # Could not determine platform
    return None


def discover_config(
    platform: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> List[ConfigFile]:
    """Discover MCP config files for platform(s).

    Args:
        platform: Specific platform to search for (None = all platforms)
        cwd: Current working directory for project-level configs

    Returns:
        List of ConfigFile objects (includes both existing and expected paths)
    """
    if cwd is None:
        cwd = Path.cwd()

    configs: List[ConfigFile] = []
    platforms = [platform] if platform else list(PLATFORM_CONFIG_PATHS.keys())

    for plat in platforms:
        if plat not in PLATFORM_CONFIG_PATHS:
            continue

        for path_template, scope in PLATFORM_CONFIG_PATHS[plat]:
            # For project scope, resolve relative to cwd
            if scope == "project":
                config_path = cwd / path_template
            else:
                config_path = path_template

            configs.append(
                ConfigFile(
                    platform=plat,
                    path=config_path,
                    scope=scope,
                )
            )

    return configs


def discover_existing_configs(
    platform: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> List[ConfigFile]:
    """Discover only existing MCP config files.

    Args:
        platform: Specific platform to search for (None = all platforms)
        cwd: Current working directory for project-level configs

    Returns:
        List of ConfigFile objects for files that exist
    """
    all_configs = discover_config(platform, cwd)
    return [c for c in all_configs if c.exists]


def get_primary_config(
    platform: str,
    cwd: Optional[Path] = None,
) -> Optional[ConfigFile]:
    """Get the primary (highest priority) config for a platform.

    Project-level configs take precedence over global configs.

    Args:
        platform: Platform to get config for
        cwd: Current working directory for project-level configs

    Returns:
        Primary ConfigFile or None if no config exists
    """
    existing = discover_existing_configs(platform, cwd)
    if not existing:
        return None

    # Return first existing (project takes priority due to order)
    return existing[0]
