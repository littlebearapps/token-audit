"""Tests for pinned_config module.

Tests for the new pinned servers configuration system that replaces
pin_storage.py with toggleable detection methods and project overrides.
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from token_audit.pinned_config import (
    DetectionMethods,
    EffectiveConfig,
    PinnedConfig,
    PinnedConfigManager,
    PinnedEntry,
    ProjectOverride,
    get_effective_config,
    load_pinned_config,
    save_pinned_config,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def manager(temp_config_dir: Path) -> PinnedConfigManager:
    """Create a PinnedConfigManager with temporary directory."""
    return PinnedConfigManager(config_dir=temp_config_dir)


@pytest.fixture
def legacy_pin_file(tmp_path: Path) -> Path:
    """Create a legacy pinned.json file for migration testing."""
    legacy_dir = tmp_path / ".token-audit"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "pinned.json"
    legacy_data = {
        "version": 1,
        "pinned": [
            {"name": "server-1", "notes": "Test server", "pinned_at": "2025-01-01T00:00:00"},
            {"name": "server-2", "notes": None, "pinned_at": "2025-01-02T00:00:00"},
        ],
    }
    legacy_file.write_text(json.dumps(legacy_data))
    return legacy_file


# =============================================================================
# DetectionMethods Tests
# =============================================================================


class TestDetectionMethods:
    """Tests for DetectionMethods dataclass."""

    def test_default_values(self) -> None:
        """Test DetectionMethods has correct defaults."""
        methods = DetectionMethods()

        assert methods.auto_detect_local is True
        assert methods.explicit_servers == []
        assert methods.high_usage_threshold == 0.2

    def test_to_dict(self) -> None:
        """Test DetectionMethods serialization."""
        methods = DetectionMethods(
            auto_detect_local=False,
            explicit_servers=["server-1", "server-2"],
            high_usage_threshold=0.3,
        )

        data = methods.to_dict()

        assert data["auto_detect_local"] is False
        assert data["explicit_servers"] == ["server-1", "server-2"]
        assert data["high_usage_threshold"] == 0.3

    def test_from_dict(self) -> None:
        """Test DetectionMethods deserialization."""
        data = {
            "auto_detect_local": False,
            "explicit_servers": ["my-server"],
            "high_usage_threshold": 0.5,
        }

        methods = DetectionMethods.from_dict(data)

        assert methods.auto_detect_local is False
        assert methods.explicit_servers == ["my-server"]
        assert methods.high_usage_threshold == 0.5

    def test_from_dict_missing_keys(self) -> None:
        """Test DetectionMethods handles missing keys with defaults."""
        methods = DetectionMethods.from_dict({})

        assert methods.auto_detect_local is True
        assert methods.explicit_servers == []
        assert methods.high_usage_threshold == 0.2


# =============================================================================
# ProjectOverride Tests
# =============================================================================


class TestProjectOverride:
    """Tests for ProjectOverride dataclass."""

    def test_default_values(self) -> None:
        """Test ProjectOverride has correct defaults."""
        override = ProjectOverride()

        assert override.inherit_global is True  # Default to inherit
        assert override.explicit_servers == []
        assert override.exclusions == []

    def test_to_dict(self) -> None:
        """Test ProjectOverride serialization."""
        override = ProjectOverride(
            inherit_global=False,
            explicit_servers=["project-server"],
            exclusions=["excluded-server"],
        )

        data = override.to_dict()

        assert data["inherit_global"] is False
        assert data["explicit_servers"] == ["project-server"]
        assert data["exclusions"] == ["excluded-server"]

    def test_from_dict(self) -> None:
        """Test ProjectOverride deserialization."""
        data = {
            "inherit_global": False,
            "explicit_servers": ["s1", "s2"],
            "exclusions": ["e1"],
        }

        override = ProjectOverride.from_dict(data)

        assert override.inherit_global is False
        assert override.explicit_servers == ["s1", "s2"]
        assert override.exclusions == ["e1"]

    def test_from_dict_missing_inherit_global_defaults_true(self) -> None:
        """Test ProjectOverride defaults inherit_global to True if missing."""
        data = {
            "explicit_servers": ["s1"],
            "exclusions": [],
        }

        override = ProjectOverride.from_dict(data)

        assert override.inherit_global is True  # Default when not specified


# =============================================================================
# PinnedConfig Tests
# =============================================================================


class TestPinnedConfig:
    """Tests for PinnedConfig dataclass."""

    def test_default_values(self) -> None:
        """Test PinnedConfig has correct defaults."""
        config = PinnedConfig()

        assert config.version == "1.0.0"
        assert isinstance(config.detection_methods, DetectionMethods)
        assert config.exclusions == []
        assert config.project_overrides == {}

    def test_to_dict(self) -> None:
        """Test PinnedConfig serialization."""
        config = PinnedConfig(
            exclusions=["brave-search"],
            project_overrides={
                "/path/to/project": ProjectOverride(explicit_servers=["project-server"])
            },
        )

        data = config.to_dict()

        assert data["version"] == "1.0.0"
        assert "detection_methods" in data
        assert data["exclusions"] == ["brave-search"]
        assert "/path/to/project" in data["project_overrides"]

    def test_from_dict(self) -> None:
        """Test PinnedConfig deserialization."""
        data = {
            "version": "1.0.0",
            "detection_methods": {
                "auto_detect_local": False,
                "explicit_servers": ["my-server"],
                "high_usage_threshold": 0.1,
            },
            "exclusions": ["context7"],
            "project_overrides": {
                "/my/project": {
                    "explicit_servers": ["proj-server"],
                    "exclusions": [],
                }
            },
        }

        config = PinnedConfig.from_dict(data)

        assert config.version == "1.0.0"
        assert config.detection_methods.auto_detect_local is False
        assert config.detection_methods.explicit_servers == ["my-server"]
        assert config.exclusions == ["context7"]
        assert "/my/project" in config.project_overrides

    def test_roundtrip(self) -> None:
        """Test PinnedConfig serialization roundtrip."""
        original = PinnedConfig(
            detection_methods=DetectionMethods(
                auto_detect_local=False,
                explicit_servers=["a", "b"],
                high_usage_threshold=0.15,
            ),
            exclusions=["x", "y"],
            project_overrides={"/proj": ProjectOverride(explicit_servers=["z"], exclusions=["w"])},
        )

        data = original.to_dict()
        restored = PinnedConfig.from_dict(data)

        assert restored.version == original.version
        assert (
            restored.detection_methods.auto_detect_local
            == original.detection_methods.auto_detect_local
        )
        assert (
            restored.detection_methods.explicit_servers
            == original.detection_methods.explicit_servers
        )
        assert restored.exclusions == original.exclusions
        assert len(restored.project_overrides) == len(original.project_overrides)


# =============================================================================
# PinnedConfigManager Tests
# =============================================================================


class TestPinnedConfigManager:
    """Tests for PinnedConfigManager class."""

    def test_load_empty(self, manager: PinnedConfigManager) -> None:
        """Test loading when no config file exists."""
        config = manager.load()

        assert isinstance(config, PinnedConfig)
        assert config.detection_methods.auto_detect_local is True

    def test_save_and_load(self, manager: PinnedConfigManager) -> None:
        """Test saving and loading config."""
        config = PinnedConfig(
            detection_methods=DetectionMethods(
                explicit_servers=["test-server"],
            ),
            exclusions=["excluded"],
        )

        manager.save(config)
        loaded = manager.load()

        assert loaded.detection_methods.explicit_servers == ["test-server"]
        assert loaded.exclusions == ["excluded"]

    def test_config_path(self, manager: PinnedConfigManager) -> None:
        """Test config_path property."""
        path = manager.config_path

        assert path.name == "pinned_servers.json"
        assert "config" in str(path)

    def test_pin_server(self, manager: PinnedConfigManager) -> None:
        """Test pinning a server."""
        entry = manager.pin("my-server", notes="Test notes")

        assert entry.name == "my-server"
        assert entry.notes == "Test notes"

        # Verify it's saved
        config = manager.load()
        assert "my-server" in config.detection_methods.explicit_servers

    def test_pin_server_duplicate(self, manager: PinnedConfigManager) -> None:
        """Test pinning same server twice doesn't duplicate."""
        manager.pin("server-a")
        manager.pin("server-a")

        config = manager.load()
        count = config.detection_methods.explicit_servers.count("server-a")
        assert count == 1

    def test_unpin_server(self, manager: PinnedConfigManager) -> None:
        """Test unpinning a server."""
        manager.pin("to-remove")
        assert manager.is_pinned("to-remove")

        result = manager.unpin("to-remove")

        assert result is True
        assert not manager.is_pinned("to-remove")

    def test_unpin_nonexistent(self, manager: PinnedConfigManager) -> None:
        """Test unpinning non-existent server returns False."""
        result = manager.unpin("does-not-exist")

        assert result is False

    def test_list(self, manager: PinnedConfigManager) -> None:
        """Test listing pinned servers."""
        manager.pin("server-1")
        manager.pin("server-2")

        entries = manager.list()

        assert len(entries) == 2
        names = [e.name for e in entries]
        assert "server-1" in names
        assert "server-2" in names

    def test_get(self, manager: PinnedConfigManager) -> None:
        """Test getting a specific pinned server."""
        manager.pin("get-test")

        entry = manager.get("get-test")

        assert entry is not None
        assert entry.name == "get-test"

    def test_get_nonexistent(self, manager: PinnedConfigManager) -> None:
        """Test getting non-existent server returns None."""
        entry = manager.get("not-there")

        assert entry is None

    def test_is_pinned(self, manager: PinnedConfigManager) -> None:
        """Test is_pinned method."""
        manager.pin("check-this")

        assert manager.is_pinned("check-this") is True
        assert manager.is_pinned("not-pinned") is False

    def test_clear(self, manager: PinnedConfigManager) -> None:
        """Test clearing all pinned servers."""
        manager.pin("a")
        manager.pin("b")
        manager.pin("c")

        count = manager.clear()

        assert count == 3
        assert len(manager.list()) == 0


