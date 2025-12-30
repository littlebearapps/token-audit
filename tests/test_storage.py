#!/usr/bin/env python3
"""
Pytest tests for storage.py module.

Tests the standardized JSONL directory structure:
    ~/.token-audit/sessions/<platform>/<YYYY-MM-DD>/<session-id>.jsonl
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Generator

import pytest

from token_audit.storage import (
    ACTIVE_SESSION_DIR,
    FILE_LOCK_TIMEOUT,
    STORAGE_SCHEMA_VERSION,
    SUPPORTED_PLATFORMS,
    DailyIndex,
    PlatformIndex,
    SessionIndex,
    StorageManager,
    StreamingStorage,
    _atomic_write_json,
    _HAS_FILELOCK,
    _index_file_lock,
    get_default_base_dir,
    migrate_all_v0_sessions,
    migrate_v0_session,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_storage_dir() -> Generator[Path, None, None]:
    """Create temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def storage(temp_storage_dir: Path) -> StorageManager:
    """Create StorageManager instance with temp directory."""
    return StorageManager(base_dir=temp_storage_dir)


@pytest.fixture
def streaming_storage(temp_storage_dir: Path) -> StreamingStorage:
    """Create StreamingStorage instance with temp directory."""
    return StreamingStorage(base_dir=temp_storage_dir)


@pytest.fixture
def sample_events() -> list:
    """Sample events for testing."""
    return [
        {
            "type": "session_start",
            "timestamp": "2025-11-25T10:00:00",
            "platform": "claude_code",
        },
        {
            "type": "tool_call",
            "tool": "mcp__zen__chat",
            "input_tokens": 500,
            "output_tokens": 200,
            "timestamp": "2025-11-25T10:01:00",
        },
        {
            "type": "tool_call",
            "tool": "mcp__brave-search__web",
            "input_tokens": 300,
            "output_tokens": 1000,
            "timestamp": "2025-11-25T10:02:00",
        },
        {
            "type": "session_end",
            "timestamp": "2025-11-25T10:30:00",
            "total_tokens": 2000,
        },
    ]


@pytest.fixture
def sample_session_index() -> SessionIndex:
    """Sample SessionIndex for testing."""
    return SessionIndex(
        schema_version=STORAGE_SCHEMA_VERSION,
        session_id="session-20251125T100000-abc123",
        platform="claude_code",
        date="2025-11-25",
        started_at="2025-11-25T10:00:00",
        ended_at="2025-11-25T10:30:00",
        project="test-project",
        total_tokens=2000,
        total_cost=0.10,
        tool_count=2,
        server_count=2,
        is_complete=True,
        file_path="claude_code/2025-11-25/session-20251125T100000-abc123.jsonl",
        file_size_bytes=1024,
    )


# =============================================================================
# Test: Default Base Directory
# =============================================================================


class TestDefaultBaseDir:
    """Test default base directory configuration."""

    def test_default_base_dir_is_home(self) -> None:
        """Default base dir should be ~/.token-audit/sessions/"""
        base_dir = get_default_base_dir()
        assert base_dir == Path.home() / ".token-audit" / "sessions"

    def test_default_base_dir_is_path(self) -> None:
        """Default base dir should be a Path object."""
        base_dir = get_default_base_dir()
        assert isinstance(base_dir, Path)


# =============================================================================
# Test: StorageManager Initialization
# =============================================================================


