"""Tests for MCP server security features.

These tests verify:
- Path validation to prevent traversal attacks
- Output sanitization to prevent credential exposure
- Error message sanitization to prevent information disclosure
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from token_audit.server.security import (
    ALLOWED_CONFIG_DIRS,
    ALLOWED_EXTENSIONS,
    redact_credential_preview,
    sanitize_error_message,
    sanitize_output_dict,
    sanitize_path_for_output,
    validate_config_path,
)


# =============================================================================
# Path Validation Tests
# =============================================================================


class TestValidateConfigPath:
    """Tests for config_path validation."""

    def test_rejects_path_traversal_double_dot(self) -> None:
        """Test that ../ sequences are rejected."""
        path, error = validate_config_path("~/.claude/../../../etc/passwd")
        assert path is None
        assert error is not None
        assert ".." in error

    def test_rejects_path_traversal_middle(self) -> None:
        """Test that embedded .. is rejected."""
        path, error = validate_config_path("~/.claude/foo/../bar")
        assert path is None
        assert ".." in error

    def test_rejects_absolute_path_outside_allowed(self) -> None:
        """Test that absolute paths outside allowed dirs are rejected."""
        path, error = validate_config_path("/etc/passwd")
        assert path is None
        assert "allowed directories" in error

    def test_rejects_tmp_directory(self) -> None:
        """Test that /tmp is rejected."""
        path, error = validate_config_path("/tmp/malicious.json")
        assert path is None
        assert "allowed directories" in error

    def test_accepts_claude_config_dir(self, tmp_path: Path) -> None:
        """Test that ~/.claude/ paths are accepted."""
        # Create a mock file in ~/.claude/
        with patch.object(Path, "home", return_value=tmp_path):
            claude_dir = tmp_path / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            config_file = claude_dir / "settings.json"
            config_file.touch()

            # Need to re-import to pick up the patched home
            from token_audit.server import security

            # Patch ALLOWED_CONFIG_DIRS with tmp_path
            with patch.object(
                security,
                "ALLOWED_CONFIG_DIRS",
                [tmp_path / ".claude", tmp_path / ".codex", tmp_path / ".gemini"],
            ):
                path, error = security.validate_config_path(str(config_file))
                assert error is None
                assert path == config_file.resolve()

    def test_accepts_codex_config_dir(self, tmp_path: Path) -> None:
        """Test that ~/.codex/ paths are accepted."""
        from token_audit.server import security

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        config_file = codex_dir / "config.toml"
        config_file.touch()

        with patch.object(
            security,
            "ALLOWED_CONFIG_DIRS",
            [tmp_path / ".claude", tmp_path / ".codex", tmp_path / ".gemini"],
        ):
            path, error = security.validate_config_path(str(config_file))
            assert error is None
            assert path == config_file.resolve()

    def test_accepts_gemini_config_dir(self, tmp_path: Path) -> None:
        """Test that ~/.gemini/ paths are accepted."""
        from token_audit.server import security

        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir(parents=True, exist_ok=True)
        config_file = gemini_dir / "config.json"
        config_file.touch()

        with patch.object(
            security,
            "ALLOWED_CONFIG_DIRS",
            [tmp_path / ".claude", tmp_path / ".codex", tmp_path / ".gemini"],
        ):
            path, error = security.validate_config_path(str(config_file))
            assert error is None
            assert path == config_file.resolve()

    def test_rejects_invalid_extension_py(self) -> None:
        """Test that .py extension is rejected."""
        path, error = validate_config_path("~/.claude/malicious.py")
        assert path is None
        assert "extension" in error.lower()

    def test_rejects_invalid_extension_sh(self) -> None:
        """Test that .sh extension is rejected."""
        path, error = validate_config_path("~/.claude/script.sh")
        assert path is None
        assert "extension" in error.lower()

    def test_accepts_json_extension(self, tmp_path: Path) -> None:
        """Test that .json extension is accepted."""
        from token_audit.server import security

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        config_file = claude_dir / "config.json"
        config_file.touch()

        with patch.object(
            security,
            "ALLOWED_CONFIG_DIRS",
            [tmp_path / ".claude", tmp_path / ".codex", tmp_path / ".gemini"],
        ):
            path, error = security.validate_config_path(str(config_file))
            assert error is None

    def test_accepts_toml_extension(self, tmp_path: Path) -> None:
        """Test that .toml extension is accepted."""
        from token_audit.server import security

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        config_file = claude_dir / "config.toml"
        config_file.touch()

        with patch.object(
            security,
            "ALLOWED_CONFIG_DIRS",
            [tmp_path / ".claude", tmp_path / ".codex", tmp_path / ".gemini"],
        ):
            path, error = security.validate_config_path(str(config_file))
            assert error is None

    def test_rejects_empty_path(self) -> None:
        """Test that empty path is rejected."""
        path, error = validate_config_path("")
        assert path is None
        assert "Empty" in error


# =============================================================================
# Output Sanitization Tests
# =============================================================================


class TestSanitizePathForOutput:
    """Tests for path sanitization in outputs."""

    def test_abbreviates_home_directory(self) -> None:
        """Test that home directory is replaced with ~."""
        home = str(Path.home())
        full_path = f"{home}/.claude/settings.json"
        result = sanitize_path_for_output(full_path)
        assert result == "~/.claude/settings.json"

    def test_handles_path_object(self) -> None:
        """Test that Path objects are handled correctly."""
        path = Path.home() / ".claude" / "settings.json"
        result = sanitize_path_for_output(path)
        assert result == "~/.claude/settings.json"

    def test_masks_path_outside_home(self) -> None:
        """Test that paths outside home are masked."""
        result = sanitize_path_for_output("/etc/passwd")
        assert result == "[config path]"


class TestRedactCredentialPreview:
    """Tests for credential redaction with preview format."""

    def test_redacts_openai_api_key(self) -> None:
        """Test OpenAI API key is redacted to preview format.

        Pattern: sk-[a-zA-Z0-9]{48} (exactly 48 chars after sk-)
        """
        # Exactly 48 alphanumeric characters after sk-
        value = "sk-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKL"
        result = redact_credential_preview(value)
        assert "sk-abcd" in result  # First 7 chars preserved
        assert "..." in result  # Ellipsis indicates redaction
        # Original full key should not be present
        assert value not in result

    def test_redacts_anthropic_api_key(self) -> None:
        """Test Anthropic API key is redacted to preview format.

        Pattern: sk-ant-[a-zA-Z0-9_-]{32,} (32+ chars after sk-ant-)
        """
        # 32+ alphanumeric characters after sk-ant-
        # abcdefghijklmnopqrstuvwxyz123456 = 32 chars
        value = "sk-ant-abcdefghijklmnopqrstuvwxyz123456"
        result = redact_credential_preview(value)
        assert "sk-ant-abc" in result  # First 10 chars preserved
        assert "..." in result
        # Original full key should not be present
        assert value not in result

    def test_redacts_github_pat_classic(self) -> None:
        """Test GitHub PAT (classic) is redacted.

        Pattern: ghp_[a-zA-Z0-9]{36} (exactly 36 chars after ghp_)
        """
        # Exactly 36 alphanumeric characters after ghp_
        # abcdefghijklmnopqrstuvwxyz1234567890 = 36 chars
        value = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_credential_preview(value)
        assert "ghp_abc" in result  # First 7 chars preserved
        assert "..." in result

    def test_redacts_aws_access_key(self) -> None:
        """Test AWS Access Key ID is redacted.

        Pattern: AKIA[0-9A-Z]{16}
        """
        # AKIA followed by exactly 16 uppercase alphanumeric
        value = "AKIAIOSFODNN7EXAMPLE"
        result = redact_credential_preview(value)
        assert "AKIAIOSF" in result  # First 8 chars preserved
        assert "..." in result

    def test_preserves_non_sensitive_data(self) -> None:
        """Test that normal strings are unchanged."""
        value = "This is a normal configuration value"
        result = redact_credential_preview(value)
        assert result == value

    def test_handles_empty_string(self) -> None:
        """Test that empty string is handled."""
        result = redact_credential_preview("")
        assert result == ""

    def test_redacts_multiple_credentials(self) -> None:
        """Test that multiple credentials in one string are redacted."""
        # GitHub PAT (36 chars after ghp_)
        github_pat = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        value = f"token={github_pat}"
        result = redact_credential_preview(value)
        assert "ghp_abc" in result
        assert "..." in result


class TestSanitizeOutputDict:
    """Tests for dictionary output sanitization."""

    def test_redacts_credentials_in_dict(self) -> None:
        """Test credentials are redacted in dictionary values."""
        # Use GitHub PAT format (36 chars after ghp_)
        data = {"api_key": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"}
        result = sanitize_output_dict(data)
        assert "ghp_abc" in result["api_key"]
        assert "..." in result["api_key"]

    def test_sanitizes_nested_dict(self) -> None:
        """Test nested dictionaries are sanitized."""
        data = {"outer": {"inner": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"}}
        result = sanitize_output_dict(data)
        assert "..." in result["outer"]["inner"]

    def test_sanitizes_list_values(self) -> None:
        """Test list values are sanitized."""
        data = {"keys": ["ghp_abcdefghijklmnopqrstuvwxyz1234567890"]}
        result = sanitize_output_dict(data)
        assert "..." in result["keys"][0]


# =============================================================================
# Error Message Sanitization Tests
# =============================================================================


class TestSanitizeErrorMessage:
    """Tests for error message sanitization."""

    def test_abbreviates_home_path_in_error(self) -> None:
        """Test that home paths are abbreviated in error messages."""
        home = str(Path.home())
        message = f"File not found: {home}/.claude/settings.json"
        result = sanitize_error_message(message)
        assert "~/.claude/settings.json" in result
        assert home not in result

    def test_redacts_credentials_in_error(self) -> None:
        """Test that credentials are redacted in error messages."""
        # Use GitHub PAT format (36 chars after ghp_)
        message = "Invalid API key: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = sanitize_error_message(message)
        assert "ghp_abc" in result
        assert "..." in result


# =============================================================================
# Integration Tests
# =============================================================================


class TestAnalyzeConfigSecurity:
    """Integration tests for analyze_config security."""

    def test_analyze_config_rejects_traversal(self) -> None:
        """Test analyze_config rejects path traversal attempts."""
        from token_audit.server.tools import analyze_config
        from token_audit.server.schemas import ServerPlatform

        result = analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path="~/.claude/../../etc/passwd",
        )

        # Should return error, not actually read /etc/passwd
        assert result.config_path == "[path validation failed]"
        assert len(result.issues) == 1
        assert result.issues[0].category == "path_validation_error"
        assert ".." in result.issues[0].message

    def test_analyze_config_rejects_absolute_outside(self) -> None:
        """Test analyze_config rejects absolute paths outside allowed dirs."""
        from token_audit.server.tools import analyze_config
        from token_audit.server.schemas import ServerPlatform

        result = analyze_config(
            platform=ServerPlatform.CLAUDE_CODE,
            config_path="/etc/passwd",
        )

        assert result.config_path == "[path validation failed]"
        assert result.issues[0].category == "path_validation_error"
        assert "allowed directories" in result.issues[0].message
