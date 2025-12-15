# Configuration Reference

Complete reference for MCP Audit configuration options. For getting started, see [Getting Started](GETTING-STARTED.md).

---

## Table of Contents

- [Configuration Files](#configuration-files)
- [CLI Options](#cli-options)
- [Pricing Configuration](#pricing-configuration)
- [Theme Configuration](#theme-configuration)
- [Zombie Tool Configuration](#zombie-tool-configuration)
- [Environment Variables](#environment-variables)

---

## Configuration Files

### File Locations

MCP Audit checks for configuration files in this order:

| Priority | Location | Use Case |
|----------|----------|----------|
| 1 | `./mcp-audit.toml` | Project-specific settings |
| 2 | `~/.mcp-audit/mcp-audit.toml` | User-level defaults |

### Creating a Config File

```bash
# Create user config directory
mkdir -p ~/.mcp-audit

# Create config file
cat > ~/.mcp-audit/mcp-audit.toml << 'EOF'
# MCP Audit Configuration

[pricing.api]
enabled = true
cache_ttl_hours = 24

[zombie_tools.zen]
tools = ["mcp__zen__thinkdeep", "mcp__zen__debug"]
EOF
```

### Check Configuration Status

```bash
mcp-audit init
```

Output:

```
MCP Audit Configuration Status
==============================
Version: 0.8.0

Configuration:
  File: ~/.mcp-audit/mcp-audit.toml (loaded)

Pricing:
  Source: api (fresh)
  Models: 2,347 available
  Cache expires: 23h 14m

Tokenizer:
  Gemma: installed
```

---

## CLI Options

### collect

Track a live session.

```bash
mcp-audit collect [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--platform` | `claude-code`, `codex-cli`, `gemini-cli`, `auto` | `auto` | Platform to track |
| `--project` | TEXT | *(auto-detected)* | Project name |
| `--theme` | See [themes](#available-themes) | `auto` | Color theme |
| `--pin-server` | NAME | *(none)* | Pin server(s) at top of MCP panel |
| `--from-start` | FLAG | `false` | Include existing session data (Codex/Gemini only) |
| `--quiet` | FLAG | `false` | Suppress display (logs only) |
| `--plain` | FLAG | `false` | Plain text output (for CI) |
| `--no-logs` | FLAG | `false` | Skip writing logs (display only) |

**Examples:**

```bash
# Basic usage
mcp-audit collect --platform claude-code

# Pin servers to monitor closely
mcp-audit collect --pin-server zen --pin-server backlog

# Dark theme with custom project name
mcp-audit collect --theme mocha --project my-feature

# CI/headless mode
mcp-audit collect --plain --quiet
```

### report

Generate usage report.

```bash
mcp-audit report [PATH] [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--format` | `json`, `csv`, `markdown` | `markdown` | Output format |
| `--output` | PATH | stdout | Output file |
| `--aggregate` | FLAG | `false` | Aggregate across sessions |
| `--top-n` | INT | 10 | Number of top tools to show |

**Examples:**

```bash
# Basic report
mcp-audit report ~/.mcp-audit/sessions/

# Top 5 tools in JSON
mcp-audit report --top-n 5 --format json

# CSV export for spreadsheet
mcp-audit report --format csv --output analysis.csv

# Aggregate all sessions
mcp-audit report --aggregate
```

### smells

Analyze efficiency patterns across sessions.

```bash
mcp-audit smells [PATH] [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--severity` | `info`, `warning`, `error` | *(all)* | Filter by severity |
| `--pattern` | PATTERN_NAME | *(all)* | Filter by pattern |
| `--format` | `json`, `markdown` | `markdown` | Output format |

**Examples:**

```bash
# All smells
mcp-audit smells ~/.mcp-audit/sessions/

# Warnings and errors only
mcp-audit smells --severity warning

# Specific pattern
mcp-audit smells --pattern CHATTY
```

### export

Export session data for external analysis.

```bash
mcp-audit export ai-prompt [PATH] [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--format` | `markdown`, `json` | `markdown` | Output format |
| `--output` | PATH | stdout | Output file |

**Examples:**

```bash
# Export for AI analysis (paste into Claude/ChatGPT)
mcp-audit export ai-prompt

# Specific session as JSON
mcp-audit export ai-prompt path/to/session.json --format json

# Save to file
mcp-audit export ai-prompt --output analysis.md
```

### ui

Interactive session browser.

```bash
mcp-audit ui [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--theme` | See [themes](#available-themes) | `auto` | Color theme |

**Examples:**

```bash
mcp-audit ui
mcp-audit ui --theme mocha
```

### tokenizer

Manage optional tokenizers.

```bash
mcp-audit tokenizer download    # Download Gemma tokenizer (~4MB)
mcp-audit tokenizer status      # Check availability
```

### init

Show configuration and pricing status.

```bash
mcp-audit init
```

---

## Pricing Configuration

MCP Audit provides accurate cost estimation through a multi-tier pricing system.

### Pricing Sources (Priority Order)

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | LiteLLM API | Fresh pricing for 2,000+ models |
| 2 | API Cache | Cached API data (24h default) |
| 3 | TOML config | Custom/override pricing |
| 4 | Built-in | Hardcoded defaults |

### Dynamic Pricing (v0.6.0)

Auto-fetch current pricing from [LiteLLM](https://github.com/BerriAI/litellm):

```toml
[pricing.api]
enabled = true        # Enable API fetching (default: true)
cache_ttl_hours = 24  # Cache duration (default: 24)
offline_mode = false  # Never fetch from network (default: false)
```

### Configuration Examples

**Default (recommended):**
```toml
[pricing.api]
enabled = true
cache_ttl_hours = 24
```

**Offline/air-gapped environment:**
```toml
[pricing.api]
enabled = true
offline_mode = true  # Use cache/TOML only
```

**TOML-only pricing:**
```toml
[pricing.api]
enabled = false
```

**Frequent updates:**
```toml
[pricing.api]
enabled = true
cache_ttl_hours = 6
```

### Custom Model Pricing

Add custom models or override API pricing:

```toml
# Override existing model
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00 }

# Add custom model
[pricing.custom]
"my-fine-tuned-model" = { input = 2.0, output = 10.0 }

# Local model (zero cost)
[pricing.custom]
"llama-3-70b-local" = { input = 0.0, output = 0.0 }
```

Fields:
- `input`: Cost per million input tokens (USD)
- `output`: Cost per million output tokens (USD)
- `cache_create`: Cost per million cache creation tokens (optional)
- `cache_read`: Cost per million cache read tokens (optional)

### Cache Location

API pricing cached at: `~/.mcp-audit/pricing-cache.json`

Clear cache to force refresh:
```bash
rm ~/.mcp-audit/pricing-cache.json
mcp-audit init
```

### Model Pricing Reference

| Provider | Pricing Page |
|----------|--------------|
| Anthropic | https://www.anthropic.com/pricing |
| OpenAI | https://openai.com/api/pricing/ |
| Google | https://ai.google.dev/gemini-api/docs/pricing |

---

## Theme Configuration

### Available Themes

| Theme | Description |
|-------|-------------|
| `auto` | Detect terminal preference (default) |
| `dark` | Standard dark theme |
| `light` | Standard light theme |
| `mocha` | Catppuccin Mocha (warm dark) |
| `latte` | Catppuccin Latte (warm light) |
| `hc-dark` | High contrast dark (WCAG AAA) |
| `hc-light` | High contrast light (WCAG AAA) |

### Usage

```bash
# Per-session
mcp-audit collect --theme mocha

# Session browser
mcp-audit ui --theme hc-dark
```

### Accessibility Options

| Option | Description |
|--------|-------------|
| `--plain` | ASCII-only output (no unicode) |
| `hc-dark`, `hc-light` | WCAG AAA compliant contrast |
| `NO_COLOR=1` | Disable colors entirely |

---

## Zombie Tool Configuration

Detect unused MCP tools that contribute to context overhead.

### Configuration

```toml
# mcp-audit.toml
[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__debug",
    "mcp__zen__refactor",
    "mcp__zen__precommit"
]

[zombie_tools.backlog]
tools = [
    "mcp__backlog__task_create",
    "mcp__backlog__task_list",
    "mcp__backlog__task_view"
]
```

### How It Works

1. List known tools per MCP server in config
2. MCP Audit tracks which tools are actually called
3. Uncalled tools are reported as "zombies"
4. Each zombie adds ~175 tokens to context overhead

### Session Data

```json
{
  "zombie_tools": {
    "zen": ["mcp__zen__refactor", "mcp__zen__precommit"]
  }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_AUDIT_DIR` | `~/.mcp-audit` | Data directory |
| `NO_COLOR` | *(unset)* | Disable colors when set |
| `TERM` | *(system)* | Used for theme auto-detection |

### Custom Data Directory

```bash
export MCP_AUDIT_DIR=/custom/path
mcp-audit collect
# Sessions saved to /custom/path/sessions/
```

### Disable Colors

```bash
NO_COLOR=1 mcp-audit collect
```

---

## Complete Example Configuration

```toml
# ~/.mcp-audit/mcp-audit.toml

# Dynamic pricing from LiteLLM API
[pricing.api]
enabled = true
cache_ttl_hours = 24
offline_mode = false

# Custom model overrides
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00 }

[pricing.custom]
"my-local-model" = { input = 0.0, output = 0.0 }

# Exchange rates (display only)
[metadata.exchange_rates]
USD_to_AUD = 1.54
USD_to_EUR = 0.92

# Zombie tool detection
[zombie_tools.zen]
tools = [
    "mcp__zen__thinkdeep",
    "mcp__zen__debug",
    "mcp__zen__refactor",
    "mcp__zen__precommit",
    "mcp__zen__codereview"
]

[zombie_tools.backlog]
tools = [
    "mcp__backlog__task_create",
    "mcp__backlog__task_list",
    "mcp__backlog__task_view",
    "mcp__backlog__task_edit"
]
```

---

## Troubleshooting

### "No pricing data available"

**Cause:** API disabled and no TOML config found.

**Solution:**
```toml
[pricing.api]
enabled = true
```

### "Network errors fetching pricing"

**Cause:** Firewall blocking GitHub raw content.

**Solution:**
```toml
[pricing.api]
enabled = true
offline_mode = true  # Use cache/TOML only
```

### "TOML support not available"

**Solution:** Install toml package (Python 3.8-3.10 only):
```bash
pip install toml
```
Python 3.11+ has built-in `tomllib`.

See [Troubleshooting Guide](TROUBLESHOOTING.md) for more issues.

---

*For feature details, see [Feature Reference](FEATURES.md). For getting started, see [Getting Started](GETTING-STARTED.md).*
