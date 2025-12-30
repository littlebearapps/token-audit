#!/usr/bin/env python3
"""
Storage Module - JSONL directory structure and session persistence

Implements the standardized storage layout:
    ~/.token-audit/sessions/<platform>/<YYYY-MM-DD>/<session-id>.jsonl

This module provides:
- Platform-separated session storage
- Date-based organization for efficient queries
- Index files for cross-session discovery
- Migration helpers from v0.x format
- Automatic migration from ~/.mcp-audit to ~/.token-audit
"""

import fcntl
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Literal, Optional

try:
    from filelock import FileLock

    _HAS_FILELOCK = True
except ImportError:
    FileLock = None  # type: ignore
    _HAS_FILELOCK = False

# Schema version for storage format
STORAGE_SCHEMA_VERSION = "1.0.0"

# Supported platforms
Platform = Literal["claude_code", "codex_cli", "gemini_cli", "ollama_cli", "custom"]
SUPPORTED_PLATFORMS: List[Platform] = [
    "claude_code",
    "codex_cli",
    "gemini_cli",
    "ollama_cli",
    "custom",
]

# Active session directory for live streaming
ACTIVE_SESSION_DIR = "active"

# Lock timeout in seconds for file operations
FILE_LOCK_TIMEOUT = 10.0


