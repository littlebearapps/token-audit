#!/usr/bin/env python3
"""
MCP Analyze CLI - Command-line interface for Token Audit

Provides commands for collecting MCP session data and generating reports.
"""

import argparse
import atexit
import re
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, cast

if TYPE_CHECKING:
    from .base_tracker import BaseTracker, Session
    from .buckets import BucketResult
    from .display import DisplayAdapter, DisplaySnapshot
    from .smell_aggregator import SmellAggregationResult
    from .storage import StreamingStorage
    from .tasks import TaskSummary

from . import __version__

# Type alias for platform names (matches storage.Platform)
Platform = Literal["claude_code", "codex_cli", "gemini_cli", "ollama_cli", "custom"]

# ============================================================================
# Global State for Signal Handlers
# ============================================================================

# These globals allow signal handlers to access tracker state for cleanup
_active_tracker: Optional["BaseTracker"] = None
_active_display: Optional["DisplayAdapter"] = None
_tracking_start_time: Optional[datetime] = None
_shutdown_in_progress: bool = False
_session_saved: bool = False


def normalize_platform(platform: Optional[str]) -> Optional[Platform]:
    """
    Normalize platform name from CLI format to internal format.

    CLI uses hyphen-style (claude-code, codex-cli) for user convenience.
    Internal storage uses underscore-style (claude_code, codex_cli).

    Args:
        platform: Platform name from CLI (may be None or "auto")

    Returns:
        Normalized platform name, or None if input is None/auto
    """
    if platform is None or platform == "auto":
        return None
    normalized = platform.replace("-", "_")
    # Cast to Platform type - validation happens at CLI argument parsing
    return cast(Platform, normalized)


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
                print("\n[token-audit] No data tracked - session not saved.")

        except Exception as e:
            print(f"\n[token-audit] Warning: Error during cleanup: {e}", file=sys.stderr)

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

    # Clean up active session marker (#117)
    if _active_tracker is not None:
        try:
            from .storage import StreamingStorage

            streaming = StreamingStorage()
            streaming.cleanup_active_session(_active_tracker.session_id)
        except Exception:
            pass  # Best effort cleanup


def _signal_handler(signum: int, _frame: object) -> None:
    """
    Handle termination signals (SIGINT, SIGTERM).

    This ensures session data is saved when:
    - Running in background and killed via `kill` command
    - Running via `timeout` command
    - User presses Ctrl+C
    """
    signal_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"\n[token-audit] Received {signal_name}, saving session...")

    _cleanup_session()

    # Exit with appropriate code
    # 128 + signal number is Unix convention for signal-terminated processes
    sys.exit(128 + signum)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="token-audit",
        description="Token Audit - Multi-platform MCP usage tracking and cost analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect session data (auto-detects platform)
  token-audit collect

  # Generate markdown report
  token-audit report ~/.token-audit/sessions --format markdown

  # Export session for AI analysis
  token-audit report ~/.token-audit/sessions --format ai

  # Analyze smell patterns across sessions
  token-audit report ~/.token-audit/sessions --smells --days 30

  # Browse sessions with Dashboard view (v1.0.0 default)
  token-audit ui

  # Start in live monitoring or recommendations view
  token-audit ui --view live
  token-audit ui --view recommendations

  # Export best practices (for AGENTS.md, etc.)
  token-audit best-practices --format markdown

  # Setup tokenizer for Gemini CLI
  token-audit tokenizer --interactive

  # Historical usage reports (v1.0.0)
  token-audit daily                     # Last 7 days
  token-audit daily --days 14 --json    # Export as JSON
  token-audit weekly --breakdown        # Show per-model breakdown
  token-audit monthly --instances       # Group by project

For more information, visit: https://github.com/littlebearapps/token-audit
        """,
    )

    parser.add_argument("--version", action="version", version=f"token-audit {__version__}")

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
        default=Path.home() / ".token-audit" / "sessions",
        help="Output directory for session data (default: ~/.token-audit/sessions)",
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

Three analysis modes are available:
  1. STANDARD REPORT  - Token usage, costs, and tool efficiency (default)
  2. AI EXPORT        - AI-ready export for LLM analysis (--format ai)
  3. SMELL ANALYSIS   - Efficiency pattern detection (--smells)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  Standard markdown report:
    token-audit report ~/.token-audit/sessions --format markdown

  Aggregate multiple sessions:
    token-audit report ~/.token-audit/sessions --aggregate --top-n 20

  AI-ready export for LLM analysis:
    token-audit report ~/.token-audit/sessions --format ai --pinned-focus

  Efficiency pattern detection:
    token-audit report ~/.token-audit/sessions --smells --days 7
        """,
    )

    report_parser.add_argument(
        "session_dir", type=Path, help="Session directory or parent directory containing sessions"
    )

    # ---- Analysis Mode Selection ----
    mode_group = report_parser.add_argument_group(
        "analysis modes",
        "Choose analysis mode (standard report is default)",
    )
    mode_group.add_argument(
        "--format",
        choices=["json", "markdown", "csv", "ai"],
        default="markdown",
        help="Report format: json, markdown, csv (standard) or ai (AI export mode)",
    )
    mode_group.add_argument(
        "--smells",
        action="store_true",
        help="Switch to smell analysis mode (pattern detection)",
    )

    # ---- Standard Report Options ----
    standard_group = report_parser.add_argument_group(
        "standard report options",
        "Options for json/markdown/csv formats",
    )
    standard_group.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    standard_group.add_argument(
        "--aggregate", action="store_true", help="Aggregate data across multiple sessions"
    )
    standard_group.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli", "ollama-cli"],
        default=None,
        help="Filter sessions by platform",
    )
    standard_group.add_argument(
        "--top-n", type=int, default=10, help="Number of top tools to show (default: 10)"
    )

    # ---- AI Export Options ----
    ai_group = report_parser.add_argument_group(
        "AI export options",
        "Options for --format ai",
    )
    ai_group.add_argument(
        "--pinned-focus",
        action="store_true",
        help="Add dedicated analysis section for pinned servers",
    )
    ai_group.add_argument(
        "--full-mcp-breakdown",
        action="store_true",
        help="Include per-server and per-tool breakdown",
    )
    ai_group.add_argument(
        "--pinned-servers",
        action="append",
        metavar="SERVER",
        help="Servers to analyze as pinned (can use multiple times)",
    )

    # ---- Smell Analysis Options ----
    smell_group = report_parser.add_argument_group(
        "smell analysis options",
        "Options for --smells mode",
    )
    smell_group.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)",
    )
    smell_group.add_argument(
        "--project",
        type=str,
        default=None,
        help="Filter by project name",
    )
    smell_group.add_argument(
        "--min-frequency",
        type=float,
        default=0.0,
        help="Minimum frequency %% to display (default: 0)",
    )

    # ---- Bucket Analysis Options (v1.0.4 - task-247.17) ----
    bucket_group = report_parser.add_argument_group(
        "bucket analysis options",
        "Options for --buckets mode",
    )
    bucket_group.add_argument(
        "--buckets",
        action="store_true",
        help="Show bucket classification summary (state, redundant, drift, discovery)",
    )
    bucket_group.add_argument(
        "--by-task",
        action="store_true",
        help="Group output by task markers (use with --buckets for per-task breakdown)",
    )

    # ========================================================================
    # best-practices command (promoted from export best-practices)
    # ========================================================================
    bp_parser = subparsers.add_parser(
        "best-practices",
        help="Export MCP best practices in various formats",
        description="""
Export MCP best practices for AI consumption or documentation.

The best practices are curated patterns for optimizing MCP tool usage,
based on analysis from the Anthropic Engineering Blog and real-world
session data. These patterns can help reduce token usage by up to 98%.

Output formats:
  json      Structured JSON array (default)
  yaml      YAML with practices wrapper
  markdown  Combined document (AGENTS.md-style, includes full content)

Examples:
  # Export all practices as JSON (default)
  token-audit best-practices

  # Export as markdown for AGENTS.md inclusion
  token-audit best-practices --format markdown

  # Export only high-severity practices
  token-audit best-practices --severity high

  # Export security category to file
  token-audit best-practices --category security -o security-practices.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    bp_parser.add_argument(
        "--format",
        "-f",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format (default: json)",
    )

    bp_parser.add_argument(
        "--category",
        "-c",
        choices=["efficiency", "security", "design", "operations"],
        help="Filter by category",
    )

    bp_parser.add_argument(
        "--severity",
        "-s",
        choices=["high", "medium", "low"],
        help="Filter by severity",
    )

    bp_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file (default: stdout)",
    )

    # ========================================================================
    # export command (v1.0.3 - task-243)
    # ========================================================================
    export_parser = subparsers.add_parser(
        "export",
        help="Export session data in various formats",
        description="""
Export session data for external analysis or backup.

Matches TUI export functionality with intuitive subcommands.

Subcommands:
  csv   Export sessions as CSV (spreadsheet-compatible)
  json  Export sessions as JSON (structured data)
  ai    Export AI analysis prompt (LLM-ready markdown)

Examples:
  # Export all sessions to CSV
  token-audit export csv

  # Export Claude Code sessions to JSON file
  token-audit export json --platform claude-code -o claude-sessions.json

  # Generate AI analysis prompt with pinned focus
  token-audit export ai --pinned-focus
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    export_subparsers = export_parser.add_subparsers(
        title="export formats",
        description="Available export formats",
        dest="export_format",
        help="Export format",
    )

    # export csv subcommand
    export_csv_parser = export_subparsers.add_parser(
        "csv",
        help="Export sessions as CSV",
        description="Export session data as CSV file.",
    )
    export_csv_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: ~/.token-audit/exports/)",
    )
    export_csv_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter by platform",
    )

    # export json subcommand
    export_json_parser = export_subparsers.add_parser(
        "json",
        help="Export sessions as JSON",
        description="Export session data as JSON file.",
    )
    export_json_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: ~/.token-audit/exports/)",
    )
    export_json_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter by platform",
    )

    # export ai subcommand
    export_ai_parser = export_subparsers.add_parser(
        "ai",
        help="Export AI analysis prompt",
        description="Generate AI-optimized markdown for LLM analysis.",
    )
    export_ai_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path (default: stdout)",
    )
    export_ai_parser.add_argument(
        "--pinned-focus",
        action="store_true",
        help="Add dedicated analysis section for pinned servers",
    )
    export_ai_parser.add_argument(
        "--full-mcp-breakdown",
        action="store_true",
        help="Include per-server and per-tool breakdown",
    )
    export_ai_parser.add_argument(
        "--pinned-servers",
        action="append",
        metavar="SERVER",
        help="Servers to analyze as pinned (can use multiple times)",
    )
    export_ai_parser.add_argument(
        "--include-buckets",
        action="store_true",
        help="Include bucket classification (state, redundant, drift, discovery) in export (v1.0.4)",
    )

    # ========================================================================
    # (removed: smells command - merged into report --smells)
    # ========================================================================

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

Without the Gemma tokenizer, token-audit falls back to tiktoken (cl100k_base)
which provides ~95% accuracy for Gemini sessions.

Commands:
  token-audit tokenizer setup      # Interactive setup wizard (v1.0.0)
  token-audit tokenizer status     # Check tokenizer installation
  token-audit tokenizer download   # Download Gemma tokenizer
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    tokenizer_parser.add_argument(
        "--interactive",
        action="store_true",
        help="[DEPRECATED] Use 'token-audit tokenizer setup' instead",
    )

    tokenizer_subparsers = tokenizer_parser.add_subparsers(
        title="tokenizer commands",
        dest="tokenizer_command",
        help="Tokenizer management commands",
    )

    # tokenizer setup (v1.0.0 - task-224.9)
    tokenizer_subparsers.add_parser(
        "setup",
        help="Interactive tokenizer setup wizard",
        description="""
Interactive setup wizard for configuring tokenizers.

Checks current tokenizer status and guides you through downloading
the Gemma tokenizer for 100% accurate Gemini CLI token counts.

This is the recommended way to set up tokenizers for new users.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
  token-audit tokenizer download

  # Download specific release
  token-audit tokenizer download --release v0.4.0

  # Download from HuggingFace (requires account)
  token-audit tokenizer download --source huggingface --token hf_xxx

The tokenizer will be saved to ~/.cache/token-audit/tokenizer.model
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
    # ui command (v0.7.0 - task-105.1, v1.0.0 - dashboard, hotkeys, command palette)
    # ========================================================================
    ui_parser = subparsers.add_parser(
        "ui",
        help="Interactive session browser with Dashboard, Live, and Recommendations views",
        description="""
Launch the interactive session browser TUI.

v1.0.0 now opens to the Dashboard view by default, showing a quick overview
of today's sessions, weekly trends, and recommendations.

Views (use number keys to switch):
  1          Dashboard - Overview and quick stats
  2          Sessions - Full session list
  3          Recommendations - Optimization suggestions
  4          Live - Real-time session monitoring

Keyboard shortcuts:
  q          Quit
  j/k        Navigate up/down
  ENTER      View session details
  :          Command palette (quick navigation)
  /          Search sessions
  f          Cycle platform filter
  s          Cycle sort order
  r          Refresh
  a          Export to AI
  ESC        Back / Cancel
  ?          Help
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    ui_parser.add_argument(
        "--theme",
        choices=["auto", "dark", "light", "mocha", "latte", "hc-dark", "hc-light"],
        default="auto",
        help="Color theme (default: auto-detect)",
    )

    ui_parser.add_argument(
        "--compact",
        action="store_true",
        help="Use compact display mode for narrow terminals",
    )

    ui_parser.add_argument(
        "--view",
        choices=["dashboard", "sessions", "recommendations", "live", "config"],
        default="dashboard",
        help="Initial view to display (default: dashboard)",
    )

    ui_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose key/event logging for debugging TUI issues",
    )

    ui_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Pre-filter to specific platform on startup",
    )

    # ========================================================================
    # validate command (v0.9.0 - task-107.6)
    # ========================================================================
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate session files against JSON Schema",
        description="""
Validate token-audit session files against the official JSON Schema.

This command checks that session files conform to the schema specification,
helping identify malformed or corrupted session data.

Examples:
  # Validate a single session file
  token-audit validate ~/.token-audit/sessions/claude-code/2025-12-14/session.json

  # Show schema file path
  token-audit validate --schema-only

  # Validate with verbose output
  token-audit validate session.json --verbose
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    validate_parser.add_argument(
        "session_file",
        type=Path,
        nargs="?",
        help="Session file to validate (JSON format)",
    )

    validate_parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Print schema file path and exit (no validation)",
    )

    validate_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation errors",
    )

    # ========================================================================
    # pin command (v1.0.0 - task-152)
    # ========================================================================
    pin_parser = subparsers.add_parser(
        "pin",
        help="Manage pinned MCP servers for focused analysis",
        description="""
