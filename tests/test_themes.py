"""Tests for theme module."""

import pytest
from token_audit.display.themes import (
    CatppuccinMocha,
    CatppuccinLatte,
    HighContrastDark,
    HighContrastLight,
    get_theme,
    list_themes,
    THEMES,
    DEFAULT_DARK,
    DEFAULT_LIGHT,
)


class TestCatppuccinMocha:
    """Tests for Catppuccin Mocha theme."""

    def test_base_colors_are_hex(self):
        """All base colors should be valid hex codes."""
        theme = CatppuccinMocha()
        for attr in [
            "rosewater",
            "flamingo",
            "pink",
            "mauve",
            "red",
            "maroon",
            "peach",
            "yellow",
            "green",
            "teal",
            "sky",
            "sapphire",
            "blue",
            "lavender",
        ]:
            color = getattr(theme, attr)
            assert color.startswith("#"), f"{attr} should start with #"
            assert len(color) == 7, f"{attr} should be 7 chars (#rrggbb)"

    def test_text_colors_are_hex(self):
        """All text colors should be valid hex codes."""
        theme = CatppuccinMocha()
        for attr in [
            "text",
            "subtext1",
            "subtext0",
            "overlay2",
            "overlay1",
            "overlay0",
            "surface2",
            "surface1",
            "surface0",
            "base",
            "mantle",
            "crust",
        ]:
            color = getattr(theme, attr)
            assert color.startswith("#"), f"{attr} should start with #"
            assert len(color) == 7, f"{attr} should be 7 chars (#rrggbb)"

    def test_semantic_colors_defined(self):
        """All semantic colors should be defined."""
        theme = CatppuccinMocha()
        assert theme.header_border.startswith("#")
        assert theme.tokens_border.startswith("#")
        assert theme.mcp_border.startswith("#")
        assert theme.activity_border.startswith("#")
        assert theme.summary_border.startswith("#")
        assert theme.success.startswith("#")
        assert theme.warning.startswith("#")
        assert theme.error.startswith("#")
        assert theme.info.startswith("#")

    def test_is_frozen_dataclass(self):
        """Theme should be immutable."""
        theme = CatppuccinMocha()
        with pytest.raises(AttributeError):
            theme.red = "#ffffff"

    def test_semantic_colors_map_correctly(self):
        """Semantic colors should map to correct base colors."""
        theme = CatppuccinMocha()
        # Header uses sapphire
        assert theme.header_border == theme.sapphire
        # Tokens uses green
        assert theme.tokens_border == theme.green
        # MCP uses peach
        assert theme.mcp_border == theme.peach
        # Activity uses lavender
        assert theme.activity_border == theme.lavender


class TestCatppuccinLatte:
    """Tests for Catppuccin Latte theme."""

    def test_base_colors_are_hex(self):
        """All base colors should be valid hex codes."""
        theme = CatppuccinLatte()
        for attr in ["rosewater", "flamingo", "pink", "mauve", "red"]:
            color = getattr(theme, attr)
            assert color.startswith("#")
            assert len(color) == 7

    def test_different_from_mocha(self):
        """Latte colors should differ from Mocha."""
        mocha = CatppuccinMocha()
        latte = CatppuccinLatte()
        # Green should be different (Latte is darker for contrast on light bg)
        assert mocha.green != latte.green
        assert mocha.base != latte.base
        # Text colors are inverted (dark on light vs light on dark)
        assert mocha.text != latte.text

    def test_is_frozen_dataclass(self):
        """Theme should be immutable."""
        theme = CatppuccinLatte()
        with pytest.raises(AttributeError):
            theme.blue = "#ffffff"


class TestHighContrastDark:
    """Tests for High Contrast Dark theme."""

    def test_all_colors_are_hex(self):
        """All colors should be valid hex codes."""
        theme = HighContrastDark()
        assert theme.header_border.startswith("#")
        assert theme.primary_text == "#FFFFFF"
        assert theme.dim_text.startswith("#")

    def test_uses_high_contrast_values(self):
        """Should use high contrast colors for accessibility."""
        theme = HighContrastDark()
        # Primary text should be pure white
        assert theme.primary_text == "#FFFFFF"
        # Borders should be pure white
        assert theme.header_border == "#FFFFFF"
        # Success should be bright green
        assert theme.success == "#00FF00"

    def test_is_frozen_dataclass(self):
        """Theme should be immutable."""
        theme = HighContrastDark()
        with pytest.raises(AttributeError):
            theme.base = "#000000"


