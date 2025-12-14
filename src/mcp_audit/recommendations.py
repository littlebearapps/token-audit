"""
Recommendation Engine - Generates actionable recommendations from smell patterns.

This module transforms detected efficiency anti-patterns (smells) into
concrete, actionable recommendations for AI agents to analyze and suggest.

Recommendation Types (v0.8.0 - task-106.2):
- REMOVE_UNUSED_SERVER: Remove underutilized MCP servers
- ENABLE_CACHING: Improve cache utilization
- BATCH_OPERATIONS: Combine sequential or chatty operations
- OPTIMIZE_COST: Reduce token consumption on expensive operations

Each recommendation includes:
- Confidence score (0.0-1.0) based on evidence strength
- Human/AI readable evidence summary
- Specific action to take
- Expected impact/benefit
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_tracker import Session, Smell

# ============================================================================
# Recommendation Types
# ============================================================================


class RecommendationType:
    """Recommendation type constants."""

    REMOVE_UNUSED_SERVER = "REMOVE_UNUSED_SERVER"
    ENABLE_CACHING = "ENABLE_CACHING"
    BATCH_OPERATIONS = "BATCH_OPERATIONS"
    OPTIMIZE_COST = "OPTIMIZE_COST"


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class Recommendation:
    """Actionable recommendation for AI consumption.

    Attributes:
        type: Recommendation category (REMOVE_UNUSED_SERVER, ENABLE_CACHING, etc.)
        confidence: Confidence score 0.0-1.0 based on evidence strength
        evidence: Human/AI readable explanation of why this is recommended
        action: Specific action to take
        impact: Expected benefit from taking this action
        source_smell: The smell pattern that triggered this recommendation
        details: Additional context-specific data
    """

    type: str
    confidence: float
    evidence: str
    action: str
    impact: str
    source_smell: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for AI export."""
        result = {
            "type": self.type,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
            "action": self.action,
            "impact": self.impact,
        }
        if self.source_smell:
            result["source_smell"] = self.source_smell
        if self.details:
            result["details"] = self.details
        return result


# ============================================================================
# Recommendation Engine
# ============================================================================


