"""Tests for NO_COLOR standard compliance.

Verifies that token-audit respects the NO_COLOR environment variable
per https://no-color.org/ specification.
"""

import pytest


class TestNoColorCompliance:
    """Tests for NO_COLOR standard compliance via Rich library."""

    def test_no_color_disables_colors(self, monkeypatch):
        """NO_COLOR=1 should disable colors in Rich Console."""
        monkeypatch.setenv("NO_COLOR", "1")

        # Import after setting env var to ensure it's picked up
        from rich.console import Console

        console = Console()

        assert console.no_color is True
        assert console.color_system is None

    def test_no_color_with_any_non_empty_value(self, monkeypatch):
        """NO_COLOR should work with any non-empty value."""
        monkeypatch.setenv("NO_COLOR", "anything")

        from rich.console import Console

        console = Console()

        assert console.no_color is True

    def test_no_color_with_true_value(self, monkeypatch):
        """NO_COLOR=true should disable colors."""
        monkeypatch.setenv("NO_COLOR", "true")

        from rich.console import Console

        console = Console()

        assert console.no_color is True

    def test_empty_no_color_ignored(self, monkeypatch):
        """Empty NO_COLOR should be ignored per spec."""
        monkeypatch.setenv("NO_COLOR", "")

        from rich.console import Console

        console = Console()

        # Empty string should NOT disable color
        assert console.no_color is False

    def test_no_color_not_set(self, monkeypatch):
        """Without NO_COLOR, colors should be enabled."""
        monkeypatch.delenv("NO_COLOR", raising=False)

        from rich.console import Console

        console = Console()

        assert console.no_color is False

    def test_rich_display_respects_no_color(self, monkeypatch):
        """RichDisplay should use Rich Console which respects NO_COLOR."""
        monkeypatch.setenv("NO_COLOR", "1")

        from token_audit.display.rich_display import RichDisplay

        display = RichDisplay()

        # RichDisplay uses a Console internally which should respect NO_COLOR
        assert display.console.no_color is True


class TestNoColorWithTheme:
    """Tests for NO_COLOR interaction with theme settings."""

    def test_no_color_overrides_theme(self, monkeypatch):
        """NO_COLOR should take precedence over theme setting."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "dark")

        from rich.console import Console

        console = Console()

        # NO_COLOR should still disable colors regardless of theme
        assert console.no_color is True
        assert console.color_system is None

    def test_theme_works_without_no_color(self, monkeypatch):
        """Theme should work normally when NO_COLOR is not set."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TOKEN_AUDIT_THEME", "dark")

        from rich.console import Console

        console = Console()

        # Colors should be enabled
        assert console.no_color is False


class TestNoColorWithAsciiMode:
    """Tests for NO_COLOR interaction with ASCII mode."""

    def test_no_color_with_ascii_mode(self, monkeypatch):
        """NO_COLOR and TOKEN_AUDIT_ASCII should work together."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setenv("TOKEN_AUDIT_ASCII", "1")

        from rich.console import Console
        from rich import box

        from token_audit.display.ascii_mode import is_ascii_mode, get_box_style

        console = Console()

        # Both should be active
        assert console.no_color is True
        assert is_ascii_mode() is True
        assert get_box_style() == box.ASCII
