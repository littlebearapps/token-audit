"""
MCP tool implementations for token-audit server.

This module contains all 20 MCP tools:
- start_tracking (implemented)
- get_metrics (implemented)
- get_recommendations (implemented)
- analyze_session (implemented)
- get_best_practices (implemented)
- analyze_config (implemented)
- get_pinned_servers (implemented)
- get_trends (implemented)
- get_daily_summary (v1.0.2)
- get_weekly_summary (v1.0.2)
- get_monthly_summary (v1.0.2)
- list_sessions (v1.0.2)
- get_session_details (v1.0.2)
- pin_server (v1.0.2)
- delete_session (v1.0.2)
- config_list_patterns (v1.0.4)
- config_add_pattern (v1.0.4)
- config_remove_pattern (v1.0.4)
- config_set_threshold (v1.0.4)
- bucket_analyze (v1.0.4)
"""

import contextlib
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Set, Tuple, cast

from ..base_tracker import Smell
from ..config_analyzer import (
    SOURCE_EXPLICIT,
    PinnedServerDetector,
    ServerConfig,
    detect_pinned_servers,
    discover_existing_configs,
    parse_config,
)
from ..config_analyzer import (
    ConfigIssue as ModuleConfigIssue,
)
from ..config_analyzer import (
    PinnedServer as ModulePinnedServer,
)
from ..config_analyzer import (
    analyze_config as module_analyze_config,
)
from ..guidance import BestPracticesLoader
from ..pinned_config import PinnedConfigManager
from ..pricing_config import PricingConfig
from ..recommendations import Recommendation as InternalRecommendation
from ..recommendations import RecommendationEngine
from ..schema_analyzer import SchemaAnalyzer
from ..smell_aggregator import AggregatedSmell, SmellAggregator
from ..storage import Platform
from ..zombie_detector import load_zombie_config
from .live_tracker import LiveTracker
from .schemas import (
    AnalyzeConfigOutput,
    AnalyzeSessionOutput,
    BestPractice,
    BucketAnalyzeOutput,
    BucketStats,
    CacheMetrics,
    ConfigAddPatternOutput,
    ConfigIssue,
    ConfigListPatternsOutput,
    ConfigRemovePatternOutput,
    ConfigSetThresholdOutput,
    DailyUsageEntry,
    DataQuality,
    DataQualityInfo,
    DeleteSessionOutput,
    GetBestPracticesOutput,
    GetDailySummaryOutput,
    GetMetricsOutput,
    GetMonthlySummaryOutput,
    GetPinnedServersOutput,
    GetRecommendationsOutput,
    GetSessionDetailsOutput,
    GetTrendsOutput,
    GetWeeklySummaryOutput,
    ListSessionsOutput,
    MCPUsage,
    MonthlyUsageEntry,
    PaginationInfo,
    PinAction,
    PinnedServerInfo,
    PinnedServerUsage,
    PinServerOutput,
    RateMetrics,
    Recommendation,
    ReportFormat,
    ServerInfo,
    ServerPlatform,
    ServerUsage,
    SessionListEntry,
    SessionMetadata,
    SessionSortBy,
    SessionTokenUsage,
    SeverityLevel,
    SmellEntry,
    SmellSummary,
    SmellTrend,
    SortOrder,
    StartTrackingOutput,
    TokenMetrics,
    ToolCallEntry,
    TopTool,
    TrendDirection,
    TrendPeriod,
    UsagePeriod,
    UsageTotals,
    UsageTrends,
    WeeklyUsageEntry,
    WeekStartDay,
    ZombieTool,
)
from .security import sanitize_error_message, sanitize_path_for_output, validate_config_path

if TYPE_CHECKING:
    from .live_tracker import LiveSession

# Global tracker instance - manages active sessions
_tracker = LiveTracker()

# Global best practices loader - cached singleton
_best_practices_loader: Optional[BestPracticesLoader] = None

# Global pricing config - cached singleton
_pricing_config: Optional[PricingConfig] = None


def get_tracker() -> LiveTracker:
    """Get the global LiveTracker instance."""
    return _tracker


def _get_best_practices_loader() -> BestPracticesLoader:
    """Get the global BestPracticesLoader instance (cached singleton)."""
    global _best_practices_loader
    if _best_practices_loader is None:
        _best_practices_loader = BestPracticesLoader()
    return _best_practices_loader


def _get_pricing_config() -> PricingConfig:
    """Get the global PricingConfig instance (cached singleton)."""
    global _pricing_config
    if _pricing_config is None:
        _pricing_config = PricingConfig()
    return _pricing_config


def _calculate_cache_savings(session: "LiveSession") -> float:
    """Calculate USD saved by cache hits vs uncached input pricing.

    Uses per-model pricing when available. Falls back to a conservative
    default rate (Claude Sonnet's savings rate) for sessions without
    per-model cache tracking or when pricing isn't available.

    Args:
        session: LiveSession with model_usage data

    Returns:
        Cache savings in USD
    """
    pricing = _get_pricing_config()
    total_savings = 0.0

    # Calculate per-model savings
    for model_name, usage in session.model_usage.items():
        cache_read = usage.get("cache_read", 0)
        if cache_read > 0:
            model_pricing = pricing.get_model_pricing(model_name)
            if model_pricing:
                input_rate = model_pricing.get("input", 0)
                cache_rate = model_pricing.get("cache_read", 0)
                # Savings = tokens * (full input price - discounted cache price)
                savings = cache_read * (input_rate - cache_rate) / 1_000_000
                total_savings += savings

    # Fallback for sessions without per-model data or unknown models
    if total_savings == 0.0 and session.total_cache_read_tokens > 0:
        # Conservative estimate using Claude Sonnet rates
        # $3.00/MTok input - $0.30/MTok cache = $2.70/MTok savings
        fallback_rate = 2.70
        total_savings = session.total_cache_read_tokens * fallback_rate / 1_000_000

    return total_savings


def _severity_to_enum(severity: str) -> SeverityLevel:
    """Convert severity string to SeverityLevel enum.

    Args:
        severity: Severity string (high, medium, low)

    Returns:
        Corresponding SeverityLevel enum value
    """
    severity_map = {
        "high": SeverityLevel.HIGH,
        "medium": SeverityLevel.MEDIUM,
        "low": SeverityLevel.LOW,
        "critical": SeverityLevel.CRITICAL,
        "info": SeverityLevel.INFO,
    }
    return severity_map.get(severity.lower(), SeverityLevel.MEDIUM)


def _live_smells_to_smell_objects(smells: List[Dict[str, Any]]) -> List[Smell]:
    """Convert LiveSession smell dicts to Smell dataclass objects.

    Args:
        smells: List of smell dictionaries from LiveSession

    Returns:
        List of Smell dataclass objects for RecommendationEngine
    """
    return [
        Smell(
            pattern=s.get("pattern", "UNKNOWN"),
            severity=s.get("severity", "info"),
            tool=s.get("tool"),
            description=s.get("description", ""),
            evidence=s.get("evidence", {}),
        )
        for s in smells
    ]


# Smell pattern to severity mapping
_SMELL_SEVERITY_MAP: Dict[str, SeverityLevel] = {
    # Security smells (high)
    "CREDENTIAL_EXPOSURE": SeverityLevel.CRITICAL,
    "SUSPICIOUS_TOOL_DESCRIPTION": SeverityLevel.HIGH,
    "UNUSUAL_DATA_FLOW": SeverityLevel.HIGH,
    # Efficiency smells (medium-high)
    "TOP_CONSUMER": SeverityLevel.MEDIUM,
    "HIGH_MCP_SHARE": SeverityLevel.MEDIUM,
    "EXPENSIVE_FAILURES": SeverityLevel.HIGH,
    "LARGE_PAYLOAD": SeverityLevel.MEDIUM,
    # Cache smells (medium)
    "LOW_CACHE_HIT": SeverityLevel.MEDIUM,
    "CACHE_MISS_STREAK": SeverityLevel.MEDIUM,
    "REDUNDANT_CALLS": SeverityLevel.MEDIUM,
    # Operational smells (low-medium)
    "CHATTY": SeverityLevel.LOW,
    "BURST_PATTERN": SeverityLevel.LOW,
    "SEQUENTIAL_READS": SeverityLevel.LOW,
    "HIGH_VARIANCE": SeverityLevel.LOW,
    "UNDERUTILIZED_SERVER": SeverityLevel.MEDIUM,
}


def _get_severity_for_pattern(pattern: str | None) -> SeverityLevel:
    """Get severity level for a smell pattern.

    Args:
        pattern: Smell pattern identifier

    Returns:
        Appropriate SeverityLevel for the pattern
    """
    if pattern is None:
        return SeverityLevel.MEDIUM
    return _SMELL_SEVERITY_MAP.get(pattern, SeverityLevel.MEDIUM)


# Recommendation type to human-readable title mapping
_RECOMMENDATION_TITLE_MAP: Dict[str, str] = {
    "REMOVE_UNUSED_SERVER": "Remove Unused Server",
    "ENABLE_CACHING": "Enable Caching",
    "BATCH_OPERATIONS": "Batch Operations",
    "OPTIMIZE_COST": "Optimize Cost",
}


def _internal_to_schema_recommendation(
    rec: InternalRecommendation,
    index: int,
) -> Recommendation:
    """Map internal Recommendation dataclass to schema Recommendation model.

    Args:
        rec: Internal Recommendation from RecommendationEngine
        index: Index for generating unique ID

    Returns:
        Schema Recommendation model for MCP output
    """
    # Generate ID from source smell + index
    rec_id = f"{rec.source_smell or rec.type}-{index}"

    # Derive severity from source smell pattern
    severity = _get_severity_for_pattern(rec.source_smell)

    # Get human-readable title
    title = _RECOMMENDATION_TITLE_MAP.get(rec.type, rec.type.replace("_", " ").title())

    return Recommendation(
        id=rec_id,
        severity=severity,
        category=rec.type,
        title=title,
        action=rec.action,
        impact=rec.impact,
        evidence={"summary": rec.evidence, **rec.details},
        confidence=rec.confidence,
    )


