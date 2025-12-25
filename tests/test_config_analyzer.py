"""Integration tests for config_analyzer module.

Tests for JSON/TOML parsing, credential detection, server count analysis,
pinned server detection, and the analyze_config MCP tool.
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from token_audit.config_analyzer import (
    ConfigIssue,
    MCPConfig,
    PinnedServer,
    ServerConfig,
    analyze_config,
    detect_credentials,
    detect_pinned_servers,
    parse_config,
    parse_json_config,
    parse_toml_config,
)
from token_audit.config_analyzer.analyzer import (
    EXCESSIVE_SERVER_THRESHOLD,
    MANY_SERVER_THRESHOLD,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_claude_config(tmp_path: Path) -> Path:
    """Create sample Claude Code .mcp.json config."""
    config = {
        "mcpServers": {
            "zen": {
                "command": "npx",
                "args": ["-y", "@anthropic/zen-mcp-server"],
                "env": {"ZEN_API_KEY": ""},
            },
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@anthropic/brave-search-mcp"],
                "env": {},
            },
            "custom-server": {
                "command": "python3",
                "args": ["/Users/dev/my-server/main.py"],
                "env": {},
            },
        }
    }
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def sample_codex_config(tmp_path: Path) -> Path:
    """Create sample Codex CLI config.toml."""
    config = """
[mcp_servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem"]

[mcp_servers.custom]
command = "node"
args = ["./local-server.js"]
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config)
    return config_path


@pytest.fixture
def sample_gemini_config(tmp_path: Path) -> Path:
    """Create sample Gemini CLI settings.json."""
    config = {
        "mcpServers": {
            "context7": {
                "command": "npx",
                "args": ["-y", "@google/context7-mcp"],
                "disabled": False,
            },
            "disabled-server": {
                "command": "python3",
                "args": ["server.py"],
                "disabled": True,
            },
        }
    }
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def config_with_credentials(tmp_path: Path) -> Path:
    """Create config with exposed credentials."""
    config = {
        "mcpServers": {
            "openai-server": {
                "command": "node",
                "args": ["server.js"],
                "env": {
                    "OPENAI_API_KEY": "sk-1234567890abcdef1234567890abcdef1234567890abcdef",
                },
            },
            "github-server": {
                "command": "python3",
                "args": ["--token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"],
            },
        }
    }
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def config_with_many_servers(tmp_path: Path) -> Path:
    """Create config with many servers (>10)."""
    servers = {}
    for i in range(12):
        servers[f"server-{i}"] = {
            "command": "npx",
            "args": ["-y", f"@test/server-{i}"],
        }
    config = {"mcpServers": servers}
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def config_with_excessive_servers(tmp_path: Path) -> Path:
    """Create config with excessive servers (>15)."""
    servers = {}
    for i in range(18):
        servers[f"server-{i}"] = {
            "command": "npx",
            "args": ["-y", f"@test/server-{i}"],
        }
    config = {"mcpServers": servers}
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def config_with_pinned_servers(tmp_path: Path) -> Path:
    """Create config with explicit pinned servers."""
    config = {
        "mcpServers": {
            "my-custom-server": {
                "command": "python3",
                "args": ["/home/dev/my-server/main.py"],
                "pinned": True,
            },
            "another-server": {
                "command": "npx",
                "args": ["-y", "@test/server"],
            },
        },
        "pinned_servers": ["another-server"],
    }
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


# =============================================================================
# JSON Parsing Tests
# =============================================================================