# =============================================================================
# EffectiveConfig Tests
# =============================================================================


class TestEffectiveConfig:
    """Tests for EffectiveConfig and get_effective_config."""

    def test_get_effective_config_defaults(self, manager: PinnedConfigManager) -> None:
        """Test effective config with default settings."""
        effective = manager.get_effective_config()

        assert effective.auto_detect_local is True
        assert effective.explicit_servers == []
        assert effective.high_usage_threshold == 0.2
        assert effective.exclusions == []

    def test_get_effective_config_with_pinned(self, manager: PinnedConfigManager) -> None:
        """Test effective config includes pinned servers."""
        manager.pin("server-1")
        manager.pin("server-2")

        effective = manager.get_effective_config()

        assert "server-1" in effective.explicit_servers
        assert "server-2" in effective.explicit_servers

    def test_get_effective_config_project_override(
        self, manager: PinnedConfigManager, tmp_path: Path
    ) -> None:
        """Test effective config merges project overrides."""
        # Set up global config with project override
        config = manager.load()
        project_path = str(tmp_path / "my-project")
        config.project_overrides[project_path] = ProjectOverride(
            explicit_servers=["project-server"],
            exclusions=["project-exclude"],
        )
        manager.save(config)

        effective = manager.get_effective_config(Path(project_path))

        assert "project-server" in effective.explicit_servers
        assert "project-exclude" in effective.exclusions

    def test_get_effective_config_merges_global_and_project(
        self, manager: PinnedConfigManager, tmp_path: Path
    ) -> None:
        """Test effective config merges global and project settings."""
        # Global settings
        manager.pin("global-server")
        config = manager.load()
        config.exclusions = ["global-exclude"]

        # Project override
        project_path = str(tmp_path / "proj")
        config.project_overrides[project_path] = ProjectOverride(
            explicit_servers=["proj-server"],
            exclusions=["proj-exclude"],
        )
        manager.save(config)

        effective = manager.get_effective_config(Path(project_path))

        # Should have both global and project servers
        assert "global-server" in effective.explicit_servers
        assert "proj-server" in effective.explicit_servers
        # Should have both exclusions
        assert "global-exclude" in effective.exclusions
        assert "proj-exclude" in effective.exclusions

    def test_effective_config_should_include(self) -> None:
        """Test EffectiveConfig.should_include method."""
        effective = EffectiveConfig(
            auto_detect_local=True,
            explicit_servers=[],
            high_usage_threshold=0.2,
            exclusions=["excluded-server"],
        )

        assert effective.should_include("normal-server") is True
        assert effective.should_include("excluded-server") is False

    def test_load_project_config_json(self, manager: PinnedConfigManager, tmp_path: Path) -> None:
        """Test loading project-level .token-audit.json config."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        project_config = {
            "pinned_servers": {
                "explicit_servers": ["local-server"],
                "exclusions": ["local-exclude"],
            }
        }
        (project_dir / ".token-audit.json").write_text(json.dumps(project_config))

        override = manager.load_project_config(project_dir)

        assert override is not None
        assert "local-server" in override.explicit_servers
        assert "local-exclude" in override.exclusions

    def test_load_project_config_toml(self, manager: PinnedConfigManager, tmp_path: Path) -> None:
        """Test loading project-level .token-audit.toml config."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        toml_content = """
