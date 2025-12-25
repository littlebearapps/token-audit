"""Tests for get_best_practices MCP tool integration (task-142).

Tests the tool implementation in server/tools.py, verifying it correctly
wires up to the BestPracticesLoader and produces valid schema output.
"""

import pytest

from token_audit.server.schemas import BestPractice, GetBestPracticesOutput, SeverityLevel
from token_audit.server.tools import get_best_practices


class TestGetBestPracticesTool:
    """Tests for the get_best_practices tool function."""

    def test_list_all_returns_all_practices(self) -> None:
        """list_all=True returns all 10 best practices."""
        result = get_best_practices(list_all=True)

        assert isinstance(result, GetBestPracticesOutput)
        assert len(result.practices) == 10
        assert result.total_available == 10

    def test_list_all_returns_schema_models(self) -> None:
        """Returned practices are Pydantic BestPractice models."""
        result = get_best_practices(list_all=True)

        for practice in result.practices:
            assert isinstance(practice, BestPractice)
            assert isinstance(practice.severity, SeverityLevel)
            assert isinstance(practice.id, str)
            assert isinstance(practice.content, str)

    def test_topic_search_finds_caching(self) -> None:
        """topic='caching' finds caching strategy practice."""
        result = get_best_practices(topic="caching")

        assert len(result.practices) >= 1
        ids = [p.id for p in result.practices]
        assert "caching_strategy" in ids
        assert result.total_available == 10

    def test_topic_search_finds_security(self) -> None:
        """topic='security' finds security practice."""
        result = get_best_practices(topic="security")

        assert len(result.practices) >= 1
        ids = [p.id for p in result.practices]
        assert "security" in ids

    def test_topic_search_smell_pattern(self) -> None:
        """topic can match smell patterns like 'LOW_CACHE_HIT'."""
        result = get_best_practices(topic="LOW_CACHE_HIT")

        assert len(result.practices) >= 1
        ids = [p.id for p in result.practices]
        assert "caching_strategy" in ids

    def test_topic_search_case_insensitive(self) -> None:
        """topic search is case insensitive."""
        upper = get_best_practices(topic="SECURITY")
        lower = get_best_practices(topic="security")

        assert len(upper.practices) == len(lower.practices)

    def test_no_args_returns_empty(self) -> None:
        """No arguments returns empty list with total available."""
        result = get_best_practices()

        assert len(result.practices) == 0
        assert result.total_available == 10

    def test_nonexistent_topic_returns_empty(self) -> None:
        """Nonexistent topic returns empty list."""
        result = get_best_practices(topic="nonexistent_xyz_123")

        assert len(result.practices) == 0
        assert result.total_available == 10

    def test_severity_mapping_high(self) -> None:
        """High severity practices map to SeverityLevel.HIGH."""
        result = get_best_practices(list_all=True)

        high_practices = [p for p in result.practices if p.severity == SeverityLevel.HIGH]
        assert len(high_practices) == 4
        high_ids = {p.id for p in high_practices}
        assert "progressive_disclosure" in high_ids
        assert "security" in high_ids
        assert "large_results" in high_ids
        assert "tool_count_limits" in high_ids

    def test_severity_mapping_medium(self) -> None:
        """Medium severity practices map to SeverityLevel.MEDIUM."""
        result = get_best_practices(list_all=True)

        medium_practices = [p for p in result.practices if p.severity == SeverityLevel.MEDIUM]
        assert len(medium_practices) == 6

    def test_practice_has_category(self) -> None:
        """All practices have category field populated."""
        result = get_best_practices(list_all=True)

        categories = {p.category for p in result.practices}
        assert "efficiency" in categories
        assert "security" in categories
        assert "design" in categories
        assert "operations" in categories

    def test_practice_has_content(self) -> None:
        """All practices have non-empty content."""
        result = get_best_practices(list_all=True)

        for practice in result.practices:
            assert practice.content, f"Practice {practice.id} has empty content"
            assert len(practice.content) > 100

    def test_related_smells_populated(self) -> None:
        """Practices with related_smells have them populated."""
        result = get_best_practices(topic="caching")

        caching = next(p for p in result.practices if p.id == "caching_strategy")
        assert "LOW_CACHE_HIT" in caching.related_smells
        assert "CACHE_MISS_STREAK" in caching.related_smells

    def test_token_savings_populated(self) -> None:
        """Practices with token_savings have them populated."""
        result = get_best_practices(topic="progressive")

        progressive = next(p for p in result.practices if p.id == "progressive_disclosure")
        assert progressive.token_savings == "98%"

    def test_source_populated(self) -> None:
        """Practices with source have them populated."""
        result = get_best_practices(topic="progressive")

        progressive = next(p for p in result.practices if p.id == "progressive_disclosure")
        assert progressive.source == "Anthropic Engineering Blog"

    def test_keywords_populated(self) -> None:
        """Practices with keywords have them populated."""
        result = get_best_practices(topic="progressive")

        progressive = next(p for p in result.practices if p.id == "progressive_disclosure")
        assert len(progressive.keywords) > 0
        assert "context bloat" in progressive.keywords


class TestSeverityToEnum:
    """Tests for the _severity_to_enum helper function."""

    def test_all_severities_mapped(self) -> None:
        """All expected severities are mapped correctly."""
        from token_audit.server.tools import _severity_to_enum

        assert _severity_to_enum("high") == SeverityLevel.HIGH
        assert _severity_to_enum("medium") == SeverityLevel.MEDIUM
        assert _severity_to_enum("low") == SeverityLevel.LOW
        assert _severity_to_enum("critical") == SeverityLevel.CRITICAL
        assert _severity_to_enum("info") == SeverityLevel.INFO

    def test_case_insensitive(self) -> None:
        """Severity mapping is case insensitive."""
        from token_audit.server.tools import _severity_to_enum

        assert _severity_to_enum("HIGH") == SeverityLevel.HIGH
        assert _severity_to_enum("High") == SeverityLevel.HIGH
        assert _severity_to_enum("MEDIUM") == SeverityLevel.MEDIUM

    def test_unknown_defaults_to_medium(self) -> None:
        """Unknown severity defaults to MEDIUM."""
        from token_audit.server.tools import _severity_to_enum

        assert _severity_to_enum("unknown") == SeverityLevel.MEDIUM
        assert _severity_to_enum("") == SeverityLevel.MEDIUM


class TestCachedLoader:
    """Tests for the cached loader singleton."""

    def test_loader_is_cached(self) -> None:
        """Loader is cached as singleton."""
        from token_audit.server.tools import _get_best_practices_loader

        loader1 = _get_best_practices_loader()
        loader2 = _get_best_practices_loader()
        assert loader1 is loader2

    def test_loader_returns_same_practices(self) -> None:
        """Multiple calls return same cached practices."""
        result1 = get_best_practices(list_all=True)
        result2 = get_best_practices(list_all=True)

        assert len(result1.practices) == len(result2.practices)
        assert result1.total_available == result2.total_available
