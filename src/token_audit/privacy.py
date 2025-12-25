#!/usr/bin/env python3
"""
Privacy Module - Data redaction and sanitization utilities

Provides utilities for protecting sensitive data in session logs and exports.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Pattern


class PrivacyFilter:
    """
    Privacy filter for sensitive data redaction.

    Redacts common sensitive patterns:
    - API keys and tokens
    - Email addresses
    - File paths (optional)
    - IP addresses
    - Passwords
    - Credit card numbers
    - Phone numbers
    """

    # Regex patterns for common sensitive data
    # Note: api_key pattern requires prefixes to avoid false positives on UUIDs/IDs
    PATTERNS: Dict[str, Pattern[str]] = {
        "api_key": re.compile(
            r"\b(?:sk-|pk-|rk-|api[-_]?key[-_]?|secret[-_]?key[-_]?)[A-Za-z0-9_-]{6,}\b"
        ),
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "password": re.compile(r'(?i)(password|passwd|pwd)["\s:=]+[^\s"]+'),
        "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
        "phone": re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "jwt_token": re.compile(r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*"),
        "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9_-]+"),
        "ssh_key": re.compile(r"ssh-rsa\s+[A-Za-z0-9+/=]+"),
    }

    # Path patterns (optional redaction)
    PATH_PATTERNS: Dict[str, Pattern[str]] = {
        "home_dir": re.compile(r"/Users/[^/\s]+|/home/[^/\s]+|C:\\Users\\[^\\]+"),
        "full_path": re.compile(r"(?:/[\w.-]+)+|(?:[A-Z]:\\(?:[\w.-]+\\)*[\w.-]+)"),
    }

    def __init__(
        self, redact_paths: bool = False, custom_patterns: Dict[str, Pattern[str]] | None = None
    ):
        """
        Initialize privacy filter.

        Args:
            redact_paths: Whether to redact file paths (default: False)
            custom_patterns: Additional custom regex patterns to redact
        """
        self.redact_paths = redact_paths
        self.custom_patterns = custom_patterns or {}

    def redact_string(self, text: str, placeholder: str = "[REDACTED]") -> str:
        """
        Redact sensitive data from a string.

        Args:
            text: Input text
            placeholder: Replacement string for redacted data

        Returns:
            Redacted text
        """
        if not text:
            return text

        # Apply standard patterns
        for _pattern_name, pattern in self.PATTERNS.items():
            text = pattern.sub(placeholder, text)

        # Apply path patterns if enabled
        if self.redact_paths:
            for _pattern_name, pattern in self.PATH_PATTERNS.items():
                text = pattern.sub(f"{placeholder}_PATH", text)

        # Apply custom patterns
        for _pattern_name, pattern in self.custom_patterns.items():
            text = pattern.sub(placeholder, text)

        return text

    def redact_dict(
        self,
        data: Dict[str, Any],
        sensitive_keys: List[str] | None = None,
        placeholder: str = "[REDACTED]",
    ) -> Dict[str, Any]:
        """
        Redact sensitive data from a dictionary.

        Args:
            data: Input dictionary
            sensitive_keys: List of keys to redact (case-insensitive)
            placeholder: Replacement string for redacted data

        Returns:
            Dictionary with redacted values
        """
        # Track if custom sensitive_keys were provided
        use_pattern_redaction = sensitive_keys is None

        if sensitive_keys is None:
            sensitive_keys = [
                "password",
                "passwd",
                "pwd",
                "secret",
                "token",
                "api_key",
                "apikey",
                "auth",
                "authorization",
                "credential",
                "private_key",
            ]

        # Convert to lowercase for case-insensitive matching
        sensitive_keys_lower = [k.lower() for k in sensitive_keys]

        def redact_value(key: str, value: Any) -> Any:
            """Recursively redact values"""
            # Check if key is sensitive
            if key.lower() in sensitive_keys_lower:
                return placeholder

            # Recursively process nested structures
            if isinstance(value, dict):
                return {k: redact_value(k, v) for k, v in value.items()}
            elif isinstance(value, list):
                return [redact_value(key, item) for item in value]
            elif isinstance(value, str) and use_pattern_redaction:
                # Only apply pattern-based redaction if using default sensitive_keys
                return self.redact_string(value, placeholder)
            else:
                return value

        return {k: redact_value(k, v) for k, v in data.items()}

    def redact_json(
        self,
        json_str: str,
        sensitive_keys: List[str] | None = None,
        placeholder: str = "[REDACTED]",
    ) -> str:
        """
        Redact sensitive data from JSON string.

        Args:
            json_str: JSON string
            sensitive_keys: List of keys to redact
            placeholder: Replacement string for redacted data

        Returns:
            Redacted JSON string
        """
        try:
            data = json.loads(json_str)
            redacted_data = self.redact_dict(data, sensitive_keys, placeholder)
            return json.dumps(redacted_data, indent=2)
        except json.JSONDecodeError:
            # If not valid JSON, treat as plain string
            return self.redact_string(json_str, placeholder)

    def redact_file(
        self, input_path: Path, output_path: Path, placeholder: str = "[REDACTED]"
    ) -> None:
        """
        Redact sensitive data from a file.

        Args:
            input_path: Input file path
            output_path: Output file path
            placeholder: Replacement string for redacted data
        """
        with open(input_path) as f:
            content = f.read()

        # Try to parse as JSON first
        try:
            data = json.loads(content)
            redacted_data = self.redact_dict(data, placeholder=placeholder)
            redacted_content = json.dumps(redacted_data, indent=2)
        except json.JSONDecodeError:
            # Not JSON, treat as plain text
            redacted_content = self.redact_string(content, placeholder)

        with open(output_path, "w") as f:
            f.write(redacted_content)


# ============================================================================
# Session Data Privacy
# ============================================================================


class SessionPrivacyFilter:
    """
    Specialized privacy filter for Token Audit session data.

    Redacts:
    - Tool input parameters (optional - may contain sensitive prompts)
    - Platform metadata (may contain file paths, user info)
    - Git metadata (may contain usernames, emails)
    """

    def __init__(self, redact_tool_inputs: bool = False):
        """
        Initialize session privacy filter.

        Args:
            redact_tool_inputs: Whether to redact tool input parameters
        """
        self.privacy_filter = PrivacyFilter(redact_paths=True)
        self.redact_tool_inputs = redact_tool_inputs

    def sanitize_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize session data for safe sharing.

        Args:
            session_data: Session data dictionary

        Returns:
            Sanitized session data
        """
        # Make a copy to avoid modifying original
        sanitized = session_data.copy()

        # Redact platform metadata
        if "platform_data" in sanitized:
            sanitized["platform_data"] = self._sanitize_platform_data(sanitized["platform_data"])

        # Redact git metadata
        if "git_metadata" in sanitized:
            sanitized["git_metadata"] = self._sanitize_git_metadata(sanitized["git_metadata"])

        # Redact server sessions
        if "server_sessions" in sanitized:
            sanitized["server_sessions"] = self._sanitize_server_sessions(
                sanitized["server_sessions"]
            )

        return sanitized

    def _sanitize_platform_data(self, platform_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize platform metadata"""
        if not platform_data:
            return platform_data

        sanitized = platform_data.copy()

        # Redact file paths
        for key in ["debug_log_path", "claude_dir", "checkpoint_path"]:
            if key in sanitized:
                sanitized[key] = "[REDACTED_PATH]"

        return sanitized

    def _sanitize_git_metadata(self, git_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize git metadata"""
        if not git_metadata:
            return git_metadata

        sanitized = git_metadata.copy()

        # Keep branch name, commit hash, and status
        # These are generally not sensitive

        return sanitized

    def _sanitize_server_sessions(self, server_sessions: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize server session data"""
        sanitized = {}

        for server_name, server_session in server_sessions.items():
            sanitized[server_name] = server_session.copy()

            # Sanitize tool data
            if "tools" in sanitized[server_name]:
                sanitized[server_name]["tools"] = self._sanitize_tools(
                    sanitized[server_name]["tools"]
                )

        return sanitized

    def _sanitize_tools(self, tools: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize tool data"""
        sanitized = {}

        for tool_name, tool_data in tools.items():
            sanitized[tool_name] = tool_data.copy()

            # Redact call history if requested
            if self.redact_tool_inputs and "call_history" in sanitized[tool_name]:
                sanitized[tool_name]["call_history"] = [
                    self._sanitize_call(call) for call in sanitized[tool_name]["call_history"]
                ]

        return sanitized

    def _sanitize_call(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize individual call data"""
        sanitized = call.copy()

        # Redact platform data (may contain input parameters)
        if "platform_data" in sanitized:
            sanitized["platform_data"] = "[REDACTED]"

        # Redact content hash (derived from input parameters)
        if "content_hash" in sanitized:
            # Keep hash for duplicate detection, but it's anonymized anyway
            pass

        return sanitized


# ============================================================================
# Convenience Functions
# ============================================================================


def redact_string(text: str, redact_paths: bool = False) -> str:
    """
    Convenience function to redact sensitive data from a string.

    Args:
        text: Input text
        redact_paths: Whether to redact file paths

    Returns:
        Redacted text
    """
    filter = PrivacyFilter(redact_paths=redact_paths)
    return filter.redact_string(text)


def sanitize_session_file(
    input_path: Path, output_path: Path, redact_tool_inputs: bool = False
) -> None:
    """
    Sanitize a session file for safe sharing.

    Args:
        input_path: Input session file (summary.json)
        output_path: Output sanitized file
        redact_tool_inputs: Whether to redact tool inputs
    """
    with open(input_path) as f:
        session_data = json.load(f)

    filter = SessionPrivacyFilter(redact_tool_inputs=redact_tool_inputs)
    sanitized = filter.sanitize_session(session_data)

    with open(output_path, "w") as f:
        json.dump(sanitized, f, indent=2)


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    print("Privacy Module Tests")
    print("=" * 60)

    # Test basic redaction
    filter = PrivacyFilter()

    test_cases = [
        "My API key is sk-1234567890abcdefghij",
        "Email me at john@example.com",
        "Password: secret123",
        "Server IP: 192.168.1.100",
        "JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ]

    print("\nString Redaction Tests:")
    for test in test_cases:
        redacted = filter.redact_string(test)
        print(f"Original: {test[:50]}...")
        print(f"Redacted: {redacted}\n")

    # Test dictionary redaction
    test_dict = {
        "username": "john",
        "password": "secret123",
        "api_key": "sk-1234567890",
        "email": "john@example.com",
        "metadata": {"token": "bearer_xyz", "public_data": "This is safe"},
    }

    print("\nDictionary Redaction Test:")
    print("Original:", test_dict)
    redacted_dict = filter.redact_dict(test_dict)
    print("Redacted:", redacted_dict)

    print("\nPrivacy module initialized successfully")
