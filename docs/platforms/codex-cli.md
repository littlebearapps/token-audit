# Codex CLI Platform

> **📖 See [Codex CLI Setup Guide](../codex-cli-setup.md) for complete documentation.**

## Overview

MCP Audit supports Codex CLI through native JSONL session file parsing.

**Session Location**: `~/.codex/sessions/YYYY/MM/DD/*.jsonl`

## Key Features

- **File-Based Tracking**: Parses native session files (no process wrapping needed)
- **Session Auto-Discovery**: Finds latest session automatically
- **Date Filtering**: Filter sessions by date range
- **Model Detection**: Supports GPT-5.1, GPT-5-Codex, o-series models

## Quick Start

```bash
# Start tracking
mcp-audit collect --platform codex_cli

# Batch process latest session
mcp-audit collect --platform codex_cli --batch --latest

# Process specific date range
mcp-audit collect --platform codex_cli --batch --since 2025-11-01
```

## Event Types Tracked

| Event Type | Description |
|------------|-------------|
| `session_meta` | Session metadata (ID, CWD, CLI version) |
| `turn_context` | Model selection and settings |
| `token_count` | Token usage per turn |
| `function_call` | MCP tool calls (filtered by `mcp__` prefix) |

## See Also

- [Complete Setup Guide](../codex-cli-setup.md)
- [Architecture](../architecture.md)
- [Pricing Configuration](../PRICING-CONFIGURATION.md)
