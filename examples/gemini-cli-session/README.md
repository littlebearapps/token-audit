# Example Gemini CLI Session

This directory contains example session data from Gemini CLI.

## Files

- `session-sample.json` - Sample native JSON session file from Gemini CLI

## Session Details

- **Platform**: Gemini CLI
- **Model**: gemini-2.5-pro
- **Duration**: ~5 minutes
- **MCP Tools Used**: zen (chat, thinkdeep), brave-search (web)

## Session Format

Gemini CLI stores sessions as JSON files at `~/.gemini/tmp/<project_hash>/chats/session-*.json`:

```json
{
  "sessionId": "uuid",
  "projectHash": "sha256-hash",
  "startTime": "ISO8601",
  "messages": [
    {
      "id": "uuid",
      "timestamp": "ISO8601",
      "type": "gemini",
      "content": "...",
      "tokens": {
        "input": 100,
        "output": 200,
        "cached": 50,
        "thoughts": 150,
        "tool": 25,
        "total": 525
      },
      "model": "gemini-2.5-pro",
      "toolCalls": [...]
    }
  ]
}
```

## Key Features

- **No OTEL required** - Parses native session files directly
- **Thinking tokens** - Tracked separately via `tokens.thoughts`
- **Tool calls** - MCP tools detected by `mcp__` prefix

## Usage

```bash
# To track your own Gemini CLI sessions:
mcp-audit collect --platform gemini-cli

# To generate a report:
mcp-audit report ~/.mcp-audit/sessions/gemini_cli/
```

See [Gemini CLI Setup Guide](../../docs/gemini-cli-setup.md) for detailed instructions.
