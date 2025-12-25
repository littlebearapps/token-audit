#!/usr/bin/env python3
"""
GeminiCLIAdapter - Platform adapter for Gemini CLI session tracking

Parses Gemini CLI session JSON files from ~/.gemini/tmp/<project_hash>/chats/
to extract MCP tool usage and token counts.

This adapter reads native Gemini CLI session files - NO OpenTelemetry required.
"""

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Set, Tuple

from .base_tracker import BaseTracker, DataQuality
from .pricing_config import PricingConfig
from .token_estimator import TokenEstimator

if TYPE_CHECKING:
    from .display import DisplayAdapter, DisplaySnapshot


# Gemini CLI built-in tools - from official source:
# https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/tools/tool-names.ts
GEMINI_BUILTIN_TOOLS: Set[str] = {
    "glob",  # File pattern matching
    "google_web_search",  # Web search (WEB_SEARCH_TOOL_NAME)
    "list_directory",  # Directory listing (LS_TOOL_NAME)
    "read_file",  # Read single file (READ_FILE_TOOL_NAME)
    "read_many_files",  # Read multiple files (READ_MANY_FILES_TOOL_NAME)
    "replace",  # File content replacement (EDIT_TOOL_NAME)
    "run_shell_command",  # Shell execution (SHELL_TOOL_NAME)
    "save_memory",  # Memory/context saving (MEMORY_TOOL_NAME)
    "search_file_content",  # Grep/ripgrep search (GREP_TOOL_NAME)
    "web_fetch",  # Fetch web content (WEB_FETCH_TOOL_NAME)
    "write_file",  # Write file (WRITE_FILE_TOOL_NAME)
    "write_todos",  # Task management (WRITE_TODOS_TOOL_NAME)
}


def _get_git_metadata(working_dir: Optional[Path] = None) -> Dict[str, str]:
    """Collect git metadata for the session (task-70.1).

    Args:
        working_dir: Path to the working directory (defaults to cwd)

    Returns:
        Dictionary with branch, commit_short, and status
    """
    metadata: Dict[str, str] = {
        "branch": "",
        "commit_short": "",
        "status": "",  # "clean", "dirty", or ""
    }

    cwd = str(working_dir) if working_dir else None

    try:
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            metadata["branch"] = result.stdout.strip()

        # Get commit hash (short)
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            metadata["commit_short"] = result.stdout.strip()

        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            has_changes = len(result.stdout.strip()) > 0
            metadata["status"] = "dirty" if has_changes else "clean"

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        # Git not available or not a git repo - return empty strings
        pass

    return metadata


# Human-readable model names for Gemini models
MODEL_DISPLAY_NAMES: Dict[str, str] = {
    # Gemini 3 Series
    "gemini-3-pro-preview": "Gemini 3 Pro Preview",
    # Gemini 2.5 Series
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-pro-preview": "Gemini 2.5 Pro Preview",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-preview": "Gemini 2.5 Flash Preview",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    # Gemini 2.0 Series
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
}

# Default exchange rate (used if not in config)
DEFAULT_USD_TO_AUD = 1.54


@dataclass
class GeminiMessage:
    """Parsed Gemini CLI message."""

    id: str
    timestamp: datetime
    message_type: str  # "user" or "gemini"
    content: str
    model: Optional[str] = None
    thoughts: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tokens: Optional[Dict[str, int]] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "GeminiMessage":
        """Parse message from JSON."""
        # Parse timestamp
        timestamp_str = data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.now()

        # Extract token data
        tokens = data.get("tokens")
        if tokens:
            tokens = {
                "input": tokens.get("input", 0),
                "output": tokens.get("output", 0),
                "cached": tokens.get("cached", 0),
                "thoughts": tokens.get("thoughts", 0),
                "tool": tokens.get("tool", 0),
                "total": tokens.get("total", 0),
            }

        return cls(
            id=data.get("id", ""),
            timestamp=timestamp,
            message_type=data.get("type", "unknown"),
            content=data.get("content", ""),
            model=data.get("model"),
            thoughts=data.get("thoughts"),
            tool_calls=data.get("toolCalls"),
            tokens=tokens,
        )


@dataclass
class GeminiSession:
    """Parsed Gemini CLI session."""

    session_id: str
    project_hash: str
    start_time: datetime
    last_updated: datetime
    messages: List[GeminiMessage]
    source_file: str

    @classmethod
    def from_file(cls, file_path: Path) -> "GeminiSession":
        """Parse session from JSON file."""
        with open(file_path) as f:
            data = json.load(f)

        # Parse timestamps
        start_time_str = data.get("startTime", "")
        last_updated_str = data.get("lastUpdated", "")

        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except ValueError:
            start_time = datetime.now()

        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
        except ValueError:
            last_updated = datetime.now()

        # Parse messages
        messages = []
        for msg_data in data.get("messages", []):
            messages.append(GeminiMessage.from_json(msg_data))

        return cls(
            session_id=data.get("sessionId", ""),
            project_hash=data.get("projectHash", ""),
            start_time=start_time,
            last_updated=last_updated,
            messages=messages,
            source_file=file_path.name,
        )