[pinned_servers]
inherit_global = false
explicit_servers = ["toml-server"]
exclusions = ["toml-exclude"]
"""
        (project_dir / ".token-audit.toml").write_text(toml_content)

        override = manager.load_project_config(project_dir)

        assert override is not None
        assert override.inherit_global is False
        assert "toml-server" in override.explicit_servers
        assert "toml-exclude" in override.exclusions

    def test_toml_takes_precedence_over_json(
        self, manager: PinnedConfigManager, tmp_path: Path
    ) -> None:
        """Test that TOML config takes precedence over JSON config."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()

        # Create both TOML and JSON configs
        toml_content = """
[pinned_servers]
explicit_servers = ["toml-wins"]
"""
        (project_dir / ".token-audit.toml").write_text(toml_content)

        json_config = {
            "pinned_servers": {
                "explicit_servers": ["json-loses"],
            }
        }
        (project_dir / ".token-audit.json").write_text(json.dumps(json_config))

        override = manager.load_project_config(project_dir)

        assert override is not None
        assert "toml-wins" in override.explicit_servers
        assert "json-loses" not in override.explicit_servers

    def test_inherit_global_false_replaces_global(
        self, manager: PinnedConfigManager, tmp_path: Path
    ) -> None:
        """Test that inherit_global=false replaces global config entirely."""
        # Set up global config with some servers
        manager.pin("global-server-1")
        manager.pin("global-server-2")
        config = manager.load()
        config.exclusions = ["global-exclude"]
        manager.save(config)

        # Create project with inherit_global = false
        project_dir = tmp_path / "isolated-project"
        project_dir.mkdir()

        toml_content = """
[pinned_servers]
inherit_global = false
explicit_servers = ["project-only-server"]
exclusions = ["project-only-exclude"]
"""
        (project_dir / ".token-audit.toml").write_text(toml_content)

        effective = manager.get_effective_config(project_dir)

        # Should have ONLY project servers, not global
        assert effective.explicit_servers == ["project-only-server"]
        assert effective.exclusions == ["project-only-exclude"]
        # Global servers should NOT be present
        assert "global-server-1" not in effective.explicit_servers
        assert "global-server-2" not in effective.explicit_servers

    def test_inherit_global_true_merges_with_global(
        self, manager: PinnedConfigManager, tmp_path: Path
    ) -> None:
        """Test that inherit_global=true (default) merges with global config."""
        # Set up global config with some servers
        manager.pin("global-server")
        config = manager.load()
        config.exclusions = ["global-exclude"]
        manager.save(config)

        # Create project with inherit_global = true (explicit)
        project_dir = tmp_path / "merged-project"
        project_dir.mkdir()

        toml_content = """
[pinned_servers]
inherit_global = true
explicit_servers = ["project-server"]
exclusions = ["project-exclude"]
"""
        (project_dir / ".token-audit.toml").write_text(toml_content)

        effective = manager.get_effective_config(project_dir)

        # Should have both global and project servers
        assert "global-server" in effective.explicit_servers
        assert "project-server" in effective.explicit_servers
        assert "global-exclude" in effective.exclusions
        assert "project-exclude" in effective.exclusions


