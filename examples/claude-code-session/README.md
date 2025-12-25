# Example Claude Code Session

This directory contains a sanitized example session from Claude Code tracking.

## Files

- `session-20251125T103045-abc123.jsonl` - Complete session event stream

## Session Summary

| Metric | Value |
|--------|-------|
| Duration | ~4 minutes |
| Total Input Tokens | 61,234 |
| Total Output Tokens | 13,890 |
| Cache Created | 1,523 |
| Cache Read | 278,155 |
| Cache Efficiency | ~78% |
| Tool Calls | 9 |

## Tool Breakdown

### MCP Tools (External)

| Tool | Calls | Tokens | Avg/Call |
|------|-------|--------|----------|
| `mcp__zen__thinkdeep` | 1 | 45,678 | 45,678 |
| `mcp__zen__chat` | 2 | 5,801 | 2,901 |
| `mcp__brave-search__brave_web_search` | 1 | 8,765 | 8,765 |

### Built-in Tools

| Tool | Calls | Tokens | Avg/Call |
|------|-------|--------|----------|
| `Read` | 1 | 234 | 234 |
| `Edit` | 1 | 567 | 567 |
| `Write` | 1 | 456 | 456 |
| `Bash` | 1 | 234 | 234 |

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
  "timestamp": "2025-11-25T10:31:02.123Z",
  "data": {
    "tool_name": "mcp__zen__chat",
    "server": "zen",
    "tokens_used": 3456,
    "duration_ms": 2341
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
with open("session-20251125T103045-abc123.jsonl") as f:
    events = [json.loads(line) for line in f]

# Or use StorageManager
storage = StorageManager()
events = storage.read_session(
    platform="claude_code",
    session_id="session-20251125T103045-abc123",
    date="2025-11-25"
)
```

## Analyzing This Session

```bash
# Generate report from this session
token-audit report ./examples/claude-code-session/

# Output includes:
# - Token usage breakdown
# - Cost estimates
# - Tool efficiency analysis
```
