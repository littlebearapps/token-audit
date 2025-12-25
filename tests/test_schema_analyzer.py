#!/usr/bin/env python3
"""
Test suite for schema_analyzer module (v0.6.0 - task-114.4)

Tests MCP schema analysis, token estimation, and static cost calculation.
"""

import json
import pytest
from pathlib import Path
from typing import Dict, Any

from token_audit.schema_analyzer import (
    SchemaAnalyzer,
    ServerSchema,
    discover_mcp_config,
    calculate_context_tax,
)
from token_audit.base_tracker import StaticCost


class TestServerSchema:
    """Tests for ServerSchema dataclass"""

    def test_server_schema_creation(self) -> None:
        """Test basic ServerSchema creation."""
        schema = ServerSchema(
            server="backlog",
            tool_count=15,
            estimated_tokens=2250,
            source="known_db",
        )

        assert schema.server == "backlog"
        assert schema.tool_count == 15
        assert schema.estimated_tokens == 2250
        assert schema.source == "known_db"

    def test_server_schema_to_dict(self) -> None:
        """Test ServerSchema serialization."""
        schema = ServerSchema(
            server="zen",
            tool_count=12,
            estimated_tokens=3000,
            source="estimate",
        )

        result = schema.to_dict()

        assert isinstance(result, dict)
        assert result["server"] == "zen"
        assert result["tool_count"] == 12
        assert result["estimated_tokens"] == 3000
        assert result["source"] == "estimate"


class TestSchemaAnalyzerKnownServers:
    """Tests for KNOWN_SERVERS database"""

    def test_known_servers_populated(self) -> None:
        """Test that KNOWN_SERVERS database is populated."""
        analyzer = SchemaAnalyzer()

        assert len(analyzer.known_servers) > 0
        assert "backlog" in analyzer.known_servers
        assert "brave-search" in analyzer.known_servers
        assert "zen" in analyzer.known_servers

    def test_known_server_structure(self) -> None:
        """Test that each known server has required fields."""
        analyzer = SchemaAnalyzer()

        for server_name, server_data in analyzer.known_servers.items():
            assert "tools" in server_data, f"Missing 'tools' for {server_name}"
            assert "tokens" in server_data, f"Missing 'tokens' for {server_name}"
            assert isinstance(server_data["tools"], int)
            assert isinstance(server_data["tokens"], int)
            assert server_data["tools"] > 0
            assert server_data["tokens"] > 0

    def test_known_server_lookup_exact_match(self) -> None:
        """Test exact match lookup in KNOWN_SERVERS."""
        analyzer = SchemaAnalyzer()

        # Create a config with known server
        config: Dict[str, Any] = {
            "mcpServers": {"backlog": {"command": "backlog", "args": ["mcp", "start"]}}
        }

        servers = analyzer.analyze_from_config(config)

        assert len(servers) == 1
        assert servers[0].server == "backlog"
        assert servers[0].tool_count == 15
        assert servers[0].estimated_tokens == 2250
        assert servers[0].source == "known_db"


class TestSchemaAnalyzerEstimation:
    """Tests for unknown server estimation"""

    def test_unknown_server_estimation(self) -> None:
        """Test that unknown servers get estimated token counts."""
        analyzer = SchemaAnalyzer()

        config: Dict[str, Any] = {
            "mcpServers": {"unknown-custom-server": {"command": "custom", "args": []}}
        }

        servers = analyzer.analyze_from_config(config)

        assert len(servers) == 1
        assert servers[0].server == "unknown-custom-server"
        assert servers[0].source == "estimate"
        # Default estimation: 10 tools * 175 tokens = 1750
        assert servers[0].estimated_tokens == 10 * 175

    def test_custom_tokens_per_tool(self) -> None:
        """Test custom tokens_per_tool estimation."""
        analyzer = SchemaAnalyzer(tokens_per_tool=200)

        config: Dict[str, Any] = {
            "mcpServers": {"custom-server": {"command": "custom", "args": []}}
        }

        servers = analyzer.analyze_from_config(config)

        # Should use custom tokens_per_tool
        assert servers[0].estimated_tokens == 10 * 200  # 10 default tools * 200

    def test_custom_known_servers(self) -> None:
        """Test extending known servers database."""
        custom_servers = {"my-custom-mcp": {"tools": 8, "tokens": 1200}}
        analyzer = SchemaAnalyzer(known_servers=custom_servers)

        config: Dict[str, Any] = {
            "mcpServers": {"my-custom-mcp": {"command": "custom", "args": []}}
        }

        servers = analyzer.analyze_from_config(config)

        assert servers[0].source == "known_db"
        assert servers[0].estimated_tokens == 1200


