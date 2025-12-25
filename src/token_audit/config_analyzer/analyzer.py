"""
Config issue detection.

Analyzes MCP configuration files for common issues like excessive servers,
credential exposure, path problems, and misconfigurations.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .credential_detector import detect_credentials
from .parsers import MCPConfig


@dataclass
class ConfigIssue:
    """An issue detected in MCP configuration."""

    severity: str  # critical, high, medium, low, info
    category: str  # credential_exposure, excessive_servers, path_issue, duplicate_server, etc.
    message: str  # Human-readable description
    location: str  # Config file and key path
    recommendation: str  # How to fix the issue

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "location": self.location,
            "recommendation": self.recommendation,
        }


# Thresholds for issue detection
EXCESSIVE_SERVER_THRESHOLD = 15
MANY_SERVER_THRESHOLD = 10


def analyze_config(config: MCPConfig) -> List[ConfigIssue]:
    """Analyze MCP config for issues.

    Checks for:
    - Credential exposure (hardcoded secrets)
    - Excessive server count (>15)
    - Path issues (invalid/missing paths)
    - Duplicate servers
    - Parse errors

    Args:
        config: Parsed MCPConfig to analyze

    Returns:
        List of ConfigIssue objects
    """
    issues: List[ConfigIssue] = []

    # Check for parse errors first
    if config.parse_error:
        issues.append(
            ConfigIssue(
                severity="high",
                category="parse_error",
                message=config.parse_error,
                location=str(config.path),
                recommendation="Fix the configuration file syntax",
            )
        )
        return issues  # Can't analyze further if parsing failed

    # Check for credential exposure
    cred_issues = detect_credentials(config.raw_data)
    for cred in cred_issues:
        issues.append(
            ConfigIssue(
                severity=cred.severity,
                category="credential_exposure",
                message=f"Potential {cred.credential_type} exposed: {cred.value_preview}",
                location=f"{config.path}:{cred.location}",
                recommendation=cred.recommendation,
            )
        )

    # Check server count
    server_count = config.server_count
    if server_count > EXCESSIVE_SERVER_THRESHOLD:
        issues.append(
            ConfigIssue(
                severity="high",
                category="excessive_servers",
                message=f"Too many MCP servers configured: {server_count} (threshold: {EXCESSIVE_SERVER_THRESHOLD})",
                location=str(config.path),
                recommendation=(
                    "Each server adds context overhead. Consider removing unused servers "
                    "or using server profiles to load only what you need."
                ),
            )
        )
    elif server_count > MANY_SERVER_THRESHOLD:
        issues.append(
            ConfigIssue(
                severity="medium",
                category="many_servers",
                message=f"Many MCP servers configured: {server_count} (consider reviewing)",
                location=str(config.path),
                recommendation=(
                    "Review configured servers and remove any that are rarely used. "
                    "Each server contributes to context overhead."
                ),
            )
        )

    # Check for path issues in server commands
    for name, server in config.servers.items():
        path_issues = _check_server_paths(server.command, server.args, config.path)
        for path_issue in path_issues:
            issues.append(
                ConfigIssue(
                    severity="medium",
                    category="path_issue",
                    message=path_issue,
                    location=f"{config.path}:mcpServers.{name}",
                    recommendation="Verify the path exists and is accessible",
                )
            )

    # Check for disabled servers (info level - not a problem, just informational)
    disabled_count = server_count - config.enabled_server_count
    if disabled_count > 0:
        issues.append(
            ConfigIssue(
                severity="info",
                category="disabled_servers",
                message=f"{disabled_count} server(s) are disabled",
                location=str(config.path),
                recommendation=("Consider removing disabled servers if they're no longer needed"),
            )
        )

    # Check for empty env vars that might indicate missing secrets
    for name, server in config.servers.items():
        empty_env = [k for k, v in server.env.items() if v == "" or v is None]
        if empty_env:
            issues.append(
                ConfigIssue(
                    severity="medium",
                    category="empty_env",
                    message=f"Empty environment variable(s): {', '.join(empty_env)}",
                    location=f"{config.path}:mcpServers.{name}.env",
                    recommendation=("Set the environment variable value or remove if not needed"),
                )
            )

    return issues


def _check_server_paths(command: str, args: List[str], config_path: Path) -> List[str]:
    """Check if paths in server config exist.

    Args:
        command: Server command
        args: Command arguments
        config_path: Path to config file (for relative path resolution)

    Returns:
        List of path issue messages
    """
    issues: List[str] = []

    # Check command if it looks like a path
    if "/" in command or "\\" in command:
        cmd_path = Path(command)
        if not cmd_path.is_absolute():
            cmd_path = config_path.parent / cmd_path
        if not cmd_path.exists():
            issues.append(f"Command path not found: {command}")

    # Check args for paths
    for arg in args:
        if "/" in arg or "\\" in arg:
            # Skip if it looks like a flag value
            if arg.startswith("-") or arg.startswith("http"):
                continue

            arg_path = Path(arg)
            if not arg_path.is_absolute():
                arg_path = config_path.parent / arg_path

            if not arg_path.exists():
                issues.append(f"Argument path not found: {arg}")

    return issues
