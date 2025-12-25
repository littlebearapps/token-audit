"""
Best Practices Loader - Parses markdown files with YAML frontmatter.

This module provides the BestPractice dataclass and BestPracticesLoader
for loading, searching, and filtering best practice patterns.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Regex pattern to match YAML frontmatter at the start of a file
# Matches: ---\n<yaml content>\n---\n
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Full markdown content with optional frontmatter.

    Returns:
        Tuple of (metadata dict, body content without frontmatter).
        If no frontmatter found, returns ({}, original content).
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content

    frontmatter_yaml = match.group(1)
    body = content[match.end() :]

    try:
        metadata = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, body


@dataclass
class BestPractice:
    """A single best practice pattern.

    Attributes:
        id: Unique identifier (e.g., "progressive_disclosure")
        title: Display title
        severity: Importance level ("high", "medium", "low")
        category: Classification ("efficiency", "security", "design", "operations")
        content: Full markdown body (without frontmatter)
        token_savings: Optional savings estimate (e.g., "98%", "40-60%")
        source: Optional source/reference
        related_smells: Smell patterns this practice addresses
        keywords: Search keywords
    """

    id: str
    title: str
    severity: str
    category: str
    content: str
    token_savings: Optional[str] = None
    source: Optional[str] = None
    related_smells: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict.

        Returns:
            Dictionary representation with only non-None optional fields.
        """
        result: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "content": self.content,
        }
        if self.token_savings:
            result["token_savings"] = self.token_savings
        if self.source:
            result["source"] = self.source
        if self.related_smells:
            result["related_smells"] = self.related_smells
        if self.keywords:
            result["keywords"] = self.keywords
        return result


# Severity ordering for sorting (high first)
SEVERITY_ORDER: Dict[str, int] = {"high": 0, "medium": 1, "low": 2}


@dataclass
class BestPracticesLoader:
    """Loads and searches best practice patterns from markdown files.

    The loader reads markdown files with YAML frontmatter from the content
    directory, parses them into BestPractice objects, and provides search
    and filter capabilities.

    Attributes:
        content_dir: Directory containing best practice markdown files.
                     Defaults to the best_practices/ subdirectory.
    """

    content_dir: Optional[Path] = None
    _cache: Optional[List[BestPractice]] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize content directory to default if not specified."""
        if self.content_dir is None:
            self.content_dir = Path(__file__).parent / "best_practices"

    def _load_file(self, path: Path) -> Optional[BestPractice]:
        """Load a single best practice from a markdown file.

        Args:
            path: Path to the markdown file.

        Returns:
            BestPractice object or None if file is malformed.
        """
        try:
            content = path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            # Use filename as fallback for id and title
            stem = path.stem

            return BestPractice(
                id=metadata.get("id", stem),
                title=metadata.get("title", stem.replace("_", " ").title()),
                severity=metadata.get("severity", "medium"),
                category=metadata.get("category", "general"),
                content=body.strip(),
                token_savings=metadata.get("token_savings"),
                source=metadata.get("source"),
                related_smells=metadata.get("related_smells", []),
                keywords=metadata.get("keywords", []),
            )
        except Exception:
            return None

    def load_all(self) -> List[BestPractice]:
        """Load all best practices from content directory.

        Results are cached after first load for performance.

        Returns:
            List of BestPractice objects sorted by severity (high first).
            Returns empty list if no content files found.
        """
        if self._cache is not None:
            return self._cache

        practices: List[BestPractice] = []

        if not self.content_dir or not self.content_dir.exists():
            return practices

        for md_file in self.content_dir.glob("*.md"):
            # Skip files starting with underscore (e.g., _index.md)
            if md_file.name.startswith("_"):
                continue

            practice = self._load_file(md_file)
            if practice is not None:
                practices.append(practice)

        # Sort by severity priority (high first)
        practices.sort(key=lambda p: SEVERITY_ORDER.get(p.severity, 99))

        self._cache = practices
        return practices

    def get_by_id(self, pattern_id: str) -> Optional[BestPractice]:
        """Get a specific pattern by ID.

        Args:
            pattern_id: The unique identifier of the pattern.

        Returns:
            The matching BestPractice or None if not found.
        """
        for practice in self.load_all():
            if practice.id == pattern_id:
                return practice
        return None

    def get_by_category(self, category: str) -> List[BestPractice]:
        """Filter practices by category.

        Args:
            category: Category to filter by (e.g., "efficiency", "security").
                      Case-insensitive.

        Returns:
            List of practices in the specified category.
        """
        category_lower = category.lower()
        return [p for p in self.load_all() if p.category.lower() == category_lower]

    def get_by_smell(self, smell_pattern: str) -> List[BestPractice]:
        """Find practices that address a specific smell pattern.

        Args:
            smell_pattern: Smell pattern identifier (e.g., "LOW_CACHE_HIT").
                           Case-insensitive.

        Returns:
            List of practices that address the specified smell.
        """
        smell_upper = smell_pattern.upper()
        return [p for p in self.load_all() if smell_upper in [s.upper() for s in p.related_smells]]

    def search(self, query: str) -> List[BestPractice]:
        """Search across id, title, keywords, category, and related_smells.

        Performs case-insensitive substring matching.

        Args:
            query: Search term to match.

        Returns:
            List of practices matching the query.
        """
        query_lower = query.lower()
        results: List[BestPractice] = []

        for practice in self.load_all():
            # Build list of all searchable fields
            searchable = [
                practice.id,
                practice.title,
                practice.category,
                *practice.keywords,
                *practice.related_smells,
            ]

            # Check if query matches any field
            if any(query_lower in field.lower() for field in searchable):
                results.append(practice)

        return results
