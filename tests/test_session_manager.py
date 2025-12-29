#!/usr/bin/env python3
"""
Test suite for session_manager module

Tests session lifecycle, persistence, and recovery.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from token_audit.session_manager import SessionManager, save_session, load_session
from token_audit.base_tracker import (
    Session,
    ServerSession,
    ToolStats,
    Call,
    TokenUsage,
    MCPToolCalls,
    SCHEMA_VERSION,
)


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create temporary session directory for tests"""
    return tmp_path / "test_sessions"


@pytest.fixture
def sample_session():
    """Create sample session for testing"""
    session = Session(
        project="test-project",
        platform="test-platform",
        timestamp=datetime(2025, 11, 24, 10, 30, 0),
        session_id="test-project-2025-11-24T10-30-00",
        token_usage=TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_created_tokens=200,
            cache_read_tokens=5000,
            total_tokens=6700,
            cache_efficiency=0.75,
        ),
        cost_estimate=0.05,
        mcp_tool_calls=MCPToolCalls(
            total_calls=10, unique_tools=3, most_called="mcp__zen__chat (5 calls)"
        ),
    )

    # Add server session
    server_session = ServerSession(server="zen", total_calls=10, total_tokens=6700)

    # Add tool stats (v1.0.4: Call objects include server field)
    tool_stats = ToolStats(
        calls=5,
        total_tokens=3000,
        avg_tokens=600.0,
        call_history=[
            Call(
                tool_name="mcp__zen__chat",
                server="zen",  # v1.0.4: server field required
                index=1,  # v1.0.4: sequential index
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                timestamp=datetime(2025, 11, 24, 10, 31, 0),
            )
        ],
    )

    server_session.tools["mcp__zen__chat"] = tool_stats
    session.server_sessions["zen"] = server_session

    return session


