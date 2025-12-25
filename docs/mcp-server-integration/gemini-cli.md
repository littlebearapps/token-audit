# Using token-audit as an MCP Server in Gemini CLI

This guide explains how to configure token-audit as an MCP server that Gemini CLI can connect to, enabling real-time efficiency monitoring and optimization guidance from within your AI sessions.

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Config File** | `~/.gemini/settings.json` |
| **Config Format** | JSON |
| **Transport** | stdio |
| **Entry Point** | `token-audit-server` |
| **Tools Available** | 8 |
| **Min Version** | token-audit v1.0.0+ |

---

## Prerequisites

- **token-audit v1.0+** installed with server extras
- **Gemini CLI** installed (`npm install -g @google/gemini-cli`)
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

Gemini CLI uses JSON format for MCP server configuration. Edit `~/.gemini/settings.json`:

### Basic Configuration

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server"
    }
  }
}
```

### With Arguments

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server",
      "args": []
    }
  }
}
```

### With Full Path

If `token-audit-server` isn't in your PATH:

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "/path/to/venv/bin/token-audit-server"
    }
  }
}
```

### Using Python Module

Alternative approach using Python directly:

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "python",
      "args": ["-m", "token_audit.server"]
    }
  }
}
```

### With Environment Variables

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server",
      "args": [],
      "env": {
        "TOKEN_AUDIT_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### Complete Example

Here's a complete `settings.json` with token-audit alongside other servers:

```json
{
  "security": {
    "auth": {
      "selectedType": "oauth-personal"
    }
  },
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server"
    },
    "fs": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]
    }
  }
}
```

---

## Verifying Installation

1. **Start Gemini CLI** in your project directory:
   ```bash
   gemini
   ```

2. **Run `/mcp`** to list connected servers

3. **Look for token-audit** in the output:
   ```
   MCP Servers:
     token-audit (connected)
       Tools: start_tracking, get_metrics, get_recommendations, ...
   ```

4. **Or ask Gemini** to verify:
   > "What MCP servers are available?"

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

Ask Gemini:

> "Start tracking this session with token-audit"

Gemini will call `start_tracking` with `platform="gemini_cli"`.

### Check Current Metrics

> "How many tokens have I used in this session?"

Gemini will call `get_metrics` and show your usage.

### Get Optimization Recommendations

> "What recommendations do you have for reducing my token costs?"

Gemini will call `get_recommendations` and provide actionable suggestions.

### Analyze Your MCP Configuration

> "Analyze my Gemini MCP configuration for any issues"

Gemini will call `analyze_config` with `platform="gemini_cli"` to detect:
- Hardcoded credentials in settings.json
- Excessive number of servers
- Context tax estimates
- Server misconfigurations

### Learn Best Practices

> "What are the best practices for handling large results in MCP?"

Gemini will call `get_best_practices` with `topic="large_results"`.

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

> "Show me my token usage trends over the last month"

Gemini will call `get_trends` with `period="last_30_days"`.

---

## Example Workflow

### 1. Start Your Session

```
You: Start tracking this Gemini session
Gemini: I've started tracking your session. You can ask for metrics at any time.
```

### 2. Work Normally

Do your coding work. token-audit monitors in the background.

### 3. Check Progress

```
You: What's my current token usage?
Gemini: Current session metrics:
  - Input tokens: 125,432
  - Output tokens: 8,543
  - Cached tokens: 45,000 (26% cache hit rate)
  - Reasoning tokens: 12,340
  - Estimated cost: $0.18

  Top token consumers:
  1. mcp__zen__chat: 34K tokens (5 calls)
  2. mcp__jina__read_url: 28K tokens (3 calls)
```

### 4. Get Recommendations

```
You: How can I improve my efficiency?
Gemini: Based on your session analysis:

  HIGH: Low cache hit rate (26%)
  - Your context is changing frequently
  - Consider keeping related work in the same session

  MEDIUM: jina/read_url fetching large pages
  - 3 calls averaging 9K tokens each
  - Consider extracting specific sections instead of full pages
```

---

## Troubleshooting

### Server Not Appearing in `/mcp`

**Symptom**: token-audit not listed when running `/mcp`

**Solutions**:

1. **Check JSON syntax** (must be valid):
   ```bash
   cat ~/.gemini/settings.json | python -m json.tool
   ```

2. **Verify command is accessible**:
   ```bash
   which token-audit-server
   ```

3. **Try full path** if not in PATH:
   ```json
   {
     "mcpServers": {
       "token-audit": {
         "command": "/Users/you/.local/bin/token-audit-server"
       }
     }
   }
   ```

4. **Restart Gemini CLI** after config changes

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

### JSON Syntax Errors

**Symptom**: Gemini won't start or shows config errors

**Common issues**:

```json
// WRONG - trailing comma
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server",  // <-- trailing comma before }
    }
  }
}

// CORRECT
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server"
    }
  }
}
```

```json
// WRONG - single quotes
{
  'mcpServers': {
    'token-audit': {
      'command': 'token-audit-server'
    }
  }
}

// CORRECT - double quotes only
{
  "mcpServers": {
    "token-audit": {
      "command": "token-audit-server"
    }
  }
}
```

### Session Tracking Not Starting

**Symptom**: `start_tracking` returns error

**Solutions**:

1. **Check Gemini sessions exist**:
   ```bash
   ls ~/.gemini/tmp/
   ```

2. **Run from correct directory** (Gemini uses directory hash):
   ```bash
   cd /path/to/your/project
   gemini
   ```

3. **Specify platform explicitly**:
   > "Start tracking with platform gemini_cli"

### Project Hash Issues

Gemini CLI uses a SHA256 hash of your project directory. If sessions aren't found:

1. **Calculate your project hash**:
   ```bash
   python -c "import hashlib; print(hashlib.sha256(str('$(pwd)').encode()).hexdigest())"
   ```

2. **Check if sessions exist for that hash**:
   ```bash
   ls ~/.gemini/tmp/<hash>/chats/
   ```

---

## Managing MCP Servers with Gemini CLI

Gemini CLI provides built-in commands for MCP management:

```bash
# Add a new MCP server
gemini mcp add token-audit --command "token-audit-server"

# List configured servers
gemini mcp list

# Remove a server
gemini mcp remove token-audit
```

You can also manage servers by editing `~/.gemini/settings.json` directly.

---

## See Also

- [MCP Server Guide](../mcp-server-guide.md) — Full tool reference with input/output schemas
- [Platform Guide: Gemini CLI](../platforms/gemini-cli.md) — CLI monitoring mode
- [Gemini CLI MCP Docs](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html) — Official Gemini MCP documentation
- [Troubleshooting](../troubleshooting.md) — Common issues and solutions

---

## MCP Server Mode vs CLI Mode

| Aspect | MCP Server Mode | CLI Mode |
|--------|-----------------|----------|
| **Command** | `token-audit-server` (via settings.json) | `token-audit collect --platform gemini-cli` |
| **Interface** | Natural language via AI | TUI dashboard |
| **Workflow** | Ask Gemini for metrics | Watch separate terminal |
| **Best For** | Integrated monitoring | Dedicated tracking |

Both modes can be used together — CLI for visual monitoring, MCP server for conversational analysis.
