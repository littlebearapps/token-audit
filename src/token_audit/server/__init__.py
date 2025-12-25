"""
MCP Server mode for token-audit.

This module provides an MCP (Model Context Protocol) server that enables
AI agents to query token-audit metrics programmatically during sessions.

Usage:
    # CLI entry point
    token-audit-server

    # Programmatic usage
    from token_audit.server import create_server, run_server

    # Create a server instance
    server = create_server()

    # Run with stdio transport
    run_server()

Note:
    Requires the [server] optional dependency:
    pip install token-audit[server]
"""

from .main import create_server, get_server, run_server

__all__ = [
    "create_server",
    "get_server",
    "run_server",
]
