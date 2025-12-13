"""
Session Browser - Interactive TUI for exploring past sessions.

Provides list view with filtering/sorting and detail view for individual sessions.
Uses Rich's Live display with keyboard input for interactive navigation.

v0.7.0 - task-105.1, task-105.3, task-105.4
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..preferences import PreferencesManager
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
from .theme_detect import get_active_theme
from .themes import THEMES, _ThemeType


class BrowserMode(Enum):
    """Browser display modes."""

    LIST = auto()
    DETAIL = auto()
    SEARCH = auto()
    SORT_MENU = auto()  # v0.7.0 - task-105.4
    HELP = auto()  # v0.7.0 - task-105.3
    TOOL_DETAIL = auto()  # v0.7.0 - task-105.7


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
    KeybindingInfo("q", "Quit browser", (BrowserMode.LIST, BrowserMode.DETAIL)),
    KeybindingInfo("?", "Show/hide help", (BrowserMode.LIST, BrowserMode.DETAIL)),
    KeybindingInfo("r", "Refresh sessions", (BrowserMode.LIST,)),
    KeybindingInfo("t", "Toggle theme", (BrowserMode.LIST, BrowserMode.DETAIL)),
    KeybindingInfo("j/k", "Move up/down", (BrowserMode.LIST, BrowserMode.SORT_MENU)),
    KeybindingInfo("Enter", "View/Select", (BrowserMode.LIST, BrowserMode.SORT_MENU)),
    KeybindingInfo(
        "Esc",
        "Back/Cancel",
        (BrowserMode.DETAIL, BrowserMode.SORT_MENU, BrowserMode.HELP, BrowserMode.TOOL_DETAIL),
    ),
    KeybindingInfo("p", "Pin/unpin session", (BrowserMode.LIST,)),
    KeybindingInfo("s", "Sort menu", (BrowserMode.LIST,)),
    KeybindingInfo("f", "Cycle platform filter", (BrowserMode.LIST,)),
    KeybindingInfo("/", "Search sessions", (BrowserMode.LIST,)),
    # v0.7.0 - task-105.7: Tool detail view
    KeybindingInfo("d", "Drill into tool", (BrowserMode.DETAIL,)),
    # v0.7.0 - task-105.8: AI export on all screens
    KeybindingInfo(
        "a", "AI export", (BrowserMode.LIST, BrowserMode.DETAIL, BrowserMode.TOOL_DETAIL)
    ),
]


@dataclass
class SessionEntry:
    """Summary of a session for list display."""

    path: Path
    session_date: date
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


@dataclass
class BrowserState:
    """Mutable state for the session browser."""

    mode: BrowserMode = BrowserMode.LIST
    sessions: List[SessionEntry] = field(default_factory=list)
    selected_index: int = 0
    scroll_offset: int = 0
    filter_platform: Optional[Platform] = None
    search_query: str = ""
    sort_key: str = "date"  # date, cost, tokens, duration, platform
    sort_reverse: bool = True  # newest/highest first
    sort_menu_index: int = 0  # v0.7.0 - task-105.4
    selected_tool: Optional[tuple[str, str]] = None  # v0.7.0 - task-105.7 (server, tool)


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
    ) -> None:
        """Initialize the session browser.

        Args:
            storage: StorageManager instance (created if not provided)
            theme: Theme name override (default: auto-detect)
        """
        self.storage = storage or StorageManager()
        self.console = Console()
        self.prefs = PreferencesManager()  # v0.7.0 - task-105.4
        self._theme_name = theme or "auto"
        self.theme: _ThemeType = get_active_theme(override=theme)
        self.box_style: box.Box = get_box_style()
        self.state = BrowserState()
        self.visible_rows = 15  # Sessions visible without scrolling
        self._detail_data: Optional[Dict[str, Any]] = None
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

    def run(self) -> None:
        """Run the interactive browser."""
        # Load sessions
        self._load_sessions()

        if not self.state.sessions:
            self.console.print(
                Panel(
                    "No sessions found.\n\nRun 'mcp-audit collect' to start tracking.",
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
            with Live(
                self._build_layout(),
                console=self.console,
                refresh_per_second=4,
                transient=True,
            ) as live:
                while True:
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

        # Sort pinned first (not is_pinned = False for pinned, True for unpinned)
        # Then sort by the selected key within each group
        sessions.sort(
            key=lambda e: (not e.is_pinned, sort_fn(e)),
            reverse=self.state.sort_reverse if not sessions or not sessions[0].is_pinned else False,
        )

        # Re-sort to ensure pinned are always at top regardless of sort direction
        pinned = [e for e in sessions if e.is_pinned]
        unpinned = [e for e in sessions if not e.is_pinned]
        unpinned.sort(key=sort_fn, reverse=self.state.sort_reverse)
        sessions = pinned + unpinned

        self.state.sessions = sessions
        self.state.selected_index = min(self.state.selected_index, max(0, len(sessions) - 1))

    def _load_session_entry(self, session_path: Path) -> Optional[SessionEntry]:
        """Load session metadata into a SessionEntry."""
        try:
            # Load the JSON file
            with open(session_path) as f:
                data = json.load(f)

            # Extract data from session format
            session_info = data.get("session", data)  # Handle both formats

            # Parse timestamp
            timestamp_str = session_info.get("timestamp", "")
            if timestamp_str:
                try:
                    session_date = datetime.fromisoformat(timestamp_str).date()
                except ValueError:
                    session_date = date.today()
            else:
                session_date = date.today()

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
        if self.state.mode == BrowserMode.LIST:
            return self._handle_list_key(key)
        elif self.state.mode == BrowserMode.DETAIL:
            return self._handle_detail_key(key)
        elif self.state.mode == BrowserMode.TOOL_DETAIL:
            return self._handle_tool_detail_key(key)
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
                self.state.mode = BrowserMode.DETAIL
        elif key == "/":
            self.state.mode = BrowserMode.SEARCH
            self.state.search_query = ""
        elif key in ("s", "S"):
            # v0.7.0 - Open sort menu instead of cycling
            self.state.mode = BrowserMode.SORT_MENU
            self.state.sort_menu_index = 0
        elif key in ("f", "F"):
            self._cycle_platform_filter()
        elif key in ("r", "R"):
            self._load_sessions()  # Refresh
        elif key in ("p", "P"):
            # v0.7.0 - task-105.4: Pin/unpin session
            self._toggle_pin()
        elif key == "?":
            # v0.7.0 - task-105.3: Show help overlay
            self.state.mode = BrowserMode.HELP
        elif key in ("t", "T"):
            # v0.7.0 - task-105.3: Toggle theme
            self._toggle_theme()
        elif key in ("a", "A"):
            # v0.7.0 - task-105.8: AI export for selected session
            self._export_list_ai_prompt()
        # Future panel navigation (no-op for now)
        elif key in ("h", "l", KEY_LEFT, KEY_RIGHT, KEY_TAB, KEY_SHIFT_TAB):
            pass  # Reserved for future panel navigation
        return False

    def _handle_detail_key(self, key: str) -> bool:
        """Handle key in detail view."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE):
            self.state.mode = BrowserMode.LIST
            self._detail_data = None
        elif key in ("d", "D"):
            # Drill into tool detail (v0.7.0 - task-105.7)
            self._select_top_tool()
        elif key in ("a", "A"):
            # v0.7.0 - task-105.8: AI export for session detail
            self._export_session_ai_prompt()
        return False

    def _handle_tool_detail_key(self, key: str) -> bool:
        """Handle key in tool detail view (v0.7.0 - task-105.7)."""
        if key in ("q", KEY_ESC, KEY_BACKSPACE, KEY_LEFT):
            # Return to session detail view
            self.state.mode = BrowserMode.DETAIL
            self.state.selected_tool = None
        elif key in ("a", "A"):
            # Export AI analysis prompt for this tool
            self._export_tool_ai_prompt()
        return False

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
            self.state.mode = BrowserMode.TOOL_DETAIL

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
        """Export AI analysis prompt for selected session in list view (v0.7.0 - task-105.8)."""
        if not self.state.sessions:
            return

        session = self.state.sessions[self.state.selected_index]

        # Generate markdown prompt
        lines = [
            "# Session Summary Analysis Request",
            "",
            "Please analyze this MCP Audit session summary:",
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
            "Please analyze this MCP Audit session data:",
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
        """Copy text to clipboard (macOS) with fallback."""
        try:
            import subprocess

            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            # Success - prompt copied (can't show message in TUI currently)
        except Exception:
            # Fallback - just silently succeed since we can't show output
            pass

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
        """Handle key in help overlay. v0.7.0 - task-105.3"""
        if key in ("q", "Q"):
            return True
        # Any key dismisses help overlay
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

        if self.state.mode == BrowserMode.DETAIL:
            layout.split_column(
                Layout(self._build_detail_view(), name="detail"),
                Layout(self._build_detail_footer(), name="footer", size=1),
            )
        elif self.state.mode == BrowserMode.TOOL_DETAIL:
            # v0.7.0 - task-105.7: Tool detail view
            layout.split_column(
                Layout(self._build_tool_detail_view(), name="tool_detail"),
                Layout(self._build_tool_detail_footer(), name="footer", size=1),
            )
        elif self.state.mode == BrowserMode.SORT_MENU:
            # v0.7.0 - task-105.4: Sort menu overlay
            layout.split_column(
                Layout(self._build_header(), name="header", size=4),
                Layout(self._build_sort_menu(), name="menu"),
                Layout(self._build_sort_menu_footer(), name="footer", size=1),
            )
        elif self.state.mode == BrowserMode.HELP:
            # v0.7.0 - task-105.3: Help overlay
            layout.split_column(
                Layout(self._build_help_overlay(), name="help"),
                Layout(self._build_help_footer(), name="footer", size=1),
            )
        else:
            layout.split_column(
                Layout(self._build_header(), name="header", size=4),
                Layout(self._build_session_table(), name="table"),
                Layout(self._build_footer(), name="footer", size=1),
            )

        return layout

    def _build_header(self) -> Panel:
        """Build header with filters and search."""
        content = Text()
        content.append("Session Browser", style=f"bold {self.theme.title}")
        content.append(f"  ({len(self.state.sessions)} sessions)\n", style=self.theme.dim_text)

        # Active filters
        filters = []
        if self.state.filter_platform:
            filters.append(f"platform={self.state.filter_platform}")
        if self.state.search_query:
            filters.append(f'search="{self.state.search_query}"')
        if filters:
            content.append(f"Filters: {', '.join(filters)}", style=self.theme.warning)

        return Panel(content, border_style=self.theme.header_border, box=self.box_style)

    def _build_session_table(self) -> Panel:
        """Build the session list table."""
        table = Table(
            box=self.box_style,
            show_header=True,
            header_style=f"bold {self.theme.primary_text}",
            expand=True,
        )

        table.add_column("", width=1)  # Selection indicator
        table.add_column("", width=2)  # Pin indicator - v0.7.0 task-105.4
        table.add_column("Date", width=10)
        table.add_column("Platform", width=12)
        table.add_column("Project", width=18)
        table.add_column("Tokens", justify="right", width=10)
        table.add_column("Cost", justify="right", width=10)
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
            is_selected = actual_idx == self.state.selected_index

            indicator = ">" if is_selected else " "
            # Pin indicator with ASCII fallback - v0.7.0 task-105.4
            pin_indicator = ascii_emoji("\U0001f4cc") if entry.is_pinned else ""
            row_style = f"bold {self.theme.info}" if is_selected else ""

            # Truncate project name if needed
            project_display = (
                entry.project[:16] + ".." if len(entry.project) > 18 else entry.project
            )

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

            table.add_row(
                indicator,
                pin_indicator,
                entry.session_date.strftime("%Y-%m-%d"),
                entry.platform.replace("_", "-"),
                project_display,
                tokens_str,
                f"${entry.cost_estimate:.4f}",
                str(entry.tool_count),
                acc_text,
                style=row_style,
            )

        # Show scroll indicator if more sessions exist
        title = f"Sessions (sorted by {self.state.sort_key})"
        if len(self.state.sessions) > self.visible_rows:
            title += f" [{start + 1}-{end}/{len(self.state.sessions)}]"

        return Panel(table, title=title, border_style=self.theme.mcp_border, box=self.box_style)

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

        # Line 2: Keybindings (v0.7.0 - task-105.8)
        footer.append(
            "q=quit  ?=help  a=AI  p=pin  s=sort  f=filter  /=search  r=refresh  t=theme",
            style=self.theme.dim_text,
        )
        footer.justify = "center"
        return footer

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
        """Build help overlay with keybindings. v0.7.0 - task-105.3"""
        table = Table(
            box=self.box_style,
            show_header=True,
            header_style=f"bold {self.theme.primary_text}",
        )
        table.add_column("Key", style=self.theme.info, width=12)
        table.add_column("Action", style=self.theme.primary_text)

        for kb in KEYBINDINGS:
            table.add_row(kb.keys, kb.description)

        # Add navigation hint
        content = Text()
        content.append("\n")

        return Panel(
            table,
            title="Keyboard Shortcuts",
            subtitle="Press any key to close",
            border_style=self.theme.header_border,
            box=self.box_style,
        )

    def _build_help_footer(self) -> Text:
        """Build footer for help overlay. v0.7.0 - task-105.3"""
        return Text(
            "Press any key to close  |  q=quit browser",
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
        # v0.7.0 - Added AI export (task-105.8)
        return Text(
            "a=AI  d=tool detail  q/ESC=back to list",
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
