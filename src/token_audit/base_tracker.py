#!/usr/bin/env python3
"""
BaseTracker - Abstract base class for platform-specific MCP trackers

Provides a stable adapter interface for Claude Code, Codex CLI, Gemini CLI, and future platforms.
"""

import contextlib
import hashlib
import json
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .display import DisplayAdapter
    from .recommendations import Recommendation

from . import __version__

# Schema version (see docs/data-contract.md for compatibility guarantees)
SCHEMA_VERSION = "1.7.0"


def _now_with_timezone() -> datetime:
    """Get current datetime with local timezone offset."""
    return datetime.now(timezone.utc).astimezone()


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO 8601 with timezone offset (e.g., 2025-12-01T14:19:38+11:00)."""
    if dt.tzinfo is None:
        # Add local timezone if naive
        dt = dt.replace(tzinfo=datetime.now(timezone.utc).astimezone().tzinfo)
    return dt.isoformat(timespec="seconds")


# ============================================================================
# Core Data Structures (Schema v1.0.4)
# ============================================================================


@dataclass
class FileHeader:
    """Self-describing file header for AI-Agent readability (v1.0.4)"""

    name: str  # File name (e.g., "token-audit-2025-12-01T14-19-38.json")
    type: str = "token_audit_session"  # File type identifier
    purpose: str = (
        "Complete MCP session log with token usage and tool call statistics for AI agent analysis"
    )
    schema_version: str = SCHEMA_VERSION
    schema_docs: str = (
        "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md"
    )
    generated_by: str = ""  # e.g., "token-audit v0.4.0"
    generated_at: str = ""  # ISO 8601 with timezone

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return asdict(self)


@dataclass
class Call:
    """Single MCP tool call record"""

    timestamp: datetime = field(default_factory=_now_with_timezone)
    tool_name: str = ""
    server: str = ""  # Server name extracted from tool_name (v1.0.4)
    index: int = 0  # Sequential call number within session (v1.0.4)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0  # 0 if not available
    content_hash: Optional[str] = None
    platform_data: Optional[Dict[str, Any]] = None
    # Token estimation metadata (v1.4.0)
    is_estimated: bool = False  # True for Codex/Gemini MCP tools
    estimation_method: Optional[str] = None  # "tiktoken", "sentencepiece", or "character"
    estimation_encoding: Optional[str] = None  # e.g., "o200k_base", "sentencepiece:gemma"
    # Multi-model tracking (v1.6.0 - task-108.2.2)
    model: Optional[str] = None  # Model used for this call (when known)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for v1.4.0 format"""
        result: Dict[str, Any] = {
            "index": self.index,
            "timestamp": _format_timestamp(self.timestamp),
            "tool": self.tool_name,
            "server": self.server,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms if self.duration_ms > 0 else None,
            "content_hash": self.content_hash,
        }
        # v1.4.0: Add estimation fields only when tokens are estimated
        # Omit when False to minimize file size for Claude Code sessions
        if self.is_estimated:
            result["is_estimated"] = True
            result["estimation_method"] = self.estimation_method
            result["estimation_encoding"] = self.estimation_encoding
        # v1.6.0: Add model field only when set (task-108.2.2)
        if self.model:
            result["model"] = self.model
        return result

    def to_dict_v1_0(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for v1.0.0 backward compatibility"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["schema_version"] = "1.0.0"  # For v1.0.0 format
        return data


@dataclass
class ToolStats:
    """Statistics for a single MCP tool"""

    calls: int = 0
    total_tokens: int = 0
    avg_tokens: float = 0.0
    call_history: List[Call] = field(default_factory=list)
    total_duration_ms: Optional[int] = None
    avg_duration_ms: Optional[float] = None
    max_duration_ms: Optional[int] = None
    min_duration_ms: Optional[int] = None
    # Per-tool cache tracking (task-47.4)
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict (v1.0.4 - no schema_version)"""
        return {
            "calls": self.calls,
            "total_tokens": self.total_tokens,
            "avg_tokens": self.avg_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": self.avg_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "min_duration_ms": self.min_duration_ms,
            "call_history": [call.to_dict() for call in self.call_history],
        }

    def to_dict_v1_0(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for v1.0.0 backward compatibility"""
        data = asdict(self)
        data["schema_version"] = "1.0.0"
        data["call_history"] = [call.to_dict_v1_0() for call in self.call_history]
        return data


@dataclass
class ServerSession:
    """Statistics for a single MCP server"""

    server: str = ""
    tools: Dict[str, ToolStats] = field(default_factory=dict)
    total_calls: int = 0
    total_tokens: int = 0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict (v1.0.4 - no schema_version)"""
        return {
            "server": self.server,
            "tools": {name: stats.to_dict() for name, stats in self.tools.items()},
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "metadata": self.metadata,
        }

    def to_dict_v1_0(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for v1.0.0 backward compatibility"""
        data = asdict(self)
        data["schema_version"] = "1.0.0"
        data["tools"] = {name: stats.to_dict_v1_0() for name, stats in self.tools.items()}
        return data


@dataclass
class TokenUsage:
    """Token usage statistics

    Attributes:
        input_tokens: Tokens from user input/context
        output_tokens: Tokens from model output (excludes reasoning)
        cache_created_tokens: Tokens added to cache
        cache_read_tokens: Tokens read from cache
        reasoning_tokens: Thinking/reasoning tokens (Gemini CLI: thoughts,
            Codex CLI: reasoning_output_tokens, Claude Code: 0)
        total_tokens: Sum of all token types
        cache_efficiency: Ratio of cache_read to total input (0.0-1.0)
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0  # v1.3.0: Gemini thoughts / Codex reasoning
    total_tokens: int = 0
    cache_efficiency: float = 0.0


@dataclass
class MCPToolCalls:
    """MCP tool call summary"""

    total_calls: int = 0
    unique_tools: int = 0
    most_called: str = ""


@dataclass
class MCPSummary:
    """Pre-computed MCP summary for quick AI access (v1.0.4)"""

    total_calls: int = 0
    unique_tools: int = 0
    unique_servers: int = 0
    servers_used: List[str] = field(default_factory=list)
    top_by_tokens: List[Dict[str, Any]] = field(default_factory=list)
    top_by_calls: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return asdict(self)


@dataclass
class BuiltinToolSummary:
    """Summary of built-in tool usage for session logs (v1.2.0)

    Tracks aggregate and per-tool statistics for built-in tools
    (Bash, Read, Write, Edit, Glob, Grep, etc.)
    """

    total_calls: int = 0
    total_tokens: int = 0
    tools: List[Dict[str, Any]] = field(default_factory=list)  # Per-tool breakdown

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "tools": self.tools,
        }


@dataclass
class CacheAnalysis:
    """AI-optimized cache analysis for session logs (task-47.3)

    Provides a clear breakdown of cache efficiency for AI agents to understand:
    - What happened (status + summary)
    - Why (top creators/readers)
    - What to do (recommendation)
    """

    status: str = "neutral"  # "efficient", "inefficient", "neutral"
    summary: str = ""  # Human/AI readable summary
    creation_tokens: int = 0
    read_tokens: int = 0
    ratio: float = 0.0  # read/creation ratio (higher = better)
    net_savings_usd: float = 0.0  # Positive = savings, negative = net cost
    top_cache_creators: List[Dict[str, Any]] = field(default_factory=list)
    top_cache_readers: List[Dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return asdict(self)


# ============================================================================
# Schema v1.5.0 Data Structures (Insight Layer)
# ============================================================================


@dataclass
class Smell:
    """Efficiency anti-pattern detected in a session (v1.5.0)

    Represents a single "code smell" for MCP tool usage patterns that
    may indicate inefficiency or suboptimal behavior.

    Attributes:
        pattern: Pattern identifier (e.g., "HIGH_VARIANCE", "CHATTY")
        severity: "info", "warning", or "error"
        tool: Tool name triggering the smell (optional, some are session-level)
        description: Human-readable explanation
        evidence: Pattern-specific supporting data
    """

    pattern: str  # HIGH_VARIANCE, TOP_CONSUMER, HIGH_MCP_SHARE, CHATTY, LOW_CACHE_HIT
    severity: str = "info"  # "info", "warning", "error"
    tool: Optional[str] = None  # Tool that triggered the smell (if applicable)
    description: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "pattern": self.pattern,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
        }
        if self.tool:
            result["tool"] = self.tool
        return result


@dataclass
class DataQuality:
    """Data quality and accuracy indicators for a session (v1.5.0, v1.6.0)

    Provides clear labeling of how accurate the token metrics are,
    helping users understand the reliability of the data.

    Attributes:
        accuracy_level: "exact", "estimated", or "calls-only"
        token_source: Tokenizer/source used (e.g., "native", "tiktoken", "sentencepiece")
        token_encoding: Specific encoding (e.g., "o200k_base", "gemma")
        confidence: Estimated accuracy as float (0.0-1.0)
        pricing_source: Where pricing data came from (v1.6.0)
        pricing_freshness: Pricing data freshness (v1.6.0)
        notes: Additional context about data quality
    """

    accuracy_level: str = "exact"  # "exact", "estimated", "calls-only"
    token_source: str = "native"  # "native", "tiktoken", "sentencepiece", "character"
    token_encoding: Optional[str] = None  # e.g., "o200k_base", "gemma"
    confidence: float = 1.0  # 0.0-1.0
    # v1.6.0: Pricing source tracking (task-108.3.4)
    pricing_source: str = "defaults"  # "api", "cache", "cache-stale", "file", "defaults"
    pricing_freshness: str = "unknown"  # "fresh", "cached", "stale", "unknown"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "accuracy_level": self.accuracy_level,
            "token_source": self.token_source,
            "confidence": self.confidence,
            "pricing_source": self.pricing_source,
            "pricing_freshness": self.pricing_freshness,
        }
        if self.token_encoding:
            result["token_encoding"] = self.token_encoding
        if self.notes:
            result["notes"] = self.notes
        return result


@dataclass
class ModelUsage:
    """Per-model token and cost tracking (v1.6.0 - task-108.2.2)

    Tracks aggregate statistics for a single model within a session,
    enabling breakdown when users switch models mid-session.

    Attributes:
        model: Model identifier (e.g., "claude-sonnet-4-20250514")
        input_tokens: Total input tokens for this model
        output_tokens: Total output tokens for this model
        cache_created_tokens: Cache creation tokens for this model
        cache_read_tokens: Cache read tokens for this model
        total_tokens: Sum of all token types for this model
        cost_usd: Cost estimate for this model's usage
        call_count: Number of tool calls using this model
    """

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_created_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_created_tokens": self.cache_created_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "call_count": self.call_count,
        }


@dataclass
class StaticCost:
    """MCP schema context tax tracking (v1.6.0 - task-108.4)

    Tracks the static token cost incurred by MCP tool schemas that are
    included in every request. This "context tax" represents overhead
    that users pay regardless of tool usage.

    Note: This feature requires either live MCP server queries or
    estimation based on known server configurations. Full implementation
    pending infrastructure support.

    Attributes:
        total_tokens: Total tokens across all MCP server schemas
        source: How the token count was obtained ("live", "cache", "estimate")
        by_server: Per-server token breakdown
        confidence: Confidence in the estimate (0.0-1.0)
    """

    total_tokens: int = 0
    source: str = "estimate"  # "live", "cache", "estimate"
    by_server: Dict[str, int] = field(default_factory=dict)  # server -> tokens
    confidence: float = 0.7  # Default for estimates

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "total_tokens": self.total_tokens,
            "source": self.source,
            "by_server": self.by_server,
            "confidence": self.confidence,
        }


@dataclass
class Session:
    """Complete session data"""

    schema_version: str = SCHEMA_VERSION
    mcp_audit_version: str = ""  # Version of token-audit that tracked this session
    project: str = ""
    platform: str = ""  # "claude-code", "codex-cli", "gemini-cli"
    model: str = ""  # Model used (e.g., "claude-opus-4-5-20251101") (v1.0.4)
    working_directory: str = ""  # Directory where token-audit was run (v1.0.4)
    timestamp: datetime = field(default_factory=_now_with_timezone)
    session_id: str = ""
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost_estimate: float = 0.0
    cost_no_cache: float = 0.0  # Cost without caching (task-47.3)
    cache_savings_usd: float = 0.0  # Net savings from caching (task-47.3)
    mcp_tool_calls: MCPToolCalls = field(default_factory=MCPToolCalls)
    server_sessions: Dict[str, ServerSession] = field(default_factory=dict)
    redundancy_analysis: Optional[Dict[str, Any]] = None
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    end_timestamp: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    source_files: List[str] = field(default_factory=list)  # Files monitored (v1.0.4)
    message_count: int = 0  # Number of assistant messages (task-49.1)
    # Built-in tool tracking (v1.2.0)
    builtin_tool_stats: Dict[str, Dict[str, int]] = field(
        default_factory=dict
    )  # tool -> {calls, tokens}
    # v1.5.0: Insight Layer
    smells: List["Smell"] = field(default_factory=list)  # Efficiency anti-patterns
    recommendations: List["Recommendation"] = field(default_factory=list)  # v0.9.1 (#69)
    data_quality: Optional["DataQuality"] = None  # Accuracy indicators
    zombie_tools: Dict[str, List[str]] = field(default_factory=dict)  # server -> unused tools
    # v1.6.0: Multi-model tracking (task-108.2.2)
    models_used: List[str] = field(default_factory=list)  # Distinct models used in session
    model_usage: Dict[str, "ModelUsage"] = field(default_factory=dict)  # Per-model breakdown
    # v1.6.0: Static cost tracking (task-108.4) - future implementation
    static_cost: Optional["StaticCost"] = None  # MCP schema context tax (when available)
    # v1.7.0: Pinned server tracking (task-106.5)
    pinned_servers: List[str] = field(default_factory=list)  # Servers pinned by user
    _call_index: int = field(default=0, repr=False)  # Internal counter for call indices

    def to_dict(self) -> Dict[str, Any]:
        """Convert to v1.7.0 JSON-serializable dict with Pinned MCP Focus"""
        # Build flat tool_calls array from all server sessions
        tool_calls = []
        for server_session in self.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    tool_calls.append(call.to_dict())

        # Sort by index (sequential order)
        tool_calls.sort(key=lambda x: x.get("index", 0))

        # v1.7.0: Build tool sequence for pattern analysis (task-106.5)
        tool_sequence = self._build_tool_sequence()

        # Build MCP summary
        mcp_summary = self._build_mcp_summary()

        # Build cache analysis (task-47.3)
        cache_analysis = self._build_cache_analysis(self.cache_savings_usd)

        # Build builtin tool summary (v1.2.0 - task-78)
        builtin_tool_summary = self._build_builtin_tool_summary()

        # v1.5.0: Build data quality block
        data_quality_dict = self.data_quality.to_dict() if self.data_quality else None

        result: Dict[str, Any] = {
            "_file": None,  # To be set by save_session()
            "session": {
                "id": self.session_id,
                "project": self.project,
                "platform": self.platform,
                "model": self.model,
                "working_directory": self.working_directory,
                "started_at": _format_timestamp(self.timestamp),
                "ended_at": _format_timestamp(self.end_timestamp) if self.end_timestamp else None,
                "duration_seconds": self.duration_seconds,
                "source_files": self.source_files,
                "message_count": self.message_count,
                # v1.6.0: Multi-model tracking (task-108.2.2)
                "models_used": self.models_used if self.models_used else [],
            },
            "token_usage": asdict(self.token_usage),
            "cost_estimate_usd": self.cost_estimate,
            "cost_no_cache_usd": self.cost_no_cache,
            "cache_savings_usd": self.cache_savings_usd,
            "mcp_summary": mcp_summary.to_dict(),
            "builtin_tool_summary": builtin_tool_summary.to_dict(),
            "cache_analysis": cache_analysis.to_dict(),
            "tool_calls": tool_calls,
            # v1.5.0: Insight Layer blocks
            "smells": [smell.to_dict() for smell in self.smells],
            "recommendations": [rec.to_dict() for rec in self.recommendations],  # v0.9.1 (#69)
            "zombie_tools": self.zombie_tools if self.zombie_tools else {},
            "analysis": {
                "redundancy": self.redundancy_analysis,
                "anomalies": self.anomalies,
            },
        }

        # v1.5.0: Add data_quality only if set (platform-dependent)
        if data_quality_dict:
            result["data_quality"] = data_quality_dict

        # v1.6.0: Add model_usage only if multi-model session (task-108.2.2)
        if self.model_usage:
            result["model_usage"] = {
                model: usage.to_dict() if hasattr(usage, "to_dict") else usage
                for model, usage in self.model_usage.items()
            }

        # v1.6.0: Add static_cost only if available (task-108.4)
        if self.static_cost:
            result["static_cost"] = self.static_cost.to_dict()

        # v1.7.0: Pinned MCP Focus (task-106.5)
        if self.pinned_servers:
            result["pinned_servers"] = self.pinned_servers
            pinned_usage = self._build_pinned_server_usage()
            result["pinned_server_usage"] = pinned_usage
            total_calls = pinned_usage["pinned_calls"] + pinned_usage["non_pinned_calls"]
            result["pinned_coverage"] = (
                pinned_usage["pinned_calls"] / total_calls if total_calls > 0 else 0.0
            )

        # v1.7.0: MCP servers hierarchy with per-tool stats (task-106.5)
        result["mcp_servers"] = self._build_mcp_servers_hierarchy()

        # v1.7.0: Tool sequence for pattern analysis (task-106.5)
        result["tool_sequence"] = tool_sequence

        return result

    def to_dict_v1_0(self) -> Dict[str, Any]:
        """Convert to v1.0.0 JSON-serializable dict for backward compatibility"""
        data = {
            "schema_version": "1.0.0",
            "mcp_audit_version": self.mcp_audit_version,
            "project": self.project,
            "platform": self.platform,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "token_usage": asdict(self.token_usage),
            "cost_estimate": self.cost_estimate,
            "mcp_tool_calls": asdict(self.mcp_tool_calls),
            "server_sessions": {
                name: sess.to_dict_v1_0() for name, sess in self.server_sessions.items()
            },
            "redundancy_analysis": self.redundancy_analysis,
            "anomalies": self.anomalies,
        }
        if self.end_timestamp:
            data["end_timestamp"] = self.end_timestamp.isoformat()
        if self.duration_seconds is not None:
            data["duration_seconds"] = self.duration_seconds
        return data

    def _build_mcp_summary(self) -> MCPSummary:
        """Build pre-computed MCP summary.

        Note: Excludes "builtin" pseudo-server (task-95.2). Built-in tools
        (shell_command, update_plan, etc.) are tracked separately in
        builtin_tool_summary.
        """
        all_tools: List[Tuple[str, str, int, int]] = []  # (tool, server, tokens, calls)

        # Filter out "builtin" pseudo-server - these are NOT MCP tools (task-95.2)
        mcp_servers = {
            name: session for name, session in self.server_sessions.items() if name != "builtin"
        }

        for server_name, server_session in mcp_servers.items():
            for tool_name, tool_stats in server_session.tools.items():
                all_tools.append(
                    (tool_name, server_name, tool_stats.total_tokens, tool_stats.calls)
                )

        # Sort by tokens for top_by_tokens
        by_tokens = sorted(all_tools, key=lambda x: x[2], reverse=True)[:5]
        top_by_tokens = [
            {"tool": t[0], "server": t[1], "tokens": t[2], "calls": t[3]} for t in by_tokens
        ]

        # Sort by calls for top_by_calls
        by_calls = sorted(all_tools, key=lambda x: x[3], reverse=True)[:5]
        top_by_calls = [
            {"tool": t[0], "server": t[1], "calls": t[3], "tokens": t[2]} for t in by_calls
        ]

        return MCPSummary(
            total_calls=sum(ss.total_calls for ss in mcp_servers.values()),
            unique_tools=len({t[0] for t in all_tools}),
            unique_servers=len(mcp_servers),
            servers_used=list(mcp_servers.keys()),
            top_by_tokens=top_by_tokens,
            top_by_calls=top_by_calls,
        )

    def _build_cache_analysis(self, net_savings_usd: float = 0.0) -> CacheAnalysis:
        """Build AI-optimized cache analysis (task-47.3).

        Args:
            net_savings_usd: Net savings in USD (positive = savings, negative = cost).
                            Should be calculated by the caller using pricing config.
        """
        creation_tokens = self.token_usage.cache_created_tokens
        read_tokens = self.token_usage.cache_read_tokens

        # Calculate read/creation ratio (higher = better cache efficiency)
        ratio = read_tokens / creation_tokens if creation_tokens > 0 else 0.0

        # Collect per-tool cache stats
        tool_cache_stats: List[Tuple[str, int, int]] = []  # (tool, created, read)
        for server_session in self.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                if tool_stats.cache_created_tokens > 0 or tool_stats.cache_read_tokens > 0:
                    tool_cache_stats.append(
                        (tool_name, tool_stats.cache_created_tokens, tool_stats.cache_read_tokens)
                    )

        # Top cache creators (by cache_created_tokens)
        by_creation = sorted(tool_cache_stats, key=lambda x: x[1], reverse=True)[:5]
        top_cache_creators = []
        for tool, created, _read in by_creation:
            if created > 0:
                pct = (created / creation_tokens * 100) if creation_tokens > 0 else 0
                top_cache_creators.append({"tool": tool, "tokens": created, "pct": round(pct, 1)})

        # Top cache readers (by cache_read_tokens)
        by_read = sorted(tool_cache_stats, key=lambda x: x[2], reverse=True)[:5]
        top_cache_readers = []
        for tool, _created, read in by_read:
            if read > 0:
                pct = (read / read_tokens * 100) if read_tokens > 0 else 0
                top_cache_readers.append({"tool": tool, "tokens": read, "pct": round(pct, 1)})

        # Determine status and generate summary/recommendation
        if creation_tokens == 0 and read_tokens == 0:
            status = "neutral"
            summary = "No cache activity in this session."
            recommendation = ""
        elif creation_tokens == 0 and read_tokens > 0:
            # Read-only cache (Codex CLI, Gemini CLI) - always efficient
            # You're reading from existing cache without paying creation cost
            status = "efficient"
            summary = (
                f"Read-only cache: {read_tokens:,} tokens read from cache. "
                f"No cache creation cost incurred."
            )
            recommendation = "Cache is working efficiently with read-only access."
        elif net_savings_usd > 0:
            status = "efficient"
            summary = (
                f"Cache saved ${net_savings_usd:.4f}. "
                f"Created {creation_tokens:,} tokens, read {read_tokens:,} tokens "
                f"(ratio: {ratio:.2f})."
            )
            recommendation = "Cache is working efficiently. Continue current usage patterns."
        elif ratio >= 1.0 and read_tokens > 0:
            # High ratio but no cost data - assume efficient
            status = "efficient"
            summary = (
                f"Good cache reuse: created {creation_tokens:,}, read {read_tokens:,} "
                f"(ratio: {ratio:.2f})."
            )
            recommendation = "Cache is working efficiently. Continue current usage patterns."
        else:
            status = "inefficient"
            abs_cost = abs(net_savings_usd)
            if read_tokens == 0:
                summary = (
                    f"High cache creation ({creation_tokens:,} tokens) with no reuse. "
                    f"Net cost: ${abs_cost:.4f}."
                )
                recommendation = (
                    "Consider batching related queries to reuse cached context. "
                    "New context every call prevents cache benefits."
                )
            elif ratio < 0.1:
                summary = (
                    f"High cache creation ({creation_tokens:,}) with low reuse ({read_tokens:,}). "
                    f"Net cost: ${abs_cost:.4f}."
                )
                recommendation = (
                    "Cache creation exceeds reuse benefit. "
                    "Try grouping related operations to maximize cache hits."
                )
            else:
                summary = (
                    f"Cache creation cost exceeds read savings. "
                    f"Created {creation_tokens:,}, read {read_tokens:,}. "
                    f"Net cost: ${abs_cost:.4f}."
                )
                recommendation = (
                    "Ratio is acceptable but volume is low. "
                    "Consider longer sessions to amortize cache creation cost."
                )

        return CacheAnalysis(
            status=status,
            summary=summary,
            creation_tokens=creation_tokens,
            read_tokens=read_tokens,
            ratio=round(ratio, 4),
            net_savings_usd=round(net_savings_usd, 4),
            top_cache_creators=top_cache_creators,
            top_cache_readers=top_cache_readers,
            recommendation=recommendation,
        )

    def _build_builtin_tool_summary(self) -> BuiltinToolSummary:
        """Build summary of built-in tool usage (v1.2.0 - task-78).

        Converts internal builtin_tool_stats dict to a structured summary
        for inclusion in session output.

        Returns:
            BuiltinToolSummary with total counts and per-tool breakdown
        """
        if not self.builtin_tool_stats:
            return BuiltinToolSummary()

        total_calls = 0
        total_tokens = 0
        tools_list: List[Dict[str, Any]] = []

        # Sort by tokens (descending) for consistent output
        sorted_tools = sorted(
            self.builtin_tool_stats.items(),
            key=lambda x: x[1].get("tokens", 0),
            reverse=True,
        )

        for tool_name, stats in sorted_tools:
            calls = stats.get("calls", 0)
            tokens = stats.get("tokens", 0)
            total_calls += calls
            total_tokens += tokens
            tools_list.append(
                {
                    "tool": tool_name,
                    "calls": calls,
                    "tokens": tokens,
                }
            )

        return BuiltinToolSummary(
            total_calls=total_calls,
            total_tokens=total_tokens,
            tools=tools_list,
        )

    def _build_tool_sequence(self) -> List[Dict[str, Any]]:
        """Build chronological tool sequence for pattern analysis (v1.7.0 - task-106.5).

        Creates a compact timeline of all tool calls in execution order,
        useful for identifying patterns like burst calls, sequential reads,
        or create-then-edit sequences.

        Returns:
            List of dicts with ts, server, tool, tokens, index
        """
        all_calls: List[Call] = []

        # Collect all calls from MCP servers (exclude builtin)
        for server_name, server_session in self.server_sessions.items():
            if server_name == "builtin":
                continue
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)

        # Sort by index (execution order)
        all_calls.sort(key=lambda c: c.index)

        # Build compact sequence
        sequence = []
        for call in all_calls:
            sequence.append(
                {
                    "ts": _format_timestamp(call.timestamp),
                    "server": call.server,
                    "tool": call.tool_name,
                    "tokens": call.total_tokens,
                    "index": call.index,
                }
            )

        return sequence

    def _build_pinned_server_usage(self) -> Dict[str, Any]:
        """Build aggregate stats for pinned vs non-pinned servers (v1.7.0 - task-106.5).

        Calculates how much of the session's MCP usage went to pinned servers
        vs non-pinned servers.

        Returns:
            Dict with pinned_calls, pinned_tokens, non_pinned_calls, non_pinned_tokens
        """
        pinned_calls = 0
        pinned_tokens = 0
        non_pinned_calls = 0
        non_pinned_tokens = 0

        pinned_set = set(self.pinned_servers)

        for server_name, server_session in self.server_sessions.items():
            if server_name == "builtin":
                continue

            if server_name in pinned_set:
                pinned_calls += server_session.total_calls
                pinned_tokens += server_session.total_tokens
            else:
                non_pinned_calls += server_session.total_calls
                non_pinned_tokens += server_session.total_tokens

        return {
            "pinned_calls": pinned_calls,
            "pinned_tokens": pinned_tokens,
            "non_pinned_calls": non_pinned_calls,
            "non_pinned_tokens": non_pinned_tokens,
        }

    def _build_mcp_servers_hierarchy(self) -> Dict[str, Any]:
        """Build full MCP servers hierarchy with per-tool stats (v1.7.0 - task-106.5).

        Creates a structured view of all MCP servers and their tools,
        including is_pinned flag for each server.

        Returns:
            Dict mapping server names to their tool breakdowns
        """
        pinned_set = set(self.pinned_servers)
        hierarchy: Dict[str, Any] = {}

        for server_name, server_session in self.server_sessions.items():
            if server_name == "builtin":
                continue

            tools_dict: Dict[str, Any] = {}
            for tool_name, tool_stats in server_session.tools.items():
                avg_tokens = (
                    tool_stats.total_tokens / tool_stats.calls if tool_stats.calls > 0 else 0
                )
                tools_dict[tool_name] = {
                    "calls": tool_stats.calls,
                    "tokens": tool_stats.total_tokens,
                    "avg": round(avg_tokens, 1),
                }

            hierarchy[server_name] = {
                "calls": server_session.total_calls,
                "tokens": server_session.total_tokens,
                "is_pinned": server_name in pinned_set,
                "tools": tools_dict,
            }

        return hierarchy

    def next_call_index(self) -> int:
        """Get next sequential call index"""
        self._call_index += 1
        return self._call_index


# ============================================================================
# BaseTracker Abstract Class
# ============================================================================


class BaseTracker(ABC):
    """
    Abstract base class for platform-specific MCP trackers.

    Provides common functionality and defines the adapter interface
    that all platform trackers must implement.
    """

    def __init__(self, project: str, platform: str):
        """
        Initialize base tracker.

        Args:
            project: Project name (e.g., "token-audit")
            platform: Platform identifier (e.g., "claude-code", "codex-cli", "gemini-cli")
        """
        self.project = project
        self.platform = platform
        self.timestamp = _now_with_timezone()
        self.session_id = self._generate_session_id()
        self.working_directory = str(Path.cwd())

        # Session data
        self.session = Session(
            project=project,
            platform=platform,
            timestamp=self.timestamp,
            session_id=self.session_id,
            mcp_audit_version=__version__,
            working_directory=self.working_directory,
        )

        # Server sessions (key: server name)
        self.server_sessions: Dict[str, ServerSession] = {}

        # Duplicate detection (key: content_hash)
        self.content_hashes: Dict[str, List[Call]] = defaultdict(list)

        # Session directory and file path
        self.session_dir: Optional[Path] = None
        self.session_path: Optional[Path] = None  # Full path to saved session file

        # Output directory (default: ~/.token-audit/sessions)
        self.output_dir: Path = Path.home() / ".token-audit" / "sessions"

        # MCP config path for static cost calculation (v0.6.0 - task-114.2)
        self._mcp_config_path: Optional[Path] = None

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%S")
        return f"{self.project}-{timestamp_str}"

    def set_mcp_config_path(self, config_path: Optional[Path]) -> None:
        """Set the MCP configuration file path for static cost calculation.

        Args:
            config_path: Path to MCP config file (.mcp.json, settings.json, etc.)
                        None to disable static cost calculation
        """
        self._mcp_config_path = config_path

    # ========================================================================
    # Abstract Methods (Platform-specific implementation required)
    # ========================================================================

    @abstractmethod
    def start_tracking(self) -> None:
        """
        Start tracking session.

        Platform-specific implementation:
        - Claude Code: Start tailing debug.log
        - Codex CLI: Start process wrapper
        - Gemini CLI: Start process wrapper with --debug
        """
        pass

    @abstractmethod
    def parse_event(self, event_data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Parse platform-specific event into normalized format.

        Args:
            event_data: Raw event data (line, JSON object, etc.)

        Returns:
            Tuple of (tool_name, usage_dict) if MCP tool call, None otherwise

        Platform-specific parsing:
        - Claude Code: Parse debug.log JSON event
        - Codex CLI: Parse stdout/stderr text
        - Gemini CLI: Parse debug output or checkpoint
        """
        pass

    @abstractmethod
    def get_platform_metadata(self) -> Dict[str, Any]:
        """
        Get platform-specific metadata.

        Returns:
            Dictionary with platform-specific data
            (e.g., model, debug_log_path, checkpoint_path)
        """
        pass

    # ========================================================================
    # Normalization (Shared implementation)
    # ========================================================================

    def normalize_server_name(self, tool_name: str) -> str:
        """
        Extract and normalize server name from tool name.

        Examples:
            "mcp__zen__chat" → "zen"
            "mcp__zen-mcp__chat" → "zen" (Codex CLI format)
            "mcp__brave-search__web" → "brave-search"
            "builtin__read_file" → "builtin" (Gemini CLI format, task-78)
            "__builtin__:shell_command" → "builtin" (Codex CLI format, task-69.31.2)

        Args:
            tool_name: Full MCP tool name or built-in tool name

        Returns:
            Normalized server name
        """
        # Handle built-in tools (task-78, task-69.31.2)
        # Gemini CLI format: builtin__tool_name
        if tool_name.startswith("builtin__"):
            return "builtin"
        # Codex CLI format: __builtin__:tool_name
        if tool_name.startswith("__builtin__:"):
            return "builtin"

        if not tool_name.startswith("mcp__"):
            warnings.warn(f"Tool name doesn't start with 'mcp__': {tool_name}", stacklevel=2)
            return "unknown"

        # Remove mcp__ prefix
        name_parts = tool_name[5:].split("__")

        # Handle Codex CLI format: mcp__zen-mcp__chat
        server_name = name_parts[0]
        if server_name.endswith("-mcp"):
            server_name = server_name[:-4]

        return server_name

    def normalize_tool_name(self, tool_name: str) -> str:
        """
        Normalize tool name to consistent format.

        Examples:
            "mcp__zen-mcp__chat" → "mcp__zen__chat" (Codex CLI)
            "mcp__zen__chat" → "mcp__zen__chat" (Claude Code)

        Args:
            tool_name: Raw tool name from platform

        Returns:
            Normalized tool name (Claude Code format)
        """
        # Strip -mcp suffix from server name (Codex CLI compatibility)
        if "-mcp__" in tool_name:
            parts = tool_name.split("__")
            if len(parts) >= 2 and parts[0] == "mcp":
                server_name = parts[1].replace("-mcp", "")
                tool_suffix = "__".join(parts[2:])
                return f"mcp__{server_name}__{tool_suffix}"

        return tool_name

    # ========================================================================
    # Session Management (Shared implementation)
    # ========================================================================

    def record_tool_call(
        self,
        tool_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_created_tokens: int = 0,
        cache_read_tokens: int = 0,
        duration_ms: int = 0,
        content_hash: Optional[str] = None,
        platform_data: Optional[Dict[str, Any]] = None,
        is_estimated: bool = False,
        estimation_method: Optional[str] = None,
        estimation_encoding: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Record a single MCP tool call.

        Args:
            tool_name: Normalized tool name
            input_tokens: Input token count
            output_tokens: Output token count
            cache_created_tokens: Cache creation tokens
            cache_read_tokens: Cache read tokens
            duration_ms: Call duration in milliseconds (0 if not available)
            content_hash: SHA256 hash of input (for duplicate detection)
            platform_data: Platform-specific metadata
            is_estimated: True if token counts are estimated (v1.4.0)
            estimation_method: "tiktoken", "sentencepiece", or "character" (v1.4.0)
            estimation_encoding: e.g., "o200k_base", "sentencepiece:gemma" (v1.4.0)
            model: Model used for this call (v1.6.0 - task-108.2.3)
        """
        # Normalize tool name
        normalized_tool = self.normalize_tool_name(tool_name)
        server_name = self.normalize_server_name(normalized_tool)

        # Create Call object with sequential index
        total_tokens = input_tokens + output_tokens + cache_created_tokens + cache_read_tokens
        call_index = self.session.next_call_index()
        call = Call(
            timestamp=_now_with_timezone(),
            tool_name=normalized_tool,
            server=server_name,  # v1.0.4: include server name in call
            index=call_index,  # v1.0.4: sequential call number
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_created_tokens=cache_created_tokens,
            cache_read_tokens=cache_read_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            content_hash=content_hash,
            platform_data=platform_data,
            # v1.4.0: Token estimation metadata
            is_estimated=is_estimated,
            estimation_method=estimation_method,
            estimation_encoding=estimation_encoding,
            # v1.6.0: Multi-model tracking (task-108.2.3)
            model=model,
        )

        # Track duplicate calls
        if content_hash:
            self.content_hashes[content_hash].append(call)

        # Get or create server session
        if server_name not in self.server_sessions:
            self.server_sessions[server_name] = ServerSession(server=server_name)

        server_session = self.server_sessions[server_name]

        # Get or create tool stats
        if normalized_tool not in server_session.tools:
            server_session.tools[normalized_tool] = ToolStats()

        tool_stats = server_session.tools[normalized_tool]

        # Update tool stats
        tool_stats.calls += 1
        tool_stats.total_tokens += total_tokens
        tool_stats.avg_tokens = tool_stats.total_tokens / tool_stats.calls
        tool_stats.call_history.append(call)
        # Per-tool cache tracking (task-47.4)
        tool_stats.cache_created_tokens += cache_created_tokens
        tool_stats.cache_read_tokens += cache_read_tokens

        # Update duration stats (if available)
        if duration_ms > 0:
            if tool_stats.total_duration_ms is None:
                tool_stats.total_duration_ms = 0
            tool_stats.total_duration_ms += duration_ms
            tool_stats.avg_duration_ms = tool_stats.total_duration_ms / tool_stats.calls

            if tool_stats.max_duration_ms is None or duration_ms > tool_stats.max_duration_ms:
                tool_stats.max_duration_ms = duration_ms

            if tool_stats.min_duration_ms is None or duration_ms < tool_stats.min_duration_ms:
                tool_stats.min_duration_ms = duration_ms

        # Update server totals
        server_session.total_calls += 1
        server_session.total_tokens += total_tokens

        # Update session token usage
        self.session.token_usage.input_tokens += input_tokens
        self.session.token_usage.output_tokens += output_tokens
        self.session.token_usage.cache_created_tokens += cache_created_tokens
        self.session.token_usage.cache_read_tokens += cache_read_tokens
        self.session.token_usage.total_tokens += total_tokens

        # Recalculate cache efficiency: percentage of INPUT tokens served from cache
        total_input = (
            self.session.token_usage.input_tokens
            + self.session.token_usage.cache_created_tokens
            + self.session.token_usage.cache_read_tokens
        )
        if total_input > 0:
            self.session.token_usage.cache_efficiency = (
                self.session.token_usage.cache_read_tokens / total_input
            )

    def finalize_session(self) -> Session:
        """
        Finalize session data and calculate summary statistics.

        Returns:
            Complete Session object
        """
        # Update session end time (use timezone-aware datetime for v1.0.4)
        self.session.end_timestamp = _now_with_timezone()
        self.session.duration_seconds = (
            self.session.end_timestamp - self.session.timestamp
        ).total_seconds()

        # Update MCP tool calls summary
        # Filter out "builtin" pseudo-server - these are NOT MCP tools (task-95.2)
        mcp_server_sessions = {
            name: session for name, session in self.server_sessions.items() if name != "builtin"
        }

        all_tools: set[str] = set()
        most_called_tool = ""
        most_called_count = 0

        for server_session in mcp_server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                all_tools.add(tool_name)
                if tool_stats.calls > most_called_count:
                    most_called_count = tool_stats.calls
                    most_called_tool = f"{tool_name} ({tool_stats.calls} calls)"

        self.session.mcp_tool_calls.total_calls = sum(
            ss.total_calls for ss in mcp_server_sessions.values()
        )
        self.session.mcp_tool_calls.unique_tools = len(all_tools)
        self.session.mcp_tool_calls.most_called = most_called_tool

        # Add server sessions to session
        self.session.server_sessions = self.server_sessions

        # v1.6.0: Multi-model aggregation (task-108.2.3)
        # Collect all calls and aggregate by model
        model_stats: Dict[str, ModelUsage] = {}
        for server_session in self.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    # Use call's model, or fall back to session model, or "unknown"
                    model = call.model or self.session.model or "unknown"
                    if model not in model_stats:
                        model_stats[model] = ModelUsage(model=model)
                    stats = model_stats[model]
                    stats.input_tokens += call.input_tokens
                    stats.output_tokens += call.output_tokens
                    stats.cache_created_tokens += call.cache_created_tokens
                    stats.cache_read_tokens += call.cache_read_tokens
                    stats.total_tokens += call.total_tokens
                    stats.call_count += 1

        # Calculate per-model costs using pricing config if available
        if hasattr(self, "_pricing_config"):
            pricing_config = self._pricing_config
            for model, stats in model_stats.items():
                # Use contextlib.suppress - if pricing fails, cost_usd remains 0.0
                with contextlib.suppress(Exception):
                    stats.cost_usd = pricing_config.calculate_cost(
                        model_name=model,
                        input_tokens=stats.input_tokens,
                        output_tokens=stats.output_tokens,
                        cache_created_tokens=stats.cache_created_tokens,
                        cache_read_tokens=stats.cache_read_tokens,
                    )

        # Set session multi-model fields
        # Ensure primary session model is always included in models_used,
        # even if there are no MCP tool calls (task-123 fix)
        models_used_set = set(model_stats.keys())
        if self.session.model and self.session.model not in models_used_set:
            models_used_set.add(self.session.model)
        self.session.models_used = sorted(models_used_set)

        # Ensure single-model sessions have model_usage populated (task-204 fix)
        # If no MCP tool calls tracked model info but session has tokens, create entry
        if not model_stats and self.session.model and self.session.token_usage.total_tokens > 0:
            session_usage = ModelUsage(
                model=self.session.model,
                input_tokens=self.session.token_usage.input_tokens,
                output_tokens=self.session.token_usage.output_tokens,
                cache_created_tokens=self.session.token_usage.cache_created_tokens,
                cache_read_tokens=self.session.token_usage.cache_read_tokens,
                total_tokens=self.session.token_usage.total_tokens,
                call_count=0,  # Session-level aggregate, no per-call tracking
            )
            # Calculate cost for this model if pricing config available
            if hasattr(self, "_pricing_config"):
                with contextlib.suppress(Exception):
                    session_usage.cost_usd = self._pricing_config.calculate_cost(
                        model_name=self.session.model,
                        input_tokens=session_usage.input_tokens,
                        output_tokens=session_usage.output_tokens,
                        cache_created_tokens=session_usage.cache_created_tokens,
                        cache_read_tokens=session_usage.cache_read_tokens,
                    )
            model_stats[self.session.model] = session_usage

        self.session.model_usage = model_stats

        # Analyze duplicates
        self.session.redundancy_analysis = self._analyze_redundancy()

        # Detect anomalies
        self.session.anomalies = self._detect_anomalies()

        # Detect efficiency smells (v1.5.0 - task-103.1)
        from .smells import detect_smells

        self.session.smells = detect_smells(self.session)

        # Generate recommendations from smells (v0.9.1 - #69)
        from .recommendations import RecommendationEngine

        engine = RecommendationEngine()
        self.session.recommendations = engine.generate(self.session.smells, self.session)

        # Detect zombie tools (v1.5.0 - task-103.4)
        from .zombie_detector import detect_zombie_tools

        self.session.zombie_tools = detect_zombie_tools(self.session)

        # Calculate static cost / context tax (v0.6.0 - task-114.2)
        if self._mcp_config_path:
            from .schema_analyzer import SchemaAnalyzer

            try:
                analyzer = SchemaAnalyzer()
                servers = analyzer.analyze_from_file(self._mcp_config_path)
                self.session.static_cost = analyzer.calculate_static_cost(servers)
            except Exception as e:
                # Log warning but don't fail session finalization
                import logging

                logging.getLogger(__name__).warning(f"Failed to calculate static cost: {e}")

        # Update data_quality pricing fields (v1.6.0 - task-108.3.4)
        # Adapters set _pricing_config, update pricing info if available
        if hasattr(self, "_pricing_config") and self.session.data_quality:
            pricing_config = self._pricing_config
            # Get pricing source from config
            if hasattr(pricing_config, "pricing_source"):
                self.session.data_quality.pricing_source = pricing_config.pricing_source
            # Get freshness from PricingAPI if available
            if hasattr(pricing_config, "_pricing_api") and pricing_config._pricing_api:
                self.session.data_quality.pricing_freshness = pricing_config._pricing_api.freshness
            elif hasattr(pricing_config, "_source"):
                # For file/defaults source, freshness depends on source type
                if pricing_config._source == "file":
                    self.session.data_quality.pricing_freshness = "cached"  # TOML is cached config
                elif pricing_config._source == "defaults":
                    self.session.data_quality.pricing_freshness = (
                        "stale"  # Hardcoded defaults may be outdated
                    )

        return self.session

    def _analyze_redundancy(self) -> Dict[str, Any]:
        """Analyze duplicate tool calls"""
        duplicate_calls = 0
        potential_savings = 0

        for _content_hash, calls in self.content_hashes.items():
            if len(calls) > 1:
                duplicate_calls += len(calls) - 1
                # Calculate savings (all calls after first could be cached)
                for call in calls[1:]:
                    potential_savings += call.total_tokens

        return {"duplicate_calls": duplicate_calls, "potential_savings": potential_savings}

    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect anomalies in tool usage"""
        anomalies = []

        for server_session in self.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                # High frequency (>10 calls)
                if tool_stats.calls > 10:
                    anomalies.append(
                        {
                            "type": "high_frequency",
                            "tool": tool_name,
                            "calls": tool_stats.calls,
                            "threshold": 10,
                        }
                    )

                # High average tokens (>500K per call - task-42.2 AC#2)
                # Note: Claude Code reports cumulative context per call (~120-130K typical)
                # So 500K indicates genuinely expensive operations like thinkdeep/consensus
                if tool_stats.avg_tokens > 500000:
                    anomalies.append(
                        {
                            "type": "high_avg_tokens",
                            "tool": tool_name,
                            "avg_tokens": tool_stats.avg_tokens,
                            "threshold": 500000,
                        }
                    )

        return anomalies

    def _convert_model_usage_for_snapshot(
        self,
    ) -> Optional[List[Tuple[str, int, int, int, int, float, int]]]:
        """Convert session.model_usage dict to tuple format for DisplaySnapshot.

        v1.6.0 (task-108.2.4): Helper to convert ModelUsage objects to the
        flat tuple format expected by DisplaySnapshot.

        Returns:
            List of tuples: (model, input_tokens, output_tokens, total_tokens,
                            cache_read, cost_usd, call_count)
            Returns None if no model_usage data.
        """
        if not self.session.model_usage:
            return None

        result = []
        for model, usage in self.session.model_usage.items():
            # Tuple format: (model, input, output, total_tokens, cache_read, cost, calls)
            # Note: total_tokens = input + output (DisplaySnapshot uses this for sorting)
            total = usage.input_tokens + usage.output_tokens
            result.append(
                (
                    model,
                    usage.input_tokens,
                    usage.output_tokens,
                    total,  # total_tokens for sorting
                    usage.cache_read_tokens,
                    usage.cost_usd,
                    usage.call_count,
                )
            )
        return result

    # ========================================================================
    # High-Level Interface (CLI integration)
    # ========================================================================

    def start(self) -> None:
        """
        Initialize tracking (called before monitor loop).

        Default implementation is a no-op. Subclasses may override
        for any pre-monitoring setup.
        """
        return None  # Intentional no-op: subclasses override as needed

    def monitor(self, display: Optional["DisplayAdapter"] = None) -> None:
        """
        Main monitoring loop with optional display integration.

        Default implementation calls start_tracking() which contains
        the platform-specific monitoring loop. Subclasses should override
        this to integrate display updates.

        Args:
            display: Optional DisplayAdapter for real-time UI updates
        """
        # Store display for use in event processing
        self._display = display
        # Call platform-specific tracking
        self.start_tracking()

    def stop(self) -> Optional[Session]:
        """
        Stop tracking and finalize session.

        Returns:
            Finalized Session object, or None if no data collected
        """
        session = self.finalize_session()

        # Save session data using configured output directory
        self.save_session(self.output_dir)

        return session

    # ========================================================================
    # Persistence (Shared implementation)
    # ========================================================================

    def save_session(self, output_dir: Optional[Path] = None) -> None:
        """
        Save session data to disk using v1.0.4 format.

        v1.0.4 Changes:
        - Date subdirectories: ~/.token-audit/sessions/YYYY-MM-DD/
        - Single file per session: <project>-<timestamp>.json
        - Self-describing _file header block
        - Flat tool_calls array (no separate mcp-*.json files)

        Args:
            output_dir: Base directory for sessions (default: ~/.token-audit/sessions)
        """
        # Use default path if not specified
        if output_dir is None:
            output_dir = Path.home() / ".token-audit" / "sessions"

        # Ensure base directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create platform/date subdirectory structure
        # e.g., ~/.token-audit/sessions/codex-cli/2025-12-04/
        date_str = self.timestamp.strftime("%Y-%m-%d")
        platform_dir = output_dir / self.platform
        date_dir = platform_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        # Generate file name: <project>-<timestamp>.json
        # Use safe timestamp format for filenames (no colons)
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%S")
        file_name = f"{self.project}-{timestamp_str}.json"
        session_path = date_dir / file_name

        # Store session_dir for reference (point to date dir, file is single file)
        self.session_dir = date_dir
        self.session_path = session_path  # Full path to session file

        # Build the _file header
        file_header = FileHeader(
            name=file_name,
            type="token_audit_session",
            purpose=(
                "Complete MCP session log with token usage and tool call statistics "
                "for AI agent analysis"
            ),
            schema_version=SCHEMA_VERSION,
            schema_docs="https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
            generated_by=f"token-audit v{__version__}",
            generated_at=_format_timestamp(_now_with_timezone()),
        )

        # Get session data and inject _file header
        session_data = self.session.to_dict()
        session_data["_file"] = file_header.to_dict()

        # Save as single JSON file
        with open(session_path, "w") as f:
            json.dump(session_data, f, indent=2, default=str)

        # Note: v1.0.4 removes separate mcp-*.json files - all data in single file

    # ========================================================================
    # Unrecognized Line Handler (Shared implementation)
    # ========================================================================

    def handle_unrecognized_line(self, line: str) -> None:
        """
        Handle unrecognized event lines gracefully.

        Args:
            line: Unrecognized event line
        """
        # Log warning but don't crash
        warnings.warn(f"Unrecognized event format: {line[:100]}...", stacklevel=2)

    # ========================================================================
    # Utility Methods
    # ========================================================================

    @staticmethod
    def compute_content_hash(input_data: Any) -> str:
        """
        Compute SHA256 hash of input data for duplicate detection.

        Args:
            input_data: Tool input parameters

        Returns:
            SHA256 hash string
        """
        # Convert to stable JSON string
        json_str = json.dumps(input_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
