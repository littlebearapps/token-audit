#!/usr/bin/env python3
"""
CodexCLIAdapter - Platform adapter for Codex CLI tracking

Implements BaseTracker for Codex CLI's session JSONL format.
Supports both file-based reading and subprocess wrapper modes.

Session files are stored at: ~/.codex/sessions/YYYY/MM/DD/*.jsonl
"""

import contextlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from .base_tracker import BaseTracker, DataQuality
from .pricing_config import PricingConfig
from .token_estimator import TokenEstimator

if TYPE_CHECKING:
    from .display import DisplayAdapter, DisplaySnapshot

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

# Codex CLI built-in tools - from official source:
# https://github.com/openai/codex/tree/main/codex-rs/core/src/tools/handlers
CODEX_BUILTIN_TOOLS: set[str] = {
    "shell",  # Main shell execution (ShellHandler)
    "shell_command",  # Alternative shell command (ShellCommandHandler)
    "apply_patch",  # File patching (ApplyPatchHandler)
    "grep_files",  # File search (GrepFilesHandler)
    "list_dir",  # Directory listing (ListDirHandler)
    "read_file",  # File reading (ReadFileHandler)
    "view_image",  # Image viewing (ViewImageHandler)
    "exec",  # Unified execution (UnifiedExecHandler)
    "update_plan",  # Task planning (PlanHandler)
    "list_mcp_resources",  # MCP resource discovery
    "list_mcp_resource_templates",  # MCP resource templates
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
        from_start: bool = False,
    ):
        """
        Initialize Codex CLI adapter.

        Args:
            project: Project name (e.g., "token-audit")
            codex_dir: Codex config directory (default: ~/.codex)
            session_file: Specific session file to read (overrides auto-detection)
            subprocess_mode: Use subprocess wrapper instead of file reading
            codex_args: Additional arguments to pass to codex command (subprocess mode only)
            from_start: If True, process entire session from start. If False (default),
                        only track new events written after token-audit starts.
        """
        super().__init__(project=project, platform="codex-cli")

        self.codex_dir = codex_dir or Path.home() / ".codex"
        self._session_file = session_file
        self.subprocess_mode = subprocess_mode
        self.codex_args = codex_args or []
        self._from_start = from_start

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

        # Built-in tool tracking (task-68.3)
        # Tracks Codex CLI built-in tools like shell_command, update_plan, etc.
        self._builtin_tool_counts: Dict[str, int] = {}
        self._builtin_tool_total_calls: int = 0

        # Pending tool calls for duration tracking (task-68.5) and token estimation (task-69.8)
        # Maps call_id to tool call info, waiting for function_call_output
        self._pending_tool_calls: Dict[str, Dict[str, Any]] = {}

        # Token estimator for MCP tool calls (task-69.8)
        # Codex CLI uses tiktoken o200k_base for ~99-100% accuracy
        self._estimator = TokenEstimator.for_platform("codex-cli")

        # Token estimation tracking (task-69.10)
        # Counts MCP tool calls that use estimated tokens
        self._estimated_tool_calls: int = 0

        # Data quality (v1.5.0 - task-103.5)
        # Codex CLI: Session tokens are native from API, MCP tool tokens are estimated
        # We report "estimated" because MCP tool breakdowns use tiktoken
        self.session.data_quality = DataQuality(
            accuracy_level="estimated",
            token_source="tiktoken",
            token_encoding=self._estimator.encoding_name,  # e.g., "o200k_base"
            confidence=0.99,  # tiktoken o200k_base is ~99-100% accurate for OpenAI
            notes="Session totals native from API; MCP tool breakdown estimated via tiktoken",
        )

        # MCP config path for static cost (v0.6.0 - task-114.2)
        # Codex CLI uses ~/.codex/config.toml
        mcp_config = self.codex_dir / "config.toml"
        if mcp_config.exists():
            self.set_mcp_config_path(mcp_config)

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

    def monitor(self, display: Optional["DisplayAdapter"] = None) -> None:
        """
        Main monitoring loop with display integration.

        Args:
            display: Optional DisplayAdapter for real-time UI updates
        """
        self._display = display
        self._start_time = datetime.now()
        self._last_display_update = 0.0

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

        # Auto-detect completed sessions (v0.9.1 - #68)
        # If session file is stale (>5 seconds old) and has data, auto-enable from_start
        if not self._from_start:
            file_mtime = session_file.stat().st_mtime
            file_age_seconds = time.time() - file_mtime
            if file_age_seconds > 5:
                with open(session_file) as f:
                    line_count = sum(1 for _ in f)
                if line_count > 0:
                    print(
                        f"[Codex CLI] Auto-detected completed session "
                        f"({line_count} lines, {file_age_seconds:.0f}s old)"
                    )
                    self._from_start = True

        # Initialize file position based on from_start flag
        if not self._from_start:
            # Skip to end - only track NEW events
            with open(session_file) as f:
                self._processed_lines = sum(1 for _ in f)
            print(
                f"[Codex CLI] Tracking NEW events only (skipped {self._processed_lines} existing lines)"
            )
        else:
            print("[Codex CLI] Processing from start (--from-start)")

        print("[Codex CLI] Tracking started. Press Ctrl+C to stop.")

        # Main monitoring loop with display updates
        while True:
            try:
                self._process_session_file(session_file)

                # Update display periodically (every 0.5 seconds)
                if display:
                    now = time.time()
                    if now - self._last_display_update >= 0.5:
                        self._last_display_update = now
                        snapshot = self._build_display_snapshot()
                        result = display.update(snapshot)
                        # Handle [Q] quit keybinding (v0.7.0 - task-105.8)
                        if result == "quit":
                            print("\n[Codex CLI] Stopping tracker...")
                            break

                time.sleep(0.2)

            except KeyboardInterrupt:
                print("\n[Codex CLI] Stopping tracker...")
                break

    def _build_display_snapshot(self) -> "DisplaySnapshot":
        """Build DisplaySnapshot from current session state."""
        from .display import DisplaySnapshot

        # Calculate duration
        duration_seconds = (datetime.now() - self._start_time).total_seconds()

        # Get token usage
        usage = self.session.token_usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_created = usage.cache_created_tokens
        cache_read = usage.cache_read_tokens
        total_tokens = usage.total_tokens

        # Calculate cache efficiency
        total_input = input_tokens + cache_created + cache_read
        cache_efficiency = cache_read / total_input if total_input > 0 else 0.0

        # Build top tools list (use self.server_sessions for live tracking - task-66.9)
        # Exclude "builtin" pseudo-server from MCP stats (task-69.32.1)
        top_tools = []
        total_mcp_calls = 0
        for server_name, server_session in self.server_sessions.items():
            # Skip builtin pseudo-server - these are tracked separately (task-69.32.1)
            if server_name == "builtin":
                continue
            total_mcp_calls += server_session.total_calls
            for tool_name, tool_stats in server_session.tools.items():
                avg_tokens = (
                    tool_stats.total_tokens // tool_stats.calls if tool_stats.calls > 0 else 0
                )
                top_tools.append((tool_name, tool_stats.calls, tool_stats.total_tokens, avg_tokens))
        top_tools.sort(key=lambda x: x[2], reverse=True)

        # Get pricing for cost calculation
        pricing = PricingConfig()
        model_id = self.detected_model or ""

        # Calculate costs
        # NOTE: For OpenAI/Codex API, input_tokens INCLUDES cache_read_tokens as a subset.
        # So: non_cached_input = input_tokens - cache_read_tokens (task-69.32.2)
        cost_with_cache = 0.0
        cost_without_cache = 0.0
        if pricing.loaded and model_id:
            # Cost with cache: charge non-cached at input_rate, cached at cache_rate
            non_cached_input = input_tokens - cache_read
            cost_with_cache = pricing.calculate_cost(
                model_id, non_cached_input, output_tokens, cache_created, cache_read
            )
            # Cost without cache: all input at full input_rate (no cache_read)
            # input_tokens already represents total input, so no addition needed
            cost_without_cache = pricing.calculate_cost(model_id, input_tokens, output_tokens, 0, 0)

            # Save costs to session for persistence (task-66.8)
            self.session.cost_estimate = cost_with_cache
            self.session.cost_no_cache = cost_without_cache
            self.session.cache_savings_usd = cost_without_cache - cost_with_cache

        # Build server hierarchy for live TUI display (task-68.1)
        # Exclude "builtin" pseudo-server - built-in tools are shown separately (task-69.32.1)
        server_hierarchy: List[Tuple[str, int, int, int, List[Tuple[str, int, int, float]]]] = []
        for server_name, server_session in self.server_sessions.items():
            # Skip builtin pseudo-server - these are tracked in builtin_tool_calls (task-69.32.1)
            if server_name == "builtin":
                continue
            server_calls = server_session.total_calls
            server_tokens = server_session.total_tokens
            server_avg = server_tokens // server_calls if server_calls > 0 else 0

            # Build tools list for this server
            tools_list: List[Tuple[str, int, int, float]] = []
            for tool_name, tool_stats in server_session.tools.items():
                # Extract short name (remove mcp__server__ prefix)
                short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
                tool_pct = (
                    (tool_stats.total_tokens / server_tokens * 100) if server_tokens > 0 else 0.0
                )
                tools_list.append((short_name, tool_stats.calls, tool_stats.total_tokens, tool_pct))

            server_hierarchy.append(
                (server_name, server_calls, server_tokens, server_avg, tools_list)
            )

        return DisplaySnapshot.create(
            project=self.project,
            platform="codex-cli",
            start_time=self._start_time,
            duration_seconds=duration_seconds,
            model_id=self.detected_model or "",
            model_name=self.model_name,
            message_count=self.session.message_count,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_created_tokens=cache_created,
            cache_read_tokens=cache_read,
            reasoning_tokens=usage.reasoning_tokens,  # v1.3.0: Codex reasoning_output_tokens
            cache_tokens=cache_created + cache_read,
            cache_efficiency=cache_efficiency,
            total_tool_calls=total_mcp_calls,  # Use computed value for live tracking (task-66.9)
            top_tools=top_tools[:10],
            cost_estimate=cost_with_cache,
            cost_no_cache=cost_without_cache,
            cache_savings=cost_without_cache - cost_with_cache,
            savings_percent=(
                ((cost_without_cache - cost_with_cache) / cost_without_cache * 100)
                if cost_without_cache > 0
                else 0.0
            ),
            tracking_mode="full" if self._from_start else "live",
            # Built-in tool tracking (task-68.3)
            builtin_tool_calls=self._builtin_tool_total_calls,
            builtin_tool_tokens=0,  # Codex CLI doesn't provide per-tool tokens
            # Server hierarchy for live TUI (task-68.1)
            server_hierarchy=server_hierarchy,
            # Token estimation tracking (task-69.10)
            estimated_tool_calls=self._estimated_tool_calls,
            estimation_method=self._estimator.method_name,
            estimation_encoding=self._estimator.encoding_name,
            # Data quality (v1.5.0 - task-103.5)
            accuracy_level="estimated",
            token_source="tiktoken",
            data_quality_confidence=0.99,  # tiktoken o200k_base ~99% accuracy
            # Multi-model tracking (v1.6.0 - task-108.2.4)
            models_used=self.session.models_used if self.session.models_used else None,
            model_usage=self._convert_model_usage_for_snapshot(),
            is_multi_model=len(self.session.models_used) > 1,
            # Static cost / context tax (v0.6.0 - task-114.3)
            static_cost_total=(
                self.session.static_cost.total_tokens if self.session.static_cost else 0
            ),
            static_cost_by_server=(
                list(self.session.static_cost.by_server.items())
                if self.session.static_cost
                else None
            ),
            static_cost_source=(
                self.session.static_cost.source if self.session.static_cost else "none"
            ),
            static_cost_confidence=(
                self.session.static_cost.confidence if self.session.static_cost else 0.0
            ),
            zombie_context_tax=0,  # TODO: Calculate from schema_analyzer
        )

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

        # Auto-detect completed sessions (v0.9.1 - #68)
        # If session file is stale (>5 seconds old) and has data, auto-enable from_start
        if not self._from_start:
            file_mtime = session_file.stat().st_mtime
            file_age_seconds = time.time() - file_mtime
            if file_age_seconds > 5:
                with open(session_file) as f:
                    line_count = sum(1 for _ in f)
                if line_count > 0:
                    print(
                        f"[Codex CLI] Auto-detected completed session "
                        f"({line_count} lines, {file_age_seconds:.0f}s old)"
                    )
                    self._from_start = True

        # Initialize file position based on from_start flag
        if not self._from_start:
            # Skip to end - only track NEW events
            with open(session_file) as f:
                self._processed_lines = sum(1 for _ in f)
            print(
                f"[Codex CLI] Tracking NEW events only (skipped {self._processed_lines} existing lines)"
            )
        else:
            print("[Codex CLI] Processing from start (--from-start)")

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

            # Handle function_call_output events for tool duration (task-68.5)
            if event_type == "response_item" and payload.get("type") == "function_call_output":
                return self._parse_function_call_output(payload)

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
        Parse turn_context event for model detection and message counting.

        Each turn_context event represents a new conversation turn (assistant response).

        Args:
            payload: The event payload containing model info
        """
        # Count each turn_context as a message (assistant turn)
        self.session.message_count += 1

        # Only set model once (first turn_context with model info)
        if not self.detected_model:
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
        last_token_usage (delta). We use total_token_usage (cumulative) because
        Codex CLI native logs contain duplicate events that would cause
        double-counting if we summed last_token_usage values.

        The cumulative values are used to REPLACE session totals (not add).

        Args:
            payload: The event payload with token info

        Returns:
            Tuple of ("__session__", usage_dict) with cumulative token data
        """
        info = payload.get("info")
        if not info:
            return None

        # Use total_token_usage (cumulative) to avoid double-counting from
        # duplicate events in Codex CLI native logs. See Task 79 for details.
        usage = info.get("total_token_usage", {})

        if not usage:
            return None

        # Codex CLI token field names
        # v1.3.0: Keep reasoning_tokens separate (previously combined into output_tokens)
        usage_dict = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),  # v1.3.0: No longer includes reasoning
            "cache_created_tokens": 0,  # Codex doesn't have cache creation
            "cache_read_tokens": usage.get("cached_input_tokens", 0),
            "reasoning_tokens": usage.get("reasoning_output_tokens", 0),  # v1.3.0: Separate field
        }

        total_tokens = sum(usage_dict.values())
        if total_tokens > 0:
            return ("__session__", usage_dict)

        return None

    def _parse_function_call(self, payload: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse function_call event for tool calls.

        Handles both MCP tools (name starts with "mcp__") and built-in tools.
        Both are stored pending until function_call_output provides the result
        for token estimation (task-69.8, task-69.24).

        Per Task 69 validated plan: "Built-in vs MCP Tools: No difference in accuracy
        approach. Both are function calls to the model and use the same estimation method."

        Args:
            payload: The event payload with tool call info

        Returns:
            None - All tool calls are recorded when function_call_output is received
        """
        tool_name = payload.get("name", "")
        call_id = payload.get("call_id")

        is_builtin = not tool_name.startswith("mcp__")

        # Track built-in tool counters (task-68.3, task-78)
        if is_builtin:
            if tool_name not in self._builtin_tool_counts:
                self._builtin_tool_counts[tool_name] = 0
            self._builtin_tool_counts[tool_name] += 1
            self._builtin_tool_total_calls += 1

            # Initialize session's builtin_tool_stats for persistence (task-78)
            # Token count will be updated when function_call_output arrives (task-69.24)
            if tool_name not in self.session.builtin_tool_stats:
                self.session.builtin_tool_stats[tool_name] = {"calls": 0, "tokens": 0}
            self.session.builtin_tool_stats[tool_name]["calls"] += 1

        # Get arguments string for token estimation (task-69.8, task-69.24)
        arguments_str = payload.get("arguments", "{}")

        # Store call info for token estimation when function_call_output arrives
        # Both MCP and built-in tools need estimation (task-69.24)
        if call_id:
            self._pending_tool_calls[call_id] = {
                "tool_name": tool_name,
                "arguments_str": arguments_str,  # Store raw args for estimation
                "is_builtin": is_builtin,  # Track for correct routing in output handler
            }

        # Don't record yet - wait for function_call_output for token estimation
        return None

    def _parse_function_call_output(
        self, payload: Dict[str, Any]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse function_call_output event for token estimation (task-69.8, task-69.24).

        This is where tool calls are recorded, once we have both arguments
        (from function_call) and result (from this event) for accurate token estimation.

        Token estimation uses tiktoken o200k_base encoding for ~99-100% accuracy
        with OpenAI/Codex models. Both MCP and built-in tools are estimated.

        Args:
            payload: The event payload with output and call_id

        Returns:
            Tuple of (tool_name, usage_dict) with estimated tokens for all tools,
            None if no matching pending call
        """
        call_id = payload.get("call_id")

        # Must have a matching pending call to process
        if not call_id or call_id not in self._pending_tool_calls:
            return None

        pending = self._pending_tool_calls.pop(call_id)
        tool_name = pending["tool_name"]
        arguments_str = pending.get("arguments_str", "{}")
        is_builtin = pending.get("is_builtin", False)

        # Get output/result for estimation
        output = payload.get("output", "")

        # Handle output being a list (some Codex CLI events have list outputs)
        if isinstance(output, list):
            output = json.dumps(output)
        elif not isinstance(output, str):
            output = str(output) if output else ""

        # Extract wall time from output (task-68.5)
        duration_ms = 0
        match = re.search(r"Wall time:\s*([\d.]+)\s*seconds?", output)
        if match:
            with contextlib.suppress(ValueError):
                duration_ms = int(float(match.group(1)) * 1000)

        # Estimate tokens from arguments and result (task-69.8, task-69.24)
        input_tokens, output_tokens = self._estimator.estimate_tool_call(arguments_str, output)

        # Track estimated tool calls for TUI display (task-69.10)
        self._estimated_tool_calls += 1

        # Update builtin_tool_stats with estimated tokens (task-69.24)
        if is_builtin and tool_name in self.session.builtin_tool_stats:
            self.session.builtin_tool_stats[tool_name]["tokens"] += input_tokens + output_tokens

        # Parse tool params for duplicate detection
        try:
            tool_params = json.loads(arguments_str)
        except json.JSONDecodeError:
            tool_params = {}

        # Build usage dict with estimated tokens
        usage_dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_created_tokens": 0,  # Codex doesn't have cache creation
            "cache_read_tokens": 0,  # Codex caching tracked at session level
            "tool_params": tool_params,
            "call_id": call_id,
            "duration_ms": duration_ms,
            # Token estimation metadata (v1.4.0)
            "is_estimated": True,
            "estimation_method": self._estimator.method_name,
            "estimation_encoding": self._estimator.encoding_name,
        }

        # Return with correct prefix for built-in vs MCP tools (task-69.24)
        if is_builtin:
            return (f"__builtin__:{tool_name}", usage_dict)
        return (tool_name, usage_dict)

    def _update_call_duration(self, tool_name: str, call_id: str, duration_ms: int) -> None:
        """
        Update duration for a recorded tool call (task-68.5).

        Searches server_sessions for the matching call and updates its duration.

        Args:
            tool_name: The MCP tool name
            call_id: The call ID to match
            duration_ms: Duration in milliseconds
        """
        if duration_ms <= 0:
            return

        # Normalize tool name to match how it was recorded
        normalized_tool = self.normalize_tool_name(tool_name)
        server_name = self.normalize_server_name(normalized_tool)

        if server_name not in self.server_sessions:
            return

        server_session = self.server_sessions[server_name]
        if normalized_tool not in server_session.tools:
            return

        tool_stats = server_session.tools[normalized_tool]

        # Find the call by call_id and update duration
        for call in tool_stats.call_history:
            if call.platform_data and call.platform_data.get("call_id") == call_id:
                call.duration_ms = duration_ms
                # Update tool stats
                if tool_stats.total_duration_ms is None:
                    tool_stats.total_duration_ms = 0
                tool_stats.total_duration_ms += duration_ms
                tool_stats.avg_duration_ms = tool_stats.total_duration_ms / tool_stats.calls
                if tool_stats.max_duration_ms is None or duration_ms > tool_stats.max_duration_ms:
                    tool_stats.max_duration_ms = duration_ms
                if tool_stats.min_duration_ms is None or duration_ms < tool_stats.min_duration_ms:
                    tool_stats.min_duration_ms = duration_ms
                break

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
            # Built-in tool tracking (task-68.3)
            "builtin_tools": self._builtin_tool_counts,
            "builtin_tool_total_calls": self._builtin_tool_total_calls,
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
        # v1.3.0: Track reasoning_tokens separately (not in total per OpenAI API)
        reasoning_tokens = usage.get("reasoning_tokens", 0)
        # Task 69.23: Match OpenAI's total_tokens formula exactly
        # total_tokens = input_tokens + output_tokens
        # Note: cache tokens are a SUBSET of input_tokens, not additive
        # Note: reasoning_tokens tracked separately, excluded from total per OpenAI API
        total_tokens = usage["input_tokens"] + usage["output_tokens"]

        # Handle session-level token tracking (non-MCP events)
        # REPLACE values (not add) because we use cumulative total_token_usage
        # to avoid double-counting from duplicate events. See Task 79.
        if tool_name == "__session__":
            self.session.token_usage.input_tokens = usage["input_tokens"]
            self.session.token_usage.output_tokens = usage["output_tokens"]
            self.session.token_usage.cache_created_tokens = usage["cache_created_tokens"]
            self.session.token_usage.cache_read_tokens = usage["cache_read_tokens"]
            self.session.token_usage.reasoning_tokens = reasoning_tokens  # v1.3.0
            self.session.token_usage.total_tokens = total_tokens

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

        # Get platform metadata - include call_id for duration update (task-68.5)
        platform_data = {
            "model": self.detected_model,
            "model_name": self.model_name,
            "call_id": usage.get("call_id"),
        }

        # Record tool call using BaseTracker
        # Duration comes from function_call_output parsing (task-68.5)
        # Token estimation metadata comes from _parse_function_call_output (task-69.8)
        self.record_tool_call(
            tool_name=tool_name,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_created_tokens=usage["cache_created_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            duration_ms=usage.get("duration_ms", 0),
            content_hash=content_hash,
            platform_data=platform_data,
            is_estimated=usage.get("is_estimated", False),
            estimation_method=usage.get("estimation_method"),
            estimation_encoding=usage.get("estimation_encoding"),
            # v1.6.0: Multi-model tracking (task-108.2.3)
            model=self.detected_model,
        )

        # Notify display for Recent Activity feed (task-68.2)
        # Use normalized tool name for consistency (task-68.7)
        if hasattr(self, "_display") and self._display is not None:
            normalized_tool = self.normalize_tool_name(tool_name)
            self._display.on_event(
                tool_name=normalized_tool,
                tokens=total_tokens,
                timestamp=datetime.now(timezone.utc),
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
    parser.add_argument("--project", default="token-audit", help="Project name")
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
        default=str(Path.home() / ".token-audit" / "sessions"),
        help="Output directory for session logs (default: ~/.token-audit/sessions)",
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

    print(f"\nSession saved to: {adapter.session_path}")
    print(f"Total tokens: {session.token_usage.total_tokens:,}")
    print(f"MCP calls: {session.mcp_tool_calls.total_calls}")
    print(f"Cache efficiency: {session.token_usage.cache_efficiency:.1%}")
    if adapter.detected_model:
        print(f"Model: {adapter.model_name}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
