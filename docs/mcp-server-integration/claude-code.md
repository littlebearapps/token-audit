# Using token-audit as an MCP Server in Claude Code

This guide explains how to configure token-audit as an MCP server that Claude Code can connect to, enabling real-time efficiency monitoring and optimization guidance from within your AI sessions.

---

## Quick Facts

| Aspect | Value |
|--------|-------|
| **Config File** | `.mcp.json` (project) or `~/.claude/settings.json` (global) |
| **Config Format** | JSON |
| **Transport** | stdio |
| **Entry Point** | `token-audit-server` |
| **Tools Available** | 8 |
| **Min Version** | token-audit v1.0.0+ |

---

## Prerequisites

- **token-audit v1.0+** installed with server extras
- **Claude Code** installed and working
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

### Project-Level (Recommended)

Add token-audit to your project's `.mcp.json` file:

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

This makes token-audit available only in this project.

### Global Level

Add to `~/.claude/settings.json` to make token-audit available in all projects:

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

### With Custom Python Path

If token-audit-server isn't in your PATH, specify the full path:

```json
{
  "mcpServers": {
    "token-audit": {
      "command": "/path/to/venv/bin/token-audit-server",
      "args": []
    }
  }
}
```

Or use Python directly:

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

---

## Verifying Installation

1. **Start Claude Code** in your project directory
2. **Run `/mcp`** to list connected servers
3. **Look for `token-audit`** in the server list

You should see output like:

```
MCP Servers:
  token-audit (connected)
    - start_tracking
    - get_metrics
    - get_recommendations
    - analyze_session
    - get_best_practices
    - analyze_config
    - get_pinned_servers
    - get_trends
```

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

Ask Claude Code:

> "Start tracking this session so I can see my token usage"

Claude Code will call `start_tracking` and begin monitoring.

### Check Current Metrics

> "How many tokens have I used so far? Show me the breakdown by tool."

Claude Code will call `get_metrics` with `include_breakdown=true`.

### Get Optimization Recommendations

> "What can I do to reduce my token costs in this session?"

Claude Code will call `get_recommendations` and provide actionable suggestions.

### Analyze Your MCP Configuration

> "Analyze my MCP configuration for any issues or security problems"

Claude Code will call `analyze_config` to detect:
- Hardcoded credentials
- Excessive number of servers
- Context tax estimates
- Server misconfigurations

### Learn Best Practices

> "What are the best practices for MCP tool design?"

Claude Code will call `get_best_practices` with `topic="tool_design"`.

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

> "Show me my token usage trends over the last 30 days"

Claude Code will call `get_trends` with `period="last_30_days"`.

---

## Example Workflow

Here's a typical workflow using token-audit as an MCP server:

### 1. Start Your Session

```
You: Start tracking this session
Claude: I've started tracking your session. You can ask for metrics at any time.
```

### 2. Work Normally

Do your coding work. token-audit monitors in the background.

### 3. Check Progress

```
You: How many tokens have I used?
Claude: Current session metrics:
  - Input tokens: 45,231
  - Output tokens: 12,543
  - Cached tokens: 125,432 (73% cache hit rate)
  - Estimated cost: $0.15

  Top token consumers:
  1. mcp__zen__thinkdeep: 112K tokens (3 calls)
  2. mcp__brave-search__brave_web_search: 45K tokens (8 calls)
```

### 4. Get Optimization Tips

```
You: Any recommendations to reduce costs?
Claude: Based on your session analysis:

  HIGH: Consider batching your zen/thinkdeep calls
  - Evidence: 3 separate calls averaging 37K tokens each
  - Potential savings: ~30% by combining related questions

  MEDIUM: High cache miss rate on brave-search
  - Evidence: Only 45% cache hit rate
  - Suggestion: Reuse previous search results when possible
```

### 5. End-of-Session Analysis

```
You: Give me a full session analysis
Claude: [Comprehensive markdown report with metrics, recommendations, and trends]
```

---

## Troubleshooting

### Server Not Appearing in `/mcp`

**Symptom**: token-audit not listed when running `/mcp`

**Solutions**:

1. **Check installation**:
   ```bash
   which token-audit-server
   token-audit-server --help
   ```

2. **Verify config syntax** (JSON must be valid):
   ```bash
   cat .mcp.json | python -m json.tool
   ```

3. **Check Claude Code logs** for connection errors

4. **Try full path** in config if not in PATH

### Tools Not Available

**Symptom**: Server appears but tools don't work

**Solutions**:

1. **Verify server extras installed**:
   ```bash
   pip show token-audit
   # Should show [server] in extras
   ```

2. **Reinstall with server extras**:
   ```bash
   pip install 'token-audit[server]' --force-reinstall
   ```

### Permission Errors

**Symptom**: "Permission denied" or similar errors

**Solutions**:

1. **Check file permissions** on config files
2. **Ensure Python environment** is accessible
3. **Try using absolute paths** in configuration

### Tracking Not Starting

**Symptom**: `start_tracking` returns error

**Solutions**:

1. **Check platform sessions exist**:
   ```bash
   ls ~/.claude/projects/
   ```

2. **Ensure you're in a project** with Claude Code activity
3. **Try specifying platform explicitly**:
   ```
   "Start tracking with platform claude_code"
   ```

---

## Advanced Configuration

### Environment Variables

Pass environment variables to the server:

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

### Multiple Configurations

You can have different token-audit configurations per project by using project-level `.mcp.json` files.

---

## See Also

- [MCP Server Guide](../mcp-server-guide.md) — Full tool reference with input/output schemas
- [Platform Guide: Claude Code](../platforms/claude-code.md) — CLI monitoring mode
- [Best Practices](../guidance/) — MCP efficiency patterns
- [Troubleshooting](../troubleshooting.md) — Common issues and solutions

---

## MCP Server Mode vs CLI Mode

| Aspect | MCP Server Mode | CLI Mode |
|--------|-----------------|----------|
| **Command** | `token-audit-server` (via config) | `token-audit collect` |
| **Interface** | Natural language via AI | TUI dashboard |
| **Workflow** | Ask AI for metrics | Watch separate terminal |
| **Best For** | Integrated monitoring | Dedicated tracking |

Both modes can be used together — CLI for visual monitoring, MCP server for conversational analysis.
