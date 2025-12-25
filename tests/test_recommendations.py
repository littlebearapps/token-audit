"""Tests for the RecommendationEngine (v0.8.0 - task-106.2)."""

import pytest

from token_audit.base_tracker import Smell
from token_audit.recommendations import (
    Recommendation,
    RecommendationEngine,
    RecommendationType,
    generate_recommendations,
)


class TestRecommendationDataclass:
    """Test the Recommendation dataclass."""

    def test_recommendation_creation(self):
        """Test creating a recommendation with all fields."""
        rec = Recommendation(
            type=RecommendationType.REMOVE_UNUSED_SERVER,
            confidence=0.85,
            evidence="Server 'test' has 0 tool usage",
            action="Remove 'test' from config",
            impact="Save 500 tokens/turn",
            source_smell="UNDERUTILIZED_SERVER",
            details={"server": "test"},
        )

        assert rec.type == RecommendationType.REMOVE_UNUSED_SERVER
        assert rec.confidence == 0.85
        assert rec.source_smell == "UNDERUTILIZED_SERVER"
        assert rec.details["server"] == "test"

    def test_recommendation_to_dict(self):
        """Test converting recommendation to dict."""
        rec = Recommendation(
            type=RecommendationType.ENABLE_CACHING,
            confidence=0.7555,  # Should be rounded
            evidence="Low cache hit rate",
            action="Improve caching",
            impact="Save tokens",
            source_smell="LOW_CACHE_HIT",
        )

        d = rec.to_dict()

        assert d["type"] == "ENABLE_CACHING"
        assert d["confidence"] == 0.76  # Rounded to 2 decimals
        assert d["evidence"] == "Low cache hit rate"
        assert d["source_smell"] == "LOW_CACHE_HIT"

    def test_recommendation_to_dict_without_optional(self):
        """Test to_dict excludes None source_smell and empty details."""
        rec = Recommendation(
            type=RecommendationType.OPTIMIZE_COST,
            confidence=0.5,
            evidence="High usage",
            action="Optimize",
            impact="Reduce cost",
        )

        d = rec.to_dict()

        assert "source_smell" not in d
        assert "details" not in d


class TestRecommendationEngine:
    """Test the RecommendationEngine class."""

    def test_empty_smells(self):
        """Test with no smells returns empty list."""
        engine = RecommendationEngine()
        recs = engine.generate([])

        assert recs == []

    def test_min_confidence_filter(self):
        """Test that low confidence recommendations are filtered."""
        # Create a smell that would produce low confidence
        smell = Smell(
            pattern="HIGH_MCP_SHARE",
            severity="info",
            description="MCP at 85%",
            evidence={
                "mcp_percentage": 85,
                "mcp_tokens": 85000,
                "session_tokens": 100000,
                "server_count": 2,
            },
        )

        # With default min_confidence (0.3), should include
        engine = RecommendationEngine(min_confidence=0.3)
        recs = engine.generate([smell])
        assert len(recs) == 1

        # With high min_confidence, should exclude
        engine_strict = RecommendationEngine(min_confidence=0.9)
        recs_strict = engine_strict.generate([smell])
        assert len(recs_strict) == 0

    def test_sorted_by_confidence(self):
        """Test recommendations are sorted by confidence descending."""
        smells = [
            Smell(
                pattern="HIGH_VARIANCE",
                severity="warning",
                tool="tool1",
                evidence={"coefficient_of_variation": 0.6, "min_tokens": 100, "max_tokens": 1000},
            ),
            Smell(
                pattern="UNDERUTILIZED_SERVER",
                severity="info",
                evidence={
                    "server": "unused",
                    "utilization_percent": 0,
                    "available_tools": 10,
                    "used_tools": 0,
                },
            ),
        ]

        engine = RecommendationEngine()
        recs = engine.generate(smells)

        # UNDERUTILIZED_SERVER with 0% should have higher confidence
        assert len(recs) == 2
        assert recs[0].source_smell == "UNDERUTILIZED_SERVER"
        assert recs[0].confidence > recs[1].confidence