class TestStorageManagerInit:
    """Test StorageManager initialization."""

    def test_init_creates_base_dir(self, temp_storage_dir: Path) -> None:
        """Init should create base directory if it doesn't exist."""
        new_dir = temp_storage_dir / "new_subdir" / "sessions"
        storage = StorageManager(base_dir=new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_init_with_existing_dir(self, temp_storage_dir: Path) -> None:
        """Init should work with existing directory."""
        storage = StorageManager(base_dir=temp_storage_dir)
        assert storage.base_dir == temp_storage_dir

    def test_init_with_none_uses_default(self) -> None:
        """Init with None should use default base dir."""
        # Note: This will try to create ~/.token-audit/sessions/ in real environment
        # We just test that it doesn't crash
        storage = StorageManager(base_dir=None)
        assert storage.base_dir == get_default_base_dir()


# =============================================================================
# Test: Path Generation
# =============================================================================


class TestPathGeneration:
    """Test path generation methods."""

    def test_get_platform_dir(self, storage: StorageManager) -> None:
        """Get platform directory path.

        Note: Platform names use underscores internally (claude_code) but
        directory names use hyphens (claude-code) for CLI consistency.
        """
        platform_dir = storage.get_platform_dir("claude_code")
        # Directory uses hyphens for CLI consistency
        assert platform_dir == storage.base_dir / "claude-code"

    def test_get_platform_dir_invalid_platform(self, storage: StorageManager) -> None:
        """Invalid platform should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            storage.get_platform_dir("invalid_platform")  # type: ignore
        assert "Unsupported platform" in str(exc_info.value)

    def test_get_date_dir(self, storage: StorageManager) -> None:
        """Get date directory path."""
        session_date = date(2025, 11, 25)
        date_dir = storage.get_date_dir("claude_code", session_date)
        # Directory uses hyphens for CLI consistency
        assert date_dir == storage.base_dir / "claude-code" / "2025-11-25"

    def test_get_session_path(self, storage: StorageManager) -> None:
        """Get session file path."""
        session_date = date(2025, 11, 25)
        session_path = storage.get_session_path("claude_code", session_date, "session-123")
        # Directory uses hyphens for CLI consistency
        expected = storage.base_dir / "claude-code" / "2025-11-25" / "session-123.jsonl"
        assert session_path == expected

    def test_generate_session_id_format(self, storage: StorageManager) -> None:
        """Session ID should have correct format."""
        session_id = storage.generate_session_id("claude_code")
        # Format: session-{YYYYMMDD}T{HHMMSS}-{6hex}
        assert session_id.startswith("session-")
        parts = session_id.split("-")
        assert len(parts) == 3  # session, timestamp, random
        assert "T" in parts[1]  # timestamp contains T

    def test_generate_session_id_unique(self, storage: StorageManager) -> None:
        """Each session ID should be unique."""
        ids = [storage.generate_session_id("claude_code") for _ in range(100)]
        assert len(set(ids)) == 100

    def test_generate_session_id_with_timestamp(self, storage: StorageManager) -> None:
        """Session ID should use provided timestamp."""
        ts = datetime(2025, 1, 15, 14, 30, 45)
        session_id = storage.generate_session_id("claude_code", timestamp=ts)
        assert "20250115T143045" in session_id


# =============================================================================
# Test: Session Writing
# =============================================================================


class TestSessionWriting:
    """Test session file writing."""

    def test_create_session_file(self, storage: StorageManager) -> None:
        """Create session file should create file and directories."""
        session_path = storage.create_session_file(
            platform="claude_code",
            session_id="test-session",
            session_date=date(2025, 11, 25),
        )
        assert session_path.exists()
        assert session_path.is_file()
        assert session_path.name == "test-session.jsonl"

    def test_create_session_file_default_date(self, storage: StorageManager) -> None:
        """Create session file with default date (today)."""
        session_path = storage.create_session_file(
            platform="claude_code",
            session_id="test-session",
        )
        assert session_path.exists()
        assert date.today().strftime("%Y-%m-%d") in str(session_path)

    def test_append_event(self, storage: StorageManager, sample_events: list) -> None:
        """Append event should add line to file."""
        session_path = storage.create_session_file("claude_code", "test-session")

        for event in sample_events:
            storage.append_event(session_path, event)

        with open(session_path) as f:
            lines = f.readlines()
        assert len(lines) == len(sample_events)

    def test_write_session_events(self, storage: StorageManager, sample_events: list) -> None:
        """Write all events at once."""
        session_path = storage.create_session_file("claude_code", "test-session")
        storage.write_session_events(session_path, sample_events)

        with open(session_path) as f:
            lines = f.readlines()
        assert len(lines) == len(sample_events)

    def test_write_session_events_overwrites(
        self, storage: StorageManager, sample_events: list
    ) -> None:
        """Write events should overwrite existing content."""
        session_path = storage.create_session_file("claude_code", "test-session")

        # Write initial events
        storage.write_session_events(session_path, sample_events)

        # Write single event (should overwrite)
        storage.write_session_events(session_path, [sample_events[0]])

        with open(session_path) as f:
            lines = f.readlines()
        assert len(lines) == 1


# =============================================================================
# Test: Session Reading
# =============================================================================


class TestSessionReading:
    """Test session file reading."""

    def test_read_session_events_iterator(
        self, storage: StorageManager, sample_events: list
    ) -> None:
        """Read events as iterator."""
        session_path = storage.create_session_file("claude_code", "test-session")
        storage.write_session_events(session_path, sample_events)

        events = list(storage.read_session_events(session_path))
        assert len(events) == len(sample_events)

    def test_read_session_events_content(
        self, storage: StorageManager, sample_events: list
    ) -> None:
        """Read events should preserve content."""
        session_path = storage.create_session_file("claude_code", "test-session")
        storage.write_session_events(session_path, sample_events)

        events = list(storage.read_session_events(session_path))
        assert events[0]["type"] == "session_start"
        assert events[1]["tool"] == "mcp__zen__chat"

    def test_read_session_events_nonexistent(self, storage: StorageManager) -> None:
        """Read from nonexistent file should return empty iterator."""
        fake_path = storage.base_dir / "nonexistent.jsonl"
        events = list(storage.read_session_events(fake_path))
        assert events == []

    def test_read_session_events_invalid_json(self, storage: StorageManager) -> None:
        """Invalid JSON should be skipped with warning."""
        session_path = storage.create_session_file("claude_code", "test-session")

        # Write mixed valid and invalid JSON
        with open(session_path, "w") as f:
            f.write('{"type": "valid"}\n')
            f.write("invalid json line\n")
            f.write('{"type": "also_valid"}\n')

        events = list(storage.read_session_events(session_path))
        assert len(events) == 2  # Invalid line skipped

    def test_load_session_events(self, storage: StorageManager, sample_events: list) -> None:
        """Load all events into memory."""
        session_path = storage.create_session_file("claude_code", "test-session")
        storage.write_session_events(session_path, sample_events)

        events = storage.load_session_events(session_path)
        assert isinstance(events, list)
        assert len(events) == len(sample_events)


# =============================================================================
# Test: Session Index
# =============================================================================


class TestSessionIndex:
    """Test SessionIndex dataclass."""

    def test_session_index_to_dict(self, sample_session_index: SessionIndex) -> None:
        """SessionIndex should convert to dict."""
        data = sample_session_index.to_dict()
        assert data["session_id"] == "session-20251125T100000-abc123"
        assert data["platform"] == "claude_code"
        assert data["total_tokens"] == 2000

    def test_session_index_from_dict(self, sample_session_index: SessionIndex) -> None:
        """SessionIndex should be reconstructable from dict."""
        data = sample_session_index.to_dict()
        reconstructed = SessionIndex.from_dict(data)
        assert reconstructed.session_id == sample_session_index.session_id
        assert reconstructed.total_tokens == sample_session_index.total_tokens


# =============================================================================
# Test: Daily Index
# =============================================================================


class TestDailyIndex:
    """Test DailyIndex dataclass."""

    def test_daily_index_creation(self) -> None:
        """Create empty daily index."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
        )
        assert daily_index.session_count == 0
        assert daily_index.total_tokens == 0

    def test_daily_index_add_session(self, sample_session_index: SessionIndex) -> None:
        """Add session to daily index."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
        )
        daily_index.add_session(sample_session_index)

        assert daily_index.session_count == 1
        assert daily_index.total_tokens == 2000
        assert daily_index.total_cost == 0.10

    def test_daily_index_recalculate_totals(self, sample_session_index: SessionIndex) -> None:
        """Recalculate totals from sessions."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
            sessions=[sample_session_index, sample_session_index],
        )
        daily_index.recalculate_totals()

        assert daily_index.session_count == 2
        assert daily_index.total_tokens == 4000

    def test_daily_index_to_dict(self, sample_session_index: SessionIndex) -> None:
        """Daily index should convert to dict."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
            sessions=[sample_session_index],
        )
        daily_index.recalculate_totals()

        data = daily_index.to_dict()
        assert data["platform"] == "claude_code"
        assert len(data["sessions"]) == 1

    def test_daily_index_from_dict(self, sample_session_index: SessionIndex) -> None:
        """Daily index should be reconstructable from dict."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
            sessions=[sample_session_index],
        )
        data = daily_index.to_dict()

        reconstructed = DailyIndex.from_dict(data)
        assert reconstructed.platform == "claude_code"
        assert len(reconstructed.sessions) == 1


