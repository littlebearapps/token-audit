#!/usr/bin/env python3
"""
GeminiCLIAdapter - Platform adapter for Gemini CLI session tracking

Parses Gemini CLI session JSON files from ~/.gemini/tmp/<project_hash>/chats/
to extract MCP tool usage and token counts.

This adapter reads native Gemini CLI session files - NO OpenTelemetry required.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_tracker import BaseTracker
from .pricing_config import PricingConfig

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
    ):
        """
        Initialize Gemini CLI adapter.

        Args:
            project: Project name (e.g., "mcp-audit")
            gemini_dir: Gemini config directory (default: ~/.gemini)
            project_hash: Project hash (auto-detected if not provided)
            session_file: Specific session file to read (overrides auto-detection)
        """
        super().__init__(project=project, platform="gemini-cli")

        self.gemini_dir = gemini_dir or Path.home() / ".gemini"
        self._project_hash = project_hash
        self._session_file = session_file

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

        Returns:
            Project hash if found, None otherwise
        """
        tmp_dir = self.gemini_dir / "tmp"
        if not tmp_dir.exists():
            return None

        # List all project hash directories
        hashes = []
        for item in tmp_dir.iterdir():
            if item.is_dir() and len(item.name) == 64:  # SHA256 = 64 hex chars
                chats_dir = item / "chats"
                if chats_dir.exists():
                    hashes.append(item.name)

        if not hashes:
            return None

        # If we have a calculated hash, check if it exists
        calculated = self._calculate_project_hash()
        if calculated in hashes:
            return calculated

        # Return most recently modified
        hashes_with_mtime = []
        for h in hashes:
            chats_dir = tmp_dir / h / "chats"
            mtime = chats_dir.stat().st_mtime
            hashes_with_mtime.append((h, mtime))

        hashes_with_mtime.sort(key=lambda x: x[1], reverse=True)
        return hashes_with_mtime[0][0]

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

        print("[Gemini CLI] Tracking started. Press Ctrl+C to stop.")

        # Main monitoring loop
        while True:
            try:
                self._process_session_file(session_file)
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n[Gemini CLI] Stopping tracker...")
                break

    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse a Gemini message into normalized format.

        Args:
            event_data: GeminiMessage object

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tool calls, or
            Tuple of ("__session__", usage_dict) for session token events
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

        # Process tool calls if present
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                result = self._parse_tool_call(tool_call, msg)
                if result:
                    return result

        # Return session-level token data
        usage_dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens + thoughts_tokens,  # Include thoughts as output
            "cache_created_tokens": 0,  # Gemini doesn't report cache creation
            "cache_read_tokens": cached_tokens,
            "thoughts_tokens": thoughts_tokens,
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

    def _parse_tool_call(
        self, tool_call: Dict[str, Any], msg: GeminiMessage
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse a tool call from Gemini message.

        Args:
            tool_call: Tool call data from toolCalls array
            msg: Parent message for token context

        Returns:
            Tuple of (tool_name, usage_dict) for MCP tools, None otherwise
        """
        tool_name = tool_call.get("name", "")

        # Only track MCP tools
        if not tool_name.startswith("mcp__"):
            return None

        # Extract token info from parent message
        tokens = msg.tokens or {}
        tool_tokens = tokens.get("tool", 0)

        usage_dict = {
            "input_tokens": 0,  # Tool-specific tokens not tracked separately
            "output_tokens": tool_tokens,
            "cache_created_tokens": 0,
            "cache_read_tokens": 0,
            "duration_ms": 0,  # Not available in session format
            "success": tool_call.get("status") == "success",
            "tool_call_id": tool_call.get("id", ""),
        }

        return (tool_name, usage_dict)

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
            tool_name: MCP tool name or "__session__" for token events
            usage: Token usage and metadata dictionary
        """
        # Handle session-level token tracking
        if tool_name == "__session__":
            self.session.token_usage.input_tokens += usage["input_tokens"]
            self.session.token_usage.output_tokens += usage["output_tokens"]
            self.session.token_usage.cache_created_tokens += usage["cache_created_tokens"]
            self.session.token_usage.cache_read_tokens += usage["cache_read_tokens"]

            total = (
                usage["input_tokens"]
                + usage["output_tokens"]
                + usage["cache_created_tokens"]
                + usage["cache_read_tokens"]
            )
            self.session.token_usage.total_tokens += total

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

        # Record MCP tool call using BaseTracker
        platform_data = {
            "model": self.detected_model,
            "success": usage.get("success", True),
            "tool_call_id": usage.get("tool_call_id"),
            "thoughts_tokens": self.thoughts_tokens,
        }

        self.record_tool_call(
            tool_name=tool_name,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_created_tokens=usage["cache_created_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            duration_ms=usage.get("duration_ms", 0),
            content_hash=None,
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


# ============================================================================
# Standalone Execution
# ============================================================================


def main() -> int:
    """Main entry point for standalone execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Gemini CLI MCP Tracker")
    parser.add_argument("--project", default="mcp-audit", help="Project name")
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
        default=str(Path.home() / ".mcp-audit" / "sessions"),
        help="Output directory for session logs (default: ~/.mcp-audit/sessions)",
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

    print(f"\nSession saved to: {adapter.session_dir}")
    print(f"Total tokens: {session.token_usage.total_tokens:,}")
    print(f"MCP calls: {session.mcp_tool_calls.total_calls}")
    print(f"Cache efficiency: {session.token_usage.cache_efficiency:.1%}")
    print(f"Thinking tokens: {adapter.thoughts_tokens:,}")
    print(f"Messages: {session.message_count}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
