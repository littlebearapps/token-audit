#!/usr/bin/env python3
"""
MCP Analyze CLI - Command-line interface for MCP Audit

Provides commands for collecting MCP session data and generating reports.
"""

import argparse
import atexit
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Literal, Optional

if TYPE_CHECKING:
    from .base_tracker import BaseTracker, Session
    from .display import DisplayAdapter, DisplaySnapshot

from . import __version__

# ============================================================================
# Global State for Signal Handlers
# ============================================================================

# These globals allow signal handlers to access tracker state for cleanup
_active_tracker: Optional["BaseTracker"] = None
_active_display: Optional["DisplayAdapter"] = None
_tracking_start_time: Optional[datetime] = None
_shutdown_in_progress: bool = False
_session_saved: bool = False


def _cleanup_session() -> None:
    """
    Clean up session data on exit.

    This function is called by signal handlers and atexit to ensure
    session data is saved regardless of how the process exits.
    """
    global _shutdown_in_progress, _session_saved

    # Prevent re-entry (signal handler + atexit can both trigger)
    if _shutdown_in_progress or _session_saved:
        return

    _shutdown_in_progress = True
    session = None
    session_dir = ""

    if _active_tracker is not None:
        try:
            # Check if any data was tracked before saving
            has_data = (
                _active_tracker.session.token_usage.total_tokens > 0
                or _active_tracker.session.mcp_tool_calls.total_calls > 0
            )

            if has_data:
                # Finalize and save session
                session = _active_tracker.stop()
                session_dir = (
                    str(_active_tracker.session_dir) if _active_tracker.session_dir else ""
                )
                _session_saved = True
            else:
                # No data tracked - don't save empty session
                session = _active_tracker.session  # Get session for display but don't save
                print("\n[mcp-audit] No data tracked - session not saved.")

        except Exception as e:
            print(f"\n[mcp-audit] Warning: Error during cleanup: {e}", file=sys.stderr)

    if _active_display is not None:
        try:
            # Stop display with actual session data if available
            if session:
                # Use actual session data for accurate summary
                snapshot = _build_snapshot_from_session(
                    session, _tracking_start_time or datetime.now(), session_dir
                )
            else:
                # Fallback to empty snapshot if no session
                from .display import DisplaySnapshot

                snapshot = DisplaySnapshot.create(
                    project="(interrupted)",
                    platform="unknown",
                    start_time=datetime.now(),
                    duration_seconds=0.0,
                )
            _active_display.stop(snapshot)
        except Exception:
            pass  # Display cleanup is best-effort


def _signal_handler(signum: int, _frame: object) -> None:
    """
    Handle termination signals (SIGINT, SIGTERM).

    This ensures session data is saved when:
    - Running in background and killed via `kill` command
    - Running via `timeout` command
    - User presses Ctrl+C
    """
    signal_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"\n[mcp-audit] Received {signal_name}, saving session...")

    _cleanup_session()

    # Exit with appropriate code
    # 128 + signal number is Unix convention for signal-terminated processes
    sys.exit(128 + signum)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="mcp-audit",
        description="MCP Audit - Multi-platform MCP usage tracking and cost analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect session data under Claude Code
  mcp-audit collect --platform claude-code --output ./session-data

  # Collect session data under Codex CLI
  mcp-audit collect --platform codex-cli --output ./session-data

  # Collect session data under Gemini CLI (requires telemetry enabled)
  mcp-audit collect --platform gemini-cli --output ./session-data

  # Generate report from session data
  mcp-audit report ./session-data --format markdown --output report.md

  # Generate JSON report
  mcp-audit report ./session-data --format json --output report.json

For more information, visit: https://github.com/littlebearapps/mcp-audit
        """,
    )

    parser.add_argument("--version", action="version", version=f"mcp-audit {__version__}")

    # Subcommands
    subparsers = parser.add_subparsers(
        title="commands",
        description="Available commands",
        dest="command",
        help="Command to execute",
    )

    # ========================================================================
    # collect command
    # ========================================================================
    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect MCP session data from CLI tools",
        description="""
Collect MCP session data by monitoring CLI tool output.

This command runs under a Claude Code, Codex CLI, or Gemini CLI session
and captures MCP tool usage, token counts, and cost data in real-time.

