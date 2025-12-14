# MCP Audit v1.7.0 Session Schema

**Version**: 1.7.0
**Last Updated**: 2025-12-14
**Status**: Active (shipped in v0.8.0)

This document defines the v1.7.0 session JSON schema, extending v1.6.0 with expanded smell taxonomy, recommendations engine, and cross-session aggregation.

---

## Schema Overview

The session schema is the canonical format for MCP Audit session logs stored in `~/.mcp-audit/sessions/`.

### What's New in v1.5.0

| Feature | v1.4.0 | v1.5.0 |
|---------|--------|--------|
| Smell detection | Not tracked | `smells` array with 5 smell types |
| Data quality | Implicit | Explicit `data_quality` block |
| Message count | Not tracked | `session.message_count` field |
| Zombie tools | Not tracked | `zombie_tools` block |
| Platform capabilities | Not tracked | `platform_capabilities` block |
| Static cost (v0.6.0+) | Not tracked | `static_cost` block |

---

## Complete Schema

```json
{
  "_file": {
    "name": "zen-mcp-2025-12-07T14-32-05.json",
    "type": "mcp_audit_session",
    "purpose": "Complete MCP session log with token usage, tool call statistics, and smell detection for AI agent analysis",
    "schema_version": "1.5.0",
    "schema_docs": "https://github.com/littlebearapps/mcp-audit/blob/main/docs/v1-session-schema.md",
    "generated_by": "mcp-audit v0.5.0",
    "generated_at": "2025-12-07T14:44:55+11:00"
  },

  "session": {
    "id": "zen-mcp-2025-12-07T14-32-05",
    "project": "zen-mcp",
    "platform": "claude-code",
    "model": "claude-opus-4-5-20251101",
    "working_directory": "/Users/user/projects/zen-mcp/main",
    "started_at": "2025-12-07T14:32:05+11:00",
    "ended_at": "2025-12-07T14:44:55+11:00",
    "duration_seconds": 770.0,
    "message_count": 45,
    "source_files": ["session-abc123.jsonl"]
  },

  "data_quality": {
    "level": "exact",
    "token_source": "native",
    "estimation_error_pct": null,
    "notes": null
  },

  "token_usage": {
    "input_tokens": 76000,
    "output_tokens": 12000,
    "reasoning_tokens": 0,
    "cache_created_tokens": 3925,
    "cache_read_tokens": 854215,
    "total_tokens": 342110,
    "cache_efficiency": 0.995
  },

  "cost_estimate_usd": 1.23,
  "cost_no_cache_usd": 2.45,
  "cache_savings_usd": 1.22,

  "mcp_summary": {
    "total_calls": 22,
    "total_tokens": 245000,
    "mcp_share": 0.72,
    "unique_tools": 4,
    "unique_servers": 2,
    "servers_used": ["zen", "brave-search"],
    "top_by_tokens": [
      {"tool": "mcp__zen__thinkdeep", "server": "zen", "tokens": 144000, "calls": 5}
    ],
    "top_by_calls": [
      {"tool": "mcp__brave-search__brave_web_search", "server": "brave-search", "calls": 14, "tokens": 89000}
    ]
  },

  "builtin_tool_summary": {
    "total_calls": 15,
    "total_tokens": 97110,
    "tools": [
      {"tool": "Read", "calls": 5, "tokens": 45000},
      {"tool": "Bash", "calls": 4, "tokens": 35000}
    ]
  },

  "smells": [
    {
      "id": "HIGH_VARIANCE",
      "severity": "warning",
      "tool": "mcp__zen__thinkdeep",
      "server": "zen",
      "p95": 37519,
      "median": 11202
    },
    {
      "id": "TOP_CONSUMER",
      "severity": "warning",
      "tool": "mcp__zen__thinkdeep",
      "server": "zen",
      "share": 0.46
    },
    {
      "id": "CHATTY",
      "severity": "info",
      "tool": "mcp__brave-search__brave_web_search",
      "server": "brave-search",
      "calls": 14
    }
  ],

  "cache_analysis": {
    "status": "efficient",
    "summary": "Cache saved $1.22. Created 3,925 tokens, read 854,215 tokens (ratio: 217.63).",
    "creation_tokens": 3925,
    "read_tokens": 854215,
    "ratio": 217.63,
    "net_savings_usd": 1.22
  },

  "tool_calls": [
    {
      "index": 1,
      "timestamp": "2025-12-07T14:32:15+11:00",
      "tool": "mcp__zen__thinkdeep",
      "server": "zen",
      "input_tokens": 8000,
      "output_tokens": 29519,
      "cache_created_tokens": 500,
      "cache_read_tokens": 80000,
      "total_tokens": 37519,
      "duration_ms": 12500,
      "content_hash": "a1b2c3d4...",
      "is_estimated": false
    }
  ],

  "analysis": {
    "redundancy": {
      "duplicate_calls": 0,
      "potential_token_savings": 0
    },
    "anomalies": []
  }
}
```

---

## New Fields in v1.5.0

### `data_quality` Block

Indicates token data accuracy for this session. Enables the TUI to display appropriate quality labels.

| Field | Type | Description |
|-------|------|-------------|
| `level` | string | `"exact"`, `"estimated"`, or `"calls_only"` |
| `token_source` | string | `"native"`, `"tiktoken"`, `"sentencepiece"`, or `"none"` |
| `estimation_error_pct` | float\|null | Estimated error margin (e.g., `6.0` for ~6%) |
| `notes` | string\|null | Platform-specific notes |

#### Platform-Specific Values