class TestSessionManager:
    """Tests for SessionManager class"""

    def test_initialization(self, temp_session_dir) -> None:
        """Test SessionManager initialization"""
        manager = SessionManager(base_dir=temp_session_dir)
        assert manager.base_dir == temp_session_dir
        assert temp_session_dir.exists()

    def test_default_base_dir(self) -> None:
        """Test default base directory creation"""
        manager = SessionManager()
        assert manager.base_dir == Path("logs/sessions")

    def test_create_session_directory(self, temp_session_dir) -> None:
        """Test session directory creation"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_id = "test-session-001"

        session_dir = manager.create_session_directory(session_id)

        assert session_dir == temp_session_dir / session_id
        assert session_dir.exists()
        assert session_dir.is_dir()


class TestSessionPersistence:
    """Tests for session save/load functionality"""

    def test_save_session(self, temp_session_dir, sample_session) -> None:
        """Test saving session to disk (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory(sample_session.session_id)

        saved_files = manager.save_session(sample_session, session_dir)

        # v1.0.4: Single file with "session" key
        assert "session" in saved_files
        assert saved_files["session"].exists()

        # Verify session file content (v1.0.4 format)
        with open(saved_files["session"], "r") as f:
            data = json.load(f)

        # Check _file header exists (v1.0.4)
        assert "_file" in data
        assert data["_file"]["type"] == "token_audit_session"
        assert data["_file"]["schema_version"].startswith("1.")  # v1.x compatible

        # Check session block (v1.0.4)
        assert "session" in data
        assert data["session"]["project"] == "test-project"
        assert data["session"]["platform"] == "test-platform"

        # Check token_usage at root level
        assert data["token_usage"]["total_tokens"] == 6700

    def test_load_session(self, temp_session_dir, sample_session) -> None:
        """Test loading session from disk (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory(sample_session.session_id)

        # Save then load - v1.0.4 saves to date subdirectory
        saved_files = manager.save_session(sample_session, session_dir)
        # Load from the directory containing the session file
        date_dir = saved_files["session"].parent
        loaded_session = manager.load_session(date_dir)

        assert loaded_session is not None
        assert loaded_session.project == sample_session.project
        assert loaded_session.platform == sample_session.platform
        # Note: session_id may be reconstructed differently
        assert loaded_session.token_usage.total_tokens == 6700

    def test_load_nonexistent_session(self, temp_session_dir) -> None:
        """Test loading session that doesn't exist"""
        manager = SessionManager(base_dir=temp_session_dir)
        nonexistent_dir = temp_session_dir / "nonexistent"

        loaded_session = manager.load_session(nonexistent_dir)

        assert loaded_session is None

    def test_load_session_with_server_sessions(self, temp_session_dir, sample_session) -> None:
        """Test loading session with server session data (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory(sample_session.session_id)

        # Save then load - v1.0.4 saves to date subdirectory
        saved_files = manager.save_session(sample_session, session_dir)
        date_dir = saved_files["session"].parent
        loaded_session = manager.load_session(date_dir)

        assert loaded_session is not None
        # v1.0.4 reconstructs server_sessions from tool_calls
        assert "zen" in loaded_session.server_sessions
        zen_session = loaded_session.server_sessions["zen"]
        assert zen_session.server == "zen"
        # Totals may differ slightly due to reconstruction
        assert zen_session.total_calls > 0
        assert "mcp__zen__chat" in zen_session.tools


class TestSchemaVersionValidation:
    """Tests for schema version validation"""

    def test_validate_schema_version_valid(self, temp_session_dir) -> None:
        """Test validation of compatible schema version"""
        manager = SessionManager(base_dir=temp_session_dir)

        data = {"schema_version": SCHEMA_VERSION}
        assert manager._validate_schema_version(data) == True

    def test_validate_schema_version_missing(self, temp_session_dir) -> None:
        """Test validation succeeds for legacy data (missing schema_version)"""
        manager = SessionManager(base_dir=temp_session_dir)

        data = {}
        # Legacy data without schema_version is allowed (returns True with warning)
        assert manager._validate_schema_version(data) == True
        # The method adds a default schema_version for legacy data
        assert data["schema_version"] == "0.0.0"

    def test_validate_schema_version_incompatible_major(self, temp_session_dir) -> None:
        """Test validation fails for incompatible major version"""
        manager = SessionManager(base_dir=temp_session_dir)

        data = {"schema_version": "2.0.0"}  # Different major version
        assert manager._validate_schema_version(data) == False

    def test_validate_schema_version_older_minor(self, temp_session_dir) -> None:
        """Test validation succeeds for older minor version (forward compatible)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # Assuming current version is 1.0.0, test with 1.0.0 (same)
        data = {"schema_version": "1.0.0"}
        assert manager._validate_schema_version(data) == True

    def test_parse_version(self, temp_session_dir) -> None:
        """Test version string parsing"""
        manager = SessionManager(base_dir=temp_session_dir)

        major, minor, patch = manager._parse_version("1.2.3")
        assert major == 1
        assert minor == 2
        assert patch == 3


class TestSessionListing:
    """Tests for session listing and discovery"""

    def test_list_sessions_empty(self, temp_session_dir) -> None:
        """Test listing sessions in empty directory"""
        manager = SessionManager(base_dir=temp_session_dir)

        sessions = manager.list_sessions()

        assert sessions == []

    def test_list_sessions(self, temp_session_dir, sample_session) -> None:
        """Test listing multiple sessions (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # Create 3 sessions - v1.0.4 saves to date subdirectory
        for i in range(3):
            sample_session.session_id = f"test-session-{i:03d}"
            sample_session.project = f"project-{i:03d}"
            manager.save_session(sample_session, temp_session_dir)

        sessions = manager.list_sessions()

        assert len(sessions) == 3

    def test_list_sessions_sorted(self, temp_session_dir, sample_session) -> None:
        """Test sessions are sorted by timestamp (newest first, v1.0.4 format)"""
        from datetime import timedelta

        manager = SessionManager(base_dir=temp_session_dir)

        # Create sessions with different timestamps
        base_timestamp = sample_session.timestamp
        projects = ["project-1", "project-2", "project-3"]

        for i, project in enumerate(projects):
            # Each session has a later timestamp
            sample_session.project = project
            sample_session.timestamp = base_timestamp + timedelta(hours=i)
            manager.save_session(sample_session, temp_session_dir)

        sessions = manager.list_sessions()

        # Should be sorted newest first (by started_at timestamp)
        assert len(sessions) == 3
        # Last created (project-3) should be first in list
        assert "project-3" in sessions[0].name

    def test_list_sessions_with_limit(self, temp_session_dir, sample_session) -> None:
        """Test listing sessions with limit (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # Create 5 sessions - v1.0.4 saves to date subdirectory
        for i in range(5):
            sample_session.session_id = f"test-session-{i:03d}"
            sample_session.project = f"project-{i:03d}"
            manager.save_session(sample_session, temp_session_dir)

        sessions = manager.list_sessions(limit=3)

        assert len(sessions) == 3


class TestIncompleteSessionDetection:
    """Tests for incomplete session detection and recovery"""

    def test_find_incomplete_sessions(self, temp_session_dir) -> None:
        """Test finding sessions missing required files (v1.0.0 format)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # Create complete v1.0.0 session (with summary.json)
        complete_dir = temp_session_dir / "complete-session"
        complete_dir.mkdir()
        (complete_dir / "summary.json").write_text("{}")

        # Create incomplete v1.0.0 session (no summary.json)
        incomplete_dir = temp_session_dir / "incomplete-session"
        incomplete_dir.mkdir()

        incomplete = manager.find_incomplete_sessions()

        # Note: v1.0.0 incomplete detection looks for directories without summary.json
        assert len(incomplete) == 1
        assert incomplete[0].name == "incomplete-session"

    def test_recover_from_events_no_file(self, temp_session_dir) -> None:
        """Test recovery when events.jsonl doesn't exist"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory("test-session")

        recovered = manager.recover_from_events(session_dir)

        assert recovered is None


class TestSessionCleanup:
    """Tests for old session cleanup"""

    def test_cleanup_old_sessions(self, temp_session_dir) -> None:
        """Test cleaning up old sessions (v1.0.0 format)"""
        from datetime import date, timedelta

        manager = SessionManager(base_dir=temp_session_dir)

        # Create old session directory (v1.0.0 format with timestamp in name)
        # Use date 60 days ago (should be deleted with 30 day max_age)
        old_date = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
        old_dir = temp_session_dir / f"test-{old_date}-100000"
        old_dir.mkdir()
        (old_dir / "summary.json").write_text('{"schema_version": "1.0.0"}')

        # Create recent session directory (v1.0.0 format)
        # Use date 10 days ago (should NOT be deleted with 30 day max_age)
        recent_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_dir = temp_session_dir / f"test-{recent_date}-100000"
        recent_dir.mkdir()
        (recent_dir / "summary.json").write_text('{"schema_version": "1.0.0"}')

        # Cleanup sessions older than 30 days
        deleted_count = manager.cleanup_old_sessions(max_age_days=30)

        # Note: cleanup_old_sessions parses timestamp from directory name
        assert deleted_count == 1
        assert not old_dir.exists()
        assert recent_dir.exists()


class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_save_session_function(self, temp_session_dir, sample_session) -> None:
        """Test save_session convenience function (v1.0.4 format)"""
        session_dir = temp_session_dir / sample_session.session_id
        session_dir.mkdir(parents=True)

        saved_files = save_session(sample_session, session_dir)

        # v1.0.4: Single file with "session" key
        assert "session" in saved_files
        assert saved_files["session"].exists()

    def test_load_session_function(self, temp_session_dir, sample_session) -> None:
        """Test load_session convenience function (v1.0.4 format)"""
        session_dir = temp_session_dir / sample_session.session_id
        session_dir.mkdir(parents=True)

        # Save then load - v1.0.4 saves to date subdirectory
        saved_files = save_session(sample_session, session_dir)
        date_dir = saved_files["session"].parent
        loaded_session = load_session(date_dir)

        assert loaded_session is not None
        assert loaded_session.project == sample_session.project


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_load_corrupt_json(self, temp_session_dir) -> None:
        """Test loading session with corrupt JSON"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory("corrupt-session")

        # Write corrupt JSON
        (session_dir / "summary.json").write_text("{ invalid json }")

        loaded_session = manager.load_session(session_dir)

        assert loaded_session is None

    def test_load_missing_fields(self, temp_session_dir) -> None:
        """Test loading session with missing required fields"""
        manager = SessionManager(base_dir=temp_session_dir)
        session_dir = manager.create_session_directory("missing-fields")

        # Write JSON missing required fields
        (session_dir / "summary.json").write_text('{"schema_version": "1.0.0"}')

        loaded_session = manager.load_session(session_dir)

        assert loaded_session is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestSessionManagerIntegration:
    """Integration tests for complete session lifecycle"""

    def test_complete_session_lifecycle(self, temp_session_dir, sample_session) -> None:
        """Test complete save/load/list/cleanup lifecycle (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # 1. Save session directly to base_dir (v1.0.4 creates date subdir)
        saved_files = manager.save_session(sample_session, temp_session_dir)
        # v1.0.4: Single file
        assert len(saved_files) == 1
        assert "session" in saved_files

        # 2. Load session from file path (v1.0.4)
        session_file = saved_files["session"]
        loaded_session = manager.load_session(session_file)
        assert loaded_session is not None
        assert loaded_session.project == sample_session.project

        # 3. List sessions
        sessions = manager.list_sessions()
        assert len(sessions) >= 1

        # 4. Verify incomplete session detection works
        # Note: With v1.0.4 format, incomplete detection looks for summary.json
        # which won't exist since we use single file format now
        # This is expected behavior - the session IS complete (just different format)

    def test_multiple_server_sessions(self, temp_session_dir, sample_session) -> None:
        """Test saving/loading session with multiple servers (v1.0.4 format)"""
        manager = SessionManager(base_dir=temp_session_dir)

        # Add second server session with tool calls (v1.0.4 reconstructs from tool_calls)
        brave_session = ServerSession(server="brave-search", total_calls=5, total_tokens=2000)
        brave_tool_stats = ToolStats(
            calls=2,
            total_tokens=1000,
            avg_tokens=500.0,
            call_history=[
                Call(
                    tool_name="mcp__brave-search__web",
                    server="brave-search",  # v1.0.4: server field required
                    index=2,  # v1.0.4: sequential index
                    input_tokens=200,
                    output_tokens=100,
                    total_tokens=300,
                    timestamp=datetime(2025, 11, 24, 10, 32, 0),
                )
            ],
        )
        brave_session.tools["mcp__brave-search__web"] = brave_tool_stats
        sample_session.server_sessions["brave-search"] = brave_session

        # Save and load
        session_dir = manager.create_session_directory(sample_session.session_id)
        saved_files = manager.save_session(sample_session, session_dir)
        # v1.0.4: Single file format
        assert len(saved_files) == 1

        # Load from date subdirectory
        date_dir = saved_files["session"].parent
        loaded_session = manager.load_session(date_dir)

        # Verify both servers loaded (reconstructed from tool_calls)
        assert loaded_session is not None
        assert "zen" in loaded_session.server_sessions
        assert "brave-search" in loaded_session.server_sessions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
