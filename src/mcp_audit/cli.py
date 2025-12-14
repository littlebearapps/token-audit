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
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

if TYPE_CHECKING:
    from .base_tracker import BaseTracker, Session
    from .display import DisplayAdapter, DisplaySnapshot
    from .smell_aggregator import SmellAggregationResult

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
                # Use full session file path if available, fallback to session_dir
                session_dir = (
                    str(_active_tracker.session_path) if _active_tracker.session_path else ""
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
        "--theme",
        choices=["auto", "dark", "light", "mocha", "latte", "hc-dark", "hc-light"],
        default="auto",
        help="TUI color theme (default: auto-detect). Options: dark/light (Catppuccin), hc-dark/hc-light (high contrast)",
    )

    collect_parser.add_argument(
        "--pin-server",
        action="append",
        dest="pinned_servers",
        metavar="SERVER",
        help="Pin server(s) at top of MCP section (can be used multiple times)",
    )

    collect_parser.add_argument(
        "--from-start",
        action="store_true",
        help="Include existing session data (Codex/Gemini CLI only). Default: track new events only.",
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

    # ========================================================================
    # smells command
    # ========================================================================
    smells_parser = subparsers.add_parser(
        "smells",
        help="Analyze smell patterns across sessions",
        description="""
Aggregate smell patterns across multiple sessions to identify persistent issues.

Shows smell frequency, trends (improving/worsening/stable), and affected tools.
Helps identify recurring efficiency problems in your workflow.

Examples:
  # Analyze last 30 days for all platforms
  mcp-audit smells

  # Analyze last 7 days for Claude Code
  mcp-audit smells --days 7 --platform claude-code

  # Export as JSON
  mcp-audit smells --format json --output smells.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    smells_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )

    smells_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Filter by platform (default: all)",
    )

    smells_parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Filter by project name (default: all)",
    )

    smells_parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text with progress bars)",
    )

    smells_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )

    smells_parser.add_argument(
        "--min-frequency",
        type=float,
        default=0.0,
        help="Minimum frequency %% to display (default: 0)",
    )

    # ========================================================================
    # init command
    # ========================================================================
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize mcp-audit with optional enhancements",
        description="""
Interactive setup wizard for mcp-audit.

This command checks your current configuration and offers optional
enhancements with y/n prompts. Nothing is installed without your approval.

Current checks:
  - Gemma tokenizer (100% accurate Gemini CLI token estimation)
  - Future: pricing config, output directories, etc.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    init_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Accept all optional enhancements without prompting",
    )

    init_parser.add_argument(
        "--no",
        "-n",
        action="store_true",
        help="Skip all optional enhancements without prompting",
    )

    init_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only show status, don't offer to install anything",
    )

    # ========================================================================
    # tokenizer command
    # ========================================================================
    tokenizer_parser = subparsers.add_parser(
        "tokenizer",
        help="Manage tokenizer models for token estimation",
        description="""
Manage tokenizer models used for accurate token estimation.

The Gemma tokenizer provides 100% accurate token counts for Gemini CLI sessions.
It can be downloaded from GitHub Releases (no account required).

Without the Gemma tokenizer, mcp-audit falls back to tiktoken (cl100k_base)
which provides ~95% accuracy for Gemini sessions.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    tokenizer_subparsers = tokenizer_parser.add_subparsers(
        title="tokenizer commands",
        dest="tokenizer_command",
        help="Tokenizer management commands",
    )

    # tokenizer status
    tokenizer_status_parser = tokenizer_subparsers.add_parser(
        "status",
        help="Check tokenizer installation status",
    )
    tokenizer_status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # tokenizer download
    tokenizer_download_parser = tokenizer_subparsers.add_parser(
        "download",
        help="Download the Gemma tokenizer for accurate Gemini CLI token estimation",
        description="""
Download the Gemma tokenizer model for 100% accurate Gemini CLI token estimation.

By default, downloads from GitHub Releases (no account required).
Alternatively, use --source huggingface if GitHub is unavailable.

Examples:
  # Download latest from GitHub (recommended)
  mcp-audit tokenizer download

  # Download specific release
  mcp-audit tokenizer download --release v0.4.0

  # Download from HuggingFace (requires account)
  mcp-audit tokenizer download --source huggingface --token hf_xxx

The tokenizer will be saved to ~/.cache/mcp-audit/tokenizer.model
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    tokenizer_download_parser.add_argument(
        "--source",
        type=str,
        choices=["github", "huggingface"],
        default="github",
        help="Download source: github (default, no auth) or huggingface (requires account)",
    )

    tokenizer_download_parser.add_argument(
        "--release",
        type=str,
        default=None,
        help="Specific release version to download (e.g., v0.4.0). Default: latest",
    )

    tokenizer_download_parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="HuggingFace access token (only for --source huggingface)",
    )

    tokenizer_download_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if tokenizer already exists",
    )

    # ========================================================================
    # export command (v1.5.0 - task-103.2)
    # ========================================================================
    export_parser = subparsers.add_parser(
        "export",
        help="Export session data in various formats",
        description="""
Export session data in formats optimized for different use cases.

Currently supports:
  ai-prompt - Export session data formatted for AI analysis
              (paste into Claude/ChatGPT for efficiency recommendations)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    export_subparsers = export_parser.add_subparsers(
        title="export formats",
        dest="export_format",
        help="Export format to use",
    )

    # export ai-prompt
    export_ai_parser = export_subparsers.add_parser(
        "ai-prompt",
        help="Export session data formatted for AI analysis",
        description="""
Export session data in a format optimized for AI analysis.

The output includes:
- Session summary (duration, platform, model)
- Token breakdown by category
- MCP tool usage ranked by tokens
- Detected smells with evidence
- Data quality indicators
- Suggested analysis questions

Use case: Copy and paste into Claude/ChatGPT for efficiency analysis.

Examples:
  # Export latest session
  mcp-audit export ai-prompt

  # Export specific session
  mcp-audit export ai-prompt path/to/session.json

  # Export as JSON (for programmatic use)
  mcp-audit export ai-prompt --format json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    export_ai_parser.add_argument(
        "session_path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to session JSON file (default: latest session)",
    )

    export_ai_parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    export_ai_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file (default: stdout)",
    )

    # v0.8.0: Pinned MCP Focus options (task-106.5)
    export_ai_parser.add_argument(
        "--pinned-focus",
        action="store_true",
        help="Add dedicated analysis section for pinned servers",
    )

    export_ai_parser.add_argument(
        "--full-mcp-breakdown",
        action="store_true",
        help="Include per-server and per-tool breakdown for ALL MCP servers",
    )

    export_ai_parser.add_argument(
        "--pinned-servers",
        action="append",
        metavar="SERVER",
        help="Servers to analyze as pinned (can use multiple times)",
    )

    # ========================================================================
    # ui command (v0.7.0 - task-105.1)
    # ========================================================================
    ui_parser = subparsers.add_parser(
        "ui",
        help="Interactive session browser",
        description="""
Launch the interactive session browser TUI.

Browse past sessions, filter by platform/date/cost, and view detailed
session breakdowns.

Keyboard shortcuts:
  q          Quit
  j/k        Navigate down/up
  ENTER      View session details
  /          Search sessions
  f          Cycle platform filter
  s          Cycle sort order
  r          Refresh session list
  ESC        Back / Cancel
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ui_parser.add_argument(
        "--theme",
        choices=["auto", "dark", "light", "mocha", "latte", "hc-dark", "hc-light"],
        default="auto",
        help="Color theme (default: auto-detect)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Execute command
    if args.command == "collect":
        return cmd_collect(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "init":
        return cmd_init(args)
    elif args.command == "tokenizer":
        return cmd_tokenizer(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "ui":
        return cmd_ui(args)
    elif args.command == "smells":
        return cmd_smells(args)
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


def _check_first_run() -> bool:
    """Check if this is the first run and offer setup if so.

    Returns True if user wants to continue, False if they ran init.
    """
    marker_file = Path.home() / ".mcp-audit" / ".initialized"

    # If marker exists, not first run
    if marker_file.exists():
        return True

    # First run - offer setup
    print()
    print("=" * 70)
    print("  Welcome to MCP Audit!")
    print("=" * 70)
    print()
    print("  Looks like this is your first time running mcp-audit.")
    print()
    print("  mcp-audit tracks MCP tool usage and token costs across all platforms:")
    print()
    print("    • Claude Code  — 100% accurate (native token counts from Anthropic)")
    print("    • Codex CLI    — 99%+ accurate (tiktoken tokenizer, bundled)")
    print("    • Gemini CLI   — ~95% accurate (tiktoken fallback)")
    print()
    print("  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │  💡 Gemini CLI Users                                            │")
    print("  │                                                                 │")
    print("  │  MCP token tracking works immediately with ~95% accuracy.      │")
    print("  │  For 100% exact token counts, optionally download the Gemma    │")
    print("  │  tokenizer (~2MB) — the same tokenizer Google uses internally. │")
    print("  │                                                                 │")
    print("  │  Command: mcp-audit tokenizer download                         │")
    print("  │                                                                 │")
    print("  │  This is optional. Without it, tracking still works — you'll   │")
    print("  │  just see estimates instead of exact counts for Gemini CLI.    │")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()
    print("  📚 Docs: https://github.com/littlebearapps/mcp-audit#readme")
    print()

    # Interactive prompt
    try:
        response = input("  Run quick setup? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        response = "n"

    # Create marker directory if needed
    marker_file.parent.mkdir(parents=True, exist_ok=True)

    if response in ("y", "yes"):
        print()
        # Run init command
        import subprocess
        import sys

        subprocess.run([sys.executable, "-m", "mcp_audit", "init"])
        # Mark as initialized
        marker_file.touch()
        print()
        print("Setup complete! Starting collect...")
        print()
        return True
    else:
        # Mark as initialized (user declined but we don't ask again)
        marker_file.touch()
        print()
        print("  No problem! You can run 'mcp-audit init' anytime for guided setup.")
        print()
        print("  Gemini CLI users: 'mcp-audit tokenizer download' for 100% accuracy")
        print("  (optional — tracking works now with ~95% accuracy)")
        print()
        return True


def cmd_collect(args: argparse.Namespace) -> int:
    """Execute collect command."""
    global _active_tracker, _active_display, _shutdown_in_progress, _session_saved

    from .display import DisplaySnapshot, create_display

    # Check for first run (interactive welcome)
    # Skip if running in non-interactive mode (quiet/plain)
    if not args.quiet and not args.plain:
        _check_first_run()

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
        # Resolve theme: 'auto' -> None (triggers auto-detection)
        theme = None if args.theme == "auto" else args.theme

        display = create_display(
            mode=display_mode,
            refresh_rate=args.refresh_rate,
            pinned_servers=args.pinned_servers,
            theme=theme,
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

            if args.from_start:
                print(
                    "Note: --from-start only works with Codex/Gemini CLI (Claude Code streams live events)"
                )
            tracker = ClaudeCodeAdapter(project=project)
        elif platform == "codex-cli":
            from .codex_cli_adapter import CodexCLIAdapter

            tracker = CodexCLIAdapter(project=project, from_start=args.from_start)
        elif platform == "gemini-cli":
            from .gemini_cli_adapter import GeminiCLIAdapter
            from .token_estimator import check_gemma_tokenizer_status

            tracker = GeminiCLIAdapter(project=project, from_start=args.from_start)

            # "Noisy fallback" - inform user if using approximate token estimation
            gemma_status = check_gemma_tokenizer_status()
            if not gemma_status["installed"]:
                print("Note: Using standard tokenizer for Gemini CLI (~95% accuracy).")
                print("      For 100% accuracy: mcp-audit tokenizer download")
                print()
        else:
            display.stop(initial_snapshot)
            print(f"Error: Platform '{platform}' not yet implemented")
            print("Supported platforms: claude-code, codex-cli, gemini-cli")
            return 1

        # Set global tracker for signal handlers
        _active_tracker = tracker

        # Set output directory from CLI args
        tracker.output_dir = args.output

        # v0.8.0: Set pinned servers from CLI args (task-106.5)
        tracker.session.pinned_servers = args.pinned_servers or []

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
                # Use full session file path if available
                session_dir = str(tracker.session_path) if tracker.session_path else ""
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
    # Enhanced cost tracking (fix for task-42.1, task-95.1)
    # ================================================================
    input_tokens = session.token_usage.input_tokens
    output_tokens = session.token_usage.output_tokens
    cache_created = session.token_usage.cache_created_tokens
    cache_read = session.token_usage.cache_read_tokens

    # Use pre-calculated costs from session if available (task-95.1)
    # This avoids double-counting for platforms like Codex CLI where
    # input_tokens already includes cache_read_tokens
    cost_estimate = session.cost_estimate
    cost_no_cache = session.cost_no_cache

    # Only recalculate if session doesn't have cost_no_cache but has tokens
    # (backwards compatibility with older session files, or Claude Code which
    # calculates costs differently - input_tokens does NOT include cache tokens)
    # For Codex/Gemini CLI, the adapter should have already set both cost fields.
    has_tokens = (input_tokens + output_tokens + cache_created + cache_read) > 0
    if cost_no_cache == 0.0 and has_tokens:
        # Check if this is a Codex/Gemini session that already has cost_estimate set
        # If so, don't recalculate as it would double-count
        is_codex_or_gemini = session.platform in ("codex-cli", "gemini-cli")

        if not is_codex_or_gemini or cost_estimate == 0.0:
            pricing_config = PricingConfig()
            model_for_pricing = model_id or "claude-sonnet-4-5-20250929"  # Default fallback
            pricing = pricing_config.get_model_pricing(model_for_pricing)
            if pricing:
                input_rate = pricing.get("input", 3.0)  # Default Sonnet 4.5 rate
                output_rate = pricing.get("output", 15.0)
                # Note: This calculation assumes Claude Code format where input_tokens
                # does NOT include cache tokens. For Codex/Gemini, the adapter
                # should have already set cost_no_cache.
                cost_no_cache = (
                    ((input_tokens + cache_created + cache_read) * input_rate)
                    + (output_tokens * output_rate)
                ) / 1_000_000
            else:
                # Fallback to Sonnet 4.5 default pricing
                cost_no_cache = (
                    ((input_tokens + cache_created + cache_read) * 3.0) + (output_tokens * 15.0)
                ) / 1_000_000

    # Calculate savings from pre-calculated or recalculated values
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

    # ================================================================
    # Smell detection (v0.7.0 - task-105.2)
    # ================================================================
    from .smells import SmellDetector

    detector = SmellDetector()
    smells = detector.analyze(session)
    # Convert to tuple format: (pattern, severity, tool, description)
    detected_smells = [(s.pattern, s.severity, s.tool, s.description) for s in smells]

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
        # Smell detection (v0.7.0 - task-105.2)
        detected_smells=detected_smells,
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


def cmd_smells(args: argparse.Namespace) -> int:
    """Execute smells command - cross-session smell aggregation."""
    from .smell_aggregator import SmellAggregator

    aggregator = SmellAggregator()
    result = aggregator.aggregate(
        days=args.days,
        platform=args.platform,
        project=args.project,
    )

    # Filter by minimum frequency
    min_freq = getattr(args, "min_frequency", 0.0)
    if min_freq > 0:
        result.aggregated_smells = [
            s for s in result.aggregated_smells if s.frequency_percent >= min_freq
        ]

    # Output based on format
    output_format = getattr(args, "format", "text")
    output_path = getattr(args, "output", None)

    if output_format == "json":
        return _output_smells_json(result, output_path)
    elif output_format == "markdown":
        return _output_smells_markdown(result, output_path)
    else:
        return _output_smells_text(result, output_path)


def _output_smells_text(result: "SmellAggregationResult", output_path: Optional[Path]) -> int:
    """Output smells report as formatted text with progress bars."""
    lines: List[str] = []

    # Header
    days = (result.query_end - result.query_start).days + 1
    lines.append(f"Smell Trends (last {days} days, {result.total_sessions} sessions)")
    lines.append("=" * 70)
    lines.append("")

    if not result.aggregated_smells:
        lines.append("No smells detected in the specified date range.")
        lines.append("")
        _output_lines(lines, output_path)
        return 0

    # Column headers
    lines.append(f"{'Pattern':<18} {'Frequency':<15} {'Sessions':<12} Trend")
    lines.append("-" * 70)

    # Smell rows
    for smell in result.aggregated_smells:
        # Progress bar (10 chars)
        filled = int(smell.frequency_percent / 10)
        bar = "█" * filled + "░" * (10 - filled)

        # Trend indicator
        if smell.trend == "worsening":
            trend = f"↑ worsening (+{abs(smell.trend_change_percent):.0f}%)"
        elif smell.trend == "improving":
            trend = f"↓ improving ({smell.trend_change_percent:.0f}%)"
        else:
            trend = "→ stable"

        # Format row
        freq_str = f"{bar} {smell.frequency_percent:>3.0f}%"
        sessions_str = f"({smell.sessions_affected:>2}/{smell.total_sessions})"

        lines.append(f"{smell.pattern:<18} {freq_str:<15} {sessions_str:<12} {trend}")

    lines.append("")
    lines.append("-" * 70)

    # Top affected tools summary
    all_tools: Dict[str, int] = {}
    for smell in result.aggregated_smells:
        for tool, count in smell.top_tools:
            all_tools[tool] = all_tools.get(tool, 0) + count

    if all_tools:
        lines.append("Top Affected Tools:")
        sorted_tools = sorted(all_tools.items(), key=lambda x: x[1], reverse=True)[:5]
        for tool, count in sorted_tools:
            lines.append(f"  • {tool}: {count} occurrences")
        lines.append("")

    _output_lines(lines, output_path)
    return 0


def _output_smells_json(result: "SmellAggregationResult", output_path: Optional[Path]) -> int:
    """Output smells report as JSON."""
    import json

    output = json.dumps(result.to_dict(), indent=2)

    if output_path:
        output_path.write_text(output)
        print(f"JSON report written to: {output_path}")
    else:
        print(output)

    return 0


def _output_smells_markdown(result: "SmellAggregationResult", output_path: Optional[Path]) -> int:
    """Output smells report as Markdown."""
    lines: List[str] = []

    # Header
    days = (result.query_end - result.query_start).days + 1
    lines.append("# Smell Trends Report")
    lines.append("")
    lines.append(f"**Period:** {result.query_start} to {result.query_end} ({days} days)")
    lines.append(f"**Sessions analyzed:** {result.total_sessions}")
    lines.append(f"**Sessions with smells:** {result.sessions_with_smells}")
    if result.platform_filter:
        lines.append(f"**Platform:** {result.platform_filter}")
    if result.project_filter:
        lines.append(f"**Project:** {result.project_filter}")
    lines.append("")

    if not result.aggregated_smells:
        lines.append("No smells detected in the specified date range.")
        _output_lines(lines, output_path)
        return 0

    # Table
    lines.append("## Smell Patterns")
    lines.append("")
    lines.append("| Pattern | Frequency | Sessions | Trend |")
    lines.append("|---------|-----------|----------|-------|")

    for smell in result.aggregated_smells:
        # Trend indicator
        if smell.trend == "worsening":
            trend = f"↑ +{abs(smell.trend_change_percent):.0f}%"
        elif smell.trend == "improving":
            trend = f"↓ {smell.trend_change_percent:.0f}%"
        else:
            trend = "→ stable"

        lines.append(
            f"| {smell.pattern} | {smell.frequency_percent:.0f}% | "
            f"{smell.sessions_affected}/{smell.total_sessions} | {trend} |"
        )

    lines.append("")

    # Top tools
    all_tools: Dict[str, int] = {}
    for smell in result.aggregated_smells:
        for tool, count in smell.top_tools:
            all_tools[tool] = all_tools.get(tool, 0) + count

    if all_tools:
        lines.append("## Top Affected Tools")
        lines.append("")
        sorted_tools = sorted(all_tools.items(), key=lambda x: x[1], reverse=True)[:10]
        for tool, count in sorted_tools:
            lines.append(f"- **{tool}**: {count} occurrences")
        lines.append("")

    _output_lines(lines, output_path)
    return 0


def _output_lines(lines: List[str], output_path: Optional[Path]) -> None:
    """Output lines to file or stdout."""
    output = "\n".join(lines)
    if output_path:
        output_path.write_text(output)
        print(f"Report written to: {output_path}")
    else:
        print(output)


def cmd_init(args: argparse.Namespace) -> int:
    """Execute init command - interactive setup wizard."""
    import importlib.util

    from .token_estimator import check_gemma_tokenizer_status

    print()
    print("=" * 60)
    print("  mcp-audit Setup Wizard")
    print("=" * 60)
    print()

    auto_yes = getattr(args, "yes", False)
    auto_no = getattr(args, "no", False)
    check_only = getattr(args, "check_only", False)

    # Track what we found and did
    issues_found = 0
    enhancements_available = 0
    enhancements_installed = 0

    # ========================================================================
    # Check 1: Core dependencies
    # ========================================================================
    print("[1/3] Checking core dependencies...")
    print()

    # Check tiktoken
    if importlib.util.find_spec("tiktoken"):
        print("  ✓ tiktoken installed (Codex CLI token estimation)")
    else:
        print("  ✗ tiktoken NOT installed")
        issues_found += 1

    # Check sentencepiece
    if importlib.util.find_spec("sentencepiece"):
        print("  ✓ sentencepiece installed (Gemini CLI token estimation)")
    else:
        print("  ✗ sentencepiece NOT installed")
        issues_found += 1

    # Check rich
    if importlib.util.find_spec("rich"):
        print("  ✓ rich installed (TUI display)")
    else:
        print("  ✗ rich NOT installed")
        issues_found += 1

    print()

    # ========================================================================
    # Check 2: Optional enhancements
    # ========================================================================
    print("[2/3] Checking optional enhancements...")
    print()

    # Gemma tokenizer status
    gemma_status = check_gemma_tokenizer_status()

    if gemma_status["installed"]:
        print("  ✓ Gemma tokenizer installed")
        print(f"    Location: {gemma_status['location']}")
        print(f"    Source: {gemma_status['source']}")
    else:
        enhancements_available += 1
        print("  ○ Gemma tokenizer NOT installed (optional)")
        print("    Provides 100% accurate Gemini CLI token counts")
        print("    Without it: ~95-99% accuracy using tiktoken fallback")

        if not check_only:
            # Ask user if they want to install
            if auto_no:
                print("    Skipped (--no flag)")
            elif auto_yes:
                print("    Installing (--yes flag)...")
                success, message = _init_install_gemma_tokenizer()
                if success:
                    enhancements_installed += 1
                    print(f"    ✓ {message}")
                else:
                    print(f"    ✗ {message}")
            else:
                # Interactive prompt
                print()
                response = _prompt_yes_no(
                    "    Install Gemma tokenizer for 100% Gemini accuracy?",
                    default=False,
                )
                if response:
                    success, message = _init_install_gemma_tokenizer()
                    if success:
                        enhancements_installed += 1
                        print(f"    ✓ {message}")
                    else:
                        print(f"    ✗ {message}")
                else:
                    print("    Skipped")

    print()

    # ========================================================================
    # Check 3: Pricing configuration (v1.6.0 - task-108.3.4)
    # ========================================================================
    print("[3/4] Checking pricing configuration...")
    print()

    from .pricing_config import PricingConfig

    pricing_config = PricingConfig()
    pricing_source = pricing_config.pricing_source

    # Display pricing source
    if pricing_source == "api":
        print("  ✓ Dynamic pricing enabled (LiteLLM API)")
        if pricing_config._pricing_api:
            api = pricing_config._pricing_api
            print(f"    Models available: {api.model_count:,}")
            if api.expires_in:
                hours_left = api.expires_in.total_seconds() / 3600
                print(f"    Cache expires in: {hours_left:.1f} hours")
    elif pricing_source == "cache":
        print("  ✓ Pricing from cached API data")
        if pricing_config._pricing_api:
            api = pricing_config._pricing_api
            print(f"    Models available: {api.model_count:,}")
            if api.expires_in:
                hours_left = api.expires_in.total_seconds() / 3600
                print(f"    Cache expires in: {hours_left:.1f} hours")
    elif pricing_source == "file":
        print("  ✓ Pricing from mcp-audit.toml")
        model_count = len(pricing_config.list_models())
        print(f"    Models configured: {model_count}")
        print(f"    Last updated: {pricing_config.metadata.get('last_updated', 'unknown')}")
    else:  # defaults
        print("  ○ Using built-in default pricing")
        print("    For custom models, create mcp-audit.toml")
        model_count = len(pricing_config.list_models())
        print(f"    Default models: {model_count}")

    # Check API configuration
    if (
        hasattr(pricing_config, "_api_enabled")
        and pricing_config._api_enabled
        and pricing_source not in ("api", "cache")
    ):
        print()
        print("  ℹ Dynamic pricing enabled but not loaded")
        print("    Will fetch on first cost calculation (requires network)")

    print()

    # ========================================================================
    # Check 4: Output directories
    # ========================================================================
    print("[4/4] Checking output directories...")
    print()

    sessions_dir = Path.home() / ".mcp-audit" / "sessions"
    cache_dir = Path.home() / ".cache" / "mcp-audit"

    if sessions_dir.exists():
        session_count = len(list(sessions_dir.glob("*.json")))
        print(f"  ✓ Sessions directory exists: {sessions_dir}")
        print(f"    Contains {session_count} session file(s)")
    else:
        print("  ○ Sessions directory not created yet")
        print(f"    Will be created at: {sessions_dir}")

    if cache_dir.exists():
        print(f"  ✓ Cache directory exists: {cache_dir}")
    else:
        print("  ○ Cache directory not created yet")
        print(f"    Will be created at: {cache_dir}")

    print()

    # ========================================================================
    # Summary
    # ========================================================================
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print()

    if issues_found == 0:
        print("  ✓ All core dependencies installed")
    else:
        print(f"  ✗ {issues_found} missing core dependency(ies)")
        print("    Run: pip install mcp-audit")

    if enhancements_available == 0:
        print("  ✓ All optional enhancements installed")
    else:
        remaining = enhancements_available - enhancements_installed
        if remaining > 0:
            print(f"  ○ {remaining} optional enhancement(s) available")
            print("    Run: mcp-audit init --yes")
        else:
            print(f"  ✓ Installed {enhancements_installed} enhancement(s)")

    print()
    print("  Ready to use: mcp-audit collect --platform <platform>")
    print()

    return 0 if issues_found == 0 else 1


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt user for yes/no response."""
    suffix = " [y/N]: " if not default else " [Y/n]: "
    try:
        response = input(prompt + suffix).strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _init_install_gemma_tokenizer() -> tuple[bool, str]:
    """Attempt to install Gemma tokenizer from GitHub Releases."""
    from .token_estimator import download_gemma_from_github

    print()
    print("    Downloading Gemma tokenizer from GitHub Releases...")
    return download_gemma_from_github()


def cmd_tokenizer(args: argparse.Namespace) -> int:
    """Execute tokenizer command."""
    tokenizer_cmd = getattr(args, "tokenizer_command", None)

    if tokenizer_cmd == "status":
        return cmd_tokenizer_status(args)
    elif tokenizer_cmd == "download":
        return cmd_tokenizer_download(args)
    else:
        # No subcommand - show help
        print("Usage: mcp-audit tokenizer <command>")
        print()
        print("Commands:")
        print("  status    Check tokenizer installation status")
        print("  download  Download the Gemma tokenizer (from GitHub by default)")
        print()
        print("Run 'mcp-audit tokenizer <command> --help' for more information.")
        return 0


def cmd_tokenizer_status(args: argparse.Namespace) -> int:
    """Show tokenizer installation status."""
    import json as json_lib

    from .token_estimator import check_gemma_tokenizer_status

    status = check_gemma_tokenizer_status()

    if getattr(args, "json", False):
        print(json_lib.dumps(status, indent=2))
        return 0

    print()
    print("Gemma Tokenizer Status")
    print("=" * 40)

    if status["installed"]:
        print("✓ Installed")
        print(f"  Location: {status['location']}")

        # Use clearer terminology for source
        source_display = {
            "bundled": "Bundled with package",
            "cached": "Downloaded (persistent)",
        }.get(status["source"], status["source"])
        print(f"  Source: {source_display}")

        # Show version info if available (from tokenizer.meta.json)
        if status.get("version"):
            print(f"  Version: {status['version']}")
        if status.get("downloaded_at"):
            # Format the ISO timestamp more readably
            downloaded_at = status["downloaded_at"]
            if "T" in downloaded_at:
                downloaded_at = downloaded_at.replace("T", " ").split(".")[0]
            print(f"  Downloaded: {downloaded_at}")

        print()
        print("Gemini CLI Accuracy: 100% (exact match)")
    else:
        print("✗ Not installed")
        print()
        print("Gemini CLI Accuracy: ~95% (tiktoken fallback)")
        print()
        print("To enable 100% accuracy for Gemini CLI:")
        print("  mcp-audit tokenizer download")

    # SentencePiece availability
    print()
    if status["sentencepiece_available"]:
        print("SentencePiece: available")
    else:
        print("SentencePiece: not installed")
        print("  pip install sentencepiece")

    print()
    return 0


def cmd_tokenizer_download(args: argparse.Namespace) -> int:
    """Download the Gemma tokenizer."""
    from .token_estimator import download_gemma_from_github, download_gemma_tokenizer

    source = getattr(args, "source", "github")
    release = getattr(args, "release", None)
    token = getattr(args, "token", None)
    force = getattr(args, "force", False)

    if source == "github":
        print("Downloading Gemma Tokenizer from GitHub")
        print("=" * 50)
        if release:
            print(f"  Release: {release}")
        else:
            print("  Release: latest")
        print()

        success, message = download_gemma_from_github(version=release, force=force)
    else:
        # HuggingFace source
        print("Downloading Gemma Tokenizer from HuggingFace")
        print("=" * 50)
        print()

        if not token:
            print("Note: HuggingFace requires account signup and license acceptance.")
            print("Visit: https://huggingface.co/google/gemma-2b")
            print()

        success, message = download_gemma_tokenizer(token=token, force=force)

    if success:
        print(f"✓ {message}")
        print()
        print("The Gemma tokenizer is now available for Gemini CLI sessions.")
        print("Token estimation will use SentencePiece for 100% accuracy.")
        return 0
    else:
        print("✗ Download failed")
        print()
        print(message)  # Already contains helpful context from the function

        # Add general troubleshooting hint for network errors
        if "rate limit" not in message.lower() and "not found" not in message.lower():
            print()
            print("Troubleshooting:")
            print("• Check your network connection")
            print("• Corporate firewall may block github.com")
            print("• Download manually: https://github.com/littlebearapps/mcp-audit/releases")
            print()
            print("Token estimation will use tiktoken fallback (~95% accuracy).")

        return 1


# ============================================================================
# Export Command (v1.5.0 - task-103.2)
# ============================================================================


def cmd_export(args: argparse.Namespace) -> int:
    """Handle export subcommands."""
    export_format = getattr(args, "export_format", None)

    if export_format == "ai-prompt":
        return cmd_export_ai_prompt(args)
    else:
        print("Usage: mcp-audit export <format>")
        print()
        print("Available formats:")
        print("  ai-prompt    Export session data formatted for AI analysis")
        print()
        print("Run 'mcp-audit export <format> --help' for more information.")
        return 1


def cmd_export_ai_prompt(args: argparse.Namespace) -> int:
    """Export session data formatted for AI analysis."""
    from .storage import get_latest_session, load_session_file

    # Load session data
    session_path = getattr(args, "session_path", None)
    output_format = getattr(args, "format", "markdown")
    output_path = getattr(args, "output", None)

    # v0.8.0: Pinned MCP Focus options (task-106.5)
    pinned_focus = getattr(args, "pinned_focus", False)
    full_mcp_breakdown = getattr(args, "full_mcp_breakdown", False)
    pinned_servers = getattr(args, "pinned_servers", None) or []

    if session_path is None:
        # Find latest session
        session_path = get_latest_session()
        if session_path is None:
            print("Error: No sessions found. Run 'mcp-audit collect' first.")
            return 1

    if not session_path.exists():
        print(f"Error: Session file not found: {session_path}")
        return 1

    # Load session
    session_data = load_session_file(session_path)
    if session_data is None:
        print(f"Error: Could not load session file: {session_path}")
        return 1

    # v0.8.0: Merge CLI pinned servers with session pinned servers
    session_pinned = session_data.get("session", {}).get("pinned_servers", [])
    all_pinned = list(set(pinned_servers + session_pinned))

    # Generate output
    if output_format == "markdown":
        output = generate_ai_prompt_markdown(
            session_data,
            session_path,
            pinned_focus=pinned_focus,
            full_mcp_breakdown=full_mcp_breakdown,
            pinned_servers=all_pinned,
        )
    else:
        output = generate_ai_prompt_json(
            session_data,
            session_path,
            pinned_focus=pinned_focus,
            full_mcp_breakdown=full_mcp_breakdown,
            pinned_servers=all_pinned,
        )

    # Write output
    if output_path:
        output_path.write_text(output)
        print(f"Exported to: {output_path}")
    else:
        print(output)

    return 0


def generate_ai_prompt_markdown(
    session_data: Dict[str, Any],
    session_path: Path,
    *,
    pinned_focus: bool = False,
    full_mcp_breakdown: bool = False,
    pinned_servers: Optional[List[str]] = None,
) -> str:
    """Generate AI-optimized markdown prompt from session data.

    Args:
        session_data: Parsed session JSON data
        session_path: Path to the session file
        pinned_focus: Add dedicated analysis section for pinned servers (v0.8.0)
        full_mcp_breakdown: Include per-server and per-tool breakdown for ALL servers (v0.8.0)
        pinned_servers: List of servers to analyze as pinned (v0.8.0)
    """
    lines = []
    pinned_servers = pinned_servers or []

    # Header
    lines.append("# MCP Session Analysis Request")
    lines.append("")
    lines.append("Please analyze this MCP (Model Context Protocol) session data and provide:")
    lines.append("1. Key observations about tool usage patterns")
    lines.append("2. Efficiency recommendations")
    lines.append("3. Cost optimization suggestions")
    lines.append("4. Architecture improvements (if applicable)")
    lines.append("")

    # v0.8.0: Pinned Server Focus Section (task-106.5)
    server_sessions = session_data.get("server_sessions", {})
    if pinned_focus and pinned_servers:
        lines.extend(_generate_pinned_server_focus(server_sessions, pinned_servers))

    # Session Summary
    session = session_data.get("session", {})
    lines.append("## Session Summary")
    lines.append("")
    lines.append(f"- **Platform**: {session.get('platform', 'unknown')}")
    lines.append(f"- **Model**: {session.get('model', 'unknown')}")
    lines.append(f"- **Duration**: {_format_duration(session.get('duration_seconds', 0))}")
    lines.append(f"- **Project**: {session.get('project', 'unknown')}")
    if pinned_servers:
        lines.append(f"- **Pinned Servers**: {', '.join(pinned_servers)}")
    lines.append("")

    # Token Usage
    token_usage = session_data.get("token_usage", {})
    duration_seconds = session.get("duration_seconds", 0)
    total_tokens = token_usage.get("total_tokens", 0)
    input_tokens = token_usage.get("input_tokens", 0)
    cache_read = token_usage.get("cache_read_tokens", 0)

    # Rate metrics (v0.7.0 - task-105.12)
    tokens_rate = "—"
    if duration_seconds > 0:
        tokens_per_min = total_tokens / (duration_seconds / 60)
        if tokens_per_min >= 1_000_000:
            tokens_rate = f"{tokens_per_min / 1_000_000:.1f}M/min"
        elif tokens_per_min >= 1_000:
            tokens_rate = f"{tokens_per_min / 1_000:.0f}K/min"
        else:
            tokens_rate = f"{int(tokens_per_min)}/min"

    # Cache hit ratio (v0.7.0 - task-105.13)
    cache_hit_ratio = 0.0
    denominator = cache_read + input_tokens
    if denominator > 0:
        cache_hit_ratio = cache_read / denominator

    lines.append("## Token Usage")
    lines.append("")
    lines.append(f"- **Input Tokens**: {input_tokens:,}")
    lines.append(f"- **Output Tokens**: {token_usage.get('output_tokens', 0):,}")
    lines.append(f"- **Total Tokens**: {total_tokens:,}")
    lines.append(f"- **Token Rate**: {tokens_rate}")
    lines.append(f"- **Cache Read**: {cache_read:,}")
    lines.append(f"- **Cache Created**: {token_usage.get('cache_created_tokens', 0):,}")
    lines.append(f"- **Cache Hit Ratio**: {cache_hit_ratio:.1%} (token-based)")
    lines.append("")

    # Cost
    cost = session_data.get("cost_estimate_usd", 0)
    lines.append("## Cost")
    lines.append("")
    lines.append(f"- **Estimated Cost**: ${cost:.4f}")
    lines.append("")

    # MCP Tool Usage
    mcp_summary = session_data.get("mcp_summary", {})
    total_calls = mcp_summary.get("total_calls", 0)

    # Call rate (v0.7.0 - task-105.12)
    calls_rate = "—"
    if duration_seconds > 0:
        calls_per_min = total_calls / (duration_seconds / 60)
        calls_rate = f"{calls_per_min:.1f}/min"

    lines.append("## MCP Tool Usage")
    lines.append("")
    lines.append(f"- **Total MCP Calls**: {total_calls}")
    lines.append(f"- **Unique Tools**: {mcp_summary.get('unique_tools', 0)}")
    lines.append(f"- **Call Rate**: {calls_rate}")
    lines.append(f"- **Most Called**: {mcp_summary.get('most_called', 'N/A')}")
    lines.append("")

    # Tool breakdown (top 10) or full breakdown
    tool_stats = []
    for server_name, server_data in server_sessions.items():
        if server_name == "builtin":
            continue
        tools = server_data.get("tools", {})
        for tool_name, stats in tools.items():
            tool_stats.append(
                {
                    "tool": tool_name,
                    "server": server_name,
                    "calls": stats.get("calls", 0),
                    "tokens": stats.get("total_tokens", 0),
                }
            )

    # Sort by tokens (descending)
    tool_stats.sort(key=lambda x: x["tokens"], reverse=True)

    if tool_stats:
        lines.append("### Top Tools by Token Usage")
        lines.append("")
        lines.append("| Tool | Server | Calls | Tokens |")
        lines.append("|------|--------|-------|--------|")
        for stat in tool_stats[:10]:
            lines.append(
                f"| {stat['tool']} | {stat['server']} | " f"{stat['calls']} | {stat['tokens']:,} |"
            )
        lines.append("")

    # v0.8.0: Full MCP Server Breakdown (task-106.5)
    if full_mcp_breakdown:
        lines.extend(_generate_full_mcp_breakdown(server_sessions, pinned_servers))

    # Detected Smells
    smells = session_data.get("smells", [])
    if smells:
        lines.append("## Detected Efficiency Issues")
        lines.append("")
        for smell in smells:
            severity_emoji = "⚠️" if smell.get("severity") == "warning" else "ℹ️"
            lines.append(f"### {severity_emoji} {smell.get('pattern', 'Unknown')}")
            lines.append("")
            if smell.get("tool"):
                lines.append(f"**Tool**: {smell['tool']}")
            lines.append(f"**Description**: {smell.get('description', 'No description')}")
            lines.append("")
            evidence = smell.get("evidence", {})
            if evidence:
                lines.append("**Evidence**:")
                for key, value in evidence.items():
                    lines.append(f"- {key}: {value}")
                lines.append("")
    else:
        lines.append("## Detected Efficiency Issues")
        lines.append("")
        lines.append("No efficiency issues detected.")
        lines.append("")

    # v0.8.0: AI Recommendations (task-106.2)
    if smells:
        lines.extend(_generate_recommendations_section(smells))

    # Zombie Tools
    zombie_tools = session_data.get("zombie_tools", {})
    if zombie_tools:
        lines.append("## Zombie Tools (Defined but Never Called)")
        lines.append("")
        for server, tools in zombie_tools.items():
            lines.append(f"**{server}**: {', '.join(tools)}")
        lines.append("")

    # Data Quality
    data_quality = session_data.get("data_quality", {})
    if data_quality:
        lines.append("## Data Quality")
        lines.append("")
        lines.append(f"- **Accuracy Level**: {data_quality.get('accuracy_level', 'unknown')}")
        lines.append(f"- **Token Source**: {data_quality.get('token_source', 'unknown')}")
        lines.append(f"- **Confidence**: {data_quality.get('confidence', 0):.0%}")
        # v1.6.0: Pricing source fields (task-108.3.4)
        if data_quality.get("pricing_source"):
            lines.append(f"- **Pricing Source**: {data_quality.get('pricing_source')}")
        if data_quality.get("pricing_freshness"):
            lines.append(f"- **Pricing Freshness**: {data_quality.get('pricing_freshness')}")
        if data_quality.get("notes"):
            lines.append(f"- **Notes**: {data_quality['notes']}")
        lines.append("")

    # v0.8.0: Context-Aware Analysis Questions (task-106.5)
    lines.extend(
        _generate_context_aware_questions(
            session_data, tool_stats, pinned_servers, smells, zombie_tools
        )
    )

    # Source file reference
    lines.append("---")
    lines.append(f"*Source: {session_path.name}*")

    return "\n".join(lines)


def _generate_pinned_server_focus(
    server_sessions: Dict[str, Any], pinned_servers: List[str]
) -> List[str]:
    """Generate the Pinned Server Focus section for AI export (v0.8.0 - task-106.5)."""
    lines = []

    for server_name in pinned_servers:
        server_data = server_sessions.get(server_name, {})
        if not server_data:
            # Server pinned but not used
            lines.append(f"## Pinned Server Focus: {server_name}")
            lines.append("")
            lines.append("**Status**: Pinned but not used in this session")
            lines.append("")
            continue

        tools = server_data.get("tools", {})
        total_calls = sum(t.get("calls", 0) for t in tools.values())
        total_tokens = sum(t.get("total_tokens", 0) for t in tools.values())

        lines.append(f"## Pinned Server Focus: {server_name}")
        lines.append("")
        lines.append("### Usage Summary")
        lines.append("")
        lines.append(f"- **Total Calls**: {total_calls}")
        lines.append(f"- **Total Tokens**: {total_tokens:,}")
        lines.append(f"- **Unique Tools Used**: {len(tools)}")
        if total_calls > 0:
            lines.append(f"- **Avg Tokens/Call**: {total_tokens // total_calls:,}")
        lines.append("")

        if tools:
            lines.append("### Tool Breakdown")
            lines.append("")
            lines.append("| Tool | Calls | Tokens | Avg/Call |")
            lines.append("|------|-------|--------|----------|")

            # Sort tools by tokens descending
            sorted_tools = sorted(
                tools.items(), key=lambda x: x[1].get("total_tokens", 0), reverse=True
            )
            for tool_name, stats in sorted_tools:
                calls = stats.get("calls", 0)
                tokens = stats.get("total_tokens", 0)
                avg = tokens // calls if calls > 0 else 0
                lines.append(f"| {tool_name} | {calls} | {tokens:,} | {avg:,} |")
            lines.append("")

        # Patterns detected for this server
        lines.append("### Patterns Detected")
        lines.append("")
        if total_calls > 0:
            avg_efficiency = total_tokens / total_calls
            lines.append(f"- Average token efficiency: {avg_efficiency:,.0f} tokens/call")
            if avg_efficiency > 5000:
                lines.append("- High token usage per call - consider optimization")
            elif avg_efficiency < 500:
                lines.append("- Efficient token usage per call")
        else:
            lines.append("- No calls recorded")
        lines.append("")

    return lines


def _generate_full_mcp_breakdown(
    server_sessions: Dict[str, Any], pinned_servers: List[str]
) -> List[str]:
    """Generate full MCP server breakdown for all servers (v0.8.0 - task-106.5)."""
    lines = []
    lines.append("## Full MCP Server Breakdown")
    lines.append("")

    # Exclude builtin
    mcp_servers = {k: v for k, v in server_sessions.items() if k != "builtin"}

    if not mcp_servers:
        lines.append("No MCP servers used in this session.")
        lines.append("")
        return lines

    # Calculate totals for percentage
    total_mcp_tokens = sum(
        sum(t.get("total_tokens", 0) for t in s.get("tools", {}).values())
        for s in mcp_servers.values()
    )

    for server_name, server_data in sorted(mcp_servers.items()):
        tools = server_data.get("tools", {})
        server_calls = sum(t.get("calls", 0) for t in tools.values())
        server_tokens = sum(t.get("total_tokens", 0) for t in tools.values())

        is_pinned = server_name in pinned_servers
        pinned_badge = " [PINNED]" if is_pinned else ""
        share_pct = (server_tokens / total_mcp_tokens * 100) if total_mcp_tokens > 0 else 0

        lines.append(f"### Server: {server_name}{pinned_badge}")
        lines.append("")
        lines.append(
            f"- **Calls**: {server_calls} | **Tokens**: {server_tokens:,} | **Share**: {share_pct:.1f}%"
        )
        lines.append("")

        if tools:
            lines.append("| Tool | Calls | Tokens | Avg |")
            lines.append("|------|-------|--------|-----|")
            sorted_tools = sorted(
                tools.items(), key=lambda x: x[1].get("total_tokens", 0), reverse=True
            )
            for tool_name, stats in sorted_tools:
                calls = stats.get("calls", 0)
                tokens = stats.get("total_tokens", 0)
                avg = tokens // calls if calls > 0 else 0
                # Format large numbers with K suffix
                tokens_fmt = f"{tokens // 1000}K" if tokens >= 1000 else str(tokens)
                avg_fmt = f"{avg // 1000}K" if avg >= 1000 else str(avg)
                lines.append(f"| {tool_name} | {calls} | {tokens_fmt} | {avg_fmt} |")
            lines.append("")

    return lines


def _generate_recommendations_section(smells: List[Dict[str, Any]]) -> List[str]:
    """Generate AI recommendations from detected smells (v0.8.0 - task-106.2)."""
    from .base_tracker import Smell
    from .recommendations import generate_recommendations

    lines: List[str] = []

    # Convert smell dicts to Smell objects
    smell_objects: List[Smell] = []
    for smell_dict in smells:
        try:
            smell_objects.append(
                Smell(
                    pattern=smell_dict.get("pattern", ""),
                    severity=smell_dict.get("severity", "info"),
                    description=smell_dict.get("description", ""),
                    tool=smell_dict.get("tool"),
                    evidence=smell_dict.get("evidence", {}),
                )
            )
        except (TypeError, ValueError):
            continue

    if not smell_objects:
        return lines

    recommendations = generate_recommendations(smell_objects, min_confidence=0.3)

    if not recommendations:
        return lines

    lines.append("## AI Recommendations")
    lines.append("")
    lines.append("Based on detected efficiency issues, here are actionable recommendations:")
    lines.append("")

    for i, rec in enumerate(recommendations, 1):
        confidence_pct = int(rec.confidence * 100)
        lines.append(f"### {i}. {rec.type}")
        lines.append("")
        lines.append(f"**Confidence**: {confidence_pct}%")
        lines.append("")
        lines.append(f"**Evidence**: {rec.evidence}")
        lines.append("")
        lines.append(f"**Action**: {rec.action}")
        lines.append("")
        lines.append(f"**Impact**: {rec.impact}")
        lines.append("")

    return lines


def _generate_context_aware_questions(
    session_data: Dict[str, Any],
    tool_stats: List[Dict[str, Any]],
    pinned_servers: List[str],
    smells: List[Dict[str, Any]],
    zombie_tools: Dict[str, List[str]],
) -> List[str]:
    """Generate context-aware analysis questions based on actual session data (v0.8.0 - task-106.5)."""
    lines = []
    questions = []

    # Token-based questions
    if tool_stats:
        top_tool = tool_stats[0]
        total_tokens = sum(s["tokens"] for s in tool_stats)
        if total_tokens > 0:
            top_pct = (top_tool["tokens"] / total_tokens) * 100
            if top_pct > 50:
                questions.append(
                    f"Why did `{top_tool['tool']}` consume {top_pct:.0f}% of MCP tokens? "
                    "Is this expected for the task?"
                )

    # Pinned server questions
    server_sessions = session_data.get("server_sessions", {})
    used_servers = set(server_sessions.keys()) - {"builtin"}

    for server in pinned_servers:
        if server not in used_servers:
            questions.append(
                f"Pinned server `{server}` wasn't used in this session. "
                "Should it be unpinned to reduce context overhead?"
            )
        else:
            server_data = server_sessions.get(server, {})
            tools = server_data.get("tools", {})
            if len(tools) == 1:
                tool_name = list(tools.keys())[0]
                questions.append(
                    f"Pinned server `{server}` only used `{tool_name}`. "
                    "Are the other available tools needed?"
                )

    # Smell-based questions
    for smell in smells:
        pattern = smell.get("pattern", "")
        tool = smell.get("tool", "")
        evidence = smell.get("evidence", {})

        if pattern == "CHATTY":
            call_count = evidence.get("call_count", 0)
            questions.append(
                f"Tool `{tool}` was called {call_count} times. "
                "Can these calls be batched or reduced?"
            )
        elif pattern == "REDUNDANT_CALLS":
            dup_count = evidence.get("duplicate_count", 0)
            questions.append(
                f"Tool `{tool}` had {dup_count} duplicate calls. "
                "Is caching being used effectively?"
            )
        elif pattern == "EXPENSIVE_FAILURES":
            tokens = evidence.get("tokens", 0)
            questions.append(
                f"A failed operation consumed {tokens:,} tokens. "
                "Should validation be added before expensive calls?"
            )

    # Zombie tool questions
    if zombie_tools:
        total_zombies = sum(len(tools) for tools in zombie_tools.values())
        if total_zombies > 10:
            questions.append(
                f"There are {total_zombies} zombie tools defined but never used. "
                "Consider removing unused MCP servers to reduce context size."
            )

    # Default questions if no specific ones generated
    if not questions:
        questions = [
            "Which tools are consuming the most tokens? Are they necessary?",
            "Is the cache being used effectively? How can cache hit rate improve?",
            "Are there chatty tools that could be batched or optimized?",
            "Are zombie tools contributing unnecessary context overhead?",
            "What architectural changes could reduce token usage?",
            "Are there alternative tools or approaches that would be more efficient?",
        ]

    lines.append("## Context-Aware Analysis Questions")
    lines.append("")
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")

    return lines


def generate_ai_prompt_json(
    session_data: Dict[str, Any],
    session_path: Path,
    *,
    pinned_focus: bool = False,
    full_mcp_breakdown: bool = False,
    pinned_servers: Optional[List[str]] = None,
) -> str:
    """Generate AI-optimized JSON from session data.

    Args:
        session_data: Parsed session JSON data
        session_path: Path to the session file
        pinned_focus: Add dedicated analysis section for pinned servers (v0.8.0)
        full_mcp_breakdown: Include per-server and per-tool breakdown for ALL servers (v0.8.0)
        pinned_servers: List of servers to analyze as pinned (v0.8.0)
    """
    import json

    from .base_tracker import Smell
    from .recommendations import generate_recommendations

    pinned_servers = pinned_servers or []
    server_sessions = session_data.get("server_sessions", {})

    # Extract relevant fields for AI analysis
    ai_prompt_data = {
        "analysis_request": {
            "instructions": [
                "Analyze this MCP session data",
                "Identify tool usage patterns",
                "Provide efficiency recommendations",
                "Suggest cost optimization strategies",
            ],
        },
        "session_summary": {
            "platform": session_data.get("session", {}).get("platform"),
            "model": session_data.get("session", {}).get("model"),
            "duration_seconds": session_data.get("session", {}).get("duration_seconds"),
            "project": session_data.get("session", {}).get("project"),
        },
        "token_usage": session_data.get("token_usage", {}),
        "cost_estimate_usd": session_data.get("cost_estimate_usd"),
        "mcp_summary": session_data.get("mcp_summary", {}),
        "smells": session_data.get("smells", []),
        "zombie_tools": session_data.get("zombie_tools", {}),
        "data_quality": session_data.get("data_quality", {}),
        "source_file": session_path.name,
    }

    # v0.8.0: Add pinned servers metadata (task-106.5)
    if pinned_servers:
        ai_prompt_data["pinned_servers"] = pinned_servers

    # Add top tools by tokens
    tool_stats = []
    for server_name, server_data in server_sessions.items():
        if server_name == "builtin":
            continue
        tools = server_data.get("tools", {})
        for tool_name, stats in tools.items():
            tool_stats.append(
                {
                    "tool": tool_name,
                    "server": server_name,
                    "calls": stats.get("calls", 0),
                    "tokens": stats.get("total_tokens", 0),
                }
            )

    tool_stats.sort(key=lambda x: x["tokens"], reverse=True)
    ai_prompt_data["top_tools"] = tool_stats[:10]

    # v0.8.0: Pinned server analysis (task-106.5)
    if pinned_focus and pinned_servers:
        pinned_analysis = {}
        for server_name in pinned_servers:
            server_data = server_sessions.get(server_name, {})
            tools = server_data.get("tools", {})
            total_calls = sum(t.get("calls", 0) for t in tools.values())
            total_tokens = sum(t.get("total_tokens", 0) for t in tools.values())

            pinned_analysis[server_name] = {
                "calls": total_calls,
                "tokens": total_tokens,
                "is_pinned": True,
                "tools": {
                    name: {
                        "calls": stats.get("calls", 0),
                        "tokens": stats.get("total_tokens", 0),
                        "avg": (
                            stats.get("total_tokens", 0) // stats.get("calls", 1)
                            if stats.get("calls", 0) > 0
                            else 0
                        ),
                    }
                    for name, stats in tools.items()
                },
            }
        ai_prompt_data["pinned_server_analysis"] = pinned_analysis

    # v0.8.0: Full server breakdown (task-106.5)
    if full_mcp_breakdown:
        full_breakdown = {}
        total_mcp_tokens = sum(
            sum(t.get("total_tokens", 0) for t in s.get("tools", {}).values())
            for name, s in server_sessions.items()
            if name != "builtin"
        )

        for server_name, server_data in server_sessions.items():
            if server_name == "builtin":
                continue
            tools = server_data.get("tools", {})
            server_calls = sum(t.get("calls", 0) for t in tools.values())
            server_tokens = sum(t.get("total_tokens", 0) for t in tools.values())
            share_pct = (server_tokens / total_mcp_tokens * 100) if total_mcp_tokens > 0 else 0

            full_breakdown[server_name] = {
                "calls": server_calls,
                "tokens": server_tokens,
                "share_percent": round(share_pct, 1),
                "is_pinned": server_name in pinned_servers,
                "tools": {
                    name: {
                        "calls": stats.get("calls", 0),
                        "tokens": stats.get("total_tokens", 0),
                        "avg": (
                            stats.get("total_tokens", 0) // stats.get("calls", 1)
                            if stats.get("calls", 0) > 0
                            else 0
                        ),
                    }
                    for name, stats in tools.items()
                },
            }
        ai_prompt_data["full_server_breakdown"] = full_breakdown

    # v0.8.0: Recommendations (task-106.2)
    smells = session_data.get("smells", [])
    if smells:
        smell_objects = []
        for smell_dict in smells:
            try:
                smell_objects.append(
                    Smell(
                        pattern=smell_dict.get("pattern", ""),
                        severity=smell_dict.get("severity", "info"),
                        description=smell_dict.get("description"),
                        tool=smell_dict.get("tool"),
                        evidence=smell_dict.get("evidence", {}),
                    )
                )
            except (TypeError, ValueError):
                continue

        if smell_objects:
            recommendations = generate_recommendations(smell_objects, min_confidence=0.3)
            ai_prompt_data["recommendations"] = [rec.to_dict() for rec in recommendations]

    # v0.8.0: Context-aware questions (task-106.5)
    questions = _generate_context_questions_list(
        session_data, tool_stats, pinned_servers, smells, session_data.get("zombie_tools", {})
    )
    ai_prompt_data["context_questions"] = questions

    return json.dumps(ai_prompt_data, indent=2)


def _generate_context_questions_list(
    session_data: Dict[str, Any],
    tool_stats: List[Dict[str, Any]],
    pinned_servers: List[str],
    smells: List[Dict[str, Any]],
    zombie_tools: Dict[str, List[str]],
) -> List[str]:
    """Generate context-aware questions as a list (v0.8.0 - task-106.5)."""
    questions = []

    # Token-based questions
    if tool_stats:
        top_tool = tool_stats[0]
        total_tokens = sum(s["tokens"] for s in tool_stats)
        if total_tokens > 0:
            top_pct = (top_tool["tokens"] / total_tokens) * 100
            if top_pct > 50:
                questions.append(
                    f"Why did '{top_tool['tool']}' consume {top_pct:.0f}% of MCP tokens?"
                )

    # Pinned server questions
    server_sessions = session_data.get("server_sessions", {})
    used_servers = set(server_sessions.keys()) - {"builtin"}

    for server in pinned_servers:
        if server not in used_servers:
            questions.append(f"Pinned server '{server}' wasn't used - should it be unpinned?")
        else:
            server_data = server_sessions.get(server, {})
            tools = server_data.get("tools", {})
            if len(tools) == 1:
                tool_name = list(tools.keys())[0]
                questions.append(
                    f"Pinned server '{server}' only used '{tool_name}' - are other tools needed?"
                )

    # Smell-based questions
    for smell in smells:
        pattern = smell.get("pattern", "")
        tool = smell.get("tool", "")
        evidence = smell.get("evidence", {})

        if pattern == "CHATTY":
            call_count = evidence.get("call_count", 0)
            questions.append(f"Tool '{tool}' was called {call_count} times - can calls be batched?")
        elif pattern == "REDUNDANT_CALLS":
            questions.append(f"Tool '{tool}' has redundant calls - is caching effective?")
        elif pattern == "EXPENSIVE_FAILURES":
            tokens = evidence.get("tokens", 0)
            questions.append(f"Failed operation consumed {tokens:,} tokens - add validation?")

    # Zombie tool questions
    if zombie_tools:
        total_zombies = sum(len(tools) for tools in zombie_tools.values())
        if total_zombies > 10:
            questions.append(
                f"{total_zombies} zombie tools found - consider removing unused servers"
            )

    # Default questions if none generated
    if not questions:
        questions = [
            "Which tools consume the most tokens?",
            "Is cache being used effectively?",
            "Are there chatty tools to optimize?",
            "Should zombie tools be removed?",
        ]

    return questions


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds / 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours = int(minutes / 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours}h {remaining_minutes}m"


# ============================================================================
# UI Command (v0.7.0 - task-105.1)
# ============================================================================


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch interactive session browser."""
    from .display.session_browser import SessionBrowser

    theme = None if args.theme == "auto" else args.theme

    try:
        browser = SessionBrowser(theme=theme)
        browser.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install mcp-audit")
        return 1
    except Exception as e:
        print(f"Error: {e}")
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

    Returns "project-name/main" for worktree setups to give full context.
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
            return f"{parent.name}/{current_name}"

        # Check if .git is a file (not directory) - indicates worktree
        git_path = cwd / ".git"
        if git_path.exists() and git_path.is_file():
            return f"{parent.name}/{current_name}"

        # Even without .bare or .git file, if parent has a meaningful name
        # (not a system directory), include it for context
        system_dirs = {"users", "home", "var", "tmp", "opt", "usr"}
        if parent.name.lower() not in system_dirs and parent.name:
            return f"{parent.name}/{current_name}"

    return current_name


if __name__ == "__main__":
    sys.exit(main())
