# MCP Audit Data Contract

**Version**: 1.1.0
**Last Updated**: 2025-12-03
**Status**: Active

This document defines the data contract for MCP Audit, including backward compatibility guarantees, versioning policy, and migration guidelines.

---

## Table of Contents

1. [Schema v1.1.0](#schema-v110)
2. [Backward Compatibility Guarantee](#backward-compatibility-guarantee)
3. [Versioning Policy](#versioning-policy)
4. [Schema Stability](#schema-stability)
5. [Migration Support](#migration-support)
6. [Breaking Changes](#breaking-changes)
7. [Deprecation Policy](#deprecation-policy)

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
~/.mcp-audit/sessions/
├── 2025-12-01/
│   ├── mcp-audit-2025-12-01T14-19-38.json
│   └── my-project-2025-12-01T15-30-00.json
└── 2025-12-02/
    └── another-project-2025-12-02T09-00-00.json
```

### Complete Schema

```json
{
  "_file": {
    "name": "mcp-audit-2025-12-01T14-19-38.json",
    "type": "mcp_audit_session",
    "purpose": "Complete MCP session log with token usage and tool call statistics for AI agent analysis",
    "schema_version": "1.1.0",
    "schema_docs": "https://github.com/littlebearapps/mcp-audit/blob/main/docs/data-contract.md",
    "generated_by": "mcp-audit v0.4.0",
    "generated_at": "2025-12-01T14:19:55+11:00"
  },

  "session": {
    "id": "mcp-audit-2025-12-01T14-19-38",
    "project": "mcp-audit",
    "platform": "claude-code",
    "model": "claude-opus-4-5-20251101",
    "working_directory": "/Users/user/projects/mcp-audit/main",
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
      {"tool": "mcp__zen__thinkdeep", "server": "zen", "tokens": 150000, "calls": 2}
    ],
    "top_by_calls": [
      {"tool": "mcp__zen__chat", "server": "zen", "calls": 10, "tokens": 30000}
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
| `type` | string | Always `"mcp_audit_session"` |
| `purpose` | string | Human-readable description for AI agents |
| `schema_version` | string | Schema version (e.g., `"1.1.0"`) |
| `schema_docs` | string | URL to this documentation |
| `generated_by` | string | Tool and version (e.g., `"mcp-audit v0.4.0"`) |
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

MCP Audit follows [Semantic Versioning 2.0.0](https://semver.org/):

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
_file.type: str            # Always "mcp_audit_session"
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

MCP Audit provides migration helpers for upgrading between versions:

```bash
# Check for sessions needing migration
mcp-audit migrate --check

# Migrate from v0.x format to v1.x
mcp-audit migrate --from logs/sessions/

# Dry run (preview without changes)
mcp-audit migrate --from logs/sessions/ --dry-run
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

Different parts of MCP Audit have different stability guarantees:

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

1. Check [GitHub Discussions](https://github.com/littlebearapps/mcp-audit/discussions)
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