def _find_affected_pinned_server(
    rec: InternalRecommendation,
    pinned_servers: Set[str],
) -> Optional[str]:
    """Check if a recommendation affects a pinned server.

    Looks at the recommendation's details and evidence to determine
    if it involves a pinned server.

    Args:
        rec: Internal Recommendation from RecommendationEngine
        pinned_servers: Set of pinned server names

    Returns:
        Name of affected pinned server, or None if not applicable
    """
    # Check details dict for server information
    details = rec.details or {}

    # Check common detail keys that might contain server names
    for key in ("server", "server_name", "mcp_server", "tool_server"):
        if key in details:
            server = details[key]
            if isinstance(server, str) and server in pinned_servers:
                return server

    # Check if tool name contains server prefix (MCP format: server__tool)
    if "tool" in details:
        tool_name = details["tool"]
        if isinstance(tool_name, str) and "__" in tool_name:
            server_part = tool_name.split("__")[0]
            if server_part in pinned_servers:
                return server_part

    # Check evidence text for server mentions
    evidence_text = str(rec.evidence).lower()
    for pinned_server in pinned_servers:
        if pinned_server.lower() in evidence_text:
            return pinned_server

    return None


# ============================================================================
# Tool 1: start_tracking (IMPLEMENTED)
# ============================================================================


def start_tracking(
    platform: ServerPlatform,
    project: str | None = None,
) -> StartTrackingOutput:
    """
    Begin live tracking of an AI agent session.

    This tool initializes a new tracking session for the specified platform.
    Once started, the session collects metrics that can be queried via
    get_metrics and analyzed via analyze_session.

    Args:
        platform: AI coding platform to track (claude_code, codex_cli, gemini_cli)
        project: Optional project name for grouping sessions

    Returns:
        Session information including the session_id for subsequent queries
    """
    tracker = get_tracker()

    # Check if session already active
    if tracker.has_active_session:
        active = tracker.active_session
        assert active is not None  # for type checker
        return StartTrackingOutput(
            session_id=active.session_id,
            platform=active.platform,
            project=active.project,
            started_at=active.started_at.isoformat(),
            status="active",
            message=f"Session already active since {active.started_at.isoformat()}. "
            "Use get_metrics to query or call start_tracking after stopping the current session.",
        )

    # Start new session
    try:
        session = tracker.start_session(
            platform=platform.value,
            project=project,
        )
        return StartTrackingOutput(
            session_id=session.session_id,
            platform=session.platform,
            project=session.project,
            started_at=session.started_at.isoformat(),
            status="active",
            message=f"Now tracking {platform.value} session. "
            "Use get_metrics to query current stats.",
        )
    except Exception as e:
        return StartTrackingOutput(
            session_id="",
            platform=platform.value,
            project=project,
            started_at=datetime.now().isoformat(),
            status="error",
            message=f"Failed to start tracking: {e}",
        )


# ============================================================================
# Tool 2: get_metrics (IMPLEMENTED)
# ============================================================================


def get_metrics(
    session_id: str | None = None,
    include_smells: bool = True,
    include_breakdown: bool = True,
) -> GetMetricsOutput:
    """
    Query current session statistics and detected issues.

    Returns live metrics from the active or specified session, including
    token usage, costs, rates, cache efficiency, and detected smells.

    Args:
        session_id: Session ID to query (uses active session if not specified)
        include_smells: Include detected efficiency issues
        include_breakdown: Include per-tool and per-server breakdown

    Returns:
        Comprehensive metrics for the session
    """
    tracker = get_tracker()
    session = tracker.get_session(session_id)

    if session is None:
        # Return empty metrics with error indication
        return GetMetricsOutput(
            session_id=session_id or "none",
            tokens=TokenMetrics(input=0, output=0, total=0),
            cost_usd=0.0,
            rates=RateMetrics(tokens_per_min=0.0, calls_per_min=0.0, duration_minutes=0.0),
            cache=CacheMetrics(hit_ratio=0.0, savings_tokens=0, savings_usd=0.0),
            smells=(
                [
                    SmellSummary(
                        pattern="NO_SESSION",
                        severity=SeverityLevel.INFO,
                        tool=None,
                        description="No active session. Call start_tracking first.",
                    )
                ]
                if include_smells
                else []
            ),
            tool_count=0,
            call_count=0,
            model_usage={},
        )

    # Calculate metrics from session
    total_tokens = (
        session.total_input_tokens + session.total_output_tokens + session.total_cache_read_tokens
    )

    # Calculate duration
    duration = datetime.now() - session.started_at
    duration_minutes = duration.total_seconds() / 60.0

    # Calculate rates
    tokens_per_min = total_tokens / duration_minutes if duration_minutes > 0 else 0.0
    calls_per_min = session.call_count / duration_minutes if duration_minutes > 0 else 0.0

    # Calculate cache metrics
    total_input = session.total_input_tokens + session.total_cache_read_tokens
    cache_hit_ratio = session.total_cache_read_tokens / total_input if total_input > 0 else 0.0

    # Convert smells to summaries
    smell_summaries = []
    if include_smells:
        for smell in session.smells:
            smell_summaries.append(
                SmellSummary(
                    pattern=smell.get("pattern", "UNKNOWN"),
                    severity=SeverityLevel(smell.get("severity", "info")),
                    tool=smell.get("tool"),
                    description=smell.get("description", ""),
                )
            )

    return GetMetricsOutput(
        session_id=session.session_id,
        tokens=TokenMetrics(
            input=session.total_input_tokens,
            output=session.total_output_tokens,
            cache_read=session.total_cache_read_tokens,
            cache_write=session.total_cache_write_tokens,
            total=total_tokens,
        ),
        cost_usd=session.total_cost_usd,
        rates=RateMetrics(
            tokens_per_min=round(tokens_per_min, 2),
            calls_per_min=round(calls_per_min, 2),
            duration_minutes=round(duration_minutes, 2),
        ),
        cache=CacheMetrics(
            hit_ratio=round(cache_hit_ratio, 3),
            savings_tokens=session.total_cache_read_tokens,
            savings_usd=round(_calculate_cache_savings(session), 4),
        ),
        smells=smell_summaries,
        tool_count=len(session.tool_calls),
        call_count=session.call_count,
        model_usage=session.model_usage if include_breakdown else {},
    )


# ============================================================================
# Tool 3: get_recommendations (IMPLEMENTED)
# ============================================================================


def get_recommendations(
    session_id: str | None = None,
    severity_filter: SeverityLevel | None = None,
    max_recommendations: int = 5,
    pinned_servers: Optional[List[str]] = None,
) -> GetRecommendationsOutput:
    """
    Get optimization recommendations for the session.

    Analyzes the session and returns prioritized recommendations
    for improving efficiency and reducing token usage.

    Args:
        session_id: Session ID to analyze (uses active session if not specified)
        severity_filter: Minimum severity level to include
        max_recommendations: Maximum number of recommendations to return
        pinned_servers: List of pinned server names to highlight in recommendations

    Returns:
        Prioritized list of recommendations with expected impact
    """
    tracker = get_tracker()
    session = tracker.get_session(session_id)

    # Handle no session case
    if session is None:
        return GetRecommendationsOutput(
            session_id=session_id or "none",
            recommendations=[],
            total_potential_savings_tokens=0,
            total_potential_savings_usd=0.0,
        )

    # Convert LiveSession smells to Smell dataclass objects
    smell_objects = _live_smells_to_smell_objects(session.smells)

    # Generate recommendations using the engine
    engine = RecommendationEngine()
    internal_recs = engine.generate(smell_objects)

    # Convert to schema Recommendation models
    pinned_set = set(pinned_servers or [])
    schema_recs: List[Recommendation] = []
    for idx, rec in enumerate(internal_recs, start=1):
        schema_rec = _internal_to_schema_recommendation(rec, idx)

        # Check if recommendation affects a pinned server
        if pinned_set:
            affected_server = _find_affected_pinned_server(rec, pinned_set)
            if affected_server:
                schema_rec = Recommendation(
                    **{
                        **schema_rec.model_dump(),
                        "affects_pinned_server": True,
                        "pinned_server_name": affected_server,
                    }
                )

        schema_recs.append(schema_rec)

    # Apply severity filter if provided
    if severity_filter is not None:
        # Define severity ordering for filtering
        severity_order = {
            SeverityLevel.CRITICAL: 4,
            SeverityLevel.HIGH: 3,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 1,
            SeverityLevel.INFO: 0,
        }
        min_severity = severity_order.get(severity_filter, 0)
        schema_recs = [r for r in schema_recs if severity_order.get(r.severity, 0) >= min_severity]

    # Sort to prioritize recommendations affecting pinned servers
    schema_recs.sort(key=lambda r: (not r.affects_pinned_server, r.severity.value))

    # Limit to max_recommendations
    schema_recs = schema_recs[:max_recommendations]

    # Calculate total potential savings from evidence data
    total_savings_tokens = 0
    total_savings_usd = 0.0
    for schema_rec in schema_recs:
        evidence = schema_rec.evidence
        # Extract token savings from various evidence fields
        if isinstance(evidence, dict):
            if "tokens_wasted" in evidence:
                tokens_wasted = evidence["tokens_wasted"]
                if isinstance(tokens_wasted, (int, float)):
                    total_savings_tokens += int(tokens_wasted)
            if "total_tokens" in evidence:
                total_tokens = evidence["total_tokens"]
                if isinstance(total_tokens, (int, float)):
                    # Estimate 30% savings for batching/caching recommendations
                    total_savings_tokens += int(total_tokens * 0.3)
        # Estimate USD savings at ~$0.00001 per token (rough average)
        total_savings_usd = total_savings_tokens * 0.00001

    return GetRecommendationsOutput(
        session_id=session.session_id,
        recommendations=schema_recs,
        total_potential_savings_tokens=total_savings_tokens,
        total_potential_savings_usd=round(total_savings_usd, 4),
    )


# ============================================================================
# Tool 4: analyze_session (IMPLEMENTED)
# ============================================================================


def _calculate_pinned_server_usage(
    session: "LiveSession",  # noqa: F821 - forward reference
    pinned_servers: List[PinnedServerInfo],
) -> List[PinnedServerUsage]:
    """Calculate usage statistics for pinned servers in a session.

    Args:
        session: LiveSession with server_calls data
        pinned_servers: List of pinned servers from analyze_config

    Returns:
        List of PinnedServerUsage with per-server statistics
    """
    if not pinned_servers:
        return []

    usage_list: List[PinnedServerUsage] = []
    total_calls = session.call_count or 1  # Avoid division by zero
    total_tokens = session.total_input_tokens + session.total_output_tokens

    for pinned in pinned_servers:
        server_name = pinned.name
        calls = session.server_calls.get(server_name, 0)
        is_active = calls > 0

        # Estimate tokens based on proportion of calls
        # (Since we don't track per-server tokens, this is an approximation)
        if total_calls > 0 and calls > 0:
            token_proportion = calls / total_calls
            tokens = int(total_tokens * token_proportion)
        else:
            tokens = 0

        percentage = (calls / total_calls * 100) if total_calls > 0 else 0.0

        usage_list.append(
            PinnedServerUsage(
                name=server_name,
                calls=calls,
                tokens=tokens,
                percentage=round(percentage, 2),
                is_active=is_active,
            )
        )

    # Sort by calls descending
    usage_list.sort(key=lambda u: u.calls, reverse=True)

    return usage_list


