#!/usr/bin/env python3
"""
Test suite for privacy module

Tests data redaction and sanitization utilities.
"""

import pytest
import json
import re
from pathlib import Path
from token_audit.privacy import (
    PrivacyFilter,
    SessionPrivacyFilter,
    redact_string,
    sanitize_session_file,
)


class TestPrivacyFilterPatterns:
    """Tests for PrivacyFilter pattern matching"""

    def test_api_key_redaction(self) -> None:
        """Test API key redaction"""
        filter = PrivacyFilter()

        text = "My API key is sk-1234567890abcdefghijklmnop"
        redacted = filter.redact_string(text)

        assert "sk-1234567890abcdefghijklmnop" not in redacted
        assert "[REDACTED]" in redacted

    def test_email_redaction(self) -> None:
        """Test email address redaction"""
        filter = PrivacyFilter()

        text = "Contact me at john.doe@example.com"
        redacted = filter.redact_string(text)

        assert "john.doe@example.com" not in redacted
        assert "[REDACTED]" in redacted

    def test_ipv4_redaction(self) -> None:
        """Test IPv4 address redaction"""
        filter = PrivacyFilter()

        text = "Server at 192.168.1.100"
        redacted = filter.redact_string(text)

        assert "192.168.1.100" not in redacted
        assert "[REDACTED]" in redacted

    def test_password_redaction(self) -> None:
        """Test password redaction"""
        filter = PrivacyFilter()

        text = "password: mysecret123"
        redacted = filter.redact_string(text)

        assert "mysecret123" not in redacted
        assert "[REDACTED]" in redacted

    def test_credit_card_redaction(self) -> None:
        """Test credit card redaction"""
        filter = PrivacyFilter()

        text = "Card: 1234-5678-9012-3456"
        redacted = filter.redact_string(text)

        assert "1234-5678-9012-3456" not in redacted
        assert "[REDACTED]" in redacted

    def test_phone_redaction(self) -> None:
        """Test phone number redaction"""
        filter = PrivacyFilter()

        text = "Call 555-123-4567"
        redacted = filter.redact_string(text)

        assert "555-123-4567" not in redacted
        assert "[REDACTED]" in redacted

    def test_jwt_token_redaction(self) -> None:
        """Test JWT token redaction"""
        filter = PrivacyFilter()

        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        redacted = filter.redact_string(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
        assert "[REDACTED]" in redacted

    def test_bearer_token_redaction(self) -> None:
        """Test Bearer token redaction"""
        filter = PrivacyFilter()

        text = "Authorization: Bearer abc123xyz456"
        redacted = filter.redact_string(text)

        assert "Bearer abc123xyz456" not in redacted
        assert "[REDACTED]" in redacted

    def test_ssh_key_redaction(self) -> None:
        """Test SSH key redaction"""
        filter = PrivacyFilter()

        text = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC..."
        redacted = filter.redact_string(text)

        assert "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC" not in redacted
        assert "[REDACTED]" in redacted


class TestPrivacyFilterPathRedaction:
    """Tests for path redaction (optional)"""

    def test_path_redaction_disabled_by_default(self) -> None:
        """Test path redaction is disabled by default"""
        filter = PrivacyFilter(redact_paths=False)

        text = "/Users/john/Documents/file.txt"
        redacted = filter.redact_string(text)

        # Paths should NOT be redacted when disabled
        assert "/Users/john" in redacted

    def test_home_dir_redaction(self) -> None:
        """Test home directory redaction when enabled"""
        filter = PrivacyFilter(redact_paths=True)

        text = "/Users/john/Documents/file.txt"
        redacted = filter.redact_string(text)

        assert "/Users/john" not in redacted
        assert "[REDACTED]_PATH" in redacted

    def test_windows_path_redaction(self) -> None:
        """Test Windows path redaction"""
        filter = PrivacyFilter(redact_paths=True)

        text = "C:\\Users\\john\\Documents\\file.txt"
        redacted = filter.redact_string(text)

        assert "C:\\Users\\john" not in redacted
        assert "[REDACTED]_PATH" in redacted


class TestPrivacyFilterCustomPatterns:
    """Tests for custom pattern support"""

    def test_custom_pattern_redaction(self) -> None:
        """Test custom regex patterns"""
        custom_patterns = {"custom_id": re.compile(r"ID-\d{6}")}

        filter = PrivacyFilter(custom_patterns=custom_patterns)

        text = "User ID-123456 logged in"
        redacted = filter.redact_string(text)

        assert "ID-123456" not in redacted
        assert "[REDACTED]" in redacted


class TestPrivacyFilterDictRedaction:
    """Tests for dictionary redaction"""

    def test_redact_dict_sensitive_keys(self) -> None:
        """Test redacting sensitive keys from dict"""
        filter = PrivacyFilter()

        data = {
            "username": "john",
            "password": "secret123",
            "api_key": "sk-1234567890",
            "email": "john@example.com",
        }

        redacted = filter.redact_dict(data)

        assert redacted["username"] == "john"  # Not sensitive
        assert redacted["password"] == "[REDACTED]"
        assert redacted["api_key"] == "[REDACTED]"
        # Email in value should be redacted too
        assert "@example.com" not in redacted["email"]

    def test_redact_dict_nested(self) -> None:
        """Test redacting nested dictionaries"""
        filter = PrivacyFilter()

        data = {"user": {"name": "john", "password": "secret123", "metadata": {"token": "abc123"}}}

        redacted = filter.redact_dict(data)

        assert redacted["user"]["name"] == "john"
        assert redacted["user"]["password"] == "[REDACTED]"
        assert redacted["user"]["metadata"]["token"] == "[REDACTED]"

    def test_redact_dict_with_lists(self) -> None:
        """Test redacting dictionaries containing lists"""
        filter = PrivacyFilter()

        data = {
            "users": [
                {"name": "john", "password": "secret1"},
                {"name": "jane", "password": "secret2"},
            ]
        }

        redacted = filter.redact_dict(data)

        assert redacted["users"][0]["name"] == "john"
        assert redacted["users"][0]["password"] == "[REDACTED]"
        assert redacted["users"][1]["password"] == "[REDACTED]"

    def test_redact_dict_custom_sensitive_keys(self) -> None:
        """Test redacting with custom sensitive key list"""
        filter = PrivacyFilter()

        data = {
            "username": "john",
            "public_key": "not_really_sensitive",
            "custom_secret": "very_secret",
        }

        redacted = filter.redact_dict(data, sensitive_keys=["custom_secret"])

        assert redacted["username"] == "john"
        assert redacted["public_key"] == "not_really_sensitive"
        assert redacted["custom_secret"] == "[REDACTED]"


class TestPrivacyFilterJSONRedaction:
    """Tests for JSON string redaction"""

    def test_redact_json_valid(self) -> None:
        """Test redacting valid JSON string"""
        filter = PrivacyFilter()

        json_str = '{"username": "john", "password": "secret123"}'
        redacted = filter.redact_json(json_str)

        data = json.loads(redacted)
        assert data["username"] == "john"
        assert data["password"] == "[REDACTED]"

    def test_redact_json_invalid(self) -> None:
        """Test redacting invalid JSON (fallback to string redaction)"""
        filter = PrivacyFilter()

        invalid_json = "{ invalid json with password: secret123 }"
        redacted = filter.redact_json(invalid_json)

        assert "secret123" not in redacted
        assert "[REDACTED]" in redacted


class TestPrivacyFilterFileRedaction:
    """Tests for file redaction"""

    def test_redact_file_json(self, tmp_path) -> None:
        """Test redacting JSON file"""
        filter = PrivacyFilter()

        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.json"

        # Write test data
        data = {"username": "john", "password": "secret123"}
        input_file.write_text(json.dumps(data))

        # Redact
        filter.redact_file(input_file, output_file)

        # Verify
        output_data = json.loads(output_file.read_text())
        assert output_data["username"] == "john"
        assert output_data["password"] == "[REDACTED]"

    def test_redact_file_text(self, tmp_path) -> None:
        """Test redacting plain text file"""
        filter = PrivacyFilter()

        input_file = tmp_path / "input.txt"
        output_file = tmp_path / "output.txt"

        # Write test data
        input_file.write_text("My API key is sk-1234567890abcdefghij")

        # Redact
        filter.redact_file(input_file, output_file)

        # Verify
        output_text = output_file.read_text()
        assert "sk-1234567890abcdefghij" not in output_text
        assert "[REDACTED]" in output_text


# ============================================================================
# SessionPrivacyFilter Tests
# ============================================================================


class TestSessionPrivacyFilter:
    """Tests for SessionPrivacyFilter"""

    def test_sanitize_session_basic(self) -> None:
        """Test basic session sanitization"""
        filter = SessionPrivacyFilter()

        session_data = {
            "project": "test-project",
            "platform": "claude-code",
            "token_usage": {"total_tokens": 1000},
        }

        sanitized = filter.sanitize_session(session_data)

        assert sanitized["project"] == "test-project"
        assert sanitized["platform"] == "claude-code"

    def test_sanitize_platform_data(self) -> None:
        """Test platform data sanitization"""
        filter = SessionPrivacyFilter()

        session_data = {
            "project": "test-project",
            "platform_data": {
                "debug_log_path": "/Users/john/.claude/debug.log",
                "claude_dir": "/Users/john/.claude",
                "checkpoint_path": "/tmp/checkpoint",
            },
        }

        sanitized = filter.sanitize_session(session_data)

        assert sanitized["platform_data"]["debug_log_path"] == "[REDACTED_PATH]"
        assert sanitized["platform_data"]["claude_dir"] == "[REDACTED_PATH]"
        assert sanitized["platform_data"]["checkpoint_path"] == "[REDACTED_PATH]"

    def test_sanitize_git_metadata(self) -> None:
        """Test git metadata sanitization"""
        filter = SessionPrivacyFilter()

        session_data = {"git_metadata": {"branch": "main", "commit": "abc123", "status": "clean"}}

        sanitized = filter.sanitize_session(session_data)

        # Git metadata should be preserved (not sensitive)
        assert sanitized["git_metadata"]["branch"] == "main"
        assert sanitized["git_metadata"]["commit"] == "abc123"

    def test_sanitize_server_sessions(self) -> None:
        """Test server session sanitization"""
        filter = SessionPrivacyFilter(redact_tool_inputs=False)

        session_data = {
            "server_sessions": {
                "zen": {"tools": {"mcp__zen__chat": {"calls": 5, "total_tokens": 1000}}}
            }
        }

        sanitized = filter.sanitize_session(session_data)

        # Server sessions should be preserved when not redacting inputs
        assert "zen" in sanitized["server_sessions"]
        assert "mcp__zen__chat" in sanitized["server_sessions"]["zen"]["tools"]

    def test_sanitize_tool_inputs_enabled(self) -> None:
        """Test tool input redaction when enabled"""
        filter = SessionPrivacyFilter(redact_tool_inputs=True)

        session_data = {
            "server_sessions": {
                "zen": {
                    "tools": {
                        "mcp__zen__chat": {
                            "calls": 5,
                            "call_history": [
                                {
                                    "platform_data": {"input": "sensitive query"},
                                    "content_hash": "abc123",
                                }
                            ],
                        }
                    }
                }
            }
        }

        sanitized = filter.sanitize_session(session_data)

        # Platform data should be redacted
        call = sanitized["server_sessions"]["zen"]["tools"]["mcp__zen__chat"]["call_history"][0]
        assert call["platform_data"] == "[REDACTED]"
        # Content hash should be preserved (anonymized anyway)
        assert call["content_hash"] == "abc123"


# ============================================================================
# Convenience Functions Tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_redact_string_function(self) -> None:
        """Test redact_string convenience function"""
        text = "My API key is sk-1234567890abcdefghij"
        redacted = redact_string(text)

        assert "sk-1234567890abcdefghij" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_string_with_paths(self) -> None:
        """Test redact_string with path redaction enabled"""
        text = "File at /Users/john/file.txt"
        redacted = redact_string(text, redact_paths=True)

        assert "/Users/john" not in redacted
        assert "[REDACTED]_PATH" in redacted


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_redact_empty_string(self) -> None:
        """Test redacting empty string"""
        filter = PrivacyFilter()

        redacted = filter.redact_string("")

        assert redacted == ""

    def test_redact_none_string(self) -> None:
        """Test redacting None"""
        filter = PrivacyFilter()

        redacted = filter.redact_string(None)

        assert redacted is None

    def test_redact_dict_empty(self) -> None:
        """Test redacting empty dictionary"""
        filter = PrivacyFilter()

        redacted = filter.redact_dict({})

        assert redacted == {}

    def test_custom_placeholder(self) -> None:
        """Test custom placeholder text"""
        filter = PrivacyFilter()

        text = "My API key is sk-1234567890abcdefghij"
        redacted = filter.redact_string(text, placeholder="***HIDDEN***")

        assert "sk-1234567890abcdefghij" not in redacted
        assert "***HIDDEN***" in redacted

    def test_multiple_patterns_in_text(self) -> None:
        """Test multiple sensitive patterns in one text"""
        filter = PrivacyFilter()

        text = "User john@example.com with key sk-123456 at 192.168.1.1"
        redacted = filter.redact_string(text)

        assert "john@example.com" not in redacted
        assert "sk-123456" not in redacted
        assert "192.168.1.1" not in redacted
        assert redacted.count("[REDACTED]") >= 3


# ============================================================================
# Integration Tests
# ============================================================================


class TestPrivacyIntegration:
    """Integration tests for complete privacy workflow"""

    def test_complete_session_sanitization(self) -> None:
        """Test complete session sanitization workflow"""
        filter = SessionPrivacyFilter(redact_tool_inputs=True)

        # Complex session data
        session_data = {
            "project": "test-project",
            "platform": "claude-code",
            "platform_data": {"debug_log_path": "/Users/john/.claude/debug.log"},
            "git_metadata": {"branch": "main"},
            "server_sessions": {
                "zen": {
                    "tools": {
                        "mcp__zen__chat": {
                            "calls": 2,
                            "call_history": [
                                {"platform_data": {"input": "query"}},
                                {"platform_data": {"input": "another"}},
                            ],
                        }
                    }
                }
            },
        }

        sanitized = filter.sanitize_session(session_data)

        # Verify all sanitization applied
        assert sanitized["platform_data"]["debug_log_path"] == "[REDACTED_PATH]"
        assert sanitized["git_metadata"]["branch"] == "main"
        assert (
            sanitized["server_sessions"]["zen"]["tools"]["mcp__zen__chat"]["call_history"][0][
                "platform_data"
            ]
            == "[REDACTED]"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
