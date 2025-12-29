"""
MCP Server entry point for token-audit.

This module provides the FastMCP-based server implementation using stdio transport.
It enables AI agents to query token-audit metrics programmatically during sessions.

Usage:
    token-audit-server  # Start stdio server

Or programmatically:
    from token_audit.server import create_server, run_server
    server = create_server()
    run_server()
"""

from typing import Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    raise ImportError(
        "MCP server dependencies not installed. " "Install with: pip install token-audit[server]"
    ) from e

from . import tools
from .schemas import (
    PinAction,
    ReportFormat,
    ServerPlatform,
    SessionSortBy,
    SeverityLevel,
    SortOrder,
    TrendPeriod,
    WeekStartDay,
)


def create_server() -> FastMCP:
    """
    Create and configure the token-audit MCP server.

    Returns:
        Configured FastMCP server instance with all tools registered.
    """
    mcp = FastMCP(name="token-audit")

    # ========================================================================
    # Tool 1: start_tracking
    # ========================================================================
    @mcp.tool()
    def start_tracking(
        platform: str,
        project: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Begin live tracking of an AI agent session.

        This tool initializes a new tracking session for the specified platform.
        Once started, the session collects metrics that can be queried via
        get_metrics and analyzed via analyze_session.

        Args:
            platform: AI coding platform to track. Valid values:
                     "claude_code", "codex_cli", "gemini_cli"
            project: Optional project name for grouping sessions

        Returns:
            Session information including session_id for subsequent queries
        """
        # Validate and convert platform string to enum
        try:
            platform_enum = ServerPlatform(platform)
        except ValueError:
            valid = ", ".join(p.value for p in ServerPlatform)
            return {
                "session_id": "",
                "platform": platform,
                "project": project,
                "started_at": "",
                "status": "error",
                "message": f"Invalid platform '{platform}'. Valid: {valid}",
            }

        result = tools.start_tracking(platform=platform_enum, project=project)
        return result.model_dump()

    # ========================================================================
    # Tool 2: get_metrics
    # ========================================================================
    @mcp.tool()
    def get_metrics(
        session_id: Optional[str] = None,
        include_smells: bool = True,
        include_breakdown: bool = True,
    ) -> dict[str, Any]:
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
        result = tools.get_metrics(
            session_id=session_id,
            include_smells=include_smells,
            include_breakdown=include_breakdown,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 3: get_recommendations
    # ========================================================================
    @mcp.tool()
    def get_recommendations(
        session_id: Optional[str] = None,
        severity_filter: Optional[str] = None,
        max_recommendations: int = 5,
    ) -> dict[str, Any]:
        """
        Get optimization recommendations for the session.

        Analyzes the session and returns prioritized recommendations
        for improving efficiency and reducing token usage.

        Args:
            session_id: Session ID to analyze (uses active session if not specified)
            severity_filter: Minimum severity level to include.
                           Valid: "critical", "high", "medium", "low", "info"
            max_recommendations: Maximum number of recommendations to return

        Returns:
            Prioritized list of recommendations with expected impact

        Note:
            Full implementation in Phase 2
        """
        severity_enum = None
        if severity_filter:
            try:
                severity_enum = SeverityLevel(severity_filter)
            except ValueError:
                pass  # Will use None (no filter)

        result = tools.get_recommendations(
            session_id=session_id,
            severity_filter=severity_enum,
            max_recommendations=max_recommendations,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 4: analyze_session
    # ========================================================================
    @mcp.tool()
    def analyze_session(
        session_id: Optional[str] = None,
        format: str = "json",
        include_model_usage: bool = True,
        include_zombie_tools: bool = True,
    ) -> dict[str, Any]:
        """
        Perform end-of-session analysis.

        Generates a comprehensive analysis of the session including
        metrics, recommendations, unused tools, and per-model breakdown.

        Args:
            session_id: Session ID to analyze (uses active session if not specified)
            format: Output format. Valid: "json", "markdown", "summary"
            include_model_usage: Include per-model breakdown
            include_zombie_tools: Include unused tool analysis

        Returns:
            Complete session analysis with recommendations

        Note:
            Full implementation in Phase 2
        """
        try:
            format_enum = ReportFormat(format)
        except ValueError:
            format_enum = ReportFormat.JSON

        result = tools.analyze_session(
            session_id=session_id,
            format=format_enum,
            include_model_usage=include_model_usage,
            include_zombie_tools=include_zombie_tools,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 5: get_best_practices
    # ========================================================================
    @mcp.tool()
    def get_best_practices(
        topic: Optional[str] = None,
        list_all: bool = False,
    ) -> dict[str, Any]:
        """
        Retrieve MCP best practices guidance.

        Returns best practices documentation filtered by topic,
        or lists all available topics.

        Args:
            topic: Topic to search for (e.g., "caching", "progressive disclosure")
            list_all: List all available best practice topics

        Returns:
            Matching best practices with full markdown content

        Note:
            Full implementation in Phase 2
        """
        result = tools.get_best_practices(topic=topic, list_all=list_all)
        return result.model_dump()

    # ========================================================================
    # Tool 6: analyze_config
    # ========================================================================
    @mcp.tool()
    def analyze_config(
        platform: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Analyze MCP configuration files.

        Examines platform configuration files for issues like
        hardcoded credentials, too many servers, or misconfigurations.

        Args:
            platform: Platform to analyze. Valid: "claude_code", "codex_cli", "gemini_cli"
                     Analyzes all platforms if not specified.
            config_path: Custom config file path (uses default if not specified)

        Returns:
            Configuration analysis with detected issues and server inventory

        Note:
            Full implementation in Phase 2b
        """
        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass  # Will use None (analyze all)

        result = tools.analyze_config(platform=platform_enum, config_path=config_path)
        return result.model_dump()

    # ========================================================================
    # Tool 7: get_pinned_servers
    # ========================================================================
    @mcp.tool()
    def get_pinned_servers(
        include_auto_detected: bool = True,
    ) -> dict[str, Any]:
        """
        Get user's pinned MCP servers.

        Returns the list of servers the user has pinned for focused analysis,
        including auto-detected custom servers if enabled.

        Args:
            include_auto_detected: Include auto-detected pinned servers

        Returns:
            List of pinned servers with detection method

        Note:
            Full implementation in Phase 2b
        """
        result = tools.get_pinned_servers(include_auto_detected=include_auto_detected)
        return result.model_dump()

    # ========================================================================
    # Tool 8: get_trends
    # ========================================================================
    @mcp.tool()
    def get_trends(
        period: str = "last_30_days",
        platform: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get cross-session pattern trends.

        Analyzes historical sessions to identify trends in efficiency
        patterns, helping identify systemic issues.

        Args:
            period: Time period for trend analysis. Valid:
                   "last_7_days", "last_30_days", "last_90_days", "all_time"
            platform: Filter by platform (all platforms if not specified)

        Returns:
            Trend analysis with pattern changes and recommendations

        Note:
            Full implementation in Phase 2c
        """
        try:
            period_enum = TrendPeriod(period)
        except ValueError:
            period_enum = TrendPeriod.LAST_30_DAYS

        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass

        result = tools.get_trends(period=period_enum, platform=platform_enum)
        return result.model_dump()

    # ========================================================================
    # Tool 9: get_daily_summary (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def get_daily_summary(
        days: int = 7,
        platform: Optional[str] = None,
        project: Optional[str] = None,
        breakdown: bool = False,
    ) -> dict[str, Any]:
        """
        Get daily token usage aggregation across sessions.

        Provides day-by-day breakdown of token usage and costs,
        with trend analysis and optional per-model breakdown.

        Args:
            days: Number of days to include (default: 7, max: 90)
            platform: Filter by platform. Valid: "claude_code", "codex_cli", "gemini_cli"
            project: Filter by project name
            breakdown: Include per-model token breakdown

        Returns:
            Daily usage summary with totals, per-day breakdown, and trends
        """
        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass

        result = tools.get_daily_summary(
            days=min(days, 90),
            platform=platform_enum,
            project=project,
            breakdown=breakdown,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 10: get_weekly_summary (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def get_weekly_summary(
        weeks: int = 4,
        start_of_week: str = "monday",
        platform: Optional[str] = None,
        breakdown: bool = False,
    ) -> dict[str, Any]:
        """
        Get weekly token usage aggregation.

        Provides week-by-week breakdown of token usage and costs,
        with configurable week boundaries and trend analysis.

        Args:
            weeks: Number of weeks to include (default: 4, max: 52)
            start_of_week: Week boundary. Valid: "monday", "sunday"
            platform: Filter by platform. Valid: "claude_code", "codex_cli", "gemini_cli"
            breakdown: Include per-model token breakdown

        Returns:
            Weekly usage summary with totals, per-week breakdown, and trends
        """
        try:
            week_start_enum = WeekStartDay(start_of_week.lower())
        except ValueError:
            week_start_enum = WeekStartDay.MONDAY

        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass

        result = tools.get_weekly_summary(
            weeks=min(weeks, 52),
            start_of_week=week_start_enum,
            platform=platform_enum,
            breakdown=breakdown,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 11: get_monthly_summary (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def get_monthly_summary(
        months: int = 3,
        platform: Optional[str] = None,
        breakdown: bool = False,
    ) -> dict[str, Any]:
        """
        Get monthly token usage aggregation.

        Provides month-by-month breakdown of token usage and costs,
        with trend analysis and optional per-model breakdown.

        Args:
            months: Number of months to include (default: 3, max: 24)
            platform: Filter by platform. Valid: "claude_code", "codex_cli", "gemini_cli"
            breakdown: Include per-model token breakdown

        Returns:
            Monthly usage summary with totals, per-month breakdown, and trends
        """
        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass

        result = tools.get_monthly_summary(
            months=min(months, 24),
            platform=platform_enum,
            breakdown=breakdown,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 12: list_sessions (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def list_sessions(
        limit: int = 20,
        offset: int = 0,
        platform: Optional[str] = None,
        project: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        """
        Query and list historical sessions with filtering.

        Provides paginated access to session history with various
        filter and sort options.

        Args:
            limit: Maximum sessions to return (1-100)
            offset: Pagination offset
            platform: Filter by platform. Valid: "claude_code", "codex_cli", "gemini_cli"
            project: Filter by project name
            since: Only sessions after this date (YYYY-MM-DD)
            until: Only sessions before this date (YYYY-MM-DD)
            sort_by: Sort field. Valid: "date", "cost", "tokens", "duration"
            sort_order: Sort order. Valid: "asc", "desc"

        Returns:
            Paginated list of session summaries
        """
        platform_enum = None
        if platform:
            try:
                platform_enum = ServerPlatform(platform)
            except ValueError:
                pass

        try:
            sort_by_enum = SessionSortBy(sort_by.lower())
        except ValueError:
            sort_by_enum = SessionSortBy.DATE

        try:
            sort_order_enum = SortOrder(sort_order.lower())
        except ValueError:
            sort_order_enum = SortOrder.DESC

        result = tools.list_sessions(
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
            platform=platform_enum,
            project=project,
            since=since,
            until=until,
            sort_by=sort_by_enum,
            sort_order=sort_order_enum,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 13: get_session_details (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def get_session_details(
        session_id: str,
        include_tool_calls: bool = True,
        include_smells: bool = True,
        include_recommendations: bool = True,
    ) -> dict[str, Any]:
        """
        Retrieve complete session data.

        Gets detailed information about a specific session including
        token usage, MCP server activity, tool calls, and detected smells.

        Args:
            session_id: Session ID to retrieve
            include_tool_calls: Include individual tool call details
            include_smells: Include detected efficiency smells
            include_recommendations: Include optimization recommendations

        Returns:
            Comprehensive session details with optional sections
        """
        result = tools.get_session_details(
            session_id=session_id,
            include_tool_calls=include_tool_calls,
            include_smells=include_smells,
            include_recommendations=include_recommendations,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 14: pin_server (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def pin_server(
        server_name: str,
        notes: Optional[str] = None,
        action: str = "pin",
    ) -> dict[str, Any]:
        """
        Add, update, or remove a pinned MCP server.

        Pinned servers receive focused analysis in recommendations
        and are tracked separately in usage reports.

        Args:
            server_name: MCP server name to pin/unpin
            notes: Optional notes about why this server is pinned
            action: Action to perform. Valid: "pin", "unpin"

        Returns:
            Operation result with updated pinned servers list
        """
        try:
            action_enum = PinAction(action.lower())
        except ValueError:
            action_enum = PinAction.PIN

        result = tools.pin_server(
            server_name=server_name,
            notes=notes,
            action=action_enum,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 15: delete_session (v1.0.2)
    # ========================================================================
    @mcp.tool()
    def delete_session(
        session_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """
        Delete a session from storage.

        Permanently removes a session and its associated data.
        Requires explicit confirmation for safety.

        Args:
            session_id: Session ID to delete
            confirm: Must be true to confirm deletion (safety check)

        Returns:
            Deletion result with status message
        """
        result = tools.delete_session(
            session_id=session_id,
            confirm=confirm,
        )
        return result.model_dump()

    # ========================================================================
    # Tool 16: config_list_patterns (v1.0.4 - bucket configuration)
    # ========================================================================
    @mcp.tool()
    def config_list_patterns(
        bucket: str | None = None,
    ) -> dict[str, Any]:
        """
        List bucket classification patterns and thresholds.

        Returns the current bucket configuration for token classification.
        Patterns determine how tool calls are categorized into 4 buckets:
        - state_serialization: Data retrieval patterns (.*_get_.*, .*_list_.*)
        - tool_discovery: Introspection patterns (.*_introspect.*, .*_describe.*)
        - redundant: Detected via content_hash (no patterns)
        - drift: Everything else

        Args:
            bucket: Optional filter by bucket name (state_serialization or tool_discovery)

        Returns:
            Current patterns and threshold settings
        """
        result = tools.config_list_patterns(bucket=bucket)
        return result.model_dump()

    # ========================================================================
    # Tool 17: config_add_pattern (v1.0.4 - bucket configuration)
    # ========================================================================
    @mcp.tool()
    def config_add_pattern(
        bucket: str,
        pattern: str,
    ) -> dict[str, Any]:
        """
        Add a regex pattern to a bucket classification.

        Extends the pattern list for a bucket. Useful for adding project-specific
        patterns (e.g., 'wpnav_get_.*' for WordPress Navigator tools).

        Args:
            bucket: Bucket name (state_serialization or tool_discovery)
            pattern: Regex pattern to add (e.g., '.*_get_.*')

        Returns:
            Success status and updated pattern list
        """
        result = tools.config_add_pattern(bucket=bucket, pattern=pattern)
        return result.model_dump()

    # ========================================================================
    # Tool 18: config_remove_pattern (v1.0.4 - bucket configuration)
    # ========================================================================
    @mcp.tool()
    def config_remove_pattern(
        bucket: str,
        pattern: str,
    ) -> dict[str, Any]:
        """
        Remove a regex pattern from a bucket classification.

        Removes an exact pattern from the bucket's pattern list.

        Args:
            bucket: Bucket name (state_serialization or tool_discovery)
            pattern: Exact pattern string to remove

        Returns:
            Success status and updated pattern list
        """
        result = tools.config_remove_pattern(bucket=bucket, pattern=pattern)
        return result.model_dump()

    # ========================================================================
    # Tool 19: config_set_threshold (v1.0.4 - bucket configuration)
    # ========================================================================
    @mcp.tool()
    def config_set_threshold(
        name: str,
        value: int,
    ) -> dict[str, Any]:
        """
        Set a bucket threshold value.

        Thresholds control classification behavior:
        - large_payload_threshold: Token count above which calls are state_serialization
        - redundant_min_occurrences: Minimum content_hash occurrences to mark as redundant

        Args:
            name: Threshold name (large_payload_threshold or redundant_min_occurrences)
            value: New threshold value (positive integer)

        Returns:
            Success status and updated thresholds
        """
        result = tools.config_set_threshold(name=name, value=value)
        return result.model_dump()

    # ========================================================================
    # Tool 20: bucket_analyze (v1.0.4 - bucket classification)
    # ========================================================================
    @mcp.tool()
    def bucket_analyze(
        session_id: str | None = None,
        include_tools: bool = True,
    ) -> dict[str, Any]:
        """
        Analyze a session's bucket classification.

        Classifies all tool calls in a session into 4 buckets and provides
        token distribution statistics. Essential for diagnosing token bloat.

        Buckets:
        - state_serialization: Large payloads and data retrieval
        - tool_discovery: Introspection and schema calls
        - redundant: Duplicate calls (same content_hash)
        - drift: Everything else (reasoning, retries, errors)

        Args:
            session_id: Session ID to analyze (uses latest if not specified)
            include_tools: Include top 10 tools per bucket

        Returns:
            Bucket breakdown with token percentages and summary
        """
        result = tools.bucket_analyze(
            session_id=session_id,
            include_tools=include_tools,
        )
        return result.model_dump()

    # ========================================================================
    # MCP Resources (v1.0.0 - task-194)
    # ========================================================================

    @mcp.resource("token-audit://best-practices")
    def best_practices_index() -> str:
        """
        List all available best practice patterns.

        Returns a markdown-formatted index of all best practices
        with IDs, titles, severities, and categories.
        """
        from ..guidance import BestPracticesLoader

        loader = BestPracticesLoader()
        practices = loader.load_all()

        if not practices:
            return "# MCP Best Practices\n\nNo best practices found."

        lines = ["# MCP Best Practices Index", ""]
        lines.append("Available patterns for optimizing MCP tool usage:")
        lines.append("")

        # Group by severity
        for severity in ["high", "medium", "low"]:
            severity_practices = [p for p in practices if p.severity == severity]
            if severity_practices:
                lines.append(f"## {severity.capitalize()} Priority")
                lines.append("")
                for p in severity_practices:
                    savings = f" ({p.token_savings} savings)" if p.token_savings else ""
                    lines.append(f"- **{p.title}** (`{p.id}`) - {p.category}{savings}")
                lines.append("")

        lines.append("---")
        lines.append("Use `token-audit://best-practices/{id}` to view details.")

        return "\n".join(lines)

    @mcp.resource("token-audit://best-practices/{pattern_id}")
    def best_practice_detail(pattern_id: str) -> str:
        """
        Get detailed content for a specific best practice pattern.

        Args:
            pattern_id: The pattern ID (e.g., "progressive_disclosure")

        Returns:
            Full markdown content for the pattern including problem,
            solution, implementation, and evidence.
        """
        from ..guidance import BestPracticesLoader

        loader = BestPracticesLoader()
        practice = loader.get_by_id(pattern_id)

        if not practice:
            available = [p.id for p in loader.load_all()]
            return f"""# Pattern Not Found: {pattern_id}

The pattern `{pattern_id}` was not found.

Available patterns:
{chr(10).join(f'- {p}' for p in available)}

Use `token-audit://best-practices` to see the full index.
"""

        lines = [
            f"# {practice.title}",
            "",
            f"**ID:** `{practice.id}`",
            f"**Severity:** {practice.severity}",
            f"**Category:** {practice.category}",
        ]

        if practice.token_savings:
            lines.append(f"**Token Savings:** {practice.token_savings}")
        if practice.source:
            lines.append(f"**Source:** {practice.source}")
        if practice.related_smells:
            lines.append(f"**Addresses Smells:** {', '.join(practice.related_smells)}")

        lines.append("")
        lines.append(practice.content)

        return "\n".join(lines)

    @mcp.resource("token-audit://best-practices/category/{category}")
    def best_practices_by_category(category: str) -> str:
        """
        Get best practices filtered by category.

        Args:
            category: Category to filter by (efficiency, security, design, operations)

        Returns:
            Markdown-formatted list of practices in the category.
        """
        from ..guidance import BestPracticesExporter, BestPracticesLoader

        loader = BestPracticesLoader()

        # Validate category
        valid_categories = ["efficiency", "security", "design", "operations"]
        if category.lower() not in valid_categories:
            return f"""# Invalid Category: {category}

Valid categories:
{chr(10).join(f'- {c}' for c in valid_categories)}

Use `token-audit://best-practices` to see all patterns.
"""

        practices = loader.get_by_category(category.lower())

        if not practices:
            return f"""# {category.capitalize()} Best Practices

No practices found in the {category} category.
"""

        exporter = BestPracticesExporter()
        return exporter.to_markdown(practices)

    # ========================================================================
    # MCP Resources for Usage Summaries (v1.0.2)
    # ========================================================================

    @mcp.resource("token-audit://usage/daily")
    def usage_daily() -> str:
        """
        Get daily usage summary for the last 7 days.

        Returns a markdown-formatted summary of token usage and costs
        with day-by-day breakdown and trend analysis.
        """
        result = tools.get_daily_summary(days=7, breakdown=False)
        return _format_daily_summary_as_markdown(result)

    @mcp.resource("token-audit://usage/weekly")
    def usage_weekly() -> str:
        """
        Get weekly usage summary for the last 4 weeks.

        Returns a markdown-formatted summary of token usage and costs
        with week-by-week breakdown and trend analysis.
        """
        from .schemas import WeekStartDay

        result = tools.get_weekly_summary(
            weeks=4, start_of_week=WeekStartDay.MONDAY, breakdown=False
        )
        return _format_weekly_summary_as_markdown(result)

    @mcp.resource("token-audit://usage/monthly")
    def usage_monthly() -> str:
        """
        Get monthly usage summary for the last 3 months.

        Returns a markdown-formatted summary of token usage and costs
        with month-by-month breakdown and trend analysis.
        """
        result = tools.get_monthly_summary(months=3, breakdown=False)
        return _format_monthly_summary_as_markdown(result)

    # ========================================================================
    # MCP Resources for Sessions (v1.0.2)
    # ========================================================================

    @mcp.resource("token-audit://sessions")
    def sessions_list() -> str:
        """
        List recent sessions.

        Returns a markdown-formatted list of the 20 most recent sessions
        with key metrics and links to detailed views.
        """
        from .schemas import SessionSortBy, SortOrder

        result = tools.list_sessions(
            limit=20,
            offset=0,
            sort_by=SessionSortBy.DATE,
            sort_order=SortOrder.DESC,
        )
        return _format_sessions_list_as_markdown(result)

    @mcp.resource("token-audit://sessions/{session_id}")
    def session_detail(session_id: str) -> str:
        """
        Get detailed session information.

        Args:
            session_id: The session ID to retrieve

        Returns:
            Markdown-formatted session details including token usage,
            MCP server activity, and detected smells.
        """
        result = tools.get_session_details(
            session_id=session_id,
            include_tool_calls=True,
            include_smells=True,
            include_recommendations=True,
        )
        return _format_session_details_as_markdown(result)

    return mcp


# =============================================================================
# Markdown Formatters for Resources (v1.0.2)
# =============================================================================


def _format_daily_summary_as_markdown(result: Any) -> str:
    """Format daily summary output as markdown."""
    lines = ["# Daily Token Usage Summary", ""]
    lines.append(f"**Period:** {result.period.start} to {result.period.end}")
    lines.append("")

    lines.append("## Totals")
    lines.append(f"- Sessions: {result.totals.sessions}")
    lines.append(f"- Total Tokens: {result.totals.total_tokens:,}")
    lines.append(f"- Total Cost: ${result.totals.cost_usd:.4f}")
    lines.append("")

    lines.append("## Daily Breakdown")
    lines.append("")
    lines.append("| Date | Sessions | Tokens | Cost |")
    lines.append("|------|----------|--------|------|")
    for day in result.daily:
        lines.append(
            f"| {day.date} | {day.sessions} | {day.total_tokens:,} | ${day.cost_usd:.4f} |"
        )
    lines.append("")

    lines.append("## Trends")
    lines.append(f"- Direction: {result.trends.direction.value}")
    lines.append(f"- Change: {result.trends.change_percent:.1f}%")
    if result.trends.busiest_day:
        lines.append(f"- Busiest Day: {result.trends.busiest_day}")
    lines.append(f"- Average Daily Cost: ${result.trends.avg_daily_cost:.4f}")

    return "\n".join(lines)


def _format_weekly_summary_as_markdown(result: Any) -> str:
    """Format weekly summary output as markdown."""
    lines = ["# Weekly Token Usage Summary", ""]
    lines.append(f"**Period:** {result.period.start} to {result.period.end}")
    lines.append("")

    lines.append("## Totals")
    lines.append(f"- Sessions: {result.totals.sessions}")
    lines.append(f"- Total Tokens: {result.totals.total_tokens:,}")
    lines.append(f"- Total Cost: ${result.totals.cost_usd:.4f}")
    lines.append("")

    lines.append("## Weekly Breakdown")
    lines.append("")
    lines.append("| Week | Sessions | Tokens | Cost | Avg/Session |")
    lines.append("|------|----------|--------|------|-------------|")
    for week in result.weekly:
        lines.append(
            f"| {week.week_start} | {week.sessions} | {week.total_tokens:,} | "
            f"${week.cost_usd:.4f} | ${week.avg_session_cost:.4f} |"
        )
    lines.append("")

    lines.append("## Trends")
    lines.append(f"- Direction: {result.trends.direction.value}")
    lines.append(f"- Change: {result.trends.change_percent:.1f}%")

    return "\n".join(lines)


def _format_monthly_summary_as_markdown(result: Any) -> str:
    """Format monthly summary output as markdown."""
    lines = ["# Monthly Token Usage Summary", ""]
    lines.append(f"**Period:** {result.period.start} to {result.period.end}")
    lines.append("")

    lines.append("## Totals")
    lines.append(f"- Sessions: {result.totals.sessions}")
    lines.append(f"- Total Tokens: {result.totals.total_tokens:,}")
    lines.append(f"- Total Cost: ${result.totals.cost_usd:.4f}")
    lines.append("")

    lines.append("## Monthly Breakdown")
    lines.append("")
    lines.append("| Month | Sessions | Tokens | Cost |")
    lines.append("|-------|----------|--------|------|")
    for month in result.monthly:
        lines.append(
            f"| {month.month} | {month.sessions} | {month.total_tokens:,} | ${month.cost_usd:.4f} |"
        )
    lines.append("")

    lines.append("## Trends")
    lines.append(f"- Direction: {result.trends.direction.value}")
    lines.append(f"- Change: {result.trends.change_percent:.1f}%")

    return "\n".join(lines)


def _format_sessions_list_as_markdown(result: Any) -> str:
    """Format sessions list output as markdown."""
    lines = ["# Recent Sessions", ""]
    lines.append(f"Showing {len(result.sessions)} of {result.pagination.total} sessions")
    lines.append("")

    if not result.sessions:
        lines.append("*No sessions found.*")
        return "\n".join(lines)

    lines.append("| Session | Platform | Started | Tokens | Cost | Smells |")
    lines.append("|---------|----------|---------|--------|------|--------|")
    for session in result.sessions:
        lines.append(
            f"| {session.session_id[:16]}... | {session.platform} | "
            f"{session.started_at[:10]} | {session.total_tokens:,} | "
            f"${session.cost_usd:.4f} | {session.smells_detected} |"
        )
    lines.append("")

    if result.pagination.has_more:
        lines.append(f"*{result.pagination.total - len(result.sessions)} more sessions available.*")

    return "\n".join(lines)


def _format_session_details_as_markdown(result: Any) -> str:
    """Format session details output as markdown."""
    lines = [f"# Session: {result.session.session_id}", ""]

    lines.append("## Overview")
    lines.append(f"- **Platform:** {result.session.platform}")
    if result.session.project:
        lines.append(f"- **Project:** {result.session.project}")
    lines.append(f"- **Started:** {result.session.started_at}")
    if result.session.ended_at:
        lines.append(f"- **Ended:** {result.session.ended_at}")
    lines.append(f"- **Duration:** {result.session.duration_seconds}s")
    if result.session.model:
        lines.append(f"- **Model:** {result.session.model}")
    lines.append("")

    lines.append("## Token Usage")
    lines.append(f"- Input: {result.token_usage.input_tokens:,}")
    lines.append(f"- Output: {result.token_usage.output_tokens:,}")
    if result.token_usage.cache_read_tokens:
        lines.append(f"- Cache Read: {result.token_usage.cache_read_tokens:,}")
    if result.token_usage.cache_write_tokens:
        lines.append(f"- Cache Write: {result.token_usage.cache_write_tokens:,}")
    lines.append(f"- **Total:** {result.token_usage.total_tokens:,}")
    lines.append(f"- **Cost:** ${result.token_usage.cost_usd:.4f}")
    lines.append("")

    if result.mcp_usage.servers:
        lines.append("## MCP Servers")
        for server in result.mcp_usage.servers:
            lines.append(
                f"- **{server.name}:** {server.total_calls} calls, {server.tools_used} tools"
            )
        lines.append("")

    if result.mcp_usage.top_tools:
        lines.append("## Top Tools")
        for tool in result.mcp_usage.top_tools[:5]:
            lines.append(f"- {tool.name}: {tool.calls} calls")
        lines.append("")

    if result.smells:
        lines.append("## Detected Smells")
        for smell in result.smells:
            lines.append(f"- **[{smell.severity.value}]** {smell.pattern}: {smell.message}")
        lines.append("")

    if result.recommendations:
        lines.append("## Recommendations")
        for rec in result.recommendations[:3]:
            lines.append(f"### {rec.title}")
            lines.append(rec.action)
            lines.append("")

    lines.append("---")
    lines.append(
        f"*Data Quality: {result.data_quality.accuracy_level.value} ({result.data_quality.confidence:.0%} confidence)*"
    )

    return "\n".join(lines)


# Global server instance (lazy initialization)
_server: Optional[FastMCP] = None


def get_server() -> FastMCP:
    """Get or create the global server instance."""
    global _server
    if _server is None:
        _server = create_server()
    return _server


def run_server() -> None:
    """
    Run the token-audit MCP server with stdio transport.

    This is the main entry point for the token-audit-server command.
    """
    import argparse

    from token_audit import __version__

    parser = argparse.ArgumentParser(
        prog="token-audit-server",
        description="MCP server for real-time session metrics and optimization guidance.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"token-audit {__version__}",
    )

    # Parse args (will handle --help and --version automatically)
    parser.parse_args()

    # If we get here, no special flags were passed - start the server
    server = get_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    run_server()
