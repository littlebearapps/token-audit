"""4-Bucket Token Classification System (v1.0.4 - task-247).

Classifies MCP tool calls into efficiency buckets for diagnosing WHERE
token bloat comes from in AI agent workflows.

Buckets:
    redundant: Duplicate tool calls (same content_hash, 2nd+ occurrence)
    tool_discovery: Introspection calls (*_introspect*, *_describe*, *_schema*)
    state_serialization: Large content payloads (>5K tokens, *_get_*, *_list_*)
    drift: Residual (reasoning, retries, errors) - default bucket

Classification Priority:
    1. redundant (highest) - exact duplicates take priority
    2. tool_discovery - schema introspection
    3. state_serialization - pattern match OR large output
    4. drift (default) - everything else

Usage:
    from token_audit.buckets import BucketClassifier

    classifier = BucketClassifier()
    results = classifier.classify_session(session)

    for result in results:
        print(f"{result.bucket}: {result.tokens} tokens ({result.percentage:.1f}%)")
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Pattern

if TYPE_CHECKING:
    from token_audit.base_tracker import Call, Session


# =============================================================================
# Bucket Name Constants
# =============================================================================


class BucketName:
    """Bucket classification constants."""

    REDUNDANT = "redundant"
    STATE_SERIALIZATION = "state_serialization"
    TOOL_DISCOVERY = "tool_discovery"
    DRIFT = "drift"

    @classmethod
    def all(cls) -> list[str]:
        """Return all bucket names in priority order."""
        return [cls.REDUNDANT, cls.TOOL_DISCOVERY, cls.STATE_SERIALIZATION, cls.DRIFT]


# =============================================================================
# Default Patterns (Task 247.2)
# =============================================================================

# Patterns are case-insensitive regex
# Order matters: checked in priority order (redundant → discovery → state → drift)

DEFAULT_BUCKET_PATTERNS: dict[str, list[str]] = {
    "state_serialization": [
        r".*_get_.*",  # wpnav_get_page, mcp__backlog__task_get
        r".*_get$",  # task_get (ending with _get)
        r".*_list_.*",  # wpnav_list_pages (with _list_ in middle)
        r".*_list$",  # task_list (ending with _list)
        r".*_snapshot.*",  # Full page captures
        r".*_export.*",  # Bulk data exports
        r".*_read.*",  # File reads (Read, read_file)
        r".*_view.*",  # mcp__backlog__task_view, document_view
        r".*_view$",  # task_view (ending with _view)
        r".*_fetch.*",  # API fetches
    ],
    "tool_discovery": [
        r".*_introspect.*",  # Schema introspection
        r".*_search_tools.*",  # Tool discovery
        r".*_describe.*",  # Tool descriptions
        r".*_list_tools.*",  # Tool listing
        r".*_schema.*",  # Schema queries
        r".*_capabilities.*",  # Capability queries
    ],
    # redundant: detected via content_hash, no patterns needed
    # drift: default bucket, no patterns needed
}


# =============================================================================
# Configuration Dataclasses
# =============================================================================


@dataclass
class BucketThresholds:
    """Configurable thresholds for bucket classification.

    Attributes:
        large_payload_threshold: Token count above which a call is considered
            "state serialization" regardless of pattern match (default: 5000)
        redundant_min_occurrences: Minimum occurrences of content_hash to
            classify as redundant. First occurrence is NOT redundant.
            (default: 2, meaning 2+ occurrences = 1st original + 1+ duplicates)
    """

    large_payload_threshold: int = 5000
    redundant_min_occurrences: int = 2  # Matches smells.py default


DEFAULT_BUCKET_THRESHOLDS = BucketThresholds()


# =============================================================================
# Result Dataclasses
# =============================================================================


@dataclass
class BucketResult:
    """Aggregated result for a single bucket.

    Attributes:
        bucket: Bucket identifier (redundant, state_serialization,
                tool_discovery, drift)
        tokens: Total tokens in this bucket
        percentage: Percentage of session tokens in this bucket
        call_count: Number of calls classified into this bucket
        top_tools: Top 5 tools by token consumption [(tool_name, tokens), ...]
    """

    bucket: str
    tokens: int = 0
    percentage: float = 0.0
    call_count: int = 0
    top_tools: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "bucket": self.bucket,
            "tokens": self.tokens,
            "percentage": round(self.percentage, 2),
            "call_count": self.call_count,
            "top_tools": [{"tool": name, "tokens": tokens} for name, tokens in self.top_tools],
        }


@dataclass
class CallClassification:
    """Classification result for a single call (internal use).

    Attributes:
        call_index: Index of the call in session
        tool_name: Name of the tool that was called
        primary_bucket: Primary classification
        secondary_bucket: Secondary classification for overlap tracking
            (e.g., a redundant call that would have been state_serialization)
        tokens: Token count for this call
    """

    call_index: int
    tool_name: str
    primary_bucket: str
    tokens: int = 0
    secondary_bucket: str | None = None


# =============================================================================
# BucketClassifier (Task 247.1)
# =============================================================================


class BucketClassifier:
    """Classifies MCP tool calls into efficiency buckets.

    Classification priority order:
    1. REDUNDANT - Duplicate content_hash (first occurrence excluded)
    2. TOOL_DISCOVERY - Matches introspection patterns
    3. STATE_SERIALIZATION - Large output OR matches state patterns
    4. DRIFT - Residual (reasoning, retries, errors)

    Usage:
        classifier = BucketClassifier()
        results = classifier.classify_session(session)

        # Or for single call (with pre-built hash index):
        hash_counts, hash_first_seen = classifier._build_hash_index(session)
        bucket = classifier.classify_call(call, hash_counts, hash_first_seen)
    """

    def __init__(
        self,
        patterns: dict[str, list[str]] | None = None,
        thresholds: BucketThresholds | None = None,
        load_from_config: bool = False,
    ):
        """Initialize classifier with patterns and thresholds.

        Args:
            patterns: Custom bucket patterns (regex strings).
                      Defaults to DEFAULT_BUCKET_PATTERNS.
            thresholds: Custom classification thresholds.
                       Defaults to DEFAULT_BUCKET_THRESHOLDS.
            load_from_config: If True and patterns/thresholds not provided,
                            load from token-audit.toml config file.
        """
        if load_from_config and patterns is None and thresholds is None:
            # Load from config file (task-247.12)
            from token_audit.bucket_config import load_config

            config = load_config()
            self.patterns = config.patterns
            self.thresholds = BucketThresholds(
                large_payload_threshold=config.large_payload_threshold,
                redundant_min_occurrences=config.redundant_min_occurrences,
            )
        else:
            self.patterns = patterns or DEFAULT_BUCKET_PATTERNS
            self.thresholds = thresholds or DEFAULT_BUCKET_THRESHOLDS

        # Compile patterns for performance
        self._compiled_patterns: dict[str, list[Pattern[str]]] = {}
        for bucket, pattern_list in self.patterns.items():
            self._compiled_patterns[bucket] = [re.compile(p, re.IGNORECASE) for p in pattern_list]

    @classmethod
    def from_config(cls, config_path: str | None = None) -> BucketClassifier:
        """Create a classifier from token-audit.toml config.

        Args:
            config_path: Optional explicit path to config file.

        Returns:
            BucketClassifier initialized from config file.
        """
        from pathlib import Path

        from token_audit.bucket_config import load_config

        path = Path(config_path) if config_path else None
        config = load_config(path)

        return cls(
            patterns=config.patterns,
            thresholds=BucketThresholds(
                large_payload_threshold=config.large_payload_threshold,
                redundant_min_occurrences=config.redundant_min_occurrences,
            ),
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def classify_call(
        self,
        call: Call,
        hash_counts: dict[str, int] | None = None,
        hash_first_seen: dict[str, int] | None = None,
    ) -> CallClassification:
        """Classify a single call into a bucket.

        Args:
            call: The Call object to classify
            hash_counts: Mapping of content_hash -> occurrence count
            hash_first_seen: Mapping of content_hash -> first call index
                            (to determine if THIS call is the first)

        Returns:
            CallClassification with primary and optional secondary bucket
        """
        # Priority 1: Check for redundancy (highest priority)
        if self._is_redundant(call, hash_counts, hash_first_seen):
            secondary = self._check_pattern_buckets(call)
            return CallClassification(
                call_index=call.index,
                tool_name=call.tool_name,
                primary_bucket=BucketName.REDUNDANT,
                secondary_bucket=secondary,
                tokens=call.total_tokens,
            )

        # Priority 2: Check tool discovery patterns
        if self._matches_patterns(call.tool_name, "tool_discovery"):
            return CallClassification(
                call_index=call.index,
                tool_name=call.tool_name,
                primary_bucket=BucketName.TOOL_DISCOVERY,
                tokens=call.total_tokens,
            )

        # Priority 3: Check state serialization (pattern OR large output)
        if self._is_state_serialization(call):
            return CallClassification(
                call_index=call.index,
                tool_name=call.tool_name,
                primary_bucket=BucketName.STATE_SERIALIZATION,
                tokens=call.total_tokens,
            )

        # Priority 4: Default to drift
        return CallClassification(
            call_index=call.index,
            tool_name=call.tool_name,
            primary_bucket=BucketName.DRIFT,
            tokens=call.total_tokens,
        )

    def classify_session(
        self,
        session: Session,
    ) -> list[BucketResult]:
        """Classify all calls in a session and aggregate results.

        Args:
            session: Complete session with server_sessions populated

        Returns:
            List of BucketResult, one per bucket (4 total), sorted by tokens descending
        """
        # Step 1: Build hash occurrence counts (reuse smells.py logic)
        hash_counts, hash_first_seen = self._build_hash_index(session)

        # Step 2: Classify each call
        classifications: list[CallClassification] = []
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    classification = self.classify_call(call, hash_counts, hash_first_seen)
                    classifications.append(classification)

        # Step 3: Aggregate into bucket results
        return self._aggregate_results(classifications)

    def get_call_classifications(
        self,
        session: Session,
    ) -> dict[int, CallClassification]:
        """Get per-call classifications for debugging/analysis.

        Args:
            session: Complete session with server_sessions populated

        Returns:
            Dict mapping call.index -> CallClassification
        """
        hash_counts, hash_first_seen = self._build_hash_index(session)

        result: dict[int, CallClassification] = {}
        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    classification = self.classify_call(call, hash_counts, hash_first_seen)
                    result[call.index] = classification

        return result

    # -------------------------------------------------------------------------
    # Private: Hash Index for Redundancy Detection (Task 247.3)
    # -------------------------------------------------------------------------

    def _build_hash_index(self, session: Session) -> tuple[dict[str, int], dict[str, int]]:
        """Build content_hash occurrence counts from session.

        Reuses logic from smells.py:_detect_redundant_calls() (lines 402-437)
        but adapted to track per-call assignments.

        Returns:
            Tuple of (hash_counts, hash_first_seen):
            - hash_counts: content_hash -> total occurrences
            - hash_first_seen: content_hash -> first call index
        """
        hash_counts: dict[str, int] = defaultdict(int)
        hash_first_seen: dict[str, int] = {}

        for server_session in session.server_sessions.values():
            for tool_stats in server_session.tools.values():
                for call in tool_stats.call_history:
                    if call.content_hash:
                        hash_counts[call.content_hash] += 1
                        if call.content_hash not in hash_first_seen:
                            hash_first_seen[call.content_hash] = call.index

        return dict(hash_counts), hash_first_seen

    def _is_redundant(
        self,
        call: Call,
        hash_counts: dict[str, int] | None,
        hash_first_seen: dict[str, int] | None,
    ) -> bool:
        """Check if call is redundant (duplicate, not first occurrence).

        A call is redundant if:
        1. It has a content_hash
        2. That hash appears 2+ times in the session
        3. This is NOT the first occurrence of that hash

        Args:
            call: The call to check
            hash_counts: Mapping of content_hash -> total occurrences
            hash_first_seen: Mapping of content_hash -> first call index

        Returns:
            True if this call is a redundant duplicate
        """
        if not call.content_hash:
            return False
        if not hash_counts or not hash_first_seen:
            return False

        # Must have multiple occurrences
        count = hash_counts.get(call.content_hash, 0)
        if count < self.thresholds.redundant_min_occurrences:
            return False

        # First occurrence is NOT redundant (it's the "original")
        first_index = hash_first_seen.get(call.content_hash)
        return call.index != first_index

    # -------------------------------------------------------------------------
    # Private: Pattern Matching
    # -------------------------------------------------------------------------

    def _matches_patterns(self, tool_name: str, bucket: str) -> bool:
        """Check if tool_name matches any pattern for the bucket.

        Args:
            tool_name: The tool name to check (e.g., "mcp__wpnav__get_page")
            bucket: The bucket to check patterns for

        Returns:
            True if any pattern matches
        """
        patterns = self._compiled_patterns.get(bucket, [])
        return any(p.match(tool_name) for p in patterns)

    def _check_pattern_buckets(self, call: Call) -> str | None:
        """Check which pattern-based bucket a call would match.

        Used for secondary bucket tracking when a call is classified as
        redundant but would have matched another pattern.

        Args:
            call: The call to check

        Returns:
            Secondary bucket name, or None if only drift
        """
        if self._matches_patterns(call.tool_name, "tool_discovery"):
            return BucketName.TOOL_DISCOVERY
        if self._is_state_serialization(call):
            return BucketName.STATE_SERIALIZATION
        return None

    def _is_state_serialization(self, call: Call) -> bool:
        """Check if call is state serialization.

        A call is state serialization if:
        1. Tool name matches state patterns (*_get_*, *_list_*, etc.), OR
        2. Output tokens exceed large_payload_threshold

        Args:
            call: The call to check

        Returns:
            True if this is a state serialization call
        """
        # Check pattern match
        if self._matches_patterns(call.tool_name, "state_serialization"):
            return True

        # Check large output threshold
        return call.output_tokens >= self.thresholds.large_payload_threshold

    # -------------------------------------------------------------------------
    # Private: Aggregation
    # -------------------------------------------------------------------------

    def _aggregate_results(
        self,
        classifications: list[CallClassification],
    ) -> list[BucketResult]:
        """Aggregate individual classifications into bucket results.

        Args:
            classifications: List of per-call classifications

        Returns:
            List of BucketResult, one per bucket, sorted by tokens descending
        """
        # Initialize all buckets
        bucket_data: dict[str, dict[str, Any]] = {
            bucket: {"tokens": 0, "call_count": 0, "tools": defaultdict(int)}
            for bucket in BucketName.all()
        }

        # Aggregate by primary bucket
        for c in classifications:
            bucket_data[c.primary_bucket]["tokens"] += c.tokens
            bucket_data[c.primary_bucket]["call_count"] += 1
            bucket_data[c.primary_bucket]["tools"][c.tool_name] += c.tokens

        # Calculate total tokens for percentages
        total_tokens = sum(d["tokens"] for d in bucket_data.values())

        # Build results
        results = []
        for bucket_name, data in bucket_data.items():
            percentage = (data["tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0

            # Top 5 tools by tokens (sorted descending)
            top_tools = sorted(data["tools"].items(), key=lambda x: x[1], reverse=True)[:5]

            results.append(
                BucketResult(
                    bucket=bucket_name,
                    tokens=data["tokens"],
                    percentage=percentage,
                    call_count=data["call_count"],
                    top_tools=top_tools,
                )
            )

        # Sort by tokens descending
        results.sort(key=lambda r: r.tokens, reverse=True)
        return results


# =============================================================================
# Convenience Function
# =============================================================================


def classify_session(
    session: Session,
    patterns: dict[str, list[str]] | None = None,
    thresholds: BucketThresholds | None = None,
) -> list[BucketResult]:
    """Convenience function to classify a session into buckets.

    Args:
        session: The session to classify
        patterns: Optional custom patterns
        thresholds: Optional custom thresholds

    Returns:
        List of BucketResult, sorted by tokens descending
    """
    classifier = BucketClassifier(patterns=patterns, thresholds=thresholds)
    return classifier.classify_session(session)