class TestHighContrastLight:
    """Tests for High Contrast Light theme."""

    def test_all_colors_are_hex(self):
        """All colors should be valid hex codes."""
        theme = HighContrastLight()
        assert theme.header_border == "#000000"
        assert theme.primary_text == "#000000"

    def test_different_from_dark(self):
        """Light theme should use dark colors (inverted from HC dark)."""
        dark = HighContrastDark()
        light = HighContrastLight()
        assert dark.primary_text != light.primary_text
        assert dark.success != light.success
        # Dark uses white, light uses black
        assert dark.primary_text == "#FFFFFF"
        assert light.primary_text == "#000000"

    def test_is_frozen_dataclass(self):
        """Theme should be immutable."""
        theme = HighContrastLight()
        with pytest.raises(AttributeError):
            theme.base = "#000000"


class TestGetTheme:
    """Tests for get_theme function."""

    def test_get_mocha(self):
        """Should return Mocha theme."""
        theme = get_theme("catppuccin-mocha")
        assert isinstance(theme, CatppuccinMocha)

    def test_get_latte(self):
        """Should return Latte theme."""
        theme = get_theme("catppuccin-latte")
        assert isinstance(theme, CatppuccinLatte)

    def test_get_high_contrast_dark(self):
        """Should return High Contrast Dark theme."""
        theme = get_theme("high-contrast-dark")
        assert isinstance(theme, HighContrastDark)

    def test_get_high_contrast_light(self):
        """Should return High Contrast Light theme."""
        theme = get_theme("high-contrast-light")
        assert isinstance(theme, HighContrastLight)

    def test_dark_alias(self):
        """'dark' should alias to Mocha."""
        theme = get_theme("dark")
        assert isinstance(theme, CatppuccinMocha)

    def test_light_alias(self):
        """'light' should alias to Latte."""
        theme = get_theme("light")
        assert isinstance(theme, CatppuccinLatte)

    def test_mocha_alias(self):
        """'mocha' should alias to Catppuccin Mocha."""
        theme = get_theme("mocha")
        assert isinstance(theme, CatppuccinMocha)

    def test_latte_alias(self):
        """'latte' should alias to Catppuccin Latte."""
        theme = get_theme("latte")
        assert isinstance(theme, CatppuccinLatte)

    def test_hc_dark_alias(self):
        """'hc-dark' should alias to High Contrast Dark."""
        theme = get_theme("hc-dark")
        assert isinstance(theme, HighContrastDark)

    def test_hc_light_alias(self):
        """'hc-light' should alias to High Contrast Light."""
        theme = get_theme("hc-light")
        assert isinstance(theme, HighContrastLight)

    def test_case_insensitive(self):
        """Theme lookup should be case-insensitive."""
        theme = get_theme("CATPPUCCIN-MOCHA")
        assert isinstance(theme, CatppuccinMocha)
        theme2 = get_theme("Dark")
        assert isinstance(theme2, CatppuccinMocha)

    def test_invalid_theme_raises(self):
        """Unknown theme should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown theme"):
            get_theme("nonexistent")

    def test_error_message_lists_valid_themes(self):
        """Error message should list valid theme names."""
        with pytest.raises(ValueError) as exc_info:
            get_theme("invalid")
        assert "dark" in str(exc_info.value)
        assert "light" in str(exc_info.value)


class TestListThemes:
    """Tests for list_themes function."""

    def test_returns_list(self):
        """Should return a list of strings."""
        themes = list_themes()
        assert isinstance(themes, list)
        assert all(isinstance(t, str) for t in themes)

    def test_includes_main_themes(self):
        """Should include main theme names."""
        themes = list_themes()
        assert "catppuccin-mocha" in themes
        assert "catppuccin-latte" in themes
        assert "dark" in themes
        assert "light" in themes

    def test_includes_high_contrast(self):
        """Should include high contrast themes."""
        themes = list_themes()
        assert "high-contrast-dark" in themes
        assert "high-contrast-light" in themes
        assert "hc-dark" in themes
        assert "hc-light" in themes

    def test_sorted(self):
        """Themes should be sorted alphabetically."""
        themes = list_themes()
        assert themes == sorted(themes)


class TestDefaults:
    """Tests for default theme constants."""

    def test_default_dark_exists(self):
        """DEFAULT_DARK should be a valid theme."""
        theme = get_theme(DEFAULT_DARK)
        assert theme is not None

    def test_default_light_exists(self):
        """DEFAULT_LIGHT should be a valid theme."""
        theme = get_theme(DEFAULT_LIGHT)
        assert theme is not None

    def test_defaults_are_catppuccin(self):
        """Defaults should be Catppuccin themes."""
        assert DEFAULT_DARK == "catppuccin-mocha"
        assert DEFAULT_LIGHT == "catppuccin-latte"
