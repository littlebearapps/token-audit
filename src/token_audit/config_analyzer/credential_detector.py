"""
Hardcoded credential detection for MCP config files.

Scans configuration for potentially exposed secrets like API keys,
tokens, passwords, and other sensitive values.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class CredentialIssue:
    """A detected credential exposure in config."""

    credential_type: str  # e.g., "OpenAI API key", "GitHub PAT"
    location: str  # Config path where found (e.g., "mcpServers.myserver.env.API_KEY")
    pattern_matched: str  # The regex pattern that matched
    value_preview: str  # First/last few chars for identification (e.g., "sk-...abc")
    severity: str = "critical"  # Always critical for credential exposure
    recommendation: str = ""

    def __post_init__(self) -> None:
        if not self.recommendation:
            self.recommendation = (
                f"Move {self.credential_type} to environment variable or secure secret manager"
            )


# Credential patterns: (regex, credential_type, preview_formatter)
# Preview formatter takes the matched value and returns a safe preview
CREDENTIAL_PATTERNS: List[Tuple[str, str, Callable[[str], str]]] = [
    # OpenAI
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key", lambda v: f"{v[:7]}...{v[-4:]}"),
    (r"sk-proj-[a-zA-Z0-9_-]{48,}", "OpenAI Project API key", lambda v: f"{v[:12]}...{v[-4:]}"),
    # Anthropic
    (r"sk-ant-[a-zA-Z0-9_-]{32,}", "Anthropic API key", lambda v: f"{v[:10]}...{v[-4:]}"),
    # GitHub
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub PAT (classic)", lambda v: f"{v[:7]}...{v[-4:]}"),
    (
        r"github_pat_[a-zA-Z0-9_]{22,}",
        "GitHub PAT (fine-grained)",
        lambda v: f"{v[:15]}...{v[-4:]}",
    ),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth token", lambda v: f"{v[:7]}...{v[-4:]}"),
    (r"ghs_[a-zA-Z0-9]{36}", "GitHub App token", lambda v: f"{v[:7]}...{v[-4:]}"),
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", lambda v: f"{v[:8]}...{v[-4:]}"),
    (
        r"(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9+/]{40})",
        "AWS Secret Key",
        lambda v: f"***...{v[-4:]}",
    ),
    # Google
    (r"AIza[0-9A-Za-z_-]{35}", "Google API key", lambda v: f"{v[:8]}...{v[-4:]}"),
    # Slack
    (
        r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*",
        "Slack token",
        lambda v: f"{v[:10]}...{v[-4:]}",
    ),
    # Generic patterns
    (
        r"['\"]?(?:password|passwd|pwd)['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
        "Hardcoded password",
        lambda _: "***",
    ),
    (
        r"['\"]?(?:secret|api_key|apikey|token|auth)['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9_-]{20,})['\"]",
        "Generic secret",
        lambda v: f"***...{v[-4:] if len(v) > 4 else '***'}",
    ),
]


def _scan_value(value: str, location: str) -> List[CredentialIssue]:
    """Scan a single value for credential patterns.

    Args:
        value: String value to scan
        location: Config path for this value

    Returns:
        List of detected credential issues
    """
    issues: List[CredentialIssue] = []

    for pattern, cred_type, preview_fn in CREDENTIAL_PATTERNS:
        matches = re.finditer(pattern, value, re.IGNORECASE)
        for match in matches:
            # Get the matched value (either full match or first group)
            matched_value = match.group(1) if match.lastindex else match.group(0)
            issues.append(
                CredentialIssue(
                    credential_type=cred_type,
                    location=location,
                    pattern_matched=pattern[:30] + "...",  # Truncate long patterns
                    value_preview=preview_fn(matched_value),
                )
            )

    return issues


def _scan_dict(
    data: Dict[str, Any],
    path_prefix: str = "",
) -> List[CredentialIssue]:
    """Recursively scan a dictionary for credentials.

    Args:
        data: Dictionary to scan
        path_prefix: Current path in the config tree

    Returns:
        List of detected credential issues
    """
    issues: List[CredentialIssue] = []

    for key, value in data.items():
        current_path = f"{path_prefix}.{key}" if path_prefix else key

        if isinstance(value, str):
            issues.extend(_scan_value(value, current_path))
        elif isinstance(value, dict):
            issues.extend(_scan_dict(value, current_path))
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                item_path = f"{current_path}[{idx}]"
                if isinstance(item, str):
                    issues.extend(_scan_value(item, item_path))
                elif isinstance(item, dict):
                    issues.extend(_scan_dict(item, item_path))

    return issues


def detect_credentials(config_data: Dict[str, Any]) -> List[CredentialIssue]:
    """Scan MCP config for hardcoded credentials.

    Args:
        config_data: Parsed config dictionary

    Returns:
        List of CredentialIssue objects for each detected credential
    """
    return _scan_dict(config_data)
