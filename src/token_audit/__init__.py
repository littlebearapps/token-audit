"""
Token Audit - Multi-platform MCP usage tracking and cost analysis.

Track token usage, costs, and efficiency across AI coding sessions
for Claude Code, Codex CLI, and other MCP-enabled tools.
"""

import warnings
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

try:
    __version__ = version("token-audit")
except PackageNotFoundError:
    # Fallback for editable/dev installs where package isn't installed
    __version__ = "0.0.0.dev0"

__author__ = "Little Bear Apps"
__email__ = "help@littlebearapps.com"

# API Stability Classification
# See docs/API-STABILITY.md for full policy
StabilityTier = Literal["stable", "evolving", "deprecated", "unknown"]

API_STABILITY: dict[str, StabilityTier] = {
    # === STABLE (v1.0.0+ guaranteed) ===
    "StorageManager": "stable",
    "SessionIndex": "stable",
    "PricingConfig": "stable",
    "load_pricing_config": "stable",
    "get_model_cost": "stable",
    "normalize_tool_name": "stable",
    "normalize_server_name": "stable",
    "extract_server_and_tool": "stable",
    "TokenEstimator": "stable",
    "count_tokens": "stable",
    "get_estimator_for_platform": "stable",
    "FUNCTION_CALL_OVERHEAD": "stable",
    "DisplayAdapter": "stable",
    "DisplaySnapshot": "stable",
    "create_display": "stable",
    "DisplayMode": "stable",
    # === EVOLVING (interface stable, implementation may change) ===
    "BaseTracker": "evolving",
    "Session": "evolving",
    "ServerSession": "evolving",
    "Call": "evolving",
    "ToolStats": "evolving",
    "TokenUsage": "evolving",
    "MCPToolCalls": "evolving",
    "ClaudeCodeAdapter": "evolving",
    "CodexCLIAdapter": "evolving",
    "GeminiCLIAdapter": "evolving",
    "SmellAggregator": "evolving",
    "AggregatedSmell": "evolving",
    "SmellAggregationResult": "evolving",
    # === EVOLVING (bucket and task classification - v1.0.4) ===
    "BucketClassifier": "evolving",
    "BucketResult": "evolving",
    "BucketName": "evolving",
    "BucketThresholds": "evolving",
    "TaskMarker": "evolving",
    "TaskSummary": "evolving",
    "TaskManager": "evolving",
    # === EVOLVING (server mode - requires [server] extra) ===
    "create_server": "evolving",
    "get_server": "evolving",
    "run_server": "evolving",
    # === DEPRECATED (remove in v1.0.5) ===
    "estimate_tool_tokens": "deprecated",
}


def get_api_stability(name: str) -> StabilityTier:
    """Get the stability tier of a public API export.

    Args:
        name: The name of the API export to check.

    Returns:
        One of: "stable", "evolving", "deprecated", or "unknown".

    Example:
        >>> from token_audit import get_api_stability
        >>> get_api_stability("StorageManager")
        'stable'
        >>> get_api_stability("estimate_tool_tokens")
        'deprecated'
    """
    return API_STABILITY.get(name, "unknown")


# Lazy imports to avoid circular dependencies
# Users can import directly: from token_audit import BaseTracker


