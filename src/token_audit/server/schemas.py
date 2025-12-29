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


# ============================================================================
# Tool 9: get_daily_summary (v1.0.2)
# ============================================================================


class TrendDirection(str, Enum):
    """Trend direction for usage summaries."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class DailyUsageEntry(BaseModel):
    """Single day's usage data."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    sessions: int = Field(description="Number of sessions")
    input_tokens: int = Field(description="Input tokens consumed")
    output_tokens: int = Field(description="Output tokens generated")
    total_tokens: int = Field(description="Total tokens")
    cost_usd: float = Field(description="Cost in USD")
    model_breakdown: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Per-model breakdown (if requested)",
    )


class UsageTrends(BaseModel):
    """Trend analysis for usage data."""

    direction: TrendDirection = Field(description="Overall trend direction")
    change_percent: float = Field(description="Percentage change")
    busiest_day: Optional[str] = Field(
        default=None,
        description="Date with highest usage (YYYY-MM-DD)",
    )
    avg_daily_cost: float = Field(description="Average daily cost in USD")


class GetDailySummaryInput(BaseModel):
    """Input schema for get_daily_summary tool."""

    days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Number of days to include (default: 7)",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Filter by platform (all platforms if not specified)",
    )
    project: Optional[str] = Field(
        default=None,
        description="Filter by project name",
    )
    breakdown: bool = Field(
        default=False,
        description="Include per-model token breakdown",
    )


class UsagePeriod(BaseModel):
    """Period information for usage summaries."""

    start: str = Field(description="Start date (YYYY-MM-DD)")
    end: str = Field(description="End date (YYYY-MM-DD)")
    days: Optional[int] = Field(default=None, description="Number of days")
    weeks: Optional[int] = Field(default=None, description="Number of weeks")
    months: Optional[int] = Field(default=None, description="Number of months")


class UsageTotals(BaseModel):
    """Aggregated totals for usage summaries."""

    sessions: int = Field(description="Total sessions")
    input_tokens: int = Field(description="Total input tokens")
    output_tokens: int = Field(description="Total output tokens")
    total_tokens: int = Field(description="Total tokens")
    cost_usd: float = Field(description="Total cost in USD")


class GetDailySummaryOutput(BaseModel):
    """Output schema for get_daily_summary tool."""

    period: UsagePeriod = Field(description="Period covered")
    totals: UsageTotals = Field(description="Aggregated totals")
    daily: List[DailyUsageEntry] = Field(
        default_factory=list,
        description="Per-day breakdown",
    )
    trends: UsageTrends = Field(description="Trend analysis")


# ============================================================================
# Tool 10: get_weekly_summary (v1.0.2)
# ============================================================================


class WeeklyUsageEntry(BaseModel):
    """Single week's usage data."""

    week_start: str = Field(description="Week start date (YYYY-MM-DD)")
    week_end: str = Field(description="Week end date (YYYY-MM-DD)")
    sessions: int = Field(description="Number of sessions")
    input_tokens: int = Field(description="Input tokens consumed")
    output_tokens: int = Field(description="Output tokens generated")
    total_tokens: int = Field(description="Total tokens")
    cost_usd: float = Field(description="Cost in USD")
    avg_session_cost: float = Field(description="Average cost per session")
    model_breakdown: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Per-model breakdown (if requested)",
    )


class WeekStartDay(str, Enum):
    """Day of week for week boundary."""

    MONDAY = "monday"
    SUNDAY = "sunday"


class GetWeeklySummaryInput(BaseModel):
    """Input schema for get_weekly_summary tool."""

    weeks: int = Field(
        default=4,
        ge=1,
        le=52,
        description="Number of weeks to include (default: 4)",
    )
    start_of_week: WeekStartDay = Field(
        default=WeekStartDay.MONDAY,
        description="Week boundary (Monday or Sunday)",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Filter by platform (all platforms if not specified)",
    )
    breakdown: bool = Field(
        default=False,
        description="Include per-model token breakdown",
    )


class GetWeeklySummaryOutput(BaseModel):
    """Output schema for get_weekly_summary tool."""

    period: UsagePeriod = Field(description="Period covered")
    totals: UsageTotals = Field(description="Aggregated totals")
    weekly: List[WeeklyUsageEntry] = Field(
        default_factory=list,
        description="Per-week breakdown",
    )
    trends: UsageTrends = Field(description="Trend analysis")


# ============================================================================
# Tool 11: get_monthly_summary (v1.0.2)
# ============================================================================


