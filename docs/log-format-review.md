# MCP Audit Log Format Review

**Date**: 2025-12-03
**Task**: task-36 - Review session log files for AI-Agent readability and completeness
**Status**: Analysis Complete - Awaiting User Approval

---

## Executive Summary

After reviewing our current log format, the three platform adapters, and **official documentation for all three platforms (Claude Code, Codex CLI, and Gemini CLI)**, I've identified several opportunities to improve AI-Agent readability while maintaining data completeness.

**Critical Finding**: Our log files are **not self-describing**. An AI agent opening `mcp-backlog.json` has zero context—no session ID, no project, no platform, no timestamp, no idea what other files exist. This is a fundamental AI-readability failure.

**Key Finding**: Our current format is functional but has redundancy and deep nesting that makes it harder for AI agents to quickly parse session summaries. **All three official platforms use flat OpenTelemetry-style metrics**, not nested hierarchies—our schema should align with this industry standard.

**Claude Code Insight**: Anthropic's official telemetry uses flat metrics (`claude_code.token.usage`, `claude_code.cost.usage`, etc.) with type attributes, not nested `server_sessions.{server}.tools.{tool}.call_history[]` structures like ours.

**Proposed Solution**: Schema v1.1.0 with:
1. **Self-describing `_file` header** in every log file
2. **Single file per session** (no more separate mcp-*.json files)
3. **Flat `tool_calls` array** instead of 6-level-deep nesting
4. **ISO 8601 timestamps with timezone**
5. **Model and working_directory at root level**

---

## Current Schema Analysis

### What We Track vs Official Platforms

| Data | MCP Audit | Claude Code (Official) | Codex CLI | Gemini CLI |
|------|-----------|------------------------|-----------|------------|
| Input tokens | ✅ | ✅ `"input"` | ✅ | ✅ `"input"` |
| Output tokens | ✅ | ✅ `"output"` | ✅ | ✅ `"output"` |
| Cache created | ✅ | ✅ `"cacheCreation"` | ❌ | ❌ |
| Cache read | ✅ | ✅ `"cacheRead"` | ✅ | ✅ `"cache"` |
| Thinking tokens | ❌ | ❌ | ❌ | ✅ `"thought"` |
| Duration/latency | ❌ | ✅ `active_time.total` | ❌ | ✅ `tool.call.latency` |
| Cost (USD) | ✅ (estimated) | ✅ `cost.usage` | ❌ | ❌ |
| Tool parameters | ✅ | ✅ (via tool_result) | ✅ | ❌ |
| Content hash | ✅ | ❌ | ✅ | ❌ |
| Model name | ✅ | ✅ (app.version) | ✅ | ✅ |
| Session ID | ✅ | ✅ `session.id` | ❌ | ❌ |
| User prompts | ❌ | ✅ `user_prompt` | ❌ | ❌ |
| API errors | ❌ | ✅ `api_error` | ❌ | ❌ |

### Current File Structure

```
~/.token-audit/sessions/<project>-<timestamp>/
├── summary.json      # Main session data (currently ~70 lines for 1 MCP call)
└── mcp-<server>.json # Per-server breakdown (redundant with summary.json)
```

---

## Issues Identified

### 0. Missing Self-Describing File Context (Critical - AI Readability)

**Current State**: Log files lack context needed for AI agents to understand them in isolation.

**What's Missing from Each File**:

| Field | summary.json | mcp-*.json | AI Agent Needs? |
|-------|-------------|------------|-----------------|
| File name inside file | ❌ Missing | ❌ Missing | ✅ **Critical** |
| File # of total in session | ❌ Missing | ❌ Missing | ✅ **Critical** |
| Related files list | ❌ Missing | ❌ Missing | ✅ **Critical** |
| Working directory | ❌ Missing | ❌ Missing | ✅ **High** |
| Session ID | ✅ Present | ❌ **Missing** | ✅ **Critical** |
| Project name | ✅ Present | ❌ **Missing** | ✅ **Critical** |
| Platform | ✅ Present | ❌ **Missing** | ✅ **Critical** |
| AI Model used | ⚠️ Buried 6 levels | ⚠️ Buried 5 levels | ✅ **High** |
| Timestamp | ✅ Present | ❌ **Missing** | ✅ **Critical** |
| Timezone | ❌ Missing | ❌ Missing | ✅ **Medium** |
| File purpose description | ❌ Missing | ❌ Missing | ✅ **Medium** |
| Schema docs URL | ❌ Missing | ❌ Missing | ✅ **Medium** |

**The mcp-backlog.json Problem**: An AI agent opening this file has **zero context**:
```json
{
  "schema_version": "1.0.0",
  "server": "backlog",
  "tools": { ... }
}
```
No session_id, no project, no platform, no timestamp, no idea what other files exist.

**Recommendation**: Every log file must be **self-describing** with a `_file` header block:
```json
{
  "_file": {
    "name": "session.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics",
    "schema_version": "1.1.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.4.0",
    "generated_at": "2025-12-01T14:19:55+11:00"
  },
  ...
}
```

### 1. Redundant `schema_version` at Every Level (High Impact)

**Current**: `schema_version: "1.0.0"` appears 4+ times per tool call:
- Root session object
- Each ServerSession
- Each ToolStats
- Each Call

**Impact**: For a session with 10 MCP calls across 3 servers, that's ~40 redundant schema_version entries.

**Recommendation**: Keep `schema_version` only at root level. Nested objects inherit the parent schema version.

### 2. Deep Nesting Makes AI Parsing Harder (High Impact)

**Current**: To get a tool's token usage:
```
session.server_sessions.backlog.tools["mcp__backlog__task_list"].call_history[0].total_tokens
```
That's **6 levels deep**.

**Recommendation**: Add a flat `tool_calls` array at the session root for quick access:
```json
{
  "tool_calls": [
    {"tool": "mcp__backlog__task_list", "tokens": 94852, "timestamp": "..."},
    {"tool": "mcp__zen__chat", "tokens": 45000, "timestamp": "..."}
  ]
}
```

### 3. Duplicate Data Storage (Medium Impact)

**Current Issues**:
- `tool_name` appears as both dictionary key AND inside the Call object
- `mcp-<server>.json` files duplicate data already in `summary.json`
- `server` name appears as both dictionary key AND `server` field