def _detect_zombie_tools_from_live_session(
    session: "LiveSession",  # noqa: F821 - forward reference
) -> List[ZombieTool]:
    """Detect zombie tools from a live session's tool_calls data.

    Parses MCP tool names (mcp__<server>__<tool>) to group by server,
    then compares against zombie config to find unused tools.

    A "zombie tool" is an MCP tool that:
    - Appears in the server's configured known tools (from token-audit.toml)
    - Was never called during the session
    - Contributes to context overhead without providing value

    Args:
        session: LiveSession being analyzed

    Returns:
        List of ZombieTool objects for unused tools, or empty list if no config
    """
    config = load_zombie_config()
    if not config.known_tools:
        return []

    # Group called tools by server (parse mcp__server__tool format)
    called_by_server: Dict[str, Set[str]] = defaultdict(set)
    for tool_name in session.tool_calls:
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__", 2)
            if len(parts) >= 3:
                server = parts[1]
                called_by_server[server].add(tool_name)

    # Find zombies: known but not called
    zombies: List[ZombieTool] = []
    for server_name, known_tools in config.known_tools.items():
        called_tools = called_by_server.get(server_name, set())
        # Only report zombies if at least one tool from this server was called
        if not called_tools:
            continue
        unused = known_tools - called_tools

        for tool_name in sorted(unused):
            zombies.append(
                ZombieTool(
                    tool_name=tool_name,
                    server=server_name,
                    schema_tokens=0,  # Unknown for live sessions
                )
            )

    return zombies


def _generate_session_summary(
    session: "LiveSession",  # noqa: F821 - forward reference
    metrics: GetMetricsOutput,
    recommendations: List[Recommendation],
    report_format: ReportFormat,
) -> str:
    """Generate human-readable summary based on format.

    Args:
        session: LiveSession being analyzed
        metrics: Computed metrics for the session
        recommendations: Generated recommendations
        report_format: Desired output format

    Returns:
        Formatted summary string
    """
    # Calculate duration
    duration = metrics.rates.duration_minutes

    # Count issues by severity
    high_severity = sum(
        1 for s in metrics.smells if s.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
    )

    if report_format == ReportFormat.SUMMARY:
        # Brief one-paragraph summary
        summary_parts = [
            f"Session {session.session_id} ran for {duration:.1f} minutes",
            f"consuming {metrics.tokens.total:,} tokens (${metrics.cost_usd:.4f}).",
        ]
        if metrics.smells:
            summary_parts.append(f"Detected {len(metrics.smells)} efficiency issues")
            if high_severity:
                summary_parts.append(f"({high_severity} high severity).")
            else:
                summary_parts.append(".")
        if recommendations:
            summary_parts.append(f"Generated {len(recommendations)} recommendations.")
        summary_parts.append("Note: Zombie tool analysis requires completed sessions.")
        return " ".join(summary_parts)

    elif report_format == ReportFormat.MARKDOWN:
        # Formatted markdown with sections
        lines = [
            f"# Session Analysis: {session.session_id}",
            "",
            "## Overview",
            f"- **Platform**: {session.platform}",
            f"- **Duration**: {duration:.1f} minutes",
            f"- **Total Tokens**: {metrics.tokens.total:,}",
            f"- **Cost**: ${metrics.cost_usd:.4f}",
            f"- **Cache Hit Ratio**: {metrics.cache.hit_ratio:.1%}",
            "",
            "## Efficiency Issues",
        ]
        if metrics.smells:
            for smell in metrics.smells:
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    smell.severity.value, "⚪"
                )
                lines.append(f"- {severity_icon} **{smell.pattern}**: {smell.description}")
        else:
            lines.append("- No efficiency issues detected")

        lines.extend(["", "## Recommendations"])
        if recommendations:
            for rec in recommendations:
                lines.append(f"- **{rec.title}** (confidence: {rec.confidence:.0%})")
                lines.append(f"  - Action: {rec.action}")
                lines.append(f"  - Impact: {rec.impact}")
        else:
            lines.append("- No recommendations at this time")

        lines.extend(
            [
                "",
                "## Notes",
                "- Zombie tool analysis requires completed sessions (not available for live tracking)",
            ]
        )
        return "\n".join(lines)

    else:  # JSON format - return structured summary as string
        return (
            f"Session {session.session_id}: "
            f"{metrics.tokens.total:,} tokens, ${metrics.cost_usd:.4f}, "
            f"{len(metrics.smells)} issues, {len(recommendations)} recommendations. "
            f"Zombie tool analysis requires completed sessions."
        )


def analyze_session(
    session_id: str | None = None,
    format: ReportFormat = ReportFormat.JSON,
    include_model_usage: bool = True,
    include_zombie_tools: bool = True,
) -> AnalyzeSessionOutput:
    """
    Perform end-of-session analysis.

    Generates a comprehensive analysis of the session including
    metrics, recommendations, unused tools, per-model breakdown,
    and pinned server usage statistics.

    Args:
        session_id: Session ID to analyze (uses active session if not specified)
        format: Output format (json, markdown, summary)
        include_model_usage: Include per-model breakdown
        include_zombie_tools: Include unused tool analysis (requires completed sessions)

    Returns:
        Complete session analysis with recommendations
    """
    tracker = get_tracker()
    session = tracker.get_session(session_id)

    # Handle no session case
    if session is None:
        metrics = get_metrics(session_id, include_smells=True, include_breakdown=True)
        return AnalyzeSessionOutput(
            session_id=session_id or "none",
            summary="No active session. Call start_tracking first to begin a session.",
            metrics=metrics,
            recommendations=[],
            zombie_tools=[],
            model_usage={},
            pinned_server_usage=[],
        )

    # Get metrics for the session
    metrics = get_metrics(session_id, include_smells=True, include_breakdown=include_model_usage)

    # Get pinned servers for the session's platform
    pinned_server_usage: List[PinnedServerUsage] = []
    pinned_servers: List[PinnedServerInfo] = []
    try:
        # Map session platform string to ServerPlatform enum
        platform_map = {
            "claude_code": ServerPlatform.CLAUDE_CODE,
            "codex_cli": ServerPlatform.CODEX_CLI,
            "gemini_cli": ServerPlatform.GEMINI_CLI,
        }
        platform_enum = platform_map.get(session.platform)
        if platform_enum:
            config_result = analyze_config(platform=platform_enum)
            pinned_servers = config_result.pinned_servers
            pinned_server_usage = _calculate_pinned_server_usage(session, pinned_servers)
    except Exception:
        # If config analysis fails, continue without pinned server data
        pass

    # Get recommendations with pinned server context
    recs_output = get_recommendations(
        session_id,
        max_recommendations=10,
        pinned_servers=[p.name for p in pinned_servers],
    )
    recommendations = recs_output.recommendations

    # Generate summary based on format
    summary = _generate_session_summary(session, metrics, recommendations, format)

    # Detect zombie tools if enabled (requires zombie config in token-audit.toml)
    zombie_tools: List[ZombieTool] = []
    if include_zombie_tools:
        zombie_tools = _detect_zombie_tools_from_live_session(session)

    return AnalyzeSessionOutput(
        session_id=session.session_id,
        summary=summary,
        metrics=metrics,
        recommendations=recommendations,
        zombie_tools=zombie_tools,
        model_usage=session.model_usage if include_model_usage else {},
        pinned_server_usage=pinned_server_usage,
    )


# ============================================================================
# Tool 5: get_best_practices (IMPLEMENTED)
# ============================================================================


def get_best_practices(
    topic: str | None = None,
    list_all: bool = False,
) -> GetBestPracticesOutput:
    """
    Retrieve MCP best practices guidance.

    Returns best practices documentation filtered by topic,
    or lists all available topics. Searches across practice IDs,
    titles, categories, keywords, and related smell patterns.

    Args:
        topic: Topic to search for (e.g., 'caching', 'progressive disclosure',
               'security', 'LOW_CACHE_HIT'). Case-insensitive.
        list_all: List all available best practice topics (ignores topic)

    Returns:
        Matching best practices with full markdown content

    Examples:
        - get_best_practices(topic="caching") - Find caching-related practices
        - get_best_practices(topic="LOW_CACHE_HIT") - Find practices for a smell
        - get_best_practices(list_all=True) - Get all 10 best practices
    """
    loader = _get_best_practices_loader()
    all_practices = loader.load_all()

    # Determine which practices to return
    if list_all:
        matched_practices = all_practices
    elif topic:
        matched_practices = loader.search(topic)
    else:
        # No topic and not list_all - return empty with hint
        matched_practices = []

    # Convert internal BestPractice dataclass to schema BestPractice model
    schema_practices = [
        BestPractice(
            id=p.id,
            title=p.title,
            severity=_severity_to_enum(p.severity),
            category=p.category,
            token_savings=p.token_savings,
            source=p.source,
            content=p.content,
            keywords=p.keywords,
            related_smells=p.related_smells,
        )
        for p in matched_practices
    ]

    return GetBestPracticesOutput(
        practices=schema_practices,
        total_available=len(all_practices),
    )


# ============================================================================
# Tool 6: analyze_config (IMPLEMENTED)
# ============================================================================


def _module_issue_to_schema(issue: ModuleConfigIssue) -> ConfigIssue:
    """Convert module ConfigIssue to schema ConfigIssue.

    Args:
        issue: Issue from config_analyzer module

    Returns:
        Schema ConfigIssue for output
    """
    # Map severity string to SeverityLevel enum
    severity_map = {
        "critical": SeverityLevel.CRITICAL,
        "high": SeverityLevel.HIGH,
        "medium": SeverityLevel.MEDIUM,
        "low": SeverityLevel.LOW,
        "info": SeverityLevel.INFO,
    }
    severity = severity_map.get(issue.severity.lower(), SeverityLevel.INFO)

    return ConfigIssue(
        severity=severity,
        category=issue.category,
        message=issue.message,
        location=issue.location,
        recommendation=issue.recommendation,
    )


