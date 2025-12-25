"""
Pinned servers configuration with toggleable detection methods.

Stores user configuration for pinned server detection in:
- Global: ~/.token-audit/config/pinned_servers.json
- Project: .token-audit.json (in project root)

Provides 3 detection methods that can be individually enabled/disabled:
1. auto_detect_local: Detect servers with local paths
2. explicit_servers: User-specified server names
3. high_usage_threshold: Servers above usage threshold
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import tomllib


@dataclass
class DetectionMethods:
    """Configuration for pinned server detection methods."""

    # Auto-detect servers with local file paths
    auto_detect_local: bool = True

    # Explicitly listed server names (user-maintained)
    explicit_servers: List[str] = field(default_factory=list)

    # Usage threshold for automatic pinning (0.0-1.0, percentage of session tokens)
    # Servers consuming more than this threshold are considered "pinned"
    # Set to 0 to disable usage-based detection
    high_usage_threshold: float = 0.2

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "auto_detect_local": self.auto_detect_local,
            "explicit_servers": self.explicit_servers,
            "high_usage_threshold": self.high_usage_threshold,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectionMethods":
        """Create from dictionary."""
        return cls(
            auto_detect_local=data.get("auto_detect_local", True),
            explicit_servers=data.get("explicit_servers", []),
            high_usage_threshold=data.get("high_usage_threshold", 0.2),
        )


@dataclass
class ProjectOverride:
    """Project-specific configuration override.

    Attributes:
        inherit_global: If True (default), merge with global config.
            If False, project config completely replaces global.
        explicit_servers: Project-specific pinned servers.
        exclusions: Project-specific exclusions.
    """

    inherit_global: bool = True
    explicit_servers: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "inherit_global": self.inherit_global,
            "explicit_servers": self.explicit_servers,
            "exclusions": self.exclusions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectOverride":
        """Create from dictionary."""
        return cls(
            inherit_global=data.get("inherit_global", True),
            explicit_servers=data.get("explicit_servers", []),
            exclusions=data.get("exclusions", []),
        )


@dataclass
class PinnedConfig:
    """
    Complete pinned servers configuration.

    Storage location: ~/.token-audit/config/pinned_servers.json

    This replaces the simpler pin_storage.py with a more powerful
    configuration that supports:
    - Toggleable detection methods
    - Global exclusions
    - Per-project overrides
    """

    version: str = "1.0.0"
    detection_methods: DetectionMethods = field(default_factory=DetectionMethods)
    exclusions: List[str] = field(default_factory=list)
    project_overrides: Dict[str, ProjectOverride] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "detection_methods": self.detection_methods.to_dict(),
            "exclusions": self.exclusions,
            "project_overrides": {
                path: override.to_dict() for path, override in self.project_overrides.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PinnedConfig":
        """Create from dictionary."""
        overrides = {}
        for path, override_data in data.get("project_overrides", {}).items():
            overrides[path] = ProjectOverride.from_dict(override_data)

        return cls(
            version=data.get("version", "1.0.0"),
            detection_methods=DetectionMethods.from_dict(data.get("detection_methods", {})),
            exclusions=data.get("exclusions", []),
            project_overrides=overrides,
        )


class PinnedConfigManager:
    """
    Manager for pinned server configuration.

    Handles loading, saving, and merging of global and project-level configs.
    Thread-safe for concurrent access.

    Usage:
        manager = PinnedConfigManager()
        config = manager.load()
        effective = manager.get_effective_config("/path/to/project")

        # Pin a server
        manager.pin("my-server", notes="My custom server")

        # Unpin a server
        manager.unpin("my-server")
    """

    # Config file locations
    GLOBAL_CONFIG_DIR = Path.home() / ".token-audit" / "config"
    GLOBAL_CONFIG_FILE = "pinned_servers.json"
    PROJECT_CONFIG_FILE_TOML = ".token-audit.toml"  # Preferred format
    PROJECT_CONFIG_FILE_JSON = ".token-audit.json"  # Fallback for backward compat

    # Legacy config for migration
    LEGACY_PIN_FILE = Path.home() / ".token-audit" / "pinned.json"

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        """
        Initialize config manager.

        Args:
            config_dir: Custom config directory (default: ~/.token-audit/config)
        """
        self._config_dir = config_dir or self.GLOBAL_CONFIG_DIR
        self._config_path = self._config_dir / self.GLOBAL_CONFIG_FILE
        self._lock = threading.RLock()  # RLock for reentrant locking (migration calls save)
        self._migrated = False

    @property
    def config_path(self) -> Path:
        """Get the global config file path."""
        return self._config_path

    def _ensure_dir(self) -> None:
        """Ensure the config directory exists."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

    def _migrate_from_legacy(self) -> bool:
        """
        Migrate from legacy pin_storage.py format if needed.

        Reads ~/.token-audit/pinned.json and migrates entries to
        detection_methods.explicit_servers in the new format.

        Returns:
            True if migration was performed, False otherwise
        """
        if self._migrated:
            return False

        self._migrated = True

        # Check for legacy file
        legacy_path = self.LEGACY_PIN_FILE
        if not legacy_path.exists():
            return False

        # Already have new config? Don't migrate
        if self._config_path.exists():
            return False

        try:
            with open(legacy_path) as f:
                legacy_data = json.load(f)

            # Extract pinned server names from legacy format
            pinned_list = legacy_data.get("pinned", [])
            server_names = []
            for entry in pinned_list:
                if isinstance(entry, dict) and "name" in entry:
                    server_names.append(entry["name"])

            if server_names:
                # Create new config with migrated servers
                config = PinnedConfig(
                    detection_methods=DetectionMethods(
                        explicit_servers=server_names,
                    )
                )
                self.save(config)

                # Remove legacy file after successful migration
                legacy_path.unlink()
                return True

        except (json.JSONDecodeError, OSError, KeyError):
            # Migration failed, continue with empty config
            pass

        return False

    def load(self) -> PinnedConfig:
        """
        Load pinned config from file.

        Performs legacy migration on first load if needed.

        Returns:
            PinnedConfig instance
        """
        with self._lock:
            # Attempt migration from legacy format
            self._migrate_from_legacy()

            if not self._config_path.exists():
                return PinnedConfig()

            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                return PinnedConfig.from_dict(data)
            except (json.JSONDecodeError, OSError):
                return PinnedConfig()

    def save(self, config: PinnedConfig) -> None:
        """
        Save pinned config to file.

        Args:
            config: Configuration to save
        """
        with self._lock:
            self._ensure_dir()
            with open(self._config_path, "w") as f:
                json.dump(config.to_dict(), f, indent=2)

    def load_project_config(self, project_path: Path) -> Optional[ProjectOverride]:
        """
        Load project-specific config from .token-audit.toml or .token-audit.json.

        Checks for TOML first (preferred), then falls back to JSON for
        backward compatibility.

        Args:
            project_path: Path to project directory

        Returns:
            ProjectOverride if config exists, None otherwise
        """
        # Try TOML first (preferred format)
        toml_path = project_path / self.PROJECT_CONFIG_FILE_TOML
        if toml_path.exists():
            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)

                # Look for pinned_servers section
                pinned_data = data.get("pinned_servers", {})
                if pinned_data:
                    return ProjectOverride.from_dict(pinned_data)
            except (tomllib.TOMLDecodeError, OSError):
                pass

        # Fall back to JSON for backward compatibility
        json_path = project_path / self.PROJECT_CONFIG_FILE_JSON
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)

                # Look for pinned_servers section
                pinned_data = data.get("pinned_servers", {})
                if pinned_data:
                    return ProjectOverride.from_dict(pinned_data)
            except (json.JSONDecodeError, OSError):
                pass

        return None

    def get_effective_config(self, project_path: Optional[Path] = None) -> "EffectiveConfig":
        """
        Get effective configuration with project overrides applied.

        By default, merges global config with project-specific overrides:
        - explicit_servers: Union of global + project
        - exclusions: Union of global + project

        If project config sets `inherit_global = false`, project settings
        completely replace global settings (no merge).

        Args:
            project_path: Optional project directory for overrides

        Returns:
            EffectiveConfig with merged settings
        """
        config = self.load()

        # Check for local project config file (.token-audit.toml or .token-audit.json)
        local_override = None
        if project_path:
            local_override = self.load_project_config(project_path)

        # If project says don't inherit, use only project settings
        if local_override and not local_override.inherit_global:
            return EffectiveConfig(
                auto_detect_local=config.detection_methods.auto_detect_local,
                explicit_servers=sorted(local_override.explicit_servers),
                high_usage_threshold=config.detection_methods.high_usage_threshold,
                exclusions=sorted(local_override.exclusions),
            )

        # Otherwise, merge global + project (default behavior)
        explicit_servers: Set[str] = set(config.detection_methods.explicit_servers)
        exclusions: Set[str] = set(config.exclusions)

        # Apply project override from global config
        if project_path:
            project_str = str(project_path)
            if project_str in config.project_overrides:
                override = config.project_overrides[project_str]
                explicit_servers.update(override.explicit_servers)
                exclusions.update(override.exclusions)

        # Apply local project config (already loaded above)
        if local_override:
            explicit_servers.update(local_override.explicit_servers)
            exclusions.update(local_override.exclusions)

        return EffectiveConfig(
            auto_detect_local=config.detection_methods.auto_detect_local,
            explicit_servers=sorted(explicit_servers),
            high_usage_threshold=config.detection_methods.high_usage_threshold,
            exclusions=sorted(exclusions),
        )

    # ==========================================================================
    # Convenience methods for CLI compatibility
    # ==========================================================================

    def pin(self, server_name: str, notes: Optional[str] = None) -> "PinnedEntry":
        """
        Pin a server (add to explicit_servers).

        Args:
            server_name: Server name to pin
            notes: Optional notes (stored in a separate metadata section)

        Returns:
            PinnedEntry with server info
        """
        config = self.load()

        # Add to explicit_servers if not already there
        if server_name not in config.detection_methods.explicit_servers:
            config.detection_methods.explicit_servers.append(server_name)
            config.detection_methods.explicit_servers.sort()
            self.save(config)

        return PinnedEntry(
            name=server_name,
            notes=notes,
            pinned_at=datetime.now().isoformat(),
        )

    def unpin(self, server_name: str) -> bool:
        """
        Unpin a server (remove from explicit_servers).

        Args:
            server_name: Server name to unpin

        Returns:
            True if server was unpinned, False if not found
        """
        config = self.load()

        if server_name in config.detection_methods.explicit_servers:
            config.detection_methods.explicit_servers.remove(server_name)
            self.save(config)
            return True

        return False

    def list(self) -> List["PinnedEntry"]:
        """
        List all explicitly pinned servers.

        Returns:
            List of PinnedEntry objects
        """
        config = self.load()
        return [
            PinnedEntry(name=name, notes=None, pinned_at="")
            for name in config.detection_methods.explicit_servers
        ]

    def get(self, server_name: str) -> Optional["PinnedEntry"]:
        """
        Get a specific pinned server.

        Args:
            server_name: Server name to look up

        Returns:
            PinnedEntry if pinned, None otherwise
        """
        config = self.load()
        if server_name in config.detection_methods.explicit_servers:
            return PinnedEntry(name=server_name, notes=None, pinned_at="")
        return None

    def is_pinned(self, server_name: str) -> bool:
        """
        Check if a server is explicitly pinned.

        Args:
            server_name: Server name to check

        Returns:
            True if pinned, False otherwise
        """
        return self.get(server_name) is not None

    def clear(self) -> int:
        """
        Clear all explicitly pinned servers.

        Returns:
            Number of servers that were cleared
        """
        config = self.load()
        count = len(config.detection_methods.explicit_servers)
        config.detection_methods.explicit_servers = []
        self.save(config)
        return count


