#!/usr/bin/env python3
"""
ClaudeCodeAdapter - Platform adapter for Claude Code tracking

Implements BaseTracker for Claude Code's debug.log format.
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from .base_tracker import BaseTracker, DataQuality
from .pricing_config import PricingConfig

if TYPE_CHECKING:
    from .display import DisplayAdapter, DisplaySnapshot

# Human-readable model names (AC #15)
MODEL_DISPLAY_NAMES: Dict[str, str] = {
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

# Model priority for detection (higher = prefer over lower)
# When multiple models appear in a session, prefer the most capable one
# This handles cases where MCP servers report their own model (often Haiku)
MODEL_PRIORITY: Dict[str, int] = {
    "opus": 3,  # Most capable
    "sonnet": 2,  # Mid-tier
    "haiku": 1,  # Lightweight
}

# Claude Code built-in tools - from official docs:
# https://docs.anthropic.com/en/docs/claude-code/settings#tools-available-to-claude
CLAUDE_CODE_BUILTIN_TOOLS: Set[str] = {
    "AskUserQuestion",  # User interaction/clarification
    "Bash",  # Shell command execution
    "BashOutput",  # Background shell output retrieval
    "Edit",  # Targeted file edits
    "EnterPlanMode",  # Enter plan mode (not in docs, but exists)
    "ExitPlanMode",  # Exit plan mode
    "Glob",  # File pattern matching
    "Grep",  # Content search
    "KillShell",  # Kill background shell
    "NotebookEdit",  # Jupyter notebook editing
    "Read",  # File reading
    "Skill",  # Execute skills
    "SlashCommand",  # Custom slash commands
    "Task",  # Sub-agent tasks
    "TodoWrite",  # Task list management
    "WebFetch",  # URL content fetching
    "WebSearch",  # Web searching
    "Write",  # File creation/overwrite
}

# Default exchange rate (used if not in config)
DEFAULT_USD_TO_AUD = 1.54


def _get_model_priority(model_id: str) -> int:
    """Get priority for a model ID. Higher = more capable."""
    if not model_id:
        return 0
    model_lower = model_id.lower()
    for key, priority in MODEL_PRIORITY.items():
        if key in model_lower:
            return priority
    return 0


def _get_git_metadata(working_dir: Optional[Path] = None) -> Dict[str, str]:
    """Collect git metadata for the session (task-46.5).

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