class TestSmellToRecommendationMapping:
    """Test each smell pattern maps to the correct recommendation type."""

    @pytest.fixture
    def engine(self):
        return RecommendationEngine()

    def test_underutilized_server_mapping(self, engine):
        """UNDERUTILIZED_SERVER -> REMOVE_UNUSED_SERVER."""
        smell = Smell(
            pattern="UNDERUTILIZED_SERVER",
            severity="info",
            evidence={
                "server": "brave-search",
                "utilization_percent": 5,
                "available_tools": 10,
                "used_tools": 1,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.REMOVE_UNUSED_SERVER
        assert "brave-search" in recs[0].evidence

    def test_low_cache_hit_mapping(self, engine):
        """LOW_CACHE_HIT -> ENABLE_CACHING."""
        smell = Smell(
            pattern="LOW_CACHE_HIT",
            severity="warning",
            evidence={
                "hit_rate_percent": 15,
                "threshold_percent": 30,
                "cache_read_tokens": 1500,
                "input_tokens": 10000,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.ENABLE_CACHING
        assert "15" in recs[0].evidence  # hit rate

    def test_cache_miss_streak_mapping(self, engine):
        """CACHE_MISS_STREAK -> ENABLE_CACHING."""
        smell = Smell(
            pattern="CACHE_MISS_STREAK",
            severity="warning",
            evidence={
                "miss_count": 8,
                "total_tokens": 5000,
                "tools_involved": {"Read": 5, "Grep": 3},
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.ENABLE_CACHING
        assert "8" in recs[0].evidence  # miss count

    def test_redundant_calls_mapping(self, engine):
        """REDUNDANT_CALLS -> ENABLE_CACHING."""
        smell = Smell(
            pattern="REDUNDANT_CALLS",
            severity="warning",
            tool="mcp__backlog__task_view",
            evidence={"duplicate_count": 5, "content_hash": "abc123..."},
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.ENABLE_CACHING
        assert "5 times" in recs[0].evidence

    def test_sequential_reads_mapping(self, engine):
        """SEQUENTIAL_READS -> BATCH_OPERATIONS."""
        smell = Smell(
            pattern="SEQUENTIAL_READS",
            severity="info",
            tool="Read",
            evidence={"read_count": 7, "total_tokens": 3500},
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.BATCH_OPERATIONS
        assert "7" in recs[0].evidence

    def test_chatty_mapping(self, engine):
        """CHATTY -> BATCH_OPERATIONS."""
        smell = Smell(
            pattern="CHATTY",
            severity="warning",
            tool="mcp__backlog__task_edit",
            evidence={
                "call_count": 35,
                "threshold": 20,
                "total_tokens": 17500,
                "avg_tokens_per_call": 500,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.BATCH_OPERATIONS
        assert "35 times" in recs[0].evidence

    def test_burst_pattern_mapping(self, engine):
        """BURST_PATTERN -> BATCH_OPERATIONS."""
        smell = Smell(
            pattern="BURST_PATTERN",
            severity="warning",
            tool="Bash",
            evidence={
                "call_count": 10,
                "window_ms": 1000,
                "tool_breakdown": {"Bash": 8, "Read": 2},
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.BATCH_OPERATIONS
        assert "10 tool calls" in recs[0].evidence

    def test_expensive_failures_mapping(self, engine):
        """EXPENSIVE_FAILURES -> OPTIMIZE_COST."""
        smell = Smell(
            pattern="EXPENSIVE_FAILURES",
            severity="high",
            tool="mcp__context7__fetch",
            evidence={
                "tokens": 15000,
                "threshold": 5000,
                "error_info": "Connection timeout",
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.OPTIMIZE_COST
        assert "15,000 tokens" in recs[0].evidence

    def test_top_consumer_mapping(self, engine):
        """TOP_CONSUMER -> OPTIMIZE_COST."""
        smell = Smell(
            pattern="TOP_CONSUMER",
            severity="info",
            tool="mcp__jina__read_url",
            evidence={
                "percentage": 65,
                "tool_tokens": 65000,
                "total_mcp_tokens": 100000,
                "calls": 10,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.OPTIMIZE_COST
        assert "65.0%" in recs[0].evidence

    def test_large_payload_mapping(self, engine):
        """LARGE_PAYLOAD -> OPTIMIZE_COST."""
        smell = Smell(
            pattern="LARGE_PAYLOAD",
            severity="info",
            tool="Read",
            evidence={
                "tokens": 25000,
                "threshold": 10000,
                "input_tokens": 5000,
                "output_tokens": 20000,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.OPTIMIZE_COST
        assert "25,000 tokens" in recs[0].evidence

    def test_high_variance_mapping(self, engine):
        """HIGH_VARIANCE -> OPTIMIZE_COST."""
        smell = Smell(
            pattern="HIGH_VARIANCE",
            severity="warning",
            tool="mcp__brave__search",
            evidence={
                "coefficient_of_variation": 0.75,
                "min_tokens": 500,
                "max_tokens": 8000,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.OPTIMIZE_COST
        assert "CV=0.75" in recs[0].evidence

    def test_high_mcp_share_mapping(self, engine):
        """HIGH_MCP_SHARE -> OPTIMIZE_COST."""
        smell = Smell(
            pattern="HIGH_MCP_SHARE",
            severity="info",
            evidence={
                "mcp_percentage": 92,
                "mcp_tokens": 92000,
                "session_tokens": 100000,
                "server_count": 5,
            },
        )

        recs = engine.generate([smell])

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.OPTIMIZE_COST
        assert "92.0%" in recs[0].evidence


class TestConfidenceScoring:
    """Test confidence scoring logic for different patterns."""

    @pytest.fixture
    def engine(self):
        return RecommendationEngine(min_confidence=0.0)

    def test_underutilized_0_percent_high_confidence(self, engine):
        """0% utilization should have very high confidence."""
        smell = Smell(
            pattern="UNDERUTILIZED_SERVER",
            evidence={
                "server": "unused",
                "utilization_percent": 0,
                "available_tools": 5,
                "used_tools": 0,
            },
        )

        recs = engine.generate([smell])
        assert recs[0].confidence == 0.95

    def test_underutilized_low_percent_medium_confidence(self, engine):
        """Low but non-zero utilization has medium-high confidence."""
        smell = Smell(
            pattern="UNDERUTILIZED_SERVER",
            evidence={
                "server": "test",
                "utilization_percent": 3,
                "available_tools": 10,
                "used_tools": 1,
            },
        )

        recs = engine.generate([smell])
        assert recs[0].confidence == 0.85

    def test_low_cache_very_low_rate_high_confidence(self, engine):
        """Very low cache hit rate should have high confidence."""
        smell = Smell(
            pattern="LOW_CACHE_HIT",
            evidence={
                "hit_rate_percent": 5,
                "threshold_percent": 30,
                "cache_read_tokens": 500,
                "input_tokens": 10000,
            },
        )

        recs = engine.generate([smell])
        assert recs[0].confidence == 0.9

    def test_chatty_very_high_calls_high_confidence(self, engine):
        """Very chatty tools have higher confidence."""
        smell = Smell(
            pattern="CHATTY",
            tool="test",
            evidence={
                "call_count": 50,  # > 2x threshold
                "threshold": 20,
                "total_tokens": 25000,
                "avg_tokens_per_call": 500,
            },
        )

        recs = engine.generate([smell])
        assert recs[0].confidence == 0.9


class TestConvenienceFunction:
    """Test the generate_recommendations convenience function."""

    def test_generate_recommendations_function(self):
        """Test the standalone generate_recommendations function."""
        smells = [
            Smell(
                pattern="CHATTY",
                tool="test",
                evidence={
                    "call_count": 25,
                    "threshold": 20,
                    "total_tokens": 5000,
                    "avg_tokens_per_call": 200,
                },
            )
        ]

        recs = generate_recommendations(smells)

        assert len(recs) == 1
        assert recs[0].type == RecommendationType.BATCH_OPERATIONS

    def test_generate_recommendations_with_min_confidence(self):
        """Test min_confidence parameter."""
        smells = [
            Smell(
                pattern="HIGH_MCP_SHARE",
                evidence={
                    "mcp_percentage": 85,
                    "mcp_tokens": 85000,
                    "session_tokens": 100000,
                    "server_count": 2,
                },
            )
        ]

        # Should include with low threshold
        recs = generate_recommendations(smells, min_confidence=0.3)
        assert len(recs) == 1

        # Should exclude with high threshold
        recs_strict = generate_recommendations(smells, min_confidence=0.9)
        assert len(recs_strict) == 0


class TestRecommendationTypes:
    """Test recommendation type coverage."""

    def test_all_types_represented(self):
        """Verify all 4 recommendation types can be generated."""
        smells = [
            # REMOVE_UNUSED_SERVER
            Smell(
                pattern="UNDERUTILIZED_SERVER",
                evidence={
                    "server": "test",
                    "utilization_percent": 0,
                    "available_tools": 5,
                    "used_tools": 0,
                },
            ),
            # ENABLE_CACHING
            Smell(
                pattern="LOW_CACHE_HIT",
                evidence={
                    "hit_rate_percent": 10,
                    "threshold_percent": 30,
                    "cache_read_tokens": 1000,
                    "input_tokens": 10000,
                },
            ),
            # BATCH_OPERATIONS
            Smell(
                pattern="CHATTY",
                tool="test",
                evidence={
                    "call_count": 30,
                    "threshold": 20,
                    "total_tokens": 6000,
                    "avg_tokens_per_call": 200,
                },
            ),
            # OPTIMIZE_COST
            Smell(
                pattern="TOP_CONSUMER",
                tool="expensive",
                evidence={
                    "percentage": 70,
                    "tool_tokens": 70000,
                    "total_mcp_tokens": 100000,
                    "calls": 5,
                },
            ),
        ]

        recs = generate_recommendations(smells)
        types = {r.type for r in recs}

        assert RecommendationType.REMOVE_UNUSED_SERVER in types
        assert RecommendationType.ENABLE_CACHING in types
        assert RecommendationType.BATCH_OPERATIONS in types
        assert RecommendationType.OPTIMIZE_COST in types