# =============================================================================
# Migration Tests
# =============================================================================


class TestMigration:
    """Tests for legacy pin_storage.py migration."""

    def test_migrate_from_legacy(self, tmp_path: Path) -> None:
        """Test migration from legacy pinned.json format."""
        # Set up legacy file
        legacy_dir = tmp_path / ".token-audit"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "pinned.json"
        legacy_data = {
            "version": 1,
            "pinned": [
                {"name": "legacy-server-1", "notes": "Test", "pinned_at": "2025-01-01"},
                {"name": "legacy-server-2", "notes": None, "pinned_at": "2025-01-02"},
            ],
        }
        legacy_file.write_text(json.dumps(legacy_data))

        # Create manager pointing to new config location
        config_dir = tmp_path / ".token-audit" / "config"

        # Patch the legacy file location
        manager = PinnedConfigManager(config_dir=config_dir)
        manager.LEGACY_PIN_FILE = legacy_file

        # Force migration check
        manager._migrated = False
        config = manager.load()

        # Should have migrated servers
        assert "legacy-server-1" in config.detection_methods.explicit_servers
        assert "legacy-server-2" in config.detection_methods.explicit_servers

        # Legacy file should be deleted
        assert not legacy_file.exists()

    def test_no_migration_if_new_config_exists(self, tmp_path: Path) -> None:
        """Test that migration doesn't overwrite existing new config."""
        # Set up legacy file
        legacy_dir = tmp_path / ".token-audit"
        legacy_dir.mkdir()
        legacy_file = legacy_dir / "pinned.json"
        legacy_data = {
            "version": 1,
            "pinned": [{"name": "legacy", "pinned_at": "2025-01-01"}],
        }
        legacy_file.write_text(json.dumps(legacy_data))

        # Create new config first
        config_dir = tmp_path / ".token-audit" / "config"
        config_dir.mkdir(parents=True)
        new_config_file = config_dir / "pinned_servers.json"
        new_config = {
            "version": "1.0.0",
            "detection_methods": {
                "explicit_servers": ["new-server"],
            },
            "exclusions": [],
            "project_overrides": {},
        }
        new_config_file.write_text(json.dumps(new_config))

        # Create manager
        manager = PinnedConfigManager(config_dir=config_dir)
        manager.LEGACY_PIN_FILE = legacy_file
        manager._migrated = False

        config = manager.load()

        # Should have new config, not legacy
        assert "new-server" in config.detection_methods.explicit_servers
        assert "legacy" not in config.detection_methods.explicit_servers


