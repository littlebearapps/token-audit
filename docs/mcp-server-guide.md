# MCP Server Guide

Token Audit v1.0+ can run as an MCP server, enabling your AI assistant to directly query efficiency metrics, get recommendations, and analyze your MCP configuration—all through natural language.

---

## Overview

**MCP Server Mode** provides 8 tools for real-time monitoring and optimization:

| Tool | Purpose |
|------|---------|
| `start_tracking` | Begin live session monitoring |
| `get_metrics` | Query current token usage, costs, cache stats, and detected smells |
| `get_recommendations` | Get optimization suggestions based on detected patterns |
| `analyze_session` | Comprehensive end-of-session analysis |
| `get_best_practices` | Retrieve MCP efficiency best practices |
| `analyze_config` | Analyze MCP configuration files for issues |
| `get_pinned_servers` | Get user's pinned/frequently-used MCP servers |
| `get_trends` | Cross-session pattern analysis over time |

### MCP Server Mode vs CLI Mode

| Aspect | MCP Server Mode | CLI Mode |
|--------|-----------------|----------|
| **Command** | Via AI assistant | `token-audit collect` |
| **Interface** | Natural language | TUI dashboard |
| **Real-time** | Yes | Yes |
| **Best For** | Integrated monitoring | Dedicated tracking |

Both modes can be used together—CLI for visual monitoring, MCP server for conversational analysis.

---

## Quick Start

### 1. Install with Server Support

```bash
# Using pipx (recommended)
pipx install 'token-audit[server]'

# Or using pip
pip install 'token-audit[server]'
```

Verify installation:

```bash
token-audit-server --help
```

### 2. Configure Your AI CLI

**Claude Code** (`.mcp.json`):

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

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.token-audit]
command = "token-audit-server"
args = []
```

**Gemini CLI** (`~/.gemini/settings.json`):

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

### 3. Verify Connection

Start your AI CLI and run the MCP status command (e.g., `/mcp` in Claude Code). You should see `token-audit` listed with 8 tools.

---

## Tool Reference

### start_tracking

Begin live session tracking for a platform.

**Input Schema:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `platform` | enum | Yes | `claude_code`, `codex_cli`, or `gemini_cli` |
| `project` | string | No | Project name for grouping sessions |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `platform` | string | Platform being tracked |
| `project` | string | Project name (if specified) |
| `started_at` | string | ISO 8601 timestamp |
| `status` | enum | `active` or `error` |
| `message` | string | Human-readable status |

**Example:**

> "Start tracking this Claude Code session for my token-audit project"

---

### get_metrics

Query current session statistics including tokens, costs, rates, cache efficiency, and detected smells.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | No | active session | Session to query |
| `include_smells` | boolean | No | `true` | Include detected efficiency issues |
| `include_breakdown` | boolean | No | `true` | Include per-tool/per-server breakdown |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session being reported |
| `tokens` | object | Token breakdown (input, output, cache_read, cache_write, total) |
| `cost_usd` | float | Estimated cost in USD |
| `rates` | object | Rate metrics (tokens_per_min, calls_per_min, duration_minutes) |
| `cache` | object | Cache metrics (hit_ratio, savings_tokens, savings_usd) |
| `smells` | array | Detected efficiency issues |
| `tool_count` | int | Number of unique tools used |
| `call_count` | int | Total tool calls |
| `model_usage` | object | Per-model breakdown |

**Example:**

> "How many tokens have I used? Show me the breakdown by tool."

---

### get_recommendations

Get optimization suggestions based on detected patterns.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | No | active session | Session to analyze |
| `severity_filter` | enum | No | all | Minimum severity: `critical`, `high`, `medium`, `low`, `info` |
| `max_recommendations` | int | No | 5 | Maximum recommendations to return |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session analyzed |
| `recommendations` | array | Prioritized list of recommendations |
| `total_potential_savings_tokens` | int | Estimated token savings if all applied |
| `total_potential_savings_usd` | float | Estimated cost savings if all applied |

Each recommendation includes:
- `id`: Unique identifier
- `severity`: Importance level
- `category`: Recommendation category
- `title`: Short title
- `action`: Recommended action
- `impact`: Expected impact
- `evidence`: Supporting metrics
- `confidence`: Confidence score (0.0-1.0)
- `affects_pinned_server`: Whether it affects a pinned server
- `pinned_server_name`: Name of affected pinned server (if any)

**Example:**

> "What can I do to reduce my token costs?"

---

### analyze_session

Comprehensive end-of-session analysis with metrics, recommendations, and zombie tool detection.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | No | active session | Session to analyze |
| `format` | enum | No | `json` | Output format: `json`, `markdown`, `summary` |
| `include_model_usage` | boolean | No | `true` | Include per-model breakdown |
| `include_zombie_tools` | boolean | No | `true` | Include unused tool analysis |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session analyzed |
| `summary` | string | Human-readable summary |
| `metrics` | object | Full metrics (same as get_metrics output) |
| `recommendations` | array | Optimization recommendations |
| `zombie_tools` | array | Tools available but never used |
| `model_usage` | object | Per-model usage breakdown |
| `pinned_server_usage` | array | Usage statistics for pinned servers |

**Example:**

> "Give me a full analysis of this session"

---

### get_best_practices

Retrieve MCP efficiency best practices guidance.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `topic` | string | No | null | Topic to search for |
| `list_all` | boolean | No | `false` | List all available topics |

**Available Topics:**
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

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `practices` | array | Matching best practices |
| `total_available` | int | Total practices in database |

Each practice includes:
- `id`: Practice identifier
- `title`: Practice title
- `severity`: Importance level
- `category`: Category (efficiency, security, design, operations)
- `token_savings`: Estimated savings (e.g., "98%")
- `source`: Reference source
- `content`: Full markdown content
- `keywords`: Related keywords
- `related_smells`: Smell patterns this addresses

**Example:**

> "What are the best practices for MCP tool design?"

---

### analyze_config

Analyze MCP configuration files for issues, estimate context tax, and identify pinned servers.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `platform` | enum | No | all | Platform to analyze: `claude_code`, `codex_cli`, `gemini_cli` |
| `config_path` | string | No | default location | Custom config file path (restricted to `~/.claude/`, `~/.codex/`, `~/.gemini/`) |

> **Security Note:** Custom paths are validated to prevent path traversal attacks. Only paths within `~/.claude/`, `~/.codex/`, or `~/.gemini/` are allowed. See [Security](security.md) for details.

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `platform` | string | Platform analyzed |
| `config_path` | string | Config file path |
| `issues` | array | Detected configuration issues |
| `servers` | array | Configured MCP servers |
| `server_count` | int | Total number of servers |
| `pinned_servers` | array | Pinned servers with detection details |
| `context_tax_estimate` | int | Estimated tokens consumed by all server schemas |

Each issue includes:
- `severity`: Issue severity
- `category`: Issue category
- `message`: Human-readable description
- `location`: Config file and key path
- `recommendation`: How to fix

**Example:**

> "Analyze my MCP configuration for any issues or security problems"

---

### get_pinned_servers

Get user's pinned MCP servers based on configuration and usage patterns.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_auto_detected` | boolean | No | `true` | Include auto-detected pinned servers |
| `platform` | enum | No | all | Platform to analyze |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `servers` | array | Pinned servers with detection details |
| `total_pinned` | int | Total pinned servers |
| `auto_detect_enabled` | boolean | Whether auto-detection is enabled |

