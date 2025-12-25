"""
Pydantic schemas for MCP server tool inputs and outputs.

Defines structured data models for all 8 MCP tools, enabling
type-safe validation and structured output responses.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Platform enum - matches storage.Platform but with user-friendly values
class ServerPlatform(str, Enum):
    """Supported AI coding platforms."""

    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    GEMINI_CLI = "gemini_cli"


class SeverityLevel(str, Enum):
    """Severity levels for smells and recommendations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class TrendPeriod(str, Enum):
    """Time periods for trend analysis."""

    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    ALL_TIME = "all_time"


class ReportFormat(str, Enum):
    """Output formats for session analysis."""

    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"


# ============================================================================
# Tool 1: start_tracking
# ============================================================================


class StartTrackingInput(BaseModel):
    """Input schema for start_tracking tool."""

    platform: ServerPlatform = Field(
        description="AI coding platform to track (claude_code, codex_cli, gemini_cli)"
    )
    project: Optional[str] = Field(
        default=None,
        description="Project name for grouping sessions (optional)",
    )


class StartTrackingOutput(BaseModel):
    """Output schema for start_tracking tool."""

    session_id: str = Field(description="Unique identifier for the tracking session")
    platform: str = Field(description="Platform being tracked")
    project: Optional[str] = Field(description="Project name if specified")
    started_at: str = Field(description="ISO 8601 timestamp when tracking started")
    status: Literal["active", "error"] = Field(description="Tracking status")
    message: str = Field(description="Human-readable status message")


# ============================================================================
# Tool 2: get_metrics
# ============================================================================


class GetMetricsInput(BaseModel):
    """Input schema for get_metrics tool."""

    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to query (uses active session if not specified)",
    )
    include_smells: bool = Field(
        default=True,
        description="Include detected efficiency issues",
    )
    include_breakdown: bool = Field(
        default=True,
        description="Include per-tool and per-server token breakdown",
    )


class TokenMetrics(BaseModel):
    """Token usage metrics."""

    input: int = Field(description="Input tokens consumed")
    output: int = Field(description="Output tokens generated")
    cache_read: int = Field(default=0, description="Tokens read from cache")
    cache_write: int = Field(default=0, description="Tokens written to cache")
    total: int = Field(description="Total tokens (input + output)")


class RateMetrics(BaseModel):
    """Rate-based metrics."""

    tokens_per_min: float = Field(description="Token consumption rate")
    calls_per_min: float = Field(description="Tool call rate")
    duration_minutes: float = Field(description="Session duration in minutes")


class CacheMetrics(BaseModel):
    """Cache efficiency metrics."""

    hit_ratio: float = Field(description="Cache hit ratio (0.0 to 1.0)")
    savings_tokens: int = Field(description="Tokens saved by caching")
    savings_usd: float = Field(description="Cost savings from caching in USD")


class SmellSummary(BaseModel):
    """Summary of a detected smell."""

    pattern: str = Field(description="Smell pattern identifier")
    severity: SeverityLevel = Field(description="Severity level")
    tool: Optional[str] = Field(description="Tool involved (if applicable)")
    description: str = Field(description="Human-readable description")


class GetMetricsOutput(BaseModel):
    """Output schema for get_metrics tool."""

    session_id: str = Field(description="Session being reported")
    tokens: TokenMetrics = Field(description="Token usage breakdown")
    cost_usd: float = Field(description="Estimated cost in USD")
    rates: RateMetrics = Field(description="Rate-based metrics")
    cache: CacheMetrics = Field(description="Cache efficiency metrics")
    smells: List[SmellSummary] = Field(
        default_factory=list,
        description="Detected efficiency issues",
    )
    tool_count: int = Field(description="Number of unique tools used")
    call_count: int = Field(description="Total tool calls")
    model_usage: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-model token and call breakdown",
    )


# ============================================================================
# Tool 3: get_recommendations
# ============================================================================


class GetRecommendationsInput(BaseModel):
    """Input schema for get_recommendations tool."""

    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to analyze (uses active session if not specified)",
    )
    severity_filter: Optional[SeverityLevel] = Field(
        default=None,
        description="Minimum severity level to include",
    )
    max_recommendations: int = Field(
        default=5,
        description="Maximum number of recommendations to return",
    )


