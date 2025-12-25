"""
Tests for JSON Schema validation (task-107.6).

Tests the token-audit validate command and schema correctness.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Schema file path
SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "schema" / "session-v1.7.0.json"


@pytest.fixture
def schema():
    """Load the JSON Schema."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def valid_minimal_session():
    """Minimal valid session matching v1.7.0 schema."""
    return {
        "_file": {
            "name": "test-session.json",
            "type": "token_audit_session",
            "schema_version": "1.7.0",
            "generated_by": "token-audit test",
            "generated_at": "2025-12-14T00:00:00+11:00",
        },
        "session": {
            "id": "test-session-001",
            "platform": "claude-code",
            "project": "test-project",
            "started_at": "2025-12-14T00:00:00+11:00",
        },
        "token_usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        },
        "cost_estimate_usd": 0.01,
    }


@pytest.fixture
def valid_full_session():
    """Full session with all optional fields populated."""
    return {
        "_file": {
            "name": "test-full-session.json",
            "type": "token_audit_session",
            "purpose": "Test session with all fields",
            "schema_version": "1.7.0",
            "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
            "generated_by": "token-audit v0.8.0",
            "generated_at": "2025-12-14T10:00:00+11:00",
        },
        "session": {
            "id": "test-full-session-001",
            "project": "token-audit",
            "platform": "claude-code",
            "model": "claude-sonnet-4-20250514",
            "models_used": ["claude-sonnet-4-20250514"],
            "working_directory": "/Users/test/projects/token-audit/main",
            "started_at": "2025-12-14T10:00:00+11:00",
            "ended_at": "2025-12-14T10:30:00+11:00",
            "duration_seconds": 1800.0,
            "source_files": ["session-abc123.jsonl"],
            "message_count": 25,
        },
        "token_usage": {
            "input_tokens": 50000,
            "output_tokens": 15000,
            "reasoning_tokens": 0,
            "cache_created_tokens": 2000,
            "cache_read_tokens": 100000,
            "total_tokens": 167000,
            "cache_efficiency": 0.85,
        },
        "cost_estimate_usd": 1.23,
        "model_usage": {
            "claude-sonnet-4-20250514": {
                "input_tokens": 50000,
                "output_tokens": 15000,
                "cache_created_tokens": 2000,
                "cache_read_tokens": 100000,
                "total_tokens": 167000,
                "cost_usd": 1.23,
                "call_count": 15,
            }
        },
        "mcp_summary": {
            "total_calls": 5,
            "unique_tools": 3,
            "unique_servers": 2,
            "servers_used": ["zen", "backlog"],
            "top_by_tokens": [
                {"tool": "mcp__zen__chat", "server": "zen", "tokens": 100000, "calls": 3}
            ],
            "top_by_calls": [
                {"tool": "mcp__zen__chat", "server": "zen", "calls": 3, "tokens": 100000}
            ],
        },
        "tool_calls": [
            {
                "index": 1,
                "timestamp": "2025-12-14T10:05:00+11:00",
                "tool": "mcp__backlog__task_list",
                "server": "backlog",
                "model": "claude-sonnet-4-20250514",
                "input_tokens": 100,
                "output_tokens": 500,
                "total_tokens": 600,
                "duration_ms": 1200,
                "content_hash": "abc123def456",
            }
        ],
        "smells": [
            {
                "pattern": "CHATTY",
                "severity": "warning",
                "tool": "Read",
                "description": "Called 25 times",
                "evidence": {"call_count": 25, "threshold": 20},
            }
        ],
        "recommendations": [
            {
                "type": "BATCH_OPERATIONS",
                "confidence": 0.9,
                "evidence": "Tool 'Read' called 25 times",
                "action": "Batch multiple Read calls",
                "impact": "Reduce from 25 to ~5 calls",
                "source_smell": "CHATTY",
                "details": {"tool": "Read", "call_count": 25},
            }
        ],
        "zombie_tools": {"zen": ["mcp__zen__refactor"]},
        "data_quality": {
            "accuracy_level": "exact",
            "token_source": "native",
            "confidence": 1.0,
            "pricing_source": "api",
            "pricing_freshness": "fresh",
        },
        "static_cost": {
            "total_tokens": 5000,
            "source": "known_db",
            "by_server": {"zen": 3000, "backlog": 2000},
            "confidence": 0.9,
        },
    }