class MonthlyUsageEntry(BaseModel):
    """Single month's usage data."""

    month: str = Field(description="Month in YYYY-MM format")
    sessions: int = Field(description="Number of sessions")
    input_tokens: int = Field(description="Input tokens consumed")
    output_tokens: int = Field(description="Output tokens generated")
    total_tokens: int = Field(description="Total tokens")
    cost_usd: float = Field(description="Cost in USD")
    model_breakdown: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Per-model breakdown (if requested)",
    )


class GetMonthlySummaryInput(BaseModel):
    """Input schema for get_monthly_summary tool."""

    months: int = Field(
        default=3,
        ge=1,
        le=24,
        description="Number of months to include (default: 3)",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Filter by platform (all platforms if not specified)",
    )
    breakdown: bool = Field(
        default=False,
        description="Include per-model token breakdown",
    )


class GetMonthlySummaryOutput(BaseModel):
    """Output schema for get_monthly_summary tool."""

    period: UsagePeriod = Field(description="Period covered")
    totals: UsageTotals = Field(description="Aggregated totals")
    monthly: List[MonthlyUsageEntry] = Field(
        default_factory=list,
        description="Per-month breakdown",
    )
    trends: UsageTrends = Field(description="Trend analysis")


# ============================================================================
# Tool 12: list_sessions (v1.0.2)
# ============================================================================


class SessionSortBy(str, Enum):
    """Sort options for session listing."""

    DATE = "date"
    COST = "cost"
    TOKENS = "tokens"
    DURATION = "duration"


class SortOrder(str, Enum):
    """Sort order."""

    ASC = "asc"
    DESC = "desc"


class DataQuality(str, Enum):
    """Data quality level."""

    EXACT = "exact"
    ESTIMATED = "estimated"
    CALLS_ONLY = "calls-only"


class ListSessionsInput(BaseModel):
    """Input schema for list_sessions tool."""

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum sessions to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Pagination offset",
    )
    platform: Optional[ServerPlatform] = Field(
        default=None,
        description="Filter by platform",
    )
    project: Optional[str] = Field(
        default=None,
        description="Filter by project name",
    )
    since: Optional[str] = Field(
        default=None,
        description="Only sessions after this date (YYYY-MM-DD)",
    )
    until: Optional[str] = Field(
        default=None,
        description="Only sessions before this date (YYYY-MM-DD)",
    )
    sort_by: SessionSortBy = Field(
        default=SessionSortBy.DATE,
        description="Sort field",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.DESC,
        description="Sort order",
    )


class SessionListEntry(BaseModel):
    """Summary entry for a session in list view."""

    session_id: str = Field(description="Unique session identifier")
    platform: str = Field(description="Platform (claude_code, codex_cli, gemini_cli)")
    project: Optional[str] = Field(default=None, description="Project name")
    started_at: str = Field(description="Start timestamp (ISO 8601)")
    ended_at: Optional[str] = Field(default=None, description="End timestamp (ISO 8601)")
    duration_seconds: int = Field(description="Session duration in seconds")
    total_tokens: int = Field(description="Total tokens used")
    cost_usd: float = Field(description="Session cost in USD")
    model: Optional[str] = Field(default=None, description="Primary model used")
    tool_calls: int = Field(description="Number of tool calls")
    smells_detected: int = Field(description="Number of efficiency smells detected")
    data_quality: DataQuality = Field(description="Data accuracy level")


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    total: int = Field(description="Total matching sessions")
    limit: int = Field(description="Requested limit")
    offset: int = Field(description="Current offset")
    has_more: bool = Field(description="Whether more results exist")


class ListSessionsOutput(BaseModel):
    """Output schema for list_sessions tool."""

    sessions: List[SessionListEntry] = Field(
        default_factory=list,
        description="Session summaries",
    )
    pagination: PaginationInfo = Field(description="Pagination info")


# ============================================================================
# Tool 13: get_session_details (v1.0.2)
# ============================================================================


class GetSessionDetailsInput(BaseModel):
    """Input schema for get_session_details tool."""

    session_id: str = Field(description="Session ID to retrieve")
    include_tool_calls: bool = Field(
        default=True,
        description="Include individual tool call details",
    )
    include_smells: bool = Field(
        default=True,
        description="Include detected efficiency smells",
    )
    include_recommendations: bool = Field(
        default=True,
        description="Include optimization recommendations",
    )


class SessionMetadata(BaseModel):
    """Session metadata."""

    session_id: str = Field(description="Unique session identifier")
    platform: str = Field(description="Platform")
    project: Optional[str] = Field(default=None, description="Project name")
    started_at: str = Field(description="Start timestamp (ISO 8601)")
    ended_at: Optional[str] = Field(default=None, description="End timestamp (ISO 8601)")
    duration_seconds: int = Field(description="Duration in seconds")
    model: Optional[str] = Field(default=None, description="Primary model")
    models_used: List[str] = Field(
        default_factory=list,
        description="All models used in session",
    )


