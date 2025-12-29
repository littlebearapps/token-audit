#!/usr/bin/env python3
"""
Session Manager Module - Session lifecycle and persistence

Handles session creation, lifecycle management, and persistence to disk.

Supports both v1.0.0 and v1.0.4 file formats:
- v1.0.0: summary.json + mcp-{server}.json (deprecated)
- v1.0.4: Single <project>-<timestamp>.json file with _file header
"""

import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .base_tracker import SCHEMA_VERSION, Call, FileHeader, ServerSession, Session


def _now_with_timezone() -> datetime:
    """Get current datetime with local timezone offset."""
    return datetime.now(timezone.utc).astimezone()


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 with timezone offset."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now(timezone.utc).astimezone().tzinfo)
    return dt.isoformat(timespec="seconds")


class SessionManager:
    """
    Manages session lifecycle and persistence.

    Responsibilities:
    - Session directory creation
    - Writing session data to disk
    - Loading sessions from disk
    - Session validation
    - Recovery from incomplete sessions
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize session manager.

        Args:
            base_dir: Base directory for session storage (default: logs/sessions)
        """
        self.base_dir = base_dir or Path("logs/sessions")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_session_directory(self, session_id: str) -> Path:
        """
        Create directory for session data.

        Args:
            session_id: Unique session identifier

        Returns:
            Path to created session directory
        """
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def save_session(self, session: Session, session_dir: Path) -> Dict[str, Path]:
        """
        Save complete session data to disk using v1.0.4 format.

        Creates a single JSON file with:
        - _file: Self-describing header block
        - session: Session metadata and context
        - tool_calls: Flat array of all tool calls
        - mcp_summary: Pre-computed per-server statistics
        - (all other session data)

        Args:
            session: Session object to save
            session_dir: Base directory for session files (date dir will be appended)

        Returns:
            Dictionary mapping file type to file path
        """
        saved_files = {}

        # Create date subdirectory (v1.0.4)
        date_str = session.timestamp.strftime("%Y-%m-%d")
        date_dir = session_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # Generate file name: <project>-<timestamp>.json
        timestamp_str = session.timestamp.strftime("%Y-%m-%dT%H-%M-%S")
        file_name = f"{session.project}-{timestamp_str}.json"
        session_path = date_dir / file_name

        # Build the _file header
        file_header = FileHeader(
            name=file_name,
            type="token_audit_session",
            purpose=(
                "Complete MCP session log with token usage and tool call statistics "
                "for AI agent analysis"
            ),
            schema_version=SCHEMA_VERSION,
            schema_docs="https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
            generated_by=f"token-audit v{__version__}",
            generated_at=_format_timestamp(_now_with_timezone()),
        )

        # Get session data and inject _file header
        session_data = session.to_dict()
        session_data["_file"] = file_header.to_dict()

        # Save as single JSON file
        with open(session_path, "w") as f:
            json.dump(session_data, f, indent=2, default=str)
        saved_files["session"] = session_path

        return saved_files

    def load_session(self, session_path: Path) -> Optional[Session]:
        """
        Load session from disk.

        Supports both v1.0.0 and v1.0.4 formats:
        - v1.0.0: Directory containing summary.json + mcp-{server}.json files
        - v1.0.4: Single <project>-<timestamp>.json file (or directory containing it)

        Args:
            session_path: Path to session file (v1.0.4) or directory (v1.0.0/v1.0.4)

        Returns:
            Session object if successful, None otherwise
        """
        # Handle file path (v1.0.4 direct file reference)
        if session_path.is_file():
            return self._load_session_from_file(session_path)

        # Handle directory path
        session_dir = session_path

        # Try v1.0.4 format first (single JSON file in directory)
        v1_1_session = self._load_session_v1_1(session_dir)
        if v1_1_session:
            return v1_1_session

        # Fall back to v1.0.0 format (summary.json + mcp-*.json)
        return self._load_session_v1_0(session_dir)

    def _load_session_from_file(self, session_file: Path) -> Optional[Session]:
        """
        Load session directly from a v1.0.4 session file.

        Args:
            session_file: Path to session JSON file

        Returns:
            Session object if successful, None otherwise
        """
        try:
            with open(session_file) as f:
                data = json.load(f)

            # Check for _file header (v1.0.4 indicator)
            if "_file" not in data:
                return None

            # Validate schema version (accept any v1.x)
            file_header = data.get("_file", {})
            schema_version = file_header.get("schema_version", "")
            if not schema_version.startswith("1."):
                return None

            # Reconstruct Session from v1.x format
            return self._reconstruct_session_v1_1(data)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading v1.x session from {session_file}: {e}")
            return None

    def _is_v1_0_server_file(self, filename: str) -> bool:
        """
        Check if filename looks like a v1.0.0 server file (mcp-{server}.json).

        v1.0.0 server files: mcp-zen.json, mcp-backlog.json (short names, no timestamp)
        v1.0.4 session files: project-2025-12-01T15-25-58.json (has ISO timestamp)

        Args:
            filename: The filename to check

        Returns:
            True if this looks like a v1.0.0 server file
        """
        import re

        # v1.0.0 server files: mcp-{short-server-name}.json
        # Pattern: mcp-{word}.json where word is a simple server name
        if not filename.startswith("mcp-"):
            return False

        # v1.0.4 files have ISO timestamp pattern in the name
        # e.g., token-audit-2025-12-01T15-25-58.json
        has_timestamp = bool(re.search(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", filename))

        # If it has a timestamp, it's v1.0.4; if not, it's v1.0.0 server file
        return not has_timestamp

    def _load_session_v1_1(self, session_dir: Path) -> Optional[Session]:
        """
        Load session from v1.0.4 format (single JSON file).

        Args:
            session_dir: Directory containing session file

        Returns:
            Session object if successful, None otherwise
        """
        # Look for single session file (not summary.json or v1.0.0 server files)
        # v1.0.0 server files: mcp-{server}.json (short names like mcp-zen.json)
        # v1.0.4 session files: {project}-{timestamp}.json (has ISO timestamp)
        session_files = [
            f
            for f in session_dir.glob("*.json")
            if f.name != "summary.json" and not self._is_v1_0_server_file(f.name)
        ]

        if not session_files:
            return None

        # Use the most recent file if multiple exist
        session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        session_file = session_files[0]

        try:
            with open(session_file) as f:
                data = json.load(f)

            # Check for _file header (v1.0.4 indicator)
            if "_file" not in data:
                return None

            # Validate schema version (accept any v1.x)
            file_header = data.get("_file", {})
            schema_version = file_header.get("schema_version", "")
            if not schema_version.startswith("1."):
                return None

            # Reconstruct Session from v1.x format
            return self._reconstruct_session_v1_1(data)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading v1.x session from {session_file}: {e}")
            return None

    def _load_session_v1_0(self, session_dir: Path) -> Optional[Session]:
        """
        Load session from v1.0.0 format (summary.json + mcp-*.json).

        Args:
            session_dir: Directory containing session files

        Returns:
            Session object if successful, None otherwise
        """
        summary_path = session_dir / "summary.json"
        if not summary_path.exists():
            return None

        try:
            with open(summary_path) as f:
                data = json.load(f)

            # Validate schema version
            if not self._validate_schema_version(data):
                return None

            # Reconstruct Session object
            session = self._reconstruct_session(data)

            # Load server sessions from mcp-*.json files
            for server_file in session_dir.glob("mcp-*.json"):
                server_name = server_file.stem[4:]  # Remove 'mcp-' prefix
                server_session = self._load_server_session_v1_0(server_file)
                if server_session:
                    session.server_sessions[server_name] = server_session

            return session

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading v1.0.0 session from {session_dir}: {e}")
            return None

    def _validate_schema_version(self, data: Dict[str, Any]) -> bool:
        """
        Validate schema version compatibility.

        Args:
            data: Session data dictionary

        Returns:
            True if compatible, False otherwise
        """
        if "schema_version" not in data:
            # Legacy data (pre-v1.0) - allow with warning
            print("Warning: Legacy session data (pre-v1.0) - attempting to load")
            # Add default schema version for legacy data
            data["schema_version"] = "0.0.0"
            return True

        session_version = data["schema_version"]
        major, minor, patch = self._parse_version(session_version)
        current_major, current_minor, _ = self._parse_version(SCHEMA_VERSION)

        # Legacy data (0.x.x) - allow with conversion attempt
        if major == 0:
            print("Warning: Legacy session data (v0.x) - attempting to load")
            return True

        # Major version must match for v1.0+
        if major != current_major:
            print(f"Error: Incompatible major version: {major} != {current_major}")
            return False

        # Minor version can be older (forward compatible)
        if minor > current_minor:
            print(f"Warning: Future minor version detected: {minor} > {current_minor}")

        return True

    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """Parse version string into (major, minor, patch) tuple"""
        parts = version_str.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    def _convert_legacy_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy (pre-v1.0) session data to v1.0 format.

        Args:
            data: Legacy session data dictionary

        Returns:
            Converted data in v1.0 format
        """
        # Extract from legacy nested structure
        session_info = data.get("session", {})
        tokens = data.get("tokens", {})
        costs = data.get("costs", {})
        mcp_summary = data.get("mcp_summary", {})

        # Map legacy fields to v1.0 format
        converted = {
            "schema_version": "1.0.0",
            "project": session_info.get("directory", "unknown"),
            "platform": "claude_code",  # Assume Claude Code for legacy
            "timestamp": session_info.get("start_time", datetime.now().isoformat()),
            "session_id": f"legacy-{session_info.get('start_time', 'unknown')[:19].replace(':', '-')}",
            "token_usage": {
                "input_tokens": tokens.get("input", 0),
                "output_tokens": tokens.get("output", 0),
                "cache_created_tokens": tokens.get("cache_create", 0),
                "cache_read_tokens": tokens.get("cache_read", 0),
            },
            "cost_estimate": costs.get("with_cache", {}).get("usd", 0.0),
            "mcp_tool_calls": {
                "total_calls": mcp_summary.get("total_calls", 0),
                "unique_tools": len(mcp_summary.get("top_5_servers", [])),
            },
            "redundancy_analysis": data.get("redundancy_analysis"),
            "anomalies": data.get("anomalies", {}).get("high_token_operations", []),
            "end_timestamp": session_info.get("end_time"),
            "duration_seconds": session_info.get("duration_seconds"),
        }

        return converted

    def _reconstruct_session(self, data: Dict[str, Any]) -> Session:
        """
        Reconstruct Session object from v1.0.0 dictionary format.

        Args:
            data: Session data dictionary

        Returns:
            Session object
        """
        # Import needed for type reconstruction
        from .base_tracker import MCPToolCalls, TokenUsage

        # Check if legacy data needs conversion
        if data.get("schema_version") == "0.0.0" or "session" in data:
            data = self._convert_legacy_data(data)

        # Reconstruct timestamp
        timestamp = datetime.fromisoformat(data["timestamp"])
        end_timestamp = None
        if data.get("end_timestamp"):
            end_timestamp = datetime.fromisoformat(data["end_timestamp"])

        # Reconstruct TokenUsage
        token_data = data.get("token_usage", {})
        # Migrate old field names (task-205: schema compatibility)
        if "cache_write_tokens" in token_data:
            token_data["cache_created_tokens"] = token_data.pop("cache_write_tokens")
        token_usage = TokenUsage(**token_data) if token_data else TokenUsage()

        # Reconstruct MCPToolCalls
        mcp_calls_data = data.get("mcp_tool_calls", {})
        mcp_tool_calls = MCPToolCalls(**mcp_calls_data) if mcp_calls_data else MCPToolCalls()

        # Create Session object (with default values for new v1.0.4 fields)
        session = Session(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            mcp_audit_version=data.get("mcp_audit_version", ""),
            project=data.get("project", "unknown"),
            platform=data.get("platform", "unknown"),
            model=data.get("model", ""),
            working_directory=data.get("working_directory", ""),
            timestamp=timestamp,
            session_id=data.get("session_id", ""),
            token_usage=token_usage,
            cost_estimate=data.get("cost_estimate_usd", data.get("cost_estimate", 0.0)),
            mcp_tool_calls=mcp_tool_calls,
            server_sessions={},  # Will be loaded separately
            redundancy_analysis=data.get("redundancy_analysis"),
            anomalies=data.get("anomalies", []),
            end_timestamp=end_timestamp,
            duration_seconds=data.get("duration_seconds"),
            source_files=data.get("source_files", []),
        )

        return session

    def _reconstruct_session_v1_1(self, data: Dict[str, Any]) -> Session:
        """
        Reconstruct Session object from v1.0.4 format.

        Args:
            data: Session data dictionary with _file header

        Returns:
            Session object
        """
        from .base_tracker import (
            MCPToolCalls,
            ModelUsage,
            ServerSession,
            Smell,
            TokenUsage,
            ToolStats,
        )

        # Extract _file header info
        file_header = data.get("_file", {})
        schema_version = file_header.get("schema_version", SCHEMA_VERSION)

        # Extract session block (v1.0.4 has nested session)
        session_data = data.get("session", data)

        # Reconstruct timestamp
        # v1.0.4 uses "started_at", v1.0.0 uses "start_time" or "timestamp"
        timestamp_str = session_data.get(
            "started_at", session_data.get("start_time", session_data.get("timestamp", ""))
        )
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else _now_with_timezone()

        end_timestamp = None
        # v1.0.4 uses "ended_at", v1.0.0 uses "end_time" or "end_timestamp"
        end_time_str = session_data.get(
            "ended_at", session_data.get("end_time", data.get("end_timestamp"))
        )
        if end_time_str:
            end_timestamp = datetime.fromisoformat(end_time_str)

        # Reconstruct TokenUsage
        token_data = data.get("token_usage", {})
        # Migrate old field names (task-205: schema compatibility)
        if "cache_write_tokens" in token_data:
            token_data["cache_created_tokens"] = token_data.pop("cache_write_tokens")
        token_usage = TokenUsage(**token_data) if token_data else TokenUsage()

        # Reconstruct MCPToolCalls from mcp_summary (v1.0.4 format)
        mcp_summary = data.get("mcp_summary", {})
        if mcp_summary:
            # v1.0.4: MCPSummary has total_calls, unique_tools, top_by_calls
            top_by_calls = mcp_summary.get("top_by_calls", [])
            most_called = ""
            if top_by_calls:
                top_tool = top_by_calls[0]
                most_called = f"{top_tool.get('tool', '')} ({top_tool.get('calls', 0)} calls)"
            mcp_tool_calls = MCPToolCalls(
                total_calls=mcp_summary.get("total_calls", 0),
                unique_tools=mcp_summary.get("unique_tools", 0),
                most_called=most_called,
            )
        else:
            # Fallback: try legacy mcp_tool_calls format or compute from tool_calls
            mcp_calls_data = data.get("mcp_tool_calls", {})
            mcp_tool_calls = MCPToolCalls(**mcp_calls_data) if mcp_calls_data else MCPToolCalls()

        # Reconstruct tool_calls
        tool_calls_data = data.get("tool_calls", [])
        # Group by server for server_sessions
        server_tools: Dict[str, Dict[str, ToolStats]] = {}
        for call_data in tool_calls_data:
            server = call_data.get("server", "unknown")
            tool_name = call_data.get("tool", call_data.get("tool_name", ""))

            if server not in server_tools:
                server_tools[server] = {}

            if tool_name not in server_tools[server]:
                server_tools[server][tool_name] = ToolStats()

            # Update tool stats
            stats = server_tools[server][tool_name]
            stats.calls += 1
            stats.total_tokens += call_data.get("total_tokens", 0)
            if stats.calls > 0:
                stats.avg_tokens = stats.total_tokens // stats.calls

            # Create Call object and add to call_history (task-247.4: bucket classification)
            call_timestamp_str = call_data.get("timestamp", "")
            call_timestamp = timestamp  # Fallback to session timestamp
            if call_timestamp_str:
                with contextlib.suppress(ValueError, TypeError):
                    call_timestamp = datetime.fromisoformat(call_timestamp_str)

            call = Call(
                timestamp=call_timestamp,
                tool_name=tool_name,
                server=server,
                index=call_data.get("index", len(stats.call_history)),
                input_tokens=call_data.get("input_tokens", 0),
                output_tokens=call_data.get("output_tokens", 0),
                cache_created_tokens=call_data.get("cache_created_tokens", 0),
                cache_read_tokens=call_data.get("cache_read_tokens", 0),
                total_tokens=call_data.get("total_tokens", 0),
                duration_ms=call_data.get("duration_ms", 0) or 0,
                content_hash=call_data.get("content_hash"),
                is_estimated=call_data.get("is_estimated", False),
                estimation_method=call_data.get("estimation_method"),
                estimation_encoding=call_data.get("estimation_encoding"),
                model=call_data.get("model"),
            )
            stats.call_history.append(call)

        # Build server_sessions
        server_sessions = {}
        mcp_summary_data = data.get("mcp_summary", {})
        for server, tools in server_tools.items():
            server_data = mcp_summary_data.get(server, {})
            server_sessions[server] = ServerSession(
                server=server,
                tools=tools,
                total_calls=server_data.get("total_calls", sum(t.calls for t in tools.values())),
                total_tokens=server_data.get(
                    "total_tokens", sum(t.total_tokens for t in tools.values())
                ),
            )

        # Reconstruct smells from v1.5.0+ format
        smells_data = data.get("smells", [])
        smells = []
        for smell_dict in smells_data:
            smell = Smell(
                pattern=smell_dict.get("pattern", ""),
                severity=smell_dict.get("severity", "info"),
                tool=smell_dict.get("tool"),
                description=smell_dict.get("description", ""),
                evidence=smell_dict.get("evidence", {}),
            )
            smells.append(smell)

        # Reconstruct model_usage from v1.6.0+ format (task-225.3: aggregation support)
        model_usage_data = data.get("model_usage", {})
        model_usage: Dict[str, ModelUsage] = {}
        for model_name, usage_dict in model_usage_data.items():
            model_usage[model_name] = ModelUsage(
                model=model_name,
                input_tokens=usage_dict.get("input_tokens", 0),
                output_tokens=usage_dict.get("output_tokens", 0),
                cache_created_tokens=usage_dict.get("cache_created_tokens", 0),
                cache_read_tokens=usage_dict.get("cache_read_tokens", 0),
                total_tokens=usage_dict.get("total_tokens", 0),
                cost_usd=usage_dict.get("cost_usd", 0.0),
                call_count=usage_dict.get("call_count", 0),
            )

        # Reconstruct models_used list (v1.6.0+)
        models_used = data.get("models_used", session_data.get("models_used", []))

        # Create Session object
        session = Session(
            schema_version=schema_version,
            mcp_audit_version=data.get("mcp_audit_version", ""),
            project=session_data.get("project", data.get("project", "unknown")),
            platform=session_data.get("platform", data.get("platform", "unknown")),
            model=session_data.get("model", data.get("model", "")),
            working_directory=session_data.get(
                "working_directory", data.get("working_directory", "")
            ),
            timestamp=timestamp,
            session_id=session_data.get("id", data.get("session_id", "")),
            token_usage=token_usage,
            cost_estimate=data.get("cost_estimate_usd", data.get("cost_estimate", 0.0)),
            mcp_tool_calls=mcp_tool_calls,
            server_sessions=server_sessions,
            redundancy_analysis=data.get("redundancy_analysis"),
            anomalies=data.get("anomalies", []),
            end_timestamp=end_timestamp,
            duration_seconds=data.get("duration_seconds", session_data.get("duration_seconds")),
            source_files=data.get("source_files", []),
            smells=smells,
            models_used=models_used,
            model_usage=model_usage,
        )

        return session

    def _load_server_session_v1_0(self, server_file: Path) -> Optional[ServerSession]:
        """
        Load ServerSession from v1.0.0 format file.

        Note: v1.0.4 removed schema_version from Call and ToolStats, so we
        skip those fields when reconstructing.

        Args:
            server_file: Path to mcp-{server}.json file

        Returns:
            ServerSession object if successful, None otherwise
        """
        try:
            with open(server_file) as f:
                data = json.load(f)

            # Import needed for type reconstruction
            from .base_tracker import Call, ToolStats

            # Reconstruct ToolStats for each tool
            tools = {}
            for tool_name, tool_data in data.get("tools", {}).items():
                # Reconstruct Call objects (skip schema_version - removed in v1.0.4)
                call_history = []
                for call_data in tool_data.get("call_history", []):
                    call = Call(
                        timestamp=datetime.fromisoformat(call_data["timestamp"]),
                        tool_name=call_data.get("tool_name", call_data.get("tool", "")),
                        server=call_data.get("server", ""),
                        index=call_data.get("index", 0),
                        input_tokens=call_data.get("input_tokens", 0),
                        output_tokens=call_data.get("output_tokens", 0),
                        cache_created_tokens=call_data.get("cache_created_tokens", 0),
                        cache_read_tokens=call_data.get("cache_read_tokens", 0),
                        total_tokens=call_data.get("total_tokens", 0),
                        duration_ms=call_data.get("duration_ms", 0),
                        content_hash=call_data.get("content_hash"),
                        platform_data=call_data.get("platform_data"),
                    )
                    call_history.append(call)

                # Create ToolStats object (skip schema_version - removed in v1.0.4)
                tool_stats = ToolStats(
                    calls=tool_data.get("calls", 0),
                    total_tokens=tool_data.get("total_tokens", 0),
                    avg_tokens=tool_data.get("avg_tokens", 0),
                    call_history=call_history,
                    total_duration_ms=tool_data.get("total_duration_ms"),
                    avg_duration_ms=tool_data.get("avg_duration_ms"),
                    max_duration_ms=tool_data.get("max_duration_ms"),
                    min_duration_ms=tool_data.get("min_duration_ms"),
                )
                tools[tool_name] = tool_stats

            # Create ServerSession object (skip schema_version - removed in v1.0.4)
            server_session = ServerSession(
                server=data.get("server", "unknown"),
                tools=tools,
                total_calls=data.get("total_calls", 0),
                total_tokens=data.get("total_tokens", 0),
                metadata=data.get("metadata"),
            )

            return server_session

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading v1.0.0 server session from {server_file}: {e}")
            return None

    def list_sessions(self, limit: Optional[int] = None) -> List[Path]:
        """
        List all session paths.

        Supports both v1.0.0 and v1.0.4 formats:
        - v1.0.0: Returns directories containing summary.json
        - v1.0.4: Returns parent directories of individual session files

        Args:
            limit: Maximum number of sessions to return (most recent first)

        Returns:
            List of session paths, sorted by timestamp (newest first).
            For v1.0.0, returns session directories.
            For v1.0.4, returns parent directories of session files (may have duplicates).
        """
        if not self.base_dir.exists():
            return []

        sessions: List[Tuple[Path, datetime]] = []

        # Iterate through base_dir
        for item in self.base_dir.iterdir():
            if not item.is_dir():
                continue

            # Check for v1.0.0 format (summary.json in directory)
            if (item / "summary.json").exists():
                # Try to extract timestamp from directory name
                try:
                    # Format: project-YYYY-MM-DD-HHMMSS
                    parts = item.name.rsplit("-", 4)
                    if len(parts) >= 4:
                        date_str = "-".join(parts[-4:])
                        ts = datetime.strptime(date_str, "%Y-%m-%d-%H%M%S")
                        sessions.append((item, ts))
                except (ValueError, IndexError):
                    # Use file modification time as fallback
                    sessions.append((item, datetime.fromtimestamp(item.stat().st_mtime)))
                continue

            # Check for v1.0.4 format (date directory with session files)
            # Date directories look like: YYYY-MM-DD
            try:
                datetime.strptime(item.name, "%Y-%m-%d")
            except ValueError:
                continue  # Not a date directory

            # Find all session files in this date directory
            for session_file in item.glob("*.json"):
                if session_file.name == "summary.json" or session_file.name.startswith("mcp-"):
                    continue  # Skip v1.0.0 files in date directories (shouldn't happen)

                # Check if it's a v1.0.4 file (has _file header)
                try:
                    with open(session_file) as f:
                        data = json.load(f)
                    if "_file" in data:
                        # Extract timestamp from session data
                        session_data = data.get("session", {})
                        ts_str = session_data.get("started_at", "")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                        else:
                            ts = datetime.fromtimestamp(session_file.stat().st_mtime)
                        # Return the session file's parent (date directory) with file as marker
                        # Store file path directly for v1.0.4
                        sessions.append((session_file, ts))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        # Sort by timestamp (newest first)
        sessions.sort(key=lambda x: x[1], reverse=True)

        # Apply limit if specified
        session_paths = [s[0] for s in sessions]
        if limit:
            session_paths = session_paths[:limit]

        return session_paths

    def find_incomplete_sessions(self) -> List[Path]:
        """
        Find sessions that are missing required files.

        For v1.0.0: Directories without summary.json
        For v1.0.4: Not applicable (single file = complete session)

        Returns:
            List of incomplete session directory paths (v1.0.0 only)
        """
        if not self.base_dir.exists():
            return []

        incomplete = []

        # Check for v1.0.0 format (directories with no summary.json)
        for item in self.base_dir.iterdir():
            if not item.is_dir():
                continue

            # Skip date directories (v1.0.4 format)
            try:
                datetime.strptime(item.name, "%Y-%m-%d")
                continue  # Skip v1.0.4 date directories
            except ValueError:
                pass

            # Check for v1.0.0 incomplete (directory without summary.json)
            if not (item / "summary.json").exists():
                incomplete.append(item)

        return incomplete

    def recover_from_events(self, session_dir: Path) -> Optional[Session]:
        """
        Recover session data from events.jsonl file.

        Used when session was interrupted and summary.json is missing.

        Args:
            session_dir: Directory containing events.jsonl

        Returns:
            Recovered Session object if successful, None otherwise
        """
        events_file = session_dir / "events.jsonl"
        if not events_file.exists():
            return None

        print(f"Attempting recovery from {events_file}")

        # TODO: Implement event stream parsing and session reconstruction
        # This would parse events.jsonl line by line and rebuild the session
        # For now, return None (will be implemented in future)

        return None

    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """
        Remove sessions older than specified age.

        Args:
            max_age_days: Maximum age in days

        Returns:
            Number of sessions deleted
        """
        import shutil
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0

        for session_dir in self.list_sessions():
            # Extract timestamp from directory name
            # Format: {project}-{YYYY-MM-DD-HHMMSS}
            try:
                parts = session_dir.name.rsplit("-", 4)
                if len(parts) >= 4:
                    date_str = "-".join(parts[-4:])  # YYYY-MM-DD-HHMMSS
                    session_date = datetime.strptime(date_str, "%Y-%m-%d-%H%M%S")

                    if session_date < cutoff_date:
                        shutil.rmtree(session_dir)
                        deleted_count += 1
            except (ValueError, IndexError):
                # Skip if can't parse timestamp
                continue

        return deleted_count


# ============================================================================
# Convenience Functions
# ============================================================================


def save_session(session: Session, session_dir: Path) -> Dict[str, Path]:
    """
    Convenience function to save a session.

    Args:
        session: Session object to save
        session_dir: Directory to save session files

    Returns:
        Dictionary mapping file type to file path
    """
    manager = SessionManager()
    return manager.save_session(session, session_dir)


def load_session(session_dir: Path) -> Optional[Session]:
    """
    Convenience function to load a session.

    Args:
        session_dir: Directory containing session files

    Returns:
        Session object if successful, None otherwise
    """
    manager = SessionManager()
    return manager.load_session(session_dir)


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Manual test
    print("Session Manager Module Tests")
    print("=" * 60)

    manager = SessionManager(base_dir=Path("test_sessions"))

    # Test session directory creation
    session_dir = manager.create_session_directory("test-session-001")
    print(f"Created session directory: {session_dir}")

    # Test listing sessions
    sessions = manager.list_sessions()
    print(f"\nFound {len(sessions)} sessions")

    # Test cleanup
    print("\nSession manager initialized successfully")