class ClaudeCodeAdapter(BaseTracker):
    """
    Claude Code platform adapter.

    Monitors Claude Code debug.log files for MCP tool usage.
    Uses file watcher approach to tail debug logs in real-time.
    """

    def __init__(self, project: str, project_path: str = "", claude_dir: Optional[Path] = None):
        """
        Initialize Claude Code adapter.

        Args:
            project: Project name (e.g., "token-audit")
            project_path: Relative project path (e.g., "wp-navigator-pro/main")
            claude_dir: Optional Claude Code directory (for testing)
        """
        super().__init__(project=project, platform="claude-code")

        self.project_path = project_path or project
        self.file_positions: Dict[Path, int] = {}  # Track read positions
        self.claude_dir: Optional[Path] = claude_dir
        self.detected_model: Optional[str] = None
        self.model_name: str = "Unknown Model"
        self._tracking_start_time: float = 0.0  # Track when monitoring started

        # Initialize pricing config for cost calculation
        self._pricing_config = PricingConfig()
        self._usd_to_aud = DEFAULT_USD_TO_AUD
        if self._pricing_config.loaded:
            rates = self._pricing_config.metadata.get("exchange_rates", {})
            self._usd_to_aud = rates.get("USD_to_AUD", DEFAULT_USD_TO_AUD)

        # ========================================================================
        # v0.1 Parity Enhancements (task-46)
        # ========================================================================

        # Message counter (task-46.1)
        self._message_count: int = 0

        # Built-in tools tracking (task-46.4, task-78)
        self._builtin_tool_calls: int = 0
        self._builtin_tool_tokens: int = 0
        self._builtin_tool_stats: Dict[str, Dict[str, int]] = {}  # tool -> {calls, tokens}

        # Git metadata (task-46.5)
        self._git_metadata = _get_git_metadata(Path.cwd())

        # Warnings tracking (task-46.10)
        self._warnings: List[Dict[str, Any]] = []

        # Data quality (v1.5.0 - task-103.5)
        # Claude Code provides exact native token counts from the API
        self.session.data_quality = DataQuality(
            accuracy_level="exact",
            token_source="native",
            token_encoding=None,  # Native API tokens, no encoding needed
            confidence=1.0,
            notes="Native token counts from Claude API response",
        )

        # MCP config path for static cost (v0.6.0 - task-114.2)
        # Claude Code uses .mcp.json in the working directory
        mcp_config = Path.cwd() / ".mcp.json"
        if mcp_config.exists():
            self.set_mcp_config_path(mcp_config)

        # Source file tracking (task-50)
        self._active_source_files: Set[str] = set()

        # Find Claude Code directory (only if not provided)
        if self.claude_dir is None:
            self._find_claude_directory()

    def _find_claude_directory(self) -> None:
        """Find Claude Code data directory for this project"""
        # Try standard locations
        base_dir = Path.home() / ".config" / "claude" / "projects"
        if not base_dir.exists():
            base_dir = Path.home() / ".claude" / "projects"

        if not base_dir.exists():
            raise FileNotFoundError(
                "Claude Code data directory not found. "
                "Tried: ~/.config/claude/projects and ~/.claude/projects"
            )

        # Try to find directory based on current working directory
        # Format: -Users-username-path-to-project
        try:
            cwd = Path.cwd()
            cwd_encoded = str(cwd).replace("/", "-")
            if cwd_encoded.startswith("-"):
                exact_dir = base_dir / cwd_encoded
                if exact_dir.exists():
                    self.claude_dir = exact_dir
                    return
        except Exception:
            pass

        # Find matching directories by project name
        matching_dirs = []
        search_term = self.project_path.replace("/", "-")
        for d in base_dir.iterdir():
            if d.is_dir() and search_term in d.name:
                # Get modification time and file count
                try:
                    jsonl_files = list(d.glob("*.jsonl"))
                    if jsonl_files:
                        # Use most recent file modification time
                        latest_mod = max(f.stat().st_mtime for f in jsonl_files)
                        matching_dirs.append((d, len(jsonl_files), latest_mod))
                except Exception:
                    continue

        # Prefer directory with most files (active project), then most recent
        if matching_dirs:
            # Sort by file count (descending), then by mod time (descending)
            matching_dirs.sort(key=lambda x: (x[1], x[2]), reverse=True)
            self.claude_dir = matching_dirs[0][0]
            return

        # Fall back to scanning all directories
        self.claude_dir = base_dir

    def _find_jsonl_files(self) -> List[Path]:
        """Find all .jsonl files in Claude Code directory.

        NOTE: We include ALL .jsonl files, even empty ones. This is important
        because Claude Code creates session files empty and then writes to them.
        If we exclude empty files, we may miss new sessions that start during
        monitoring.
        """
        if not self.claude_dir or not self.claude_dir.exists():
            return []

        # Get all .jsonl files (including empty ones to catch new sessions)
        return list(self.claude_dir.glob("*.jsonl"))

    # ========================================================================
    # Abstract Method Implementations
    # ========================================================================

    def start_tracking(self) -> None:
        """
        Start tracking Claude Code session.

        Monitors .jsonl debug log files in real-time.
        """
        self._tracking_start_time = time.time()

        print(f"[Claude Code] Initializing tracker for: {self.project_path}")
        print(f"[Claude Code] Monitoring directory: {self.claude_dir}")

        # Initial file discovery
        files = self._find_jsonl_files()
        print(f"[Claude Code] Found {len(files)} .jsonl files")

        # Initialize file positions (start from end - track NEW content only)
        for file_path in files:
            try:
                self.file_positions[file_path] = file_path.stat().st_size
            except Exception:
                continue

        print("[Claude Code] Tracking started. Press Ctrl+C to stop.")

        # Main monitoring loop
        while True:
            try:
                files = self._find_jsonl_files()

                for file_path in files:
                    # Initialize position for new files
                    if file_path not in self.file_positions:
                        try:
                            # Check if this file was created after we started tracking
                            creation_time = self._get_file_creation_time(file_path)
                            if creation_time >= self._tracking_start_time:
                                # New session file - read from beginning
                                self.file_positions[file_path] = 0
                            else:
                                # Existing file - read only new content
                                self.file_positions[file_path] = file_path.stat().st_size
                        except Exception:
                            continue

                    # Read new content
                    try:
                        with open(file_path) as f:
                            # Seek to last position
                            f.seek(self.file_positions[file_path])

                            # Read new content
                            new_content = f.read()
                            if new_content:
                                # Process each new line
                                for line in new_content.split("\n"):
                                    if line.strip():
                                        result = self.parse_event(line)
                                        if result:
                                            # Track source file (task-50)
                                            self._active_source_files.add(file_path.name)
                                            tool_name, usage = result
                                            self._process_tool_call(tool_name, usage)

                            # Update position
                            self.file_positions[file_path] = f.tell()
                    except Exception as e:
                        self.handle_unrecognized_line(f"Error reading {file_path.name}: {e}")
                        continue

                # Sleep briefly
                time.sleep(0.5)

            except KeyboardInterrupt:
                print("\n[Claude Code] Stopping tracker...")
                # Populate source_files before exit (task-50)
                self.session.source_files = sorted(self._active_source_files)
                break

    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse Claude Code debug.log event.

        Args:
            event_data: JSONL line from debug.log

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tool calls, or
            Tuple of ("__builtin__:<tool>", usage_dict) for built-in tool calls, or
            Tuple of ("__session__", usage_dict) for text-only assistant messages
        """
        try:
            data = json.loads(event_data)

            # Only process assistant messages with usage data
            if data.get("type") != "assistant":
                return None

            message = data.get("message", {})

            # Extract model information (AC #5)
            # Use priority to prefer more capable models (opus > sonnet > haiku)
            # This handles MCP servers that may report their own model (often Haiku)
            model_id = message.get("model")
            if model_id:
                new_priority = _get_model_priority(model_id)
                old_priority = _get_model_priority(self.detected_model or "")
                if new_priority > old_priority:
                    self.detected_model = model_id
                    # Map to human-readable name (AC #15)
                    self.model_name = MODEL_DISPLAY_NAMES.get(model_id, model_id)
                    # Set on session object for persistence
                    self.session.model = model_id

            # Extract token usage
            usage = message.get("usage", {})
            if not usage:
                return None

            # Claude Code format field names
            usage_dict = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_created_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            }

            # Extract tools used (task-46.4: track built-in tools separately)
            mcp_tool_name = None
            builtin_tool_name = None
            tool_params = {}
            content = message.get("content", [])
            if isinstance(content, list):
                for content_block in content:
                    if isinstance(content_block, dict) and content_block.get("type") == "tool_use":
                        tool_name = content_block.get("name")
                        if tool_name:
                            if tool_name.startswith("mcp__"):
                                mcp_tool_name = tool_name
                                tool_params = content_block.get("input", {})
                                break  # Use first MCP tool found
                            else:
                                # Built-in tool (see CLAUDE_CODE_BUILTIN_TOOLS)
                                builtin_tool_name = tool_name
                                tool_params = content_block.get("input", {})
                                # Don't break - MCP tool takes priority

            # Return MCP tool call if found
            if mcp_tool_name:
                usage_dict["tool_params"] = tool_params
                return (mcp_tool_name, usage_dict)

            # Return built-in tool call if found (task-46.4)
            if builtin_tool_name:
                usage_dict["tool_params"] = tool_params
                return (f"__builtin__:{builtin_tool_name}", usage_dict)

            # Return session-level token data for non-tool events (text only)
            # This allows tracking total session tokens even without tool calls
            total_tokens = sum(usage_dict.values())
            if total_tokens > 0:
                return ("__session__", usage_dict)

            return None

        except (json.JSONDecodeError, KeyError) as e:
            self.handle_unrecognized_line(f"Parse error: {e}")
            return None

    def get_platform_metadata(self) -> Dict[str, Any]:
        """
        Get Claude Code platform metadata.

        Returns:
            Dictionary with platform-specific data
        """
        return {
            "model": self.detected_model,
            "model_name": self.model_name,
            "claude_dir": str(self.claude_dir),
            "project_path": self.project_path,
            "files_monitored": len(self.file_positions),
        }

    # ========================================================================
    # Display Integration
    # ========================================================================

    def _get_file_creation_time(self, file_path: Path) -> float:
        """Get file creation time (st_birthtime on macOS, fallback to st_mtime)."""
        try:
            stat = file_path.stat()
            # macOS has st_birthtime for actual creation time
            # Use getattr to avoid mypy error (st_birthtime not in type stubs)
            birthtime = getattr(stat, "st_birthtime", None)
            if birthtime is not None:
                return float(birthtime)
            # Fallback to modification time (less accurate but works cross-platform)
            return stat.st_mtime
        except Exception:
            return 0.0

    def monitor(self, display: Optional["DisplayAdapter"] = None) -> None:
        """
        Main monitoring loop with display integration.

        Args:
            display: Optional DisplayAdapter for real-time UI updates
        """
        self._display = display
        self._start_time = datetime.now()
        self._last_display_update = 0.0
        self._tracking_start_time = time.time()

        print(f"[Claude Code] Initializing tracker for: {self.project_path}")
        print(f"[Claude Code] Monitoring directory: {self.claude_dir}")

        # Initial file discovery
        files = self._find_jsonl_files()
        print(f"[Claude Code] Found {len(files)} .jsonl files")

        # Initialize file positions (start from end - track NEW content only)
        for file_path in files:
            try:
                self.file_positions[file_path] = file_path.stat().st_size
            except Exception:
                continue

        # Main monitoring loop
        while True:
            try:
                files = self._find_jsonl_files()

                for file_path in files:
                    # Initialize position for new files
                    if file_path not in self.file_positions:
                        try:
                            # Check if this file was created after we started tracking
                            creation_time = self._get_file_creation_time(file_path)
                            if creation_time >= self._tracking_start_time:
                                # New session file - read from beginning
                                self.file_positions[file_path] = 0
                            else:
                                # Existing file - read only new content
                                self.file_positions[file_path] = file_path.stat().st_size
                        except Exception:
                            continue

                    # Read new content
                    try:
                        with open(file_path) as f:
                            # Seek to last position
                            f.seek(self.file_positions[file_path])

                            # Read new content
                            new_content = f.read()
                            if new_content:
                                # Process each new line
                                for line in new_content.split("\n"):
                                    if line.strip():
                                        result = self.parse_event(line)
                                        if result:
                                            # Track source file (task-50)
                                            self._active_source_files.add(file_path.name)
                                            tool_name, usage = result
                                            self._process_tool_call(tool_name, usage)

                            # Update position
                            self.file_positions[file_path] = f.tell()
                    except Exception as e:
                        self.handle_unrecognized_line(f"Error reading {file_path.name}: {e}")
                        continue

                # Update display periodically (every 0.5 seconds)
                if display:
                    now = time.time()
                    if now - self._last_display_update >= 0.5:
                        self._last_display_update = now
                        snapshot = self._build_display_snapshot()
                        action = display.update(snapshot)
                        # Handle [Q] quit keybinding (v0.7.0 - task-105.8)
                        if action == "quit":
                            self.session.source_files = sorted(self._active_source_files)
                            break

                # Sleep briefly
                time.sleep(0.2)

            except KeyboardInterrupt:
                # Populate source_files before exit (task-50)
                self.session.source_files = sorted(self._active_source_files)
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

        # Calculate cache tokens (for display purposes)
        cache_tokens = cache_read + cache_created

        # Calculate cache efficiency: percentage of INPUT tokens served from cache
        # (cache_read saves money, cache_created costs more - only count cache_read)
        total_input = input_tokens + cache_created + cache_read
        cache_efficiency = cache_read / total_input if total_input > 0 else 0.0

        # ================================================================
        # Cost Calculation (AC #1, #2, #3, #4, #11, #12)
        # ================================================================
        model = self.detected_model or "claude-sonnet-4-5-20250929"  # Default fallback

        # Calculate actual cost (with cache)
        cost_estimate = self._pricing_config.calculate_cost(
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_created_tokens=cache_created,
            cache_read_tokens=cache_read,
        )

        # Update session cost estimate (AC #2 - persist to JSON)
        self.session.cost_estimate = cost_estimate

        # Calculate cost without cache (all cache tokens charged at input rate)
        # This is what it would cost if no caching existed
        pricing = self._pricing_config.get_model_pricing(model)
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

        # Calculate savings (AC #4)
        cache_savings = cost_no_cache - cost_estimate
        savings_percent = (cache_savings / cost_no_cache * 100) if cost_no_cache > 0 else 0.0

        # Store in session for cache_analysis (task-47.3)
        self.session.cost_no_cache = cost_no_cache
        self.session.cache_savings_usd = cache_savings

        # ================================================================
        # Server Hierarchy (AC #7, #8, #9, #13, #14)
        # ================================================================
        # Build server hierarchy with nested tools
        server_hierarchy: List[Tuple[str, int, int, int, List[Tuple[str, int, int, float]]]] = []

        # Sort servers by total tokens (descending)
        sorted_servers = sorted(
            self.server_sessions.items(),
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

            server_hierarchy.append(
                (server_name, server_calls, server_tokens, server_avg, tools_list)
            )

        # Calculate MCP tokens as percentage of session (AC #14)
        total_mcp_tokens = sum(ss.total_tokens for ss in self.server_sessions.values())
        mcp_tokens_percent = (total_mcp_tokens / total_tokens * 100) if total_tokens > 0 else 0.0

        # Build top tools list (legacy - kept for compatibility)
        top_tools = []
        for server_session in self.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                avg_tokens = (
                    tool_stats.total_tokens // tool_stats.calls if tool_stats.calls > 0 else 0
                )
                top_tools.append((tool_name, tool_stats.calls, tool_stats.total_tokens, avg_tokens))

        # Sort by total tokens descending
        top_tools.sort(key=lambda x: x[2], reverse=True)

        # ================================================================
        # Warnings/Health Check (task-46.10)
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
            platform=self.platform,
            start_time=self._start_time,
            duration_seconds=duration_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_tokens=cache_tokens,
            total_tokens=total_tokens,
            cache_efficiency=cache_efficiency,
            cost_estimate=cost_estimate,
            total_tool_calls=sum(ss.total_calls for ss in self.server_sessions.values()),
            unique_tools=len(
                {tool_name for ss in self.server_sessions.values() for tool_name in ss.tools}
            ),
            top_tools=top_tools[:10],
            # New fields (AC enhancements)
            model_id=self.detected_model or "",
            model_name=self.model_name,
            cost_no_cache=cost_no_cache,
            cache_savings=cache_savings,
            savings_percent=savings_percent,
            server_hierarchy=server_hierarchy,
            mcp_tokens_percent=mcp_tokens_percent,
            # v0.1 Parity Enhancements (task-46)
            message_count=self._message_count,
            cache_created_tokens=cache_created,
            cache_read_tokens=cache_read,
            reasoning_tokens=0,  # v1.3.0: Claude Code doesn't expose reasoning tokens
            builtin_tool_calls=self._builtin_tool_calls,
            builtin_tool_tokens=self._builtin_tool_tokens,
            git_branch=self._git_metadata.get("branch", ""),
            git_commit_short=self._git_metadata.get("commit_short", ""),
            git_status=self._git_metadata.get("status", ""),
            warnings_count=warnings_count,
            health_status=health_status,
            files_monitored=len(self.file_positions),
            # Data quality (v1.5.0 - task-103.5)
            accuracy_level="exact",
            token_source="native",
            data_quality_confidence=1.0,
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

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _process_tool_call(self, tool_name: str, usage: Dict[str, Any]) -> None:
        """
        Process a single tool call or session event.

        Args:
            tool_name: MCP tool name, "__builtin__:<tool>", or "__session__" for non-MCP events
            usage: Token usage dictionary
        """
        total_tokens = (
            usage["input_tokens"]
            + usage["output_tokens"]
            + usage["cache_created_tokens"]
            + usage["cache_read_tokens"]
        )

        # Increment message count for all assistant messages (task-46.1, task-49.1)
        self._message_count += 1
        self.session.message_count = self._message_count  # Persist to session for summary

        # Handle session-level token tracking (non-MCP, non-tool events)
        if tool_name == "__session__":
            # Update session token usage directly (don't record as tool call)
            self.session.token_usage.input_tokens += usage["input_tokens"]
            self.session.token_usage.output_tokens += usage["output_tokens"]
            self.session.token_usage.cache_created_tokens += usage["cache_created_tokens"]
            self.session.token_usage.cache_read_tokens += usage["cache_read_tokens"]
            self.session.token_usage.total_tokens += total_tokens

            # Recalculate cache efficiency: percentage of INPUT tokens served from cache
            total_input = (
                self.session.token_usage.input_tokens
                + self.session.token_usage.cache_created_tokens
                + self.session.token_usage.cache_read_tokens
            )
            if total_input > 0:
                self.session.token_usage.cache_efficiency = (
                    self.session.token_usage.cache_read_tokens / total_input
                )

            # Notify display of session event (but don't show as tool call)
            if hasattr(self, "_display") and self._display:
                self._display.on_event("(session)", total_tokens, datetime.now())
            return

        # Handle built-in tool calls (task-46.4, task-78)
        if tool_name.startswith("__builtin__:"):
            actual_tool_name = tool_name.replace("__builtin__:", "")
            self._builtin_tool_calls += 1
            self._builtin_tool_tokens += total_tokens

            # Track per-tool stats (task-78: for session file output)
            if actual_tool_name not in self._builtin_tool_stats:
                self._builtin_tool_stats[actual_tool_name] = {"calls": 0, "tokens": 0}
            self._builtin_tool_stats[actual_tool_name]["calls"] += 1
            self._builtin_tool_stats[actual_tool_name]["tokens"] += total_tokens

            # Update session's builtin_tool_stats for persistence (task-78)
            self.session.builtin_tool_stats = self._builtin_tool_stats

            # Update session token usage (built-in tools contribute to total)
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

            # Notify display of built-in tool event
            if hasattr(self, "_display") and self._display:
                self._display.on_event(
                    f"[built-in] {actual_tool_name}", total_tokens, datetime.now()
                )
            return

        # Extract tool parameters for duplicate detection
        tool_params = usage.get("tool_params", {})
        content_hash = None
        if tool_params:
            content_hash = self.compute_content_hash(tool_params)

        # Get platform metadata
        platform_data = {"model": self.detected_model, "model_name": self.model_name}

        # Record MCP tool call using BaseTracker
        self.record_tool_call(
            tool_name=tool_name,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_created_tokens=usage["cache_created_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            duration_ms=0,  # Claude Code doesn't provide duration
            content_hash=content_hash,
            platform_data=platform_data,
            # v1.6.0: Multi-model tracking (task-108.2.3)
            model=self.detected_model,
        )

        # Notify display of MCP event
        if hasattr(self, "_display") and self._display:
            self._display.on_event(tool_name, total_tokens, datetime.now())


# ============================================================================
# Standalone Execution
# ============================================================================


def main() -> int:
    """Main entry point for standalone execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Claude Code MCP Tracker (BaseTracker Adapter)")
    parser.add_argument("--project", default="token-audit", help="Project name")
    parser.add_argument("--path", default="", help="Project path (e.g., wp-navigator-pro/main)")
    parser.add_argument(
        "--output",
        default=str(Path.home() / ".token-audit" / "sessions"),
        help="Output directory for session logs (default: ~/.token-audit/sessions)",
    )
    args = parser.parse_args()

    # Create adapter
    print(f"Starting Claude Code tracker for project: {args.project}")
    adapter = ClaudeCodeAdapter(project=args.project, project_path=args.path)

    try:
        # Start tracking
        adapter.start_tracking()
    except KeyboardInterrupt:
        print("\nStopping tracker...")
    finally:
        # Finalize session
        session = adapter.finalize_session()

        # Save session data
        output_dir = Path(args.output)
        adapter.save_session(output_dir)

        print(f"\nSession saved to: {adapter.session_path}")
        print(f"Total tokens: {session.token_usage.total_tokens:,}")
        print(f"MCP calls: {session.mcp_tool_calls.total_calls}")
        print(f"Cache efficiency: {session.token_usage.cache_efficiency:.1%}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