Manage pinned MCP servers for focused analysis.

Pinned servers receive prioritized tracking and recommendations.
Use this to focus on MCP servers you're developing or actively monitoring.

Examples:
  # Pin a server
  token-audit pin my-custom-server

  # Pin with a note
  token-audit pin my-custom-server --notes "Local dev server"

  # List all pinned servers
  token-audit pin --list

  # Auto-detect pinnable servers from config
  token-audit pin --auto

  # Remove a pinned server
  token-audit pin --remove my-custom-server

  # Clear all pinned servers
  token-audit pin --clear
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    pin_parser.add_argument(
        "server_name",
        type=str,
        nargs="?",
        default=None,
        help="Server name to pin (optional if using --list, --auto, or --clear)",
    )

    pin_parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Optional notes about the pinned server",
    )

    pin_parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all pinned servers",
    )

    pin_parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-detect and suggest servers to pin from MCP config",
    )

    pin_parser.add_argument(
        "--remove",
        "-r",
        type=str,
        metavar="SERVER",
        help="Remove a pinned server",
    )

    pin_parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all pinned servers",
    )

    pin_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format (for --list and --auto)",
    )

    # ========================================================================
    # sessions command (v1.0.0 - task-224.7)
    # ========================================================================
    sessions_parser = subparsers.add_parser(
        "sessions",
        help="List and manage collected sessions",
        description="""
List and manage collected MCP session data.

Browse recent sessions, view session details, or delete old data.
For interactive browsing, use 'token-audit ui' instead.

Examples:
  # List recent sessions (default: 10)
  token-audit sessions list

  # List more sessions with details
  token-audit sessions list -n 20 --verbose

  # List all sessions as JSON
  token-audit sessions list --all --json

  # Show session details
  token-audit sessions show <session-id>

  # Delete old sessions
  token-audit sessions delete --older-than 30d

  # Delete specific session
  token-audit sessions delete <session-id>
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sessions_subparsers = sessions_parser.add_subparsers(
        title="session commands",
        description="Available session commands",
        dest="sessions_command",
        help="Session command to execute",
    )

    # sessions list subcommand
    sessions_list_parser = sessions_subparsers.add_parser(
        "list",
        help="List recent sessions",
        description="List collected sessions with optional filtering.",
    )
    sessions_list_parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="Number of sessions to show (default: 10)",
    )
    sessions_list_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all sessions (ignore count limit)",
    )
    sessions_list_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter by platform",
    )
    sessions_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    sessions_list_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed session info (tokens, cost, duration)",
    )

    # sessions show subcommand
    sessions_show_parser = sessions_subparsers.add_parser(
        "show",
        help="Show session details",
        description="Display detailed information about a specific session.",
    )
    sessions_show_parser.add_argument(
        "session_id",
        type=str,
        help="Session ID to display (can be partial match)",
    )
    sessions_show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    # sessions delete subcommand
    sessions_delete_parser = sessions_subparsers.add_parser(
        "delete",
        help="Delete sessions",
        description="Delete specific sessions or sessions older than a threshold.",
    )
    sessions_delete_parser.add_argument(
        "session_id",
        type=str,
        nargs="?",
        default=None,
        help="Session ID to delete (optional if using --older-than)",
    )
    sessions_delete_parser.add_argument(
        "--older-than",
        type=str,
        metavar="DURATION",
        help="Delete sessions older than duration (e.g., 7d, 30d, 1w)",
    )
    sessions_delete_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Only delete sessions from this platform",
    )
    sessions_delete_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    sessions_delete_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )

    # ========================================================================
    # daily command (v1.0.0 - task-226.1)
    # ========================================================================
    daily_parser = subparsers.add_parser(
        "daily",
        help="Show daily token usage summary",
        description="""
Display token usage aggregated by day.

Shows sessions, tokens, and costs for each day in the specified range.
By default shows the last 7 days with data.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    daily_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter to specific platform",
    )
    daily_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to show (default: 7)",
    )
    daily_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    daily_parser.add_argument(
        "--instances",
        action="store_true",
        help="Group by project/instance",
    )
    daily_parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Show per-model breakdown",
    )

    # ========================================================================
    # weekly command (v1.0.0 - task-226.2)
    # ========================================================================
    weekly_parser = subparsers.add_parser(
        "weekly",
        help="Show weekly token usage summary",
        description="""
Display token usage aggregated by week.

Shows sessions, tokens, and costs for each week in the specified range.
By default shows the last 4 weeks with data.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    weekly_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter to specific platform",
    )
    weekly_parser.add_argument(
        "--weeks",
        type=int,
        default=4,
        help="Number of weeks to show (default: 4)",
    )
    weekly_parser.add_argument(
        "--start-of-week",
        choices=["monday", "sunday"],
        default="monday",
        help="Week start day (default: monday/ISO 8601)",
    )
    weekly_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    weekly_parser.add_argument(
        "--instances",
        action="store_true",
        help="Group by project/instance",
    )
    weekly_parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Show per-model breakdown",
    )

    # ========================================================================
    # monthly command (v1.0.0 - task-226.3)
    # ========================================================================
    monthly_parser = subparsers.add_parser(
        "monthly",
        help="Show monthly token usage summary",
        description="""
Display token usage aggregated by month.

Shows sessions, tokens, and costs for each month in the specified range.
By default shows the last 3 months with data.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    monthly_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        help="Filter to specific platform",
    )
    monthly_parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Number of months to show (default: 3)",
    )
    monthly_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    monthly_parser.add_argument(
        "--instances",
        action="store_true",
        help="Group by project/instance",
    )
    monthly_parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Show per-model breakdown",
    )

    # ========================================================================
    # bucket command (v1.0.4 - task-247.4)
    # ========================================================================
    bucket_parser = subparsers.add_parser(
        "bucket",
        help="Analyze token distribution across efficiency buckets",
        description="""
Analyze MCP tool calls by efficiency bucket classification.

Buckets (in priority order):
  1. Redundant outputs  - Duplicate tool calls (same content_hash)
  2. Tool discovery     - Schema/introspection calls (*_introspect*, *_schema*)
  3. State serialization - Large content payloads (*_get_*, *_list_*, >5K tokens)
  4. Conversation drift - Residual (reasoning, retries, errors)

Use this to diagnose WHERE token bloat comes from in AI agent workflows.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze latest session
  token-audit bucket

  # Analyze specific session file
  token-audit bucket --session ~/.token-audit/sessions/claude-code/2024-01-15/project-2024-01-15T10-30-00.json

  # Output as JSON
  token-audit bucket --format json

  # Output as CSV
  token-audit bucket --format csv --output buckets.csv
        """,
    )
    bucket_parser.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session file or directory to analyze (default: latest session)",
    )
    bucket_parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    bucket_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    bucket_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Filter to specific platform when finding latest session",
    )
    bucket_parser.add_argument(
        "--by-task",
        action="store_true",
        help="Show bucket breakdown per task (requires task markers)",
    )

    # ========================================================================
    # task command (v1.0.4 - task-247.7)
    # ========================================================================
    task_parser = subparsers.add_parser(
        "task",
        help="Manage task markers for per-task bucket analysis",
        description="""
Manage task markers to group tool calls into logical work units.

Task markers create boundaries for per-task bucket analysis, helping you
understand token distribution across different activities in a session.

Commands:
  start    Begin a new task (auto-ends previous if active)
  end      End the current task
  list     List all tasks in a session
  show     Show detailed task info with bucket breakdown
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a new task
  token-audit task start "Implement user login"

  # End current task
  token-audit task end

  # List tasks in current session
  token-audit task list

  # Show task details with buckets
  token-audit task show "Implement user login"

  # Work with specific session
  token-audit task list --session my-session-id
        """,
    )

    task_subparsers = task_parser.add_subparsers(
        title="task commands",
        description="Available task management commands",
        dest="task_command",
        help="Task command to execute",
    )

    # task start subcommand
    task_start_parser = task_subparsers.add_parser(
        "start",
        help="Start a new task",
        description="Create a task start marker. Auto-ends previous task if active.",
    )
    task_start_parser.add_argument(
        "name",
        type=str,
        help="Task name (e.g., 'Implement user login')",
    )
    task_start_parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID (default: latest/active session)",
    )
    task_start_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Platform for session detection",
    )

    # task end subcommand
    task_end_parser = task_subparsers.add_parser(
        "end",
        help="End the current task",
        description="Create a task end marker for the active task.",
    )
    task_end_parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID (default: latest/active session)",
    )
    task_end_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Platform for session detection",
    )

    # task list subcommand
    task_list_parser = task_subparsers.add_parser(
        "list",
        help="List tasks in a session",
        description="Show all tasks with token usage and duration.",
    )
    task_list_parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID (default: latest session)",
    )
    task_list_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Platform for session detection",
    )
    task_list_parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )

    # task show subcommand
    task_show_parser = task_subparsers.add_parser(
        "show",
        help="Show task details with bucket breakdown",
        description="Display detailed task info including per-bucket analysis.",
    )
    task_show_parser.add_argument(
        "name",
        type=str,
        help="Task name to show",
    )
    task_show_parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID (default: latest session)",
    )
    task_show_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Platform for session detection",
    )
    task_show_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # ========================================================================
    # compare command (v1.0.4 - task-247.16)
    # ========================================================================
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare bucket classification across multiple sessions",
        description="""
Compare bucket classification across multiple sessions.

Shows bucket distribution (State, Redundant, Drift, Discovery) for each session
with an AVERAGE row for cross-session analysis.

Use this to identify trends in token efficiency across work sessions.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare specific session files
  token-audit compare session1.json session2.json session3.json

  # Compare last 5 sessions
  token-audit compare --latest 5

  # Compare last 10 sessions for Claude Code
  token-audit compare --latest 10 --platform claude-code

  # Export comparison as JSON
  token-audit compare --latest 5 --format json --output comparison.json
        """,
    )
    compare_parser.add_argument(
        "sessions",
        nargs="*",
        type=Path,
        help="Session files to compare",
    )
    compare_parser.add_argument(
        "--latest",
        type=int,
        metavar="N",
        help="Compare the last N sessions (mutually exclusive with positional sessions)",
    )
    compare_parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    compare_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    compare_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex-cli", "gemini-cli"],
        default=None,
        help="Filter to specific platform when using --latest",
    )

    # Parse arguments
    args = parser.parse_args()

    # Execute command
    if args.command == "collect":
        return cmd_collect(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "tokenizer":
        return cmd_tokenizer(args)
    elif args.command == "ui":
        return cmd_ui(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "pin":
        return cmd_pin(args)
    elif args.command == "sessions":
        return cmd_sessions(args)
    elif args.command == "best-practices":
        return cmd_best_practices(args)
    elif args.command == "daily":
        return cmd_daily(args)
    elif args.command == "weekly":
        return cmd_weekly(args)
    elif args.command == "monthly":
        return cmd_monthly(args)
    elif args.command == "export":
        return cmd_export_new(args)
    elif args.command == "bucket":
        return cmd_bucket(args)
    elif args.command == "task":
        return cmd_task(args)
    elif args.command == "compare":
        return cmd_compare(args)
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
    marker_file = Path.home() / ".token-audit" / ".initialized"

    # If marker exists, not first run
    if marker_file.exists():
        return True

    # First run - offer setup
    print()
    print("=" * 70)
    print("  Welcome to Token Audit!")
    print("=" * 70)
    print()
    print("  Looks like this is your first time running token-audit.")
    print()
    print("  token-audit tracks MCP tool usage and token costs across all platforms:")
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
    print("  │  Command: token-audit tokenizer download                         │")
    print("  │                                                                 │")
    print("  │  This is optional. Without it, tracking still works — you'll   │")
    print("  │  just see estimates instead of exact counts for Gemini CLI.    │")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()
    print("  📚 Docs: https://github.com/littlebearapps/token-audit#readme")
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
        # Run tokenizer setup wizard directly (v1.0.0 - task-224.8)
        _cmd_tokenizer_interactive()
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
        # v1.0.0 - task-224.8: Reference new subcommand interface
        print("  No problem! You can run 'token-audit tokenizer setup' anytime.")
        print()
        print("  Gemini CLI users: 'token-audit tokenizer download' for 100% accuracy")
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

    # Detect platform (keep hyphen format for adapter selection)
    # Note: Storage normalization (hyphen→underscore) happens inside adapters
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
                print("      For 100% accuracy: token-audit tokenizer download")
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

        # Register this session as active for task command resolution (#117)
        from .storage import StreamingStorage

        _streaming_storage = StreamingStorage()
        try:
            _streaming_storage.create_active_session(tracker.session_id)
            start_event = {
                "type": "session_start",
                "session_id": tracker.session_id,
                "platform": platform,
                "project": project,
                "timestamp": start_time.isoformat(),
            }
            _streaming_storage.append_event(tracker.session_id, start_event)
        except FileExistsError:
            pass  # Session already registered (restart without cleanup)

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
                    print("\n[token-audit] No data tracked - session not saved.")

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


# ============================================================================
# Report Sub-handlers (v1.0.0 CLI consolidation)
# ============================================================================


def _cmd_report_smells(args: argparse.Namespace) -> int:
    """Handle 'report --smells' - cross-session smell aggregation.

    Merged from standalone 'smells' command in v1.0.0.
    """
    from .smell_aggregator import SmellAggregator

    aggregator = SmellAggregator()
    result = aggregator.aggregate(
        days=args.days,
        platform=getattr(args, "platform", None),
        project=getattr(args, "project", None),
    )

    # Filter by minimum frequency
    min_freq = getattr(args, "min_frequency", 0.0)
    if min_freq > 0:
        result.aggregated_smells = [
            s for s in result.aggregated_smells if s.frequency_percent >= min_freq
        ]

    # Output as text (the standard smells output format)
    output_path = getattr(args, "output", None)
    return _output_smells_text(result, output_path)


def _cmd_report_buckets(args: argparse.Namespace) -> int:
    """Handle 'report --buckets' - bucket classification summary.

    Added in v1.0.4 (task-247.17).

    Supports:
    - --buckets: Show bucket classification summary
    - --buckets --by-task: Show per-task bucket breakdown
    """
    from .buckets import BucketClassifier
    from .session_manager import SessionManager
    from .storage import get_latest_session
    from .tasks import TaskManager

    session_path = args.session_dir
    output_path = getattr(args, "output", None)
    by_task = getattr(args, "by_task", False)

    # Find session to analyze
    if not session_path.exists():
        # Find latest session
        latest = get_latest_session()
        if latest is None:
            print("Error: No sessions found. Run 'token-audit collect' first.")
            return 1
        session_path = latest
        print(f"Analyzing latest session: {session_path.name}")

    # If it's a directory, find the session file
    if session_path.is_dir():
        summary_path = session_path / "summary.json"
        if summary_path.exists():
            session_path = summary_path
        else:
            json_files = list(session_path.glob("*.json"))
            if json_files:
                session_path = max(json_files, key=lambda p: p.stat().st_mtime)
            else:
                print(f"Error: No session files found in: {args.session_dir}")
                return 1

    # Load session
    manager = SessionManager()
    session = manager.load_session(session_path)

    if not session:
        print(f"Error: Failed to load session from: {session_path}")
        return 1

    # Check for --by-task flag
    if by_task:
        task_manager = TaskManager()
        summaries = task_manager.get_tasks(session)

        if not summaries:
            print("No task markers found in session.")
            print("Use 'token-audit task start <name>' to create task markers.")
            print()
            print("Showing overall bucket analysis instead:")
            print()
            # Fall back to overall analysis
            classifier = BucketClassifier()
            results = classifier.classify_session(session)
            total_tokens = sum(r.tokens for r in results)
            total_calls = sum(r.call_count for r in results)
            return _bucket_output_table(results, total_tokens, total_calls, output_path)

        # Output per-task breakdown (reuse existing function)
        return _bucket_by_task_table(summaries, output_path)

    # Standard bucket analysis
    classifier = BucketClassifier()
    results = classifier.classify_session(session)
    total_tokens = sum(r.tokens for r in results)
    total_calls = sum(r.call_count for r in results)

    return _bucket_output_table(results, total_tokens, total_calls, output_path)


def _cmd_report_ai(args: argparse.Namespace) -> int:
    """Handle 'report --format ai' - export session for AI analysis.

    Merged from 'export ai-prompt' command in v1.0.0.
    """
    from .storage import get_latest_session, load_session_file

    # v1.0.0: Use session_dir as the session path
    session_path = args.session_dir
    output_path = getattr(args, "output", None)

    # Options for AI analysis
    pinned_focus = getattr(args, "pinned_focus", False)
    full_mcp_breakdown = getattr(args, "full_mcp_breakdown", False)
    pinned_servers = getattr(args, "pinned_servers", None) or []

    # Handle "latest" session (if path doesn't exist or is a directory with no sessions)
    if not session_path.exists():
        # Find latest session
        session_path = get_latest_session()
        if session_path is None:
            print("Error: No sessions found. Run 'token-audit collect' first.")
            return 1

    # If it's a directory, find the latest session in it
    if session_path.is_dir():
        # Try to find summary.json (v1.0.0 format) or latest JSON file
        summary_path = session_path / "summary.json"
        if summary_path.exists():
            session_path = summary_path
        else:
            # Find latest JSON file
            json_files = list(session_path.glob("*.json"))
            if json_files:
                session_path = max(json_files, key=lambda p: p.stat().st_mtime)
            else:
                # Try subdirectories
                subdirs = [d for d in session_path.iterdir() if d.is_dir()]
                if subdirs:
                    latest_subdir = max(subdirs, key=lambda d: d.stat().st_mtime)
                    session_path = latest_subdir / "summary.json"
                    if not session_path.exists():
                        print(f"Error: No valid session found in: {args.session_dir}")
                        return 1
                else:
                    print(f"Error: No sessions found in: {args.session_dir}")
                    return 1

    # Load session
    session_data = load_session_file(session_path)
    if session_data is None:
        print(f"Error: Could not load session file: {session_path}")
        return 1

    # Merge CLI pinned servers with session pinned servers
    session_pinned = session_data.get("session", {}).get("pinned_servers", [])
    all_pinned = list(set(pinned_servers + session_pinned))

    # Generate markdown output (AI format is always markdown)
    output = generate_ai_prompt_markdown(
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


def cmd_export_new(args: argparse.Namespace) -> int:
    """Execute export command.

    Provides intuitive export subcommands matching TUI functionality:
    - csv: Export sessions as CSV
    - json: Export sessions as JSON
    - ai: Generate AI analysis prompt

    v1.0.3: New CLI command (task-243)
    """
    export_format = getattr(args, "export_format", None)

    if not export_format:
        print("Error: export subcommand required (csv, json, or ai)")
        print("Usage: token-audit export {csv,json,ai} [options]")
        return 1

    if export_format == "ai":
        # Delegate to AI export handler
        return _cmd_export_ai(args)
    elif export_format in ("csv", "json"):
        # Delegate to CSV/JSON export handler
        return _cmd_export_data(args)
    else:
        print(f"Error: Unknown export format: {export_format}")
        return 1


def _cmd_export_data(args: argparse.Namespace) -> int:
    """Handle 'export csv' and 'export json' commands.

    Loads all sessions and exports to specified format.
    """
    from .session_manager import SessionManager
    from .storage import StorageManager

    storage = StorageManager()
    manager = SessionManager()

    # Load all sessions
    sessions = []
    # base_dir is ~/.token-audit/sessions/ (the sessions directory)
    sessions_dir = storage.base_dir

    if not sessions_dir.exists():
        print(f"Error: Sessions directory not found: {sessions_dir}")
        print("Tip: Run 'token-audit collect' first to gather session data.")
        return 1

    # Check for platform filter
    platform_filter = getattr(args, "platform", None)

    # Platform directories structure: sessions/<platform>/<date>/<session>.json
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for platform_dir in sessions_dir.iterdir():
        if not platform_dir.is_dir():
            continue

        # Skip if filtering and doesn't match
        if platform_filter:
            platform_internal = platform_filter.replace("-", "_")
            if platform_dir.name.replace("-", "_") != platform_internal:
                continue

        # Look in date subdirectories
        for date_dir in platform_dir.iterdir():
            if date_dir.is_dir() and date_pattern.match(date_dir.name):
                for json_file in date_dir.glob("*.json"):
                    if json_file.name != "summary.json" and not json_file.name.startswith("."):
                        session = manager.load_session(json_file)
                        if session:
                            sessions.append(session)

    if not sessions:
        if platform_filter:
            print(f"Error: No sessions found for platform: {platform_filter}")
        else:
            print("Error: No sessions found.")
        print("Tip: Run 'token-audit collect' to gather session data.")
        return 1

    print(f"Loaded {len(sessions)} session(s)")

    # Generate output based on format
    export_format = args.export_format
    output_path = getattr(args, "output", None)

    if export_format == "csv":
        # Create mock args for generate_csv_report
        mock_args = argparse.Namespace(output=output_path)
        return generate_csv_report(sessions, mock_args)
    elif export_format == "json":
        # Create mock args for generate_json_report
        mock_args = argparse.Namespace(output=output_path)
        return generate_json_report(sessions, mock_args)

    return 1


def _cmd_export_ai(args: argparse.Namespace) -> int:
    """Handle 'export ai' command.

    Generates AI analysis prompt for latest session.
    """
    from .storage import get_latest_session, load_session_file

    output_path = getattr(args, "output", None)
    pinned_focus = getattr(args, "pinned_focus", False)
    full_mcp_breakdown = getattr(args, "full_mcp_breakdown", False)
    pinned_servers = getattr(args, "pinned_servers", None) or []
    include_buckets = getattr(args, "include_buckets", False)

    # Get latest session
    session_path = get_latest_session()
    if session_path is None:
        print("Error: No sessions found. Run 'token-audit collect' first.")
        return 1

    # Load session data
    session_data = load_session_file(session_path)
    if session_data is None:
        print(f"Error: Could not load session file: {session_path}")
        return 1

    # Merge CLI pinned servers with session pinned servers
    session_pinned = session_data.get("session", {}).get("pinned_servers", [])
    all_pinned = list(set(pinned_servers + session_pinned))

    # Generate markdown output
    output = generate_ai_prompt_markdown(
        session_data,
        session_path,
        pinned_focus=pinned_focus,
        full_mcp_breakdown=full_mcp_breakdown,
        pinned_servers=all_pinned,
        include_buckets=include_buckets,
    )

    # Write output
    if output_path:
        output_path.write_text(output)
        path_str = str(output_path).replace(str(Path.home()), "~")
        print(f"Exported AI analysis prompt to: {path_str}")
    else:
        print(output)

    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Execute report command.

    Supports multiple modes:
    - Standard reports: json, markdown, csv formats
    - AI analysis: --format ai (formerly export ai-prompt)
    - Smell analysis: --smells (formerly smells command)
    - Bucket analysis: --buckets (v1.0.4 - task-247.17)
    """
    # v1.0.0: Check for --smells flag first (merged from smells command)
    if getattr(args, "smells", False):
        return _cmd_report_smells(args)

    # v1.0.4: Check for --buckets flag (task-247.17)
    if getattr(args, "buckets", False):
        return _cmd_report_buckets(args)

    # v1.0.0: Check for --format ai (merged from export ai-prompt)
    if args.format == "ai":
        return _cmd_report_ai(args)

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
        # Multiple sessions (parent directory or JSON files)
        print(f"Loading sessions from: {session_dir}")
        sessions = []

        # Check if this is a platform directory (contains date-formatted subdirectories)
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        # Try loading from subdirectories
        session_dirs = [d for d in session_dir.iterdir() if d.is_dir()]
        for s_dir in session_dirs:
            # Check if it's a date directory (platform → date → sessions structure)
            if date_pattern.match(s_dir.name):
                # Look for session JSON files inside date directory
                for json_file in s_dir.glob("*.json"):
                    if json_file.name != "summary.json" and not json_file.name.startswith("."):
                        session = manager.load_session(json_file)
                        if session:
                            sessions.append(session)
            else:
                # Try loading as v1.0.0 format session directory
                session = manager.load_session(s_dir)
                if session:
                    sessions.append(session)

        # Also try direct JSON files in the current directory (v1.0.4 format)
        for json_file in session_dir.glob("*.json"):
            if json_file.name != "summary.json" and not json_file.name.startswith("."):
                session = manager.load_session(json_file)
                if session:
                    sessions.append(session)

        if not sessions:
            print("Error: No valid sessions found in directory")
            print(f"  Searched: {session_dir}")
            print("  Tip: Specify a session file directly or check the path")
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
        platform=normalize_platform(args.platform),
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


def _init_install_gemma_tokenizer() -> tuple[bool, str]:
    """Attempt to install Gemma tokenizer from GitHub Releases."""
    from .token_estimator import download_gemma_from_github

    print()
    print("    Downloading Gemma tokenizer from GitHub Releases...")
    return download_gemma_from_github()


def cmd_tokenizer(args: argparse.Namespace) -> int:
    """Execute tokenizer command."""
    # v1.0.0: Check for --interactive flag (deprecated alias for setup)
    if getattr(args, "interactive", False):
        print(
            "Warning: --interactive is deprecated. " "Use 'token-audit tokenizer setup' instead.",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        return _cmd_tokenizer_interactive()

    tokenizer_cmd = getattr(args, "tokenizer_command", None)

    if tokenizer_cmd == "setup":
        # v1.0.0 - task-224.9: New setup subcommand
        return _cmd_tokenizer_interactive()
    elif tokenizer_cmd == "status":
        return cmd_tokenizer_status(args)
    elif tokenizer_cmd == "download":
        return cmd_tokenizer_download(args)
    else:
        # No subcommand - show help
        print("Usage: token-audit tokenizer <command>")
        print()
        print("Commands:")
        print("  setup        Interactive setup wizard (recommended)")
        print("  status       Check tokenizer installation status")
        print("  download     Download the Gemma tokenizer (from GitHub)")
        print()
        print("Run 'token-audit tokenizer <command> --help' for more information.")
        return 0


def _cmd_tokenizer_interactive() -> int:
    """Interactive tokenizer setup wizard (merged from init command in v1.0.0).

    Checks tokenizer status and offers to download if not installed.
    """
    from .token_estimator import check_gemma_tokenizer_status

    print()
    print("=" * 60)
    print("  token-audit Tokenizer Setup")
    print("=" * 60)
    print()

    # Check current status
    print("[1/2] Checking tokenizer status...")
    print()

    gemma_status = check_gemma_tokenizer_status()

    if gemma_status["installed"]:
        print("  ✓ Gemma tokenizer is already installed")
        print(f"    Location: {gemma_status['location']}")
        print(f"    Source: {gemma_status['source']}")
        print()
        print("  Your Gemini CLI sessions will have 100% accurate token counts.")
        print()
        return 0

    # Not installed - offer to download
    print("  ○ Gemma tokenizer NOT installed")
    print()
    print("  The Gemma tokenizer provides 100% accurate token counts for")
    print("  Gemini CLI sessions. Without it, token-audit uses tiktoken")
    print("  (cl100k_base) which provides ~95-99% accuracy.")
    print()
    print("  Download size: ~4MB (from GitHub, no account needed)")
    print()

    # Prompt user
    print("[2/2] Download tokenizer?")
    print()
    try:
        response = input("  Download Gemma tokenizer now? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        print("  Cancelled.")
        return 0

    if response in ("", "y", "yes"):
        print()
        print("  Downloading...")
        success, message = _init_install_gemma_tokenizer()
        if success:
            print(f"  ✓ {message}")
            print()
            print("  Your Gemini CLI sessions will now have 100% accurate token counts!")
        else:
            print(f"  ✗ {message}")
            print()
            print("  You can try again later with: token-audit tokenizer download")
            return 1
    else:
        print()
        print("  Skipped. You can download later with: token-audit tokenizer download")
        print("  (Tracking works now with ~95-99% accuracy)")

    print()
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
        print("  token-audit tokenizer download")

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
            print("• Download manually: https://github.com/littlebearapps/token-audit/releases")
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
    elif export_format == "best-practices":
        return cmd_export_best_practices(args)
    else:
        print("Usage: token-audit export <format>")
        print()
        print("Available formats:")
        print("  ai-prompt       Export session data formatted for AI analysis")
        print("  best-practices  Export MCP best practices (JSON/YAML/Markdown)")
        print()
        print("Run 'token-audit export <format> --help' for more information.")
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
            print("Error: No sessions found. Run 'token-audit collect' first.")
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


def cmd_export_best_practices(args: argparse.Namespace) -> int:
    """Export MCP best practices in various formats (v1.0.0 - task-196).

    Supports JSON, YAML, and Markdown output formats with optional
    filtering by category and severity.
    """
    from .guidance import BestPracticesExporter, BestPracticesLoader

    # Get arguments
    output_format = getattr(args, "format", "json")
    category_filter = getattr(args, "category", None)
    severity_filter = getattr(args, "severity", None)
    output_path = getattr(args, "output", None)

    # Load practices
    loader = BestPracticesLoader()
    exporter = BestPracticesExporter()

    practices = loader.load_all()

    if not practices:
        print("Error: No best practices found. Check installation.")
        return 1

    # Apply filters
    original_count = len(practices)
    if category_filter:
        practices = [p for p in practices if p.category == category_filter]
    if severity_filter:
        practices = [p for p in practices if p.severity == severity_filter]

    # Generate output
    if output_format == "json":
        output = exporter.to_json(practices)
    elif output_format == "yaml":
        output = exporter.to_yaml(practices)
    else:  # markdown
        output = exporter.to_markdown(practices)

    # Write output
    if output_path:
        output_path.write_text(output)
        filter_msg = ""
        if category_filter or severity_filter:
            filter_msg = f" (filtered from {original_count})"
        print(f"Exported {len(practices)} practices{filter_msg} to {output_path}")
    else:
        print(output)

    return 0


def cmd_best_practices(args: argparse.Namespace) -> int:
    """Top-level best-practices command (v1.0.0 CLI consolidation).

    Promoted from 'export best-practices' to top-level command.
    Delegates to the existing implementation.
    """
    return cmd_export_best_practices(args)


def generate_ai_prompt_markdown(
    session_data: Dict[str, Any],
    session_path: Path,
    *,
    pinned_focus: bool = False,
    full_mcp_breakdown: bool = False,
    pinned_servers: Optional[List[str]] = None,
    include_buckets: bool = False,
) -> str:
    """Generate AI-optimized markdown prompt from session data.

    Args:
        session_data: Parsed session JSON data
        session_path: Path to the session file
        pinned_focus: Add dedicated analysis section for pinned servers (v0.8.0)
        full_mcp_breakdown: Include per-server and per-tool breakdown for ALL servers (v0.8.0)
        pinned_servers: List of servers to analyze as pinned (v0.8.0)
        include_buckets: Include bucket classification data (v1.0.4 - task-247.18)
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

    # v1.0.4: Bucket Classification (task-247.18)
    if include_buckets:
        lines.extend(_generate_bucket_classification_section(session_path, session_data))

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


def _generate_bucket_classification_section(
    session_path: Path, session_data: Dict[str, Any]
) -> List[str]:
    """Generate bucket classification section for AI export (v1.0.4 - task-247.18).

    Args:
        session_path: Path to the session file
        session_data: Parsed session JSON data (for fallback context)

    Returns:
        List of markdown lines for the bucket classification section
    """
    from .buckets import BucketClassifier
    from .session_manager import SessionManager

    lines: List[str] = []

    # Load session for classification
    manager = SessionManager()
    session = manager.load_session(session_path)

    if not session:
        lines.append("## Bucket Classification")
        lines.append("")
        lines.append("*Unable to load session for bucket classification*")
        lines.append("")
        return lines

    # Classify session
    classifier = BucketClassifier()
    results = classifier.classify_session(session)

    if not results:
        lines.append("## Bucket Classification")
        lines.append("")
        lines.append("*No tool calls to classify*")
        lines.append("")
        return lines

    # Calculate totals
    total_tokens = sum(r.tokens for r in results)
    total_calls = sum(r.call_count for r in results)

    lines.append("## Bucket Classification")
    lines.append("")
    lines.append("Token usage classified into 4 efficiency buckets:")
    lines.append("")
    lines.append("| Bucket | Tokens | % | Calls | Description |")
    lines.append("|--------|--------|---|-------|-------------|")

    bucket_descriptions = {
        "state_serialization": "Large content payloads (>5K tokens, *_get_*, *_list_*)",
        "redundant": "Duplicate tool calls (same content_hash)",
        "tool_discovery": "Schema introspection (*_introspect*, *_schema*)",
        "drift": "Residual (reasoning, retries, errors)",
    }

    for result in results:
        desc = bucket_descriptions.get(result.bucket, "Unknown")
        lines.append(
            f"| {result.bucket} | {result.tokens:,} | {result.percentage:.1f}% | "
            f"{result.call_count} | {desc} |"
        )

    lines.append(f"| **TOTAL** | **{total_tokens:,}** | **100%** | **{total_calls}** | |")
    lines.append("")

    # Add decision guidance
    guidance = _generate_bucket_guidance(results)
    lines.append("### Decision Guidance")
    lines.append("")
    lines.append(guidance)
    lines.append("")

    return lines


def _generate_bucket_guidance(results: List[Any]) -> str:
    """Generate optimization guidance based on dominant bucket (v1.0.4 - task-247.18).

    Args:
        results: List of BucketResult objects from BucketClassifier

    Returns:
        String with actionable guidance based on dominant bucket percentages
    """
    if not results:
        return "No data available for guidance."

    # Sort by percentage descending to find dominant bucket
    sorted_results = sorted(results, key=lambda r: r.percentage, reverse=True)
    dominant = sorted_results[0]

    # Guidance thresholds from plan
    if dominant.bucket == "state_serialization" and dominant.percentage >= 60:
        return (
            f"**State serialization is {dominant.percentage:.0f}%** - "
            "Focus on delta-sync or pagination strategies to reduce large payload transfers."
        )
    elif dominant.bucket == "redundant" and dominant.percentage >= 30:
        return (
            f"**Redundant calls are {dominant.percentage:.0f}%** - "
            "Implement caching or request deduplication to avoid repeated identical calls."
        )
    elif dominant.bucket == "drift" and dominant.percentage >= 40:
        return (
            f"**Conversation drift is {dominant.percentage:.0f}%** - "
            "Investigate error handling, retries, and conversation flow efficiency."
        )
    elif dominant.bucket == "tool_discovery" and dominant.percentage >= 20:
        return (
            f"**Tool discovery is {dominant.percentage:.0f}%** - "
            "Consider caching introspection results or pre-loading tool schemas."
        )

    # Well-distributed case
    return (
        "Token usage is well-distributed across buckets. "
        "No single category dominates - consider holistic optimization."
    )


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
# UI Command (v0.7.0 - task-105.1, v1.0.0 - dashboard, hotkeys, command palette)
# ============================================================================


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch interactive session browser."""
    from .display.session_browser import BrowserMode, SessionBrowser

    theme = None if args.theme == "auto" else args.theme

    # Map view name to BrowserMode
    view_modes = {
        "dashboard": BrowserMode.DASHBOARD,
        "sessions": BrowserMode.LIST,
        "recommendations": BrowserMode.RECOMMENDATIONS,
        "live": BrowserMode.LIVE,
        "config": BrowserMode.BUCKET_CONFIG,
    }
    initial_mode = view_modes.get(args.view, BrowserMode.DASHBOARD)

    try:
        debug_mode = getattr(args, "debug", False)
        browser = SessionBrowser(theme=theme, debug=debug_mode)

        # Set initial view (v1.0.0)
        browser.state.mode = initial_mode

        # Set compact mode if specified (v1.0.0)
        if args.compact:
            browser.state.compact_mode = True

        # Set platform filter if specified (v1.0.3 - task-241)
        if args.platform:
            browser.state.filter_platform = normalize_platform(args.platform)

        browser.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install token-audit")
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
    lines.append("# Token Audit Report")
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
    output_path = args.output or Path("token-audit-report.csv")

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


# ============================================================================
# validate command (v0.9.0 - task-107.6)
# ============================================================================


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Validate session files against JSON Schema.

    Args:
        args: CLI arguments with session_file, schema_only, verbose

    Returns:
        0 on success, 1 on validation failure
    """
    import json

    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        print("Error: jsonschema package not installed.", file=sys.stderr)
        print("Install with: pip install jsonschema", file=sys.stderr)
        return 1

    # Schema file path - check multiple locations
    # 1. Package resources (installed or editable install)
    # 2. Development: relative to source (../../../docs/schema/)
    # 3. Fallback: same-level schema/ directory
    schema_name = "session-v1.7.0.json"
    schema_path: Optional[Path] = None

    # Try package resources first (works for both installed and editable installs)
    try:
        from importlib.resources import files

        schema_resource = files("token_audit").joinpath("schema", schema_name)
        # Check if resource exists and convert to path
        if hasattr(schema_resource, "is_file") and schema_resource.is_file():
            schema_path = Path(str(schema_resource))
        elif hasattr(schema_resource, "__fspath__"):
            candidate = Path(str(schema_resource))
            if candidate.exists():
                schema_path = candidate
    except (ImportError, TypeError, AttributeError):
        pass  # importlib.resources not available or failed

    # Fallback paths for development
    if schema_path is None or not schema_path.exists():
        possible_paths = [
            Path(__file__).parent / "schema" / schema_name,  # Package (src/token_audit/schema/)
            Path(__file__).parent.parent.parent / "docs" / "schema" / schema_name,  # Development
        ]
        schema_path = next((p for p in possible_paths if p.exists()), possible_paths[0])

    # Handle --schema-only
    if args.schema_only:
        if schema_path.exists():
            print(f"Schema file: {schema_path}")
            print("Schema version: 1.7.0")
            print(
                "Docs: https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md"
            )
            return 0
        else:
            print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
            return 1

    # Validate session_file is provided
    if not args.session_file:
        print("Error: session_file is required (or use --schema-only)", file=sys.stderr)
        return 1

    session_file: Path = args.session_file

    if not session_file.exists():
        print(f"Error: File not found: {session_file}", file=sys.stderr)
        return 1

    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
        return 1

    # Load schema
    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid schema JSON: {e}", file=sys.stderr)
        return 1

    # Load session file
    try:
        with open(session_file, encoding="utf-8") as f:
            session_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid session JSON: {e}", file=sys.stderr)
        return 1

    # Validate
    validator = jsonschema.Draft7Validator(schema)
    errors = list(validator.iter_errors(session_data))

    if not errors:
        print(f"✓ Valid: {session_file}")
        schema_version = session_data.get("_file", {}).get("schema_version", "unknown")
        print(f"  Schema version: {schema_version}")
        return 0

    # Validation failed
    print(f"✗ Invalid: {session_file}")
    print(f"  {len(errors)} validation error(s) found:")
    print()

    for i, error in enumerate(errors, 1):
        path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        print(f"  {i}. Path: {path}")
        print(f"     Error: {error.message}")
        if args.verbose and error.context:
            print(f"     Context: {error.context}")
        print()

    return 1


def cmd_pin(args: argparse.Namespace) -> int:
    """Execute pin command - manage pinned MCP servers."""
    import json

    from .pinned_config import PinnedConfigManager

    storage = PinnedConfigManager()
    use_json = getattr(args, "json", False)

    # Handle --list flag
    if getattr(args, "list", False):
        entries = storage.list()
        if use_json:
            output = {
                "pinned_servers": [e.to_dict() for e in entries],
                "total": len(entries),
            }
            print(json.dumps(output, indent=2))
        else:
            if not entries:
                print("No pinned servers.")
                print()
                print("Pin a server with: token-audit pin <server-name>")
                print("Auto-detect candidates: token-audit pin --auto")
            else:
                print(f"Pinned servers ({len(entries)}):")
                print()
                for entry in entries:
                    notes_str = f" - {entry.notes}" if entry.notes else ""
                    print(f"  • {entry.name}{notes_str}")
                    print(f"    Pinned: {entry.pinned_at[:10]}")
        return 0

    # Handle --auto flag
    if getattr(args, "auto", False):
        return _cmd_pin_auto(args, storage, use_json)

    # Handle --remove flag
    remove_name = getattr(args, "remove", None)
    if remove_name:
        if storage.unpin(remove_name):
            print(f"Unpinned: {remove_name}")
            return 0
        else:
            print(f"Server not found: {remove_name}", file=sys.stderr)
            return 1

    # Handle --clear flag
    if getattr(args, "clear", False):
        count = storage.clear()
        print(f"Cleared {count} pinned server(s).")
        return 0

    # Handle pin operation (server_name required)
    server_name = getattr(args, "server_name", None)
    if not server_name:
        print("Error: server name required", file=sys.stderr)
        print()
        print("Usage:")
        print("  token-audit pin <server-name>        Pin a server")
        print("  token-audit pin --list               List pinned servers")
        print("  token-audit pin --auto               Auto-detect candidates")
        print("  token-audit pin --remove <name>      Unpin a server")
        return 1

    notes = getattr(args, "notes", None)
    entry = storage.pin(server_name, notes=notes)

    if storage.get(server_name):
        print(f"Pinned: {entry.name}")
        if entry.notes:
            print(f"  Notes: {entry.notes}")
    else:
        print(f"Updated: {entry.name}")

    return 0


def _cmd_pin_auto(args: argparse.Namespace, storage: Any, use_json: bool) -> int:
    """Auto-detect and suggest servers to pin from MCP config."""
    import json
    from pathlib import Path

    from .config_analyzer.parsers import parse_json_config
    from .config_analyzer.pinned_servers import detect_pinned_servers

    # Find Claude Code config
    config_paths = [
        Path.home() / ".claude.json",
        Path.home() / ".config" / "claude" / "claude.json",
    ]

    config_path = None
    for path in config_paths:
        if path.exists():
            config_path = path
            break

    if not config_path:
        if use_json:
            print(json.dumps({"error": "No MCP config found", "candidates": []}))
        else:
            print("No MCP configuration found.")
            print()
            print("Expected locations:")
            for path in config_paths:
                print(f"  • {path}")
        return 1

    # Parse config and detect pinnable servers
    try:
        config = parse_json_config(config_path, "claude_code")
    except Exception as e:
        if use_json:
            print(json.dumps({"error": str(e), "candidates": []}))
        else:
            print(f"Error parsing config: {e}", file=sys.stderr)
        return 1

    candidates = detect_pinned_servers(config)

    # Filter out already-pinned servers
    already_pinned = {e.name for e in storage.list()}
    new_candidates = [c for c in candidates if c.name not in already_pinned]

    if use_json:
        output = {
            "config_path": str(config_path),
            "candidates": [c.to_dict() for c in new_candidates],
            "already_pinned": list(already_pinned),
            "total_candidates": len(new_candidates),
        }
        print(json.dumps(output, indent=2))
        return 0

    if not new_candidates:
        print("No new servers to pin.")
        if already_pinned:
            print(f"  (Already pinned: {', '.join(sorted(already_pinned))})")
        return 0

    print(f"Auto-detected {len(new_candidates)} server(s) to pin:")
    print()

    for candidate in new_candidates:
        method = candidate.detection_method or "unknown"
        print(f"  • {candidate.name}")
        print(f"    Detection: {method}")
        if candidate.path:
            print(f"    Path: {candidate.path}")

    print()
    print("To pin these servers:")
    for candidate in new_candidates:
        print(f"  token-audit pin {candidate.name}")

    return 0


# ============================================================================
# sessions command (v1.0.0 - task-224.7)
# ============================================================================


def cmd_sessions(args: argparse.Namespace) -> int:
    """Execute sessions command - list and manage collected sessions."""
    from .storage import StorageManager

    storage = StorageManager()

    # Dispatch to subcommand
    subcommand = getattr(args, "sessions_command", None)

    if subcommand == "list":
        return _cmd_sessions_list(args, storage)
    elif subcommand == "show":
        return _cmd_sessions_show(args, storage)
    elif subcommand == "delete":
        return _cmd_sessions_delete(args, storage)
    else:
        # No subcommand - show help
        print("Usage: token-audit sessions <command>")
        print()
        print("Commands:")
        print("  list     List recent sessions")
        print("  show     Show session details")
        print("  delete   Delete sessions")
        print()
        print("Run 'token-audit sessions <command> --help' for more info.")
        return 1


def _cmd_sessions_list(args: argparse.Namespace, storage: Any) -> int:
    """List collected sessions."""
    import json
    from datetime import datetime

    platform = normalize_platform(getattr(args, "platform", None))
    limit = None if getattr(args, "all", False) else getattr(args, "count", 10)
    use_json = getattr(args, "json", False)
    verbose = getattr(args, "verbose", False)

    # Get sessions
    sessions = storage.list_sessions(platform=platform, limit=limit)

    if not sessions:
        if use_json:
            print(json.dumps({"sessions": [], "total": 0}))
        else:
            print("No sessions found.")
            print()
            print("Start tracking with: token-audit collect")
        return 0

    # Build session data
    session_data = []
    for session_path in sessions:
        try:
            # Extract platform from path structure: sessions/{platform}/{date}/{session}.json
            platform_dir = session_path.parent.parent.name  # platform directory
            platform_name = platform_dir.replace("-", " ").title().replace(" ", "-")

            # Get basic info
            entry = {
                "id": session_path.stem,
                "platform": platform_name,
                "date": session_path.parent.name,  # date directory
                "path": str(session_path),
            }

            if verbose or use_json:
                # Load session for detailed info
                with open(session_path) as f:
                    first_line = f.readline()
                    if first_line.strip():
                        header = json.loads(first_line)
                        if isinstance(header, dict):
                            entry["project"] = header.get("project", "unknown")
                            entry["model"] = header.get("model", "unknown")

                            # Get token usage if available
                            token_usage = header.get("token_usage", {})
                            if isinstance(token_usage, dict):
                                entry["total_tokens"] = token_usage.get("total_tokens", 0)
                                entry["cached_tokens"] = token_usage.get("cached_tokens", 0)

                            # Get duration if available
                            start = header.get("start_time")
                            end = header.get("end_time")
                            if start and end:
                                try:
                                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                                    entry["duration_seconds"] = (end_dt - start_dt).total_seconds()
                                except (ValueError, AttributeError):
                                    pass

            session_data.append(entry)
        except Exception as e:
            # Still include session with minimal info instead of skipping entirely
            # This prevents verbose/JSON mode from showing 0 sessions on parse errors
            entry["parse_error"] = str(e)
            session_data.append(entry)

    if use_json:
        output = {"sessions": session_data, "total": len(session_data)}
        print(json.dumps(output, indent=2))
        return 0

    # Print human-readable list
    print(f"Sessions ({len(session_data)}):")
    print()

    for entry in session_data:
        if verbose:
            tokens = entry.get("total_tokens", 0)
            duration = entry.get("duration_seconds", 0)
            duration_str = _format_duration(duration) if duration else ""
            tokens_str = f"{tokens:,}" if tokens else ""
            project = entry.get("project", "")[:20]

            print(
                f"  {entry['id'][:36]:36}  {entry['platform']:12} {entry['date']}  {project:20}  {tokens_str:>10}  {duration_str:>8}"
            )
        else:
            print(f"  {entry['id'][:36]:36}  {entry['platform']:12}  {entry['date']}")

    print()
    print("Show details: token-audit sessions show <session-id>")
    print("Interactive:  token-audit ui")

    return 0


def _cmd_sessions_show(args: argparse.Namespace, storage: Any) -> int:
    """Show session details."""
    import json

    session_id = args.session_id
    use_json = getattr(args, "json", False)

    # Find session (supports partial match)
    session_path = storage.find_session(session_id)

    # If not found by ID, try partial match
    if not session_path:
        sessions = storage.list_sessions()
        matches = [s for s in sessions if session_id in s.stem]
        if len(matches) == 1:
            session_path = matches[0]
        elif len(matches) > 1:
            print(f"Multiple sessions match '{session_id}':", file=sys.stderr)
            for m in matches[:10]:
                print(f"  {m.stem}", file=sys.stderr)
            if len(matches) > 10:
                print(f"  ... and {len(matches) - 10} more", file=sys.stderr)
            return 1

    if not session_path:
        print(f"Session not found: {session_id}", file=sys.stderr)
        return 1

    # Load and display session
    try:
        with open(session_path) as f:
            content = f.read()

        if not content.strip():
            print("Empty session file.", file=sys.stderr)
            return 1

        # Parse session - could be JSON or JSONL format
        data = json.loads(content)

        # Handle token-audit v1.0.0+ JSON format: {"_file": {...}, "session": {...}}
        if isinstance(data, dict) and "session" in data:
            session = data["session"]
            # v1.0.4 has tool_calls at top level, v1.0.0 inside session
            event_count = len(data.get("tool_calls", session.get("calls", [])))
        else:
            # Legacy JSONL format - first line is header
            session = data
            event_count = 0

        if use_json:
            # Return full session data
            output = {
                "id": session_path.stem,
                "path": str(session_path),
                "data": data,
            }
            print(json.dumps(output, indent=2))
            return 0

        # Human-readable display
        print(f"Session: {session_path.stem}")
        print("=" * 60)
        print()

        print(f"  Platform: {session.get('platform', 'unknown')}")
        print(f"  Project:  {session.get('project', 'unknown')}")
        print(f"  Model:    {session.get('model', 'unknown')}")
        print()

        # Token usage - v1.0.4 has token_usage at top level, v1.0.0 inside session
        token_usage = data.get("token_usage", session.get("token_usage", {}))
        if isinstance(token_usage, dict):
            total = token_usage.get("total_tokens", 0)
            # v1.0.4 uses cache_read_tokens, v1.0.0 used cached_tokens
            cached = token_usage.get("cache_read_tokens", token_usage.get("cached_tokens", 0))
            print(f"  Tokens:   {total:,} total, {cached:,} cached")

        # MCP calls - v1.0.4 has mcp_summary at top level, v1.0.0 had mcp_tool_calls
        mcp_summary = data.get("mcp_summary", {})
        if isinstance(mcp_summary, dict) and mcp_summary:
            total_calls = mcp_summary.get("total_calls", 0)
            print(f"  MCP Calls: {total_calls:,}")
        else:
            # Fallback to v1.0.0 format
            mcp_calls = session.get("mcp_tool_calls", {})
            if isinstance(mcp_calls, dict):
                total_calls = mcp_calls.get("total_calls", 0)
                print(f"  MCP Calls: {total_calls:,}")

        # Duration - v1.0.4 uses started_at/ended_at, v1.0.0 used start_time/end_time
        start = session.get("started_at", session.get("start_time"))
        end = session.get("ended_at", session.get("end_time"))
        if start:
            print(f"  Start:    {start[:19]}")
        if end:
            print(f"  End:      {end[:19]}")

        print()
        print(f"  Path: {session_path}")
        print()
        print(f"Tool calls in session: {event_count}")

    except Exception as e:
        print(f"Error reading session: {e}", file=sys.stderr)
        return 1

    return 0


def _cmd_sessions_delete(args: argparse.Namespace, storage: Any) -> int:
    """Delete sessions."""
    import re
    from datetime import datetime, timedelta

    session_id = getattr(args, "session_id", None)
    older_than = getattr(args, "older_than", None)
    platform = normalize_platform(getattr(args, "platform", None))
    force = getattr(args, "force", False)
    dry_run = getattr(args, "dry_run", False)

    if not session_id and not older_than:
        print("Error: specify session ID or --older-than", file=sys.stderr)
        print()
        print("Examples:")
        print("  token-audit sessions delete <session-id>")
        print("  token-audit sessions delete --older-than 30d")
        return 1

    to_delete: List[Path] = []

    if older_than:
        # Parse duration (e.g., 7d, 30d, 1w, 2w)
        match = re.match(r"(\d+)([dwm])", older_than.lower())
        if not match:
            print(f"Invalid duration format: {older_than}", file=sys.stderr)
            print("Use format like: 7d, 30d, 1w, 2m")
            return 1

        value, unit = int(match.group(1)), match.group(2)
        if unit == "d":
            delta = timedelta(days=value)
        elif unit == "w":
            delta = timedelta(weeks=value)
        elif unit == "m":
            delta = timedelta(days=value * 30)
        else:
            delta = timedelta(days=value)

        cutoff = datetime.now() - delta

        # Find sessions older than cutoff
        sessions = storage.list_sessions(platform=platform)
        for session_path in sessions:
            try:
                mtime = datetime.fromtimestamp(session_path.stat().st_mtime)
                if mtime < cutoff:
                    to_delete.append(session_path)
            except OSError:
                continue
    else:
        # Delete specific session
        session_path = storage.find_session(session_id)

        # Try partial match
        if not session_path:
            sessions = storage.list_sessions(platform=platform)
            matches = [s for s in sessions if session_id in s.stem]
            if len(matches) == 1:
                session_path = matches[0]
            elif len(matches) > 1:
                print(f"Multiple sessions match '{session_id}':", file=sys.stderr)
                for m in matches[:10]:
                    print(f"  {m.stem}", file=sys.stderr)
                return 1

        if not session_path:
            print(f"Session not found: {session_id}", file=sys.stderr)
            return 1

        to_delete = [session_path]

    if not to_delete:
        print("No sessions to delete.")
        return 0

    # Show what will be deleted
    print(f"Sessions to delete: {len(to_delete)}")
    if dry_run or not force:
        for path in to_delete[:10]:
            print(f"  {path.stem}")
        if len(to_delete) > 10:
            print(f"  ... and {len(to_delete) - 10} more")

    if dry_run:
        print()
        print("(Dry run - no files deleted)")
        return 0

    # Confirm unless --force
    if not force:
        print()
        try:
            response = input("Delete these sessions? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1

        if response not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Delete sessions
    deleted = 0
    errors = 0
    for path in to_delete:
        try:
            path.unlink()
            deleted += 1
        except OSError as e:
            print(f"Error deleting {path.stem}: {e}", file=sys.stderr)
            errors += 1

    print(f"Deleted {deleted} session(s).")
    if errors:
        print(f"Errors: {errors}")
        return 1

    return 0


# ============================================================================
# Historical Reporting Commands (v1.0.0 - task-226)
# ============================================================================


def _format_token_count(n: int) -> str:
    """Format token count with thousands separators."""
    return f"{n:,}"


def _format_cost_usd(cost_usd: Any) -> str:
    """Format cost as $X.XX."""
    from decimal import Decimal

    if isinstance(cost_usd, Decimal):
        return f"${cost_usd:.2f}"
    return f"${float(cost_usd):.2f}"


def _format_week_range(start: str, end: str) -> str:
    """Format week range for display (e.g., 'Dec 16-22' or 'Dec 28 - Jan 3')."""
    from datetime import datetime as dt

    s = dt.strptime(start, "%Y-%m-%d")
    e = dt.strptime(end, "%Y-%m-%d")
    if s.month == e.month and s.year == e.year:
        return f"{s.strftime('%b')} {s.day}-{e.day}"
    elif s.year == e.year:
        return f"{s.strftime('%b %d')} - {e.strftime('%b %d')}"
    else:
        return f"{s.strftime('%b %d, %Y')} - {e.strftime('%b %d, %Y')}"


def _month_name(month: int) -> str:
    """Return abbreviated month name."""
    import calendar

    return calendar.month_abbr[month]


def _render_historical_table(
    title: str,
    aggregates: List[Any],
    period_formatter: Any,  # Callable[[Any], str]
    show_breakdown: bool = False,
    show_instances: bool = False,
) -> None:
    """Render Rich table for historical data with totals row.

    Args:
        title: Table title
        aggregates: List of DailyAggregate, WeeklyAggregate, or MonthlyAggregate
        period_formatter: Function to format the period column
        show_breakdown: Show per-model breakdown rows
        show_instances: Show per-project breakdown rows
    """
    from decimal import Decimal

    from rich.console import Console
    from rich.table import Table

    console = Console()

    if not aggregates:
        console.print(f"[dim]{title}[/dim]")
        console.print("[yellow]No data found for the specified period.[/yellow]")
        return

    # Create table
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Period", style="white")
    table.add_column("Sessions", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cache Read", justify="right")
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Cost", justify="right", style="green")

    # Track totals
    total_sessions = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_tokens = 0
    total_cost_micros = 0

    for agg in aggregates:
        period_str = period_formatter(agg)

        table.add_row(
            period_str,
            str(agg.session_count),
            _format_token_count(agg.input_tokens),
            _format_token_count(agg.output_tokens),
            _format_token_count(agg.cache_read_tokens),
            _format_token_count(agg.total_tokens),
            _format_cost_usd(agg.cost_usd),
        )

        # Accumulate totals
        total_sessions += agg.session_count
        total_input += agg.input_tokens
        total_output += agg.output_tokens
        total_cache_read += agg.cache_read_tokens
        total_tokens += agg.total_tokens
        total_cost_micros += agg.cost_micros

        # Show model breakdown if requested
        if show_breakdown and agg.model_breakdowns:
            # Sort by total tokens descending
            sorted_models = sorted(
                agg.model_breakdowns.values(),
                key=lambda m: m.total_tokens,
                reverse=True,
            )
            for model_usage in sorted_models:
                table.add_row(
                    f"  [dim]{model_usage.model}[/dim]",
                    "",
                    f"[dim]{_format_token_count(model_usage.input_tokens)}[/dim]",
                    f"[dim]{_format_token_count(model_usage.output_tokens)}[/dim]",
                    f"[dim]{_format_token_count(model_usage.cache_read_tokens)}[/dim]",
                    f"[dim]{_format_token_count(model_usage.total_tokens)}[/dim]",
                    f"[dim]{_format_cost_usd(model_usage.cost_usd)}[/dim]",
                )

        # Show project breakdown if requested
        if show_instances and agg.project_breakdowns:
            for project_path, proj in agg.project_breakdowns.items():
                display_path = project_path if project_path else "Unknown"
                # Shorten long paths
                if len(display_path) > 40:
                    display_path = "..." + display_path[-37:]
                table.add_row(
                    f"  [dim]{display_path}[/dim]",
                    f"[dim]{proj.session_count}[/dim]",
                    f"[dim]{_format_token_count(proj.input_tokens)}[/dim]",
                    f"[dim]{_format_token_count(proj.output_tokens)}[/dim]",
                    f"[dim]{_format_token_count(proj.cache_read_tokens)}[/dim]",
                    f"[dim]{_format_token_count(proj.total_tokens)}[/dim]",
                    f"[dim]{_format_cost_usd(proj.cost_usd)}[/dim]",
                )

    # Add totals row with separator
    table.add_section()
    total_cost_usd = Decimal(total_cost_micros) / Decimal(1_000_000)
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_sessions}[/bold]",
        f"[bold]{_format_token_count(total_input)}[/bold]",
        f"[bold]{_format_token_count(total_output)}[/bold]",
        f"[bold]{_format_token_count(total_cache_read)}[/bold]",
        f"[bold]{_format_token_count(total_tokens)}[/bold]",
        f"[bold green]{_format_cost_usd(total_cost_usd)}[/bold green]",
    )

    console.print(table)


def _output_historical_json(
    aggregates: List[Any],
    include_breakdown: bool = False,
    include_instances: bool = False,
) -> None:
    """Output aggregates as JSON to stdout.

    Args:
        aggregates: List of aggregate objects with to_dict() method
        include_breakdown: Include model_breakdowns in output
        include_instances: Include project_breakdowns in output
    """
    import json

    output = []
    for agg in aggregates:
        data = agg.to_dict()

        # Optionally remove breakdowns to reduce output size
        if not include_breakdown:
            data.pop("model_breakdowns", None)
        if not include_instances:
            data.pop("project_breakdowns", None)

        # Convert Decimal cost_usd to string for precision
        data["cost_usd"] = str(agg.cost_usd)

        output.append(data)

    print(json.dumps(output, indent=2))


def cmd_daily(args: argparse.Namespace) -> int:
    """Execute daily command (v1.0.0 - task-226.1).

    Shows token usage aggregated by day.
    """
    from datetime import date, timedelta

    from .aggregation import aggregate_daily

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)  # Inclusive

    # Normalize platform format
    platform = normalize_platform(args.platform)

    # Get aggregated data
    results = aggregate_daily(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        group_by_project=args.instances,
    )

    # Output
    if args.json:
        _output_historical_json(results, args.breakdown, args.instances)
    else:
        _render_historical_table(
            title=f"Daily Token Usage (Last {args.days} Days)",
            aggregates=results,
            period_formatter=lambda a: a.date,
            show_breakdown=args.breakdown,
            show_instances=args.instances,
        )

    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    """Execute weekly command (v1.0.0 - task-226.2).

    Shows token usage aggregated by week.
    """
    from datetime import date, timedelta

    from .aggregation import aggregate_weekly

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(weeks=args.weeks)

    # Convert week start (monday=0, sunday=6)
    start_of_week = 0 if args.start_of_week == "monday" else 6

    # Normalize platform format
    platform = normalize_platform(args.platform)

    # Get aggregated data
    results = aggregate_weekly(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        start_of_week=start_of_week,
        group_by_project=args.instances,
    )

    # Output
    if args.json:
        _output_historical_json(results, args.breakdown, args.instances)
    else:
        _render_historical_table(
            title=f"Weekly Token Usage (Last {args.weeks} Weeks)",
            aggregates=results,
            period_formatter=lambda a: _format_week_range(a.week_start, a.week_end),
            show_breakdown=args.breakdown,
            show_instances=args.instances,
        )

    return 0


def cmd_monthly(args: argparse.Namespace) -> int:
    """Execute monthly command (v1.0.0 - task-226.3).

    Shows token usage aggregated by month.
    """
    from datetime import date

    from .aggregation import aggregate_monthly

    # Calculate date range (go back N months from current month)
    end_date = date.today()
    # Calculate start date N-1 months ago
    month = end_date.month - (args.months - 1)
    year = end_date.year
    while month < 1:
        month += 12
        year -= 1
    start_date = date(year, month, 1)  # Start of month

    # Normalize platform format
    platform = normalize_platform(args.platform)

    # Get aggregated data
    results = aggregate_monthly(
        platform=platform,
        start_date=start_date,
        end_date=end_date,
        group_by_project=args.instances,
    )

    # Output
    if args.json:
        _output_historical_json(results, args.breakdown, args.instances)
    else:
        _render_historical_table(
            title=f"Monthly Token Usage (Last {args.months} Months)",
            aggregates=results,
            period_formatter=lambda a: f"{_month_name(a.month)} {a.year}",
            show_breakdown=args.breakdown,
            show_instances=args.instances,
        )

    return 0


# ============================================================================
# Bucket Command (v1.0.4 - task-247.4)
# ============================================================================

# Display names for bucket classification
BUCKET_DISPLAY_NAMES = {
    "state_serialization": "State serialization",
    "redundant": "Redundant outputs",
    "drift": "Conversation drift",
    "tool_discovery": "Tool discovery",
}


def cmd_bucket(args: argparse.Namespace) -> int:
    """Execute bucket command - analyze token distribution by efficiency bucket.

    Classifies MCP tool calls into 4 buckets:
    1. Redundant outputs - Duplicate tool calls (same content_hash)
    2. Tool discovery - Schema introspection calls
    3. State serialization - Large content payloads
    4. Conversation drift - Residual (default bucket)
    """

    from .buckets import BucketClassifier
    from .session_manager import SessionManager
    from .storage import StorageManager

    # Determine session to analyze
    session_path = args.session
    session = None

    if session_path is None:
        # Find latest session
        storage = StorageManager()
        platform = normalize_platform(args.platform)
        sessions = storage.list_sessions(platform=platform, limit=1)

        if not sessions:
            print("Error: No sessions found. Run 'token-audit collect' first.")
            return 1

        session_path = sessions[0]
        print(f"Analyzing latest session: {session_path.name}")

    # Load session
    manager = SessionManager()
    if session_path.is_file() or session_path.is_dir():
        session = manager.load_session(session_path)

    if not session:
        print(f"Error: Failed to load session from: {session_path}")
        return 1

    # Check for --by-task flag (v1.0.4 - task-247.9)
    by_task = getattr(args, "by_task", False)
    if by_task:
        return _bucket_by_task(args, session)

    # Classify session
    classifier = BucketClassifier()
    results = classifier.classify_session(session)

    # Calculate total for the summary row
    total_tokens = sum(r.tokens for r in results)
    total_calls = sum(r.call_count for r in results)

    # Output based on format
    output_format = args.format
    output_path = args.output

    if output_format == "json":
        return _bucket_output_json(results, total_tokens, total_calls, output_path)
    elif output_format == "csv":
        return _bucket_output_csv(results, total_tokens, total_calls, output_path)
    else:  # table
        return _bucket_output_table(results, total_tokens, total_calls, output_path)


def _bucket_output_table(
    results: List["BucketResult"],
    total_tokens: int,
    total_calls: int,
    output_path: Optional[Path],
) -> int:
    """Output bucket results as formatted table."""
    lines: List[str] = []

    # Header
    lines.append("")
    lines.append("Bucket Classification Analysis")
    lines.append("\u2550" * 70)  # ══════

    # Column headers
    lines.append(
        f"{'Bucket':<20} \u2502 {'Tokens':>8} \u2502 {'%':>6} \u2502 {'Calls':>5} \u2502 {'Top Tool':<20}"
    )
    lines.append(
        "\u2500" * 20
        + "\u253c"
        + "\u2500" * 10
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 7
        + "\u253c"
        + "\u2500" * 21
    )

    # Data rows (sorted by tokens descending - already sorted by classifier)
    for result in results:
        display_name = BUCKET_DISPLAY_NAMES.get(result.bucket, result.bucket)
        top_tool = result.top_tools[0][0] if result.top_tools else "-"
        # Truncate tool name if too long
        if len(top_tool) > 20:
            top_tool = top_tool[:17] + "..."

        lines.append(
            f"{display_name:<20} \u2502 {result.tokens:>8,} \u2502 {result.percentage:>5.1f}% \u2502 {result.call_count:>5} \u2502 {top_tool:<20}"
        )

    # Footer separator and total
    lines.append(
        "\u2500" * 20
        + "\u2534"
        + "\u2500" * 10
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 7
        + "\u2534"
        + "\u2500" * 21
    )
    lines.append(f"{'Total':<20}   {total_tokens:>8,}   {'100.0':>5}%   {total_calls:>5}  ")
    lines.append("")

    # Write output
    output = "\n".join(lines)
    if output_path:
        output_path.write_text(output)
        print(f"Wrote bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


def _bucket_output_json(
    results: List["BucketResult"],
    total_tokens: int,
    total_calls: int,
    output_path: Optional[Path],
) -> int:
    """Output bucket results as JSON."""
    import json as json_module

    data = {
        "buckets": [r.to_dict() for r in results],
        "summary": {
            "total_tokens": total_tokens,
            "total_calls": total_calls,
        },
    }

    output = json_module.dumps(data, indent=2)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


def _bucket_output_csv(
    results: List["BucketResult"],
    total_tokens: int,
    total_calls: int,
    output_path: Optional[Path],
) -> int:
    """Output bucket results as CSV."""
    lines: List[str] = []

    # Header
    lines.append("bucket,display_name,tokens,percentage,call_count,top_tool,top_tool_tokens")

    # Data rows
    for result in results:
        display_name = BUCKET_DISPLAY_NAMES.get(result.bucket, result.bucket)
        top_tool = result.top_tools[0][0] if result.top_tools else ""
        top_tool_tokens = result.top_tools[0][1] if result.top_tools else 0

        lines.append(
            f"{result.bucket},{display_name},{result.tokens},{result.percentage:.2f},{result.call_count},{top_tool},{top_tool_tokens}"
        )

    # Total row
    lines.append(f"total,Total,{total_tokens},100.0,{total_calls},,")

    output = "\n".join(lines)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


# ============================================================================
# Task Command (v1.0.4 - task-247.7)
# ============================================================================


def _format_duration_task(seconds: float) -> str:
    """Format duration as human-readable string for task display.

    Note: Uses the same format as the existing _format_duration() above.
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def _active_session_matches_platform(
    streaming: "StreamingStorage",
    session_id: str,
    platform: Optional[str],
) -> bool:
    """
    Check if an active session matches the specified platform filter.

    Args:
        streaming: StreamingStorage instance
        session_id: Active session ID to check
        platform: Platform filter (normalized form, e.g. "claude_code")

    Returns:
        True if session matches platform or no platform filter specified
    """
    if platform is None:
        return True  # No filter, accept any active session

    try:
        # Read the session_start event to get platform metadata
        for event in streaming.read_events(session_id):
            if event.get("type") == "session_start":
                session_platform: str = event.get("platform", "")
                # Normalize both for comparison (hyphen -> underscore)
                session_platform_normalized = session_platform.replace("-", "_")
                platform_normalized = platform.replace("-", "_")
                return bool(session_platform_normalized == platform_normalized)
    except Exception:
        pass
    return False


def _resolve_session_for_task(
    session_id: Optional[str],
    platform: Optional[str],
) -> Tuple[str, Optional[Path]]:
    """Resolve session ID and path for task operations.

    Priority:
    1. Explicit --session argument
    2. Environment variable (CLAUDE_CODE_SESSION, CODEX_SESSION, GEMINI_SESSION)
    3. Active collector session (if running) - added in #117
    4. Latest completed session from StorageManager

    Returns:
        Tuple of (session_id, session_path or None)
    """
    import os

    from .storage import StorageManager, StreamingStorage

    norm_platform = normalize_platform(platform) if platform else None

    # 1. Explicit session ID
    if session_id:
        storage = StorageManager()
        # Try to find session file by ID
        sessions = storage.list_sessions(platform=norm_platform, limit=100)
        for session_path in sessions:
            if session_id in session_path.stem:
                return session_id, session_path
        # Session ID provided but not found - return ID without path
        return session_id, None

    # 2. Environment variable
    env_vars = ["CLAUDE_CODE_SESSION", "CODEX_SESSION", "GEMINI_SESSION"]
    for var in env_vars:
        if var in os.environ:
            env_session_id = os.environ[var]
            storage = StorageManager()
            sessions = storage.list_sessions(limit=100)
            for session_path in sessions:
                if env_session_id in session_path.stem:
                    return env_session_id, session_path
            return env_session_id, None

    # 3. Active collector session (#117)
    streaming = StreamingStorage()
    active_sessions = streaming.get_active_sessions()

    if active_sessions:
        # Find first active session matching platform filter
        for active_session_id in active_sessions:
            if _active_session_matches_platform(streaming, active_session_id, norm_platform):
                return active_session_id, streaming.get_active_session_path(active_session_id)

    # 4. Latest completed session
    storage = StorageManager()
    sessions = storage.list_sessions(platform=norm_platform, limit=1)

    if sessions:
        session_path = sessions[0]
        # Extract session ID from path
        resolved_session_id = session_path.stem
        return resolved_session_id, session_path

    return "", None


def cmd_task(args: argparse.Namespace) -> int:
    """Execute task command - manage task markers for per-task analysis."""
    subcommand = getattr(args, "task_command", None)

    if subcommand == "start":
        return _cmd_task_start(args)
    elif subcommand == "end":
        return _cmd_task_end(args)
    elif subcommand == "list":
        return _cmd_task_list(args)
    elif subcommand == "show":
        return _cmd_task_show(args)
    else:
        print("Usage: token-audit task <command>")
        print()
        print("Commands:")
        print("  start    Start a new task")
        print("  end      End the current task")
        print("  list     List tasks in a session")
        print("  show     Show task details with bucket breakdown")
        print()
        print("Run 'token-audit task <command> --help' for more info.")
        return 1


def _cmd_task_start(args: argparse.Namespace) -> int:
    """Start a new task."""
    from .tasks import TaskManager

    task_name = args.name
    session_id, session_path = _resolve_session_for_task(
        getattr(args, "session", None),
        getattr(args, "platform", None),
    )

    if not session_id:
        print("Error: No session found. Run 'token-audit collect' first or specify --session.")
        return 1

    manager = TaskManager()

    # Check if there's an active task (for informational message)
    is_active, current = manager.is_task_active(session_id)
    if is_active and current:
        print(f"Auto-ending previous task: {current}")

    marker = manager.start_task(task_name, session_id)
    print(f"Started task: {task_name}")
    print(f"  Session: {session_id}")
    print(f"  Time: {marker.timestamp.isoformat(timespec='seconds')}")

    return 0


def _cmd_task_end(args: argparse.Namespace) -> int:
    """End the current task."""
    from .tasks import TaskManager

    session_id, session_path = _resolve_session_for_task(
        getattr(args, "session", None),
        getattr(args, "platform", None),
    )

    if not session_id:
        print("Error: No session found. Run 'token-audit collect' first or specify --session.")
        return 1

    manager = TaskManager()

    # Check if there's an active task
    is_active, active_task = manager.is_task_active(session_id)

    if not is_active or not active_task:
        print("Error: No active task to end.")
        print("Start a task first: token-audit task start <name>")
        return 1

    # Load existing markers and set state for end_task to work
    markers = manager._load_markers(session_id)
    manager._current_task = active_task
    manager._current_session_id = session_id
    manager.markers = markers

    end_marker = manager.end_task(session_id)
    if end_marker:
        print(f"Ended task: {active_task}")
        print(f"  Session: {session_id}")
        print(f"  Time: {end_marker.timestamp.isoformat(timespec='seconds')}")
        return 0
    else:
        print("Error: Failed to end task.")
        return 1


def _cmd_task_list(args: argparse.Namespace) -> int:
    """List tasks in a session."""
    import json as json_module

    from .session_manager import SessionManager
    from .tasks import TaskManager

    session_id, session_path = _resolve_session_for_task(
        getattr(args, "session", None),
        getattr(args, "platform", None),
    )

    if not session_id:
        print("Error: No session found.")
        return 1

    output_format = getattr(args, "format", "table")

    # Load session for task analysis
    session = None
    if session_path:
        sm = SessionManager()
        session = sm.load_session(session_path)

    manager = TaskManager()

    if session:
        # Get full task summaries with bucket analysis
        summaries = manager.get_tasks(session)
    else:
        # No session file - just check if markers exist
        markers = manager._load_markers(session_id)
        if not markers:
            print("No tasks found in session.")
            print("Start a task: token-audit task start <name>")
            return 0
        # Can't compute full summaries without session data
        print(f"Found {len(markers)} task markers, but session file not found.")
        print("Cannot compute task summaries without session data.")
        return 1

    if not summaries:
        print("No tasks found in session.")
        print("Start a task: token-audit task start <name>")
        return 0

    if output_format == "json":
        data = {
            "session_id": session_id,
            "tasks": [s.to_dict() for s in summaries],
        }
        print(json_module.dumps(data, indent=2))
        return 0

    if output_format == "csv":
        print("name,total_tokens,call_count,duration_seconds,start_time,end_time")
        for s in summaries:
            print(
                f'"{s.name}",{s.total_tokens},{s.call_count},{s.duration_seconds:.1f},'
                f"{s.start_time.isoformat()},{s.end_time.isoformat()}"
            )
        return 0

    # Table format
    print(f"\nTasks in session: {session_id}")
    print("=" * 80)
    print(f"{'#':<3} {'Task':<30} | {'Tokens':>10} | {'Calls':>6} | {'Duration':>10}")
    print("-" * 3 + " " + "-" * 30 + "-+-" + "-" * 10 + "-+-" + "-" * 6 + "-+-" + "-" * 10)

    for i, s in enumerate(summaries, 1):
        duration_str = _format_duration(s.duration_seconds)
        task_name = s.name[:30] if len(s.name) > 30 else s.name
        print(
            f"{i:<3} {task_name:<30} | {s.total_tokens:>10,} | {s.call_count:>6} | {duration_str:>10}"
        )

    print("-" * 80)
    total_tokens = sum(s.total_tokens for s in summaries)
    total_calls = sum(s.call_count for s in summaries)
    total_duration = sum(s.duration_seconds for s in summaries)
    print(
        f"{'':3} {'Total':<30} | {total_tokens:>10,} | {total_calls:>6} | {_format_duration(total_duration):>10}"
    )
    print()

    return 0


def _cmd_task_show(args: argparse.Namespace) -> int:
    """Show task details with bucket breakdown."""
    import json as json_module

    from .session_manager import SessionManager
    from .tasks import TaskManager

    task_name = args.name
    session_id, session_path = _resolve_session_for_task(
        getattr(args, "session", None),
        getattr(args, "platform", None),
    )

    if not session_id:
        print("Error: No session found.")
        return 1

    if not session_path:
        print(f"Error: Session file not found for: {session_id}")
        return 1

    output_format = getattr(args, "format", "table")

    # Load session
    sm = SessionManager()
    session = sm.load_session(session_path)

    if not session:
        print(f"Error: Failed to load session: {session_path}")
        return 1

    manager = TaskManager()
    summaries = manager.get_tasks(session)

    # Find matching task
    matching = [s for s in summaries if s.name == task_name]
    if not matching:
        # Try partial match
        matching = [s for s in summaries if task_name.lower() in s.name.lower()]

    if not matching:
        print(f"Error: Task not found: {task_name}")
        if summaries:
            print("Available tasks:")
            for s in summaries:
                print(f"  - {s.name}")
        return 1

    if len(matching) > 1:
        print(f"Multiple tasks match '{task_name}':")
        for s in matching:
            print(f"  - {s.name}")
        return 1

    summary = matching[0]

    if output_format == "json":
        print(json_module.dumps(summary.to_dict(), indent=2))
        return 0

    # Table format with bucket breakdown
    print(f"\nTask: {summary.name}")
    print("=" * 70)
    print()
    print(f"  Start:    {summary.start_time.isoformat(timespec='seconds')}")
    print(f"  End:      {summary.end_time.isoformat(timespec='seconds')}")
    print(f"  Duration: {_format_duration(summary.duration_seconds)}")
    print(f"  Tokens:   {summary.total_tokens:,}")
    print(f"  Calls:    {summary.call_count}")
    print()
    print("Bucket Breakdown:")
    print("-" * 70)
    print(f"{'Bucket':<20} | {'Tokens':>8} | {'%':>6} | {'Calls':>5} | {'Top Tool':<20}")
    print("-" * 20 + "-+-" + "-" * 8 + "-+-" + "-" * 6 + "-+-" + "-" * 5 + "-+-" + "-" * 20)

    for bucket_name in ["state_serialization", "redundant", "tool_discovery", "drift"]:
        if bucket_name in summary.buckets:
            result = summary.buckets[bucket_name]
            display_name = BUCKET_DISPLAY_NAMES.get(bucket_name, bucket_name)
            if result.top_tools:
                top_tool = result.top_tools[0][0]
                if len(top_tool) > 20:
                    top_tool = top_tool[:17] + "..."
            else:
                top_tool = "-"
            print(
                f"{display_name:<20} | {result.tokens:>8,} | {result.percentage:>5.1f}% | "
                f"{result.call_count:>5} | {top_tool:<20}"
            )

    print("-" * 70)
    print()

    return 0


# ============================================================================
# Bucket by Task (v1.0.4 - task-247.9)
# ============================================================================


def _bucket_by_task(args: argparse.Namespace, session: "Session") -> int:
    """Output bucket analysis broken down by task."""

    from .buckets import BucketClassifier
    from .tasks import TaskManager

    output_format = getattr(args, "format", "table")
    output_path = getattr(args, "output", None)

    task_manager = TaskManager()
    summaries = task_manager.get_tasks(session)

    if not summaries:
        print("No task markers found in session.")
        print("Use 'token-audit task start <name>' to create task markers.")
        print()
        print("Showing overall bucket analysis instead:")
        print()
        # Fall back to overall analysis
        classifier = BucketClassifier()
        results = classifier.classify_session(session)
        total_tokens = sum(r.tokens for r in results)
        total_calls = sum(r.call_count for r in results)
        return _bucket_output_table(results, total_tokens, total_calls, output_path)

    if output_format == "json":
        return _bucket_by_task_json(summaries, output_path)
    elif output_format == "csv":
        return _bucket_by_task_csv(summaries, output_path)
    else:
        return _bucket_by_task_table(summaries, output_path)


def _bucket_by_task_table(
    summaries: List["TaskSummary"],
    output_path: Optional[Path],
) -> int:
    """Output per-task bucket analysis as table."""
    from .buckets import BucketResult

    lines: List[str] = []

    lines.append("")
    lines.append("Per-Task Bucket Analysis")
    lines.append("\u2550" * 85)

    # Column headers
    lines.append(
        f"{'Task':<30} \u2502 {'Tokens':>8} \u2502 {'State':>6} \u2502 {'Redund':>6} \u2502 {'Drift':>6} \u2502 {'Disc':>5}"
    )
    lines.append(
        "\u2500" * 30
        + "\u253c"
        + "\u2500" * 10
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 7
    )

    # Data rows
    for summary in summaries:
        task_name = summary.name[:30] if len(summary.name) > 30 else summary.name
        state_pct = summary.buckets.get(
            "state_serialization", BucketResult("state_serialization")
        ).percentage
        redund_pct = summary.buckets.get("redundant", BucketResult("redundant")).percentage
        drift_pct = summary.buckets.get("drift", BucketResult("drift")).percentage
        disc_pct = summary.buckets.get("tool_discovery", BucketResult("tool_discovery")).percentage

        lines.append(
            f"{task_name:<30} \u2502 {summary.total_tokens:>8,} \u2502 {state_pct:>5.1f}% \u2502 "
            f"{redund_pct:>5.1f}% \u2502 {drift_pct:>5.1f}% \u2502 {disc_pct:>4.1f}%"
        )

    # Footer with averages
    lines.append(
        "\u2500" * 30
        + "\u2534"
        + "\u2500" * 10
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 7
    )

    # Calculate averages
    if summaries:
        avg_tokens = sum(s.total_tokens for s in summaries) // len(summaries)
        avg_state = sum(
            s.buckets.get("state_serialization", BucketResult("state_serialization")).percentage
            for s in summaries
        ) / len(summaries)
        avg_redund = sum(
            s.buckets.get("redundant", BucketResult("redundant")).percentage for s in summaries
        ) / len(summaries)
        avg_drift = sum(
            s.buckets.get("drift", BucketResult("drift")).percentage for s in summaries
        ) / len(summaries)
        avg_disc = sum(
            s.buckets.get("tool_discovery", BucketResult("tool_discovery")).percentage
            for s in summaries
        ) / len(summaries)

        lines.append(
            f"{'AVERAGE':<30}   {avg_tokens:>8,}   {avg_state:>5.1f}%   {avg_redund:>5.1f}%   "
            f"{avg_drift:>5.1f}%   {avg_disc:>4.1f}%"
        )

    lines.append("")

    output = "\n".join(lines)
    if output_path:
        output_path.write_text(output)
        print(f"Wrote per-task bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


def _bucket_by_task_json(
    summaries: List["TaskSummary"],
    output_path: Optional[Path],
) -> int:
    """Output per-task bucket analysis as JSON."""
    import json as json_module

    data = {
        "tasks": [s.to_dict() for s in summaries],
        "summary": {
            "task_count": len(summaries),
            "total_tokens": sum(s.total_tokens for s in summaries),
        },
    }

    output = json_module.dumps(data, indent=2)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote per-task bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


def _bucket_by_task_csv(
    summaries: List["TaskSummary"],
    output_path: Optional[Path],
) -> int:
    """Output per-task bucket analysis as CSV."""
    from .buckets import BucketResult

    lines: List[str] = []

    # Header
    lines.append(
        "task,tokens,state_pct,redundant_pct,drift_pct,discovery_pct,calls,duration_seconds"
    )

    # Data rows
    for s in summaries:
        state_pct = s.buckets.get(
            "state_serialization", BucketResult("state_serialization")
        ).percentage
        redund_pct = s.buckets.get("redundant", BucketResult("redundant")).percentage
        drift_pct = s.buckets.get("drift", BucketResult("drift")).percentage
        disc_pct = s.buckets.get("tool_discovery", BucketResult("tool_discovery")).percentage

        lines.append(
            f'"{s.name}",{s.total_tokens},{state_pct:.2f},{redund_pct:.2f},{drift_pct:.2f},'
            f"{disc_pct:.2f},{s.call_count},{s.duration_seconds:.1f}"
        )

    output = "\n".join(lines)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote per-task bucket analysis to: {output_path}")
    else:
        print(output)

    return 0


# ============================================================================
# Compare Command (v1.0.4 - task-247.16)
# ============================================================================


def cmd_compare(args: argparse.Namespace) -> int:
    """Execute compare command - compare bucket classification across sessions.

    Compares multiple sessions showing bucket distribution for each with
    an AVERAGE row for cross-session analysis.
    """
    from dataclasses import dataclass

    from .buckets import BucketClassifier
    from .session_manager import SessionManager
    from .storage import StorageManager

    @dataclass
    class SessionComparison:
        """Data for a single session in comparison."""

        session_name: str
        total_tokens: int
        state_pct: float
        redundant_pct: float
        drift_pct: float
        discovery_pct: float

    # Validate arguments: either sessions or --latest, not both
    sessions_provided = args.sessions and len(args.sessions) > 0
    latest_provided = args.latest is not None

    if sessions_provided and latest_provided:
        print("Error: Cannot use both positional sessions and --latest flag.")
        print("Use either: token-audit compare file1.json file2.json")
        print("Or: token-audit compare --latest 5")
        return 1

    if not sessions_provided and not latest_provided:
        print("Error: Must provide session files or use --latest flag.")
        print("Examples:")
        print("  token-audit compare session1.json session2.json")
        print("  token-audit compare --latest 5")
        return 1

    # Get session paths
    session_paths: List[Path] = []

    if latest_provided:
        storage = StorageManager()
        platform = normalize_platform(args.platform)
        session_paths = storage.list_sessions(platform=platform, limit=args.latest)

        if not session_paths:
            print("Error: No sessions found. Run 'token-audit collect' first.")
            return 1

        if len(session_paths) < 2:
            print(f"Warning: Only {len(session_paths)} session(s) found. Need 2+ for comparison.")
    else:
        session_paths = args.sessions
        # Validate files exist
        for path in session_paths:
            if not path.exists():
                print(f"Error: Session file not found: {path}")
                return 1

    if len(session_paths) < 1:
        print("Error: Need at least 1 session for analysis.")
        return 1

    # Load and classify each session
    comparisons: List[SessionComparison] = []
    manager = SessionManager()
    classifier = BucketClassifier()

    for session_path in session_paths:
        session = manager.load_session(session_path)
        if not session:
            print(f"Warning: Could not load session: {session_path}")
            continue

        results = classifier.classify_session(session)

        # Extract bucket percentages
        state_pct = 0.0
        redundant_pct = 0.0
        drift_pct = 0.0
        discovery_pct = 0.0

        for result in results:
            if result.bucket == "state_serialization":
                state_pct = result.percentage
            elif result.bucket == "redundant":
                redundant_pct = result.percentage
            elif result.bucket == "drift":
                drift_pct = result.percentage
            elif result.bucket == "tool_discovery":
                discovery_pct = result.percentage

        total_tokens = sum(r.tokens for r in results)

        # Fallback to session token_usage when classifier has no data
        # (older sessions may lack tool_calls detail for bucket classification)
        if total_tokens == 0 and hasattr(session, "token_usage") and session.token_usage:
            total_tokens = session.token_usage.total_tokens

        # Use session timestamp as name, fallback to filename
        session_name = session_path.stem
        if hasattr(session, "timestamp") and session.timestamp:
            session_name = session.timestamp.strftime("%Y-%m-%dT%H-%M-%S")

        comparisons.append(
            SessionComparison(
                session_name=session_name,
                total_tokens=total_tokens,
                state_pct=state_pct,
                redundant_pct=redundant_pct,
                drift_pct=drift_pct,
                discovery_pct=discovery_pct,
            )
        )

    if not comparisons:
        print("Error: No sessions could be loaded.")
        return 1

    # Sort by session name (timestamp)
    comparisons.sort(key=lambda c: c.session_name)

    # Output based on format
    output_format = args.format
    output_path = args.output

    if output_format == "json":
        return _compare_output_json(comparisons, output_path)
    elif output_format == "csv":
        return _compare_output_csv(comparisons, output_path)
    else:  # table
        return _compare_output_table(comparisons, output_path)


def _compare_output_table(
    comparisons: List[Any],
    output_path: Optional[Path],
) -> int:
    """Output session comparison as formatted table."""
    lines: List[str] = []

    lines.append("")
    lines.append("Session Comparison")
    lines.append("\u2550" * 78)

    # Column headers
    lines.append(
        f"{'Session':<30} \u2502 {'Tokens':>8} \u2502 {'State':>6} \u2502 {'Redund':>6} \u2502 {'Drift':>6} \u2502 {'Disc':>5}"
    )
    lines.append(
        "\u2500" * 30
        + "\u253c"
        + "\u2500" * 10
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 8
        + "\u253c"
        + "\u2500" * 7
    )

    # Data rows
    for c in comparisons:
        session_name = c.session_name[:30] if len(c.session_name) > 30 else c.session_name
        lines.append(
            f"{session_name:<30} \u2502 {c.total_tokens:>8,} \u2502 {c.state_pct:>5.1f}% \u2502 "
            f"{c.redundant_pct:>5.1f}% \u2502 {c.drift_pct:>5.1f}% \u2502 {c.discovery_pct:>4.1f}%"
        )

    # Footer with averages
    lines.append(
        "\u2500" * 30
        + "\u2534"
        + "\u2500" * 10
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 8
        + "\u2534"
        + "\u2500" * 7
    )

    if comparisons:
        avg_tokens = sum(c.total_tokens for c in comparisons) // len(comparisons)
        avg_state = sum(c.state_pct for c in comparisons) / len(comparisons)
        avg_redundant = sum(c.redundant_pct for c in comparisons) / len(comparisons)
        avg_drift = sum(c.drift_pct for c in comparisons) / len(comparisons)
        avg_discovery = sum(c.discovery_pct for c in comparisons) / len(comparisons)

        lines.append(
            f"{'AVERAGE':<30}   {avg_tokens:>8,}   {avg_state:>5.1f}%   "
            f"{avg_redundant:>5.1f}%   {avg_drift:>5.1f}%   {avg_discovery:>4.1f}%"
        )

    lines.append("")

    output = "\n".join(lines)
    if output_path:
        output_path.write_text(output)
        print(f"Wrote session comparison to: {output_path}")
    else:
        print(output)

    return 0


def _compare_output_json(
    comparisons: List[Any],
    output_path: Optional[Path],
) -> int:
    """Output session comparison as JSON."""
    import json as json_module

    # Calculate averages
    avg_tokens = sum(c.total_tokens for c in comparisons) // len(comparisons) if comparisons else 0
    avg_state = sum(c.state_pct for c in comparisons) / len(comparisons) if comparisons else 0
    avg_redundant = (
        sum(c.redundant_pct for c in comparisons) / len(comparisons) if comparisons else 0
    )
    avg_drift = sum(c.drift_pct for c in comparisons) / len(comparisons) if comparisons else 0
    avg_discovery = (
        sum(c.discovery_pct for c in comparisons) / len(comparisons) if comparisons else 0
    )

    data = {
        "sessions": [
            {
                "session_name": c.session_name,
                "total_tokens": c.total_tokens,
                "state_serialization_pct": round(c.state_pct, 2),
                "redundant_pct": round(c.redundant_pct, 2),
                "drift_pct": round(c.drift_pct, 2),
                "discovery_pct": round(c.discovery_pct, 2),
            }
            for c in comparisons
        ],
        "averages": {
            "total_tokens": avg_tokens,
            "state_serialization_pct": round(avg_state, 2),
            "redundant_pct": round(avg_redundant, 2),
            "drift_pct": round(avg_drift, 2),
            "discovery_pct": round(avg_discovery, 2),
        },
        "session_count": len(comparisons),
    }

    output = json_module.dumps(data, indent=2)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote session comparison to: {output_path}")
    else:
        print(output)

    return 0


def _compare_output_csv(
    comparisons: List[Any],
    output_path: Optional[Path],
) -> int:
    """Output session comparison as CSV."""
    lines: List[str] = []

    # Header
    lines.append("session,tokens,state_pct,redundant_pct,drift_pct,discovery_pct")

    # Data rows
    for c in comparisons:
        lines.append(
            f'"{c.session_name}",{c.total_tokens},{c.state_pct:.2f},{c.redundant_pct:.2f},'
            f"{c.drift_pct:.2f},{c.discovery_pct:.2f}"
        )

    # Average row
    if comparisons:
        avg_tokens = sum(c.total_tokens for c in comparisons) // len(comparisons)
        avg_state = sum(c.state_pct for c in comparisons) / len(comparisons)
        avg_redundant = sum(c.redundant_pct for c in comparisons) / len(comparisons)
        avg_drift = sum(c.drift_pct for c in comparisons) / len(comparisons)
        avg_discovery = sum(c.discovery_pct for c in comparisons) / len(comparisons)

        lines.append(
            f'"AVERAGE",{avg_tokens},{avg_state:.2f},{avg_redundant:.2f},'
            f"{avg_drift:.2f},{avg_discovery:.2f}"
        )

    output = "\n".join(lines)

    if output_path:
        output_path.write_text(output)
        print(f"Wrote session comparison to: {output_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