Each server includes:
- `name`: Server name
- `source`: Detection method (auto_detect_local, explicit, high_usage)
- `reason`: Human-readable explanation
- `path`: Server path (if local/custom)
- `notes`: User notes
- `token_share`: Token share for high_usage detection

**Example:**

> "What MCP servers do I use most frequently?"

---

### get_trends

Cross-session pattern analysis over time.

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `period` | enum | No | `last_30_days` | Time period: `last_7_days`, `last_30_days`, `last_90_days`, `all_time` |
| `platform` | enum | No | all | Filter by platform |

**Output Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `period` | string | Analysis period |
| `sessions_analyzed` | int | Number of sessions in period |
| `patterns` | array | Trend data per smell pattern |
| `top_affected_tools` | array | Tools most frequently involved in issues |
| `overall_trend` | enum | `improving`, `stable`, or `worsening` |
| `recommendations` | array | High-level recommendations based on trends |

Each pattern includes:
- `pattern`: Smell pattern identifier
- `occurrences`: Number of occurrences
- `trend`: Direction (improving, stable, worsening)
- `change_percent`: Percentage change from previous period

**Example:**

> "Show me my token usage trends over the last 30 days"

---

## Workflow Examples

### Real-time Monitoring

```
1. "Start tracking this Claude Code session"
2. [Work normally with your AI assistant]
3. "How many tokens have I used so far?"
4. "Any recommendations to reduce costs?"
5. "Give me a full session analysis"
```

### Configuration Audit

```
1. "Analyze my MCP configuration for issues"
2. "What's my estimated context tax?"
3. "Which MCP servers should I consider removing?"
```

### Learning Best Practices

```
1. "What are MCP best practices for caching?"
2. "How can I design tools to minimize tokens?"
3. "List all available best practice topics"
```

### Trend Analysis

```
1. "Show me my efficiency trends over the last 90 days"
2. "Which tools are causing the most issues?"
3. "Is my token usage improving or getting worse?"
```

---

## Platform-Specific Setup

For detailed setup instructions per platform:

- [Claude Code Setup](mcp-server-integration/claude-code.md)
- [Codex CLI Setup](mcp-server-integration/codex-cli.md)
- [Gemini CLI Setup](mcp-server-integration/gemini-cli.md)

---

## Troubleshooting

### Server Not Appearing

1. Verify installation: `token-audit-server --help`
2. Check config syntax (JSON/TOML must be valid)
3. Try using full path: `/path/to/venv/bin/token-audit-server`
4. Check AI CLI logs for connection errors

### Tools Not Working

1. Verify server extras installed: `pip show token-audit`
2. Reinstall: `pip install 'token-audit[server]' --force-reinstall`

### Tracking Not Starting

1. Check platform sessions exist in expected locations
2. Ensure you're in a project with AI CLI activity
3. Try specifying platform explicitly

See [Troubleshooting Guide](troubleshooting.md) for more solutions.

---

## See Also

- [README](../README.md) — Project overview
- [Architecture](architecture.md) — System design
- [Security](security.md) — Security considerations and measures
- [API Reference](api.md) — Programmatic usage
- [Migration Guide](migration-v1.0.md) — Upgrading from v0.9.x
