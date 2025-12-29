"""
Session Browser - Interactive TUI for exploring past sessions.

Provides list view with filtering/sorting and detail view for individual sessions.
Uses Rich's Live display with keyboard input for interactive navigation.

v0.7.0 - task-105.1, task-105.3, task-105.4
v0.8.0 - task-106.7 (Comparison), task-106.9 (Notifications)
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple, Union

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import __version__
from ..preferences import PreferencesManager
from ..smell_aggregator import SmellAggregator
from ..storage import SUPPORTED_PLATFORMS, Platform, StorageManager
from .ascii_mode import (
    accuracy_indicator,
    ascii_emoji,
    compute_percentile,
    generate_histogram,
    get_box_style,
)
from .keyboard import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_ENTER,
    KEY_ESC,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_SHIFT_TAB,
    KEY_TAB,
    KEY_UP,
    check_keypress,
    disable_raw_mode,
    enable_raw_mode,
)
from .rich_display import Notification
from .theme_detect import get_active_theme
from .themes import THEMES, _ThemeType


class BrowserMode(Enum):
    """Browser display modes."""

    # v1.0.0 - New primary views
    DASHBOARD = auto()  # Default landing view with overview
    LIVE = auto()  # Real-time session monitoring
    RECOMMENDATIONS = auto()  # Actionable recommendations panel
    COMMAND_PALETTE = auto()  # Quick navigation (: key)

    # Existing views
    LIST = auto()
    DETAIL = auto()
    SEARCH = auto()
    SORT_MENU = auto()  # v0.7.0 - task-105.4
    HELP = auto()  # v0.7.0 - task-105.3
    TOOL_DETAIL = auto()  # v0.7.0 - task-105.7
    TIMELINE = auto()  # v0.8.0 - task-106.8
    COMPARISON = auto()  # v0.8.0 - task-106.7

    # v1.0.3 - New views and modals
    ANALYTICS = auto()  # Time-series aggregation (daily/weekly/monthly)
    SMELL_TRENDS = auto()  # Cross-session smell pattern analysis (key 6)
    PINNED_SERVERS = auto()  # Pinned servers view (key 7) - task-233.8
    START_TRACKING_MODAL = auto()  # Platform selection for new tracking
    DELETE_CONFIRM_MODAL = auto()  # Session deletion confirmation
    EXPORT_MODAL = auto()  # Export format selection
    DATE_FILTER_MODAL = auto()  # Date range filter input
    ADD_SERVER_MODAL = auto()  # Add pinned server selection - task-233.8

    # v1.0.4 - Bucket configuration (task-247.13)
    BUCKET_CONFIG = auto()  # Bucket classification configuration view (key 8)
    ADD_PATTERN_MODAL = auto()  # Add pattern to bucket modal


# Sort options: (display_label, sort_key, reverse)
SORT_OPTIONS: List[tuple[str, str, bool]] = [
    ("Date (newest)", "date", True),
    ("Date (oldest)", "date", False),
    ("Cost (highest)", "cost", True),
    ("Cost (lowest)", "cost", False),
    ("Tokens (most)", "tokens", True),
    ("Tokens (least)", "tokens", False),
    ("Duration (longest)", "duration", True),
    ("Duration (shortest)", "duration", False),
    ("Platform (A-Z)", "platform", False),
]


@dataclass
class KeybindingInfo:
    """Keybinding definition for help overlay."""

    keys: str
    description: str
    modes: tuple[BrowserMode, ...]


# Keybinding registry for help overlay - v0.7.0 task-105.3
KEYBINDINGS: List[KeybindingInfo] = [
    KeybindingInfo(
        "q", "Quit browser", (BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.DASHBOARD)
    ),
    KeybindingInfo(
        "?", "Show/hide help", (BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.DASHBOARD)
    ),
    KeybindingInfo("r", "Refresh sessions", (BrowserMode.LIST, BrowserMode.DASHBOARD)),
    KeybindingInfo(
        "t", "Toggle theme", (BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.DASHBOARD)
    ),
    KeybindingInfo(
        "j/k", "Move up/down", (BrowserMode.LIST, BrowserMode.SORT_MENU, BrowserMode.DASHBOARD)
    ),
    KeybindingInfo(
        "Enter", "View/Select", (BrowserMode.LIST, BrowserMode.SORT_MENU, BrowserMode.DASHBOARD)
    ),
    KeybindingInfo(
        "Esc",
        "Back/Cancel",
        (
            BrowserMode.DETAIL,
            BrowserMode.SORT_MENU,
            BrowserMode.HELP,
            BrowserMode.TOOL_DETAIL,
            BrowserMode.TIMELINE,
            BrowserMode.LIVE,
            BrowserMode.RECOMMENDATIONS,
            BrowserMode.COMMAND_PALETTE,
        ),
    ),
    KeybindingInfo("p", "Pin/unpin session", (BrowserMode.LIST,)),
    KeybindingInfo("P", "Unpin all sessions", (BrowserMode.LIST,)),
    KeybindingInfo("s", "Sort menu", (BrowserMode.LIST,)),
    KeybindingInfo("f", "Cycle platform filter", (BrowserMode.LIST,)),
    KeybindingInfo("/", "Search sessions", (BrowserMode.LIST,)),
    KeybindingInfo("Space", "Select for compare", (BrowserMode.LIST,)),
    KeybindingInfo("c", "Compare selected", (BrowserMode.LIST,)),
    # v1.0.3 - task-233.6: Delete session
    KeybindingInfo("D", "Delete session", (BrowserMode.LIST,)),
    # v0.7.0 - task-105.7: Tool detail view
    KeybindingInfo("d", "Drill into tool", (BrowserMode.DETAIL,)),
    # v0.7.0 - task-105.8: AI export on all screens
    KeybindingInfo(
        "a",
        "AI export (selected)",
        (
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.TOOL_DETAIL,
            BrowserMode.TIMELINE,
            BrowserMode.DASHBOARD,
            BrowserMode.RECOMMENDATIONS,
        ),
    ),
    # v0.8.0 - task-106.8: Timeline view
    KeybindingInfo("T", "Timeline view", (BrowserMode.DETAIL,)),
    # v1.0.0 - Hotkeys for quick navigation
    KeybindingInfo(
        "1",
        "Dashboard",
        (BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.RECOMMENDATIONS, BrowserMode.LIVE),
    ),
    KeybindingInfo(
        "2",
        "Sessions list",
        (BrowserMode.DASHBOARD, BrowserMode.DETAIL, BrowserMode.RECOMMENDATIONS, BrowserMode.LIVE),
    ),
    KeybindingInfo(
        "3",
        "Recommendations",
        (BrowserMode.DASHBOARD, BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.LIVE),
    ),
    KeybindingInfo(
        "4",
        "Live monitor",
        (BrowserMode.DASHBOARD, BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.RECOMMENDATIONS),
    ),
    KeybindingInfo(
        ":", "Command palette", (BrowserMode.DASHBOARD, BrowserMode.LIST, BrowserMode.DETAIL)
    ),
    KeybindingInfo("l", "Live monitor", (BrowserMode.DASHBOARD,)),
    # v1.0.3 - New views and actions
    KeybindingInfo(
        "5",
        "Analytics",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.RECOMMENDATIONS,
            BrowserMode.LIVE,
        ),
    ),
    KeybindingInfo(
        "6",
        "Smell Trends",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.RECOMMENDATIONS,
            BrowserMode.LIVE,
            BrowserMode.ANALYTICS,
        ),
    ),
    # v1.0.3 - task-233.8: Pinned Servers view
    KeybindingInfo(
        "7",
        "Pinned Servers",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.RECOMMENDATIONS,
            BrowserMode.LIVE,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
        ),
    ),
    KeybindingInfo(
        "n",
        "Start tracking",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.ANALYTICS,
            BrowserMode.RECOMMENDATIONS,
        ),
    ),
    KeybindingInfo(
        "d",
        "Daily view",
        (BrowserMode.ANALYTICS,),
    ),
    KeybindingInfo(
        "w",
        "Weekly view",
        (BrowserMode.ANALYTICS,),
    ),
    KeybindingInfo(
        "m",
        "Monthly view",
        (BrowserMode.ANALYTICS,),
    ),
    KeybindingInfo(
        "g",
        "Group by project",
        (BrowserMode.ANALYTICS,),
    ),
    # v1.0.3 - task-233.10: Date range filter
    KeybindingInfo(
        "R",
        "Date range filter",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
        ),
    ),
    # v1.0.3 - task-233.9: Export functionality
    KeybindingInfo(
        "e",
        "Export CSV",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
            BrowserMode.PINNED_SERVERS,
        ),
    ),
    KeybindingInfo(
        "x",
        "Export JSON",
        (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
            BrowserMode.PINNED_SERVERS,
        ),
    ),
]


@dataclass
class SessionEntry:
    """Summary of a session for list display."""

    path: Path
    session_date: datetime  # Full datetime for display with time
    platform: str
    project: str
    duration_seconds: float
    total_tokens: int
    cost_estimate: float
    tool_count: int
    smell_count: int = 0
    model_name: str = ""
    is_pinned: bool = False  # v0.7.0 - task-105.4
    accuracy_level: str = "exact"  # v0.7.0 - task-105.5
    is_live: bool = False  # v1.0.0 - active session marker


@dataclass
class BrowserState:
    """Mutable state for the session browser."""

    mode: BrowserMode = BrowserMode.DASHBOARD  # v1.0.0: Start at dashboard
    sessions: List[SessionEntry] = field(default_factory=list)
    selected_index: int = 0
    scroll_offset: int = 0
    filter_platform: Optional[Platform] = None
    search_query: str = ""
    sort_key: str = "date"  # date, cost, tokens, duration, platform
    sort_reverse: bool = True  # newest/highest first
    sort_menu_index: int = 0  # v0.7.0 - task-105.4
    selected_tool: Optional[tuple[str, str]] = None  # v0.7.0 - task-105.7 (server, tool)
    selected_sessions: Set[int] = field(default_factory=set)  # v0.8.0 - task-106.7 (comparison)
    # v1.0.0 - Command palette state
    command_input: str = ""
    command_menu_index: int = 0
    # v1.0.0 - Compact mode (auto-detect or manual)
    compact_mode: Optional[bool] = None  # None = auto-detect
    # v1.0.0 - task-224.3: Navigation breadcrumb
    navigation_history: List[BrowserMode] = field(default_factory=list)
    current_session_id: Optional[str] = None  # Session context for breadcrumb
    # v1.0.0 - task-224.10: Refresh/staleness indicator
    last_refresh: Optional[datetime] = None
    is_refreshing: bool = False
    # v1.0.3 - Analytics view state
    analytics_period: str = "daily"  # daily, weekly, monthly
    analytics_group_by_project: bool = False
    analytics_selected_index: int = 0  # Selected row in analytics table
    date_filter_start: Optional[datetime] = None  # Date range filter
    date_filter_end: Optional[datetime] = None
    # v1.0.3 - Start tracking modal state
    start_tracking_platform_index: int = 0  # 0=Claude, 1=Codex, 2=Gemini
    start_tracking_from_start: bool = True  # Include prior messages
    # v1.0.3 - Delete session modal state
    delete_target_session: Optional["SessionEntry"] = None
    # v1.0.3 - Smell Trends view state
    smell_trends_selected_index: int = 0
    smell_trends_days: int = 30  # Default filter period (7, 14, 30, 90)
    smell_trends_data: Optional[Any] = None  # SmellAggregationResult
    # v1.0.3 - Date filter modal state (task-233.10)
    date_filter_preset_index: int = 2  # Default to "Last 7 days" (index 2)
    # v1.0.3 - Pinned Servers view state (task-233.8)
    pinned_servers_selected_index: int = 0
    pinned_servers_data: Optional[List[Any]] = None  # List of pinned server info dicts
    available_servers_for_add: Optional[List[str]] = None  # Unpinned servers for add modal
    # v1.0.3 - Concurrency handling (task-233.14)
    file_mtimes: Dict[str, float] = field(default_factory=dict)  # path -> mtime
    external_change_detected: bool = False
    last_mtime_check: Optional[float] = None  # time.time() value
    # v1.0.4 - Bucket configuration view state (task-247.13)
    bucket_config: Optional[Any] = None  # BucketConfig instance
    bucket_config_section: int = 0  # 0=state_serialization, 1=tool_discovery, 2=thresholds
    bucket_config_item_index: int = 0  # Selected item within section
    bucket_config_modified: bool = False  # Track unsaved changes
    bucket_add_pattern_input: str = ""  # Pattern input for add modal
    bucket_add_pattern_bucket: str = "state_serialization"  # Target bucket for add


@dataclass
class ToolDetailData:
    """Computed metrics for tool detail view (v0.7.0 - task-105.7)."""

    server: str
    tool_name: str
    call_count: int
    total_tokens: int
    avg_tokens: float
    p50_tokens: int
    p95_tokens: int
    min_tokens: int
    max_tokens: int
    histogram: str  # Unicode block characters
    smells: List[Dict[str, Any]]
    static_cost_tokens: int
    call_history: List[Dict[str, Any]]  # For AI export


@dataclass
class TimelineBucket:
    """A time bucket for timeline visualization (v0.8.0 - task-106.8)."""

    bucket_index: int  # 0-based index
    start_seconds: float  # Start time in seconds from session start
    duration_seconds: float  # Bucket duration
    mcp_tokens: int = 0  # Tokens from MCP tool calls
    builtin_tokens: int = 0  # Tokens from built-in tools
    total_tokens: int = 0  # Total tokens in this bucket
    call_count: int = 0  # Number of calls in this bucket
    is_spike: bool = False  # Whether this bucket is a spike
    spike_magnitude: float = 0.0  # Z-score for spike detection


@dataclass
class TimelineData:
    """Computed timeline data for visualization (v0.8.0 - task-106.8)."""

    session_date: datetime
    duration_seconds: float
    bucket_duration_seconds: float  # How long each bucket represents
    buckets: List[TimelineBucket] = field(default_factory=list)
    spikes: List[TimelineBucket] = field(default_factory=list)
    max_tokens_per_bucket: int = 0
    avg_tokens_per_bucket: float = 0.0
    total_tokens: int = 0
    total_mcp_tokens: int = 0
    total_builtin_tokens: int = 0


@dataclass
class ComparisonData:
    """Computed comparison data for multi-session analysis (v0.8.0 - task-106.7)."""

    # Session entries and their full data
    baseline: "SessionEntry"
    baseline_data: Dict[str, Any]
    comparisons: List[tuple["SessionEntry", Dict[str, Any]]]

    # Computed deltas (each element corresponds to a comparison session)
    token_deltas: List[int]  # total_tokens - baseline
    mcp_share_deltas: List[float]  # mcp% - baseline%

    # Top tool changes: (tool_name, delta_tokens) sorted by absolute value
    tool_changes: List[tuple[str, int]]

    # Smell presence matrix: {pattern: [baseline_has, comp1_has, comp2_has, ...]}
    smell_matrix: Dict[str, List[bool]]


class SessionBrowser:
    """Interactive session browser using Rich.

    Provides keyboard-driven navigation through past sessions with:
    - List view with sorting and filtering
    - Detail view for individual sessions
    - Search by project name or session ID
    """

    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        theme: Optional[str] = None,
        debug: bool = False,
    ) -> None:
        """Initialize the session browser.

        Args:
            storage: StorageManager instance (created if not provided)
            theme: Theme name override (default: auto-detect)
            debug: Enable verbose key/event logging for debugging
        """
        self.storage = storage or StorageManager()
        self.console = Console()
        self.prefs = PreferencesManager()  # v0.7.0 - task-105.4
        self._theme_name = theme or "auto"
        self.theme: _ThemeType = get_active_theme(override=theme)
        self.box_style: box.Box = get_box_style()
        self.state = BrowserState()
        self.visible_rows = 25  # Sessions visible without scrolling
        self._detail_data: Optional[Dict[str, Any]] = None
        self._timeline_data: Optional[TimelineData] = None  # v0.8.0 - task-106.8
        self._comparison_data: Optional[ComparisonData] = None  # v0.8.0 - task-106.7
        self._notification: Optional[Notification] = None  # v0.8.0 - task-106.9
        self._is_new_user: bool = False  # v1.0.0 - task-224.5: Track for onboarding hints
        self._debug = debug  # v1.0.3 - task-240: Debug logging for key events
        self._load_preferences()  # Apply saved preferences

    def _load_preferences(self) -> None:
        """Load user preferences and apply to state."""
        prefs = self.prefs.load()
        self.state.sort_key = prefs.last_sort.key
        self.state.sort_reverse = prefs.last_sort.reverse
        if prefs.last_filter_platform:
            # Convert string back to Platform enum if valid
            for platform in SUPPORTED_PLATFORMS:
                if platform == prefs.last_filter_platform:
                    self.state.filter_platform = platform
                    break

    # v1.0.0 - task-224.3: Navigation breadcrumb helpers
    def _navigate_to(self, new_mode: BrowserMode, session_id: Optional[str] = None) -> None:
        """Navigate to a new mode while tracking history.

        Args:
            new_mode: The mode to navigate to
            session_id: Optional session context for detail views
        """
        # Push current mode to history if navigating forward
        current = self.state.mode
        if current not in (BrowserMode.SEARCH, BrowserMode.SORT_MENU, BrowserMode.HELP) and (
            not self.state.navigation_history or self.state.navigation_history[-1] != current
        ):
            self.state.navigation_history.append(current)
        self.state.mode = new_mode
        if session_id:
            self.state.current_session_id = session_id

    def _navigate_back(self) -> bool:
        """Navigate back in history.

        Returns:
            True if navigation happened, False if at root.
        """
        if self.state.navigation_history:
            self.state.mode = self.state.navigation_history.pop()
            # Clear session context when going back to list/dashboard
            if self.state.mode in (BrowserMode.DASHBOARD, BrowserMode.LIST):
                self.state.current_session_id = None
            return True
        return False

    def _build_breadcrumb(self) -> Text:
        """Build breadcrumb navigation bar showing current location."""
        breadcrumb = Text()

        # Mode display names
        mode_names = {
            BrowserMode.DASHBOARD: "Dashboard",
            BrowserMode.LIST: "Sessions",
            BrowserMode.DETAIL: "Detail",
            BrowserMode.TOOL_DETAIL: "Tool",
            BrowserMode.TIMELINE: "Timeline",
            BrowserMode.COMPARISON: "Compare",
            BrowserMode.LIVE: "Live",
            BrowserMode.RECOMMENDATIONS: "Recs",
        }

        # Build path from history + current
        path_parts = []
        for mode in self.state.navigation_history:
            if mode in mode_names:
                path_parts.append(mode_names[mode])

        # Add current mode
        current_name = mode_names.get(self.state.mode, "")
        if current_name:
            # Add session context if in detail view
            if (
                self.state.mode
                in (BrowserMode.DETAIL, BrowserMode.TOOL_DETAIL, BrowserMode.TIMELINE)
                and self.state.current_session_id
            ):
                # Truncate session ID
                sid = self.state.current_session_id[:12]
                current_name = f"{current_name}:{sid}"
            path_parts.append(current_name)

        # Render with separators
        for i, part in enumerate(path_parts):
            if i > 0:
                breadcrumb.append(" > ", style=self.theme.dim_text)
            # Last item is bold (current location)
            style = f"bold {self.theme.info}" if i == len(path_parts) - 1 else self.theme.dim_text
            breadcrumb.append(part, style=style)

        return breadcrumb

    def show_notification(self, message: str, level: str = "info", timeout: float = 3.0) -> None:
        """Show a transient notification in the browser TUI (v0.8.0 - task-106.9).

        Args:
            message: The notification message to display.
            level: Notification type - "success", "warning", "error", or "info".
            timeout: Seconds until auto-dismiss (default 3.0).
        """
        self._notification = Notification(
            message=message,
            level=level,
            expires_at=time.time() + timeout,
        )

    def _format_tokens(self, tokens: int) -> str:
        """Format token count with K/M suffix."""
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        elif tokens >= 1_000:
            return f"{tokens / 1_000:.0f}K"
        else:
            return str(tokens)

    # ─────────────────────────────────────────────────────────────────────────
    # v1.0.3 - Concurrency Handling (task-233.14)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_watched_files(self) -> List[Path]:
        """Get list of files to monitor for external changes.

        Returns paths to session index files and config files that could be
        modified by CLI or MCP while TUI is running.
        """
        watched = []

        # Pinned servers config
        pinned_path = self.storage.base_dir / "pinned-servers.json"
        if pinned_path.exists():
            watched.append(pinned_path)

        # Session directory (monitor for new/deleted sessions)
        for platform_dir in self.storage.base_dir.iterdir():
            if platform_dir.is_dir() and platform_dir.name in (
                "claude-code",
                "codex-cli",
                "gemini-cli",
            ):
                watched.append(platform_dir)

        return watched

    def _check_external_changes(self) -> bool:
        """Check if watched files have been modified externally.

        Uses 5-second throttle to avoid excessive stat() calls.
        Returns True if changes detected.
        """
        now = time.time()

        # Throttle checks to every 5 seconds
        if self.state.last_mtime_check is not None:
            if now - self.state.last_mtime_check < 5.0:
                return False

        self.state.last_mtime_check = now
        changes_detected = False

        for path in self._get_watched_files():
            try:
                if path.is_dir():
                    # For directories, check count of json files
                    current_count = len(list(path.glob("*.json")))
                    key = f"dir:{path}"
                    if key in self.state.file_mtimes:
                        if current_count != self.state.file_mtimes[key]:
                            changes_detected = True
                    self.state.file_mtimes[key] = current_count
                else:
                    # For files, check mtime
                    current_mtime = path.stat().st_mtime
                    key = str(path)
                    if key in self.state.file_mtimes:
                        if current_mtime != self.state.file_mtimes[key]:
                            changes_detected = True
                    self.state.file_mtimes[key] = current_mtime
            except OSError:
                # File/dir may have been deleted
                key = str(path) if path.is_file() else f"dir:{path}"
                if key in self.state.file_mtimes:
                    changes_detected = True
                    del self.state.file_mtimes[key]

        if changes_detected:
            self.state.external_change_detected = True

        return changes_detected

    def _refresh_data(self) -> None:
        """Refresh all data from disk.

        Called on Ctrl+R or when user acknowledges external changes.
        Reloads sessions, pinned servers, and clears caches.
        """
        # Clear external change flag
        self.state.external_change_detected = False

        # Reload sessions
        self._load_sessions()

        # Reload pinned servers if in that view
        if self.state.mode == BrowserMode.PINNED_SERVERS:
            self._load_pinned_servers()

        # Reload smell trends if in that view
        if self.state.mode == BrowserMode.SMELL_TRENDS:
            self._load_smell_trends()

        # Update mtime cache
        self.state.last_mtime_check = time.time()
        for path in self._get_watched_files():
            try:
                if path.is_dir():
                    self.state.file_mtimes[f"dir:{path}"] = len(list(path.glob("*.json")))
                else:
                    self.state.file_mtimes[str(path)] = path.stat().st_mtime
            except OSError:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # v1.0.3 - Responsive Terminal Layouts (task-233.13)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_terminal_width(self) -> int:
        """Get terminal width, defaulting to 80.

        Returns:
            Terminal width in columns, or 80 if unable to detect.
        """
        import shutil

        try:
            return shutil.get_terminal_size().columns
        except (ValueError, OSError):
            return 80

    def _is_narrow_terminal(self) -> bool:
        """Check if terminal is narrow (<100 columns).

        Returns:
            True if terminal width is less than 100 columns.
        """
        return self._get_terminal_width() < 100

    def _should_show_column(self, column: str) -> bool:
        """Determine if column should be shown based on terminal width.

        Args:
            column: Column identifier (e.g., 'smells', 'model', 'trend')

        Returns:
            True if column should be displayed at current terminal width.
        """
        # Column priority: higher = shown on narrower terminals
        COLUMN_PRIORITY = {
            "period": 100,  # Always shown
            "sessions": 100,  # Always shown
            "tokens": 100,  # Always shown
            "cost": 100,  # Always shown
            "date": 100,  # Always shown
            "project": 90,  # Show on medium terminals
            "platform": 85,  # Show on medium terminals
            "trend": 80,  # Hide on narrow
            "smells": 70,  # Hide on narrow
            "model": 60,  # Hide on narrow
            "notes": 50,  # Hide on narrow
            "share": 75,  # Hide on narrow
        }

        width = self._get_terminal_width()
        priority = COLUMN_PRIORITY.get(column, 50)

        if width >= 120:
            return True
        elif width >= 100:
            return priority >= 60
        elif width >= 80:
            return priority >= 80
        else:
            return priority >= 100

    def _truncate_with_ellipsis(self, text: str, max_width: int) -> str:
        """Truncate text with ellipsis if it exceeds max_width.

        Args:
            text: Text to potentially truncate
            max_width: Maximum width including ellipsis

        Returns:
            Truncated text with '..' suffix if needed, otherwise original text.
        """
        if len(text) <= max_width:
            return text
        if max_width <= 2:
            return text[:max_width]
        return text[: max_width - 2] + ".."

    # =========================================================================
    # v1.0.3 - Visual Polish Helpers (task-233.12)
    # =========================================================================

    def _format_trend_indicator(self, change_pct: float, invert: bool = False) -> Tuple[str, str]:
        """Format trend indicator with consistent semantics.

        Args:
            change_pct: Percentage change value
            invert: If True, negative is good (e.g., cost reduction)

        Returns:
            Tuple of (indicator_string, theme_color)

        v1.0.3 - task-233.12
        """
        if abs(change_pct) < 5:
            indicator = f"{ascii_emoji('→')} {change_pct:+.0f}%"
            return (indicator, self.theme.dim_text)
        elif change_pct > 0:
            capped = min(change_pct, 999)
            indicator = f"{ascii_emoji('▲')} +{capped:.0f}%"
            color = self.theme.error if invert else self.theme.success
            return (indicator, color)
        else:
            capped = max(change_pct, -999)
            indicator = f"{ascii_emoji('▼')} {capped:.0f}%"
            color = self.theme.success if invert else self.theme.error
            return (indicator, color)

    def _format_number(self, value: int, align_width: int = 0) -> str:
        """Format number with thousand separators, optionally right-aligned.

        Args:
            value: Integer value to format
            align_width: If > 0, right-align to this width

        Returns:
            Formatted number string with commas

        v1.0.3 - task-233.12
        """
        formatted = f"{value:,}"
        if align_width > 0:
            return f"{formatted:>{align_width}}"
        return formatted

    def _format_cost(self, cost: float, precision: int = 2) -> str:
        """Format cost value consistently.

        Args:
            cost: Dollar cost value
            precision: Decimal places (2 for summary, 4 for detail)

        Returns:
            Formatted cost string with $ prefix

        v1.0.3 - task-233.12
        """
        if precision == 2:
            return f"${cost:,.2f}"
        return f"${cost:,.4f}"

    def run(self) -> None:
        """Run the interactive browser."""
        # v1.0.0 - task-224.5: Track TUI launches for onboarding hints
        self.prefs.increment_launch_count()
        self._is_new_user = self.prefs.is_new_user()

        # Load sessions
        self._load_sessions()

        if not self.state.sessions:
            self.console.print(
                Panel(
                    "No sessions found.\n\nRun 'token-audit collect' to start tracking.",
                    title="Session Browser",
                    border_style=self.theme.warning,
                    box=self.box_style,
                )
            )
            return

        # Enable raw mode for single-key input
        if not enable_raw_mode():
            self.console.print(
                "[yellow]Warning: Could not enable raw mode. Keyboard navigation may not work.[/]"
            )

        try:
            # v1.0.3 - task-233.14: Initialize mtime tracking
            self.state.last_mtime_check = time.time()
            for path in self._get_watched_files():
                try:
                    if path.is_dir():
                        self.state.file_mtimes[f"dir:{path}"] = len(list(path.glob("*.json")))
                    else:
                        self.state.file_mtimes[str(path)] = path.stat().st_mtime
                except OSError:
                    pass

            with Live(
                self._build_layout(),
                console=self.console,
                refresh_per_second=4,
                transient=True,
            ) as live:
                while True:
                    # Clear expired notifications (v0.8.0 - task-106.9)
                    if self._notification and time.time() > self._notification.expires_at:
                        self._notification = None
                        live.update(self._build_layout())

                    # v1.0.3 - task-233.14: Check for external changes periodically
                    if self._check_external_changes():
                        self.show_notification(
                            f"{ascii_emoji('ℹ')} External changes detected. Press Ctrl+R to refresh.",
                            level="warning",
                            timeout=10.0,
                        )
                        live.update(self._build_layout())

                    key = check_keypress(timeout=0.1)
                    if key:
                        if self._handle_key(key):
                            break  # Exit requested
                        live.update(self._build_layout())
        finally:
            disable_raw_mode()

    def _load_sessions(self) -> None:
        """Load session list from storage with current filters."""
        sessions: List[SessionEntry] = []

        for session_path in self.storage.list_sessions(
            platform=self.state.filter_platform,
            limit=500,  # Reasonable limit
        ):
            entry = self._load_session_entry(session_path)
            if entry is None:
                continue

            # Apply search filter
            if self.state.search_query:
                query = self.state.search_query.lower()
                if not (
                    query in entry.project.lower()
                    or query in entry.platform.lower()
                    or query in str(entry.path.stem).lower()
                ):
                    continue

            # v1.0.3 - task-233.10: Apply date range filter
            if self.state.date_filter_start and entry.session_date < self.state.date_filter_start:
                continue
            if self.state.date_filter_end and entry.session_date > self.state.date_filter_end:
                continue

            # Mark pinned sessions - v0.7.0 task-105.4
            entry.is_pinned = self.prefs.is_pinned(entry.path.stem)

            sessions.append(entry)

        # Sort - pinned sessions always first, then by sort key
        sort_keys: Dict[str, Any] = {
            "date": lambda e: e.session_date,
            "cost": lambda e: e.cost_estimate,
            "tokens": lambda e: e.total_tokens,
            "duration": lambda e: e.duration_seconds,
            "platform": lambda e: e.platform,
        }
        sort_fn: Any = sort_keys.get(self.state.sort_key, lambda e: e.session_date)

        # Sort by selected key
        # Order: pinned first (if enabled), then live sessions, then rest
        if self.prefs.prefs.pins_sort_to_top:
            # Sort: pinned → live → rest, each group sorted by selected key
            pinned = [e for e in sessions if e.is_pinned]
            live = [e for e in sessions if e.is_live and not e.is_pinned]
            rest = [e for e in sessions if not e.is_pinned and not e.is_live]
            pinned.sort(key=sort_fn, reverse=self.state.sort_reverse)
            live.sort(key=sort_fn, reverse=self.state.sort_reverse)
            rest.sort(key=sort_fn, reverse=self.state.sort_reverse)
            sessions = pinned + live + rest
        else:
            # Live sessions first, then rest
            live = [e for e in sessions if e.is_live]
            rest = [e for e in sessions if not e.is_live]
            live.sort(key=sort_fn, reverse=self.state.sort_reverse)
            rest.sort(key=sort_fn, reverse=self.state.sort_reverse)
            sessions = live + rest

        self.state.sessions = sessions
        self.state.selected_index = min(self.state.selected_index, max(0, len(sessions) - 1))
        # v1.0.0 - task-224.10: Update refresh timestamp
        self.state.last_refresh = datetime.now()
        self.state.is_refreshing = False

    def _load_session_entry(self, session_path: Path) -> Optional[SessionEntry]:
        """Load session metadata into a SessionEntry."""
        try:
            # Load the JSON file
            with open(session_path) as f:
                data = json.load(f)

            # Extract data from session format
            session_info = data.get("session", data)  # Handle both formats

            # Parse timestamp (keep full datetime for time display)
            # Try started_at first (v1.0+ format), then timestamp (legacy)
            timestamp_str = session_info.get("started_at", "") or session_info.get("timestamp", "")
            if timestamp_str:
                try:
                    session_date = datetime.fromisoformat(timestamp_str)
                    # Convert to naive datetime for comparison with datetime.now()
                    if session_date.tzinfo is not None:
                        # Convert to local time and strip timezone
                        session_date = session_date.astimezone().replace(tzinfo=None)
                except ValueError:
                    session_date = datetime.now()
            else:
                session_date = datetime.now()

            # Get token usage
            token_usage = data.get("token_usage", {})
            total_tokens = token_usage.get("total_tokens", 0)

            # Get cost
            cost_estimate = data.get("cost_estimate_usd", data.get("cost_estimate", 0))

            # Get tool count
            mcp_summary = data.get("mcp_summary", data.get("mcp_tool_calls", {}))
            tool_count = mcp_summary.get("unique_tools", 0)

            # Get smells count
            smells = data.get("smells", [])

            # Get model
            model = session_info.get("model", "")

            # Get accuracy level (v0.7.0 - task-105.5)
            data_quality = data.get("data_quality", {})
            accuracy_level = data_quality.get("accuracy_level", "exact")

            # Detect live/active sessions (v1.0.0)
            # Session is live if file modified in last 5 minutes
            is_live = False
            try:
                mtime = session_path.stat().st_mtime
                file_age_seconds = datetime.now().timestamp() - mtime
                is_live = file_age_seconds < 300  # 5 minutes
            except OSError:
                pass

            return SessionEntry(
                path=session_path,
                session_date=session_date,
                platform=session_info.get("platform", "unknown"),
                project=session_info.get("project", session_path.stem),
                duration_seconds=session_info.get("duration_seconds", 0),
                total_tokens=total_tokens,
                cost_estimate=float(cost_estimate) if cost_estimate else 0.0,
                tool_count=tool_count,
                smell_count=len(smells),
                model_name=model,
                accuracy_level=accuracy_level,
                is_live=is_live,
            )
        except Exception:
            return None

    def _load_tool_detail(self, server: str, tool_name: str) -> Optional[ToolDetailData]:
        """Load detailed metrics for a specific tool (v0.7.0 - task-105.7).

        Args:
            server: MCP server name
            tool_name: Tool name within the server

        Returns:
            ToolDetailData with computed metrics, or None if not found
        """
        if not self._detail_data:
            return None

        server_sessions = self._detail_data.get("server_sessions", {})
        server_data = server_sessions.get(server, {})
        tools = server_data.get("tools", {})
        tool_stats = tools.get(tool_name, {})

        if not tool_stats:
            return None

        # Extract token values from call history
        call_history = tool_stats.get("call_history", [])
        token_values = [call.get("total_tokens", 0) for call in call_history]

        # Compute percentiles and histogram
        p50 = compute_percentile(token_values, 50)
        p95 = compute_percentile(token_values, 95)
        histogram = generate_histogram(token_values)

        # Filter smells for this tool
        all_smells = self._detail_data.get("smells", [])
        tool_smells = [s for s in all_smells if s.get("tool") == tool_name]

        # Get static cost (per-server, not per-tool in v0.6.0)
        static_cost = self._detail_data.get("static_cost", {})
        by_server = static_cost.get("by_server", {})
        server_static_tokens = by_server.get(server, 0)

        return ToolDetailData(
            server=server,
            tool_name=tool_name,
            call_count=tool_stats.get("calls", 0),
            total_tokens=tool_stats.get("total_tokens", 0),
            avg_tokens=tool_stats.get("avg_tokens", 0.0),
            p50_tokens=p50,
            p95_tokens=p95,
            min_tokens=min(token_values) if token_values else 0,
            max_tokens=max(token_values) if token_values else 0,
            histogram=histogram,
            smells=tool_smells,
            static_cost_tokens=server_static_tokens,
            call_history=call_history,
        )

    def _handle_key(self, key: str) -> bool:
        """Handle keyboard input. Returns True if should exit."""
        # v1.0.3 - task-240: Debug logging for key events
        if self._debug:
            import sys

            mode_name = (
                self.state.mode.name if hasattr(self.state.mode, "name") else str(self.state.mode)
            )
            print(f"[DEBUG] Key: {repr(key)} | Mode: {mode_name}", file=sys.stderr)

        # v1.0.0 - Global hotkeys (1-4) for quick navigation
        if key == "1" and self.state.mode not in (
            BrowserMode.DASHBOARD,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.DASHBOARD
            return False
        elif key == "2" and self.state.mode not in (
            BrowserMode.LIST,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.LIST
            return False
        elif key == "3" and self.state.mode not in (
            BrowserMode.RECOMMENDATIONS,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.RECOMMENDATIONS
            return False
        elif key == "4" and self.state.mode not in (
            BrowserMode.LIVE,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.LIVE
            return False
        # v1.0.3 - task-233.3: Analytics view (key 5)
        elif key == "5" and self.state.mode not in (
            BrowserMode.ANALYTICS,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.ANALYTICS
            self.state.analytics_selected_index = 0  # Reset selection
            return False
        # v1.0.3 - task-233.5: Smell Trends view (key 6)
        elif key == "6" and self.state.mode not in (
            BrowserMode.SMELL_TRENDS,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.SMELL_TRENDS
            self.state.smell_trends_selected_index = 0  # Reset selection
            self._load_smell_trends()  # Load aggregation data
            return False
        # v1.0.3 - task-233.8: Pinned Servers view (key 7)
        elif key == "7" and self.state.mode not in (
            BrowserMode.PINNED_SERVERS,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.PINNED_SERVERS
            self.state.pinned_servers_selected_index = 0  # Reset selection
            self._load_pinned_servers()  # Load pinned server data
            return False
        # v1.0.4 - task-247.13: Bucket Configuration view (key 8)
        elif key == "8" and self.state.mode not in (
            BrowserMode.BUCKET_CONFIG,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.BUCKET_CONFIG
            self.state.bucket_config_section = 0  # Reset to first section
            self.state.bucket_config_item_index = 0  # Reset selection
            self._load_bucket_config()  # Load bucket configuration
            return False
        # v1.0.3 - task-233.2: Start Tracking modal (key n)
        elif key == "n" and self.state.mode not in (
            BrowserMode.START_TRACKING_MODAL,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self.state.mode = BrowserMode.START_TRACKING_MODAL
            self.state.start_tracking_platform_index = 0  # Reset to Claude Code
            return False
        # v1.0.3 - task-233.10: Date Range Filter modal (key R)
        elif key == "R" and self.state.mode not in (
            BrowserMode.DATE_FILTER_MODAL,
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
            BrowserMode.START_TRACKING_MODAL,
            BrowserMode.DELETE_CONFIRM_MODAL,
        ):
            self.state.mode = BrowserMode.DATE_FILTER_MODAL
            return False
        # v1.0.3 - task-233.9: Export functionality (keys e/j)
        elif key == "e" and self.state.mode in (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
            BrowserMode.PINNED_SERVERS,
        ):
            self._do_export("csv")
            return False
        elif key == "x" and self.state.mode in (
            BrowserMode.DASHBOARD,
            BrowserMode.LIST,
            BrowserMode.DETAIL,
            BrowserMode.ANALYTICS,
            BrowserMode.SMELL_TRENDS,
            BrowserMode.PINNED_SERVERS,
        ):
            self._do_export("json")
            return False
        # v1.0.3 - task-233.14: Ctrl+R to refresh data from disk
        elif key == "\x12" and self.state.mode not in (
            BrowserMode.SEARCH,
            BrowserMode.COMMAND_PALETTE,
        ):
            self._refresh_data()
            self.show_notification(
                f"{ascii_emoji('✓')} Data refreshed from disk",
                level="success",
                timeout=3.0,
            )
            return False

        # Mode-specific handlers
        if self.state.mode == BrowserMode.DASHBOARD:
            return self._handle_dashboard_key(key)  # v1.0.0
        elif self.state.mode == BrowserMode.LIVE:
            return self._handle_live_key(key)  # v1.0.0
        elif self.state.mode == BrowserMode.RECOMMENDATIONS:
            return self._handle_recommendations_key(key)  # v1.0.0
        elif self.state.mode == BrowserMode.ANALYTICS:
            return self._handle_analytics_key(key)  # v1.0.3 - task-233.3
        elif self.state.mode == BrowserMode.SMELL_TRENDS:
            return self._handle_smell_trends_key(key)  # v1.0.3 - task-233.5
        elif self.state.mode == BrowserMode.PINNED_SERVERS:
            return self._handle_pinned_servers_key(key)  # v1.0.3 - task-233.8
        elif self.state.mode == BrowserMode.ADD_SERVER_MODAL:
            return self._handle_add_server_modal_key(key)  # v1.0.3 - task-233.8
        elif self.state.mode == BrowserMode.BUCKET_CONFIG:
            return self._handle_bucket_config_key(key)  # v1.0.4 - task-247.13
        elif self.state.mode == BrowserMode.ADD_PATTERN_MODAL:
            return self._handle_add_pattern_modal_key(key)  # v1.0.4 - task-247.13
        elif self.state.mode == BrowserMode.START_TRACKING_MODAL:
            return self._handle_start_tracking_modal_key(key)  # v1.0.3 - task-233.2
        elif self.state.mode == BrowserMode.DELETE_CONFIRM_MODAL:
            return self._handle_delete_confirm_modal_key(key)  # v1.0.3 - task-233.6
        elif self.state.mode == BrowserMode.DATE_FILTER_MODAL:
            return self._handle_date_filter_modal_key(key)  # v1.0.3 - task-233.10
        elif self.state.mode == BrowserMode.COMMAND_PALETTE:
            return self._handle_command_palette_key(key)  # v1.0.0
        elif self.state.mode == BrowserMode.LIST:
            return self._handle_list_key(key)
        elif self.state.mode == BrowserMode.DETAIL:
            return self._handle_detail_key(key)
        elif self.state.mode == BrowserMode.TOOL_DETAIL:
            return self._handle_tool_detail_key(key)
        elif self.state.mode == BrowserMode.TIMELINE:
            return self._handle_timeline_key(key)  # v0.8.0 - task-106.8
        elif self.state.mode == BrowserMode.COMPARISON:
            return self._handle_comparison_key(key)  # v0.8.0 - task-106.7
        elif self.state.mode == BrowserMode.SORT_MENU:
            return self._handle_sort_menu_key(key)
        elif self.state.mode == BrowserMode.HELP:
            return self._handle_help_key(key)
        else:  # BrowserMode.SEARCH
            return self._handle_search_key(key)

    def _handle_list_key(self, key: str) -> bool:
        """Handle key in list view."""
        if key in ("q", "Q"):
            return True
        elif key in (KEY_UP, "k"):
            self._move_selection(-1)
        elif key in (KEY_DOWN, "j"):
            self._move_selection(1)
        elif key == KEY_ENTER:
            if self.state.sessions:
                self._detail_data = self._load_session_detail()
                # v1.0.0 - task-224.3: Track navigation for breadcrumb
                entry = self.state.sessions[self.state.selected_index]
                self._navigate_to(BrowserMode.DETAIL, session_id=entry.path.stem)
        elif key == "/":
            self.state.mode = BrowserMode.SEARCH
            self.state.search_query = ""
        elif key in ("s", "S"):
            # v0.7.0 - Open sort menu instead of cycling
            self.state.mode = BrowserMode.SORT_MENU
            self.state.sort_menu_index = 0
        elif key in ("f", "F"):
            self._cycle_platform_filter()
        elif key == "r":
            self._load_sessions()  # Refresh (R opens date filter modal)
        elif key == "p":
            # v0.7.0 - task-105.4: Pin/unpin session
            self._toggle_pin()
        elif key == "P":
            # v1.0.0: Unpin all sessions
            self._unpin_all()
        elif key == "?":
            # v0.7.0 - task-105.3: Show help overlay
            self.state.mode = BrowserMode.HELP
        elif key in ("t", "T"):
            # v0.7.0 - task-105.3: Toggle theme
            self._toggle_theme()
        elif key in ("a", "A"):
            # v0.7.0 - task-105.8: AI export for selected session
            self._export_list_ai_prompt()
        elif key == " ":
            # v0.8.0 - task-106.7: Toggle session selection for comparison
            self._toggle_session_selection()
        elif key in ("c", "C"):
            # v0.8.0 - task-106.7: Open comparison view (requires 2+ selected)
            self._open_comparison_view()
        elif key == ":":
            # v1.0.0 - Command palette
            self.state.mode = BrowserMode.COMMAND_PALETTE
            self.state.command_input = ""
            self.state.command_menu_index = 0
        elif key == "d":
            # v1.0.0 - Go to dashboard
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "D":
            # v1.0.3 - task-233.6: Delete session (Shift+D)
            self._initiate_delete_session()
        # Future panel navigation (no-op for now)
        elif key in ("h", "l", KEY_LEFT, KEY_RIGHT, KEY_TAB, KEY_SHIFT_TAB):
            pass  # Reserved for future panel navigation
        return False

    def _handle_detail_key(self, key: str) -> bool:
        """Handle key in detail view."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE):
            # v1.0.0 - task-224.3: Use navigation history for breadcrumb
            if not self._navigate_back():
                self.state.mode = BrowserMode.LIST
            self._detail_data = None
        elif key in ("d", "D"):
            # Drill into tool detail (v0.7.0 - task-105.7)
            self._select_top_tool()
        elif key in ("T",):
            # v0.8.0 - task-106.8: Open timeline view
            self._open_timeline_view()
        elif key in ("a", "A"):
            # v0.7.0 - task-105.8: AI export for session detail
            self._export_session_ai_prompt()
        return False

    def _handle_tool_detail_key(self, key: str) -> bool:
        """Handle key in tool detail view (v0.7.0 - task-105.7)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE, KEY_LEFT):
            # v1.0.0 - task-224.3: Use navigation history for breadcrumb
            if not self._navigate_back():
                self.state.mode = BrowserMode.DETAIL
            self.state.selected_tool = None
        elif key in ("a", "A"):
            # Export AI analysis prompt for this tool
            self._export_tool_ai_prompt()
        return False

    def _handle_timeline_key(self, key: str) -> bool:
        """Handle key in timeline view (v0.8.0 - task-106.8)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE, KEY_LEFT):
            # v1.0.0 - task-224.3: Use navigation history for breadcrumb
            if not self._navigate_back():
                self.state.mode = BrowserMode.DETAIL
            self._timeline_data = None
        elif key in ("a", "A"):
            # Export AI analysis prompt for timeline
            self._export_timeline_ai_prompt()
        return False

    def _handle_comparison_key(self, key: str) -> bool:
        """Handle key in comparison view (v0.8.0 - task-106.7)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE, KEY_LEFT):
            # v1.0.0 - task-224.3: Use navigation history for breadcrumb
            if not self._navigate_back():
                self.state.mode = BrowserMode.LIST
            self.state.selected_sessions.clear()
            self._comparison_data = None
        elif key in ("a", "A"):
            # Export AI analysis prompt for comparison
            self._export_comparison_ai_prompt()
        return False

    # =========================================================================
    # v1.0.0 - New mode handlers
    # =========================================================================

    def _handle_dashboard_key(self, key: str) -> bool:
        """Handle key in dashboard view (v1.0.0)."""
        if key in ("q", "Q"):
            return True
        elif key in (KEY_UP, "k"):
            self._move_selection(-1)
        elif key in (KEY_DOWN, "j"):
            self._move_selection(1)
        elif key == KEY_ENTER:
            # Enter drills into the selected recent session
            if self.state.sessions:
                self._detail_data = self._load_session_detail()
                # v1.0.0 - task-224.3: Track navigation for breadcrumb
                entry = self.state.sessions[self.state.selected_index]
                self._navigate_to(BrowserMode.DETAIL, session_id=entry.path.stem)
        elif key == "?":
            self.state.mode = BrowserMode.HELP
        elif key in ("t", "T"):
            self._toggle_theme()
        elif key == "r":
            self._load_sessions()  # Refresh (R opens date filter modal)
        elif key in ("a", "A"):
            self._export_dashboard_ai_prompt()
        elif key == ":":
            self.state.mode = BrowserMode.COMMAND_PALETTE
            self.state.command_input = ""
            self.state.command_menu_index = 0
        elif key in ("l", "L"):
            self.state.mode = BrowserMode.LIVE
        return False

    def _handle_live_key(self, key: str) -> bool:
        """Handle key in live monitoring view (v1.0.0)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE):
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "?":
            self.state.mode = BrowserMode.HELP
        elif key == "r":
            self._load_sessions()  # Refresh for latest session (R opens date filter)
        return False

    def _handle_recommendations_key(self, key: str) -> bool:
        """Handle key in recommendations view (v1.0.0)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE):
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "?":
            self.state.mode = BrowserMode.HELP
        elif key in ("a", "A"):
            self._export_recommendations_ai_prompt()
        elif key == "r":
            self._load_sessions()  # Refresh (R opens date filter modal)
        return False

    def _handle_command_palette_key(self, key: str) -> bool:
        """Handle key in command palette (v1.0.0)."""
        if key == KEY_ESC:
            # Cancel and return to previous mode (default to dashboard)
            self.state.mode = BrowserMode.DASHBOARD
            self.state.command_input = ""
        elif key == KEY_ENTER:
            # Execute the selected command
            self._execute_command()
        elif key == KEY_BACKSPACE:
            # Delete last character
            if self.state.command_input:
                self.state.command_input = self.state.command_input[:-1]
        elif key in (KEY_UP, "k"):
            # Move up in command list
            if self.state.command_menu_index > 0:
                self.state.command_menu_index -= 1
        elif key in (KEY_DOWN, "j"):
            # Move down in command list
            commands = self._get_filtered_commands()
            if self.state.command_menu_index < len(commands) - 1:
                self.state.command_menu_index += 1
        elif len(key) == 1 and key.isprintable():
            # Add character to input
            self.state.command_input += key
            self.state.command_menu_index = 0  # Reset selection on input change
        return False

    def _get_filtered_commands(self) -> List[tuple[str, str, BrowserMode]]:
        """Get commands filtered by current input (v1.0.0).

        Returns list of (name, description, target_mode) tuples.
        """
        commands = [
            ("dashboard", "Dashboard overview", BrowserMode.DASHBOARD),
            ("sessions", "Browse all sessions", BrowserMode.LIST),
            ("recommendations", "View recommendations", BrowserMode.RECOMMENDATIONS),
            ("live", "Live session monitor", BrowserMode.LIVE),
            ("help", "Show help", BrowserMode.HELP),
        ]

        if not self.state.command_input:
            return commands

        # Fuzzy match: command contains all chars of input in order
        query = self.state.command_input.lower()
        filtered = []
        for name, desc, mode in commands:
            if query in name.lower() or query in desc.lower():
                filtered.append((name, desc, mode))
        return filtered if filtered else commands

    def _execute_command(self) -> None:
        """Execute the selected command from palette (v1.0.0)."""
        commands = self._get_filtered_commands()
        if commands and 0 <= self.state.command_menu_index < len(commands):
            _, _, target_mode = commands[self.state.command_menu_index]
            self.state.mode = target_mode
            self.state.command_input = ""

    def _toggle_session_selection(self) -> None:
        """Toggle selection of current session for comparison (v0.8.0 - task-106.7)."""
        if not self.state.sessions:
            return

        idx = self.state.selected_index
        if idx in self.state.selected_sessions:
            self.state.selected_sessions.remove(idx)
        else:
            self.state.selected_sessions.add(idx)

    def _open_comparison_view(self) -> None:
        """Open comparison view if 2+ sessions selected (v0.8.0 - task-106.7)."""
        if len(self.state.selected_sessions) < 2:
            self.show_notification("Select at least 2 sessions to compare", "warning")
            return

        # Compute comparison data
        self._comparison_data = self._compute_comparison_data()
        if self._comparison_data:
            self.state.mode = BrowserMode.COMPARISON

    def _open_timeline_view(self) -> None:
        """Open the timeline view for the current session (v0.8.0 - task-106.8)."""
        if not self._detail_data:
            return

        # Compute timeline data
        self._timeline_data = self._compute_timeline_data()
        if self._timeline_data:
            # v1.0.0 - task-224.3: Track navigation for breadcrumb
            self._navigate_to(BrowserMode.TIMELINE)

    def _compute_timeline_data(self) -> Optional[TimelineData]:
        """Compute timeline data from session calls (v0.8.0 - task-106.8).

        Uses adaptive bucket sizes based on session duration:
        - < 10 min: 30-second buckets
        - 10-60 min: 1-minute buckets
        - 1-4 hours: 5-minute buckets
        - > 4 hours: 15-minute buckets

        Detects spikes using Z-score with threshold of 2.0 standard deviations.
        """
        if not self._detail_data:
            return None

        # Get session info
        session_meta = self._detail_data.get("session", {})
        duration_seconds = session_meta.get("duration_seconds", 0)
        session_date = datetime.fromisoformat(
            session_meta.get("timestamp", datetime.now().isoformat())
        )

        if duration_seconds <= 0:
            return None

        # Determine bucket size based on duration
        if duration_seconds < 600:  # < 10 min
            bucket_duration = 30.0  # 30-second buckets
        elif duration_seconds < 3600:  # < 1 hour
            bucket_duration = 60.0  # 1-minute buckets
        elif duration_seconds < 14400:  # < 4 hours
            bucket_duration = 300.0  # 5-minute buckets
        else:
            bucket_duration = 900.0  # 15-minute buckets

        # Calculate number of buckets
        num_buckets = max(1, int(duration_seconds / bucket_duration) + 1)

        # Initialize buckets
        buckets: List[TimelineBucket] = []
        for i in range(num_buckets):
            buckets.append(
                TimelineBucket(
                    bucket_index=i,
                    start_seconds=i * bucket_duration,
                    duration_seconds=bucket_duration,
                )
            )

        # Collect all calls with timestamps from server_sessions
        server_sessions = self._detail_data.get("server_sessions", {})

        for server_name, server_data in server_sessions.items():
            if not isinstance(server_data, dict):
                continue

            is_builtin = server_name == "builtin"
            tools = server_data.get("tools", {})

            for _tool_name, tool_stats in tools.items():
                if not isinstance(tool_stats, dict):
                    continue

                call_history = tool_stats.get("call_history", [])
                for call in call_history:
                    if not isinstance(call, dict):
                        continue

                    # Get timestamp and tokens
                    timestamp_str = call.get("timestamp")
                    tokens = call.get("total_tokens", 0)

                    if not timestamp_str:
                        # Distribute evenly if no timestamps
                        continue

                    # Parse timestamp and compute offset from session start
                    try:
                        call_time = datetime.fromisoformat(timestamp_str)
                        session_start_str = session_meta.get(
                            "start_time", session_meta.get("timestamp")
                        )
                        if session_start_str:
                            session_start = datetime.fromisoformat(session_start_str)
                            offset_seconds = (call_time - session_start).total_seconds()
                        else:
                            offset_seconds = 0
                    except (ValueError, TypeError):
                        continue

                    # Find the bucket for this call
                    if offset_seconds < 0:
                        offset_seconds = 0
                    bucket_idx = min(int(offset_seconds / bucket_duration), num_buckets - 1)

                    # Add tokens to bucket
                    buckets[bucket_idx].total_tokens += tokens
                    buckets[bucket_idx].call_count += 1
                    if is_builtin:
                        buckets[bucket_idx].builtin_tokens += tokens
                    else:
                        buckets[bucket_idx].mcp_tokens += tokens

        # If no calls with timestamps, create approximate distribution
        if all(b.total_tokens == 0 for b in buckets):
            # Fall back to distributing total tokens evenly
            token_usage = self._detail_data.get("token_usage", {})
            total_tokens = token_usage.get("total_tokens", 0)
            if total_tokens > 0 and num_buckets > 0:
                tokens_per_bucket = total_tokens // num_buckets
                for bucket in buckets:
                    bucket.total_tokens = tokens_per_bucket
                    bucket.builtin_tokens = tokens_per_bucket

        # Compute statistics for spike detection
        token_values = [b.total_tokens for b in buckets if b.total_tokens > 0]
        if token_values:
            mean_tokens = sum(token_values) / len(token_values)
            variance = sum((t - mean_tokens) ** 2 for t in token_values) / len(token_values)
            std_dev = variance**0.5 if variance > 0 else 0
        else:
            mean_tokens = 0
            std_dev = 0

        # Detect spikes (Z-score > 2.0)
        spike_threshold = 2.0
        spikes: List[TimelineBucket] = []
        for bucket in buckets:
            if std_dev > 0 and bucket.total_tokens > 0:
                z_score = (bucket.total_tokens - mean_tokens) / std_dev
                if z_score > spike_threshold:
                    bucket.is_spike = True
                    bucket.spike_magnitude = z_score
                    spikes.append(bucket)

        # Compute totals
        max_tokens = max((b.total_tokens for b in buckets), default=0)
        total_tokens = sum(b.total_tokens for b in buckets)
        total_mcp = sum(b.mcp_tokens for b in buckets)
        total_builtin = sum(b.builtin_tokens for b in buckets)

        return TimelineData(
            session_date=session_date,
            duration_seconds=duration_seconds,
            bucket_duration_seconds=bucket_duration,
            buckets=buckets,
            spikes=spikes,
            max_tokens_per_bucket=max_tokens,
            avg_tokens_per_bucket=mean_tokens,
            total_tokens=total_tokens,
            total_mcp_tokens=total_mcp,
            total_builtin_tokens=total_builtin,
        )

    def _compute_comparison_data(self) -> Optional[ComparisonData]:
        """Compute comparison data for selected sessions (v0.8.0 - task-106.7)."""
        if len(self.state.selected_sessions) < 2:
            return None

        # Get sorted indices (first one becomes baseline)
        indices = sorted(self.state.selected_sessions)
        baseline_idx = indices[0]
        comparison_indices = indices[1:]

        # Load baseline session data
        baseline_entry = self.state.sessions[baseline_idx]
        baseline_data = self._load_session_data(baseline_entry.path)
        if not baseline_data:
            return None

        # Load comparison sessions
        comparisons: List[tuple[SessionEntry, Dict[str, Any]]] = []
        for idx in comparison_indices:
            entry = self.state.sessions[idx]
            data = self._load_session_data(entry.path)
            if data:
                comparisons.append((entry, data))

        if not comparisons:
            return None

        # Compute baseline metrics
        baseline_tokens = baseline_data.get("token_usage", {}).get("total_tokens", 0)
        baseline_mcp = baseline_data.get("mcp_summary", {})
        baseline_mcp_tokens = baseline_mcp.get("total_tokens", 0)
        baseline_mcp_pct = (
            (baseline_mcp_tokens / baseline_tokens * 100) if baseline_tokens > 0 else 0
        )

        # Compute deltas
        token_deltas: List[int] = []
        mcp_share_deltas: List[float] = []
        for _entry, data in comparisons:
            comp_tokens = data.get("token_usage", {}).get("total_tokens", 0)
            comp_mcp = data.get("mcp_summary", {})
            comp_mcp_tokens = comp_mcp.get("total_tokens", 0)
            comp_mcp_pct = (comp_mcp_tokens / comp_tokens * 100) if comp_tokens > 0 else 0

            token_deltas.append(comp_tokens - baseline_tokens)
            mcp_share_deltas.append(comp_mcp_pct - baseline_mcp_pct)

        # Compute tool changes (aggregate across sessions)
        tool_tokens_baseline: Dict[str, int] = {}
        for server_name, server_data in baseline_data.get("server_sessions", {}).items():
            if server_name == "builtin" or not isinstance(server_data, dict):
                continue
            for tool_name, stats in server_data.get("tools", {}).items():
                if isinstance(stats, dict):
                    key = f"{server_name}.{tool_name}"
                    tool_tokens_baseline[key] = stats.get("total_tokens", 0)

        tool_changes_sum: Dict[str, int] = {}
        for _, data in comparisons:
            for server_name, server_data in data.get("server_sessions", {}).items():
                if server_name == "builtin" or not isinstance(server_data, dict):
                    continue
                for tool_name, stats in server_data.get("tools", {}).items():
                    if isinstance(stats, dict):
                        key = f"{server_name}.{tool_name}"
                        comp_tokens = stats.get("total_tokens", 0)
                        base_tokens = tool_tokens_baseline.get(key, 0)
                        delta = comp_tokens - base_tokens
                        tool_changes_sum[key] = tool_changes_sum.get(key, 0) + delta

        # Sort by absolute delta
        tool_changes = sorted(tool_changes_sum.items(), key=lambda x: abs(x[1]), reverse=True)[:5]

        # Build smell matrix
        all_smells: Set[str] = set()
        session_smells: List[Set[str]] = []

        # Baseline smells
        baseline_smells_set = {
            smell.get("pattern", "") for smell in baseline_data.get("detected_smells", [])
        }
        all_smells.update(baseline_smells_set)
        session_smells.append(baseline_smells_set)

        # Comparison smells
        for _, data in comparisons:
            comp_smells = {smell.get("pattern", "") for smell in data.get("detected_smells", [])}
            all_smells.update(comp_smells)
            session_smells.append(comp_smells)

        smell_matrix: Dict[str, List[bool]] = {}
        for pattern in sorted(all_smells):
            if not pattern:
                continue
            smell_matrix[pattern] = [pattern in s for s in session_smells]

        return ComparisonData(
            baseline=baseline_entry,
            baseline_data=baseline_data,
            comparisons=comparisons,
            token_deltas=token_deltas,
            mcp_share_deltas=mcp_share_deltas,
            tool_changes=tool_changes,
            smell_matrix=smell_matrix,
        )

    def _load_session_data(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load full session data from path (v0.8.0 - task-106.7)."""
        try:
            data: Dict[str, Any] = json.loads(path.read_text())
            return data
        except Exception:
            return None

    def _select_top_tool(self) -> None:
        """Select the top tool by tokens for detail view (v0.7.0 - task-105.7)."""
        if not self._detail_data:
            return

        server_sessions = self._detail_data.get("server_sessions", {})
        top_tool: Optional[tuple[str, str]] = None
        max_tokens = 0

        for server_name, server_data in server_sessions.items():
            if server_name == "builtin":
                continue
            if not isinstance(server_data, dict):
                continue
            tools = server_data.get("tools", {})
            for tool_name, stats in tools.items():
                if not isinstance(stats, dict):
                    continue
                tokens = stats.get("total_tokens", 0)
                if tokens > max_tokens:
                    max_tokens = tokens
                    top_tool = (server_name, tool_name)

        if top_tool:
            self.state.selected_tool = top_tool
            # v1.0.0 - task-224.3: Track navigation for breadcrumb
            self._navigate_to(BrowserMode.TOOL_DETAIL)

    def _export_tool_ai_prompt(self) -> None:
        """Export AI analysis prompt for selected tool (v0.7.0 - task-105.7)."""
        if not self.state.selected_tool or not self._detail_data:
            return

        server, tool_name = self.state.selected_tool
        detail = self._load_tool_detail(server, tool_name)

        if not detail:
            return

        # Generate markdown prompt
        lines = [
            "# Tool Analysis Request",
            "",
            f"Please analyze this MCP tool usage data for **{tool_name}** "
            f"from server **{server}**:",
            "",
            "## Metrics",
            f"- Call Count: {detail.call_count}",
            f"- Total Tokens: {detail.total_tokens:,}",
            f"- Average Tokens/Call: {detail.avg_tokens:,.0f}",
            "",
            "## Token Distribution",
            f"- Min: {detail.min_tokens:,}",
            f"- P50 (Median): {detail.p50_tokens:,}",
            f"- P95: {detail.p95_tokens:,}",
            f"- Max: {detail.max_tokens:,}",
            f"- Histogram: [{detail.histogram}]",
            "",
        ]

        if detail.smells:
            lines.append("## Detected Issues")
            for smell in detail.smells:
                lines.append(f"- **{smell.get('pattern')}**: {smell.get('description')}")
            lines.append("")

        lines.extend(
            [
                "## Questions",
                "1. Is this tool being used efficiently?",
                "2. Should usage be batched or restructured?",
                "3. What explains the token variance (if any)?",
                "4. Are there alternative approaches?",
            ]
        )

        output = "\n".join(lines)

        # Try to copy to clipboard (macOS), fall back to console message
        self._copy_to_clipboard(output)

    def _export_list_ai_prompt(self) -> None:
        """Export AI analysis prompt for selected sessions in list view (v0.7.0 - task-105.8).

        If Space-selected sessions exist, exports all of them.
        Otherwise exports the cursor-selected session.
        """
        if not self.state.sessions:
            return

        # Determine which sessions to export: Space-selected or cursor-selected
        if self.state.selected_sessions:
            sessions_to_export = [
                self.state.sessions[idx]
                for idx in sorted(self.state.selected_sessions)
                if idx < len(self.state.sessions)
            ]
        else:
            sessions_to_export = [self.state.sessions[self.state.selected_index]]

        if not sessions_to_export:
            return

        # Generate markdown prompt for single or multiple sessions
        if len(sessions_to_export) == 1:
            session = sessions_to_export[0]
            lines = [
                "# Session Summary Analysis Request",
                "",
                "Please analyze this Token Audit session summary:",
                "",
                "## Session Overview",
                f"- **Platform**: {session.platform}",
                f"- **Project**: {session.project}",
                f"- **Date**: {session.session_date.isoformat()}",
                f"- **Duration**: {self._format_duration(session.duration_seconds)}",
                f"- **Model**: {session.model_name or 'Unknown'}",
                "",
                "## Metrics",
                f"- **Total Tokens**: {session.total_tokens:,}",
                f"- **Estimated Cost**: ${session.cost_estimate:.4f}",
                f"- **Tool Calls**: {session.tool_count}",
                f"- **Smells Detected**: {session.smell_count}",
                f"- **Data Quality**: {session.accuracy_level}",
                "",
                "## Questions",
                "1. Is this session's token usage typical for the task type?",
                "2. Are there any efficiency concerns based on the metrics?",
                "3. What optimizations might reduce costs for similar sessions?",
                "4. How does this compare to expected token usage patterns?",
            ]
        else:
            # Multi-session export
            lines = [
                "# Multi-Session Analysis Request",
                "",
                f"Please analyze and compare these {len(sessions_to_export)} Token Audit sessions:",
                "",
            ]

            # Add each session
            for i, session in enumerate(sessions_to_export, 1):
                lines.extend(
                    [
                        f"## Session {i}: {session.project}",
                        f"- **Platform**: {session.platform}",
                        f"- **Date**: {session.session_date.isoformat()}",
                        f"- **Duration**: {self._format_duration(session.duration_seconds)}",
                        f"- **Model**: {session.model_name or 'Unknown'}",
                        f"- **Total Tokens**: {session.total_tokens:,}",
                        f"- **Estimated Cost**: ${session.cost_estimate:.4f}",
                        f"- **Tool Calls**: {session.tool_count}",
                        f"- **Smells Detected**: {session.smell_count}",
                        f"- **Data Quality**: {session.accuracy_level}",
                        "",
                    ]
                )

            # Add comparison questions
            lines.extend(
                [
                    "## Comparison Questions",
                    "1. Which session was most efficient in terms of tokens per task?",
                    "2. Are there patterns in token usage across these sessions?",
                    "3. What accounts for differences in costs between sessions?",
                    "4. Which session's approach would you recommend for similar tasks?",
                    "5. Are there common optimization opportunities across all sessions?",
                ]
            )

        output = "\n".join(lines)
        self._copy_to_clipboard(output)

    def _export_session_ai_prompt(self) -> None:
        """Export AI analysis prompt for session detail view (v0.7.0 - task-105.8)."""
        if not self._detail_data:
            return

        data = self._detail_data
        session_meta = data.get("session", {})
        token_usage = data.get("token_usage", {})
        mcp_summary = data.get("mcp_summary", {})
        smells = data.get("smells", [])
        static_cost = data.get("static_cost", {})

        # Generate comprehensive markdown prompt
        lines = [
            "# Detailed Session Analysis Request",
            "",
            "Please analyze this Token Audit session data:",
            "",
            "## Session Metadata",
            f"- **Platform**: {session_meta.get('platform', 'Unknown')}",
            f"- **Project**: {session_meta.get('project', 'Unknown')}",
            f"- **Start Time**: {session_meta.get('start_time', 'Unknown')}",
            f"- **Duration**: {session_meta.get('duration_seconds', 0):.0f} seconds",
            f"- **Model(s)**: {', '.join(data.get('models_used', [session_meta.get('model_id', 'Unknown')]))}",
            "",
            "## Token Usage",
            f"- **Input Tokens**: {token_usage.get('input_tokens', 0):,}",
            f"- **Output Tokens**: {token_usage.get('output_tokens', 0):,}",
            f"- **Total Tokens**: {token_usage.get('total_tokens', 0):,}",
            f"- **Cache Read**: {token_usage.get('cache_read', 0):,}",
            f"- **Cache Created**: {token_usage.get('cache_created', 0):,}",
        ]

        # Reasoning tokens (v0.7.0 - task-105.10) - only for Gemini/Codex
        reasoning = token_usage.get("reasoning_tokens", 0)
        if reasoning > 0:
            lines.append(f"- **Reasoning Tokens**: {reasoning:,}")

        lines.extend(
            [
                "",
                "## Cost",
                f"- **Estimated Cost**: ${data.get('cost_estimate_usd', 0):.4f}",
                "",
            ]
        )

        # MCP Tool Usage
        if mcp_summary:
            lines.extend(
                [
                    "## MCP Tool Usage",
                    f"- **Total Calls**: {mcp_summary.get('total_calls', 0)}",
                    f"- **Unique Tools**: {mcp_summary.get('unique_tools', 0)}",
                ]
            )
            # Add server breakdown if available
            server_sessions = data.get("server_sessions", {})
            if server_sessions:
                lines.append("\n### By Server:")
                for server_name, server_data in list(server_sessions.items())[:5]:
                    if server_name == "builtin":
                        continue
                    if isinstance(server_data, dict):
                        calls = server_data.get("total_calls", 0)
                        tokens = server_data.get("total_tokens", 0)
                        lines.append(f"- **{server_name}**: {calls} calls, {tokens:,} tokens")
            lines.append("")

        # Smells
        if smells:
            lines.append("## Detected Issues (Smells)")
            for smell in smells:
                pattern = smell.get("pattern", "Unknown")
                severity = smell.get("severity", "info")
                tool = smell.get("tool", "session-level")
                desc = smell.get("description", "")
                lines.append(f"- **[{severity.upper()}] {pattern}** ({tool}): {desc}")
            lines.append("")

        # Static Cost
        if static_cost.get("schema_tokens", 0) > 0:
            lines.extend(
                [
                    "## Context Tax (Schema Overhead)",
                    f"- **Total Schema Tokens**: {static_cost.get('schema_tokens', 0):,}",
                    f"- **Source**: {static_cost.get('source', 'unknown')}",
                ]
            )
            zombie_tax = data.get("zombie_context_tax", 0)
            if zombie_tax > 0:
                lines.append(f"- **Zombie Tax (unused tools)**: {zombie_tax:,} tokens")
            lines.append("")

        # Questions
        lines.extend(
            [
                "## Questions",
                "1. What are the main efficiency opportunities in this session?",
                "2. Are there any concerning patterns in the tool usage?",
                "3. How could the context tax be reduced?",
                "4. What explains the cost breakdown?",
                "5. Are there any smells that need immediate attention?",
            ]
        )

        output = "\n".join(lines)
        self._copy_to_clipboard(output)

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard (macOS) with notification (v0.8.0 - task-106.9)."""
        try:
            import subprocess

            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            self.show_notification("Ask AI prompt copied to clipboard", "success")
        except Exception:
            # Fallback - prompt generated but clipboard unavailable
            self.show_notification("Ask AI prompt exported (clipboard unavailable)", "warning")

    def _handle_search_key(self, key: str) -> bool:
        """Handle key in search mode."""
        if key == KEY_ENTER:
            self.state.mode = BrowserMode.LIST
            self._load_sessions()
        elif key == KEY_ESC:
            self.state.search_query = ""
            self.state.mode = BrowserMode.LIST
        elif key == KEY_BACKSPACE:
            self.state.search_query = self.state.search_query[:-1]
        elif len(key) == 1 and key.isprintable():
            self.state.search_query += key
        return False

    def _handle_sort_menu_key(self, key: str) -> bool:
        """Handle key in sort menu. v0.7.0 - task-105.4"""
        if key in ("q", "Q"):
            return True
        elif key in (KEY_UP, "k"):
            self.state.sort_menu_index = max(0, self.state.sort_menu_index - 1)
        elif key in (KEY_DOWN, "j"):
            self.state.sort_menu_index = min(len(SORT_OPTIONS) - 1, self.state.sort_menu_index + 1)
        elif key == KEY_ENTER:
            # Apply selected sort option
            _, sort_key, sort_reverse = SORT_OPTIONS[self.state.sort_menu_index]
            self.state.sort_key = sort_key
            self.state.sort_reverse = sort_reverse
            self.prefs.set_sort(sort_key, sort_reverse)
            self.state.mode = BrowserMode.LIST
            self._load_sessions()
        elif key == KEY_ESC:
            self.state.mode = BrowserMode.LIST
        return False

    def _handle_help_key(self, key: str) -> bool:
        """Handle key in help overlay. v0.7.0 - task-105.3, v1.0.4 - task-245.2"""
        # v1.0.4: 'q' in help mode closes help, doesn't quit TUI
        # Only truly global quit should exit (handled in list mode)
        if key == "T":
            # Toggle pins-sort-to-top setting
            self.prefs.toggle_pins_sort_to_top()
            # Reload sessions to apply new sort order
            self._load_sessions()
            return False  # Stay in help mode to see the change
        # Any other key dismisses help overlay
        self.state.mode = BrowserMode.LIST
        return False

    def _move_selection(self, delta: int) -> None:
        """Move selection up/down."""
        if not self.state.sessions:
            return

        self.state.selected_index += delta
        self.state.selected_index = max(
            0, min(self.state.selected_index, len(self.state.sessions) - 1)
        )

        # Adjust scroll if needed
        if self.state.selected_index < self.state.scroll_offset:
            self.state.scroll_offset = self.state.selected_index
        elif self.state.selected_index >= self.state.scroll_offset + self.visible_rows:
            self.state.scroll_offset = self.state.selected_index - self.visible_rows + 1

    def _toggle_pin(self) -> None:
        """Toggle pin state for selected session. v0.7.0 - task-105.4"""
        if not self.state.sessions:
            return
        entry = self.state.sessions[self.state.selected_index]
        session_id = entry.path.stem
        new_state = self.prefs.toggle_pin(session_id)
        entry.is_pinned = new_state
        # Reload to re-sort with pin state change
        self._load_sessions()

    def _unpin_all(self) -> None:
        """Unpin all sessions. v1.0.0"""
        count = self.prefs.clear_all_pins()
        if count > 0:
            # Update in-memory state
            for entry in self.state.sessions:
                entry.is_pinned = False
            # Reload to re-sort
            self._load_sessions()

    def _toggle_theme(self) -> None:
        """Toggle between dark and light themes. v0.7.0 - task-105.3"""
        # Cycle through themes: auto -> dark -> light -> high-contrast-dark -> auto
        theme_cycle = ["auto", "dark", "light", "high-contrast-dark", "high-contrast-light"]
        try:
            idx = theme_cycle.index(self._theme_name)
            new_theme = theme_cycle[(idx + 1) % len(theme_cycle)]
        except ValueError:
            new_theme = "dark"

        self._theme_name = new_theme
        self.theme = THEMES.get(new_theme, THEMES["dark"])
        self.prefs.set_theme(new_theme)

    def _cycle_platform_filter(self) -> None:
        """Cycle through platform filters."""
        platforms: List[Optional[Platform]] = [None] + list(SUPPORTED_PLATFORMS)
        try:
            idx = platforms.index(self.state.filter_platform)
        except ValueError:
            idx = 0
        self.state.filter_platform = platforms[(idx + 1) % len(platforms)]
        self._load_sessions()

    def _load_session_detail(self) -> Optional[Dict[str, Any]]:
        """Load full session data for detail view."""
        if not self.state.sessions:
            return None
        entry = self.state.sessions[self.state.selected_index]
        try:
            with open(entry.path) as f:
                data: Dict[str, Any] = json.load(f)
                return data
        except Exception:
            return None

    def _build_layout(self) -> Layout:
        """Build the browser layout."""
        layout = Layout()

        # Build panels list (v0.8.0: dynamically add notification bar)
        panels: List[Layout] = []

        # v1.0.0 - task-224.3: Add breadcrumb for navigation context (except overlays)
        show_breadcrumb = self.state.mode not in (
            BrowserMode.COMMAND_PALETTE,
            BrowserMode.SORT_MENU,
            BrowserMode.HELP,
            BrowserMode.SEARCH,
        )
        if show_breadcrumb and self.state.navigation_history:
            # Only show breadcrumb if there's navigation history
            panels.append(Layout(self._build_breadcrumb(), name="breadcrumb", size=1))

        # v1.0.0 - New primary views
        if self.state.mode == BrowserMode.DASHBOARD:
            panels.extend(
                [
                    Layout(self._build_dashboard_view(), name="dashboard"),
                    Layout(self._build_dashboard_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.LIVE:
            panels.extend(
                [
                    Layout(self._build_live_view(), name="live"),
                    Layout(self._build_live_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.RECOMMENDATIONS:
            panels.extend(
                [
                    Layout(self._build_recommendations_view(), name="recommendations"),
                    Layout(self._build_recommendations_footer(), name="footer", size=1),
                ]
            )
        # v1.0.3 - task-233.3: Analytics view
        elif self.state.mode == BrowserMode.ANALYTICS:
            panels.extend(
                [
                    Layout(self._build_analytics_view(), name="analytics"),
                    Layout(self._build_analytics_footer(), name="footer", size=1),
                ]
            )
        # v1.0.3 - task-233.5: Smell Trends view
        elif self.state.mode == BrowserMode.SMELL_TRENDS:
            panels.extend(
                [
                    Layout(self._build_smell_trends_view(), name="smell_trends"),
                    Layout(self._build_smell_trends_footer(), name="footer", size=1),
                ]
            )
        # v1.0.3 - task-233.8: Pinned Servers view
        elif self.state.mode == BrowserMode.PINNED_SERVERS:
            panels.extend(
                [
                    Layout(self._build_pinned_servers_view(), name="pinned_servers"),
                    Layout(self._build_pinned_servers_footer(), name="footer", size=1),
                ]
            )
        # v1.0.3 - task-233.8: Add Server modal
        elif self.state.mode == BrowserMode.ADD_SERVER_MODAL:
            panels = [
                Layout(self._build_add_server_modal(), name="modal"),
            ]
        # v1.0.4 - task-247.13: Bucket Configuration view
        elif self.state.mode == BrowserMode.BUCKET_CONFIG:
            panels.extend(
                [
                    Layout(self._build_bucket_config_view(), name="bucket_config"),
                    Layout(self._build_bucket_config_footer(), name="footer", size=1),
                ]
            )
        # v1.0.4 - task-247.13: Add Pattern modal
        elif self.state.mode == BrowserMode.ADD_PATTERN_MODAL:
            panels = [
                Layout(self._build_add_pattern_modal(), name="modal"),
            ]
        # v1.0.3 - task-233.2: Start Tracking modal
        elif self.state.mode == BrowserMode.START_TRACKING_MODAL:
            panels = [
                Layout(self._build_start_tracking_modal(), name="modal"),
            ]
        # v1.0.3 - task-233.6: Delete Confirmation modal
        elif self.state.mode == BrowserMode.DELETE_CONFIRM_MODAL:
            panels = [
                Layout(self._build_delete_confirm_modal(), name="modal"),
            ]
        # v1.0.3 - task-233.10: Date Range Filter modal
        elif self.state.mode == BrowserMode.DATE_FILTER_MODAL:
            panels = [
                Layout(self._build_date_filter_modal(), name="modal"),
            ]
        elif self.state.mode == BrowserMode.COMMAND_PALETTE:
            panels = [
                Layout(self._build_command_palette(), name="palette"),
            ]
        elif self.state.mode == BrowserMode.DETAIL:
            panels.extend(
                [
                    Layout(self._build_detail_view(), name="detail"),
                    Layout(self._build_detail_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.TOOL_DETAIL:
            # v0.7.0 - task-105.7: Tool detail view
            panels.extend(
                [
                    Layout(self._build_tool_detail_view(), name="tool_detail"),
                    Layout(self._build_tool_detail_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.TIMELINE:
            # v0.8.0 - task-106.8: Timeline view
            panels.extend(
                [
                    Layout(self._build_timeline_view(), name="timeline"),
                    Layout(self._build_timeline_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.COMPARISON:
            # v0.8.0 - task-106.7: Comparison view
            panels.extend(
                [
                    Layout(self._build_comparison_view(), name="comparison"),
                    Layout(self._build_comparison_footer(), name="footer", size=1),
                ]
            )
        elif self.state.mode == BrowserMode.SORT_MENU:
            # v0.7.0 - task-105.4: Sort menu overlay
            panels = [
                Layout(self._build_header(), name="header", size=4),
                Layout(self._build_sort_menu(), name="menu"),
                Layout(self._build_sort_menu_footer(), name="footer", size=1),
            ]
        elif self.state.mode == BrowserMode.HELP:
            # v0.7.0 - task-105.3: Help overlay
            panels = [
                Layout(self._build_help_overlay(), name="help"),
                Layout(self._build_help_footer(), name="footer", size=1),
            ]
        else:
            # LIST mode (and fallback)
            panels.extend(
                [
                    Layout(self._build_header(), name="header", size=4),
                    Layout(self._build_session_table(), name="table"),
                    Layout(self._build_footer(), name="footer", size=2),
                ]
            )

        # Add notification bar if active (v0.8.0 - task-106.9)
        if self._notification:
            panels.append(Layout(self._build_notification(), name="notification", size=1))

        layout.split_column(*panels)

        return layout

    def _build_header(self) -> Panel:
        """Build header with title, version, theme, help hint, and filters."""
        content = Text()

        # Line 1: Title with version and session count
        content.append("Token Audit", style=f"bold {self.theme.title}")
        content.append(f" v{__version__}", style=self.theme.dim_text)
        content.append(" - Session Browser", style=f"bold {self.theme.title}")
        content.append(f"  ({len(self.state.sessions)} sessions)\n", style=self.theme.dim_text)

        # Line 2: Theme, refresh status, and help hint
        theme_display = self._theme_name if self._theme_name != "auto" else "auto"
        content.append(f"Theme: {theme_display}", style=self.theme.dim_text)
        content.append("  |  ", style=self.theme.dim_text)

        # v1.0.0 - task-224.10: Refresh/staleness indicator
        if self.state.is_refreshing:
            content.append("⟳ Refreshing...", style=self.theme.info)
        elif self.state.last_refresh:
            refresh_text, is_stale = self._format_refresh_time(self.state.last_refresh)
            if is_stale:
                content.append(f"Last refresh: {refresh_text} ⚠", style=self.theme.warning)
            else:
                content.append(f"Last refresh: {refresh_text}", style=self.theme.dim_text)
        content.append("  |  ", style=self.theme.dim_text)
        content.append("? for help\n", style=self.theme.info)

        # Line 3: Active filters (only if any)
        filters = []
        if self.state.filter_platform:
            filters.append(f"platform={self.state.filter_platform}")
        if self.state.search_query:
            filters.append(f'search="{self.state.search_query}"')
        # v1.0.3 - task-233.10: Add date filter badge
        date_badge = self._get_date_filter_badge()
        if date_badge:
            filters.append(f"date={date_badge}")
        if filters:
            content.append(f"Filters: {', '.join(filters)}", style=self.theme.warning)

        return Panel(content, border_style=self.theme.header_border, box=self.box_style)

    def _format_refresh_time(self, last_refresh: datetime) -> tuple[str, bool]:
        """Format last refresh time as relative string.

        v1.0.0 - task-224.10

        Args:
            last_refresh: The datetime of the last refresh

        Returns:
            Tuple of (formatted string, is_stale flag). Stale if > 5 minutes old.
        """
        now = datetime.now()
        delta = now - last_refresh
        seconds = int(delta.total_seconds())

        if seconds < 10:
            return "just now", False
        elif seconds < 60:
            return f"{seconds}s ago", False
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago", minutes >= 5
        else:
            hours = seconds // 3600
            return f"{hours}h ago", True

    def _build_session_table(self) -> Panel:
        """Build the session list table."""
        table = Table(
            box=self.box_style,
            show_header=True,
            header_style=f"bold {self.theme.primary_text}",
            expand=True,
        )

        # v1.0.3 - task-233.13: Responsive column visibility
        show_platform = self._should_show_column("platform")
        show_project = self._should_show_column("project")
        is_narrow = self._is_narrow_terminal()
        project_width = 14 if is_narrow else 18
        date_width = 12 if is_narrow else 14

        table.add_column("", width=1)  # Selection indicator
        table.add_column("Pin", width=3)  # Pin indicator - v0.7.0 task-105.4
        table.add_column("", width=2)  # Live indicator - v1.0.0
        table.add_column("Date", width=date_width)  # "18 Dec 2:30pm"
        if show_platform:
            table.add_column("AI/Platform", width=12)
        if show_project:
            table.add_column("Directory/Project", width=project_width)
        table.add_column("Tokens", justify="right", width=10)
        table.add_column("Cost", justify="right", width=10)
        if not is_narrow:
            table.add_column("Tools", justify="right", width=6)
        table.add_column("", width=2)  # Accuracy indicator - v0.7.0 task-105.5

        if not self.state.sessions:
            # Empty state
            return Panel(
                Text("No sessions found", style=f"{self.theme.dim_text} italic"),
                title="Sessions",
                border_style=self.theme.mcp_border,
                box=self.box_style,
            )

        # Display visible rows
        start = self.state.scroll_offset
        end = min(start + self.visible_rows, len(self.state.sessions))

        for i, entry in enumerate(self.state.sessions[start:end]):
            actual_idx = start + i
            is_cursor = actual_idx == self.state.selected_index
            is_selected_for_compare = actual_idx in self.state.selected_sessions

            # v0.8.0 - task-106.7: Show both cursor and selection state
            # Cursor: ">", Selection: checkbox [X] or [ ]
            if is_cursor:
                indicator = ">"
            elif is_selected_for_compare:
                indicator = ascii_emoji("✓")  # Checkmark for selected sessions
            else:
                indicator = " "
            # Pin indicator with ASCII fallback - v0.7.0 task-105.4
            pin_indicator = ascii_emoji("\U0001f4cc") if entry.is_pinned else ""
            row_style = (
                f"bold {self.theme.info}"
                if is_cursor
                else (f"{self.theme.success}" if is_selected_for_compare else "")
            )

            # v1.0.3 - task-233.13: Truncate project name using responsive helper
            max_project_len = project_width - 2 if show_project else 0
            project_display = self._truncate_with_ellipsis(entry.project, max_project_len)

            # Format tokens
            if entry.total_tokens >= 1_000_000:
                tokens_str = f"{entry.total_tokens / 1_000_000:.1f}M"
            elif entry.total_tokens >= 1_000:
                tokens_str = f"{entry.total_tokens / 1_000:.0f}K"
            else:
                tokens_str = str(entry.total_tokens)

            # Accuracy indicator with color - v0.7.0 task-105.5
            acc_icon, acc_color = accuracy_indicator(entry.accuracy_level)
            acc_text = Text(acc_icon, style=acc_color)

            # Format date with time: "18 Dec 2:30pm" (shorter for narrow terminals)
            if is_narrow:
                date_str = entry.session_date.strftime("%d %b %-I%p").lower()
            else:
                date_str = entry.session_date.strftime("%d %b %-I:%M%p").lower()
            # Capitalize month abbreviation (Dec not dec)
            date_str = date_str[:3] + date_str[3:6].title() + date_str[6:]

            # Live indicator - v1.0.0
            live_text = (
                Text(ascii_emoji("🔴"), style=self.theme.error) if entry.is_live else Text("")
            )

            # v1.0.3 - task-233.13: Build row dynamically based on visible columns
            row: List[Text | str] = [indicator, pin_indicator, live_text, date_str]
            if show_platform:
                row.append(entry.platform.replace("_", "-"))
            if show_project:
                row.append(project_display)
            row.extend([tokens_str, f"${entry.cost_estimate:.4f}"])
            if not is_narrow:
                row.append(str(entry.tool_count))
            row.append(acc_text)

            table.add_row(*row, style=row_style)

        # Title with accuracy legend and position counter subtitle (v1.0.0 - task-224.6)
        total = len(self.state.sessions)
        title = f"Sessions ({total}) | Accuracy: ✓=exact ~=est •=calls"
        subtitle = f"Showing {start + 1}-{end} · sorted by {self.state.sort_key}"

        return Panel(
            table,
            title=title,
            subtitle=subtitle,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_footer(self) -> Text:
        """Build footer with keybindings and selected session info."""
        if self.state.mode == BrowserMode.SEARCH:
            return Text(
                f"Search: {self.state.search_query}_ (ENTER=apply, ESC=cancel)",
                style=self.theme.warning,
                justify="center",
            )

        # Build two-line footer: session info + keybindings (v0.7.0 - task-105.11)
        footer = Text()

        # Line 1: Selected session ID (LIST mode only)
        if (
            self.state.mode == BrowserMode.LIST
            and self.state.sessions
            and self.state.selected_index < len(self.state.sessions)
        ):
            entry = self.state.sessions[self.state.selected_index]
            session_id = entry.path.stem
            footer.append(f"Session: {session_id}\n", style=self.theme.info)

        # Line 2: Keybindings (v0.7.0 - task-105.8, v0.8.0 - task-106.7 added Space/C, v1.0.0 P=unpin all)
        # v1.0.0 - task-224.5: Show help hint for new users
        if self._is_new_user:
            footer.append("[?] Press ? for help  |  ", style=f"bold {self.theme.info}")
        # Show selection count if sessions are selected
        selection_info = ""
        if self.state.selected_sessions:
            count = len(self.state.selected_sessions)
            selection_info = f"  [{count} selected] c=compare"
        footer.append(
            f"j/k=nav  :=cmd  a=AI  p=pin  s=sort  /=search  Space=select{selection_info}  ?=help  q=quit",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

    # =========================================================================
    # v1.0.0 - Dashboard View
    # =========================================================================

    def _build_dashboard_view(self) -> Panel:
        """Build the enhanced dashboard overview panel (v1.0.3).

        Features:
        - Summary cards: Today / This Week / This Month
        - 7-day sparkline with cost trend
        - Week-over-week comparison with trend badges
        - Smell frequency bars with percentages
        - Top cost drivers
        - Enhanced recent sessions table
        """

        content = Text()

        # Header with hotkeys (updated for v1.0.3)
        content.append("Token Audit Dashboard", style=f"bold {self.theme.title}")
        content.append(f"  v{__version__}", style=self.theme.dim_text)
        # v1.0.3 - task-233.10: Date filter badge
        date_badge = self._get_date_filter_badge()
        if date_badge:
            content.append(f"  [{date_badge}]", style=f"bold {self.theme.info}")
        content.append("\n")
        content.append(
            "[1]Dashboard [2]Sessions [3]Recs [4]Live [5]Analytics | [R]Filter [n]New [?]Help [q]Quit\n\n",
            style=self.theme.dim_text,
        )

        # ========== SUMMARY CARDS: TODAY / THIS WEEK / THIS MONTH ==========
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        month_start = today.replace(day=1)

        # Calculate stats from sessions
        today_sessions = [s for s in self.state.sessions if s.session_date.date() == today]
        week_sessions = [s for s in self.state.sessions if s.session_date.date() >= week_start]
        month_sessions = [s for s in self.state.sessions if s.session_date.date() >= month_start]

        today_tokens = sum(s.total_tokens for s in today_sessions)
        today_cost = sum(s.cost_estimate for s in today_sessions)
        week_tokens = sum(s.total_tokens for s in week_sessions)
        week_cost = sum(s.cost_estimate for s in week_sessions)
        month_tokens = sum(s.total_tokens for s in month_sessions)
        month_cost = sum(s.cost_estimate for s in month_sessions)

        # Build summary cards in a row
        content.append(
            "┌─ TODAY ──────────┐ ┌─ THIS WEEK ─────┐ ┌─ THIS MONTH ────┐\n",
            style=self.theme.dim_text,
        )
        content.append(f"│ Sessions: {len(today_sessions):>5}  │ ", style=self.theme.dim_text)
        content.append(f"│ Sessions: {len(week_sessions):>5} │ ", style=self.theme.dim_text)
        content.append(f"│ Sessions: {len(month_sessions):>5} │\n", style=self.theme.dim_text)
        content.append(
            f"│ Tokens: {self._format_tokens(today_tokens):>7}  │ ", style=self.theme.dim_text
        )
        content.append(
            f"│ Tokens: {self._format_tokens(week_tokens):>7} │ ", style=self.theme.dim_text
        )
        content.append(
            f"│ Tokens: {self._format_tokens(month_tokens):>7} │\n", style=self.theme.dim_text
        )
        content.append(f"│ Cost:   ${today_cost:>7.2f}  │ ", style=self.theme.dim_text)
        content.append(f"│ Cost:  ${week_cost:>7.2f} │ ", style=self.theme.dim_text)
        content.append(f"│ Cost:  ${month_cost:>7.2f} │\n", style=self.theme.dim_text)
        content.append(
            "└──────────────────┘ └─────────────────┘ └─────────────────┘\n\n",
            style=self.theme.dim_text,
        )

        # ========== 7-DAY COST TREND SPARKLINE ==========
        content.append(ascii_emoji("📈"), style=self.theme.info)
        content.append(" 7-Day Cost Trend", style=f"bold {self.theme.primary_text}")

        # Calculate last week comparison for trend badge
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start - timedelta(days=1)
        last_week_sessions = [
            s
            for s in self.state.sessions
            if last_week_start <= s.session_date.date() <= last_week_end
        ]
        last_week_cost = sum(s.cost_estimate for s in last_week_sessions)

        # v1.0.3 - task-233.12: Show week-over-week change using helper
        if last_week_cost > 0:
            change_pct = ((week_cost - last_week_cost) / last_week_cost) * 100
            # Cost increases are bad (invert=True)
            trend_str, trend_color = self._format_trend_indicator(change_pct, invert=True)
            content.append(f"  {trend_str}", style=trend_color)
        content.append("\n", style=self.theme.dim_text)
        content.append("─" * 50 + "\n", style=self.theme.dim_text)

        # Build 7-day sparkline (ASCII bar chart)
        daily_costs: List[float] = []
        day_labels: List[str] = []
        for i in range(6, -1, -1):  # 6 days ago to today
            d = today - timedelta(days=i)
            day_sessions = [s for s in self.state.sessions if s.session_date.date() == d]
            daily_costs.append(sum(s.cost_estimate for s in day_sessions))
            day_labels.append(d.strftime("%a")[0])  # M, T, W, T, F, S, S

        max_cost = max(daily_costs) if daily_costs else 1.0
        if max_cost == 0:
            max_cost = 1.0

        # Draw sparkline (3 rows: $max, bars, labels)
        bar_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        sparkline = ""
        for cost in daily_costs:
            level = int((cost / max_cost) * 7) if max_cost > 0 else 0
            sparkline += bar_chars[min(level, 7)] + " "

        content.append(f"  ${max_cost:.0f} │ ", style=self.theme.dim_text)
        content.append(sparkline + "\n", style=self.theme.info)
        content.append("   $0 │ ", style=self.theme.dim_text)
        content.append(" ".join(day_labels) + "\n\n", style=self.theme.dim_text)

        # ========== TOP SMELLS (FREQUENCY BARS) ==========
        content.append(ascii_emoji("🔥"), style=self.theme.warning)
        content.append(" Top Smells (7 days)\n", style=f"bold {self.theme.primary_text}")
        content.append("─" * 40 + "\n", style=self.theme.dim_text)

        # Use SmellAggregator for real smell frequency data
        try:
            smell_agg = SmellAggregator(base_dir=self.storage.base_dir)
            smell_result = smell_agg.aggregate(days=7)
            top_smells = sorted(
                smell_result.aggregated_smells, key=lambda s: s.frequency_percent, reverse=True
            )[:3]

            for smell in top_smells:
                # Build frequency bar
                bar_width = int(smell.frequency_percent / 100 * 20)
                bar = "█" * bar_width + "░" * (20 - bar_width)

                # Trend indicator
                if smell.trend == "worsening":
                    trend = " ▲"
                    trend_style = self.theme.error
                elif smell.trend == "improving":
                    trend = " ▼"
                    trend_style = self.theme.success
                else:
                    trend = ""
                    trend_style = self.theme.dim_text

                content.append(f"  {smell.pattern:<15} ", style=self.theme.primary_text)
                content.append(f"{smell.frequency_percent:>3.0f}% ", style=self.theme.primary_text)
                content.append(bar, style=self.theme.info)
                if trend:
                    content.append(trend, style=trend_style)
                content.append("\n")

            if not top_smells:
                content.append("  No smells detected\n", style=self.theme.dim_text)
        except Exception:
            # Fallback if SmellAggregator fails
            content.append("  No smell data available\n", style=self.theme.dim_text)

        content.append("\n")

        # ========== RECENT SESSIONS (ENHANCED) ==========
        content.append(ascii_emoji("📋"), style=self.theme.info)
        content.append(" Recent Sessions\n", style=f"bold {self.theme.primary_text}")
        content.append("─" * 75 + "\n", style=self.theme.dim_text)

        # Column headers
        content.append(
            f"  {'Time':<12} {'Project':<14} {'Tokens':>8} {'Cost':>8} {'Tools':>6} {'Smells':>7}\n",
            style=self.theme.dim_text,
        )
        content.append("  " + "─" * 73 + "\n", style=self.theme.dim_text)

        # Sort sessions by date for recent view (most recent first)
        recent_sessions = sorted(self.state.sessions, key=lambda e: e.session_date, reverse=True)

        # Show up to 5 recent sessions
        visible_count = min(5, len(recent_sessions))
        for i, entry in enumerate(recent_sessions[:visible_count]):
            is_selected = i == self.state.selected_index
            prefix = "▸" if is_selected else " "
            style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text

            # Format relative time (Today: "2:15 PM", Yesterday: "Yesterday", Older: "Dec 24")
            session_date = entry.session_date.date()
            if session_date == today:
                try:
                    time_display = entry.session_date.strftime("%-I:%M %p")
                except ValueError:
                    time_display = entry.session_date.strftime("%I:%M %p")
            elif session_date == today - timedelta(days=1):
                time_display = "Yesterday"
            else:
                time_display = entry.session_date.strftime("%b %d")

            tokens_str = self._format_tokens(entry.total_tokens)
            project = entry.project[:12] + ".." if len(entry.project) > 14 else entry.project

            content.append(f"{prefix} ", style=style)
            if entry.is_live:
                content.append(ascii_emoji("🔴"), style=self.theme.error)
                content.append(" ", style=style)
            else:
                content.append("  ", style=style)
            content.append(
                f"{time_display:<10} {project:<14} {tokens_str:>8} ${entry.cost_estimate:>7.2f} {entry.tool_count:>6} {entry.smell_count:>7}\n",
                style=style,
            )

        if len(self.state.sessions) > visible_count:
            content.append(
                f"\n  ... and {len(self.state.sessions) - visible_count} more (press 2 for full list)\n",
                style=self.theme.dim_text,
            )

        return Panel(
            content,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_dashboard_footer(self) -> Text:
        """Build footer for dashboard view (v1.0.3)."""
        footer = Text()
        # v1.0.0 - task-224.5: Show help hint for new users
        if self._is_new_user:
            footer.append("[?] Press ? for help  |  ", style=f"bold {self.theme.info}")
        # v1.0.3 - Updated keybindings with Analytics and Start Tracking
        footer.append(
            "j/k=nav  5=analytics  n=new  Enter=view  r=refresh  ?=help  q=quit",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

    def _format_time_ago(self, dt: datetime) -> str:
        """Format datetime as relative time (e.g., '2h ago', '1d ago')."""
        now = datetime.now()
        delta = now - dt

        if delta.total_seconds() < 60:
            return "now"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins}m ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}h ago"
        else:
            days = int(delta.total_seconds() / 86400)
            return f"{days}d ago"

    # =========================================================================
    # v1.0.0 - Live Monitoring View
    # =========================================================================

    def _build_live_view(self) -> Panel:
        """Build the live monitoring panel (v1.0.0)."""
        content = Text()

        # Header
        content.append("Live Monitor", style=f"bold {self.theme.title}")
        content.append(f"  v{__version__}\n", style=self.theme.dim_text)
        content.append(
            "[1]Dashboard  [2]Sessions  [3]Recs  [4]Live  |  [?]Help  [q]Quit\n\n",
            style=self.theme.dim_text,
        )

        # Check for active/recent session
        if self.state.sessions:
            latest = self.state.sessions[0]
            time_ago = self._format_time_ago(latest.session_date)

            # Determine if session is likely active (within last 5 min)
            delta = (datetime.now() - latest.session_date).total_seconds()
            is_active = delta < 300  # 5 minutes

            if is_active:
                content.append(ascii_emoji("🔴"), style=self.theme.error)
                content.append(" ACTIVE SESSION\n", style=f"bold {self.theme.error}")
            else:
                content.append(ascii_emoji("⚪"), style=self.theme.dim_text)
                content.append(" MOST RECENT SESSION\n", style=f"bold {self.theme.dim_text}")

            content.append("─" * 50 + "\n", style=self.theme.dim_text)

            # Session info
            content.append(f"  Platform:   {latest.platform}\n", style=self.theme.primary_text)
            content.append(f"  Project:    {latest.project}\n", style=self.theme.primary_text)
            content.append(
                f"  Model:      {latest.model_name or 'unknown'}\n", style=self.theme.primary_text
            )
            content.append(
                f"  Duration:   {self._format_duration_short(latest.duration_seconds)}\n",
                style=self.theme.primary_text,
            )
            content.append(f"  Last seen:  {time_ago}\n\n", style=self.theme.primary_text)

            # Token stats
            content.append(ascii_emoji("📊"), style=self.theme.info)
            content.append(" Token Usage\n", style=f"bold {self.theme.primary_text}")
            content.append("─" * 30 + "\n", style=self.theme.dim_text)
            content.append(
                f"  Total:    {self._format_tokens(latest.total_tokens)}\n",
                style=self.theme.primary_text,
            )
            content.append(
                f"  Cost:     ${latest.cost_estimate:.4f}\n", style=self.theme.primary_text
            )
            content.append(f"  Tools:    {latest.tool_count}\n", style=self.theme.primary_text)
            content.append(f"  Smells:   {latest.smell_count}\n\n", style=self.theme.primary_text)

            # Simple rate estimate
            if latest.duration_seconds > 0:
                tokens_per_min = (latest.total_tokens / latest.duration_seconds) * 60
                cost_per_min = (latest.cost_estimate / latest.duration_seconds) * 60
                content.append(ascii_emoji("⚡"), style=self.theme.warning)
                content.append(" Rate (avg)\n", style=f"bold {self.theme.primary_text}")
                content.append("─" * 30 + "\n", style=self.theme.dim_text)
                content.append(
                    f"  {self._format_tokens(int(tokens_per_min))} tok/min\n",
                    style=self.theme.primary_text,
                )
                content.append(f"  ${cost_per_min:.4f}/min\n", style=self.theme.primary_text)
        else:
            content.append("\n  No sessions found.\n", style=self.theme.dim_text)
            content.append(
                "  Run a Claude Code/Codex/Gemini session to see live data.\n",
                style=self.theme.dim_text,
            )

        return Panel(
            content,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_live_footer(self) -> Text:
        """Build footer for live view (v1.0.0)."""
        footer = Text()
        footer.append(
            "r=refresh  Esc=back  ?=help  q=quit",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

    def _format_duration_short(self, seconds: float) -> str:
        """Format duration in short form (e.g., '12m 34s')."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    # =========================================================================
    # v1.0.0 - Recommendations View
    # =========================================================================

    def _build_recommendations_view(self) -> Panel:
        """Build the enhanced recommendations panel (v1.0.3 - task-233.7).

        Enhanced with:
        - HIGH PRIORITY section: Urgent issues with trends
        - INSIGHTS section: Cost concentration, patterns
        - POSITIVE TRENDS section: Improvements to celebrate
        """

        content = Text()

        # Header
        content.append("Recommendations", style=f"bold {self.theme.title}")
        content.append(f"  v{__version__}\n", style=self.theme.dim_text)
        content.append(
            "[1]Dashboard  [2]Sessions  [3]Recs  [4]Live  [5]Analytics [6]Smells |  [?]Help  [q]Quit\n\n",
            style=self.theme.dim_text,
        )

        if not self.state.sessions:
            content.append("\n  No sessions to analyze.\n", style=self.theme.dim_text)
            content.append(
                "  Run 'token-audit collect' to gather session data.\n", style=self.theme.dim_text
            )
        else:
            # Gather data for recommendations
            high_priority_items = []
            insight_items = []
            positive_items = []

            # ═══════════════════════════════════════════════════════════════
            # HIGH PRIORITY Section
            # ═══════════════════════════════════════════════════════════════

            # 1. Usage Trending - Compare this week to last week
            try:
                today = datetime.now().date()
                week_ago = today - timedelta(days=7)
                two_weeks_ago = today - timedelta(days=14)

                current_week_sessions = [
                    s for s in self.state.sessions if s.session_date.date() >= week_ago
                ]
                prev_week_sessions = [
                    s
                    for s in self.state.sessions
                    if two_weeks_ago <= s.session_date.date() < week_ago
                ]

                if current_week_sessions and prev_week_sessions:
                    current_tokens = sum(s.total_tokens for s in current_week_sessions)
                    prev_tokens = sum(s.total_tokens for s in prev_week_sessions)

                    if prev_tokens > 0:
                        change_pct = ((current_tokens - prev_tokens) / prev_tokens) * 100

                        if change_pct > 20:
                            high_priority_items.append(
                                (
                                    ascii_emoji("chart"),
                                    "Usage Trending Up",
                                    f"Token usage increased {change_pct:.0f}% compared to last week.",
                                    "Review high-token sessions for optimization opportunities",
                                )
                            )
                        elif change_pct < -20:
                            positive_items.append(
                                (
                                    ascii_emoji("chart"),
                                    "Usage Trending Down",
                                    f"Token usage decreased {abs(change_pct):.0f}% compared to last week.",
                                )
                            )
            except Exception:
                pass

            # 2. Recurring Smell Patterns (>30% frequency)
            try:
                agg = SmellAggregator()
                smell_data = agg.aggregate(
                    days=14,
                    platform=self.state.filter_platform if self.state.filter_platform else None,
                )

                if smell_data and smell_data.aggregated_smells:
                    recurring = [
                        s for s in smell_data.aggregated_smells if s.frequency_percent > 30
                    ]
                    for smell in recurring[:2]:  # Top 2 recurring
                        if smell.trend == "worsening":
                            high_priority_items.append(
                                (
                                    ascii_emoji("warning"),
                                    f"Recurring Pattern: {smell.pattern}",
                                    f"This smell appears in {smell.frequency_percent:.0f}% of your sessions and is worsening.",
                                    self._get_smell_recommendation(smell.pattern),
                                )
                            )
                        elif smell.frequency_percent > 50:
                            high_priority_items.append(
                                (
                                    ascii_emoji("warning"),
                                    f"Frequent Pattern: {smell.pattern}",
                                    f"This smell appears in {smell.frequency_percent:.0f}% of your sessions.",
                                    self._get_smell_recommendation(smell.pattern),
                                )
                            )

                    # Check for improving smells (positive)
                    improving = [s for s in smell_data.aggregated_smells if s.trend == "improving"]
                    for smell in improving[:1]:  # Top 1 improving
                        positive_items.append(
                            (
                                ascii_emoji("success"),
                                f"{smell.pattern} improving",
                                f"Down {abs(smell.trend_change_percent):.0f}% this period.",
                            )
                        )
            except Exception:
                pass

            # 3. High-severity smells requiring attention
            try:
                if smell_data and smell_data.aggregated_smells:
                    for smell in smell_data.aggregated_smells:
                        severity = self._get_dominant_severity(smell.severity_breakdown)
                        if severity in ("high", "critical") and smell.pattern not in [
                            h[1].split(": ")[-1] for h in high_priority_items
                        ]:
                            high_priority_items.append(
                                (
                                    ascii_emoji("error"),
                                    f"High Severity: {smell.pattern}",
                                    f"{smell.total_occurrences} occurrences detected.",
                                    "Address immediately to prevent token waste",
                                )
                            )
                            break  # Only add one
            except Exception:
                pass

            # ═══════════════════════════════════════════════════════════════
            # INSIGHTS Section
            # ═══════════════════════════════════════════════════════════════

            # 4. Cost Concentration (top 3 tools by cost share)
            try:
                tool_costs: Dict[str, float] = {}
                total_cost = 0.0
                for session in self.state.sessions[:50]:  # Last 50 sessions
                    total_cost += session.cost_estimate
                    # We'd need to load session details for tool breakdown
                    # For now, use session-level data

                if total_cost > 0:
                    # Get tool stats from loaded detail if available
                    if self._detail_data:
                        for tool_name, stats in self._detail_data.get("tool_stats", {}).items():
                            tool_costs[tool_name] = tool_costs.get(tool_name, 0) + stats.get(
                                "cost_estimate", 0
                            )

                    if tool_costs:
                        sorted_tools = sorted(tool_costs.items(), key=lambda x: x[1], reverse=True)[
                            :3
                        ]
                        top_3_pct = (
                            sum(c for _, c in sorted_tools) / total_cost * 100 if total_cost else 0
                        )
                        tools_str = ", ".join(
                            f"{t} ({c/total_cost*100:.0f}%)" for t, c in sorted_tools
                        )
                        insight_items.append(
                            (
                                ascii_emoji("money"),
                                "Cost Concentration",
                                f"Top tools account for {top_3_pct:.0f}% of token usage",
                                tools_str,
                            )
                        )
            except Exception:
                pass

            # 5. Cache efficiency insight
            try:
                # Calculate overall cache hit rate from sessions
                sessions_with_cache_data = [
                    s for s in self.state.sessions if hasattr(s, "accuracy_level")
                ]
                if sessions_with_cache_data:
                    insight_items.append(
                        (
                            ascii_emoji("info"),
                            "Session Accuracy",
                            f"{len([s for s in sessions_with_cache_data if s.accuracy_level == 'exact'])} of {len(sessions_with_cache_data)} sessions have exact token counts",
                            "Use Claude Code for native token accuracy",
                        )
                    )
            except Exception:
                pass

            # ═══════════════════════════════════════════════════════════════
            # Render Sections
            # ═══════════════════════════════════════════════════════════════

            # HIGH PRIORITY Section
            if high_priority_items:
                content.append(ascii_emoji("warning"), style=self.theme.error)
                content.append("  HIGH PRIORITY\n", style=f"bold {self.theme.error}")
                content.append("═" * 60 + "\n", style=self.theme.error)

                for icon, title, description, suggestion in high_priority_items:
                    content.append(f"{icon} ", style=self.theme.warning)
                    content.append(f"{title}\n", style=f"bold {self.theme.primary_text}")
                    content.append(f"   {description}\n", style=self.theme.dim_text)
                    content.append(
                        f"   {ascii_emoji('lightbulb')} {suggestion}\n\n", style=self.theme.info
                    )

            # INSIGHTS Section
            if insight_items:
                content.append(ascii_emoji("info"), style=self.theme.info)
                content.append("  INSIGHTS\n", style=f"bold {self.theme.info}")
                content.append("═" * 60 + "\n", style=self.theme.info)

                for icon, title, description, detail in insight_items:
                    content.append(f"{icon} ", style=self.theme.info)
                    content.append(f"{title}\n", style=f"bold {self.theme.primary_text}")
                    content.append(f"   {description}\n", style=self.theme.dim_text)
                    if detail:
                        content.append(f"   {detail}\n\n", style=self.theme.dim_text)
                    else:
                        content.append("\n")

            # POSITIVE TRENDS Section
            if positive_items:
                content.append(ascii_emoji("success"), style=self.theme.success)
                content.append("  POSITIVE TRENDS\n", style=f"bold {self.theme.success}")
                content.append("═" * 60 + "\n", style=self.theme.success)

                for icon, title, description in positive_items:
                    content.append(f"   {icon} {title}: ", style=self.theme.success)
                    content.append(f"{description}\n", style=self.theme.primary_text)

            # No issues - everything looks good!
            if not high_priority_items and not insight_items and not positive_items:
                content.append(ascii_emoji("success"), style=self.theme.success)
                content.append(" Everything looks good!\n\n", style=f"bold {self.theme.success}")
                content.append("   No urgent issues detected.\n", style=self.theme.dim_text)
                content.append("   Your MCP usage is efficient.\n", style=self.theme.dim_text)

            # Legacy recommendations (fallback)
            recommendations = self._generate_quick_recommendations()
            if recommendations and not high_priority_items:
                content.append("\n")
                content.append(ascii_emoji("lightbulb"), style=self.theme.warning)
                content.append(
                    " Optimization Suggestions\n", style=f"bold {self.theme.primary_text}"
                )
                content.append("─" * 50 + "\n\n", style=self.theme.dim_text)

                for icon, rec, confidence in recommendations[:3]:  # Limit to 3
                    conf_color = (
                        self.theme.success
                        if confidence >= 80
                        else self.theme.warning if confidence >= 60 else self.theme.dim_text
                    )
                    content.append(f"  {icon} ", style=conf_color)
                    content.append(f"{rec}\n", style=self.theme.primary_text)

        return Panel(
            content,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _get_smell_recommendation(self, pattern: str) -> str:
        """Get actionable recommendation for a smell pattern (v1.0.3 - task-233.7)."""
        recommendations = {
            "HIGH_VARIANCE": "Add result limits or pagination to reduce variance",
            "TOP_CONSUMER": "Consider caching or batching for this tool",
            "HIGH_MCP_SHARE": "Balance MCP usage with built-in tools",
            "CHATTY": "Batch operations or use more specific queries",
            "LOW_CACHE_HIT": "Review cache configuration and request patterns",
            "REDUNDANT_CALLS": "Cache results or deduplicate requests",
            "EXPENSIVE_FAILURES": "Add input validation before expensive calls",
            "UNDERUTILIZED_SERVER": "Consider removing unused server tools",
            "BURST_PATTERN": "Add rate limiting or request batching",
            "LARGE_PAYLOAD": "Break large operations into smaller chunks",
            "SEQUENTIAL_READS": "Use glob patterns or batch file operations",
            "CACHE_MISS_STREAK": "Pre-warm cache or adjust cache strategy",
            "CREDENTIAL_EXPOSURE": "Move credentials to environment variables",
            "SUSPICIOUS_TOOL_DESCRIPTION": "Review tool descriptions for safety",
            "UNUSUAL_DATA_FLOW": "Audit data flow for security concerns",
        }
        return recommendations.get(pattern, "Review and optimize this pattern")

    def _build_recommendations_footer(self) -> Text:
        """Build footer for recommendations view (v1.0.0)."""
        footer = Text()
        footer.append(
            "a=Ask AI  r=refresh  Esc=back  ?=help  q=quit",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

    # =========================================================================
    # v1.0.3 - Analytics View (task-233.3)
    # =========================================================================

    def _build_analytics_view(self) -> Panel:
        """Build the analytics time-series view (v1.0.3).

        Features:
        - Daily/Weekly/Monthly period toggle (d/w/m keys)
        - Table with date, sessions, tokens, cost, trend, smells
        - Period summary with totals and averages
        - Model breakdown panel
        """

        content = Text()

        # Header with mode indicator
        content.append("Analytics", style=f"bold {self.theme.title}")
        content.append(f"  v{__version__}", style=self.theme.dim_text)
        # v1.0.3 - task-233.10: Date filter badge
        date_badge = self._get_date_filter_badge()
        if date_badge:
            content.append(f"  [{date_badge}]", style=f"bold {self.theme.info}")
        content.append("\n")
        content.append(
            "[1]Dashboard [2]Sessions [3]Recs [4]Live [5]Analytics | [?]Help [q]Quit\n\n",
            style=self.theme.dim_text,
        )

        # Period toggle header
        periods = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
        period_line = Text()
        for key, label in [("d", "daily"), ("w", "weekly"), ("m", "monthly")]:
            if self.state.analytics_period == label:
                period_line.append(f"[{key}]", style=f"bold {self.theme.info}")
                period_line.append(f"{periods[label]}", style=f"bold {self.theme.info}")
            else:
                period_line.append(f"[{key}]", style=self.theme.dim_text)
                period_line.append(f"{periods[label]}", style=self.theme.dim_text)
            period_line.append("  ")

        # Group by project toggle
        if self.state.analytics_group_by_project:
            period_line.append("[g]", style=f"bold {self.theme.success}")
            period_line.append("Grouped", style=f"bold {self.theme.success}")
        else:
            period_line.append("[g]", style=self.theme.dim_text)
            period_line.append("Group", style=self.theme.dim_text)

        content.append(period_line)
        content.append("\n")
        # v1.0.3 - task-233.13: Responsive divider width
        divider_width = min(self._get_terminal_width() - 4, 78)
        content.append("─" * divider_width + "\n", style=self.theme.dim_text)

        # Get aggregated data based on period
        aggregated_data = self._get_analytics_data()

        if not aggregated_data:
            content.append("\n  No data for selected period\n", style=self.theme.dim_text)
        else:
            # v1.0.3 - task-233.13: Responsive column visibility
            show_trend = self._should_show_column("trend")
            show_smells = self._should_show_column("smells")
            show_share = self._should_show_column("share") and self.state.analytics_group_by_project
            is_grouped = self.state.analytics_group_by_project

            # v1.0.3 - task-233.11: Table header (different for grouped mode)
            if is_grouped:
                header = f"  {'Project':<14} {'Sessions':>9} {'Tokens':>10} {'Cost':>10}"
                if show_share:
                    header += f" {'Share':>7}"
            else:
                header = f"  {'Period':<14} {'Sessions':>9} {'Tokens':>10} {'Cost':>10}"
            if show_trend and not is_grouped:
                header += f" {'Trend':>8}"
            if show_smells:
                header += f" {'Smells':>8}"
            content.append(header + "\n", style=self.theme.dim_text)
            content.append("  " + "─" * (divider_width - 2) + "\n", style=self.theme.dim_text)

            # Calculate trends (compare to previous period - only for time-based views)
            prev_costs = [0.0] + [d["cost"] for d in aggregated_data[:-1]]

            # Table rows
            for i, row in enumerate(aggregated_data):
                is_selected = i == self.state.analytics_selected_index
                prefix = "▸" if is_selected else " "
                row_style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text

                # v1.0.3 - task-233.11: Format label with truncation for project names
                label = (
                    self._truncate_with_ellipsis(row["label"], 14)
                    if is_grouped
                    else row["label"][:14]
                )

                # Format tokens
                tokens_str = self._format_tokens(row["tokens"])

                content.append(f"{prefix} ", style=row_style)
                content.append(f"{label:<14}", style=row_style)
                content.append(f"{row['sessions']:>9}", style=row_style)
                content.append(f"{tokens_str:>10}", style=row_style)
                content.append(f"${row['cost']:>9.2f}", style=row_style)

                # v1.0.3 - task-233.11: Show share column for grouped mode
                if is_grouped and show_share:
                    cost_share = row.get("cost_share", 0)
                    content.append(f" {cost_share:>5.1f}%", style=row_style)

                # v1.0.3 - task-233.13: Responsive trend column (only for time-based views)
                if show_trend and not is_grouped:
                    if i > 0 and prev_costs[i] > 0:
                        change_pct = ((row["cost"] - prev_costs[i]) / prev_costs[i]) * 100
                        # Cost increases are bad (invert=True)
                        trend, trend_style = self._format_trend_indicator(change_pct, invert=True)
                    else:
                        trend = "—"
                        trend_style = self.theme.dim_text
                    content.append(f" {trend:>8}", style=trend_style)

                if show_smells:
                    content.append(f"{row['smells']:>8}", style=row_style)
                content.append("\n")

            # Summary section
            content.append("\n")
            content.append("─" * divider_width + "\n", style=self.theme.dim_text)

            total_sessions = sum(d["sessions"] for d in aggregated_data)
            total_tokens = sum(d["tokens"] for d in aggregated_data)
            total_cost = sum(d["cost"] for d in aggregated_data)
            total_smells = sum(d["smells"] for d in aggregated_data)
            avg_sessions = total_sessions / len(aggregated_data) if aggregated_data else 0
            avg_cost = total_cost / len(aggregated_data) if aggregated_data else 0

            # v1.0.3 - task-233.12: Use consistent formatting helpers
            content.append(ascii_emoji("📊"), style=self.theme.info)
            content.append(" Period Summary\n", style=f"bold {self.theme.primary_text}")
            content.append(
                f"  Total: {self._format_number(total_sessions)} sessions, ",
                style=self.theme.primary_text,
            )
            content.append(
                f"{self._format_tokens(total_tokens)} tokens, ", style=self.theme.primary_text
            )
            content.append(f"{self._format_cost(total_cost)} cost, ", style=self.theme.primary_text)
            content.append(
                f"{self._format_number(total_smells)} smells\n", style=self.theme.primary_text
            )
            content.append(
                f"  Average per period: {avg_sessions:.1f} sessions, ", style=self.theme.dim_text
            )
            content.append(f"{self._format_cost(avg_cost)} cost\n", style=self.theme.dim_text)

            # Model breakdown (top 3 models by tokens)
            model_usage = self._get_model_breakdown()
            if model_usage:
                content.append("\n")
                content.append(ascii_emoji("🤖"), style=self.theme.info)
                content.append(
                    " Model Breakdown (by tokens)\n", style=f"bold {self.theme.primary_text}"
                )
                for model, tokens, pct in model_usage[:3]:
                    bar_width = int(pct / 100 * 20)
                    bar = "█" * bar_width + "░" * (20 - bar_width)
                    content.append(f"  {model[:18]:<18} ", style=self.theme.primary_text)
                    content.append(f"{pct:>4.0f}% ", style=self.theme.primary_text)
                    content.append(bar, style=self.theme.info)
                    content.append("\n")

        return Panel(
            content,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _get_analytics_data(self) -> List[Dict[str, Any]]:
        """Get aggregated analytics data based on current period setting.

        Returns list of dicts with keys: label, sessions, tokens, cost, smells
        (and cost_share when grouped by project)
        """

        # v1.0.3 - task-233.11: Check for project grouping mode first
        if self.state.analytics_group_by_project:
            return self._get_analytics_data_grouped()

        if not self.state.sessions:
            return []

        today = datetime.now().date()
        data: List[Dict[str, Any]] = []

        if self.state.analytics_period == "daily":
            # Group by day (last 14 days)
            day_data: DefaultDict[str, Dict[str, Union[int, float]]] = defaultdict(
                lambda: {"sessions": 0, "tokens": 0, "cost": 0.0, "smells": 0}
            )
            for session in self.state.sessions:
                session_date = session.session_date.date()
                if session_date >= today - timedelta(days=13):
                    key = session_date.strftime("%Y-%m-%d")
                    day_data[key]["sessions"] += 1
                    day_data[key]["tokens"] += session.total_tokens
                    day_data[key]["cost"] += session.cost_estimate
                    day_data[key]["smells"] += session.smell_count

            # Sort by date
            for d in range(13, -1, -1):
                date_key = (today - timedelta(days=d)).strftime("%Y-%m-%d")
                if date_key in day_data:
                    weekday = (today - timedelta(days=d)).strftime("%a")
                    data.append(
                        {
                            "label": f"{date_key} ({weekday})",
                            **day_data[date_key],
                        }
                    )

        elif self.state.analytics_period == "weekly":
            # Group by ISO week (last 8 weeks)
            week_data: DefaultDict[str, Dict[str, Union[int, float]]] = defaultdict(
                lambda: {"sessions": 0, "tokens": 0, "cost": 0.0, "smells": 0}
            )
            for session in self.state.sessions:
                session_date = session.session_date.date()
                iso_year, iso_week, _ = session_date.isocalendar()
                if session_date >= today - timedelta(weeks=8):
                    key = f"{iso_year}-W{iso_week:02d}"
                    week_data[key]["sessions"] += 1
                    week_data[key]["tokens"] += session.total_tokens
                    week_data[key]["cost"] += session.cost_estimate
                    week_data[key]["smells"] += session.smell_count

            # Sort by week
            for key in sorted(week_data.keys()):
                data.append({"label": key, **week_data[key]})

        elif self.state.analytics_period == "monthly":
            # Group by month (last 6 months)
            month_data: DefaultDict[str, Dict[str, Union[int, float]]] = defaultdict(
                lambda: {"sessions": 0, "tokens": 0, "cost": 0.0, "smells": 0}
            )
            for session in self.state.sessions:
                session_date = session.session_date.date()
                if session_date >= today - timedelta(days=180):
                    key = session_date.strftime("%Y-%m")
                    month_data[key]["sessions"] += 1
                    month_data[key]["tokens"] += session.total_tokens
                    month_data[key]["cost"] += session.cost_estimate
                    month_data[key]["smells"] += session.smell_count

            # Sort by month
            for key in sorted(month_data.keys()):
                month_name = datetime.strptime(key, "%Y-%m").strftime("%b %Y")
                data.append({"label": month_name, **month_data[key]})

        return data

    def _get_filtered_sessions(self) -> List["SessionEntry"]:
        """Get sessions filtered by current date range.

        Returns sessions that fall within date_filter_start and date_filter_end
        if those filters are set.

        v1.0.3 - task-233.11
        """
        sessions = self.state.sessions
        if self.state.date_filter_start:
            sessions = [
                s for s in sessions if s.session_date.date() >= self.state.date_filter_start.date()
            ]
        if self.state.date_filter_end:
            sessions = [
                s for s in sessions if s.session_date.date() <= self.state.date_filter_end.date()
            ]
        return sessions

    def _get_analytics_data_grouped(self) -> List[Dict[str, Any]]:
        """Get analytics data grouped by project.

        Returns list of dicts with keys: label, sessions, tokens, cost, smells, cost_share

        v1.0.3 - task-233.11
        """

        sessions = self._get_filtered_sessions()
        if not sessions:
            return []

        project_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"sessions": 0, "tokens": 0, "cost": 0.0, "smells": 0}
        )

        for session in sessions:
            project = session.project or "(no project)"
            project_data[project]["sessions"] += 1
            project_data[project]["tokens"] += session.total_tokens
            project_data[project]["cost"] += session.cost_estimate
            project_data[project]["smells"] += session.smell_count

        total_cost = sum(p["cost"] for p in project_data.values())

        # Build result sorted by cost descending
        result = []
        for project, stats in sorted(
            project_data.items(), key=lambda x: x[1]["cost"], reverse=True
        ):
            cost_share = (stats["cost"] / total_cost * 100) if total_cost > 0 else 0
            result.append(
                {
                    "label": project,
                    "sessions": stats["sessions"],
                    "tokens": stats["tokens"],
                    "cost": stats["cost"],
                    "smells": stats["smells"],
                    "cost_share": cost_share,
                }
            )

        return result

    def _get_model_breakdown(self) -> List[Tuple[str, int, float]]:
        """Get model breakdown by token usage.

        Returns list of (model_name, tokens, percentage) tuples.
        """
        model_tokens: DefaultDict[str, int] = defaultdict(int)
        for session in self.state.sessions:
            model_name = session.model_name or "unknown"
            model_tokens[model_name] += session.total_tokens

        total_tokens = sum(model_tokens.values())
        if total_tokens == 0:
            return []

        # Sort by tokens descending
        sorted_models = sorted(model_tokens.items(), key=lambda x: x[1], reverse=True)
        return [(model, tokens, (tokens / total_tokens) * 100) for model, tokens in sorted_models]

    def _build_analytics_footer(self) -> Text:
        """Build footer for analytics view (v1.0.3)."""
        footer = Text()
        # v1.0.3 - task-233.11: Show g=ungroup when in grouped mode
        group_key = "g=ungroup" if self.state.analytics_group_by_project else "g=group"
        footer.append(
            f"j/k=nav  d=daily  w=weekly  m=monthly  {group_key}  Enter=drill  ?=help  q=quit",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

    def _handle_analytics_key(self, key: str) -> bool:
        """Handle key in analytics view (v1.0.3 - task-233.3)."""
        aggregated_data = self._get_analytics_data()
        max_index = len(aggregated_data) - 1 if aggregated_data else 0

        if key in (KEY_DOWN, "j"):
            self.state.analytics_selected_index = min(
                self.state.analytics_selected_index + 1, max_index
            )
        elif key in (KEY_UP, "k"):
            self.state.analytics_selected_index = max(self.state.analytics_selected_index - 1, 0)
        elif key == "d":
            self.state.analytics_period = "daily"
            self.state.analytics_selected_index = 0
        elif key == "w":
            self.state.analytics_period = "weekly"
            self.state.analytics_selected_index = 0
        elif key == "m":
            self.state.analytics_period = "monthly"
            self.state.analytics_selected_index = 0
        elif key == "g":
            self.state.analytics_group_by_project = not self.state.analytics_group_by_project
            self.state.analytics_selected_index = 0
        elif key == KEY_ENTER:
            # v1.0.3 - task-233.11: Drill into selected period or project
            if aggregated_data and 0 <= self.state.analytics_selected_index < len(aggregated_data):
                selected_row = aggregated_data[self.state.analytics_selected_index]
                if self.state.analytics_group_by_project:
                    # Drill into project - set search query and switch to LIST
                    self.state.search_query = selected_row["label"]
                    self.state.mode = BrowserMode.LIST
                else:
                    # Switch to LIST mode with date filter
                    # Future: Set date filter based on selected row
                    self.state.mode = BrowserMode.LIST
        elif key == KEY_ESC:
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "?":
            self.state.navigation_history.append(self.state.mode)
            self.state.mode = BrowserMode.HELP
        elif key == "q":
            return True  # Exit

        return False

    # =========================================================================
    # v1.0.3 - Start Tracking Modal (task-233.2)
    # =========================================================================

    def _build_start_tracking_modal(self) -> Panel:
        """Build the Start Tracking platform selection modal (v1.0.3).

        Uses centered modal with platform options:
        - Claude Code (native tokens)
        - Codex CLI (tiktoken)
        - Gemini CLI (95%+ accuracy)
        """
        from rich.align import Align

        content = Text()

        # Title
        content.append("Start Tracking\n\n", style=f"bold {self.theme.title}")

        # Platform options with selection indicator
        platforms = [
            ("Claude Code", "(native tokens)", "claude-code"),
            ("Codex CLI", "(tiktoken)", "codex-cli"),
            ("Gemini CLI", "(95%+ accuracy)", "gemini-cli"),
        ]

        for i, (label, description, _) in enumerate(platforms):
            is_selected = i == self.state.start_tracking_platform_index
            if is_selected:
                indicator = "●"  # Filled circle
                style = f"bold {self.theme.info}"
            else:
                indicator = "○"  # Empty circle
                style = self.theme.primary_text

            # Number prefix for quick selection
            content.append(f"  [{i + 1}] {indicator} ", style=style)
            content.append(label, style=style)
            content.append(f"  {description}\n", style=self.theme.dim_text)

        content.append("\n")

        # Project auto-detection hint
        try:
            import os

            cwd = os.getcwd()
            project_name = os.path.basename(cwd)
            content.append(f"  Project: {project_name}\n", style=self.theme.dim_text)
        except Exception:
            pass

        content.append("\n")

        # Footer with keybinds
        footer = Text()
        footer.append("[Enter]", style=f"bold {self.theme.info}")
        footer.append(" Start  ", style=self.theme.dim_text)
        footer.append("[1-3]", style=f"bold {self.theme.dim_text}")
        footer.append(" Quick select  ", style=self.theme.dim_text)
        footer.append("[Esc]", style=f"bold {self.theme.dim_text}")
        footer.append(" Cancel", style=self.theme.dim_text)
        content.append(footer)

        inner_panel = Panel(
            content,
            title="Select Platform",
            border_style=self.theme.info,
            box=self.box_style,
            width=50,
            padding=(1, 2),
        )

        # Center the modal vertically and horizontally
        return Panel(
            Align.center(inner_panel, vertical="middle"),
            border_style=self.theme.dim_text,
            box=box.SIMPLE,
        )

    def _handle_start_tracking_modal_key(self, key: str) -> bool:
        """Handle key in Start Tracking modal (v1.0.3 - task-233.2)."""
        platforms = ["claude-code", "codex-cli", "gemini-cli"]
        max_index = len(platforms) - 1

        if key in (KEY_DOWN, "j"):
            self.state.start_tracking_platform_index = min(
                self.state.start_tracking_platform_index + 1, max_index
            )
        elif key in (KEY_UP, "k"):
            self.state.start_tracking_platform_index = max(
                self.state.start_tracking_platform_index - 1, 0
            )
        elif key in ("1", "2", "3"):
            # Quick select by number
            self.state.start_tracking_platform_index = int(key) - 1
            self._start_tracking()
        elif key == KEY_ENTER:
            self._start_tracking()
        elif key == KEY_ESC:
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "q":
            return True  # Exit

        return False

    def _start_tracking(self) -> None:
        """Start token-audit collect subprocess and switch to LIVE view."""
        import subprocess

        platforms = ["claude-code", "codex-cli", "gemini-cli"]
        platform = platforms[self.state.start_tracking_platform_index]

        try:
            # Spawn collect subprocess in background
            # Use token-audit collect --platform <platform>
            subprocess.Popen(
                ["token-audit", "collect", "--platform", platform],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process
            )

            # Switch to LIVE mode to monitor
            self.state.mode = BrowserMode.LIVE

            # Show notification
            self.show_notification(f"Started tracking for {platform}", "success")
        except FileNotFoundError:
            # token-audit not in PATH
            self.show_notification("Error: token-audit command not found", "error")
            self.state.mode = BrowserMode.DASHBOARD
        except Exception as e:
            self.show_notification(f"Error starting tracking: {str(e)[:30]}", "error")
            self.state.mode = BrowserMode.DASHBOARD

    # =========================================================================
    # v1.0.3 - task-233.6: Delete Session Modal
    # =========================================================================

    def _initiate_delete_session(self) -> None:
        """Initiate session deletion with confirmation modal (v1.0.3 - task-233.6).

        Checks if the session is active before allowing deletion.
        """
        if not self.state.sessions:
            self.show_notification("No session selected", "warning")
            return

        entry = self.state.sessions[self.state.selected_index]

        # Check if session is active (cannot delete live sessions)
        try:
            from ..storage import StreamingStorage

            streaming = StreamingStorage()
            if streaming.has_active_session(entry.path.stem):
                self.show_notification("Cannot delete active session", "error")
                return
        except Exception:
            pass  # If check fails, allow deletion attempt

        # Store target and show confirmation modal
        self.state.delete_target_session = entry
        self.state.mode = BrowserMode.DELETE_CONFIRM_MODAL

    def _handle_delete_confirm_modal_key(self, key: str) -> bool:
        """Handle key in Delete Confirmation modal (v1.0.3 - task-233.6)."""
        if key in ("y", "Y"):
            self._execute_delete_session()
        elif key in ("n", "N", KEY_ESC):
            self.state.mode = BrowserMode.LIST
            self.state.delete_target_session = None
        elif key == "q":
            return True  # Exit browser

        return False

    def _execute_delete_session(self) -> None:
        """Execute the session deletion (v1.0.3 - task-233.6)."""
        session = self.state.delete_target_session
        if session is None:
            self.state.mode = BrowserMode.LIST
            return

        try:
            # Delete session file
            session.path.unlink()

            # Delete associated .jsonl file if exists
            jsonl_path = session.path.with_suffix(".jsonl")
            if jsonl_path.exists():
                jsonl_path.unlink()

            self.show_notification("Session deleted", "success")

            # Refresh the sessions list
            self._load_sessions()

        except PermissionError:
            self.show_notification("Permission denied - file may be locked", "error")
        except FileNotFoundError:
            self.show_notification("Session file not found", "error")
        except OSError as e:
            self.show_notification(f"Delete failed: {str(e)[:30]}", "error")
        finally:
            self.state.mode = BrowserMode.LIST
            self.state.delete_target_session = None

    def _build_delete_confirm_modal(self) -> Panel:
        """Build the Delete Session confirmation modal (v1.0.3 - task-233.6).

        Displays session details and asks for confirmation.
        """
        from rich.align import Align

        content = Text()
        session = self.state.delete_target_session

        # Title
        content.append("Delete Session\n\n", style=f"bold {self.theme.error}")

        if session is None:
            content.append("No session selected.\n", style=self.theme.dim_text)
        else:
            # Confirmation message
            content.append("Are you sure you want to delete?\n\n", style=self.theme.primary_text)

            # Session details
            session_id = (
                session.path.stem[:12] + "..." if len(session.path.stem) > 15 else session.path.stem
            )
            date_str = session.session_date.strftime("%b %d, %Y at %I:%M %p")

            content.append("  Session:   ", style=self.theme.dim_text)
            content.append(f"{session_id}\n", style=self.theme.primary_text)

            content.append("  Date:      ", style=self.theme.dim_text)
            content.append(f"{date_str}\n", style=self.theme.primary_text)

            content.append("  Platform:  ", style=self.theme.dim_text)
            content.append(f"{session.platform}\n", style=self.theme.primary_text)

            content.append("  Tokens:    ", style=self.theme.dim_text)
            content.append(f"{session.total_tokens:,}\n", style=self.theme.primary_text)

            content.append("  Cost:      ", style=self.theme.dim_text)
            content.append(f"${session.cost_estimate:.2f}\n", style=self.theme.primary_text)

            content.append("\n")

            # Warning
            warning = ascii_emoji("warning") + " "
            content.append(f"  {warning}", style=self.theme.warning)
            content.append("This action cannot be undone.\n", style=self.theme.warning)

        content.append("\n")

        # Footer with keybinds
        footer = Text()
        footer.append("[y]", style=f"bold {self.theme.error}")
        footer.append(" Yes, Delete    ", style=self.theme.dim_text)
        footer.append("[n]", style=f"bold {self.theme.dim_text}")
        footer.append(" Cancel", style=self.theme.dim_text)
        content.append(footer)

        inner_panel = Panel(
            content,
            title="Confirm Deletion",
            border_style=self.theme.error,
            box=self.box_style,
            width=50,
            padding=(1, 2),
        )

        # Center the modal vertically and horizontally
        return Panel(
            Align.center(inner_panel, vertical="middle"),
            border_style=self.theme.dim_text,
            box=box.SIMPLE,
        )

    # =========================================================================
    # v1.0.3 - task-233.10: Date Range Filter Modal
    # =========================================================================

    # Date presets: (label, days_back_start, days_back_end)
    # None means no limit (all time)
    DATE_PRESETS: List[tuple[str, Optional[int], Optional[int]]] = [
        ("Today", 0, 0),
        ("Yesterday", 1, 1),
        ("Last 7 days", 7, 0),
        ("Last 14 days", 14, 0),
        ("Last 30 days", 30, 0),
        ("Last 60 days", 60, 0),
        ("This month", None, None),  # Special handling
        ("Last month", None, None),  # Special handling
        ("All time", None, None),
    ]

    def _build_date_filter_modal(self) -> Panel:
        """Build the Date Range Filter modal (v1.0.3 - task-233.10).

        Displays preset options (0-8) for quick date filtering.
        Custom date input deferred to v1.0.4.
        """
        from rich.align import Align

        content = Text()

        # Title
        content.append("Date Range Filter\n\n", style=f"bold {self.theme.title}")

        # Quick presets with selection indicator
        content.append("  Quick Presets:\n", style=self.theme.dim_text)

        for i, (label, _, _) in enumerate(self.DATE_PRESETS):
            is_selected = i == self.state.date_filter_preset_index
            if is_selected:
                indicator = "●"  # Filled circle
                style = f"bold {self.theme.info}"
            else:
                indicator = "○"  # Empty circle
                style = self.theme.primary_text

            # Layout in two columns for compactness
            num_key = str(i + 1) if i < 8 else "0"
            content.append(f"  [{num_key}] {indicator} ", style=style)
            content.append(f"{label:<15}", style=style)
            if i % 2 == 1 or i == len(self.DATE_PRESETS) - 1:
                content.append("\n")

        content.append("\n")

        # Current filter status
        content.append("  Current: ", style=self.theme.dim_text)
        if self.state.date_filter_start or self.state.date_filter_end:
            badge = self._get_date_filter_badge()
            content.append(badge, style=f"bold {self.theme.info}")
        else:
            content.append("All time (no filter)", style=self.theme.primary_text)
        content.append("\n\n")

        # Footer with keybinds
        footer = Text()
        footer.append("[1-8,0]", style=f"bold {self.theme.info}")
        footer.append(" Select  ", style=self.theme.dim_text)
        footer.append("[c]", style=f"bold {self.theme.dim_text}")
        footer.append(" Clear  ", style=self.theme.dim_text)
        footer.append("[Esc]", style=f"bold {self.theme.dim_text}")
        footer.append(" Cancel", style=self.theme.dim_text)
        content.append(footer)

        inner_panel = Panel(
            content,
            title="Filter by Date",
            border_style=self.theme.info,
            box=self.box_style,
            width=50,
            padding=(1, 2),
        )

        # Center the modal vertically and horizontally
        return Panel(
            Align.center(inner_panel, vertical="middle"),
            border_style=self.theme.dim_text,
            box=box.SIMPLE,
        )

    def _handle_date_filter_modal_key(self, key: str) -> bool:
        """Handle key in Date Range Filter modal (v1.0.3 - task-233.10)."""

        max_index = len(self.DATE_PRESETS) - 1

        if key in (KEY_DOWN, "j"):
            self.state.date_filter_preset_index = min(
                self.state.date_filter_preset_index + 1, max_index
            )
        elif key in (KEY_UP, "k"):
            self.state.date_filter_preset_index = max(self.state.date_filter_preset_index - 1, 0)
        elif key in ("1", "2", "3", "4", "5", "6", "7", "8"):
            # Quick select by number (1-8 map to indices 0-7)
            self.state.date_filter_preset_index = int(key) - 1
            self._apply_date_filter()
        elif key == "0":
            # 0 selects "All time" (last preset)
            self.state.date_filter_preset_index = max_index
            self._apply_date_filter()
        elif key == KEY_ENTER:
            self._apply_date_filter()
        elif key in ("c", "C"):
            # Clear filter
            self.state.date_filter_start = None
            self.state.date_filter_end = None
            self.show_notification("Date filter cleared", "success")
            self.state.mode = BrowserMode.DASHBOARD
            self._load_sessions()
        elif key == KEY_ESC:
            self.state.mode = BrowserMode.DASHBOARD
        elif key == "q":
            return True  # Exit browser

        return False

    def _apply_date_filter(self) -> None:
        """Apply the selected date filter preset (v1.0.3 - task-233.10)."""

        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        idx = self.state.date_filter_preset_index
        label, days_start, days_end = self.DATE_PRESETS[idx]

        if label == "All time":
            self.state.date_filter_start = None
            self.state.date_filter_end = None
        elif label == "This month":
            self.state.date_filter_start = today.replace(day=1)
            self.state.date_filter_end = now
        elif label == "Last month":
            first_of_this = today.replace(day=1)
            last_of_prev = first_of_this - timedelta(days=1)
            first_of_prev = last_of_prev.replace(day=1)
            self.state.date_filter_start = first_of_prev
            self.state.date_filter_end = last_of_prev.replace(hour=23, minute=59, second=59)
        else:
            # Standard days-based presets
            if days_start is not None:
                self.state.date_filter_start = today - timedelta(days=days_start)
            else:
                self.state.date_filter_start = None

            if days_end is not None:
                if days_end == 0:
                    self.state.date_filter_end = now
                else:
                    end_date = today - timedelta(days=days_end)
                    self.state.date_filter_end = end_date.replace(hour=23, minute=59, second=59)
            else:
                self.state.date_filter_end = None

        # Show notification and return to previous view
        self.show_notification(f"Filter: {label}", "success")
        self.state.mode = BrowserMode.DASHBOARD
        self._load_sessions()

    def _get_date_filter_badge(self) -> str:
        """Get a compact badge string for the current date filter (v1.0.3 - task-233.10)."""
        start = self.state.date_filter_start
        end = self.state.date_filter_end

        if start is None and end is None:
            return ""

        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if it matches a known preset
        if start and end:
            days_diff = (today - start.replace(hour=0, minute=0, second=0, microsecond=0)).days
            if days_diff == 0 and end.date() == now.date():
                return "Today"
            elif days_diff == 1 and (end.date() - start.date()).days == 0:
                return "Yesterday"
            elif days_diff == 7:
                return "Last 7d"
            elif days_diff == 14:
                return "Last 14d"
            elif days_diff == 30:
                return "Last 30d"
            elif days_diff == 60:
                return "Last 60d"

        # Fallback to date range format
        if start and end:
            return f"{start.strftime('%b %d')}-{end.strftime('%b %d')}"
        elif start:
            return f"Since {start.strftime('%b %d')}"
        elif end:
            return f"Until {end.strftime('%b %d')}"
        else:
            return ""

    # =========================================================================
    # v1.0.3 - task-233.5: Smell Trends View
    # =========================================================================

    def _load_smell_trends(self) -> None:
        """Load smell aggregation data for trends view (v1.0.3 - task-233.5)."""
        try:
            agg = SmellAggregator()
            self.state.smell_trends_data = agg.aggregate(
                days=self.state.smell_trends_days,
                platform=self.state.filter_platform if self.state.filter_platform else None,
            )
        except Exception as e:
            self.state.smell_trends_data = None
            self.show_notification(f"Error loading smell trends: {str(e)[:30]}", "error")

    def _handle_smell_trends_key(self, key: str) -> bool:
        """Handle key in Smell Trends view (v1.0.3 - task-233.5)."""
        if key in ("q", "Q"):
            return True
        elif key in (KEY_UP, "k"):
            self.state.smell_trends_selected_index = max(
                self.state.smell_trends_selected_index - 1, 0
            )
        elif key in (KEY_DOWN, "j"):
            # Limit to available smells
            if self.state.smell_trends_data:
                max_index = len(self.state.smell_trends_data.aggregated_smells) - 1
                self.state.smell_trends_selected_index = min(
                    self.state.smell_trends_selected_index + 1, max(0, max_index)
                )
        elif key == KEY_ENTER:
            # Navigate to sessions list filtered by selected smell
            if self.state.smell_trends_data and self.state.smell_trends_data.aggregated_smells:
                idx = self.state.smell_trends_selected_index
                if idx < len(self.state.smell_trends_data.aggregated_smells):
                    smell = self.state.smell_trends_data.aggregated_smells[idx]
                    # Set search query to smell pattern for filtering
                    self.state.search_query = f"smell:{smell.pattern}"
                    self.state.mode = BrowserMode.LIST
                    self._load_sessions()
        elif key == "d":
            # Cycle days filter: 7 -> 14 -> 30 -> 90 -> 7
            days_cycle = [7, 14, 30, 90]
            current_idx = (
                days_cycle.index(self.state.smell_trends_days)
                if self.state.smell_trends_days in days_cycle
                else 2
            )
            self.state.smell_trends_days = days_cycle[(current_idx + 1) % len(days_cycle)]
            self._load_smell_trends()
            self.show_notification(f"Showing last {self.state.smell_trends_days} days", "info")
        elif key == "r":
            # Refresh data
            self._load_smell_trends()
            self.show_notification("Smell trends refreshed", "success")
        elif key == KEY_ESC:
            self.state.mode = BrowserMode.DASHBOARD
        elif key in ("a", "A"):
            # AI export
            self._export_smell_trends_ai_prompt()
        return False

    def _build_smell_trends_view(self) -> Panel:
        """Build the Smell Trends view (v1.0.3 - task-233.5).

        Shows cross-session smell pattern analysis with frequency and trends.
        """
        content = Text()

        # Header
        title_icon = ascii_emoji("chart")
        content.append(f"{title_icon} Smell Trends\n", style=f"bold {self.theme.title}")
        content.append(
            f"Last {self.state.smell_trends_days} days",
            style=self.theme.dim_text,
        )
        if self.state.filter_platform:
            content.append(f" • {self.state.filter_platform}", style=self.theme.dim_text)
        # v1.0.3 - task-233.10: Date filter badge
        date_badge = self._get_date_filter_badge()
        if date_badge:
            content.append(f" • [{date_badge}]", style=f"bold {self.theme.info}")
        content.append("\n\n")

        data = self.state.smell_trends_data

        if data is None:
            content.append("Loading smell trends...\n", style=self.theme.dim_text)
        elif not data.aggregated_smells:
            content.append(
                "No smell patterns detected in this period.\n", style=self.theme.dim_text
            )
            content.append("\nThis is good! Your sessions are healthy.\n", style=self.theme.success)
        else:
            # Summary stats
            content.append(f"Sessions analyzed: {data.total_sessions}  ", style=self.theme.dim_text)
            content.append(
                f"Sessions with smells: {data.sessions_with_smells}\n\n",
                style=self.theme.dim_text,
            )

            # v1.0.3 - task-233.13: Responsive layout
            divider_width = min(self._get_terminal_width() - 4, 75)
            show_trend_col = self._should_show_column("trend")

            # Table header
            content.append("  ", style=self.theme.dim_text)
            content.append(f"{'Pattern':<20}", style=f"bold {self.theme.primary_text}")
            content.append(f"{'Freq':>8}", style=f"bold {self.theme.primary_text}")
            if show_trend_col:
                content.append(f"{'Trend':>10}", style=f"bold {self.theme.primary_text}")
            content.append(f"{'Severity':>12}", style=f"bold {self.theme.primary_text}")
            content.append(f"  {'Top Tool':<20}\n", style=f"bold {self.theme.primary_text}")
            content.append("─" * divider_width + "\n", style=self.theme.dim_text)

            # Smell rows
            for i, smell in enumerate(data.aggregated_smells):
                is_selected = i == self.state.smell_trends_selected_index

                # Selection indicator
                if is_selected:
                    content.append("▶ ", style=f"bold {self.theme.info}")
                else:
                    content.append("  ", style=self.theme.dim_text)

                # Pattern name (truncated)
                pattern = smell.pattern[:18] if len(smell.pattern) > 18 else smell.pattern
                style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
                content.append(f"{pattern:<20}", style=style)

                # Frequency
                freq_style = (
                    self.theme.warning if smell.frequency_percent > 50 else self.theme.primary_text
                )
                content.append(f"{smell.frequency_percent:>6.1f}%", style=freq_style)

                # Trend indicator (v1.0.3 - task-233.13: conditional on terminal width)
                if show_trend_col:
                    if smell.trend == "worsening":
                        trend_icon = " ▲"
                        trend_style = self.theme.error
                    elif smell.trend == "improving":
                        trend_icon = " ▼"
                        trend_style = self.theme.success
                    else:
                        trend_icon = " →"
                        trend_style = self.theme.dim_text
                    content.append(f"{trend_icon:>10}", style=trend_style)

                # Severity indicator
                severity = self._get_dominant_severity(smell.severity_breakdown)
                if severity in ("high", "critical"):
                    sev_indicator = "●●●"
                    sev_style = self.theme.error
                elif severity == "medium":
                    sev_indicator = "●●○"
                    sev_style = self.theme.warning
                else:
                    sev_indicator = "●○○"
                    sev_style = self.theme.dim_text
                content.append(f"{sev_indicator:>12}", style=sev_style)

                # Top tool
                if smell.top_tools:
                    top_tool = (
                        smell.top_tools[0][0][:18]
                        if len(smell.top_tools[0][0]) > 18
                        else smell.top_tools[0][0]
                    )
                else:
                    top_tool = "-"
                content.append(f"  {top_tool:<20}\n", style=self.theme.dim_text)

            # Detail panel for selected smell
            if data.aggregated_smells:
                idx = self.state.smell_trends_selected_index
                if idx < len(data.aggregated_smells):
                    smell = data.aggregated_smells[idx]
                    content.append("\n")
                    # v1.0.3 - task-233.13: Responsive divider
                    content.append("─" * divider_width + "\n", style=self.theme.dim_text)
                    content.append(f"  {smell.pattern}\n", style=f"bold {self.theme.info}")

                    # Description (generate from pattern)
                    desc = self._get_smell_description(smell.pattern)
                    content.append(f"  {desc}\n\n", style=self.theme.dim_text)

                    # Stats
                    content.append(
                        f"  Occurrences: {smell.total_occurrences}  ", style=self.theme.dim_text
                    )
                    content.append(
                        f"Sessions: {smell.sessions_affected}/{smell.total_sessions}  ",
                        style=self.theme.dim_text,
                    )
                    if smell.trend_change_percent != 0:
                        sign = "+" if smell.trend_change_percent > 0 else ""
                        content.append(
                            f"Change: {sign}{smell.trend_change_percent:.1f}%\n",
                            style=self.theme.dim_text,
                        )
                    else:
                        content.append("\n")

                    # Affected tools
                    if smell.top_tools:
                        content.append("  Top tools: ", style=self.theme.dim_text)
                        tools_str = ", ".join(f"{t[0]} ({t[1]})" for t in smell.top_tools[:3])
                        content.append(f"{tools_str}\n", style=self.theme.primary_text)

        return Panel(
            content,
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_smell_trends_footer(self) -> Panel:
        """Build footer for Smell Trends view (v1.0.3 - task-233.5)."""
        content = Text()
        content.append("[j/k]", style=f"bold {self.theme.dim_text}")
        content.append(" Navigate  ", style=self.theme.dim_text)
        content.append("[Enter]", style=f"bold {self.theme.dim_text}")
        content.append(" View sessions  ", style=self.theme.dim_text)
        content.append("[d]", style=f"bold {self.theme.dim_text}")
        content.append(f" Days ({self.state.smell_trends_days})  ", style=self.theme.dim_text)
        content.append("[r]", style=f"bold {self.theme.dim_text}")
        content.append(" Refresh  ", style=self.theme.dim_text)
        content.append("[a]", style=f"bold {self.theme.dim_text}")
        content.append(" AI export  ", style=self.theme.dim_text)
        content.append("[q]", style=f"bold {self.theme.dim_text}")
        content.append(" Quit", style=self.theme.dim_text)

        return Panel(
            content,
            border_style=self.theme.dim_text,
            box=box.SIMPLE,
        )

    def _get_dominant_severity(self, severity_breakdown: Dict[str, int]) -> str:
        """Get the most common severity from breakdown (v1.0.3 - task-233.5)."""
        if not severity_breakdown:
            return "low"
        # Priority order: critical > high > medium > warning > low > info
        priority = ["critical", "high", "medium", "warning", "low", "info"]
        for sev in priority:
            if severity_breakdown.get(sev, 0) > 0:
                return sev
        return "low"

    def _get_smell_description(self, pattern: str) -> str:
        """Get human-readable description for a smell pattern (v1.0.3 - task-233.5)."""
        descriptions = {
            "HIGH_VARIANCE": "Token counts vary significantly across calls",
            "TOP_CONSUMER": "This tool consumes >50% of session tokens",
            "HIGH_MCP_SHARE": "MCP tools account for >80% of tokens",
            "CHATTY": "More than 20 calls to this tool in a session",
            "LOW_CACHE_HIT": "Cache efficiency below 30%",
            "REDUNDANT_CALLS": "Identical calls made multiple times",
            "EXPENSIVE_FAILURES": "Failed calls consuming >5000 tokens",
            "UNDERUTILIZED_SERVER": "Server tool utilization below 10%",
            "BURST_PATTERN": "More than 5 calls within 1 second",
            "LARGE_PAYLOAD": "Single call exceeds 10K tokens",
            "SEQUENTIAL_READS": "3+ consecutive file read operations",
            "CACHE_MISS_STREAK": "5+ consecutive cache misses",
            "CREDENTIAL_EXPOSURE": "Potential hardcoded credentials detected",
            "SUSPICIOUS_TOOL_DESCRIPTION": "Tool description may contain injection",
            "UNUSUAL_DATA_FLOW": "Large reads followed by external calls",
        }
        return descriptions.get(pattern, "Unknown smell pattern")

    def _export_smell_trends_ai_prompt(self) -> None:
        """Export smell trends for AI analysis (v1.0.3 - task-233.5)."""
        data = self.state.smell_trends_data
        if not data:
            self.show_notification("No smell trends data to export", "warning")
            return

        # Build markdown prompt
        prompt = f"""# Token Audit Smell Trends Analysis

## Overview
- Period: Last {self.state.smell_trends_days} days
- Sessions analyzed: {data.total_sessions}
- Sessions with smells: {data.sessions_with_smells}
- Platform: {self.state.filter_platform if self.state.filter_platform else 'All'}

## Detected Patterns

"""
        for smell in data.aggregated_smells:
            trend_arrow = (
                "↑" if smell.trend == "worsening" else ("↓" if smell.trend == "improving" else "→")
            )
            prompt += f"""### {smell.pattern}
- Frequency: {smell.frequency_percent:.1f}% ({smell.sessions_affected}/{smell.total_sessions} sessions)
- Trend: {smell.trend} {trend_arrow} ({smell.trend_change_percent:+.1f}%)
- Total occurrences: {smell.total_occurrences}
- Description: {self._get_smell_description(smell.pattern)}
"""
            if smell.top_tools:
                prompt += f"- Top affected tools: {', '.join(t[0] for t in smell.top_tools[:3])}\n"
            prompt += "\n"

        prompt += """## Analysis Request
Please analyze these smell patterns and provide:
1. Priority ranking of issues to address
2. Specific recommendations for each pattern
3. Estimated token savings if addressed
4. Any correlations between patterns
"""

        try:
            import subprocess

            subprocess.run(["pbcopy"], input=prompt.encode(), check=True)
            self.show_notification("Smell trends copied to clipboard", "success")
        except Exception:
            self.show_notification("Export failed - clipboard not available", "error")

    # =========================================================================
    # v1.0.3 - task-233.8: Pinned Servers View
    # =========================================================================

    def _load_pinned_servers(self) -> None:
        """Load pinned servers data for display (v1.0.3 - task-233.8)."""
        from token_audit.pinned_config import PinnedConfigManager

        try:
            manager = PinnedConfigManager()
            pinned_entries = manager.list()

            # Build display data with usage aggregation from recent sessions
            pinned_data = []
            server_usage: Dict[str, int] = {}

            # Aggregate usage from loaded sessions
            for session in self.state.sessions:
                try:
                    session_data = self._load_session_data(session.path)
                    if session_data and "token_usage" in session_data:
                        for server_name, tools in session_data["token_usage"].items():
                            if isinstance(tools, dict):
                                for tool_name, tool_data in tools.items():
                                    if isinstance(tool_data, dict) and "call_count" in tool_data:
                                        server_usage[server_name] = (
                                            server_usage.get(server_name, 0)
                                            + tool_data["call_count"]
                                        )
                except Exception:
                    continue

            # Create display entries
            for entry in pinned_entries:
                pinned_data.append(
                    {
                        "name": entry.name,
                        "source": "explicit",
                        "notes": entry.notes or "",
                        "usage": server_usage.get(entry.name, 0),
                    }
                )

            self.state.pinned_servers_data = pinned_data

            # Build list of available (unpinned) servers from session data
            all_servers = set(server_usage.keys())
            pinned_names = {e.name for e in pinned_entries}
            self.state.available_servers_for_add = sorted(all_servers - pinned_names)

        except Exception as e:
            self.state.pinned_servers_data = []
            self.state.available_servers_for_add = []
            self.show_notification(f"Failed to load pinned servers: {e}", "error")

    def _build_pinned_servers_view(self) -> Panel:
        """Build the Pinned Servers view (v1.0.3 - task-233.8)."""
        content = Text()

        # Header
        title_icon = ascii_emoji("pin")
        content.append(f"{title_icon} Pinned Servers\n", style=f"bold {self.theme.title}")
        content.append("Servers marked for focused analysis\n", style=self.theme.dim_text)
        # v1.0.3 - task-233.10: Date filter badge
        date_badge = self._get_date_filter_badge()
        if date_badge:
            content.append(f"[{date_badge}]", style=f"bold {self.theme.info}")
        content.append("\n\n")

        data = self.state.pinned_servers_data

        if data is None:
            content.append("Loading pinned servers...\n", style=self.theme.dim_text)
        elif not data:
            content.append("No servers pinned yet.\n\n", style=self.theme.dim_text)
            content.append("Press [a] to add a server, or use:\n", style=self.theme.dim_text)
            content.append("  token-audit pin <server-name>\n", style=self.theme.info)
            if self.state.available_servers_for_add:
                content.append(
                    f"\nAvailable servers ({len(self.state.available_servers_for_add)}):\n",
                    style=self.theme.dim_text,
                )
                for server in self.state.available_servers_for_add[:10]:
                    content.append(f"  • {server}\n", style=self.theme.primary_text)
                if len(self.state.available_servers_for_add) > 10:
                    content.append(
                        f"  ... and {len(self.state.available_servers_for_add) - 10} more\n",
                        style=self.theme.dim_text,
                    )
        else:
            # v1.0.3 - task-233.13: Responsive layout
            divider_width = min(self._get_terminal_width() - 4, 80)
            is_narrow = self._is_narrow_terminal()
            show_notes = self._should_show_column("notes")
            server_width = 24 if is_narrow else 30
            source_width = 10 if is_narrow else 12
            notes_width = 20 if is_narrow else 25

            # Table header
            content.append("  ", style=self.theme.dim_text)
            content.append(f"{'Server':<{server_width}}", style=f"bold {self.theme.primary_text}")
            content.append(f"{'Source':>{source_width}}", style=f"bold {self.theme.primary_text}")
            content.append(f"{'Usage':>10}", style=f"bold {self.theme.primary_text}")
            if show_notes:
                content.append(
                    f"  {'Notes':<{notes_width}}\n", style=f"bold {self.theme.primary_text}"
                )
            else:
                content.append("\n")
            content.append("─" * divider_width + "\n", style=self.theme.dim_text)

            # Server rows
            server_info: Dict[str, Any]
            for i, server_info in enumerate(data):
                is_selected = i == self.state.pinned_servers_selected_index

                # Selection indicator
                if is_selected:
                    content.append("▶ ", style=f"bold {self.theme.info}")
                else:
                    content.append("  ", style=self.theme.dim_text)

                row_style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text

                # v1.0.3 - task-233.13: Format server name with responsive truncation
                name = self._truncate_with_ellipsis(server_info["name"], server_width - 2)
                content.append(f"{name:<{server_width}}", style=row_style)

                # Source badge
                source = server_info.get("source", "explicit")
                source_style = self.theme.success if source == "explicit" else self.theme.dim_text
                content.append(f"{source:>{source_width}}", style=source_style)

                # Usage count
                usage = server_info.get("usage", 0)
                usage_str = f"{usage:,}" if usage else "-"
                content.append(f"{usage_str:>10}", style=row_style)

                # Notes (v1.0.3 - task-233.13: conditional based on width)
                if show_notes:
                    notes = self._truncate_with_ellipsis(
                        server_info.get("notes", ""), notes_width - 2
                    )
                    content.append(f"  {notes:<{notes_width}}\n", style=self.theme.dim_text)
                else:
                    content.append("\n")

            content.append("\n")
            content.append("─" * divider_width + "\n", style=self.theme.dim_text)
            content.append(f"Total: {len(data)} pinned server(s)", style=self.theme.dim_text)

            # Show available servers section
            if self.state.available_servers_for_add:
                content.append(
                    f"  |  {len(self.state.available_servers_for_add)} available to add",
                    style=self.theme.dim_text,
                )

        return Panel(
            content,
            title="[7] Pinned Servers",
            border_style=self.theme.mcp_border,
            padding=(1, 2),
        )

    def _build_pinned_servers_footer(self) -> Panel:
        """Build footer for Pinned Servers view (v1.0.3 - task-233.8)."""
        has_data = bool(self.state.pinned_servers_data)
        has_available = bool(self.state.available_servers_for_add)

        if has_data:
            footer_text = "[j/k]Navigate  [a]Add  [d]Remove  [Enter]Edit notes  [Esc]Back"
        elif has_available:
            footer_text = "[a]Add server  [Esc]Back"
        else:
            footer_text = "[Esc]Back"

        return Panel(
            Text(footer_text, style=self.theme.dim_text, justify="center"),
            border_style=self.theme.mcp_border,
            padding=(0, 0),
        )

    def _handle_pinned_servers_key(self, key: str) -> bool:
        """Handle key input for Pinned Servers view (v1.0.3 - task-233.8)."""
        data = self.state.pinned_servers_data or []

        if key == "escape":
            self.state.mode = BrowserMode.DASHBOARD
            return False

        if key in ("j", "down"):
            if data and self.state.pinned_servers_selected_index < len(data) - 1:
                self.state.pinned_servers_selected_index += 1
            return False

        if key in ("k", "up"):
            if data and self.state.pinned_servers_selected_index > 0:
                self.state.pinned_servers_selected_index -= 1
            return False

        if key == "a":
            # Open add server modal if there are available servers
            if self.state.available_servers_for_add:
                self.state.mode = BrowserMode.ADD_SERVER_MODAL
            else:
                self.show_notification("No unpinned servers available", "warning")
            return False

        if key == "d":
            # Remove selected server
            if data:
                server = data[self.state.pinned_servers_selected_index]
                try:
                    from token_audit.pinned_config import PinnedConfigManager

                    manager = PinnedConfigManager()
                    manager.unpin(server["name"])
                    self.show_notification(f"Unpinned: {server['name']}", "success")
                    self._load_pinned_servers()  # Reload
                    # Adjust selection if needed
                    if self.state.pinned_servers_selected_index >= len(
                        self.state.pinned_servers_data or []
                    ):
                        self.state.pinned_servers_selected_index = max(
                            0, len(self.state.pinned_servers_data or []) - 1
                        )
                except Exception as e:
                    self.show_notification(f"Failed to unpin: {e}", "error")
            return False

        if key == "enter":
            # Edit notes for selected server (simplified: just show current notes)
            if data:
                server = data[self.state.pinned_servers_selected_index]
                notes = server.get("notes", "")
                self.show_notification(f"Notes for {server['name']}: {notes or '(none)'}", "info")
            return False

        return False

    def _build_add_server_modal(self) -> Panel:
        """Build the Add Server modal (v1.0.3 - task-233.8)."""
        content = Text()

        content.append("Add Pinned Server\n\n", style=f"bold {self.theme.title}")
        content.append(
            "Select a server to pin for focused analysis:\n\n", style=self.theme.dim_text
        )

        available = self.state.available_servers_for_add or []

        if not available:
            content.append("No unpinned servers available.\n", style=self.theme.dim_text)
        else:
            # Show list with numbers for quick selection
            for i, server in enumerate(available[:9]):  # Show up to 9 servers
                is_selected = i == self.state.pinned_servers_selected_index
                prefix = "▶" if is_selected else " "
                style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
                content.append(f" {prefix} [{i + 1}] {server}\n", style=style)

            if len(available) > 9:
                content.append(
                    f"\n... and {len(available) - 9} more (use j/k to scroll)\n",
                    style=self.theme.dim_text,
                )

        content.append("\n")
        content.append("[1-9]Quick select  [Enter]Confirm  [Esc]Cancel", style=self.theme.dim_text)

        inner_panel = Panel(
            content,
            title="Add Server",
            border_style=self.theme.info,
            padding=(1, 2),
        )

        return Panel(
            Align.center(inner_panel, vertical="middle"),
            border_style=self.theme.mcp_border,
        )

    def _handle_add_server_modal_key(self, key: str) -> bool:
        """Handle key input for Add Server modal (v1.0.3 - task-233.8)."""
        available = self.state.available_servers_for_add or []

        if key == "escape":
            self.state.mode = BrowserMode.PINNED_SERVERS
            self.state.pinned_servers_selected_index = 0
            return False

        if key in ("j", "down"):
            if available and self.state.pinned_servers_selected_index < len(available) - 1:
                self.state.pinned_servers_selected_index += 1
            return False

        if key in ("k", "up"):
            if available and self.state.pinned_servers_selected_index > 0:
                self.state.pinned_servers_selected_index -= 1
            return False

        # Number keys 1-9 for quick selection
        if key in "123456789":
            idx = int(key) - 1
            if idx < len(available):
                self._pin_server(available[idx])
                self.state.mode = BrowserMode.PINNED_SERVERS
                self._load_pinned_servers()
            return False

        if key == "enter":
            if available and self.state.pinned_servers_selected_index < len(available):
                self._pin_server(available[self.state.pinned_servers_selected_index])
                self.state.mode = BrowserMode.PINNED_SERVERS
                self._load_pinned_servers()
            return False

        return False

    def _pin_server(self, server_name: str) -> None:
        """Pin a server (v1.0.3 - task-233.8)."""
        try:
            from token_audit.pinned_config import PinnedConfigManager

            manager = PinnedConfigManager()
            manager.pin(server_name)
            self.show_notification(f"Pinned: {server_name}", "success")
        except Exception as e:
            self.show_notification(f"Failed to pin: {e}", "error")

    # =========================================================================
    # End of v1.0.3 - task-233.8: Pinned Servers View
    # =========================================================================

    # =========================================================================
    # v1.0.3 - task-233.9: Export Functionality
    # =========================================================================

    def _do_export(self, format: str) -> None:
        """Export current view data to file (v1.0.3 - task-233.9).

        Args:
            format: Export format ('csv', 'json', or 'ai')
        """
        from pathlib import Path

        mode = self.state.mode
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        home = Path.home()
        export_dir = home / ".token-audit" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Get data based on current view
            if mode == BrowserMode.DASHBOARD:
                data = self._get_dashboard_export_data()
                view_name = "dashboard"
            elif mode == BrowserMode.LIST:
                data = self._get_list_export_data()
                view_name = "sessions"
            elif mode == BrowserMode.DETAIL:
                data = self._get_detail_export_data()
                view_name = "session-detail"
            elif mode == BrowserMode.ANALYTICS:
                data = self._get_analytics_export_data()
                view_name = "analytics"
            elif mode == BrowserMode.SMELL_TRENDS:
                data = self._get_smell_trends_export_data()
                view_name = "smell-trends"
            elif mode == BrowserMode.PINNED_SERVERS:
                data = self._get_pinned_servers_export_data()
                view_name = "pinned-servers"
            else:
                self.show_notification("Export not supported for this view", "warning")
                return

            if not data:
                self.show_notification("No data to export", "warning")
                return

            # Generate file based on format
            if format == "csv":
                filepath = export_dir / f"token-audit-{view_name}-{timestamp}.csv"
                self._write_csv(filepath, data)
            elif format == "json":
                filepath = export_dir / f"token-audit-{view_name}-{timestamp}.json"
                self._write_json(filepath, data)
            else:
                self.show_notification(f"Unknown format: {format}", "error")
                return

            record_count = len(data.get("records", data.get("items", [])))
            # Show full path with ~ abbreviation for home directory
            path_str = str(filepath).replace(str(Path.home()), "~")
            self.show_notification(f"Exported {record_count} records to {path_str}", "success")

        except Exception as e:
            self.show_notification(f"Export failed: {e}", "error")

    def _write_csv(self, filepath: Path, data: Dict[str, Any]) -> None:
        """Write data to CSV file (v1.0.3 - task-233.9)."""
        import csv

        records = data.get("records", data.get("items", []))
        if not records:
            filepath.write_text("")
            return

        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

    def _write_json(self, filepath: Path, data: Dict[str, Any]) -> None:
        """Write data to JSON file (v1.0.3 - task-233.9)."""
        import json

        with filepath.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _get_dashboard_export_data(self) -> Dict[str, Any]:
        """Get dashboard data for export (v1.0.3 - task-233.9)."""
        sessions = self.state.sessions
        if not sessions:
            return {}

        total_tokens = sum(s.total_tokens for s in sessions)
        total_cost = sum(s.cost_estimate for s in sessions)

        records = [
            {
                "date": s.session_date.isoformat(),
                "platform": s.platform,
                "project": s.project,
                "tokens": s.total_tokens,
                "cost": round(s.cost_estimate, 4),
                "duration_seconds": round(s.duration_seconds, 1),
                "tool_count": s.tool_count,
                "smell_count": s.smell_count,
            }
            for s in sessions[:20]  # Recent 20 sessions
        ]

        return {
            "summary": {
                "total_sessions": len(sessions),
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 2),
                "export_date": datetime.now().isoformat(),
            },
            "records": records,
        }

    def _get_list_export_data(self) -> Dict[str, Any]:
        """Get session list data for export (v1.0.3 - task-233.9)."""
        sessions = self.state.sessions
        if not sessions:
            return {}

        records = [
            {
                "session_id": s.path.stem,
                "date": s.session_date.isoformat(),
                "platform": s.platform,
                "project": s.project,
                "tokens": s.total_tokens,
                "cost": round(s.cost_estimate, 4),
                "duration_seconds": round(s.duration_seconds, 1),
                "tool_count": s.tool_count,
                "smell_count": s.smell_count,
                "model": s.model_name,
            }
            for s in sessions
        ]

        return {
            "total_sessions": len(sessions),
            "filter_platform": self.state.filter_platform if self.state.filter_platform else None,
            "date_filter_start": (
                self.state.date_filter_start.isoformat() if self.state.date_filter_start else None
            ),
            "date_filter_end": (
                self.state.date_filter_end.isoformat() if self.state.date_filter_end else None
            ),
            "export_date": datetime.now().isoformat(),
            "records": records,
        }

    def _get_detail_export_data(self) -> Dict[str, Any]:
        """Get session detail data for export (v1.0.3 - task-233.9)."""
        if self.state.selected_index >= len(self.state.sessions):
            return {}

        session = self.state.sessions[self.state.selected_index]
        try:
            session_data = self._load_session_data(session.path)
            if not session_data:
                return {}

            tool_records = []
            if "token_usage" in session_data:
                for server, tools in session_data["token_usage"].items():
                    if isinstance(tools, dict):
                        for tool_name, tool_data in tools.items():
                            if isinstance(tool_data, dict):
                                tool_records.append(
                                    {
                                        "server": server,
                                        "tool": tool_name,
                                        "call_count": tool_data.get("call_count", 0),
                                        "total_tokens": tool_data.get("total_tokens", 0),
                                        "avg_tokens": round(tool_data.get("avg_tokens", 0), 1),
                                    }
                                )

            return {
                "session_id": session.path.stem,
                "date": session.session_date.isoformat(),
                "platform": session.platform,
                "project": session.project,
                "total_tokens": session.total_tokens,
                "cost": round(session.cost_estimate, 4),
                "duration_seconds": round(session.duration_seconds, 1),
                "export_date": datetime.now().isoformat(),
                "records": tool_records,
            }
        except Exception:
            return {}

    def _get_analytics_export_data(self) -> Dict[str, Any]:
        """Get analytics data for export (v1.0.3 - task-233.9)."""
        aggregated = self._get_analytics_data()
        if not aggregated:
            return {}

        records = [
            {
                "period": row["label"],
                "sessions": row["sessions"],
                "tokens": row["tokens"],
                "cost": round(row["cost"], 4),
                "smells": row.get("smells", 0),
            }
            for row in aggregated
        ]

        return {
            "period_type": self.state.analytics_period,
            "group_by_project": self.state.analytics_group_by_project,
            "date_filter_start": (
                self.state.date_filter_start.isoformat() if self.state.date_filter_start else None
            ),
            "date_filter_end": (
                self.state.date_filter_end.isoformat() if self.state.date_filter_end else None
            ),
            "export_date": datetime.now().isoformat(),
            "records": records,
        }

    def _get_smell_trends_export_data(self) -> Dict[str, Any]:
        """Get smell trends data for export (v1.0.3 - task-233.9)."""
        data = self.state.smell_trends_data
        if not data or not data.aggregated_smells:
            return {}

        records = [
            {
                "pattern": smell.pattern,
                "frequency_percent": round(smell.frequency_percent, 1),
                "trend": smell.trend,
                "trend_change_percent": round(smell.trend_change_percent, 1),
                "total_occurrences": smell.total_occurrences,
                "sessions_affected": smell.sessions_affected,
                "top_tools": (
                    ", ".join(t[0] for t in smell.top_tools[:3]) if smell.top_tools else ""
                ),
            }
            for smell in data.aggregated_smells
        ]

        return {
            "period_days": self.state.smell_trends_days,
            "total_sessions": data.total_sessions,
            "sessions_with_smells": data.sessions_with_smells,
            "export_date": datetime.now().isoformat(),
            "records": records,
        }

    def _get_pinned_servers_export_data(self) -> Dict[str, Any]:
        """Get pinned servers data for export (v1.0.3 - task-233.9)."""
        data = self.state.pinned_servers_data
        if not data:
            return {}

        records = [
            {
                "server": server["name"],
                "source": server.get("source", "explicit"),
                "usage": server.get("usage", 0),
                "notes": server.get("notes", ""),
            }
            for server in data
        ]

        return {
            "total_pinned": len(data),
            "available_to_add": len(self.state.available_servers_for_add or []),
            "export_date": datetime.now().isoformat(),
            "records": records,
        }

    # =========================================================================
    # End of v1.0.3 - task-233.9: Export Functionality
    # =========================================================================

    def _generate_quick_recommendations(self) -> List[tuple[str, str, int]]:
        """Generate quick recommendations from session stats (v1.0.0).

        Returns list of (icon, recommendation, confidence) tuples.
        """

        recommendations: List[tuple[str, str, int]] = []
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)

        week_sessions = [s for s in self.state.sessions if s.session_date.date() >= week_ago]

        if not week_sessions:
            return recommendations

        # Check for high token sessions
        high_token_sessions = [s for s in week_sessions if s.total_tokens > 500000]
        if high_token_sessions:
            recommendations.append(
                (
                    ascii_emoji("🔴"),
                    f"Review {len(high_token_sessions)} high-token sessions (>500K tokens)",
                    85,
                )
            )

        # Check for high smell sessions
        high_smell_sessions = [s for s in week_sessions if s.smell_count >= 3]
        if high_smell_sessions:
            recommendations.append(
                (
                    ascii_emoji("🟠"),
                    f"{len(high_smell_sessions)} sessions have 3+ code smells - investigate patterns",
                    75,
                )
            )

        # Check for cost optimization
        total_week_cost = sum(s.cost_estimate for s in week_sessions)
        if total_week_cost > 10:
            recommendations.append(
                (
                    ascii_emoji("🟡"),
                    f"Weekly cost is ${total_week_cost:.2f} - consider caching strategies",
                    70,
                )
            )

        # Check for frequent short sessions (might indicate restarts)
        short_sessions = [s for s in week_sessions if s.duration_seconds < 60]
        if len(short_sessions) >= 5:
            recommendations.append(
                (
                    ascii_emoji("🟡"),
                    f"{len(short_sessions)} very short sessions (<1min) - possible session issues",
                    65,
                )
            )

        return recommendations[:5]  # Limit to 5 recommendations

    # =========================================================================
    # v1.0.0 - Command Palette
    # =========================================================================

    def _build_command_palette(self) -> Panel:
        """Build the command palette overlay (v1.0.0)."""
        content = Text()

        # Input field
        content.append(": ", style=f"bold {self.theme.info}")
        content.append(self.state.command_input, style=self.theme.primary_text)
        content.append("_\n", style=self.theme.dim_text)  # Cursor
        content.append("─" * 40 + "\n", style=self.theme.dim_text)

        # Command list
        commands = self._get_filtered_commands()
        for i, (name, desc, _mode) in enumerate(commands):
            is_selected = i == self.state.command_menu_index
            prefix = ">" if is_selected else " "
            style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text

            content.append(f" {prefix} {name:<16}", style=style)
            content.append(f" {desc}\n", style=self.theme.dim_text)

        content.append("\n")
        content.append("Enter=select  Esc=cancel  j/k=navigate", style=self.theme.dim_text)

        return Panel(
            content,
            title="Command Palette",
            border_style=self.theme.info,
            box=self.box_style,
        )

    # =========================================================================
    # v1.0.0 - AI Export methods for new views
    # =========================================================================

    def _export_dashboard_ai_prompt(self) -> None:
        """Export dashboard overview for AI analysis (v1.0.0)."""

        today = datetime.now().date()
        week_ago = today - timedelta(days=7)

        today_sessions = [s for s in self.state.sessions if s.session_date.date() == today]
        week_sessions = [s for s in self.state.sessions if s.session_date.date() >= week_ago]

        prompt = f"""# Token Audit Dashboard Overview

## Today's Summary
- Sessions: {len(today_sessions)}
- Total Tokens: {sum(s.total_tokens for s in today_sessions):,}
- Total Cost: ${sum(s.cost_estimate for s in today_sessions):.2f}

## Weekly Stats (Last 7 Days)
- Sessions: {len(week_sessions)}
- Total Tokens: {sum(s.total_tokens for s in week_sessions):,}
- Total Cost: ${sum(s.cost_estimate for s in week_sessions):.2f}
- Avg Smells/Session: {sum(s.smell_count for s in week_sessions) / len(week_sessions):.1f if week_sessions else 0}

## Platform Breakdown
"""
        # Add platform breakdown
        platforms: Dict[str, Dict[str, Any]] = {}
        for s in week_sessions:
            if s.platform not in platforms:
                platforms[s.platform] = {"count": 0, "tokens": 0, "cost": 0}
            platforms[s.platform]["count"] += 1
            platforms[s.platform]["tokens"] += s.total_tokens
            platforms[s.platform]["cost"] += s.cost_estimate

        for platform, stats in sorted(
            platforms.items(), key=lambda x: x[1]["tokens"], reverse=True
        ):
            prompt += f"- {platform}: {stats['count']} sessions, {stats['tokens']:,} tokens, ${stats['cost']:.2f}\n"

        prompt += "\nPlease analyze my MCP usage patterns and suggest optimizations."

        self._copy_to_clipboard(prompt)
        self.show_notification("Dashboard overview copied to clipboard", "success")

    def _export_recommendations_ai_prompt(self) -> None:
        """Export recommendations for AI analysis (v1.0.0)."""
        recommendations = self._generate_quick_recommendations()

        prompt = """# Token Audit Recommendations Export

## Current Recommendations
"""
        if recommendations:
            for _icon, rec, confidence in recommendations:
                prompt += f"- [{confidence}% confidence] {rec}\n"
        else:
            prompt += "- No specific recommendations at this time\n"

        prompt += """
## Request
Please review these automated recommendations and provide:
1. Additional insights based on the patterns
2. Specific action items to improve MCP efficiency
3. Best practices for MCP tool usage
"""

        self._copy_to_clipboard(prompt)
        self.show_notification("Recommendations copied to clipboard", "success")

    def _build_notification(self) -> Text:
        """Build notification bar for user feedback (v0.8.0 - task-106.9)."""
        if not self._notification:
            return Text("")

        notification = self._notification

        # Map level to icon and color
        level_config = {
            "success": (ascii_emoji("✓"), self.theme.success),
            "warning": (ascii_emoji("⚠"), self.theme.warning),
            "error": (ascii_emoji("✗"), self.theme.error),
            "info": (ascii_emoji("ℹ"), self.theme.info),
        }
        icon, color = level_config.get(notification.level, ("", self.theme.dim_text))

        # Calculate remaining time
        remaining = max(0, notification.expires_at - time.time())
        remaining_str = f"[{remaining:.0f}s]" if remaining > 0 else ""

        # Build notification text
        text = Text()
        text.append(f"{icon} ", style=f"bold {color}")
        text.append(notification.message, style=color)
        text.append(f"  {remaining_str}", style=self.theme.dim_text)
        text.justify = "center"

        return text

    def _build_sort_menu(self) -> Panel:
        """Build sort options menu. v0.7.0 - task-105.4"""
        content = Text()
        content.append("Sort Sessions By\n\n", style=f"bold {self.theme.title}")

        for i, (label, _, _) in enumerate(SORT_OPTIONS):
            is_selected = i == self.state.sort_menu_index
            prefix = ">" if is_selected else " "
            style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
            content.append(f" {prefix} {label}\n", style=style)

        return Panel(
            content,
            title="Sort Menu",
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_sort_menu_footer(self) -> Text:
        """Build footer for sort menu. v0.7.0 - task-105.4"""
        return Text(
            "j/k=navigate  ENTER=select  ESC=cancel  q=quit",
            style=self.theme.dim_text,
            justify="center",
        )

    def _build_help_overlay(self) -> Panel:
        """Build help overlay with keybindings and accuracy legend. v0.7.0 - task-105.3"""
        # Keybindings table
        table = Table(
            box=self.box_style,
            show_header=True,
            header_style=f"bold {self.theme.primary_text}",
        )
        table.add_column("Key", style=self.theme.info, width=12)
        table.add_column("Action", style=self.theme.primary_text)

        for kb in KEYBINDINGS:
            table.add_row(kb.keys, kb.description)

        # Build combined content with keybindings and accuracy legend
        content = Text()
        content.append("Keyboard Shortcuts\n", style=f"bold {self.theme.title}")
        content.append("\n")

        for kb in KEYBINDINGS:
            content.append(f"  {kb.keys:<12}", style=self.theme.info)
            content.append(f"{kb.description}\n", style=self.theme.primary_text)

        # Spacing between sections
        content.append("\n\n")

        # Accuracy legend section
        content.append("Accuracy Column\n", style=f"bold {self.theme.title}")
        content.append("\n")
        acc_icon_exact, acc_color_exact = accuracy_indicator("exact")
        acc_icon_estimated, acc_color_estimated = accuracy_indicator("estimated")
        acc_icon_calls, acc_color_calls = accuracy_indicator("calls-only")
        content.append(f"  {acc_icon_exact}  ", style=acc_color_exact)
        content.append("Exact - native API token counts\n", style=self.theme.primary_text)
        content.append(f"  {acc_icon_estimated}  ", style=acc_color_estimated)
        content.append("Estimated - tokenizer-based estimate\n", style=self.theme.primary_text)
        content.append(f"  {acc_icon_calls}  ", style=acc_color_calls)
        content.append(
            "Calls-only - tool calls without token data\n", style=self.theme.primary_text
        )

        # Spacing between sections
        content.append("\n\n")

        # Settings section with toggle
        content.append("Settings (press key to toggle)\n", style=f"bold {self.theme.title}")
        content.append("\n")
        pins_to_top = self.prefs.prefs.pins_sort_to_top
        pins_state = "ON" if pins_to_top else "OFF"
        pins_color = self.theme.success if pins_to_top else self.theme.dim_text
        content.append("  T            ", style=self.theme.info)
        content.append(f"Pins sort to top [{pins_state}]\n", style=pins_color)

        # Bottom padding
        content.append("\n")

        return Panel(
            content,
            title="Help",
            subtitle="T=toggle settings  |  any other key=close",
            border_style=self.theme.header_border,
            box=self.box_style,
        )

    def _build_help_footer(self) -> Text:
        """Build footer for help overlay. v0.7.0 - task-105.3"""
        return Text(
            "T=toggle settings  |  any other key=close  |  q=quit browser",
            style=self.theme.dim_text,
            justify="center",
        )

    def _build_detail_view(self) -> Panel:
        """Build detailed session view."""
        if not self.state.sessions:
            return Panel("No session selected", border_style=self.theme.error, box=self.box_style)

        entry = self.state.sessions[self.state.selected_index]
        data = self._detail_data
        if data is None:
            return Panel(
                "Could not load session",
                border_style=self.theme.error,
                box=self.box_style,
            )

        content = Text()

        # Header info
        content.append(f"Project: {entry.project}\n", style=f"bold {self.theme.title}")
        content.append(f"Platform: {entry.platform}\n", style=self.theme.primary_text)
        content.append(
            f"Date: {entry.session_date}  Duration: {self._format_duration(entry.duration_seconds)}\n",
            style=self.theme.dim_text,
        )
        if entry.model_name:
            content.append(f"Model: {entry.model_name}\n", style=self.theme.success)

        # Accuracy indicator (v0.7.0 - task-105.5)
        acc_icon, acc_color = accuracy_indicator(entry.accuracy_level)
        accuracy_labels = {
            "exact": "Exact (native API counts)",
            "estimated": "Estimated (tokenizer)",
            "calls-only": "Calls only (no tokens)",
        }
        acc_label = accuracy_labels.get(entry.accuracy_level, entry.accuracy_level)
        content.append(f"Data: {acc_icon} {acc_label}\n", style=acc_color)

        # Token breakdown
        tu = data.get("token_usage", {})
        content.append(
            f"\nTokens: {tu.get('total_tokens', 0):,}\n",
            style=f"bold {self.theme.success}",
        )
        content.append(f"  Input: {tu.get('input_tokens', 0):,}\n", style=self.theme.dim_text)
        content.append(f"  Output: {tu.get('output_tokens', 0):,}\n", style=self.theme.dim_text)
        cache_read = tu.get("cache_read_tokens", 0)
        cache_created = tu.get("cache_created_tokens", 0)
        if cache_read > 0 or cache_created > 0:
            content.append(
                f"  Cache Read: {cache_read:,}  Created: {cache_created:,}\n",
                style=self.theme.dim_text,
            )
        # Reasoning tokens (v0.7.0 - task-105.10) - only for Gemini/Codex
        reasoning = tu.get("reasoning_tokens", 0)
        if reasoning > 0:
            content.append(f"  Reasoning: {reasoning:,}\n", style=self.theme.dim_text)

        # Cost
        content.append(f"\nCost: ${entry.cost_estimate:.4f}\n", style=f"bold {self.theme.warning}")

        # MCP Summary
        mcp_summary = data.get("mcp_summary", data.get("mcp_tool_calls", {}))
        if mcp_summary:
            content.append(
                f"\nMCP Tools: {mcp_summary.get('unique_tools', 0)} unique, "
                f"{mcp_summary.get('total_calls', 0)} calls\n",
                style=self.theme.primary_text,
            )

        # Server breakdown
        server_sessions = data.get("server_sessions", {})
        if server_sessions:
            content.append("\nServers:\n", style=f"bold {self.theme.primary_text}")
            for server_name, server_data in list(server_sessions.items())[:5]:
                if isinstance(server_data, dict):
                    calls = server_data.get("total_calls", 0)
                    tokens = server_data.get("total_tokens", 0)
                    content.append(
                        f"  {server_name}: {calls} calls, {tokens:,} tokens\n",
                        style=self.theme.dim_text,
                    )

        # Smells
        smells = data.get("smells", [])
        if smells:
            warning_emoji = ascii_emoji("\u26a0")
            content.append(
                f"\n{warning_emoji} Smells ({len(smells)}):\n",
                style=f"bold {self.theme.warning}",
            )
            for smell in smells[:5]:
                if isinstance(smell, dict):
                    pattern = smell.get("pattern", "Unknown")
                    severity = smell.get("severity", "info")
                    style = self.theme.warning if severity == "warning" else self.theme.info
                    content.append(f"  {pattern}\n", style=style)
            if len(smells) > 5:
                content.append(f"  +{len(smells) - 5} more\n", style=self.theme.dim_text)

        # File path
        content.append(f"\nFile: {entry.path}\n", style=self.theme.dim_text)

        return Panel(
            content,
            title="Session Details",
            border_style=self.theme.activity_border,
            box=self.box_style,
        )

    def _build_detail_footer(self) -> Text:
        """Build footer for detail view."""
        # v0.7.0 - Added AI export (task-105.8), v0.8.0 - Added timeline (task-106.8)
        return Text(
            "a=AI  d=tool detail  T=timeline  q/ESC=back to list",
            style=self.theme.dim_text,
            justify="center",
        )

    def _build_tool_detail_view(self) -> Panel:
        """Build detailed tool metrics view (v0.7.0 - task-105.7)."""
        if not self.state.selected_tool:
            return Panel(
                "No tool selected",
                border_style=self.theme.error,
                box=self.box_style,
            )

        server, tool_name = self.state.selected_tool
        detail = self._load_tool_detail(server, tool_name)

        if not detail:
            return Panel(
                "Could not load tool data",
                border_style=self.theme.error,
                box=self.box_style,
            )

        content = Text()

        # Header
        content.append(f"Tool: {tool_name}\n", style=f"bold {self.theme.title}")
        content.append(f"Server: {server}\n\n", style=self.theme.dim_text)

        # Basic metrics
        content.append("Metrics\n", style=f"bold {self.theme.primary_text}")
        content.append(f"  Calls: {detail.call_count}\n", style=self.theme.primary_text)
        content.append(f"  Total Tokens: {detail.total_tokens:,}\n", style=self.theme.primary_text)
        content.append(f"  Avg Tokens: {detail.avg_tokens:,.0f}\n\n", style=self.theme.dim_text)

        # Percentile statistics
        content.append("Token Distribution\n", style=f"bold {self.theme.primary_text}")
        content.append(f"  Min: {detail.min_tokens:,}  ", style=self.theme.dim_text)
        content.append(f"P50: {detail.p50_tokens:,}  ", style=self.theme.info)
        content.append(f"P95: {detail.p95_tokens:,}  ", style=self.theme.warning)
        content.append(f"Max: {detail.max_tokens:,}\n", style=self.theme.dim_text)

        # Histogram
        content.append(f"  Histogram: [{detail.histogram}]\n\n", style=self.theme.info)

        # Tool-specific smells
        if detail.smells:
            warning_emoji = ascii_emoji("\u26a0")
            content.append(
                f"{warning_emoji} Smells ({len(detail.smells)})\n",
                style=f"bold {self.theme.warning}",
            )
            for smell in detail.smells[:3]:
                pattern = smell.get("pattern", "Unknown")
                desc = smell.get("description", "")[:50]
                content.append(f"  {pattern}: {desc}\n", style=self.theme.warning)
            if len(detail.smells) > 3:
                content.append(f"  +{len(detail.smells) - 3} more\n", style=self.theme.dim_text)
            content.append("\n")

        # Static cost info
        if detail.static_cost_tokens > 0:
            content.append(
                f"Context Tax (server): {detail.static_cost_tokens:,} tokens\n",
                style=self.theme.dim_text,
            )

        return Panel(
            content,
            title=f"Tool Details - {tool_name}",
            border_style=self.theme.activity_border,
            box=self.box_style,
        )

    def _build_tool_detail_footer(self) -> Text:
        """Build footer for tool detail view (v0.7.0 - task-105.7)."""
        return Text(
            "a=AI export  q/ESC=back to session",
            style=self.theme.dim_text,
            justify="center",
        )

    def _build_timeline_view(self) -> Panel:
        """Build timeline visualization view (v0.8.0 - task-106.8)."""
        if not self._timeline_data:
            return Panel(
                "No timeline data available",
                border_style=self.theme.error,
                box=self.box_style,
            )

        td = self._timeline_data
        content = Text()

        # Header
        content.append("Session Timeline\n", style=f"bold {self.theme.title}")
        content.append(f"Date: {td.session_date}  ", style=self.theme.dim_text)
        content.append(
            f"Duration: {self._format_duration(td.duration_seconds)}\n\n", style=self.theme.dim_text
        )

        # Summary metrics
        content.append("Summary\n", style=f"bold {self.theme.primary_text}")
        content.append(f"  Total Tokens: {td.total_tokens:,}\n", style=self.theme.primary_text)
        content.append(f"  MCP Tokens: {td.total_mcp_tokens:,}\n", style=self.theme.info)
        content.append(
            f"  Built-in Tokens: {td.total_builtin_tokens:,}\n", style=self.theme.dim_text
        )
        content.append(
            f"  Avg/Bucket: {td.avg_tokens_per_bucket:,.0f}\n", style=self.theme.dim_text
        )
        content.append(f"  Max/Bucket: {td.max_tokens_per_bucket:,}\n", style=self.theme.warning)
        bucket_label = self._format_bucket_duration(td.bucket_duration_seconds)
        content.append(f"  Bucket Size: {bucket_label}\n\n", style=self.theme.dim_text)

        # Timeline graph
        content.append("Token Usage Timeline\n", style=f"bold {self.theme.primary_text}")
        graph = self._generate_timeline_graph(td)
        content.append(graph)
        content.append("\n")

        # Legend
        content.append("Legend: ", style=self.theme.dim_text)
        content.append("\u2588 ", style=self.theme.info)
        content.append("MCP  ", style=self.theme.dim_text)
        content.append("\u2591 ", style=self.theme.dim_text)
        content.append("Built-in  ", style=self.theme.dim_text)
        content.append("\u25b2 ", style=self.theme.warning)
        content.append("Spike\n\n", style=self.theme.warning)

        # Spikes
        if td.spikes:
            warning_emoji = ascii_emoji("\u26a0")
            content.append(
                f"{warning_emoji} Detected Spikes ({len(td.spikes)})\n",
                style=f"bold {self.theme.warning}",
            )
            for spike in td.spikes[:5]:
                time_label = self._format_bucket_time(spike.start_seconds)
                content.append(
                    f"  {time_label}: {spike.total_tokens:,} tokens "
                    f"(z={spike.spike_magnitude:.1f})\n",
                    style=self.theme.warning,
                )
            if len(td.spikes) > 5:
                content.append(f"  +{len(td.spikes) - 5} more\n", style=self.theme.dim_text)

        return Panel(
            content,
            title="Timeline View",
            border_style=self.theme.activity_border,
            box=self.box_style,
        )

    def _generate_timeline_graph(self, td: TimelineData) -> Text:
        """Generate Unicode timeline graph (v0.8.0 - task-106.8).

        Creates a horizontal bar chart showing token usage over time.
        Uses Unicode block characters for visualization.
        """
        text = Text()

        if not td.buckets or td.max_tokens_per_bucket == 0:
            text.append("  [No data to display]\n", style=self.theme.dim_text)
            return text

        # Graph dimensions
        max_bar_width = 40  # Maximum width for the bar
        y_scale = td.max_tokens_per_bucket

        # Show Y-axis scale
        text.append(f"  {td.max_tokens_per_bucket:>6,} ", style=self.theme.dim_text)
        text.append("\u2502\n", style=self.theme.dim_text)

        # Generate bars for each bucket (limit to ~20 buckets for display)
        display_buckets = td.buckets
        if len(td.buckets) > 20:
            # Aggregate into 20 display buckets
            step = len(td.buckets) // 20
            display_buckets = td.buckets[::step][:20]

        for bucket in display_buckets:
            # Calculate bar widths
            total_ratio = bucket.total_tokens / y_scale if y_scale > 0 else 0
            mcp_ratio = bucket.mcp_tokens / y_scale if y_scale > 0 else 0

            total_width = int(total_ratio * max_bar_width)
            mcp_width = int(mcp_ratio * max_bar_width)
            builtin_width = total_width - mcp_width

            # Time label
            time_label = self._format_bucket_time(bucket.start_seconds)
            text.append(f"  {time_label:>6} ", style=self.theme.dim_text)
            text.append("\u2502", style=self.theme.dim_text)

            # MCP portion (solid block)
            text.append("\u2588" * mcp_width, style=self.theme.info)

            # Built-in portion (light shade)
            text.append("\u2591" * builtin_width, style=self.theme.dim_text)

            # Spike marker
            if bucket.is_spike:
                text.append(" \u25b2", style=self.theme.warning)

            text.append("\n")

        # X-axis
        text.append("         \u2514", style=self.theme.dim_text)
        text.append("\u2500" * max_bar_width, style=self.theme.dim_text)
        text.append("\n")

        return text

    def _format_bucket_time(self, seconds: float) -> str:
        """Format bucket time as MM:SS or HH:MM."""
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}:{secs:02d}"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}"

    def _format_bucket_duration(self, seconds: float) -> str:
        """Format bucket duration in human-friendly format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}min"
        else:
            return f"{int(seconds // 3600)}hr"

    def _build_timeline_footer(self) -> Text:
        """Build footer for timeline view (v0.8.0 - task-106.8)."""
        return Text(
            "a=AI export  q/ESC=back to session",
            style=self.theme.dim_text,
            justify="center",
        )

    def _export_timeline_ai_prompt(self) -> None:
        """Export AI analysis prompt for timeline (v0.8.0 - task-106.8)."""
        if not self._timeline_data or not self._detail_data:
            return

        td = self._timeline_data
        session_meta = self._detail_data.get("session", {})

        # Generate markdown prompt
        lines = [
            "# Timeline Analysis Request",
            "",
            f"Please analyze this session timeline data for project "
            f"**{session_meta.get('project', 'Unknown')}**:",
            "",
            "## Session Overview",
            f"- **Date**: {td.session_date.isoformat()}",
            f"- **Duration**: {self._format_duration(td.duration_seconds)}",
            f"- **Bucket Size**: {self._format_bucket_duration(td.bucket_duration_seconds)}",
            "",
            "## Token Distribution",
            f"- **Total Tokens**: {td.total_tokens:,}",
            f"- **MCP Tokens**: {td.total_mcp_tokens:,} ({td.total_mcp_tokens * 100 // max(td.total_tokens, 1)}%)",
            f"- **Built-in Tokens**: {td.total_builtin_tokens:,} ({td.total_builtin_tokens * 100 // max(td.total_tokens, 1)}%)",
            f"- **Average per Bucket**: {td.avg_tokens_per_bucket:,.0f}",
            f"- **Maximum per Bucket**: {td.max_tokens_per_bucket:,}",
            "",
        ]

        # Add spike information
        if td.spikes:
            lines.append("## Detected Spikes")
            lines.append(f"Found {len(td.spikes)} spike(s) (>2.0 standard deviations):")
            lines.append("")
            for spike in td.spikes[:10]:
                time_label = self._format_bucket_time(spike.start_seconds)
                lines.append(
                    f"- **{time_label}**: {spike.total_tokens:,} tokens "
                    f"(z-score: {spike.spike_magnitude:.2f})"
                )
            lines.append("")

        # Add bucket data summary
        lines.append("## Token Usage by Time")
        lines.append("```")
        for bucket in td.buckets[:20]:
            time_label = self._format_bucket_time(bucket.start_seconds)
            spike_marker = " [SPIKE]" if bucket.is_spike else ""
            lines.append(
                f"{time_label}: {bucket.total_tokens:>8,} tokens "
                f"(MCP: {bucket.mcp_tokens:,}, Built-in: {bucket.builtin_tokens:,}){spike_marker}"
            )
        if len(td.buckets) > 20:
            lines.append(f"... and {len(td.buckets) - 20} more buckets")
        lines.append("```")
        lines.append("")

        lines.extend(
            [
                "## Questions",
                "1. What explains the token usage patterns over time?",
                "2. Are the detected spikes concerning or expected?",
                "3. Is the MCP vs built-in ratio appropriate?",
                "4. What could reduce token usage in high-activity periods?",
                "5. Are there any inefficiency patterns in the timeline?",
            ]
        )

        output = "\n".join(lines)
        self._copy_to_clipboard(output)

    def _build_comparison_view(self) -> Panel:
        """Build comparison view panel (v0.8.0 - task-106.7)."""
        if not self._comparison_data:
            return Panel("No comparison data", border_style=self.theme.warning)

        cd = self._comparison_data
        content = Text()

        # Title
        num_sessions = 1 + len(cd.comparisons)
        content.append(
            f"COMPARISON ({num_sessions} sessions)\n\n", style=f"bold {self.theme.title}"
        )

        # Session list
        baseline_tokens = cd.baseline_data.get("token_usage", {}).get("total_tokens", 0)
        baseline_mcp = cd.baseline_data.get("mcp_summary", {})
        baseline_mcp_tokens = baseline_mcp.get("total_tokens", 0)
        baseline_mcp_pct = (
            (baseline_mcp_tokens / baseline_tokens * 100) if baseline_tokens > 0 else 0
        )

        content.append("Baseline: ", style=f"bold {self.theme.info}")
        content.append(
            f"{cd.baseline.session_date.strftime('%Y-%m-%d')}  "
            f"{self._format_tokens(baseline_tokens)}  MCP {baseline_mcp_pct:.0f}%\n",
            style=self.theme.primary_text,
        )

        for _i, (entry, data) in enumerate(cd.comparisons):
            comp_tokens = data.get("token_usage", {}).get("total_tokens", 0)
            comp_mcp = data.get("mcp_summary", {})
            comp_mcp_tokens = comp_mcp.get("total_tokens", 0)
            comp_mcp_pct = (comp_mcp_tokens / comp_tokens * 100) if comp_tokens > 0 else 0

            content.append("Compare:  ", style=self.theme.dim_text)
            content.append(
                f"{entry.session_date.strftime('%Y-%m-%d')}  "
                f"{self._format_tokens(comp_tokens)}  MCP {comp_mcp_pct:.0f}%\n",
                style=self.theme.primary_text,
            )

        # Deltas vs Baseline
        content.append("\n─── DELTAS VS BASELINE ───\n", style=self.theme.dim_text)

        # Token deltas
        token_delta_strs = []
        for delta in cd.token_deltas:
            sign = "+" if delta >= 0 else ""
            token_delta_strs.append(f"{sign}{self._format_tokens(delta)}")
        content.append(
            f"tokens:     {' / '.join(token_delta_strs)}\n", style=self.theme.primary_text
        )

        # MCP share deltas
        mcp_delta_strs = []
        for mcp_delta in cd.mcp_share_deltas:
            sign = "+" if mcp_delta >= 0 else ""
            mcp_delta_strs.append(f"{sign}{mcp_delta:.0f}%")
        content.append(f"MCP share:  {' / '.join(mcp_delta_strs)}\n", style=self.theme.primary_text)

        # Top tool changes
        if cd.tool_changes:
            tool_strs = []
            for tool_name, delta in cd.tool_changes[:3]:
                sign = "+" if delta >= 0 else ""
                tool_strs.append(f"{tool_name} ({sign}{self._format_tokens(delta)})")
            content.append(f"top tools:  {', '.join(tool_strs)}\n", style=self.theme.dim_text)

        # Smell comparison
        if cd.smell_matrix:
            content.append("\n─── SMELL COMPARISON ───\n", style=self.theme.dim_text)
            for pattern, presence_list in list(cd.smell_matrix.items())[:5]:
                icons = ""
                for has_smell in presence_list:
                    icons += ascii_emoji("✓") + " " if has_smell else ascii_emoji("✗") + " "
                count = sum(presence_list)
                content.append(
                    f"{pattern:20s}  {icons} ({count}/{len(presence_list)} sessions)\n",
                    style=(
                        self.theme.warning
                        if count > len(presence_list) // 2
                        else self.theme.dim_text
                    ),
                )

        return Panel(
            content,
            title="Session Comparison",
            border_style=self.theme.header_border,
            box=self.box_style,
        )

    def _build_comparison_footer(self) -> Text:
        """Build footer for comparison view (v0.8.0 - task-106.7)."""
        return Text(
            "a=AI analysis export  q/ESC=back to list (clears selection)",
            style=self.theme.dim_text,
            justify="center",
        )

    def _export_comparison_ai_prompt(self) -> None:
        """Export AI analysis prompt for comparison (v0.8.0 - task-106.7)."""
        if not self._comparison_data:
            return

        cd = self._comparison_data

        # Build session info
        baseline_tokens = cd.baseline_data.get("token_usage", {}).get("total_tokens", 0)
        baseline_mcp = cd.baseline_data.get("mcp_summary", {})
        baseline_mcp_tokens = baseline_mcp.get("total_tokens", 0)
        baseline_mcp_pct = (
            (baseline_mcp_tokens / baseline_tokens * 100) if baseline_tokens > 0 else 0
        )

        lines = [
            "# Multi-Session Comparison Analysis Request",
            "",
            f"Please analyze these {1 + len(cd.comparisons)} sessions:",
            "",
            "## Sessions",
            "",
            f"### Baseline: {cd.baseline.session_date.isoformat()}",
            f"- **Project**: {cd.baseline.project}",
            f"- **Platform**: {cd.baseline.platform}",
            f"- **Tokens**: {baseline_tokens:,}",
            f"- **MCP %**: {baseline_mcp_pct:.1f}%",
            f"- **Cost**: ${cd.baseline.cost_estimate:.4f}",
            "",
        ]

        for i, (entry, data) in enumerate(cd.comparisons, 1):
            comp_tokens = data.get("token_usage", {}).get("total_tokens", 0)
            comp_mcp = data.get("mcp_summary", {})
            comp_mcp_tokens = comp_mcp.get("total_tokens", 0)
            comp_mcp_pct = (comp_mcp_tokens / comp_tokens * 100) if comp_tokens > 0 else 0

            lines.extend(
                [
                    f"### Compare {i}: {entry.session_date.isoformat()}",
                    f"- **Project**: {entry.project}",
                    f"- **Platform**: {entry.platform}",
                    f"- **Tokens**: {comp_tokens:,}",
                    f"- **MCP %**: {comp_mcp_pct:.1f}%",
                    f"- **Cost**: ${entry.cost_estimate:.4f}",
                    "",
                ]
            )

        # Deltas
        lines.extend(
            [
                "## Deltas vs Baseline",
                "",
            ]
        )

        for i, (entry, _) in enumerate(cd.comparisons):
            delta_tokens = cd.token_deltas[i]
            delta_mcp = cd.mcp_share_deltas[i]
            sign_t = "+" if delta_tokens >= 0 else ""
            sign_m = "+" if delta_mcp >= 0 else ""
            lines.append(
                f"- **{entry.session_date.isoformat()}**: "
                f"tokens {sign_t}{delta_tokens:,}, MCP {sign_m}{delta_mcp:.1f}%"
            )
        lines.append("")

        # Tool changes
        if cd.tool_changes:
            lines.extend(
                [
                    "## Top Tool Changes",
                    "",
                ]
            )
            for tool_name, delta in cd.tool_changes[:5]:
                sign = "+" if delta >= 0 else ""
                lines.append(f"- **{tool_name}**: {sign}{delta:,} tokens")
            lines.append("")

        # Smell matrix
        if cd.smell_matrix:
            lines.extend(
                [
                    "## Smell Comparison Matrix",
                    "",
                    "| Pattern | "
                    + " | ".join(
                        [cd.baseline.session_date.strftime("%m-%d")]
                        + [e.session_date.strftime("%m-%d") for e, _ in cd.comparisons]
                    )
                    + " |",
                    "|" + "----|" * (1 + len(cd.comparisons) + 1),
                ]
            )
            for pattern, presence in cd.smell_matrix.items():
                row = f"| {pattern} | "
                row += " | ".join(["Yes" if p else "No" for p in presence])
                row += " |"
                lines.append(row)
            lines.append("")

        lines.extend(
            [
                "## Questions",
                "1. What factors explain the differences between these sessions?",
                "2. Which session is most efficient and why?",
                "3. Are the tool usage changes intentional or problematic?",
                "4. What patterns emerge across the sessions?",
                "5. What recommendations would you make for future sessions?",
            ]
        )

        output = "\n".join(lines)
        self._copy_to_clipboard(output)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-friendly format."""
        if seconds < 60:
            return f"{int(seconds)}s"

        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {secs}s"

    # ========================================================================
    # Bucket Configuration View (v1.0.4 - task-247.13)
    # ========================================================================

    def _load_bucket_config(self) -> None:
        """Load bucket configuration from file."""
        try:
            from ..bucket_config import load_config

            self.state.bucket_config = load_config()
            self.state.bucket_config_modified = False
        except Exception as e:
            self.show_notification(f"Failed to load bucket config: {e}", "error")
            self.state.bucket_config = None

    def _build_bucket_config_view(self) -> Panel:
        """Build the Bucket Configuration view (v1.0.4 - task-247.13)."""
        content = Text()

        # Header
        title_icon = ascii_emoji("gear")
        content.append(f"{title_icon} Bucket Configuration\n", style=f"bold {self.theme.title}")
        content.append("Configure token classification patterns\n", style=self.theme.dim_text)
        if self.state.bucket_config_modified:
            content.append("[unsaved changes]", style=f"bold {self.theme.warning}")
        content.append("\n\n")

        config = self.state.bucket_config

        if config is None:
            content.append("Loading configuration...\n", style=self.theme.dim_text)
            return Panel(
                content,
                title="[8] Bucket Configuration",
                border_style=self.theme.mcp_border,
                padding=(1, 2),
            )

        divider_width = min(self._get_terminal_width() - 4, 80)
        section_idx = self.state.bucket_config_section
        item_idx = self.state.bucket_config_item_index

        # Section 0: State Serialization Patterns
        patterns_ss = config.patterns.get("state_serialization", [])
        section_style = f"bold {self.theme.info}" if section_idx == 0 else self.theme.primary_text
        content.append("State Serialization Patterns", style=section_style)
        content.append(f" ({len(patterns_ss)})\n", style=self.theme.dim_text)

        if section_idx == 0:
            for i, pattern in enumerate(patterns_ss):
                is_selected = i == item_idx
                if is_selected:
                    content.append("  ▶ ", style=f"bold {self.theme.info}")
                else:
                    content.append("    ", style=self.theme.dim_text)
                style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
                content.append(f"{pattern}\n", style=style)
            if not patterns_ss:
                content.append("    (no patterns)\n", style=self.theme.dim_text)
        else:
            for pattern in patterns_ss[:3]:
                content.append(f"    {pattern}\n", style=self.theme.dim_text)
            if len(patterns_ss) > 3:
                content.append(
                    f"    ...and {len(patterns_ss) - 3} more\n", style=self.theme.dim_text
                )

        content.append("\n")

        # Section 1: Tool Discovery Patterns
        patterns_td = config.patterns.get("tool_discovery", [])
        section_style = f"bold {self.theme.info}" if section_idx == 1 else self.theme.primary_text
        content.append("Tool Discovery Patterns", style=section_style)
        content.append(f" ({len(patterns_td)})\n", style=self.theme.dim_text)

        if section_idx == 1:
            for i, pattern in enumerate(patterns_td):
                is_selected = i == item_idx
                if is_selected:
                    content.append("  ▶ ", style=f"bold {self.theme.info}")
                else:
                    content.append("    ", style=self.theme.dim_text)
                style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
                content.append(f"{pattern}\n", style=style)
            if not patterns_td:
                content.append("    (no patterns)\n", style=self.theme.dim_text)
        else:
            for pattern in patterns_td[:3]:
                content.append(f"    {pattern}\n", style=self.theme.dim_text)
            if len(patterns_td) > 3:
                content.append(
                    f"    ...and {len(patterns_td) - 3} more\n", style=self.theme.dim_text
                )

        content.append("\n")

        # Section 2: Thresholds
        section_style = f"bold {self.theme.info}" if section_idx == 2 else self.theme.primary_text
        content.append("Thresholds\n", style=section_style)

        thresholds = [
            ("large_payload_threshold", config.large_payload_threshold, "tokens"),
            ("redundant_min_occurrences", config.redundant_min_occurrences, "occurrences"),
        ]

        if section_idx == 2:
            for i, (name, value, unit) in enumerate(thresholds):
                is_selected = i == item_idx
                if is_selected:
                    content.append("  ▶ ", style=f"bold {self.theme.info}")
                else:
                    content.append("    ", style=self.theme.dim_text)
                style = f"bold {self.theme.info}" if is_selected else self.theme.primary_text
                content.append(f"{name}: ", style=style)
                content.append(f"{value:,} {unit}\n", style=self.theme.success)
        else:
            for name, value, unit in thresholds:
                content.append(f"    {name}: ", style=self.theme.dim_text)
                content.append(f"{value:,} {unit}\n", style=self.theme.dim_text)

        content.append("\n")
        content.append("─" * divider_width + "\n", style=self.theme.dim_text)

        # Config path info
        if config.config_path:
            content.append(f"Config: {config.config_path}", style=self.theme.dim_text)
        else:
            content.append("Config: (using defaults)", style=self.theme.dim_text)

        return Panel(
            content,
            title="[8] Bucket Configuration",
            border_style=self.theme.mcp_border,
            padding=(1, 2),
        )

    def _build_bucket_config_footer(self) -> Panel:
        """Build footer for Bucket Configuration view (v1.0.4 - task-247.13)."""
        section = self.state.bucket_config_section

        if section in (0, 1):  # Pattern sections
            footer_text = (
                "[j/k]Navigate  [Tab]Section  [a]Add  [d]Delete  [s]Save  [r]Reset  [Esc]Back"
            )
        else:  # Thresholds section
            footer_text = "[j/k]Navigate  [Tab]Section  [e]Edit  [s]Save  [r]Reset  [Esc]Back"

        return Panel(
            Text(footer_text, style=self.theme.dim_text, justify="center"),
            border_style=self.theme.mcp_border,
            padding=(0, 0),
        )

    def _handle_bucket_config_key(self, key: str) -> bool:
        """Handle key input for Bucket Configuration view (v1.0.4 - task-247.13)."""
        config = self.state.bucket_config
        if config is None:
            if key == "escape":
                self.state.mode = BrowserMode.DASHBOARD
            return False

        section = self.state.bucket_config_section

        # Get current section's item count
        if section == 0:
            items = config.patterns.get("state_serialization", [])
        elif section == 1:
            items = config.patterns.get("tool_discovery", [])
        else:  # section == 2
            items = ["large_payload_threshold", "redundant_min_occurrences"]

        if key == "escape":
            if self.state.bucket_config_modified:
                self.show_notification("Unsaved changes discarded", "warning")
            self.state.mode = BrowserMode.DASHBOARD
            return False

        if key in ("j", "down"):
            if items and self.state.bucket_config_item_index < len(items) - 1:
                self.state.bucket_config_item_index += 1
            return False

        if key in ("k", "up"):
            if items and self.state.bucket_config_item_index > 0:
                self.state.bucket_config_item_index -= 1
            return False

        if key == "tab":
            # Cycle through sections
            self.state.bucket_config_section = (section + 1) % 3
            self.state.bucket_config_item_index = 0
            return False

        if key == "a" and section in (0, 1):
            # Add pattern - open modal
            bucket = "state_serialization" if section == 0 else "tool_discovery"
            self.state.bucket_add_pattern_bucket = bucket
            self.state.bucket_add_pattern_input = ""
            self.state.mode = BrowserMode.ADD_PATTERN_MODAL
            return False

        if key == "d" and section in (0, 1):
            # Delete selected pattern
            if items and self.state.bucket_config_item_index < len(items):
                pattern = items[self.state.bucket_config_item_index]
                bucket = "state_serialization" if section == 0 else "tool_discovery"
                try:
                    from ..bucket_config import remove_pattern

                    remove_pattern(config, bucket, pattern)
                    self.state.bucket_config_modified = True
                    # Adjust selection if needed
                    if self.state.bucket_config_item_index >= len(items) - 1:
                        self.state.bucket_config_item_index = max(0, len(items) - 2)
                    self.show_notification(f"Removed pattern: {pattern}", "success")
                except Exception as e:
                    self.show_notification(f"Failed to remove: {e}", "error")
            return False

        if key == "e" and section == 2:
            # Edit threshold - for now just show a notification
            # Full implementation would use InputModal
            threshold_name = items[self.state.bucket_config_item_index]
            self.show_notification(
                f"Edit threshold '{threshold_name}' via: token-audit config set {threshold_name} <value>",
                "info",
            )
            return False

        if key == "s":
            # Save configuration
            try:
                from ..bucket_config import save_config

                save_config(config)
                self.state.bucket_config_modified = False
                self.show_notification("Configuration saved to token-audit.toml", "success")
            except Exception as e:
                self.show_notification(f"Failed to save: {e}", "error")
            return False

        if key == "r":
            # Reset to defaults
            try:
                from ..bucket_config import reset_to_defaults

                reset_to_defaults(config)
                self.state.bucket_config_modified = True
                self.state.bucket_config_item_index = 0
                self.show_notification("Reset to default patterns", "success")
            except Exception as e:
                self.show_notification(f"Failed to reset: {e}", "error")
            return False

        return False

    def _build_add_pattern_modal(self) -> Panel:
        """Build the Add Pattern modal (v1.0.4 - task-247.13)."""
        content = Text()

        bucket = self.state.bucket_add_pattern_bucket
        bucket_display = bucket.replace("_", " ").title()

        content.append(f"Add Pattern to {bucket_display}\n\n", style=f"bold {self.theme.title}")
        content.append("Enter a regex pattern:\n", style=self.theme.dim_text)
        content.append(
            f"> {self.state.bucket_add_pattern_input}_\n\n", style=self.theme.primary_text
        )
        content.append("Examples:\n", style=self.theme.dim_text)
        content.append(
            "  .*_get_.*      Match tool names containing '_get_'\n", style=self.theme.dim_text
        )
        content.append("  wpnav_list_.*  Match wpnav list tools\n", style=self.theme.dim_text)
        content.append("  ^mcp__.*       Match MCP server tools\n\n", style=self.theme.dim_text)
        content.append("[Enter] Add  [Esc] Cancel", style=self.theme.dim_text)

        return Panel(
            Align.center(content, vertical="middle"),
            title="Add Pattern",
            border_style=self.theme.info,
            padding=(2, 4),
        )

    def _handle_add_pattern_modal_key(self, key: str) -> bool:
        """Handle key input for Add Pattern modal (v1.0.4 - task-247.13)."""
        if key == "escape":
            self.state.mode = BrowserMode.BUCKET_CONFIG
            return False

        if key == "enter":
            pattern = self.state.bucket_add_pattern_input.strip()
            if pattern:
                try:
                    from ..bucket_config import add_pattern, validate_pattern

                    # Validate pattern first
                    is_valid, error = validate_pattern(pattern)
                    if not is_valid:
                        self.show_notification(f"Invalid regex: {error}", "error")
                        return False

                    config = self.state.bucket_config
                    if config:
                        add_pattern(config, self.state.bucket_add_pattern_bucket, pattern)
                        self.state.bucket_config_modified = True
                        self.show_notification(f"Added pattern: {pattern}", "success")
                except Exception as e:
                    self.show_notification(f"Failed to add: {e}", "error")
            self.state.mode = BrowserMode.BUCKET_CONFIG
            return False

        if key == "backspace":
            if self.state.bucket_add_pattern_input:
                self.state.bucket_add_pattern_input = self.state.bucket_add_pattern_input[:-1]
            return False

        # Regular character input
        if len(key) == 1 and key.isprintable():
            self.state.bucket_add_pattern_input += key
            return False

        return False
