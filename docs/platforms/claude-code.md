# Claude Code Platform Guide

This guide explains how to use Token Audit with [Claude Code](https://claude.ai/claude-code), Anthropic's AI coding assistant.

> **v1.0 Feature**: Want to use token-audit as an MCP server inside Claude Code? See [MCP Server Integration: Claude Code](../mcp-server-integration/claude-code.md).

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Token Accuracy** | Native (100%) — exact counts from Anthropic |
| **Per-tool Attribution** | Yes — native per-tool token breakdown |
| **Cache Tracking** | Full (create + read) |
| **Reasoning Tokens** | Not exposed |
| **Session Location** | `~/.claude/projects/<hash>/session.jsonl` |
| **Special Features** | Highest accuracy, full cache visibility |

---

## Prerequisites

- **Claude Code** installed and configured
- **Python 3.8+** installed
- **MCP servers** configured in Claude Code (optional, but tracking is most useful with MCP)

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
token-audit collect --platform claude-code
```

You'll see a live TUI dashboard:

```
Token Audit v1.0.0 - Claude Code Session
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Status: Tracking...
Project: my-project (auto-detected)
Model: Claude Opus 4.5

Tokens:      0 input │ 0 output │ 0 cached
Cost (USD):  $0.00
MCP Tools:   0 calls │ 0 unique

Waiting for events... (Ctrl+C to stop)
```

### 2. Use Claude Code Normally

In a separate terminal, start Claude Code:

```bash
claude
```

Work as usual. Token Audit will track:
- All model interactions (tokens used)
- All MCP tool calls (which tools, how many tokens)
- Cache efficiency (cache hits vs misses)

### 3. Stop Tracking

When done, press `Ctrl+C` in the Token Audit terminal:

```
^C
Session complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Duration:    45 minutes
Tokens:      125,432 total (93% cached)
Cost (USD):  $0.15
MCP Tools:   42 calls across 3 servers

Session saved to:
~/.token-audit/sessions/claude_code/2025-12-08/session-20251208T103045-abc123.jsonl
```

---

## How It Works

Token Audit monitors Claude Code's session log files located at:

```
~/.claude/projects/<project_hash>/session.jsonl
```

It parses events in real-time to extract:
- Token usage (input, output, cache created, cache read)
- MCP tool calls (tool name, server, tokens per call)
- Model information (which Claude model variant)

### File Watcher Approach

```
Claude Code          Token Audit
    │                    │
    │ writes events      │
    ▼                    │
~/.claude/projects/  watches
session.jsonl ──────────►│
                         │ parses events
                         ▼
                   Tracking Data
```

---

## Configuration

### Auto-Detection

Token Audit automatically detects:
- **Project name**: From your current working directory
- **Model**: From Claude Code's session metadata
- **MCP servers**: From tool call events

### CLI Options

```bash
# Specify project name
token-audit collect --platform claude-code --project "my-feature"

# Use a specific theme
token-audit collect --platform claude-code --theme mocha

# Pin specific servers at top of MCP panel
token-audit collect --platform claude-code --pin-server zen --pin-server brave-search
```

### Theme Options

Token Audit supports multiple color themes:

| Theme | Description |
|-------|-------------|
| `auto` | Auto-detect terminal background (default) |
| `dark` | Dark theme |
| `light` | Light theme |
| `mocha` | Catppuccin Mocha (dark) |
| `latte` | Catppuccin Latte (light) |
| `hc-dark` | High contrast dark (WCAG AAA) |
| `hc-light` | High contrast light (WCAG AAA) |

```bash
# Use Catppuccin Mocha theme
token-audit collect --platform claude-code --theme mocha

# Or set via environment variable
export TOKEN_AUDIT_THEME=mocha
```

### Pricing Configuration

Create or edit `~/.token-audit/token-audit.toml`:

```toml
[pricing.claude]
# Prices are per 1M tokens (USD)
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00, cache_create = 6.25, cache_read = 0.50 }
"claude-sonnet-4-5-20250929" = { input = 3.00, output = 15.00, cache_create = 3.75, cache_read = 0.30 }
"claude-haiku-4-5-20251001" = { input = 1.00, output = 5.00, cache_create = 1.25, cache_read = 0.10 }
```

---

## Platform Capabilities

Claude Code provides **native token attribution** — the most accurate tracking available:

| Capability | Status | Notes |
|------------|--------|-------|
| Session tokens | ✅ Native | Exact counts from Anthropic |
| Per-tool tokens | ✅ Native | Each MCP call shows exact token cost |
| Reasoning tokens | ❌ | Not exposed by Claude Code |
| Cache tracking | ✅ Full | Both cache creation and read |
| Cost estimates | ✅ Accurate | Uses native token counts |
| Data quality | **exact** | Confidence: 1.0 (100% accurate) |

**No estimation needed** — Claude Code exposes exact per-tool token counts directly.

### Key Features

**Data Quality Indicators**: Claude Code sessions have `accuracy_level: "exact"` with 100% confidence.

**Smell Detection**: All 12 anti-patterns detected including HIGH_VARIANCE, TOP_CONSUMER, HIGH_MCP_SHARE, CHATTY, LOW_CACHE_HIT, and more.

**AI Export**: Export session data for AI analysis:
```bash
token-audit report --format ai
```

---

## MCP Server Tracking

### Supported MCP Servers

Token Audit tracks all MCP servers configured in Claude Code:

| Server | Common Tools | Notes |
|--------|--------------|-------|
| zen | chat, thinkdeep, consensus | High token usage |
| brave-search | brave_web_search, brave_local_search | Variable by query |
| jina | read_url, search_web | Web content |
| context7 | resolve-library-id, get-library-docs | Documentation |

### Tool Name Format

Claude Code uses this format for MCP tools:

```
mcp__<server>__<tool>
```

Examples:
- `mcp__zen__chat`
- `mcp__brave-search__brave_web_search`
- `mcp__jina__read_url`

### Built-in Tools

Claude Code's built-in tools are tracked separately:

| Tool | Purpose |
|------|---------|
| Read | Read files |
| Write | Write files |
| Edit | Edit files |
| Bash | Execute commands |
| BashOutput | Get background shell output |
| Glob | Find files by pattern |
| Grep | Search file contents |
| Task | Launch subagents |
| AskUserQuestion | Request user input |
| TodoWrite | Manage task lists |
| WebFetch | Fetch URL content |
| WebSearch | Search the web |
| NotebookEdit | Edit Jupyter notebooks |
| Skill | Execute skills |
| SlashCommand | Run slash commands |
| KillShell | Kill background shell |
| EnterPlanMode | Enter plan mode |
| ExitPlanMode | Exit plan mode |

Built-in tools appear in the "Built-in Tools" section, not the MCP server hierarchy.

---

## Viewing Results

### Terminal Report

```bash
token-audit report
```

### JSON Export

```bash
token-audit report --format json --output report.json
```

### CSV for Spreadsheets

```bash
token-audit report --format csv --output report.csv
```

### Aggregate Multiple Sessions

```bash
token-audit report ~/.token-audit/sessions/ --aggregate --top-n 10
```

---

## Troubleshooting

### No Events Detected

**Symptom**: Tracker shows "Waiting for events..." but nothing appears.

**Solutions**:
1. Ensure Claude Code is running in a separate terminal
2. Check that Claude Code's session directory exists:
   ```bash
   ls ~/.claude/projects/
   ```
3. Start Token Audit **before** starting Claude Code (only new events are tracked)

### Missing MCP Data

**Symptom**: Model tokens tracked but no MCP tool calls.

**Solutions**:
1. Verify MCP servers are configured:
   ```bash
   cat ~/.claude/settings.json | grep -A 20 mcpServers
   ```
2. Use an MCP tool in Claude Code to trigger events
3. Check for parsing errors in Token Audit output

### High Cache Miss Rate

**Symptom**: Low cache efficiency (<50%).

**Causes**:
- New conversation (no cache to hit)
- Rapidly changing context
- Large file edits

**Note**: High cache miss is normal at the start of new sessions.

---

## Best Practices

### Session Organization

- Run one Token Audit instance per Claude Code session
- Name projects descriptively: `--project "feature-auth-refactor"`
- Review sessions weekly to identify patterns

### Cost Optimization

Based on Token Audit data:

1. **Spot expensive tools**:
   - `thinkdeep`: Use for complex debugging only
   - `consensus`: Batch questions to minimize calls

2. **Leverage caching**:
   - Keep context consistent within sessions
   - Avoid frequent large file changes

3. **Use appropriate tools**:
   - `chat` for simple questions (lower tokens)
   - `thinkdeep` for complex analysis (higher tokens)

---

## Example Session

### Sample TUI Output

```
Token Audit v1.0.0 - Claude Code
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Project: my-project │ Elapsed: 12m 34s
Model: Claude Opus 4.5

