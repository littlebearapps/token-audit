"""Tests for ASCII mode utilities."""

import pytest
from rich import box

from token_audit.display.ascii_mode import (
    is_ascii_mode,
    get_box_style,
    ascii_emoji,
    format_with_emoji,
    EMOJI_TO_ASCII,
)


class TestIsAsciiMode:
    """Tests for is_ascii_mode function."""

    def test_not_set(self, monkeypatch):
        """Should return False when env var not set."""
        monkeypatch.delenv("TOKEN_AUDIT_ASCII", raising=False)
        assert is_ascii_mode() is False

    def test_set_to_1(self, monkeypatch):
        """Should return True when set to '1'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert is_ascii_mode() is True

    def test_set_to_true(self, monkeypatch):
        """Should return True when set to 'true'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "true")
        assert is_ascii_mode() is True

    def test_set_to_yes(self, monkeypatch):
        """Should return True when set to 'yes'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "yes")
        assert is_ascii_mode() is True

    def test_set_to_on(self, monkeypatch):
        """Should return True when set to 'on'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "on")
        assert is_ascii_mode() is True

    def test_set_to_0(self, monkeypatch):
        """Should return False when set to '0'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "0")
        assert is_ascii_mode() is False

    def test_set_to_false(self, monkeypatch):
        """Should return False when set to 'false'."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "false")
        assert is_ascii_mode() is False

    def test_case_insensitive(self, monkeypatch):
        """Should be case insensitive."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "TRUE")
        assert is_ascii_mode() is True

    def test_empty_string(self, monkeypatch):
        """Empty string should return False."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "")
        assert is_ascii_mode() is False


class TestGetBoxStyle:
    """Tests for get_box_style function."""

    def test_unicode_default(self, monkeypatch):
        """Should return ROUNDED when ASCII mode disabled."""
        monkeypatch.delenv("TOKEN_AUDIT_ASCII", raising=False)
        assert get_box_style() == box.ROUNDED

    def test_ascii_mode(self, monkeypatch):
        """Should return ASCII when ASCII mode enabled."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert get_box_style() == box.ASCII


class TestAsciiEmoji:
    """Tests for ascii_emoji function."""

    def test_unicode_mode(self, monkeypatch):
        """Should return original emoji in Unicode mode."""
        monkeypatch.delenv("TOKEN_AUDIT_ASCII", raising=False)
        assert ascii_emoji("📌") == "📌"
        assert ascii_emoji("💰") == "💰"
        assert ascii_emoji("💸") == "💸"
        assert ascii_emoji("🌿") == "🌿"
        assert ascii_emoji("📁") == "📁"
        assert ascii_emoji("↺") == "↺"

    def test_ascii_mode_pin(self, monkeypatch):
        """Should convert pin emoji to [pin] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("📌") == "[pin]"

    def test_ascii_mode_savings(self, monkeypatch):
        """Should convert money bag emoji to [+$] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("💰") == "[+$]"

    def test_ascii_mode_cost(self, monkeypatch):
        """Should convert flying money emoji to [-$] in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("💸") == "[-$]"

    def test_ascii_mode_branch(self, monkeypatch):
        """Should convert herb emoji to 'branch:' in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("🌿") == "branch:"

    def test_ascii_mode_files(self, monkeypatch):
        """Should convert folder emoji to 'files:' in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("📁") == "files:"

    def test_ascii_mode_sync(self, monkeypatch):
        """Should convert sync symbol to '(sync)' in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("↺") == "(sync)"

    def test_unknown_emoji(self, monkeypatch):
        """Should return original for unknown emoji."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        assert ascii_emoji("🎉") == "🎉"


class TestFormatWithEmoji:
    """Tests for format_with_emoji function."""

    def test_unicode_mode(self, monkeypatch):
        """Should format with emoji in Unicode mode."""
        monkeypatch.delenv("TOKEN_AUDIT_ASCII", raising=False)
        result = format_with_emoji("📌", "zen-server")
        assert result == "📌 zen-server"

    def test_ascii_bracket_format(self, monkeypatch):
        """Should format with bracketed ASCII in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        result = format_with_emoji("📌", "zen-server")
        assert result == "[pin] zen-server"

    def test_ascii_colon_format(self, monkeypatch):
        """Should format with colon ASCII in ASCII mode."""
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")
        result = format_with_emoji("🌿", "main")
        assert result == "branch: main"


class TestEmojiMapping:
    """Tests for EMOJI_TO_ASCII mapping."""

    def test_all_used_emoji_mapped(self):
        """All emoji used in rich_display should have mappings."""
        required_emoji = ["📌", "💰", "💸", "🌿", "📁", "↺"]
        for emoji in required_emoji:
            assert emoji in EMOJI_TO_ASCII, f"Missing mapping for {emoji}"

    def test_mappings_are_ascii_safe(self):
        """All ASCII replacements should be ASCII-only characters."""
        for emoji, replacement in EMOJI_TO_ASCII.items():
            # Check that replacement contains only ASCII characters
            assert all(
                ord(c) < 128 for c in replacement
            ), f"Replacement for {emoji} contains non-ASCII: {replacement}"
