"""Integration tests for MCP server mode.

These tests spawn token-audit-server as a subprocess and communicate
via JSON-RPC over stdio to verify MCP protocol compliance.
"""

import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import pytest


# =============================================================================
# Constants
# =============================================================================

LATENCY_WARNING_THRESHOLD_MS = 100
SERVER_STARTUP_TIMEOUT = 5.0


# =============================================================================
# Helper Functions
# =============================================================================


def send_jsonrpc(
    proc: subprocess.Popen[bytes],
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    """
    Send a JSON-RPC request and return the response.

    Args:
        proc: Subprocess with stdin/stdout pipes
        method: JSON-RPC method name
        params: Optional parameters dict
        request_id: Request ID for matching responses

    Returns:
        Parsed JSON-RPC response dict
    """
    request: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
    }
    if params is not None:
        request["params"] = params

    # Send request
    request_bytes = json.dumps(request).encode() + b"\n"
    assert proc.stdin is not None
    proc.stdin.write(request_bytes)
    proc.stdin.flush()

    # Read response
    assert proc.stdout is not None
    response_line = proc.stdout.readline()
    if not response_line:
        raise RuntimeError("Server closed connection without response")

    return json.loads(response_line.decode())


def call_tool(
    proc: subprocess.Popen[bytes],
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    """
    Call an MCP tool and return the result.

    Args:
        proc: Subprocess with stdin/stdout pipes
        tool_name: Name of the tool to call
        arguments: Tool arguments
        request_id: Request ID

    Returns:
        Tool result dict
    """
    params: dict[str, Any] = {"name": tool_name}
    if arguments is not None:
        params["arguments"] = arguments

    return send_jsonrpc(proc, "tools/call", params, request_id)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_audit_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Create a temporary token-audit directory and set HOME to use it.

    This isolates tests from the user's real ~/.token-audit directory.
    """
    # Create the expected directory structure
    audit_dir = tmp_path / ".token-audit"
    audit_dir.mkdir()
    (audit_dir / "sessions").mkdir()
    (audit_dir / "sessions" / "active").mkdir()

    # Set HOME so token-audit uses our temp directory
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TOKEN_AUDIT_HOME", str(audit_dir))

    return audit_dir


@pytest.fixture
def server_process(
    temp_audit_dir: Path,
) -> subprocess.Popen[bytes]:
    """
    Spawn token-audit-server as a subprocess with stdio pipes.

    Yields the process and terminates it after the test.
    """
    # Use the current Python interpreter to ensure we're using the right env
    proc = subprocess.Popen(
        [sys.executable, "-m", "token_audit.server.main"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "HOME": str(temp_audit_dir.parent)},
    )

    # Give the server a moment to start
    time.sleep(0.1)

    # Check server is still running
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        raise RuntimeError(f"Server failed to start: {stderr}")

    yield proc

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()


# =============================================================================
# CLI Flag Tests
# =============================================================================


class TestServerCLI:
    """Tests for token-audit-server CLI flags."""

    def test_server_help(self) -> None:
        """Test --help flag prints usage and exits."""
        result = subprocess.run(
            [sys.executable, "-m", "token_audit.server.main", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "token-audit-server" in result.stdout
        assert "MCP server" in result.stdout
        assert "--help" in result.stdout
        assert "--version" in result.stdout

    def test_server_version(self) -> None:
        """Test --version flag prints version and exits."""
        result = subprocess.run(
            [sys.executable, "-m", "token_audit.server.main", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "token-audit" in result.stdout
        # Version should be a semver-like string
        parts = result.stdout.strip().split()
        assert len(parts) >= 2
        version = parts[-1]
        assert "." in version  # e.g., "0.9.1"


class TestServerStartup:
    """Tests for server startup and basic connectivity."""

    def test_server_starts(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test server process starts without immediate error."""
        # If we got here, the fixture succeeded
        assert server_process.poll() is None  # Still running

    def test_mcp_initialize(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test MCP initialize handshake succeeds."""
        response = send_jsonrpc(
            server_process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        )

        assert "result" in response
        result = response["result"]
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "token-audit"


class TestMCPTools:
    """Tests for MCP tool functionality via protocol."""

    def test_list_tools(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test tools/list returns expected tools."""
        # Initialize first
        send_jsonrpc(
            server_process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )

        # List tools
        response = send_jsonrpc(server_process, "tools/list", {}, request_id=2)

        assert "result" in response
        tools = response["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        # Verify expected tools are present
        expected_tools = {
            "start_tracking",
            "get_metrics",
            "get_recommendations",
            "analyze_session",
            "get_best_practices",
            "analyze_config",
            "get_pinned_servers",
            "get_trends",
        }
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    def test_start_tracking_via_mcp(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test start_tracking tool works via MCP protocol."""
        # Initialize
        send_jsonrpc(
            server_process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )

        # Call start_tracking
        response = call_tool(
            server_process,
            "start_tracking",
            {"platform": "claude_code", "project": "test-project"},
            request_id=2,
        )

        assert "result" in response
        result = response["result"]

        # The result should contain tool output
        assert "content" in result
        content = result["content"]
        assert len(content) > 0

        # Parse the text content (JSON string)
        text_content = content[0]
        assert text_content["type"] == "text"
        data = json.loads(text_content["text"])

        assert data["status"] == "active"
        assert data["session_id"] != ""
        assert data["platform"] == "claude_code"
        assert data["project"] == "test-project"

    def test_get_metrics_via_mcp(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test get_metrics tool works via MCP protocol."""
        # Initialize
        send_jsonrpc(
            server_process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )

        # Start tracking first
        call_tool(
            server_process,
            "start_tracking",
            {"platform": "claude_code"},
            request_id=2,
        )

        # Get metrics
        response = call_tool(
            server_process,
            "get_metrics",
            {"include_smells": True, "include_breakdown": True},
            request_id=3,
        )

        assert "result" in response
        result = response["result"]
        assert "content" in result

        text_content = result["content"][0]
        data = json.loads(text_content["text"])

        # Verify metrics structure
        assert "session_id" in data
        assert "tokens" in data
        assert "cost_usd" in data
        assert "rates" in data
        assert "cache" in data

    def test_get_metrics_latency(self, server_process: subprocess.Popen[bytes]) -> None:
        """Test get_metrics responds within acceptable latency (soft guideline)."""
        # Initialize
        send_jsonrpc(
            server_process,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )

        # Start tracking
        call_tool(
            server_process,
            "start_tracking",
            {"platform": "claude_code"},
            request_id=2,
        )

        # Measure latency
        start_time = time.perf_counter()
        call_tool(server_process, "get_metrics", {}, request_id=3)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Soft guideline: warn if > 100ms but don't fail
        if elapsed_ms > LATENCY_WARNING_THRESHOLD_MS:
            warnings.warn(
                f"get_metrics latency ({elapsed_ms:.1f}ms) exceeded {LATENCY_WARNING_THRESHOLD_MS}ms threshold",
                UserWarning,
                stacklevel=1,
            )

        # Hard limit: fail if > 5 seconds (something is clearly wrong)
        assert elapsed_ms < 5000, f"get_metrics took {elapsed_ms:.1f}ms (>5s)"


class TestExistingCLI:
    """Tests to verify existing CLI mode is unchanged."""

    def test_cli_mode_unchanged(self) -> None:
        """Test token-audit --version still works (CLI not broken)."""
        result = subprocess.run(
            [sys.executable, "-m", "token_audit.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "token-audit" in result.stdout

    def test_cli_help_unchanged(self) -> None:
        """Test token-audit --help still works."""
        result = subprocess.run(
            [sys.executable, "-m", "token_audit.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "collect" in result.stdout  # Existing subcommand
        assert "report" in result.stdout  # Existing subcommand
