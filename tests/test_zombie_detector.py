"""
Tests for the Zombie Tool Detector (v1.5.0 - task-103.4).

Tests cover:
- ZombieToolConfig loading
- detect_zombie_tools() with various configurations
- Integration with session finalization
"""

import tempfile
from pathlib import Path

import pytest

from token_audit.base_tracker import ServerSession, Session, ToolStats
from token_audit.zombie_detector import (
    ZombieToolConfig,
    detect_zombie_tools,
    load_zombie_config,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_session() -> Session:
    """Create a minimal test session."""
    return Session(
        project="test-project",
        platform="claude-code",
        session_id="test-session-123",
    )


def add_server_with_tools(
    session: Session,
    server_name: str,
    tools: list[str],
    calls_per_tool: int = 1,
) -> None:
    """Add a server with called tools to a session."""
    if server_name not in session.server_sessions:
        session.server_sessions[server_name] = ServerSession(server=server_name)

    server = session.server_sessions[server_name]
    for tool_name in tools:
        server.tools[tool_name] = ToolStats(
            calls=calls_per_tool,
            total_tokens=100 * calls_per_tool,
        )
        server.total_calls += calls_per_tool


# ============================================================================
# ZombieToolConfig Tests
# ============================================================================


class TestZombieToolConfig:
    """Tests for ZombieToolConfig."""

    def test_default_config(self) -> None:
        """Test default empty config."""
        config = ZombieToolConfig()
        assert config.known_tools == {}

    def test_config_with_known_tools(self) -> None:
        """Test config with known tools."""
        config = ZombieToolConfig(
            known_tools={
                "zen": {"mcp__zen__chat", "mcp__zen__debug"},
                "backlog": {"mcp__backlog__task_list"},
            }
        )
        assert "zen" in config.known_tools
        assert "mcp__zen__chat" in config.known_tools["zen"]
        assert len(config.known_tools["backlog"]) == 1


class TestLoadZombieConfig:
    """Tests for load_zombie_config()."""

    def test_missing_config_file(self) -> None:
        """Test loading from non-existent file returns empty config."""
        config = load_zombie_config(Path("/nonexistent/path.toml"))
        assert config.known_tools == {}

    def test_load_valid_config(self) -> None:
        """Test loading valid TOML configuration."""
        toml_content = """
[zombie_tools.zen]
tools = ["mcp__zen__chat", "mcp__zen__debug", "mcp__zen__thinkdeep"]

[zombie_tools.backlog]
tools = ["mcp__backlog__task_list", "mcp__backlog__task_create"]
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_zombie_config(config_path)
            assert "zen" in config.known_tools
            assert len(config.known_tools["zen"]) == 3
            assert "mcp__zen__chat" in config.known_tools["zen"]
            assert "backlog" in config.known_tools
            assert len(config.known_tools["backlog"]) == 2
        finally:
            config_path.unlink()

    def test_load_config_without_zombie_section(self) -> None:
        """Test loading config file without zombie_tools section."""
        toml_content = """
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.0, output = 25.0 }
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_zombie_config(config_path)
            assert config.known_tools == {}
        finally:
            config_path.unlink()


# ============================================================================
# detect_zombie_tools Tests
# ============================================================================


