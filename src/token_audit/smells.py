"""
Smell Engine - Detects efficiency anti-patterns in MCP usage.

This module identifies common inefficiencies in AI coding assistant sessions
by analyzing tool usage patterns, token distribution, and cache behavior.

Smell Patterns (v1.5.0 - task-103.1):
- HIGH_VARIANCE: Tool with unusually variable token counts across calls
- TOP_CONSUMER: Single tool consuming >50% of session tokens
- HIGH_MCP_SHARE: MCP tools consuming >80% of total tokens
- CHATTY: Tool called >20 times in a session
- LOW_CACHE_HIT: Cache hit rate <30% for cacheable operations

Smell Patterns (v1.7.0 - task-106.1):
- REDUNDANT_CALLS: Same tool called with identical parameters (content_hash)
- EXPENSIVE_FAILURES: High-token tool calls that resulted in errors
- UNDERUTILIZED_SERVER: MCP server with <10% tool utilization
- BURST_PATTERN: >5 tool calls within 1 second (may indicate loop)
- LARGE_PAYLOAD: Single tool call >10K tokens
- SEQUENTIAL_READS: Multiple file reads that could be batched
- CACHE_MISS_STREAK: 5+ consecutive cache misses

Security Smell Patterns (v1.0.0 - task-143):
- CREDENTIAL_EXPOSURE: Potential credentials detected in tool parameters
- SUSPICIOUS_TOOL_DESCRIPTION: Potential prompt injection indicators
- UNUSUAL_DATA_FLOW: External call after large file reads (potential exfiltration)

Severity Levels:
- critical: Immediate action required (reserved for future use)
- high: Significant inefficiency, should be addressed
- medium: Notable pattern worth investigating (alias: warning)
- low: Minor issue, nice to fix
- info: Informational, no action required
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Pattern

from .base_tracker import Call, Session, Smell


class SmellSeverity:
    """Severity levels for smell patterns."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"  # Note: "warning" is used in v1.5.0 patterns as alias
    WARNING = "warning"  # Alias for backward compatibility
    LOW = "low"
    INFO = "info"


# Prompt injection indicator patterns (task-143)
# Used by _detect_suspicious_tool_description to identify potential attacks
PROMPT_INJECTION_INDICATORS: List[Pattern[str]] = [
    re.compile(r"\b(ignore|disregard|forget)\s+(previous|above|prior|all)", re.I),
    re.compile(r"\b(system:|you\s+are\s+now|act\s+as|pretend\s+to\s+be)", re.I),
    re.compile(r"^(assistant|user|human|system):\s*", re.I | re.M),
    re.compile(r"\b(DAN|do\s+anything\s+now|no\s+restrictions|bypass)", re.I),
    re.compile(r"```\s*(system|ignore|override)", re.I),
]

# External tool name patterns for data flow detection (task-143)
# Used by _detect_unusual_data_flow to identify potential exfiltration
EXTERNAL_TOOL_PATTERNS: List[str] = [
    "fetch",
    "http",
    "request",
    "webhook",
    "send",
    "post",
]


@dataclass
class SmellThresholds:
    """Configurable thresholds for smell detection."""

    # HIGH_VARIANCE: coefficient of variation threshold (std_dev / mean)
    high_variance_cv: float = 0.5  # 50% coefficient of variation

    # TOP_CONSUMER: percentage of session tokens for single tool
    top_consumer_percent: float = 50.0

    # HIGH_MCP_SHARE: percentage of session tokens from MCP tools
    high_mcp_share_percent: float = 80.0

    # CHATTY: minimum calls to trigger chatty detection
    chatty_call_threshold: int = 20

    # LOW_CACHE_HIT: minimum cache hit rate (cache_read / (cache_read + input))
    low_cache_hit_percent: float = 30.0

    # Minimum calls/tokens to consider for certain patterns
    min_calls_for_variance: int = 3  # Need at least 3 calls to detect variance
    min_tokens_for_consumer: int = 1000  # Ignore tiny token consumers

    # v1.7.0 thresholds (task-106.1)

    # REDUNDANT_CALLS: minimum duplicate calls to flag
    redundant_call_min_duplicates: int = 2

    # EXPENSIVE_FAILURES: token threshold for "expensive" failed call
    expensive_failure_token_threshold: int = 5000

    # UNDERUTILIZED_SERVER: percentage of available tools that must be used
    underutilized_server_percent: float = 10.0

    # BURST_PATTERN: number of calls within window to trigger
    burst_pattern_calls: int = 5
    burst_pattern_window_ms: int = 1000  # 1 second

    # LARGE_PAYLOAD: token threshold for a single call
    large_payload_tokens: int = 10000

    # SEQUENTIAL_READS: minimum consecutive reads to flag
    sequential_read_threshold: int = 3

    # CACHE_MISS_STREAK: consecutive misses to flag
    cache_miss_streak_threshold: int = 5

    # v1.0.0 Security thresholds (task-143)

    # CREDENTIAL_EXPOSURE: enable/disable credential detection
    credential_exposure_enabled: bool = True

    # SUSPICIOUS_TOOL_DESCRIPTION: minimum indicators to flag
    suspicious_description_min_indicators: int = 2

    # UNUSUAL_DATA_FLOW: token threshold for "large" read before external call
    unusual_data_flow_output_threshold: int = 5000

    # UNUSUAL_DATA_FLOW: minimum base64-like string length to flag
    unusual_data_flow_base64_min_length: int = 100