# =============================================================================
# Test: Platform Index
# =============================================================================


class TestPlatformIndex:
    """Test PlatformIndex dataclass."""

    def test_platform_index_creation(self) -> None:
        """Create empty platform index."""
        platform_index = PlatformIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
        )
        assert platform_index.total_sessions == 0
        assert platform_index.dates == []

    def test_platform_index_to_dict(self) -> None:
        """Platform index should convert to dict."""
        platform_index = PlatformIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            dates=["2025-11-24", "2025-11-25"],
            total_sessions=5,
        )
        data = platform_index.to_dict()
        assert data["platform"] == "claude_code"
        assert len(data["dates"]) == 2

    def test_platform_index_from_dict(self) -> None:
        """Platform index should be reconstructable from dict."""
        data = {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "platform": "claude_code",
            "dates": ["2025-11-25"],
            "total_sessions": 3,
            "total_tokens": 10000,
            "total_cost": 0.50,
            "first_session_date": "2025-11-25",
            "last_session_date": "2025-11-25",
            "last_updated": "2025-11-25T12:00:00",
        }
        platform_index = PlatformIndex.from_dict(data)
        assert platform_index.total_sessions == 3


# =============================================================================
# Test: Index Management
# =============================================================================


class TestIndexManagement:
    """Test index file management."""

    def test_save_and_load_daily_index(
        self, storage: StorageManager, sample_session_index: SessionIndex
    ) -> None:
        """Save and load daily index."""
        daily_index = DailyIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            date="2025-11-25",
            sessions=[sample_session_index],
        )
        daily_index.recalculate_totals()

        # Save
        storage.save_daily_index(daily_index)

        # Load
        loaded = storage.load_daily_index("claude_code", date(2025, 11, 25))
        assert loaded is not None
        assert loaded.session_count == 1
        assert len(loaded.sessions) == 1

    def test_load_daily_index_nonexistent(self, storage: StorageManager) -> None:
        """Load nonexistent daily index returns None."""
        loaded = storage.load_daily_index("claude_code", date(2025, 1, 1))
        assert loaded is None

    def test_save_and_load_platform_index(self, storage: StorageManager) -> None:
        """Save and load platform index."""
        platform_index = PlatformIndex(
            schema_version=STORAGE_SCHEMA_VERSION,
            platform="claude_code",
            dates=["2025-11-25"],
            total_sessions=3,
        )

        # Save
        storage.save_platform_index(platform_index)

        # Load
        loaded = storage.load_platform_index("claude_code")
        assert loaded is not None
        assert loaded.total_sessions == 3

    def test_update_indexes_for_session(
        self, storage: StorageManager, sample_session_index: SessionIndex
    ) -> None:
        """Update both indexes when adding a session."""
        storage.update_indexes_for_session(
            platform="claude_code",
            session_date=date(2025, 11, 25),
            session_index=sample_session_index,
        )

        # Check daily index
        daily = storage.load_daily_index("claude_code", date(2025, 11, 25))
        assert daily is not None
        assert daily.session_count == 1

        # Check platform index
        platform = storage.load_platform_index("claude_code")
        assert platform is not None
        assert "2025-11-25" in platform.dates