@dataclass
class EffectiveConfig:
    """Effective configuration after merging global and project overrides."""

    auto_detect_local: bool
    explicit_servers: List[str]
    high_usage_threshold: float
    exclusions: List[str]

    def should_include(self, server_name: str) -> bool:
        """
        Check if a server should be included in pinned detection.

        Args:
            server_name: Server name to check

        Returns:
            True if server should be included, False if excluded
        """
        return server_name not in self.exclusions


@dataclass
class PinnedEntry:
    """A pinned server entry (for CLI compatibility)."""

    name: str
    notes: Optional[str] = None
    pinned_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "notes": self.notes,
            "pinned_at": self.pinned_at,
        }


# Module-level convenience functions


def load_pinned_config(config_dir: Optional[Path] = None) -> PinnedConfig:
    """
    Load pinned configuration.

    Args:
        config_dir: Custom config directory

    Returns:
        PinnedConfig instance
    """
    manager = PinnedConfigManager(config_dir)
    return manager.load()


def save_pinned_config(config: PinnedConfig, config_dir: Optional[Path] = None) -> None:
    """
    Save pinned configuration.

    Args:
        config: Configuration to save
        config_dir: Custom config directory
    """
    manager = PinnedConfigManager(config_dir)
    manager.save(config)


def get_effective_config(
    project_path: Optional[Path] = None,
    config_dir: Optional[Path] = None,
) -> EffectiveConfig:
    """
    Get effective configuration with project overrides applied.

    Args:
        project_path: Optional project directory for overrides
        config_dir: Custom config directory

    Returns:
        EffectiveConfig with merged settings
    """
    manager = PinnedConfigManager(config_dir)
    return manager.get_effective_config(project_path)
