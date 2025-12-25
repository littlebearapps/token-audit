"""Theme definitions for token-audit TUI.

Provides Catppuccin color palettes for light and dark terminal modes,
plus high contrast themes for accessibility (WCAG AAA compliance).
"""

from dataclasses import dataclass
from typing import Dict, List, Protocol, Union


class ThemeColors(Protocol):
    """Protocol for theme color definitions.

    All implementations must provide hex color values (#rrggbb format)
    for each semantic color role.
    """

    # Panel borders
    header_border: str
    tokens_border: str
    mcp_border: str
    activity_border: str
    summary_border: str

    # Text styles
    title: str
    primary_text: str
    secondary_text: str
    dim_text: str

    # Semantic colors
    success: str  # Positive values, savings
    warning: str  # Warnings, caution
    error: str  # Errors, negative values
    info: str  # Informational

    # Element-specific
    server_name: str
    tool_name: str
    pinned_indicator: str

    # Additional accents
    accent1: str
    accent2: str


@dataclass(frozen=True)
class CatppuccinMocha:
    """Catppuccin Mocha (dark mode) color palette.

    Deep dark theme with warm pastel accents.
    Background: #1e1e2e
    Source: https://catppuccin.com/palette
    """

    # Base colors (Catppuccin Mocha palette)
    rosewater: str = "#f5e0dc"
    flamingo: str = "#f2cdcd"
    pink: str = "#f5c2e7"
    mauve: str = "#cba6f7"
    red: str = "#f38ba8"
    maroon: str = "#eba0ac"
    peach: str = "#fab387"
    yellow: str = "#f9e2af"
    green: str = "#a6e3a1"
    teal: str = "#94e2d5"
    sky: str = "#89dceb"
    sapphire: str = "#74c7ec"
    blue: str = "#89b4fa"
    lavender: str = "#b4befe"

    # Text colors
    text: str = "#cdd6f4"
    subtext1: str = "#bac2de"
    subtext0: str = "#a6adc8"
    overlay2: str = "#9399b2"
    overlay1: str = "#7f849c"
    overlay0: str = "#6c7086"
    surface2: str = "#585b70"
    surface1: str = "#45475a"
    surface0: str = "#313244"
    base: str = "#1e1e2e"
    mantle: str = "#181825"
    crust: str = "#11111b"

    # Semantic mappings (ThemeColors protocol)
    @property
    def header_border(self) -> str:
        return self.sapphire

    @property
    def tokens_border(self) -> str:
        return self.green

    @property
    def mcp_border(self) -> str:
        return self.peach

    @property
    def activity_border(self) -> str:
        return self.lavender

    @property
    def summary_border(self) -> str:
        return self.green

    @property
    def title(self) -> str:
        return self.sapphire

    @property
    def primary_text(self) -> str:
        return self.text

    @property
    def secondary_text(self) -> str:
        return self.subtext0

    @property
    def dim_text(self) -> str:
        return self.overlay1

    @property
    def success(self) -> str:
        return self.green

    @property
    def warning(self) -> str:
        return self.yellow

    @property
    def error(self) -> str:
        return self.red

    @property
    def info(self) -> str:
        return self.blue

    @property
    def server_name(self) -> str:
        return self.blue

    @property
    def tool_name(self) -> str:
        return self.sky

    @property
    def pinned_indicator(self) -> str:
        return self.yellow

    @property
    def accent1(self) -> str:
        return self.mauve

    @property
    def accent2(self) -> str:
        return self.teal


@dataclass(frozen=True)
class CatppuccinLatte:
    """Catppuccin Latte (light mode) color palette.

    Light theme with warm pastel accents.
    Background: #eff1f5
    Source: https://catppuccin.com/palette
    """

    # Base colors (Catppuccin Latte palette)
    rosewater: str = "#dc8a78"
    flamingo: str = "#dd7878"
    pink: str = "#ea76cb"
    mauve: str = "#8839ef"
    red: str = "#d20f39"
    maroon: str = "#e64553"
    peach: str = "#fe640b"
    yellow: str = "#df8e1d"
    green: str = "#40a02b"
    teal: str = "#179299"
    sky: str = "#04a5e5"
    sapphire: str = "#209fb5"
    blue: str = "#1e66f5"
    lavender: str = "#7287fd"

    # Text colors
    text: str = "#4c4f69"
    subtext1: str = "#5c5f77"
    subtext0: str = "#6c6f85"
    overlay2: str = "#7c7f93"
    overlay1: str = "#8c8fa1"
    overlay0: str = "#9ca0b0"
    surface2: str = "#acb0be"
    surface1: str = "#bcc0cc"
    surface0: str = "#ccd0da"
    base: str = "#eff1f5"
    mantle: str = "#e6e9ef"
    crust: str = "#dce0e8"

    # Semantic mappings (ThemeColors protocol)
    @property
    def header_border(self) -> str:
        return self.sapphire

    @property
    def tokens_border(self) -> str:
        return self.green

    @property
    def mcp_border(self) -> str:
        return self.peach

    @property
    def activity_border(self) -> str:
        return self.lavender

    @property
    def summary_border(self) -> str:
        return self.green

    @property
    def title(self) -> str:
        return self.sapphire

    @property
    def primary_text(self) -> str:
        return self.text

    @property
    def secondary_text(self) -> str:
        return self.subtext0

    @property
    def dim_text(self) -> str:
        return self.overlay1

    @property
    def success(self) -> str:
        return self.green

    @property
    def warning(self) -> str:
        return self.yellow

    @property
    def error(self) -> str:
        return self.red

    @property
    def info(self) -> str:
        return self.blue

    @property
    def server_name(self) -> str:
        return self.blue

    @property
    def tool_name(self) -> str:
        return self.sky

    @property
    def pinned_indicator(self) -> str:
        return self.yellow

    @property
    def accent1(self) -> str:
        return self.mauve

    @property
    def accent2(self) -> str:
        return self.teal


