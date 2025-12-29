#!/usr/bin/env python3
"""
Tests for CLI historical commands (v1.0.0 - task-226.7).

Tests cover:
- token-audit daily command
- token-audit weekly command
- token-audit monthly command
- --json output format
- --instances flag (project grouping)
- --breakdown flag (model detail)
- --platform filter
"""

import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest


def run_token_audit(*args: str, storage_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Run token-audit CLI command via subprocess.

    Args:
        *args: CLI arguments to pass to token-audit
        storage_dir: Optional storage directory override

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    env = None
    if storage_dir:
        import os

        env = os.environ.copy()
        env["TOKEN_AUDIT_STORAGE_DIR"] = str(storage_dir)

    return subprocess.run(
        [sys.executable, "-m", "token_audit.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def create_test_session_file(
    storage_dir: Path,
    platform: str,
    session_date: date,
    session_id: str,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cost_estimate: float = 0.01,
    working_directory: str = "/test/project",
    model: str = "claude-sonnet-4",
) -> Path:
    """Create a test session file in storage.

    Args:
        storage_dir: Base storage directory
        platform: Platform name (claude_code, codex_cli, gemini_cli)
        session_date: Date for the session
        session_id: Unique session ID
        input_tokens: Input token count
        output_tokens: Output token count
        cost_estimate: Cost in USD
        working_directory: Working directory path
        model: Model name

    Returns:
        Path to created session file
    """
    date_str = session_date.strftime("%Y-%m-%d")
    # Convert underscore to hyphen for directory name
    platform_dir_name = platform.replace("_", "-")
    date_dir = storage_dir / platform_dir_name / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    session_file = date_dir / f"session-{session_id}.json"

    session_data = {
        "_file": {
            "schema_version": "1.7.0",
            "session_id": session_id,
            "started_at": f"{date_str}T10:00:00Z",
            "ended_at": f"{date_str}T11:00:00Z",
            "project": "test-project",
            "total_tokens": input_tokens + output_tokens,
            "total_cost": cost_estimate,
            "tool_count": 5,
            "server_count": 2,
        },
        "session": {
            "id": session_id,
            "project": "test-project",
            "platform": platform,
            "model": model,
            "working_directory": working_directory,
            "started_at": f"{date_str}T10:00:00Z",
            "ended_at": f"{date_str}T11:00:00Z",
            "duration_seconds": 3600,
            "source_files": [],
            "message_count": 10,
            "models_used": [model],
        },
        "token_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_created_tokens": 100,
            "cache_read_tokens": 200,
            "reasoning_tokens": 0,
            "total_tokens": input_tokens + output_tokens + 300,
            "cache_efficiency": 0.2,
        },
        "cost_estimate": cost_estimate,
        "cost_no_cache_usd": cost_estimate * 1.5,
        "cache_savings_usd": cost_estimate * 0.5,
        "mcp_summary": {
            "total_calls": 10,
            "unique_tools": 5,
            "unique_servers": 2,
            "servers_used": [],
            "top_by_tokens": [],
            "top_by_calls": [],
        },
        "builtin_tool_summary": {"total_calls": 5, "total_tokens": 500, "tools": []},
        "cache_analysis": {
            "status": "efficient",
            "summary": "Good cache usage",
            "creation_tokens": 100,
            "read_tokens": 200,
            "ratio": 2.0,
            "net_savings_usd": 0.005,
            "top_cache_creators": [],
            "top_cache_readers": [],
            "recommendation": "",
        },
        "tool_calls": [],
        "smells": [],
        "recommendations": [],
        "zombie_tools": {},
        "analysis": {"redundancy": None, "anomalies": []},
        "model_usage": {
            model: {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_created_tokens": 100,
                "cache_read_tokens": 200,
                "total_tokens": input_tokens + output_tokens + 300,
                "cost_usd": cost_estimate,
                "call_count": 10,
            }
        },
        "tool_sequence": [],
        "server_sessions": {},
    }

    session_file.write_text(json.dumps(session_data, indent=2))
    return session_file


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def populated_storage(temp_storage_dir) -> Path:
    """Create a storage directory with test session files across multiple days.

    Creates sessions for the past 10 days across different platforms and models.
    """
    today = date.today()

    # Create sessions for past 10 days
    for days_ago in range(10):
        session_date = today - timedelta(days=days_ago)

        # Claude Code session
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            session_date,
            f"claude-{days_ago}",
            input_tokens=1000 + days_ago * 100,
            output_tokens=500 + days_ago * 50,
            cost_estimate=0.01 + days_ago * 0.001,
            working_directory="/project/alpha",
            model="claude-sonnet-4",
        )

        # Additional Claude session with different model
        create_test_session_file(
            temp_storage_dir,
            "claude_code",
            session_date,
            f"claude-opus-{days_ago}",
            input_tokens=2000 + days_ago * 200,
            output_tokens=1000 + days_ago * 100,
            cost_estimate=0.05 + days_ago * 0.005,
            working_directory="/project/beta",
            model="claude-opus-4",
        )

        # Codex CLI session (every other day)
        if days_ago % 2 == 0:
            create_test_session_file(
                temp_storage_dir,
                "codex_cli",
                session_date,
                f"codex-{days_ago}",
                input_tokens=800 + days_ago * 80,
                output_tokens=400 + days_ago * 40,
                cost_estimate=0.008 + days_ago * 0.0008,
                working_directory="/project/gamma",
                model="gpt-4.1",
            )

    return temp_storage_dir


