"""
MCP Audit - Multi-platform MCP usage tracking and cost analysis.

Track token usage, costs, and efficiency across AI coding sessions
for Claude Code, Codex CLI, and other MCP-enabled tools.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-audit")
except PackageNotFoundError:
    # Fallback for editable/dev installs where package isn't installed
    __version__ = "0.0.0.dev0"

__author__ = "Little Bear Apps"
__email__ = "help@littlebearapps.com"

# Lazy imports to avoid circular dependencies
# Users can import directly: from mcp_audit import BaseTracker


from typing import Any


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
        "estimate_tool_tokens",
        "get_estimator_for_platform",
        "FUNCTION_CALL_OVERHEAD",
    ):
        from .token_estimator import (  # noqa: F401
            FUNCTION_CALL_OVERHEAD,
            TokenEstimator,
            count_tokens,
            estimate_tool_tokens,
            get_estimator_for_platform,
        )

        return locals()[name]

    # Display module
    if name in ("DisplayAdapter", "DisplaySnapshot", "create_display", "DisplayMode"):
        from .display import (  # noqa: F401
            DisplayAdapter,
            DisplayMode,
            DisplaySnapshot,
            create_display,
        )

        return locals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__email__",
    # Core classes
    "BaseTracker",
    "Session",
    "ServerSession",
    "Call",
    "ToolStats",
    "TokenUsage",
    "MCPToolCalls",
    # Normalization
    "normalize_tool_name",
    "normalize_server_name",
    "extract_server_and_tool",
    # Pricing
    "PricingConfig",
    "load_pricing_config",
    "get_model_cost",
    # Storage
    "StorageManager",
    "SessionIndex",
    # Smell aggregation
    "SmellAggregator",
    "AggregatedSmell",
    "SmellAggregationResult",
    # Platform adapters
    "ClaudeCodeAdapter",
    "CodexCLIAdapter",
    "GeminiCLIAdapter",
    # Token estimation
    "TokenEstimator",
    "count_tokens",
    "estimate_tool_tokens",
    "get_estimator_for_platform",
    "FUNCTION_CALL_OVERHEAD",
    # Display
    "DisplayAdapter",
    "DisplaySnapshot",
    "create_display",
    "DisplayMode",
]
