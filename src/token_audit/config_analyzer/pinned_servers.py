"""
Pinned server detection (3 methods).

Identifies MCP servers that are "pinned" for focused analysis using:
1. Explicit pinned_servers config key (and user-configured explicit_servers)
2. Custom server paths (non-npm, local development) - toggleable
3. Server usage frequency from historical sessions - configurable threshold

Detection methods can be toggled via ~/.token-audit/config/pinned_servers.json
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from .parsers import MCPConfig, ServerConfig

if TYPE_CHECKING:
    from ..pinned_config import EffectiveConfig

# Detection method source values
SOURCE_AUTO_DETECT_LOCAL = "auto_detect_local"
SOURCE_EXPLICIT = "explicit"
SOURCE_HIGH_USAGE = "high_usage"

# Human-readable reason templates
_REASON_TEMPLATES = {
    "explicit_config": "Explicitly listed in pinned_servers config",
    "explicit_flag": "Server has pinned: true flag",
    "user_explicit": "User-configured in token-audit settings",
    "custom_path": "Custom/local server path detected",
    "usage_frequency": "High usage in recent sessions ({token_share:.1%} of tokens)",
}


@dataclass
class PinnedServer:
    """A pinned MCP server for focused analysis."""

    name: str
    source: str  # "auto_detect_local" | "explicit" | "high_usage"
    reason: str  # Human-readable explanation
    path: Optional[str] = None  # Path if local/custom
    notes: Optional[str] = None  # User-provided notes
    token_share: Optional[float] = None  # For high_usage detection (0.0-1.0)
    _detection_method: Optional[str] = None  # Specific detection method

    @property
    def auto_detected(self) -> bool:
        """Whether this server was auto-detected (backward compatibility)."""
        return self.source in (SOURCE_AUTO_DETECT_LOCAL, SOURCE_HIGH_USAGE)

    @property
    def detection_method(self) -> str:
        """Detection method string (backward compatibility).

        Returns the specific detection method if stored, otherwise derives from source.
        """
        if self._detection_method:
            return self._detection_method
        # Default mapping for backward compatibility
        source_to_method = {
            SOURCE_AUTO_DETECT_LOCAL: "custom_path",
            SOURCE_EXPLICIT: "explicit_config",
            SOURCE_HIGH_USAGE: "usage_frequency",
        }
        return source_to_method.get(self.source, self.source)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "source": self.source,
            "reason": self.reason,
            "path": self.path,
            "notes": self.notes,
            "token_share": self.token_share,
            # Backward compatibility
            "auto_detected": self.auto_detected,
            "detection_method": self.detection_method,
        }


# Common npm package prefixes that indicate non-custom servers
NPM_PREFIXES = (
    "@modelcontextprotocol/",
    "@anthropic/",
    "@google/",
    "@openai/",
    "mcp-server-",
    "npx ",
)


def detect_pinned_servers(
    config: MCPConfig,
    usage_data: Optional[Dict[str, int]] = None,
    effective_config: Optional["EffectiveConfig"] = None,
) -> List[PinnedServer]:
    """Detect pinned servers using 3 toggleable methods.

    Methods (can be individually enabled/disabled via effective_config):
    1. Explicit: Check for pinned_servers config key + user explicit_servers
    2. Custom paths: Detect local/custom server paths (auto_detect_local)
    3. Usage frequency: Use session history with configurable threshold

    Args:
        config: Parsed MCP config
        usage_data: Optional dict of server_name -> call_count from sessions
        effective_config: Optional config to control detection methods and exclusions.
            If not provided, all methods are enabled with default settings.

    Returns:
        List of PinnedServer objects (excluding any in exclusions list)
    """
    pinned: Dict[str, PinnedServer] = {}
    exclusions: Set[str] = set()

    # Extract settings from effective_config if provided
    auto_detect_local = True
    explicit_servers: List[str] = []
    high_usage_threshold = 0.0  # Disabled by default if no config
    min_calls = 10  # Legacy default

    if effective_config:
        auto_detect_local = effective_config.auto_detect_local
        explicit_servers = effective_config.explicit_servers
        high_usage_threshold = effective_config.high_usage_threshold
        exclusions = set(effective_config.exclusions)

        # Convert threshold (0.0-1.0) to min_calls if usage_data provided
        # Threshold of 0.2 means "top 20% of calls"
        if usage_data and high_usage_threshold > 0:
            total_calls = sum(usage_data.values())
            if total_calls > 0:
                # Servers with >= threshold % of total calls are "frequent"
                min_calls = int(total_calls * high_usage_threshold)
                min_calls = max(1, min_calls)  # At least 1 call

    # Method 1: Explicit pinned_servers from MCP config file
    explicit = _detect_explicit_pinned(config)
    for server in explicit:
        if server.name not in exclusions:
            pinned[server.name] = server

    # Method 1b: User-configured explicit_servers from pinned_config
    for server_name in explicit_servers:
        if server_name not in pinned and server_name not in exclusions:
            # Check if server exists in config for path info
            path = None
            if server_name in config.servers:
                path = _extract_server_path(config.servers[server_name])
            pinned[server_name] = PinnedServer(
                name=server_name,
                source=SOURCE_EXPLICIT,
                reason=_REASON_TEMPLATES["user_explicit"],
                path=path,
                _detection_method="user_explicit",
            )

    # Method 2: Custom server paths (toggleable)
    if auto_detect_local:
        custom = _detect_custom_servers(config)
        for server in custom:
            if server.name not in pinned and server.name not in exclusions:
                pinned[server.name] = server

    # Method 3: Usage frequency (if data provided and threshold > 0)
    if usage_data and (effective_config is None or high_usage_threshold > 0):
        frequent = _detect_frequent_servers(usage_data, config, min_calls=min_calls)
        for server in frequent:
            if server.name not in pinned and server.name not in exclusions:
                pinned[server.name] = server

    return list(pinned.values())


def _detect_explicit_pinned(config: MCPConfig) -> List[PinnedServer]:
    """Detect servers explicitly marked as pinned.

    Looks for:
    - pinned_servers key in config root
    - pinned: true flag on individual servers

    Args:
        config: Parsed MCP config

    Returns:
        List of explicitly pinned servers
    """
    pinned: List[PinnedServer] = []

    # Check for pinned_servers array in config root
    pinned_names = config.raw_data.get("pinned_servers", [])
    if isinstance(pinned_names, list):
        for name in pinned_names:
            if isinstance(name, str) and name in config.servers:
                server = config.servers[name]
                pinned.append(
                    PinnedServer(
                        name=name,
                        source=SOURCE_EXPLICIT,
                        reason=_REASON_TEMPLATES["explicit_config"],
                        path=_extract_server_path(server),
                        _detection_method="explicit_config",
                    )
                )

    # Check for pinned flag on individual servers
    for name, server in config.servers.items():
        if server.raw_config.get("pinned", False):
            if not any(p.name == name for p in pinned):
                pinned.append(
                    PinnedServer(
                        name=name,
                        source=SOURCE_EXPLICIT,
                        reason=_REASON_TEMPLATES["explicit_flag"],
                        path=_extract_server_path(server),
                        notes=server.raw_config.get("notes"),
                        _detection_method="explicit_flag",
                    )
                )

    return pinned


def _detect_custom_servers(config: MCPConfig) -> List[PinnedServer]:
    """Detect custom/local servers by path analysis.

    Custom servers are identified by:
    - Local file paths (not npm packages)
    - Commands that aren't npx
    - Paths in home directory or project directories

    Args:
        config: Parsed MCP config

    Returns:
        List of auto-detected custom servers
    """
    custom: List[PinnedServer] = []

    for name, server in config.servers.items():
        if _is_custom_server(server):
            custom.append(
                PinnedServer(
                    name=name,
                    source=SOURCE_AUTO_DETECT_LOCAL,
                    reason=_REASON_TEMPLATES["custom_path"],
                    path=_extract_server_path(server),
                )
            )

    return custom


def _is_custom_server(server: ServerConfig) -> bool:
    """Check if a server is a custom/local development server.

    Args:
        server: Server configuration to check

    Returns:
        True if server appears to be custom/local
    """
    command = server.command.lower()
    args_str = " ".join(server.args).lower()
    full_cmd = f"{command} {args_str}"

    # Check if it's a standard npm package
    for prefix in NPM_PREFIXES:
        if prefix.lower() in full_cmd:
            return False

    # Check for local path indicators
    local_indicators = [
        "/home/",
        "/Users/",
        "~/",
        "./",
        "../",
        ".ts",
        ".js",
        "localhost",
        "127.0.0.1",
    ]

    for indicator in local_indicators:
        if indicator in full_cmd:
            return True

    # Check if command is python/node running a local file
    if command in ("python", "python3", "node", "ts-node"):
        # If first arg looks like a local path
        if server.args and ("/" in server.args[0] or "\\" in server.args[0]):
            return True

    return False


def _detect_frequent_servers(
    usage_data: Dict[str, int],
    config: MCPConfig,
    min_calls: int = 10,
) -> List[PinnedServer]:
    """Detect frequently used servers from session history.

    Args:
        usage_data: Dict mapping server names to call counts
        config: MCP config for path information
        min_calls: Minimum calls to be considered frequent

    Returns:
        List of frequently used servers
    """
    frequent: List[PinnedServer] = []

    # Calculate total for token_share
    total_calls = sum(usage_data.values())
    if total_calls == 0:
        return frequent

    # Sort by usage descending
    sorted_usage = sorted(usage_data.items(), key=lambda x: x[1], reverse=True)

    for name, calls in sorted_usage:
        if calls < min_calls:
            break

        path = None
        if name in config.servers:
            path = _extract_server_path(config.servers[name])

        # Calculate token share as fraction of total calls
        token_share = calls / total_calls

        frequent.append(
            PinnedServer(
                name=name,
                source=SOURCE_HIGH_USAGE,
                reason=_REASON_TEMPLATES["usage_frequency"].format(token_share=token_share),
                path=path,
                notes=f"Called {calls} times in recent sessions",
                token_share=token_share,
            )
        )

    return frequent


def _extract_server_path(server: ServerConfig) -> Optional[str]:
    """Extract the primary path from a server config.

    Args:
        server: Server configuration

    Returns:
        Server path if found, None otherwise
    """
    # Check if command is a path
    cmd = server.command
    if "/" in cmd or "\\" in cmd:
        return cmd

    # Check first arg for path
    if server.args:
        first_arg = server.args[0]
        if "/" in first_arg or "\\" in first_arg:
            return first_arg

    return None


class PinnedServerDetector:
    """Detector for pinned MCP servers using 3 configurable methods.

    Supports detection via:
    1. Explicit config (pinned_servers key, pinned: true flag, user explicit_servers)
    2. Auto-detect local paths (custom servers with local file paths)
    3. High-usage detection (from session data or historical aggregation)

    Usage:
        detector = PinnedServerDetector()
        servers = detector.detect(mcp_config, platform="claude-code")
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """Initialize detector with optional storage base directory.

        Args:
            base_dir: Base directory for session storage (for historical aggregation).
                     Defaults to ~/.token-audit/sessions/
        """
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        """Get the session storage base directory."""
        if self._base_dir is None:
            # Lazy import to avoid circular dependency
            from ..storage import get_default_base_dir

            self._base_dir = get_default_base_dir()
        return self._base_dir

    def detect(
        self,
        config: MCPConfig,
        effective_config: Optional["EffectiveConfig"] = None,
        usage_data: Optional[Dict[str, int]] = None,
        platform: Optional[str] = None,
        days: int = 30,
    ) -> List[PinnedServer]:
        """Detect pinned servers using all enabled methods.

        Args:
            config: Parsed MCP config
            effective_config: Configuration controlling detection methods.
                If None, uses default settings (all methods enabled).
            usage_data: Optional pre-computed server -> call_count mapping.
                If None and high_usage detection enabled, loads from storage.
            platform: Platform name for historical aggregation (e.g., "claude-code").
                Required if usage_data is None and high_usage is enabled.
            days: Number of days of history for aggregation (default: 30)

        Returns:
            List of PinnedServer objects, excluding any in exclusions list
        """
        pinned: Dict[str, PinnedServer] = {}
        exclusions: Set[str] = set()

        # Extract settings from effective_config
        auto_detect_local = True
        explicit_servers: List[str] = []
        high_usage_threshold = 0.0

        if effective_config:
            auto_detect_local = effective_config.auto_detect_local
            explicit_servers = effective_config.explicit_servers
            high_usage_threshold = effective_config.high_usage_threshold
            exclusions = set(effective_config.exclusions)

        # Method 1: Explicit pinned servers
        for server in self._detect_explicit(config, explicit_servers):
            if server.name not in exclusions:
                pinned[server.name] = server

        # Method 2: Auto-detect local paths
        if auto_detect_local:
            for server in self._detect_auto_local(config):
                if server.name not in pinned and server.name not in exclusions:
                    pinned[server.name] = server

        # Method 3: High-usage detection
        if high_usage_threshold > 0:
            # Load historical usage if not provided
            if usage_data is None and platform:
                usage_data = self._load_historical_usage(platform, days)

            if usage_data:
                for server in self._detect_high_usage(config, usage_data, high_usage_threshold):
                    if server.name not in pinned and server.name not in exclusions:
                        pinned[server.name] = server

        return list(pinned.values())

    def _detect_explicit(
        self,
        config: MCPConfig,
        explicit_servers: Optional[List[str]] = None,
    ) -> List[PinnedServer]:
        """Detect explicitly pinned servers.

        Checks:
        - pinned_servers key in config root
        - pinned: true flag on individual servers
        - User-configured explicit_servers list

        Args:
            config: Parsed MCP config
            explicit_servers: User-configured server names to pin

        Returns:
            List of explicitly pinned servers
        """
        servers: List[PinnedServer] = []
        seen: Set[str] = set()

        # Check for pinned_servers array in config root
        pinned_names = config.raw_data.get("pinned_servers", [])
        if isinstance(pinned_names, list):
            for name in pinned_names:
                if isinstance(name, str) and name in config.servers:
                    server_config = config.servers[name]
                    servers.append(
                        PinnedServer(
                            name=name,
                            source=SOURCE_EXPLICIT,
                            reason=_REASON_TEMPLATES["explicit_config"],
                            path=_extract_server_path(server_config),
                            _detection_method="explicit_config",
                        )
                    )
                    seen.add(name)

        # Check for pinned flag on individual servers
        for name, server_config in config.servers.items():
            if name not in seen and server_config.raw_config.get("pinned", False):
                servers.append(
                    PinnedServer(
                        name=name,
                        source=SOURCE_EXPLICIT,
                        reason=_REASON_TEMPLATES["explicit_flag"],
                        path=_extract_server_path(server_config),
                        notes=server_config.raw_config.get("notes"),
                        _detection_method="explicit_flag",
                    )
                )
                seen.add(name)

        # Add user-configured explicit servers
        if explicit_servers:
            for name in explicit_servers:
                if name not in seen:
                    path = None
                    if name in config.servers:
                        path = _extract_server_path(config.servers[name])
                    servers.append(
                        PinnedServer(
                            name=name,
                            source=SOURCE_EXPLICIT,
                            reason=_REASON_TEMPLATES["user_explicit"],
                            path=path,
                            _detection_method="user_explicit",
                        )
                    )
                    seen.add(name)

        return servers

    def _detect_auto_local(self, config: MCPConfig) -> List[PinnedServer]:
        """Detect custom/local servers by path analysis.

        Identifies servers with:
        - Local file paths (not npm packages)
        - Commands that aren't npx
        - Paths in home directory or project directories

        Args:
            config: Parsed MCP config

        Returns:
            List of auto-detected custom servers
        """
        servers: List[PinnedServer] = []

        for name, server_config in config.servers.items():
            if _is_custom_server(server_config):
                servers.append(
                    PinnedServer(
                        name=name,
                        source=SOURCE_AUTO_DETECT_LOCAL,
                        reason=_REASON_TEMPLATES["custom_path"],
                        path=_extract_server_path(server_config),
                    )
                )

        return servers

    def _detect_high_usage(
        self,
        config: MCPConfig,
        usage_data: Dict[str, int],
        threshold: float,
    ) -> List[PinnedServer]:
        """Detect high-usage servers from call frequency.

        Args:
            config: Parsed MCP config (for path extraction)
            usage_data: Dict mapping server names to call counts
            threshold: Minimum token share to be considered high-usage (0.0-1.0)

        Returns:
            List of high-usage servers
        """
        servers: List[PinnedServer] = []

        total_calls = sum(usage_data.values())
        if total_calls == 0:
            return servers

        # Sort by usage descending
        sorted_usage = sorted(usage_data.items(), key=lambda x: x[1], reverse=True)

        for name, calls in sorted_usage:
            token_share = calls / total_calls

            # Only include servers above threshold
            if token_share < threshold:
                continue

            path = None
            if name in config.servers:
                path = _extract_server_path(config.servers[name])

            servers.append(
                PinnedServer(
                    name=name,
                    source=SOURCE_HIGH_USAGE,
                    reason=_REASON_TEMPLATES["usage_frequency"].format(token_share=token_share),
                    path=path,
                    notes=f"Called {calls} times in recent sessions",
                    token_share=token_share,
                )
            )

        return servers

    def _load_historical_usage(
        self,
        platform: str,
        days: int = 30,
    ) -> Dict[str, int]:
        """Load aggregated server usage from session storage.

        Args:
            platform: Platform name (e.g., "claude-code", "codex-cli")
            days: Number of days of history to aggregate

        Returns:
            Dict mapping server names to total call counts
        """
        usage: Dict[str, int] = {}

        try:
            # Lazy import to avoid circular dependency
            from ..session_manager import SessionManager

            manager = SessionManager(base_dir=self.base_dir)
            cutoff = date.today() - timedelta(days=days)

            # Load sessions from storage (returns list of Path objects)
            session_paths = manager.list_sessions()

            # Aggregate MCP tool calls per server
            for session_path in session_paths:
                session = manager.load_session(session_path)
                if session and hasattr(session, "mcp_calls"):
                    # Filter by platform and date if session has metadata
                    session_platform = getattr(session, "platform", None)
                    session_start = getattr(session, "start_time", None)

                    # Skip if wrong platform
                    if session_platform and session_platform != platform:
                        continue

                    # Skip if too old (if we can determine the date)
                    if session_start:
                        try:
                            session_date = (
                                session_start.date()
                                if hasattr(session_start, "date")
                                else session_start
                            )
                            if session_date < cutoff:
                                continue
                        except (AttributeError, TypeError):
                            pass

                    for call in session.mcp_calls:
                        server = getattr(call, "server", None)
                        if server:
                            usage[server] = usage.get(server, 0) + 1

        except (ImportError, OSError, AttributeError):
            # If session loading fails, return empty usage
            pass

        return usage