Tokens:  45,231 input │ 12,543 output │ 125K cached
Cost:    $0.12 │ Cache savings: $0.89

MCP Servers & Tools (42 calls)
  zen (28 calls, 234K tokens)
    chat ............. 15 calls, 45K tokens
    thinkdeep ........ 8 calls, 156K tokens
    debug ............ 5 calls, 33K tokens
  brave-search (14 calls, 89K tokens)
    brave_web_search   14 calls, 89K tokens

Built-in Tools (127 calls)
  Read .... 45 calls │ Edit .... 32 calls
  Bash .... 28 calls │ Glob .... 22 calls
```

### Sample Report

```
Top 5 Most Expensive Tools
═══════════════════════════════════════════════════════════════
Tool                              Calls    Tokens    Avg/Call
mcp__zen__thinkdeep                   3   112,345      37,448
mcp__zen__chat                       15    45,678       3,045
mcp__brave-search__brave_web_search   8    23,456       2,932
mcp__jina__read_url                   5    12,345       2,469
Read (built-in)                      45     8,765         195

Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total tokens:     202,589
Cache efficiency: 87%
Estimated cost:   $0.23
```

---

## See Also

- [MCP Server Integration: Claude Code](../mcp-server-integration/claude-code.md) - Use token-audit as an MCP server (v1.0)
- [Getting Started](../getting-started.md) - Installation and first session
- [Feature Reference](../features.md) - Complete feature guide
- [Configuration Reference](../configuration.md) - CLI options and pricing
- [Troubleshooting](../troubleshooting.md) - Common issues and solutions
- [Architecture](../architecture.md) - How Token Audit works internally
- [Data Contract](../data-contract.md) - Session schema documentation