def __getattr__(name: str) -> Any:
    """Lazy import handler for package attributes."""
    if name in (
        "BaseTracker",
        "Session",
        "ServerSession",
        "Call",
        "ToolStats",
        "TokenUsage",
        "MCPToolCalls",
    ):
        from .base_tracker import (  # noqa: F401
            BaseTracker,
            Call,
            MCPToolCalls,
            ServerSession,
            Session,
            TokenUsage,
            ToolStats,
        )

        return locals()[name]

    if name in ("normalize_tool_name", "normalize_server_name", "extract_server_and_tool"):
        from .normalization import (  # noqa: F401
            extract_server_and_tool,
            normalize_server_name,
            normalize_tool_name,
        )

        return locals()[name]

    if name in ("PricingConfig", "load_pricing_config", "get_model_cost"):
        from .pricing_config import (  # noqa: F401
            PricingConfig,
            get_model_cost,
            load_pricing_config,
        )

        return locals()[name]

    if name in ("StorageManager", "SessionIndex"):
        from .storage import SessionIndex, StorageManager  # noqa: F401

        return locals()[name]

    if name in ("SmellAggregator", "AggregatedSmell", "SmellAggregationResult"):
        from .smell_aggregator import (  # noqa: F401
            AggregatedSmell,
            SmellAggregationResult,
            SmellAggregator,
        )

        return locals()[name]

    # Bucket classification (v1.0.4)
    if name in ("BucketClassifier", "BucketResult", "BucketName", "BucketThresholds"):
        from .buckets import (  # noqa: F401
            BucketClassifier,
            BucketName,
            BucketResult,
            BucketThresholds,
        )

        return locals()[name]

    # Task management (v1.0.4)
    if name in ("TaskMarker", "TaskSummary", "TaskManager"):
        from .tasks import TaskManager, TaskMarker, TaskSummary  # noqa: F401

        return locals()[name]

    if name in ("ClaudeCodeAdapter",):
        from .claude_code_adapter import ClaudeCodeAdapter

        return ClaudeCodeAdapter

    if name in ("CodexCLIAdapter",):
        from .codex_cli_adapter import CodexCLIAdapter

        return CodexCLIAdapter

    if name in ("GeminiCLIAdapter",):
        from .gemini_cli_adapter import GeminiCLIAdapter

        return GeminiCLIAdapter

    # Token estimation
    if name in (
        "TokenEstimator",
        "count_tokens",
        "get_estimator_for_platform",
        "FUNCTION_CALL_OVERHEAD",
    ):
        from .token_estimator import (  # noqa: F401
            FUNCTION_CALL_OVERHEAD,
            TokenEstimator,
            count_tokens,
            get_estimator_for_platform,
        )

        return locals()[name]

    # Deprecated: estimate_tool_tokens (use TokenEstimator.estimate_tool_call instead)
    if name == "estimate_tool_tokens":
        warnings.warn(
            "estimate_tool_tokens is deprecated and will be removed in v1.0.5."
            "Use TokenEstimator.estimate_tool_call() instead. "
            "See docs/API-STABILITY.md for migration guide.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .token_estimator import estimate_tool_tokens

        return estimate_tool_tokens

    # Display module
    if name in ("DisplayAdapter", "DisplaySnapshot", "create_display", "DisplayMode"):
        from .display import (  # noqa: F401
            DisplayAdapter,
            DisplayMode,
            DisplaySnapshot,
            create_display,
        )

        return locals()[name]

    # Server module (requires [server] optional dependency)
    if name in ("create_server", "get_server", "run_server"):
        try:
            from .server import create_server, get_server, run_server  # noqa: F401

            return locals()[name]
        except ImportError as e:
            raise ImportError(
                "Server mode requires the [server] optional dependency. "
                "Install with: pip install token-audit[server]"
            ) from e

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # === Package Metadata ===
    "__version__",
    "__author__",
    "__email__",
    # === API Stability (v0.9.0+) ===
    "API_STABILITY",
    "StabilityTier",
    "get_api_stability",
    # === STABLE APIs (v1.0.0+ guaranteed) ===
    # Storage
    "StorageManager",
    "SessionIndex",
    # Pricing
    "PricingConfig",
    "load_pricing_config",
    "get_model_cost",
    # Normalization
    "normalize_tool_name",
    "normalize_server_name",
    "extract_server_and_tool",
    # Token estimation
    "TokenEstimator",
    "count_tokens",
    "get_estimator_for_platform",
    "FUNCTION_CALL_OVERHEAD",
    # Display
    "DisplayAdapter",
    "DisplaySnapshot",
    "create_display",
    "DisplayMode",
    # === EVOLVING APIs (interface stable, implementation may change) ===
    # Core data classes
    "BaseTracker",
    "Session",
    "ServerSession",
    "Call",
    "ToolStats",
    "TokenUsage",
    "MCPToolCalls",
    # Platform adapters
    "ClaudeCodeAdapter",
    "CodexCLIAdapter",
    "GeminiCLIAdapter",
    # Smell aggregation
    "SmellAggregator",
    "AggregatedSmell",
    "SmellAggregationResult",
    # Bucket classification (v1.0.4)
    "BucketClassifier",
    "BucketResult",
    "BucketName",
    "BucketThresholds",
    # Task management (v1.0.4)
    "TaskMarker",
    "TaskSummary",
    "TaskManager",
    # === EVOLVING APIs (server mode - requires [server] extra) ===
    "create_server",
    "get_server",
    "run_server",
    # === DEPRECATED (remove in v1.0.5) ===
    "estimate_tool_tokens",  # Use TokenEstimator.estimate_tool_call()
]