@dataclass
class SmellDetector:
    """Detects efficiency anti-patterns in session data.

    Usage:
        detector = SmellDetector()
        smells = detector.analyze(session)
        session.smells = smells
    """

    thresholds: SmellThresholds = field(default_factory=SmellThresholds)

    def analyze(self, session: Session) -> List[Smell]:
        """Analyze a session and return all detected smells.

        Args:
            session: Finalized session with tool statistics

        Returns:
            List of Smell objects for detected anti-patterns
        """
        smells: List[Smell] = []

        # v1.5.0 detectors
        smells.extend(self._detect_high_variance(session))
        smells.extend(self._detect_top_consumer(session))
        smells.extend(self._detect_high_mcp_share(session))
        smells.extend(self._detect_chatty(session))
        smells.extend(self._detect_low_cache_hit(session))

        # v1.7.0 detectors (task-106.1)
        smells.extend(self._detect_redundant_calls(session))
        smells.extend(self._detect_expensive_failures(session))
        smells.extend(self._detect_underutilized_server(session))
        smells.extend(self._detect_burst_pattern(session))
        smells.extend(self._detect_large_payload(session))
        smells.extend(self._detect_sequential_reads(session))
        smells.extend(self._detect_cache_miss_streak(session))

        # v1.0.0 Security detectors (task-143)
        smells.extend(self._detect_credential_exposure(session))
        smells.extend(self._detect_suspicious_tool_description(session))
        smells.extend(self._detect_unusual_data_flow(session))

        return smells

    def _detect_high_variance(self, session: Session) -> List[Smell]:
        """Detect tools with highly variable token counts.

        A high variance indicates inconsistent tool usage that may benefit
        from batching or restructuring.
        """
        smells: List[Smell] = []

        for _server_name, server_session in session.server_sessions.items():
            for tool_name, tool_stats in server_session.tools.items():
                # Need minimum calls and token history
                if tool_stats.calls < self.thresholds.min_calls_for_variance:
                    continue

                # Check if we have token history for variance calculation
                if not hasattr(tool_stats, "token_history") or not tool_stats.token_history:
                    # Fall back to checking if avg vs total suggests high variance
                    # This is a heuristic when we don't have per-call history
                    continue

                # Calculate coefficient of variation
                tokens = tool_stats.token_history
                if len(tokens) < self.thresholds.min_calls_for_variance:
                    continue

                mean = sum(tokens) / len(tokens)
                if mean == 0:
                    continue

                variance = sum((t - mean) ** 2 for t in tokens) / len(tokens)
                std_dev = variance**0.5
                cv = std_dev / mean  # Coefficient of variation

                if cv >= self.thresholds.high_variance_cv:
                    smells.append(
                        Smell(
                            pattern="HIGH_VARIANCE",
                            severity="warning",
                            tool=tool_name,
                            description=f"Token counts vary significantly (CV={cv:.2f})",
                            evidence={
                                "coefficient_of_variation": round(cv, 3),
                                "std_dev": round(std_dev, 1),
                                "mean": round(mean, 1),
                                "min_tokens": min(tokens),
                                "max_tokens": max(tokens),
                                "call_count": len(tokens),
                            },
                        )
                    )

        return smells

    def _detect_top_consumer(self, session: Session) -> List[Smell]:
        """Detect tools consuming >50% of session tokens.

        A single tool dominating token usage may indicate over-reliance
        or opportunities for optimization.
        """
        smells: List[Smell] = []

        # Calculate total MCP tokens
        total_mcp_tokens = sum(ss.total_tokens for ss in session.server_sessions.values())

        if total_mcp_tokens < self.thresholds.min_tokens_for_consumer:
            return smells

        # Find tools consuming high percentage
        for _server_name, server_session in session.server_sessions.items():
            for tool_name, tool_stats in server_session.tools.items():
                if tool_stats.total_tokens < self.thresholds.min_tokens_for_consumer:
                    continue

                percentage = (tool_stats.total_tokens / total_mcp_tokens) * 100

                if percentage >= self.thresholds.top_consumer_percent:
                    smells.append(
                        Smell(
                            pattern="TOP_CONSUMER",
                            severity="info",
                            tool=tool_name,
                            description=f"Consuming {percentage:.1f}% of MCP tokens",
                            evidence={
                                "percentage": round(percentage, 1),
                                "tool_tokens": tool_stats.total_tokens,
                                "total_mcp_tokens": total_mcp_tokens,
                                "calls": tool_stats.calls,
                            },
                        )
                    )

        return smells

    def _detect_high_mcp_share(self, session: Session) -> List[Smell]:
        """Detect when MCP tools consume >80% of session tokens.

        High MCP share may indicate heavy reliance on external tools
        or opportunities to reduce MCP overhead.
        """
        smells: List[Smell] = []

        # Get session total tokens
        total_session_tokens = session.token_usage.total_tokens
        if total_session_tokens == 0:
            return smells

        # Calculate MCP tokens
        total_mcp_tokens = sum(ss.total_tokens for ss in session.server_sessions.values())

        mcp_percentage = (total_mcp_tokens / total_session_tokens) * 100

        if mcp_percentage >= self.thresholds.high_mcp_share_percent:
            smells.append(
                Smell(
                    pattern="HIGH_MCP_SHARE",
                    severity="info",
                    tool=None,  # Session-level smell
                    description=f"MCP tools consuming {mcp_percentage:.1f}% of session tokens",
                    evidence={
                        "mcp_percentage": round(mcp_percentage, 1),
                        "mcp_tokens": total_mcp_tokens,
                        "session_tokens": total_session_tokens,
                        "server_count": len(session.server_sessions),
                    },
                )
            )

        return smells

    def _detect_chatty(self, session: Session) -> List[Smell]:
        """Detect tools called >20 times in a session.

        Chatty tools may benefit from batching or indicate
        inefficient usage patterns.
        """
        smells: List[Smell] = []

        for _server_name, server_session in session.server_sessions.items():
            for tool_name, tool_stats in server_session.tools.items():
                if tool_stats.calls >= self.thresholds.chatty_call_threshold:
                    avg_tokens = (
                        tool_stats.total_tokens / tool_stats.calls if tool_stats.calls > 0 else 0
                    )
                    smells.append(
                        Smell(
                            pattern="CHATTY",
                            severity="warning",
                            tool=tool_name,
                            description=f"Called {tool_stats.calls} times",
                            evidence={
                                "call_count": tool_stats.calls,
                                "threshold": self.thresholds.chatty_call_threshold,
                                "total_tokens": tool_stats.total_tokens,
                                "avg_tokens_per_call": round(avg_tokens, 1),
                            },
                        )
                    )

        return smells

    def _detect_low_cache_hit(self, session: Session) -> List[Smell]:
        """Detect low cache hit rates (<30%).

        Low cache efficiency indicates missed optimization opportunities
        or context that isn't being reused effectively.
        """
        smells: List[Smell] = []

        # Session-level cache analysis
        cache_read = session.token_usage.cache_read_tokens
        cache_created = session.token_usage.cache_created_tokens
        input_tokens = session.token_usage.input_tokens

        # Calculate cache hit rate
        # Hit rate = cache_read / (cache_read + non-cached input)
        # Non-cached input = input - cache_read
        total_input_opportunity = input_tokens + cache_read
        if total_input_opportunity == 0:
            return smells

        # Only check if there's cache activity
        if cache_created == 0 and cache_read == 0:
            return smells

        # Calculate effective hit rate
        hit_rate = (
            (cache_read / total_input_opportunity) * 100 if total_input_opportunity > 0 else 0
        )

        if hit_rate < self.thresholds.low_cache_hit_percent:
            # Determine severity based on how low the hit rate is
            severity = "warning" if hit_rate < 10 else "info"

            smells.append(
                Smell(
                    pattern="LOW_CACHE_HIT",
                    severity=severity,
                    tool=None,  # Session-level smell
                    description=f"Cache hit rate is {hit_rate:.1f}%",
                    evidence={
                        "hit_rate_percent": round(hit_rate, 1),
                        "threshold_percent": self.thresholds.low_cache_hit_percent,
                        "cache_read_tokens": cache_read,
                        "cache_created_tokens": cache_created,
                        "input_tokens": input_tokens,
                    },
                )
            )

        return smells

    # ========================================================================
    # v1.7.0 Detectors (task-106.1)
    # ========================================================================

    def _detect_redundant_calls(self, session: Session) -> List[Smell]:
        """Detect tools called with identical parameters (same content_hash).

        Redundant calls waste tokens by performing the same operation multiple
        times. Consider caching or restructuring to avoid duplicates.
        """
        smells: List[Smell] = []

        # Collect all calls with content_hash by tool
        tool_hashes: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for server_session in session.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                for call in tool_stats.call_history:
                    if call.content_hash:
                        tool_hashes[tool_name][call.content_hash] += 1

        # Find tools with duplicate hashes
        for tool_name, hashes in tool_hashes.items():
            for content_hash, count in hashes.items():
                if count >= self.thresholds.redundant_call_min_duplicates:
                    smells.append(
                        Smell(
                            pattern="REDUNDANT_CALLS",
                            severity="warning",
                            tool=tool_name,
                            description=f"Called {count} times with identical content",
                            evidence={
                                "duplicate_count": count,
                                "content_hash": content_hash[:16] + "...",
                                "threshold": self.thresholds.redundant_call_min_duplicates,
                            },
                        )
                    )

        return smells

    def _detect_expensive_failures(self, session: Session) -> List[Smell]:
        """Detect high-token tool calls that resulted in errors.

        Expensive failures indicate wasted tokens on operations that didn't
        succeed. Consider better validation or error prevention.
        """
        smells: List[Smell] = []

        for server_session in session.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                for call in tool_stats.call_history:
                    # Check if call has error indicators in platform_data
                    if not call.platform_data:
                        continue

                    # Look for common error indicators
                    is_error = (
                        call.platform_data.get("error")
                        or call.platform_data.get("is_error")
                        or call.platform_data.get("status") == "error"
                        or call.platform_data.get("exit_code", 0) != 0
                    )

                    if (
                        is_error
                        and call.total_tokens >= self.thresholds.expensive_failure_token_threshold
                    ):
                        smells.append(
                            Smell(
                                pattern="EXPENSIVE_FAILURES",
                                severity="high",
                                tool=tool_name,
                                description=f"Failed call consumed {call.total_tokens:,} tokens",
                                evidence={
                                    "tokens": call.total_tokens,
                                    "threshold": self.thresholds.expensive_failure_token_threshold,
                                    "call_index": call.index,
                                    "error_info": str(call.platform_data.get("error", "unknown"))[
                                        :100
                                    ],
                                },
                            )
                        )

        return smells

    def _detect_underutilized_server(self, session: Session) -> List[Smell]:
        """Detect MCP servers where less than 10% of available tools were used.

        Underutilized servers add schema overhead (context tax) without
        providing proportional value. Consider removing or consolidating.
        """
        smells: List[Smell] = []

        # Use zombie_tools to find servers with many unused tools
        for server_name, unused_tools in session.zombie_tools.items():
            if server_name not in session.server_sessions:
                # Server has zero usage - even more concerning
                if len(unused_tools) > 0:
                    smells.append(
                        Smell(
                            pattern="UNDERUTILIZED_SERVER",
                            severity="info",
                            tool=None,
                            description=f"Server '{server_name}' has {len(unused_tools)} tools but none were used",
                            evidence={
                                "server": server_name,
                                "available_tools": len(unused_tools),
                                "used_tools": 0,
                                "utilization_percent": 0.0,
                            },
                        )
                    )
                continue

            server_session = session.server_sessions[server_name]
            used_count = len(server_session.tools)
            total_count = used_count + len(unused_tools)

            if total_count == 0:
                continue

            utilization = (used_count / total_count) * 100

            if utilization < self.thresholds.underutilized_server_percent:
                smells.append(
                    Smell(
                        pattern="UNDERUTILIZED_SERVER",
                        severity="info",
                        tool=None,
                        description=f"Server '{server_name}' using {utilization:.1f}% of available tools",
                        evidence={
                            "server": server_name,
                            "used_tools": used_count,
                            "available_tools": total_count,
                            "utilization_percent": round(utilization, 1),
                            "threshold_percent": self.thresholds.underutilized_server_percent,
                            "unused_tools_sample": unused_tools[:5],  # First 5 as sample
                        },
                    )
                )

        return smells

    def _detect_burst_pattern(self, session: Session) -> List[Smell]:
        """Detect rapid tool calls (>5 within 1 second).

        Burst patterns may indicate loops, retry storms, or inefficient
        sequential operations that could be batched.
        """
        smells: List[Smell] = []

        # Collect all calls with timestamps, sorted by time
        all_calls: List[Call] = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)

        if len(all_calls) < self.thresholds.burst_pattern_calls:
            return smells

        # Sort by timestamp
        all_calls.sort(key=lambda c: c.timestamp)

        # Sliding window detection
        window_ms = self.thresholds.burst_pattern_window_ms
        window_delta = timedelta(milliseconds=window_ms)

        i = 0
        detected_bursts: List[tuple[int, int, int]] = []  # (start_idx, end_idx, count)

        while i < len(all_calls):
            window_start = all_calls[i].timestamp
            window_end = window_start + window_delta

            # Count calls in window
            j = i
            while j < len(all_calls) and all_calls[j].timestamp <= window_end:
                j += 1

            calls_in_window = j - i

            if calls_in_window >= self.thresholds.burst_pattern_calls:
                # Found a burst - record it
                detected_bursts.append((i, j - 1, calls_in_window))
                # Skip past this burst to avoid duplicate detection
                i = j
            else:
                i += 1

        # Create smells for each burst
        for start_idx, end_idx, count in detected_bursts:
            burst_calls = all_calls[start_idx : end_idx + 1]
            tool_counts: Dict[str, int] = defaultdict(int)
            for call in burst_calls:
                tool_counts[call.tool_name] += 1

            most_common_tool = max(tool_counts.keys(), key=lambda t: tool_counts[t])

            smells.append(
                Smell(
                    pattern="BURST_PATTERN",
                    severity="warning",
                    tool=most_common_tool if tool_counts[most_common_tool] > count // 2 else None,
                    description=f"{count} tool calls within {window_ms}ms",
                    evidence={
                        "call_count": count,
                        "window_ms": window_ms,
                        "threshold": self.thresholds.burst_pattern_calls,
                        "start_index": all_calls[start_idx].index,
                        "end_index": all_calls[end_idx].index,
                        "tool_breakdown": dict(tool_counts),
                    },
                )
            )

        return smells

    def _detect_large_payload(self, session: Session) -> List[Smell]:
        """Detect single tool calls consuming >10K tokens.

        Large payloads may indicate over-fetching or missing pagination.
        Consider chunking or more targeted queries.
        """
        smells: List[Smell] = []

        for server_session in session.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                for call in tool_stats.call_history:
                    if call.total_tokens >= self.thresholds.large_payload_tokens:
                        smells.append(
                            Smell(
                                pattern="LARGE_PAYLOAD",
                                severity="info",
                                tool=tool_name,
                                description=f"Single call consumed {call.total_tokens:,} tokens",
                                evidence={
                                    "tokens": call.total_tokens,
                                    "threshold": self.thresholds.large_payload_tokens,
                                    "call_index": call.index,
                                    "input_tokens": call.input_tokens,
                                    "output_tokens": call.output_tokens,
                                },
                            )
                        )

        return smells

    def _detect_sequential_reads(self, session: Session) -> List[Smell]:
        """Detect multiple consecutive file read operations.

        Sequential reads may benefit from batching into a single operation
        or using glob patterns for related files.
        """
        smells: List[Smell] = []

        # Collect all calls sorted by index
        all_calls: List[Call] = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)

        if len(all_calls) < self.thresholds.sequential_read_threshold:
            return smells

        # Sort by call index
        all_calls.sort(key=lambda c: c.index)

        # Look for consecutive Read tool calls
        read_tool_names = {"Read", "mcp__Read", "read_file", "mcp__read_file"}
        read_sequences: List[List[Call]] = []
        current_sequence: List[Call] = []

        for call in all_calls:
            # Check if this is a read operation
            tool_base = call.tool_name.split("__")[-1] if "__" in call.tool_name else call.tool_name
            is_read = tool_base in read_tool_names or "read" in tool_base.lower()

            if is_read:
                current_sequence.append(call)
            else:
                if len(current_sequence) >= self.thresholds.sequential_read_threshold:
                    read_sequences.append(current_sequence)
                current_sequence = []

        # Check final sequence
        if len(current_sequence) >= self.thresholds.sequential_read_threshold:
            read_sequences.append(current_sequence)

        # Create smells for each sequence
        for sequence in read_sequences:
            total_tokens = sum(c.total_tokens for c in sequence)
            smells.append(
                Smell(
                    pattern="SEQUENTIAL_READS",
                    severity="info",
                    tool=sequence[0].tool_name,
                    description=f"{len(sequence)} consecutive file reads",
                    evidence={
                        "read_count": len(sequence),
                        "threshold": self.thresholds.sequential_read_threshold,
                        "total_tokens": total_tokens,
                        "start_index": sequence[0].index,
                        "end_index": sequence[-1].index,
                    },
                )
            )

        return smells

    def _detect_cache_miss_streak(self, session: Session) -> List[Smell]:
        """Detect 5+ consecutive calls with zero cache hits.

        Cache miss streaks indicate context that isn't being reused,
        potentially from non-deterministic queries or missing cache warmup.
        """
        smells: List[Smell] = []

        # Collect all calls sorted by index
        all_calls: List[Call] = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)

        if len(all_calls) < self.thresholds.cache_miss_streak_threshold:
            return smells

        # Sort by call index
        all_calls.sort(key=lambda c: c.index)

        # Find streaks of cache misses
        miss_streaks: List[List[Call]] = []
        current_streak: List[Call] = []

        for call in all_calls:
            if call.cache_read_tokens == 0:
                current_streak.append(call)
            else:
                if len(current_streak) >= self.thresholds.cache_miss_streak_threshold:
                    miss_streaks.append(current_streak)
                current_streak = []

        # Check final streak
        if len(current_streak) >= self.thresholds.cache_miss_streak_threshold:
            miss_streaks.append(current_streak)

        # Create smells for each streak
        for streak in miss_streaks:
            total_tokens = sum(c.total_tokens for c in streak)
            tool_counts: Dict[str, int] = defaultdict(int)
            for call in streak:
                tool_counts[call.tool_name] += 1

            smells.append(
                Smell(
                    pattern="CACHE_MISS_STREAK",
                    severity="warning",
                    tool=None,  # Session-level pattern
                    description=f"{len(streak)} consecutive cache misses",
                    evidence={
                        "miss_count": len(streak),
                        "threshold": self.thresholds.cache_miss_streak_threshold,
                        "total_tokens": total_tokens,
                        "start_index": streak[0].index,
                        "end_index": streak[-1].index,
                        "tools_involved": dict(tool_counts),
                    },
                )
            )

        return smells

    # v1.0.0 Security detectors (task-143)

    def _detect_credential_exposure(self, session: Session) -> List[Smell]:
        """Detect hardcoded credentials in tool parameters using PrivacyFilter.

        This detector uses the existing PrivacyFilter's redact_string() method
        to identify potential credentials (API keys, tokens, passwords, etc.)
        in tool call parameters.

        Evidence includes:
        - call_index: Which call triggered the detection
        - redacted_count: Number of [REDACTED] replacements
        - matched_patterns: List of pattern names that matched (e.g., ["api_key", "bearer_token"])
        - redacted_preview: Truncated redacted string for context (max 150 chars)
        """
        from .privacy import PrivacyFilter

        smells: List[Smell] = []
        if not self.thresholds.credential_exposure_enabled:
            return smells

        privacy_filter = PrivacyFilter()

        for server_session in session.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                for call in tool_stats.call_history:
                    if not call.platform_data:
                        continue

                    data_str = json.dumps(call.platform_data, default=str)
                    redacted = privacy_filter.redact_string(data_str)

                    if redacted != data_str:
                        redacted_count = redacted.count("[REDACTED]")

                        # Identify which patterns matched (task-162)
                        matched_patterns = [
                            name
                            for name, pattern in privacy_filter.PATTERNS.items()
                            if pattern.search(data_str)
                        ]

                        # Create truncated preview for context (task-162)
                        max_preview_len = 150
                        redacted_preview = (
                            redacted[:max_preview_len] + "..."
                            if len(redacted) > max_preview_len
                            else redacted
                        )

                        smells.append(
                            Smell(
                                pattern="CREDENTIAL_EXPOSURE",
                                severity="high",
                                tool=tool_name,
                                description="Potential credential detected in tool parameters",
                                evidence={
                                    "call_index": call.index,
                                    "redacted_count": redacted_count,
                                    "matched_patterns": matched_patterns,
                                    "redacted_preview": redacted_preview,
                                },
                            )
                        )
        return smells

    def _detect_suspicious_tool_description(self, session: Session) -> List[Smell]:
        """Detect potential prompt injection indicators in tool parameters.

        This detector looks for patterns commonly used in prompt injection
        attacks, such as attempts to override instructions or role changes.
        """
        smells: List[Smell] = []

        for server_session in session.server_sessions.values():
            for tool_name, tool_stats in server_session.tools.items():
                for call in tool_stats.call_history:
                    if not call.platform_data:
                        continue

                    data_str = json.dumps(call.platform_data, default=str)
                    matched = [
                        p.pattern[:30] for p in PROMPT_INJECTION_INDICATORS if p.search(data_str)
                    ]

                    if len(matched) >= self.thresholds.suspicious_description_min_indicators:
                        smells.append(
                            Smell(
                                pattern="SUSPICIOUS_TOOL_DESCRIPTION",
                                severity="medium",
                                tool=tool_name,
                                description=f"Potential prompt injection ({len(matched)} indicators)",
                                evidence={
                                    "call_index": call.index,
                                    "indicator_count": len(matched),
                                },
                            )
                        )
        return smells

    def _detect_unusual_data_flow(self, session: Session) -> List[Smell]:
        """Detect potential data exfiltration patterns.

        This detector identifies when large amounts of data are read
        followed by external tool calls (fetch, http, webhook, etc.),
        which could indicate data exfiltration attempts.
        """
        smells: List[Smell] = []

        # Collect and sort all calls by index
        all_calls: List[Call] = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                all_calls.extend(tool_stats.call_history)
        all_calls.sort(key=lambda c: c.index)

        recent_reads: List[Call] = []

        for call in all_calls:
            tool_lower = call.tool_name.lower()
            is_read = "read" in tool_lower
            is_external = any(ext in tool_lower for ext in EXTERNAL_TOOL_PATTERNS)

            if is_read:
                recent_reads.append(call)
                # Keep a sliding window of recent reads
                if len(recent_reads) > 5:
                    recent_reads.pop(0)

            if is_external and recent_reads:
                total_read_tokens = sum(r.output_tokens for r in recent_reads)
                if total_read_tokens >= self.thresholds.unusual_data_flow_output_threshold:
                    smells.append(
                        Smell(
                            pattern="UNUSUAL_DATA_FLOW",
                            severity="medium",
                            tool=call.tool_name,
                            description=f"External call after large reads ({total_read_tokens:,} tokens)",
                            evidence={
                                "call_index": call.index,
                                "read_tokens": total_read_tokens,
                                "recent_read_count": len(recent_reads),
                            },
                        )
                    )
                    recent_reads.clear()

        return smells


def detect_smells(
    session: Session,
    thresholds: Optional[SmellThresholds] = None,
) -> List[Smell]:
    """Convenience function to detect smells in a session.

    Args:
        session: Finalized session with tool statistics
        thresholds: Optional custom thresholds (uses defaults if not provided)

    Returns:
        List of Smell objects for detected anti-patterns
    """
    detector = SmellDetector(thresholds=thresholds or SmellThresholds())
    return detector.analyze(session)
