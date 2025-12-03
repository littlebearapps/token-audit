# Codex CLI Setup Guide

This guide explains how to configure MCP Audit to track your Codex CLI (OpenAI) sessions.

## Prerequisites

- Codex CLI installed (`npm install -g @openai/codex` or via npx)
- MCP Audit installed (`pip install mcp-audit`)

## Session File Location

Codex CLI automatically stores session files in:

```
~/.codex/sessions/YYYY/MM/DD/*.jsonl
```

Each session creates a new JSONL file with events including:
- `session_meta`: Session metadata (ID, CWD, CLI version, git info)
- `turn_context`: Model selection and settings
- `event_msg`: Token usage (`token_count` events)
- `response_item`: Tool calls including MCP tools

## Tracking Modes

### 1. Live Monitoring (Recommended)

Monitor a running Codex CLI session:

```bash
# Start Codex CLI in one terminal
codex

# In another terminal, monitor the session
mcp-audit collect --platform codex_cli

# Or use Python API
from mcp_audit.codex_cli_adapter import CodexCLIAdapter
adapter = CodexCLIAdapter(project="my-project")
adapter.start_tracking()
```

### 2. Batch Processing

Analyze completed sessions:

```bash
# Process the most recent session
mcp-audit collect --platform codex_cli --batch --latest

# Process a specific session file
mcp-audit collect --platform codex_cli --batch --session-file ~/.codex/sessions/2025/11/04/session.jsonl
```

### 3. List Available Sessions

View recent sessions with metadata:

```bash
python -c "
from mcp_audit.codex_cli_adapter import CodexCLIAdapter
adapter = CodexCLIAdapter(project='my-project')
for path, mtime, sid in adapter.list_sessions(limit=10):
    print(f'{mtime.strftime(\"%Y-%m-%d %H:%M\")} - {sid or \"no-id\"[:8]}')
    print(f'  {path}')
"
```

## What Gets Tracked

### Token Usage
- `input_tokens`: User prompts and context
- `output_tokens`: Model responses (includes `reasoning_output_tokens`)
- `cached_input_tokens`: Prompt cache hits

### MCP Tool Calls
Only tools prefixed with `mcp__` are tracked:
- `mcp__zen__chat` → zen server, chat tool
- `mcp__brave-search__web_search` → brave-search server, web_search tool

### Model Detection
The adapter detects and records the model from `turn_context` events:
- `gpt-5.1`, `gpt-5.1-codex-max`, `gpt-5-codex`
- `gpt-4.1`, `gpt-4.1-mini`
- `o4-mini`, `o3-mini`

### Session Metadata
- CLI version
- Working directory (CWD)
- Git info (commit hash, branch, repository URL)

## Configuration

### Custom Codex Directory

If your Codex config is in a non-standard location:

```python
adapter = CodexCLIAdapter(
    project="my-project",
    codex_dir=Path("/custom/codex/path"),
)
```

### Date Filtering

Filter sessions by date range:

```python
from datetime import datetime
adapter = CodexCLIAdapter(project="my-project")

# Sessions from last 7 days
since = datetime(2025, 11, 1)
until = datetime(2025, 11, 30)
sessions = adapter.get_session_files(since=since, until=until)
```

## Example Output

```
$ mcp-audit collect --platform codex_cli --batch --latest

[Codex CLI] Processing: rollout-2025-11-23T16-40-08-...jsonl
  Total tokens: 10,454,282
  Input tokens: 5,664,572
  Output tokens: 117,582
  Cache read tokens: 4,672,128
  Cache efficiency: 45.2%
  MCP calls: 12
  Model: GPT-5.1 Codex Max

Session saved to: ~/.mcp-audit/sessions/codex-cli/...
```

## Pricing Configuration

Edit `mcp-audit.toml` to add custom Codex models:

```toml
[pricing.openai]
# Standard models (included by default)
"gpt-5.1" = { input = 1.25, output = 10.0, cache_read = 0.125 }

# Codex CLI specific models
"gpt-5.1-codex-max" = { input = 1.25, output = 10.0, cache_read = 0.125 }
"gpt-5-codex" = { input = 1.25, output = 10.0, cache_read = 0.125 }
```

## Troubleshooting

### No Sessions Found

1. Verify Codex has created sessions:
   ```bash
   ls ~/.codex/sessions/
   ```

2. Check for recent sessions:
   ```bash
   find ~/.codex/sessions -name "*.jsonl" -mtime -7
   ```

### Wrong Session Selected

Use `--session-file` to specify exact file:
```bash
mcp-audit collect --platform codex_cli --session-file /path/to/session.jsonl
```

### Model Not Detected

Ensure the session contains `turn_context` events with a `model` field:
```bash
head -20 ~/.codex/sessions/2025/11/04/session.jsonl | grep turn_context
```
