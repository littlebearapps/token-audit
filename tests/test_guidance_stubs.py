"""Tests for guidance module structure (task-191).

These tests verify the foundation structure is in place with working stubs.
"""

import pytest


class TestGuidanceImports:
    """Tests for guidance module imports."""

    def test_can_import_module(self) -> None:
        """Verify guidance module is importable."""
        from token_audit import guidance

        assert guidance is not None

    def test_can_import_best_practice(self) -> None:
        """Verify BestPractice is importable."""
        from token_audit.guidance import BestPractice

        assert BestPractice is not None

    def test_can_import_loader(self) -> None:
        """Verify BestPracticesLoader is importable."""
        from token_audit.guidance import BestPracticesLoader

        assert BestPracticesLoader is not None

    def test_can_import_exporter(self) -> None:
        """Verify BestPracticesExporter is importable."""
        from token_audit.guidance import BestPracticesExporter

        assert BestPracticesExporter is not None


class TestBestPracticeDataclass:
    """Tests for BestPractice dataclass."""

    def test_create_minimal(self) -> None:
        """Create BestPractice with required fields only."""
        from token_audit.guidance import BestPractice

        practice = BestPractice(
            id="test",
            title="Test Practice",
            severity="medium",
            category="general",
            content="# Test\nContent here.",
        )
        assert practice.id == "test"
        assert practice.title == "Test Practice"
        assert practice.severity == "medium"
        assert practice.category == "general"
        assert practice.content == "# Test\nContent here."
        assert practice.token_savings is None
        assert practice.source is None
        assert practice.related_smells == []
        assert practice.keywords == []

    def test_create_full(self) -> None:
        """Create BestPractice with all fields."""
        from token_audit.guidance import BestPractice

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
        assert practice.token_savings == "50%"
        assert practice.source == "Anthropic Blog"
        assert practice.related_smells == ["CHATTY", "TOP_CONSUMER"]
        assert practice.keywords == ["batching", "optimization"]

    def test_to_dict_minimal(self) -> None:
        """to_dict excludes None optional fields."""
        from token_audit.guidance import BestPractice

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
        from token_audit.guidance import BestPractice

        practice = BestPractice(
            id="full",
            title="Full",
            severity="high",
            category="efficiency",
            content="Content",
            token_savings="90%",
            source="Test Source",
            related_smells=["SMELL_A"],
            keywords=["keyword1"],
        )
        result = practice.to_dict()
        assert result["token_savings"] == "90%"
        assert result["source"] == "Test Source"
        assert result["related_smells"] == ["SMELL_A"]
        assert result["keywords"] == ["keyword1"]


class TestBestPracticesLoaderStub:
    """Tests for BestPracticesLoader with empty directory."""

    def test_load_all_returns_empty_with_nonexistent_dir(self) -> None:
        """Loader should return empty list when content dir doesn't exist."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader(content_dir=Path("/nonexistent/path"))
        result = loader.load_all()
        assert result == []
        assert isinstance(result, list)

    def test_get_by_id_returns_none_with_nonexistent_dir(self) -> None:
        """get_by_id should return None when content dir doesn't exist."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader(content_dir=Path("/nonexistent/path"))
        result = loader.get_by_id("any_id")
        assert result is None

    def test_get_by_category_returns_empty_with_nonexistent_dir(self) -> None:
        """get_by_category should return empty list when dir doesn't exist."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader(content_dir=Path("/nonexistent/path"))
        result = loader.get_by_category("efficiency")
        assert result == []

    def test_get_by_smell_returns_empty_with_nonexistent_dir(self) -> None:
        """get_by_smell should return empty list when dir doesn't exist."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader(content_dir=Path("/nonexistent/path"))
        result = loader.get_by_smell("LOW_CACHE_HIT")
        assert result == []

    def test_search_returns_empty_with_nonexistent_dir(self) -> None:
        """search should return empty list when dir doesn't exist."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader(content_dir=Path("/nonexistent/path"))
        result = loader.search("any query")
        assert result == []

    def test_default_content_dir(self) -> None:
        """Loader should set default content directory."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        loader = BestPracticesLoader()
        assert loader.content_dir is not None
        assert loader.content_dir.name == "best_practices"

    def test_custom_content_dir(self) -> None:
        """Loader should accept custom content directory."""
        from pathlib import Path

        from token_audit.guidance import BestPracticesLoader

        custom_dir = Path("/tmp/custom_practices")
        loader = BestPracticesLoader(content_dir=custom_dir)
        assert loader.content_dir == custom_dir


class TestBestPracticesExporterStub:
    """Tests for BestPracticesExporter stub."""

    def test_to_json_returns_empty_array(self) -> None:
        """to_json stub should return empty JSON array."""
        from token_audit.guidance import BestPracticesExporter

        exporter = BestPracticesExporter()
        result = exporter.to_json([])
        assert result == "[]"

    def test_to_yaml_returns_empty_practices(self) -> None:
        """to_yaml stub should return empty practices."""
        from token_audit.guidance import BestPracticesExporter

        exporter = BestPracticesExporter()
        result = exporter.to_yaml([])
        assert "practices" in result

    def test_to_markdown_returns_empty_string(self) -> None:
        """to_markdown stub should return empty string."""
        from token_audit.guidance import BestPracticesExporter

        exporter = BestPracticesExporter()
        result = exporter.to_markdown([])
        assert result == ""