@dataclass
class RecommendationEngine:
    """Generates actionable recommendations from detected smells.

    Usage:
        engine = RecommendationEngine()
        recommendations = engine.generate(smells, session)

    The engine maps each smell pattern to appropriate recommendations,
    calculating confidence based on the smell's evidence data.
    """

    # Minimum confidence threshold to include a recommendation
    min_confidence: float = 0.3

    def generate(
        self, smells: List[Smell], session: Optional[Session] = None
    ) -> List[Recommendation]:
        """Generate recommendations from detected smells.

        Args:
            smells: List of detected smell patterns
            session: Optional session for additional context

        Returns:
            List of Recommendation objects sorted by confidence (descending)
        """
        recommendations: List[Recommendation] = []

        for smell in smells:
            rec = self._smell_to_recommendation(smell, session)
            if rec and rec.confidence >= self.min_confidence:
                recommendations.append(rec)

        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)

        return recommendations

    def _smell_to_recommendation(
        self, smell: Smell, _session: Optional[Session]
    ) -> Optional[Recommendation]:
        """Map a single smell to its corresponding recommendation.

        Args:
            smell: Detected smell pattern
            session: Optional session for context

        Returns:
            Recommendation or None if no mapping exists
        """
        # Pattern-specific mapping
        handlers = {
            "UNDERUTILIZED_SERVER": self._handle_underutilized_server,
            "LOW_CACHE_HIT": self._handle_low_cache_hit,
            "CACHE_MISS_STREAK": self._handle_cache_miss_streak,
            "REDUNDANT_CALLS": self._handle_redundant_calls,
            "SEQUENTIAL_READS": self._handle_sequential_reads,
            "CHATTY": self._handle_chatty,
            "BURST_PATTERN": self._handle_burst_pattern,
            "EXPENSIVE_FAILURES": self._handle_expensive_failures,
            "TOP_CONSUMER": self._handle_top_consumer,
            "LARGE_PAYLOAD": self._handle_large_payload,
            "HIGH_VARIANCE": self._handle_high_variance,
            "HIGH_MCP_SHARE": self._handle_high_mcp_share,
        }

        handler = handlers.get(smell.pattern)
        if handler:
            return handler(smell, _session)

        return None

    # ========================================================================
    # REMOVE_UNUSED_SERVER Recommendations
    # ========================================================================

    def _handle_underutilized_server(
        self, smell: Smell, _session: Optional[Session]
    ) -> Recommendation:
        """Handle UNDERUTILIZED_SERVER smell -> REMOVE_UNUSED_SERVER recommendation."""
        evidence = smell.evidence
        server = evidence.get("server", "unknown")
        utilization = evidence.get("utilization_percent", 0)
        available = evidence.get("available_tools", 0)
        used = evidence.get("used_tools", 0)

        # Higher confidence when utilization is very low
        if utilization == 0:
            confidence = 0.95
        elif utilization < 5:
            confidence = 0.85
        else:
            confidence = 0.6

        return Recommendation(
            type=RecommendationType.REMOVE_UNUSED_SERVER,
            confidence=confidence,
            evidence=f"Server '{server}' has {available} tools but only {used} were used ({utilization:.1f}% utilization)",
            action=f"Consider removing '{server}' from .mcp.json to reduce context overhead",
            impact=f"Save ~{available * 500:,} tokens/turn in schema context tax",
            source_smell="UNDERUTILIZED_SERVER",
            details={
                "server": server,
                "utilization_percent": utilization,
                "tools_available": available,
                "tools_used": used,
            },
        )

    # ========================================================================
    # ENABLE_CACHING Recommendations
    # ========================================================================

    def _handle_low_cache_hit(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle LOW_CACHE_HIT smell -> ENABLE_CACHING recommendation."""
        evidence = smell.evidence
        hit_rate = evidence.get("hit_rate_percent", 0)
        threshold = evidence.get("threshold_percent", 30)
        cache_read = evidence.get("cache_read_tokens", 0)
        input_tokens = evidence.get("input_tokens", 0)

        # Very low cache = higher confidence
        if hit_rate < 10:
            confidence = 0.9
        elif hit_rate < 20:
            confidence = 0.75
        else:
            confidence = 0.6

        potential_savings = int(input_tokens * 0.5)  # Assume 50% could be cached

        return Recommendation(
            type=RecommendationType.ENABLE_CACHING,
            confidence=confidence,
            evidence=f"Cache hit rate is only {hit_rate:.1f}% (threshold: {threshold}%)",
            action="Restructure prompts to maximize context reuse and cache hits",
            impact=f"Potential savings of ~{potential_savings:,} tokens/session with better caching",
            source_smell="LOW_CACHE_HIT",
            details={
                "current_hit_rate": hit_rate,
                "target_hit_rate": max(threshold, 50),
                "cache_read_tokens": cache_read,
                "input_tokens": input_tokens,
            },
        )

    def _handle_cache_miss_streak(
        self, smell: Smell, _session: Optional[Session]
    ) -> Recommendation:
        """Handle CACHE_MISS_STREAK smell -> ENABLE_CACHING recommendation."""
        evidence = smell.evidence
        miss_count = evidence.get("miss_count", 0)
        total_tokens = evidence.get("total_tokens", 0)
        tools = evidence.get("tools_involved", {})

        confidence = min(0.5 + (miss_count * 0.05), 0.85)

        return Recommendation(
            type=RecommendationType.ENABLE_CACHING,
            confidence=confidence,
            evidence=f"{miss_count} consecutive cache misses consuming {total_tokens:,} tokens",
            action="Review tool call order to enable cache reuse between operations",
            impact=f"Could save ~{int(total_tokens * 0.3):,} tokens by improving cache locality",
            source_smell="CACHE_MISS_STREAK",
            details={
                "miss_count": miss_count,
                "total_tokens": total_tokens,
                "tools_involved": list(tools.keys()) if tools else [],
            },
        )

    def _handle_redundant_calls(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle REDUNDANT_CALLS smell -> ENABLE_CACHING recommendation."""
        evidence = smell.evidence
        duplicate_count = evidence.get("duplicate_count", 0)
        tool = smell.tool or "unknown"

        confidence = min(0.6 + (duplicate_count * 0.1), 0.95)

        return Recommendation(
            type=RecommendationType.ENABLE_CACHING,
            confidence=confidence,
            evidence=f"Tool '{tool}' called {duplicate_count} times with identical content",
            action=f"Cache the result of '{tool}' calls to avoid redundant invocations",
            impact=f"Eliminate {duplicate_count - 1} redundant calls and their token cost",
            source_smell="REDUNDANT_CALLS",
            details={
                "tool": tool,
                "duplicate_count": duplicate_count,
            },
        )

    # ========================================================================
    # BATCH_OPERATIONS Recommendations
    # ========================================================================

    def _handle_sequential_reads(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle SEQUENTIAL_READS smell -> BATCH_OPERATIONS recommendation."""
        evidence = smell.evidence
        read_count = evidence.get("read_count", 0)
        total_tokens = evidence.get("total_tokens", 0)
        tool = smell.tool or "Read"

        confidence = min(0.5 + (read_count * 0.08), 0.9)

        return Recommendation(
            type=RecommendationType.BATCH_OPERATIONS,
            confidence=confidence,
            evidence=f"{read_count} consecutive file reads consuming {total_tokens:,} tokens",
            action="Use Glob patterns to batch file reads or read multiple files in parallel",
            impact=f"Reduce {read_count} calls to 1-2 batched operations",
            source_smell="SEQUENTIAL_READS",
            details={
                "read_count": read_count,
                "total_tokens": total_tokens,
                "tool": tool,
            },
        )

    def _handle_chatty(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle CHATTY smell -> BATCH_OPERATIONS recommendation."""
        evidence = smell.evidence
        call_count = evidence.get("call_count", 0)
        threshold = evidence.get("threshold", 20)
        total_tokens = evidence.get("total_tokens", 0)
        avg_tokens = evidence.get("avg_tokens_per_call", 0)
        tool = smell.tool or "unknown"

        # Very chatty = higher confidence
        if call_count > threshold * 2:
            confidence = 0.9
        elif call_count > threshold * 1.5:
            confidence = 0.75
        else:
            confidence = 0.6

        return Recommendation(
            type=RecommendationType.BATCH_OPERATIONS,
            confidence=confidence,
            evidence=f"Tool '{tool}' called {call_count} times (threshold: {threshold})",
            action=f"Batch multiple '{tool}' calls into fewer, larger requests",
            impact=f"Reduce overhead from {call_count} calls to ~{max(call_count // 5, 1)} batched calls",
            source_smell="CHATTY",
            details={
                "tool": tool,
                "call_count": call_count,
                "total_tokens": total_tokens,
                "avg_tokens_per_call": round(avg_tokens, 1),
            },
        )

    def _handle_burst_pattern(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle BURST_PATTERN smell -> BATCH_OPERATIONS recommendation."""
        evidence = smell.evidence
        call_count = evidence.get("call_count", 0)
        window_ms = evidence.get("window_ms", 1000)
        tool_breakdown = evidence.get("tool_breakdown", {})
        tool = smell.tool

        confidence = min(0.55 + (call_count * 0.05), 0.85)

        tool_desc = f"'{tool}'" if tool else "multiple tools"

        return Recommendation(
            type=RecommendationType.BATCH_OPERATIONS,
            confidence=confidence,
            evidence=f"{call_count} tool calls within {window_ms}ms - possible loop or retry storm",
            action=f"Review {tool_desc} usage for unintended loops or implement request batching",
            impact="Reduce burst overhead and improve response time",
            source_smell="BURST_PATTERN",
            details={
                "call_count": call_count,
                "window_ms": window_ms,
                "tool_breakdown": tool_breakdown,
            },
        )

    # ========================================================================
    # OPTIMIZE_COST Recommendations
    # ========================================================================

    def _handle_expensive_failures(
        self, smell: Smell, _session: Optional[Session]
    ) -> Recommendation:
        """Handle EXPENSIVE_FAILURES smell -> OPTIMIZE_COST recommendation."""
        evidence = smell.evidence
        tokens = evidence.get("tokens", 0)
        _threshold = evidence.get("threshold", 5000)  # Reserved for future use
        error_info = evidence.get("error_info", "unknown error")
        tool = smell.tool or "unknown"

        # Higher token waste = higher confidence
        confidence = min(0.7 + (tokens / 50000), 0.95)

        return Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=confidence,
            evidence=f"Failed call to '{tool}' consumed {tokens:,} tokens ({error_info[:50]})",
            action=f"Add validation before calling '{tool}' to prevent expensive failures",
            impact=f"Save {tokens:,} tokens per prevented failure",
            source_smell="EXPENSIVE_FAILURES",
            details={
                "tool": tool,
                "tokens_wasted": tokens,
                "error_summary": error_info[:100],
            },
        )

    def _handle_top_consumer(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle TOP_CONSUMER smell -> OPTIMIZE_COST recommendation."""
        evidence = smell.evidence
        percentage = evidence.get("percentage", 0)
        tool_tokens = evidence.get("tool_tokens", 0)
        calls = evidence.get("calls", 0)
        tool = smell.tool or "unknown"

        # Only recommend if very dominant
        if percentage < 60:
            confidence = 0.4
        elif percentage < 75:
            confidence = 0.6
        else:
            confidence = 0.75

        avg_tokens = tool_tokens // calls if calls > 0 else 0

        return Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=confidence,
            evidence=f"Tool '{tool}' consumes {percentage:.1f}% of MCP tokens ({tool_tokens:,} total)",
            action=f"Optimize '{tool}' usage: chunk large requests, use pagination, or find alternatives",
            impact=f"Reducing '{tool}' usage by 20% could save ~{int(tool_tokens * 0.2):,} tokens",
            source_smell="TOP_CONSUMER",
            details={
                "tool": tool,
                "percentage": percentage,
                "total_tokens": tool_tokens,
                "calls": calls,
                "avg_tokens_per_call": avg_tokens,
            },
        )

    def _handle_large_payload(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle LARGE_PAYLOAD smell -> OPTIMIZE_COST recommendation."""
        evidence = smell.evidence
        tokens = evidence.get("tokens", 0)
        threshold = evidence.get("threshold", 10000)
        input_tokens = evidence.get("input_tokens", 0)
        output_tokens = evidence.get("output_tokens", 0)
        tool = smell.tool or "unknown"

        # Larger payload = higher confidence
        confidence = min(0.5 + (tokens / 50000), 0.85)

        return Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=confidence,
            evidence=f"Single call to '{tool}' consumed {tokens:,} tokens (threshold: {threshold:,})",
            action=f"Use pagination or targeted queries with '{tool}' to reduce payload size",
            impact="Splitting into chunks could reduce per-call cost by 50-80%",
            source_smell="LARGE_PAYLOAD",
            details={
                "tool": tool,
                "total_tokens": tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

    def _handle_high_variance(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle HIGH_VARIANCE smell -> OPTIMIZE_COST recommendation."""
        evidence = smell.evidence
        cv = evidence.get("coefficient_of_variation", 0)
        min_tokens = evidence.get("min_tokens", 0)
        max_tokens = evidence.get("max_tokens", 0)
        tool = smell.tool or "unknown"

        # High variance might indicate inefficient usage
        confidence = min(0.4 + (cv * 0.3), 0.7)

        return Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=confidence,
            evidence=f"Tool '{tool}' has high token variance (CV={cv:.2f}, range: {min_tokens:,}-{max_tokens:,})",
            action=f"Standardize '{tool}' usage patterns for more predictable token consumption",
            impact="Reduce worst-case token usage and improve cost predictability",
            source_smell="HIGH_VARIANCE",
            details={
                "tool": tool,
                "coefficient_of_variation": round(cv, 3),
                "min_tokens": min_tokens,
                "max_tokens": max_tokens,
            },
        )

    def _handle_high_mcp_share(self, smell: Smell, _session: Optional[Session]) -> Recommendation:
        """Handle HIGH_MCP_SHARE smell -> OPTIMIZE_COST recommendation."""
        evidence = smell.evidence
        mcp_percentage = evidence.get("mcp_percentage", 0)
        mcp_tokens = evidence.get("mcp_tokens", 0)
        session_tokens = evidence.get("session_tokens", 0)
        server_count = evidence.get("server_count", 0)

        # Very high MCP share might indicate over-reliance
        confidence = 0.65 if mcp_percentage > 90 else 0.45

        return Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=confidence,
            evidence=f"MCP tools consume {mcp_percentage:.1f}% of session tokens ({mcp_tokens:,} of {session_tokens:,})",
            action="Review MCP server configuration - consider removing unused servers or optimizing tool usage",
            impact=f"Reducing MCP overhead by 10% could save ~{int(mcp_tokens * 0.1):,} tokens/session",
            source_smell="HIGH_MCP_SHARE",
            details={
                "mcp_percentage": mcp_percentage,
                "mcp_tokens": mcp_tokens,
                "session_tokens": session_tokens,
                "server_count": server_count,
            },
        )


# ============================================================================
# Convenience Function
# ============================================================================


def generate_recommendations(
    smells: List[Smell],
    session: Optional[Session] = None,
    min_confidence: float = 0.3,
) -> List[Recommendation]:
    """Convenience function to generate recommendations from smells.

    Args:
        smells: List of detected smell patterns
        session: Optional session for additional context
        min_confidence: Minimum confidence threshold (default 0.3)

    Returns:
        List of Recommendation objects sorted by confidence
    """
    engine = RecommendationEngine(min_confidence=min_confidence)
    return engine.generate(smells, session)
