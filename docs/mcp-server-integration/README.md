# MCP Server Integration Guides

This directory contains guides for integrating token-audit as an **MCP server** into your AI coding assistant.

---

## What is MCP Server Mode?

Token Audit v1.0 introduces **MCP server mode** — run token-audit as an MCP server that your AI assistant connects to, enabling:

- **Real-time session monitoring** from within your AI sessions
- **On-demand efficiency analysis** without switching terminals
- **Best practices guidance** accessible via natural language
- **Configuration analysis** to find issues in your MCP setup

---

## Platform Guides

| Platform | Guide | Config Format |
|----------|-------|---------------|
| **Claude Code** | [claude-code.md](./claude-code.md) | JSON (`.mcp.json`) |
| **Codex CLI** | [codex-cli.md](./codex-cli.md) | TOML (`config.toml`) |
| **Gemini CLI** | [gemini-cli.md](./gemini-cli.md) | JSON (`settings.json`) |

---

## Quick Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| Config File | `.mcp.json` (project) | `~/.codex/config.toml` | `~/.gemini/settings.json` |
| Config Format | JSON | TOML | JSON |
| MCP Section | `mcpServers` | `[mcp_servers.*]` | `mcpServers` |
| Transport | stdio | stdio | stdio |

---

## Available Tools (All Platforms)

The token-audit MCP server provides **8 tools** for efficiency monitoring and optimization:

| Tool | Purpose |
|------|---------|
| `start_tracking` | Begin live session tracking |
| `get_metrics` | Query current session statistics |
| `get_recommendations` | Get optimization recommendations |
| `analyze_session` | Comprehensive end-of-session analysis |
| `get_best_practices` | Retrieve MCP best practices guidance |
| `analyze_config` | Analyze MCP configuration files for issues |
| `get_pinned_servers` | Get user's pinned MCP servers |
| `get_trends` | Cross-session pattern analysis |

---

## MCP Server Mode vs CLI Mode

token-audit supports two complementary modes:

| Mode | Command | Use Case |
|------|---------|----------|
| **MCP Server** | `token-audit-server` | Real-time monitoring from within AI sessions |
| **CLI** | `token-audit collect` | External monitoring in a separate terminal |

**MCP Server mode** is ideal when you want to:
- Ask your AI assistant about token usage during a session
- Get recommendations without leaving your workflow
- Learn best practices through natural conversation

**CLI mode** is ideal when you want to:
- Track sessions in a dedicated terminal with TUI
- Monitor multiple sessions simultaneously
- Generate reports after sessions complete

---

## See Also

- [MCP Server Guide](../mcp-server-guide.md) — Full tool reference with schemas
- [Getting Started](../getting-started.md) — Installation and first session
- [Platform Guides](../platforms/) — CLI monitoring guides
