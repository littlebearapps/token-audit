# Token Audit Data Contract

**Version**: 1.7.0
**Last Updated**: 2025-12-13
**Status**: Active (shipped in v1.0.3)

This document defines the data contract for Token Audit, including backward compatibility guarantees, versioning policy, and migration guidelines.

---

## Table of Contents

1. [JSON Schema Validation](#json-schema-validation)
2. [Schema v1.7.0](#schema-v170)
3. [Schema v1.6.0](#schema-v160)
4. [Schema v1.5.0](#schema-v150)
5. [Schema v1.4.0](#schema-v140)
6. [Schema v1.3.0](#schema-v130)
7. [Schema v1.2.0](#schema-v120)
8. [Schema v1.1.0](#schema-v110)
9. [Backward Compatibility Guarantee](#backward-compatibility-guarantee)
10. [Versioning Policy](#versioning-policy)
11. [Schema Stability](#schema-stability)
12. [Migration Support](#migration-support)
13. [Breaking Changes](#breaking-changes)
14. [Deprecation Policy](#deprecation-policy)

---

## JSON Schema Validation

token-audit provides a formal JSON Schema for validating session files:

**Schema File**: [`docs/schema/session-v1.7.0.json`](schema/session-v1.7.0.json)

### Validate Command

```bash
# Validate a session file against the schema
token-audit validate /path/to/session.json

# Show schema file location and version
token-audit validate --schema-only

# Verbose output with detailed error messages
token-audit validate session.json --verbose
```

### Programmatic Validation

```python
import json
import jsonschema
from pathlib import Path

# Load schema
schema_path = Path("docs/schema/session-v1.7.0.json")
with open(schema_path) as f:
    schema = json.load(f)

# Validate session
with open("session.json") as f:
    session = json.load(f)

jsonschema.validate(session, schema)  # Raises on error
```

---

## Schema v1.7.0

Schema v1.7.0 introduces the "Analysis Layer" - expanded smell detection patterns, AI-consumable recommendations, and cross-session aggregation capabilities.

### Key Changes from v1.6.0

| Change | v1.6.0 | v1.7.0 |
|--------|--------|--------|
| Smell patterns | 5 patterns | 12 patterns (7 new) |
| Recommendations | Not tracked | `recommendations` block with AI-consumable suggestions |
| Cross-session trends | Not tracked | `aggregation_metadata` block |
| Severity enum | 3 values | 5 values (critical, high, medium/warning, low, info) |
| Schema version | `"1.6.0"` | `"1.7.0"` |

### Expanded `smells` Block

v1.7.0 adds 7 new smell patterns for a total of 12:

#### v1.5.0 Patterns (Existing)

| Pattern | Severity | Threshold | Description |
|---------|----------|-----------|-------------|
| `HIGH_VARIANCE` | warning | CV > 0.5 | Tool with highly variable token counts across calls |
| `TOP_CONSUMER` | info | >50% of MCP tokens | Single tool consuming majority of session tokens |
| `HIGH_MCP_SHARE` | info | >80% of session | MCP tools consuming most session tokens |
| `CHATTY` | warning | >20 calls | Tool called excessively in one session |
| `LOW_CACHE_HIT` | warning/info | <30% ratio | Cache hit rate below efficient threshold |

#### v1.7.0 Patterns (New)

| Pattern | Severity | Threshold | Description |
|---------|----------|-----------|-------------|
| `REDUNDANT_CALLS` | warning | ≥2 identical | Same tool called with identical content (content_hash) |
| `EXPENSIVE_FAILURES` | high | >5K tokens | Failed tool calls consuming significant tokens |
| `UNDERUTILIZED_SERVER` | info | <10% utilization | MCP server with most tools unused |
| `BURST_PATTERN` | warning | >5 calls/second | Rapid tool calls suggesting loops or retry storms |
| `LARGE_PAYLOAD` | info | >10K tokens | Single tool call with excessive token consumption |
| `SEQUENTIAL_READS` | info | ≥3 consecutive | Multiple file reads that could be batched |
| `CACHE_MISS_STREAK` | warning | ≥5 consecutive | Consecutive cache misses indicating poor locality |

#### Severity Enum

v1.7.0 formalizes the severity levels:

| Level | Priority | Description |
|-------|----------|-------------|
| `critical` | Highest | Immediate action required (reserved for future use) |
| `high` | 2nd | Significant inefficiency, should be addressed |
| `medium` | 3rd | Notable pattern worth investigating (alias: `warning`) |
| `low` | 4th | Minor issue, nice to fix |
| `info` | Lowest | Informational, no action required |

**Note**: `warning` is maintained as an alias for `medium` for backward compatibility.

#### Complete Smell Entry Example

```json
{
  "smells": [
    {
      "pattern": "REDUNDANT_CALLS",
      "severity": "warning",
      "tool": "mcp__zen__chat",
      "description": "Called 4 times with identical content",
      "evidence": {
        "duplicate_count": 4,
        "content_hash": "10c4e76b1234abcd...",
        "threshold": 2
      }
    },
    {
      "pattern": "EXPENSIVE_FAILURES",
      "severity": "high",
      "tool": "mcp__jina__read_url",
      "description": "Failed call consumed 8,500 tokens",
      "evidence": {
        "tokens": 8500,
        "threshold": 5000,
        "call_index": 42,
        "error_info": "Connection timeout"
      }
    },
    {
      "pattern": "BURST_PATTERN",
      "severity": "warning",
      "tool": "mcp__brave-search__brave_web_search",
      "description": "7 tool calls within 1000ms",
      "evidence": {
        "call_count": 7,
        "window_ms": 1000,
        "threshold": 5,
        "start_index": 15,
        "end_index": 21,
        "tool_breakdown": {"mcp__brave-search__brave_web_search": 7}
      }
    }
  ]
}
```

### New Block: `recommendations`

AI-consumable actionable suggestions generated from detected smells:

```json
{
  "recommendations": [
    {
      "type": "REMOVE_UNUSED_SERVER",
      "confidence": 0.85,
      "evidence": "Server 'zen' has 12 tools but only 1 used (8.3% utilization)",
      "action": "Consider removing 'zen' from .mcp.json to reduce context overhead",
      "impact": "Save ~6,000 tokens/turn in schema context tax",
      "source_smell": "UNDERUTILIZED_SERVER",
      "details": {
        "server": "zen",
        "utilization_percent": 8.3,
        "tools_available": 12,
        "tools_used": 1
      }
    },
    {
      "type": "ENABLE_CACHING",
      "confidence": 0.75,
      "evidence": "Cache hit rate is only 15.2% (threshold: 30%)",
      "action": "Restructure prompts to maximize context reuse and cache hits",
      "impact": "Potential savings of ~25,000 tokens/session with better caching",
      "source_smell": "LOW_CACHE_HIT",
      "details": {
        "current_hit_rate": 15.2,
        "target_hit_rate": 50,
        "cache_read_tokens": 10000,
        "input_tokens": 55000
      }
    },
    {
      "type": "BATCH_OPERATIONS",
      "confidence": 0.9,
      "evidence": "Tool 'Read' called 35 times (threshold: 20)",
      "action": "Batch multiple 'Read' calls into fewer, larger requests",
      "impact": "Reduce overhead from 35 calls to ~7 batched calls",
      "source_smell": "CHATTY",
      "details": {
        "tool": "Read",
        "call_count": 35,
        "total_tokens": 150000,
        "avg_tokens_per_call": 4285.7
      }
    },
    {
      "type": "OPTIMIZE_COST",
      "confidence": 0.7,
      "evidence": "Failed call to 'mcp__jina__read_url' consumed 8,500 tokens",
      "action": "Add validation before calling 'mcp__jina__read_url' to prevent expensive failures",
      "impact": "Save 8,500 tokens per prevented failure",
      "source_smell": "EXPENSIVE_FAILURES",
      "details": {
        "tool": "mcp__jina__read_url",
        "tokens_wasted": 8500,
        "error_summary": "Connection timeout"
      }
    }
  ]
}
```

#### Recommendation Types

| Type | Source Smells | Description |
|------|---------------|-------------|
| `REMOVE_UNUSED_SERVER` | UNDERUTILIZED_SERVER | Remove MCP servers with low tool utilization |
| `ENABLE_CACHING` | LOW_CACHE_HIT, CACHE_MISS_STREAK, REDUNDANT_CALLS | Improve cache utilization |
| `BATCH_OPERATIONS` | SEQUENTIAL_READS, CHATTY, BURST_PATTERN | Combine operations for efficiency |
| `OPTIMIZE_COST` | EXPENSIVE_FAILURES, TOP_CONSUMER, LARGE_PAYLOAD, HIGH_VARIANCE, HIGH_MCP_SHARE | Reduce token consumption |

#### Recommendation Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Recommendation category (see table above) |
| `confidence` | float | Confidence score 0.0-1.0 based on evidence strength |
| `evidence` | string | Human/AI readable explanation |
| `action` | string | Specific action to take |
| `impact` | string | Expected benefit from taking this action |
| `source_smell` | string | The smell pattern that triggered this recommendation |
| `details` | object | Context-specific data (varies by type) |

### New Block: `aggregation_metadata`

Cross-session smell trend analysis (included in aggregation reports):

```json
{
  "aggregation_metadata": {
    "query": {
      "start_date": "2025-11-15",
      "end_date": "2025-12-13",
      "platform": "claude-code",
      "project": null
    },
    "summary": {
      "total_sessions": 45,
      "sessions_with_smells": 32
    },
    "smell_trends": [
      {
        "pattern": "CHATTY",
        "total_occurrences": 28,
        "sessions_affected": 15,
        "frequency_percent": 33.3,
        "trend": "worsening",
        "trend_change_percent": 25.0,
        "severity_breakdown": {"warning": 28},
        "top_tools": [["mcp__zen__chat", 12], ["Read", 8], ["Grep", 5]],
        "first_seen": "2025-11-18T10:30:00+11:00",
        "last_seen": "2025-12-13T09:15:00+11:00"
      },
      {
        "pattern": "LOW_CACHE_HIT",
        "total_occurrences": 18,
        "sessions_affected": 12,
        "frequency_percent": 26.7,
        "trend": "improving",
        "trend_change_percent": -15.0,
        "severity_breakdown": {"warning": 10, "info": 8},
        "top_tools": [],
        "first_seen": "2025-11-15T14:00:00+11:00",
        "last_seen": "2025-12-10T16:45:00+11:00"
      }
    ],
    "generated_at": "2025-12-13T10:00:00+11:00"
  }
}
```

#### Aggregation Fields

| Field | Type | Description |
|-------|------|-------------|
| `query.start_date` | string | Start of analysis period (ISO date) |
| `query.end_date` | string | End of analysis period (ISO date) |
| `query.platform` | string | Platform filter (null = all) |
| `query.project` | string | Project filter (null = all) |
| `summary.total_sessions` | int | Total sessions analyzed |
| `summary.sessions_with_smells` | int | Sessions with at least one smell |
| `smell_trends` | array | Per-pattern aggregation (see below) |
| `generated_at` | string | When aggregation was computed |

#### Smell Trend Fields

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | string | Smell pattern identifier |
| `total_occurrences` | int | Total times detected across all sessions |
| `sessions_affected` | int | Number of sessions with this smell |
| `frequency_percent` | float | `sessions_affected / total_sessions * 100` |
| `trend` | string | `"improving"`, `"worsening"`, or `"stable"` |
| `trend_change_percent` | float | Percentage change (negative = improving) |
| `severity_breakdown` | object | Count by severity level |
| `top_tools` | array | Top 5 tools triggering this smell `[[tool, count], ...]` |
| `first_seen` | string | First occurrence timestamp |
| `last_seen` | string | Most recent occurrence timestamp |

#### Trend Detection

Trends are calculated by comparing occurrence rates between first and second half of the analysis period:

| Trend | Condition |
|-------|-----------|
| `"improving"` | Rate decreased by >10% |
| `"worsening"` | Rate increased by >10% |
| `"stable"` | Rate change within ±10% |

### Updated Complete Schema (v1.7.0)

```json
{
  "_file": {
    "name": "token-audit-2025-12-13T14-00-00.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage, tool statistics, and efficiency analysis for AI agent consumption",
    "schema_version": "1.7.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.8.0",
    "generated_at": "2025-12-13T14:00:00+11:00"
  },

  "session": {
    "id": "token-audit-2025-12-13T14-00-00",
    "project": "token-audit",
    "platform": "claude-code",
    "model": "claude-sonnet-4-20250514",
    "models_used": ["claude-sonnet-4-20250514"],
    "working_directory": "/Users/user/projects/token-audit/main",
    "started_at": "2025-12-13T14:00:00+11:00",
    "ended_at": "2025-12-13T14:30:00+11:00",
    "duration_seconds": 1800.0,
    "source_files": ["session-abc123.jsonl"],
    "message_count": 25
  },

  "token_usage": { ... },
  "cost_estimate_usd": 1.23,
  "model_usage": { ... },
  "mcp_summary": { ... },
  "builtin_tool_summary": { ... },
  "cache_analysis": { ... },
  "tool_calls": [ ... ],

  "smells": [
    {
      "pattern": "CHATTY",
      "severity": "warning",
      "tool": "Read",
      "description": "Called 35 times",
      "evidence": { ... }
    },
    {
      "pattern": "REDUNDANT_CALLS",
      "severity": "warning",
      "tool": "mcp__zen__chat",
      "description": "Called 4 times with identical content",
      "evidence": { ... }
    }
  ],

  "recommendations": [
    {
      "type": "BATCH_OPERATIONS",
      "confidence": 0.9,
      "evidence": "Tool 'Read' called 35 times",
      "action": "Batch multiple 'Read' calls into fewer requests",
      "impact": "Reduce from 35 to ~7 batched calls",
      "source_smell": "CHATTY",
      "details": { ... }
    }
  ],

  "zombie_tools": { ... },

  "data_quality": {
    "accuracy_level": "exact",
    "token_source": "native",
    "confidence": 1.0,
    "pricing_source": "api",
    "pricing_freshness": "fresh"
  },

  "static_cost": { ... },

  "analysis": { ... }
}
```

**Backward Compatibility:**

- Old readers (v1.6.0 and earlier) ignore the new fields (`recommendations`, expanded `smells` patterns)
- Old sessions without these fields are read with defaults (empty recommendations, only v1.5.0 smell patterns)
- Schema version in `_file.schema_version` indicates presence of new fields
- The `warning` severity alias continues to work for backward compatibility

---

## Schema v1.6.0

Schema v1.6.0 introduces "Multi-Model Intelligence" - per-model token tracking, dynamic pricing integration, and foundation for static cost analysis.

### Key Changes from v1.5.0

| Change | v1.5.0 | v1.6.0 |
|--------|--------|--------|
| Multi-model tracking | Not tracked | `models_used` and `model_usage` blocks |
| Per-call model | Not tracked | `tool_calls[].model` field |
| Pricing source | Not tracked | `data_quality.pricing_source` |
| Pricing freshness | Not tracked | `data_quality.pricing_freshness` |
| Static cost | Not tracked | `static_cost` block with per-server breakdown |
| Schema version | `"1.5.0"` | `"1.6.0"` |

### New Field: `session.models_used`

Array of unique model identifiers used during the session:

```json
{
  "session": {
    "id": "token-audit-2025-12-11T14-00-00",
    "platform": "claude-code",
    "model": "claude-sonnet-4-20250514",
    "models_used": [
      "claude-sonnet-4-20250514",
      "claude-opus-4-5-20251101"
    ]
  }
}
```

**Field Details:**

| Field | Type | Description |
|-------|------|-------------|
| `models_used` | array | List of unique model IDs used in session (may be single-element for most sessions) |

**Note**: The primary `model` field contains the initial/most-used model. `models_used` tracks all models when users switch mid-session.

### New Block: `model_usage`

Per-model token and cost breakdown for multi-model sessions:

```json
{
  "model_usage": {
    "claude-sonnet-4-20250514": {
      "input_tokens": 50000,
      "output_tokens": 15000,
      "cache_created_tokens": 2000,
      "cache_read_tokens": 100000,
      "total_tokens": 167000,
      "cost_usd": 0.45,
      "call_count": 12
    },
    "claude-opus-4-5-20251101": {
      "input_tokens": 10000,
      "output_tokens": 5000,
      "cache_created_tokens": 0,
      "cache_read_tokens": 25000,
      "total_tokens": 40000,
      "cost_usd": 0.18,
      "call_count": 3
    }
  }
}
```

#### Model Usage Fields

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | int | Total input tokens for this model |
| `output_tokens` | int | Total output tokens for this model |
| `cache_created_tokens` | int | Cache creation tokens for this model |
| `cache_read_tokens` | int | Cache read tokens for this model |
| `total_tokens` | int | Sum of all token types |
| `cost_usd` | float | Cost estimate for this model's usage |
| `call_count` | int | Number of tool calls using this model |

**Platform Behavior:**

| Platform | Multi-Model Support | Notes |
|----------|---------------------|-------|
| Claude Code | Yes | Users can switch models via `/model` command |
| Codex CLI | Yes | Model specified per session or via flags |
| Gemini CLI | Limited | Model typically fixed per session |

### New Field: `tool_calls[].model`

Per-call model tracking:

```json
{
  "tool_calls": [
    {
      "index": 1,
      "tool": "mcp__backlog__task_list",
      "server": "backlog",
      "model": "claude-sonnet-4-20250514",
      "input_tokens": 156,
      "output_tokens": 2340
    }
  ]
}
```

**Note**: The `model` field is only present when the model is known. For platforms without per-call model attribution, this field is omitted.

### Updated Block: `data_quality`

Extended with pricing source tracking:

```json
{
  "data_quality": {
    "accuracy_level": "exact",
    "token_source": "native",
    "confidence": 1.0,
    "pricing_source": "api",
    "pricing_freshness": "fresh",
    "notes": "Tokens from native platform, pricing from LiteLLM API"
  }
}
```

#### New Data Quality Fields

| Field | Type | Description |
|-------|------|-------------|
| `pricing_source` | string | Where pricing data came from |
| `pricing_freshness` | string | Freshness of pricing data |

#### Pricing Source Values

| Value | Description |
|-------|-------------|
| `"api"` | Fresh from LiteLLM API (real-time) |
| `"cache"` | Cached API data (within TTL) |
| `"cache-stale"` | Expired API cache (fallback) |
| `"file"` | TOML configuration file |
| `"defaults"` | Hardcoded default pricing |

#### Pricing Freshness Values

| Value | Description |
|-------|-------------|
| `"fresh"` | Fetched within the last hour |
| `"cached"` | Valid cache (within TTL, default 24h) |
| `"stale"` | Cache expired or defaults used |
| `"unknown"` | Freshness cannot be determined |

### New Block: `static_cost`

The "context tax" — static token overhead from MCP server tool schemas:

```json
{
  "static_cost": {
    "total_tokens": 6450,
    "source": "mixed",
    "by_server": {
      "zen": 3000,
      "backlog": 2250,
      "brave-search": 1200
    },
    "confidence": 0.8
  }
}
```

#### Static Cost Fields

| Field | Type | Description |
|-------|------|-------------|
| `total_tokens` | int | Total estimated tokens for all MCP server schemas |
| `source` | string | Data source (`"known_db"`, `"estimate"`, `"mixed"`, `"none"`) |
| `by_server` | object | Per-server token breakdown |
| `confidence` | float | Confidence level (0.0-1.0) based on data sources |

#### Source Values

| Value | Description | Confidence |
|-------|-------------|------------|
| `"known_db"` | All servers from pre-measured database | 0.9 |
| `"estimate"` | All servers estimated (10 tools × 175 tokens) | 0.7 |
| `"mixed"` | Combination of known and estimated | Weighted average |
| `"none"` | No MCP config found | 0.0 |

#### Known Servers Database

Pre-measured token counts for popular MCP servers:

| Server | Tools | Tokens |
|--------|-------|--------|
| `backlog` | 15 | 2,250 |
| `brave-search` | 6 | 1,200 |
| `zen` | 12 | 3,000 |
| `jina` | 20 | 3,600 |
| `context7` | 5 | 750 |
| `mult-fetch` | 3 | 450 |

Unknown servers use default estimate: 10 tools × 175 tokens/tool = 1,750 tokens.

**Platform Config Discovery:**

| Platform | Config File |
|----------|-------------|
| Claude Code | `.mcp.json` in working directory |
| Codex CLI | `~/.codex/config.toml` |
| Gemini CLI | `~/.gemini/settings.json` |

### Updated Complete Schema (v1.6.0)

```json
{
  "_file": {
    "name": "token-audit-2025-12-11T14-00-00.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics for AI agent analysis",
    "schema_version": "1.6.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.6.0",
    "generated_at": "2025-12-11T14:00:00+11:00"
  },

  "session": {
    "id": "token-audit-2025-12-11T14-00-00",
    "project": "token-audit",
    "platform": "claude-code",
    "model": "claude-sonnet-4-20250514",
    "models_used": ["claude-sonnet-4-20250514"],
    "working_directory": "/Users/user/projects/token-audit/main",
    "started_at": "2025-12-11T14:00:00+11:00",
    "ended_at": "2025-12-11T14:30:00+11:00",
    "duration_seconds": 1800.0,
    "source_files": ["session-abc123.jsonl"],
    "message_count": 25
  },

  "token_usage": { ... },
  "cost_estimate_usd": 1.23,

  "model_usage": {
    "claude-sonnet-4-20250514": {
      "input_tokens": 50000,
      "output_tokens": 15000,
      "cache_created_tokens": 2000,
      "cache_read_tokens": 100000,
      "total_tokens": 167000,
      "cost_usd": 1.23,
      "call_count": 15
    }
  },

  "mcp_summary": { ... },
  "builtin_tool_summary": { ... },
  "cache_analysis": { ... },
  "tool_calls": [ ... ],
  "smells": [ ... ],
  "zombie_tools": { ... },

  "data_quality": {
    "accuracy_level": "exact",
    "token_source": "native",
    "confidence": 1.0,
    "pricing_source": "api",
    "pricing_freshness": "fresh"
  },

  "static_cost": {
    "total_tokens": 6450,
    "source": "mixed",
    "by_server": {
      "zen": 3000,
      "backlog": 2250,
      "brave-search": 1200
    },
    "confidence": 0.8
  },

  "analysis": { ... }
}
```

**Backward Compatibility:**

- Old readers (v1.5.0 and earlier) ignore the new fields (`models_used`, `model_usage`, `tool_calls[].model`, `static_cost`)
- Old sessions without these fields are read with defaults (empty model_usage, no per-call models, no static cost)
- Schema version in `_file.schema_version` indicates presence of new fields

---

## Schema v1.5.0

Schema v1.5.0 introduces the "Insight Layer" - efficiency analysis, data quality indicators, and zombie tool detection. This enables users to identify inefficient MCP usage patterns and provides accuracy labeling for all metrics.

### Key Changes from v1.4.0

| Change | v1.4.0 | v1.5.0 |
|--------|--------|--------|
| Smell detection | Not tracked | `smells` block with 5 anti-patterns |
| Data quality | Not tracked | `data_quality` block with accuracy labels |
| Zombie tools | Not tracked | `zombie_tools` block per server |
| Schema version | `"1.4.0"` | `"1.5.0"` |

### New Block: `smells`

Efficiency anti-patterns detected in the session:

```json
{
  "smells": [
    {
      "pattern": "HIGH_VARIANCE",
      "severity": "warning",
      "tool": "mcp__zen__thinkdeep",
      "description": "Token counts vary significantly (σ=45000, range: 10K-150K)",
      "evidence": {
        "std_dev": 45000,
        "min_tokens": 10000,
        "max_tokens": 150000,
        "call_count": 5
      }
    },
    {
      "pattern": "TOP_CONSUMER",
      "severity": "info",
      "tool": "mcp__zen__consensus",
      "description": "Single tool consuming 65% of session tokens",
      "evidence": {
        "tool_tokens": 850000,
        "session_tokens": 1300000,
        "percentage": 65.4
      }
    }
  ]
}
```

#### Smell Patterns

| Pattern | Severity | Threshold | Description |
|---------|----------|-----------|-------------|
| `HIGH_VARIANCE` | warning | σ > 30% of mean | Tool with unusually variable token counts |
| `TOP_CONSUMER` | info | >50% of total | Single tool consuming majority of tokens |
| `HIGH_MCP_SHARE` | info | >80% of total | MCP tools consuming most session tokens |
| `CHATTY` | warning | >20 calls | Tool called excessively in one session |
| `LOW_CACHE_HIT` | warning | <30% ratio | Cache hit rate below efficient threshold |

#### Smell Entry Fields

| Field | Type | Description |
|-------|------|-------------|
| `pattern` | string | Pattern identifier (see table above) |
| `severity` | string | `"info"`, `"warning"`, or `"error"` |
| `tool` | string | Tool name triggering the smell (optional) |
| `description` | string | Human-readable explanation |
| `evidence` | object | Pattern-specific supporting data |

### New Block: `data_quality`

Accuracy indicators for all metrics in the session:

```json
{
  "data_quality": {
    "accuracy_level": "estimated",
    "token_source": "tiktoken",
    "token_encoding": "o200k_base",
    "confidence": 0.99,
    "pricing_source": "cache",
    "pricing_freshness": "cached",
    "notes": "Tokens estimated using tiktoken o200k_base (~99% accuracy for Codex CLI)"
  }
}
```

#### Accuracy Levels

| Value | Description | Platforms |
|-------|-------------|-----------|
| `exact` | Native platform tokens | Claude Code |
| `estimated` | Tokenizer-based estimation | Codex CLI, Gemini CLI |
| `calls-only` | Only call counts, no tokens | Ollama CLI (v1.4.0) |

**Note on "estimated" vs "exact":** Codex CLI and Gemini CLI are marked "estimated" because while they provide native session-level token totals, token-audit estimates the per-MCP-tool breakdown using tiktoken/sentencepiece. Claude Code is "exact" because it provides per-message token attribution directly.

#### Data Quality Fields

| Field | Type | Description |
|-------|------|-------------|
| `accuracy_level` | string | `"exact"`, `"estimated"`, or `"calls-only"` |
| `token_source` | string | Tokenizer used (e.g., `"native"`, `"tiktoken"`, `"sentencepiece"`) |
| `token_encoding` | string | Specific encoding (e.g., `"o200k_base"`, `"gemma"`) |
| `confidence` | float | Estimated accuracy (0.0-1.0) |
| `pricing_source` | string | **v1.6.0:** Pricing data source (`"api"`, `"cache"`, `"file"`, `"defaults"`) |
| `pricing_freshness` | string | **v1.6.0:** Pricing freshness (`"fresh"`, `"cached"`, `"stale"`, `"unknown"`) |
| `notes` | string | Additional context about data quality |

### New Block: `zombie_tools`

MCP tools defined in server schemas but never called during the session:

```json
{
  "zombie_tools": {
    "zen": ["mcp__zen__refactor", "mcp__zen__precommit"],
    "backlog": ["mcp__backlog__task_archive"]
  }
}
```

#### Zombie Tools Fields

| Field | Type | Description |
|-------|------|-------------|
| `<server_name>` | array | List of tool names defined but never used |

**Note**: Zombie tools indicate potential context overhead. Each unused tool's schema is included in the context but provides no value.

### Updated Complete Schema (v1.5.0)

```json
{
  "_file": {
    "name": "token-audit-2025-12-10T14-19-38.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics for AI agent analysis",
    "schema_version": "1.5.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.5.0",
    "generated_at": "2025-12-10T14:19:55+11:00"
  },

  "session": { ... },
  "token_usage": { ... },
  "cost_estimate_usd": 1.23,
  "mcp_summary": { ... },
  "builtin_tool_summary": { ... },
  "cache_analysis": { ... },
  "tool_calls": [ ... ],

  "smells": [
    {
      "pattern": "HIGH_VARIANCE",
      "severity": "warning",
      "tool": "mcp__zen__thinkdeep",
      "description": "Token counts vary significantly",
      "evidence": { ... }
    }
  ],

  "data_quality": {
    "accuracy_level": "exact",
    "token_source": "native",
    "confidence": 1.0,
    "pricing_source": "cache",
    "pricing_freshness": "cached"
  },

  "zombie_tools": {
    "zen": ["mcp__zen__refactor"]
  },

  "analysis": { ... }
}
```

**Backward Compatibility:**

- Old readers (v1.4.0 and earlier) ignore the new blocks (`smells`, `data_quality`, `zombie_tools`)
- Old sessions without these blocks are read with defaults (empty smells, no data quality info)
- Schema version in `_file.schema_version` indicates presence of new fields

---

## Schema v1.4.0

Schema v1.4.0 adds token estimation metadata for MCP tool calls on platforms without native per-tool token attribution. This enables accurate token tracking for Codex CLI and Gemini CLI.

### Key Changes from v1.3.0

| Change | v1.3.0 | v1.4.0 |
|--------|--------|--------|
| Token estimation | Not tracked | `is_estimated`, `estimation_method`, `estimation_encoding` |
| Schema version | `"1.3.0"` | `"1.4.0"` |

### New Fields in `tool_calls`

```json
{
  "tool_calls": [
    {
      "index": 1,
      "tool": "mcp__brave-search__brave_web_search",
      "server": "brave-search",
      "input_tokens": 156,
      "output_tokens": 2340,
      "total_tokens": 2496,
      "is_estimated": true,
      "estimation_method": "tiktoken",
      "estimation_encoding": "o200k_base"
    }
  ]
}
```

#### `is_estimated` Field

Indicates whether token counts are estimated (Codex CLI, Gemini CLI) or native (Claude Code).

| Value | Meaning |
|-------|---------|
| `true` | Tokens estimated using tiktoken/sentencepiece |
| `false` or absent | Native tokens from platform |

**Optimization**: When `is_estimated` is `false`, the field and related estimation fields are omitted from output to minimize file size. Claude Code sessions will not have these fields.

#### `estimation_method` Field

Tokenization method used for estimation. Only present when `is_estimated` is `true`.

| Value | Description | Accuracy |
|-------|-------------|----------|
| `"tiktoken"` | OpenAI tiktoken library | ~99-100% for Codex CLI |
| `"sentencepiece"` | Google SentencePiece | 100% for Gemini CLI |
| `"character"` | Fallback (~4 chars/token) | ~80% approximation |

#### `estimation_encoding` Field

Specific encoding/tokenizer used. Only present when `is_estimated` is `true`.

| Value | Platform | Notes |
|-------|----------|-------|
| `"o200k_base"` | Codex CLI | Native OpenAI tokenizer |
| `"cl100k_base"` | Claude Code fallback | Best approximation |
| `"sentencepiece:gemma"` | Gemini CLI | Gemma tokenizer (identical BPE vocab) |
| `"character-fallback"` | Any | When tokenizers unavailable |

### Platform-Specific Behavior

| Platform | `is_estimated` | `estimation_method` | Accuracy |
|----------|----------------|---------------------|----------|
| Claude Code | `false` (omitted) | N/A | 100% (native) |
| Codex CLI | `true` | `"tiktoken"` | ~99-100% |
| Gemini CLI | `true` | `"sentencepiece"` | 100% (with optional tokenizer) |
| Gemini CLI | `true` | `"tiktoken"` | ~95% (fallback) |

> **Note**: Gemini CLI 100% accuracy requires the optional Gemma tokenizer (`token-audit tokenizer download`). Without it, tiktoken cl100k_base is used as fallback.

**Backward Compatibility:**

- Old readers (v1.3.0 and earlier) ignore the new estimation fields
- Claude Code sessions (no estimation) have minimal overhead since fields are omitted
- Old sessions without estimation fields are read as having native tokens

---

## Schema v1.3.0

Schema v1.3.0 adds separate tracking of reasoning/thinking tokens while maintaining full backward compatibility with v1.2.0, v1.1.0, and v1.0.0.

### Key Changes from v1.2.0

| Change | v1.2.0 | v1.3.0 |
|--------|--------|--------|
| Reasoning tokens | Combined into `output_tokens` | Separate `reasoning_tokens` field |
| Schema version | `"1.2.0"` | `"1.3.0"` |

### New Field: `reasoning_tokens`

```json
{
  "token_usage": {
    "input_tokens": 76,
    "output_tokens": 88,
    "reasoning_tokens": 50,
    "cache_created_tokens": 3925,
    "cache_read_tokens": 854215,
    "total_tokens": 858354,
    "cache_efficiency": 0.995
  }
}
```

#### `reasoning_tokens` Field

Tracks thinking/reasoning tokens separately from output tokens. This enables accurate cost analysis for models with thinking tokens (Codex CLI o-series, Gemini CLI).

| Platform | Source Field | Notes |
|----------|-------------|-------|
| Claude Code | N/A | Always 0 (no thinking tokens exposed) |
| Codex CLI | `reasoning_output_tokens` | Present in o1/o3-mini and similar models |
| Gemini CLI | `thoughts` | Present in Gemini 2.0+ responses |

**Backward Compatibility:**

- Old readers (v1.2.0 and earlier) ignore the new `reasoning_tokens` field
- Old sessions without `reasoning_tokens` are read as having 0 reasoning tokens
- TUI only displays reasoning row when `reasoning_tokens > 0` (auto-hides for Claude Code)

**Display Behavior:**

When `reasoning_tokens > 0`, the TUI shows:
```
╭─ Token Usage ────────────────────╮
│  Input:      10,000              │
│  Output:     2,000               │
│  Reasoning:  500                 │
│  ...                             │
╰──────────────────────────────────╯
```

When `reasoning_tokens == 0` (e.g., Claude Code), the row is hidden automatically.

---

## Schema v1.2.0

Schema v1.2.0 adds built-in tool tracking to session output while maintaining full backward compatibility with v1.1.0 and v1.0.0.

### Key Changes from v1.1.0

| Change | v1.1.0 | v1.2.0 |
|--------|--------|--------|
| Built-in tools | Tracked in TUI only | Persisted in `builtin_tool_summary` |
| Schema version | `"1.1.0"` | `"1.2.0"` |

### New Field: `builtin_tool_summary`

```json
{
  "builtin_tool_summary": {
    "total_calls": 15,
    "total_tokens": 1250000,
    "tools": [
      {"tool": "Read", "calls": 5, "tokens": 450000},
      {"tool": "Bash", "calls": 4, "tokens": 350000},
      {"tool": "Glob", "calls": 3, "tokens": 250000},
      {"tool": "Grep", "calls": 2, "tokens": 150000},
      {"tool": "Edit", "calls": 1, "tokens": 50000}
    ]
  }
}
```

#### `builtin_tool_summary` Block

Tracks aggregate and per-tool statistics for built-in tools (Bash, Read, Write, Edit, Glob, Grep, etc.).

| Field | Type | Description |
|-------|------|-------------|
| `total_calls` | int | Total number of built-in tool calls |
| `total_tokens` | int | Total tokens consumed by built-in tools |
| `tools` | array | Per-tool breakdown sorted by tokens (descending) |

**Per-tool entry:**

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Built-in tool name (e.g., `"Read"`, `"Bash"`) |
| `calls` | int | Number of calls to this tool |
| `tokens` | int | Total tokens for this tool |

**Platform-Specific Behavior:**

| Platform | `calls` | `tokens` |
|----------|---------|----------|
| Claude Code | Per-tool | Per-tool (token attribution available) |
| Codex CLI | Per-tool | Always 0 (no token attribution) |
| Gemini CLI | Per-tool | Always 0 (no token attribution) |

---

## Schema v1.1.0

Schema v1.1.0 introduces significant improvements for AI-Agent readability while maintaining backward compatibility with v1.0.0.

### Key Changes from v1.0.0

| Change | v1.0.0 | v1.1.0 |
|--------|--------|--------|
| File structure | Directory with multiple files | Single file per session |
| Schema version | At every nested level | Only in `_file` header |
| Tool calls | 6-level nested hierarchy | Flat `tool_calls` array |
| Timestamps | ISO 8601 (no timezone) | ISO 8601 with timezone offset |
| File naming | `<project>-<timestamp>/summary.json` | `<project>-<timestamp>.json` |
| Directory structure | Flat sessions directory | Date subdirectories (YYYY-MM-DD) |
| MCP data | Separate `mcp-*.json` files | Embedded in single file |
| Session context | Scattered fields | `session` block at root |
| File self-description | None | `_file` header block |

### Directory Structure

```
~/.token-audit/sessions/
├── 2025-12-01/
│   ├── token-audit-2025-12-01T14-19-38.json
│   └── my-project-2025-12-01T15-30-00.json
└── 2025-12-02/
    └── another-project-2025-12-02T09-00-00.json
```

### Complete Schema

```json
{
  "_file": {
    "name": "token-audit-2025-12-01T14-19-38.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics for AI agent analysis",
    "schema_version": "1.1.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.4.0",
    "generated_at": "2025-12-01T14:19:55+11:00"
  },

  "session": {
    "id": "token-audit-2025-12-01T14-19-38",
    "project": "token-audit",
    "platform": "claude-code",
    "model": "claude-opus-4-5-20251101",
    "working_directory": "/Users/user/projects/token-audit/main",
    "started_at": "2025-12-01T14:19:38+11:00",
    "ended_at": "2025-12-01T14:35:55+11:00",
    "duration_seconds": 976.93,
    "source_files": ["session-abc123.jsonl"]
  },

  "token_usage": {
    "input_tokens": 76,
    "output_tokens": 88,
    "reasoning_tokens": 0,
    "cache_created_tokens": 3925,
    "cache_read_tokens": 854215,
    "total_tokens": 858304,
    "cache_efficiency": 0.995
  },

  "cost_estimate_usd": 1.23,

  "mcp_summary": {
    "total_calls": 5,
    "unique_tools": 3,
    "unique_servers": 2,
    "servers_used": ["zen", "backlog"],
    "top_by_tokens": [
      {"tool": "mcp__zen__thinkdeep", "server": "zen", "tokens": 150000, "calls": 2}
    ],
    "top_by_calls": [
      {"tool": "mcp__zen__chat", "server": "zen", "calls": 10, "tokens": 30000}
    ]
  },

  "builtin_tool_summary": {
    "total_calls": 15,
    "total_tokens": 1250000,
    "tools": [
      {"tool": "Read", "calls": 5, "tokens": 450000},
      {"tool": "Bash", "calls": 4, "tokens": 350000},
      {"tool": "Glob", "calls": 3, "tokens": 250000}
    ]
  },

  "cache_analysis": {
    "status": "efficient",
    "summary": "Cache saved $0.1234. Created 50,000 tokens, read 500,000 tokens (ratio: 10.00).",
    "creation_tokens": 50000,
    "read_tokens": 500000,
    "ratio": 10.0,
    "net_savings_usd": 0.1234,
    "top_cache_creators": [
      {"tool": "mcp__zen__thinkdeep", "tokens": 30000, "pct": 60.0}
    ],
    "top_cache_readers": [
      {"tool": "mcp__zen__chat", "tokens": 400000, "pct": 80.0}
    ],
    "recommendation": "Cache is working efficiently. Continue current usage patterns."
  },

  "cost_no_cache_usd": 1.35,
  "cache_savings_usd": 0.12,

  "tool_calls": [
    {
      "index": 1,
      "timestamp": "2025-12-01T14:19:43+11:00",
      "tool": "mcp__backlog__task_list",
      "server": "backlog",
      "input_tokens": 8,
      "output_tokens": 2,
      "cache_created_tokens": 505,
      "cache_read_tokens": 94337,
      "total_tokens": 94852,
      "duration_ms": 1250,
      "content_hash": "10c4e76b..."
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

### Field Descriptions

#### `_file` Header Block

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | File name (matches actual filename) |
| `type` | string | Always `"token_audit_session"` |
| `purpose` | string | Human-readable description for AI agents |
| `schema_version` | string | Schema version (e.g., `"1.1.0"`) |
| `schema_docs` | string | URL to this documentation |
| `generated_by` | string | Tool and version (e.g., `"token-audit v0.4.0"`) |
| `generated_at` | string | ISO 8601 timestamp with timezone |

#### `session` Block

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique session identifier |
| `project` | string | Project name (from working directory) |
| `platform` | string | `"claude-code"`, `"codex-cli"`, or `"gemini-cli"` |
| `model` | string | AI model used (e.g., `"claude-opus-4-5-20251101"`) |
| `working_directory` | string | Absolute path where session was tracked |
| `started_at` | string | Session start (ISO 8601 with timezone) |
| `ended_at` | string | Session end (ISO 8601 with timezone, nullable) |
| `duration_seconds` | float | Session duration in seconds (nullable) |
| `source_files` | array | Source log files monitored |

#### `tool_calls` Array

| Field | Type | Description |
|-------|------|-------------|
| `index` | int | Sequential call number (1, 2, 3...) |
| `timestamp` | string | When the call occurred (ISO 8601 with timezone) |
| `tool` | string | Full tool name (e.g., `"mcp__zen__chat"`) |
| `server` | string | MCP server name (e.g., `"zen"`) |
| `input_tokens` | int | Input tokens consumed |
| `output_tokens` | int | Output tokens generated |
| `cache_created_tokens` | int | Cache tokens created (optional) |
| `cache_read_tokens` | int | Cache tokens read (optional) |
| `total_tokens` | int | Total tokens for this call |
| `duration_ms` | int | Call duration in milliseconds (optional) |
| `content_hash` | string | SHA256 hash of input for deduplication |

**Platform-Specific Behavior:**

| Field | Claude Code | Codex CLI | Gemini CLI |
|-------|-------------|-----------|------------|
| `input_tokens` | Per-call | Always 0 | Always 0 |
| `output_tokens` | Per-call | Always 0 | Always 0 |
| `cache_created_tokens` | Per-call | Always 0 | N/A |
| `cache_read_tokens` | Per-call | Always 0 | N/A |
| `total_tokens` | Per-call | Always 0 | Always 0 |
| `duration_ms` | Available | Available | N/A |

See platform setup guides for details on these limitations. Codex CLI and Gemini CLI provide session/message-level tokens only, not per-call attribution.

#### `mcp_summary` Block

| Field | Type | Description |
|-------|------|-------------|
| `total_calls` | int | Total MCP tool calls in session |
| `unique_tools` | int | Number of distinct tools used |
| `unique_servers` | int | Number of distinct MCP servers used |
| `servers_used` | array | List of server names |
| `top_by_tokens` | array | Top 5 tools by token consumption |
| `top_by_calls` | array | Top 5 tools by call frequency |

#### `cache_analysis` Block (v1.1.0+)

AI-optimized cache efficiency analysis. Explains cache behavior for AI agents.

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"efficient"`, `"inefficient"`, or `"neutral"` |
| `summary` | string | Human/AI readable summary of cache behavior |
| `creation_tokens` | int | Total cache creation tokens |
| `read_tokens` | int | Total cache read tokens |
| `ratio` | float | Read/creation ratio (higher = better) |
| `net_savings_usd` | float | Positive = savings, negative = net cost |
| `top_cache_creators` | array | Top 5 tools by cache creation |
| `top_cache_readers` | array | Top 5 tools by cache reads |
| `recommendation` | string | Actionable suggestion based on analysis |

**Cache Creator/Reader Entries:**
```json
{"tool": "mcp__zen__thinkdeep", "tokens": 30000, "pct": 60.0}
```
- `tool`: Full tool name
- `tokens`: Cache tokens created/read by this tool
- `pct`: Percentage of total creation/read

**Status Values:**
- `"efficient"`: Cache saves money (`net_savings_usd > 0`)
- `"inefficient"`: Cache costs more than it saves (`net_savings_usd < 0`)
- `"neutral"`: No cache activity or break-even

---

## Backward Compatibility Guarantee

### Our Promise

**We guarantee backward compatibility for the on-disk session format within major versions.**

This means:

- ✅ **v1.0 sessions will always be readable by v1.x**
- ✅ **v1.5 can read sessions created by v1.0, v1.1, v1.2, etc.**
- ✅ **Index files remain compatible within major versions**
- ⚠️ **v2.0 may require migration from v1.x format**

### What This Covers

| Component | Guarantee |
|-----------|-----------|
| Session JSONL files | Read compatibility within major version |
| Daily index files | Read compatibility within major version |
| Platform index files | Read compatibility within major version |
| Event schema | Additive changes only within major version |
| Storage directory structure | Stable within major version |

### What This Does NOT Cover

| Component | Note |
|-----------|------|
| CLI arguments | May change between minor versions |
| Python API signatures | May add optional parameters |
| Report output format | May improve between versions |
| Configuration file format | May add new options |

---

## Versioning Policy

Token Audit follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

### Version Bump Rules

#### Major Version (1.x.x → 2.x.x)

Bump major version when making **breaking changes**:

- Removing required fields from schema
- Changing field types (e.g., `int` → `string`)
- Renaming fields
- Changing directory structure
- Removing support for old session formats

**User Impact**: May require data migration

#### Minor Version (x.1.x → x.2.x)

Bump minor version for **additive changes**:

- Adding new optional fields to schema
- Adding new event types
- Adding new platforms
- Adding new CLI commands
- Adding new configuration options

**User Impact**: No action required, new features available

#### Patch Version (x.x.1 → x.x.2)

Bump patch version for **bug fixes**:

- Fixing parsing errors
- Fixing calculation bugs
- Documentation corrections
- Performance improvements (no behavior change)

**User Impact**: Safe to upgrade immediately

### Examples

| Change | Version Bump |
|--------|--------------|
| Add `duration_ms` field to Call | Minor (additive) |
| Remove `legacy_field` from Session | **Major** (breaking) |
| Fix token calculation bug | Patch |
| Add Gemini CLI support | Minor |
| Change `total_tokens: int` to `total_tokens: str` | **Major** (type change) |
| Add `[analytics]` optional dependency | Minor |

---

## Schema Stability

### Schema Version Field

**v1.1.0+**: Schema version is in the `_file` header block:

```json
{
  "_file": {
    "schema_version": "1.1.0",
    ...
  },
  "session": {
    "id": "session-20251125T103045-abc123",
    ...
  }
}
```

**v1.0.0**: Schema version at root level (legacy format):

```json
{
  "schema_version": "1.0.0",
  "session_id": "session-20251125T103045-abc123",
  ...
}
```

This enables:

- Version detection when loading old sessions
- Graceful handling of unknown fields
- Migration path identification

### Field Categories

#### Required Fields (Stable)

These fields will always be present and maintain their type:

**v1.1.0 Format:**
```python
# _file header (required in v1.1.0+)
_file.schema_version: str  # Always present
_file.type: str            # Always "token_audit_session"
_file.generated_at: str    # ISO 8601 with timezone

# session block (required in v1.1.0+)
session.id: str            # Unique session ID
session.platform: str      # "claude-code", "codex-cli", or "gemini-cli"
session.project: str       # Project name
session.started_at: str    # ISO 8601 with timezone

# token_usage (same in both versions)
token_usage.input_tokens: int
token_usage.output_tokens: int
token_usage.total_tokens: int
```

**v1.0.0 Format (Legacy):**
```python
schema_version: str    # At root level
session_id: str        # At root level
platform: str          # At root level
timestamp: str         # ISO 8601 (no timezone)
token_usage: dict      # Same structure
```

#### Optional Fields (May be absent in older versions)

```python
# Added in v1.0.0
duration_ms: Optional[int]         # For time-based tracking
content_hash: Optional[str]        # For duplicate detection
cache_created_tokens: Optional[int]
cache_read_tokens: Optional[int]

# Added in v1.1.0
session.model: Optional[str]              # AI model used
session.working_directory: Optional[str]  # Absolute path
session.ended_at: Optional[str]           # Session end time
session.duration_seconds: Optional[float] # Duration
mcp_summary: Optional[dict]               # Pre-computed tool stats
tool_calls: Optional[list]                # Flat array of calls
```

#### Extension Fields (Platform-specific)

```python
# May vary by platform
platform_data: Optional[dict]  # Platform-specific metadata
metadata: Optional[dict]       # Additional context
```

### Handling Unknown Fields

When loading sessions, unknown fields are **preserved but ignored**:

```python
# Session created by v1.5.0, loaded by v1.2.0
{
  "schema_version": "1.5.0",
  "session_id": "...",
  "new_field_in_1_5": "value",  # Unknown to v1.2.0, preserved
  ...
}
```

This ensures forward compatibility within major versions.

---

## Migration Support

### Automatic Migration

Token Audit provides migration helpers for upgrading between versions:

```bash
# Check for sessions needing migration
token-audit migrate --check

# Migrate from v0.x format to v1.x
token-audit migrate --from logs/sessions/

# Dry run (preview without changes)
token-audit migrate --from logs/sessions/ --dry-run
```

### Programmatic Migration

```python
from storage import StorageManager, migrate_all_v0_sessions
from pathlib import Path

# Migrate v0.x sessions to v1.x format
storage = StorageManager()
results = migrate_all_v0_sessions(
    v0_base_dir=Path("logs/sessions"),
    storage=storage,
    platform="claude_code"
)

print(f"Migrated: {results['migrated']}")
print(f"Skipped: {results['skipped']}")
print(f"Failed: {results['failed']}")
```

### Migration Matrix

| From | To | Migration Path |
|------|-----|----------------|
| v0.x | v1.x | `migrate_all_v0_sessions()` |
| v1.0.0 | v1.1.0 | Automatic (readers support both formats) |
| v1.x | v2.x | Future: `migrate_v1_to_v2()` |

### v1.0.0 to v1.1.0 Compatibility

**Reading v1.0.0 files with v1.1.0 reader:**
- SessionManager automatically detects format by presence of `_file` header
- v1.0.0 sessions (directories with `summary.json`) are loaded and converted
- `server_sessions` nested structure is reconstructed into flat `tool_calls`
- `mcp_summary` is built from legacy `mcp_tool_calls` data

**Reading v1.1.0 files with v1.0.0 reader:**
- Unknown fields (`_file`, `session`, `mcp_summary`, `tool_calls`) are ignored
- Core fields (`token_usage`, `cost_estimate`, `platform`, `project`) are preserved
- Analysis will work but won't benefit from new flat structure

### What Gets Migrated

When migrating from v0.x to v1.x:

| v0.x File | v1.x Destination | Notes |
|-----------|------------------|-------|
| `events.jsonl` | `<session-id>.jsonl` | Copied directly |
| `summary.json` | Index entries | Metadata extracted |
| `mcp-*.json` | Embedded in JSONL | Data merged |

### Migration Safety

- **Non-destructive**: Original files are never deleted
- **Idempotent**: Running twice won't create duplicates
- **Reversible**: Keep v0.x files until confident

---

## Breaking Changes

### Definition

A **breaking change** is any modification that:

1. Prevents reading existing session files
2. Changes the meaning of existing fields
3. Removes functionality users depend on

### Breaking Change Process

When a breaking change is necessary:

1. **Announce** in release notes (minimum 1 minor version notice)
2. **Provide** migration tooling
3. **Document** upgrade path
4. **Support** previous major version for 6 months
5. **Bump** major version

### Example Timeline

```
v1.8.0 - Announce: "field_x will be removed in v2.0"
v1.9.0 - Deprecation warning when field_x is used
v2.0.0 - field_x removed, migration tool available
v2.0.0+6mo - v1.x support ends
```

### Breaking Changes History

| Version | Change | Migration |
|---------|--------|-----------|
| v1.0.0 | Initial release | N/A |
| v1.1.0 | Additive changes (not breaking) | Automatic - readers support both |
| v1.2.0 | Added `builtin_tool_summary` (not breaking) | Automatic - new field ignored by old readers |
| v1.3.0 | Added `reasoning_tokens` field (not breaking) | Automatic - new field ignored by old readers |
| v1.4.0 | Added token estimation fields (not breaking) | Automatic - new fields ignored by old readers |
| v1.5.0 | Added `smells`, `data_quality`, `zombie_tools` (not breaking) | Automatic - new blocks ignored by old readers |
| v1.6.0 | Added `models_used`, `model_usage`, `tool_calls[].model`, `static_cost` (not breaking) | Automatic - new fields ignored by old readers |
| v1.7.0 | Added `recommendations`, expanded `smells` (12 patterns), `aggregation_metadata` (not breaking) | Automatic - new fields ignored by old readers |

### v1.7.0 Changes (Non-Breaking)

v1.7.0 introduces the Recommendation Engine, expanded smell detection (12 patterns), and cross-session aggregation:

| Change | Type | Impact |
|--------|------|--------|
| Added `recommendations` block | Additive | New block, ignored by old readers |
| Added `aggregation_metadata` block | Additive | New block for multi-session analysis |
| Expanded `smells` to 12 patterns | Additive | 7 new patterns, old patterns unchanged |
| Added `smells[].details` field | Additive | Tool-specific context for each smell |
| Added 4 recommendation types | Feature | REMOVE_UNUSED_SERVER, ENABLE_CACHING, BATCH_OPERATIONS, OPTIMIZE_COST |
| Added trend detection | Feature | Improving/worsening/stable for each pattern |
| New patterns: REDUNDANT_CALLS | Feature | Identical content hash detection |
| New patterns: EXPENSIVE_FAILURES | Feature | High-token failed calls |
| New patterns: UNDERUTILIZED_SERVER | Feature | Server tool usage < 10% |
| New patterns: BURST_PATTERN | Feature | >5 calls within 1 second |
| New patterns: LARGE_PAYLOAD | Feature | Single call >10K tokens |
| New patterns: SEQUENTIAL_READS | Feature | Consecutive file read detection |
| New patterns: CACHE_MISS_STREAK | Feature | 5+ consecutive cache misses |

### v1.6.0 Changes (Non-Breaking)

v1.6.0 introduces Multi-Model Intelligence with per-model tracking, dynamic pricing, and static cost analysis:

| Change | Type | Impact |
|--------|------|--------|
| Added `session.models_used` array | Additive | New field, ignored by old readers |
| Added `model_usage` block | Additive | New block, ignored by old readers |
| Added `tool_calls[].model` field | Additive | New field, only present when known |
| Added `data_quality.pricing_source` | Additive | New field in existing block |
| Added `data_quality.pricing_freshness` | Additive | New field in existing block |
| Added `static_cost` block | Additive | New block with per-server context tax |
| Multi-model per-session tracking | Feature | Per-model token and cost breakdown |
| Dynamic pricing via LiteLLM API | Feature | Real-time pricing with cache/fallback |
| Context tax tracking | Feature | Static token overhead from MCP schemas |

### v1.5.0 Changes (Non-Breaking)

v1.5.0 introduces the Insight Layer with efficiency analysis and data quality indicators:

| Change | Type | Impact |
|--------|------|--------|
| Added `smells` block | Additive | New block, ignored by old readers |
| Added `data_quality` block | Additive | New block, ignored by old readers |
| Added `zombie_tools` block | Additive | New block, ignored by old readers |
| Smell detection for 5 patterns | Feature | HIGH_VARIANCE, TOP_CONSUMER, HIGH_MCP_SHARE, CHATTY, LOW_CACHE_HIT |
| Accuracy labeling | Feature | exact/estimated/calls-only indicators |
| Zombie tool detection | Feature | Tracks unused MCP tools per server |

### v1.4.0 Changes (Non-Breaking)

v1.4.0 adds token estimation metadata for Codex CLI and Gemini CLI:

| Change | Type | Impact |
|--------|------|--------|
| Added `is_estimated` to `tool_calls` | Additive | New field, omitted when false |
| Added `estimation_method` to `tool_calls` | Additive | New field, only present when estimated |
| Added `estimation_encoding` to `tool_calls` | Additive | New field, only present when estimated |
| Codex CLI uses tiktoken o200k_base | Enhancement | ~99-100% accuracy |
| Gemini CLI uses SentencePiece | Enhancement | 100% accuracy |

### v1.3.0 Changes (Non-Breaking)

v1.3.0 adds reasoning token tracking to separate thinking tokens from output:

| Change | Type | Impact |
|--------|------|--------|
| Added `reasoning_tokens` to `token_usage` | Additive | New field, ignored by old readers |
| Gemini CLI `thoughts` tracked separately | Change | More accurate token breakdown |
| Codex CLI `reasoning_output_tokens` tracked separately | Change | More accurate token breakdown |
| TUI shows reasoning row conditionally | Display | Only shown when > 0 |

### v1.2.0 Changes (Non-Breaking)

v1.2.0 adds built-in tool tracking to session output:

| Change | Type | Impact |
|--------|------|--------|
| Added `builtin_tool_summary` block | Additive | New field, ignored by old readers |
| Added `session.builtin_tool_stats` internal field | Additive | Used to build summary |

### v1.1.0 Changes (Non-Breaking)

v1.1.0 introduces additive changes that improve AI-agent readability:

| Change | Type | Impact |
|--------|------|--------|
| Added `_file` header block | Additive | New field, ignored by old readers |
| Added `session` block | Additive | New field, ignored by old readers |
| Added `mcp_summary` block | Additive | New field, ignored by old readers |
| Added flat `tool_calls` array | Additive | New field, ignored by old readers |
| Changed to single-file format | Structure | Old readers can still load v1.0.0 |
| Added date subdirectories | Structure | Old readers can still load v1.0.0 |
| Added timezone to timestamps | Format | ISO 8601 remains valid |
| Removed nested `schema_version` | Removal | Moved to `_file.schema_version` |

**Note**: v1.1.0 is backward compatible. The SessionManager loads both formats transparently.

---

## Deprecation Policy

### Deprecation Warnings

Deprecated features generate warnings:

```python
# Example deprecation warning
import warnings
warnings.warn(
    "field_x is deprecated and will be removed in v2.0. "
    "Use field_y instead.",
    DeprecationWarning
)
```

### Deprecation Timeline

1. **Announcement**: Feature marked deprecated in release notes
2. **Warning Period**: Minimum 2 minor versions with warnings
3. **Removal**: Feature removed in next major version

### Currently Deprecated

| Feature | Deprecated In | Removed In | Replacement |
|---------|---------------|------------|-------------|
| (none currently) | | | |

---

## Stability Tiers

Different parts of Token Audit have different stability guarantees:

### Tier 1: Stable (Data Format)

- Session JSONL format
- Index file format
- Directory structure
- Core schema fields

**Guarantee**: Backward compatible within major version

### Tier 2: Stable (Core API)

- `StorageManager` class
- `BaseTracker` abstract class
- CLI commands (`collect`, `report`)

**Guarantee**: API stable, may add optional parameters

### Tier 3: Evolving (Extensions)

- Platform adapters (may add new ones)
- Report formats (may improve)
- Optional dependencies (may change)

**Guarantee**: Functionality stable, implementation may change

### Tier 4: Experimental

- Features marked `[experimental]`
- New platform integrations
- Preview features

**Guarantee**: May change without notice

---

## Testing Compatibility

### Automated Tests

Our CI pipeline includes:

- **Schema validation tests**: Verify all fields match spec
- **Migration tests**: Test v0.x → v1.x migration
- **Round-trip tests**: Write → Read → Compare
- **Forward compatibility tests**: Old reader, new data

### Manual Verification

Before each release:

1. Load sessions from all previous minor versions
2. Verify index files remain readable
3. Test migration from v0.x format
4. Confirm no data loss

---

## Questions?

If you have questions about the data contract:

1. Check [GitHub Discussions](https://github.com/littlebearapps/token-audit/discussions)
2. Open an issue for clarification
3. Review the [CORE-SCHEMA-SPEC.md](CORE-SCHEMA-SPEC.md) for technical details

---

## Summary

| Aspect | Guarantee |
|--------|-----------|
| Session files | Readable within major version |
| Schema version | Always present |
| Unknown fields | Preserved on load |
| Migration | Tools provided for major upgrades |
| Deprecation | 2+ minor version warning period |
| Breaking changes | Major version bump required |
