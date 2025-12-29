# Bucket Classification

Diagnose WHERE token bloat comes from in AI agent workflows with 4-bucket classification. Available since v1.0.4.

---

## Table of Contents

- [Overview](#overview)
- [The 4 Buckets](#the-4-buckets)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Task Markers](#task-markers)
- [Comparison Reports](#comparison-reports)
- [Decision Matrix](#decision-matrix)
- [WP Navigator Example](#wp-navigator-example)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Problem:** You know your session consumed too many tokens, but you don't know *why*. Was it large data payloads? Duplicate calls? Schema introspection overhead?

**Solution:** Bucket classification automatically categorizes every tool call into one of 4 efficiency buckets, revealing exactly where your tokens go.

```bash
# Analyze current session
token-audit bucket

# Output:
# Bucket               │ Tokens   │   %   │ Calls │ Top Tool
# ─────────────────────┼──────────┼───────┼───────┼──────────────────
# State serialization  │ 15,000   │ 45.5% │   32  │ wpnav_get_page
# Conversation drift   │ 10,200   │ 30.9% │   45  │ mcp__zen__chat
# Tool discovery       │ 5,100    │ 15.5% │    8  │ wpnav_introspect
# Redundant outputs    │ 2,700    │  8.2% │   10  │ wpnav_get_page
```

---

## The 4 Buckets

Buckets are evaluated in priority order. A tool call is classified into the **first matching bucket**.

### 1. Redundant Outputs (Highest Priority)

**Definition:** Duplicate tool calls with identical content.

**Detection:** Same `content_hash` seen more than once. The 2nd+ occurrence is classified as redundant.

**Examples:**
- Calling `wpnav_get_page` twice with the same page ID
- Fetching the same file content multiple times
- Repeated identical API queries

**Solution:** Implement caching, reuse results from earlier calls.

### 2. Tool Discovery

**Definition:** Schema introspection and capability discovery calls.

**Detection:** Tool names matching patterns like:
- `.*_introspect.*` (e.g., `wpnav_introspect`)
- `.*_schema.*` (e.g., `mcp__zen__schema`)
- `.*_describe.*`
- `.*_list_tools.*`
- `.*_capabilities.*`

**Examples:**
- `mcp__backlog__list_tools`
- `wpnav_introspect`
- Fetching server capabilities at session start

**Note:** Some tool discovery is unavoidable. High percentages may indicate excessive re-introspection.

### 3. State Serialization

**Definition:** Large data retrieval operations.

**Detection:** Matches either:
1. **Pattern match:** `.*_get_.*`, `.*_list_.*`, `.*_view.*`, `.*_fetch.*`, `.*_read.*`
2. **Size threshold:** Output tokens >= 5,000 (configurable)

**Examples:**
- `wpnav_get_page` returning full page content
- `mcp__backlog__task_list` returning many tasks
- `Read` tool fetching large files
- Any tool returning >5K tokens of output

**Solution:** Paginate results, fetch only needed fields, use selective queries.

### 4. Conversation Drift (Default)

**Definition:** Everything else — reasoning, retries, errors, analysis.

**Examples:**
- `mcp__zen__chat` for thinking/analysis
- Error responses from failed tool calls
- Retry attempts
- Context building and reasoning

**Note:** Some drift is healthy (reasoning is valuable). Excessive drift may indicate confusion or inefficient workflows.

### Classification Priority

```
Tool call received
        │
        ▼
   ┌────────────────┐
   │ Same content   │──Yes──▶ REDUNDANT
   │ hash seen?     │
   └───────┬────────┘
           │ No
           ▼
   ┌────────────────┐
   │ Matches tool   │──Yes──▶ TOOL DISCOVERY
   │ discovery      │
   │ patterns?      │
   └───────┬────────┘
           │ No
           ▼
   ┌────────────────┐
   │ Matches state  │
   │ patterns OR    │──Yes──▶ STATE SERIALIZATION
   │ output >5K?    │
   └───────┬────────┘
           │ No
           ▼
        DRIFT
```

---

## Quick Start

### Basic Workflow

```bash
# 1. Start a session (normal usage)
# ... use Claude Code, Codex CLI, or Gemini CLI ...

# 2. Analyze bucket distribution
token-audit bucket

# 3. Get detailed breakdown
token-audit bucket --format json
```

### With Task Markers

```bash
# Mark task boundaries for per-task analysis
token-audit task start "Install plugin"
# ... work on task ...
token-audit task end

token-audit task start "Configure settings"
# ... work on task ...
token-audit task end

# Analyze by task
token-audit bucket --by-task
```

### Export for AI Analysis

```bash
# Generate AI-ready report
token-audit bucket --format json > buckets.json

# Or include in full AI export
token-audit export ai --include-buckets
```

---

## Configuration

Bucket patterns and thresholds are configurable via three methods:

### 1. TOML Configuration

Edit `token-audit.toml` (project-level) or `~/.token-audit/token-audit.toml` (user-level):

```toml
[buckets]
# Token threshold for "large payload" classification
large_payload_threshold = 5000

# Minimum duplicate occurrences to classify as redundant
# (2 = original + 1 duplicate)
redundant_min_occurrences = 2

[buckets.patterns]
# State serialization patterns (regex)
state_serialization = [
    ".*_get_.*",
    ".*_get$",
    ".*_list_.*",
    ".*_list$",
    ".*_snapshot.*",
    ".*_export.*",
    ".*_read.*",
    ".*_view.*",
    ".*_view$",
    ".*_fetch.*",
]

# Tool discovery patterns (regex)
tool_discovery = [
    ".*_introspect.*",
    ".*_search_tools.*",
    ".*_describe.*",
    ".*_list_tools.*",
    ".*_schema.*",
    ".*_capabilities.*",
]
```

**Config priority order:**
1. `./token-audit.toml` (project-specific)
2. `~/.token-audit/token-audit.toml` (user config)
3. Package defaults

### 2. TUI Configuration

Access the bucket configuration screen in the TUI:

```bash
# Option 1: Direct access
token-audit ui --view config

# Option 2: From dashboard, press 8
token-audit ui
# Press '8' for bucket configuration
```

From here you can:
- View current patterns for each bucket
- Add/remove patterns
- Modify thresholds
- Reset to defaults

### 3. MCP Tools

Configure buckets programmatically via MCP tools:

| Tool | Purpose |
|------|---------|
| `config_list_patterns` | Get current bucket patterns and thresholds |
| `config_set_threshold` | Set large_payload_threshold or redundant_min_occurrences |
| `config_add_pattern` | Add a regex pattern to a bucket |
| `config_remove_pattern` | Remove a pattern from a bucket |

**Example MCP usage:**

```json
{
  "tool": "config_set_threshold",
  "arguments": {
    "threshold_name": "large_payload_threshold",
    "value": 10000
  }
}
```

---

## Task Markers

Task markers let you group tool calls into logical units for per-task analysis.

### Commands

```bash
# Start tracking a new task
token-audit task start "Implement user login"

# End current task
token-audit task end

# List all completed tasks
token-audit task list

# Show details for a specific task
token-audit task show "Implement user login"
```

### Automatic Task Ending

Starting a new task automatically ends the previous one:

```bash
token-audit task start "Task A"
# ... work ...
token-audit task start "Task B"  # Automatically ends "Task A"
```

### Task List Output

```bash
token-audit task list

# Task                    │ Tokens   │ Calls │ Duration
# ────────────────────────┼──────────┼───────┼──────────
# Implement user login    │ 8,500    │   32  │ 5m 23s
# Configure database      │ 3,200    │   14  │ 2m 10s
# Fix authentication bug  │ 5,100    │   28  │ 4m 45s
```

### Task Detail Output

```bash
token-audit task show "Implement user login"

# Task: Implement user login
# Duration: 5m 23s (10:30:00 - 10:35:23)
# Total tokens: 8,500
# Total calls: 32
#
# Bucket Breakdown:
#   State serialization ... 50.0% (4,250 tokens)
#   Conversation drift .... 30.0% (2,550 tokens)
#   Redundant outputs ..... 15.0% (1,275 tokens)
#   Tool discovery ........ 5.0% (425 tokens)
```

### Session Detection

Task markers use environment variables to detect the current session:
- `CLAUDE_CODE_SESSION` for Claude Code
- `CODEX_SESSION` for Codex CLI
- `GEMINI_SESSION` for Gemini CLI

You can also specify explicitly:

```bash
token-audit task start "My task" --session my-session-id
```

---

## Comparison Reports

### Per-Task Bucket Analysis

Use `--by-task` to see bucket breakdown per task:

```bash
token-audit bucket --by-task

# Per-Task Bucket Analysis
# ═══════════════════════════════════════════════════════════════════════
# Task                    │ Tokens │ State  │ Redund │ Drift  │ Disc
# ────────────────────────┼────────┼────────┼────────┼────────┼────────
# Implement user login    │ 8,500  │ 50.0%  │ 15.0%  │ 30.0%  │ 5.0%
# Configure database      │ 3,200  │ 35.0%  │  5.0%  │ 55.0%  │ 5.0%
# Fix authentication bug  │ 5,100  │ 60.0%  │  2.0%  │ 35.0%  │ 3.0%
# ────────────────────────┴────────┴────────┴────────┴────────┴────────
# AVERAGE                   5,600    48.3%    7.3%    40.0%    4.3%
```

### Output Formats

```bash
# Table (default)
token-audit bucket --format table

# JSON (for programmatic use)
token-audit bucket --format json

# CSV (for spreadsheets)
token-audit bucket --format csv --output buckets.csv
```

### JSON Output Structure

```json
{
  "session_id": "abc123",
  "timestamp": "2025-12-28T10:30:00Z",
  "totals": {
    "tokens": 33000,
    "calls": 95
  },
  "buckets": [
    {
      "bucket": "state_serialization",
      "tokens": 15000,
      "percentage": 45.5,
      "call_count": 32,
      "top_tools": [
        ["wpnav_get_page", 8500],
        ["mcp__backlog__task_view", 3200]
      ]
    }
  ],
  "by_task": [
    {
      "name": "Implement user login",
      "total_tokens": 8500,
      "buckets": {
        "state_serialization": {"tokens": 4250, "percentage": 50.0},
        "redundant": {"tokens": 1275, "percentage": 15.0}
      }
    }
  ]
}
```

---

## Decision Matrix

Use this matrix to interpret bucket analysis results and take action:

| Bucket | % Range | Interpretation | Action |
|--------|---------|----------------|--------|
| **State Serialization** | <30% | Healthy | No action needed |
| | 30-50% | Moderate | Review large payloads, consider pagination |
| | >50% | High | Implement selective queries, reduce payload sizes |
| **Redundant Outputs** | <5% | Healthy | No action needed |
| | 5-15% | Moderate | Consider caching frequently-accessed data |
| | >15% | High | Implement caching layer, reuse results |
| **Tool Discovery** | <10% | Healthy | Normal introspection overhead |
| | 10-20% | Moderate | Check for repeated introspection |
| | >20% | High | Cache schema info, reduce re-introspection |
| **Drift** | <40% | Healthy | Normal reasoning overhead |
| | 40-60% | Moderate | Review for confusion or inefficient patterns |
| | >60% | High | Simplify prompts, reduce retries |

### Red Flags

| Pattern | Indicates | Solution |
|---------|-----------|----------|
| Redundant >20% | No caching | Implement tool result caching |
| State + Redundant >60% | Fetching same data repeatedly | Cache data between calls |
| Discovery >25% | Schema fetched every turn | Cache server capabilities |
| Single tool >50% of bucket | Over-reliance on one tool | Diversify or optimize that tool |

---

## WP Navigator Example

This section shows bucket classification patterns specific to WordPress agent workflows using WP Navigator.

### WordPress-Specific Patterns

Add these patterns to your `token-audit.toml` for better WP Navigator classification:

```toml
[buckets.patterns]
state_serialization = [
    # Default patterns...
    ".*_get_.*",
    ".*_list_.*",
    # WP Navigator specific
    "wpnav_get_page",
    "wpnav_get_post",
    "wpnav_list_posts",
    "wpnav_list_pages",
    "wpnav_list_plugins",
    "wpnav_list_themes",
    "wpnav_list_media",
    "wpnav_get_theme",
    "wpnav_get_plugin",
]

tool_discovery = [
    # Default patterns...
    ".*_introspect.*",
    # WP Navigator specific
    "wpnav_introspect",
    "wpnav_gutenberg_introspect",
    "wpnav_list_taxonomies",
]
```

### Typical WP Navigator Session

A healthy WP Navigator session might look like:

```
Bucket               │ Tokens   │   %   │ Top Tool
─────────────────────┼──────────┼───────┼─────────────────────
State serialization  │ 12,000   │ 40.0% │ wpnav_get_page
Conversation drift   │ 10,500   │ 35.0% │ mcp__zen__chat
Tool discovery       │ 4,500    │ 15.0% │ wpnav_introspect
Redundant outputs    │ 3,000    │ 10.0% │ wpnav_get_page
```

### WP Navigator Optimization Tips

1. **High State Serialization (>50%)**
   - Use `wpnav_get_page` with specific fields instead of full content
   - Paginate `wpnav_list_posts` results
   - Avoid fetching full theme/plugin details when only names needed

2. **High Redundant (>15%)**
   - Cache page content between edits
   - Don't re-fetch plugin list after each install
   - Use task markers to track what's already fetched

3. **High Discovery (>20%)**
   - `wpnav_introspect` should only run once per session
   - Cache Gutenberg block definitions
   - Don't re-discover taxonomies mid-task

### 5-Task WP Navigator Test

Run this sequence to test bucket classification:

```bash
# Task 1: Site Discovery
token-audit task start "Site Discovery"
# Introspect site capabilities
token-audit task end

# Task 2: Content Audit
token-audit task start "Content Audit"
# List pages, posts, analyze structure
token-audit task end

# Task 3: Theme Changes
token-audit task start "Theme Changes"
# Modify theme settings
token-audit task end

# Task 4: Plugin Install
token-audit task start "Plugin Install"
# Install and configure plugin
token-audit task end

# Task 5: Content Edit
token-audit task start "Content Edit"
# Edit page content
token-audit task end

# Analyze results
token-audit bucket --by-task
```

**Expected results:**
- Task 1 (Discovery): High tool_discovery, low everything else
- Task 2 (Audit): High state_serialization
- Tasks 3-5: Balanced, low redundant if caching works

---

## Troubleshooting

### No Data in Bucket Report

**Symptom:** `token-audit bucket` shows empty or zero tokens.

**Causes:**
1. No session data collected yet
2. Wrong platform detected

**Solutions:**
```bash
# Check for sessions
token-audit sessions list

# Specify platform explicitly
token-audit bucket --platform claude-code

# Specify session directly
token-audit bucket --session ~/.token-audit/sessions/claude-code/2024-01-15/session.json
```

### Patterns Not Matching

**Symptom:** Tools being classified into wrong buckets.

**Causes:**
1. Pattern syntax error (regex)
2. Pattern order (checked in definition order)

**Solutions:**
```bash
# View current patterns
token-audit bucket --show-config

# Test a specific pattern
python -c "import re; print(re.match(r'.*_get_.*', 'wpnav_get_page'))"

# Validate TOML config
python -c "import tomllib; tomllib.load(open('token-audit.toml', 'rb'))"
```

### Task Markers Not Working

**Symptom:** `token-audit task list` shows no tasks.

**Causes:**
1. Session ID mismatch
2. Markers stored in different session

**Solutions:**
```bash
# Check which sessions have markers
token-audit task list --all-sessions

# Specify session explicitly
token-audit task list --session <session-id>

# Check environment variables
echo $CLAUDE_CODE_SESSION
echo $CODEX_SESSION
```

### High Redundant Despite Caching

**Symptom:** Redundant bucket is high even though you're caching.

**Causes:**
1. `content_hash` differs (different parameters, timestamps)
2. Caching not applied to all calls

**Solutions:**
```bash
# Get detailed JSON to see content hashes
token-audit bucket --format json | jq '.call_classifications'

# Look for tools with multiple hashes
# Different hashes = different content = not truly redundant
```

---

## Related Documentation

- [Features Reference](features.md) — All Token Audit features
- [Configuration](configuration.md) — Full configuration options
- [CLI Reference](../README.md#cli-reference) — All commands
- [MCP Server Guide](mcp-server-guide.md) — Using Token Audit via MCP
