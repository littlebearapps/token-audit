# Gemini CLI Platform Guide

This guide explains how to use MCP Audit with [Gemini CLI](https://github.com/google-gemini/gemini-cli), Google's AI coding assistant.

> **📖 See [Gemini CLI Setup Guide](../gemini-cli-setup.md) for detailed configuration options.**

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Token Accuracy** | Session: Native / Per-tool: Estimated (100% with Gemma, 95% without) |
| **Per-tool Attribution** | Estimated via Gemma tokenizer or tiktoken fallback |
| **Cache Tracking** | Read only (cache creation not reported) |
| **Reasoning Tokens** | Yes — Gemini 2.0+ models (`thoughts` field) |
| **Session Location** | `~/.gemini/tmp/<hash>/chats/session-*.json` |
| **Special Features** | Gemma tokenizer for 100% accuracy, reasoning tokens |

---

## Prerequisites

- **Gemini CLI** installed (`npm install -g @google/gemini-cli`)
- **Python 3.8+** installed
- **MCP servers** configured in Gemini (optional)

---

## Installation

```bash
pipx install mcp-audit
```

Or with pip:

```bash
pip install mcp-audit
```

### Optional: Gemma Tokenizer (100% Accuracy)

For exact token counts, download the Gemma tokenizer:

```bash
mcp-audit tokenizer download
```

This downloads ~4MB from GitHub Releases (no account required). Without it, mcp-audit uses tiktoken (~95% accuracy).

---

## Quick Start

### 1. Start Tracking

Open a new terminal **in your project directory** and run:

```bash
cd /path/to/your/project
mcp-audit collect --platform gemini-cli
```

> **Important**: Run from your project directory so MCP Audit can auto-detect the project hash.

### 2. Use Gemini CLI Normally

In a separate terminal, start Gemini from the same directory:

```bash
cd /path/to/your/project
gemini
```

Work as usual. MCP Audit will track:
- All model interactions (tokens used)
- All MCP tool calls (call counts + estimated tokens)
- Thinking/reasoning tokens (Gemini 2.0+)

### 3. View Results

When done, press `Ctrl+C` to see the session summary, or generate a report:

```bash
mcp-audit report
```

---

## Platform Capabilities

Gemini CLI provides **message-level token counts** with per-tool estimation:

| Capability | Status | Notes |
|------------|--------|-------|
| Session tokens | ✅ Native | Exact counts from Google |
| Per-tool tokens | ✅ Estimated (100%/95%) | Gemma or tiktoken fallback |
| Reasoning tokens | ✅ Gemini 2.0+ | `thoughts` field tracked separately |
| Cache tracking | ✅ Read only | Cache creation not reported |
| Cost estimates | ✅ Accurate | Based on session totals + model pricing |

### Token Estimation (v0.4.0)

MCP Audit supports two accuracy levels for per-tool token estimation:

| Mode | Accuracy | Requirement |
|------|----------|-------------|
| With Gemma tokenizer | **100%** | `mcp-audit tokenizer download` |
| Without tokenizer | **~95%** | None (works immediately) |

**With Gemma tokenizer**:
- Uses Google's official SentencePiece model
- Exact same tokenization as Gemini models
- One-time 4MB download from GitHub Releases

**Without tokenizer**:
- Uses tiktoken `cl100k_base` as fallback
- ~95% accuracy (close but not exact)
- TUI shows "Estimated (tiktoken)" indicator

### Installing the Tokenizer

```bash
# Download from GitHub Releases (recommended)
mcp-audit tokenizer download

# Check status
mcp-audit tokenizer status

# For corporate networks, see manual install guide
```

For firewalled networks, see [Manual Tokenizer Install](../manual-tokenizer-install.md).

---

## Session File Location

Gemini CLI stores sessions per-project using a SHA256 hash:

```
~/.gemini/tmp/<project_hash>/chats/session-*.json
```

MCP Audit auto-detects the hash from your current directory, or you can specify:

```bash
# Include existing session data (not just new events)
mcp-audit collect --platform gemini-cli --from-start

# Specify project hash manually
mcp-audit collect --platform gemini-cli --project-hash abc123...
```

---

## Token Mapping

Gemini CLI provides detailed token breakdowns per message:

| Gemini Token | MCP Audit Field | Description |
|--------------|-----------------|-------------|
| `input` | `input_tokens` | Prompts and context |
| `output` | `output_tokens` | Model responses |
| `cached` | `cache_read_tokens` | Cached context |
| `thoughts` | `reasoning_tokens` | Thinking/reasoning (Gemini 2.0+) |
| `tool` | Tool-related | Tokens for tool execution |

---

## Configuration

### Theme Options

```bash
# Use Catppuccin Mocha theme
mcp-audit collect --platform gemini-cli --theme mocha

# Available themes: auto, dark, light, mocha, latte, hc-dark, hc-light
```

### Pricing Configuration

Edit `~/.mcp-audit/mcp-audit.toml`:

```toml
[pricing.gemini]
# Prices per 1M tokens (USD)
"gemini-3-pro-preview" = { input = 2.00, output = 12.00, cache_read = 0.20 }
"gemini-2.5-pro" = { input = 1.25, output = 10.00, cache_read = 0.125 }
"gemini-2.5-flash" = { input = 0.30, output = 2.50, cache_read = 0.03 }
"gemini-2.0-flash" = { input = 0.10, output = 0.40, cache_read = 0.025 }
```

---

## Built-in Tools vs MCP Tools

Gemini CLI has platform-specific built-in tools tracked separately:

| Built-in Tool | Purpose |
|---------------|---------|
| `glob` | File pattern matching |
| `google_web_search` | Web search |
| `list_directory` | List directory contents |
| `read_file` | Read files |
| `read_many_files` | Read multiple files |
| `replace` | Edit/replace file content |
| `run_shell_command` | Execute shell commands |
| `save_memory` | Save context to memory |
| `search_file_content` | Search within files |
| `web_fetch` | Fetch web content |
| `write_file` | Write files |
| `write_todos` | Manage todo items |

Built-in tools appear in the "Built-in Tools" count, not the MCP server hierarchy.

---

## Example Output

```
$ mcp-audit collect --platform gemini-cli

MCP Audit v0.4.0 - Gemini CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Project: my-project │ Elapsed: 15m 22s
Model: Gemini 2.5 Pro

Tokens (Estimated via Gemma):
  125,432 input │ 8,543 output │ 45K cached
Reasoning: 12,340 tokens

Cost (USD): $0.18

MCP Servers & Tools (8 calls)
  zen (5 calls)
    chat ............. 3 calls
    thinkdeep ........ 2 calls
  jina (3 calls)
    read_url ......... 3 calls

Built-in Tools: 67 calls
```

---

## Troubleshooting

### No Sessions Found

1. Verify Gemini has created sessions:
   ```bash
   ls ~/.gemini/tmp/
   ```

2. Check the session directory for your project:
   ```bash
   # Calculate hash for current directory
   python -c "import hashlib; print(hashlib.sha256(str('$(pwd)').encode()).hexdigest())"
   # Then check
   ls ~/.gemini/tmp/<hash>/chats/
   ```

### Wrong Project Hash

Ensure you're in the correct directory when running MCP Audit:

```bash
cd /path/to/your/project
mcp-audit collect --platform gemini-cli
```

Or specify the hash manually:

```bash
mcp-audit collect --platform gemini-cli --project-hash <correct-hash>
```

### Tokenizer Not Found

If you see "Estimated (tiktoken)" instead of "Estimated (Gemma)":

```bash
# Check tokenizer status
mcp-audit tokenizer status

# Download if missing
mcp-audit tokenizer download
```

---

## See Also

- [Getting Started](../GETTING-STARTED.md) - Installation and first session
- [Feature Reference](../FEATURES.md) - Complete feature guide
- [Configuration Reference](../CONFIGURATION.md) - CLI options and pricing
- [Troubleshooting](../TROUBLESHOOTING.md) - Common issues and solutions
- [Complete Setup Guide](../gemini-cli-setup.md) - Detailed configuration options
- [Manual Tokenizer Install](../manual-tokenizer-install.md) - For corporate networks
- [Architecture](../architecture.md) - How MCP Audit works internally
- [Data Contract](../data-contract.md) - Session schema documentation
