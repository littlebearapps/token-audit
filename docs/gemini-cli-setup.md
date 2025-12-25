# Gemini CLI Setup Guide

This guide explains how to configure Token Audit to track your Gemini CLI sessions.

## Prerequisites

- Gemini CLI installed (`npm install -g @anthropic/gemini-cli`)
- Token Audit installed (`pip install token-audit`)

## Session File Location

Gemini CLI stores session files per-project using a hash of the working directory:

```
~/.gemini/tmp/<project_hash>/chats/session-*.json
```

Where `<project_hash>` is a SHA256 hash of your project's absolute path.

## Session File Format

Each session file is a JSON document containing:
- `sessionId`: Unique session identifier
- `projectHash`: Hash identifying the project
- `startTime`/`lastUpdated`: Session timestamps
- `messages`: Array of conversation messages

### Message Structure

```json
{
  "type": "gemini",
  "content": "...",
  "model": "gemini-2.5-pro",
  "thoughts": [...],
  "toolCalls": [...],
  "tokens": {
    "input": 7420,
    "output": 84,
    "cached": 0,
    "thoughts": 868,
    "tool": 0,
    "total": 8372
  }
}
```

## Tracking Modes

### 1. Live Monitoring

Monitor a running Gemini CLI session:

```bash
# Start Gemini CLI in your project directory
cd /path/to/project
gemini

# In another terminal, from the same directory
token-audit collect --platform gemini-cli

# Or use Python API
from token_audit.gemini_cli_adapter import GeminiCLIAdapter
adapter = GeminiCLIAdapter(project="my-project")
adapter.start_tracking()
```

### 2. Batch Processing

Analyze completed sessions:

```bash
# Process the most recent session (auto-detects project hash)
cd /path/to/project
token-audit collect --platform gemini-cli --batch --latest

# Process a specific session file
token-audit collect --platform gemini-cli --batch \
  --session-file ~/.gemini/tmp/abc123.../chats/session-2025-11-07T05-10-xyz.json
```

### 3. List Available Projects

View all project hashes with their last activity:

```bash
python -c "
from token_audit.gemini_cli_adapter import GeminiCLIAdapter
adapter = GeminiCLIAdapter(project='my-project')
for h, path, mtime in adapter.list_available_hashes():
    print(f'{h[:16]}...  {mtime.strftime(\"%Y-%m-%d %H:%M\")}')
    print(f'  {path}')
"

# Or use CLI
python -m token_audit.gemini_cli_adapter --list-hashes
```

## Project Hash Auto-Detection

Token Audit automatically calculates the project hash from your current working directory:

```python
import hashlib
from pathlib import Path

cwd = Path.cwd().absolute()
project_hash = hashlib.sha256(str(cwd).encode()).hexdigest()
print(f"Project hash: {project_hash}")
```

### Manual Project Hash

If auto-detection fails, specify the hash directly:

```bash
token-audit collect --platform gemini-cli --project-hash abc123...
```

## What Gets Tracked

### Token Usage

Gemini CLI provides detailed token breakdowns per message:
- `input`: Input tokens (prompts, context)
- `output`: Model response tokens
- `cached`: Cached context tokens
- `thoughts`: Thinking/reasoning tokens (Gemini-specific)
- `tool`: Tokens for tool execution

### MCP Tool Calls

Only tools prefixed with `mcp__` are tracked:
- `mcp__zen__chat` → zen server, chat tool
- `mcp__jina__search_web` → jina server, search_web tool

Native Gemini tools (e.g., `read_file`, `google_web_search`) are excluded.

### Model Detection

The adapter detects models from the first `gemini` message:
- `gemini-3-pro-preview`
- `gemini-2.5-pro`, `gemini-2.5-pro-preview`
- `gemini-2.5-flash`, `gemini-2.5-flash-lite`
- `gemini-2.0-flash`, `gemini-2.0-flash-lite`

### Thinking Tokens

Gemini's extended thinking is tracked separately via `thoughts_tokens`:

```python
adapter = GeminiCLIAdapter(project="my-project")
adapter.process_session_file_batch(session_file)
print(f"Thinking tokens: {adapter.thoughts_tokens}")
```

## Example Output

```
$ token-audit collect --platform gemini-cli --batch --latest

[Gemini CLI] Processing: session-2025-11-07T05-10-0b04c358.json
  Total tokens: 13,175,835
  Input tokens: 7,499,154
  Output tokens: 82,257
  Cache read tokens: 5,594,424
  Thinking tokens: 52,540
  MCP calls: 8
  Model: Gemini 2.5 Pro
  Messages: 94

Session saved to: ~/.token-audit/sessions/gemini-cli/...
```

## Pricing Configuration

Gemini pricing is included by default. Edit `token-audit.toml` to customize:

```toml
[pricing.gemini]
# Gemini 3 Series
"gemini-3-pro-preview" = { input = 2.0, output = 12.0, cache_create = 0.50, cache_read = 0.20 }

# Gemini 2.5 Series
"gemini-2.5-pro" = { input = 1.25, output = 10.0, cache_create = 0.3125, cache_read = 0.125 }
"gemini-2.5-flash" = { input = 0.30, output = 2.50, cache_create = 0.075, cache_read = 0.03 }

# Gemini 2.0 Series
"gemini-2.0-flash" = { input = 0.10, output = 0.40, cache_create = 0.025, cache_read = 0.025 }
```

## Differences from OTEL Telemetry

Previous versions of Token Audit used Gemini's OpenTelemetry output. The new adapter:

1. **No OTEL setup required** - Reads native session files directly
2. **Simpler configuration** - No environment variables needed
3. **Better accuracy** - Uses authoritative session data
4. **Thinking tokens** - Full access to Gemini's reasoning tokens

## Troubleshooting

### No Sessions Found

1. Verify Gemini has created sessions:
   ```bash
   ls ~/.gemini/tmp/
   ```

2. Check the session directory for your project:
   ```bash
   # Calculate hash
   python -c "import hashlib; print(hashlib.sha256(str('$(pwd)').encode()).hexdigest())"
   # Then check
   ls ~/.gemini/tmp/<hash>/chats/
   ```

### Wrong Project Hash

Ensure you're in the correct directory when running Token Audit, or specify the hash:

```bash
token-audit collect --platform gemini-cli --project-hash <correct-hash>
```

### Model Not Detected

The session file must contain at least one `gemini` message with a `model` field:

```bash
cat ~/.gemini/tmp/.../chats/session-*.json | grep -o '"model":"[^"]*"' | head -1
```

### Multiple Projects

If you work in multiple projects, each has its own session history. List all:

```bash
python -m token_audit.gemini_cli_adapter --list-hashes
```