# =============================================================================
# Test: Session Discovery
# =============================================================================


class TestSessionDiscovery:
    """Test session discovery methods."""

    def test_list_platforms_empty(self, storage: StorageManager) -> None:
        """List platforms when empty."""
        platforms = storage.list_platforms()
        assert platforms == []

    def test_list_platforms_with_sessions(
        self, storage: StorageManager, sample_events: list
    ) -> None:
        """List platforms that have sessions."""
        # Create sessions for two platforms
        storage.create_session_file("claude_code", "session-1")
        storage.create_session_file("codex_cli", "session-2")

        platforms = storage.list_platforms()
        assert set(platforms) == {"claude_code", "codex_cli"}

    def test_list_dates(self, storage: StorageManager) -> None:
        """List dates for a platform."""
        # Create sessions on different dates
        storage.create_session_file("claude_code", "s1", date(2025, 11, 24))
        storage.create_session_file("claude_code", "s2", date(2025, 11, 25))
        storage.create_session_file("claude_code", "s3", date(2025, 11, 23))

        dates = storage.list_dates("claude_code")
        assert len(dates) == 3
        # Should be sorted newest first
        assert dates[0] == date(2025, 11, 25)
        assert dates[-1] == date(2025, 11, 23)

    def test_list_sessions_all(self, storage: StorageManager) -> None:
        """List all sessions."""
        storage.create_session_file("claude_code", "s1", date(2025, 11, 24))
        storage.create_session_file("claude_code", "s2", date(2025, 11, 25))
        storage.create_session_file("codex_cli", "s3", date(2025, 11, 25))

        sessions = storage.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_by_platform(self, storage: StorageManager) -> None:
        """List sessions filtered by platform."""
        storage.create_session_file("claude_code", "s1")
        storage.create_session_file("codex_cli", "s2")

        sessions = storage.list_sessions(platform="claude_code")
        assert len(sessions) == 1
        # Directory uses hyphens for CLI consistency
        assert "claude-code" in str(sessions[0])

    def test_list_sessions_by_date_range(self, storage: StorageManager) -> None:
        """List sessions filtered by date range."""
        storage.create_session_file("claude_code", "s1", date(2025, 11, 20))
        storage.create_session_file("claude_code", "s2", date(2025, 11, 24))
        storage.create_session_file("claude_code", "s3", date(2025, 11, 25))
        storage.create_session_file("claude_code", "s4", date(2025, 11, 30))

        sessions = storage.list_sessions(
            start_date=date(2025, 11, 23),
            end_date=date(2025, 11, 26),
        )
        assert len(sessions) == 2

    def test_list_sessions_with_limit(self, storage: StorageManager) -> None:
        """List sessions with limit."""
        for i in range(5):
            storage.create_session_file("claude_code", f"s{i}")

        sessions = storage.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_find_session_by_id(self, storage: StorageManager) -> None:
        """Find session by ID."""
        storage.create_session_file("claude_code", "target-session", date(2025, 11, 25))
        storage.create_session_file("claude_code", "other-session", date(2025, 11, 24))

        found = storage.find_session("target-session")
        assert found is not None
        assert "target-session" in found.name

    def test_find_session_not_found(self, storage: StorageManager) -> None:
        """Find nonexistent session returns None."""
        storage.create_session_file("claude_code", "existing-session")

        found = storage.find_session("nonexistent-session")
        assert found is None


# =============================================================================
# Test: Storage Statistics
# =============================================================================


class TestStorageStats:
    """Test storage statistics."""

    def test_get_storage_stats_empty(self, storage: StorageManager) -> None:
        """Get stats when empty."""
        stats = storage.get_storage_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_size_bytes"] == 0

    def test_get_storage_stats_with_sessions(
        self, storage: StorageManager, sample_events: list
    ) -> None:
        """Get stats with sessions."""
        # Create sessions with content
        path1 = storage.create_session_file("claude_code", "s1")
        storage.write_session_events(path1, sample_events)

        path2 = storage.create_session_file("codex_cli", "s2")
        storage.write_session_events(path2, sample_events)

        stats = storage.get_storage_stats()
        assert stats["total_sessions"] == 2
        assert stats["total_size_bytes"] > 0
        assert "claude_code" in stats["platforms"]
        assert "codex_cli" in stats["platforms"]


# =============================================================================
# Test: Migration Helpers
# =============================================================================