class TestSchemaFileExists:
    """Test that schema file exists and is valid JSON."""

    def test_schema_file_exists(self):
        """Schema file exists at expected location."""
        assert SCHEMA_PATH.exists(), f"Schema file not found at {SCHEMA_PATH}"

    def test_schema_is_valid_json(self, schema):
        """Schema file is valid JSON."""
        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema

    def test_schema_version(self, schema):
        """Schema has correct version info."""
        assert schema.get("title") == "Token Audit Session Schema v1.7.0"


class TestSchemaValidation:
    """Test schema validation against session data."""

    def test_valid_minimal_session(self, schema, valid_minimal_session):
        """Minimal valid session passes validation."""
        import jsonschema

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_minimal_session))
        assert len(errors) == 0, f"Validation errors: {[e.message for e in errors]}"

    def test_valid_full_session(self, schema, valid_full_session):
        """Full session with all fields passes validation."""
        import jsonschema

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(valid_full_session))
        assert len(errors) == 0, f"Validation errors: {[e.message for e in errors]}"

    def test_missing_required_file_header(self, schema):
        """Missing _file header fails validation."""
        import jsonschema

        invalid_session = {
            "session": {
                "id": "x",
                "platform": "claude-code",
                "project": "x",
                "started_at": "2025-12-14T00:00:00Z",
            },
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "cost_estimate_usd": 0.0,
        }

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(invalid_session))
        assert len(errors) > 0
        assert any("_file" in str(e.message) for e in errors)

    def test_missing_required_session(self, schema):
        """Missing session block fails validation."""
        import jsonschema

        invalid_session = {
            "_file": {
                "name": "x.json",
                "type": "token_audit_session",
                "schema_version": "1.7.0",
                "generated_by": "test",
                "generated_at": "2025-12-14T00:00:00Z",
            },
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "cost_estimate_usd": 0.0,
        }

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(invalid_session))
        assert len(errors) > 0
        assert any("session" in str(e.message) for e in errors)

    def test_invalid_platform(self, schema, valid_minimal_session):
        """Invalid platform enum value fails validation."""
        import jsonschema

        invalid_session = valid_minimal_session.copy()
        invalid_session["session"] = valid_minimal_session["session"].copy()
        invalid_session["session"]["platform"] = "invalid-platform"

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(invalid_session))
        assert len(errors) > 0
        assert any("platform" in str(e.absolute_path) for e in errors)

    def test_invalid_smell_pattern(self, schema, valid_minimal_session):
        """Invalid smell pattern enum fails validation."""
        import jsonschema

        invalid_session = valid_minimal_session.copy()
        invalid_session["smells"] = [
            {
                "pattern": "INVALID_PATTERN",
                "severity": "warning",
                "description": "Test",
            }
        ]

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(invalid_session))
        assert len(errors) > 0

    def test_negative_tokens_fails(self, schema, valid_minimal_session):
        """Negative token count fails validation."""
        import jsonschema

        invalid_session = valid_minimal_session.copy()
        invalid_session["token_usage"] = {
            "input_tokens": -100,  # Invalid!
            "output_tokens": 50,
            "total_tokens": 150,
        }

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(invalid_session))
        assert len(errors) > 0


class TestValidateCLI:
    """Test the token-audit validate CLI command."""

    def test_validate_schema_only(self):
        """--schema-only prints schema path."""
        result = subprocess.run(
            [sys.executable, "-m", "token_audit.cli", "validate", "--schema-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
        assert "Schema file:" in result.stdout
        assert "1.7.0" in result.stdout

    def test_validate_missing_file(self, tmp_path):
        """Validate non-existent file returns error."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "token_audit.cli",
                "validate",
                str(tmp_path / "nonexistent.json"),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()

    def test_validate_valid_session(self, tmp_path, valid_minimal_session):
        """Validate valid session file succeeds."""
        session_file = tmp_path / "valid_session.json"
        session_file.write_text(json.dumps(valid_minimal_session))

        result = subprocess.run(
            [sys.executable, "-m", "token_audit.cli", "validate", str(session_file)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 0
        assert "Valid" in result.stdout

    def test_validate_invalid_session(self, tmp_path):
        """Validate invalid session file fails."""
        invalid_session = {"not": "valid"}
        session_file = tmp_path / "invalid_session.json"
        session_file.write_text(json.dumps(invalid_session))

        result = subprocess.run(
            [sys.executable, "-m", "token_audit.cli", "validate", str(session_file)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert result.returncode == 1
        assert "Invalid" in result.stdout or "error" in result.stdout.lower()