**Recommendation**:
- Remove `tool_name` from Call objects (it's the dict key)
- Remove separate `mcp-*.json` files (all data in summary.json)

### 4. Null Values Add Noise (Medium Impact)

**Current**: Duration fields are `null` when not tracked:
```json
{
  "total_duration_ms": null,
  "avg_duration_ms": null,
  "max_duration_ms": null,
  "min_duration_ms": null
}
```

**Recommendation**: Omit fields that have no data, or use `0` for numeric fields.

### 5. call_history Can Grow Very Large (Medium Impact)

**Current**: Every single call is stored with full details in `call_history[]`.

**Impact**: A 2-hour session with 100 MCP calls could have 500+ lines just for call_history.

**Recommendation**:
- Keep detailed `call_history` for deduplication/analysis
- Add pre-computed summaries at session level for quick AI access

### 6. Missing Useful Metadata (Low Impact)

**Currently Missing**:
- `working_directory` - Where token-audit was run from
- `source_files` - Which session files were monitored
- `top_tools_by_tokens` - Pre-computed top 5
- `top_tools_by_calls` - Pre-computed top 5

---

## Comparison with Official Formats

### Claude Code (Official OpenTelemetry)
- Uses **OpenTelemetry standard** with flat metrics (same pattern as Gemini CLI)
- Metric types:
  - `claude_code.token.usage` - Token counts with type attribute
  - `claude_code.session.count` - Session tracking
  - `claude_code.cost.usage` - Cost in USD (millicents)
  - `claude_code.active_time.total` - Active usage time in ms
- Token type attributes: `"input"`, `"output"`, `"cacheRead"`, `"cacheCreation"`
- Events (spans):
  - `claude_code.user_prompt` - User input events
  - `claude_code.tool_result` - Tool execution results
  - `claude_code.api_request` - API call tracking
  - `claude_code.api_error` - Error events
- Standard attributes: `session.id`, `app.version`, `organization.id`, `user.account_uuid`, `terminal.type`
- Session logs stored in: `~/.claude/projects/<encoded-directory>/*.jsonl`
- Uses JSONL format (newline-delimited JSON)

### Codex CLI (Official)
- Stores JSONL in `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl`
- Has `--experimental-json` flag for structured JSON output
- Uses flat event stream (one JSON per line)

### Gemini CLI (Native JSON Sessions)
- Uses **native JSON session files** at `~/.gemini/tmp/<project_hash>/chats/session-*.json`
- Per-message token breakdown: `input`, `output`, `cached`, `thoughts`, `tool`, `total`
- **Thinking tokens** tracked separately (Gemini-specific)
- Tool calls in `toolCalls` array with MCP tools identified by `mcp__` prefix
- No OTEL setup required - parses session files directly

**Key Insight**: While Claude Code and Codex CLI use flat event streams, Gemini CLI stores complete session state in JSON files. MCP Audit adapts to each platform's native format.

---

## Recommendations Summary

### Priority 0: Self-Describing Files for AI Agents (Critical)
Every log file must include a `_file` header block:
```json
{
  "_file": {
    "name": "session.json",
    "type": "token_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics",
    "schema_version": "1.1.0",
    "schema_docs": "https://github.com/littlebearapps/token-audit/blob/main/docs/data-contract.md",
    "generated_by": "token-audit v0.4.0",
    "generated_at": "2025-12-01T14:19:55+11:00"
  }
}
```
**Plus**: Single-file approach (remove mcp-*.json, everything in one session.json)

### Priority 1: Remove Redundant schema_version (Easy Win)
- Keep only at root level (moved to `_file.schema_version`)
- **Estimated reduction**: 30-50% fewer lines in output

### Priority 2: Add Flat tool_calls Array (High Value)
```json
{
  "quick_summary": {
    "top_tools_by_tokens": [
      {"tool": "mcp__zen__thinkdeep", "tokens": 150000, "calls": 2},
      {"tool": "mcp__backlog__task_list", "tokens": 94852, "calls": 1}
    ],
    "top_tools_by_calls": [
      {"tool": "mcp__zen__chat", "calls": 15, "tokens": 45000}
    ]
  }
}
```

### Priority 3: Remove Separate mcp-*.json Files (Simplify)
- All data already in summary.json
- One file per session is easier to manage

### Priority 4: Omit Null/Zero Fields (Cleaner Output)
- Only include fields with actual data
- Use `0` instead of `null` for numeric fields when tracking is enabled but value is zero

### Priority 5: Add Working Directory Metadata (Useful Context)
```json
{
  "metadata": {
    "working_directory": "/Users/user/projects/my-app",
    "source_files": ["session-abc123.jsonl"],
    "token_audit_command": "token-audit collect --platform claude-code"
  }
}
```

---

## Proposed Schema v1.1.0

### File Naming Convention

**Single file per session** (replaces summary.json + mcp-*.json):
```
~/.token-audit/sessions/
├── token-audit-2025-12-01T14-19-38.json      # Single self-contained file
├── my-project-2025-12-01T15-30-00.json     # Project name + timestamp
└── ...
```

Or with subdirectories for organization:
```
~/.token-audit/sessions/
├── 2025-12-01/
│   ├── token-audit-2025-12-01T14-19-38.json
│   └── my-project-2025-12-01T15-30-00.json
└── 2025-12-02/
    └── ...
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
      {"tool": "mcp__zen__thinkdeep", "server": "zen", "tokens": 150000, "calls": 2},
      {"tool": "mcp__backlog__task_list", "server": "backlog", "tokens": 94852, "calls": 1}
    ],
    "top_by_calls": [
      {"tool": "mcp__zen__chat", "server": "zen", "calls": 10, "tokens": 30000}
    ]
  },

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
    },
    {
      "index": 2,
      "timestamp": "2025-12-01T14:20:15+11:00",
      "tool": "mcp__zen__chat",
      "server": "zen",
      "input_tokens": 50,
      "output_tokens": 100,
      "total_tokens": 150
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

### Key Changes from v1.0.0:

**AI Readability (New)**:
1. **Added**: `_file` header block - self-describing file metadata
2. **Added**: `_file.purpose` - explains what this file is for
3. **Added**: `_file.schema_docs` - link to schema documentation
4. **Changed**: All timestamps now ISO 8601 with timezone (`+11:00`)
5. **Added**: `tool_calls[].index` - sequential call number for context

**Structure (Previously Proposed)**:
6. **Removed**: Nested `server_sessions` with repeated schema_version
7. **Removed**: Separate `mcp-*.json` files (single file approach)
8. **Added**: `session` block with all session context at root level
9. **Added**: `mcp_summary.servers_used` - quick list of MCP servers
10. **Flattened**: `tool_calls` array replaces nested structure
11. **Simplified**: Each tool_call includes server name directly
12. **Renamed**: `cost_estimate` → `cost_estimate_usd` for clarity

---

## Migration Path

### Backward Compatibility
- v1.1.0 readers can read v1.0.0 files (just ignore new fields)
- v1.0.0 readers can read v1.1.0 files (just ignore new fields)
- Per data-contract.md, additive changes are minor version bumps

### Implementation Steps
1. Update `base_tracker.py` dataclasses
2. Update `save_session()` to use new format
3. Update report generation to read both formats
4. Remove separate mcp-*.json file generation
5. Update documentation

---

## Questions for User Approval

### AI Readability (Critical)
1. **Add `_file` header block?** Self-describing file metadata with name, type, purpose, schema_version, schema_docs, generated_by, generated_at.
2. **Single file per session?** Remove separate mcp-*.json files, everything in one `<session-id>.json` file.
3. **ISO 8601 with timezone?** Change `"2025-12-01T14:19:38.619229"` → `"2025-12-01T14:19:38+11:00"`.
4. **Add `tool_calls[].index`?** Sequential call number (1, 2, 3...) for context.

### Structure (Previously Proposed)
5. **Flatten to `tool_calls` array?** Replaces 6-level-deep nested `server_sessions` structure.
6. **Add `session` block at root?** With id, project, platform, model, working_directory, started_at, ended_at, duration_seconds, source_files.
7. **Add `mcp_summary`?** Pre-computed top_by_tokens, top_by_calls, servers_used for quick AI access.
8. **Rename `cost_estimate` → `cost_estimate_usd`?** Explicit currency for clarity.
9. **Remove redundant `schema_version`?** Keep only in `_file.schema_version`, not at every nested level.

### File Naming
10. **Single file naming?** `<project>-<timestamp>.json` instead of directory with multiple files.
11. **Date subdirectories?** `~/.token-audit/sessions/2025-12-01/<session>.json` for organization.

---

## Next Steps (Pending Approval)

- [ ] Get user approval on proposed changes
- [ ] Implement schema v1.1.0 in base_tracker.py
- [ ] Update save_session() to use new format with `_file` header
- [ ] Update report generation to read both v1.0.0 and v1.1.0 formats
- [ ] Remove separate mcp-*.json file generation
- [ ] Update tests for new schema
- [ ] Update data-contract.md with v1.1.0 schema
- [ ] Update quickref documentation