def _server_config_to_info(
    name: str,
    server: ServerConfig,
    pinned_names: Set[str],
) -> ServerInfo:
    """Convert ServerConfig to ServerInfo.

    Args:
        name: Server name
        server: Server configuration
        pinned_names: Set of pinned server names

    Returns:
        ServerInfo for output
    """
    return ServerInfo(
        name=name,
        command=server.command,
        is_pinned=name in pinned_names,
        tool_count=None,  # Tool count requires runtime introspection
    )


# Mapping from detection_method to human-readable reason
_DETECTION_METHOD_REASONS: Dict[str, str] = {
    "explicit_config": "Explicitly listed in pinned_servers config",
    "explicit_flag": "Server has pinned: true flag",
    "custom_path": "Custom/local server path detected",
    "usage_frequency": "Frequently used in recent sessions",
}


def _pinned_to_info(pinned: ModulePinnedServer) -> PinnedServerInfo:
    """Convert module PinnedServer to schema PinnedServerInfo.

    Args:
        pinned: PinnedServer from config_analyzer

    Returns:
        PinnedServerInfo for output
    """
    source = pinned.detection_method or "unknown"
    reason = _DETECTION_METHOD_REASONS.get(
        source,
        pinned.notes or f"Detected via {source}",
    )

    return PinnedServerInfo(
        name=pinned.name,
        source=source,
        reason=reason,
    )


def _calculate_context_tax(config_path: Path) -> int:
    """Calculate context tax estimate for a config file.

    Args:
        config_path: Path to the MCP config file

    Returns:
        Estimated tokens consumed by server schemas
    """
    try:
        analyzer = SchemaAnalyzer()
        servers = analyzer.analyze_from_file(config_path)
        static_cost = analyzer.calculate_static_cost(servers)
        return static_cost.total_tokens
    except Exception:
        # Return 0 if analysis fails (file issues, etc.)
        return 0


def analyze_config(
    platform: ServerPlatform | None = None,
    config_path: str | None = None,
) -> AnalyzeConfigOutput:
    """
    Analyze MCP configuration files.

    Examines platform configuration files for issues like
    hardcoded credentials, too many servers, or misconfigurations.

    Args:
        platform: Platform to analyze (analyzes all if not specified)
        config_path: Custom config file path (uses default if not specified)

    Returns:
        Configuration analysis with detected issues and server inventory
    """
    all_issues: List[ConfigIssue] = []
    all_servers: List[ServerInfo] = []
    pinned_servers_info: List[PinnedServerInfo] = []
    context_tax: int = 0
    analyzed_path: str = ""
    analyzed_platform: Optional[str] = None
    config_file_path: Optional[Path] = None  # Track for context tax calculation

    # If custom config path provided, parse and analyze it directly
    if config_path:
        # Security: Validate path is within allowed directories
        validated_path, validation_error = validate_config_path(config_path)
        if validation_error:
            return AnalyzeConfigOutput(
                platform=platform.value if platform else None,
                config_path="[path validation failed]",
                issues=[
                    ConfigIssue(
                        severity=SeverityLevel.HIGH,
                        category="path_validation_error",
                        message=validation_error,
                        location="config_path parameter",
                        recommendation="Use platform auto-discovery or specify a path within ~/.claude/, ~/.codex/, or ~/.gemini/",
                    )
                ],
                servers=[],
                server_count=0,
                pinned_servers=[],
                context_tax_estimate=0,
            )

        # validated_path is guaranteed to be non-None if validation_error is None
        if validated_path is None:
            # This shouldn't happen, but handle it gracefully
            return AnalyzeConfigOutput(
                platform=platform.value if platform else None,
                config_path="[path validation failed]",
                issues=[
                    ConfigIssue(
                        severity=SeverityLevel.HIGH,
                        category="path_validation_error",
                        message="Path validation returned no result",
                        location="config_path parameter",
                        recommendation="Use platform auto-discovery or specify a path within ~/.claude/, ~/.codex/, or ~/.gemini/",
                    )
                ],
                servers=[],
                server_count=0,
                pinned_servers=[],
                context_tax_estimate=0,
            )

        path = validated_path
        # Security: Use sanitized path in output (abbreviate home dir)
        analyzed_path = sanitize_path_for_output(path)
        platform_str = platform.value if platform else "unknown"
        analyzed_platform = platform_str

        if not path.exists():
            return AnalyzeConfigOutput(
                platform=analyzed_platform,
                config_path=analyzed_path,
                issues=[
                    ConfigIssue(
                        severity=SeverityLevel.HIGH,
                        category="file_not_found",
                        message="Config file not found",
                        location=analyzed_path,
                        recommendation="Verify the config file path and ensure the file exists",
                    )
                ],
                servers=[],
                server_count=0,
                pinned_servers=[],
                context_tax_estimate=0,
            )

        # Parse and analyze the config
        config = parse_config(path, platform_str)

        if config.parse_error:
            # Security: Sanitize parse error to avoid exposing file contents
            safe_error = sanitize_error_message(config.parse_error)
            return AnalyzeConfigOutput(
                platform=analyzed_platform,
                config_path=analyzed_path,
                issues=[
                    ConfigIssue(
                        severity=SeverityLevel.HIGH,
                        category="parse_error",
                        message=safe_error,
                        location=analyzed_path,
                        recommendation="Fix the configuration file syntax",
                    )
                ],
                servers=[],
                server_count=0,
                pinned_servers=[],
                context_tax_estimate=0,
            )

        # Track config path for context tax
        config_file_path = path

        # Analyze for issues
        module_issues = module_analyze_config(config)
        all_issues = [_module_issue_to_schema(i) for i in module_issues]

        # Get pinned servers and convert to schema format
        pinned = detect_pinned_servers(config)
        pinned_names = {p.name for p in pinned}
        pinned_servers_info = [_pinned_to_info(p) for p in pinned]

        # Convert servers to ServerInfo
        all_servers = [
            _server_config_to_info(name, server, pinned_names)
            for name, server in config.servers.items()
        ]

    else:
        # Discover and analyze platform configs
        platform_filter = platform.value if platform else None
        discovered = discover_existing_configs(platform_filter)

        if not discovered:
            return AnalyzeConfigOutput(
                platform=platform_filter,
                config_path="(no configs found)",
                issues=[
                    ConfigIssue(
                        severity=SeverityLevel.INFO,
                        category="no_config",
                        message="No MCP configuration files found"
                        + (f" for platform {platform_filter}" if platform_filter else ""),
                        location="~/.claude/, ~/.codex/, ~/.gemini/",
                        recommendation="Create an MCP configuration file to enable server management",
                    )
                ],
                servers=[],
                server_count=0,
                pinned_servers=[],
                context_tax_estimate=0,
            )

        # Use first discovered config as primary
        primary = discovered[0]
        # Security: Use sanitized path in output
        analyzed_path = sanitize_path_for_output(primary.path)
        analyzed_platform = primary.platform
        config_file_path = primary.path  # Track for context tax

        # Parse and analyze
        config = parse_config(primary.path, primary.platform)

        if config.parse_error:
            # Security: Sanitize parse error message
            safe_error = sanitize_error_message(config.parse_error)
            all_issues.append(
                ConfigIssue(
                    severity=SeverityLevel.HIGH,
                    category="parse_error",
                    message=safe_error,
                    location=analyzed_path,
                    recommendation="Fix the configuration file syntax",
                )
            )
        else:
            # Analyze for issues
            module_issues = module_analyze_config(config)
            all_issues = [_module_issue_to_schema(i) for i in module_issues]

            # Get pinned servers and convert to schema format
            pinned = detect_pinned_servers(config)
            pinned_names = {p.name for p in pinned}
            pinned_servers_info = [_pinned_to_info(p) for p in pinned]

            # Convert servers to ServerInfo
            all_servers = [
                _server_config_to_info(name, server, pinned_names)
                for name, server in config.servers.items()
            ]

        # If analyzing all platforms, note additional configs found
        if not platform_filter and len(discovered) > 1:
            # Security: Use sanitized paths in output
            additional = [sanitize_path_for_output(c.path) for c in discovered[1:]]
            all_issues.append(
                ConfigIssue(
                    severity=SeverityLevel.INFO,
                    category="additional_configs",
                    message=f"Found {len(additional)} additional config(s): {', '.join(additional)}",
                    location=analyzed_path,
                    recommendation="Run analyze_config with specific platform to analyze each",
                )
            )

    # Calculate context tax if we have a valid config path
    if config_file_path is not None:
        context_tax = _calculate_context_tax(config_file_path)

    return AnalyzeConfigOutput(
        platform=analyzed_platform,
        config_path=analyzed_path,
        issues=all_issues,
        servers=all_servers,
        server_count=len(all_servers),
        pinned_servers=pinned_servers_info,
        context_tax_estimate=context_tax,
    )


# ============================================================================
# Tool 7: get_pinned_servers (IMPLEMENTED)
# ============================================================================


def get_pinned_servers(
    include_auto_detected: bool = True,
    platform: ServerPlatform | None = None,
) -> GetPinnedServersOutput:
    """
    Get user's pinned MCP servers.

    Returns the list of servers the user has pinned for focused analysis,
    using 3 detection methods:
    1. Explicit: Servers with pinned:true or in pinned_servers config
    2. Auto-detect local: Servers with local file paths (custom servers)
    3. High-usage: Servers exceeding usage threshold in recent sessions

    Args:
        include_auto_detected: Include auto-detected pinned servers
            (auto_detect_local and high_usage methods)
        platform: Platform to analyze (analyzes all discovered if not specified)

    Returns:
        List of pinned servers with detection method and reason
    """
    # Discover MCP config for platform
    platform_filter = platform.value if platform else None
    discovered = discover_existing_configs(platform_filter)

    if not discovered:
        return GetPinnedServersOutput(
            servers=[],
            total_pinned=0,
            auto_detect_enabled=include_auto_detected,
        )

    # Use first discovered config
    primary = discovered[0]
    config = parse_config(primary.path, primary.platform)

    if config.parse_error:
        return GetPinnedServersOutput(
            servers=[],
            total_pinned=0,
            auto_detect_enabled=include_auto_detected,
        )

    # Get effective configuration (global + project overrides)
    config_manager = PinnedConfigManager()
    effective_config = config_manager.get_effective_config()

    # Create detector and detect pinned servers
    detector = PinnedServerDetector()
    pinned_servers = detector.detect(
        config=config,
        effective_config=effective_config,
        platform=primary.platform,
    )

    # Filter by include_auto_detected if needed
    if not include_auto_detected:
        pinned_servers = [s for s in pinned_servers if s.source == SOURCE_EXPLICIT]

    # Convert to schema format
    schema_servers = [
        PinnedServerInfo(
            name=server.name,
            source=server.source,
            reason=server.reason,
        )
        for server in pinned_servers
    ]

    return GetPinnedServersOutput(
        servers=schema_servers,
        total_pinned=len(schema_servers),
        auto_detect_enabled=include_auto_detected,
    )


