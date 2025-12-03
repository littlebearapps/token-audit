#!/usr/bin/env python3
"""
CodexCLIAdapter - Platform adapter for Codex CLI tracking

Implements BaseTracker for Codex CLI's session JSONL format.
Supports both file-based reading and subprocess wrapper modes.

Session files are stored at: ~/.codex/sessions/YYYY/MM/DD/*.jsonl
"""

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_tracker import BaseTracker
from .pricing_config import PricingConfig

# Human-readable model names for OpenAI models
MODEL_DISPLAY_NAMES: Dict[str, str] = {
    # Codex-specific models
    "gpt-5.1-codex-max": "GPT-5.1 Codex Max",
    "gpt-5-codex": "GPT-5 Codex",
    # GPT-5 Series
    "gpt-5.1": "GPT-5.1",
    "gpt-5-mini": "GPT-5 Mini",
    "gpt-5-nano": "GPT-5 Nano",
    "gpt-5-pro": "GPT-5 Pro",
    # GPT-4.1 Series
    "gpt-4.1": "GPT-4.1",
    "gpt-4.1-mini": "GPT-4.1 Mini",
    "gpt-4.1-nano": "GPT-4.1 Nano",
    # O-Series
    "o4-mini": "O4 Mini",
    "o3-mini": "O3 Mini",
    "o1-preview": "O1 Preview",
    "o1-mini": "O1 Mini",
    # GPT-4o Series
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini",
}

# Default exchange rate (used if not in config)
DEFAULT_USD_TO_AUD = 1.54


