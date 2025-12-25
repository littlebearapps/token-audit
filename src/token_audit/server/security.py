"""
Security utilities for MCP server.

Provides path validation, output sanitization, and credential redaction
to protect against path traversal attacks and information disclosure.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import credential patterns from existing module
from ..config_analyzer.credential_detector import CREDENTIAL_PATTERNS

# ============================================================================
# Path Validation
# ============================================================================

# Allowed directories for config file access
ALLOWED_CONFIG_DIRS: List[Path] = [
    Path.home() / ".claude",
    Path.home() / ".codex",
    Path.home() / ".gemini",
]

# Allowed file extensions for config files
ALLOWED_EXTENSIONS: List[str] = [".json", ".toml"]


def validate_config_path(path_str: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Validate that config_path is within allowed directories.

    Security checks:
    1. Reject path traversal sequences (..)
    2. Expand ~ to home directory
    3. Resolve to absolute path
    4. Verify path is within allowed directories
    5. Verify file extension is allowed

    Args:
        path_str: User-provided path string

    Returns:
        Tuple of (validated_path, error_message)
        - If valid: (Path, None)
        - If invalid: (None, error_message)
    """
    if not path_str:
        return None, "Empty path provided"

    # Security: Reject path traversal attempts early
    if ".." in path_str:
        return None, "Path traversal sequences (..) are not allowed"

    try:
        # Expand ~ to home directory
        path = Path(path_str).expanduser()

        # Resolve to absolute path (handles . and symlinks)
        resolved = path.resolve()

        # Security: Check resolved path doesn't contain traversal
        # (catches symlink escapes)
        if ".." in str(resolved):
            return None, "Path resolves to invalid location"

        # Security: Verify path is within allowed directories
        is_allowed = False
        for allowed_dir in ALLOWED_CONFIG_DIRS:
            try:
                resolved.relative_to(allowed_dir.resolve())
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            allowed_dirs_str = ", ".join(f"~/{d.name}/" for d in ALLOWED_CONFIG_DIRS)
            return None, f"Path must be within allowed directories: {allowed_dirs_str}"

        # Security: Validate file extension
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            return None, f"Invalid file extension. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

        return resolved, None

    except (OSError, ValueError) as e:
        return None, f"Invalid path: {type(e).__name__}"


# ============================================================================
# Output Sanitization
# ============================================================================


def sanitize_path_for_output(path: str | Path) -> str:
    """
    Convert full path to safe abbreviated form for output.

    Replaces home directory with ~ to avoid exposing full paths.

    Args:
        path: Full path (string or Path object)

    Returns:
        Abbreviated path string (e.g., ~/.claude/settings.json)
    """
    path_str = str(path)
    home = str(Path.home())

    if path_str.startswith(home):
        return "~" + path_str[len(home) :]

    # If path is outside home, use generic placeholder
    return "[config path]"


def redact_credential_preview(value: str) -> str:
    """
    Create redacted preview matching credential_detector format.

    Uses the same patterns and preview formatters as credential_detector
    to maintain consistency (e.g., sk-...abc format).

    Args:
        value: String that may contain credentials

    Returns:
        String with credentials redacted to preview format
    """
    if not value:
        return value

    result = value
    for pattern, _cred_type, preview_fn in CREDENTIAL_PATTERNS:
        matches = list(re.finditer(pattern, result, re.IGNORECASE))
        # Process matches in reverse order to preserve positions
        for match in reversed(matches):
            matched_value = match.group(1) if match.lastindex else match.group(0)
            redacted = preview_fn(matched_value)
            result = result[: match.start()] + redacted + result[match.end() :]

    return result


def sanitize_output_dict(
    data: Dict[str, Any],
    redact_credentials: bool = True,
    sanitize_paths: bool = True,
) -> Dict[str, Any]:
    """
    Recursively sanitize dictionary values for safe MCP output.

    Args:
        data: Dictionary to sanitize
        redact_credentials: Whether to redact credential patterns
        sanitize_paths: Whether to abbreviate file paths

    Returns:
        Sanitized dictionary
    """

    def sanitize_value(value: Any) -> Any:
        if isinstance(value, str):
            result = value
            if redact_credentials:
                result = redact_credential_preview(result)
            if sanitize_paths:
                # Only sanitize if it looks like a path
                if result.startswith("/") or result.startswith("~"):
                    result = sanitize_path_for_output(result)
            return result
        elif isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(item) for item in value]
        else:
            return value

    return {k: sanitize_value(v) for k, v in data.items()}


def sanitize_error_message(message: str) -> str:
    """
    Sanitize error message to prevent information disclosure.

    Redacts credentials and abbreviates paths.

    Args:
        message: Error message that may contain sensitive data

    Returns:
        Sanitized error message
    """
    # Redact credentials
    result = redact_credential_preview(message)

    # Abbreviate home directory paths
    home = str(Path.home())
    result = result.replace(home, "~")

    return result
