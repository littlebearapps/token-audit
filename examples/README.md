# MCP Audit Examples

This directory contains example sessions demonstrating the MCP Audit data format.

## Contents

| Directory | Platform | Description |
|-----------|----------|-------------|
| `claude-code-session/` | Claude Code | Example Claude Code tracking session |
| `codex-cli-session/` | Codex CLI | Example Codex CLI tracking session |
| `gemini-cli-session/` | Gemini CLI | Example Gemini CLI tracking session |

## Purpose

These examples serve multiple purposes:

1. **Documentation** - Show the expected data format
2. **Testing** - Validate parsing and analysis code
3. **Development** - Reference for adding new platform adapters
4. **Debugging** - Compare against real sessions when troubleshooting

## Session Format

All sessions use the JSONL (JSON Lines) format:

```
session-{YYYYMMDD}T{HHMMSS}-{random}.jsonl
```

Each line is a self-contained JSON event:

```json
{"schema_version":"1.6.0","event_type":"token_usage","timestamp":"...","data":{...}}
```

## Event Types

| Type | Description | Fields |
|------|-------------|--------|
| `session_start` | Session begins | session_id, platform, project, model |
| `token_usage` | Token consumption | input_tokens, output_tokens, cache_* |
| `tool_call` | Tool invocation | tool_name, server, tokens_used |
| `session_end` | Session ends | duration_ms, totals |

## Privacy

All example sessions are sanitized:

- ✅ No actual prompt or response content
- ✅ No sensitive tool arguments
- ✅ No real file paths
- ✅ Anonymized project names
- ✅ Safe for public sharing

## Using Examples

### Load a Session

```python
import json

with open("claude-code-session/session-20251125T103045-abc123.jsonl") as f:
    events = [json.loads(line) for line in f]

print(f"Loaded {len(events)} events")
```

### Analyze Examples

```bash
# Analyze all example sessions
mcp-audit report ./examples/

# Analyze specific platform
mcp-audit report ./examples/claude-code-session/
```

### Test Against Examples

```bash
# Run tests that use example data
pytest tests/ -k "example"
```

## Adding New Examples

When adding examples for a new platform:

1. Create directory: `examples/{platform}-session/`
2. Add JSONL file: `session-{timestamp}-{id}.jsonl`
3. Add README.md explaining platform specifics
4. Ensure all data is sanitized (no sensitive content)

See existing examples for format reference.

## Schema Version

All examples use schema version `1.0.0`. If the schema changes, examples will be updated to demonstrate the new format.