class TestSchemaAnalyzerConfigParsing:
    """Tests for config parsing"""

    def test_analyze_from_config_empty(self) -> None:
        """Test handling of empty config."""
        analyzer = SchemaAnalyzer()

        servers = analyzer.analyze_from_config({})

        assert len(servers) == 0

    def test_analyze_from_config_mcp_json_format(self) -> None:
        """Test parsing Claude Code .mcp.json format."""
        analyzer = SchemaAnalyzer()

        config: Dict[str, Any] = {
            "mcpServers": {
                "backlog": {"command": "backlog", "args": ["mcp", "start"]},
                "brave-search": {"command": "npx", "args": ["@brave/brave-search-mcp-server"]},
            }
        }

        servers = analyzer.analyze_from_config(config)

        assert len(servers) == 2
        server_names = {s.server for s in servers}
        assert "backlog" in server_names
        assert "brave-search" in server_names

    def test_analyze_from_config_partial_match(self) -> None:
        """Test partial name matching in KNOWN_SERVERS."""
        analyzer = SchemaAnalyzer()

        # Use the npm package name pattern
        config: Dict[str, Any] = {
            "mcpServers": {
                "search": {"command": "npx", "args": ["-y", "@brave/brave-search-mcp-server"]}
            }
        }

        servers = analyzer.analyze_from_config(config)

        # Should match based on command args containing known server name
        assert len(servers) == 1
        assert servers[0].source == "known_db"

    def test_analyze_from_config_skips_non_dict_entries(self) -> None:
        """Test that non-dict entries are skipped."""
        analyzer = SchemaAnalyzer()

        config: Dict[str, Any] = {
            "mcpServers": {
                "valid-server": {"command": "cmd", "args": []},
                "invalid-entry": "not a dict",
                "another-invalid": 123,
            }
        }

        servers = analyzer.analyze_from_config(config)

        assert len(servers) == 1
        assert servers[0].server == "valid-server"


class TestSchemaAnalyzerFromFile:
    """Tests for file-based config loading"""

    def test_analyze_from_file_json(self, tmp_path: Path) -> None:
        """Test analyzing from JSON config file."""
        config_file = tmp_path / ".mcp.json"
        config = {"mcpServers": {"backlog": {"command": "backlog", "args": []}}}
        config_file.write_text(json.dumps(config))

        analyzer = SchemaAnalyzer()
        servers = analyzer.analyze_from_file(config_file)

        assert len(servers) == 1
        assert servers[0].server == "backlog"

    def test_analyze_from_file_not_found(self, tmp_path: Path) -> None:
        """Test handling of missing config file."""
        analyzer = SchemaAnalyzer()

        with pytest.raises(FileNotFoundError):
            analyzer.analyze_from_file(tmp_path / "nonexistent.json")

    def test_analyze_from_file_invalid_json(self, tmp_path: Path) -> None:
        """Test handling of invalid JSON."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text("not valid json {{{")

        analyzer = SchemaAnalyzer()

        with pytest.raises(json.JSONDecodeError):
            analyzer.analyze_from_file(config_file)


class TestCalculateStaticCost:
    """Tests for static cost calculation"""

    def test_calculate_static_cost_empty(self) -> None:
        """Test static cost with no servers."""
        analyzer = SchemaAnalyzer()

        result = analyzer.calculate_static_cost([])

        assert result.total_tokens == 0
        assert result.source == "estimate"
        assert result.by_server == {}
        assert result.confidence == 0.0

    def test_calculate_static_cost_single_known_server(self) -> None:
        """Test static cost with single known server."""
        analyzer = SchemaAnalyzer()

        servers = [
            ServerSchema(
                server="backlog",
                tool_count=15,
                estimated_tokens=2250,
                source="known_db",
            )
        ]

        result = analyzer.calculate_static_cost(servers)

        assert result.total_tokens == 2250
        assert result.source == "known_db"
        assert result.by_server == {"backlog": 2250}
        assert result.confidence == 0.9  # 100% known servers

    def test_calculate_static_cost_mixed_servers(self) -> None:
        """Test static cost with known and estimated servers."""
        analyzer = SchemaAnalyzer()

        servers = [
            ServerSchema(server="backlog", tool_count=15, estimated_tokens=2250, source="known_db"),
            ServerSchema(server="custom", tool_count=10, estimated_tokens=1750, source="estimate"),
        ]

        result = analyzer.calculate_static_cost(servers)

        assert result.total_tokens == 4000
        assert result.source == "mixed"
        assert result.by_server == {"backlog": 2250, "custom": 1750}
        # Confidence: (1 * 0.9 + 1 * 0.7) / 2 = 0.8
        assert result.confidence == 0.8

    def test_calculate_static_cost_all_estimated(self) -> None:
        """Test static cost with all estimated servers."""
        analyzer = SchemaAnalyzer()

        servers = [
            ServerSchema(server="a", tool_count=10, estimated_tokens=1750, source="estimate"),
            ServerSchema(server="b", tool_count=10, estimated_tokens=1750, source="estimate"),
        ]

        result = analyzer.calculate_static_cost(servers)

        assert result.source == "estimate"
        assert result.confidence == 0.7  # All estimated


class TestZombieContextTax:
    """Tests for zombie tool context tax calculation"""

    def test_zombie_context_tax_empty(self) -> None:
        """Test zombie tax with no zombies."""
        analyzer = SchemaAnalyzer()

        result = analyzer.get_zombie_context_tax({}, [])

        assert result == 0

    def test_zombie_context_tax_calculation(self) -> None:
        """Test zombie tax calculation."""
        analyzer = SchemaAnalyzer()

        servers = [
            ServerSchema(server="backlog", tool_count=15, estimated_tokens=2250, source="known_db"),
        ]
        zombie_tools = {
            "backlog": ["task_archive", "task_delete", "document_delete"],  # 3 zombies
        }

        result = analyzer.get_zombie_context_tax(zombie_tools, servers)

        # backlog: 2250 tokens / 15 tools = 150 tokens/tool
        # 3 zombies * 150 = 450 tokens
        assert result == 450

    def test_zombie_context_tax_unknown_server(self) -> None:
        """Test zombie tax with server not in schema list."""
        analyzer = SchemaAnalyzer()

        servers = [
            ServerSchema(server="backlog", tool_count=15, estimated_tokens=2250, source="known_db"),
        ]
        zombie_tools = {
            "unknown-server": ["tool1", "tool2"],  # Server not in servers list
        }

        result = analyzer.get_zombie_context_tax(zombie_tools, servers)

        # Falls back to default estimate: 2 zombies * 175 tokens/tool = 350
        assert result == 350


class TestDiscoverMcpConfig:
    """Tests for MCP config discovery"""

    def test_discover_mcp_config_in_directory(self, tmp_path: Path) -> None:
        """Test discovering .mcp.json in working directory."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text('{"mcpServers": {}}')

        result = discover_mcp_config(tmp_path)

        assert result == config_file

    def test_discover_mcp_config_parent_directory(self, tmp_path: Path) -> None:
        """Test discovering .mcp.json in parent directory."""
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        config_file = parent / ".mcp.json"
        config_file.write_text('{"mcpServers": {}}')

        result = discover_mcp_config(child)

        assert result == config_file

    def test_discover_mcp_config_not_found(self, tmp_path: Path) -> None:
        """Test when no config file exists."""
        # Create empty directory with no config
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Mock home directory to avoid finding global config
        result = discover_mcp_config(empty_dir)

        # May find global config or return None
        # Just verify it doesn't crash
        assert result is None or isinstance(result, Path)


