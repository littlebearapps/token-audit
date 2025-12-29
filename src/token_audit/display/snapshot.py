"""
DisplaySnapshot - Immutable snapshot of session state for display.

This dataclass captures all the information needed to render a display,
allowing the display layer to be completely decoupled from tracking logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class DisplaySnapshot:
    """Immutable snapshot of session state for display rendering."""

    # Session metadata
    project: str
    platform: str
    start_time: datetime
    duration_seconds: float

    # Token metrics
    input_tokens: int
    output_tokens: int
    cache_tokens: int  # cache_read + cache_created
    total_tokens: int
    cache_efficiency: float  # 0.0 to 1.0
    cost_estimate: float

    # Tool metrics
    total_tool_calls: int
    unique_tools: int

    # Fields with defaults must come after fields without defaults
    top_tools: Tuple[Tuple[str, int, int, int], ...] = field(default_factory=tuple)
    # Each tuple is (name, calls, tokens, avg_per_call)

    # Recent activity (newest first)
    recent_events: Tuple[Tuple[datetime, str, int], ...] = field(default_factory=tuple)
    # Each tuple is (timestamp, tool_name, tokens)

    # token-audit version that tracked this session
    version: str = ""

    # Model tracking (v1.0.4 enhancement)
    model_id: str = ""  # Raw model ID (e.g., "claude-opus-4-5-20251101")
    model_name: str = ""  # Human-readable name (e.g., "Claude Opus 4.5")

    # Enhanced cost tracking (v1.0.4 enhancement)
    cost_no_cache: float = 0.0  # Cost if no cache was used
    cache_savings: float = 0.0  # USD saved by caching
    savings_percent: float = 0.0  # Percentage saved (0.0 to 100.0)

    # MCP Server hierarchy (v1.0.4 enhancement)
    # Dict[server_name, Dict] where inner dict has: calls, tokens, avg, tools (list)
    # tools is list of (tool_short_name, calls, tokens, pct_of_server)
    server_hierarchy: Tuple[
        Tuple[str, int, int, int, Tuple[Tuple[str, int, int, float], ...]], ...
    ] = field(default_factory=tuple)
    # Each tuple is (server_name, calls, tokens, avg_per_call, tools)
    # tools is tuple of (short_name, calls, tokens, pct_of_server)

    # MCP usage as percentage of session tokens
    mcp_tokens_percent: float = 0.0

    # Session directory (for final summary display)
    session_dir: str = ""

    # ========================================================================
    # v0.1 Parity Enhancements (task-46)
    # ========================================================================

    # Message counter (task-46.1) - counts assistant messages, not just tool calls
    message_count: int = 0

    # Split cache tokens (task-46.8)
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0

    # Reasoning/thinking tokens (v1.3.0 - task-80)
    # Gemini CLI: thoughts, Codex CLI: reasoning_output_tokens, Claude Code: 0
    # Only displayed in TUI when > 0 (auto-hides for Claude Code)
    reasoning_tokens: int = 0

    # Built-in tools tracking (task-46.4)
    builtin_tool_calls: int = 0
    builtin_tool_tokens: int = 0

    # Git metadata (task-46.5)
    git_branch: str = ""
    git_commit_short: str = ""
    git_status: str = ""  # "clean", "dirty", or ""

    # Anomaly/warnings tracking (task-46.10)
    warnings_count: int = 0
    health_status: str = "healthy"  # "healthy", "warnings", "errors"

    # File monitoring status (task-46.6)
    files_monitored: int = 0

    # Tracking mode: "live" (new events only) or "full" (from start)
    tracking_mode: str = "live"

    # ========================================================================
    # Token Estimation Tracking (task-69.10)
    # ========================================================================

    # Number of MCP tool calls with estimated tokens (Codex/Gemini CLI)
    estimated_tool_calls: int = 0
    # Estimation method used (tiktoken, sentencepiece, character, or "")
    estimation_method: str = ""
    # Encoding used (o200k_base, sentencepiece:gemma, cl100k_base, or "")
    estimation_encoding: str = ""

    # ========================================================================
    # Data Quality (v1.5.0 - task-103.5)
    # ========================================================================

    # Accuracy level: "exact" (Claude Code), "estimated" (Codex/Gemini CLI), "calls-only"
    accuracy_level: str = "exact"
    # Token source: "native", "tiktoken", "sentencepiece", "character"
    token_source: str = "native"
    # Confidence score (0.0-1.0)
    data_quality_confidence: float = 1.0

    # ========================================================================
    # Multi-Model Tracking (v1.6.0 - task-108.2.4)
    # ========================================================================

    # List of distinct models used in session
    models_used: Tuple[str, ...] = field(default_factory=tuple)
    # Per-model usage: {model: {input_tokens, output_tokens, total_tokens, cost_usd, call_count}}
    model_usage: Tuple[Tuple[str, int, int, int, int, float, int], ...] = field(
        default_factory=tuple
    )
    # Each tuple is (model, input_tokens, output_tokens, cache_created, cache_read, cost_usd, call_count)
    # True if len(models_used) > 1
    is_multi_model: bool = False

    # ========================================================================
    # Static Cost / Context Tax (v0.6.0 - task-114.3)
    # ========================================================================

    # Total tokens for MCP server schemas (context tax)
    static_cost_total: int = 0
    # Per-server breakdown: tuple of (server_name, tokens)
    static_cost_by_server: Tuple[Tuple[str, int], ...] = field(default_factory=tuple)
    # How the estimate was obtained: "known_db", "estimate", "mixed", "none"
    static_cost_source: str = "none"
    # Confidence in the estimate (0.0-1.0)
    static_cost_confidence: float = 0.0
    # Tokens wasted on unused zombie tools
    zombie_context_tax: int = 0

    # ========================================================================
    # Smells Detection (v0.7.0 - task-105.2)
    # ========================================================================

    # Detected smells: tuple of (pattern, severity, tool, description)
    # severity is "warning" or "info"
    # tool is Optional[str] - None for session-level smells
    detected_smells: Tuple[Tuple[str, str, Optional[str], str], ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        project: str,
        platform: str,
        start_time: datetime,
        duration_seconds: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_tokens: int = 0,
        total_tokens: int = 0,
        cache_efficiency: float = 0.0,
        cost_estimate: float = 0.0,
        total_tool_calls: int = 0,
        unique_tools: int = 0,
        top_tools: List[Tuple[str, int, int, int]] | None = None,
        recent_events: List[Tuple[datetime, str, int]] | None = None,
        version: str = "",
        model_id: str = "",
        model_name: str = "",
        cost_no_cache: float = 0.0,
        cache_savings: float = 0.0,
        savings_percent: float = 0.0,
        server_hierarchy: (
            List[Tuple[str, int, int, int, List[Tuple[str, int, int, float]]]] | None
        ) = None,
        mcp_tokens_percent: float = 0.0,
        session_dir: str = "",
        # v0.1 Parity Enhancements (task-46)
        message_count: int = 0,
        cache_created_tokens: int = 0,
        cache_read_tokens: int = 0,
        reasoning_tokens: int = 0,  # v1.3.0: Gemini thoughts / Codex reasoning
        builtin_tool_calls: int = 0,
        builtin_tool_tokens: int = 0,
        git_branch: str = "",
        git_commit_short: str = "",
        git_status: str = "",
        warnings_count: int = 0,
        health_status: str = "healthy",
        files_monitored: int = 0,
        tracking_mode: str = "live",
        # Token estimation (task-69.10)
        estimated_tool_calls: int = 0,
        estimation_method: str = "",
        estimation_encoding: str = "",
        # Data quality (v1.5.0 - task-103.5)
        accuracy_level: str = "exact",
        token_source: str = "native",
        data_quality_confidence: float = 1.0,
        # Multi-model tracking (v1.6.0 - task-108.2.4)
        models_used: List[str] | None = None,
        model_usage: (
            List[Tuple[str, int, int, int, int, float, int]] | None
        ) = None,  # (model, input, output, cache_created, cache_read, cost, calls)
        is_multi_model: bool = False,
        # Static cost / context tax (v0.6.0 - task-114.3)
        static_cost_total: int = 0,
        static_cost_by_server: List[Tuple[str, int]] | None = None,
        static_cost_source: str = "none",
        static_cost_confidence: float = 0.0,
        zombie_context_tax: int = 0,
        # Smells detection (v0.7.0 - task-105.2)
        detected_smells: List[Tuple[str, str, Optional[str], str]] | None = None,
    ) -> "DisplaySnapshot":
        """Factory method to create a DisplaySnapshot with proper tuple conversion."""
        # Import version if not provided
        if not version:
            from .. import __version__

            version = __version__

        # Convert server_hierarchy to nested tuples
        hierarchy_tuple: Tuple[
            Tuple[str, int, int, int, Tuple[Tuple[str, int, int, float], ...]], ...
        ] = ()
        if server_hierarchy:
            hierarchy_tuple = tuple(
                (server, calls, tokens, avg, tuple(tools))
                for server, calls, tokens, avg, tools in server_hierarchy
            )

        return cls(
            project=project,
            platform=platform,
            start_time=start_time,
            duration_seconds=duration_seconds,
            version=version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_tokens=cache_tokens,
            total_tokens=total_tokens,
            cache_efficiency=cache_efficiency,
            cost_estimate=cost_estimate,
            total_tool_calls=total_tool_calls,
            unique_tools=unique_tools,
            top_tools=tuple(top_tools) if top_tools else (),
            recent_events=tuple(recent_events) if recent_events else (),
            model_id=model_id,
            model_name=model_name,
            cost_no_cache=cost_no_cache,
            cache_savings=cache_savings,
            savings_percent=savings_percent,
            server_hierarchy=hierarchy_tuple,
            mcp_tokens_percent=mcp_tokens_percent,
            session_dir=session_dir,
            # v0.1 Parity Enhancements (task-46)
            message_count=message_count,
            cache_created_tokens=cache_created_tokens,
            cache_read_tokens=cache_read_tokens,
            reasoning_tokens=reasoning_tokens,
            builtin_tool_calls=builtin_tool_calls,
            builtin_tool_tokens=builtin_tool_tokens,
            git_branch=git_branch,
            git_commit_short=git_commit_short,
            git_status=git_status,
            warnings_count=warnings_count,
            health_status=health_status,
            files_monitored=files_monitored,
            tracking_mode=tracking_mode,
            # Token estimation (task-69.10)
            estimated_tool_calls=estimated_tool_calls,
            estimation_method=estimation_method,
            estimation_encoding=estimation_encoding,
            # Data quality (v1.5.0 - task-103.5)
            accuracy_level=accuracy_level,
            token_source=token_source,
            data_quality_confidence=data_quality_confidence,
            # Multi-model tracking (v1.6.0 - task-108.2.4)
            models_used=tuple(models_used) if models_used else (),
            model_usage=tuple(model_usage) if model_usage else (),
            is_multi_model=is_multi_model,
            # Static cost / context tax (v0.6.0 - task-114.3)
            static_cost_total=static_cost_total,
            static_cost_by_server=(tuple(static_cost_by_server) if static_cost_by_server else ()),
            static_cost_source=static_cost_source,
            static_cost_confidence=static_cost_confidence,
            zombie_context_tax=zombie_context_tax,
            # Smells detection (v0.7.0 - task-105.2)
            detected_smells=tuple(detected_smells) if detected_smells else (),
        )