class TestMigration:
    """Test v0.x to v1.x migration."""

    def test_migrate_v0_session_with_events(self, temp_storage_dir: Path) -> None:
        """Migrate v0.x session with events.jsonl."""
        # Create v0.x structure
        v0_dir = temp_storage_dir / "v0_sessions"
        v0_session = v0_dir / "test-project-2025-11-25-103045"
        v0_session.mkdir(parents=True)

        # Create events.jsonl
        events = [
            {"type": "start", "timestamp": "2025-11-25T10:30:45"},
            {"type": "tool_call", "tool": "mcp__zen__chat"},
        ]
        events_file = v0_session / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        # Create summary.json
        summary = {
            "schema_version": "1.0.0",
            "project": "test-project",
            "timestamp": "2025-11-25T10:30:45",
            "end_timestamp": "2025-11-25T11:00:00",
            "token_usage": {"total_tokens": 1500},
            "cost_estimate": 0.05,
            "mcp_tool_calls": {"unique_tools": 1},
            "server_sessions": {"zen": {}},
        }
        with open(v0_session / "summary.json", "w") as f:
            json.dump(summary, f)

        # Migrate
        v1_storage = StorageManager(base_dir=temp_storage_dir / "v1_sessions")
        new_path = migrate_v0_session(v0_session, v1_storage)

        assert new_path is not None
        assert new_path.exists()
        # Directory uses hyphens for CLI consistency
        assert "claude-code" in str(new_path)

        # Check events were copied
        v1_events = v1_storage.load_session_events(new_path)
        assert len(v1_events) == 2

    def test_migrate_v0_session_no_files(self, temp_storage_dir: Path) -> None:
        """Migration should fail if no events or summary."""
        v0_dir = temp_storage_dir / "empty_session"
        v0_dir.mkdir(parents=True)

        v1_storage = StorageManager(base_dir=temp_storage_dir / "v1_sessions")
        new_path = migrate_v0_session(v0_dir, v1_storage)

        assert new_path is None

    def test_migrate_all_v0_sessions(self, temp_storage_dir: Path) -> None:
        """Migrate multiple v0.x sessions."""
        v0_dir = temp_storage_dir / "v0_sessions"

        # Create multiple sessions
        for i, name in enumerate(["proj-a-2025-11-24-100000", "proj-b-codex-2025-11-25-110000"]):
            session_dir = v0_dir / name
            session_dir.mkdir(parents=True)
            with open(session_dir / "events.jsonl", "w") as f:
                f.write('{"type": "test"}\n')
            with open(session_dir / "summary.json", "w") as f:
                json.dump({"schema_version": "1.0.0", "project": f"proj-{i}"}, f)

        # Migrate all
        v1_storage = StorageManager(base_dir=temp_storage_dir / "v1_sessions")
        results = migrate_all_v0_sessions(v0_dir, v1_storage)

        assert results["total"] == 2
        assert results["migrated"] == 2
        assert results["failed"] == 0

    def test_migrate_detects_codex_platform(self, temp_storage_dir: Path) -> None:
        """Migration should detect codex from directory name."""
        v0_dir = temp_storage_dir / "v0_sessions"
        v0_session = v0_dir / "test-codex-2025-11-25-120000"
        v0_session.mkdir(parents=True)

        with open(v0_session / "events.jsonl", "w") as f:
            f.write('{"type": "test"}\n')

        v1_storage = StorageManager(base_dir=temp_storage_dir / "v1_sessions")
        results = migrate_all_v0_sessions(v0_dir, v1_storage)

        # Check that codex_cli directory was used
        sessions = v1_storage.list_sessions(platform="codex_cli")
        assert len(sessions) == 1


# =============================================================================
# Test: Supported Platforms
# =============================================================================


class TestSupportedPlatforms:
    """Test supported platforms constant."""

    def test_supported_platforms_list(self) -> None:
        """Check all expected platforms are in list."""
        assert "claude_code" in SUPPORTED_PLATFORMS
        assert "codex_cli" in SUPPORTED_PLATFORMS
        assert "gemini_cli" in SUPPORTED_PLATFORMS
        assert "ollama_cli" in SUPPORTED_PLATFORMS
        assert "custom" in SUPPORTED_PLATFORMS

    def test_all_platforms_can_create_sessions(self, storage: StorageManager) -> None:
        """Each platform should support session creation."""
        for platform in SUPPORTED_PLATFORMS:
            session_path = storage.create_session_file(platform, f"test-{platform}")
            assert session_path.exists()
            assert platform in str(session_path)


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_jsonl_file(self, storage: StorageManager) -> None:
        """Read empty JSONL file."""
        session_path = storage.create_session_file("claude_code", "empty")
        events = storage.load_session_events(session_path)
        assert events == []

    def test_jsonl_with_blank_lines(self, storage: StorageManager) -> None:
        """JSONL with blank lines should skip them."""
        session_path = storage.create_session_file("claude_code", "test")
        with open(session_path, "w") as f:
            f.write('{"type": "a"}\n')
            f.write("\n")
            f.write("   \n")
            f.write('{"type": "b"}\n')

        events = storage.load_session_events(session_path)
        assert len(events) == 2

    def test_concurrent_session_ids(self, storage: StorageManager) -> None:
        """Session IDs generated at same second should differ."""

        ts = datetime.now()
        ids = [storage.generate_session_id("claude_code", ts) for _ in range(10)]
        # Random suffix should make them unique
        assert len(set(ids)) == 10

    def test_special_characters_in_event(self, storage: StorageManager) -> None:
        """Events with special characters should be handled."""
        session_path = storage.create_session_file("claude_code", "test")
        event = {
            "type": "test",
            "content": 'Special chars: \n\t"quotes" and unicode: 日本語',
        }
        storage.append_event(session_path, event)

        events = storage.load_session_events(session_path)
        assert len(events) == 1
        assert "日本語" in events[0]["content"]