# ============================================================================
# Tool 8: get_trends (IMPLEMENTED)
# ============================================================================


# Period to days mapping for SmellAggregator
_PERIOD_DAYS: Dict[TrendPeriod, int] = {
    TrendPeriod.LAST_7_DAYS: 7,
    TrendPeriod.LAST_30_DAYS: 30,
    TrendPeriod.LAST_90_DAYS: 90,
    TrendPeriod.ALL_TIME: 365,  # Use 365 days as practical "all time"
}


def _calculate_overall_trend(smells: List[AggregatedSmell]) -> str:
    """Determine overall efficiency trend from aggregated smells.

    Compares the number of worsening vs improving patterns to determine
    the overall direction of efficiency.

    Args:
        smells: List of aggregated smell statistics

    Returns:
        "improving", "worsening", or "stable"
    """
    if not smells:
        return "stable"

    worsening_count = sum(1 for s in smells if s.trend == "worsening")
    improving_count = sum(1 for s in smells if s.trend == "improving")

    if worsening_count > improving_count:
        return "worsening"
    elif improving_count > worsening_count:
        return "improving"
    return "stable"


def _generate_trend_recommendations(smells: List[AggregatedSmell]) -> List[str]:
    """Generate actionable recommendations based on detected trends.

    Focuses on the top 3 worsening patterns, providing specific
    guidance to address deteriorating efficiency.

    Args:
        smells: List of aggregated smell statistics

    Returns:
        List of recommendation strings (max 5)
    """
    recommendations: List[str] = []

    # Find worsening patterns, sorted by severity (change percent)
    worsening = [s for s in smells if s.trend == "worsening"]
    worsening.sort(key=lambda s: abs(s.trend_change_percent), reverse=True)

    # Generate recommendations for top 3 worsening patterns
    for smell in worsening[:3]:
        change_str = (
            f"+{smell.trend_change_percent:.0f}"
            if smell.trend_change_percent > 0
            else f"{smell.trend_change_percent:.0f}"
        )
        recommendations.append(
            f"Address worsening {smell.pattern} pattern ({change_str}% change, "
            f"affects {smell.sessions_affected}/{smell.total_sessions} sessions)"
        )

    # Add general recommendations based on overall state
    if not recommendations:
        if smells:
            # Check for high-frequency patterns even if stable
            high_freq = [s for s in smells if s.frequency_percent > 50]
            if high_freq:
                recommendations.append(
                    f"Monitor persistent {high_freq[0].pattern} pattern "
                    f"(occurs in {high_freq[0].frequency_percent:.0f}% of sessions)"
                )
            else:
                recommendations.append(
                    "Efficiency patterns are stable. Continue current practices."
                )
        else:
            recommendations.append("Collect more session data for meaningful trend analysis.")

    # Add improving patterns as positive feedback (max 2)
    improving = [s for s in smells if s.trend == "improving"]
    improving.sort(key=lambda s: abs(s.trend_change_percent), reverse=True)
    for smell in improving[:2]:
        if len(recommendations) < 5:
            recommendations.append(
                f"Good progress: {smell.pattern} is improving "
                f"({smell.trend_change_percent:.0f}% reduction)"
            )

    return recommendations[:5]  # Cap at 5 recommendations


def get_trends(
    period: TrendPeriod = TrendPeriod.LAST_30_DAYS,
    platform: ServerPlatform | None = None,
) -> GetTrendsOutput:
    """
    Get cross-session pattern trends.

    Analyzes historical sessions to identify trends in efficiency
    patterns, helping identify systemic issues. Uses SmellAggregator
    to compute statistics across the specified time period.

    Args:
        period: Time period for trend analysis
        platform: Filter by platform (all platforms if not specified)

    Returns:
        Trend analysis with pattern changes and recommendations
    """
    # Map period to days
    days = _PERIOD_DAYS.get(period, 30)

    # Map platform enum to string for SmellAggregator
    # SmellAggregator uses hyphenated names (claude-code, codex-cli, gemini-cli)
    platform_str: Optional[str] = None
    if platform:
        platform_map = {
            ServerPlatform.CLAUDE_CODE: "claude-code",
            ServerPlatform.CODEX_CLI: "codex-cli",
            ServerPlatform.GEMINI_CLI: "gemini-cli",
        }
        platform_str = platform_map.get(platform)

    # Create aggregator and run analysis
    aggregator = SmellAggregator()
    result = aggregator.aggregate(
        days=days,
        platform=platform_str,
    )

    # Handle empty results
    if result.total_sessions == 0:
        return GetTrendsOutput(
            period=period.value,
            sessions_analyzed=0,
            patterns=[],
            top_affected_tools=[],
            overall_trend="stable",
            recommendations=[
                "No sessions found for the specified period. "
                "Run 'token-audit collect' to capture session data."
            ],
        )

    # Convert AggregatedSmell to SmellTrend schema objects
    # Type alias for trend literals
    TrendLiteral = Literal["improving", "stable", "worsening"]
    smell_trends: List[SmellTrend] = []
    for agg_smell in result.aggregated_smells:
        smell_trends.append(
            SmellTrend(
                pattern=agg_smell.pattern,
                occurrences=agg_smell.total_occurrences,
                trend=cast(TrendLiteral, agg_smell.trend),
                change_percent=round(agg_smell.trend_change_percent, 1),
            )
        )

    # Extract top affected tools from all patterns
    # Flatten tool counts across all smell patterns
    tool_counts: Counter[str] = Counter()
    for agg_smell in result.aggregated_smells:
        for tool_name, count in agg_smell.top_tools:
            tool_counts[tool_name] += count

    # Get top 5 most affected tools
    top_tools = [tool for tool, _ in tool_counts.most_common(5)]

    # Calculate overall trend
    overall = _calculate_overall_trend(result.aggregated_smells)

    # Generate recommendations
    recommendations = _generate_trend_recommendations(result.aggregated_smells)

    return GetTrendsOutput(
        period=period.value,
        sessions_analyzed=result.total_sessions,
        patterns=smell_trends,
        top_affected_tools=top_tools,
        overall_trend=cast(TrendLiteral, overall),
        recommendations=recommendations,
    )


# ============================================================================
# Tool 9: get_daily_summary (v1.0.2)
# ============================================================================


def _calculate_usage_trends(
    entries: List[Tuple[float, int]],  # List of (cost, tokens) tuples
) -> Tuple[TrendDirection, float, float]:
    """Calculate trend direction, change percent, and average cost.

    Args:
        entries: List of (cost_usd, total_tokens) tuples in chronological order

    Returns:
        Tuple of (direction, change_percent, avg_cost)
    """
    if not entries:
        return TrendDirection.STABLE, 0.0, 0.0

    costs = [e[0] for e in entries]
    avg_cost = sum(costs) / len(costs) if costs else 0.0

    if len(costs) < 2:
        return TrendDirection.STABLE, 0.0, avg_cost

    # Compare first half to second half for trend
    mid = len(costs) // 2
    first_half_avg = sum(costs[:mid]) / mid if mid > 0 else 0.0
    second_half_avg = sum(costs[mid:]) / (len(costs) - mid) if len(costs) - mid > 0 else 0.0

    if first_half_avg == 0:
        change_percent = 100.0 if second_half_avg > 0 else 0.0
    else:
        change_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100

    if change_percent > 10:
        direction = TrendDirection.INCREASING
    elif change_percent < -10:
        direction = TrendDirection.DECREASING
    else:
        direction = TrendDirection.STABLE

    return direction, round(change_percent, 1), round(avg_cost, 6)


def get_daily_summary(
    days: int = 7,
    platform: ServerPlatform | None = None,
    project: str | None = None,
    breakdown: bool = False,
) -> GetDailySummaryOutput:
    """
    Retrieve daily token usage aggregation across sessions.

    Args:
        days: Number of days to include (default: 7, max: 90)
        platform: Filter by platform (all platforms if not specified)
        project: Filter by project name
        breakdown: Include per-model token breakdown

    Returns:
        Daily usage summary with totals, per-day breakdown, and trends
    """
    from ..aggregation import aggregate_daily
    from ..storage import StorageManager

    storage = StorageManager()
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    # Map platform enum to storage Platform type
    platform_filter: Optional[Platform] = platform.value if platform else None

    # Get daily aggregates
    daily_aggregates = aggregate_daily(
        platform=platform_filter,
        start_date=start_date,
        end_date=end_date,
        group_by_project=project is not None,
        storage=storage,
    )

    # Filter by project if specified
    if project and daily_aggregates:
        # Project filter is applied per-session during aggregation
        # For now we don't have project-level filtering in aggregate_daily
        pass  # TODO: Add project filtering when aggregation supports it

    # Build daily entries
    daily_entries: List[DailyUsageEntry] = []
    trend_data: List[Tuple[float, int]] = []
    busiest_day: Optional[str] = None
    busiest_tokens = 0

    for agg in daily_aggregates:
        cost_usd = float(agg.cost_usd)

        entry = DailyUsageEntry(
            date=agg.date,
            sessions=agg.session_count,
            input_tokens=agg.input_tokens,
            output_tokens=agg.output_tokens,
            total_tokens=agg.total_tokens,
            cost_usd=cost_usd,
            model_breakdown=(
                {k: v.to_dict() for k, v in agg.model_breakdowns.items()} if breakdown else None
            ),
        )
        daily_entries.append(entry)
        trend_data.append((cost_usd, agg.total_tokens))

        if agg.total_tokens > busiest_tokens:
            busiest_tokens = agg.total_tokens
            busiest_day = agg.date

    # Calculate totals
    total_sessions = sum(d.sessions for d in daily_entries)
    total_input = sum(d.input_tokens for d in daily_entries)
    total_output = sum(d.output_tokens for d in daily_entries)
    total_tokens = sum(d.total_tokens for d in daily_entries)
    total_cost = sum(d.cost_usd for d in daily_entries)

    # Calculate trends
    direction, change_percent, avg_cost = _calculate_usage_trends(trend_data)

    return GetDailySummaryOutput(
        period=UsagePeriod(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            days=days,
        ),
        totals=UsageTotals(
            sessions=total_sessions,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_tokens,
            cost_usd=round(total_cost, 6),
        ),
        daily=daily_entries,
        trends=UsageTrends(
            direction=direction,
            change_percent=change_percent,
            busiest_day=busiest_day,
            avg_daily_cost=avg_cost,
        ),
    )