The collected data is saved to the specified output directory and can be
analyzed later with the 'report' command.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    collect_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli", "auto"],
        default="auto",
        help="Platform to monitor (default: auto-detect)",
    )

    collect_parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".mcp-audit" / "sessions",
        help="Output directory for session data (default: ~/.mcp-audit/sessions)",
    )

    collect_parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Project name for session (default: auto-detect from directory)",
    )

    collect_parser.add_argument(
        "--no-logs", action="store_true", help="Skip writing logs to disk (real-time display only)"
    )

    collect_parser.add_argument(
        "--quiet", action="store_true", help="Suppress all display output (logs only)"
    )

    collect_parser.add_argument(
        "--tui",
        action="store_true",
        help="Use rich TUI display (default when TTY available)",
    )

    collect_parser.add_argument(
        "--plain",
        action="store_true",
        help="Use plain text output (for CI/logs)",
    )

    collect_parser.add_argument(
        "--refresh-rate",
        type=float,
        default=0.5,
        help="TUI refresh rate in seconds (default: 0.5)",
    )

    collect_parser.add_argument(
        "--pin-server",
        action="append",
        dest="pinned_servers",
        metavar="SERVER",
        help="Pin server(s) at top of MCP section (can be used multiple times)",
    )

    # ========================================================================
    # report command
    # ========================================================================
    report_parser = subparsers.add_parser(
        "report",
        help="Generate reports from collected session data",
        description="""
Generate reports from collected MCP session data.

This command analyzes session data and produces reports in various formats
(JSON, Markdown, CSV) showing token usage, costs, and MCP tool efficiency.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    report_parser.add_argument(
        "session_dir", type=Path, help="Session directory or parent directory containing sessions"
    )

    report_parser.add_argument(
        "--format",
        choices=["json", "markdown", "csv"],
        default="markdown",
        help="Report format (default: markdown)",
    )

    report_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout or auto-generated filename)",
    )

    report_parser.add_argument(
        "--aggregate", action="store_true", help="Aggregate data across multiple sessions"
    )

    report_parser.add_argument(
        "--platform",
        choices=["claude_code", "codex_cli", "gemini_cli", "ollama_cli"],
        default=None,
        help="Filter sessions by platform (default: all platforms)",
    )

    report_parser.add_argument(
        "--top-n", type=int, default=10, help="Number of top tools to show (default: 10)"
    )

    # Parse arguments
    args = parser.parse_args()

    # Execute command
    if args.command == "collect":
        return cmd_collect(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


# ============================================================================
# Command Implementations
# ============================================================================


def get_display_mode(args: argparse.Namespace) -> Literal["auto", "tui", "plain", "quiet"]:
    """Determine display mode from CLI args."""
    if args.quiet:
        return "quiet"
    if args.plain:
        return "plain"
    if args.tui:
        return "tui"
    return "auto"  # Will use TUI if TTY, else plain


def cmd_collect(args: argparse.Namespace) -> int:
    """Execute collect command."""
    global _active_tracker, _active_display, _shutdown_in_progress, _session_saved

    from .display import DisplaySnapshot, create_display

    # Reset global state for this session
    _active_tracker = None
    _active_display = None
    _shutdown_in_progress = False
    _session_saved = False

    # Register signal handlers for graceful shutdown
    # This ensures session is saved when:
    # - Ctrl+C (SIGINT) in foreground or background
    # - kill command (SIGTERM) in background
    # - timeout command (sends SIGTERM)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Register atexit handler as backup (for edge cases)
    atexit.register(_cleanup_session)

    # Determine display mode
    display_mode = get_display_mode(args)

    # Create display adapter
    try:
        display = create_display(
            mode=display_mode,
            refresh_rate=args.refresh_rate,
            pinned_servers=args.pinned_servers,
        )
        _active_display = display
    except ImportError as e:
        print(f"Error: {e}")
        return 1

    # Detect platform
    platform = args.platform
    if platform == "auto":
        platform = detect_platform()

    # Determine project name
    project = args.project or detect_project_name()

    # Create initial snapshot for display start
    global _tracking_start_time
    start_time = datetime.now()
    _tracking_start_time = start_time
    initial_snapshot = DisplaySnapshot.create(
        project=project,
        platform=platform,
        start_time=start_time,
        duration_seconds=0.0,
    )

    # Start display
    display.start(initial_snapshot)

    # Import appropriate tracker and create instance
    try:
        tracker: BaseTracker
        if platform == "claude-code":
            from .claude_code_adapter import ClaudeCodeAdapter

            tracker = ClaudeCodeAdapter(project=project)
        elif platform == "codex-cli":
            from .codex_cli_adapter import CodexCLIAdapter

            tracker = CodexCLIAdapter(project=project)
        elif platform == "gemini-cli":
            from .gemini_cli_adapter import GeminiCLIAdapter

            tracker = GeminiCLIAdapter(project=project)
        else:
            display.stop(initial_snapshot)
            print(f"Error: Platform '{platform}' not yet implemented")
            print("Supported platforms: claude-code, codex-cli, gemini-cli")
            return 1

        # Set global tracker for signal handlers
        _active_tracker = tracker

        # Set output directory from CLI args
        tracker.output_dir = args.output

        # Start tracking
        tracker.start()

        # Monitor until interrupted (signal handler will save session)
        # NOTE: We intentionally don't use contextlib.suppress here because
        # we need to handle KeyboardInterrupt gracefully without traceback
        try:  # noqa: SIM105
            tracker.monitor(display=display)
        except KeyboardInterrupt:
            # Ctrl+C in foreground - signal handler already ran
            pass

        # If we get here normally (not via signal), save session
        if not _session_saved:
            # Check if any data was tracked before saving
            has_data = (
                tracker.session.token_usage.total_tokens > 0
                or tracker.session.mcp_tool_calls.total_calls > 0
            )

            session_dir = ""
            if has_data and not args.no_logs:
                session = tracker.stop()
                session_dir = str(tracker.session_dir) if tracker.session_dir else ""
            else:
                session = tracker.session  # Get session for display but don't save
                if not has_data:
                    print("\n[mcp-audit] No data tracked - session not saved.")

            _session_saved = True

            # Build final snapshot
            if session:
                final_snapshot = _build_snapshot_from_session(session, start_time, session_dir)
            else:
                final_snapshot = initial_snapshot

            # Stop display and show summary
            display.stop(final_snapshot)

        return 0

    except Exception as e:
        display.stop(initial_snapshot)
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


def _build_snapshot_from_session(
    session: "Session", start_time: datetime, session_dir: str = ""
) -> "DisplaySnapshot":
    """Build DisplaySnapshot from a Session object with all enhanced fields."""
    from .display import DisplaySnapshot
    from .pricing_config import PricingConfig

    # Human-readable model names
    MODEL_DISPLAY_NAMES = {
        # Claude 4.5 Series
        "claude-opus-4-5-20251101": "Claude Opus 4.5",
        "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
        "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
        "claude-haiku-4-5": "Claude Haiku 4.5",
        # Claude 4 Series
        "claude-opus-4-1": "Claude Opus 4.1",
        "claude-sonnet-4-20250514": "Claude Sonnet 4",
        "claude-opus-4-20250514": "Claude Opus 4",
        # Claude 3.5 Series
        "claude-3-5-haiku-20241022": "Claude Haiku 3.5",
        "claude-3-5-sonnet-20241022": "Claude Sonnet 3.5",
    }

    # Calculate duration
    duration_seconds = (datetime.now() - start_time).total_seconds()

    # Calculate cache tokens (for display purposes)
    cache_tokens = session.token_usage.cache_read_tokens + session.token_usage.cache_created_tokens

    # Calculate cache efficiency: percentage of INPUT tokens served from cache
    # (cache_read saves money, cache_created costs more - only count cache_read)
    total_input = (
        session.token_usage.input_tokens
        + session.token_usage.cache_created_tokens
        + session.token_usage.cache_read_tokens
    )
    cache_efficiency = (
        session.token_usage.cache_read_tokens / total_input if total_input > 0 else 0.0
    )

    # Build top tools list
    top_tools = []
    for server_session in session.server_sessions.values():
        for tool_name, tool_stats in server_session.tools.items():
            avg_tokens = tool_stats.total_tokens // tool_stats.calls if tool_stats.calls > 0 else 0
            top_tools.append((tool_name, tool_stats.calls, tool_stats.total_tokens, avg_tokens))

    # Sort by total tokens descending
    top_tools.sort(key=lambda x: x[2], reverse=True)

    # ================================================================
    # Model tracking (fix for task-42.1)
    # ================================================================
    model_id = session.model or ""
    model_name = MODEL_DISPLAY_NAMES.get(model_id, model_id) if model_id else "Unknown Model"

    # ================================================================
    # Enhanced cost tracking (fix for task-42.1)
    # ================================================================
    pricing_config = PricingConfig()
    input_tokens = session.token_usage.input_tokens
    output_tokens = session.token_usage.output_tokens
    cache_created = session.token_usage.cache_created_tokens
    cache_read = session.token_usage.cache_read_tokens

    # Calculate cost without cache (all cache tokens charged at input rate)
    model_for_pricing = model_id or "claude-sonnet-4-5-20250929"  # Default fallback
    pricing = pricing_config.get_model_pricing(model_for_pricing)
    if pricing:
        input_rate = pricing.get("input", 3.0)  # Default Sonnet 4.5 rate
        output_rate = pricing.get("output", 15.0)
        cost_no_cache = (
            ((input_tokens + cache_created + cache_read) * input_rate)
            + (output_tokens * output_rate)
        ) / 1_000_000
    else:
        # Fallback to Sonnet 4.5 default pricing
        cost_no_cache = (
            ((input_tokens + cache_created + cache_read) * 3.0) + (output_tokens * 15.0)
        ) / 1_000_000

    # Calculate savings
    cost_estimate = session.cost_estimate
    cache_savings = cost_no_cache - cost_estimate
    savings_percent = (cache_savings / cost_no_cache * 100) if cost_no_cache > 0 else 0.0

    # ================================================================
    # Server hierarchy (fix for task-42.1)
    # ================================================================
    from typing import List, Tuple

    server_hierarchy: List[Tuple[str, int, int, int, List[Tuple[str, int, int, float]]]] = []

    # Sort servers by total tokens (descending)
    sorted_servers = sorted(
        session.server_sessions.items(),
        key=lambda x: x[1].total_tokens,
        reverse=True,
    )

    for server_name, server_session in sorted_servers[:5]:  # Top 5 servers
        server_calls = server_session.total_calls
        server_tokens = server_session.total_tokens
        server_avg = server_tokens // server_calls if server_calls > 0 else 0

        # Build tool list for this server
        tools_list: List[Tuple[str, int, int, float]] = []

        # Sort tools by tokens (descending)
        sorted_tools = sorted(
            server_session.tools.items(),
            key=lambda x: x[1].total_tokens,
            reverse=True,
        )

        for tool_name, tool_stats in sorted_tools:
            # Extract short tool name (last part after __)
            short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
            tool_calls = tool_stats.calls
            tool_tokens = tool_stats.total_tokens
            pct_of_server = (tool_tokens / server_tokens * 100) if server_tokens > 0 else 0.0

            tools_list.append((short_name, tool_calls, tool_tokens, pct_of_server))

        server_hierarchy.append((server_name, server_calls, server_tokens, server_avg, tools_list))

    # Calculate MCP tokens as percentage of session
    total_mcp_tokens = sum(ss.total_tokens for ss in session.server_sessions.values())
    total_tokens = session.token_usage.total_tokens
    mcp_tokens_percent = (total_mcp_tokens / total_tokens * 100) if total_tokens > 0 else 0.0

    return DisplaySnapshot.create(
        project=session.project,
        platform=session.platform,
        start_time=start_time,
        duration_seconds=duration_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_tokens=cache_tokens,
        total_tokens=session.token_usage.total_tokens,
        cache_efficiency=cache_efficiency,
        cost_estimate=cost_estimate,
        total_tool_calls=session.mcp_tool_calls.total_calls,
        unique_tools=session.mcp_tool_calls.unique_tools,
        top_tools=top_tools,
        session_dir=session_dir,
        # Enhanced fields (fix for task-42.1)
        model_id=model_id,
        model_name=model_name,
        cost_no_cache=cost_no_cache,
        cache_savings=cache_savings,
        savings_percent=savings_percent,
        server_hierarchy=server_hierarchy,
        mcp_tokens_percent=mcp_tokens_percent,
        # Fix for task-49.1 and task-49.2: pass message count and cache tokens
        message_count=session.message_count,
        cache_created_tokens=cache_created,
        cache_read_tokens=cache_read,
    )


def cmd_report(args: argparse.Namespace) -> int:
    """Execute report command."""
    print("=" * 70)
    print("MCP Analyze - Generate Report")
    print("=" * 70)
    print()

    session_dir = args.session_dir

    # Check if session directory exists
    if not session_dir.exists():
        print(f"Error: Session directory not found: {session_dir}")
        return 1

    # Import session manager
    from .session_manager import SessionManager

    manager = SessionManager()

    # Determine if single session or multiple sessions
    if (session_dir / "summary.json").exists():
        # Single session
        print(f"Loading session from: {session_dir}")
        session = manager.load_session(session_dir)

        if not session:
            print("Error: Failed to load session")
            return 1

        sessions = [session]
    else:
        # Multiple sessions (parent directory)
        print(f"Loading sessions from: {session_dir}")
        session_dirs = [d for d in session_dir.iterdir() if d.is_dir()]
        sessions = []

        for s_dir in session_dirs:
            session = manager.load_session(s_dir)
            if session:
                sessions.append(session)

        if not sessions:
            print("Error: No valid sessions found")
            return 1

        print(f"Loaded {len(sessions)} session(s)")

    # Apply platform filter if specified
    platform_filter = getattr(args, "platform", None)
    if platform_filter:
        sessions = [s for s in sessions if s.platform == platform_filter]
        if not sessions:
            print(f"Error: No sessions found for platform: {platform_filter}")
            return 1
        print(f"Filtered to {len(sessions)} session(s) for platform: {platform_filter}")

    print()

    # Generate report
    if args.format == "json":
        return generate_json_report(sessions, args)
    elif args.format == "markdown":
        return generate_markdown_report(sessions, args)
    elif args.format == "csv":
        return generate_csv_report(sessions, args)
    else:
        print(f"Error: Unknown format: {args.format}")
        return 1


# ============================================================================
# Report Generators
# ============================================================================


def generate_json_report(sessions: List["Session"], args: argparse.Namespace) -> int:
    """Generate JSON report."""
    import json
    from collections import defaultdict
    from datetime import datetime
    from typing import Any, Dict
    from typing import List as TList

    from . import __version__

    # Build report data
    sessions_list: TList[Dict[str, Any]] = []
    for session in sessions:
        sessions_list.append(session.to_dict())

    # Calculate platform breakdown
    platform_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "total_tokens": 0, "cost": 0.0, "mcp_calls": 0}
    )
    for session in sessions:
        platform = session.platform or "unknown"
        platform_stats[platform]["sessions"] += 1
        platform_stats[platform]["total_tokens"] += session.token_usage.total_tokens
        platform_stats[platform]["cost"] += session.cost_estimate
        platform_stats[platform]["mcp_calls"] += session.mcp_tool_calls.total_calls

    # Calculate efficiency metrics
    for stats in platform_stats.values():
        stats["cost_per_1m_tokens"] = (
            (stats["cost"] / stats["total_tokens"]) * 1_000_000 if stats["total_tokens"] > 0 else 0
        )
        stats["cost_per_session"] = (
            stats["cost"] / stats["sessions"] if stats["sessions"] > 0 else 0
        )

    # Find most efficient platform
    most_efficient_platform = None
    if platform_stats:
        most_efficient = min(
            platform_stats.items(),
            key=lambda x: (
                x[1]["cost_per_1m_tokens"] if x[1]["cost_per_1m_tokens"] > 0 else float("inf")
            ),
        )
        most_efficient_platform = most_efficient[0]

    report: Dict[str, Any] = {
        "generated": datetime.now().isoformat(),
        "version": __version__,
        "summary": {
            "total_sessions": len(sessions),
            "total_tokens": sum(s.token_usage.total_tokens for s in sessions),
            "total_cost": sum(s.cost_estimate for s in sessions),
            "total_mcp_calls": sum(s.mcp_tool_calls.total_calls for s in sessions),
            "most_efficient_platform": most_efficient_platform,
        },
        "platforms": dict(platform_stats),
        "sessions": sessions_list,
    }

    # Output to file or stdout
    output_path = args.output
    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"JSON report written to: {output_path}")
    else:
        print(json.dumps(report, indent=2, default=str))

    return 0


def generate_markdown_report(sessions: List["Session"], args: argparse.Namespace) -> int:
    """Generate Markdown report."""
    from collections import defaultdict
    from datetime import datetime
    from typing import Dict

    # Build markdown content
    lines = []
    lines.append("# MCP Audit Report")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Sessions**: {len(sessions)}")

    # Calculate platform breakdown
    platform_stats: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"sessions": 0, "tokens": 0, "cost": 0.0, "mcp_calls": 0}
    )
    for session in sessions:
        platform = session.platform or "unknown"
        platform_stats[platform]["sessions"] += 1
        platform_stats[platform]["tokens"] += session.token_usage.total_tokens
        platform_stats[platform]["cost"] += session.cost_estimate
        platform_stats[platform]["mcp_calls"] += session.mcp_tool_calls.total_calls

    # Calculate efficiency metrics for each platform
    for stats in platform_stats.values():
        # Cost per million tokens
        stats["cost_per_1m"] = (
            (stats["cost"] / stats["tokens"]) * 1_000_000 if stats["tokens"] > 0 else 0
        )
        # Cost per session
        stats["cost_per_session"] = (
            stats["cost"] / stats["sessions"] if stats["sessions"] > 0 else 0
        )

    # Show platform breakdown if multiple platforms
    if len(platform_stats) > 1:
        lines.append("")
        lines.append("## Platform Summary")
        lines.append("")
        lines.append("| Platform | Sessions | Total Tokens | Cost | MCP Calls |")
        lines.append("|----------|----------|--------------|------|-----------|")
        for platform, stats in sorted(platform_stats.items()):
            lines.append(
                f"| {platform} | {stats['sessions']} | "
                f"{stats['tokens']:,.0f} | ${stats['cost']:.4f} | "
                f"{stats['mcp_calls']} |"
            )
        # Add totals row
        total_tokens = sum(s["tokens"] for s in platform_stats.values())
        total_cost = sum(s["cost"] for s in platform_stats.values())
        total_mcp = sum(s["mcp_calls"] for s in platform_stats.values())
        lines.append(
            f"| **Total** | **{len(sessions)}** | "
            f"**{total_tokens:,.0f}** | **${total_cost:.4f}** | "
            f"**{total_mcp}** |"
        )
        lines.append("")

        # Add cost comparison section
        lines.append("### Cost Comparison")
        lines.append("")
        lines.append("| Platform | Cost/1M Tokens | Cost/Session | Efficiency |")
        lines.append("|----------|----------------|--------------|------------|")

        # Find most efficient platform (lowest cost per 1M tokens)
        most_efficient = min(
            platform_stats.items(),
            key=lambda x: x[1]["cost_per_1m"] if x[1]["cost_per_1m"] > 0 else float("inf"),
        )
        most_efficient_platform = most_efficient[0]

        for platform, stats in sorted(platform_stats.items()):
            efficiency_marker = "✓ Best" if platform == most_efficient_platform else ""
            lines.append(
                f"| {platform} | ${stats['cost_per_1m']:.4f} | "
                f"${stats['cost_per_session']:.4f} | {efficiency_marker} |"
            )
    lines.append("")

    # Per-session summaries
    for i, session in enumerate(sessions, 1):
        lines.append(f"## Session {i}: {session.project}")
        lines.append("")
        lines.append(f"**Timestamp**: {session.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Platform**: {session.platform}")
        if session.model:
            lines.append(f"**Model**: {session.model}")
        lines.append("")

        lines.append("### Token Usage")
        lines.append("")
        lines.append(f"- **Input tokens**: {session.token_usage.input_tokens:,}")
        lines.append(f"- **Output tokens**: {session.token_usage.output_tokens:,}")
        lines.append(f"- **Cache created**: {session.token_usage.cache_created_tokens:,}")
        lines.append(f"- **Cache read**: {session.token_usage.cache_read_tokens:,}")
        lines.append(f"- **Total tokens**: {session.token_usage.total_tokens:,}")
        lines.append("")

        lines.append(f"**Cost Estimate**: ${session.cost_estimate:.4f}")
        lines.append("")

        lines.append("### MCP Tool Calls")
        lines.append("")
        lines.append(f"- **Total calls**: {session.mcp_tool_calls.total_calls}")
        lines.append(f"- **Unique tools**: {session.mcp_tool_calls.unique_tools}")
        lines.append("")

        # Top tools
        if session.server_sessions:
            lines.append("#### Top MCP Tools")
            lines.append("")

            # Collect all tools
            all_tools = []
            for _server_name, server_session in session.server_sessions.items():
                for tool_name, tool_stats in server_session.tools.items():
                    all_tools.append((tool_name, tool_stats.calls, tool_stats.total_tokens))

            # Sort by total tokens
            all_tools.sort(key=lambda x: x[2], reverse=True)

            # Show top N
            for tool_name, calls, total_tokens in all_tools[: args.top_n]:
                lines.append(f"- **{tool_name}**: {calls} calls, {total_tokens:,} tokens")

            lines.append("")

    # Output to file or stdout
    content = "\n".join(lines)
    output_path = args.output
    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
        print(f"Markdown report written to: {output_path}")
    else:
        print(content)

    return 0


def generate_csv_report(sessions: List["Session"], args: argparse.Namespace) -> int:
    """Generate CSV report."""
    import csv
    from typing import Any, Dict

    # Collect tool statistics across all sessions, grouped by platform
    aggregated_stats: Dict[str, Dict[str, Any]] = {}

    for session in sessions:
        platform = session.platform or "unknown"
        for _server_name, server_session in session.server_sessions.items():
            for tool_name, tool_stats in server_session.tools.items():
                key = f"{platform}:{tool_name}"
                if key not in aggregated_stats:
                    aggregated_stats[key] = {
                        "platform": platform,
                        "tool_name": tool_name,
                        "calls": 0,
                        "total_tokens": 0,
                    }

                aggregated_stats[key]["calls"] += tool_stats.calls
                aggregated_stats[key]["total_tokens"] += tool_stats.total_tokens

    # Build CSV rows
    rows: List[Dict[str, Any]] = []
    for _key, stats in sorted(
        aggregated_stats.items(), key=lambda x: x[1]["total_tokens"], reverse=True
    ):
        rows.append(
            {
                "platform": stats["platform"],
                "tool_name": stats["tool_name"],
                "total_calls": stats["calls"],
                "total_tokens": stats["total_tokens"],
                "avg_tokens": stats["total_tokens"] // stats["calls"] if stats["calls"] > 0 else 0,
            }
        )

    # Output to file or stdout
    output_path = args.output or Path("mcp-audit-report.csv")

    with open(output_path, "w", newline="") as f:
        if rows:
            writer = csv.DictWriter(
                f,
                fieldnames=["platform", "tool_name", "total_calls", "total_tokens", "avg_tokens"],
            )
            writer.writeheader()
            writer.writerows(rows)

    print(f"CSV report written to: {output_path}")
    return 0


# ============================================================================
# Utility Functions
# ============================================================================


def detect_platform() -> str:
    """Auto-detect platform from environment."""
    # Check for Claude Code debug log
    claude_log = Path.home() / ".claude" / "cache"
    if claude_log.exists():
        return "claude-code"

    # Check for Codex CLI indicators
    # (Would need to check for codex-specific environment variables)

    # Default to Claude Code
    return "claude-code"


def detect_project_name() -> str:
    """
    Detect project name from current directory.

    Handles git worktree setups where directory structure is:
        project-name/
        ├── .bare/          # Bare git repository
        └── main/           # Working directory (worktree)

    In this case, returns "project-name" instead of just "main".
    """
    cwd = Path.cwd()
    current_name = cwd.name
    parent = cwd.parent

    # Common branch/worktree directory names that indicate we're in a worktree
    worktree_indicators = {"main", "master", "develop", "dev", "staging", "production"}

    # Check if we're likely in a git worktree setup
    if current_name.lower() in worktree_indicators:
        # Check for .bare directory in parent (bare repo pattern)
        bare_dir = parent / ".bare"
        if bare_dir.exists() and bare_dir.is_dir():
            return parent.name

        # Check if .git is a file (not directory) - indicates worktree
        git_path = cwd / ".git"
        if git_path.exists() and git_path.is_file():
            return parent.name

    return current_name


if __name__ == "__main__":
    sys.exit(main())
