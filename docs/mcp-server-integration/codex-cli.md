# Using token-audit as an MCP Server in Codex CLI

This guide explains how to configure token-audit as an MCP server that Codex CLI can connect to, enabling real-time efficiency monitoring and optimization guidance from within your AI sessions.

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Config File** | `~/.codex/config.toml` |
| **Config Format** | TOML |
| **Transport** | stdio |
| **Entry Point** | `token-audit-server` |
| **Tools Available** | 8 |
| **Min Version** | token-audit v1.0.0+ |

---

## Prerequisites

- **token-audit v1.0+** installed with server extras
- **Codex CLI** installed (`npm install -g @openai/codex`)
- **Python 3.8+** installed

---

## Installation

Install token-audit with server dependencies:

```bash
# Using pipx (recommended)
pipx install 'token-audit[server]'

# Or using pip
pip install 'token-audit[server]'
```

Verify the server is available:

```bash
token-audit-server --help
```

---

## Configuration

Codex CLI uses TOML format for MCP server configuration. Edit `~/.codex/config.toml`:

### Basic Configuration

```toml
[mcp_servers.token-audit]
command = "token-audit-server"
args = []
```

### With Full Path

If `token-audit-server` isn't in your PATH:

```toml
[mcp_servers.token-audit]
command = "/path/to/venv/bin/token-audit-server"
args = []
```

### Using Python Module

Alternative approach using Python directly:

```toml
[mcp_servers.token-audit]
command = "python"
args = ["-m", "token_audit.server"]
```

### With Environment Variables

```toml
[mcp_servers.token-audit]
command = "token-audit-server"
args = []

[mcp_servers.token-audit.env]
TOKEN_AUDIT_LOG_LEVEL = "DEBUG"
```

### Complete Example

Here's a complete `config.toml` with token-audit alongside other servers:

```toml
model = "gpt-5.1"

[mcp_servers.token-audit]
command = "token-audit-server"
args = []

[mcp_servers.brave-search]
command = "npx"
args = ["-y", "@anthropic/mcp-server-brave-search"]

[mcp_servers.brave-search.env]
BRAVE_API_KEY = "your-api-key"
```

---

## Verifying Installation

1. **Start Codex CLI**:
   ```bash
   codex
   ```

2. **List MCP servers**:
   ```bash
   codex mcp list
   ```

3. **Look for token-audit** in the output:
   ```
   token-audit
     command: token-audit-server
     enabled: true
     transport: stdio
   ```

4. **Or ask Codex** to verify:
   > "What MCP servers do I have configured?"

---

## Available Tools

The token-audit MCP server provides 8 tools for efficiency monitoring and optimization:

### Session Tracking

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `start_tracking` | Begin live session tracking | `platform`, `project` |
| `get_metrics` | Query current session statistics | `session_id`, `include_smells`, `include_breakdown` |
| `analyze_session` | Comprehensive end-of-session analysis | `session_id`, `format`, `include_zombie_tools` |

### Optimization

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `get_recommendations` | Get optimization recommendations | `session_id`, `severity_filter`, `max_recommendations` |
| `get_trends` | Cross-session pattern analysis | `period`, `platform` |

### Configuration & Best Practices

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `analyze_config` | Analyze MCP configuration files | `platform`, `config_path` |
| `get_pinned_servers` | Get user's pinned MCP servers | `include_auto_detected`, `platform` |
| `get_best_practices` | Retrieve MCP best practices guidance | `topic`, `list_all` |

---

## Usage Examples

### Start Tracking Your Session

Ask Codex:

> "Start tracking this session with token-audit"

Codex will call `start_tracking` with `platform="codex_cli"`.

### Check Current Metrics

> "How many tokens have I used so far?"

Codex will call `get_metrics` and show your usage.

### Get Optimization Recommendations

> "What can I do to reduce my token costs?"

Codex will call `get_recommendations` and provide actionable suggestions.

### Analyze Your MCP Configuration

> "Analyze my Codex MCP configuration for issues"

Codex will call `analyze_config` with `platform="codex_cli"` to detect:
- Hardcoded credentials in config.toml
- Excessive number of servers
- Context tax estimates
- Server misconfigurations

### Learn Best Practices

> "What are the best practices for caching in MCP servers?"

Codex will call `get_best_practices` with `topic="caching_strategy"`.