| Platform | `level` | `token_source` | `estimation_error_pct` |
|----------|---------|----------------|------------------------|
| Claude Code | `"exact"` | `"native"` | `null` |
| Codex CLI | `"estimated"` | `"tiktoken"` | `1.0` to `5.0` |
| Gemini CLI | `"estimated"` | `"sentencepiece"` | `5.0` to `10.0` |
| Ollama | `"calls_only"` | `"none"` | `null` |

#### TUI Display Mapping

| `level` | TUI Display |
|---------|-------------|
| `"exact"` | `exact` |
| `"estimated"` | `~N%` (uses `estimation_error_pct`) |
| `"calls_only"` | `calls` |

---

### `smells` Array

List of detected smell indicators. Smells are attention cues - they do NOT provide recommendations.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Smell type identifier |
| `severity` | string | `"warning"` or `"info"` |
| `tool` | string | Full tool name (e.g., `mcp__zen__thinkdeep`) |
| `server` | string | MCP server name |
| (varies) | varies | Additional fields per smell type |

#### Smell Types

| ID | Severity | Trigger | Additional Fields |
|----|----------|---------|-------------------|
| `HIGH_VARIANCE` | warning | P95 > median × 2.0 | `p95`, `median` |
| `TOP_CONSUMER` | warning | tool_tokens >= 25% of MCP tokens | `share` |
| `HIGH_MCP_SHARE` | warning | mcp_share > 60% | `mcp_share` |
| `CHATTY` | info | calls > 10 | `calls` |
| `LOW_CACHE_HIT` | info | cache_hit_rate < 15% | `cache_hit_rate` |

#### Platform Support

| Smell | Claude Code | Codex CLI | Gemini CLI |
|-------|-------------|-----------|------------|
| HIGH_VARIANCE | Native | Estimated | Estimated |
| TOP_CONSUMER | Native | Estimated | Estimated |
| HIGH_MCP_SHARE | Calculable | Calculable | Calculable |
| CHATTY | Yes | Yes | Yes |
| LOW_CACHE_HIT | Yes | No | No |

---

### `session.message_count` Field

New optional field tracking the number of conversation messages/turns in the session.

| Field | Type | Description |
|-------|------|-------------|
| `message_count` | int\|null | Number of messages in session |

---

### `zombie_tools` Block (v0.5.0+)

Tracks tools defined but never called during the session:

```json
"zombie_tools": {
  "defined_count": 12,
  "called_count": 4,
  "unused_count": 8,
  "unused": [
    {"server": "zen", "tool": "consensus"},
    {"server": "zen", "tool": "planner"}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `defined_count` | int | Total tools available across all MCP servers |
| `called_count` | int | Number of tools actually invoked |
| `unused_count` | int | `defined_count - called_count` |
| `unused` | array | List of unused tools with server and tool name |

---

### `platform_capabilities` Block (v0.5.0+)

Metadata about what the platform can provide:

```json
"platform_capabilities": {
  "per_tool_tokens": "exact",
  "session_tokens": "exact",
  "cache_metrics": true,
  "reasoning_tokens": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `per_tool_tokens` | string | `"exact"`, `"estimated"`, or `"unsupported"` |
| `session_tokens` | string | `"exact"`, `"estimated"`, or `"unsupported"` |
| `cache_metrics` | bool | Whether cache read/create is available |
| `reasoning_tokens` | bool | Whether thinking tokens are tracked separately |

---

### `static_cost` Block (v0.6.0+)

Tracks the "context tax" - tokens consumed by tool definitions:

```json
"static_cost": {
  "schema_tokens": 1240,
  "tool_count": 12,
  "servers": [
    {"name": "zen", "schema_tokens": 850, "tool_count": 8},
    {"name": "brave-search", "schema_tokens": 390, "tool_count": 4}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `schema_tokens` | int | Total tokens for all tool definitions |
| `tool_count` | int | Number of tools defined |
| `servers` | array | Per-server breakdown |

**Note:** This field requires parsing `list_tools` output, which may not be available on all platforms. Field is omitted when data is unavailable.

---

## Backward Compatibility

v1.5.0 is fully backward compatible with v1.4.0:

- **New fields are additive** - Old readers ignore `data_quality`, `smells`, `message_count`, `zombie_tools`, etc.
- **Existing fields unchanged** - All v1.4.0 fields retain their meaning
- **Optional by default** - Missing new fields have sensible defaults

### Reading Old Sessions

When loading v1.4.0 or earlier sessions:

| Missing Field | Default Value |
|---------------|---------------|
| `data_quality` | Inferred from `is_estimated` in tool_calls |
| `smells` | Empty array `[]` |
| `session.message_count` | `null` |

### Writing New Sessions

v1.5.0 writers should:

1. Always include `data_quality` block
2. Always include `smells` array (empty if no smells detected)
3. Include `message_count` if available from platform

---

## Schema Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.5.0 | 2025-12-07 | Added `data_quality`, `smells`, `message_count`, `zombie_tools`, `platform_capabilities`, `static_cost` |
| 1.4.0 | 2025-12-07 | Added token estimation fields |
| 1.3.0 | 2025-12-06 | Added `reasoning_tokens` |
| 1.2.0 | 2025-12-05 | Added `builtin_tool_summary` |
| 1.1.0 | 2025-12-01 | Single-file format, flat `tool_calls` |
| 1.0.0 | 2025-11-25 | Initial release |

---

## Related Documentation

- [Data Contract](data-contract.md) - Backward compatibility guarantees
- [AI Export Schema](ai-export-schema.md) - Compact format for AI analysis
- [Smell Engine Spec](ideas/mcp-audit-smell-engine-spec.md) - Smell detection rules
