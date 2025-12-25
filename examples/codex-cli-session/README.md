# Example Codex CLI Session

This directory contains a sanitized example session from Codex CLI tracking.

## Files

- `session-20251125T143022-def456.jsonl` - Complete session event stream

## Session Summary

| Metric | Value |
|--------|-------|
| Duration | ~4 minutes |
| Total Input Tokens | 48,567 |
| Total Output Tokens | 10,789 |
| Cache Created | 892 |
| Cache Read | 126,859 |
| Cache Efficiency | ~72% |
| Tool Calls | 8 |

## Tool Breakdown

### MCP Tools (External)

| Tool | Calls | Tokens | Avg/Call |
|------|-------|--------|----------|
| `mcp__zen__thinkdeep` | 1 | 38,976 | 38,976 |
| `mcp__zen__chat` | 1 | 2,890 | 2,890 |
| `mcp__brave-search__brave_web_search` | 1 | 6,789 | 6,789 |

### Built-in Tools (Codex-Specific)

| Tool | Calls | Tokens | Avg/Call |
|------|-------|--------|----------|
| `read_file` | 1 | 156 | 156 |
| `execute_zsh` | 1 | 345 | 345 |
| `write_to_file` | 1 | 456 | 456 |
| `glob_search` | 1 | 123 | 123 |
| `list_directory` | 1 | 89 | 89 |

## Platform Differences

### Built-in Tool Names

Codex CLI uses different built-in tool names than Claude Code:

| Codex CLI | Claude Code Equivalent |
|-----------|------------------------|
| `read_file` | `Read` |
| `write_to_file` | `Write` |
| `execute_zsh` | `Bash` |
| `glob_search` | `Glob` |
| `list_directory` | (via Bash) |

### MCP Tool Normalization

Raw Codex CLI MCP tools have a `-mcp` suffix:
- Raw: `mcp__zen-mcp__chat`
- Normalized: `mcp__zen__chat`

MCP Audit normalizes these automatically for consistent tracking across platforms.

### Model Identifier

This session uses `gpt-4o` instead of Claude models.

## Event Types

This session demonstrates all standard event types:

1. **session_start** - Session initialization with metadata
2. **token_usage** - Token consumption updates
3. **tool_call** - MCP and built-in tool invocations
4. **session_end** - Final summary with totals

## Data Format

Each line is a JSON object with:

```json
{
  "schema_version": "1.0.0",
  "event_type": "tool_call",
  "timestamp": "2025-11-25T14:30:40.012Z",
  "data": {
    "tool_name": "mcp__zen__chat",
    "server": "zen",
    "tokens_used": 2890,
    "duration_ms": 1987
  }
}
```

## Privacy Notes

This session has been sanitized:

- ✅ No prompt content
- ✅ No response content
- ✅ No tool arguments
- ✅ No file paths
- ✅ Anonymized project name

Safe to share for debugging, analysis, or documentation.

## Loading This Session

```python
from token_audit.storage import StorageManager

# Load manually
with open("session-20251125T143022-def456.jsonl") as f:
    events = [json.loads(line) for line in f]

# Or use StorageManager
storage = StorageManager()
events = storage.read_session(
    platform="codex_cli",
    session_id="session-20251125T143022-def456",
    date="2025-11-25"
)
```

## Analyzing This Session

```bash
# Generate report from this session
token-audit report ./examples/codex-cli-session/

# Output includes:
# - Token usage breakdown
# - Cost estimates (OpenAI pricing)
# - Tool efficiency analysis
```

## Cross-Platform Comparison

Use Token Audit to compare costs across platforms:

```bash
# Analyze both example sessions
token-audit report ./examples/

# Compare Claude Code vs Codex CLI:
# - Different pricing models
# - Similar MCP tool usage patterns
# - Platform-specific built-in tools
```