class SessionTokenUsage(BaseModel):
    """Detailed token usage for a session."""

    input_tokens: int = Field(description="Input tokens")
    output_tokens: int = Field(description="Output tokens")
    cache_read_tokens: int = Field(default=0, description="Cache read tokens")
    cache_write_tokens: int = Field(default=0, description="Cache write tokens")
    reasoning_tokens: int = Field(default=0, description="Reasoning tokens")
    total_tokens: int = Field(description="Total tokens")
    cost_usd: float = Field(description="Total cost in USD")


class ServerUsage(BaseModel):
    """MCP server usage within a session."""

    name: str = Field(description="Server name")
    tools_used: int = Field(description="Number of unique tools used")
    total_calls: int = Field(description="Total tool calls")
    total_tokens: int = Field(description="Estimated tokens for this server")


class TopTool(BaseModel):
    """Top tool usage."""

    name: str = Field(description="Tool name")
    calls: int = Field(description="Number of calls")
    tokens: int = Field(description="Total tokens")
    avg_tokens: float = Field(description="Average tokens per call")


class MCPUsage(BaseModel):
    """MCP usage breakdown."""

    servers: List[ServerUsage] = Field(
        default_factory=list,
        description="Per-server usage",
    )
    top_tools: List[TopTool] = Field(
        default_factory=list,
        description="Most used tools",
    )


class ToolCallEntry(BaseModel):
    """Individual tool call record."""

    timestamp: str = Field(description="Call timestamp (ISO 8601)")
    tool_name: str = Field(description="Tool name")
    server: str = Field(description="MCP server name")
    tokens_in: int = Field(description="Input tokens for this call")
    tokens_out: int = Field(description="Output tokens for this call")
    is_estimated: bool = Field(default=False, description="Whether tokens are estimated")


class SmellEntry(BaseModel):
    """Detected efficiency smell."""

    pattern: str = Field(description="Smell pattern identifier")
    severity: SeverityLevel = Field(description="Severity level")
    message: str = Field(description="Human-readable message")
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting evidence",
    )


class DataQualityInfo(BaseModel):
    """Data quality information."""

    accuracy_level: DataQuality = Field(description="Data accuracy level")
    pricing_source: str = Field(description="Source of pricing data")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0)",
    )


class GetSessionDetailsOutput(BaseModel):
    """Output schema for get_session_details tool."""

    session: SessionMetadata = Field(description="Session metadata")
    token_usage: SessionTokenUsage = Field(description="Token usage details")
    mcp_usage: MCPUsage = Field(description="MCP server and tool usage")
    tool_calls: List[ToolCallEntry] = Field(
        default_factory=list,
        description="Individual tool calls (if requested)",
    )
    smells: List[SmellEntry] = Field(
        default_factory=list,
        description="Detected smells (if requested)",
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Optimization recommendations (if requested)",
    )
    data_quality: DataQualityInfo = Field(description="Data quality metadata")


# ============================================================================
# Tool 14: pin_server (v1.0.2)
# ============================================================================


class PinAction(str, Enum):
    """Pin action."""

    PIN = "pin"
    UNPIN = "unpin"


class PinServerInput(BaseModel):
    """Input schema for pin_server tool."""

    server_name: str = Field(description="MCP server name to pin/unpin")
    notes: Optional[str] = Field(
        default=None,
        description="Optional notes about why this server is pinned",
    )
    action: PinAction = Field(
        default=PinAction.PIN,
        description="Pin or unpin the server",
    )


class PinServerOutput(BaseModel):
    """Output schema for pin_server tool."""

    success: bool = Field(description="Whether operation succeeded")
    action: PinAction = Field(description="Action performed")
    server_name: str = Field(description="Server name")
    message: str = Field(description="Human-readable result message")
    pinned_servers: List[str] = Field(
        default_factory=list,
        description="Updated list of all pinned server names",
    )


# ============================================================================
# Tool 15: delete_session (v1.0.2)
# ============================================================================


class DeleteSessionInput(BaseModel):
    """Input schema for delete_session tool."""

    session_id: str = Field(description="Session ID to delete")
    confirm: bool = Field(
        default=False,
        description="Must be true to confirm deletion (safety check)",
    )


class DeleteSessionOutput(BaseModel):
    """Output schema for delete_session tool."""

    success: bool = Field(description="Whether deletion succeeded")
    session_id: str = Field(description="Session ID")
    message: str = Field(description="Human-readable result message")
    deleted_at: Optional[str] = Field(
        default=None,
        description="Deletion timestamp (ISO 8601)",
    )