# =============================================================================
# Test: Streaming Storage for Active Sessions
# =============================================================================


class TestStreamingStorageInit:
    """Test StreamingStorage initialization."""

    def test_init_creates_active_dir(self, temp_storage_dir: Path) -> None:
        """StreamingStorage should create active directory on init."""
        storage = StreamingStorage(base_dir=temp_storage_dir)
        assert (temp_storage_dir / ACTIVE_SESSION_DIR).exists()
        assert storage.get_active_dir() == temp_storage_dir / ACTIVE_SESSION_DIR

    def test_init_with_none_uses_default(self) -> None:
        """Init with None should use default base dir."""
        storage = StreamingStorage(base_dir=None)
        assert storage.base_dir == get_default_base_dir()


class TestStreamingStorageSessionLifecycle:
    """Test active session creation, events, and completion."""

    def test_create_active_session(self, streaming_storage: StreamingStorage) -> None:
        """Create a new active session file."""
        session_id = "test-session-123"
        path = streaming_storage.create_active_session(session_id)

        assert path.exists()
        assert path.suffix == ".jsonl"
        assert session_id in path.stem
        assert streaming_storage.has_active_session(session_id)

    def test_create_active_session_already_exists(
        self, streaming_storage: StreamingStorage
    ) -> None:
        """Creating duplicate session should raise error."""
        session_id = "test-session-123"
        streaming_storage.create_active_session(session_id)

        with pytest.raises(FileExistsError):
            streaming_storage.create_active_session(session_id)

    def test_get_active_session_path(self, streaming_storage: StreamingStorage) -> None:
        """Get correct path for active session."""
        session_id = "test-session-456"
        path = streaming_storage.get_active_session_path(session_id)

        assert path.parent == streaming_storage.get_active_dir()
        assert path.name == f"{session_id}.jsonl"

    def test_append_event(self, streaming_storage: StreamingStorage) -> None:
        """Append events to active session."""
        session_id = "test-session"
        streaming_storage.create_active_session(session_id)

        event1 = {"type": "session_start", "platform": "claude_code"}
        event2 = {"type": "tool_call", "tool": "Read", "tokens_in": 100}

        streaming_storage.append_event(session_id, event1)
        streaming_storage.append_event(session_id, event2)

        events = streaming_storage.load_all_events(session_id)
        assert len(events) == 2
        assert events[0]["type"] == "session_start"
        assert events[1]["type"] == "tool_call"

    def test_append_event_nonexistent_session(self, streaming_storage: StreamingStorage) -> None:
        """Appending to nonexistent session should raise error."""
        with pytest.raises(FileNotFoundError):
            streaming_storage.append_event("nonexistent", {"type": "test"})

    def test_read_events_iterator(self, streaming_storage: StreamingStorage) -> None:
        """Read events as iterator."""
        session_id = "test-session"
        streaming_storage.create_active_session(session_id)

        for i in range(3):
            streaming_storage.append_event(session_id, {"index": i})

        events = list(streaming_storage.read_events(session_id))
        assert len(events) == 3
        assert [e["index"] for e in events] == [0, 1, 2]

    def test_read_events_nonexistent_session(self, streaming_storage: StreamingStorage) -> None:
        """Reading from nonexistent session should raise error."""
        with pytest.raises(FileNotFoundError):
            list(streaming_storage.read_events("nonexistent"))


class TestStreamingStorageMoveToComplete:
    """Test moving active sessions to completed directory."""

    def test_move_to_complete(self, streaming_storage: StreamingStorage) -> None:
        """Move active session to completed directory."""
        session_id = "test-session"
        streaming_storage.create_active_session(session_id)

        # Add some events
        streaming_storage.append_event(session_id, {"type": "session_start"})
        streaming_storage.append_event(session_id, {"type": "tool_call"})

        # Prepare final data
        final_data = {
            "session_id": session_id,
            "platform": "claude_code",
            "total_tokens": 1000,
            "events": streaming_storage.load_all_events(session_id),
        }

        # Move to complete
        completed_path = streaming_storage.move_to_complete(
            session_id=session_id,
            platform="claude_code",
            session_date=date(2025, 12, 16),
            final_data=final_data,
        )

        # Check completed file
        assert completed_path.exists()
        assert completed_path.suffix == ".json"
        assert "claude-code" in str(completed_path)
        assert "2025-12-16" in str(completed_path)

        # Check active file removed
        assert not streaming_storage.has_active_session(session_id)

        # Check JSON content
        with open(completed_path) as f:
            loaded = json.load(f)
        assert loaded["session_id"] == session_id
        assert loaded["total_tokens"] == 1000
        assert len(loaded["events"]) == 2

    def test_move_to_complete_nonexistent(self, streaming_storage: StreamingStorage) -> None:
        """Moving nonexistent session should raise error."""
        with pytest.raises(FileNotFoundError):
            streaming_storage.move_to_complete(
                session_id="nonexistent",
                platform="claude_code",
                session_date=date.today(),
                final_data={},
            )


