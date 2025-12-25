"""
RichDisplay - Rich-based TUI with in-place updating.

Uses Rich's Live display for a beautiful, real-time updating dashboard
that shows session metrics without scrolling.

Supports Catppuccin color themes (dark/light) and ASCII mode for
terminals with limited Unicode support.
"""

import contextlib
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..base_tracker import SCHEMA_VERSION
from .ascii_mode import ascii_emoji, get_box_style, is_ascii_mode
from .base import DisplayAdapter
from .keyboard import check_keypress, disable_raw_mode, enable_raw_mode
from .snapshot import DisplaySnapshot
from .theme_detect import get_active_theme
from .themes import _ThemeType


@dataclass
class Notification:
    """Transient notification for user feedback (v0.8.0 - task-106.9).

    Attributes:
        message: The notification message to display.
        level: Notification type - "success", "warning", "error", or "info".
        expires_at: Unix timestamp when notification should auto-dismiss.
    """

    message: str
    level: str  # "success", "warning", "error", "info"
    expires_at: float  # time.time() + timeout


class RichDisplay(DisplayAdapter):
    """Rich-based TUI with in-place updating dashboard.

    Provides a beautiful terminal UI that updates in place,
    showing real-time token usage, tool calls, and activity.

    Supports Catppuccin color themes for light/dark mode and
    ASCII mode for legacy terminal compatibility.
    """

    def __init__(
        self,
        refresh_rate: float = 0.5,
        pinned_servers: Optional[List[str]] = None,
        theme: Optional[str] = None,
    ) -> None:
        """Initialize Rich display.

        Args:
            refresh_rate: Display refresh rate in seconds (default 0.5 = 2Hz)
            pinned_servers: List of server names to pin at top of MCP section
            theme: Theme name override (default: auto-detect from environment)
        """
        self.console = Console()
        self.refresh_rate = refresh_rate
        self.pinned_servers = set(pinned_servers) if pinned_servers else set()
        self.live: Optional[Live] = None
        self.recent_events: Deque[Tuple[datetime, str, int]] = deque(maxlen=5)
        self._current_snapshot: Optional[DisplaySnapshot] = None
        self._fallback_warned = False

        # Theme support (task-83)
        self.theme: _ThemeType = get_active_theme(override=theme)
        self.ascii_mode: bool = is_ascii_mode()
        self.box_style: box.Box = get_box_style()

        # Keyboard support (v0.7.0 - task-105.8)
        self._raw_mode_enabled: bool = False

        # Notification support (v0.8.0 - task-106.9)
        self._notification: Optional[Notification] = None

        # Performance optimization: dirty-flag caching (v0.9.0 - task-107.3)
        # Only rebuild panels that have changed between snapshots
        self._last_snapshot: Optional[DisplaySnapshot] = None
        self._cached_panels: dict[str, Any] = {}
        self._dirty_flags: dict[str, bool] = {
            "header": True,
            "tokens": True,
            "tools": True,
            "smells": True,
            "context_tax": True,
            "activity": True,
            "notification": True,
        }

    def start(self, snapshot: DisplaySnapshot) -> None:
        """Start the live display."""
        self._current_snapshot = snapshot
        # Enable raw mode for keyboard capture (v0.7.0 - task-105.8)
        self._raw_mode_enabled = enable_raw_mode()
        self.live = Live(
            self._build_layout(snapshot),
            console=self.console,
            refresh_per_second=1 / self.refresh_rate,
            transient=True,  # Clear display on stop to avoid gap before summary (task-49.5)
        )
        self.live.start()

    def update(self, snapshot: DisplaySnapshot) -> Optional[str]:
        """Update display with new snapshot.

        Returns:
            Optional action string if key pressed:
            - "ai_export": User pressed [A] for AI export
            - "quit": User pressed [Q] to quit
            - None: No action
        """
        self._current_snapshot = snapshot

        # Clear expired notifications (v0.8.0 - task-106.9)
        if self._notification and time.time() > self._notification.expires_at:
            self._notification = None

        # Check for keypresses (non-blocking) - v0.7.0 task-105.8
        if self._raw_mode_enabled:
            key = check_keypress(timeout=0.0)  # Non-blocking
            if key in ("a", "A"):
                self._export_live_ai_prompt()
                return "ai_export"
            elif key in ("q", "Q"):
                return "quit"

        if self.live:
            try:
                self.live.update(self._build_layout(snapshot))
            except Exception as e:
                # Graceful fallback if rendering fails
                if not self._fallback_warned:
                    import sys

                    print(
                        f"Warning: TUI rendering failed ({e}), continuing without updates",
                        file=sys.stderr,
                    )
                    self._fallback_warned = True
        return None

    def on_event(self, tool_name: str, tokens: int, timestamp: datetime) -> None:
        """Add event to recent activity feed."""
        self.recent_events.append((timestamp, tool_name, tokens))

    def show_notification(self, message: str, level: str = "info", timeout: float = 3.0) -> None:
        """Show a transient notification in the TUI (v0.8.0 - task-106.9).

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

    def stop(self, snapshot: DisplaySnapshot) -> None:
        """Stop live display and show final summary."""
        # Disable raw mode for keyboard capture (v0.7.0 - task-105.8)
        if self._raw_mode_enabled:
            disable_raw_mode()
            self._raw_mode_enabled = False
        if self.live:
            with contextlib.suppress(Exception):
                self.live.stop()
            self.live = None
        self._print_final_summary(snapshot)

    def _detect_changes(self, old: DisplaySnapshot, new: DisplaySnapshot) -> None:
        """Detect which panels need rebuilding based on snapshot changes.

        Sets dirty flags for panels where relevant data has changed.
        This optimization avoids rebuilding unchanged panels (v0.9.0 - task-107.3).
        """
        # Header changes: project, platform, model, duration, git info
        if any(
            [
                old.project != new.project,
                old.platform != new.platform,
                old.model_name != new.model_name,
                old.model_id != new.model_id,
                old.is_multi_model != new.is_multi_model,
                abs(old.duration_seconds - new.duration_seconds) >= 1.0,  # Only on second change
                old.git_branch != new.git_branch,
                old.git_commit_short != new.git_commit_short,
                old.git_status != new.git_status,
                old.files_monitored != new.files_monitored,
                old.static_cost_total != new.static_cost_total,
                old.zombie_context_tax != new.zombie_context_tax,
            ]
        ):
            self._dirty_flags["header"] = True

        # Token panel changes
        if any(
            [
                old.total_tokens != new.total_tokens,
                old.input_tokens != new.input_tokens,
                old.output_tokens != new.output_tokens,
                old.cache_tokens != new.cache_tokens,
                abs(old.cost_estimate - new.cost_estimate) >= 0.001,
                abs(old.cache_efficiency - new.cache_efficiency) >= 0.01,
                old.message_count != new.message_count,
                old.builtin_tool_calls != new.builtin_tool_calls,
            ]
        ):
            self._dirty_flags["tokens"] = True

        # Tools panel changes (check call counts, not full hierarchy)
        if any(
            [
                old.total_tool_calls != new.total_tool_calls,
                old.unique_tools != new.unique_tools,
                len(old.server_hierarchy) != len(new.server_hierarchy),
            ]
        ):
            self._dirty_flags["tools"] = True

        # Smells panel changes
        if old.detected_smells != new.detected_smells:
            self._dirty_flags["smells"] = True

        # Context tax panel changes
        if any(
            [
                old.static_cost_total != new.static_cost_total,
                old.static_cost_by_server != new.static_cost_by_server,
                old.zombie_context_tax != new.zombie_context_tax,
            ]
        ):
            self._dirty_flags["context_tax"] = True

        # Activity always updates if there are recent events
        # (handled separately since it uses self.recent_events)
        self._dirty_flags["activity"] = True  # Always rebuild activity

        # Notification changes
        if self._notification:
            self._dirty_flags["notification"] = True

    def _build_layout(self, snapshot: DisplaySnapshot) -> Layout:
        """Build the dashboard layout with dirty-flag caching (v0.9.0 - task-107.3).

        Only rebuilds panels whose underlying data has changed, using cached
        versions for unchanged panels to improve refresh performance.
        """
        layout = Layout()

        # Detect which panels need rebuilding
        if self._last_snapshot is not None:
            self._detect_changes(self._last_snapshot, snapshot)
        else:
            # First build - everything is dirty
            for key in self._dirty_flags:
                self._dirty_flags[key] = True

        # Build or use cached header panel
        if self._dirty_flags["header"] or "header" not in self._cached_panels:
            self._cached_panels["header"] = self._build_header(snapshot)
            self._dirty_flags["header"] = False

        # Build or use cached tokens panel
        if self._dirty_flags["tokens"] or "tokens" not in self._cached_panels:
            self._cached_panels["tokens"] = self._build_tokens(snapshot)
            self._dirty_flags["tokens"] = False

        # Build or use cached tools panel
        if self._dirty_flags["tools"] or "tools" not in self._cached_panels:
            self._cached_panels["tools"] = self._build_tools(snapshot)
            self._dirty_flags["tools"] = False

        # Build or use cached smells panel (if applicable)
        if snapshot.detected_smells and (
            self._dirty_flags["smells"] or "smells" not in self._cached_panels
        ):
            self._cached_panels["smells"] = self._build_smells(snapshot)
            self._dirty_flags["smells"] = False

        # Build or use cached context tax panel (if applicable)
        if snapshot.static_cost_total > 0 and (
            self._dirty_flags["context_tax"] or "context_tax" not in self._cached_panels
        ):
            self._cached_panels["context_tax"] = self._build_context_tax(snapshot)
            self._dirty_flags["context_tax"] = False

        # Activity panel always rebuilds (uses self.recent_events which isn't in snapshot)
        self._cached_panels["activity"] = self._build_activity()

        # Footer is static, only build once
        if "footer" not in self._cached_panels:
            self._cached_panels["footer"] = self._build_footer()

        # Notification panel (if active)
        if self._notification:
            self._cached_panels["notification"] = self._build_notification()

        # Assemble layout using cached panels
        # Header size=7 to accommodate context tax line (v0.7.0 - task-105.9)
        # Tokens size=9 to accommodate rate metrics row (v0.7.0 - task-105.12)
        panels = [
            Layout(self._cached_panels["header"], name="header", size=7),
            Layout(self._cached_panels["tokens"], name="tokens", size=9),
        ]

        # Tools and Smells: side-by-side if smells detected, otherwise tools only
        if snapshot.detected_smells:
            tools_and_smells = Layout()
            tools_and_smells.split_row(
                Layout(self._cached_panels["tools"], name="tools", ratio=3),
                Layout(self._cached_panels["smells"], name="smells", ratio=2),
            )
            panels.append(Layout(tools_and_smells, name="tools_smells", size=12))
        else:
            panels.append(Layout(self._cached_panels["tools"], name="tools", size=12))

        # Add context tax panel if static_cost data is available
        if snapshot.static_cost_total > 0:
            panels.append(Layout(self._cached_panels["context_tax"], name="context_tax", size=6))

        panels.extend(
            [
                Layout(self._cached_panels["activity"], name="activity", size=6),
                Layout(self._cached_panels["footer"], name="footer", size=1),
            ]
        )

        # Add notification bar if active (v0.8.0 - task-106.9)
        if self._notification:
            panels.append(Layout(self._cached_panels["notification"], name="notification", size=1))

        layout.split_column(*panels)

        # Update last snapshot reference for next comparison
        self._last_snapshot = snapshot

        return layout

    def _build_header(self, snapshot: DisplaySnapshot) -> Panel:
        """Build header panel with project info, model, git metadata, and file monitoring."""
        duration = self._format_duration_human(snapshot.duration_seconds)
        version_str = f" v{snapshot.version}" if snapshot.version else ""

        header_text = Text()
        header_text.append(f"Token Audit{version_str} - ", style=f"bold {self.theme.title}")
        # Show session type based on tracking mode
        if snapshot.tracking_mode == "full":
            sync_indicator = ascii_emoji("↺")
            header_text.append(f"Full Session {sync_indicator}", style=f"bold {self.theme.warning}")
        else:
            header_text.append("Live Session", style=f"bold {self.theme.title}")
        header_text.append(f"  [{snapshot.platform}]", style=f"bold {self.theme.title}")

        # Project and started time
        started_str = snapshot.start_time.strftime("%H:%M:%S")
        header_text.append(f"\nProject: {snapshot.project}", style=self.theme.primary_text)
        header_text.append(f"  Started: {started_str}", style=self.theme.dim_text)
        header_text.append(f"  Duration: {duration}", style=self.theme.dim_text)

        # Model name (v1.6.0: multi-model support)
        if snapshot.is_multi_model and snapshot.model_usage:
            # Multi-model: show count and breakdown
            header_text.append(
                f"\nModels ({len(snapshot.models_used)}): ", style=self.theme.success
            )
            # Sort models by total_tokens descending for display
            sorted_models = sorted(
                snapshot.model_usage, key=lambda m: m[3], reverse=True  # m[3] = total_tokens
            )
            total_tokens = sum(m[3] for m in sorted_models)
            model_strs = []
            for m in sorted_models[:3]:  # Show top 3 models
                model_name = m[0]
                model_tokens = m[3]
                pct = (model_tokens / total_tokens * 100) if total_tokens > 0 else 0
                # Truncate long model names
                display_name = model_name[:20] + "..." if len(model_name) > 20 else model_name
                model_strs.append(f"{display_name} ({pct:.0f}%)")
            header_text.append(", ".join(model_strs), style=self.theme.success)
            if len(sorted_models) > 3:
                header_text.append(f" +{len(sorted_models) - 3} more", style=self.theme.dim_text)
        elif snapshot.model_name and snapshot.model_name != "Unknown Model":
            header_text.append(f"\nModel: {snapshot.model_name}", style=self.theme.success)
        elif snapshot.model_id:
            header_text.append(f"\nModel: {snapshot.model_id}", style=self.theme.success)

        # Git metadata and file monitoring
        git_info = []
        if snapshot.git_branch:
            branch_emoji = ascii_emoji("🌿")
            git_info.append(f"{branch_emoji} {snapshot.git_branch}")
        if snapshot.git_commit_short:
            git_info.append(f"@{snapshot.git_commit_short}")
        if snapshot.git_status == "dirty":
            git_info.append("*")
        if snapshot.files_monitored > 0:
            files_emoji = ascii_emoji("📁")
            git_info.append(f"  {files_emoji} {snapshot.files_monitored} files")
        # Session ID (v0.7.0 - task-105.11)
        if snapshot.session_dir:
            session_id = Path(snapshot.session_dir).name
            display_id = session_id[:20] + "..." if len(session_id) > 20 else session_id
            git_info.append(f"  Session: {display_id}")

        if git_info:
            header_text.append(f"\n{''.join(git_info)}", style=self.theme.dim_text)

        # Static Cost & Zombie Tools in header (v0.7.0 - task-105.9)
        context_metrics = []
        if snapshot.static_cost_total > 0:
            context_metrics.append(
                f"Context Tax: {self._format_tokens(snapshot.static_cost_total)}"
            )
        if snapshot.zombie_context_tax > 0:
            warning_emoji = ascii_emoji("⚠")
            context_metrics.append(
                f"{warning_emoji} Zombie Tax: {self._format_tokens(snapshot.zombie_context_tax)}"
            )

        if context_metrics:
            header_text.append(f"\n{' | '.join(context_metrics)}", style=self.theme.warning)

        return Panel(header_text, border_style=self.theme.header_border, box=self.box_style)

    def _build_tokens(self, snapshot: DisplaySnapshot) -> Panel:
        """Build token usage panel with 3-column layout."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        # Column 1: Tokens (Input, Output, Total, Messages)
        table.add_column("Label1", style=self.theme.dim_text, width=16)
        table.add_column("Value1", justify="right", width=12)
        # Column 2: Cache (Created, Read, Efficiency, Built-in)
        table.add_column("Label2", style=self.theme.dim_text, width=16)
        table.add_column("Value2", justify="right", width=12)
        # Column 3: Cost (w/ Cache, w/o Cache, Savings)
        table.add_column("Label3", style=self.theme.dim_text, width=16)
        table.add_column("Value3", justify="right", width=14)

        # Data quality indicator (v1.5.0 - task-103.5)
        # "~" prefix for estimated values, nothing for exact
        approx = "~" if snapshot.accuracy_level == "estimated" else ""

        # Row 1: Input | Cache Created | Cost w/ Cache
        table.add_row(
            "Input:",
            f"{snapshot.input_tokens:,}",
            "Cache Created:",
            f"{snapshot.cache_created_tokens:,}",
            "Cost w/ Cache:",
            f"${snapshot.cost_estimate:.4f}",
        )

        # Row 2: Output | Cache Read | Cost w/o Cache
        table.add_row(
            "Output:",
            f"{snapshot.output_tokens:,}",
            "Cache Read:",
            f"{snapshot.cache_read_tokens:,}",
            "Cost w/o Cache:",
            f"${snapshot.cost_no_cache:.4f}" if snapshot.cost_no_cache > 0 else "$-.----",
        )

        # Row 2.5 (conditional): Reasoning tokens - only shown when > 0
        if snapshot.reasoning_tokens > 0:
            table.add_row(
                "Reasoning:",
                f"{snapshot.reasoning_tokens:,}",
                "",
                "",
                "",
                "",
            )

        # Row 3: Total | Efficiency | Savings/Net Cost
        savings_emoji = ascii_emoji("💰")
        cost_emoji = ascii_emoji("💸")
        if snapshot.cache_savings > 0:
            savings_label = f"{savings_emoji} Savings:"
            savings_str = f"${snapshot.cache_savings:.4f}"
            savings_pct = (
                f"({snapshot.savings_percent:.0f}%)" if snapshot.savings_percent > 0 else ""
            )
            savings_display = f"{savings_str} {savings_pct}"
        elif snapshot.cache_savings < 0:
            savings_label = f"{cost_emoji} Net Cost:"
            savings_str = f"${abs(snapshot.cache_savings):.4f}"
            hint = self._get_cache_inefficiency_hint(snapshot)
            savings_display = f"{savings_str} {hint}" if hint else savings_str
        else:
            # Zero savings - neutral display
            savings_label = f"{savings_emoji} Savings:"
            savings_display = "$0.0000"
        # Show "~" prefix for estimated token counts (v1.5.0 - task-103.5)
        total_display = (
            f"{approx}{snapshot.total_tokens:,}" if approx else f"{snapshot.total_tokens:,}"
        )
        table.add_row(
            "Total:",
            total_display,
            "Efficiency:",
            f"{snapshot.cache_efficiency:.1%}",
            savings_label,
            savings_display,
        )

        # Row 4: Messages | Built-in Tools | Cache Hit Ratio (v0.7.0 - task-105.13)
        builtin_str = (
            f"{snapshot.builtin_tool_calls} ({self._format_tokens(snapshot.builtin_tool_tokens)})"
        )
        # Cache hit ratio: what % of input came from cache (token-based, not cost-based)
        cache_hit_ratio = 0.0
        denominator = snapshot.cache_read_tokens + snapshot.input_tokens
        if denominator > 0:
            cache_hit_ratio = snapshot.cache_read_tokens / denominator
        table.add_row(
            "Messages:",
            f"{snapshot.message_count}",
            "Built-in Tools:",
            builtin_str,
            "Cache Hit:",
            f"{cache_hit_ratio:.1%}",
        )

        # Row 5: Rate metrics (v0.7.0 - task-105.12)
        # Only meaningful after ~30s, show actual rate not extrapolated for short sessions
        if snapshot.duration_seconds > 0:
            tokens_per_min = snapshot.total_tokens / (snapshot.duration_seconds / 60)
            calls_per_min = snapshot.total_tool_calls / (snapshot.duration_seconds / 60)
            # Format rate: use K/M suffix for tokens
            tokens_rate_str = f"{self._format_tokens(int(tokens_per_min))}/min"
            calls_rate_str = f"{calls_per_min:.1f}/min"
        else:
            tokens_rate_str = "—"
            calls_rate_str = "—"
        table.add_row(
            "Token Rate:",
            tokens_rate_str,
            "Call Rate:",
            calls_rate_str,
            "",
            "",
        )

        # Panel title includes accuracy indicator (v1.5.0 - task-103.5)
        if snapshot.accuracy_level == "estimated":
            confidence_pct = int(snapshot.data_quality_confidence * 100)
            title = f"Token Usage & Cost (~{confidence_pct}% accuracy)"
        else:
            title = "Token Usage & Cost"

        return Panel(
            table,
            title=title,
            border_style=self.theme.tokens_border,
            box=self.box_style,
        )

    def _build_tools(self, snapshot: DisplaySnapshot) -> Panel:
        """Build MCP Server→Tools hierarchy."""
        content = Text()

        # Max content lines (size=14 minus 2 for panel border)
        max_display_lines = 9
        lines_used = 0
        servers_shown = 0
        tools_shown = 0
        truncated = False

        if snapshot.server_hierarchy:
            total_servers = len(snapshot.server_hierarchy)
            total_tools = sum(len(s[4]) for s in snapshot.server_hierarchy)

            # Detect if platform provides per-tool tokens
            total_mcp_tokens = sum(s[2] for s in snapshot.server_hierarchy)
            show_tokens = total_mcp_tokens > 0

            # Sort servers: pinned first, then by token usage
            server_list = list(snapshot.server_hierarchy)
            if self.pinned_servers:
                server_list.sort(key=lambda s: (0 if s[0] in self.pinned_servers else 1))

            # Show server hierarchy
            for server_data in server_list:
                server_name, server_calls, server_tokens, server_avg, tools = server_data

                if lines_used >= max_display_lines - 1:
                    truncated = True
                    break

                # Server line with pin indicator if pinned
                is_pinned = server_name in self.pinned_servers
                if is_pinned:
                    pin_emoji = ascii_emoji("📌")
                    content.append(f"  {pin_emoji} ", style=self.theme.pinned_indicator)
                    content.append(
                        f"{server_name:<15}", style=f"{self.theme.pinned_indicator} bold"
                    )
                else:
                    content.append(f"  {server_name:<18}", style=f"{self.theme.server_name} bold")
                content.append(f" {server_calls:>3} calls", style=self.theme.dim_text)

                if show_tokens:
                    tokens_str = self._format_tokens(server_tokens)
                    avg_str = self._format_tokens(server_avg)
                    content.append(f"  {tokens_str:>8}", style=self.theme.primary_text)
                    content.append(f"  (avg {avg_str}/call)", style=self.theme.dim_text)
                content.append("\n")
                lines_used += 1
                servers_shown += 1

                # Tool breakdown
                for tool_short, tool_calls, tool_tokens, pct_of_server in tools:
                    if lines_used >= max_display_lines:
                        truncated = True
                        break

                    content.append(f"    └─ {tool_short:<15}", style=self.theme.dim_text)
                    content.append(f" {tool_calls:>3} calls", style=self.theme.dim_text)

                    if show_tokens:
                        tool_tokens_str = self._format_tokens(tool_tokens)
                        content.append(f"  {tool_tokens_str:>8}", style=self.theme.dim_text)
                        content.append(
                            f"  ({pct_of_server:.0f}% of server)", style=self.theme.dim_text
                        )
                    content.append("\n")
                    lines_used += 1
                    tools_shown += 1

                if truncated:
                    break

            # Truncation indicator
            if truncated:
                remaining_servers = total_servers - servers_shown
                remaining_tools = total_tools - tools_shown
                if remaining_servers > 0 and remaining_tools > 0:
                    content.append(
                        f"  ... +{remaining_servers} more server(s), +{remaining_tools} more tool(s)\n",
                        style=f"{self.theme.warning} italic",
                    )
                elif remaining_tools > 0:
                    content.append(
                        f"  ... +{remaining_tools} more tool(s)\n",
                        style=f"{self.theme.warning} italic",
                    )

            # Summary line with MCP percentage of session
            total_mcp_calls = snapshot.total_tool_calls
            content.append("  ─" * 30 + "\n", style=self.theme.dim_text)
            content.append(f"  Total MCP: {total_mcp_calls} calls", style=self.theme.primary_text)
            if show_tokens and snapshot.mcp_tokens_percent > 0:
                content.append(
                    f"  ({snapshot.mcp_tokens_percent:.0f}% of session tokens)",
                    style=self.theme.dim_text,
                )
        else:
            content.append("  No MCP tools called yet", style=f"{self.theme.dim_text} italic")

        # Add estimation info for platforms that estimate MCP tokens (task-69.32)
        if snapshot.estimated_tool_calls > 0 and snapshot.estimation_method:
            content.append("\n")
            method = snapshot.estimation_method
            content.append(
                f"  MCP tokens estimated via {method}. See github.com/littlebearapps/token-audit",
                style=f"{self.theme.dim_text} italic",
            )

        # Title includes server count and unique tools (v0.7.0 - task-105.13)
        # Calculate MCP calls from server_hierarchy only (excludes built-in tools)
        num_servers = len(snapshot.server_hierarchy)
        mcp_calls = sum(s[1] for s in snapshot.server_hierarchy) if snapshot.server_hierarchy else 0
        title = (
            f"MCP Servers ({num_servers} servers, {snapshot.unique_tools} tools, {mcp_calls} calls)"
        )

        return Panel(content, title=title, border_style=self.theme.mcp_border, box=self.box_style)

    def _format_tokens(self, tokens: int) -> str:
        """Format token count with K/M suffix."""
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        elif tokens >= 1_000:
            return f"{tokens / 1_000:.0f}K"
        else:
            return str(tokens)

    def _get_cache_inefficiency_hint(self, snapshot: DisplaySnapshot) -> str:
        """Get brief explanation for cache inefficiency.

        Returns a short hint explaining why cache is costing more than saving.
        """
        created = snapshot.cache_created_tokens
        read = snapshot.cache_read_tokens

        if created > 0 and read == 0:
            return "(new context, no reuse)"
        elif created > 0 and read > 0:
            ratio = read / created if created > 0 else 0
            if ratio < 0.1:
                return "(high creation, low reuse)"
            else:
                return "(creation > savings)"
        elif created == 0 and read == 0:
            return "(no cache activity)"
        else:
            return ""

    def _build_context_tax(self, snapshot: DisplaySnapshot) -> Panel:
        """Build context tax panel showing MCP schema overhead (v0.6.0 - task-114.3)."""
        content = Text()

        # Total schema tokens
        total = snapshot.static_cost_total
        content.append("Total Schema Tokens: ", style=self.theme.dim_text)
        content.append(f"{total:,}\n", style=f"bold {self.theme.warning}")

        # Source and confidence
        source = snapshot.static_cost_source
        confidence = snapshot.static_cost_confidence * 100
        content.append(f"Source: {source} ", style=self.theme.dim_text)
        content.append(f"({confidence:.0f}% confidence)\n", style=self.theme.dim_text)

        # Per-server breakdown (if available)
        if snapshot.static_cost_by_server:
            content.append("\nBy Server:\n", style=self.theme.dim_text)
            # Sort servers by tokens descending
            sorted_servers = sorted(
                snapshot.static_cost_by_server, key=lambda x: x[1], reverse=True
            )
            for server_name, tokens in sorted_servers[:5]:  # Show top 5
                pct = (tokens / total * 100) if total > 0 else 0
                # Truncate long server names
                display_name = server_name[:16] + ".." if len(server_name) > 18 else server_name
                content.append(f"  {display_name:<18}", style=self.theme.primary_text)
                content.append(f"{tokens:>6,}", style=f"bold {self.theme.primary_text}")
                content.append(f"  ({pct:.0f}%)\n", style=self.theme.dim_text)
            if len(sorted_servers) > 5:
                content.append(
                    f"  +{len(sorted_servers) - 5} more servers\n",
                    style=self.theme.dim_text,
                )

        # Zombie context tax (unused tools overhead)
        if snapshot.zombie_context_tax > 0:
            warning_emoji = ascii_emoji("⚠")
            content.append(f"\n{warning_emoji} Zombie Tax: ", style=f"bold {self.theme.warning}")
            content.append(
                f"{snapshot.zombie_context_tax:,} tokens (unused tools)",
                style=self.theme.warning,
            )

        return Panel(
            content,
            title="Context Tax",
            border_style=self.theme.mcp_border,
            box=self.box_style,
        )

    def _build_smells(self, snapshot: DisplaySnapshot) -> Panel:
        """Build Smells panel showing detected efficiency issues (v0.7.0 - task-105.2)."""
        content = Text()

        if not snapshot.detected_smells:
            content.append("No smells detected", style=f"{self.theme.dim_text} italic")
        else:
            for pattern, severity, tool, description in snapshot.detected_smells:
                # Severity color and emoji
                if severity == "warning":
                    emoji = ascii_emoji("\u26a0")  # Warning triangle
                    style = self.theme.warning
                else:  # "info"
                    emoji = ascii_emoji("\u2139")  # Info circle
                    style = self.theme.info

                content.append(f"{emoji} ", style=f"bold {style}")
                content.append(f"{pattern}", style=f"bold {style}")
                if tool:
                    # Truncate long tool names
                    display_tool = tool[:14] + ".." if len(tool) > 16 else tool
                    content.append(f" ({display_tool})", style=self.theme.dim_text)
                content.append("\n")
                # Show truncated description
                desc = description[:40] + ".." if len(description) > 42 else description
                content.append(f"   {desc}\n", style=self.theme.dim_text)

        # Title with count badge
        smell_count = len(snapshot.detected_smells)
        title = f"Smells ({smell_count})" if smell_count > 0 else "Smells"

        # Use warning border if smells exist, dim otherwise
        border_style = self.theme.warning if smell_count > 0 else self.theme.dim_text

        return Panel(
            content,
            title=title,
            border_style=border_style,
            box=self.box_style,
        )

    def _build_activity(self) -> Panel:
        """Build recent activity panel."""
        if not self.recent_events:
            content = Text("Waiting for events...", style=f"{self.theme.dim_text} italic")
        else:
            content = Text()
            for timestamp, tool_name, tokens in self.recent_events:
                local_time = timestamp.astimezone()
                time_str = local_time.strftime("%H:%M:%S")
                short_name = tool_name if len(tool_name) <= 40 else tool_name[:37] + "..."
                content.append(f"[{time_str}] ", style=self.theme.dim_text)
                content.append(f"{short_name}", style=self.theme.tool_name)
                if tokens > 0:
                    content.append(f" ({tokens:,} tokens)", style=self.theme.dim_text)
                content.append("\n")

        return Panel(
            content,
            title="Recent Activity",
            border_style=self.theme.activity_border,
            box=self.box_style,
        )

    def _export_live_ai_prompt(self) -> None:
        """Export AI analysis prompt for current live session (v0.7.0 - task-105.8)."""
        if not self._current_snapshot:
            return

        snapshot = self._current_snapshot

        # Generate markdown prompt
        lines = [
            "# Live Session Analysis Request",
            "",
            "Please analyze this live Token Audit session data:",
            "",
            "## Session Overview",
            f"- **Platform**: {snapshot.platform}",
            f"- **Project**: {snapshot.project}",
            f"- **Duration**: {self._format_duration_human(snapshot.duration_seconds)}",
            f"- **Tracking Mode**: {snapshot.tracking_mode}",
        ]

        # Model info
        if snapshot.is_multi_model and snapshot.models_used:
            lines.append(f"- **Models**: {', '.join(snapshot.models_used)}")
        elif snapshot.model_name:
            lines.append(f"- **Model**: {snapshot.model_name}")

        # Rate metrics (v0.7.0 - task-105.12)
        tokens_rate = "—"
        calls_rate = "—"
        if snapshot.duration_seconds > 0:
            tokens_per_min = snapshot.total_tokens / (snapshot.duration_seconds / 60)
            calls_per_min = snapshot.total_tool_calls / (snapshot.duration_seconds / 60)
            tokens_rate = f"{self._format_tokens(int(tokens_per_min))}/min"
            calls_rate = f"{calls_per_min:.1f}/min"

        # Cache hit ratio (v0.7.0 - task-105.13)
        cache_hit_ratio = 0.0
        denominator = snapshot.cache_read_tokens + snapshot.input_tokens
        if denominator > 0:
            cache_hit_ratio = snapshot.cache_read_tokens / denominator

        lines.extend(
            [
                "",
                "## Token Usage",
                f"- **Input Tokens**: {snapshot.input_tokens:,}",
                f"- **Output Tokens**: {snapshot.output_tokens:,}",
                f"- **Total Tokens**: {snapshot.total_tokens:,}",
                f"- **Token Rate**: {tokens_rate}",
                f"- **Cache Read**: {snapshot.cache_read_tokens:,}",
                f"- **Cache Created**: {snapshot.cache_created_tokens:,}",
                f"- **Cache Hit Ratio**: {cache_hit_ratio:.1%} (token-based)",
                f"- **Cache Efficiency**: {snapshot.cache_efficiency:.1%} (cost-based)",
                "",
                "## Cost",
                f"- **Cost w/ Cache**: ${snapshot.cost_estimate:.4f}",
                f"- **Cost w/o Cache**: ${snapshot.cost_no_cache:.4f}",
                f"- **Cache Savings**: ${snapshot.cache_savings:.4f} ({snapshot.savings_percent:.1f}%)",
                "",
                "## MCP Tool Usage",
                f"- **Total Calls**: {snapshot.total_tool_calls}",
                f"- **Unique Tools**: {snapshot.unique_tools}",
                f"- **Call Rate**: {calls_rate}",
                f"- **MCP Token Share**: {snapshot.mcp_tokens_percent:.1f}%",
            ]
        )

        # Server breakdown
        if snapshot.server_hierarchy:
            lines.append("\n### By Server:")
            for server_data in snapshot.server_hierarchy[:5]:
                server_name, calls, tokens, avg, _ = server_data
                lines.append(f"- **{server_name}**: {calls} calls, {self._format_tokens(tokens)}")

        # Smells
        if snapshot.detected_smells:
            lines.append("\n## Detected Issues (Smells)")
            for pattern, severity, tool, desc in snapshot.detected_smells:
                tool_info = f" ({tool})" if tool else ""
                lines.append(f"- **[{severity.upper()}] {pattern}**{tool_info}: {desc}")

        # Context tax
        if snapshot.static_cost_total > 0:
            lines.extend(
                [
                    "",
                    "## Context Tax",
                    f"- **Total Schema Tokens**: {snapshot.static_cost_total:,}",
                    f"- **Source**: {snapshot.static_cost_source} ({snapshot.static_cost_confidence * 100:.0f}% confidence)",
                ]
            )
            if snapshot.zombie_context_tax > 0:
                lines.append(f"- **Zombie Tax (unused tools)**: {snapshot.zombie_context_tax:,}")

        # Data quality
        lines.extend(
            [
                "",
                "## Data Quality",
                f"- **Accuracy Level**: {snapshot.accuracy_level}",
                f"- **Token Source**: {snapshot.token_source}",
                f"- **Confidence**: {snapshot.data_quality_confidence * 100:.0f}%",
                "",
                "## Questions",
                "1. Is this session's token usage efficient so far?",
                "2. Are there any concerning patterns in the MCP tool usage?",
                "3. What optimizations could reduce costs?",
                "4. Are the detected smells actionable?",
            ]
        )

        output = "\n".join(lines)

        # Try to copy to clipboard (macOS) - v0.8.0: show notification
        try:
            import subprocess

            subprocess.run(["pbcopy"], input=output.encode(), check=True)
            self.show_notification("Ask AI prompt copied to clipboard", "success")
        except Exception:
            # Fallback: still show success since prompt was generated
            self.show_notification("Ask AI prompt exported (clipboard unavailable)", "warning")

    def _build_footer(self) -> Text:
        """Build footer with instructions."""
        # v0.7.0 - Added keybindings (task-105.8)
        return Text(
            "[A] Ask AI  [Q] Quit  Ctrl+C to stop and save",
            style=f"{self.theme.dim_text} italic",
            justify="center",
        )

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

    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _format_duration_human(self, seconds: float) -> str:
        """Format duration in human-friendly format.

        Examples: "5s", "2m 30s", "1h 15m", "2h 30m 15s"
        """
        if seconds < 60:
            return f"{int(seconds)}s"

        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)

        if hours > 0:
            if secs > 0:
                return f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{hours}h"
        else:
            if secs > 0:
                return f"{minutes}m {secs}s"
            else:
                return f"{minutes}m"

    def _print_final_summary(self, snapshot: DisplaySnapshot) -> None:
        """Print final summary after stopping with enhanced display."""
        version_str = f" v{snapshot.version}" if snapshot.version else ""

        # Emoji for summary display
        savings_emoji = ascii_emoji("💰")
        cost_emoji = ascii_emoji("💸")
        branch_emoji = ascii_emoji("🌿")

        # Build summary text
        summary_parts = [
            f"[bold {self.theme.success}]Session Complete![/]\n",
        ]

        # Model info (v1.6.0: multi-model support)
        if snapshot.is_multi_model and snapshot.model_usage:
            summary_parts.append(f"[bold]Models[/bold] ({len(snapshot.models_used)}):\n")
            # Sort by total_tokens descending
            sorted_models = sorted(
                snapshot.model_usage, key=lambda m: m[3], reverse=True  # m[3] = total_tokens
            )
            for model_data in sorted_models:
                # model_data: (model, input, output, total_tokens, cache_read, cost_usd, call_count)
                model_name = model_data[0]
                total_tokens = model_data[3]
                cost_usd = model_data[5]
                call_count = model_data[6]
                # Truncate long model names
                display_name = model_name[:25] + "..." if len(model_name) > 25 else model_name
                summary_parts.append(
                    f"  {display_name}: {total_tokens:,} tokens, "
                    f"${cost_usd:.4f}, {call_count} calls\n"
                )
        elif snapshot.model_name and snapshot.model_name != "Unknown Model":
            summary_parts.append(f"Model: {snapshot.model_name}\n")

        # Duration and rate stats
        duration_human = self._format_duration_human(snapshot.duration_seconds)
        summary_parts.append(f"Duration: {duration_human}")

        # Rate statistics
        if snapshot.duration_seconds > 0:
            msg_per_min = snapshot.message_count / (snapshot.duration_seconds / 60)
            tokens_per_min = snapshot.total_tokens / (snapshot.duration_seconds / 60)
            summary_parts.append(
                f"  ({snapshot.message_count} msgs @ {msg_per_min:.1f}/min, "
                f"{self._format_tokens(int(tokens_per_min))}/min)\n"
            )
        else:
            summary_parts.append(f"  ({snapshot.message_count} messages)\n")

        # Token breakdown with percentages
        summary_parts.append(f"\n[bold]Tokens[/bold]: {snapshot.total_tokens:,}\n")
        if snapshot.total_tokens > 0:
            input_pct = snapshot.input_tokens / snapshot.total_tokens * 100
            output_pct = snapshot.output_tokens / snapshot.total_tokens * 100
            cache_read_pct = snapshot.cache_read_tokens / snapshot.total_tokens * 100
            cache_created_pct = snapshot.cache_created_tokens / snapshot.total_tokens * 100

            summary_parts.append(
                f"  Input: {snapshot.input_tokens:,} ({input_pct:.1f}%) | "
                f"Output: {snapshot.output_tokens:,} ({output_pct:.1f}%)\n"
            )
            # Show reasoning tokens when > 0 (Gemini thoughts / Codex reasoning)
            if snapshot.reasoning_tokens > 0:
                reasoning_pct = snapshot.reasoning_tokens / snapshot.total_tokens * 100
                summary_parts.append(
                    f"  Reasoning: {snapshot.reasoning_tokens:,} ({reasoning_pct:.1f}%)\n"
                )
            if snapshot.cache_read_tokens > 0 or snapshot.cache_created_tokens > 0:
                summary_parts.append(
                    f"  Cache read: {snapshot.cache_read_tokens:,} ({cache_read_pct:.1f}%)"
                )
                if snapshot.cache_created_tokens > 0:
                    summary_parts.append(
                        f" | Cache created: {snapshot.cache_created_tokens:,} ({cache_created_pct:.1f}%)"
                    )
                summary_parts.append("\n")
        summary_parts.append(f"  Cache efficiency: {snapshot.cache_efficiency:.1%}\n")

        # Tool breakdown
        summary_parts.append("\n[bold]Tools[/bold]:\n")

        # MCP tools with server breakdown
        if snapshot.total_tool_calls > 0:
            num_servers = len(snapshot.server_hierarchy) if snapshot.server_hierarchy else 0
            summary_parts.append(
                f"  MCP: {snapshot.total_tool_calls} calls across {num_servers} servers\n"
            )
            # Show top servers
            if snapshot.server_hierarchy:
                top_servers = sorted(snapshot.server_hierarchy, key=lambda s: s[2], reverse=True)[
                    :3
                ]
                server_strs = [f"{s[0]}({s[1]})" for s in top_servers]
                summary_parts.append(f"    Top: {', '.join(server_strs)}\n")
        else:
            summary_parts.append("  MCP: 0 calls\n")

        # Token estimation indicator
        if snapshot.estimated_tool_calls > 0:
            method = snapshot.estimation_method or "estimated"
            encoding = snapshot.estimation_encoding or ""
            if encoding:
                summary_parts.append(
                    f"    [{self.theme.dim_text}]({snapshot.estimated_tool_calls} calls with {method} estimation, {encoding})[/]\n"
                )
            else:
                summary_parts.append(
                    f"    [{self.theme.dim_text}]({snapshot.estimated_tool_calls} calls with {method} estimation)[/]\n"
                )

        # Built-in tools
        if snapshot.builtin_tool_calls > 0:
            summary_parts.append(
                f"  Built-in: {snapshot.builtin_tool_calls} calls "
                f"({self._format_tokens(snapshot.builtin_tool_tokens)})\n"
            )

        # Enhanced cost display
        summary_parts.append(f"\nCost w/ Cache (USD): ${snapshot.cost_estimate:.4f}\n")

        if snapshot.cost_no_cache > 0:
            summary_parts.append(f"Cost w/o Cache (USD): ${snapshot.cost_no_cache:.4f}\n")
            if snapshot.cache_savings > 0:
                summary_parts.append(
                    f"[{self.theme.success}]{savings_emoji} Cache savings: ${snapshot.cache_savings:.4f} "
                    f"({snapshot.savings_percent:.1f}% saved)[/]\n"
                )
            elif snapshot.cache_savings < 0:
                hint = self._get_cache_inefficiency_hint(snapshot)
                hint_str = f" {hint}" if hint else ""
                summary_parts.append(
                    f"[{self.theme.warning}]{cost_emoji} Net cost from caching: ${abs(snapshot.cache_savings):.4f}{hint_str}[/]\n"
                )
            else:
                summary_parts.append(f"{savings_emoji} Cache savings: $0.0000 (break even)\n")

        # Git metadata
        if snapshot.git_branch:
            git_info = f"{branch_emoji} {snapshot.git_branch}"
            if snapshot.git_commit_short:
                git_info += f"@{snapshot.git_commit_short}"
            if snapshot.git_status == "dirty":
                git_info += " (uncommitted changes)"
            summary_parts.append(f"\n{git_info}\n")

        # Context tax section (v0.6.0 - task-114.3)
        if snapshot.static_cost_total > 0:
            summary_parts.append("\n[bold]Context Tax[/bold] (MCP schema overhead):\n")
            summary_parts.append(f"  Total: {snapshot.static_cost_total:,} tokens\n")
            summary_parts.append(
                f"  Source: {snapshot.static_cost_source} "
                f"({snapshot.static_cost_confidence * 100:.0f}% confidence)\n"
            )
            # Show per-server breakdown if available
            if snapshot.static_cost_by_server:
                top_static_servers = sorted(
                    snapshot.static_cost_by_server, key=lambda x: x[1], reverse=True
                )[:3]
                server_strs = [f"{s[0]}({s[1]:,})" for s in top_static_servers]
                summary_parts.append(f"  Top: {', '.join(server_strs)}\n")
            # Show zombie tax if present
            if snapshot.zombie_context_tax > 0:
                warning_emoji = ascii_emoji("⚠")
                summary_parts.append(
                    f"  {warning_emoji} Zombie tax: {snapshot.zombie_context_tax:,} tokens (unused tools)\n"
                )

        summary_parts.append(f"\nSchema version: {SCHEMA_VERSION}")

        # Data quality disclaimer (v1.5.0 - task-103.5)
        if snapshot.accuracy_level == "estimated":
            confidence_pct = int(snapshot.data_quality_confidence * 100)
            summary_parts.append(
                f"\n[{self.theme.dim_text}]Data quality: MCP tool tokens estimated via "
                f"{snapshot.token_source} (~{confidence_pct}% accuracy)[/]"
            )

        # Session save location
        if snapshot.session_dir:
            summary_parts.append(
                f"\n\n[{self.theme.dim_text}]Session saved to: {snapshot.session_dir}[/]"
            )

        self.console.print(
            Panel(
                "".join(summary_parts),
                title=f"Token Audit{version_str} - Session Summary",
                border_style=self.theme.summary_border,
                box=self.box_style,
            )
        )
