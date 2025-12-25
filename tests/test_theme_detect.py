"""Tests for theme detection utilities."""

import subprocess
from unittest.mock import patch, MagicMock
import pytest

from token_audit.display.theme_detect import (
    detect_terminal_mode,
    get_active_theme,
    is_ascii_mode,
    _detect_macos_mode,
)
from token_audit.display.themes import CatppuccinMocha, CatppuccinLatte


class TestDetectTerminalMode:
    """Tests for detect_terminal_mode function."""

    def test_explicit_dark_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=dark should return dark."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "dark")
        assert detect_terminal_mode() == "dark"

    def test_explicit_light_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=light should return light."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "light")
        assert detect_terminal_mode() == "light"

    def test_explicit_mocha_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=mocha should return dark."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "mocha")
        assert detect_terminal_mode() == "dark"

    def test_explicit_latte_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=latte should return light."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "latte")
        assert detect_terminal_mode() == "light"

    def test_explicit_catppuccin_mocha_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=catppuccin-mocha should return dark."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "catppuccin-mocha")
        assert detect_terminal_mode() == "dark"

    def test_explicit_catppuccin_latte_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=catppuccin-latte should return light."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "catppuccin-latte")
        assert detect_terminal_mode() == "light"

    def test_explicit_hc_dark_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=hc-dark should return dark."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "hc-dark")
        assert detect_terminal_mode() == "dark"

    def test_explicit_hc_light_env(self, monkeypatch):
        """TOKEN_AUDIT_THEME=hc-light should return light."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "hc-light")
        assert detect_terminal_mode() == "light"

    def test_colorfgbg_dark(self, monkeypatch):
        """COLORFGBG with dark background should return dark."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "15;0")  # white on black
        assert detect_terminal_mode() == "dark"

    def test_colorfgbg_dark_8(self, monkeypatch):
        """COLORFGBG with bg=8 (dark gray) should return dark."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "15;8")
        assert detect_terminal_mode() == "dark"

    def test_colorfgbg_light(self, monkeypatch):
        """COLORFGBG with light background should return light."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "0;15")  # black on white
        assert detect_terminal_mode() == "light"

    def test_colorfgbg_light_7(self, monkeypatch):
        """COLORFGBG with bg=7 (light gray) should return light."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "0;7")
        assert detect_terminal_mode() == "light"

    def test_colorfgbg_invalid(self, monkeypatch):
        """Invalid COLORFGBG should not crash."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "invalid")
        # Should fall through to other detection methods
        result = detect_terminal_mode()
        assert result in ("dark", "light", "unknown")

    def test_colorfgbg_single_value(self, monkeypatch):
        """COLORFGBG with single value should not crash."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.setenv("COLORFGBG", "15")
        result = detect_terminal_mode()
        assert result in ("dark", "light", "unknown")

    def test_no_env_returns_unknown_or_detected(self, monkeypatch):
        """Without env vars, should return detected or unknown."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.delenv("COLORFGBG", raising=False)
        result = detect_terminal_mode()
        assert result in ("dark", "light", "unknown")


class TestGetActiveTheme:
    """Tests for get_active_theme function."""

    def test_override_takes_precedence(self, monkeypatch):
        """CLI override should take precedence over everything."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "dark")
        theme = get_active_theme(override="light")
        assert isinstance(theme, CatppuccinLatte)

    def test_env_takes_precedence_over_config(self, monkeypatch):
        """Environment variable should override config."""
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "dark")
        theme = get_active_theme(config_theme="light")
        assert isinstance(theme, CatppuccinMocha)

    def test_config_used_when_no_env(self, monkeypatch):
        """Config theme should be used when no env var."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.delenv("COLORFGBG", raising=False)
        theme = get_active_theme(config_theme="catppuccin-latte")
        assert isinstance(theme, CatppuccinLatte)

    def test_auto_override_triggers_detection(self, monkeypatch):
        """override='auto' should trigger auto-detection."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.delenv("COLORFGBG", raising=False)
        theme = get_active_theme(override="auto")
        # Should return some valid theme
        assert hasattr(theme, "header_border")

    def test_defaults_to_dark(self, monkeypatch):
        """With no detection info, should default to dark."""
        monkeypatch.delenv("TOKEN_AUDIT_THEME", raising=False)
        monkeypatch.delenv("COLORFGBG", raising=False)
        # Mock macOS detection to return None
        with patch("token_audit.display.theme_detect._is_macos", return_value=False):
            theme = get_active_theme()
            assert isinstance(theme, CatppuccinMocha)

    def test_returns_theme_colors(self):
        """Should return a valid ThemeColors object."""
        theme = get_active_theme(override="dark")
        assert hasattr(theme, "header_border")
        assert hasattr(theme, "success")
        assert hasattr(theme, "warning")
        assert hasattr(theme, "error")


class TestMacOSDetection:
    """Tests for macOS-specific detection."""

    def test_macos_dark_mode(self):
        """Should detect macOS dark mode."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Dark\n"

        with patch("subprocess.run", return_value=mock_result):
            result = _detect_macos_mode()
            assert result == "dark"

    def test_macos_light_mode(self):
        """Should detect macOS light mode (no AppleInterfaceStyle)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""  # Light mode returns empty

        with patch("subprocess.run", return_value=mock_result):
            result = _detect_macos_mode()
            assert result == "light"

    def test_macos_detection_timeout(self):
        """Should handle detection timeout gracefully."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
            result = _detect_macos_mode()
            assert result is None

    def test_macos_detection_file_not_found(self):
        """Should handle missing defaults command gracefully."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = _detect_macos_mode()
            assert result is None

    def test_macos_detection_os_error(self):
        """Should handle OS errors gracefully."""
        with patch("subprocess.run", side_effect=OSError()):
            result = _detect_macos_mode()
            assert result is None


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