# ============================================================================
# Tool 10: get_weekly_summary (v1.0.2)
# ============================================================================


def get_weekly_summary(
    weeks: int = 4,
    start_of_week: WeekStartDay = WeekStartDay.MONDAY,
    platform: ServerPlatform | None = None,
    breakdown: bool = False,
) -> GetWeeklySummaryOutput:
    """
    Retrieve weekly token usage aggregation.

    Args:
        weeks: Number of weeks to include (default: 4, max: 52)
        start_of_week: Week boundary (Monday or Sunday)
        platform: Filter by platform (all platforms if not specified)
        breakdown: Include per-model token breakdown

    Returns:
        Weekly usage summary with totals, per-week breakdown, and trends
    """
    from ..aggregation import aggregate_weekly
    from ..storage import StorageManager

    storage = StorageManager()
    end_date = date.today()
    # Calculate start date to cover requested weeks
    start_date = end_date - timedelta(weeks=weeks)

    # Map platform enum to storage Platform type
    platform_filter: Optional[Platform] = platform.value if platform else None

    # Map start_of_week to integer (0=Monday, 6=Sunday)
    week_start_int = 0 if start_of_week == WeekStartDay.MONDAY else 6

    # Get weekly aggregates
    weekly_aggregates = aggregate_weekly(
        platform=platform_filter,
        start_date=start_date,
        end_date=end_date,
        start_of_week=week_start_int,
        storage=storage,
    )

    # Build weekly entries
    weekly_entries: List[WeeklyUsageEntry] = []
    trend_data: List[Tuple[float, int]] = []
    busiest_week: Optional[str] = None
    busiest_tokens = 0

    for agg in weekly_aggregates:
        cost_usd = float(agg.cost_usd)
        avg_session_cost = cost_usd / agg.session_count if agg.session_count > 0 else 0.0

        entry = WeeklyUsageEntry(
            week_start=agg.week_start,
            week_end=agg.week_end,
            sessions=agg.session_count,
            input_tokens=agg.input_tokens,
            output_tokens=agg.output_tokens,
            total_tokens=agg.total_tokens,
            cost_usd=cost_usd,
            avg_session_cost=round(avg_session_cost, 6),
            model_breakdown=(
                {k: v.to_dict() for k, v in agg.model_breakdowns.items()} if breakdown else None
            ),
        )
        weekly_entries.append(entry)
        trend_data.append((cost_usd, agg.total_tokens))

        if agg.total_tokens > busiest_tokens:
            busiest_tokens = agg.total_tokens
            busiest_week = agg.week_start

    # Calculate totals
    total_sessions = sum(w.sessions for w in weekly_entries)
    total_input = sum(w.input_tokens for w in weekly_entries)
    total_output = sum(w.output_tokens for w in weekly_entries)
    total_tokens = sum(w.total_tokens for w in weekly_entries)
    total_cost = sum(w.cost_usd for w in weekly_entries)

    # Calculate trends
    direction, change_percent, avg_cost = _calculate_usage_trends(trend_data)

    # Determine period start/end from actual data
    if weekly_entries:
        period_start = weekly_entries[0].week_start
        period_end = weekly_entries[-1].week_end
    else:
        period_start = start_date.isoformat()
        period_end = end_date.isoformat()

    return GetWeeklySummaryOutput(
        period=UsagePeriod(
            start=period_start,
            end=period_end,
            weeks=weeks,
        ),
        totals=UsageTotals(
            sessions=total_sessions,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_tokens,
            cost_usd=round(total_cost, 6),
        ),
        weekly=weekly_entries,
        trends=UsageTrends(
            direction=direction,
            change_percent=change_percent,
            busiest_day=busiest_week,  # Reusing field for busiest_week
            avg_daily_cost=avg_cost,  # Actually avg_weekly_cost here
        ),
    )


# ============================================================================
# Tool 11: get_monthly_summary (v1.0.2)
# ============================================================================


def get_monthly_summary(
    months: int = 3,
    platform: ServerPlatform | None = None,
    breakdown: bool = False,
) -> GetMonthlySummaryOutput:
    """
    Retrieve monthly token usage aggregation.

    Args:
        months: Number of months to include (default: 3, max: 24)
        platform: Filter by platform (all platforms if not specified)
        breakdown: Include per-model token breakdown

    Returns:
        Monthly usage summary with totals, per-month breakdown, and trends
    """
    from ..aggregation import aggregate_monthly
    from ..storage import StorageManager

    storage = StorageManager()
    end_date = date.today()
    # Calculate start date to cover requested months
    start_date = date(end_date.year, end_date.month, 1) - timedelta(days=30 * (months - 1))

    # Map platform enum to storage Platform type
    platform_filter: Optional[Platform] = platform.value if platform else None

    # Get monthly aggregates
    monthly_aggregates = aggregate_monthly(
        platform=platform_filter,
        start_date=start_date,
        end_date=end_date,
        storage=storage,
    )

    # Build monthly entries
    monthly_entries: List[MonthlyUsageEntry] = []
    trend_data: List[Tuple[float, int]] = []
    busiest_month: Optional[str] = None
    busiest_tokens = 0

    for agg in monthly_aggregates:
        cost_usd = float(agg.cost_usd)

        entry = MonthlyUsageEntry(
            month=agg.month_str,
            sessions=agg.session_count,
            input_tokens=agg.input_tokens,
            output_tokens=agg.output_tokens,
            total_tokens=agg.total_tokens,
            cost_usd=cost_usd,
            model_breakdown=(
                {k: v.to_dict() for k, v in agg.model_breakdowns.items()} if breakdown else None
            ),
        )
        monthly_entries.append(entry)
        trend_data.append((cost_usd, agg.total_tokens))

        if agg.total_tokens > busiest_tokens:
            busiest_tokens = agg.total_tokens
            busiest_month = agg.month_str

    # Calculate totals
    total_sessions = sum(m.sessions for m in monthly_entries)
    total_input = sum(m.input_tokens for m in monthly_entries)
    total_output = sum(m.output_tokens for m in monthly_entries)
    total_tokens = sum(m.total_tokens for m in monthly_entries)
    total_cost = sum(m.cost_usd for m in monthly_entries)

    # Calculate trends
    direction, change_percent, avg_cost = _calculate_usage_trends(trend_data)

    # Determine period start/end from actual data
    if monthly_entries:
        period_start = f"{monthly_entries[0].month}-01"
        # Last day of the last month
        last_month = monthly_entries[-1].month
        year, month_num = map(int, last_month.split("-"))
        next_month = date(year + 1, 1, 1) if month_num == 12 else date(year, month_num + 1, 1)
        period_end = (next_month - timedelta(days=1)).isoformat()
    else:
        period_start = start_date.isoformat()
        period_end = end_date.isoformat()

    return GetMonthlySummaryOutput(
        period=UsagePeriod(
            start=period_start,
            end=period_end,
            months=months,
        ),
        totals=UsageTotals(
            sessions=total_sessions,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_tokens,
            cost_usd=round(total_cost, 6),
        ),
        monthly=monthly_entries,
        trends=UsageTrends(
            direction=direction,
            change_percent=change_percent,
            busiest_day=busiest_month,  # Reusing field for busiest_month
            avg_daily_cost=avg_cost,  # Actually avg_monthly_cost here
        ),
    )


# ============================================================================
# Tool 12: list_sessions (v1.0.2)
# ============================================================================


def list_sessions(
    limit: int = 20,
    offset: int = 0,
    platform: ServerPlatform | None = None,
    project: str | None = None,
    since: str | None = None,
    until: str | None = None,
    sort_by: SessionSortBy = SessionSortBy.DATE,
    sort_order: SortOrder = SortOrder.DESC,
) -> ListSessionsOutput:
    """
    Query and list historical sessions with filtering.

    Args:
        limit: Maximum sessions to return (1-100)
        offset: Pagination offset
        platform: Filter by platform
        project: Filter by project name
        since: Only sessions after this date (YYYY-MM-DD)
        until: Only sessions before this date (YYYY-MM-DD)
        sort_by: Sort field (date, cost, tokens, duration)
        sort_order: Sort order (asc, desc)

    Returns:
        Paginated list of session summaries
    """
    from ..session_manager import SessionManager
    from ..storage import StorageManager

    storage = StorageManager()
    session_manager = SessionManager()

    # Parse date filters
    start_date = date.fromisoformat(since) if since else None
    end_date = date.fromisoformat(until) if until else None

    # Map platform enum to storage Platform type
    platform_filter: Optional[Platform] = platform.value if platform else None

    # Get all matching sessions
    session_paths = storage.list_sessions(
        platform=platform_filter,
        start_date=start_date,
        end_date=end_date,
    )

    # Load session data for sorting and filtering
    sessions_data: List[Dict[str, Any]] = []
    for path in session_paths:
        session = session_manager.load_session(path)
        if session is None:
            continue

        # Filter by project if specified
        if project and session.working_directory != project:
            continue

        # Calculate duration
        if session.end_timestamp and session.timestamp:
            try:
                # Both are datetime objects
                duration_seconds = int((session.end_timestamp - session.timestamp).total_seconds())
            except (ValueError, TypeError):
                duration_seconds = 0
        else:
            duration_seconds = 0

        # Determine data quality
        if session.token_usage and session.token_usage.total_tokens > 0:
            data_quality = DataQuality.EXACT
        elif session.mcp_tool_calls and session.mcp_tool_calls.total_calls > 0:
            data_quality = DataQuality.CALLS_ONLY
        else:
            data_quality = DataQuality.ESTIMATED

        # Get primary model
        primary_model = None
        if session.model_usage:
            # Get model with most calls
            max_calls = 0
            for model_name, usage in session.model_usage.items():
                if usage.call_count > max_calls:
                    max_calls = usage.call_count
                    primary_model = model_name

        # Count smells
        smells_count = len(session.smells) if session.smells else 0

        # Convert timestamps to ISO strings
        started_at_str = session.timestamp.isoformat() if session.timestamp else ""
        ended_at_str = session.end_timestamp.isoformat() if session.end_timestamp else None

        sessions_data.append(
            {
                "session_id": path.stem,
                "platform": session.platform or "unknown",
                "project": session.working_directory,
                "started_at": started_at_str,
                "ended_at": ended_at_str,
                "duration_seconds": duration_seconds,
                "total_tokens": session.token_usage.total_tokens if session.token_usage else 0,
                "cost_usd": session.cost_estimate or 0.0,
                "model": primary_model,
                "tool_calls": session.mcp_tool_calls.total_calls if session.mcp_tool_calls else 0,
                "smells_detected": smells_count,
                "data_quality": data_quality,
            }
        )

    # Sort sessions
    reverse = sort_order == SortOrder.DESC
    if sort_by == SessionSortBy.DATE:
        sessions_data.sort(key=lambda s: s["started_at"], reverse=reverse)
    elif sort_by == SessionSortBy.COST:
        sessions_data.sort(key=lambda s: s["cost_usd"], reverse=reverse)
    elif sort_by == SessionSortBy.TOKENS:
        sessions_data.sort(key=lambda s: s["total_tokens"], reverse=reverse)
    elif sort_by == SessionSortBy.DURATION:
        sessions_data.sort(key=lambda s: s["duration_seconds"], reverse=reverse)

    # Calculate pagination
    total = len(sessions_data)
    has_more = offset + limit < total

    # Apply pagination
    paginated = sessions_data[offset : offset + limit]

    # Convert to output schema
    entries = [
        SessionListEntry(
            session_id=s["session_id"],
            platform=s["platform"],
            project=s["project"],
            started_at=s["started_at"],
            ended_at=s["ended_at"],
            duration_seconds=s["duration_seconds"],
            total_tokens=s["total_tokens"],
            cost_usd=s["cost_usd"],
            model=s["model"],
            tool_calls=s["tool_calls"],
            smells_detected=s["smells_detected"],
            data_quality=s["data_quality"],
        )
        for s in paginated
    ]

    return ListSessionsOutput(
        sessions=entries,
        pagination=PaginationInfo(
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        ),
    )