class TestParseJsonConfig:
    """Tests for JSON config parsing."""

    def test_parse_json_config_valid(self, sample_claude_config: Path) -> None:
        """Test parsing valid JSON config file."""
        config = parse_json_config(sample_claude_config, "claude_code")

        assert config.platform == "claude_code"
        assert config.path == sample_claude_config
        assert config.parse_error is None
        assert len(config.servers) == 3

    def test_parse_json_config_servers_extracted(self, sample_claude_config: Path) -> None:
        """Test that servers are correctly extracted from JSON."""
        config = parse_json_config(sample_claude_config, "claude_code")

        assert "zen" in config.servers
        assert "brave-search" in config.servers
        assert "custom-server" in config.servers

        zen = config.servers["zen"]
        assert zen.command == "npx"
        assert zen.args == ["-y", "@anthropic/zen-mcp-server"]

    def test_parse_json_config_invalid(self, tmp_path: Path) -> None:
        """Test handling malformed JSON file."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json content")

        config = parse_json_config(bad_json, "claude_code")

        assert config.parse_error is not None
        assert "JSON parse error" in config.parse_error
        assert len(config.servers) == 0

    def test_parse_json_config_file_not_found(self, tmp_path: Path) -> None:
        """Test handling missing config file."""
        missing = tmp_path / "missing.json"

        config = parse_json_config(missing, "claude_code")

        assert config.parse_error is not None
        assert "File not found" in config.parse_error

    def test_parse_json_config_empty(self, tmp_path: Path) -> None:
        """Test handling empty JSON config."""
        empty = tmp_path / "empty.json"
        empty.write_text("{}")

        config = parse_json_config(empty, "claude_code")

        assert config.parse_error is None
        assert len(config.servers) == 0

    def test_parse_json_config_no_mcp_servers_key(self, tmp_path: Path) -> None:
        """Test config without mcpServers key."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"other": "data"}))

        config = parse_json_config(config_file, "claude_code")

        assert config.parse_error is None
        assert len(config.servers) == 0

    def test_parse_json_config_disabled_server(self, sample_gemini_config: Path) -> None:
        """Test parsing config with disabled servers."""
        config = parse_json_config(sample_gemini_config, "gemini_cli")

        assert "disabled-server" in config.servers
        assert config.servers["disabled-server"].disabled is True
        assert config.servers["context7"].disabled is False


# =============================================================================
# TOML Parsing Tests
# =============================================================================


class TestParseTomlConfig:
    """Tests for TOML config parsing."""

    def test_parse_toml_config_valid(self, sample_codex_config: Path) -> None:
        """Test parsing valid TOML config file."""
        config = parse_toml_config(sample_codex_config, "codex_cli")

        assert config.platform == "codex_cli"
        assert config.path == sample_codex_config
        assert config.parse_error is None
        assert len(config.servers) == 2

    def test_parse_toml_config_servers_extracted(self, sample_codex_config: Path) -> None:
        """Test that servers are correctly extracted from TOML."""
        config = parse_toml_config(sample_codex_config, "codex_cli")

        assert "filesystem" in config.servers
        assert "custom" in config.servers

        filesystem = config.servers["filesystem"]
        assert filesystem.command == "npx"
        assert "-y" in filesystem.args

    def test_parse_toml_config_invalid(self, tmp_path: Path) -> None:
        """Test handling malformed TOML file."""
        bad_toml = tmp_path / "bad.toml"
        bad_toml.write_text("[invalid toml = content")

        config = parse_toml_config(bad_toml, "codex_cli")

        assert config.parse_error is not None
        assert "TOML parse error" in config.parse_error

    def test_parse_toml_config_empty(self, tmp_path: Path) -> None:
        """Test handling empty TOML config."""
        empty = tmp_path / "empty.toml"
        empty.write_text("")

        config = parse_toml_config(empty, "codex_cli")

        assert config.parse_error is None
        assert len(config.servers) == 0


# =============================================================================
# parse_config Auto-Detection Tests
# =============================================================================


class TestParseConfig:
    """Tests for auto-detecting config format."""

    def test_parse_config_json(self, sample_claude_config: Path) -> None:
        """Test parse_config auto-detects JSON."""
        config = parse_config(sample_claude_config, "claude_code")

        assert config.parse_error is None
        assert len(config.servers) == 3

    def test_parse_config_toml(self, sample_codex_config: Path) -> None:
        """Test parse_config auto-detects TOML."""
        config = parse_config(sample_codex_config, "codex_cli")

        assert config.parse_error is None
        assert len(config.servers) == 2

    def test_parse_config_unsupported_format(self, tmp_path: Path) -> None:
        """Test parse_config rejects unsupported formats."""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("key: value")

        config = parse_config(yaml_file, "unknown")

        assert config.parse_error is not None
        assert "Unsupported config format" in config.parse_error


# =============================================================================
# Credential Detection Tests
# =============================================================================


