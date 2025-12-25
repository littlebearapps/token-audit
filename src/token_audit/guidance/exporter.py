"""
Best Practices Exporter - Multi-format export for AI consumption.

This module provides the BestPracticesExporter class for converting
best practices to JSON, YAML, and Markdown formats.
"""

import json
from dataclasses import dataclass
from typing import List

import yaml

from .loader import BestPractice


@dataclass
class BestPracticesExporter:
    """Exports best practices to various formats for AI consumption.

    Supports JSON, YAML, and combined Markdown formats suitable for
    AGENTS.md-style documentation or programmatic access.
    """

    def to_json(self, practices: List[BestPractice], indent: int = 2) -> str:
        """Export to JSON format.

        Args:
            practices: List of best practices to export.
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        return json.dumps(
            [p.to_dict() for p in practices],
            indent=indent,
            ensure_ascii=False,
        )

    def to_yaml(self, practices: List[BestPractice]) -> str:
        """Export to YAML format for config-like contexts.

        Args:
            practices: List of best practices to export.

        Returns:
            YAML string representation with practices wrapper.
        """
        data = {"practices": [p.to_dict() for p in practices]}
        result: str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return result

    def to_markdown(self, practices: List[BestPractice]) -> str:
        """Export to combined markdown for AGENTS.md-style usage.

        Creates a single markdown document with all practices, each
        formatted with a header, metadata summary, and full content.

        Args:
            practices: List of best practices to export.

        Returns:
            Markdown document with all practices, or empty string if none.
        """
        if not practices:
            return ""

        sections: List[str] = ["# MCP Best Practices\n"]

        for practice in practices:
            # Header with title
            header = f"## {practice.title}\n\n"

            # Metadata summary
            metadata_lines = [
                f"- **Severity**: {practice.severity}",
                f"- **Category**: {practice.category}",
            ]
            if practice.token_savings:
                metadata_lines.append(f"- **Token Savings**: {practice.token_savings}")
            if practice.source:
                metadata_lines.append(f"- **Source**: {practice.source}")
            if practice.related_smells:
                metadata_lines.append(f"- **Addresses**: {', '.join(practice.related_smells)}")

            metadata = "\n".join(metadata_lines) + "\n\n"

            # Combine header, metadata, content, and separator
            sections.append(header + metadata + practice.content + "\n\n---\n\n")

        return "".join(sections).strip()