# ============================================================================
# Tool 13: get_session_details (v1.0.2)
# ============================================================================


def get_session_details(
    session_id: str,
    include_tool_calls: bool = True,
    include_smells: bool = True,
    include_recommendations: bool = True,
) -> GetSessionDetailsOutput:
    """
    Retrieve complete session data including tool calls and smells.

    Args:
        session_id: Session ID to retrieve
        include_tool_calls: Include individual tool call details
        include_smells: Include detected efficiency smells
        include_recommendations: Include optimization recommendations

    Returns:
        Comprehensive session details with optional sections
    """
    from ..session_manager import SessionManager
    from ..storage import StorageManager

    storage = StorageManager()
    session_manager = SessionManager()

    # Find session file
    session_path = storage.find_session(session_id)
    if session_path is None:
        # Return empty result with error message
        return GetSessionDetailsOutput(
            session=SessionMetadata(
                session_id=session_id,
                platform="unknown",
                started_at="",
                duration_seconds=0,
            ),
            token_usage=SessionTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
            ),
            mcp_usage=MCPUsage(),
            data_quality=DataQualityInfo(
                accuracy_level=DataQuality.ESTIMATED,
                pricing_source="none",
                confidence=0.0,
            ),
        )

    # Load session
    session = session_manager.load_session(session_path)
    if session is None:
        return GetSessionDetailsOutput(
            session=SessionMetadata(
                session_id=session_id,
                platform="unknown",
                started_at="",
                duration_seconds=0,
            ),
            token_usage=SessionTokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
            ),
            mcp_usage=MCPUsage(),
            data_quality=DataQualityInfo(
                accuracy_level=DataQuality.ESTIMATED,
                pricing_source="none",
                confidence=0.0,
            ),
        )

    # Calculate duration
    duration_seconds = 0
    if session.end_timestamp and session.timestamp:
        with contextlib.suppress(ValueError, TypeError):
            # Both are datetime objects
            duration_seconds = int((session.end_timestamp - session.timestamp).total_seconds())

    # Get all models used
    models_used = list(session.model_usage.keys()) if session.model_usage else []
    primary_model = models_used[0] if models_used else None

    # Convert timestamps to ISO strings
    started_at_str = session.timestamp.isoformat() if session.timestamp else ""
    ended_at_str = session.end_timestamp.isoformat() if session.end_timestamp else None

    # Build session metadata
    session_meta = SessionMetadata(
        session_id=session_id,
        platform=session.platform or "unknown",
        project=session.working_directory,
        started_at=started_at_str,
        ended_at=ended_at_str,
        duration_seconds=duration_seconds,
        model=primary_model,
        models_used=models_used,
    )

    # Build token usage
    token_usage = SessionTokenUsage(
        input_tokens=session.token_usage.input_tokens if session.token_usage else 0,
        output_tokens=session.token_usage.output_tokens if session.token_usage else 0,
        cache_read_tokens=session.token_usage.cache_read_tokens if session.token_usage else 0,
        cache_write_tokens=session.token_usage.cache_created_tokens if session.token_usage else 0,
        total_tokens=session.token_usage.total_tokens if session.token_usage else 0,
        cost_usd=session.cost_estimate or 0.0,
    )

    # Build MCP usage
    servers: List[ServerUsage] = []
    top_tools_list: List[TopTool] = []

    if session.server_sessions:
        for server_name, server_data in session.server_sessions.items():
            if isinstance(server_data, dict):
                tools_used = len(server_data.get("tools", {}))
                total_calls = sum(
                    t.get("call_count", 0) for t in server_data.get("tools", {}).values()
                )
                total_tokens = sum(
                    t.get("total_tokens", 0) for t in server_data.get("tools", {}).values()
                )
                servers.append(
                    ServerUsage(
                        name=server_name,
                        tools_used=tools_used,
                        total_calls=total_calls,
                        total_tokens=total_tokens,
                    )
                )

    # Get top tools from server_sessions (MCPToolCalls is just a summary)
    # Tool usage details are stored in server_sessions
    if session.server_sessions:
        tool_calls_counter: Dict[str, int] = {}
        for server_session in session.server_sessions.values():
            if hasattr(server_session, "tools"):
                for tool_name, tool_stats in server_session.tools.items():
                    call_count = tool_stats.call_count if hasattr(tool_stats, "call_count") else 0
                    tool_calls_counter[tool_name] = (
                        tool_calls_counter.get(tool_name, 0) + call_count
                    )
        tool_items = sorted(tool_calls_counter.items(), key=lambda x: x[1], reverse=True)[:10]
        for tool_name, calls in tool_items:
            top_tools_list.append(
                TopTool(
                    name=tool_name,
                    calls=calls,
                    tokens=0,  # Token breakdown not always available
                    avg_tokens=0.0,
                )
            )

    mcp_usage = MCPUsage(servers=servers, top_tools=top_tools_list)

    # Build tool calls if requested
    tool_calls_list: List[ToolCallEntry] = []
    if include_tool_calls and hasattr(session, "tool_calls_log"):
        for call in getattr(session, "tool_calls_log", []):
            if isinstance(call, dict):
                tool_calls_list.append(
                    ToolCallEntry(
                        timestamp=call.get("timestamp", ""),
                        tool_name=call.get("tool", ""),
                        server=call.get("server", ""),
                        tokens_in=call.get("tokens_in", 0),
                        tokens_out=call.get("tokens_out", 0),
                        is_estimated=call.get("is_estimated", False),
                    )
                )

    # Build smells if requested
    smells_list: List[SmellEntry] = []
    if include_smells and session.smells:
        for smell in session.smells:
            smells_list.append(
                SmellEntry(
                    pattern=smell.pattern,
                    severity=_severity_to_enum(smell.severity),
                    message=smell.description or "",
                    evidence=smell.evidence or {},
                )
            )

    # Build recommendations if requested
    recommendations_list: List[Recommendation] = []
    if include_recommendations and session.smells:
        smell_objects = session.smells
        engine = RecommendationEngine()
        internal_recs = engine.generate(smell_objects)
        for idx, rec in enumerate(internal_recs[:5], start=1):
            recommendations_list.append(_internal_to_schema_recommendation(rec, idx))

    # Determine data quality
    if session.token_usage and session.token_usage.total_tokens > 0:
        accuracy = DataQuality.EXACT
        confidence = 0.95
    elif session.mcp_tool_calls and session.mcp_tool_calls.total_calls > 0:
        accuracy = DataQuality.CALLS_ONLY
        confidence = 0.7
    else:
        accuracy = DataQuality.ESTIMATED
        confidence = 0.5

    data_quality = DataQualityInfo(
        accuracy_level=accuracy,
        pricing_source="token-audit.toml" if session.cost_estimate else "estimated",
        confidence=confidence,
    )

    return GetSessionDetailsOutput(
        session=session_meta,
        token_usage=token_usage,
        mcp_usage=mcp_usage,
        tool_calls=tool_calls_list if include_tool_calls else [],
        smells=smells_list if include_smells else [],
        recommendations=recommendations_list if include_recommendations else [],
        data_quality=data_quality,
    )


# ============================================================================
# Tool 14: pin_server (v1.0.2)
# ============================================================================


def pin_server(
    server_name: str,
    notes: str | None = None,
    action: PinAction = PinAction.PIN,
) -> PinServerOutput:
    """
    Add, update, or remove a pinned MCP server.

    Args:
        server_name: MCP server name to pin/unpin
        notes: Optional notes about why this server is pinned
        action: Pin or unpin the server

    Returns:
        Operation result with updated pinned servers list
    """
    from ..pinned_config import PinnedConfigManager

    manager = PinnedConfigManager()

    if action == PinAction.PIN:
        # Check if already pinned
        was_pinned = manager.is_pinned(server_name)
        manager.pin(server_name, notes=notes)
        message = (
            f"Server '{server_name}' was already pinned."
            if was_pinned
            else f"Server '{server_name}' has been pinned."
        )
        success = True
    else:
        # Remove pinned server
        success = manager.unpin(server_name)
        message = (
            f"Server '{server_name}' has been unpinned."
            if success
            else f"Server '{server_name}' was not pinned."
        )

    # Get updated list of pinned servers
    config = manager.get_effective_config()
    pinned_list = config.explicit_servers

    return PinServerOutput(
        success=success,
        action=action,
        server_name=server_name,
        message=message,
        pinned_servers=list(pinned_list),
    )


# ============================================================================
# Tool 15: delete_session (v1.0.2)
# ============================================================================