class TestStreamingStorageDiscovery:
    """Test session discovery methods."""

    def test_get_active_sessions_empty(self, streaming_storage: StreamingStorage) -> None:
        """Empty active directory should return empty list."""
        sessions = streaming_storage.get_active_sessions()
        assert sessions == []

    def test_get_active_sessions_with_sessions(self, streaming_storage: StreamingStorage) -> None:
        """List active sessions."""
        streaming_storage.create_active_session("session-a")
        streaming_storage.create_active_session("session-b")
        streaming_storage.create_active_session("session-c")

        sessions = streaming_storage.get_active_sessions()
        assert len(sessions) == 3
        assert set(sessions) == {"session-a", "session-b", "session-c"}

    def test_has_active_session(self, streaming_storage: StreamingStorage) -> None:
        """Check if active session exists."""
        assert not streaming_storage.has_active_session("test")

        streaming_storage.create_active_session("test")
        assert streaming_storage.has_active_session("test")


class TestStreamingStorageCleanup:
    """Test cleanup operations."""

    def test_cleanup_active_session(self, streaming_storage: StreamingStorage) -> None:
        """Cleanup should remove active session file."""
        session_id = "test-session"
        streaming_storage.create_active_session(session_id)
        assert streaming_storage.has_active_session(session_id)

        streaming_storage.cleanup_active_session(session_id)
        assert not streaming_storage.has_active_session(session_id)

    def test_cleanup_nonexistent_session(self, streaming_storage: StreamingStorage) -> None:
        """Cleanup of nonexistent session should not raise error."""
        # Should not raise
        streaming_storage.cleanup_active_session("nonexistent")


class TestStreamingStorageFileLocking:
    """Test file locking behavior."""

    def test_concurrent_appends_same_session(self, streaming_storage: StreamingStorage) -> None:
        """Concurrent appends to same session should be safe."""
        import threading
        import time

        session_id = "concurrent-test"
        streaming_storage.create_active_session(session_id)

        num_threads = 5
        events_per_thread = 20
        errors: list = []

        def append_events(thread_id: int) -> None:
            try:
                for i in range(events_per_thread):
                    streaming_storage.append_event(session_id, {"thread": thread_id, "event": i})
                    # Small delay to increase contention
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=append_events, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check no errors
        assert len(errors) == 0

        # Check all events were written
        events = streaming_storage.load_all_events(session_id)
        assert len(events) == num_threads * events_per_thread

    def test_read_during_write(self, streaming_storage: StreamingStorage) -> None:
        """Reading while writing should return consistent data."""
        session_id = "read-write-test"
        streaming_storage.create_active_session(session_id)

        # Write some events first
        for i in range(10):
            streaming_storage.append_event(session_id, {"index": i})

        # Read should return complete events
        events = streaming_storage.load_all_events(session_id)
        assert len(events) == 10


class TestActiveSessionDirConstant:
    """Test ACTIVE_SESSION_DIR constant."""

    def test_active_session_dir_value(self) -> None:
        """Active session dir should be 'active'."""
        assert ACTIVE_SESSION_DIR == "active"


