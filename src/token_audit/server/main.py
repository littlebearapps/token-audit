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
    ReportFormat,
    ServerPlatform,
    SeverityLevel,
    TrendPeriod,
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

    return mcp


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