class GeminiCLIAdapter(BaseTracker):
    """
    Gemini CLI platform adapter.

    Reads native Gemini CLI session JSON files from:
    ~/.gemini/tmp/<project_hash>/chats/session-*.json

    NO OpenTelemetry required - directly parses Gemini's session format.

    Usage:
        # Auto-detect project from current directory
        adapter = GeminiCLIAdapter(project="my-project")
        adapter.start_tracking()

        # Manual project hash
        adapter = GeminiCLIAdapter(
            project="my-project",
            project_hash="abc123..."
        )
    """

    def __init__(
        self,
        project: str,
        gemini_dir: Optional[Path] = None,
        project_hash: Optional[str] = None,
        session_file: Optional[Path] = None,
        from_start: bool = False,
    ):
        """
        Initialize Gemini CLI adapter.

        Args:
            project: Project name (e.g., "token-audit")
            gemini_dir: Gemini config directory (default: ~/.gemini)
            project_hash: Project hash (auto-detected if not provided)
            session_file: Specific session file to read (overrides auto-detection)
            from_start: If True, process entire session from start. If False (default),
                        only track new events written after token-audit starts.
        """
        super().__init__(project=project, platform="gemini-cli")

        self.gemini_dir = gemini_dir or Path.home() / ".gemini"
        self._project_hash = project_hash
        self._session_file = session_file
        self._from_start = from_start

        # Gemini-specific: track thinking tokens separately
        self.thoughts_tokens: int = 0

        # Model detection
        self.detected_model: Optional[str] = None
        self.model_name: str = "Unknown Model"

        # Initialize pricing config for cost calculation
        self._pricing_config = PricingConfig()
        self._usd_to_aud = DEFAULT_USD_TO_AUD
        if self._pricing_config.loaded:
            rates = self._pricing_config.metadata.get("exchange_rates", {})
            self._usd_to_aud = rates.get("USD_to_AUD", DEFAULT_USD_TO_AUD)

        # Session tracking
        self._processed_message_ids: set[str] = set()
        self._last_file_mtime: float = 0.0

        # ========================================================================
        # v0.1 Parity Enhancements (task-70)
        # ========================================================================

        # Built-in tools tracking (task-70.2)
        self._builtin_tool_calls: int = 0
        self._builtin_tool_tokens: int = 0

        # Git metadata (task-70.1)
        self._git_metadata = _get_git_metadata(Path.cwd())

        # Warnings tracking (task-70)
        self._warnings: List[Dict[str, Any]] = []

        # Current source files being tracked by this adapter instance
        self._current_source_files: Set[str] = set()

        # Token estimation for MCP tools (task-69.9)
        # Gemini CLI uses SentencePiece with Gemma tokenizer for 100% accuracy
        self._token_estimator = TokenEstimator.for_platform("gemini-cli")

        # Token estimation tracking (task-69.10)
        # Counts MCP tool calls that use estimated tokens
        self._estimated_tool_calls: int = 0

        # Native session token tracking (task-69.27)
        # Track native Gemini session tokens separately to avoid double-counting
        # with tool estimation tokens. These accumulate per-message tokens and
        # become the authoritative session.token_usage values.
        self._native_input_tokens: int = 0
        self._native_output_tokens: int = 0
        self._native_cache_created_tokens: int = 0
        self._native_cache_read_tokens: int = 0
        self._native_reasoning_tokens: int = 0
        self._native_total_tokens: int = 0

        # Data quality (v1.5.0 - task-103.5)
        # Gemini CLI: Session tokens are native from API, MCP tool tokens are estimated
        # Gemma tokenizer provides 100% accuracy when available, tiktoken ~95% fallback
        self.session.data_quality = DataQuality(
            accuracy_level=(
                "exact" if self._token_estimator.method_name == "sentencepiece" else "estimated"
            ),
            token_source=self._token_estimator.method_name,  # "sentencepiece" or "tiktoken"
            token_encoding=self._token_estimator.encoding_name,  # "gemma" or "o200k_base"
            confidence=1.0 if self._token_estimator.method_name == "sentencepiece" else 0.95,
            notes="Session totals native from API; MCP tool breakdown estimated via "
            + (
                "Gemma tokenizer (100% accuracy)"
                if self._token_estimator.method_name == "sentencepiece"
                else "tiktoken fallback (~95% accuracy)"
            ),
        )

        # MCP config path for static cost (v0.6.0 - task-114.2)
        # Gemini CLI uses ~/.gemini/settings.json
        mcp_config = self.gemini_dir / "settings.json"
        if mcp_config.exists():
            self.set_mcp_config_path(mcp_config)

    def _extract_files_from_tool_params(self, tool_name: str, params: Dict[str, Any]) -> None:
        """
        Extracts file paths from tool parameters and adds them to _current_source_files.
        """
        if not params:
            return

        if tool_name in ["read_file", "write_file", "replace"]:
            file_path = params.get("file_path")
            if file_path:
                self._current_source_files.add(str(file_path))
        elif tool_name == "list_directory":
            dir_path = params.get("dir_path")
            if dir_path:
                self._current_source_files.add(str(dir_path))
        elif tool_name == "read_many_files":
            file_paths = params.get("file_paths")
            if isinstance(file_paths, list):
                for fp in file_paths:
                    self._current_source_files.add(str(fp))
        elif tool_name == "search_file_content":
            dir_path = params.get("dir_path")
            if dir_path:
                self._current_source_files.add(str(dir_path))
            # Glob patterns are complex to resolve to actual files, so we'll skip for now
            # include = params.get("include")
        elif tool_name == "write_todos":
            todos = params.get("todos")
            if isinstance(todos, list):
                for todo in todos:
                    file_path = todo.get("file_path")
                    if file_path:
                        self._current_source_files.add(str(file_path))

    # ========================================================================
    # Project Hash Detection (Task 60.2)
    # ========================================================================

    @property
    def project_hash(self) -> Optional[str]:
        """Get or calculate project hash."""
        if self._project_hash:
            return self._project_hash

        # Try to auto-detect from CWD
        self._project_hash = self._calculate_project_hash()
        return self._project_hash

    def _calculate_project_hash(self) -> Optional[str]:
        """
        Calculate project hash from current working directory.

        Gemini CLI uses SHA256 of the absolute path.
        """
        cwd = Path.cwd().absolute()
        # Gemini CLI hashes the absolute path
        path_bytes = str(cwd).encode("utf-8")
        return hashlib.sha256(path_bytes).hexdigest()

    def _find_project_hash(self) -> Optional[str]:
        """
        Find project hash by listing available project directories.

        Only returns hashes that have actual session files, not just empty
        chats directories. This aligns with list_available_hashes() behavior.

        Returns:
            Project hash if found, None otherwise
        """
        tmp_dir = self.gemini_dir / "tmp"
        if not tmp_dir.exists():
            return None

        # List all project hash directories that have session files
        # (aligns with list_available_hashes behavior)
        hashes_with_sessions = []
        for item in tmp_dir.iterdir():
            if item.is_dir() and len(item.name) == 64:  # SHA256 = 64 hex chars
                chats_dir = item / "chats"
                if chats_dir.exists():
                    # Check for actual session files, not just directory existence
                    session_files = list(chats_dir.glob("session-*.json"))
                    if session_files:
                        # Use most recent session file mtime (consistent with list_available_hashes)
                        latest = max(session_files, key=lambda p: p.stat().st_mtime)
                        mtime = latest.stat().st_mtime
                        hashes_with_sessions.append((item.name, mtime))

        if not hashes_with_sessions:
            return None

        # If we have a calculated hash, check if it exists with session files
        calculated = self._calculate_project_hash()
        for h, _ in hashes_with_sessions:
            if h == calculated:
                return calculated

        # Return hash with most recently modified session file
        hashes_with_sessions.sort(key=lambda x: x[1], reverse=True)
        return hashes_with_sessions[0][0]

    def get_chats_directory(self) -> Optional[Path]:
        """Get the chats directory for this project."""
        if self.project_hash:
            chats_dir = self.gemini_dir / "tmp" / self.project_hash / "chats"
            if chats_dir.exists():
                return chats_dir

        # Try to find any valid project
        found_hash = self._find_project_hash()
        if found_hash:
            self._project_hash = found_hash
            return self.gemini_dir / "tmp" / found_hash / "chats"

        return None

    def list_available_hashes(self) -> List[Tuple[str, Path, datetime]]:
        """
        List all available project hashes with their paths and last update times.

        Returns:
            List of (hash, path, last_updated) tuples sorted by last_updated descending
        """
        tmp_dir = self.gemini_dir / "tmp"
        if not tmp_dir.exists():
            return []

        results = []
        for item in tmp_dir.iterdir():
            if item.is_dir() and len(item.name) == 64:
                chats_dir = item / "chats"
                if chats_dir.exists():
                    # Find most recent session file
                    session_files = list(chats_dir.glob("session-*.json"))
                    if session_files:
                        latest = max(session_files, key=lambda p: p.stat().st_mtime)
                        mtime = datetime.fromtimestamp(latest.stat().st_mtime)
                        results.append((item.name, chats_dir, mtime))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    # ========================================================================
    # Session File Discovery (Task 60.1, 60.3)
    # ========================================================================

    def get_session_files(self) -> List[Path]:
        """Get all session files for this project, sorted by modification time."""
        chats_dir = self.get_chats_directory()
        if not chats_dir:
            return []

        session_files = list(chats_dir.glob("session-*.json"))
        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return session_files

    def _check_for_newer_session_file(self, current_file: Path) -> Optional[Path]:
        """
        Check if a newer session file exists than the one being monitored.

        This handles the case where the user starts a new Gemini CLI conversation,
        which creates a new session file.

        Args:
            current_file: The session file currently being monitored

        Returns:
            Path to newer session file if found, None otherwise
        """
        session_files = self.get_session_files()
        if not session_files:
            return None

        # Most recent file is first (sorted by mtime descending)
        newest_file = session_files[0]

        # Return the new file only if it's different from the current one
        if newest_file != current_file and newest_file.name != current_file.name:
            return newest_file

        return None

    def get_latest_session_file(self) -> Optional[Path]:
        """Get the most recently modified session file."""
        if self._session_file:
            return self._session_file

        session_files = self.get_session_files()
        return session_files[0] if session_files else None

    # ========================================================================
    # Session Parsing (Task 60.1)
    # ========================================================================

    def parse_session_file(self, file_path: Path) -> GeminiSession:
        """Parse a single session file."""
        return GeminiSession.from_file(file_path)

    def iter_messages(
        self, session: GeminiSession, skip_processed: bool = True
    ) -> Iterator[GeminiMessage]:
        """
        Iterate over messages in a session.

        Args:
            session: Parsed session
            skip_processed: Skip messages already processed (for live monitoring)

        Yields:
            GeminiMessage objects
        """
        for msg in session.messages:
            if skip_processed and msg.id in self._processed_message_ids:
                continue
            yield msg

    # ========================================================================
    # Abstract Method Implementations
    # ========================================================================

    def start_tracking(self) -> None:
        """
        Start tracking Gemini CLI session.

        Monitors session files for new messages.
        """
        print(f"[Gemini CLI] Initializing tracker for: {self.project}")

        # Find session file
        session_file = self.get_latest_session_file()
        if not session_file:
            # Try to find project hash
            available = self.list_available_hashes()
            if available:
                print("[Gemini CLI] Available project hashes:")
                for h, _path, mtime in available[:5]:
                    print(f"  - {h[:16]}... (last: {mtime.strftime('%Y-%m-%d %H:%M')})")
                print("[Gemini CLI] Use --project-hash to specify one")
            else:
                print("[Gemini CLI] No session files found.")
                print(f"[Gemini CLI] Expected at: {self.gemini_dir}/tmp/<hash>/chats/")
            return

        print(f"[Gemini CLI] Monitoring: {session_file}")
        if self.project_hash:
            print(f"[Gemini CLI] Project hash: {self.project_hash[:16]}...")

        # Record session file
        self.session.source_files = [session_file.name]

        # Initialize position based on from_start flag
        if not self._from_start:
            # Skip existing messages - only track NEW events
            try:
                existing_session = self.parse_session_file(session_file)
                for msg in existing_session.messages:
                    self._processed_message_ids.add(msg.id)
                print(
                    f"[Gemini CLI] Tracking NEW events only (skipped {len(self._processed_message_ids)} existing messages)"
                )
            except Exception:
                pass  # Continue even if we can't count existing messages
        else:
            print("[Gemini CLI] Processing from start (--from-start)")

        print("[Gemini CLI] Tracking started. Press Ctrl+C to stop.")

        # Track last check for new session files
        last_new_file_check = 0.0

        # Main monitoring loop
        while True:
            try:
                # Check for NEW session files periodically (every 2 seconds)
                now = time.time()
                if now - last_new_file_check >= 2.0:
                    last_new_file_check = now
                    new_session_file = self._check_for_newer_session_file(session_file)
                    if new_session_file:
                        print(f"\n[Gemini CLI] Detected new session: {new_session_file.name}")
                        session_file = new_session_file
                        self.session.source_files = [session_file.name]
                        self._last_file_mtime = 0.0

                self._process_session_file(session_file)
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n[Gemini CLI] Stopping tracker...")
                break

    def monitor(self, display: Optional["DisplayAdapter"] = None) -> None:
        """
        Main monitoring loop with display integration.

        Args:
            display: Optional DisplayAdapter for real-time UI updates
        """
        self._display = display
        self._start_time = datetime.now()
        self._last_display_update = 0.0

        print(f"[Gemini CLI] Initializing tracker for: {self.project}")

        # Find session file
        session_file = self.get_latest_session_file()
        if not session_file:
            # Try to find project hash
            available = self.list_available_hashes()
            if available:
                print("[Gemini CLI] Available project hashes:")
                for h, _path, mtime in available[:5]:
                    print(f"  - {h[:16]}... (last: {mtime.strftime('%Y-%m-%d %H:%M')})")
                print("[Gemini CLI] Use --project-hash to specify one")
            else:
                print("[Gemini CLI] No session files found.")
                print(f"[Gemini CLI] Expected at: {self.gemini_dir}/tmp/<hash>/chats/")
            return

        print(f"[Gemini CLI] Monitoring: {session_file}")
        if self.project_hash:
            print(f"[Gemini CLI] Project hash: {self.project_hash[:16]}...")

        # Record session file
        self.session.source_files = [session_file.name]

        # Initialize position based on from_start flag
        if not self._from_start:
            # Skip existing messages - only track NEW events
            try:
                existing_session = self.parse_session_file(session_file)
                for msg in existing_session.messages:
                    self._processed_message_ids.add(msg.id)
                print(
                    f"[Gemini CLI] Tracking NEW events only (skipped {len(self._processed_message_ids)} existing messages)"
                )
            except Exception:
                pass  # Continue even if we can't count existing messages
        else:
            print("[Gemini CLI] Processing from start (--from-start)")

        print("[Gemini CLI] Tracking started. Press Ctrl+C to stop.")

        # Track last check for new session files
        self._last_new_file_check = 0.0

        # Main monitoring loop with display updates
        while True:
            try:
                # Check for NEW session files periodically (every 2 seconds)
                # This handles the case where user starts a new Gemini CLI conversation
                now = time.time()
                if now - self._last_new_file_check >= 2.0:
                    self._last_new_file_check = now
                    new_session_file = self._check_for_newer_session_file(session_file)
                    if new_session_file:
                        print(f"\n[Gemini CLI] Detected new session: {new_session_file.name}")
                        session_file = new_session_file
                        self.session.source_files = [session_file.name]
                        # Reset file tracking for new file
                        self._last_file_mtime = 0.0

                self._process_session_file(session_file)

                # Update display periodically (every 0.5 seconds)
                if display and now - self._last_display_update >= 0.5:
                    self._last_display_update = now
                    snapshot = self._build_display_snapshot()
                    result = display.update(snapshot)
                    # Handle [Q] quit keybinding (v0.7.0 - task-105.8)
                    if result == "quit":
                        print("\n[Gemini CLI] Stopping tracker...")
                        break

                time.sleep(0.2)

            except KeyboardInterrupt:
                print("\n[Gemini CLI] Stopping tracker...")
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
        top_tools = []
        total_mcp_calls = 0
        for server_session in self.server_sessions.values():
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
        # NOTE: For Gemini CLI, cache_read is a SUBSET of input_tokens (not additive)
        # - input_tokens = total input/prompt tokens
        # - cache_read = portion of input_tokens served from cache
        # - fresh_input = input_tokens - cache_read (tokens at full price)
        cost_with_cache = 0.0
        cost_without_cache = 0.0
        if pricing.loaded and model_id:
            # Fresh input tokens (not served from cache) - charged at full rate
            fresh_input_tokens = input_tokens - cache_read

            # Cost with cache: fresh at full rate, cached at discounted rate
            cost_with_cache = pricing.calculate_cost(
                model_id, fresh_input_tokens, output_tokens, cache_created, cache_read
            )
            # Cost without cache: all input at full rate
            cost_without_cache = pricing.calculate_cost(model_id, input_tokens, output_tokens, 0, 0)

            # Save costs to session for persistence (task-66.8)
            self.session.cost_estimate = cost_with_cache
            self.session.cost_no_cache = cost_without_cache
            self.session.cache_savings_usd = cost_without_cache - cost_with_cache

        # ================================================================
        # Warnings/Health Check (task-70)
        # ================================================================
        warnings_count = len(self._warnings)
        if warnings_count == 0:
            health_status = "healthy"
        elif warnings_count <= 3:
            health_status = "warnings"
        else:
            health_status = "errors"

        return DisplaySnapshot.create(
            project=self.project,
            platform="gemini-cli",
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
            reasoning_tokens=usage.reasoning_tokens,  # v1.3.0: Gemini thoughts
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
            # v0.1 Parity Enhancements (task-70)
            builtin_tool_calls=self._builtin_tool_calls,
            builtin_tool_tokens=self._builtin_tool_tokens,
            git_branch=self._git_metadata.get("branch", ""),
            git_commit_short=self._git_metadata.get("commit_short", ""),
            git_status=self._git_metadata.get("status", ""),
            warnings_count=warnings_count,
            health_status=health_status,
            files_monitored=1,  # Gemini CLI monitors one session file at a time
            # Token estimation tracking (task-69.10)
            estimated_tool_calls=self._estimated_tool_calls,
            estimation_method=self._token_estimator.method_name,
            estimation_encoding=self._token_estimator.encoding_name,
            # Data quality (v1.5.0 - task-103.5)
            accuracy_level="estimated",
            token_source=self._token_estimator.method_name,
            data_quality_confidence=(
                1.0 if self._token_estimator.method_name == "sentencepiece" else 0.95
            ),
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

    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse a Gemini message into normalized format.

        Processes ALL tool calls in a message (not just the first one) and
        ALWAYS returns session tokens so message-level token data is captured.

        Args:
            event_data: GeminiMessage object

        Returns:
            Tuple of ("__session__", usage_dict) for session token events.
            Tool calls are processed in-place via _process_parsed_event.
        """
        if not isinstance(event_data, GeminiMessage):
            return None

        msg = event_data

        # Skip user messages (no token data)
        if msg.message_type == "user":
            return None

        # Track model
        if msg.model and not self.detected_model:
            self.detected_model = msg.model
            self.model_name = MODEL_DISPLAY_NAMES.get(msg.model, msg.model)
            self.session.model = msg.model

        # Extract token usage
        tokens = msg.tokens or {}
        input_tokens = tokens.get("input", 0)
        output_tokens = tokens.get("output", 0)
        cached_tokens = tokens.get("cached", 0)
        thoughts_tokens = tokens.get("thoughts", 0)
        tool_tokens = tokens.get("tool", 0)

        # Track thoughts tokens cumulatively
        self.thoughts_tokens += thoughts_tokens

        # Process ALL tool calls if present (task-72.1)
        # Tool calls are processed in-place - we don't return early anymore
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                result = self._parse_tool_call(tool_call, msg)
                if result:
                    # Process tool call immediately instead of returning
                    self._process_parsed_event(*result)

        # ALWAYS return session-level token data (task-72.2)
        # This ensures token counts are captured even for messages with tool calls
        # v1.3.0: Keep reasoning_tokens separate (previously combined into output_tokens)
        usage_dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,  # v1.3.0: No longer includes thoughts
            "cache_created_tokens": 0,  # Gemini doesn't report cache creation
            "cache_read_tokens": cached_tokens,
            "reasoning_tokens": thoughts_tokens,  # v1.3.0: Renamed from thoughts_tokens
            "tool_tokens": tool_tokens,
        }

        return ("__session__", usage_dict)

    def get_platform_metadata(self) -> Dict[str, Any]:
        """Get Gemini CLI platform metadata."""
        return {
            "model": self.detected_model,
            "model_name": self.model_name,
            "gemini_dir": str(self.gemini_dir),
            "project_hash": self.project_hash,
            "thoughts_tokens": self.thoughts_tokens,
        }

    # ========================================================================
    # Tool Call Parsing (Task 60.5)
    # ========================================================================

    def _is_gemini_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool is a Gemini CLI MCP tool in native format.

        Gemini CLI uses <server>__<tool> format for MCP tools,
        e.g., "fs__read_file" for the filesystem server's read_file tool.

        This is different from Claude Code which uses mcp__<server>__<tool>.

        Returns True if:
        - Tool contains "__" (server/tool separator)
        - Tool is NOT a built-in (not in GEMINI_BUILTIN_TOOLS)
        - Tool is NOT an internal marker (doesn't start with "__")
        - Tool is NOT already in Claude format (doesn't start with "mcp__")

        Task 69.28: Fix Gemini CLI MCP tool detection.
        """
        if tool_name in GEMINI_BUILTIN_TOOLS:
            return False
        if tool_name.startswith("__"):
            return False  # Internal markers like __session__
        if tool_name.startswith("mcp__"):
            return False  # Already in Claude/normalized format
        return "__" in tool_name  # Server__tool pattern (Gemini native format)

    def _parse_tool_call(
        self, tool_call: Dict[str, Any], msg: GeminiMessage
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse a tool call from Gemini message.

        Args:
            tool_call: Tool call data from toolCalls array
            msg: Parent message for token context

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tools,
            Tuple of ("__builtin__:<tool>", usage_dict) for built-in tools,
            None otherwise
        """
        tool_name = tool_call.get("name", "")
        params = tool_call.get("args", {})  # Gemini CLI tool args are under "args"

        # Extract file paths from tool parameters (task-50.3)
        self._extract_files_from_tool_params(tool_name, params)

        # Extract token info from parent message
        tokens = msg.tokens or {}
        tool_tokens = tokens.get("tool", 0)

        # Token estimation for MCP tools AND built-in tools (task-69.9, task-69.24, task-69.28)
        # Per Task 69 validated plan: "Built-in vs MCP Tools: No difference in accuracy approach.
        # Both are function calls to the model and use the same estimation method."
        #
        # Task 69.28: Gemini CLI uses <server>__<tool> format (e.g., fs__read_file),
        # NOT the mcp__<server>__<tool> format used by Claude Code.
        # We detect both formats:
        # - Gemini native: fs__read_file -> needs normalization to mcp__fs__read_file
        # - Already normalized: mcp__zen__chat -> use as-is
        is_gemini_mcp_tool = self._is_gemini_mcp_tool(tool_name)
        is_normalized_mcp_tool = tool_name.startswith("mcp__")
        is_mcp_tool = is_gemini_mcp_tool or is_normalized_mcp_tool
        is_builtin_tool = tool_name in GEMINI_BUILTIN_TOOLS
        should_estimate = is_mcp_tool or is_builtin_tool

        input_tokens = 0
        output_tokens = tool_tokens
        is_estimated = False
        estimation_method: Optional[str] = None
        estimation_encoding: Optional[str] = None

        if should_estimate:
            # Serialize args for estimation
            args_str = json.dumps(params, separators=(",", ":")) if params else ""

            # Get result for output estimation
            result = tool_call.get("result")
            if isinstance(result, list):
                result_str = "\n".join(str(r) for r in result)
            elif result is not None:
                result_str = str(result)
            else:
                result_str = ""

            # Estimate tokens using platform tokenizer
            input_tokens, output_tokens = self._token_estimator.estimate_tool_call(
                args_str, result_str
            )
            is_estimated = True
            estimation_method = self._token_estimator.method_name
            estimation_encoding = self._token_estimator.encoding_name

            # Track estimated tool calls for TUI display (task-69.10)
            self._estimated_tool_calls += 1

        usage_dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "duration_ms": 0,  # Not available in session format
            "success": tool_call.get("status") == "success",
            "tool_call_id": tool_call.get("id", ""),
            # Token estimation metadata (task-69.9)
            "is_estimated": is_estimated,
            "estimation_method": estimation_method,
            "estimation_encoding": estimation_encoding,
        }

        # Track MCP tools (Task 69.28)
        # - Gemini native format (fs__read_file) -> normalize to mcp__fs__read_file
        # - Already normalized format (mcp__zen__chat) -> use as-is
        if is_mcp_tool:
            # Normalize Gemini format to standard mcp__ format, or use as-is
            normalized_name = f"mcp__{tool_name}" if is_gemini_mcp_tool else tool_name
            return (normalized_name, usage_dict)

        # Track Gemini CLI built-in tools (task-70.2)
        if tool_name in GEMINI_BUILTIN_TOOLS:
            return (f"__builtin__:{tool_name}", usage_dict)

        return None

    # ========================================================================
    # File Monitoring (Task 60.3)
    # ========================================================================

    def _process_session_file(self, file_path: Path) -> None:
        """Read and process session file for new messages."""
        if not file_path.exists():
            return

        # Check if file was modified
        current_mtime = file_path.stat().st_mtime
        if current_mtime == self._last_file_mtime:
            return

        self._last_file_mtime = current_mtime

        try:
            session = self.parse_session_file(file_path)

            # Process new messages
            for msg in self.iter_messages(session, skip_processed=True):
                result = self.parse_event(msg)
                if result:
                    tool_name, usage = result
                    self._process_parsed_event(tool_name, usage)

                # Mark as processed
                self._processed_message_ids.add(msg.id)

                # Increment message count for gemini messages
                if msg.message_type == "gemini":
                    self.session.message_count += 1

        except (json.JSONDecodeError, OSError) as e:
            self.handle_unrecognized_line(f"Error reading session file: {e}")

    def _process_parsed_event(self, tool_name: str, usage: Dict[str, Any]) -> None:
        """
        Process a parsed event (tool call or session tokens).

        Args:
            tool_name: MCP tool name, "__builtin__:<tool>", or "__session__" for token events
            usage: Token usage and metadata dictionary
        """
        # Calculate total tokens WITHOUT cache_read (task-71)
        # Gemini CLI: total = input + output + cache_created + reasoning
        # cache_read is a SUBSET of input tokens (already counted), not additional tokens
        # tool_tokens are NOT included here - they are already counted in input/output tokens
        # (similar to cache_read, tool_tokens represent a breakdown, not additional tokens)
        reasoning_tokens = usage.get("reasoning_tokens", 0)
        total_tokens = (
            usage["input_tokens"]
            + usage["output_tokens"]
            + usage["cache_created_tokens"]
            + reasoning_tokens  # v1.3.0: Include reasoning/thoughts in total
            # cache_read_tokens NOT included - already subset of input
            # tool_tokens NOT included - already subset of input/output
        )

        # Handle session-level token tracking
        if tool_name == "__session__":
            # Task 69.27: Accumulate native tokens separately, then SET (not ADD)
            # to session.token_usage. This avoids double-counting with tool
            # estimation tokens that were added by record_tool_call().
            # Native Gemini session tokens already include tool costs.
            self._native_input_tokens += usage["input_tokens"]
            self._native_output_tokens += usage["output_tokens"]
            self._native_cache_created_tokens += usage["cache_created_tokens"]
            self._native_cache_read_tokens += usage["cache_read_tokens"]
            self._native_reasoning_tokens += reasoning_tokens  # v1.3.0
            self._native_total_tokens += total_tokens

            # SET session.token_usage from native totals (replaces tool estimates)
            self.session.token_usage.input_tokens = self._native_input_tokens
            self.session.token_usage.output_tokens = self._native_output_tokens
            self.session.token_usage.cache_created_tokens = self._native_cache_created_tokens
            self.session.token_usage.cache_read_tokens = self._native_cache_read_tokens
            self.session.token_usage.reasoning_tokens = self._native_reasoning_tokens
            self.session.token_usage.total_tokens = self._native_total_tokens

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

            # Notify display of session event (task-70.3)
            if hasattr(self, "_display") and self._display:
                self._display.on_event("(session)", total_tokens, datetime.now())
            return

        # Handle built-in tool calls (task-70.2, task-72.3, task-78)
        if tool_name.startswith("__builtin__:"):
            actual_tool_name = tool_name.replace("__builtin__:", "")
            self._builtin_tool_calls += 1
            self._builtin_tool_tokens += total_tokens

            # Track per-tool stats (task-78: for builtin_tool_summary in session file)
            if actual_tool_name not in self.session.builtin_tool_stats:
                self.session.builtin_tool_stats[actual_tool_name] = {"calls": 0, "tokens": 0}
            self.session.builtin_tool_stats[actual_tool_name]["calls"] += 1
            self.session.builtin_tool_stats[actual_tool_name]["tokens"] += total_tokens

            # Record built-in tool call to session file (task-72.3, task-69.24)
            # Use "builtin" as the server name so it appears in tool_calls array
            builtin_tool_name = f"builtin__{actual_tool_name}"
            platform_data = {
                "model": self.detected_model,
                "success": usage.get("success", True),
                "tool_call_id": usage.get("tool_call_id"),
                "is_builtin": True,
            }

            self.record_tool_call(
                tool_name=builtin_tool_name,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_created_tokens=usage["cache_created_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                duration_ms=usage.get("duration_ms", 0),
                content_hash=None,
                platform_data=platform_data,
                # Token estimation metadata (task-69.24)
                is_estimated=usage.get("is_estimated", False),
                estimation_method=usage.get("estimation_method"),
                estimation_encoding=usage.get("estimation_encoding"),
                # v1.6.0: Multi-model tracking (task-108.2.3)
                model=self.detected_model,
            )

            # Notify display of built-in tool event (task-70.3)
            if hasattr(self, "_display") and self._display:
                self._display.on_event(
                    f"[built-in] {actual_tool_name}", total_tokens, datetime.now()
                )

            # task-80: Update session.source_files for built-in tools
            # (Previously skipped due to early return - files from _extract_files_from_tool_params were lost)
            if self._current_source_files:
                current_session_files = set(self.session.source_files)
                updated_session_files = sorted(
                    current_session_files.union(self._current_source_files)
                )
                self.session.source_files = updated_session_files
            return

        # Record MCP tool call using BaseTracker
        platform_data = {
            "model": self.detected_model,
            "success": usage.get("success", True),
            "tool_call_id": usage.get("tool_call_id"),
            "thoughts_tokens": self.thoughts_tokens,
        }

        # Token estimation metadata (task-69.9)
        self.record_tool_call(
            tool_name=tool_name,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_created_tokens=usage["cache_created_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            duration_ms=usage.get("duration_ms", 0),
            content_hash=None,
            platform_data=platform_data,
            is_estimated=usage.get("is_estimated", False),
            estimation_method=usage.get("estimation_method"),
            estimation_encoding=usage.get("estimation_encoding"),
            # v1.6.0: Multi-model tracking (task-108.2.3)
            model=self.detected_model,
        )

        # Notify display of MCP event (task-70.3)
        if hasattr(self, "_display") and self._display:
            self._display.on_event(tool_name, total_tokens, datetime.now())

        # Update session.source_files (task-50.3)
        # Combine existing session source_files with _current_source_files
        current_session_files = set(self.session.source_files)
        updated_session_files = sorted(current_session_files.union(self._current_source_files))
        self.session.source_files = updated_session_files

    # ========================================================================
    # Batch Processing (for report generation)
    # ========================================================================

    def process_session_file_batch(self, file_path: Path) -> None:
        """
        Process a complete session file in batch mode (no live monitoring).

        Used for generating reports from existing session files.

        Args:
            file_path: Path to session file
        """
        session = self.parse_session_file(file_path)

        # Record source file
        self.session.source_files = [file_path.name]

        # Update session timestamps from Gemini session
        self.session.timestamp = session.start_time
        self.session.end_timestamp = session.last_updated

        # Process all messages
        for msg in session.messages:
            result = self.parse_event(msg)
            if result:
                tool_name, usage = result
                self._process_parsed_event(tool_name, usage)

            # Increment message count for gemini messages
            if msg.message_type == "gemini":
                self.session.message_count += 1

    def get_active_source_files(self) -> List[str]:
        """
        Get the list of source files actively being monitored by GeminiCLIAdapter.

        For Gemini CLI, this returns the session file(s) being monitored.

        Returns:
            A sorted list of strings, each representing a path to a source file.
        """
        source_files: List[str] = []

        # Add currently monitored session file
        if hasattr(self, "_session_file") and self._session_file:
            source_files.append(str(self._session_file))

        # Add any files from session
        if self.session and self.session.source_files:
            source_files.extend(self.session.source_files)

        return sorted(set(source_files))


# ============================================================================
# Standalone Execution
# ============================================================================


def main() -> int:
    """Main entry point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Gemini CLI MCP Tracker")
    parser.add_argument("--project", default="token-audit", help="Project name")
    parser.add_argument(
        "--gemini-dir",
        type=Path,
        default=None,
        help="Gemini config directory (default: ~/.gemini)",
    )
    parser.add_argument(
        "--project-hash",
        default=None,
        help="Project hash (auto-detected from CWD if not provided)",
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
        "--list-hashes",
        action="store_true",
        help="List available project hashes and exit",
    )
    args = parser.parse_args()

    # Create adapter
    adapter = GeminiCLIAdapter(
        project=args.project,
        gemini_dir=args.gemini_dir,
        project_hash=args.project_hash,
        session_file=args.session_file,
    )

    # List hashes mode
    if args.list_hashes:
        print("Available Gemini CLI project hashes:")
        print("-" * 80)
        for h, path, mtime in adapter.list_available_hashes():
            print(f"  {h[:16]}...  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Path: {path}")
        return 0

    print(f"Starting Gemini CLI tracker for project: {args.project}")

    try:
        if args.batch and args.session_file:
            # Batch mode - process file without monitoring
            adapter.process_session_file_batch(args.session_file)
            session = adapter.finalize_session()
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
    print(f"Thinking tokens: {adapter.thoughts_tokens:,}")
    print(f"Messages: {session.message_count}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