class TestCalculateContextTax:
    """Tests for the convenience function"""

    def test_calculate_context_tax_with_config(self, tmp_path: Path) -> None:
        """Test convenience function with explicit config."""
        config_file = tmp_path / ".mcp.json"
        config = {"mcpServers": {"backlog": {"command": "backlog", "args": []}}}
        config_file.write_text(json.dumps(config))

        result = calculate_context_tax(config_path=config_file)

        assert isinstance(result, StaticCost)
        assert result.total_tokens > 0
        assert "backlog" in result.by_server

    def test_calculate_context_tax_no_local_config(self, tmp_path: Path) -> None:
        """Test convenience function when no local config found.

        Note: May find global ~/.claude/settings.json as fallback,
        so we just verify it handles the case gracefully.
        """
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = calculate_context_tax(working_dir=empty_dir)

        assert isinstance(result, StaticCost)
        # May find global config, so just verify it returns valid result
        assert result.total_tokens >= 0
        assert result.source in ("none", "estimate", "known_db", "mixed")


class TestSchemaAnalyzerToml:
    """Tests for TOML config parsing (Codex CLI)"""

    @pytest.fixture
    def has_toml_support(self) -> bool:
        """Check if TOML support is available."""
        try:
            import tomllib  # noqa: F401

            return True
        except ImportError:
            try:
                import tomli  # noqa: F401

                return True
            except ImportError:
                return False

    def test_analyze_from_file_toml(self, tmp_path: Path, has_toml_support: bool) -> None:
        """Test analyzing from TOML config file."""
        if not has_toml_support:
            pytest.skip("TOML support not available (requires Python 3.11+ or tomli)")

        config_file = tmp_path / "config.toml"
        config_content = """
[mcp_servers.brave-search-mcp]
command = "npx"
args = ["-y", "@brave/brave-search-mcp-server"]

[mcp_servers.backlog]
command = "backlog"
args = ["mcp", "start"]
"""
        config_file.write_text(config_content)

        analyzer = SchemaAnalyzer()
        servers = analyzer.analyze_from_file(config_file)

        assert len(servers) == 2
        server_names = {s.server for s in servers}
        assert "brave-search-mcp" in server_names
        assert "backlog" in server_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