class Recommendation(BaseModel):
    """A single optimization recommendation."""

    id: str = Field(description="Unique recommendation identifier")
    severity: SeverityLevel = Field(description="Severity level")
    category: str = Field(description="Recommendation category")
    title: str = Field(description="Short title")
    action: str = Field(description="Recommended action to take")
    impact: str = Field(description="Expected impact of taking action")
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting evidence and metrics",
    )
    confidence: float = Field(
        description="Confidence score (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    affects_pinned_server: bool = Field(
        default=False,
        description="Whether this recommendation affects a pinned server",
    )
    pinned_server_name: Optional[str] = Field(
        default=None,
        description="Name of the affected pinned server (if any)",
    )


class GetRecommendationsOutput(BaseModel):
    """Output schema for get_recommendations tool."""

    session_id: str = Field(description="Session analyzed")
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Prioritized list of recommendations",
    )
    total_potential_savings_tokens: int = Field(
        default=0,
        description="Estimated token savings if all recommendations applied",
    )
    total_potential_savings_usd: float = Field(
        default=0.0,
        description="Estimated cost savings if all recommendations applied",
    )


# ============================================================================
# Tool 4: analyze_session
# ============================================================================


class AnalyzeSessionInput(BaseModel):
    """Input schema for analyze_session tool."""

    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to analyze (uses active session if not specified)",
    )
    format: ReportFormat = Field(
        default=ReportFormat.JSON,
        description="Output format for the analysis",
    )
    include_model_usage: bool = Field(
        default=True,
        description="Include per-model breakdown",
    )
    include_zombie_tools: bool = Field(
        default=True,
        description="Include unused tool analysis",
    )


class PinnedServerUsage(BaseModel):
    """Usage statistics for a pinned server in a session."""

    name: str = Field(description="Server name")
    calls: int = Field(description="Number of tool calls to this server")
    tokens: int = Field(default=0, description="Estimated tokens consumed by this server")
    percentage: float = Field(
        default=0.0,
        description="Percentage of total session calls (0.0 to 100.0)",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the server was actually used in this session",
    )


class ZombieTool(BaseModel):
    """An unused (zombie) tool that was available but never called."""

    tool_name: str = Field(description="Tool name")
    server: str = Field(description="MCP server providing the tool")
    schema_tokens: int = Field(description="Tokens consumed by tool schema")


class AnalyzeSessionOutput(BaseModel):
    """Output schema for analyze_session tool."""

    session_id: str = Field(description="Session analyzed")
    summary: str = Field(description="Human-readable summary")
    metrics: GetMetricsOutput = Field(description="Full metrics")
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Optimization recommendations",
    )
    zombie_tools: List[ZombieTool] = Field(
        default_factory=list,
        description="Tools available but never used",
    )
    model_usage: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-model usage breakdown",
    )
    pinned_server_usage: List[PinnedServerUsage] = Field(
        default_factory=list,
        description="Usage statistics for pinned servers",
    )


# ============================================================================
# Tool 5: get_best_practices
# ============================================================================


class GetBestPracticesInput(BaseModel):
    """Input schema for get_best_practices tool."""

    topic: Optional[str] = Field(
        default=None,
        description="Topic to search for (e.g., 'caching', 'progressive disclosure')",
    )
    list_all: bool = Field(
        default=False,
        description="List all available best practice topics",
    )


class BestPractice(BaseModel):
    """A single best practice entry."""

    id: str = Field(description="Best practice identifier")
    title: str = Field(description="Best practice title")
    severity: SeverityLevel = Field(description="Importance level")
    category: str = Field(
        default="general",
        description="Category (efficiency, security, design, operations)",
    )
    token_savings: Optional[str] = Field(
        default=None,
        description="Estimated token savings (e.g., '98%')",
    )
    source: Optional[str] = Field(
        default=None,
        description="Source or reference for this practice",
    )
    content: str = Field(description="Full markdown content")
    keywords: List[str] = Field(
        default_factory=list,
        description="Related keywords for search",
    )
    related_smells: List[str] = Field(
        default_factory=list,
        description="Smell patterns this practice addresses",
    )


class GetBestPracticesOutput(BaseModel):
    """Output schema for get_best_practices tool."""

    practices: List[BestPractice] = Field(
        default_factory=list,
        description="Matching best practices",
    )
    total_available: int = Field(description="Total best practices in database")


# ============================================================================
# Tool 6: analyze_config
# ============================================================================


