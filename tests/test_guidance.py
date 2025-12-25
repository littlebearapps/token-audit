"""Tests for guidance module full implementation (task-141).

Tests the BestPracticesLoader parsing, searching, and filtering,
as well as the BestPracticesExporter multi-format output.
"""

import json
from pathlib import Path

import pytest
import yaml

from token_audit.guidance import BestPractice, BestPracticesExporter, BestPracticesLoader


class TestBestPracticeDataclass:
    """Tests for BestPractice dataclass."""

    def test_to_dict_minimal(self) -> None:
        """to_dict excludes None optional fields."""
        practice = BestPractice(
            id="test",
            title="Test",
            severity="low",
            category="design",
            content="Content",
        )
        result = practice.to_dict()
        assert result == {
            "id": "test",
            "title": "Test",
            "severity": "low",
            "category": "design",
            "content": "Content",
        }
        assert "token_savings" not in result
        assert "source" not in result
        assert "related_smells" not in result
        assert "keywords" not in result

    def test_to_dict_full(self) -> None:
        """to_dict includes all non-None fields."""
        practice = BestPractice(
            id="full",
            title="Full Practice",
            severity="high",
            category="efficiency",
            content="Content",
            token_savings="50%",
            source="Anthropic Blog",
            related_smells=["CHATTY", "TOP_CONSUMER"],
            keywords=["batching", "optimization"],
        )
        result = practice.to_dict()
        assert result["token_savings"] == "50%"
        assert result["source"] == "Anthropic Blog"
        assert result["related_smells"] == ["CHATTY", "TOP_CONSUMER"]
        assert result["keywords"] == ["batching", "optimization"]


