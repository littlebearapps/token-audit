# Configuration Reference

Complete reference for Token Audit configuration options. For getting started, see [Getting Started](getting-started.md).

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

Token Audit checks for configuration files in this order:

| Priority | Location | Use Case |
|----------|----------|----------|
| 1 | `./token-audit.toml` | Project-specific settings |
| 2 | `~/.token-audit/token-audit.toml` | User-level defaults |

### Creating a Config File

```bash
# Create user config directory
mkdir -p ~/.token-audit

# Create config file
cat > ~/.token-audit/token-audit.toml << 'EOF'
# Token Audit Configuration

[pricing.api]
enabled = true
cache_ttl_hours = 24

[zombie_tools.zen]
tools = ["mcp__zen__thinkdeep", "mcp__zen__debug"]
EOF
```

### Check Configuration Status

```bash
token-audit tokenizer setup
```

Output:

```
Token Audit Configuration Status
==============================
Version: 1.0.0

Configuration:
  File: ~/.token-audit/token-audit.toml (loaded)

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
token-audit collect [OPTIONS]
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
token-audit collect --platform claude-code

# Pin servers to monitor closely
token-audit collect --pin-server zen --pin-server backlog

# Dark theme with custom project name
token-audit collect --theme mocha --project my-feature

# CI/headless mode
token-audit collect --plain --quiet
```

### report

Generate usage report.

```bash
token-audit report [PATH] [OPTIONS]
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
token-audit report ~/.token-audit/sessions/

# Top 5 tools in JSON
token-audit report --top-n 5 --format json

# CSV export for spreadsheet
token-audit report --format csv --output analysis.csv

# Aggregate all sessions
token-audit report --aggregate
```

### report --smells

Analyze efficiency patterns across sessions.

```bash
token-audit report --smells [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--days` | INT | `30` | Number of days to analyze |
| `--platform` | `claude-code`, `codex-cli`, `gemini-cli` | *(all)* | Filter by platform |
| `--project` | TEXT | *(all)* | Filter by project name |
| `--format` | `text`, `json`, `markdown` | `text` | Output format |
| `--min-frequency` | FLOAT | `0` | Minimum frequency % to display |
| `--output` | PATH | stdout | Output file |

**Examples:**

```bash
# Analyze last 30 days (default)
token-audit report --smells

# Last 7 days, Claude Code only
token-audit report --smells --days 7 --platform claude-code

# Export as JSON
token-audit report --smells --format json --output smells.json
```

### report --format ai

Export session data for AI assistant analysis.

```bash
token-audit report --format ai [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--output` | PATH | stdout | Output file |
| `--session` | ID | *(latest)* | Specific session to export |

**Examples:**

```bash
# Export for AI analysis (paste into Claude/ChatGPT)
token-audit report --format ai

# Specific session
token-audit report --format ai --session session-2024-01-15

# Save to file
token-audit report --format ai --output analysis.md
```

### best-practices

Export MCP best practices from usage patterns.

```bash
token-audit best-practices [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--format` | `json`, `yaml`, `markdown` | `json` | Output format |
| `--category` | `efficiency`, `security`, `performance`, `all` | `all` | Filter by category |
| `--output` | PATH | stdout | Output file |

**Examples:**

```bash
# Export best practices as markdown for AGENTS.md
token-audit best-practices --format markdown

# Export security-related best practices
token-audit best-practices --category security
```

### ui

Interactive session browser with Dashboard, Live monitoring, and Recommendations views (v1.0.0).

```bash
token-audit ui [OPTIONS]
```

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--theme` | See [themes](#available-themes) | `auto` | Color theme |
| `--view` | `dashboard`, `sessions`, `recommendations`, `live` | `dashboard` | Initial view to display |
| `--compact` | flag | auto-detect | Force compact display mode |

**Views (use number keys 1-4 to switch):**

| View | Key | Description |
|------|-----|-------------|
| Dashboard | `1` | Today's summary, weekly trends, top smells, recent sessions |
| Sessions | `2` | Full session list with filtering and sorting |
| Recommendations | `3` | Optimization suggestions grouped by confidence |
| Live | `4` | Real-time session monitoring |

**Examples:**

```bash
token-audit ui                              # Launch to Dashboard (default)
token-audit ui --view sessions              # Start in session list
token-audit ui --view live                  # Start in live monitoring
token-audit ui --compact                    # Force compact display
token-audit ui --theme mocha                # Use specific theme
```

### tokenizer

Manage optional tokenizers.

```bash
token-audit tokenizer download    # Download Gemma tokenizer (~4MB)
token-audit tokenizer status      # Check availability
```

### tokenizer setup

Show configuration and pricing status.

```bash
token-audit tokenizer setup
```

### validate

Validate session files against JSON Schema.

```bash
token-audit validate <session_file> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--schema-only` | Show schema path without validating |
| `--verbose` | Show detailed validation errors |

**Examples:**

```bash
# Validate a session file
token-audit validate ~/.token-audit/sessions/session-2024-01-15.json

# Show schema path
token-audit validate --schema-only

# Verbose validation errors
token-audit validate session.json --verbose
```

### pin

Manage pinned MCP servers for focused analysis.

```bash
token-audit pin [server_name] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--list`, `-l` | List all pinned servers |
| `--remove`, `-r` | Remove a pinned server |
| `--auto` | Auto-detect servers from MCP config |
| `--clear` | Clear all pinned servers |
| `--json` | Output as JSON |
| `--notes` | Add notes when pinning |

**Examples:**

```bash
# Pin a server
token-audit pin zen

# Pin with notes
token-audit pin brave-search --notes "Monitor for rate limits"

# List pinned servers
token-audit pin --list

# Auto-detect from config
token-audit pin --auto

# Remove a pinned server
token-audit pin --remove zen

# Clear all pinned
token-audit pin --clear
```

---

## Pricing Configuration

Token Audit provides accurate cost estimation through a multi-tier pricing system.

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

API pricing cached at: `~/.token-audit/pricing-cache.json`

Clear cache to force refresh:
```bash
rm ~/.token-audit/pricing-cache.json
token-audit tokenizer setup
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
token-audit collect --theme mocha

# Session browser
token-audit ui --theme hc-dark
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
# token-audit.toml
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
2. Token Audit tracks which tools are actually called
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
| `TOKEN_AUDIT_DIR` | `~/.token-audit` | Data directory |
| `NO_COLOR` | *(unset)* | Disable colors when set |
| `TERM` | *(system)* | Used for theme auto-detection |

### Custom Data Directory

```bash
export TOKEN_AUDIT_DIR=/custom/path
token-audit collect
# Sessions saved to /custom/path/sessions/
```

### Disable Colors

```bash
NO_COLOR=1 token-audit collect
```

---

## Complete Example Configuration

```toml
# ~/.token-audit/token-audit.toml

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

See [Troubleshooting Guide](troubleshooting.md) for more issues.

---

*For feature details, see [Feature Reference](features.md). For getting started, see [Getting Started](getting-started.md).*