# =============================================================================
# Module-Level Function Tests
# =============================================================================


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_load_pinned_config(self, temp_config_dir: Path) -> None:
        """Test load_pinned_config function."""
        config = load_pinned_config(config_dir=temp_config_dir)

        assert isinstance(config, PinnedConfig)

    def test_save_pinned_config(self, temp_config_dir: Path) -> None:
        """Test save_pinned_config function."""
        config = PinnedConfig(detection_methods=DetectionMethods(explicit_servers=["test"]))

        save_pinned_config(config, config_dir=temp_config_dir)
        loaded = load_pinned_config(config_dir=temp_config_dir)

        assert "test" in loaded.detection_methods.explicit_servers

    def test_get_effective_config_function(self, temp_config_dir: Path) -> None:
        """Test get_effective_config module function."""
        effective = get_effective_config(config_dir=temp_config_dir)

        assert isinstance(effective, EffectiveConfig)


# =============================================================================
# PinnedEntry Tests
# =============================================================================


class TestPinnedEntry:
    """Tests for PinnedEntry dataclass."""

    def test_default_values(self) -> None:
        """Test PinnedEntry has correct defaults."""
        entry = PinnedEntry(name="test")

        assert entry.name == "test"
        assert entry.notes is None
        assert entry.pinned_at == ""

    def test_to_dict(self) -> None:
        """Test PinnedEntry serialization."""
        entry = PinnedEntry(
            name="server",
            notes="My notes",
            pinned_at="2025-01-01T00:00:00",
        )

        data = entry.to_dict()

        assert data["name"] == "server"
        assert data["notes"] == "My notes"
        assert data["pinned_at"] == "2025-01-01T00:00:00"