Available topics:
- `progressive_disclosure` — Gradual tool/field exposure
- `security` — Credential handling
- `tool_design` — Tool API design principles
- `caching_strategy` — Caching techniques
- `large_results` — Handling large response payloads
- `schema_versioning` — Schema evolution management
- `error_handling` — Error response patterns
- `async_operations` — Asynchronous tool execution
- `statelessness` — Stateless server design
- `tool_count_limits` — Optimal tool portfolio size

### View Cross-Session Trends

> "Show me my token usage patterns over the last week"

Codex will call `get_trends` with `period="last_7_days"`.

---

## Example Workflow

### 1. Start Your Session

```
You: Start tracking this Codex session
Codex: I've started tracking your session. Session ID: codex-20251217-abc123
```

### 2. Work Normally

Do your coding work. token-audit monitors in the background.

### 3. Check Progress

```
You: Show me my current token usage
Codex: Current session metrics:
  - Input tokens: 32,150
  - Output tokens: 8,420
  - Cached tokens: 89,000 (68% cache hit rate)
  - Estimated cost: $0.08

  Top token consumers:
  1. mcp__zen__thinkdeep: 45K tokens (2 calls)
  2. mcp__brave-search__brave_web_search: 23K tokens (5 calls)
```

### 4. Get Recommendations

```
You: How can I optimize my token usage?
Codex: Based on your session:

  HIGH: Consider consolidating thinkdeep calls
  - You made 2 calls with similar context
  - Potential savings: ~20K tokens

  MEDIUM: brave-search queries could be batched
  - 5 separate searches on related topics
  - Consider using a single comprehensive query
```

---

## Troubleshooting

### Server Not Listed in `codex mcp list`

**Symptom**: token-audit doesn't appear in server list

**Solutions**:

1. **Check TOML syntax** (must be valid):
   ```bash
   cat ~/.codex/config.toml
   # Verify [mcp_servers.token-audit] section exists
   ```

2. **Verify command is accessible**:
   ```bash
   which token-audit-server
   ```

3. **Try full path** if not in PATH:
   ```toml
   [mcp_servers.token-audit]
   command = "/Users/you/.local/bin/token-audit-server"
   ```

### Tools Not Working

**Symptom**: Server appears but tools return errors

**Solutions**:

1. **Check server extras installed**:
   ```bash
   pip show token-audit
   ```

2. **Reinstall with server extras**:
   ```bash
   pip install 'token-audit[server]' --force-reinstall
   ```

### TOML Syntax Errors

**Symptom**: Codex won't start or shows config errors

**Common issues**:

```toml
# WRONG - missing quotes around value with special chars
[mcp_servers.token-audit.env]
API_KEY = abc-123-def

# CORRECT
[mcp_servers.token-audit.env]
API_KEY = "abc-123-def"
```

```toml
# WRONG - using JSON-style arrays
args = ["-y", "server"]

# CORRECT (this is actually fine in TOML)
args = ["-y", "server"]
```

### Session Tracking Not Starting

**Symptom**: `start_tracking` returns error

**Solutions**:

1. **Check Codex sessions exist**:
   ```bash
   ls ~/.codex/sessions/
   ```

2. **Specify platform explicitly**:
   > "Start tracking with platform codex_cli"

---

## Managing MCP Servers with Codex CLI

Codex provides built-in commands for MCP management:

```bash
# List all configured servers
codex mcp list

# Get details about a specific server
codex mcp get token-audit

# Remove a server (if needed)
codex mcp remove token-audit
```

You can also manage servers via the config file directly.

---

## See Also

- [MCP Server Guide](../mcp-server-guide.md) — Full tool reference with input/output schemas
- [Platform Guide: Codex CLI](../platforms/codex-cli.md) — CLI monitoring mode
- [OpenAI Codex MCP Docs](https://developers.openai.com/codex/mcp/) — Official Codex MCP documentation
- [Troubleshooting](../troubleshooting.md) — Common issues and solutions

---

## MCP Server Mode vs CLI Mode

| Aspect | MCP Server Mode | CLI Mode |
|--------|-----------------|----------|
| **Command** | `token-audit-server` (via config.toml) | `token-audit collect --platform codex-cli` |
| **Interface** | Natural language via AI | TUI dashboard |
| **Workflow** | Ask Codex for metrics | Watch separate terminal |
| **Best For** | Integrated monitoring | Dedicated tracking |

Both modes can be used together — CLI for visual monitoring, MCP server for conversational analysis.