# ============================================================================
# Daily Command Tests
# ============================================================================


class TestDailyCommand:
    """Tests for 'token-audit daily' command."""

    def test_daily_help(self) -> None:
        """Test --help shows expected options."""
        result = run_token_audit("daily", "--help")
        assert result.returncode == 0
        assert "--days" in result.stdout
        assert "--platform" in result.stdout
        assert "--json" in result.stdout
        assert "--instances" in result.stdout
        assert "--breakdown" in result.stdout

    def test_daily_json_empty_storage(self, temp_storage_dir) -> None:
        """Test --json with no session data returns empty list."""
        result = run_token_audit("daily", "--json", storage_dir=temp_storage_dir)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_daily_json_valid_structure(self, populated_storage) -> None:
        """Test --json outputs valid JSON with expected structure."""
        result = run_token_audit("daily", "--json", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) > 0

        # Check first entry structure
        day = data[0]
        assert "date" in day
        assert "session_count" in day
        assert "input_tokens" in day
        assert "output_tokens" in day
        assert "total_tokens" in day
        assert "cost_usd" in day

    def test_daily_days_option(self, populated_storage) -> None:
        """Test --days limits results to specified date range."""
        result = run_token_audit("daily", "--days", "3", "--json", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # With 2 platforms, we could have up to 6 records (3 days × 2 platforms)
        # Verify unique dates are <= 3
        unique_dates = set(d["date"] for d in data)
        assert len(unique_dates) <= 3

    def test_daily_platform_filter(self, populated_storage) -> None:
        """Test --platform filters to specific platform."""
        result = run_token_audit(
            "daily", "--platform", "codex-cli", "--json", storage_dir=populated_storage
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        # All entries should be for codex_cli
        for day in data:
            assert day.get("platform") == "codex_cli"

    def test_daily_breakdown_includes_models(self, populated_storage) -> None:
        """Test --breakdown includes model_breakdowns in output."""
        result = run_token_audit("daily", "--json", "--breakdown", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)

        # At least one day should have model breakdowns
        days_with_breakdowns = [d for d in data if "model_breakdowns" in d]
        assert len(days_with_breakdowns) > 0

    def test_daily_instances_includes_projects(self, populated_storage) -> None:
        """Test --instances includes project_breakdowns in output."""
        result = run_token_audit("daily", "--json", "--instances", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)

        # At least one day should have project breakdowns
        days_with_projects = [d for d in data if "project_breakdowns" in d]
        assert len(days_with_projects) > 0


# ============================================================================
# Weekly Command Tests
# ============================================================================


class TestWeeklyCommand:
    """Tests for 'token-audit weekly' command."""

    def test_weekly_help(self) -> None:
        """Test --help shows expected options."""
        result = run_token_audit("weekly", "--help")
        assert result.returncode == 0
        assert "--weeks" in result.stdout
        assert "--start-of-week" in result.stdout
        assert "--platform" in result.stdout
        assert "--json" in result.stdout

    def test_weekly_json_empty_storage(self, temp_storage_dir) -> None:
        """Test --json with no session data returns empty list."""
        result = run_token_audit("weekly", "--json", storage_dir=temp_storage_dir)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_weekly_json_valid_structure(self, populated_storage) -> None:
        """Test --json outputs valid JSON with expected structure."""
        result = run_token_audit("weekly", "--json", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

        if len(data) > 0:
            week = data[0]
            assert "week_start" in week
            assert "week_end" in week
            assert "session_count" in week
            assert "total_tokens" in week
            assert "cost_usd" in week

    def test_weekly_weeks_option(self, populated_storage) -> None:
        """Test --weeks limits results to specified date range."""
        result = run_token_audit("weekly", "--weeks", "2", "--json", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # With 2 platforms, we could have up to 6 records (3 weeks × 2 platforms)
        # Note: 2 weeks of data can span 3 calendar weeks at week boundaries
        # (e.g., partial current week + 2 full weeks back)
        unique_weeks = set(d["week_start"] for d in data)
        assert len(unique_weeks) <= 3

    def test_weekly_start_of_week_monday(self, populated_storage) -> None:
        """Test --start-of-week monday uses Monday as week start."""
        result = run_token_audit(
            "weekly", "--start-of-week", "monday", "--json", storage_dir=populated_storage
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        # Verify week_start dates are Mondays
        from datetime import datetime

        for week in data:
            start_date = datetime.strptime(week["week_start"], "%Y-%m-%d")
            assert start_date.weekday() == 0  # Monday = 0

    def test_weekly_start_of_week_sunday(self, populated_storage) -> None:
        """Test --start-of-week sunday uses Sunday as week start."""
        result = run_token_audit(
            "weekly", "--start-of-week", "sunday", "--json", storage_dir=populated_storage
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)

        # Verify week_start dates are Sundays
        from datetime import datetime

        for week in data:
            start_date = datetime.strptime(week["week_start"], "%Y-%m-%d")
            assert start_date.weekday() == 6  # Sunday = 6


# ============================================================================
# Monthly Command Tests
# ============================================================================


class TestMonthlyCommand:
    """Tests for 'token-audit monthly' command."""

    def test_monthly_help(self) -> None:
        """Test --help shows expected options."""
        result = run_token_audit("monthly", "--help")
        assert result.returncode == 0
        assert "--months" in result.stdout
        assert "--platform" in result.stdout
        assert "--json" in result.stdout

    def test_monthly_json_empty_storage(self, temp_storage_dir) -> None:
        """Test --json with no session data returns empty list."""
        result = run_token_audit("monthly", "--json", storage_dir=temp_storage_dir)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_monthly_json_valid_structure(self, populated_storage) -> None:
        """Test --json outputs valid JSON with expected structure."""
        result = run_token_audit("monthly", "--json", storage_dir=populated_storage)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

        if len(data) > 0:
            month = data[0]
            assert "year" in month
            assert "month" in month
            assert "session_count" in month
            assert "total_tokens" in month
            assert "cost_usd" in month

    def test_monthly_months_option(self, populated_storage) -> None:
        """Test --months limits results to specified date range."""
        result = run_token_audit(
            "monthly", "--months", "1", "--json", storage_dir=populated_storage
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # With 2 platforms, we could have up to 2 records (1 month × 2 platforms)
        # Verify unique months are <= 1
        unique_months = set((d["year"], d["month"]) for d in data)
        assert len(unique_months) <= 1


# ============================================================================
# Cross-Command Tests
# ============================================================================


class TestHistoricalCommandsCommon:
    """Tests for common behavior across all historical commands."""

    @pytest.mark.parametrize("command", ["daily", "weekly", "monthly"])
    def test_command_exists(self, command: str) -> None:
        """Test all historical commands are registered."""
        result = run_token_audit(command, "--help")
        assert result.returncode == 0

    @pytest.mark.parametrize("command", ["daily", "weekly", "monthly"])
    def test_json_output_is_valid(self, command: str, temp_storage_dir) -> None:
        """Test --json always produces valid JSON."""
        result = run_token_audit(command, "--json", storage_dir=temp_storage_dir)
        assert result.returncode == 0
        # Should not raise
        json.loads(result.stdout)

    @pytest.mark.parametrize(
        "command,flag",
        [
            ("daily", "--breakdown"),
            ("daily", "--instances"),
            ("weekly", "--breakdown"),
            ("weekly", "--instances"),
            ("monthly", "--breakdown"),
            ("monthly", "--instances"),
        ],
    )
    def test_flags_accepted(self, command: str, flag: str, temp_storage_dir) -> None:
        """Test --breakdown and --instances flags are accepted."""
        result = run_token_audit(command, flag, "--json", storage_dir=temp_storage_dir)
        assert result.returncode == 0

    @pytest.mark.parametrize(
        "command,platform",
        [
            ("daily", "claude-code"),
            ("daily", "codex-cli"),
            ("daily", "gemini-cli"),
            ("weekly", "claude-code"),
            ("monthly", "claude-code"),
        ],
    )
    def test_platform_filter_accepted(self, command: str, platform: str, temp_storage_dir) -> None:
        """Test --platform filter is accepted for valid platforms."""
        result = run_token_audit(
            command, "--platform", platform, "--json", storage_dir=temp_storage_dir
        )
        assert result.returncode == 0