def _atomic_write_json(target_path: Path, data: Dict[str, Any]) -> None:
    """
    Write JSON data atomically using temp file + rename pattern.

    This ensures readers never see partial/corrupt files.

    Args:
        target_path: Path to write the JSON data to
        data: Dictionary data to write as JSON

    Raises:
        OSError: If file operations fail
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (for atomic rename on same filesystem)
    fd, temp_path_str = tempfile.mkstemp(
        dir=target_path.parent,
        prefix=f".{target_path.stem}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        # Atomic rename (POSIX guarantees atomicity for same filesystem)
        temp_path.rename(target_path)
    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise


@contextmanager
def _index_file_lock(index_path: Path) -> Generator[None, None, None]:
    """
    Context manager for cross-process file locking on index files.

    Uses filelock for cross-process safety. Holds the lock for the
    duration of the context, allowing safe read-modify-write cycles.

    Args:
        index_path: Path to the index file to lock

    Yields:
        None

    Raises:
        Timeout: If lock cannot be acquired within FILE_LOCK_TIMEOUT
    """
    lock_path = index_path.with_suffix(index_path.suffix + ".lock")

    if _HAS_FILELOCK and FileLock is not None:
        # Use filelock for cross-process safety
        lock = FileLock(str(lock_path), timeout=FILE_LOCK_TIMEOUT)
        with lock:
            yield
    else:
        # Fallback: no locking (safe for single-process use)
        # Note: fcntl is Unix-only and doesn't work well for this pattern
        yield


def _migrate_legacy_storage() -> None:
    """
    One-time migration from ~/.mcp-audit to ~/.token-audit.

    Copies all data from the legacy location to the new location if:
    - The old directory exists
    - The new directory does not exist

    Creates a marker file to track that migration occurred.
    """
    import shutil

    old_base = Path.home() / ".mcp-audit"
    new_base = Path.home() / ".token-audit"

    if old_base.exists() and not new_base.exists():
        try:
            shutil.copytree(old_base, new_base)
            # Create marker file to track migration
            marker = new_base / ".migrated-from-mcp-audit"
            marker.touch()
            print(f"[token-audit] Migrated data from {old_base} to {new_base}")
        except Exception as e:
            # Don't fail if migration fails - just use new location
            print(f"[token-audit] Warning: Migration failed: {e}")


def get_default_base_dir() -> Path:
    """
    Get the default base directory for token-audit data.

    Checks TOKEN_AUDIT_STORAGE_DIR environment variable first,
    then falls back to ~/.token-audit/sessions/.

    Performs one-time migration from ~/.mcp-audit if needed.

    Returns:
        Path to session storage directory
    """
    import os

    env_dir = os.environ.get("TOKEN_AUDIT_STORAGE_DIR")
    if env_dir:
        return Path(env_dir)

    # Perform one-time migration if needed
    _migrate_legacy_storage()

    return Path.home() / ".token-audit" / "sessions"


@dataclass
class SessionIndex:
    """
    Index entry for a single session.

    Used for efficient cross-session queries without loading full session data.
    """

    schema_version: str
    session_id: str
    platform: Platform
    date: str  # YYYY-MM-DD format
    started_at: str  # ISO 8601 timestamp
    ended_at: Optional[str]  # ISO 8601 timestamp or None if incomplete
    project: Optional[str]
    total_tokens: int
    total_cost: float
    tool_count: int
    server_count: int
    is_complete: bool
    file_path: str  # Relative path from base_dir
    file_size_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionIndex":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class DailyIndex:
    """
    Index file for a single day's sessions.

    Stored at: <platform>/<YYYY-MM-DD>/.index.json
    """

    schema_version: str
    platform: Platform
    date: str  # YYYY-MM-DD
    sessions: List[SessionIndex] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0
    session_count: int = 0
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "platform": self.platform,
            "date": self.date,
            "sessions": [s.to_dict() for s in self.sessions],
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "session_count": self.session_count,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyIndex":
        """Create from dictionary."""
        sessions = [SessionIndex.from_dict(s) for s in data.get("sessions", [])]
        return cls(
            schema_version=data["schema_version"],
            platform=data["platform"],
            date=data["date"],
            sessions=sessions,
            total_tokens=data.get("total_tokens", 0),
            total_cost=data.get("total_cost", 0.0),
            session_count=data.get("session_count", 0),
            last_updated=data.get("last_updated"),
        )

    def add_session(self, session_index: SessionIndex) -> None:
        """Add a session to the daily index."""
        self.sessions.append(session_index)
        self.total_tokens += session_index.total_tokens
        self.total_cost += session_index.total_cost
        self.session_count += 1
        self.last_updated = datetime.now().isoformat()

    def recalculate_totals(self) -> None:
        """Recalculate aggregate totals from sessions."""
        self.total_tokens = sum(s.total_tokens for s in self.sessions)
        self.total_cost = sum(s.total_cost for s in self.sessions)
        self.session_count = len(self.sessions)


@dataclass
class PlatformIndex:
    """
    Index file for a platform's sessions.

    Stored at: <platform>/.index.json
    Provides quick access to date ranges and totals without scanning directories.
    """

    schema_version: str
    platform: Platform
    dates: List[str] = field(default_factory=list)  # List of YYYY-MM-DD with sessions
    total_sessions: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    first_session_date: Optional[str] = None
    last_session_date: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformIndex":
        """Create from dictionary."""
        return cls(**data)


class StorageManager:
    """
    Manages session storage with the standardized directory structure.

    Directory Layout:
        ~/.token-audit/
        ├── sessions/
        │   ├── claude_code/
        │   │   ├── .index.json              # Platform-level index
        │   │   ├── 2025-11-24/
        │   │   │   ├── .index.json          # Daily index
        │   │   │   ├── session-abc123.jsonl # Session events
        │   │   │   └── session-def456.jsonl
        │   │   └── 2025-11-25/
        │   │       └── ...
        │   ├── codex_cli/
        │   │   └── ...
        │   └── gemini_cli/
        │       └── ...
        └── config/
            └── token-audit.toml             # User configuration

    File Formats:
        - .jsonl files: Line-delimited JSON events (one event per line)
        - .index.json files: Metadata indexes for efficient queries
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize storage manager.

        Args:
            base_dir: Base directory for session storage.
                      Defaults to ~/.token-audit/sessions/
        """
        self.base_dir = base_dir or get_default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Performance optimization: mtime caching (v0.9.0 - task-107.3)
        # Cache file modification times to reduce stat() calls in list_sessions
        self._mtime_cache: Dict[Path, float] = {}
        self._mtime_cache_timestamp: float = 0.0
        self._mtime_cache_ttl: float = 60.0  # Refresh cache every 60 seconds

    # =========================================================================
    # Path Generation
    # =========================================================================

    def get_platform_dir(self, platform: Platform) -> Path:
        """Get directory for a specific platform.

        Note: Platform names use underscores internally (claude_code) but
        directory names use hyphens (claude-code) for CLI consistency.
        """
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform: {platform}. Must be one of {SUPPORTED_PLATFORMS}"
            )
        # Convert underscore to hyphen for directory name (e.g., claude_code -> claude-code)
        dir_name = platform.replace("_", "-")
        return self.base_dir / dir_name

    def get_date_dir(self, platform: Platform, session_date: date) -> Path:
        """Get directory for a specific date."""
        date_str = session_date.strftime("%Y-%m-%d")
        return self.get_platform_dir(platform) / date_str

    def get_session_path(self, platform: Platform, session_date: date, session_id: str) -> Path:
        """
        Get the path for a session file.

        Args:
            platform: Platform identifier
            session_date: Date of the session
            session_id: Unique session identifier

        Returns:
            Path to the session .jsonl file
        """
        return self.get_date_dir(platform, session_date) / f"{session_id}.jsonl"

    def generate_session_id(self, platform: Platform, timestamp: Optional[datetime] = None) -> str:
        """
        Generate a unique session ID.

        Format: session-{timestamp}-{random}
        Example: session-20251124T143052-a1b2c3

        Args:
            platform: Platform identifier (for context, not included in ID)
            timestamp: Session start time (defaults to now)

        Returns:
            Unique session identifier
        """
        import secrets

        ts = timestamp or datetime.now()
        ts_str = ts.strftime("%Y%m%dT%H%M%S")
        random_suffix = secrets.token_hex(3)  # 6 hex chars

        return f"session-{ts_str}-{random_suffix}"

    # =========================================================================
    # Session Writing
    # =========================================================================

    def create_session_file(
        self, platform: Platform, session_id: str, session_date: Optional[date] = None
    ) -> Path:
        """
        Create a new session file and its parent directories.

        Args:
            platform: Platform identifier
            session_id: Unique session identifier
            session_date: Date for the session (defaults to today)

        Returns:
            Path to the created session file
        """
        session_date = session_date or date.today()
        session_path = self.get_session_path(platform, session_date, session_id)

        # Create parent directories
        session_path.parent.mkdir(parents=True, exist_ok=True)

        # Create empty file
        session_path.touch()

        return session_path

    def append_event(self, session_path: Path, event: Dict[str, Any]) -> None:
        """
        Append an event to a session file.

        Args:
            session_path: Path to the session .jsonl file
            event: Event data to append
        """
        with open(session_path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def write_session_events(self, session_path: Path, events: List[Dict[str, Any]]) -> None:
        """
        Write all events to a session file (overwrites existing).

        Args:
            session_path: Path to the session .jsonl file
            events: List of events to write
        """
        with open(session_path, "w") as f:
            for event in events:
                f.write(json.dumps(event, default=str) + "\n")

    # =========================================================================
    # Session Reading
    # =========================================================================

    def read_session_events(self, session_path: Path) -> Iterator[Dict[str, Any]]:
        """
        Read events from a session file as an iterator.

        Args:
            session_path: Path to the session .jsonl file

        Yields:
            Event dictionaries, one at a time
        """
        if not session_path.exists():
            return

        with open(session_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    # Log warning but continue (graceful degradation)
                    print(f"Warning: Invalid JSON at {session_path}:{line_num}: {e}")

    def load_session_events(self, session_path: Path) -> List[Dict[str, Any]]:
        """
        Load all events from a session file into memory.

        Args:
            session_path: Path to the session .jsonl file

        Returns:
            List of event dictionaries
        """
        return list(self.read_session_events(session_path))

    # =========================================================================
    # Index Management
    # =========================================================================

    def get_daily_index_path(self, platform: Platform, session_date: date) -> Path:
        """Get path to daily index file."""
        return self.get_date_dir(platform, session_date) / ".index.json"

    def get_platform_index_path(self, platform: Platform) -> Path:
        """Get path to platform index file."""
        return self.get_platform_dir(platform) / ".index.json"

    def load_daily_index(self, platform: Platform, session_date: date) -> Optional[DailyIndex]:
        """
        Load daily index for a specific date.

        Args:
            platform: Platform identifier
            session_date: Date to load index for

        Returns:
            DailyIndex if exists, None otherwise
        """
        index_path = self.get_daily_index_path(platform, session_date)
        if not index_path.exists():
            return None

        try:
            with open(index_path) as f:
                data = json.load(f)
            return DailyIndex.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Invalid daily index at {index_path}: {e}")
            return None

    def save_daily_index(self, index: DailyIndex) -> Path:
        """
        Save daily index to disk with atomic write.

        Uses temp file + rename pattern to ensure readers never see
        partial/corrupt index files.

        Args:
            index: DailyIndex to save

        Returns:
            Path to saved index file
        """
        session_date = datetime.strptime(index.date, "%Y-%m-%d").date()
        index_path = self.get_daily_index_path(index.platform, session_date)

        # Atomic write with temp file + rename
        _atomic_write_json(index_path, index.to_dict())

        return index_path

    def load_platform_index(self, platform: Platform) -> Optional[PlatformIndex]:
        """
        Load platform index.

        Args:
            platform: Platform identifier

        Returns:
            PlatformIndex if exists, None otherwise
        """
        index_path = self.get_platform_index_path(platform)
        if not index_path.exists():
            return None

        try:
            with open(index_path) as f:
                data = json.load(f)
            return PlatformIndex.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Invalid platform index at {index_path}: {e}")
            return None

    def save_platform_index(self, index: PlatformIndex) -> Path:
        """
        Save platform index to disk with atomic write.

        Uses temp file + rename pattern to ensure readers never see
        partial/corrupt index files.

        Args:
            index: PlatformIndex to save

        Returns:
            Path to saved index file
        """
        index_path = self.get_platform_index_path(index.platform)

        # Atomic write with temp file + rename
        _atomic_write_json(index_path, index.to_dict())

        return index_path

    def update_indexes_for_session(
        self, platform: Platform, session_date: date, session_index: SessionIndex
    ) -> None:
        """
        Update both daily and platform indexes after adding/updating a session.

        Uses file locking to ensure safe concurrent access from MCP server,
        CLI, and TUI. Holds locks during read-modify-write cycles to prevent
        data loss from simultaneous updates.

        Args:
            platform: Platform identifier
            session_date: Date of the session
            session_index: Index entry for the session
        """
        date_str = session_date.strftime("%Y-%m-%d")

        # Get paths for locking
        daily_index_path = self.get_daily_index_path(platform, session_date)
        platform_index_path = self.get_platform_index_path(platform)

        # Update daily index under lock
        with _index_file_lock(daily_index_path):
            daily_index = self.load_daily_index(platform, session_date)
            if daily_index is None:
                daily_index = DailyIndex(
                    schema_version=STORAGE_SCHEMA_VERSION,
                    platform=platform,
                    date=date_str,
                )

            # Check if session already exists (update) or is new (add)
            existing_idx = next(
                (
                    i
                    for i, s in enumerate(daily_index.sessions)
                    if s.session_id == session_index.session_id
                ),
                None,
            )
            if existing_idx is not None:
                daily_index.sessions[existing_idx] = session_index
                daily_index.recalculate_totals()
            else:
                daily_index.add_session(session_index)

            self.save_daily_index(daily_index)

        # Update platform index under lock
        with _index_file_lock(platform_index_path):
            platform_index = self.load_platform_index(platform)
            if platform_index is None:
                platform_index = PlatformIndex(
                    schema_version=STORAGE_SCHEMA_VERSION,
                    platform=platform,
                )

            if date_str not in platform_index.dates:
                platform_index.dates.append(date_str)
                platform_index.dates.sort()

            platform_index.first_session_date = (
                platform_index.dates[0] if platform_index.dates else None
            )
            platform_index.last_session_date = (
                platform_index.dates[-1] if platform_index.dates else None
            )
            platform_index.last_updated = datetime.now().isoformat()

            # Recalculate totals
            platform_index.total_tokens = 0
            platform_index.total_cost = 0.0
            platform_index.total_sessions = 0
            for d_str in platform_index.dates:
                daily = self.load_daily_index(platform, datetime.strptime(d_str, "%Y-%m-%d").date())
                if daily:
                    platform_index.total_tokens += daily.total_tokens
                    platform_index.total_cost += daily.total_cost
                    platform_index.total_sessions += daily.session_count

            self.save_platform_index(platform_index)

    # =========================================================================
    # Session Discovery
    # =========================================================================

    def list_platforms(self) -> List[Platform]:
        """
        List all platforms with stored sessions.

        Returns:
            List of platform identifiers
        """
        platforms = []
        for platform in SUPPORTED_PLATFORMS:
            platform_dir = self.get_platform_dir(platform)
            if platform_dir.exists() and any(platform_dir.iterdir()):
                platforms.append(platform)
        return platforms

    def list_dates(self, platform: Platform) -> List[date]:
        """
        List all dates with sessions for a platform.

        Args:
            platform: Platform identifier

        Returns:
            List of dates, sorted newest first
        """
        platform_dir = self.get_platform_dir(platform)
        if not platform_dir.exists():
            return []

        dates = []
        for item in platform_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                try:
                    session_date = datetime.strptime(item.name, "%Y-%m-%d").date()
                    dates.append(session_date)
                except ValueError:
                    continue

        dates.sort(reverse=True)
        return dates

    # =========================================================================
    # Performance Optimizations (v0.9.0 - task-107.3)
    # =========================================================================

    def _get_cached_mtime(self, path: Path) -> float:
        """Get file modification time with caching.

        Uses a cache with TTL to reduce stat() system calls during list_sessions.
        Cache is invalidated after _mtime_cache_ttl seconds (default 60s).

        Args:
            path: Path to get mtime for

        Returns:
            File modification time as Unix timestamp
        """
        now = time.time()

        # Invalidate cache if TTL expired
        if now - self._mtime_cache_timestamp > self._mtime_cache_ttl:
            self._mtime_cache.clear()
            self._mtime_cache_timestamp = now

        # Return cached value or compute and cache
        if path not in self._mtime_cache:
            try:
                self._mtime_cache[path] = path.stat().st_mtime
            except OSError:
                # File might have been deleted, use 0
                self._mtime_cache[path] = 0.0

        return self._mtime_cache[path]

    def peek_session_header(
        self, session_path: Path, max_bytes: int = 4096
    ) -> Optional[Dict[str, Any]]:
        """Read session file header without loading full JSON.

        Extracts the _file metadata block from the first few KB of a session file.
        Much faster than json.load() for large sessions when only metadata is needed.

        Args:
            session_path: Path to session JSON file
            max_bytes: Maximum bytes to read (default 4096)

        Returns:
            The _file metadata dict if found, None otherwise
        """
        if not session_path.exists():
            return None

        try:
            with open(session_path) as f:
                # Read first chunk
                chunk = f.read(max_bytes)

            # Quick check for _file key
            if '"_file"' not in chunk:
                return None

            # Try to extract just the _file block using string parsing
            # This is faster than parsing the entire JSON
            import re

            # Match "_file": { ... } where braces are balanced at the first level
            # This regex finds the _file block up to the first closing brace
            match = re.search(r'"_file"\s*:\s*\{[^{}]*\}', chunk)
            if match:
                # Wrap in braces to make valid JSON
                header_json = "{" + match.group() + "}"
                header_data = json.loads(header_json)
                result = header_data.get("_file")
                if isinstance(result, dict):
                    return result
                return None

        except (OSError, json.JSONDecodeError, KeyError):
            pass

        return None

    def invalidate_mtime_cache(self) -> None:
        """Force invalidation of the mtime cache.

        Call this after creating or modifying session files to ensure
        subsequent list_sessions calls see fresh data.
        """
        self._mtime_cache.clear()
        self._mtime_cache_timestamp = 0.0

    def list_sessions(
        self,
        platform: Optional[Platform] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> List[Path]:
        """
        List session files with optional filtering.

        Args:
            platform: Filter by platform (None for all)
            start_date: Filter sessions on or after this date
            end_date: Filter sessions on or before this date
            limit: Maximum number of sessions to return

        Returns:
            List of session file paths, sorted by date (newest first)
        """
        sessions = []

        platforms_to_check = [platform] if platform else self.list_platforms()

        for p in platforms_to_check:
            for session_date in self.list_dates(p):
                # Apply date filters
                if start_date and session_date < start_date:
                    continue
                if end_date and session_date > end_date:
                    continue

                date_dir = self.get_date_dir(p, session_date)
                # Support both .json (actual sessions) and .jsonl (storage module design)
                for pattern in ["*.json", "*.jsonl"]:
                    for session_file in date_dir.glob(pattern):
                        if not session_file.name.startswith("."):
                            sessions.append(session_file)

        # Sort by modification time (newest first)
        # Uses cached mtimes to reduce stat() calls (v0.9.0 - task-107.3)
        sessions.sort(key=lambda p: self._get_cached_mtime(p), reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def list_sessions_in_range(
        self,
        platform: Platform,
        start_date: date,
        end_date: date,
    ) -> List[SessionIndex]:
        """
        List SessionIndex objects for sessions within a date range.

        Returns SessionIndex objects (not paths) for efficient aggregation
        without loading full session data. Uses DailyIndex when available,
        falls back to directory scan if not.

        Args:
            platform: Platform to query
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of SessionIndex objects for sessions in the date range
        """
        result: List[SessionIndex] = []

        # Get dates in range
        dates_in_range = [d for d in self.list_dates(platform) if start_date <= d <= end_date]

        for session_date in dates_in_range:
            date_str = session_date.strftime("%Y-%m-%d")

            # Try to use DailyIndex first (efficient path)
            daily_index = self.load_daily_index(platform, session_date)
            if daily_index and daily_index.sessions:
                result.extend(daily_index.sessions)
            else:
                # Fall back to directory scan (slower path)
                date_dir = self.get_date_dir(platform, session_date)
                if date_dir.exists():
                    for pattern in ["*.json", "*.jsonl"]:
                        for session_file in date_dir.glob(pattern):
                            if not session_file.name.startswith("."):
                                idx = self._build_session_index_from_file(
                                    session_file, platform, date_str
                                )
                                if idx:
                                    result.append(idx)

        return result

    def get_date_range(
        self, platform: Optional[Platform] = None
    ) -> tuple[Optional[date], Optional[date]]:
        """
        Get the date range of sessions for a platform.

        Args:
            platform: Platform to query (None = across all platforms)

        Returns:
            Tuple of (first_date, last_date) or (None, None) if no sessions
        """
        first_date: Optional[date] = None
        last_date: Optional[date] = None

        platforms_to_check = [platform] if platform else self.list_platforms()

        for p in platforms_to_check:
            # Try PlatformIndex first (efficient)
            platform_index = self.load_platform_index(p)
            if platform_index:
                if platform_index.first_session_date:
                    try:
                        p_first = datetime.strptime(
                            platform_index.first_session_date, "%Y-%m-%d"
                        ).date()
                        if first_date is None or p_first < first_date:
                            first_date = p_first
                    except ValueError:
                        pass
                if platform_index.last_session_date:
                    try:
                        p_last = datetime.strptime(
                            platform_index.last_session_date, "%Y-%m-%d"
                        ).date()
                        if last_date is None or p_last > last_date:
                            last_date = p_last
                    except ValueError:
                        pass
            else:
                # Fall back to directory listing
                dates = self.list_dates(p)
                if dates:
                    # list_dates returns newest first, so last is first, first is last
                    p_last = dates[0]
                    p_first = dates[-1]
                    if first_date is None or p_first < first_date:
                        first_date = p_first
                    if last_date is None or p_last > last_date:
                        last_date = p_last

        return (first_date, last_date)

    def _build_session_index_from_file(
        self,
        session_file: Path,
        platform: Platform,
        date_str: str,
    ) -> Optional[SessionIndex]:
        """
        Build a SessionIndex from a session file without loading full data.

        Uses peek_session_header() for efficiency.

        Args:
            session_file: Path to session file
            platform: Platform identifier
            date_str: Date string (YYYY-MM-DD)

        Returns:
            SessionIndex if file is valid, None otherwise
        """
        header = self.peek_session_header(session_file)
        if not header:
            return None

        try:
            # Extract session ID from filename
            session_id = session_file.stem
            if session_id.startswith("session-"):
                session_id = session_id[8:]  # Remove "session-" prefix

            # Get file size
            try:
                file_size = session_file.stat().st_size
            except OSError:
                file_size = 0

            # Build relative path from base_dir
            try:
                rel_path = str(session_file.relative_to(self.base_dir))
            except ValueError:
                rel_path = str(session_file)

            return SessionIndex(
                schema_version=header.get("schema_version", "1.0.0"),
                session_id=session_id,
                platform=platform,
                date=date_str,
                started_at=header.get("started_at", ""),
                ended_at=header.get("ended_at"),
                project=header.get("project"),
                total_tokens=header.get("total_tokens", 0),
                total_cost=header.get("total_cost", 0.0),
                tool_count=header.get("tool_count", 0),
                server_count=header.get("server_count", 0),
                is_complete=header.get("ended_at") is not None,
                file_path=rel_path,
                file_size_bytes=file_size,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def find_session(self, session_id: str) -> Optional[Path]:
        """
        Find a session file by ID across all platforms and dates.

        Args:
            session_id: Session identifier to find

        Returns:
            Path to session file if found, None otherwise
        """
        for platform in self.list_platforms():
            for session_date in self.list_dates(platform):
                session_path = self.get_session_path(platform, session_date, session_id)
                if session_path.exists():
                    return session_path
        return None

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics across all platforms.

        Returns:
            Dictionary with storage statistics
        """
        platforms_dict: Dict[str, Dict[str, int]] = {}
        total_sessions = 0
        total_size_bytes = 0

        for platform in self.list_platforms():
            session_count = 0
            size_bytes = 0

            dates = self.list_dates(platform)

            for session_date in dates:
                date_dir = self.get_date_dir(platform, session_date)
                # Support both .json and .jsonl formats
                for pattern in ["*.json", "*.jsonl"]:
                    for session_file in date_dir.glob(pattern):
                        session_count += 1
                        size_bytes += session_file.stat().st_size

            platforms_dict[platform] = {
                "session_count": session_count,
                "date_count": len(dates),
                "size_bytes": size_bytes,
            }
            total_sessions += session_count
            total_size_bytes += size_bytes

        return {
            "base_dir": str(self.base_dir),
            "platforms": platforms_dict,
            "total_sessions": total_sessions,
            "total_size_bytes": total_size_bytes,
        }