class TestAtomicWriteJson:
    """Test _atomic_write_json function for crash-safe writes."""

    def test_creates_file(self, temp_storage_dir: Path) -> None:
        """Should create file with JSON content."""
        target = temp_storage_dir / "test.json"
        data = {"key": "value", "number": 42}

        _atomic_write_json(target, data)

        assert target.exists()
        with open(target) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_creates_parent_directories(self, temp_storage_dir: Path) -> None:
        """Should create parent directories if they don't exist."""
        target = temp_storage_dir / "nested" / "deep" / "test.json"
        data = {"nested": True}

        _atomic_write_json(target, data)

        assert target.exists()

    def test_overwrites_existing_file(self, temp_storage_dir: Path) -> None:
        """Should overwrite existing file atomically."""
        target = temp_storage_dir / "test.json"
        old_data = {"version": 1}
        new_data = {"version": 2}

        _atomic_write_json(target, old_data)
        _atomic_write_json(target, new_data)

        with open(target) as f:
            loaded = json.load(f)
        assert loaded == new_data

    def test_no_temp_files_left_on_success(self, temp_storage_dir: Path) -> None:
        """Should not leave temp files after successful write."""
        target = temp_storage_dir / "test.json"
        _atomic_write_json(target, {"clean": True})

        # Check no temp files remain
        files = list(temp_storage_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.json"

    def test_writes_formatted_json(self, temp_storage_dir: Path) -> None:
        """Should write indented JSON for readability."""
        target = temp_storage_dir / "test.json"
        _atomic_write_json(target, {"key": "value"})

        content = target.read_text()
        # Check it's indented (has newlines and spaces)
        assert "\n" in content
        assert "  " in content


class TestIndexFileLock:
    """Test _index_file_lock context manager."""

    def test_lock_context_executes(self, temp_storage_dir: Path) -> None:
        """Should execute code inside context."""
        index_path = temp_storage_dir / "test.json"
        executed = False

        with _index_file_lock(index_path):
            executed = True

        assert executed

    def test_lock_creates_lock_file(self, temp_storage_dir: Path) -> None:
        """Lock should create a .lock file while held."""
        import importlib.util

        index_path = temp_storage_dir / "test.json"
        lock_path = index_path.with_suffix(".json.lock")

        if importlib.util.find_spec("filelock") is not None:
            # Lock file should be created when lock is acquired
            with _index_file_lock(index_path):
                assert lock_path.exists()
        else:
            # Without filelock, no lock file is created (fallback is no-op)
            with _index_file_lock(index_path):
                pass  # Just verify no error


class TestIndexFileLockingConcurrency:
    """Test concurrent access to index files with locking."""

    @pytest.mark.skipif(
        not _HAS_FILELOCK, reason="filelock package required for concurrent access safety"
    )
    def test_concurrent_update_indexes(self, storage: StorageManager) -> None:
        """Concurrent index updates should not lose data."""
        import threading

        platform = "claude_code"
        session_date = date.today()
        date_str = session_date.strftime("%Y-%m-%d")
        num_threads = 5
        errors: list = []

        def update_index(thread_id: int) -> None:
            try:
                session_index = SessionIndex(
                    schema_version=STORAGE_SCHEMA_VERSION,
                    session_id=f"session-{thread_id}",
                    platform=platform,
                    date=date_str,
                    started_at=datetime.now().isoformat(),
                    ended_at=datetime.now().isoformat(),
                    project="test-project",
                    total_tokens=100 * thread_id,
                    total_cost=0.001 * thread_id,
                    tool_count=1,
                    server_count=1,
                    is_complete=True,
                    file_path=f"claude_code/{date_str}/session-{thread_id}.jsonl",
                    file_size_bytes=1024,
                )
                storage.update_indexes_for_session(platform, session_date, session_index)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_index, args=(i,)) for i in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all sessions were indexed
        daily_index = storage.load_daily_index(platform, session_date)
        assert daily_index is not None
        assert daily_index.session_count == num_threads

    def test_file_lock_timeout_constant(self) -> None:
        """FILE_LOCK_TIMEOUT should be a reasonable value."""
        assert FILE_LOCK_TIMEOUT > 0
        assert FILE_LOCK_TIMEOUT <= 60  # Not too long


# =============================================================================
# Active Session Metadata Tests (#117)
# =============================================================================


class TestGetActiveSessionMetadata:
    """Tests for StreamingStorage.get_active_session_metadata() method."""

    def test_get_metadata_with_session_start_event(self, temp_storage_dir: Path) -> None:
        """Should return metadata from session_start event."""
        storage = StreamingStorage(temp_storage_dir)
        session_id = "test-session-123"

        # Create active session with session_start event
        storage.create_active_session(session_id)
        start_event = {
            "type": "session_start",
            "session_id": session_id,
            "platform": "claude-code",
            "project": "my-project",
            "timestamp": "2025-01-01T10:00:00",
        }
        storage.append_event(session_id, start_event)

        # Should retrieve the metadata
        metadata = storage.get_active_session_metadata(session_id)
        assert metadata is not None
        assert metadata["session_id"] == session_id
        assert metadata["platform"] == "claude-code"
        assert metadata["project"] == "my-project"
        assert metadata["timestamp"] == "2025-01-01T10:00:00"

    def test_get_metadata_nonexistent_session(self, temp_storage_dir: Path) -> None:
        """Should return None for nonexistent session."""
        storage = StreamingStorage(temp_storage_dir)

        metadata = storage.get_active_session_metadata("nonexistent-session")
        assert metadata is None

    def test_get_metadata_no_session_start_event(self, temp_storage_dir: Path) -> None:
        """Should return None if session has no session_start event."""
        storage = StreamingStorage(temp_storage_dir)
        session_id = "test-session-456"

        # Create active session with only a regular event
        storage.create_active_session(session_id)
        storage.append_event(session_id, {"type": "tool_call", "name": "test"})

        # Should return None since no session_start event
        metadata = storage.get_active_session_metadata(session_id)
        assert metadata is None

    def test_get_metadata_first_session_start_wins(self, temp_storage_dir: Path) -> None:
        """Should return first session_start event if multiple exist."""
        storage = StreamingStorage(temp_storage_dir)
        session_id = "test-session-789"

        # Create active session with multiple events including two session_starts
        storage.create_active_session(session_id)
        storage.append_event(
            session_id,
            {
                "type": "session_start",
                "session_id": session_id,
                "platform": "first-platform",
                "project": "first-project",
                "timestamp": "2025-01-01T09:00:00",
            },
        )
        storage.append_event(session_id, {"type": "tool_call", "name": "test"})
        storage.append_event(
            session_id,
            {
                "type": "session_start",
                "session_id": session_id,
                "platform": "second-platform",
                "project": "second-project",
                "timestamp": "2025-01-01T10:00:00",
            },
        )

        # Should return first session_start
        metadata = storage.get_active_session_metadata(session_id)
        assert metadata is not None
        assert metadata["platform"] == "first-platform"
        assert metadata["project"] == "first-project"
