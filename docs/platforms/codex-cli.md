# Codex CLI Platform Guide

This guide explains how to use Token Audit with [Codex CLI](https://github.com/openai/codex), OpenAI's AI coding assistant.

> **v1.0 Feature**: Want to use token-audit as an MCP server inside Codex CLI? See [MCP Server Integration: Codex CLI](../mcp-server-integration/codex-cli.md).

> **📖 See [Codex CLI Setup Guide](../codex-cli-setup.md) for detailed configuration options.**

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Token Accuracy** | Session: Native / Per-tool: Estimated (99%+) |
| **Per-tool Attribution** | Estimated via tiktoken `o200k_base` |
| **Cache Tracking** | Read only (cache creation not reported) |
| **Reasoning Tokens** | Yes — O-series models (o1, o3, o4-mini) |
| **Session Location** | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` |
| **Special Features** | Tool duration tracking, reasoning tokens |

---

## Prerequisites

- **Codex CLI** installed (`npm install -g @openai/codex`)
- **Python 3.8+** installed
- **MCP servers** configured in Codex (optional)

---

## Installation

```bash
pipx install token-audit
```

Or with pip:

```bash
pip install token-audit
```

---

## Quick Start

### 1. Start Tracking

Open a new terminal and run:

```bash
token-audit collect --platform codex-cli
```

### 2. Use Codex CLI Normally

In a separate terminal, start Codex:

```bash
codex
```

Work as usual. Token Audit will track:
- All model interactions (tokens used)
- All MCP tool calls (call counts)
- Cache efficiency (cache read tokens)

### 3. View Results

When done, press `Ctrl+C` to see the session summary, or generate a report:

```bash
token-audit report
```

---

## Platform Capabilities

Codex CLI provides **session-level token counts** with per-tool estimation:

| Capability | Status | Notes |
|------------|--------|-------|
| Session tokens | ✅ Native | Exact session totals from OpenAI |
| Per-tool tokens | ✅ Estimated (99%+) | Via tiktoken `o200k_base` |
| Reasoning tokens | ✅ o-series | Tracked separately for o1, o3 models |
| Cache tracking | ✅ Read only | Cache creation not reported by OpenAI |
| Cost estimates | ✅ Accurate | Based on session totals + model pricing |

### Token Estimation

Token Audit uses OpenAI's `tiktoken` library with the `o200k_base` encoding to estimate per-tool token usage:

- **Accuracy**: ~99-100% (same tokenizer OpenAI uses)
- **No setup required**: tiktoken is bundled with token-audit
- **TUI indicator**: Shows "Estimated (tiktoken)" in token panel

---

## Session File Location

Codex CLI stores sessions at:

```
~/.codex/sessions/YYYY/MM/DD/*.jsonl
```

Token Audit auto-discovers the latest session. Use `--from-start` to include existing data:

```bash
# Track only new events (default)
token-audit collect --platform codex-cli

# Include existing session data from the start
token-audit collect --platform codex-cli --from-start
```

---

## Event Types Tracked

| Event Type | Description |
|------------|-------------|
| `session_meta` | Session metadata (ID, CWD, CLI version) |
| `turn_context` | Model selection and settings |
| `token_count` | Token usage (cumulative totals) |
| `function_call` | MCP tool calls (filtered by `mcp__` prefix) |

---

## Configuration

### Theme Options

```bash
# Use Catppuccin Mocha theme
token-audit collect --platform codex-cli --theme mocha

# Available themes: auto, dark, light, mocha, latte, hc-dark, hc-light
```

### Pricing Configuration

Edit `~/.token-audit/token-audit.toml`:

```toml
[pricing.openai]
# Prices per 1M tokens (USD)
"gpt-5.1" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"gpt-5.1-codex-max" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"o4-mini" = { input = 4.00, output = 16.00, cache_read = 1.00 }
```

---

## Built-in Tools vs MCP Tools

Codex CLI has platform-specific built-in tools tracked separately:

| Built-in Tool | Purpose |
|---------------|---------|
| `shell` | Execute bash commands |
| `shell_command` | Alternative shell execution |
| `read_file` | Read files |
| `apply_patch` | Apply code patches |
| `list_dir` | List directory contents |
| `grep_files` | Search file contents |
| `view_image` | View image files |
| `exec` | Unified execution handler |
| `update_plan` | Task planning |
| `list_mcp_resources` | MCP resource discovery |
| `list_mcp_resource_templates` | MCP resource templates |

Built-in tools appear in the "Built-in Tools" count, not the MCP server hierarchy.

---

## Platform Limitations

### Cache Creation Not Reported

Only cache reads are available. `cache_created_tokens` is always 0:

```json
"token_usage": {
  "cache_created_tokens": 0,
  "cache_read_tokens": 1272832
}
```

**Why**: OpenAI's API only reports `cached_input_tokens` (cache hits).

### Tool Duration Available

Tool execution time IS available via `function_call_output` events:

```json
{
  "tool_calls": [
    {
      "tool": "mcp__brave-search__brave_web_search",
      "duration_ms": 1500
    }
  ]
}
```

---

## Example Output

```
$ token-audit collect --platform codex-cli

Token Audit v1.0.0 - Codex CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Project: my-project │ Elapsed: 8m 12s
Model: GPT-5.1 Codex Max

Tokens (Estimated via tiktoken):
  45,231 input │ 12,543 output │ 125K cached

Cost (USD): $0.08

MCP Servers & Tools (12 calls)
  zen (8 calls)
    chat ............. 5 calls
    thinkdeep ........ 3 calls
  brave-search (4 calls)
    brave_web_search   4 calls

Built-in Tools: 45 calls
```

---

## Troubleshooting

### No Sessions Found

1. Verify Codex has created sessions:
   ```bash
   ls ~/.codex/sessions/
   ```

2. Check for recent sessions:
   ```bash
   find ~/.codex/sessions -name "*.jsonl" -mtime -7
   ```

### Model Not Detected

Ensure the session contains `turn_context` events:
```bash
head -20 ~/.codex/sessions/2025/12/08/session.jsonl | grep turn_context
```

---

## See Also

- [MCP Server Integration: Codex CLI](../mcp-server-integration/codex-cli.md) - Use token-audit as an MCP server (v1.0)
- [Getting Started](../getting-started.md) - Installation and first session
- [Feature Reference](../features.md) - Complete feature guide
- [Configuration Reference](../configuration.md) - CLI options and pricing
- [Troubleshooting](../troubleshooting.md) - Common issues and solutions
- [Complete Setup Guide](../codex-cli-setup.md) - Detailed configuration options
- [Architecture](../architecture.md) - How Token Audit works internally
- [Data Contract](../data-contract.md) - Session schema documentation