# =============================================================================
# Streaming Storage for Active Sessions
# =============================================================================


class StreamingStorage:
    """
    Manages active session JSONL streaming with file locking.

    Active sessions are stored in a separate directory and use JSONL format
    for incremental writes. When a session completes, it's converted to JSON
    and moved to the standard platform/date directory structure.

    Directory Layout:
        ~/.token-audit/sessions/
        ├── active/                          # Active streaming sessions
        │   └── <session-id>.jsonl
        ├── claude-code/<date>/*.json        # Completed sessions
        └── ...

    Thread Safety:
        - Per-session thread locks for intra-process safety
        - Advisory file locks (fcntl) for cross-process safety
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize streaming storage.

        Args:
            base_dir: Base directory for session storage.
                      Defaults to ~/.token-audit/sessions/
        """
        self.base_dir = base_dir or get_default_base_dir()
        self._active_dir = self.base_dir / ACTIVE_SESSION_DIR
        self._active_dir.mkdir(parents=True, exist_ok=True)

        # Thread locks per session for intra-process safety
        self._thread_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # Lock for accessing _thread_locks

    def _get_thread_lock(self, session_id: str) -> threading.Lock:
        """Get or create a thread lock for a session."""
        with self._locks_lock:
            if session_id not in self._thread_locks:
                self._thread_locks[session_id] = threading.Lock()
            return self._thread_locks[session_id]

    def _cleanup_thread_lock(self, session_id: str) -> None:
        """Remove thread lock for a session (after completion)."""
        with self._locks_lock:
            self._thread_locks.pop(session_id, None)

    def get_active_session_path(self, session_id: str) -> Path:
        """
        Get path for active session JSONL file.

        Args:
            session_id: Unique session identifier

        Returns:
            Path to the session .jsonl file in active directory
        """
        return self._active_dir / f"{session_id}.jsonl"

    def create_active_session(self, session_id: str) -> Path:
        """
        Create new active session file.

        Args:
            session_id: Unique session identifier

        Returns:
            Path to the created session file

        Raises:
            FileExistsError: If session file already exists
            ValueError: If session_id is invalid (e.g., MagicMock stringification)
        """
        # Validate session_id format to prevent test pollution
        # MagicMock objects stringify as "<MagicMock id='...'>" or similar
        if not isinstance(session_id, str) or not session_id:
            raise ValueError(f"session_id must be a non-empty string, got: {type(session_id)}")
        if "<" in session_id or ">" in session_id:
            raise ValueError(f"Invalid session_id (contains angle brackets): {session_id}")

        session_path = self.get_active_session_path(session_id)

        if session_path.exists():
            raise FileExistsError(f"Session already exists: {session_id}")

        # Create empty file
        session_path.touch()
        return session_path

    def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        Append event to active session with file locking.

        Uses both thread locks and advisory file locks for safety.

        Args:
            session_id: Session identifier
            event: Event data to append (will be JSON serialized)

        Raises:
            FileNotFoundError: If session file doesn't exist
        """
        session_path = self.get_active_session_path(session_id)

        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        thread_lock = self._get_thread_lock(session_id)

        with thread_lock:
            with open(session_path, "a") as f:
                # Acquire exclusive lock for writing
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(event, default=str) + "\n")
                    f.flush()  # Ensure data is written
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def read_events(self, session_id: str) -> Iterator[Dict[str, Any]]:
        """
        Read events from active session.

        Uses shared lock for reading to allow concurrent reads.

        Args:
            session_id: Session identifier

        Yields:
            Event dictionaries, one at a time

        Raises:
            FileNotFoundError: If session file doesn't exist
        """
        session_path = self.get_active_session_path(session_id)

        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        thread_lock = self._get_thread_lock(session_id)

        with thread_lock:
            with open(session_path) as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as e:
                            print(f"Warning: Invalid JSON at {session_path}:{line_num}: {e}")
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load_all_events(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Load all events from active session into memory.

        Args:
            session_id: Session identifier

        Returns:
            List of event dictionaries
        """
        return list(self.read_events(session_id))

    def move_to_complete(
        self,
        session_id: str,
        platform: Platform,
        session_date: date,
        final_data: Dict[str, Any],
    ) -> Path:
        """
        Convert active session JSONL to JSON and move to completed directory.

        This method:
        1. Creates the target directory structure
        2. Writes the final session data as JSON
        3. Removes the active JSONL file
        4. Cleans up thread locks

        Args:
            session_id: Session identifier
            platform: Platform for the session
            session_date: Date for organizing the session
            final_data: Final session data to write as JSON

        Returns:
            Path to the completed session JSON file

        Raises:
            FileNotFoundError: If active session doesn't exist
        """
        active_path = self.get_active_session_path(session_id)

        if not active_path.exists():
            raise FileNotFoundError(f"Active session not found: {session_id}")

        # Create completed session path
        # Convert underscore to hyphen for directory name (e.g., claude_code -> claude-code)
        platform_dir = platform.replace("_", "-")
        date_str = session_date.strftime("%Y-%m-%d")
        completed_dir = self.base_dir / platform_dir / date_str
        completed_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename matching existing convention: <project>-<timestamp>.json
        # Use session_id as base if no project
        completed_path = completed_dir / f"{session_id}.json"

        thread_lock = self._get_thread_lock(session_id)

        with thread_lock:
            # Write final JSON
            with open(completed_path, "w") as f:
                json.dump(final_data, f, indent=2, default=str)

            # Remove active JSONL file
            active_path.unlink()

        # Clean up thread lock
        self._cleanup_thread_lock(session_id)

        return completed_path

    def get_active_sessions(self) -> List[str]:
        """
        List all active session IDs.

        Returns:
            List of session IDs with active JSONL files
        """
        sessions = []
        for path in self._active_dir.glob("*.jsonl"):
            sessions.append(path.stem)
        return sessions

    def has_active_session(self, session_id: str) -> bool:
        """
        Check if an active session exists.

        Args:
            session_id: Session identifier

        Returns:
            True if active session exists
        """
        return self.get_active_session_path(session_id).exists()

    def cleanup_active_session(self, session_id: str) -> None:
        """
        Remove active session file (after move or on error).

        Args:
            session_id: Session identifier
        """
        session_path = self.get_active_session_path(session_id)
        if session_path.exists():
            session_path.unlink()
        self._cleanup_thread_lock(session_id)

    def get_active_dir(self) -> Path:
        """Get the active sessions directory path."""
        return self._active_dir

    def get_active_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata from an active session's session_start event.

        This is used to retrieve platform/project info for task command resolution
        when a collector is running but hasn't yet created the final session file.

        Args:
            session_id: Active session identifier

        Returns:
            Dictionary with session_id, platform, project, timestamp if found,
            None otherwise

        Note:
            Added in #117 to support task commands targeting active collector sessions.
        """
        try:
            for event in self.read_events(session_id):
                if event.get("type") == "session_start":
                    return {
                        "session_id": event.get("session_id", session_id),
                        "platform": event.get("platform"),
                        "project": event.get("project"),
                        "timestamp": event.get("timestamp"),
                    }
        except FileNotFoundError:
            pass
        return None


# =============================================================================
# Migration Helpers
# =============================================================================


def migrate_v0_session(
    v0_session_dir: Path, storage: StorageManager, platform: Platform = "claude_code"
) -> Optional[Path]:
    """
    Migrate a v0.x session directory to v1.x format.

    v0.x format: logs/sessions/{project}-{timestamp}/
        - summary.json
        - mcp-{server}.json
        - events.jsonl

    v1.x format (legacy): ~/.mcp-audit/sessions/<platform>/<YYYY-MM-DD>/<session-id>.jsonl

    Args:
        v0_session_dir: Path to v0.x session directory
        storage: StorageManager instance for v1.x storage
        platform: Platform to assign to migrated session

    Returns:
        Path to new session file if successful, None otherwise
    """
    # Check for events.jsonl (primary source)
    events_file = v0_session_dir / "events.jsonl"
    summary_file = v0_session_dir / "summary.json"

    if not events_file.exists() and not summary_file.exists():
        print(f"Warning: No events.jsonl or summary.json in {v0_session_dir}")
        return None

    # Extract date from directory name
    # Format: {project}-{YYYY}-{MM}-{DD}-{HHMMSS}
    dir_name = v0_session_dir.name
    try:
        # Try to extract date from the directory name
        parts = dir_name.rsplit("-", 4)
        if len(parts) >= 4:
            year = int(parts[-4])
            month = int(parts[-3])
            day = int(parts[-2])
            session_date = date(year, month, day)
        else:
            # Fallback to today
            session_date = date.today()
    except (ValueError, IndexError):
        session_date = date.today()

    # Generate new session ID
    session_id = storage.generate_session_id(platform)

    # Create new session file
    new_session_path = storage.create_session_file(platform, session_id, session_date)

    # Copy events to new format
    if events_file.exists():
        with open(events_file) as src, open(new_session_path, "w") as dst:
            for line in src:
                dst.write(line)

    # If we have summary.json, extract metadata for index
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                summary = json.load(f)

            # Create index entry
            session_index = SessionIndex(
                schema_version=STORAGE_SCHEMA_VERSION,
                session_id=session_id,
                platform=platform,
                date=session_date.strftime("%Y-%m-%d"),
                started_at=summary.get("timestamp", datetime.now().isoformat()),
                ended_at=summary.get("end_timestamp"),
                project=summary.get("project"),
                total_tokens=summary.get("token_usage", {}).get("total_tokens", 0),
                total_cost=summary.get("cost_estimate", 0.0),
                tool_count=summary.get("mcp_tool_calls", {}).get("unique_tools", 0),
                server_count=len(summary.get("server_sessions", {})),
                is_complete=summary.get("end_timestamp") is not None,
                file_path=str(new_session_path.relative_to(storage.base_dir)),
                file_size_bytes=new_session_path.stat().st_size,
            )

            # Update indexes
            storage.update_indexes_for_session(platform, session_date, session_index)

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse summary.json: {e}")

    return new_session_path


def migrate_all_v0_sessions(
    v0_base_dir: Path, storage: StorageManager, platform: Platform = "claude_code"
) -> Dict[str, Any]:
    """
    Migrate all v0.x sessions from a directory.

    Args:
        v0_base_dir: Base directory containing v0.x sessions (e.g., logs/sessions/)
        storage: StorageManager instance for v1.x storage
        platform: Default platform for migrated sessions

    Returns:
        Migration results dictionary
    """
    total = 0
    migrated = 0
    failed = 0
    skipped = 0
    errors: List[str] = []

    if not v0_base_dir.exists():
        return {
            "total": total,
            "migrated": migrated,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }

    for session_dir in v0_base_dir.iterdir():
        if not session_dir.is_dir():
            continue

        total += 1

        # Detect platform from directory name if possible
        detected_platform = platform
        if "codex" in session_dir.name.lower():
            detected_platform = "codex_cli"
        elif "gemini" in session_dir.name.lower():
            detected_platform = "gemini_cli"
        elif "ollama" in session_dir.name.lower():
            detected_platform = "ollama_cli"

        try:
            new_path = migrate_v0_session(session_dir, storage, detected_platform)
            if new_path:
                migrated += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            errors.append(f"{session_dir.name}: {e}")

    return {
        "total": total,
        "migrated": migrated,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    import tempfile

    print("Storage Module Tests")
    print("=" * 60)

    # Use temporary directory for tests
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = StorageManager(base_dir=Path(temp_dir))

        # Test 1: Generate session ID
        session_id = storage.generate_session_id("claude_code")
        print(f"✓ Generated session ID: {session_id}")

        # Test 2: Create session file
        session_path = storage.create_session_file(
            platform="claude_code", session_id=session_id, session_date=date.today()
        )
        print(f"✓ Created session file: {session_path}")

        # Test 3: Write events
        events: List[Dict[str, Any]] = [
            {"type": "start", "timestamp": datetime.now().isoformat()},
            {"type": "tool_call", "tool": "mcp__zen__chat", "tokens": 1000},
            {"type": "end", "timestamp": datetime.now().isoformat()},
        ]
        storage.write_session_events(session_path, events)
        print(f"✓ Wrote {len(events)} events")

        # Test 4: Read events
        loaded_events = storage.load_session_events(session_path)
        assert len(loaded_events) == len(events)
        print(f"✓ Read {len(loaded_events)} events")

        # Test 5: Create and save daily index
        session_index = SessionIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            session_id=session_id,
            platform="claude_code",
            date=date.today().strftime("%Y-%m-%d"),
            started_at=datetime.now().isoformat(),
            ended_at=datetime.now().isoformat(),
            project="test-project",
            total_tokens=1000,
            total_cost=0.05,
            tool_count=1,
            server_count=1,
            is_complete=True,
            file_path=str(session_path.relative_to(storage.base_dir)),
            file_size_bytes=session_path.stat().st_size,
        )
        storage.update_indexes_for_session("claude_code", date.today(), session_index)
        print("✓ Updated indexes")

        # Test 6: List sessions
        sessions = storage.list_sessions()
        assert len(sessions) == 1
        print(f"✓ Listed {len(sessions)} session(s)")

        # Test 7: Get storage stats
        stats = storage.get_storage_stats()
        print(
            f"✓ Storage stats: {stats['total_sessions']} sessions, {stats['total_size_bytes']} bytes"
        )

        # Test 8: Load daily index
        daily_index = storage.load_daily_index("claude_code", date.today())
        assert daily_index is not None
        assert daily_index.session_count == 1
        print(
            f"✓ Daily index: {daily_index.session_count} session(s), {daily_index.total_tokens} tokens"
        )

        # Test 9: Load platform index
        platform_index = storage.load_platform_index("claude_code")
        assert platform_index is not None
        print(f"✓ Platform index: {platform_index.total_sessions} session(s)")

    print("\n" + "=" * 60)
    print("All tests passed!")


# =============================================================================
# Convenience Functions for CLI (v1.5.0 - task-103.2)
# =============================================================================


def get_latest_session(base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find the most recent session file.

    Searches all platforms and dates to find the newest session.

    Args:
        base_dir: Base directory for sessions (default: ~/.token-audit/sessions)

    Returns:
        Path to the most recent session JSON file, or None if not found
    """
    if base_dir is None:
        base_dir = get_default_base_dir()

    if not base_dir.exists():
        return None

    latest_path: Optional[Path] = None
    latest_mtime: float = 0

    # Search all platform directories
    for platform_dir in base_dir.iterdir():
        if not platform_dir.is_dir():
            continue

        # Search all date directories within platform
        for date_dir in platform_dir.iterdir():
            if not date_dir.is_dir():
                continue

            # Search for JSON files
            for session_file in date_dir.glob("*.json"):
                if session_file.is_file():
                    mtime = session_file.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_path = session_file

    return latest_path


def load_session_file(session_path: Path) -> Optional[Dict[str, Any]]:
    """
    Load a session JSON file.

    Args:
        session_path: Path to session JSON file

    Returns:
        Session data as dict, or None if loading failed
    """
    try:
        with open(session_path) as f:
            result: Dict[str, Any] = json.load(f)
            return result
    except (json.JSONDecodeError, OSError):
        return None