# ============================================================================
# Tool 16: config_list_patterns (v1.0.4 - bucket configuration)
# ============================================================================


class ConfigListPatternsOutput(BaseModel):
    """Output schema for config_list_patterns tool."""

    patterns: Dict[str, List[str]] = Field(description="Mapping of bucket names to regex patterns")
    thresholds: Dict[str, int] = Field(
        description="Threshold settings (large_payload_threshold, redundant_min_occurrences)"
    )
    config_path: Optional[str] = Field(
        default=None,
        description="Path to loaded config file (None if using defaults)",
    )


# ============================================================================
# Tool 17: config_add_pattern (v1.0.4 - bucket configuration)
# ============================================================================


class ConfigAddPatternInput(BaseModel):
    """Input schema for config_add_pattern tool."""

    bucket: str = Field(description="Bucket name: 'state_serialization' or 'tool_discovery'")
    pattern: str = Field(description="Regex pattern to add (e.g., '.*_get_.*')")


class ConfigAddPatternOutput(BaseModel):
    """Output schema for config_add_pattern tool."""

    success: bool = Field(description="Whether pattern was added successfully")
    message: str = Field(description="Human-readable result message")
    bucket: str = Field(description="Bucket the pattern was added to")
    patterns: List[str] = Field(
        default_factory=list,
        description="Updated list of patterns for this bucket",
    )


# ============================================================================
# Tool 18: config_remove_pattern (v1.0.4 - bucket configuration)
# ============================================================================


class ConfigRemovePatternInput(BaseModel):
    """Input schema for config_remove_pattern tool."""

    bucket: str = Field(description="Bucket name: 'state_serialization' or 'tool_discovery'")
    pattern: str = Field(description="Exact regex pattern to remove")


class ConfigRemovePatternOutput(BaseModel):
    """Output schema for config_remove_pattern tool."""

    success: bool = Field(description="Whether pattern was removed successfully")
    message: str = Field(description="Human-readable result message")
    bucket: str = Field(description="Bucket the pattern was removed from")
    patterns: List[str] = Field(
        default_factory=list,
        description="Updated list of patterns for this bucket",
    )


# ============================================================================
# Tool 19: config_set_threshold (v1.0.4 - bucket configuration)
# ============================================================================


class ThresholdName(str, Enum):
    """Valid threshold names for configuration."""

    LARGE_PAYLOAD = "large_payload_threshold"
    REDUNDANT_MIN = "redundant_min_occurrences"


class ConfigSetThresholdInput(BaseModel):
    """Input schema for config_set_threshold tool."""

    name: ThresholdName = Field(
        description="Threshold name: 'large_payload_threshold' or 'redundant_min_occurrences'"
    )
    value: int = Field(
        ge=1,
        description="New threshold value (must be positive integer)",
    )


class ConfigSetThresholdOutput(BaseModel):
    """Output schema for config_set_threshold tool."""

    success: bool = Field(description="Whether threshold was set successfully")
    message: str = Field(description="Human-readable result message")
    thresholds: Dict[str, int] = Field(description="Updated threshold settings")


# ============================================================================
# Tool 20: bucket_analyze (v1.0.4 - bucket classification)
# ============================================================================


class BucketStats(BaseModel):
    """Statistics for a single bucket."""

    count: int = Field(description="Number of tool calls in this bucket")
    tokens: int = Field(description="Total tokens in this bucket")
    percentage: float = Field(description="Percentage of total tokens")
    tools: List[str] = Field(
        default_factory=list,
        description="List of tool names in this bucket (top 10)",
    )


class BucketAnalyzeInput(BaseModel):
    """Input schema for bucket_analyze tool."""

    session_id: Optional[str] = Field(
        default=None,
        description="Session ID to analyze (uses latest if not specified)",
    )
    include_tools: bool = Field(
        default=True,
        description="Include list of tools per bucket",
    )


class BucketAnalyzeOutput(BaseModel):
    """Output schema for bucket_analyze tool."""

    success: bool = Field(description="Whether analysis succeeded")
    session_id: str = Field(description="Session ID that was analyzed")
    buckets: Dict[str, BucketStats] = Field(
        description="Stats for each bucket (state_serialization, tool_discovery, redundant, drift)"
    )
    total_tokens: int = Field(description="Total tokens across all buckets")
    total_calls: int = Field(description="Total tool calls analyzed")
    summary: str = Field(description="Human-readable summary of bucket distribution")
    message: Optional[str] = Field(
        default=None,
        description="Additional message (e.g., error details)",
    )