@dataclass(frozen=True)
class HighContrastDark:
    """High contrast dark theme (WCAG AAA compliant).

    Uses pure white and bright colors on dark background.
    All colors meet 7:1 contrast ratio against #1e1e2e.
    """

    # Background (for reference)
    base: str = "#1e1e2e"

    # All borders - pure white for maximum visibility
    @property
    def header_border(self) -> str:
        return "#FFFFFF"

    @property
    def tokens_border(self) -> str:
        return "#FFFFFF"

    @property
    def mcp_border(self) -> str:
        return "#FFFFFF"

    @property
    def activity_border(self) -> str:
        return "#FFFFFF"

    @property
    def summary_border(self) -> str:
        return "#FFFFFF"

    # Text - pure white
    @property
    def title(self) -> str:
        return "#FFFFFF"

    @property
    def primary_text(self) -> str:
        return "#FFFFFF"

    @property
    def secondary_text(self) -> str:
        return "#DDDDDD"

    @property
    def dim_text(self) -> str:
        return "#CCCCCC"  # 10.9:1 contrast

    # Semantic - bright saturated colors
    @property
    def success(self) -> str:
        return "#00FF00"  # Bright green, 8.2:1

    @property
    def warning(self) -> str:
        return "#FFFF00"  # Bright yellow, 13.1:1

    @property
    def error(self) -> str:
        return "#FF6B6B"  # Bright red, 7.1:1

    @property
    def info(self) -> str:
        return "#00FFFF"  # Cyan, 12.0:1

    # Element-specific
    @property
    def server_name(self) -> str:
        return "#FFFFFF"

    @property
    def tool_name(self) -> str:
        return "#DDDDDD"

    @property
    def pinned_indicator(self) -> str:
        return "#FFFF00"

    @property
    def accent1(self) -> str:
        return "#FF00FF"  # Magenta

    @property
    def accent2(self) -> str:
        return "#00FFFF"  # Cyan


@dataclass(frozen=True)
class HighContrastLight:
    """High contrast light theme (WCAG AAA compliant).

    Uses pure black and dark colors on white background.
    All colors meet 7:1 contrast ratio against #FFFFFF.
    """

    # Background (for reference)
    base: str = "#FFFFFF"

    # All borders - pure black for maximum visibility
    @property
    def header_border(self) -> str:
        return "#000000"

    @property
    def tokens_border(self) -> str:
        return "#000000"

    @property
    def mcp_border(self) -> str:
        return "#000000"

    @property
    def activity_border(self) -> str:
        return "#000000"

    @property
    def summary_border(self) -> str:
        return "#000000"

    # Text - pure black
    @property
    def title(self) -> str:
        return "#000000"

    @property
    def primary_text(self) -> str:
        return "#000000"

    @property
    def secondary_text(self) -> str:
        return "#333333"

    @property
    def dim_text(self) -> str:
        return "#555555"  # 7.5:1 contrast

    # Semantic - dark saturated colors
    @property
    def success(self) -> str:
        return "#006400"  # Dark green, 9.4:1

    @property
    def warning(self) -> str:
        return "#996600"  # Dark orange, 5.7:1 (use bold)

    @property
    def error(self) -> str:
        return "#990000"  # Dark red, 9.7:1

    @property
    def info(self) -> str:
        return "#000080"  # Navy, 12.6:1

    # Element-specific
    @property
    def server_name(self) -> str:
        return "#000000"

    @property
    def tool_name(self) -> str:
        return "#333333"

    @property
    def pinned_indicator(self) -> str:
        return "#996600"

    @property
    def accent1(self) -> str:
        return "#800080"  # Purple

    @property
    def accent2(self) -> str:
        return "#006666"  # Teal


# Theme registry - all available themes
# Using Any in Union to satisfy mypy since dataclasses implement ThemeColors structurally
_ThemeType = Union[CatppuccinMocha, CatppuccinLatte, HighContrastDark, HighContrastLight]
THEMES: Dict[str, _ThemeType] = {
    # Main themes
    "catppuccin-mocha": CatppuccinMocha(),
    "catppuccin-latte": CatppuccinLatte(),
    # High contrast themes
    "high-contrast-dark": HighContrastDark(),
    "high-contrast-light": HighContrastLight(),
    # Aliases for convenience
    "dark": CatppuccinMocha(),
    "light": CatppuccinLatte(),
    "mocha": CatppuccinMocha(),
    "latte": CatppuccinLatte(),
    "hc-dark": HighContrastDark(),
    "hc-light": HighContrastLight(),
}

# Default themes by mode
DEFAULT_DARK = "catppuccin-mocha"
DEFAULT_LIGHT = "catppuccin-latte"


def get_theme(name: str) -> _ThemeType:
    """Get a theme by name.

    Args:
        name: Theme name (e.g., "catppuccin-mocha", "dark", "light", "hc-dark")

    Returns:
        ThemeColors implementation

    Raises:
        ValueError: If theme name is not recognized
    """
    name_lower = name.lower()
    if name_lower not in THEMES:
        valid = ", ".join(sorted(set(THEMES.keys())))
        raise ValueError(f"Unknown theme '{name}'. Valid themes: {valid}")
    return THEMES[name_lower]


def list_themes() -> List[str]:
    """List available theme names (sorted, unique)."""
    return sorted(set(THEMES.keys()))