class CodexCLIAdapter(BaseTracker):
    """
    Codex CLI platform adapter.

    Supports two modes:
    1. File-based: Reads session JSONL files from ~/.codex/sessions/
    2. Subprocess: Wraps `codex` command and monitors stdout (legacy)

    Usage:
        # File-based mode (recommended)
        adapter = CodexCLIAdapter(project="my-project")
        adapter.start_tracking()  # Monitors latest session file

        # Process specific session file
        adapter = CodexCLIAdapter(project="my-project")
        adapter.process_session_file_batch(Path("~/.codex/sessions/..."))

        # Subprocess mode (legacy)
        adapter = CodexCLIAdapter(project="my-project", subprocess_mode=True)
        adapter.start_tracking()  # Launches codex as subprocess
    """

    def __init__(
        self,
        project: str,
        codex_dir: Optional[Path] = None,
        session_file: Optional[Path] = None,
        subprocess_mode: bool = False,
        codex_args: list[str] | None = None,
    ):
        """
        Initialize Codex CLI adapter.

        Args:
            project: Project name (e.g., "mcp-audit")
            codex_dir: Codex config directory (default: ~/.codex)
            session_file: Specific session file to read (overrides auto-detection)
            subprocess_mode: Use subprocess wrapper instead of file reading
            codex_args: Additional arguments to pass to codex command (subprocess mode only)
        """
        super().__init__(project=project, platform="codex-cli")

        self.codex_dir = codex_dir or Path.home() / ".codex"
        self._session_file = session_file
        self.subprocess_mode = subprocess_mode
        self.codex_args = codex_args or []

        self.detected_model: Optional[str] = None
        self.model_name: str = "Unknown Model"
        self.process: Optional[subprocess.Popen[str]] = None

        # Initialize pricing config for cost calculation
        self._pricing_config = PricingConfig()
        self._usd_to_aud = DEFAULT_USD_TO_AUD
        if self._pricing_config.loaded:
            rates = self._pricing_config.metadata.get("exchange_rates", {})
            self._usd_to_aud = rates.get("USD_to_AUD", DEFAULT_USD_TO_AUD)

        # File monitoring state
        self._processed_lines: int = 0
        self._last_file_mtime: float = 0.0
        self._has_received_events: bool = False

        # Session metadata from session_meta event
        self.session_cwd: Optional[str] = None
        self.cli_version: Optional[str] = None
        self.git_info: Optional[Dict[str, Any]] = None

    # ========================================================================
    # Session File Discovery (Task 60.9)
    # ========================================================================

    def get_sessions_directory(self) -> Path:
        """Get the base sessions directory."""
        return self.codex_dir / "sessions"

    def get_session_files(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Path]:
        """
        Get all session files, optionally filtered by date range.

        Args:
            since: Only include sessions after this datetime
            until: Only include sessions before this datetime

        Returns:
            List of session file paths sorted by modification time (newest first)
        """
        sessions_dir = self.get_sessions_directory()
        if not sessions_dir.exists():
            return []

        session_files = []

        # Walk the YYYY/MM/DD directory structure
        for year_dir in sessions_dir.iterdir():
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue

            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue

                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir() or not day_dir.name.isdigit():
                        continue

                    # Apply date filter if specified
                    if since or until:
                        try:
                            dir_date = datetime(
                                int(year_dir.name),
                                int(month_dir.name),
                                int(day_dir.name),
                            )
                            if since and dir_date.date() < since.date():
                                continue
                            if until and dir_date.date() > until.date():
                                continue
                        except ValueError:
                            continue

                    # Collect JSONL files
                    for jsonl_file in day_dir.glob("*.jsonl"):
                        session_files.append(jsonl_file)

        # Sort by modification time (newest first)
        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return session_files

    def get_latest_session_file(self) -> Optional[Path]:
        """Get the most recently modified session file."""
        if self._session_file:
            return self._session_file

        session_files = self.get_session_files()
        return session_files[0] if session_files else None

    def list_sessions(
        self,
        limit: int = 10,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[Tuple[Path, datetime, Optional[str]]]:
        """
        List available sessions with metadata.

        Args:
            limit: Maximum number of sessions to return
            since: Only include sessions after this datetime
            until: Only include sessions before this datetime

        Returns:
            List of (path, mtime, session_id) tuples
        """
        session_files = self.get_session_files(since=since, until=until)[:limit]

        results = []
        for path in session_files:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)

            # Try to extract session ID from first line
            session_id = None
            try:
                with open(path) as f:
                    first_line = f.readline()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("type") == "session_meta":
                            session_id = data.get("payload", {}).get("id")
            except (json.JSONDecodeError, OSError):
                pass

            results.append((path, mtime, session_id))

        return results

    # ========================================================================
    # Session Parsing
    # ========================================================================

    def iter_session_events(self, file_path: Path) -> Iterator[Dict[str, Any]]:
        """
        Iterate over events in a session JSONL file.

        Args:
            file_path: Path to session JSONL file

        Yields:
            Parsed JSON event dictionaries
        """
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    # ========================================================================
    # Abstract Method Implementations
    # ========================================================================

    def start_tracking(self) -> None:
        """
        Start tracking Codex CLI session.

        Uses file-based monitoring by default, or subprocess mode if enabled.
        """
        if self.subprocess_mode:
            self._start_subprocess_tracking()
        else:
            self._start_file_tracking()

    def _start_file_tracking(self) -> None:
        """Start file-based session monitoring."""
        print(f"[Codex CLI] Initializing tracker for: {self.project}")

        # Find session file
        session_file = self.get_latest_session_file()
        if not session_file:
            print("[Codex CLI] No session files found.")
            print(f"[Codex CLI] Expected at: {self.codex_dir}/sessions/YYYY/MM/DD/")

            # List recent sessions if any exist
            recent = self.list_sessions(limit=5)
            if recent:
                print("[Codex CLI] Available sessions:")
                for path, mtime, _sid in recent:
                    print(f"  - {path.name} ({mtime.strftime('%Y-%m-%d %H:%M')})")
            return

        print(f"[Codex CLI] Monitoring: {session_file}")
        self.session.source_files = [session_file.name]

        print("[Codex CLI] Tracking started. Press Ctrl+C to stop.")

        # Main monitoring loop
        while True:
            try:
                self._process_session_file(session_file)
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n[Codex CLI] Stopping tracker...")
                break

    def _start_subprocess_tracking(self) -> None:
        """Start subprocess-based session monitoring (legacy mode)."""
        print(f"[Codex CLI] Starting tracker for project: {self.project}")
        print(f"[Codex CLI] Launching codex with args: {self.codex_args}")

        # Launch codex as subprocess
        self.process = subprocess.Popen(
            ["codex"] + self.codex_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        print("[Codex CLI] Process started. Monitoring output...")

        # Monitor output
        try:
            assert self.process.stdout is not None, "Process stdout is None"
            while True:
                line = self.process.stdout.readline()
                if not line:
                    if self._has_received_events:
                        self.session.source_files = ["codex:stdout"]
                    break

                result = self.parse_event(line)
                if result:
                    self._has_received_events = True
                    tool_name, usage = result
                    self._process_tool_call(tool_name, usage)

        except KeyboardInterrupt:
            print("\n[Codex CLI] Stopping tracker...")
            if self._has_received_events:
                self.session.source_files = ["codex:stdout"]
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)

    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse Codex CLI output event.

        Codex CLI outputs JSONL with event types:
        - session_meta: Session metadata
        - turn_context: Contains model information
        - event_msg with payload.type="token_count": Token usage
        - response_item with payload.type="function_call": Tool calls (including MCP)

        Args:
            event_data: Text line from codex stdout/stderr or session JSONL,
                       or pre-parsed dict from file iteration

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tool calls, or
            Tuple of ("__session__", usage_dict) for token usage events
        """
        try:
            # Handle both string input and pre-parsed dict
            if isinstance(event_data, dict):
                data = event_data
            else:
                line = str(event_data).strip()
                if not line:
                    return None
                data = json.loads(line)

            event_type = data.get("type", "")
            payload = data.get("payload", {})

            # Handle session_meta events
            if event_type == "session_meta":
                self._parse_session_meta(payload)
                return None

            # Handle turn_context events for model detection
            if event_type == "turn_context":
                self._parse_turn_context(payload)
                return None

            # Handle token_count events for token usage
            if event_type == "event_msg" and payload.get("type") == "token_count":
                return self._parse_token_count(payload)

            # Handle function_call events for MCP tool calls
            if event_type == "response_item" and payload.get("type") == "function_call":
                return self._parse_function_call(payload)

            return None

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.handle_unrecognized_line(f"Parse error: {e}")
            return None

    def _parse_session_meta(self, payload: Dict[str, Any]) -> None:
        """Parse session_meta event for session metadata."""
        self.session_cwd = payload.get("cwd")
        self.cli_version = payload.get("cli_version")
        self.git_info = payload.get("git")

        # Update session working directory
        if self.session_cwd:
            self.session.working_directory = self.session_cwd

    def _parse_turn_context(self, payload: Dict[str, Any]) -> None:
        """
        Parse turn_context event for model detection.

        Args:
            payload: The event payload containing model info
        """
        if self.detected_model:
            return None

        model_id = payload.get("model")
        if model_id:
            self.detected_model = model_id
            self.model_name = MODEL_DISPLAY_NAMES.get(model_id, model_id)
            self.session.model = model_id

        return None

    def _parse_token_count(self, payload: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse token_count event for token usage.

        Codex CLI provides both total_token_usage (cumulative) and
        last_token_usage (delta). We use last_token_usage for incremental tracking.

        Args:
            payload: The event payload with token info

        Returns:
            Tuple of ("__session__", usage_dict) with token data
        """
        info = payload.get("info")
        if not info:
            return None

        # Use last_token_usage for incremental tracking (delta from last event)
        # Fall back to total_token_usage if last not available
        usage = info.get("last_token_usage") or info.get("total_token_usage", {})

        if not usage:
            return None

        # Codex CLI token field names
        usage_dict = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0)
            + usage.get("reasoning_output_tokens", 0),
            "cache_created_tokens": 0,  # Codex doesn't have cache creation
            "cache_read_tokens": usage.get("cached_input_tokens", 0),
        }

        total_tokens = sum(usage_dict.values())
        if total_tokens > 0:
            return ("__session__", usage_dict)

        return None

    def _parse_function_call(self, payload: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse function_call event for MCP tool calls.

        Only returns events for MCP tools (name starts with "mcp__").

        Args:
            payload: The event payload with tool call info

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tool calls
        """
        tool_name = payload.get("name", "")

        # Only track MCP tools
        if not tool_name.startswith("mcp__"):
            return None

        # Parse arguments if available
        arguments_str = payload.get("arguments", "{}")
        try:
            tool_params = json.loads(arguments_str)
        except json.JSONDecodeError:
            tool_params = {}

        # MCP tool calls don't include token usage directly
        # Tokens are tracked separately via token_count events
        usage_dict = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "tool_params": tool_params,
            "call_id": payload.get("call_id"),
        }

        return (tool_name, usage_dict)

    def get_platform_metadata(self) -> Dict[str, Any]:
        """Get Codex CLI platform metadata."""
        return {
            "model": self.detected_model,
            "model_name": self.model_name,
            "codex_dir": str(self.codex_dir),
            "codex_args": self.codex_args,
            "process_id": self.process.pid if self.process else None,
            "cli_version": self.cli_version,
            "session_cwd": self.session_cwd,
            "git_info": self.git_info,
        }

    # ========================================================================
    # File Monitoring (Task 60.8)
    # ========================================================================

    def _process_session_file(self, file_path: Path) -> None:
        """Read and process session file for new events."""
        if not file_path.exists():
            return

        # Check if file was modified
        current_mtime = file_path.stat().st_mtime
        if current_mtime == self._last_file_mtime:
            return

        self._last_file_mtime = current_mtime

        try:
            with open(file_path) as f:
                # Skip already processed lines
                for _ in range(self._processed_lines):
                    f.readline()

                # Process new lines
                line_count = self._processed_lines
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            result = self.parse_event(event)
                            if result:
                                self._has_received_events = True
                                tool_name, usage = result
                                self._process_tool_call(tool_name, usage)
                        except json.JSONDecodeError:
                            pass
                    line_count += 1

                self._processed_lines = line_count

        except OSError as e:
            self.handle_unrecognized_line(f"Error reading session file: {e}")

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _process_tool_call(self, tool_name: str, usage: Dict[str, Any]) -> None:
        """
        Process a single tool call or session event.

        Args:
            tool_name: MCP tool name or "__session__" for non-MCP events
            usage: Token usage dictionary
        """
        total_tokens = (
            usage["input_tokens"]
            + usage["output_tokens"]
            + usage["cache_created_tokens"]
            + usage["cache_read_tokens"]
        )

        # Handle session-level token tracking (non-MCP events)
        if tool_name == "__session__":
            self.session.token_usage.input_tokens += usage["input_tokens"]
            self.session.token_usage.output_tokens += usage["output_tokens"]
            self.session.token_usage.cache_created_tokens += usage["cache_created_tokens"]
            self.session.token_usage.cache_read_tokens += usage["cache_read_tokens"]
            self.session.token_usage.total_tokens += total_tokens

            # Recalculate cache efficiency
            total_input = (
                self.session.token_usage.input_tokens
                + self.session.token_usage.cache_created_tokens
                + self.session.token_usage.cache_read_tokens
            )
            if total_input > 0:
                self.session.token_usage.cache_efficiency = (
                    self.session.token_usage.cache_read_tokens / total_input
                )
            return

        # Extract tool parameters for duplicate detection
        tool_params = usage.get("tool_params", {})
        content_hash = None
        if tool_params:
            content_hash = self.compute_content_hash(tool_params)

        # Get platform metadata
        platform_data = {"model": self.detected_model, "model_name": self.model_name}

        # Record tool call using BaseTracker
        self.record_tool_call(
            tool_name=tool_name,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_created_tokens=usage["cache_created_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            duration_ms=0,  # Codex CLI doesn't provide duration
            content_hash=content_hash,
            platform_data=platform_data,
        )

    # ========================================================================
    # Batch Processing (for report generation)
    # ========================================================================

    def process_session_file_batch(self, file_path: Path) -> None:
        """
        Process a complete session file in batch mode (no live monitoring).

        Used for generating reports from existing session files.

        Args:
            file_path: Path to session JSONL file
        """
        self.session.source_files = [file_path.name]

        # Get file timestamps (use timezone-aware datetime for consistency)
        stat = file_path.stat()
        self.session.timestamp = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # Process all events
        for event in self.iter_session_events(file_path):
            result = self.parse_event(event)
            if result:
                tool_name, usage = result
                self._process_tool_call(tool_name, usage)


# ============================================================================
# Standalone Execution
# ============================================================================


def main() -> int:
    """Main entry point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Codex CLI MCP Tracker",
        epilog="All arguments after -- are passed to codex command (subprocess mode)",
    )
    parser.add_argument("--project", default="mcp-audit", help="Project name")
    parser.add_argument(
        "--codex-dir",
        type=Path,
        default=None,
        help="Codex config directory (default: ~/.codex)",
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        default=None,
        help="Specific session file to process",
    )
    parser.add_argument(
        "--output",
        default=str(Path.home() / ".mcp-audit" / "sessions"),
        help="Output directory for session logs (default: ~/.mcp-audit/sessions)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process session file in batch mode (no live monitoring)",
    )
    parser.add_argument(
        "--subprocess",
        action="store_true",
        help="Use subprocess wrapper mode instead of file reading",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Auto-select the most recent session file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sessions and exit",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Only include sessions after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="Only include sessions before this date (YYYY-MM-DD)",
    )

    # Parse known args, rest go to codex
    args, codex_args = parser.parse_known_args()

    # Parse date filters
    since = None
    until = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")
    if args.until:
        until = datetime.strptime(args.until, "%Y-%m-%d")

    # Create adapter
    adapter = CodexCLIAdapter(
        project=args.project,
        codex_dir=args.codex_dir,
        session_file=args.session_file,
        subprocess_mode=args.subprocess,
        codex_args=codex_args,
    )

    # List mode
    if args.list:
        print("Available Codex CLI sessions:")
        print("-" * 80)
        sessions = adapter.list_sessions(limit=20, since=since, until=until)
        if not sessions:
            print("  No sessions found")
        else:
            for path, mtime, sid in sessions:
                sid_str = f" ({sid[:8]}...)" if sid else ""
                print(f"  {mtime.strftime('%Y-%m-%d %H:%M:%S')}{sid_str}")
                print(f"    {path}")
        return 0

    print(f"Starting Codex CLI tracker for project: {args.project}")

    try:
        if args.batch and args.session_file:
            # Batch mode - process file without monitoring
            adapter.process_session_file_batch(args.session_file)
            session = adapter.finalize_session()
        elif args.batch and args.latest:
            # Batch mode with latest file
            latest = adapter.get_latest_session_file()
            if latest:
                adapter.process_session_file_batch(latest)
                session = adapter.finalize_session()
            else:
                print("No session files found")
                return 1
        else:
            # Live monitoring mode
            adapter.start_tracking()
            session = adapter.finalize_session()
    except KeyboardInterrupt:
        print("\nStopping tracker...")
        session = adapter.finalize_session()

    # Save session data
    output_dir = Path(args.output)
    adapter.save_session(output_dir)

    print(f"\nSession saved to: {adapter.session_dir}")
    print(f"Total tokens: {session.token_usage.total_tokens:,}")
    print(f"MCP calls: {session.mcp_tool_calls.total_calls}")
    print(f"Cache efficiency: {session.token_usage.cache_efficiency:.1%}")
    if adapter.detected_model:
        print(f"Model: {adapter.model_name}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