class TestDetectZombieTools:
    """Tests for detect_zombie_tools()."""

    def test_no_zombies_when_all_called(self) -> None:
        """Test no zombies when all known tools are called."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat", "mcp__zen__debug"])

        config = ZombieToolConfig(known_tools={"zen": {"mcp__zen__chat", "mcp__zen__debug"}})

        zombies = detect_zombie_tools(session, config)
        assert zombies == {}

    def test_detects_zombies(self) -> None:
        """Test detection of zombie tools."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat"])

        config = ZombieToolConfig(
            known_tools={
                "zen": {
                    "mcp__zen__chat",
                    "mcp__zen__debug",
                    "mcp__zen__thinkdeep",
                }
            }
        )

        zombies = detect_zombie_tools(session, config)
        assert "zen" in zombies
        assert set(zombies["zen"]) == {"mcp__zen__debug", "mcp__zen__thinkdeep"}

    def test_skips_unconfigured_servers(self) -> None:
        """Test that servers without known tools config are skipped."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat"])
        add_server_with_tools(session, "other", ["mcp__other__foo"])

        # Only configure zen
        config = ZombieToolConfig(known_tools={"zen": {"mcp__zen__chat", "mcp__zen__debug"}})

        zombies = detect_zombie_tools(session, config)
        # Only zen should be checked
        assert "zen" in zombies
        assert "other" not in zombies

    def test_skips_builtin_server(self) -> None:
        """Test that builtin pseudo-server is skipped."""
        session = create_test_session()
        add_server_with_tools(session, "builtin", ["Bash", "Read"])

        config = ZombieToolConfig(known_tools={"builtin": {"Bash", "Read", "Write"}})

        zombies = detect_zombie_tools(session, config)
        assert "builtin" not in zombies

    def test_zombies_sorted_alphabetically(self) -> None:
        """Test that zombie tools are sorted for consistent output."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat"])

        config = ZombieToolConfig(
            known_tools={
                "zen": {
                    "mcp__zen__chat",
                    "mcp__zen__zzz",
                    "mcp__zen__aaa",
                    "mcp__zen__mmm",
                }
            }
        )

        zombies = detect_zombie_tools(session, config)
        assert zombies["zen"] == [
            "mcp__zen__aaa",
            "mcp__zen__mmm",
            "mcp__zen__zzz",
        ]

    def test_multiple_servers_with_zombies(self) -> None:
        """Test zombie detection across multiple servers."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat"])
        add_server_with_tools(session, "backlog", ["mcp__backlog__task_list"])

        config = ZombieToolConfig(
            known_tools={
                "zen": {"mcp__zen__chat", "mcp__zen__debug"},
                "backlog": {
                    "mcp__backlog__task_list",
                    "mcp__backlog__task_create",
                },
            }
        )

        zombies = detect_zombie_tools(session, config)
        assert "zen" in zombies
        assert zombies["zen"] == ["mcp__zen__debug"]
        assert "backlog" in zombies
        assert zombies["backlog"] == ["mcp__backlog__task_create"]

    def test_empty_session(self) -> None:
        """Test with empty session (no server sessions)."""
        session = create_test_session()

        config = ZombieToolConfig(known_tools={"zen": {"mcp__zen__chat"}})

        zombies = detect_zombie_tools(session, config)
        assert zombies == {}

    def test_no_config_provided(self) -> None:
        """Test with no config (uses default empty config)."""
        session = create_test_session()
        add_server_with_tools(session, "zen", ["mcp__zen__chat"])

        # With no config file in cwd, should return empty
        zombies = detect_zombie_tools(session, None)
        assert zombies == {}


# ============================================================================
# Integration Tests
# ============================================================================


class TestSessionFinalizationIntegration:
    """Test zombie detection during session finalization."""

    def test_finalize_session_populates_zombie_tools(self) -> None:
        """Test that finalize_session runs zombie detection."""
        from token_audit.base_tracker import BaseTracker

        class TestTracker(BaseTracker):
            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

            def start_tracking(self) -> None:
                pass

            def get_platform_metadata(self):
                return {}

            def _build_display_snapshot(self):
                pass

            def parse_event(self, event_data):
                return None

        tracker = TestTracker(project="test", platform="test-platform")

        # Record some tool calls
        tracker.record_tool_call(
            tool_name="mcp__zen__chat",
            input_tokens=100,
            output_tokens=50,
        )

        session = tracker.finalize_session()

        # zombie_tools should be populated (may be empty dict)
        assert hasattr(session, "zombie_tools")
        assert isinstance(session.zombie_tools, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