class AnalyzeConfigInput(BaseModel):
    """Input schema for analyze_config tool."""

    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Platform to analyze (analyzes all if not specified)",
    )
    config_path: Optional[str] = Field(
        default=None,
        description="Custom config file path (uses default location if not specified)",
    )


class ConfigIssue(BaseModel):
    """An issue detected in MCP configuration."""

    severity: SeverityLevel = Field(description="Issue severity")
    category: str = Field(description="Issue category")
    message: str = Field(description="Human-readable description")
    location: str = Field(description="Config file and key path")
    recommendation: str = Field(description="How to fix the issue")


class ServerInfo(BaseModel):
    """Information about a configured MCP server."""

    name: str = Field(description="Server name")
    command: str = Field(description="Server command")
    is_pinned: bool = Field(default=False, description="Whether server is pinned")
    tool_count: Optional[int] = Field(
        default=None,
        description="Number of tools (if known)",
    )


class PinnedServerInfo(BaseModel):
    """Pinned server with detection details for analyze_config output."""

    name: str = Field(description="Server name")
    source: str = Field(
        description="Detection method: explicit_config, explicit_flag, custom_path, usage_frequency"
    )
    reason: str = Field(description="Human-readable explanation of why server is pinned")


class AnalyzeConfigOutput(BaseModel):
    """Output schema for analyze_config tool."""

    platform: Optional[str] = Field(description="Platform analyzed")
    config_path: str = Field(description="Config file path")
    issues: List[ConfigIssue] = Field(
        default_factory=list,
        description="Detected issues",
    )
    servers: List[ServerInfo] = Field(
        default_factory=list,
        description="Configured servers",
    )
    server_count: int = Field(description="Total number of servers")
    pinned_servers: List[PinnedServerInfo] = Field(
        default_factory=list,
        description="Pinned servers with detection details",
    )
    context_tax_estimate: int = Field(
        default=0,
        description="Estimated tokens consumed by all server schemas (context tax)",
    )


# ============================================================================
# Tool 7: get_pinned_servers
# ============================================================================


class GetPinnedServersInput(BaseModel):
    """Input schema for get_pinned_servers tool."""

    include_auto_detected: bool = Field(
        default=True,
        description="Include auto-detected pinned servers (auto_detect_local and high_usage methods)",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Platform to analyze (analyzes all discovered if not specified)",
    )


class PinnedServer(BaseModel):
    """A pinned MCP server for focused analysis."""

    name: str = Field(description="Server name")
    source: str = Field(description="Detection source: auto_detect_local, explicit, high_usage")
    reason: str = Field(description="Human-readable explanation of why server is pinned")
    path: Optional[str] = Field(default=None, description="Server path if local/custom")
    notes: Optional[str] = Field(default=None, description="User notes")
    token_share: Optional[float] = Field(
        default=None,
        description="Token share for high_usage detection (0.0 to 1.0)",
    )


class GetPinnedServersOutput(BaseModel):
    """Output schema for get_pinned_servers tool."""

    servers: List[PinnedServerInfo] = Field(
        default_factory=list,
        description="Pinned servers with detection details",
    )
    total_pinned: int = Field(description="Total pinned servers")
    auto_detect_enabled: bool = Field(description="Whether auto-detection is enabled")


# ============================================================================
# Tool 8: get_trends
# ============================================================================


class GetTrendsInput(BaseModel):
    """Input schema for get_trends tool."""

    period: TrendPeriod = Field(
        default=TrendPeriod.LAST_30_DAYS,
        description="Time period for trend analysis",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Filter by platform (all platforms if not specified)",
    )


class SmellTrend(BaseModel):
    """Trend data for a smell pattern."""

    pattern: str = Field(description="Smell pattern identifier")
    occurrences: int = Field(description="Number of occurrences in period")
    trend: Literal["improving", "stable", "worsening"] = Field(description="Trend direction")
    change_percent: float = Field(description="Percentage change from previous period")


class GetTrendsOutput(BaseModel):
    """Output schema for get_trends tool."""

    period: str = Field(description="Analysis period")
    sessions_analyzed: int = Field(description="Number of sessions in period")
    patterns: List[SmellTrend] = Field(
        default_factory=list,
        description="Trend data per smell pattern",
    )
    top_affected_tools: List[str] = Field(
        default_factory=list,
        description="Tools most frequently involved in issues",
    )
    overall_trend: Literal["improving", "stable", "worsening"] = Field(
        description="Overall efficiency trend"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="High-level recommendations based on trends",
    )