class TestCredentialDetection:
    """Tests for credential exposure detection."""

    def test_detect_credentials_api_key_in_env(self) -> None:
        """Test detecting API keys in environment variables."""
        config_data = {
            "mcpServers": {
                "test": {
                    "env": {
                        "OPENAI_API_KEY": "sk-1234567890abcdef1234567890abcdef1234567890abcdef",
                    }
                }
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 1
        assert any(i.credential_type == "OpenAI API key" for i in issues)

    def test_detect_credentials_token_in_args(self) -> None:
        """Test detecting tokens in command arguments."""
        config_data = {
            "mcpServers": {
                "test": {
                    "args": ["--token", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"],
                }
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 1
        assert any("GitHub" in i.credential_type for i in issues)

    def test_detect_credentials_no_issues(self) -> None:
        """Test clean config returns no credential issues."""
        config_data = {
            "mcpServers": {
                "test": {
                    "command": "npx",
                    "args": ["-y", "@test/server"],
                    "env": {"PATH": "/usr/bin"},
                }
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) == 0

    def test_detect_credentials_multiple_issues(self) -> None:
        """Test detecting multiple credential exposures."""
        config_data = {
            "mcpServers": {
                "server1": {
                    "env": {
                        "OPENAI_API_KEY": "sk-1234567890abcdef1234567890abcdef1234567890abcdef",
                    }
                },
                "server2": {
                    "args": ["ghp_abcdefghijklmnopqrstuvwxyz0123456789"],
                },
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 2
        credential_types = [i.credential_type for i in issues]
        assert any("OpenAI" in t for t in credential_types)
        assert any("GitHub" in t for t in credential_types)

    def test_detect_credentials_anthropic_key(self) -> None:
        """Test detecting Anthropic API keys."""
        config_data = {
            "env": {
                "ANTHROPIC_API_KEY": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz01234567890",
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 1
        assert any("Anthropic" in i.credential_type for i in issues)

    def test_detect_credentials_aws_key(self) -> None:
        """Test detecting AWS access keys."""
        config_data = {
            "env": {
                "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 1
        assert any("AWS" in i.credential_type for i in issues)

    def test_detect_credentials_value_preview_masked(self) -> None:
        """Test that credential preview is properly masked."""
        config_data = {
            "env": {
                "KEY": "sk-1234567890abcdef1234567890abcdef1234567890abcdef",
            }
        }

        issues = detect_credentials(config_data)

        assert len(issues) >= 1
        # Preview should show partial key, not full
        preview = issues[0].value_preview
        assert "sk-" in preview
        assert len(preview) < 50  # Much shorter than full key


# =============================================================================
# Server Count Analysis Tests
# =============================================================================


class TestServerCountAnalysis:
    """Tests for server count issue detection."""

    def test_analyze_excessive_servers(self, config_with_excessive_servers: Path) -> None:
        """Test >15 servers triggers high severity warning."""
        config = parse_json_config(config_with_excessive_servers, "claude_code")
        issues = analyze_config(config)

        excessive_issues = [i for i in issues if i.category == "excessive_servers"]
        assert len(excessive_issues) == 1
        assert excessive_issues[0].severity == "high"
        assert str(EXCESSIVE_SERVER_THRESHOLD) in excessive_issues[0].message

    def test_analyze_many_servers(self, config_with_many_servers: Path) -> None:
        """Test >10 servers triggers medium severity info."""
        config = parse_json_config(config_with_many_servers, "claude_code")
        issues = analyze_config(config)

        many_issues = [i for i in issues if i.category == "many_servers"]
        assert len(many_issues) == 1
        assert many_issues[0].severity == "medium"

    def test_analyze_normal_server_count(self, sample_claude_config: Path) -> None:
        """Test <10 servers generates no server count warning."""
        config = parse_json_config(sample_claude_config, "claude_code")
        issues = analyze_config(config)

        server_count_issues = [
            i for i in issues if i.category in ("excessive_servers", "many_servers")
        ]
        assert len(server_count_issues) == 0

    def test_analyze_server_count_threshold_boundary(self, tmp_path: Path) -> None:
        """Test boundary at exactly 10 servers (no warning)."""
        servers = {}
        for i in range(MANY_SERVER_THRESHOLD):  # Exactly 10
            servers[f"server-{i}"] = {
                "command": "npx",
                "args": [f"@test/server-{i}"],
            }
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({"mcpServers": servers}))

        config = parse_json_config(config_file, "claude_code")
        issues = analyze_config(config)

        # Exactly at threshold should NOT trigger warning
        server_issues = [i for i in issues if i.category in ("excessive_servers", "many_servers")]
        assert len(server_issues) == 0


# =============================================================================
# Pinned Server Detection Tests
# =============================================================================


class TestPinnedServerDetection:
    """Tests for pinned server detection."""

    def test_detect_pinned_explicit_config(self, config_with_pinned_servers: Path) -> None:
        """Test detecting servers from pinned_servers array in config."""
        config = parse_json_config(config_with_pinned_servers, "claude_code")
        pinned = detect_pinned_servers(config)

        # Should find "another-server" from pinned_servers array
        pinned_names = [p.name for p in pinned]
        assert "another-server" in pinned_names

        # Find the entry and check method
        another = next(p for p in pinned if p.name == "another-server")
        assert another.detection_method == "explicit_config"

    def test_detect_pinned_explicit_flag(self, config_with_pinned_servers: Path) -> None:
        """Test detecting servers with pinned: true flag."""
        config = parse_json_config(config_with_pinned_servers, "claude_code")
        pinned = detect_pinned_servers(config)

        # Should find "my-custom-server" with pinned: true
        pinned_names = [p.name for p in pinned]
        assert "my-custom-server" in pinned_names

        # Find the entry and check method
        custom = next(p for p in pinned if p.name == "my-custom-server")
        assert custom.detection_method == "explicit_flag"

    def test_detect_pinned_custom_path(self, sample_claude_config: Path) -> None:
        """Test auto-detecting servers with local paths."""
        config = parse_json_config(sample_claude_config, "claude_code")
        pinned = detect_pinned_servers(config)

        # "custom-server" has a local path, should be auto-detected
        pinned_names = [p.name for p in pinned]
        assert "custom-server" in pinned_names

        custom = next(p for p in pinned if p.name == "custom-server")
        assert custom.auto_detected is True
        assert custom.detection_method == "custom_path"

    def test_detect_pinned_npm_excluded(self, sample_claude_config: Path) -> None:
        """Test that NPM packages are not auto-pinned."""
        config = parse_json_config(sample_claude_config, "claude_code")
        pinned = detect_pinned_servers(config)

        # "zen" and "brave-search" use npx, should NOT be pinned
        pinned_names = [p.name for p in pinned]
        assert "zen" not in pinned_names
        assert "brave-search" not in pinned_names

    def test_detect_pinned_usage_frequency(self, sample_claude_config: Path) -> None:
        """Test detecting frequently used servers."""
        config = parse_json_config(sample_claude_config, "claude_code")
        usage_data = {"zen": 50, "brave-search": 5}  # zen has high usage

        pinned = detect_pinned_servers(config, usage_data=usage_data)

        # zen should be pinned due to high usage (>10 calls)
        pinned_names = [p.name for p in pinned]
        assert "zen" in pinned_names

        zen = next(p for p in pinned if p.name == "zen")
        assert zen.detection_method == "usage_frequency"

    def test_detect_pinned_merged_results(self, config_with_pinned_servers: Path) -> None:
        """Test all 3 detection methods are merged without duplicates."""
        config = parse_json_config(config_with_pinned_servers, "claude_code")
        # Add usage data that overlaps with explicit config
        usage_data = {"another-server": 100}

        pinned = detect_pinned_servers(config, usage_data=usage_data)

        # "another-server" appears in both explicit and usage, should appear once
        names = [p.name for p in pinned]
        assert names.count("another-server") == 1

    def test_detect_pinned_empty_config(self, tmp_path: Path) -> None:
        """Test pinned detection with empty config."""
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps({"mcpServers": {}}))

        config = parse_json_config(config_file, "claude_code")
        pinned = detect_pinned_servers(config)

        assert len(pinned) == 0


# =============================================================================
# analyze_config Tool Integration Tests
# =============================================================================


class TestAnalyzeConfigTool:
    """Tests for the analyze_config function (module level)."""

    def test_analyze_config_returns_issues_list(self, sample_claude_config: Path) -> None:
        """Test analyze_config returns list of ConfigIssue."""
        config = parse_json_config(sample_claude_config, "claude_code")
        issues = analyze_config(config)

        assert isinstance(issues, list)
        for issue in issues:
            assert isinstance(issue, ConfigIssue)

    def test_analyze_config_with_credentials(self, config_with_credentials: Path) -> None:
        """Test analyze_config detects credential exposure."""
        config = parse_json_config(config_with_credentials, "claude_code")
        issues = analyze_config(config)

        cred_issues = [i for i in issues if i.category == "credential_exposure"]
        assert len(cred_issues) >= 1
        assert all(i.severity == "critical" for i in cred_issues)

    def test_analyze_config_parse_error(self, tmp_path: Path) -> None:
        """Test analyze_config handles parse errors."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid")

        config = parse_json_config(bad_json, "claude_code")
        issues = analyze_config(config)

        # Should return single parse error issue
        assert len(issues) == 1
        assert issues[0].category == "parse_error"
        assert issues[0].severity == "high"

    def test_analyze_config_empty_env_vars(self, sample_claude_config: Path) -> None:
        """Test analyze_config detects empty environment variables."""
        config = parse_json_config(sample_claude_config, "claude_code")
        issues = analyze_config(config)

        # "zen" server has empty ZEN_API_KEY
        empty_env_issues = [i for i in issues if i.category == "empty_env"]
        assert len(empty_env_issues) >= 1

    def test_analyze_config_disabled_servers_info(self, sample_gemini_config: Path) -> None:
        """Test analyze_config reports disabled servers as info."""
        config = parse_json_config(sample_gemini_config, "gemini_cli")
        issues = analyze_config(config)

        disabled_issues = [i for i in issues if i.category == "disabled_servers"]
        assert len(disabled_issues) == 1
        assert disabled_issues[0].severity == "info"

    def test_analyze_config_returns_all_issue_fields(self, config_with_credentials: Path) -> None:
        """Test ConfigIssue has all required fields."""
        config = parse_json_config(config_with_credentials, "claude_code")
        issues = analyze_config(config)

        assert len(issues) >= 1
        issue = issues[0]

        assert issue.severity in ("critical", "high", "medium", "low", "info")
        assert issue.category != ""
        assert issue.message != ""
        assert issue.location != ""
        assert issue.recommendation != ""

    def test_analyze_config_clean_config(self, tmp_path: Path) -> None:
        """Test analyze_config with a clean config has minimal issues."""
        config_data = {
            "mcpServers": {
                "server1": {
                    "command": "npx",
                    "args": ["-y", "@test/server"],
                    "env": {"VALID_VAR": "value"},
                },
            }
        }
        config_file = tmp_path / ".mcp.json"
        config_file.write_text(json.dumps(config_data))

        config = parse_json_config(config_file, "claude_code")
        issues = analyze_config(config)

        # Should have no critical/high issues
        critical_high = [i for i in issues if i.severity in ("critical", "high")]
        assert len(critical_high) == 0


# =============================================================================
# MCPConfig/ServerConfig Model Tests
# =============================================================================


class TestConfigModels:
    """Tests for MCPConfig and ServerConfig dataclasses."""

    def test_mcp_config_server_count(self, sample_claude_config: Path) -> None:
        """Test MCPConfig.server_count property."""
        config = parse_json_config(sample_claude_config, "claude_code")

        assert config.server_count == 3

    def test_mcp_config_enabled_server_count(self, sample_gemini_config: Path) -> None:
        """Test MCPConfig.enabled_server_count property."""
        config = parse_json_config(sample_gemini_config, "gemini_cli")

        # 2 servers, 1 disabled
        assert config.server_count == 2
        assert config.enabled_server_count == 1

    def test_server_config_to_dict(self, sample_claude_config: Path) -> None:
        """Test ServerConfig.to_dict method."""
        config = parse_json_config(sample_claude_config, "claude_code")
        server = config.servers["zen"]

        server_dict = server.to_dict()

        assert server_dict["name"] == "zen"
        assert server_dict["command"] == "npx"
        assert isinstance(server_dict["args"], list)
        assert isinstance(server_dict["env"], dict)

    def test_pinned_server_to_dict(self, config_with_pinned_servers: Path) -> None:
        """Test PinnedServer.to_dict method."""
        config = parse_json_config(config_with_pinned_servers, "claude_code")
        pinned = detect_pinned_servers(config)

        assert len(pinned) > 0
        pinned_dict = pinned[0].to_dict()

        assert "name" in pinned_dict
        assert "auto_detected" in pinned_dict
        assert "detection_method" in pinned_dict