class TestBestPracticesLoader:
    """Tests for BestPracticesLoader with real content files."""

    def test_load_all_returns_list(self) -> None:
        """Load all should return a list of practices."""
        loader = BestPracticesLoader()
        practices = loader.load_all()
        assert isinstance(practices, list)
        # With 10 content files, should have 10 practices
        assert len(practices) == 10

    def test_load_all_sorted_by_severity(self) -> None:
        """Practices should be sorted high -> medium -> low."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        severities = [p.severity for p in practices]
        high_indices = [i for i, s in enumerate(severities) if s == "high"]
        medium_indices = [i for i, s in enumerate(severities) if s == "medium"]

        # All high severity should come before all medium severity
        if high_indices and medium_indices:
            assert max(high_indices) < min(medium_indices)

    def test_load_all_caches_results(self) -> None:
        """Results should be cached after first load."""
        loader = BestPracticesLoader()
        result1 = loader.load_all()
        result2 = loader.load_all()
        assert result1 is result2  # Same object reference

    def test_get_by_id_found(self) -> None:
        """Get by ID should return matching practice."""
        loader = BestPracticesLoader()
        practice = loader.get_by_id("progressive_disclosure")
        assert practice is not None
        assert practice.id == "progressive_disclosure"
        assert practice.severity == "high"

    def test_get_by_id_not_found(self) -> None:
        """Get by ID should return None for unknown ID."""
        loader = BestPracticesLoader()
        assert loader.get_by_id("nonexistent_id") is None

    def test_get_by_category_efficiency(self) -> None:
        """Filter by efficiency category."""
        loader = BestPracticesLoader()
        practices = loader.get_by_category("efficiency")
        assert (
            len(practices) >= 3
        )  # progressive_disclosure, caching_strategy, large_results, tool_count_limits
        assert all(p.category == "efficiency" for p in practices)

    def test_get_by_category_security(self) -> None:
        """Filter by security category."""
        loader = BestPracticesLoader()
        practices = loader.get_by_category("security")
        assert len(practices) == 1
        assert practices[0].id == "security"

    def test_get_by_category_case_insensitive(self) -> None:
        """Category filter should be case insensitive."""
        loader = BestPracticesLoader()
        upper = loader.get_by_category("EFFICIENCY")
        lower = loader.get_by_category("efficiency")
        assert len(upper) == len(lower)

    def test_get_by_smell(self) -> None:
        """Get by smell should find practices addressing that smell."""
        loader = BestPracticesLoader()
        practices = loader.get_by_smell("LOW_CACHE_HIT")
        assert len(practices) >= 1
        # caching_strategy addresses LOW_CACHE_HIT
        ids = [p.id for p in practices]
        assert "caching_strategy" in ids

    def test_get_by_smell_case_insensitive(self) -> None:
        """Smell filter should be case insensitive."""
        loader = BestPracticesLoader()
        upper = loader.get_by_smell("LOW_CACHE_HIT")
        lower = loader.get_by_smell("low_cache_hit")
        assert len(upper) == len(lower)

    def test_search_by_keyword(self) -> None:
        """Search should match keywords."""
        loader = BestPracticesLoader()
        results = loader.search("caching")
        assert len(results) >= 1
        ids = [p.id for p in results]
        assert "caching_strategy" in ids

    def test_search_by_id(self) -> None:
        """Search should match ID."""
        loader = BestPracticesLoader()
        results = loader.search("progressive")
        assert len(results) >= 1
        ids = [p.id for p in results]
        assert "progressive_disclosure" in ids

    def test_search_by_title(self) -> None:
        """Search should match title."""
        loader = BestPracticesLoader()
        results = loader.search("Security")
        assert len(results) >= 1
        ids = [p.id for p in results]
        assert "security" in ids

    def test_search_by_smell_pattern(self) -> None:
        """Search should match related_smells."""
        loader = BestPracticesLoader()
        results = loader.search("LARGE_PAYLOAD")
        assert len(results) >= 1
        ids = [p.id for p in results]
        assert "large_results" in ids

    def test_search_case_insensitive(self) -> None:
        """Search should be case insensitive."""
        loader = BestPracticesLoader()
        upper = loader.search("SECURITY")
        lower = loader.search("security")
        assert len(upper) == len(lower)

    def test_practice_has_content(self) -> None:
        """Each practice should have non-empty content."""
        loader = BestPracticesLoader()
        for practice in loader.load_all():
            assert practice.content, f"Practice {practice.id} has empty content"
            assert len(practice.content) > 100, f"Practice {practice.id} has very short content"

    def test_high_severity_practices(self) -> None:
        """Should have 4 high severity practices."""
        loader = BestPracticesLoader()
        high = [p for p in loader.load_all() if p.severity == "high"]
        assert len(high) == 4
        high_ids = {p.id for p in high}
        expected = {"progressive_disclosure", "security", "large_results", "tool_count_limits"}
        assert high_ids == expected


class TestBestPracticesExporter:
    """Tests for BestPracticesExporter."""

    @pytest.fixture
    def sample_practices(self) -> list[BestPractice]:
        return [
            BestPractice(
                id="test1",
                title="Test Practice 1",
                severity="high",
                category="efficiency",
                content="## Problem\nTest problem.\n\n## Solution\nTest solution.",
                token_savings="50%",
                related_smells=["CHATTY"],
                keywords=["testing", "sample"],
            ),
            BestPractice(
                id="test2",
                title="Test Practice 2",
                severity="low",
                category="security",
                content="Security content here.",
                source="Test Source",
            ),
        ]

    def test_to_json_produces_valid_json(self, sample_practices: list[BestPractice]) -> None:
        """to_json should produce valid JSON."""
        exporter = BestPracticesExporter()
        result = exporter.to_json(sample_practices)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["id"] == "test1"
        assert parsed[0]["token_savings"] == "50%"
        assert parsed[1]["id"] == "test2"

    def test_to_json_empty_list(self) -> None:
        """to_json with empty list should return empty array."""
        exporter = BestPracticesExporter()
        result = exporter.to_json([])
        assert result == "[]"

    def test_to_yaml_produces_valid_yaml(self, sample_practices: list[BestPractice]) -> None:
        """to_yaml should produce valid YAML."""
        exporter = BestPracticesExporter()
        result = exporter.to_yaml(sample_practices)
        parsed = yaml.safe_load(result)
        assert "practices" in parsed
        assert len(parsed["practices"]) == 2
        assert parsed["practices"][0]["id"] == "test1"

    def test_to_yaml_empty_list(self) -> None:
        """to_yaml with empty list should have empty practices."""
        exporter = BestPracticesExporter()
        result = exporter.to_yaml([])
        parsed = yaml.safe_load(result)
        assert parsed["practices"] == []

    def test_to_markdown_produces_valid_markdown(
        self, sample_practices: list[BestPractice]
    ) -> None:
        """to_markdown should produce formatted markdown."""
        exporter = BestPracticesExporter()
        result = exporter.to_markdown(sample_practices)

        assert "# MCP Best Practices" in result
        assert "## Test Practice 1" in result
        assert "## Test Practice 2" in result
        assert "**Severity**: high" in result
        assert "**Token Savings**: 50%" in result
        assert "**Addresses**: CHATTY" in result
        assert "**Source**: Test Source" in result
        assert "---" in result  # Separators

    def test_to_markdown_empty_list(self) -> None:
        """to_markdown with empty list should return empty string."""
        exporter = BestPracticesExporter()
        assert exporter.to_markdown([]) == ""

    def test_to_json_with_real_practices(self) -> None:
        """Export real practices to JSON."""
        loader = BestPracticesLoader()
        exporter = BestPracticesExporter()

        practices = loader.load_all()
        result = exporter.to_json(practices)

        parsed = json.loads(result)
        assert len(parsed) == 10
        # Check first practice (high severity, sorted first)
        assert parsed[0]["severity"] == "high"

    def test_to_markdown_with_real_practices(self) -> None:
        """Export real practices to markdown."""
        loader = BestPracticesLoader()
        exporter = BestPracticesExporter()

        practices = loader.load_all()
        result = exporter.to_markdown(practices)

        # Should include all 10 practice titles (top-level headings)
        assert "## Progressive Tool Disclosure" in result
        assert "## MCP Security Best Practices" in result
        assert "## Purpose-Specific Tool Design" in result
        assert "## Caching Strategy" in result
        # Content includes its own ## headings, so just check titles are present
        assert result.startswith("# MCP Best Practices")


class TestFrontmatterParsing:
    """Tests for YAML frontmatter parsing."""

    def test_parse_progressive_disclosure(self) -> None:
        """Progressive disclosure should have correct metadata."""
        loader = BestPracticesLoader()
        practice = loader.get_by_id("progressive_disclosure")

        assert practice is not None
        assert practice.title == "Progressive Tool Disclosure"
        assert practice.severity == "high"
        assert practice.category == "efficiency"
        assert practice.token_savings == "98%"
        assert practice.source == "Anthropic Engineering Blog"
        assert "UNDERUTILIZED_SERVER" in practice.related_smells
        assert "HIGH_MCP_SHARE" in practice.related_smells
        assert "context bloat" in practice.keywords

    def test_parse_security(self) -> None:
        """Security practice should have correct metadata."""
        loader = BestPracticesLoader()
        practice = loader.get_by_id("security")

        assert practice is not None
        assert practice.title == "MCP Security Best Practices"
        assert practice.severity == "high"
        assert practice.category == "security"
        assert practice.source == "Astrix Security Report 2025"

    def test_parse_caching_strategy(self) -> None:
        """Caching strategy should have correct related_smells."""
        loader = BestPracticesLoader()
        practice = loader.get_by_id("caching_strategy")

        assert practice is not None
        assert "LOW_CACHE_HIT" in practice.related_smells
        assert "CACHE_MISS_STREAK" in practice.related_smells
        assert "REDUNDANT_CALLS" in practice.related_smells


class TestContentFileIntegrity:
    """Tests for content file validation (task-144).

    These tests verify that all best practice content files have
    proper structure, valid metadata, and reference valid patterns.
    """

    # Valid categories as defined in BestPractice dataclass docs
    VALID_CATEGORIES = {"efficiency", "security", "design", "operations", "general"}

    # Valid severities as defined in loader defaults
    VALID_SEVERITIES = {"high", "medium", "low"}

    # All known smell patterns from smells.py (v1.5.0 + v1.7.0 + v1.0.0)
    VALID_SMELL_PATTERNS = {
        # v1.5.0 patterns
        "HIGH_VARIANCE",
        "TOP_CONSUMER",
        "HIGH_MCP_SHARE",
        "CHATTY",
        "LOW_CACHE_HIT",
        # v1.7.0 patterns
        "REDUNDANT_CALLS",
        "EXPENSIVE_FAILURES",
        "UNDERUTILIZED_SERVER",
        "BURST_PATTERN",
        "LARGE_PAYLOAD",
        "SEQUENTIAL_READS",
        "CACHE_MISS_STREAK",
        # v1.0.0 Security patterns
        "CREDENTIAL_EXPOSURE",
        "SUSPICIOUS_TOOL_DESCRIPTION",
        "UNUSUAL_DATA_FLOW",
    }

    def test_all_practices_have_required_fields(self) -> None:
        """Verify all practices have required frontmatter fields."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        assert len(practices) > 0, "No practices loaded"

        for practice in practices:
            assert practice.id, f"Practice missing id: {practice}"
            assert practice.title, f"Practice {practice.id} missing title"
            assert practice.severity, f"Practice {practice.id} missing severity"
            assert practice.category, f"Practice {practice.id} missing category"
            assert practice.content, f"Practice {practice.id} missing content"
            # Content should have meaningful length
            assert (
                len(practice.content) >= 100
            ), f"Practice {practice.id} has very short content ({len(practice.content)} chars)"

    def test_no_duplicate_practice_ids(self) -> None:
        """Verify no duplicate practice IDs exist."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        ids = [p.id for p in practices]
        unique_ids = set(ids)

        assert len(ids) == len(
            unique_ids
        ), f"Duplicate practice IDs found: {[id for id in ids if ids.count(id) > 1]}"

    def test_related_smells_are_valid_patterns(self) -> None:
        """Verify related_smells reference valid smell patterns."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        for practice in practices:
            for smell in practice.related_smells:
                assert smell in self.VALID_SMELL_PATTERNS, (
                    f"Practice {practice.id} references unknown smell: {smell}. "
                    f"Valid patterns: {self.VALID_SMELL_PATTERNS}"
                )

    def test_categories_are_valid(self) -> None:
        """Verify all practices use valid category values."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        for practice in practices:
            assert practice.category.lower() in self.VALID_CATEGORIES, (
                f"Practice {practice.id} has invalid category: {practice.category}. "
                f"Valid categories: {self.VALID_CATEGORIES}"
            )

    def test_severities_are_valid(self) -> None:
        """Verify all practices use valid severity values."""
        loader = BestPracticesLoader()
        practices = loader.load_all()

        for practice in practices:
            assert practice.severity.lower() in self.VALID_SEVERITIES, (
                f"Practice {practice.id} has invalid severity: {practice.severity}. "
                f"Valid severities: {self.VALID_SEVERITIES}"
            )