def delete_session(
    session_id: str,
    confirm: bool = False,
) -> DeleteSessionOutput:
    """
    Delete a session from storage.

    Args:
        session_id: Session ID to delete
        confirm: Must be true to confirm deletion (safety check)

    Returns:
        Deletion result with status message
    """
    from ..storage import StorageManager

    if not confirm:
        return DeleteSessionOutput(
            success=False,
            session_id=session_id,
            message="Deletion not confirmed. Set confirm=true to delete the session.",
            deleted_at=None,
        )

    storage = StorageManager()

    # Find session file
    session_path = storage.find_session(session_id)
    if session_path is None:
        return DeleteSessionOutput(
            success=False,
            session_id=session_id,
            message=f"Session '{session_id}' not found.",
            deleted_at=None,
        )

    try:
        # Delete the session file
        session_path.unlink()

        # Also delete any associated .jsonl file
        jsonl_path = session_path.with_suffix(".jsonl")
        if jsonl_path.exists():
            jsonl_path.unlink()

        deleted_at = datetime.now().isoformat()

        return DeleteSessionOutput(
            success=True,
            session_id=session_id,
            message=f"Session '{session_id}' has been deleted.",
            deleted_at=deleted_at,
        )
    except OSError as e:
        return DeleteSessionOutput(
            success=False,
            session_id=session_id,
            message=f"Failed to delete session: {e}",
            deleted_at=None,
        )


# ============================================================================
# Tool 16: config_list_patterns (v1.0.4 - bucket configuration)
# ============================================================================


def config_list_patterns(
    bucket: Optional[str] = None,
) -> ConfigListPatternsOutput:
    """
    List bucket classification patterns and thresholds.

    Returns the current bucket configuration, optionally filtered by bucket name.
    Useful for AI agents to understand how tool calls are classified.

    Args:
        bucket: Optional bucket name to filter (state_serialization or tool_discovery).
            If None, returns patterns for all buckets.

    Returns:
        Configuration with patterns and thresholds.
    """
    from ..bucket_config import load_config

    config = load_config()

    # Filter by bucket if specified
    patterns = config.patterns
    if bucket is not None:
        patterns = {bucket: patterns[bucket]} if bucket in patterns else {}

    thresholds = {
        "large_payload_threshold": config.large_payload_threshold,
        "redundant_min_occurrences": config.redundant_min_occurrences,
    }

    return ConfigListPatternsOutput(
        patterns=patterns,
        thresholds=thresholds,
        config_path=str(config.config_path) if config.config_path else None,
    )


# ============================================================================
# Tool 17: config_add_pattern (v1.0.4 - bucket configuration)
# ============================================================================


def config_add_pattern(
    bucket: str,
    pattern: str,
) -> ConfigAddPatternOutput:
    """
    Add a regex pattern to a bucket classification.

    Patterns are used to classify tool calls into buckets for analysis.
    The pattern is validated as a valid regex before being added.

    Args:
        bucket: Bucket name (state_serialization or tool_discovery).
        pattern: Regex pattern to add (e.g., '.*_get_.*').

    Returns:
        Result with updated pattern list for the bucket.
    """
    from ..bucket_config import add_pattern, load_config, save_config

    try:
        config = load_config()
        add_pattern(config, bucket, pattern)
        save_config(config)

        return ConfigAddPatternOutput(
            success=True,
            message=f"Added pattern '{pattern}' to bucket '{bucket}'",
            bucket=bucket,
            patterns=config.patterns.get(bucket, []),
        )
    except ValueError as e:
        return ConfigAddPatternOutput(
            success=False,
            message=str(e),
            bucket=bucket,
            patterns=[],
        )
    except RuntimeError as e:
        return ConfigAddPatternOutput(
            success=False,
            message=f"Failed to save config: {e}",
            bucket=bucket,
            patterns=[],
        )


# ============================================================================
# Tool 18: config_remove_pattern (v1.0.4 - bucket configuration)
# ============================================================================


def config_remove_pattern(
    bucket: str,
    pattern: str,
) -> ConfigRemovePatternOutput:
    """
    Remove a regex pattern from a bucket classification.

    Args:
        bucket: Bucket name (state_serialization or tool_discovery).
        pattern: Exact pattern string to remove.

    Returns:
        Result with updated pattern list for the bucket.
    """
    from ..bucket_config import load_config, remove_pattern, save_config

    try:
        config = load_config()

        # Check if bucket exists
        if bucket not in config.patterns:
            return ConfigRemovePatternOutput(
                success=False,
                message=f"Unknown bucket '{bucket}'",
                bucket=bucket,
                patterns=[],
            )

        # Check if pattern exists
        if pattern not in config.patterns[bucket]:
            return ConfigRemovePatternOutput(
                success=False,
                message=f"Pattern '{pattern}' not found in bucket '{bucket}'",
                bucket=bucket,
                patterns=config.patterns.get(bucket, []),
            )

        remove_pattern(config, bucket, pattern)
        save_config(config)

        return ConfigRemovePatternOutput(
            success=True,
            message=f"Removed pattern '{pattern}' from bucket '{bucket}'",
            bucket=bucket,
            patterns=config.patterns.get(bucket, []),
        )
    except RuntimeError as e:
        return ConfigRemovePatternOutput(
            success=False,
            message=f"Failed to save config: {e}",
            bucket=bucket,
            patterns=[],
        )


# ============================================================================
# Tool 19: config_set_threshold (v1.0.4 - bucket configuration)
# ============================================================================


def config_set_threshold(
    name: str,
    value: int,
) -> ConfigSetThresholdOutput:
    """
    Set a bucket threshold value.

    Thresholds control how tool calls are classified:
    - large_payload_threshold: Token count above which calls are classified as state_serialization
    - redundant_min_occurrences: Minimum content_hash occurrences to classify as redundant

    Args:
        name: Threshold name (large_payload_threshold or redundant_min_occurrences).
        value: New threshold value (must be positive integer).

    Returns:
        Result with updated threshold settings.
    """
    from ..bucket_config import load_config, save_config, set_threshold

    try:
        config = load_config()
        set_threshold(config, name, value)
        save_config(config)

        thresholds = {
            "large_payload_threshold": config.large_payload_threshold,
            "redundant_min_occurrences": config.redundant_min_occurrences,
        }

        return ConfigSetThresholdOutput(
            success=True,
            message=f"Set {name} to {value}",
            thresholds=thresholds,
        )
    except ValueError as e:
        return ConfigSetThresholdOutput(
            success=False,
            message=str(e),
            thresholds={},
        )
    except RuntimeError as e:
        return ConfigSetThresholdOutput(
            success=False,
            message=f"Failed to save config: {e}",
            thresholds={},
        )


# ============================================================================
# Tool 20: bucket_analyze (v1.0.4 - bucket classification)
# ============================================================================


def bucket_analyze(
    session_id: Optional[str] = None,
    include_tools: bool = True,
) -> BucketAnalyzeOutput:
    """
    Analyze a session's bucket classification.

    Classifies all tool calls in a session into 4 buckets:
    - state_serialization: Large payloads and data retrieval calls
    - tool_discovery: Introspection and schema calls
    - redundant: Duplicate calls (same content_hash)
    - drift: Everything else (reasoning, retries, errors)

    Args:
        session_id: Session ID to analyze (uses latest if not specified).
        include_tools: Include list of top tools per bucket.

    Returns:
        Bucket breakdown with token distribution and summary.
    """
    from ..bucket_config import load_config
    from ..buckets import BucketClassifier
    from ..storage import StorageManager

    storage = StorageManager()

    # Find session
    if session_id is None:
        # Get latest session
        sessions = list(storage.list_sessions())
        if not sessions:
            return BucketAnalyzeOutput(
                success=False,
                session_id="",
                buckets={},
                total_tokens=0,
                total_calls=0,
                summary="No sessions found",
                message="No sessions available for analysis",
            )
        # Sort by timestamp descending and get the first
        sessions.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
        session_path = storage.find_session(sessions[0]["id"])
        actual_session_id = sessions[0]["id"]
    else:
        session_path = storage.find_session(session_id)
        actual_session_id = session_id

    if session_path is None:
        return BucketAnalyzeOutput(
            success=False,
            session_id=session_id or "",
            buckets={},
            total_tokens=0,
            total_calls=0,
            summary=f"Session not found: {session_id}",
            message=f"Session '{session_id}' not found in storage",
        )

    # Load session
    try:
        session = storage.load_session(session_path)
    except Exception as e:
        return BucketAnalyzeOutput(
            success=False,
            session_id=actual_session_id,
            buckets={},
            total_tokens=0,
            total_calls=0,
            summary=f"Failed to load session: {e}",
            message=str(e),
        )

    # Load config and create classifier
    config = load_config()
    classifier = BucketClassifier(
        patterns=config.patterns,
        thresholds={
            "large_payload_threshold": config.large_payload_threshold,
            "redundant_min_occurrences": config.redundant_min_occurrences,
        },
    )

    # Classify all calls
    results = classifier.classify_session(session)

    # Aggregate by bucket
    bucket_data: Dict[str, Dict[str, Any]] = {
        "state_serialization": {"count": 0, "tokens": 0, "tools": Counter()},
        "tool_discovery": {"count": 0, "tokens": 0, "tools": Counter()},
        "redundant": {"count": 0, "tokens": 0, "tools": Counter()},
        "drift": {"count": 0, "tokens": 0, "tools": Counter()},
    }

    total_tokens = 0
    total_calls = 0

    for result in results:
        bucket = result.bucket
        tokens = result.tokens
        tool = result.tool_name

        bucket_data[bucket]["count"] += 1
        bucket_data[bucket]["tokens"] += tokens
        bucket_data[bucket]["tools"][tool] += 1
        total_tokens += tokens
        total_calls += 1

    # Build output
    buckets: Dict[str, BucketStats] = {}
    for bucket_name, data in bucket_data.items():
        percentage = (data["tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0
        top_tools = [tool for tool, _ in data["tools"].most_common(10)] if include_tools else []

        buckets[bucket_name] = BucketStats(
            count=data["count"],
            tokens=data["tokens"],
            percentage=round(percentage, 2),
            tools=top_tools,
        )

    # Build summary
    summary_parts = []
    for bucket_name in ["state_serialization", "redundant", "tool_discovery", "drift"]:
        stats = buckets[bucket_name]
        if stats.count > 0:
            summary_parts.append(f"{bucket_name}: {stats.percentage:.1f}%")

    summary = " | ".join(summary_parts) if summary_parts else "No tool calls found"

    return BucketAnalyzeOutput(
        success=True,
        session_id=actual_session_id,
        buckets=buckets,
        total_tokens=total_tokens,
        total_calls=total_calls,
        summary=summary,
        message=None,
    )
